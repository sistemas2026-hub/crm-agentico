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

from datetime import datetime, timedelta

import requests

from nucleo.herramientas import http as ejecutor_http

TIMEOUT_SEGUNDOS = 15


class ErrorIncidente(Exception):
    """Fallo al resolver la ubicacion de la ONU o al consultar incidentes."""


# Cuanto pueden separarse dos caidas para considerarlas la MISMA falla.
# Minutos, no dias: cuando se corta algo fisico los equipos se van casi
# juntos -- medido el 21/08/2026 sobre una caida real, SIETE ONUs del mismo
# puerto cayeron en el MISMO instante ('2026-08-21 07:16:44.419668', hasta
# la fraccion de segundo).
#
# La ventana agrupa por CERCANIA ENTRE SI, no por "hace poco". Un corte del
# sabado sigue siendo el mismo grupo el lunes: en Rapilink no se despacha
# tecnico en fin de semana ni festivo salvo agendado, asi que una falla
# puede seguir abierta dias sin que eso la vuelva vieja. Por eso no hay
# ningun corte por antiguedad -- lo que separa a un cliente caido hoy de uno
# abandonado hace meses es que el abandonado no coincide con NADIE.
VENTANA_MISMA_FALLA_MINUTOS = 20


def _a_fecha(valor):
    """El timestamp de SmartOLT a datetime, o None si no se puede leer.

    Vienen en dos formas segun el endpoint ('2026-08-21 07:16:44.419668' y
    '2026-08-21 12:16:44'), asi que se prueban las dos en vez de asumir una.
    """
    texto = str(valor or "").strip()
    if not texto:
        return None
    for formato in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def _caidas_simultaneas(base_url, headers, olt_id, board, port, sn_onu):
    """
    Cuantas ONUs del MISMO puerto se cayeron junto con esta, y desde cuando.

    Por que no alcanza con contar las caidas del puerto: un puerto acumula
    equipos que llevan meses fuera -- clientes que se fueron y nadie dio de
    baja. Medido el 21/08/2026 en una caida real: 17 ONUs caidas en el
    puerto, de las cuales 7 se fueron en el mismo instante (la falla) y 10
    llevaban entre mes y medio y OCHO MESES (abandono).

    Contarlas todas daria 17 y ese puerto marcaria "falla masiva" todos los
    dias, aunque no pase nada. Y un umbral por cantidad tampoco sirve: los
    10 muertos ya lo superan solos, mientras que una falla real de 5 casas
    quedaria por debajo.

    Devuelve (cuantos, desde) o (0, None) si no se pudo saber. Nunca lanza:
    esto ENRIQUECE el veredicto de SmartOLT, no lo reemplaza.
    """
    try:
        r = requests.get(f"{base_url}/api/onu/get_all_onus_details",
                         headers=headers, timeout=TIMEOUT_SEGUNDOS * 4)
        r.raise_for_status()
        onus = r.json().get("onus") or []
    except Exception as e:
        print(f"[incidentes] no se pudo correlacionar por tiempo: {type(e).__name__}: {e}")
        return 0, None

    del_puerto = [o for o in onus
                  if str(o.get("olt_id")) == str(olt_id)
                  and str(o.get("board")) == str(board)
                  and str(o.get("port")) == str(port)]
    caidas = [(o, _a_fecha(o.get("last_status_change"))) for o in del_puerto
              if (o.get("status") or "") != "Online"]
    caidas = [(o, f) for o, f in caidas if f is not None]
    if not caidas:
        return 0, None

    # La referencia es CUANDO SE CAYO ESTE CLIENTE. Si su propia ONU no
    # figura caida (el caso raro de que reporte sin estar caido), se toma la
    # caida mas reciente del puerto, que es la unica candidata a ser la
    # falla en curso.
    propia = next((f for o, f in caidas if str(o.get("sn") or "").upper() == str(sn_onu).upper()), None)
    referencia = propia or max(f for _, f in caidas)

    ventana = timedelta(minutes=VENTANA_MISMA_FALLA_MINUTOS)
    grupo = [f for _, f in caidas if abs(f - referencia) <= ventana]
    return len(grupo), min(grupo).strftime("%Y-%m-%d %H:%M:%S") if grupo else None


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
                    # SmartOLT agrupa con criterio propio y no siempre coincide
                    # con la evidencia cruda: en la caida del 21/08/2026 declaro
                    # 8 suscriptores desde las 12:16, cuando los timestamps de
                    # las ONUs mostraban 7 caidas simultaneas a las 07:16 --
                    # cinco horas antes y un cliente de diferencia. Por eso se
                    # recuenta contra los tiempos y se informan los dos.
                    juntos, desde_real = _caidas_simultaneas(
                        base_url, headers, olt_id, board, port, sn_onu)
                    salida = {
                        "es_incidente_de_red": True,
                        "tipo_alerta": pon.get("alert_kind"),
                        "clientes_afectados": pon.get("affected_onus"),
                        "porcentaje_afectado": pon.get("affected_percent"),
                        "desde": pon.get("partial_started_at") or grupo.get("since"),
                        "zona": pon.get("zone_name"),
                        "caja": pon.get("odb_name"),
                    }
                    if juntos:
                        salida["clientes_caidos_a_la_vez"] = juntos
                        salida["desde_por_tiempos"] = desde_real
                    return salida
    return {"es_incidente_de_red": False}
