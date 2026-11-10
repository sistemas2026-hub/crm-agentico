# -*- coding: utf-8 -*-
"""Mandar al ISP la ubicacion que tomo un tecnico parado en la casa.

POR QUE PASA POR EL MOTOR Y NO LE PEGA AL ISP DIRECTO. Medido el 10/11/2026:
`grep` de `requests.patch|requests.put|"PATCH"` sobre todo `backend/`
(excluyendo pruebas) devuelve CERO. Django nunca escribe en los sistemas del
ISP por su cuenta, y esa propiedad vale mas que la comodidad de ahorrarse un
salto: la credencial vive solo en el motor, y la frontera de autorizacion
--interruptor, puerta humana, idempotencia-- tambien.

LA RUTA ES DEDICADA, `/interno/orden/<id>/guardar-ubicacion`, y no la generica
`/interno/herramienta/<nombre>`: esa entra por la puerta AUTONOMA, que hoy
esta cerrada por Autonomia 2. Por ahi el boton andaria en local y fallaria
solo en produccion.

PRIVACIDAD: la coordenada NO se escribe en ningun log ni en ningun evento.
Es el domicilio de una persona. Lo que queda registrado es que se guardo (o
que no) y en que sistemas, nunca donde.
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

#: Lo mismo que el motor, pero del lado de aca: sirve para no hacer el viaje
#: cuando ya se sabe que la respuesta va a ser que no.
_LAT_MAX = 90.0
_LNG_MAX = 180.0


def _tenant_de(orden):
    from operaciones import areas_del_tenant

    return areas_del_tenant.tenant_de(orden.org_id)


def _nombre_de(profile) -> str:
    """Quien decidio, para la puerta humana. El NOMBRE, nunca el email.

    EL MODELO DE ESTE PROYECTO TIENE UN SOLO CAMPO DE NOMBRE: `name`
    (`common/models.py`). No tiene `get_full_name`, ni `first_name`, ni
    `username` -- `USERNAME_FIELD` es el email.

    Esta funcion buscaba esos tres, medido el 10/11/2026 con el boton ya
    desplegado: ninguno existia, devolvia cadena vacia, y la peticion moria en
    `sin_actor` con un 400 antes de salir de Django. El motor no llego a
    enterarse. La prueba no lo vio porque su doble de usuario TENIA
    `get_full_name()`: estaba verde contra un modelo imaginario.

    Y SI NO HAY NOMBRE, CAE AL ID DEL PERFIL en vez de rechazar. Una cuenta
    sin nombre cargado es un dato faltante, no una falta de responsable: el
    perfil identifica a la persona igual --mejor, incluso: dos tecnicos
    homonimos son el mismo nombre y distinto id--. Rechazar por eso dejaba la
    capacidad muerta para cualquier cuenta sin nombre.
    """
    if profile is None:
        return ""
    user = getattr(profile, "user", None)
    nombre = str(getattr(user, "name", "") or "").strip()
    if nombre:
        return nombre
    #  El email NO: identifica a la persona igual pero es un dato de contacto,
    #  y este valor viaja al motor y puede quedar en una fila de auditoria.
    pid = getattr(profile, "id", None)
    return f"perfil:{pid}" if pid else ""


def _numero(valor):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def es_una_coordenada(latitud, longitud) -> bool:
    """La misma regla que el motor, aplicada antes de hacer el viaje.

    SE REPITE A PROPOSITO, y no es la guarda: la que manda es la del motor,
    que corre pegada a la escritura. Esta solo evita un viaje y un mensaje de
    error peor. Si alguna vez discrepan, gana la del motor -- por eso ninguna
    de las dos se escribio pensando que la otra existe.
    """
    lat, lng = _numero(latitud), _numero(longitud)
    if lat is None or lng is None:
        return False
    if abs(lat) > _LAT_MAX or abs(lng) > _LNG_MAX:
        return False
    if lat == 0.0 and lng == 0.0:
        return False
    return True


def guardar_ubicacion(orden, *, latitud, longitud, profile) -> dict:
    """Deja la ubicacion escrita en los sistemas del ISP.

    Responde siempre un dict con `guardada`, `codigo` y `detalle`, y nunca
    levanta: el tecnico esta en la calle y una excepcion aca le tumbaria la
    pantalla.
    """
    from campo.services import telemetria

    if not es_una_coordenada(latitud, longitud):
        return {"guardada": False, "codigo": "coordenada_invalida",
                "detalle": "la ubicacion recibida no es un punto del planeta"}

    #  LO QUE SIGUE VA DENTRO DE UN `try` Y NO ES CEREMONIA (10/11/2026,
    #  hallazgo de una revision de PII). Esta funcion promete no levantar, y
    #  tres llamadas quedaban afuera --la empresa, el serial y el servicio--;
    #  cualquiera de las tres toca la base o la ficha congelada y puede
    #  reventar. Una excepcion que sale de aca llega a DRF como 500, y el
    #  archivo de al lado ya tiene escrito lo que pasa entonces: `con DEBUG
    #  encendido la pagina de error de Django devolvia la coordenada en el
    #  cuerpo` (`campo/ubicacion_views.py`). No se depende de que DEBUG este
    #  apagado para que el domicilio no salga en una respuesta HTTP.
    try:
        tenant = _tenant_de(orden)
        actor = _nombre_de(profile)
        serial = telemetria.serial_de(orden)
        servicio = telemetria.servicio_de(orden)
    except Exception as e:                                      # noqa: BLE001
        logger.warning("ubicacion_al_isp: no se pudo leer la orden (%s)",
                       type(e).__name__)
        return {"guardada": False, "codigo": "sin_empresa",
                "detalle": type(e).__name__}

    if not tenant:
        return {"guardada": False, "codigo": "sin_empresa",
                "detalle": "sin saber de que empresa es la orden no se le "
                           "escribe al ISP"}

    if not actor:
        #  LA PUERTA HUMANA EXIGE UN ACTOR, y uno de verdad: es la evidencia
        #  de que detras de la escritura hay una persona y no el sistema
        #  actuando solo.
        return {"guardada": False, "codigo": "sin_actor",
                "detalle": "no se pudo determinar quien tomo la ubicacion"}

    #  LOS IDENTIFICADORES SALEN DE LA FICHA CONGELADA AL DESPACHAR, igual que
    #  en `telemetria`: volver a resolverlos ahora podria dar otro equipo --un
    #  cliente puede tener mas de uno-- y la ubicacion terminaria escrita en
    #  el equipo equivocado sin que nadie se entere.
    identificadores = {}
    if serial:
        identificadores["sn_onu"] = serial
    if servicio:
        identificadores["id_servicio"] = servicio
    if not identificadores:
        return {"guardada": False, "codigo": "sin_identificador",
                "detalle": "la orden no trae con que identificar al cliente "
                           "en el sistema del ISP"}

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    cuerpo = {"latitud": latitud, "longitud": longitud, "actor": actor,
              "identificadores": identificadores}
    try:
        r = requests.post(
            f"{base}/interno/orden/{orden.id}/guardar-ubicacion",
            params={"tenant": tenant}, json=cuerpo,
            headers=cabeceras, timeout=45)
        datos = r.json() if r.content else {}
        if not isinstance(datos, dict):
            datos = {}
    except Exception as e:                                      # noqa: BLE001
        #  POR TIPO Y SIN `str(e)`: el mensaje de un cliente HTTP puede traer
        #  la URL, y la URL puede traer la clave.
        logger.warning("ubicacion_al_isp: no se pudo guardar (%s)",
                       type(e).__name__)
        return {"guardada": False, "codigo": "sin_respuesta",
                "detalle": type(e).__name__}

    estado = str(datos.get("estado") or "")
    #  207 ES UN EXITO A MEDIAS Y SE DICE ASI. Darlo por bueno dejaria al
    #  tecnico creyendo que quedo en los dos sistemas; darlo por fallido lo
    #  haria repetir algo que ya salio en uno. El cuerpo trae cual falta, y
    #  volver a llamar reintenta solo ese.
    if r.status_code == 200 and estado == "guardada":
        return {"guardada": True, "codigo": "guardada", "detalle": "",
                "destinos": datos.get("destinos") or []}
    if r.status_code == 207 or estado == "parcial":
        return {"guardada": True, "parcial": True, "codigo": "parcial",
                "detalle": str(datos.get("motivo") or ""),
                "destinos": datos.get("destinos") or []}
    return {"guardada": False,
            "codigo": estado or f"http_{r.status_code}",
            "detalle": str(datos.get("motivo") or ""),
            "destinos": datos.get("destinos") or []}
