# -*- coding: utf-8 -*-
"""
================================================================================
 LA COLA PIDE SOLO LAS CERRADAS RECIENTES
================================================================================

    py -3.13 tests/test_cola_cerradas_dias.py

Corre sin base y sin red. GET /conversaciones?cerradas_dias=N debe llevar N a
la consulta (acotado a 1..3650), devolverlo en la respuesta, y rechazar con 400
lo que no es un numero. Sin el parametro, la consulta recibe None (todas): el
detector de seguimientos y el resto de los llamadores no cambian.
La consulta real, contra Postgres: tests/test_cola_acotada_base.py.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
         if not p.name.startswith("tenant.config.example")]
CFG = cargar_config(yamls[0])
recibido: list = []


def falsa(tenant, canal=None, cerradas_dias=None):
    recibido.append(cerradas_dias)
    return []


reales = (api._config_de, api.persistencia.ultima_actividad,
          api.persistencia.salud_canal_whatsapp)
api._config_de = lambda tenant: CFG
api.persistencia.ultima_actividad = falsa
api.persistencia.salud_canal_whatsapp = lambda tenant: None
try:
    print("\n" + "=" * 78 + "\n  LA COLA PIDE SOLO LAS CERRADAS RECIENTES\n" + "=" * 78)
    with api.app.test_client() as c:
        r = c.get("/conversaciones?tenant=prueba")
        comprobar(r.status_code == 200 and recibido[-1] is None and r.get_json()["cerradas_dias"] is None,
                  "sin el parametro: todas (None)")
        r = c.get("/conversaciones?tenant=prueba&cerradas_dias=30")
        comprobar(r.status_code == 200 and recibido[-1] == 30 and r.get_json()["cerradas_dias"] == 30,
                  "con 30: llega 30 a la consulta y vuelve en la respuesta")
        c.get("/conversaciones?tenant=prueba&cerradas_dias=0")
        comprobar(recibido[-1] == 1, "0 se acota a 1: cero dias no es 'todas'")
        c.get("/conversaciones?tenant=prueba&cerradas_dias=999999")
        comprobar(recibido[-1] == 3650, "un numero absurdo se acota a 3650")
        n = len(recibido)
        r = c.get("/conversaciones?tenant=prueba&cerradas_dias=abc")
        comprobar(r.status_code == 400 and len(recibido) == n,
                  "'abc': 400 y la consulta no corre")
finally:
    (api._config_de, api.persistencia.ultima_actividad,
     api.persistencia.salud_canal_whatsapp) = reales

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S)")
    raise SystemExit(1)
print("  todo en verde")
