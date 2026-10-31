# -*- coding: utf-8 -*-
"""
================================================================================
 FLOTA  --  las caidas por PON de TODAS las OLTs, descubriendo las OLTs
================================================================================

QUE RESUELVE, Y POR QUE NO LO RESOLVIA NINGUNA HERRAMIENTA
----------------------------------------------------------
El Supervisor NOC necesita ver la red ANTES de que alguien abra un ticket. Para
eso hace falta una lectura de FLOTA: que puertos PON estan anormales ahora
mismo, sin partir de un cliente.

Lo que ya existia es otra cosa, y conviene no confundirlas:

  * 'incidentes.detectar' (bandera 'detecta_incidente') PARTE DE UN CLIENTE:
    exige 'sn_onu', resuelve su OLT/board/port con 'get_onu_details' y despues
    pregunta por los incidentes de ESA OLT. Contesta "¿la falla de este cliente
    es aislada o compartida?". No puede contestar "¿como esta la red?", porque
    sin un cliente no tiene por donde empezar.

  * 'cli/reporte_incidentes_red.py' SI hace la cadena de flota, pero es un
    script de linea de comandos: no esta en el catalogo, asi que el motor no lo
    puede ejecutar y el backend no lo puede pedir.

Esto es la tercera pieza, y la unica que faltaba: la cadena de flota, dentro del
catalogo, invocable por el servicio.

    get_olts                       -> que OLTs hay (SE DESCUBREN)
      por cada una:
        get_outage_pons(olt_id)    -> que PONs estan anormales en esa OLT
      ->  un solo sobre, con las secciones de todas

LAS OLTs SE DESCUBREN, NO SE CONFIGURAN
---------------------------------------
No hay 'SMARTOLT_OLT_ID_1' ni '_2'. Se intento una vez y se revirtio: la API
tiene 'get_olts' y una lista fija en la configuracion es un dato que se queda
viejo sin que nadie lo note -- el dia que la empresa agrega una OLT, el
Supervisor dejaria de verla y no diria nada.

POR QUE UN FALLO PARCIAL INVALIDA LA LECTURA COMPLETA
-----------------------------------------------------
Si 'get_olts' responde tres OLTs y la segunda no contesta, esta funcion LEVANTA
en vez de devolver las dos que si. Un resumen al que le falta una OLT se leeria,
aguas abajo, como "en esa OLT no hay caidas" -- y esa es exactamente la
afirmacion que no se puede hacer. Es mejor no saber de ninguna que creer saber
de todas. El adaptador del backend ya trata ese error como ERROR de fuente, no
como ausencia de caidas.

LA FORMA DE LA RESPUESTA, Y POR QUE ESA
---------------------------------------
Se devuelve el MISMO sobre que 'get_outage_pons' ya devuelve
--{'response': {'sections': [...]}}-- con las secciones de todas las OLTs
concatenadas. No se inventa un formato nuevo: 'operaciones/fuentes_adaptadores.
py::_resumir_pons' ya sabe leer ese sobre y resumirlo por PON, y cambiarlo
obligaria a tocar las dos puntas para no ganar nada.

A cada seccion se le agrega 'olt_id' y 'olt_nombre' cuando la API los da. Las
claves del resumen de aguas abajo son 'olt/board/port', asi que sin el olt dos
OLTs distintas con el mismo board/port se pisarian.

LO QUE NO HACE
--------------
No escribe. No reinicia nada. No toca una ONU. No nombra a ningun cliente: este
endpoint AGRUPA por puerto, y lo mas identificable que devuelve es 'odb_name',
que es el nombre de la caja en la calle, no de una persona.
================================================================================
"""

from __future__ import annotations

import requests

from nucleo.herramientas import http as ejecutor_http
from nucleo.observabilidad.registro import registrar

#  Mas largo que una consulta puntual a proposito: son 1 + N llamadas y corre en
#  un trabajo periodico, no en el turno de una conversacion.
TIMEOUT_SEGUNDOS = 30

#  Tope de OLTs por lectura. No es estetica: si una cuenta devolviera cientos,
#  esto haria cientos de llamadas a un tercero que pide explicitamente no hacer
#  polling masivo. Si se alcanza, se LEVANTA -- recortar en silencio dejaria una
#  lectura incompleta con aspecto de completa.
TOPE_OLTS = 25


class FlotaNoLegible(RuntimeError):
    """No se pudo leer la flota completa. NO significa que no haya caidas."""


def _pedir(url: str, headers: dict, que: str):
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT_SEGUNDOS)
    except Exception as e:                                       # noqa: BLE001
        #  Tipo y no texto: el texto de una excepcion de red trae la URL, y la
        #  URL lleva el subdominio de la empresa.
        raise FlotaNoLegible(
            f"{que}: no se pudo consultar ({type(e).__name__})") from None
    if r.status_code != 200:
        raise FlotaNoLegible(f"{que}: el proveedor respondio {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise FlotaNoLegible(f"{que}: la respuesta no es JSON") from None


def _olts_de(crudo) -> list[dict]:
    """
    Las OLTs del sobre de 'get_olts', tolerante con la forma.

    Verificado el 14/08/2026: la respuesta envuelve bajo 'olts'. Se aceptan
    tambien 'response' y una lista suelta, porque cada endpoint de este
    proveedor trae su propio sobre y no hay un patron comun entre ellos.
    """
    if isinstance(crudo, list):
        return [o for o in crudo if isinstance(o, dict)]
    if not isinstance(crudo, dict):
        return []
    for clave in ("olts", "response", "data"):
        valor = crudo.get(clave)
        if isinstance(valor, list):
            return [o for o in valor if isinstance(o, dict)]
        if isinstance(valor, dict):
            for dentro in ("olts", "data"):
                if isinstance(valor.get(dentro), list):
                    return [o for o in valor[dentro] if isinstance(o, dict)]
    return []


def _id_de(olt: dict):
    for clave in ("id", "olt_id", "ID"):
        valor = olt.get(clave)
        if valor not in (None, ""):
            return valor
    return None


def _secciones_de(crudo) -> list[dict]:
    """Las secciones del sobre de 'get_outage_pons'. Sin inventar ninguna."""
    if not isinstance(crudo, dict):
        return []
    respuesta = crudo.get("response")
    if isinstance(respuesta, dict):
        secciones = respuesta.get("sections")
        if isinstance(secciones, list):
            return [s for s in secciones if isinstance(s, dict)]
    secciones = crudo.get("sections")
    if isinstance(secciones, list):
        return [s for s in secciones if isinstance(s, dict)]
    return []


def caidas_por_pon(herramienta, argumentos: dict, tenant: str | None = None,
                   variables_tenant: dict | None = None) -> dict:
    """
    Las caidas por PON de toda la flota. Solo lectura, sin argumentos.

    'argumentos' se acepta por el contrato de las herramientas internas y se
    IGNORA a proposito: esta lectura no se parametriza. Un filtro por OLT la
    convertiria en una lectura parcial con aspecto de completa, que es justo lo
    que 'get_outage_pons' por si solo ya era.

    Devuelve {'response': {'sections': [...]}, 'olts_consultadas': N}. Levanta
    'FlotaNoLegible' si no se puede leer la flota ENTERA.
    """
    base_url = ejecutor_http.base_url_de(herramienta, variables_tenant).rstrip("/")
    headers = ejecutor_http.headers_de(herramienta, tenant)

    #  1. Las OLTs se descubren.
    crudo_olts = _pedir(f"{base_url}/api/system/get_olts", headers, "get_olts")
    olts = _olts_de(crudo_olts)
    if not olts:
        #  CERO OLTs no es "la red esta bien": es que no se pudo saber cuales
        #  hay, y sin eso no hay nada que consultar.
        raise FlotaNoLegible(
            "get_olts no devolvio ninguna OLT: sin saber que OLTs hay no se "
            "puede afirmar nada sobre el estado de la red")
    if len(olts) > TOPE_OLTS:
        raise FlotaNoLegible(
            f"get_olts devolvio {len(olts)} OLTs y el tope es {TOPE_OLTS}: "
            f"recortar dejaria una lectura incompleta con aspecto de completa")

    #  2. Las caidas de cada una. Si una falla, falla todo.
    secciones: list[dict] = []
    consultadas = 0
    for olt in olts:
        olt_id = _id_de(olt)
        if olt_id is None:
            raise FlotaNoLegible(
                "una OLT de 'get_olts' vino sin identificador: no se consulta "
                "con un id inventado")
        crudo = _pedir(f"{base_url}/api/system/get_outage_pons/{olt_id}",
                       headers, f"get_outage_pons/{olt_id}")
        for seccion in _secciones_de(crudo):
            #  EL OLT VA DENTRO DE CADA PON, y esto no es un detalle de
            #  estilo: 'operaciones/fuentes_adaptadores.py::_resumir_pons'
            #  arma la clave del resumen con
            #  pon['olt_id'] / pon['board'] / pon['port'].
            #
            #  La primera version de este archivo lo ponia solo en la
            #  SECCION, y la clave salia '?/3/3-1-4' -- con el olt perdido.
            #  Dos OLTs con el mismo board/port se habrian pisado y el
            #  conteo de afectados habria quedado mal sin que nada fallara.
            #  Lo cazo la prueba de extremo a extremo, no la unitaria.
            seccion = dict(seccion)
            seccion.setdefault("olt_id", olt_id)
            nombre = olt.get("name") or olt.get("olt_name")
            if nombre:
                seccion.setdefault("olt_nombre", nombre)
            grupos = []
            for grupo in (seccion.get("groups") or []):
                if not isinstance(grupo, dict):
                    continue
                grupo = dict(grupo)
                pons = []
                for pon in (grupo.get("pons") or []):
                    if not isinstance(pon, dict):
                        continue
                    pon = dict(pon)
                    pon.setdefault("olt_id", olt_id)
                    pons.append(pon)
                grupo["pons"] = pons
                grupos.append(grupo)
            seccion["groups"] = grupos
            secciones.append(seccion)
        consultadas += 1

    registrar("flota", "caidas por PON leidas de la flota",
              olts=consultadas, secciones=len(secciones))
    return {"response": {"sections": secciones},
            "olts_consultadas": consultadas}
