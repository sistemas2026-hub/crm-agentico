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
- No hay mecanismo de confirmacion humana asincrona (solo aplica a
  herramientas de escritura; cliente_final hoy solo tiene una de lectura).
================================================================================
"""

from __future__ import annotations

import json
import time

from nucleo.herramientas import agregado as ejecutor_agregado
from nucleo.herramientas import http as ejecutor_http
from nucleo.modelo import cliente
from nucleo.recuperacion.prompt import construir_system
from nucleo.recuperacion.busqueda import (recuperar, bloque_de_contexto,
                                          registrar_sin_resultados)
from nucleo.seguridad import listas_blancas
from nucleo.seguridad.verificacion import nivel_requerido


class ErrorMotor(Exception):
    pass


def herramientas_del_rol(config, rol_cfg):
    catalogo = {h.nombre: h for h in config.herramientas}
    return [catalogo[n] for n in rol_cfg.puede_consultar if n in catalogo]


def _esquema_openai(herramienta):
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
    devuelve un resultado minimo (verificado/ambiguo/no encontrado) para que
    el modelo redacte sobre ESO, nunca sobre el dato real.
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
        sesion.verificado = True
        sesion.nivel = max(sesion.nivel, 1)
        sesion.id_cliente = str(filas[0]["id_servicio"])
        sesion.interfaz_lan = filas[0].get("interfaz_lan") or None
        sesion.candidatos = []
    return {"verificado": True}


def _ejecutar_tool(herramienta, sesion, argumentos_modelo: dict,
                   tenant: str | None = None) -> dict | list:
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

    # El modelo puede proponer estas claves; se sobrescriben siempre con la
    # sesion verificada -- ver el comentario de 'inyectar_sesion' en schema.py.
    for arg_llamada, atributo_sesion in herramienta.inyectar_sesion.items():
        argumentos[arg_llamada] = getattr(sesion, atributo_sesion, None)

    if herramienta.tipo == "http":
        if herramienta.asincrona:
            return ejecutor_http.ejecutar_asincrono(herramienta, argumentos,
                                                    tenant=tenant)
        return ejecutor_http.ejecutar(herramienta, argumentos, tenant)
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


def _redactar(referencia_modelo: str, historial: list[dict], temperatura: float) -> str:
    resp = cliente.chat(referencia_modelo, historial, tools=None, temperatura=temperatura)
    historial.append({"role": "assistant", "content": resp.contenido})
    return resp.contenido


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

    hubo_llamadas = False
    iteraciones = 0
    while iteraciones < config.llm.limite_iteraciones_agente:
        iteraciones += 1
        resp = cliente.chat(referencia_decision, historial,
                            tools=catalogo_openai or None, temperatura=config.llm.temperatura)

        if not resp.llamadas:
            if not hubo_llamadas:
                historial.append({"role": "assistant", "content": resp.contenido})
                return resp.contenido, registro
            break  # ya no pide mas herramientas: pasa a redaccion final

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
            elif rol_cfg.orientado_a == "cliente_final" and (sesion is None or sesion.nivel < nivel_exigido):
                salida = {"error": "IDENTIDAD_NO_VERIFICADA",
                         "instruccion_interna": "No muestres ningun dato. "
                             "Pedile al cliente el dato que falta para "
                             "verificar su identidad antes de continuar."}
                codigo_error = "IDENTIDAD_NO_VERIFICADA"
            else:
                try:
                    crudo = _ejecutar_tool(herramienta, sesion, llamada.argumentos,
                                          config.identidad.slug)
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
