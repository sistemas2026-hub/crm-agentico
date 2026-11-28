# -*- coding: utf-8 -*-
"""
================================================================================
 QUE IP SE LE PUEDEN OFRECER AL TECNICO, EN UNA ZONA
================================================================================
Le pregunta al motor, que es el unico que habla con el proveedor. Este modulo
no sabe la clave del ISP ni su URL: pide y traduce.

POR QUE NO SE CALCULA ACA
-------------------------
La ocupacion sale de recorrer el listado de clientes del proveedor --7.679
filas, decenas de llamadas-- y esa credencial vive en el motor
(`auth_ref`/`base_url_ref`). Duplicarla de este lado seria duplicar el secreto
y la decision de que endpoint es, que es justo lo que `nucleo/` existe para
concentrar.

FALLA CERRADO, Y NO LO DECIDE ESTE MODULO
-----------------------------------------
El motor devuelve lista vacia con un motivo cuando no puede saber: sin
sincronizar, lectura incompleta, zona sin pool. Aca no se rellena nada ni se
"ayuda" con un valor por defecto. Una direccion ofrecida a partir de un dato
que falta es como dos clientes terminan con la misma IP.

Si el motor no contesta, tambien cero. No poder preguntar no es permiso.

LO QUE NINGUNA CAPA PUEDE PROMETER
----------------------------------
Que una direccion libre sea USABLE. Los equipos de red --antenas, switches,
cajas-- no son clientes del proveedor, asi que no estan en su listado y la
resta no los ve. El motor manda esa advertencia en la respuesta; este modulo la
pasa tal cual y la pantalla la tiene que mostrar.
================================================================================
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

#: Igual que el resto de las llamadas al motor desde el backend.
ESPERA_MAXIMA = 10

#: Cuantas se le ofrecen al tecnico. No son 253: una lista de 253 opciones no
#: se elige, se abandona. El usuario dijo que «puede ser cualquiera», asi que
#: un puñado alcanza.
CUANTAS_POR_DEFECTO = 20
CUANTAS_MAXIMO = 50


def _motor():
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, cabeceras


def libre_en_el_proveedor(org, ip: str):
    """Si ningun cliente del proveedor tiene esa IP AHORA: True o False, y
    None si no se pudo saber. Ver `/interno/red/ip-libre` en el motor."""
    from operaciones.areas_del_tenant import tenant_de

    tenant = tenant_de(org)
    if not tenant:
        return None
    base, cabeceras = _motor()
    try:
        r = requests.get(f"{base}/interno/red/ip-libre", headers=cabeceras,
                         params={"tenant": tenant, "ip": ip}, timeout=ESPERA_MAXIMA)
        if not r.ok:
            logger.info("IP en vivo: el motor respondio %s", r.status_code)
            return None
        libre = (r.json() or {}).get("libre")
    except Exception as e:                                   # noqa: BLE001
        logger.info("IP en vivo: no se pudo preguntar al motor (%s)", type(e).__name__)
        return None
    return libre if isinstance(libre, bool) else None


def _vacio(motivo: str) -> dict:
    return {"libres": [], "motivo": motivo, "advertencia": "",
            "actualizado_en": None, "zona_nombre": "", "prefijos": []}


def para_la_zona(org, zona_id, cuantas: int = CUANTAS_POR_DEFECTO) -> dict:
    """Las direcciones que se le pueden ofrecer, y de cuando es el dato.

        {"libres": ["172.16.9.2", ...],
         "motivo": "",            # por que NO hay, cuando la lista esta vacia
         "advertencia": "...",    # que esto no prueba que sean usables
         "actualizado_en": "...", # ISO, para que la pantalla diga que tan
                                  # vieja es la lectura
         "zona_nombre": "...", "prefijos": [...]}

    Nunca levanta: si algo falla devuelve la lista vacia con el motivo. Quien
    llama esta en la pantalla de un tecnico parado en una casa, y una
    excepcion ahi no le sirve de nada.
    """
    from operaciones.areas_del_tenant import tenant_de

    try:
        zona = int(zona_id)
    except (TypeError, ValueError):
        return _vacio("la zona tiene que ser el id numerico del catalogo")

    tenant = tenant_de(org)
    if not tenant:
        return _vacio("no se sabe de que empresa es esta orden")

    try:
        cuantas = max(1, min(int(cuantas), CUANTAS_MAXIMO))
    except (TypeError, ValueError):
        cuantas = CUANTAS_POR_DEFECTO

    base, cabeceras = _motor()
    try:
        r = requests.get(f"{base}/interno/red/ips-libres", headers=cabeceras,
                         params={"tenant": tenant, "zona": zona,
                                 "cuantas": cuantas},
                         timeout=ESPERA_MAXIMA)
    except Exception as e:                                   # noqa: BLE001
        #  Por TIPO y no `str(e)`: el texto de una excepcion de red puede
        #  traer la URL con sus parametros.
        logger.info("IP libres: no se pudo preguntar al motor (%s)",
                    type(e).__name__)
        return _vacio("no se pudo consultar las direcciones disponibles")

    if not r.ok:
        logger.info("IP libres: el motor respondio %s", r.status_code)
        return _vacio("no se pudo consultar las direcciones disponibles")

    try:
        cuerpo = r.json() or {}
    except ValueError:
        return _vacio("la respuesta del motor no se pudo leer")

    libres = [str(x) for x in (cuerpo.get("libres") or []) if str(x).strip()]
    return {
        "libres": libres[:cuantas],
        "motivo": str(cuerpo.get("motivo") or ""),
        "advertencia": str(cuerpo.get("advertencia") or ""),
        "actualizado_en": cuerpo.get("actualizado_en"),
        "zona_nombre": str(cuerpo.get("zona_nombre") or ""),
        "prefijos": [str(p) for p in (cuerpo.get("prefijos") or [])],
    }
