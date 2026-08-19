# -*- coding: utf-8 -*-
"""
================================================================================
 REPORTE DE INCIDENTES DE RED  --  a quien avisar, y a quien no se puede
================================================================================

Primera pieza de "avisar antes de que reclame" (punto 3 del roadmap
discutido el 18/08/2026). SOLO LECTURA a proposito: no manda nada. El
envio automatico esta bloqueado en origen -- no existe todavia una
plantilla de WhatsApp aprobada por Meta para avisos de interrupcion, y sin
eso no se puede iniciar una conversacion proactiva por ese canal (decision
del usuario, misma conversacion: aprobacion humana antes de enviar, ademas
del bloqueo de la plantilla). Mientras tanto, esto le da al staff la lista
lista para avisar a mano.

Que hace
--------
Para cada OLT de la empresa:
  1. get_outage_pons -- que incidentes estan activos ahora mismo
     (verificado en vivo el 18/08/2026 contra una caida real, ver skill
     smartolt-api)
  2. Por cada grupo activo: get_all_onus_details(olt_id), filtrado en
     Python por board+port (el filtro 'pon_port' de la API lo ignora en
     silencio -- ver skill smartolt-api, mismo patron que el filtro 'zona'
     de WispHub)
  3. Por cada ONU afectada: buscar el cliente real en WispHub por sn_onu
     (filtro verificado con el metodo del valor imposible, 18/08/2026)

Por que separa "identificados" de "sin identificar"
------------------------------------------------------
No todo sn_onu de SmartOLT tiene un cliente cargado en WispHub -- la skill
wisphub-api mide la cobertura entre 68% y 93% segun el backfill mas
reciente, nunca 100%. Descartar en silencio los que no matchean
subestimaria el incidente: si 8 ONUs caen y solo 6 tienen cliente
identificable, el reporte tiene que decir "6 identificados + 2 sin
identificar", nunca "6 afectados" a secas -- eso ultimo le miente al
staff sobre cuanta gente hay realmente sin servicio.

Uso
---
    py -3.13 cli/reporte_incidentes_red.py
    py -3.13 cli/reporte_incidentes_red.py --olt 3
================================================================================
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

import requests

SMARTOLT_BASE = os.environ.get("SMARTOLT_BASE_URL", "").rstrip("/")
SMARTOLT_HEADERS = {"X-Token": os.environ.get("SMARTOLT_API_KEY", "")}
WISPHUB_BASE = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
WISPHUB_HEADERS = {"Authorization": f"Api-Key {os.environ.get('WISPHUB_API_KEY', '')}"}
TIMEOUT = 30


def _olts() -> list[dict]:
    r = requests.get(f"{SMARTOLT_BASE}/api/system/get_olts",
                     headers=SMARTOLT_HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("response", [])


def _incidentes_activos(olt_id) -> list[dict]:
    """PONs con alguna alerta activa (partial_los, los, power, offline),
    cada uno con su board/port -- 'pons' adentro de cada grupo, ver la
    forma real documentada en la skill smartolt-api."""
    r = requests.get(f"{SMARTOLT_BASE}/api/system/get_outage_pons/{olt_id}",
                     headers=SMARTOLT_HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    datos = r.json().get("response", {})
    salida = []
    for seccion in datos.get("sections", []):
        for grupo in seccion.get("groups", []):
            for pon in grupo.get("pons", []):
                salida.append(pon)
    return salida


def _onus_del_puerto(olt_id, board, port) -> list[str]:
    """Seriales de las ONUs de ese board+port -- 'pon_port' se ignora en
    silencio en la API (verificado agosto 2026), asi que se trae la OLT
    completa y se filtra aca."""
    r = requests.get(f"{SMARTOLT_BASE}/api/onu/get_all_onus_details",
                     headers=SMARTOLT_HEADERS, params={"olt_id": olt_id},
                     timeout=TIMEOUT)
    r.raise_for_status()
    cuerpo = r.json()
    onus = cuerpo.get("onus") if isinstance(cuerpo, dict) else cuerpo
    return [o.get("sn") for o in (onus or [])
           if str(o.get("board")) == str(board) and str(o.get("port")) == str(port)]


def _cliente_wisphub(sn_onu: str) -> dict | None:
    """None si no hay ningun cliente con ese sn_onu en WispHub -- caso
    real y esperado, no un error (ver el docstring del modulo)."""
    r = requests.get(f"{WISPHUB_BASE}/api/clientes/", headers=WISPHUB_HEADERS,
                     params={"sn_onu": sn_onu, "limit": 1}, timeout=TIMEOUT)
    r.raise_for_status()
    resultados = r.json().get("results") or []
    return resultados[0] if resultados else None


def resolver_afectados(olt_id, board, port) -> dict:
    seriales = _onus_del_puerto(olt_id, board, port)
    identificados = []
    sin_identificar = 0
    for sn in seriales:
        cliente = _cliente_wisphub(sn)
        if cliente:
            identificados.append({
                "id_servicio": cliente.get("id_servicio"),
                "nombre": cliente.get("nombre"),
                "telefono": cliente.get("telefono"),
                "sn_onu": sn,
            })
        else:
            sin_identificar += 1
    return {"identificados": identificados, "sin_identificar": sin_identificar}


def main(solo_olt: int | None) -> None:
    if not SMARTOLT_BASE or not SMARTOLT_HEADERS.get("X-Token"):
        raise SystemExit("Faltan SMARTOLT_BASE_URL/SMARTOLT_API_KEY en el entorno.")

    olts = [o for o in _olts() if solo_olt is None or int(o.get("id")) == solo_olt]
    if not olts:
        print("Sin OLTs para revisar." if solo_olt is None else
             f"OLT {solo_olt} no existe.")
        return

    total_incidentes = 0
    for olt in olts:
        olt_id = olt.get("id")
        incidentes = _incidentes_activos(olt_id)
        if not incidentes:
            continue
        for pon in incidentes:
            total_incidentes += 1
            print(f"\n{'=' * 72}")
            print(f"  {pon.get('alert_kind')}  --  OLT {olt.get('name')}, "
                 f"board {pon.get('board')} / puerto {pon.get('port')}")
            print(f"  zona: {pon.get('zone_name')}  |  caja: {pon.get('odb_name')}")
            print(f"  desde: {pon.get('partial_started_at') or pon.get('latest_status_change')}")
            print(f"  SmartOLT reporta {pon.get('affected_onus')} ONUs afectadas "
                 f"({pon.get('affected_percent')}%)")
            print("=" * 72)

            resuelto = resolver_afectados(olt_id, pon.get("board"), pon.get("port"))
            for c in resuelto["identificados"]:
                print(f"  {c['id_servicio']:>6}  {c['nombre']:<35} {c['telefono']}")
            if resuelto["sin_identificar"]:
                print(f"\n  ⚠ {resuelto['sin_identificar']} ONU(s) mas sin cliente "
                     f"identificable en WispHub (sn_onu no cargado) -- estan "
                     f"afectadas igual, no se pueden avisar por este medio.")

    if total_incidentes == 0:
        print("Sin incidentes activos en ninguna OLT.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--olt", type=int, default=None,
                        help="Solo esta OLT (por id). Sin esto, revisa todas.")
    args = parser.parse_args()
    main(args.olt)
