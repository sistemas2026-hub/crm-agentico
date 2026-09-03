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
import uuid
from datetime import datetime, timedelta

from nucleo.config.schema import _sin_tildes
from nucleo.herramientas import agregado as ejecutor_agregado
from nucleo.herramientas import http as ejecutor_http
from nucleo.herramientas import incidentes as ejecutor_incidentes
from nucleo.herramientas import estabilidad as ejecutor_estabilidad
from nucleo.herramientas import wifi as ejecutor_wifi
from nucleo.herramientas import informes
from nucleo.modelo import cliente
from nucleo.modelo import tuteo
from nucleo.persistencia import db as persistencia
from nucleo.habilidades import catalogo as catalogo_habilidades
from nucleo.recuperacion.prompt import construir_system
from nucleo.recuperacion.busqueda import (recuperar, bloque_de_contexto,
                                          registrar_sin_resultados)
from nucleo.seguridad import listas_blancas
from nucleo.seguridad import redaccion
from nucleo.seguridad import salida as guardia_salida
from nucleo.seguridad.verificacion import Sesion, nivel_requerido, es_factor_de_posesion


class ErrorMotor(Exception):
    pass


class FaltaIdentidadEnSesion(ErrorMotor):
    """
    La sesion no tiene un campo que la herramienta declaro imprescindible.

    Es una EXCEPCION y no un valor de retorno para que ningun camino pueda
    ignorarla por descuido: lo que esta en juego es que una consulta salga sin
    el filtro que la acota a un cliente, y eso no devuelve un error -- devuelve
    a todos los demas. Ver 'inyectados_obligatorios' en schema.py.
    """

    def __init__(self, herramienta: str, faltantes: list[str]):
        self.herramienta = herramienta
        self.faltantes = faltantes
        super().__init__(
            f"'{herramienta}' necesita {faltantes} de la sesion verificada y "
            f"no lo tiene: la llamada no sale.")


# 'formato' que el modelo puede pedir en una herramienta 'agregado'
# exportable -> (funcion generadora, mime). Un solo lugar para agregar un
# formato nuevo (ver _esquema_openai, que arma el enum desde estas mismas
# claves) sin tocar la logica de ejecucion.
_GENERADORES_INFORME = {
    "excel": (informes.generar_excel, informes.MIME_XLSX),
    "pdf": (informes.generar_pdf, informes.MIME_PDF),
}


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
    if herramienta.deriva_rol:
        # El modelo SI propone 'area', pero acotada al enum declarado en el
        # YAML (areas_destino) -- nunca un nombre de rol libre. La
        # coherencia global (schema.py) ya garantizo que cada uno de esos
        # nombres es un rol real, orientado_a=cliente_final.
        propiedades = {
            "area": {"type": "string", "enum": herramienta.areas_destino,
                     "description": "A que area pasar el resto de la conversacion."},
        }
        requeridos = ["area"]
        if herramienta.servicios_reportables:
            # 'no_lo_dijo' es la razon de ser de este argumento, no un relleno:
            # es lo que frena las acciones que interrumpen el servicio (ver
            # Herramienta.exige_turno_propio). Por eso se pide SIEMPRE y con
            # la consigna de no adivinar -- un 'internet' inventado sobre un
            # "me quede sin servicio" habilita un reinicio que quizas le corta
            # el unico servicio que le andaba.
            propiedades["servicio"] = {
                "type": "string",
                "enum": list(herramienta.servicios_reportables) + ["no_lo_dijo"],
                "description": "Que servicio dijo el CLIENTE que le falla, con "
                               "SUS palabras. Usa 'no_lo_dijo' si no lo "
                               "aclaro ('me quede sin servicio', 'no me "
                               "funciona', 'no tengo señal'): no lo deduzcas "
                               "ni elijas el mas probable.",
            }
            requeridos.append("servicio")
        return {
            "type": "function",
            "function": {
                "name": herramienta.nombre,
                "description": herramienta.descripcion,
                "parameters": {
                    "type": "object",
                    "properties": propiedades,
                    "required": requeridos,
                },
            },
        }
    if herramienta.sondea_api:
        # Cuarta excepcion a "sin argumentos libres" -- ver
        # Herramienta.sondea_api (schema.py) para el porque. 'auth_ref' es
        # el NOMBRE de un secreto ya guardado, nunca la clave: el modelo no
        # tiene forma de proponer un valor de credencial aca.
        return {
            "type": "function",
            "function": {
                "name": herramienta.nombre,
                "description": herramienta.descripcion,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string",
                               "description": "URL completa (https) del endpoint a sondear."},
                        "auth_ref": {"type": "string",
                                    "description": "Nombre del secreto YA GUARDADO con la "
                                        "clave de esta API (no el valor). Si la API no "
                                        "necesita auth, omitir."},
                        "auth_header": {"type": "string",
                                       "description": "Nombre del header de auth. Por "
                                           "defecto 'Authorization'."},
                        "auth_esquema": {"type": "string",
                                        "description": "Prefijo antes de la clave en el "
                                            "header, ej. 'Bearer' o 'Api-Key'. Vacio si "
                                            "la API no usa prefijo."},
                        "params": {"type": "string",
                                  "description": "Query params a probar, como texto JSON. "
                                      "Ej: '{\"estado\": \"1\"}'. Omitir para la llamada base."},
                    },
                    "required": ["url"],
                },
            },
        }
    if herramienta.propone_herramienta:
        # Quinta excepcion. El modelo arma el borrador completo -- pero
        # NUNCA se activa solo con esto: queda 'pendiente' hasta que un
        # humano lo apruebe (ver Herramienta.propone_herramienta).
        return {
            "type": "function",
            "function": {
                "name": herramienta.nombre,
                "description": herramienta.descripcion,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "descripcion_pedido": {"type": "string",
                            "description": "Lo que el ADMIN pidio conectar, en sus palabras."},
                        "sondeo": {"type": "string",
                            "description": "Texto JSON con la evidencia real del sondeo: "
                                "URL(s) probadas y lo que devolvieron. Para que quien "
                                "aprueba pueda auditar que se probo de verdad."},
                        "herramienta_propuesta": {"type": "string",
                            "description": "Texto JSON con el borrador de Herramienta "
                                "(mismos campos que nucleo/config/schema.py: nombre, "
                                "tipo, endpoint, filtros_verificados, etc.) armado a "
                                "partir de lo que el sondeo confirmo -- nunca de lo que "
                                "el ADMIN supone sin probarlo."},
                    },
                    "required": ["descripcion_pedido", "sondeo", "herramienta_propuesta"],
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
    if herramienta.filtros_verificados or (es_agregado and (
            herramienta.agrupar_por or herramienta.periodo or herramienta.exportable)):
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
        if es_agregado and herramienta.exportable:
            propiedades["formato"] = {
                "type": "string", "enum": ["texto", *_GENERADORES_INFORME],
                "description": "'excel' o 'pdf' SOLO si el usuario pidio "
                               "explicitamente un archivo/reporte descargable "
                               "(ej. 'mandame un excel', 'quiero el reporte en "
                               "pdf'). Si no especifico el tipo de archivo, "
                               "usa 'excel' por defecto. Si solo pregunto un "
                               "numero, usa 'texto' (o no lo indiques)."}
        return {
            "type": "function",
            "function": {
                "name": herramienta.nombre,
                "description": herramienta.descripcion,
                "parameters": {"type": "object", "properties": propiedades,
                               "required": herramienta.requeridos},
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


def _recuperar_campos_de_sesion(sesion, herramienta, crudo) -> None:
    """
    Rellena un campo persistible que la sesion perdio, leyendolo de la
    respuesta cruda de una herramienta que ya se llamo igual.

    Esos campos (Sesion.CAMPOS_PERSISTIBLES: el serial de la ONU, la interfaz)
    se capturan al verificar la identidad, y esa era la UNICA oportunidad. Una
    conversacion que sigue abierta pero cuya captura se perdio quedaba ciega
    para siempre: verificada, atendida con normalidad, y con todas las
    herramientas que dependen del serial fallando en silencio detras. El
    cliente recibia el protocolo alternativo -- "desconecta el router 30
    segundos" -- en vez del diagnostico y el reinicio remoto que si estaban a
    mano. Visto en produccion el 15/08/2026, en las conversaciones que ya
    estaban abiertas cuando se agrego la persistencia (migracion 17) y que por
    eso nunca llegaron a guardar nada.

    Solo se lee de herramientas cuyo DESTINATARIO lo eligio el motor
    ('inyectar_sesion' no vacio: el id sale de la sesion verificada, nunca de
    un argumento del modelo). Si no, bastaria que el modelo consultara a otro
    cliente -- por inyeccion de prompt o por un rol interno que si puede
    hacerlo -- para que la sesion se quedara con el serial ajeno y el siguiente
    reinicio remoto cayera sobre la casa equivocada.

    Solo rellena lo que falta: nunca pisa un valor que la sesion ya tiene.
    """
    if sesion is None or not sesion.verificado or not herramienta.inyectar_sesion:
        return
    faltan = [c for c in Sesion.CAMPOS_PERSISTIBLES if not getattr(sesion, c, None)]
    if not faltan:
        return
    for campo in faltan:
        valor = _buscar_campo(crudo, campo)
        if valor:
            setattr(sesion, campo, valor)
            print(f"[sesion] '{campo}' se recupero de '{herramienta.nombre}' "
                  "(se habia perdido; la conversacion vuelve a tener diagnostico)")


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
            sesion.intentos_verificacion_fallidos += 1
        # Sin 'instruccion_interna' aca, el modelo improvisaba: a veces
        # insistia con el dato, a veces asumia un prospecto nuevo, a veces
        # inventaba una excusa de "problema del sistema" -- probado en vivo
        # el 19/08/2026, tres corridas, tres comportamientos distintos.
        # 'no encontrado' es genuinamente ambiguo -- puede ser un error de
        # tipeo (cliente real) o alguien que todavia no es cliente -- asi
        # que se le da UN reintento antes de asumir lo segundo.
        intentos = sesion.intentos_verificacion_fallidos if sesion else 1
        # La via de escape ("si en cualquier momento te dice que no es
        # cliente, deriva YA") aplica siempre, no solo despues de dos
        # intentos -- probado en vivo el 19/08/2026: alguien puede
        # autodeclararse "no soy cliente todavia" respondiendo al PRIMER
        # pedido de reintento, sin llegar nunca al segundo. Sin esto en el
        # intento 1, el modelo no tenia ninguna instruccion para ese caso y
        # volvia al reflejo viejo de "te paso con un colaborador humano" sin
        # llamar a ninguna herramienta.
        via_de_escape = (
            "Si en CUALQUIER momento la persona dice explicitamente que "
            "todavia no es cliente (aunque sea respondiendo a que le pediste "
            "reescribir el dato), no insistas mas con el dato -- LLAMA a "
            "derivar_a_area en ESE MISMO mensaje, hacia el area de la tabla "
            "de derivacion marcada como que NO requiere verificar identidad "
            "(si hay alguna). Nunca digas 'te paso con...' sin haber llamado "
            "la herramienta: eso deja a la persona esperando una derivacion "
            "que nunca ocurre.")
        if intentos <= 1:
            instruccion = (
                "No se encontro ningun cliente con ese dato. Puede ser un "
                "error al escribirlo -- pedile que lo confirme o lo vuelva "
                "a escribir. Todavia NO asumas que no es cliente vos mismo, "
                "esperá a que te lo diga. " + via_de_escape)
        else:
            # Version anterior (18-19/08/2026) preguntaba directo "¿ya sos
            # cliente o queres contratar?" -- tenia sentido cuando esta
            # herramienta solo la llamaba el router, sin saber de que se
            # trataba el pedido. Desde que la verificacion se movio a cada
            # especialista (19/08/2026, ver Rol.deriva_verificacion en
            # schema.py), quien llama a esta funcion YA SABE el tema (llego
            # aca porque el router entendio que era soporte, o facturacion):
            # asumir "capaz queres contratar" en ese contexto es un cambio
            # de tema que no viene a cuento -- a alguien reportando una
            # falla real de internet no se le pregunta si quiere contratar
            # solo porque escribio mal la cedula dos veces.
            instruccion = (
                "Van dos intentos sin encontrar coincidencia con lo que ya "
                "sabes que necesita. Decile que no lograste ubicar la "
                "cuenta con ese dato, y pedile un dato alternativo (otro "
                "numero de documento, o el nombre completo del titular) -- "
                "sin cambiar de tema ni asumir que dejo de ser cliente. Si "
                "con eso tampoco se resuelve, decile que vas a pasar el "
                "caso a un colaborador humano para que lo revise "
                "directamente. " + via_de_escape)
        return {"verificado": False, "motivo": "no encontrado",
               "instruccion_interna": instruccion}

    if len(filas) > 1:
        if sesion is not None:
            sesion.verificado = False
            sesion.candidatos = [str(f["id_servicio"]) for f in filas]
        return {"verificado": False, "motivo": "ambiguo",
               "instruccion_interna": "Hay mas de un cliente con ese dato. "
                   "Pidele otro dato adicional para desambiguar -- nunca "
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
        "instruccion_interna": "Todavia NO esta verificado. Dile al cliente "
            "que el servicio figura a nombre de 'nombre_a_confirmar' y "
            "pidele que confirme si es el/ella. Nunca reveles ningun otro "
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
               "instruccion_interna": "Pidele de nuevo el numero de cedula, "
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
               "impida seguir. Dile al cliente en una frase breve que ya "
               "quedo verificado, y en el MISMO mensaje sigue de inmediato "
               "con el problema que te habia contado antes de pedirle la "
               "cedula, usando las herramientas que tengas para su rol. "
               "Nunca digas que falta un paso, que el canal no lo permite, "
               "ni escales a un humano solo por este motivo."}


def _buscar_campo(dato, campo: str):
    """El valor de 'campo' dentro de la respuesta YA FILTRADA de una
    herramienta, sea cual sea la forma en que quedo.

    Existe porque esa forma NO es una sola. 'nucleo/seguridad/listas_blancas.py'
    normaliza una respuesta de lista a {'total': N, 'resultados': [...]}, y
    cada fila puede traer un campo distinto -- ping_cliente devuelve
    exactamente eso: [{'ping-1': {...}}, ..., {'ping-exitoso': '3 de 3'}].
    Buscar solo en el primer nivel encuentra 'total' y 'resultados', nunca
    'ping-exitoso'.

    Costo un bug real (agosto 2026): la precondicion de 'reiniciar_ont'
    nunca podia cumplirse, el modelo jamas lograba ofrecer el reinicio, y
    desde afuera se veia identico a "el modelo no quiere hacerlo" -- se
    perdio tiempo ajustando prompts antes de mirar la forma del dato.
    """
    if isinstance(dato, dict):
        if campo in dato:
            return dato[campo]
        for anidado in dato.values():
            if isinstance(anidado, (dict, list)):
                encontrado = _buscar_campo(anidado, campo)
                if encontrado is not None:
                    return encontrado
    elif isinstance(dato, list):
        for item in dato:
            encontrado = _buscar_campo(item, campo)
            if encontrado is not None:
                return encontrado
    return None


def _ejecutar_derivacion(herramienta, sesion, argumentos_modelo: dict, nombre_rol_actual: str) -> dict:
    """
    Pasa el resto de la conversacion a otro rol cliente_final (facturacion,
    soporte tecnico...). No llama a ninguna API: solo deja la decision en
    'sesion.rol_siguiente', que atender_turno() (nucleo/canales/api.py) lee
    despues de esta llamada para persistir 'rol_efectivo' con el rol nuevo.

    Verificacion de identidad: NO se repite. 'sesion' es la misma instancia
    para toda la conversacion, y el estado de verificado/id_cliente vive ahi
    independiente del rol -- el especialista la hereda automatica.

    'area' llega acotada por el enum del esquema (ver _esquema_openai), pero
    se revalida aca contra 'areas_destino' igual: el esquema es lo que el
    modelo VE, no una garantia de lo que puede llegar a mandar.
    """
    area = (argumentos_modelo or {}).get("area")
    if area not in herramienta.areas_destino:
        return {"error": f"'{area}' no es un area valida para derivar.",
               "instruccion_interna": f"Elige una de estas: "
                   f"{', '.join(herramienta.areas_destino)}."}

    if area == nombre_rol_actual:
        # Auto-derivacion: el modelo se confundio, no hace nada -- no tiene
        # sentido "derivar" a donde ya esta. Se le avisa para que no repita.
        return {"ok": True, "area": area,
               "instruccion_interna": "Ya estas atendiendo esta area, no "
                   "hace falta derivar. Sigue con la conversacion."}

    # Ida y vuelta entre dos areas. Impedir la auto-derivacion no alcanzaba:
    # soporte manda el caso a facturacion, facturacion se lo devuelve a
    # soporte, y el cliente no recibe una sola respuesta. Visto el 21/08/2026
    # con un suspendido -- derivar, mirar el servicio, derivar de vuelta, y
    # el turno agotandose hasta escalar por no tener salida.
    #
    # Fail-closed: un area que ya vio esta conversacion no la recibe otra vez.
    # Si de verdad no puede resolverla, el camino es escalar, no rebotar.
    if sesion is not None and area in getattr(sesion, "areas_visitadas", []):
        return {"error": "AREA_YA_INTERVINO",
               "instruccion_interna": f"'{area}' ya atendio esta conversacion "
                   "y te la paso a ti: devolversela la dejaria rebotando sin "
                   "que nadie le conteste al cliente. Resuelve lo que puedas "
                   "con tus herramientas y, si de verdad excede lo tuyo, "
                   "dilo y deja que el caso pase a una persona -- pero "
                   "contestale algo primero."}

    if sesion is not None:
        sesion.rol_siguiente = area
        # El area que deriva tambien queda marcada: es por donde ya paso.
        for quien in (nombre_rol_actual, area):
            if quien and quien not in sesion.areas_visitadas:
                sesion.areas_visitadas.append(quien)
        # Solo se pisa si vino algo: una segunda derivacion sin 'servicio'
        # (herramienta sin 'servicios_reportables') no puede borrar lo que
        # la primera ya habia establecido.
        if (argumentos_modelo or {}).get("servicio"):
            sesion.servicio_reportado = argumentos_modelo["servicio"]

    # El especialista atiende EN ESTE MISMO TURNO: responder() detecta
    # 'rol_siguiente' apenas termina esta tanda de llamadas, rearma el
    # catalogo con las herramientas del area nueva y sigue el bucle (ver el
    # bloque 'DERIVACION EN EL MISMO TURNO'). Por eso ya no se le pide un
    # cierre breve al modelo: el cliente no tiene que volver a escribir, y
    # avisarle del cambio de area seria contarle una plomeria interna que no
    # le sirve de nada.
    return {"ok": True, "area": area,
           "instruccion_interna": f"Listo, la atiende '{area}' -- que sigue "
               f"AHORA MISMO, en este mismo mensaje, con sus propias "
               f"herramientas. No le anuncies al cliente que lo derivaste ni "
               f"le pidas que espere: para el es la misma conversacion y la "
               f"respuesta le llega ya."}


def _con_obligatorios(texto: str, obligatorios: list[str]) -> str:
    """
    Agrega al final lo que el cliente TIENE que recibir y el modelo no escribio.

    Medido el 02/09/2026: en una de cada dos corridas el asistente registraba
    la solicitud y contestaba "listo, ya te llega el link del formulario"...
    sin el link. La herramienta habia funcionado y el link existia; el cliente
    se quedaba esperando algo que nunca iba a llegar. Es el peor final posible,
    porque todo el sistema hizo bien su trabajo y el resultado igual se perdio.

    Se agrega en vez de reescribir el mensaje: el texto del modelo ya dice lo
    que hay que decir, lo unico que falta es el dato. Pegarlo al final no
    contradice nada -- a diferencia de la escalada, donde el aviso SI puede
    contradecir la pregunta que el modelo acababa de hacer (ver api.py).
    """
    if not obligatorios:
        return texto
    faltan = [v for v in obligatorios if v and v not in (texto or "")]
    if not faltan:
        return texto
    return ((texto or "").rstrip() + "\n\n" + "\n".join(faltan)).strip()


def _localidades_parecidas(config, clave: str, cuantas: int = 4) -> list[str]:
    """
    Los nombres del catalogo que se parecen a lo que escribio el cliente.

    Existe porque cuando una localidad "no esta", casi nunca es que no haya
    cobertura: es que se escribio distinto. Ya paso con 'DOÑA MANUELA' /
    'DONA MANUELA', y con 128 localidades cargadas hay margen de sobra para
    equivocarse ('las flores' por 'LAS FLORES DEL NORTE').

    Dos pasadas, y la primera importa mas que la segunda: si lo que escribio
    esta CONTENIDO en un nombre del catalogo (o al reves), eso es una
    coincidencia mucho mas fuerte que un parecido de letras -- 'centro' contra
    'CENTRO DE SOLEDAD' es obvio para una persona y difflib lo puntua bajo por
    la diferencia de largo.

    Sin llamadas de red: el catalogo ya esta en memoria del turno.
    """
    import difflib

    if not clave:
        return []
    nombres = [l.localidad for l in config.localidades]
    contenidos = [n for n in nombres
                  if clave in _sin_tildes(n) or _sin_tildes(n) in clave]
    if len(contenidos) >= cuantas:
        return contenidos[:cuantas]
    # Se completa con parecidos de letras, sin repetir los que ya entraron.
    faltan = cuantas - len(contenidos)
    restantes = {_sin_tildes(n): n for n in nombres if n not in contenidos}
    cercanos = difflib.get_close_matches(clave, list(restantes), n=faltan, cutoff=0.72)
    return contenidos + [restantes[c] for c in cercanos]


def _ejecutar_consulta_documentacion(config, nombre_rol: str,
                                     argumentos_modelo: dict) -> dict:
    """
    Los fragmentos del corpus que responden una pregunta, cuando el modelo los
    pide. Ver Herramienta.consulta_documentacion en schema.py para el porque.

    La pregunta que se vectoriza es la que ESCRIBE EL MODELO, no el mensaje
    crudo del cliente, y eso es una ventaja lateral del cambio: el modelo
    reformula "no navega" como "que hacer cuando un cliente no tiene conexion
    a internet", que es lo que se parece al texto de la guia. Los dos casos
    legitimos que hoy se pierden por umbral (0.343 y 0.349) son exactamente
    frases cortas y vagas de ese tipo.

    Devuelve los fragmentos crudos, no el bloque de texto armado: el bloque
    tiene formato de mensaje 'system' y esto entra por el canal 'tool', que ya
    trae su propia envoltura. Duplicar el encuadre le diria dos veces lo mismo
    con palabras distintas.

    Fuera del gate de identidad, igual que las otras internas: una guia de
    procedimientos no menciona a ningun cliente.
    """
    pregunta = str((argumentos_modelo or {}).get("pregunta", "")).strip()
    if not pregunta:
        return {"error": "FALTA_PREGUNTA",
                "instruccion_interna": "Indica que necesitas buscar en la "
                    "documentacion, con una frase completa."}

    try:
        fragmentos, mejor = recuperar(config, config.identidad.slug,
                                      nombre_rol, pregunta)
    except Exception as fallo:      # noqa: BLE001
        # Mismo criterio que la precarga que esto reemplaza: un fallo de
        # recuperacion no puede dejar al cliente sin turno. Antes se seguia
        # sin contexto; ahora se le dice al modelo, que es mejor -- puede
        # decidir consultar otra cosa en vez de creer que el corpus esta vacio.
        print(f"[rag] no se pudo recuperar contexto: {fallo!r}")
        return {"error": "BUSQUEDA_NO_DISPONIBLE",
                "instruccion_interna": "No se pudo consultar la documentacion "
                    "en este momento. No inventes el contenido: segui con lo "
                    "que puedas resolver por otras vias, o decilo."}

    if not fragmentos:
        registrar_sin_resultados(config.identidad.slug, pregunta, nombre_rol, mejor)
        return {"encontrado": False,
                "instruccion_interna": "La documentacion de la empresa no "
                    "cubre eso. NO improvises un procedimiento ni completes "
                    "con lo que te parezca razonable: decilo, y ofrece pasar "
                    "el caso a un colaborador humano si hace falta."}

    citar_fuente = config.roles[nombre_rol].orientado_a != "cliente_final"
    return {"encontrado": True,
            "fragmentos": [
                {"documento": f.codigo, "titulo": f.titulo,
                 "contenido": f.contenido} if citar_fuente
                else {"contenido": f.contenido}
                for f in fragmentos],
            "instruccion_interna": "Esto es lo MAS PARECIDO que hay en la "
                "documentacion, no necesariamente la respuesta. Si no "
                "responde lo que te preguntaron, decilo en vez de forzarlo."}


def _ejecutar_carga_habilidad(config, nombre_rol: str,
                              argumentos_modelo: dict) -> dict:
    """
    Entrega los PASOS de un procedimiento de la empresa, si ese rol lo tiene.

    El indice (que existe y cuando usarlo) ya viaja en el prompt de cada
    turno; aca llega el cuerpo. Ver nucleo/habilidades/catalogo.py para el
    porque de la division.

    NO llama a ninguna API y no revela ningun dato de cliente -- un
    procedimiento no menciona a nadie. Por eso queda fuera del gate de
    identidad, igual que consultar_planes_venta: si pasara por el gate, un
    agente de cara al cliente no podria leer justamente el procedimiento que
    le explica como pedir la verificacion.

    El codigo que llega lo escribio el modelo, asi que puede no existir, o
    existir y ser de otro rol. Las dos cosas devuelven lo mismo a proposito:
    decirle "existe pero no es tuya" le contaria que hay un procedimiento que
    no puede ver. Y la instruccion de vuelta es explicita sobre que NO hacer
    -- sin eso, un modelo que pide un procedimiento y recibe un error tiende
    a inventarse los pasos, que es el problema que las habilidades vienen a
    resolver.
    """
    codigo = str((argumentos_modelo or {}).get("codigo", "")).strip()
    if not codigo:
        return {"error": "FALTA_CODIGO",
                "instruccion_interna": "Indica el codigo exacto del "
                    "procedimiento, tal como aparece en la lista."}

    habilidad = catalogo_habilidades.cargar(config.identidad.slug, nombre_rol, codigo)
    if habilidad is None:
        # Sin interpolar el codigo pedido, a proposito: asi la respuesta es
        # IDENTICA para "no existe" y para "existe pero no es de tu rol", y
        # esa igualdad se puede verificar (tests/test_habilidades.py). Con el
        # codigo adentro las dos respuestas difieren en algo -- no es una fuga,
        # porque el modelo mando ese codigo, pero vuelve la propiedad
        # imposible de comprobar, y una garantia que no se puede comprobar se
        # rompe sin que nadie se entere.
        return {"error": "HABILIDAD_DESCONOCIDA",
                "instruccion_interna": "No tienes ningun procedimiento con "
                    "ese codigo. Revisa la lista de procedimientos "
                    "disponibles y usa uno de esos codigos, o segui adelante "
                    "sin procedimiento. NO te inventes los pasos."}

    catalogo_habilidades.registrar_uso(config.identidad.slug, codigo, nombre_rol)
    return {"codigo": habilidad.codigo, "nombre": habilidad.nombre,
            "pasos": habilidad.pasos,
            "instruccion_interna": "Este es el procedimiento de la empresa "
                "para este caso. Seguilo al pie de la letra: es lo que la "
                "empresa decidio, no una sugerencia. Si un paso te pide un "
                "dato que no tienes, conseguilo con tus herramientas antes de "
                "seguir; si un paso te pide algo que no puedes hacer, decilo "
                "en vez de saltearlo."}


def _ejecutar_consulta_planes_venta(config, argumentos_modelo: dict) -> dict:
    """
    Resuelve cobertura Y planes en un solo paso, leyendo config.localidades
    (catalogo localidad -> zona(s) real(es), sincronizado bajo demanda --
    ver LocalidadZona en schema.py y nucleo/herramientas/localidades.py) y
    config.planes_venta (PlanVenta.zonas). NO llama a ninguna API: es la
    razon de ser de este cambio -- 'ventas' antes llamaba a contar_clientes
    en vivo por cada mensaje que mencionaba una localidad (1-2s de latencia
    de red por turno, ver incidente 20/08/2026, "doña manuela"). Ahora lee
    config, que ya esta en memoria del turno.

    Localidad no encontrada en el catalogo sincronizado (puede ser una zona
    nueva sin clientes todavia, o el nombre escrito distinto a como esta
    cargado) -> cobertura=False, con aviso de no negarla sin mas.

    Localidad encontrada pero ningun PlanVenta con una zona en comun (nadie
    curo un plan para esa zona todavia) -> cobertura=True, planes=[], con
    aviso de no inventar que no hay servicio.
    """
    localidad = str((argumentos_modelo or {}).get("localidad", "")).strip()
    clave = _sin_tildes(localidad)

    # UN MUNICIPIO NO ES UN BARRIO, aunque figure en el catalogo.
    #
    # 'localidad' es texto libre en WispHub y hay registros donde alguien
    # escribio el municipio ahi: 'SOLEDAD' figura como localidad con 1 cliente
    # y 'SABANAGRANDE' con 156. Consultarlos devolvia "hay cobertura", que es
    # verdad para el municipio entero y no dice NADA del barrio de quien
    # pregunta.
    #
    # Paso el 28/08/2026: el asistente le pregunto a un prospecto si su barrio
    # quedaba en Sabanagrande, el dijo "no, Soledad", y el asistente consulto
    # 'soledad' -- que respondio que si por ese unico registro. Le confirmo
    # cobertura en un barrio del que no sabemos nada.
    #
    # Los municipios salen de los datos (ZonaConteo.municipio, deducido por
    # mayoria en la sincronizacion), no de una lista fija: otro ISP opera en
    # otros.
    municipios_conocidos = {_sin_tildes(z.municipio)
                            for l in config.localidades for z in l.zonas
                            if z.municipio}
    if clave in municipios_conocidos:
        return {"cobertura": None, "planes": [], "es_un_municipio": localidad,
                "advertencia":
                    f"'{localidad}' es un MUNICIPIO, no un barrio. Que haya "
                    f"clientes ahi no dice nada del barrio de esta persona. "
                    f"Preguntale como se llama su barrio y volve a "
                    f"consultarme con ese nombre. No le confirmes cobertura "
                    f"todavia."}

    entrada = next(
        (l for l in config.localidades if _sin_tildes(l.localidad) == clave), None)

    if entrada is None:
        # Antes de mandar esto a una persona: lo mas probable NO es que no
        # haya cobertura, es que el nombre este escrito distinto. Ya paso con
        # 'DOÑA MANUELA' / 'DONA MANUELA'. Con el catalogo en memoria, buscar
        # los parecidos no cuesta ninguna llamada, y convierte un traspaso en
        # una pregunta que el cliente puede contestar.
        similares = _localidades_parecidas(config, clave)
        salida = {"cobertura": False, "planes": [], "similares": similares}
        salida["advertencia"] = (
            ("No encontre esa localidad con ese nombre exacto, pero hay "
             "parecidas: preguntale si es alguna de las de 'similares', con "
             "esos nombres. Si dice que si, volve a llamarme con el nombre "
             "que te confirme.")
            if similares else
            "No hay ningun cliente registrado en esa localidad todavia "
            "-- puede ser una zona nueva sin clientes, o que el nombre "
            "esta escrito distinto a como figura en el sistema. No "
            "digas que no hay cobertura: decile que vas a confirmar "
            "con un colaborador.")
        return salida

    zonas_localidad = {z.zona_id for z in entrada.zonas}
    coincidentes = [
        p.nombre_wisphub for p in config.planes_venta
        if not p.zonas or (zonas_localidad & set(p.zonas))
    ]
    # EN QUE MUNICIPIO, y no en que nodo. Un mismo nombre de barrio existe en
    # varios municipios ('CENTRO' esta en todos), y el catalogo se arma por
    # nombre de localidad, asi que hay que poder desambiguar.
    #
    # Se devuelve el MUNICIPIO y NO el nombre de la zona ('CORTE 30 - SERVIDOR
    # 1') porque el modelo se lo lee al cliente: el 28/08/2026 le pregunto a un
    # prospecto si su barrio quedaba en 'CORTE 30 - SERVIDOR 1'. Eso es un
    # nombre interno de un nodo de red. Lo que una persona puede contestar es
    # en que municipio vive.
    municipios = sorted({z.municipio for z in entrada.zonas if z.municipio})
    salida = {"cobertura": True, "n_clientes": entrada.n_clientes,
              "planes": coincidentes, "municipios": municipios}

    # UN SOLO CLIENTE NO ES EVIDENCIA DE COBERTURA. Medido el 28/08/2026: un
    # prospecto pregunto por "barrio centro" y el catalogo dijo que si, con un
    # unico cliente -- que resulto estar en el CENTRO de Sabanagrande, otro
    # municipio. Se le ofrecieron los planes de fibra de alla.
    #
    # No se convierte en "no hay cobertura", que seria el error caro (perder
    # una venta diciendole algo falso a quien iba a contratar). Se le pide al
    # modelo que confirme el municipio, que es lo que un vendedor haria.
    if (entrada.n_clientes or 0) <= 2:
        salida["confirmar_municipio"] = True
        donde = " o ".join(municipios) if municipios else "el municipio que tenemos registrado"
        salida["advertencia"] = (
            f"OJO: en esa localidad hay muy pocos clientes "
            f"({entrada.n_clientes}), y ese nombre de barrio existe en mas de "
            f"un municipio. Antes de darle planes o precios, preguntale si su "
            f"barrio queda en {donde}. Si te dice que NO, es otro barrio con "
            f"el mismo nombre: NO tenemos su cobertura confirmada, no le des "
            f"planes ni precios y decile que lo vas a confirmar con un "
            f"colaborador. Y NO vuelvas a consultar usando el nombre del "
            f"municipio como si fuera el barrio -- eso responde por otro "
            f"lugar distinto.")
    if not coincidentes:
        salida["advertencia"] = (
            "Hay cobertura en esa localidad pero todavia no hay ningun "
            "plan curado para su zona. No inventes que no hay servicio "
            "disponible -- decile que vas a confirmar los planes con un "
            "colaborador humano.")
    return salida


def _ejecutar_sondeo(argumentos_modelo: dict, tenant: str) -> dict:
    """
    Sondea una API EXTERNA que un ADMIN describio en el chat -- unico lugar
    del proyecto que llama a una URL no verificada de antemano. Ver
    Herramienta.sondea_api (schema.py) para el porque, y
    nucleo/herramientas/sondeo.py para el bloqueo de SSRF.

    'auth_ref' es el NOMBRE de un secreto ya guardado (nunca la clave): se
    resuelve aca, server-side, y no pasa por el modelo en ningun momento.
    """
    from nucleo.herramientas import sondeo as sondeo_seguro
    from nucleo.seguridad import secretos

    argumentos_modelo = argumentos_modelo or {}
    url = argumentos_modelo.get("url", "")
    if not url:
        return {"error": "Falta 'url'."}

    headers = {}
    auth_ref = argumentos_modelo.get("auth_ref")
    if auth_ref:
        clave = secretos.obtener(tenant, auth_ref)
        if clave is None:
            return {"error": f"No existe un secreto guardado llamado "
                             f"'{auth_ref}'. Pedile al ADMIN que lo guarde "
                             f"primero desde la pantalla de credenciales."}
        esquema = argumentos_modelo.get("auth_esquema", "")
        header_nombre = argumentos_modelo.get("auth_header") or "Authorization"
        headers[header_nombre] = f"{esquema} {clave}".strip()

    params = None
    params_texto = argumentos_modelo.get("params")
    if params_texto:
        try:
            params = json.loads(params_texto)
        except (TypeError, ValueError):
            return {"error": "'params' no es JSON valido."}

    try:
        return sondeo_seguro.sondear(url, headers, params)
    except sondeo_seguro.ErrorSondeo as e:
        return {"error": str(e)}


def _ejecutar_propuesta(argumentos_modelo: dict, tenant: str, propuesto_por: str) -> dict:
    """
    Guarda el borrador de Herramienta que el ADMIN armo junto con el
    asistente, DESPUES de sondear -- ver Herramienta.propone_herramienta.
    Nunca se activa sola: queda 'pendiente' en
    asistente.herramientas_propuestas hasta que una persona la apruebe
    (nucleo/canales/api.py::aprobar_propuesta), que recien ahi la valida
    contra el esquema completo (schema.py) y la escribe al catalogo real.
    """
    from nucleo.persistencia import db as persistencia

    argumentos_modelo = argumentos_modelo or {}
    descripcion_pedido = argumentos_modelo.get("descripcion_pedido", "")
    try:
        sondeo_dict = json.loads(argumentos_modelo.get("sondeo") or "{}")
        herramienta_dict = json.loads(argumentos_modelo.get("herramienta_propuesta") or "{}")
    except (TypeError, ValueError):
        return {"error": "'sondeo' o 'herramienta_propuesta' no son JSON valido."}

    if not herramienta_dict.get("nombre") or not herramienta_dict.get("tipo"):
        return {"error": "El borrador necesita al menos 'nombre' y 'tipo'."}

    id_propuesta = persistencia.guardar_herramienta_propuesta(
        tenant, descripcion_pedido, sondeo_dict, herramienta_dict, propuesto_por)
    return {"propuesta_id": id_propuesta, "estado": "pendiente",
           "instruccion_interna": "Decile al ADMIN que quedo guardada, "
               "pendiente de que alguien la apruebe desde la pantalla de "
               "configuracion -- no esta activa todavia, no lo prometas."}


def _resumen_de_accion(herramienta, argumentos: dict) -> str:
    """Texto legible para quien va a aprobar/rechazar una accion propuesta
    -- ver Herramienta.plantilla_resumen. Fallback generico si no hay
    plantilla o si le falta algun dato: nunca revienta el turno por esto,
    en el peor caso el resumen es menos lindo, no inexistente."""
    if herramienta.plantilla_resumen:
        try:
            return herramienta.plantilla_resumen.format(**argumentos)
        except (KeyError, IndexError):
            pass
    pares = ", ".join(f"{k}={v}" for k, v in argumentos.items())
    return f"{herramienta.nombre}({pares})"


def _ejecutar_propuesta_de_accion(herramienta, sesion, argumentos_modelo: dict,
                                  tenant: str, rol: str, propuesto_por: str) -> dict:
    """
    Para una Herramienta con aprobacion_humana=True (nucleo/config/
    schema.py): resuelve los argumentos reales -- igual que _ejecutar_tool,
    mismo _resolver_argumentos() -- pero NUNCA llama a la API. Los deja
    'pendiente' en asistente.acciones_propuestas. La unica funcion que de
    verdad escribe es ejecutar_accion_aprobada(), llamada desde
    nucleo/canales/api.py solo despues de que una persona aprueba.

    Retomado el 18/08/2026 con un caso concreto (tickets de WispHub) --
    'requiere_confirmacion' sigue significando lo mismo que siempre
    (declarado, no aplicado): este es un mecanismo NUEVO y separado, no una
    reactivacion de ese campo. Ver el comentario de aprobacion_humana en
    schema.py.
    """
    from nucleo.persistencia import db as persistencia

    argumentos = _resolver_argumentos(herramienta, sesion, argumentos_modelo)
    resumen = _resumen_de_accion(herramienta, argumentos)
    accion_id = persistencia.guardar_accion_propuesta(
        tenant, herramienta.nombre, argumentos, resumen, rol, propuesto_por)
    return {"accion_id": accion_id, "estado": "pendiente", "resumen": resumen,
           "instruccion_interna": f"Decile a quien te pidio esto que la accion "
               f"quedo pendiente de aprobacion ({resumen}) -- todavia NO se "
               f"ejecuto, no confirmes que ya se hizo. Alguien tiene que "
               f"aprobarla desde la pantalla correspondiente."}


def ejecutar_accion_aprobada(config, accion: dict) -> tuple[dict, str | None]:
    """
    La UNICA funcion que ejecuta de verdad una escritura que paso por
    aprobacion_humana -- llamada desde nucleo/canales/api.py despues de que
    alguien aprueba. 'accion' es la fila de asistente.acciones_propuestas
    (ya con 'herramienta' y 'argumentos' resueltos de antes, guardados tal
    cual se iban a mandar).

    Devuelve (resultado, codigo_error) -- mismo patron que el resto del
    motor: codigo_error es None si salio bien. No reintenta ni interpreta
    el error, solo lo deja explicito para que quien aprobo sepa que paso.
    """
    herramienta = next((h for h in config.herramientas
                        if h.nombre == accion["herramienta"]), None)
    if herramienta is None:
        return {"error": f"La herramienta '{accion['herramienta']}' ya no "
                         f"existe en el catalogo."}, "HERRAMIENTA_DESCONOCIDA"
    try:
        if herramienta.tipo == "http":
            resultado = (ejecutor_http.ejecutar_asincrono(herramienta, accion["argumentos"],
                                                          tenant=config.identidad.slug)
                        if herramienta.asincrona else
                        ejecutor_http.ejecutar(herramienta, accion["argumentos"],
                                               config.identidad.slug, config.variables_tenant))
            return resultado, None
        return {"error": f"Tipo '{herramienta.tipo}' no soportado para "
                         f"ejecucion aprobada."}, "TIPO_NO_SOPORTADO"
    except Exception as e:
        return {"error": "La API no acepto la accion."}, f"{type(e).__name__}: {e}"[:200]


def ejecutar_para_servicio(config, herramienta, argumentos_modelo: dict) -> dict:
    """
    Ejecuta una herramienta a pedido de OTRO servicio del despliegue, no de un
    modelo ni de una persona. La llama POST /interno/herramienta/<nombre>.

    Existe porque la credencial de WispHub vive solo en el motor y el backend
    del CRM tambien necesita crear un ticket ahi. Ver el docstring de esa ruta
    en nucleo/canales/api.py, y 'invocable_por_servicio' en schema.py -- ESE
    es el permiso; aca ya se da por concedido.

    Se pasa sesion=None a proposito, y no es un descuido: del otro lado no hay
    ninguna persona a la que verificar. Una herramienta que dependa de
    'inyectar_sesion' va a llegar a la API sin ese campo y fallar de forma
    controlada, en vez de ejecutarse sobre el cliente equivocado -- que es
    exactamente lo que tiene que pasar.

    Los argumentos pasan por el MISMO _resolver_argumentos que usa el modelo:
    un servicio interno no tiene mas permisos para inventar parametros que el
    modelo, y los filtros no verificados se descartan igual.
    """
    argumentos = _resolver_argumentos(herramienta, None, argumentos_modelo or {},
                                      variables_tenant=config.variables_tenant)

    # Consultas internas que NO dependen de una sesion ni tocan datos de un
    # cliente puntual. La que trajo esto: el formulario de contratacion
    # necesita mostrarle al prospecto los planes de SU zona, y esa lista sale
    # del catalogo curado del tenant -- no de lo que el modelo haya dicho en
    # la conversacion, que es justo lo que no hay que reenviar de un sistema
    # a otro (PRD 12.5: el modelo compone, el codigo calcula).
    if herramienta.tipo == "interno" and herramienta.consulta_planes_venta:
        return _ejecutar_consulta_planes_venta(config, argumentos)

    if herramienta.tipo == "http":
        return (ejecutor_http.ejecutar_asincrono(herramienta, argumentos,
                                                 tenant=config.identidad.slug)
                if herramienta.asincrona else
                ejecutor_http.ejecutar(herramienta, argumentos,
                                       config.identidad.slug, config.variables_tenant))
    raise ValueError(f"Tipo '{herramienta.tipo}' no se puede ejecutar desde un "
                     f"servicio -- solo 'http'.")


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
            # No se corta al primer match: la ULTIMA ocurrencia en el
            # historial (mas reciente) es la que decide.
            cumplida = previa.acepta(_buscar_campo(dato, previa.campo))
        if not cumplida:
            faltantes.append(previa.herramienta)
    return faltantes


def _veces_ejecutada(herramienta, historial: list[dict]) -> int:
    """Cuantas veces CORRIO DE VERDAD 'herramienta' en esta conversacion --
    para Herramienta.limite_por_conversacion.

    Un intento que el motor freno (precondicion, turno propio, el limite
    mismo) no cuenta: no le paso nada al cliente, asi que no puede gastarle
    la unica oportunidad que tiene. Visto el 21/08/2026 con reiniciar_ont --
    el modelo lo intento en el turno de la derivacion, la guarda lo bloqueo
    con razon, y cuando el reinicio SI correspondia un turno despues salio
    'LIMITE_DE_CONVERSACION'. El cliente quedaba sin el reinicio y la
    conversacion sin salida, asi que terminaba escalando.

    Mismo error que tenia el arnes de casos dorados con 'no_usa': contar
    intentos donde habia que contar ejecuciones."""
    n = 0
    for msg in historial:
        if msg.get("role") != "tool" or msg.get("name") != herramienta.nombre:
            continue
        try:
            dato = json.loads(msg.get("content") or "null")
        except (TypeError, ValueError):
            dato = None
        # Las salidas de error del motor son siempre {"error": ..., ...}
        if isinstance(dato, dict) and dato.get("error"):
            continue
        n += 1
    return n


def _resolver_argumentos(herramienta, sesion, argumentos_modelo: dict,
                         sobrescribir: dict | None = None,
                         variables_tenant: dict | None = None) -> dict:
    """
    Los argumentos REALES que se le mandan a una API, a partir de lo que el
    modelo propuso -- filtros traducidos (fail-closed: solo lo declarado en
    filtros_verificados), constantes del tenant, fechas calculadas, y la
    sesion verificada pisando lo que el modelo haya dicho. Separado de
    _ejecutar_tool() para que _ejecutar_propuesta_de_accion() pueda armar
    los mismos argumentos SIN llamar a la API todavia -- son los que se
    guardan en asistente.acciones_propuestas, listos para ejecutar cuando
    alguien apruebe.
    """
    argumentos_modelo = argumentos_modelo or {}
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

    # Los fijos que viven en la config del tenant y no en el YAML -- ver
    # 'argumentos_desde_variables' en schema.py. Van junto a los otros fijos:
    # para la llamada son lo mismo, la unica diferencia es de donde salio el
    # valor y quien lo puede editar.
    for arg_llamada, nombre_variable in herramienta.argumentos_desde_variables.items():
        valor = (variables_tenant or {}).get(nombre_variable)
        if valor not in (None, ""):
            argumentos[arg_llamada] = valor

    # Y despues, lo que el CODIGO decidio para esta llamada puntual -- solo
    # sobre las claves que la herramienta declaro sobrescribibles. Va DESPUES
    # de los fijos a proposito: el valor de la config pasa a ser el respaldo,
    # no la ultima palabra.
    #
    # 'sobrescribir' no llega por ningun camino del modelo: lo arma quien
    # llama, en codigo. La lista blanca de claves esta igual, para que un
    # llamador nuevo no pueda cambiar algo que el tenant quiso fijo sin
    # haberlo declarado.
    for clave, valor in (sobrescribir or {}).items():
        if clave in herramienta.argumentos_sobrescribibles and valor:
            argumentos[clave] = valor

    # La firma, al final del texto y una sola vez. Se pega aca -- donde se
    # arman los argumentos REALES -- para que valga tanto en una escritura
    # directa como en una que pasa por aprobacion: en los dos casos el texto
    # que sale lleva el nombre de quien lo mando.
    firma = getattr(sesion, "nombre_colaborador", "") if sesion else ""
    campo = herramienta.firmar_campo
    if campo and firma and argumentos.get(campo):
        texto = str(argumentos[campo])
        marca = "-- " + firma
        if not texto.rstrip().endswith(marca):
            argumentos[campo] = texto.rstrip() + chr(10) + chr(10) + marca

    # Fechas calculadas en el momento (ver 'fechas_automaticas' en
    # schema.py). Formato DD/MM/AAAA HH:MM: es lo que exige WispHub hoy, el
    # unico proveedor con esta necesidad -- si aparece otro con un formato
    # distinto, esto pasa a ser un campo de config en vez de una constante.
    for arg_llamada, dias in herramienta.fechas_automaticas.items():
        fecha = datetime.now() + timedelta(days=dias)
        argumentos[arg_llamada] = fecha.strftime(herramienta.formato_fechas_automaticas)

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

    # Y si lo que falta es un campo de IDENTIDAD, la llamada no sale.
    #
    # Omitir un campo vacio es correcto para uno opcional y es un agujero para
    # uno de identidad: sin 'id_servicio', la consulta no pregunta por nadie --
    # pregunta SIN FILTRO, y devuelve a todo el mundo con cara de exito. Ver
    # 'inyectados_obligatorios' en schema.py y el caso medido que lo motivo.
    #
    # Va aca y no en el despacho a proposito: por esta funcion pasan los TRES
    # caminos que arman argumentos -- el modelo, una accion aprobada por una
    # persona, y la ruta interna de servicio. Ponerlo en uno solo dejaria los
    # otros dos abiertos.
    faltan = [c for c in herramienta.inyectados_obligatorios if not argumentos.get(c)]
    if faltan:
        raise FaltaIdentidadEnSesion(herramienta.nombre, faltan)

    # Ver Herramienta.espejar_campos en schema.py -- despues de todo lo
    # demas, para copiar el valor YA resuelto (traducido, no lo que dijo
    # el modelo en crudo).
    for origen, destino in herramienta.espejar_campos.items():
        if origen in argumentos:
            argumentos[destino] = argumentos[origen]

    return argumentos


def medir_para_verificar(config, verificacion, sesion, tenant: str | None,
                         variables_tenant: dict | None = None) -> dict:
    """
    Toma una medicion con cada herramienta que la verificacion declara.

    {nombre: respuesta cruda} -- y None en la que no se pudo medir, que es lo
    que despues se traduce en NO_VERIFICABLE en vez de en un fallo inventado.

    TRES COSAS QUE HACE A PROPOSITO:

    - Devuelve la respuesta CRUDA, sin pasar por la lista blanca del rol. El
      campo que prueba un reinicio ('last_status_change') no es algo que el
      modelo tenga que ver ni decidir: lo compara el codigo. La lista blanca
      sigue gobernando lo que se le muestra al modelo, que es para lo que
      existe.

    - No toca el cache del turno. Ese cache vive dentro de responder() y sirve
      para no repetir una lectura que el modelo pidio dos veces en el mismo
      turno; una medicion de verificacion tiene que ser FRESCA por definicion
      -- reusar el ping de antes del reinicio daria por confirmado lo que
      justamente hay que comprobar.

    - Nunca levanta: una medicion que falla es un dato ('no se pudo medir'),
      no un error que tumbe el turno.
    """
    por_nombre = {h.nombre: h for h in config.herramientas}
    medicion: dict = {}
    for comprobacion in verificacion.comprobaciones:
        herr = por_nombre.get(comprobacion.herramienta)
        if herr is None:
            medicion[comprobacion.herramienta] = None
            continue
        try:
            medicion[comprobacion.herramienta] = _ejecutar_tool(
                herr, sesion, {}, tenant, variables_tenant)
        except Exception as e:
            print(f"[verificacion] no se pudo medir con "
                  f"'{comprobacion.herramienta}': {type(e).__name__}: {e}")
            medicion[comprobacion.herramienta] = None
    return medicion


def _ejecutar_tool(herramienta, sesion, argumentos_modelo: dict,
                   tenant: str | None = None,
                   variables_tenant: dict | None = None,
                   sobrescribir: dict | None = None) -> dict | list:
    argumentos_modelo = argumentos_modelo or {}

    if herramienta.tipo == "agregado":
        # No pasa por la traduccion de mas abajo: agregado necesita los
        # valores CRUDOS del modelo (incluido 'agrupar_por'/'periodo', que no
        # son filtros) para decidir agrupamiento y rango -- hace su propia
        # traduccion de filtros adentro.
        return ejecutor_agregado.ejecutar(herramienta, argumentos_modelo, tenant)

    argumentos = _resolver_argumentos(herramienta, sesion, argumentos_modelo,
                                      sobrescribir, variables_tenant)

    if herramienta.tipo == "interno" and herramienta.detecta_incidente:
        return ejecutor_incidentes.detectar(herramienta, argumentos, tenant, variables_tenant)

    if herramienta.tipo == "interno" and herramienta.resume_estabilidad:
        return ejecutor_estabilidad.resumir(herramienta, argumentos, tenant, variables_tenant)

    if herramienta.tipo == "interno" and herramienta.valida_pedido_wifi:
        return ejecutor_wifi.procesar(herramienta, argumentos, tenant, variables_tenant)

    if herramienta.tipo == "http":
        if herramienta.cache and tenant:
            # 'argumentos' ya tiene TODO resuelto en este punto (filtros del
            # modelo + inyectar_sesion) -- la clave sale de ahi, ordenada
            # para que el mismo pedido siempre arme la misma clave. El
            # validador de Herramienta ya garantiza que una herramienta con
            # cache=true nunca tiene inyectar_sesion (ver schema.py), asi
            # que aca nunca hay un dato de cliente puntual.
            clave = "&".join(f"{k}={argumentos[k]}" for k in sorted(argumentos))
            cacheado = persistencia.leer_cache(
                tenant, herramienta.nombre, clave, herramienta.cache_vigencia_dias)
            if cacheado is not None:
                return cacheado
            resultado = (ejecutor_http.ejecutar_asincrono(herramienta, argumentos, tenant=tenant,
                                                          variables_tenant=variables_tenant)
                        if herramienta.asincrona else
                        ejecutor_http.ejecutar(herramienta, argumentos, tenant, variables_tenant))
            persistencia.guardar_cache(tenant, herramienta.nombre, clave, resultado)
            return resultado
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


class _LlamadaRecuperada:
    """Una llamada que el modelo pidio en texto en vez de por la API, con la
    misma forma que las de verdad para que el bucle no tenga que distinguirlas."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.argumentos = {}


def _llamadas_fugadas(contenido: str, herramientas) -> list:
    """
    Rescata las herramientas que el modelo pidio ESCRIBIENDOLAS en vez de
    usar el tool-calling de la API. DeepSeek lo hace de forma reproducible
    (medido el 15/08/2026: tres veces seguidas sobre el mismo turno), y
    reintentar no lo corrige -- pero el texto dice exactamente que queria:

        <｜｜DSML｜｜invoke name="consultar_estado_ont">

    Descartarlo dejaba al cliente con "No pude terminar de redactar la
    respuesta"; ejecutarlo es hacer lo que el modelo pidio, solo que leyendolo
    de donde lo escribio.

    SOLO se recuperan herramientas SIN argumentos del modelo. Una que los
    necesite (un filtro, la cedula, el area a la que derivar) se ignora a
    proposito: el texto fugado no los trae de forma confiable, y ejecutarla
    con los argumentos vacios seria inventar la consulta. Y solo las que ESE
    rol tiene en su catalogo -- el permiso no lo afloja este rescate.
    """
    nombres = re.findall(r'name="([a-z0-9_]+)"', contenido or "", re.I)
    if not nombres:
        return []
    por_nombre = {h.nombre: h for h in herramientas}
    recuperadas, vistas = [], set()
    for nombre in nombres:
        herr = por_nombre.get(nombre)
        if herr is None or nombre in vistas:
            continue
        if (herr.filtros_verificados or herr.verifica_identidad
                or herr.confirma_identidad or herr.deriva_rol):
            continue
        vistas.add(nombre)
        recuperadas.append(_LlamadaRecuperada(nombre))
    return recuperadas


def _sanitizar(texto: str, nombres_rol=(), tratamiento: str | None = None) -> str:
    limpio = _RE_FUGA_TOOL_CALL.sub("", texto)
    # Tratamiento (tuteo/voseo/usted). Va aca y no en el prompt porque el
    # prompt es guia y esto es garantia -- ver la explicacion larga en
    # nucleo/modelo/tuteo.py. Cual se aplica lo decide el tenant; nucleo/
    # no sabe cual usa ninguna empresa.
    normalizador = tuteo.NORMALIZADORES.get(tratamiento or "")
    if normalizador:
        limpio = normalizador(limpio)
    # Nombres de rol sueltos. Visto en vivo (15/08/2026): al derivar, el
    # modelo escupio 'soporte_tecnico_cliente' como una linea propia en medio
    # del mensaje, y el cliente lo vio. Es el identificador INTERNO del
    # agente, no algo que signifique nada para quien escribe por WhatsApp.
    #
    # Se borra solo cuando ocupa la linea entera: si aparece dentro de una
    # frase, sacarlo dejaria una oracion rota, y eso se lee peor que el
    # nombre. Los nombres salen de la config del tenant, asi que nucleo/
    # sigue sin conocer ninguno.
    for nombre in nombres_rol:
        limpio = re.sub(rf"^\s*{re.escape(nombre)}\s*$", "", limpio, flags=re.M)
    # Y cualquier OTRO identificador interno suelto, aunque no sea un rol de
    # este tenant. Visto el 18/08/2026: el modelo cerro un mensaje con
    # 'colaborador_humano' en su propia linea -- no es un rol declarado, asi
    # que el barrido de arriba no lo tocaba, y el cliente lo leyo.
    #
    # La regla pide guion bajo a proposito: una linea con UNA sola palabra en
    # minusculas y sin espacios puede ser una respuesta legitima ("listo"),
    # pero una con guion bajo es siempre un identificador de codigo. Nadie le
    # escribe 'colaborador_humano' a un cliente por WhatsApp.
    limpio = re.sub(r"^\s*[a-z][a-z0-9]*(?:_[a-z0-9]+)+\s*$", "", limpio, flags=re.M)
    limpio = re.sub(r"\n{3,}", "\n\n", limpio).strip()
    return limpio


def _redactar(referencia_modelo: str, historial: list[dict], temperatura: float,
              intentos: int = 3, nombres_rol=(), tratamiento: str | None = None) -> str:
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
    for intento in range(intentos):
        resp = cliente.chat(referencia_modelo, historial, tools=None, temperatura=temperatura)
        limpio = _sanitizar(resp.contenido, nombres_rol, tratamiento)
        if not limpio or _RE_RESPUESTA_CRUDA.match(limpio):
            # Por que no sirvio. Sin esto, cuando el cliente ve "no pude
            # terminar de redactar" no queda NADA en el log: ni cuantas veces
            # se reintento, ni si el modelo devolvio vacio o un valor suelto,
            # ni --lo mas util-- si en vez de redactar quiso llamar otra
            # herramienta, que es lo que explica un contenido en blanco
            # cuando se pidio sin herramientas. Paso en produccion el
            # 28/08/2026 y no se pudo saber por que.
            print(f"[modelo] redaccion en blanco (intento {intento + 1}/{intentos}): "
                  f"crudo={resp.contenido[:60]!r} "
                  f"llamadas={[l.nombre for l in (resp.llamadas or [])]}")
        if limpio and not _RE_RESPUESTA_CRUDA.match(limpio):
            limpio, fuga = guardia_salida.verificar(limpio)
            if fuga:
                print(f"[salida] fuga bloqueada en redaccion final: '{fuga}'")
            historial.append({"role": "assistant", "content": limpio})
            return limpio
    print(f"[modelo] se agotaron los {intentos} intentos de redaccion -- al "
          f"cliente le sale el aviso de reintentar")
    historial.append({"role": "assistant", "content": ""})
    # Sin conjugacion de segunda persona ('podes'/'puedes'/'puede') a
    # proposito: este texto sale de nucleo/, que no sabe -- ni tiene por que
    # saber -- que trato usa cada empresa. El dialecto es dato del tenant
    # (persona.instrucciones_adicionales), y una empresa colombiana que
    # configuro tuteo no puede recibir un voseo rioplatense por un mensaje
    # de error. La primera persona del plural sirve en cualquiera de los tres.
    return "No pude terminar de redactar la respuesta. ¿Lo intentamos de nuevo?"


def responder(config, nombre_rol: str, mensaje: str, historial: list[dict],
              sesion, nota_continuidad: str | None = None
              ) -> tuple[str, list[dict], list[dict]]:
    """
    'sesion' es una nucleo.seguridad.verificacion.Sesion (o None si el rol no
    exige verificacion). 'historial' se muta in-place -- el llamador lo
    conserva entre turnos.

    'nota_continuidad': solo la usa nucleo/canales/api.py::atender_turno()
    cuando esta conversacion ya estaba derivada a este rol (via
    derivar_a_area) pero el historial en memoria se perdio -- un reinicio
    del motor, ver _sesion_nueva(). Sin esto, el especialista arranca con
    CERO contexto de por que esta atendiendo, y se vio en vivo (agosto
    2026) que sin esa aclaracion podia derivar de nuevo a otra area sin
    ningun motivo real, solo por no saber que ya estaba en la correcta.

    Devuelve (respuesta, registro_herramientas, medios_pendientes).

    'registro_herramientas': una fila por herramienta invocada este turno --
    nombre, parametros enmascarados, exito, duracion -- para que
    nucleo/canales/api.py lo guarde en asistente.tool_calls despues de
    resolver el conversation_id (que todavia no existe en este punto: la
    conversacion se crea/reusa recien al persistir el turno). Es la base de
    "ver proceso" en /conversaciones: que hizo el agente, en que orden, sin
    que el motor sepa que existe esa pantalla.

    'medios_pendientes': igual problema, mismo motivo -- un archivo generado
    por una herramienta 'agregado' con 'exportable' (ver
    nucleo/herramientas/informes.py) no se puede guardar en asistente.media
    aca porque esa tabla exige conversation_id, que todavia no existe. Casi
    siempre vacia: solo trae algo cuando el turno de verdad genero un
    archivo.
    """
    rol_cfg = config.roles.get(nombre_rol)
    if rol_cfg is None:
        raise ErrorMotor(f"Rol '{nombre_rol}' no existe en la configuracion del tenant.")

    registro: list[dict] = []
    medios_pendientes: list[dict] = []
    # Datos que una herramienta produjo y el cliente TIENE que recibir en este
    # turno (ej. el link del formulario). Se llenan al ejecutar y se comprueban
    # justo antes de contestar -- ver 'campo_obligatorio_en_respuesta'.
    obligatorios: list[str] = []

    if not historial:
        historial.append({"role": "system", "content": construir_system(config, nombre_rol)})
        if nota_continuidad:
            historial.append({"role": "system", "content": nota_continuidad})
        # Si la sesion YA venia verificada (lo normal en WhatsApp a partir
        # del segundo mensaje) hay que DECIRLO. El modelo lo deducia solo
        # cuando una herramienta le devolvia datos reales -- señal que
        # desaparece en un rol sin herramientas de datos, como el router:
        # ahi volvia a pedir la cedula de alguien ya verificado, en cada
        # conversacion. Verificado en vivo (agosto 2026).
        if sesion is not None and sesion.verificado:
            # El NOMBRE va en el mensaje a proposito. Sin el, ante "¿vos sabes
            # quien soy?" el modelo no tiene con que contestar y se inventa
            # una explicacion -- visto en vivo (15/08/2026): dijo "tu chat
            # esta asociado a tu cuenta porque escribis desde el WhatsApp que
            # tenes registrado" y "el sistema me confirma que sos el
            # titular", las dos frases fabricadas. Con el nombre a mano puede
            # contestar con la verdad, que ademas es el dato que el cliente
            # esta pidiendo. No es una fuga: es SU propio nombre, y ya se lo
            # dijimos al verificarlo ("el servicio figura a nombre de X").
            # Son DOS preguntas distintas y se contestan distinto. Mezclarlas
            # en una sola regla salio mal (15/08/2026): ante "¿sabes quien te
            # habla?" contestaba "tu identidad quedo verificada antes en esta
            # conversacion" -- cierto, pero le respondia sobre el TRAMITE a
            # alguien que preguntaba por su NOMBRE, teniendolo a mano. Suena a
            # evasiva justo donde el cliente esta midiendo si le hablan a el o
            # a un numero de expediente.
            quien = (f" QUIEN es: el servicio figura a nombre de {sesion.nombre}"
                     " -- si te pregunta si sabes quien te habla, o como se"
                     " llama, dile el nombre, es el dato que esta pidiendo y"
                     " es suyo." if sesion.nombre else "")
            historial.append({"role": "system", "content":
                "Este cliente YA esta verificado: no le pidas la cedula ni "
                f"ningun dato de identidad, sigue directo con lo que necesita.{quien}"
                " COMO se supo es otra cosa: si te pregunta como lo sabes, o "
                "por que no le pediste datos, contestale solo que su identidad "
                "quedo verificada antes en esta misma conversacion. NUNCA "
                "expliques el mecanismo ni inventes uno (no digas que lo "
                "reconociste por su numero, por su chat, ni que 'el sistema lo "
                "confirma') -- si no sabes como se verifico, decilo asi de "
                "simple y ofrecele confirmarlo de nuevo con su cedula."})
    historial.append({"role": "user", "content": mensaje})

    herramientas = herramientas_del_rol(config, rol_cfg)
    catalogo_openai = [_esquema_openai(h) for h in herramientas]

    # --- Habilidades: que procedimientos puede cargar este rol -----------------
    # Solo el INDICE (codigo + cuando usar cada uno), no los pasos. Es barato y
    # va en todos los turnos porque el modelo no puede elegir lo que no sabe que
    # existe; el cuerpo se paga solo cuando llama a cargar_habilidad. Ver
    # nucleo/habilidades/catalogo.py.
    #
    # A diferencia del RAG, esto NO depende del parecido con el mensaje: una
    # habilidad hace falta en situaciones que el mensaje no nombra. Por eso el
    # indice entra siempre y es el modelo, leyendo el disparador, quien decide.
    #
    # Nunca rompe el turno: sin habilidades el agente trabaja como venia
    # trabajando hasta hoy.
    try:
        indice_habilidades = catalogo_habilidades.indice_de(
            config.identidad.slug, nombre_rol)
    except Exception as e:
        print(f"[habilidades] no se pudo leer el indice: {e}")
        indice_habilidades = []

    if indice_habilidades:
        historial.append({"role": "system",
                          "content": catalogo_habilidades.bloque_de_indice(
                              indice_habilidades)})

    # --- RAG: que dice la documentacion interna sobre esto ---------------------
    # Va DESPUES del catalogo de herramientas porque la decision de que hacer
    # cuando el corpus no responde depende de si el rol tiene con que buscar el
    # dato en otro lado.
    #
    # Nunca rompe el turno: si Ollama no responde o la base falla, se sigue sin
    # contexto documental. Peor es no atender.
    #
    # SALVO que el rol tenga una herramienta de documentacion declarada. En ese
    # caso NO se precarga: el modelo la pide cuando la necesita, igual que
    # cualquier otro dato. Ver Herramienta.consulta_documentacion (schema.py)
    # para la medicion que motivo el cambio.
    #
    # La condicion existe para poder migrar rol por rol y volver atras sin
    # tocar codigo: un rol que no declara la herramienta sigue funcionando
    # exactamente como funcionaba.
    if any(getattr(h, "consulta_documentacion", False) for h in herramientas):
        fragmentos, mejor = [], None
        _corpus_es_herramienta = True
    else:
        _corpus_es_herramienta = False
        try:
            fragmentos, mejor = recuperar(config, config.identidad.slug,
                                          nombre_rol, mensaje)
        except Exception as e:
            print(f"[rag] no se pudo recuperar contexto: {e}")
            fragmentos, mejor = [], None

    if fragmentos:
        citar_fuente = rol_cfg.orientado_a != "cliente_final"
        historial.append({"role": "system",
                          "content": bloque_de_contexto(fragmentos, citar_fuente)})
    elif not _corpus_es_herramienta:
        # Con el corpus como herramienta esta rama no corresponde: no se
        # busco nada todavia. El registro de "el corpus no cubre esto" lo hace
        # la herramienta cuando de verdad busca y no encuentra -- si no,
        # quedaria una fila por CADA turno, incluidos los que nunca iban a
        # necesitar documentacion, y ese registro es justamente el que se usa
        # para saber que documentacion falta escribir.
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
            return respuesta, registro, medios_pendientes

    referencia_decision = config.llm.overrides.get(f"rol:{nombre_rol}",
                                                    config.llm.modelo_por_defecto)
    referencia_redaccion = config.llm.modelo_redaccion or referencia_decision

    # 'exige_verificacion=False' (ver schema.py) es la salida: un cliente_final
    # que TODAVIA NO ES CLIENTE (ej. 'ventas') no tiene nada que verificar
    # contra WispHub, asi que el gate completo queda en 0 para ese rol. Sin
    # este chequeo el codigo bloqueaba la herramienta igual aunque el prompt
    # ya le hubiera dicho al modelo que no hacia falta verificar -- el
    # modelo terminaba recibiendo IDENTIDAD_NO_VERIFICADA sin entender por
    # que, y esa entrada se excluye del registro (ver mas abajo), asi que
    # parecia que no habia intentado nada. Bug real, visto en vivo el
    # 19/08/2026 con el rol 'ventas' recien creado.
    _cliente_final_verificable = (rol_cfg.orientado_a == "cliente_final"
                                  and rol_cfg.exige_verificacion)
    nivel_exigido = nivel_requerido(rol_cfg, config.seguridad) if _cliente_final_verificable else 0
    # Sin un telefono real de por medio, el identificador del canal (ej. un
    # BSUID de WhatsApp) no es un factor de posesion -- cualquiera que
    # escriba desde esa cuenta pasaria la barra igual. Se exige nivel 1 ANTES
    # de cualquier herramienta, no solo de las marcadas sensibles: es la
    # unica forma de saber quien es, y sin esto la conversacion queda para
    # siempre como "sin identificar" en /conversaciones si nunca toca un
    # recurso protegido.
    #
    # Y EL TELEFONO SOLO CUENTA SI RESOLVIO A UN CLIENTE (27/08/2026). Poseer
    # el numero prueba que controlas ESE numero, no que seas un cliente
    # concreto: si no esta vinculado a ninguno, no hay contra que contrastar
    # la posesion y el descuento no se gana. Antes bastaba con que el
    # identificador fuera de digitos, asi que un numero cualquiera --que no es
    # cliente de nadie-- entraba a un rol que exige verificacion con
    # 'nivel_exigido' en 0. Medido: con eso, al primer mensaje se llamo a
    # WispHub y volvieron 300 filas de 7.356 clientes.
    #
    # 'inyectados_obligatorios' ya impide que se filtre un dato de cliente por
    # ahi, pero esto es la otra mitad: las herramientas que NO inyectan
    # identidad seguian abiertas -- entre ellas 'registrar_pedido_wifi', que
    # crea un ticket. Dos capas, como el resto del proyecto (PRD 7.4).
    #
    # No estorba a nadie que ya se identifico: si hay 'id_cliente', la sesion
    # esta verificada y su nivel ya es 1. Y no toca a 'ventas' ni al agente
    # general, que declaran exige_verificacion=False -- un prospecto se sigue
    # atendiendo igual, que es justamente quien nunca va a poder verificarse.
    _posesion_util = (es_factor_de_posesion(sesion.identificador_canal)
                      and bool(getattr(sesion, "id_cliente", None))) if sesion else False
    if _cliente_final_verificable and sesion is not None and not _posesion_util:
        nivel_exigido = max(nivel_exigido, 1)

    # Cache DENTRO DE ESTE TURNO: {(nombre, argumentos_del_modelo) -> (salida,
    # codigo_error)}. Visto en vivo (agosto 2026, diagnostico de SmartOLT): el
    # modelo a veces pide la MISMA consulta de solo lectura dos veces en el
    # mismo turno (dos iteraciones del bucle de abajo), sin que haya pasado
    # nada nuevo que justifique repetirla -- duplica la latencia y el consumo
    # de la API externa sin agregar dato alguno. Solo aplica a solo_lectura:
    # una escritura nunca se sirve de una copia vieja.
    cache_turno: dict[tuple[str, str], tuple[object, str | None]] = {}
    # Que herramientas ya recibieron el empujon de 'sugerir_cuando_disponible'
    # en este turno -- ver el bloque despues del for de abajo.
    ya_sugeridas_este_turno: set[str] = set()

    hubo_llamadas = False
    # Se enciende si la conversacion cambia de rol A MITAD de este turno
    # (ver el bloque de derivacion, mas abajo) y ya no se apaga: de ahi en
    # mas, todo lo que haga el especialista sale del mensaje de entrada que
    # recibio la puerta, no de algo que el cliente le haya dicho a EL.
    # Lo usa 'Herramienta.exige_turno_propio'.
    derivado_en_este_turno = False
    iteraciones = 0
    # Los reintentos por una llamada mal escrita se cuentan APARTE (ver mas
    # abajo): son un error de formato del modelo, no trabajo hecho, y
    # cobrarselos al presupuesto de iteraciones deja al turno sin margen para
    # terminar lo que estaba haciendo. Con tope propio para que no giren solos.
    reintentos_fuga = 0
    while iteraciones < config.llm.limite_iteraciones_agente:
        iteraciones += 1
        resp = cliente.chat(referencia_decision, historial,
                            tools=catalogo_openai or None, temperatura=config.llm.temperatura)

        if not resp.llamadas:
            # Antes de decidir nada: si el modelo pidio herramientas
            # escribiendolas en vez de usar la API, se ejecutan igual. Ver
            # _llamadas_fugadas -- es reproducible con DeepSeek y reintentar
            # no lo corrige, pero el texto dice exactamente que queria.
            rescatadas = _llamadas_fugadas(resp.contenido, herramientas)
            if rescatadas:
                print(f"[motor] el modelo escribio {len(rescatadas)} llamada(s) "
                      f"en vez de invocarlas; se ejecutan igual: "
                      f"{[l.nombre for l in rescatadas]}")
                resp.llamadas = rescatadas
                resp.contenido = ""

        if not resp.llamadas:
            # La decision se toma sobre el texto YA LIMPIO, no sobre el crudo.
            # DeepSeek a veces no usa el tool-calling de la API y escribe la
            # llamada como texto con sus tokens de control
            # ('<｜｜DSML｜｜invoke name="consultar_estado_ont">'). Eso llega
            # aca con 'llamadas' vacio y 'contenido' lleno, y medido sobre el
            # crudo parecia "ya no pide mas herramientas" -- el motor pasaba a
            # redactar cuando el modelo todavia queria medir. En la redaccion
            # las herramientas ya estan apagadas, asi que lo repetia, se
            # limpiaba a vacio, y el cliente terminaba viendo "No pude
            # terminar de redactar la respuesta". Reproducido en vivo el
            # 15/08/2026 con una falla de TV, tres veces seguidas.
            limpio = _sanitizar(resp.contenido, config.roles,
                                config.persona.normalizar_tratamiento)
            if limpio:
                if not hubo_llamadas:
                    limpio, fuga = guardia_salida.verificar(limpio)
                    if fuga:
                        print(f"[salida] fuga bloqueada en rol '{nombre_rol}': '{fuga}'")
                    limpio = _con_obligatorios(limpio, obligatorios)
                    historial.append({"role": "assistant", "content": limpio})
                    return limpio, registro, medios_pendientes
                break  # ya no pide mas herramientas: pasa a redaccion final
            if _RE_FUGA_TOOL_CALL.search(resp.contenido or "") and reintentos_fuga < 2:
                # Queria seguir usando herramientas y lo escribio mal: se le
                # da otra vuelta del bucle, con el catalogo todavia
                # disponible, en vez de mandarlo a redactar sin los datos.
                reintentos_fuga += 1
                iteraciones -= 1
                continue
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
            # Se inicializa para TODA llamada, no solo para la rama que mide:
            # la traza se arma mas abajo para cualquiera de los caminos de
            # despacho, y una accion que salio por otra rama tiene que llegar
            # ahi con la medicion en None, no sin definir.
            medicion_previa = None

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
            elif herramienta.consulta_planes_venta:
                # tipo 'interno', igual que las de arriba: no llama a ninguna
                # API, solo lee TenantConfig.planes_venta. Nunca pasa por el
                # gate de identidad -- no revela ningun dato de cliente, solo
                # el catalogo de planes que un humano ya decidio publicar.
                salida = _ejecutar_consulta_planes_venta(config, llamada.argumentos)
            elif herramienta.consulta_documentacion:
                # Fuera del gate: una guia de procedimientos no menciona a
                # ningun cliente. Ver el porque del cambio entero en
                # Herramienta.consulta_documentacion (schema.py).
                salida = _ejecutar_consulta_documentacion(
                    config, nombre_rol, llamada.argumentos)
            elif herramienta.carga_habilidad:
                # Fuera del gate por el mismo motivo que las de arriba: un
                # procedimiento no menciona a ningun cliente. Y hace falta
                # justo antes de verificar -- el procedimiento puede ser el
                # que explica COMO pedir la verificacion.
                salida = _ejecutar_carga_habilidad(config, nombre_rol, llamada.argumentos)
            elif (rol_cfg.orientado_a == "cliente_final" and (sesion is None or sesion.nivel < nivel_exigido)
                  # Excepcion: 'derivar_a_area' hacia un area que declara
                  # exige_verificacion=False (ej. 'ventas') tiene que poder
                  # llamarse SIN estar verificado -- es justamente la salida
                  # para alguien que nunca va a poder verificarse porque
                  # todavia no es cliente. Sin esto, el gate bloqueaba la
                  # derivacion misma antes de que pudiera llegar al area que
                  # no la necesita: bug real, visto en vivo el 19/08/2026 --
                  # el modelo intentaba derivar, recibia IDENTIDAD_NO_VERIFICADA
                  # (que se excluye del registro, ver mas abajo, asi que
                  # parecia que no habia intentado nada) y terminaba
                  # inventando una excusa en vez de la derivacion real.
                  and not (herramienta.deriva_rol
                          and not config.roles.get(
                              (llamada.argumentos or {}).get("area"), rol_cfg
                          ).exige_verificacion)):
                salida = {"error": "IDENTIDAD_NO_VERIFICADA",
                         "instruccion_interna": "No muestres ningun dato. "
                             "Pidele al cliente el dato que falta para "
                             "verificar su identidad antes de continuar."}
                codigo_error = "IDENTIDAD_NO_VERIFICADA"
            elif herramienta.deriva_rol:
                # Despues del gate a proposito, pero el gate en si mismo ya
                # sabe dejar pasar esta llamada sin identidad verificada
                # cuando el area de destino no la exige (ver la excepcion
                # en el gate mas arriba, y Rol.exige_verificacion/
                # deriva_verificacion en schema.py) -- 19/08/2026: la
                # verificacion se movio del router a cada especialista, asi
                # que 'derivar_a_area' tiene que poder ejecutarse ANTES de
                # que nadie este verificado.
                salida = _ejecutar_derivacion(herramienta, sesion, llamada.argumentos, nombre_rol)
            elif herramienta.exige_turno_propio and derivado_en_este_turno:
                # Fail-closed: la conversacion llego a esta area en este
                # mismo turno y la puerta declaro que el cliente NO dijo que
                # servicio se le cayo. Una accion que le interrumpe el
                # servicio no puede salir de un reporte ambiguo -- podria
                # estar cortandole justo el que si le andaba (ver
                # 'exige_turno_propio' en schema.py).
                salida = {"error": "FALTA_HABLAR_CON_EL_CLIENTE",
                         "instruccion_interna": "Esta conversacion acaba de "
                             "llegar a tu area y el cliente todavia no te "
                             f"escribio a vos: '{herramienta.nombre}' le "
                             "interrumpe el servicio, asi que no la puedes "
                             "usar en este turno. Primero MIDE lo que puedas "
                             "(estado del equipo, señal, ping) y preguntale "
                             "lo que ningun sistema te dice -- en cuantos "
                             "aparatos le falla, si tiene alguno por cable. "
                             "Con lo que responda decides si esto sigue "
                             "haciendo falta."}
                codigo_error = "FALTA_HABLAR_CON_EL_CLIENTE"
            elif herramienta.sondea_api:
                # Colaborador (ADMIN, gateado en la capa web -- ver
                # nucleo/canales/api.py), nunca cliente_final: el gate de
                # identidad de arriba no aplica a este rol para empezar.
                salida = _ejecutar_sondeo(llamada.argumentos, config.identidad.slug)
            elif herramienta.propone_herramienta:
                quien = sesion.identificador_canal if sesion else "desconocido"
                salida = _ejecutar_propuesta(llamada.argumentos, config.identidad.slug, quien)
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
                             "herramienta no es el siguiente paso, sigue el "
                             "protocolo alternativo en vez de insistir."}
                codigo_error = "PRECONDICION_NO_CUMPLIDA"
            elif herramienta.limite_por_conversacion is not None and _veces_ejecutada(
                    herramienta, historial) >= herramienta.limite_por_conversacion:
                salida = {"error": "LIMITE_DE_CONVERSACION",
                         "instruccion_interna": f"'{herramienta.nombre}' ya se "
                             "uso el maximo de veces permitidas en esta "
                             "conversacion. No la repitas -- si el cliente "
                             "insiste, dile que un colaborador humano va a "
                             "seguir el caso."}
                codigo_error = "LIMITE_DE_CONVERSACION"
            elif herramienta.aprobacion_humana:
                # Mecanismo NUEVO (18/08/2026), separado de
                # 'requiere_confirmacion' -- ver el comentario de
                # aprobacion_humana en schema.py sobre por que no se reuso
                # ese campo. Despues del gate de identidad y de
                # precondiciones/limite: no tiene sentido proponer una
                # accion que de entrada no se podria ejecutar.
                quien = sesion.identificador_canal if sesion else "desconocido"
                salida = _ejecutar_propuesta_de_accion(
                    herramienta, sesion, llamada.argumentos,
                    config.identidad.slug, nombre_rol, quien)
            else:
                clave_cache = (herramienta.nombre,
                              json.dumps(llamada.argumentos or {}, sort_keys=True))
                if herramienta.solo_lectura and clave_cache in cache_turno:
                    salida, codigo_error = cache_turno[clave_cache]
                else:
                    # La medicion de ANTES se toma aca, pegada a la accion, y
                    # no de lo que el modelo haya consultado antes: asi el
                    # punto de partida es siempre el mismo instante y no
                    # depende de que herramientas se le ocurrio pedir.
                    if herramienta.verificacion and not herramienta.solo_lectura:
                        medicion_previa = medir_para_verificar(
                            config, herramienta.verificacion, sesion,
                            config.identidad.slug, config.variables_tenant)
                    try:
                        crudo = _ejecutar_tool(herramienta, sesion, llamada.argumentos,
                                              config.identidad.slug, config.variables_tenant)
                        _recuperar_campos_de_sesion(sesion, herramienta, crudo)
                        formato_pedido = (llamada.argumentos or {}).get("formato")
                        if (herramienta.tipo == "agregado" and herramienta.exportable
                                and isinstance(crudo, dict) and "error" not in crudo
                                and formato_pedido in _GENERADORES_INFORME):
                            # El archivo lo arma el codigo a partir del MISMO
                            # 'crudo' que ya se iba a redactar en texto -- el
                            # modelo no aporta ni ve un solo dato nuevo, solo
                            # el identificador para poder mencionarlo. Un
                            # fallo aca (ej. falta la libreria) no tumba el
                            # turno: 'error_archivo' queda en 'crudo' y el
                            # modelo puede avisar que el archivo no se pudo
                            # generar, en vez de fingir que si (RF-07).
                            generar, mime = _GENERADORES_INFORME[formato_pedido]
                            try:
                                archivo = generar(crudo.get("interpretacion", ""), crudo)
                                media_id = str(uuid.uuid4())
                                medios_pendientes.append({
                                    "media_id": media_id,
                                    "tipo": "document",
                                    "mime": mime,
                                    "contenido": archivo,
                                    "descripcion": crudo.get("interpretacion", ""),
                                })
                                crudo["archivo_id"] = media_id
                            except informes.ErrorInforme as e:
                                crudo["error_archivo"] = str(e)
                        salida = listas_blancas.filtrar_campos(rol_cfg, herramienta.nombre, crudo)
                        if herramienta.campos_texto_libre:
                            salida = redaccion.redactar_campos(
                                salida, herramienta.campos_texto_libre)
                    except FaltaIdentidadEnSesion as e:
                        # No es un fallo del sistema: es la proteccion haciendo
                        # su trabajo. Se le dice al modelo QUE hacer -- pedir la
                        # cedula-- en vez de dejarlo anunciar una averia que no
                        # existe. Codigo propio para poder contarlo aparte en la
                        # auditoria: esto tiene que poder verse.
                        salida = {"error": "IDENTIDAD_NO_RESUELTA",
                                 "instruccion_interna":
                                     f"'{e.herramienta}' consulta datos de UN "
                                     f"cliente y la sesion todavia no sabe cual. "
                                     f"No la reintentes ni le digas al cliente "
                                     f"que hubo un problema tecnico: pedile su "
                                     f"numero de cedula y verifica la identidad "
                                     f"primero."}
                        codigo_error = "IDENTIDAD_NO_RESUELTA"
                    except Exception as e:
                        # No tumba el turno: el modelo recibe un error legible y
                        # puede decirle al cliente que hubo un problema, en vez de
                        # que /chat completo se caiga con un 500.
                        salida = {"error": "No se pudo completar la consulta en este momento."}
                        codigo_error = f"{type(e).__name__}: {e}"[:200]
                    if herramienta.solo_lectura:
                        cache_turno[clave_cache] = (salida, codigo_error)

            # Un dato que el modelo NO tiene hasta que esta herramienta salio
            # bien -- ver 'entrega_variable' en schema.py. Va aca, despues de
            # toda la cadena de despacho, para que valga sea cual sea la rama
            # que atendio la llamada: si manana la herramienta que entrega el
            # dato pasa a ser 'interno' o queda detras del gate de identidad,
            # esto sigue funcionando igual.
            #
            # Las tres condiciones son el punto entero: si la herramienta no
            # existe, si fallo, o si devolvio un error, el dato NO se entrega.
            # Asi el modelo no puede dar el link de un formulario cuando la
            # solicitud no quedo registrada -- no lo tiene.
            # Se mira el VALOR de 'error', no si la clave existe: BottleCRM
            # responde {"error": false, "message": "..."} cuando todo salio
            # bien, asi que preguntar por la clave habria dado siempre "fallo"
            # y el link no se hubiera entregado nunca.
            if (herramienta is not None and herramienta.entrega_variable
                    and codigo_error is None
                    and not (isinstance(salida, dict) and salida.get("error"))):
                valor = (config.variables_tenant or {}).get(herramienta.entrega_variable)
                if valor and isinstance(salida, dict):
                    salida[herramienta.entrega_variable] = valor

            # Un dato que el cliente TIENE que recibir si esto salio bien --
            # ver 'campo_obligatorio_en_respuesta' en schema.py. Se anota
            # ahora, y antes de contestar se comprueba que este en el texto.
            if (herramienta is not None and herramienta.campo_obligatorio_en_respuesta
                    and codigo_error is None and isinstance(salida, dict)
                    and not salida.get("error")):
                imprescindible = salida.get(herramienta.campo_obligatorio_en_respuesta)
                if imprescindible:
                    obligatorios.append(str(imprescindible))

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
                # Lo que la herramienta declaro como resumen del caso, si
                # declaro alguno (Herramienta.resumen_desde). Viaja SOLO ese
                # campo y no la respuesta entera: la traza no es lugar para un
                # registro de cliente completo, y quien la escribe a la base
                # ademas la ignora -- esto existe para el turno, no para
                # guardarse.
                resumen_pedido = ""
                if (herramienta and herramienta.resumen_desde
                        and codigo_error is None and isinstance(salida, dict)):
                    resumen_pedido = str(salida.get(herramienta.resumen_desde) or "")
                # La verificacion pendiente viaja con la traza porque aca
                # todavia no existe conversation_id -- lo resuelve api.py al
                # persistir el turno, igual que con los archivos generados.
                pendiente = None
                if (herramienta and herramienta.verificacion
                        and not herramienta.solo_lectura and codigo_error is None):
                    pendiente = {
                        "espera_segundos": herramienta.verificacion.espera_segundos,
                        "max_intentos": herramienta.verificacion.max_intentos,
                        "medicion_previa": medicion_previa,
                    }
                registro.append({
                    "herramienta": llamada.nombre,
                    "parametros": _enmascarar(llamada.argumentos),
                    "resumen": resumen_pedido,
                    "verificacion_pendiente": pendiente,
                    "exito": codigo_error is None,
                    "n_registros": len(salida) if isinstance(salida, list) else None,
                    "codigo_error": codigo_error,
                    "duracion_ms": int((time.monotonic() - t0) * 1000),
                    "es_escritura": bool(herramienta and not herramienta.solo_lectura),
                })

            historial.append({"role": "tool", "name": llamada.nombre,
                              "tool_call_id": f"call_{i}",
                              "content": json.dumps(salida, ensure_ascii=False)})

        # Segunda oportunidad de decision: el modelo que arma esta tanda de
        # llamadas lo hace ANTES de tener los resultados, asi que no puede
        # haber decidido llamar 'reiniciar_ont' (ni cualquier otra con
        # 'exige_previas') en el mismo lote que recien la habilita. Sin este
        # empujon, el modelo tipicamente pasa derecho a redactar con lo que
        # ya tiene -- la respuesta final ('_redactar') ni siquiera puede
        # llamar herramientas (tools=None), asi que esta es la UNICA
        # ventana. Una vez por herramienta por turno (no reinsistir si el
        # modelo ya lo vio y opto por otra cosa) y solo si todavia no se
        # intento ejecutar en esta conversacion.
        for h in herramientas:
            if (h.exige_previas and h.sugerir_cuando_disponible
                    and h.nombre not in ya_sugeridas_este_turno
                    and _veces_ejecutada(h, historial) == 0
                    and not _previas_no_cumplidas(h, historial)):
                historial.append({"role": "system", "content": h.sugerir_cuando_disponible})
                ya_sugeridas_este_turno.add(h.nombre)

        # DERIVACION EN EL MISMO TURNO. Si el modelo acaba de derivar a otra
        # area, el especialista atiende ACA, no en el proximo mensaje del
        # cliente: se rearma el catalogo con SUS herramientas y se le da su
        # prompt, y el bucle sigue.
        #
        # Sin esto, derivar le cuesta al cliente un intercambio entero: el
        # router contesta "dale, te ayudo con eso", el cliente tiene que
        # volver a escribir, y recien ahi lo atienden -- sobre turnos que ya
        # tardan 20-40s. Con el rearme, el cliente ve UNA respuesta, ya
        # resuelta por quien corresponde.
        #
        # El prompt del area nueva entra como 'system' al final del
        # historial, no reemplazando al de arriba: el modelo necesita el
        # contexto de lo que ya paso en la conversacion (que se pidio, que
        # devolvieron las herramientas), no empezar de cero.
        if sesion is not None and getattr(sesion, "rol_siguiente", None):
            rol_nuevo = sesion.rol_siguiente
            rol_cfg_nuevo = config.roles.get(rol_nuevo)
            if rol_cfg_nuevo is not None and rol_nuevo != nombre_rol:
                nombre_rol = rol_nuevo
                rol_cfg = rol_cfg_nuevo
                herramientas = herramientas_del_rol(config, rol_cfg)
                catalogo_openai = [_esquema_openai(h) for h in herramientas]
                # Mismo criterio que al entrar al turno -- ver el comentario
                # de '_cliente_final_verificable' mas arriba. Aca importa
                # todavia mas: es el momento en que derivar_a_area cambia el
                # rol activo a mitad de turno (ej. a 'ventas'), y sin esto el
                # gate seguia calculado para el rol VIEJO.
                _cliente_final_verificable_nuevo = (rol_cfg.orientado_a == "cliente_final"
                                                    and rol_cfg.exige_verificacion)
                nivel_exigido = (nivel_requerido(rol_cfg, config.seguridad)
                                if _cliente_final_verificable_nuevo else 0)
                # Mismo criterio que al entrar al turno: el telefono solo
                # cuenta como posesion si resolvio a un cliente. Este es
                # justamente el camino del caso del WiFi -- derivar_a_area
                # cambia el rol a uno que exige verificacion a mitad de turno,
                # y sin esto el descuento del telefono se aplicaba igual.
                _posesion_util_nuevo = (
                    es_factor_de_posesion(sesion.identificador_canal)
                    and bool(getattr(sesion, "id_cliente", None))) if sesion else False
                if (_cliente_final_verificable_nuevo and sesion is not None
                        and not _posesion_util_nuevo):
                    nivel_exigido = max(nivel_exigido, 1)
                # El empujon de 'sugerir_cuando_disponible' se evalua contra
                # el catalogo nuevo: lo ya sugerido para el rol viejo no
                # aplica a herramientas que recien ahora existen.
                ya_sugeridas_este_turno.clear()
                derivado_en_este_turno = True
                historial.append({"role": "system",
                                  "content": construir_system(config, nombre_rol)})
                historial.append({"role": "system", "content":
                    f"Tu atiendes ahora esta conversacion, en el mismo mensaje "
                    f"-- el cliente NO tiene que volver a escribir. Sigue "
                    f"desde donde quedo (ya esta verificado, no le pidas la "
                    f"identidad de nuevo) y resolvele lo que pidio con TUS "
                    f"herramientas. No le digas que lo estas derivando ni que "
                    f"lo pasas con otra area: para el es la misma "
                    f"conversacion."})
                # 'sesion.rol_siguiente' NO se limpia aca a proposito:
                # nucleo/canales/api.py lo lee DESPUES de que responder()
                # vuelve, para persistir 'rol_efectivo' y que el proximo
                # mensaje del cliente entre directo al area correcta. Si se
                # limpiara, el handoff funcionaria en este turno y se
                # perderia en el siguiente. Tampoco hace falta para detectar
                # una segunda derivacion: 'nombre_rol' ya quedo igual a
                # 'rol_siguiente', asi que este bloque no vuelve a disparar
                # salvo que el especialista derive de nuevo (y ahi cambia el
                # valor). El ping-pong queda acotado por
                # 'limite_iteraciones_agente'.

    if hubo_llamadas:
        # Igual que en el retorno directo de mas arriba: la redaccion final es
        # otra llamada al modelo, asi que tambien puede quedarse sin el dato.
        return (_con_obligatorios(
                    _redactar(referencia_redaccion, historial, config.llm.temperatura,
                              nombres_rol=config.roles,
                              tratamiento=config.persona.normalizar_tratamiento),
                    obligatorios),
                registro, medios_pendientes)
    return ("No pude completar la consulta en el numero de pasos permitido.",
            registro, medios_pendientes)
