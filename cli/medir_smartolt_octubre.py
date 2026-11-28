# -*- coding: utf-8 -*-
"""
================================================================================
 MEDIR LOS CAMBIOS DE SMARTOLT (octubre 2026)  --  SOLO LECTURA, solo GET
================================================================================
La documentacion de SmartOLT se actualizo en octubre 2026. Lo que dice es una
hipotesis (CLAUDE.md §4); esto la mide contra la instancia real antes de
construir encima. Cada medicion es UNA o dos llamadas, y el total cabe holgado
en el cupo de la hora (unas 15 llamadas).

QUE NO IMPRIME, A PROPOSITO
---------------------------
Ni la clave, ni la URL del stream de eventos (lleva un token: es una
credencial), ni nombres, direcciones, contactos, MACs o seriales completos.
Solo codigos HTTP, cantidades, nombres de campos y si dos valores coinciden.

    py -3.13 cli/medir_smartolt_octubre.py

Necesita SMARTOLT_BASE_URL, SMARTOLT_API_KEY, WISPHUB_API_KEY (y opcional
WISPHUB_BASE_URL) en el entorno o en el .env de la raiz, como
cli/proponer_sn_onu.py.
================================================================================
"""

from __future__ import annotations

import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv(override=False)

SMARTOLT = os.environ.get("SMARTOLT_BASE_URL", "").rstrip("/")
H_OLT = {"X-Token": os.environ.get("SMARTOLT_API_KEY", "")}
WISPHUB = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
H_WH = {"Authorization": f"Api-Key {os.environ.get('WISPHUB_API_KEY', '')}"}
TIMEOUT = 60


def tapar(valor) -> str:
    """Los ultimos 3 caracteres, para poder hablar de un valor sin mostrarlo."""
    texto = str(valor or "")
    return f"…{texto[-3:]}" if len(texto) > 3 else "…"


def cupo(r) -> str:
    h = r.headers
    return (f"cupo {h.get('X-RateLimit-Remaining', '?')}/{h.get('X-RateLimit-Limit', '?')}"
            f" reinicia en {h.get('X-RateLimit-Reset', '?')} s")


def pedir(ruta, params=None):
    t = time.monotonic()
    r = requests.get(f"{SMARTOLT}{ruta}", headers=H_OLT, params=params, timeout=TIMEOUT)
    return r, time.monotonic() - t


def cuerpo(r):
    try:
        return r.json()
    except ValueError:
        return None


def error_de(c) -> str:
    if not isinstance(c, dict):
        return ""
    return f"error_code={c.get('error_code')!r} response_code={c.get('response_code')!r}"


def titulo(t):
    print(f"\n== {t}")


def main() -> int:
    if not SMARTOLT or not H_OLT["X-Token"]:
        print("Falta SMARTOLT_BASE_URL / SMARTOLT_API_KEY en el entorno.")
        return 2

    # ── M1 · OLTs y cupo ──────────────────────────────────────────────────
    titulo("M1 · get_olts y cupo de la hora")
    r, s = pedir("/api/system/get_olts")
    c = cuerpo(r) or {}
    olts = [o.get("id") for o in (c.get("response") or []) if isinstance(o, dict)]
    print(f"HTTP {r.status_code} en {s:.1f} s · {len(olts)} OLT(s) · {cupo(r)}")

    # ── M2 · page_size 200 contra el maximo documentado de 100 ────────────
    titulo("M2 · get_all_onus_details paginado: page_size=200 contra 100")
    olt = olts[0] if olts else None
    for tam in (200, 100):
        r, s = pedir("/api/onu/get_all_onus_details",
                     {"olt_id": olt, "status": "los", "fields": "status,sn",
                      "page": 1, "page_size": tam})
        c = cuerpo(r) or {}
        filas = c.get("onus") if isinstance(c, dict) else None
        print(f"page_size={tam}: HTTP {r.status_code} · filas={len(filas) if isinstance(filas, list) else '—'}"
              f" · page_size devuelto={c.get('page_size') if isinstance(c, dict) else '—'}"
              f" · total_items={c.get('total_items') if isinstance(c, dict) else '—'} · {error_de(c)}")
    # Con una pagina de 100 y pocas en LOS no se ve un recorte: probar sin
    # filtro de estado, donde hay miles.
    r, s = pedir("/api/onu/get_all_onus_details",
                 {"olt_id": olt, "fields": "sn", "page": 1, "page_size": 200})
    c = cuerpo(r) or {}
    filas = c.get("onus") if isinstance(c, dict) else None
    print(f"sin filtro de estado, page_size=200: HTTP {r.status_code} · filas={len(filas) if isinstance(filas, list) else '—'}"
          f" · total_items={c.get('total_items') if isinstance(c, dict) else '—'} · {error_de(c)}")

    # ── M3 · forma de get_outage_pons por OLT ─────────────────────────────
    titulo("M3 · get_outage_pons: claves y secciones")
    for o in olts:
        r, s = pedir(f"/api/system/get_outage_pons/{o}")
        c = cuerpo(r) or {}
        resp = c.get("response") if isinstance(c, dict) else None
        if not isinstance(resp, dict):
            print(f"OLT {o}: HTTP {r.status_code} · sin 'response' · {error_de(c)}")
            continue
        secciones = [(x.get("key"), len(x.get("groups") or [])) for x in (resp.get("sections") or [])
                     if isinstance(x, dict)]
        tipos = sorted({p.get("alert_kind") for x in (resp.get("sections") or []) if isinstance(x, dict)
                        for g in (x.get("groups") or []) for p in (g.get("pons") or []) if isinstance(p, dict)})
        print(f"OLT {o}: HTTP {r.status_code} en {s:.1f} s · claves={sorted(resp)} · secciones={secciones}"
              f" · alert_kind vistos={tipos} · unreachable_olts={resp.get('unreachable_olts')!r}"
              f" · stale.pon_count={(resp.get('stale') or {}).get('pon_count') if isinstance(resp.get('stale'), dict) else resp.get('stale')!r}")

    # ── M4 · ¿la clave sirve para eventos? ────────────────────────────────
    titulo("M4 · get_event_stream (NO se abre el stream; la URL no se imprime)")
    r, s = pedir("/api/onu/get_event_stream", {"events": "pon.outage_started"})
    c = cuerpo(r) or {}
    tiene_url = isinstance(c, dict) and isinstance(c.get("response"), dict) and bool(c["response"].get("url"))
    print(f"HTTP {r.status_code} · devolvio url={tiene_url} · expires_in="
          f"{c['response'].get('expires_in') if tiene_url else '—'} · {error_de(c)}"
          f" · mensaje={(c.get('error') or '')[:90] if isinstance(c, dict) else ''}")

    # ── M5 · ONUs deshabilitadas por la empresa ───────────────────────────
    titulo("M5 · ONUs con administrative_status=disabled (conteo)")
    for o in olts:
        r, s = pedir("/api/onu/get_all_onus_details",
                     {"olt_id": o, "administrative_status": "disabled", "fields": "sn",
                      "page": 1, "page_size": 1})
        c = cuerpo(r) or {}
        print(f"OLT {o}: HTTP {r.status_code} · total_items={c.get('total_items') if isinstance(c, dict) else '—'}"
              f" · Deprecation={r.headers.get('Deprecation')!r} · {error_de(c)}")

    # ── M6 · energia de las OLT ───────────────────────────────────────────
    titulo("M6 · get_olts_uptime_and_env_temperature: power_state y voltage")
    r, s = pedir("/api/olt/get_olts_uptime_and_env_temperature")
    c = cuerpo(r) or {}
    filas = c.get("response") if isinstance(c, dict) else None
    if isinstance(filas, list):
        for f in filas:
            if isinstance(f, dict):
                print(f"OLT {f.get('olt_id')}: power_state={f.get('power_state')!r} voltage={f.get('voltage')!r}"
                      f" voltage_read_at={'si' if f.get('voltage_read_at') else 'no'}")
    print(f"HTTP {r.status_code} · {error_de(c)} · forma={type(filas).__name__}")

    # ── M7 · un cliente real con serial y MAC: search_by_mac ──────────────
    titulo("M7 · search_by_mac con la mac_cpe de WispHub de un cliente con serial")
    if not H_WH["Authorization"].split(" ", 1)[1]:
        print("Sin WISPHUB_API_KEY: se salta.")
        return 0
    rw = requests.get(f"{WISPHUB}/api/clientes/", headers=H_WH,
                      params={"estado": 1, "limit": 100, "offset": 0}, timeout=TIMEOUT)
    clientes = (cuerpo(rw) or {}).get("results") or []
    elegido = next((x for x in clientes if (x.get("sn_onu") or "").strip()
                    and (x.get("mac_cpe") or "").strip()), None)
    print(f"WispHub HTTP {rw.status_code} · {len(clientes)} clientes en la pagina · "
          f"con serial y MAC: {sum(1 for x in clientes if (x.get('sn_onu') or '').strip() and (x.get('mac_cpe') or '').strip())}")
    if not elegido:
        print("Ningun cliente de la pagina tiene serial y MAC: se salta.")
        return 0
    sn = elegido["sn_onu"].strip()
    mac = elegido["mac_cpe"].strip()
    print(f"cliente elegido: serial {tapar(sn)} · mac_cpe con {len(mac)} caracteres, "
          f"separadores={sorted(set(ch for ch in mac if not ch.isalnum()))}")

    r, s = pedir(f"/api/onu/get_onu_details/{sn}")
    det = (cuerpo(r) or {}).get("onu_details") or {}
    olt_cliente = det.get("olt_id")
    print(f"get_onu_details: HTTP {r.status_code} · olt_id={olt_cliente} · status={det.get('status')!r}"
          f" · trae administrative_status={'administrative_status' in det}"
          f" ({det.get('administrative_status')!r})")

    r, s = pedir("/api/onu/search_by_mac", {"mac_address": mac, "olt_id": olt_cliente})
    c = cuerpo(r) or {}
    resp = c.get("response") if isinstance(c.get("response"), dict) else c
    matches = resp.get("matches") if isinstance(resp, dict) else None
    acierta = isinstance(matches, list) and any(
        str(m.get("sn") or "").upper() == sn.upper() or str(m.get("onu_external_id") or "").upper() == sn.upper()
        for m in matches if isinstance(m, dict))
    print(f"MAC real: HTTP {r.status_code} en {s:.1f} s · verified={resp.get('verified') if isinstance(resp, dict) else '—'}"
          f" · matches={len(matches) if isinstance(matches, list) else '—'} · la ONU del cliente esta entre ellos={acierta}"
          f" · claves={sorted(resp) if isinstance(resp, dict) else '—'} · {error_de(c)} · Retry-After={r.headers.get('Retry-After')!r}")

    time.sleep(11)   # documentado: 1 busqueda cada 10 s con olt_id
    r, s = pedir("/api/onu/search_by_mac", {"mac_address": "02:00:00:00:00:01", "olt_id": olt_cliente})
    c = cuerpo(r) or {}
    resp = c.get("response") if isinstance(c.get("response"), dict) else c
    matches = resp.get("matches") if isinstance(resp, dict) else None
    print(f"MAC imposible: HTTP {r.status_code} · verified={resp.get('verified') if isinstance(resp, dict) else '—'}"
          f" · matches={len(matches) if isinstance(matches, list) else '—'} · {error_de(c)}")

    # ── M8 · historial de estado del mismo cliente ────────────────────────
    titulo("M8 · get_onu_status_history (24 h) del mismo cliente")
    r, s = pedir(f"/api/onu/get_onu_status_history/{sn}")
    c = cuerpo(r) or {}
    resp = c.get("response") if isinstance(c.get("response"), dict) else c
    resumen = resp.get("summary") if isinstance(resp, dict) else None
    print(f"HTTP {r.status_code} en {s:.1f} s · claves={sorted(resp) if isinstance(resp, dict) else '—'}"
          f" · detail={resp.get('detail') if isinstance(resp, dict) else '—'}"
          f" · timezone={resp.get('timezone') if isinstance(resp, dict) else '—'}"
          f" · summary={sorted(resumen) if isinstance(resumen, dict) else resumen!r} · {cupo(r)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
