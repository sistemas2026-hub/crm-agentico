# -*- coding: utf-8 -*-
"""
Prueba puntual: reinicia una ONU en SmartOLT y hace ping real (via WispHub,
mismo mecanismo que ping_cliente) cada pocos segundos hasta que responda,
para medir el tiempo real de recuperacion. Uso unico, no se integra a nada.
"""
import os
import time

from dotenv import load_dotenv
load_dotenv(".env", override=True)
import requests

SO_BASE = os.environ["SMARTOLT_BASE_URL"].rstrip("/")
SO_HEADERS = {"X-Token": os.environ["SMARTOLT_API_KEY"]}
WH_HEADERS = {"Authorization": f"Api-Key {os.environ['WISPHUB_API_KEY']}"}
SN = "CDTC505AE4AB"
ID_SERVICIO = 6555


def ping() -> tuple[bool, dict]:
    r = requests.post(f"https://api.wisphub.io/api/clientes/{ID_SERVICIO}/ping/",
                      headers=WH_HEADERS, json={"pings": 3, "arp_ping": False}, timeout=20)
    r.raise_for_status()
    inicial = r.json()
    task_id = inicial.get("task_id")
    if not task_id:
        return False, inicial
    for _ in range(8):
        time.sleep(1.2)
        rt = requests.get(f"https://api.wisphub.io/api/tasks/{task_id}/",
                          headers=WH_HEADERS, timeout=15)
        tarea = rt.json().get("task", rt.json())
        if tarea.get("status") == "SUCCESS":
            resultado_lista = tarea.get("result") or []
            resultado = {}
            for item in resultado_lista:
                if isinstance(item, dict):
                    resultado.update(item)
            exitoso = resultado.get("ping-exitoso", "0 de")
            ok = isinstance(exitoso, str) and not exitoso.startswith("0 de")
            return ok, resultado
    return False, {"error": "timeout esperando la tarea de ping"}


print("=" * 72, flush=True)
t0 = time.monotonic()
r = requests.post(f"{SO_BASE}/api/onu/reboot/{SN}", headers=SO_HEADERS, timeout=15)
print(f"+{time.monotonic()-t0:5.1f}s  POST reboot -> {r.status_code} {r.json()}", flush=True)

exitoso_antes = True
for i in range(60):
    ok, detalle = ping()
    elapsed = time.monotonic() - t0
    print(f"+{elapsed:5.1f}s  ping-exitoso={ok}  {detalle}", flush=True)
    if not ok:
        exitoso_antes = False
    if not exitoso_antes and ok:
        print(f"\n>>> Volvio a responder al ping a los {elapsed:.1f}s desde el POST de reinicio", flush=True)
        break
    time.sleep(5)
else:
    print("\n>>> No volvio a responder dentro de la ventana de espera", flush=True)
