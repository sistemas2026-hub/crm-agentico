# -*- coding: utf-8 -*-
"""
================================================================================
 MOTOR  -  el "coordinador": lee la config del tenant y ejecuta la conversacion
================================================================================

Por que existe
--------------
No habia ningun codigo que EJECUTARA lo que 'nucleo/config/schema.py' valida.
'soporte_wisphub.py' funciona, pero con sus propios diccionarios AREAS/
HERRAMIENTAS hardcodeados a mano -- no lee 'tenants/*.yaml'. Este modulo es
el primer motor que sí lo hace: recibe un TenantConfig ya cargado y un
nombre de rol, y arma todo lo demas (que herramientas, que prompt, que
modelo) desde ahi.

Por que no hace falta un framework multiagente aparte
-------------------------------------------------------
El prompt y el catalogo de herramientas ya varian por rol (Rol.descripcion,
Rol.puede_consultar). Eso ES la especializacion que un framework tipo CrewAI
daria con mas codigo encima: un "coordinador + subagentes" no es mas que
"un modelo, un prompt y un catalogo de tools distintos segun quien pregunta"
-- que es exactamente lo que este 'responder()' hace.

Alcance de esta version (ver plan)
-----------------------------------
- Solo el tipo de herramienta 'http' tiene ejecutor. Los demas levantan
  NotImplementedError explicito -- fallar ruidoso, no en silencio.
- Solo herramientas SIN argumentos libres del modelo (todo lo que necesitan
  viene de 'Herramienta.inyectar_sesion'). Un catalogo con argumentos que el
  modelo deba proponer necesita un campo de esquema que todavia no existe.
- La verificacion de identidad es por ROL (nivel maximo declarado), no por
  herramienta individual -- ver nucleo/seguridad/verificacion.py.
- No hay mecanismo de confirmacion humana asincrona para escrituras.
  'requiere_confirmacion' se valida en schema.py pero no se aplica aca --
  la unica escritura de 'cliente_final' hoy ('reiniciar_ont') usa en su
  lugar 'Herramienta.exige_previas' (precondiciones en codigo, fail-closed,
  ver _previas_no_cumplidas mas abajo), por decision explicita: reiniciar
  un equipo no necesita aprobacion humana si el diagnostico previo ya
  favorece hacerlo.
================================================================================
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta

from nucleo.herramientas import agregado as ejecutor_agregado
from nucleo.herramientas import http as ejecutor_http
from nucleo.modelo import cliente
from nucleo.recuperacion.prompt import construir_system
from nucleo.recuperacion.busqueda import (recuperar, bloque_de_contexto,
                                          registrar_sin_resultados)
from nucleo.seguridad import listas_blancas
from nucleo.seguridad.verificacion import nivel_requerido, es_factor_de_posesion


class ErrorMotor(Exception):
    pass


def herramientas_del_rol(config, rol_cfg):
    catalogo = {h.nombre: h for h in config.herramientas}
    return [catalogo[n] for n in rol_cfg.puede_consultar if n in catalogo]


def _esquema_openai(herramienta):
    if herramienta.confirma_identidad:
        # Segunda excepcion a "sin argumentos libres": no es un identificador,
        # es lo que el CLIENTE respondio (si/no) a la pregunta de confirmar
        # el nombre -- ver _ejecutar_confirmacion.
        return {
            "type": "function",
            "function": {
                "name": herramienta.nombre,
                "description": herramienta.descripcion,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirma": {
                            "type": "boolean",
                            "description": "true si el cliente confirmo que el "
                                          "nombre es el suyo, false si dijo que no.",
                        }
                    },
                    "required": ["confirma"],
                },
            },
        }
    if herramienta.verifica_identidad:
        # Unica excepcion a "sin argumentos libres": el dato para verificar
        # (ej. cedula) lo tiene que dar el cliente, no puede venir de sesion.
        campo = herramienta.campo_busqueda
        return {
            "type": "function",
            "function": {
                "name": herramienta.nombre,
                "description": herramienta.descripcion,
                "parameters": {
                    "type": "object",
                    "properties": {
                        campo: {"type": "string",
                               "description": f"Dato que dio el cliente para "
                                              f"verificar su identidad ({campo})."}
                    },
                    "required": [campo],
                },
            },
        }
    es_agregado = herramienta.tipo == "agregado"
    if herramienta.filtros_verificados or (es_agregado and (herramienta.agrupar_por or herramienta.periodo)):
        # Reusa 'filtros_verificados' (ya existia para herramientas tipo
        # 'agregado') tambien para 'http': cada entrada YA fue confirmada
        # contra la API real con el metodo del valor imposible -- ofrecerla
        # como argumento es seguro porque no es un filtro cualquiera, es uno
        # verificado. El modelo nunca propone un query-param crudo: propone
        # una de estas claves, y el motor traduce.
        propiedades = {}
        for clave, filtro in herramienta.filtros_verificados.items():
            if filtro.tipo == "enum" and filtro.valores:
                propiedades[clave] = {"type": "string", "enum": list(filtro.valores),
                                      "description": f"Filtro por {clave}."}
            else:
                propiedades[clave] = {"type": "string", "description": f"Filtro por {clave}."}
        if es_agregado and herramienta.agrupar_por:
            propiedades["agrupar_por"] = {
                "type": "string", "enum": herramienta.agrupar_por,
                "description": "Si se quiere el desglose por este campo en "
                               "vez de un solo total."}
        if es_agregado and herramienta.periodo:
            propiedades["periodo"] = {
                "type": "string",
                "description": "Rango de fechas: 'AAAA-MM' o "
                               "'AAAA-MM-DD a AAAA-MM-DD'. Si se omite, se "
                               "usa el periodo por defecto de la API."}
        return {
            "type": "function",
            "function": {
                "name": herramienta.nombre,
                "description": herramienta.descripcion,
                "parameters": {"type": "object", "properties": propiedades, "required": []},
            },
        }
    # Ver "Alcance" arriba: el resto, sin argumentos libres por ahora.
    return {
        "type": "function",
        "function": {
            "name": herramienta.nombre,
            "description": herramienta.descripcion,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


def _ejecutar_verificacion(herramienta, sesion, argumentos_modelo: dict,
                           tenant: str | None = None) -> dict:
    """
    Ejecuta una herramienta 'verifica_identidad=True'. Nunca deja pasar el
    registro crudo del cliente hacia el modelo: solo actualiza 'sesion' y
    devuelve un resultado minimo para que el modelo redacte sobre ESO, nunca
    sobre el dato real.

    Encontrar UN cliente por el dato buscado NO alcanza para verificar --
    deja el candidato en 'pendiente' (Sesion.id_cliente_pendiente) y el
    nombre para que el modelo se lo lea al cliente y le pida confirmar.
    'verificado' sigue en False hasta que _ejecutar_confirmacion cierre el
    segundo paso; el nombre es el UNICO campo que se deja pasar a proposito,
    justamente para poder pedir esa confirmacion.
    """
    campo = herramienta.campo_busqueda
    valor = str((argumentos_modelo or {}).get(campo, "")).strip()
    if not valor:
        return {"verificado": False, "motivo": "no se recibio el dato a verificar"}

    crudo = ejecutor_http.ejecutar(herramienta, {campo: valor}, tenant)
    filas = crudo.get("results", []) if isinstance(crudo, dict) else crudo
    if not isinstance(filas, list):
        filas = []
    # Defensa: confirmar que el valor buscado de verdad aparece en el campo,
    # no confiar en que el filtro de la API hizo bien su trabajo (mismo
    # principio que el resto del proyecto: verificar, no asumir).
    filas = [f for f in filas if valor in str(f.get(campo) or "")]

    if not filas:
        if sesion is not None:
            sesion.verificado = False
        return {"verificado": False, "motivo": "no encontrado"}

    if len(filas) > 1:
        if sesion is not None:
            sesion.verificado = False
            sesion.candidatos = [str(f["id_servicio"]) for f in filas]
        return {"verificado": False, "motivo": "ambiguo",
               "instruccion_interna": "Hay mas de un cliente con ese dato. "
                   "Pedile otro dato adicional para desambiguar -- nunca "
                   "elijas vos cual es."}

    if sesion is not None:
        sesion.id_cliente_pendiente = str(filas[0]["id_servicio"])
        sesion.interfaz_lan_pendiente = filas[0].get("interfaz_lan") or None
        sesion.sn_onu_pendiente = filas[0].get("sn_onu") or None
        sesion.nombre_pendiente = filas[0].get("nombre") or None
        sesion.candidatos = []
    return {
        "verificado": False,
        "nombre_a_confirmar": sesion.nombre_pendiente if sesion else None,
        "instruccion_interna": "Todavia NO esta verificado. Decile al cliente "
            "que el servicio figura a nombre de 'nombre_a_confirmar' y "
            "pedile que confirme si es el/ella. Nunca reveles ningun otro "
            "dato todavia. Cuando responda, llama a confirmar_identidad con "
            "confirma=true si dijo que si, confirma=false si dijo que no.",
    }


def _ejecutar_confirmacion(sesion, argumentos_modelo: dict) -> dict:
    """
    Cierra (o descarta) la verificacion en dos pasos que dejo pendiente
    _ejecutar_verificacion. Es el UNICO lugar que marca 'sesion.verificado
    = True' -- encontrar el candidato por cedula ya no alcanza por si solo.
    """
    if sesion is None or not sesion.id_cliente_pendiente:
        return {"error": "No hay ninguna verificacion pendiente de confirmar."}

    confirma = bool((argumentos_modelo or {}).get("confirma"))

    if not confirma:
        # Se descarta: puede ser una cedula mal tipeada que por coincidencia
        # matcheo a otra persona. Se limpia para que el cliente pueda
        # reintentar de cero, no queda a mitad de camino.
        sesion.id_cliente_pendiente = None
        sesion.nombre_pendiente = None
        sesion.interfaz_lan_pendiente = None
        sesion.sn_onu_pendiente = None
        return {"verificado": False, "motivo": "el cliente no confirmo el nombre",
               "instruccion_interna": "Pedile de nuevo el numero de cedula, "
                   "puede haber un error de tipeo."}

    sesion.verificado = True
    sesion.nivel = max(sesion.nivel, 1)
    sesion.id_cliente = sesion.id_cliente_pendiente
    sesion.nombre = sesion.nombre_pendiente
    sesion.interfaz_lan = sesion.interfaz_lan_pendiente
    sesion.sn_onu = sesion.sn_onu_pendiente
    sesion.id_cliente_pendiente = None
    sesion.nombre_pendiente = None
    sesion.interfaz_lan_pendiente = None
    sesion.sn_onu_pendiente = None
    # Reproducido en vivo (agosto 2026): sin esta instruccion, el modelo a
    # veces inventaba que "no tenia la herramienta para cerrar la
    # verificacion por este canal" y escalaba sin necesidad -- pese a que
    # 'verificado' ya es True en este mismo punto. Es la UNICA rama de este
    # archivo que dejaba al modelo sin instruccion_interna; el resto (arriba
    # y en _ejecutar_verificacion) ya la tiene. Se nombran las dos excusas
    # puntuales que aparecieron en produccion, no solo "ya estas verificado":
    # negarlas explicitamente es lo que evita que el modelo las repita.
    return {"verificado": True,
           "instruccion_interna": "Verificacion CERRADA en este mismo paso, "
               "sin nada pendiente: no existe ningun paso adicional, ni "
               "ninguna limitacion de este canal (WhatsApp u otro) que te "
               "impida seguir. Decile al cliente en una frase breve que ya "
               "quedo verificado, y en el MISMO mensaje segui de inmediato "
               "con el problema que te habia contado antes de pedirle la "
               "cedula, usando las herramientas que tengas para su rol. "
               "Nunca digas que falta un paso, que el canal no lo permite, "
               "ni escales a un humano solo por este motivo."}


def _previas_no_cumplidas(herramienta, historial: list[dict]) -> list[str]:
    """Nombres de las herramientas de 'exige_previas' (schema.py) que
    TODAVIA no dieron el resultado favorable declarado, en esta conversacion.
    Vacio = todo cumplido. Mira la llamada MAS RECIENTE de cada herramienta
    requerida en 'historial' -- una que cumplio hace varios mensajes pero ya
    no representa el estado actual no cuenta (ej. la senal pudo haber
    empeorado despues)."""
    faltantes = []
    for previa in herramienta.exige_previas:
        cumplida = False
        for msg in historial:
            if msg.get("role") != "tool" or msg.get("name") != previa.herramienta:
                continue
            try:
                dato = json.loads(msg.get("content") or "null")
            except (TypeError, ValueError):
                continue
            if isinstance(dato, dict):
                # No se corta al primer match: la ULTIMA ocurrencia en el
                # historial (mas reciente) es la que decide.
                cumplida = dato.get(previa.campo) == previa.valor
        if not cumplida:
            faltantes.append(previa.herramienta)
    return faltantes


def _veces_ejecutada(herramienta, historial: list[dict]) -> int:
    """Cuantas veces ya corrio 'herramienta' en esta conversacion -- para
    Herramienta.limite_por_conversacion."""
    return sum(1 for msg in historial
              if msg.get("role") == "tool" and msg.get("name") == herramienta.nombre)


def _ejecutar_tool(herramienta, sesion, argumentos_modelo: dict,
                   tenant: str | None = None,
                   variables_tenant: dict | None = None) -> dict | list:
    argumentos_modelo = argumentos_modelo or {}

    if herramienta.tipo == "agregado":
        # No pasa por la traduccion de mas abajo: agregado necesita los
        # valores CRUDOS del modelo (incluido 'agrupar_por'/'periodo', que no
        # son filtros) para decidir agrupamiento y rango -- hace su propia
        # traduccion de filtros adentro.
        return ejecutor_agregado.ejecutar(herramienta, argumentos_modelo, tenant)

    argumentos = {}

    # Solo se traducen los filtros DECLARADOS (fail-closed): si el modelo
    # propone una clave que no esta en 'filtros_verificados', se ignora --
    # no se manda tal cual al query string. Cada filtro ya fue confirmado
    # contra la API real (metodo del valor imposible) antes de entrar aca.
    for clave, filtro in herramienta.filtros_verificados.items():
        valor = argumentos_modelo.get(clave)
        if valor is None:
            continue
        if filtro.tipo == "enum" and filtro.valores:
            if valor not in filtro.valores:
                continue  # el modelo inventa un valor fuera del enum -- se descarta
            argumentos[filtro.param] = filtro.valores[valor]
        else:
            argumentos[filtro.param] = valor

    # Constantes del tenant, nunca decididas por el modelo (ver el comentario
    # de 'argumentos_fijos' en schema.py).
    argumentos.update(herramienta.argumentos_fijos)

    # Fechas calculadas en el momento (ver 'fechas_automaticas' en
    # schema.py). Formato DD/MM/AAAA HH:MM: es lo que exige WispHub hoy, el
    # unico proveedor con esta necesidad -- si aparece otro con un formato
    # distinto, esto pasa a ser un campo de config en vez de una constante.
    for arg_llamada, dias in herramienta.fechas_automaticas.items():
        fecha = datetime.now() + timedelta(days=dias)
        argumentos[arg_llamada] = fecha.strftime("%d/%m/%Y %H:%M")

    # El modelo puede proponer estas claves; se sobrescriben siempre con la
    # sesion verificada -- ver el comentario de 'inyectar_sesion' en schema.py.
    #
    # Un valor VACIO en la sesion se OMITE, no se manda como null. Un campo
    # opcional que la API acepta ausente no siempre acepta un nulo explicito,
    # y ahi la diferencia deja de ser cosmetica: verificado contra WispHub
    # (agosto 2026), 'interfaz' ausente o '' responde 202, pero
    # {"interfaz": null} devuelve 400 "Este campo no puede ser nulo". El
    # sintoma era un cliente al que no se le podia diagnosticar la conexion --
    # y 'interfaz_lan' vacio es NORMAL, no un dato faltante (ver skill
    # wisphub-api), asi que le pasaba a muchos.
    #
    # Se descarta el vacio y no solo el None: el propio motor ya convierte ''
    # en None al verificar la identidad, y quien escriba el YAML no deberia
    # tener que saber cual de las dos formas llega.
    for arg_llamada, atributo_sesion in herramienta.inyectar_sesion.items():
        valor = getattr(sesion, atributo_sesion, None)
        if valor is None or valor == "":
            argumentos.pop(arg_llamada, None)
        else:
            argumentos[arg_llamada] = valor

    if herramienta.tipo == "http":
        if herramienta.asincrona:
            return ejecutor_http.ejecutar_asincrono(herramienta, argumentos,
                                                    tenant=tenant,
                                                    variables_tenant=variables_tenant)
        return ejecutor_http.ejecutar(herramienta, argumentos, tenant, variables_tenant)
    raise NotImplementedError(
        f"Tipo de herramienta '{herramienta.tipo}' aun no tiene ejecutor en nucleo/.")


def _enmascarar(argumentos: dict) -> dict:
    """
    Para asistente.tool_calls.parametros -- deja ver QUE se consulto (nombre
    de la clave) sin guardar el dato completo (cedula, id_servicio...). Los
    ultimos 4 caracteres alcanzan para que un supervisor reconozca "es el
    mismo cliente de siempre" sin que la auditoria termine siendo una copia
    de los datos del cliente.
    """
    out = {}
    for clave, valor in (argumentos or {}).items():
        texto = str(valor)
        out[clave] = f"...{texto[-4:]}" if len(texto) > 4 else texto
    return out


def _tool_call_a_dict(nombre: str, argumentos: dict, id_llamada: str) -> dict:
    return {"id": id_llamada, "type": "function",
            "function": {"name": nombre, "arguments": argumentos}}


# Visto en vivo (agosto 2026): el modelo, sin ninguna herramienta real para
# lo que queria hacer (un cliente pregunto por un servicio que la empresa no
# ofrece -- TV, este ISP no la tiene), fabrico una llamada a herramienta
# INEXISTENTE como texto plano en vez de usar el tool-calling real de la API
# -- con tokens de control de su propio vocabulario (<｜｜DSML｜｜tool_calls>,
# barra vertical ancha U+FF5C) que se filtraron directo al cliente. El
# prompt ya le pide no inventar (ver construir_system), pero esto es
# fail-closed en codigo: nunca se le muestra al cliente un intento de
# llamada a herramienta que no paso por el tool-calling real.
_RE_FUGA_TOOL_CALL = re.compile(r"<\s*/?\s*｜+[^>]*>")

# Visto en vivo con DeepSeek (agosto 2026): despues de que una herramienta de
# verificacion devuelve {"verificado": true}, la redaccion final a veces
# repite el valor crudo del campo -- la burbuja del cliente decia
# literalmente "true", sin ninguna frase. RF-07 prohibe mostrar el dato
# crudo; esto es el mismo fail-closed en codigo que _RE_FUGA_TOOL_CALL, para
# un tipo de fuga distinto (no un token de control, sino el propio valor de
# un resultado de herramienta sin redactar).
_RE_RESPUESTA_CRUDA = re.compile(r"^(true|false|null|\d+(\.\d+)?|[\{\[].*[\}\]])$",
                                 re.IGNORECASE)


def _sanitizar(texto: str) -> str:
    limpio = _RE_FUGA_TOOL_CALL.sub("", texto)
    limpio = re.sub(r"\n{3,}", "\n\n", limpio).strip()
    return limpio


def _redactar(referencia_modelo: str, historial: list[dict], temperatura: float,
              intentos: int = 3) -> str:
    """
    Redaccion final despues de que el modelo ya uso las herramientas que
    necesitaba. Reintenta si viene vacia -- visto en vivo con DeepSeek dos
    veces (agosto 2026): el primer intento post-tool-call a veces devuelve
    contenido en blanco. El primer caso (blanco en el intento INICIAL, sin
    tool calls todavia) ya se reintentaba en responder(); a este, que pasa
    DESPUES de una herramienta real (ej. verificar_identidad_por_cedula), le
    faltaba la misma proteccion -- el cliente se quedaba con una burbuja
    vacia y tenia que escribir de nuevo para obtener respuesta.

    Tambien reintenta si la redaccion es un valor crudo sin frase (ver
    _RE_RESPUESTA_CRUDA) -- mismo motivo que la burbuja vacia: es una
    respuesta que no le sirve al cliente, asi que se trata igual, no como un
    resultado valido que solo hay que sanitizar.
    """
    for _ in range(intentos):
        resp = cliente.chat(referencia_modelo, historial, tools=None, temperatura=temperatura)
        limpio = _sanitizar(resp.contenido)
        if limpio and not _RE_RESPUESTA_CRUDA.match(limpio):
            historial.append({"role": "assistant", "content": limpio})
            return limpio
    historial.append({"role": "assistant", "content": ""})
    return "No pude terminar de redactar la respuesta. ¿Podés reformular tu mensaje?"


def responder(config, nombre_rol: str, mensaje: str, historial: list[dict],
              sesion) -> tuple[str, list[dict]]:
    """
    'sesion' es una nucleo.seguridad.verificacion.Sesion (o None si el rol no
    exige verificacion). 'historial' se muta in-place -- el llamador lo
    conserva entre turnos.

    Devuelve (respuesta, registro_herramientas). El registro es una fila por
    herramienta invocada este turno -- nombre, parametros enmascarados,
    exito, duracion -- para que nucleo/canales/api.py lo guarde en
    asistente.tool_calls despues de resolver el conversation_id (que todavia
    no existe en este punto: la conversacion se crea/reusa recien al
    persistir el turno). Es la base de "ver proceso" en /conversaciones: que
    hizo el agente, en que orden, sin que el motor sepa que existe esa
    pantalla.
    """
    rol_cfg = config.roles.get(nombre_rol)
    if rol_cfg is None:
        raise ErrorMotor(f"Rol '{nombre_rol}' no existe en la configuracion del tenant.")

    registro: list[dict] = []

    if not historial:
        historial.append({"role": "system", "content": construir_system(config, nombre_rol)})
    historial.append({"role": "user", "content": mensaje})

    herramientas = herramientas_del_rol(config, rol_cfg)
    catalogo_openai = [_esquema_openai(h) for h in herramientas]

    # --- RAG: que dice la documentacion interna sobre esto ---------------------
    # Va DESPUES del catalogo de herramientas porque la decision de que hacer
    # cuando el corpus no responde depende de si el rol tiene con que buscar el
    # dato en otro lado.
    #
    # Nunca rompe el turno: si Ollama no responde o la base falla, se sigue sin
    # contexto documental. Peor es no atender.
    try:
        fragmentos, mejor = recuperar(config, config.identidad.slug, nombre_rol, mensaje)
    except Exception as e:
        print(f"[rag] no se pudo recuperar contexto: {e}")
        fragmentos, mejor = [], None

    if fragmentos:
        citar_fuente = rol_cfg.orientado_a != "cliente_final"
        historial.append({"role": "system",
                          "content": bloque_de_contexto(fragmentos, citar_fuente)})
    else:
        registrar_sin_resultados(config.identidad.slug, mensaje, nombre_rol, mejor)
        # Solo se corta el turno si NO hay herramientas: ahi no queda nada con
        # que responder y llamar al modelo es pedirle que invente (RF-07).
        #
        # Con herramientas se sigue: "cuanto debe el cliente 1234" no esta en
        # ninguna guia y se responde consultando WispHub. Aplicar el corte a
        # todo dejaria al asistente mudo para la mayoria de las preguntas
        # reales, que es lo contrario de lo que busca la regla. El mensaje
        # configurado lo confirma: habla de "la documentacion disponible".
        if not herramientas:
            respuesta = config.rag.mensaje_sin_resultados.strip()
            historial.append({"role": "assistant", "content": respuesta})
            return respuesta, registro

    referencia_decision = config.llm.overrides.get(f"rol:{nombre_rol}",
                                                    config.llm.modelo_por_defecto)
    referencia_redaccion = config.llm.modelo_redaccion or referencia_decision

    nivel_exigido = nivel_requerido(rol_cfg, config.seguridad) if rol_cfg.orientado_a == "cliente_final" else 0
    # Sin un telefono real de por medio, el identificador del canal (ej. un
    # BSUID de WhatsApp) no es un factor de posesion -- cualquiera que
    # escriba desde esa cuenta pasaria la barra igual. Se exige nivel 1 ANTES
    # de cualquier herramienta, no solo de las marcadas sensibles: es la
    # unica forma de saber quien es, y sin esto la conversacion queda para
    # siempre como "sin identificar" en /conversaciones si nunca toca un
    # recurso protegido.
    if (rol_cfg.orientado_a == "cliente_final" and sesion is not None
            and not es_factor_de_posesion(sesion.identificador_canal)):
        nivel_exigido = max(nivel_exigido, 1)

    hubo_llamadas = False
    iteraciones = 0
    while iteraciones < config.llm.limite_iteraciones_agente:
        iteraciones += 1
        resp = cliente.chat(referencia_decision, historial,
                            tools=catalogo_openai or None, temperatura=config.llm.temperatura)

        if not resp.llamadas:
            if resp.contenido.strip():
                if not hubo_llamadas:
                    limpio = _sanitizar(resp.contenido)
                    historial.append({"role": "assistant", "content": limpio})
                    return limpio, registro
                break  # ya no pide mas herramientas: pasa a redaccion final
            if hubo_llamadas:
                break  # sin texto pero ya hubo tools: igual pasa a redaccion final
            # Sin texto y sin tool call en el primer intento: visto en vivo con
            # DeepSeek en el primer turno de una conversacion nueva (respuesta
            # en blanco, el cliente tenia que reescribir el mismo mensaje para
            # obtener contestacion). Se reintenta en vez de devolverle al
            # cliente una burbuja vacia -- acotado por 'limite_iteraciones_agente'.
            continue

        hubo_llamadas = True
        tool_calls = [_tool_call_a_dict(l.nombre, l.argumentos, f"call_{i}")
                     for i, l in enumerate(resp.llamadas)]
        historial.append({"role": "assistant", "content": resp.contenido,
                          "tool_calls": tool_calls})

        for i, llamada in enumerate(resp.llamadas):
            herramienta = next((h for h in herramientas if h.nombre == llamada.nombre), None)
            t0 = time.monotonic()
            codigo_error = None

            if herramienta is None:
                # El catalogo que vio el modelo ya estaba acotado al rol, pero
                # puede inventar un nombre -- el permiso lo decide el codigo.
                salida = {"error": f"El rol '{nombre_rol}' no tiene la "
                                   f"herramienta '{llamada.nombre}'."}
                codigo_error = "HERRAMIENTA_DESCONOCIDA"
            elif herramienta.verifica_identidad:
                # Se ofrece SIEMPRE, este o no verificada la sesion todavia --
                # es justamente como se verifica. Nunca pasa por el gate.
                salida = _ejecutar_verificacion(herramienta, sesion, llamada.argumentos,
                                                config.identidad.slug)
            elif herramienta.confirma_identidad:
                # Idem: tiene que poder llamarse ANTES de que la sesion este
                # verificada -- es lo que la termina de verificar.
                salida = _ejecutar_confirmacion(sesion, llamada.argumentos)
            elif rol_cfg.orientado_a == "cliente_final" and (sesion is None or sesion.nivel < nivel_exigido):
                salida = {"error": "IDENTIDAD_NO_VERIFICADA",
                         "instruccion_interna": "No muestres ningun dato. "
                             "Pedile al cliente el dato que falta para "
                             "verificar su identidad antes de continuar."}
                codigo_error = "IDENTIDAD_NO_VERIFICADA"
            elif (faltantes := _previas_no_cumplidas(herramienta, historial)):
                # Fail-closed en codigo, no aprobacion humana -- ver
                # Precondicion en schema.py. Ninguna herramienta actual la
                # necesita salvo 'reiniciar_ont'; generico por si aparece
                # otra accion con el mismo requisito.
                salida = {"error": "PRECONDICION_NO_CUMPLIDA",
                         "instruccion_interna": "Todavia no ejecutaste (o no "
                             "dio un resultado favorable) esto antes de "
                             f"intentar '{herramienta.nombre}': "
                             f"{', '.join(faltantes)}. Llamalas primero -- "
                             "si el resultado no es favorable, esta "
                             "herramienta no es el siguiente paso, segui el "
                             "protocolo alternativo en vez de insistir."}
                codigo_error = "PRECONDICION_NO_CUMPLIDA"
            elif herramienta.limite_por_conversacion is not None and _veces_ejecutada(
                    herramienta, historial) >= herramienta.limite_por_conversacion:
                salida = {"error": "LIMITE_DE_CONVERSACION",
                         "instruccion_interna": f"'{herramienta.nombre}' ya se "
                             "uso el maximo de veces permitidas en esta "
                             "conversacion. No la repitas -- si el cliente "
                             "insiste, decile que un colaborador humano va a "
                             "seguir el caso."}
                codigo_error = "LIMITE_DE_CONVERSACION"
            else:
                try:
                    crudo = _ejecutar_tool(herramienta, sesion, llamada.argumentos,
                                          config.identidad.slug, config.variables_tenant)
                    salida = listas_blancas.filtrar_campos(rol_cfg, herramienta.nombre, crudo)
                except Exception as e:
                    # No tumba el turno: el modelo recibe un error legible y
                    # puede decirle al cliente que hubo un problema, en vez de
                    # que /chat completo se caiga con un 500.
                    salida = {"error": "No se pudo completar la consulta en este momento."}
                    codigo_error = f"{type(e).__name__}: {e}"[:200]

            # asistente.tool_calls: fila por invocacion, para la auditoria en
            # /conversaciones (nucleo/canales/api.py la persiste despues, una
            # vez resuelto el conversation_id). n_registros solo tiene
            # sentido para una lista (results de una consulta); para
            # cualquier otra forma queda None a proposito, no un 0 enganoso.
            #
            # IDENTIDAD_NO_VERIFICADA se excluye a proposito: no es un fallo,
            # es el gate de seguridad frenando ANTES de llamar a nada (0ms,
            # ninguna API externa de por medio) -- es normal que el modelo
            # pruebe una herramienta antes de tener con que verificar, y
            # registrarlo como una X en "Ver proceso" parece un error cuando
            # en realidad la proteccion funciono como debia.
            if codigo_error != "IDENTIDAD_NO_VERIFICADA":
                registro.append({
                    "herramienta": llamada.nombre,
                    "parametros": _enmascarar(llamada.argumentos),
                    "exito": codigo_error is None,
                    "n_registros": len(salida) if isinstance(salida, list) else None,
                    "codigo_error": codigo_error,
                    "duracion_ms": int((time.monotonic() - t0) * 1000),
                    "es_escritura": bool(herramienta and not herramienta.solo_lectura),
                })

            historial.append({"role": "tool", "name": llamada.nombre,
                              "tool_call_id": f"call_{i}",
                              "content": json.dumps(salida, ensure_ascii=False)})

    if hubo_llamadas:
        return _redactar(referencia_redaccion, historial, config.llm.temperatura), registro
    return "No pude completar la consulta en el numero de pasos permitido.", registro
