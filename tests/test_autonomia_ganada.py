# -*- coding: utf-8 -*-
"""
================================================================================
 LA AUTONOMIA SE GANA CON EVIDENCIA  --  autonomia_ganada.py (31/10/2026)
================================================================================

PRD §2 y §8.17 (Ola 3). Lo que se protege:

  - candidata es SOLO la accion cuyo efecto se verifica en codigo y cuyas
    previas se comprueban en codigo, mirando su config: con la de Rapilink,
    reiniciar_ont si; registrar_pago, cancelar y los tickets, no -- sin una
    lista con nombres;
  - ninguna empresa baja del piso: ni por config (el schema la rechaza) ni
    por una config vieja que se cuele (umbrales() la sube);
  - elegible exige las cuatro cosas a la vez, y una sola no confirmada o
    fallida alcanza para que no lo sea; 0 de 0 no es 0% ni 100%;
  - la ventana es la de la empresa, y lo que no pide aprobacion no aparece.

    py -3.13 tests/test_autonomia_ganada.py
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import yaml                                                  # noqa: E402
from pydantic import ValidationError                         # noqa: E402

from nucleo.config.schema import TenantConfig, UmbralesAutonomia  # noqa: E402
from nucleo.seguridad import autonomia_ganada as ag          # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


print("\nque acciones son candidatas, por su config")
RAPILINK = TenantConfig.model_validate(
    yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8")))
por_nombre = {h.nombre: h for h in RAPILINK.herramientas}
comprobar(ag.por_que_no_es_candidata(por_nombre["reiniciar_ont"]) == [],
          "reiniciar_ont es candidata: mide su efecto y exige previas")
comprobar("efecto_no_verificable" in ag.por_que_no_es_candidata(por_nombre["registrar_pago"]),
          "registrar_pago NO: su efecto no se mide en codigo")
comprobar(all(ag.por_que_no_es_candidata(h) for h in RAPILINK.herramientas
              if h.aprobacion_humana and h.nombre != "reiniciar_ont"),
          "y ninguna otra de las que hoy piden aprobacion")
sin_comprobaciones = SimpleNamespace(verificacion=SimpleNamespace(comprobaciones=[]),
                                     exige_previas=[object()])
comprobar(ag.por_que_no_es_candidata(sin_comprobaciones) == ["efecto_no_verificable"],
          "una verificacion declarada sin comprobaciones no cuenta como verificable")
sin_previas = SimpleNamespace(verificacion=SimpleNamespace(comprobaciones=[object()]), exige_previas=[])
comprobar(ag.por_que_no_es_candidata(sin_previas) == ["sin_previas_en_codigo"],
          "medir el efecto no alcanza: sin previas en codigo tampoco es candidata")

print("\nel piso")
for campo, valor in (("minimo_revisadas", 5), ("ventana_dias", 7), ("tasa_minima_aprobacion", 0.8)):
    try:
        UmbralesAutonomia(**{campo: valor})
        comprobar(False, f"el schema rechaza {campo}={valor}")
    except ValidationError:
        comprobar(True, f"el schema rechaza {campo}={valor}")
vieja = SimpleNamespace(autonomia_ganada=SimpleNamespace(acciones={"reiniciar_ont": SimpleNamespace(
    minimo_revisadas=3, ventana_dias=2, tasa_minima_aprobacion=0.5)}))
comprobar(ag.umbrales(vieja, "reiniciar_ont") == ag.PISO,
          "una config vieja bajo el piso se sube al piso", str(ag.umbrales(vieja, "reiniciar_ont")))
comprobar(ag.umbrales(SimpleNamespace(autonomia_ganada=None), "x") == ag.POR_DEFECTO,
          "sin config, los por defecto (mas que el piso)")
propia = SimpleNamespace(autonomia_ganada=SimpleNamespace(acciones={"reiniciar_ont": UmbralesAutonomia(
    minimo_revisadas=50, ventana_dias=60, tasa_minima_aprobacion=0.98)}))
comprobar(ag.umbrales(propia, "reiniciar_ont") == {"minimo_revisadas": 50, "ventana_dias": 60,
                                                   "tasa_minima_aprobacion": 0.98},
          "una empresa mas exigente que el piso se respeta")

print("\nel veredicto")
U = {"minimo_revisadas": 30, "ventana_dias": 30, "tasa_minima_aprobacion": 0.95}


def m(revisadas=40, rechazadas=1, fallidas=0, no_confirmadas=0):
    return {"revisadas": revisadas, "rechazadas": rechazadas, "fallidas": fallidas,
            "confirmadas": 30, "no_confirmadas": no_confirmadas, "no_verificables": 2, "pendientes": 0}


v = ag.veredicto(m(), U)
comprobar(v["elegible"] and v["faltan"] == [] and v["tasa_aprobacion"] == 0.975,
          "40 revisadas, 1 rechazada, nada fallido: elegible (97,5%)", str(v))
v = ag.veredicto(m(revisadas=29, rechazadas=0), U)
comprobar(not v["elegible"] and v["faltan"] == [{"condicion": "minimo_revisadas", "tiene": 29, "necesita": 30}],
          "29 de 30 no alcanza, y dice cuanto falta", str(v))
v = ag.veredicto(m(rechazadas=3), U)
comprobar(not v["elegible"] and v["faltan"][0]["condicion"] == "tasa_minima_aprobacion"
          and v["faltan"][0]["tiene"] == 0.925, "3 de 40 rechazadas (92,5%) no alcanza el 95%", str(v))
v = ag.veredicto(m(no_confirmadas=1), U)
comprobar(not v["elegible"] and {"condicion": "cero_no_confirmadas", "tiene": 1, "necesita": 0} in v["faltan"],
          "UNA verificacion no confirmada alcanza para que no sea elegible", str(v))
v = ag.veredicto(m(fallidas=1), U)
comprobar(not v["elegible"] and {"condicion": "cero_fallidas", "tiene": 1, "necesita": 0} in v["faltan"],
          "UNA ejecucion fallida tambien", str(v))
v = ag.veredicto(m(revisadas=0, rechazadas=0), U)
comprobar(v["tasa_aprobacion"] is None and not v["elegible"]
          and any(f["condicion"] == "tasa_minima_aprobacion" and f["tiene"] is None for f in v["faltan"]),
          "0 de 0 no es una tasa: None, y no es elegible", str(v))

print("\nevaluar")
AHORA = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
pedidos: list[tuple] = []


def medir(tenant, herramienta, desde, hasta):
    pedidos.append((tenant, herramienta, desde, hasta))
    return m()


filas = ag.evaluar(RAPILINK, "rapilink", AHORA, medir=medir)
nombres = [f["accion"] for f in filas]
comprobar("reiniciar_ont" in nombres and "consultar_cliente" not in nombres,
          "solo las que piden aprobacion humana", str(nombres))
reinicio = next(f for f in filas if f["accion"] == "reiniciar_ont")
comprobar(reinicio["candidata"] and reinicio["elegible"] and reinicio["evidencia"]["revisadas"] == 40,
          "reiniciar_ont con su evidencia y su veredicto", str(reinicio))
comprobar(pedidos == [("rapilink", "reiniciar_ont", AHORA - timedelta(days=30), AHORA)],
          "se mide SOLO la candidata, en la ventana de la empresa", str(pedidos))
pago = next(f for f in filas if f["accion"] == "registrar_pago")
comprobar(not pago["candidata"] and not pago["elegible"] and "evidencia" not in pago,
          "una no candidata no se mide ni puede ser elegible", str(pago))

print("\nla ruta GET /reportes/autonomia-ganada")
from nucleo.canales import api                               # noqa: E402
from nucleo.persistencia import autonomia_ganada as medicion  # noqa: E402

api._config_de = lambda tenant: RAPILINK
api._TOKEN_SERVICIO = None
medicion.medir = lambda tenant, h, desde, hasta: m(revisadas=10, rechazadas=0)
http = api.app.test_client()
r = http.get("/reportes/autonomia-ganada?tenant=rapilink")
d = r.get_json() or {}
reinicio = next((f for f in d.get("acciones", []) if f["accion"] == "reiniciar_ont"), {})
comprobar(r.status_code == 200 and d.get("piso") == ag.PISO and reinicio.get("elegible") is False
          and reinicio["faltan"] == [{"condicion": "minimo_revisadas", "tiene": 10, "necesita": 30}],
          "devuelve cada accion con su veredicto y el piso", r.get_data(as_text=True)[:300])
comprobar(http.get("/reportes/autonomia-ganada").status_code == 400, "sin tenant: 400")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] La autonomia se calcula con evidencia, por empresa, y nunca bajo el piso.")
