# -*- coding: utf-8 -*-
"""
================================================================================
 LA VENTANA DE 24 H VIAJA CON LA COLA
================================================================================

    py -3.13 tests/test_cola_ventana.py

Corre sin base y sin red: se sustituye la persistencia y la config, y se pide
GET /conversaciones con el cliente de prueba de Flask.

POR QUE EXISTE  (29/10/2026)
----------------------------
La ventana de WhatsApp solo se calculaba al abrir UNA conversacion; en la cola
no se veia cual estaba por cerrarse. Ahora cada fila de WhatsApp lleva
'ventana_whatsapp', calculada con el mismo whatsapp.estado_de_ventana. Lo que
se protege: que la cuente desde el ultimo mensaje del NUMERO (puede estar en
otra abierta del chat), y que una fila sin mensaje del cliente diga "no se
sabe" y no "cerrada".
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
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


ahora = datetime.now(timezone.utc)
FILAS = [
    # Escribio hace 23 h: le queda una hora.
    {"id": "a", "canal": "whatsapp", "usuario_externo": "1", "estado": "abierta",
     "control": "humano", "ultimo_mensaje_cliente": ahora - timedelta(hours=23)},
    # Nunca escribio el cliente: no se sabe, no es "cerrada".
    {"id": "b", "canal": "whatsapp", "usuario_externo": "2", "estado": "abierta",
     "control": "humano", "ultimo_mensaje_cliente": None},
    # Otro canal: la regla de Meta no aplica.
    {"id": "c", "canal": "whatsapp-simulado", "usuario_externo": "3", "estado": "abierta",
     "control": "humano", "ultimo_mensaje_cliente": ahora - timedelta(hours=1)},
]

yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
         if not p.name.startswith("tenant.config.example")]
CFG = cargar_config(yamls[0])

reales = (api._config_de, api.persistencia.ultima_actividad,
          api.persistencia.salud_canal_whatsapp)
api._config_de = lambda tenant: CFG
api.persistencia.ultima_actividad = lambda tenant, canal=None: [dict(f) for f in FILAS]
api.persistencia.salud_canal_whatsapp = lambda tenant: None
try:
    print()
    print("=" * 78)
    print("  LA VENTANA DE 24 H VIAJA CON LA COLA")
    print("=" * 78)
    with api.app.test_client() as c:
        r = c.get("/conversaciones?tenant=prueba")
        filas = {f["id"]: f for f in (r.get_json() or {}).get("conversaciones", [])}
    comprobar(r.status_code == 200, f"la cola responde (devolvio {r.status_code})")
    va = (filas.get("a") or {}).get("ventana_whatsapp") or {}
    comprobar(va.get("abierta") is True and 3000 < (va.get("restante_seg") or 0) <= 3600,
              f"escribio hace 23 h: abierta y con ~1 h (restante {va.get('restante_seg')})")
    vb = (filas.get("b") or {}).get("ventana_whatsapp") or {}
    comprobar(vb.get("abierta") is None,
              "sin mensaje del cliente: 'no se sabe', no cerrada")
    comprobar("ventana_whatsapp" not in (filas.get("c") or {}),
              "otro canal: no lleva ventana")

    # El ultimo mensaje del NUMERO puede estar en otra abierta del chat.
    vieja = dict(FILAS[0], ultimo_mensaje_cliente=ahora - timedelta(hours=30))
    nueva = dict(FILAS[0], id="a2", ultimo_mensaje_cliente=ahora - timedelta(hours=2))
    api.persistencia.ultima_actividad = lambda tenant, canal=None: [vieja]
    fila = {**vieja, "abiertas": [nueva]}
    real_agrupar = api.proyeccion.agrupar_por_numero
    api.proyeccion.agrupar_por_numero = lambda salida, nac: [fila]
    real_creado = api.persistencia.creado_en_de
    api.persistencia.creado_en_de = lambda tenant, ids: {}
    try:
        with api.app.test_client() as c:
            r = c.get("/conversaciones?tenant=prueba&por_numero=1")
        v = ((r.get_json() or {}).get("conversaciones") or [{}])[0].get("ventana_whatsapp") or {}
    finally:
        api.proyeccion.agrupar_por_numero = real_agrupar
        api.persistencia.creado_en_de = real_creado
    comprobar(v.get("abierta") is True and (v.get("restante_seg") or 0) > 20 * 3600,
              "por chat: cuenta desde el mensaje mas nuevo entre sus abiertas, no el de la fila")
finally:
    (api._config_de, api.persistencia.ultima_actividad,
     api.persistencia.salud_canal_whatsapp) = reales

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
