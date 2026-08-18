# -*- coding: utf-8 -*-
"""
================================================================================
 DETECCION DE INCIDENTES DE RED  --  correlaciona SmartOLT, no lo inventa
================================================================================

Por que existe
--------------
Antes de esto, cada conversacion de un cliente sin servicio era una isla: el
diagnostico (consultar_estado_ont, consultar_senal_ont) mira SOLO su ONU. Si
20 clientes del mismo splitter estan caidos a la vez, el asistente los trata
como 20 problemas sueltos -- nadie ve que es UN incidente hasta que un humano
junta las piezas a mano.

SmartOLT ya agrupa esto (get_outage_pons, verificado en vivo el 18/08/2026
contra una caida real -- ver .claude/skills/smartolt-api/SKILL.md). Lo que
faltaba era conectar "la ONU de ESTE cliente" con "el grupo que le
corresponde", que exige dos llamadas encadenadas:

  1. get_onu_details(sn_onu)       -> en que OLT/board/port vive esta ONU
  2. get_outage_pons(olt_id)       -> incidentes activos de esa OLT
  3. filtrar en Python el grupo cuyo board+port coincide con el de la ONU

Ninguna API de SmartOLT hace este cruce sola -- por eso es codigo, no una
herramienta 'http' de un solo llamado.

El modelo compone, el codigo calcula (PRD SS12.5): el veredicto
('es_incidente_de_red', cuantos afectados, desde cuando) sale calculado de
aca. El modelo nunca recibe la lista cruda de PONs para comparar board/port
a mano -- esa comparacion en un LLM es exactamente el tipo de aritmetica
donde se equivoca con el mismo tono seguro con el que acierta.

Latencia de agrupacion: 2 a 5 minutos segun el proveedor (dato de
SmartOLT, no medido por este proyecto -- ver la skill). Una respuesta
'es_incidente_de_red: false' en los primeros minutos de un reporte no es
"confirmado que no es de red", es "todavia no hay nada agrupado". Quien
redacta la respuesta al colaborador deberia saber esto -- ver la
descripcion de la herramienta en el YAML del tenant.
================================================================================
"""

from __future__ import annotations

import requests

from nucleo.herramientas import http as ejecutor_http

TIMEOUT_SEGUNDOS = 15


class ErrorIncidente(Exception):
    """Fallo al resolver la ubicacion de la ONU o al consultar incidentes."""


def detectar(herramienta, argumentos: dict, tenant: str | None = None,
             variables_tenant: dict | None = None) -> dict:
    """
    'argumentos' ya trae 'sn_onu' inyectado desde la sesion (ver
    Herramienta.inyectar_sesion en schema.py) -- el modelo no lo elige.

    Devuelve SIEMPRE 'es_incidente_de_red' (bool). Si es true, suma
    'clientes_afectados', 'porcentaje_afectado', 'desde' y 'zona' -- los
    mismos campos que ya vio el metodo del valor imposible contra la caida
    real del 18/08/2026, listos para que campos_permitidos los filtre por
    rol igual que cualquier otra herramienta.
    """
    sn_onu = argumentos.get("sn_onu")
    if not sn_onu:
        return {"es_incidente_de_red": False,
               "motivo": "no hay una ONU identificada para este cliente"}

    base_url = ejecutor_http.base_url_de(herramienta, variables_tenant).rstrip("/")
    headers = ejecutor_http.headers_de(herramienta, tenant)

    def _detalle_de(serial: str):
        r = requests.get(f"{base_url}/api/onu/get_onu_details/{serial}",
                         headers=headers, timeout=TIMEOUT_SEGUNDOS)
        return r

    r = _detalle_de(sn_onu)
    if not r.ok:
        # Mismo reintento que ejecutor_http.ejecutar(): 68 de 4.966 ONUs de
        # Rapilink solo responden con el serial en su forma hexadecimal
        # (verificado en vivo, agosto 2026) -- sin esto, esos clientes
        # activos se quedan sin correlacion de incidente con un 400 que no
        # explica nada. Un unico reintento, solo si la transformacion
        # produce un valor distinto.
        alternativo = ejecutor_http._gpon_hex(sn_onu)
        if alternativo and alternativo != sn_onu:
            r = _detalle_de(alternativo)
    r.raise_for_status()
    # get_onu_details envuelve todo bajo 'onu_details' -- verificado en vivo
    # (18/08/2026), no es un objeto plano como get_onu_status/get_onu_signal.
    detalle = r.json().get("onu_details") or {}
    olt_id = detalle.get("olt_id")
    board = detalle.get("board")
    port = detalle.get("port")
    if not olt_id or board is None or port is None:
        # No es un error del ejecutor: una ONU que SmartOLT no ubica en
        # ninguna OLT (serial mal cargado, equipo nunca aprovisionado) no
        # tiene incidente que buscarle. Fail-closed hacia "no se sabe", no
        # hacia una excepcion que tumbe el turno.
        return {"es_incidente_de_red": False,
               "motivo": "no se pudo resolver la ubicacion de la ONU en la OLT"}

    r2 = requests.get(f"{base_url}/api/system/get_outage_pons/{olt_id}",
                      headers=headers, timeout=TIMEOUT_SEGUNDOS)
    r2.raise_for_status()
    datos = r2.json().get("response", {})

    for seccion in datos.get("sections", []):
        for grupo in seccion.get("groups", []):
            for pon in grupo.get("pons", []):
                # Comparacion como texto: SmartOLT devuelve board/port como
                # string en get_outage_pons y como int en get_onu_details
                # (verificado en vivo) -- normalizar de los dos lados evita
                # un falso negativo por tipo en vez de por dato.
                if str(pon.get("board")) == str(board) and str(pon.get("port")) == str(port):
                    return {
                        "es_incidente_de_red": True,
                        "tipo_alerta": pon.get("alert_kind"),
                        "clientes_afectados": pon.get("affected_onus"),
                        "porcentaje_afectado": pon.get("affected_percent"),
                        "desde": pon.get("partial_started_at") or grupo.get("since"),
                        "zona": pon.get("zone_name"),
                        "caja": pon.get("odb_name"),
                    }
    return {"es_incidente_de_red": False}
