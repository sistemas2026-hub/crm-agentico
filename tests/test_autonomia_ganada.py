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

print("\nel estado vigente falla cerrado")


def leer_lanza(t, h):
    raise ConnectionError("la base no contesta")


comprobar(ag.vigente("t", "reiniciar_ont", leer=lambda t, h: {"id": "p1", "estado": "activa"})
          == {"autonoma": True, "estado": "activa", "promocion_id": "p1"}, "la ultima fila activa: autonoma")
for fila, estado in ((None, "sin_registro"), ({"id": "p2", "estado": "degradada"}, "degradada"),
                     ({"id": "p3", "estado": "retirada"}, "retirada")):
    comprobar(ag.vigente("t", "x", leer=lambda t, h, f=fila: f)
              == {"autonoma": False, "estado": estado, "promocion_id": None}, f"{estado}: NO autonoma")
comprobar(ag.vigente("t", "x", leer=leer_lanza)
          == {"autonoma": False, "estado": "desconocido", "promocion_id": None},
          "con la base caida NO es autonoma (no se adivina)")


def leer_sin_credenciales(t, h):
    raise SystemExit("No hay datos de conexion")


comprobar(ag.vigente("t", "x", leer=leer_sin_credenciales)["autonoma"] is False,
          "sin credenciales (SystemExit) tampoco: falla cerrado y no tumba el proceso")

print("\npromover")
escritas: list[tuple] = []


def escribir(tenant, accion, actor, motivo, evidencia):
    escritas.append((tenant, accion, actor, evidencia))
    return {"id": "nueva", "estado": "activa"}


def intentar(accion="reiniciar_ont", actor="Ana · u-1", medicion=None):
    escritas.clear()
    try:
        return ag.promover(RAPILINK, "rapilink", accion, actor, AHORA,
                           medir=lambda *a: medicion or m(), escribir=escribir), None
    except ag.NoPromovible as e:
        return None, e


fila, error = intentar()
comprobar(fila == {"id": "nueva", "estado": "activa"} and escritas[0][:3] == ("rapilink", "reiniciar_ont", "Ana · u-1")
          and escritas[0][3]["evidencia"]["revisadas"] == 40 and escritas[0][3]["tasa_aprobacion"] == 0.975,
          "con evidencia, se promueve y queda escrita la evidencia que lo justifico", str(escritas))
_, error = intentar(medicion=m(revisadas=10, rechazadas=0))
comprobar(error is not None and error.codigo == "SIN_EVIDENCIA" and escritas == []
          and error.faltan[0]["condicion"] == "minimo_revisadas",
          "sin evidencia AHORA no se promueve, aunque la pantalla dijera otra cosa", str(error and error.faltan))
_, error = intentar(accion="registrar_pago")
comprobar(error is not None and error.codigo == "NO_CANDIDATA" and escritas == [],
          "registrar_pago no se puede promover: su efecto no se mide", str(error and error.codigo))
_, error = intentar(accion="consultar_cliente")
comprobar(error is not None and error.codigo == "NO_ES_UNA_ACCION_CON_APROBACION",
          "lo que no pide aprobacion no se promueve")
_, error = intentar(actor="   ")
comprobar(error is not None and error.codigo == "FALTA_QUIEN_PROMUEVE" and escritas == [],
          "sin una persona que promueva, no")

print("\nla ruta GET /reportes/autonomia-ganada")
from nucleo.canales import api                               # noqa: E402
from nucleo.persistencia import autonomia_ganada as medicion  # noqa: E402

api._config_de = lambda tenant: RAPILINK
api._TOKEN_SERVICIO = None
medicion.medir = lambda tenant, h, desde, hasta: m(revisadas=10, rechazadas=0)
medicion.vigente = lambda t, h: None
http = api.app.test_client()
r = http.get("/reportes/autonomia-ganada?tenant=rapilink")
d = r.get_json() or {}
reinicio = next((f for f in d.get("acciones", []) if f["accion"] == "reiniciar_ont"), {})
comprobar(r.status_code == 200 and d.get("piso") == ag.PISO and reinicio.get("elegible") is False
          and reinicio["faltan"] == [{"condicion": "minimo_revisadas", "tiene": 10, "necesita": 30}],
          "devuelve cada accion con su veredicto y el piso", r.get_data(as_text=True)[:300])
comprobar(http.get("/reportes/autonomia-ganada").status_code == 400, "sin tenant: 400")

print("\nlas rutas de promover y retirar")
escritas_ruta: list[tuple] = []
medicion.promover = lambda t, a, actor, motivo, ev: escritas_ruta.append(("promover", a, actor)) or {
    "id": "p9", "estado": "activa"}
medicion.retirar = lambda t, a, actor, motivo: escritas_ruta.append(("retirar", a, actor, motivo)) or {
    "id": "p10", "estado": "retirada"}
medicion.vigente = lambda t, h: None
medicion.medir = lambda tenant, h, desde, hasta: m()
AUTOR = {"autor": "Ana Perez", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}
r = http.post("/autonomia-ganada/promover", json={"tenant": "rapilink", "accion": "reiniciar_ont", **AUTOR})
comprobar(r.status_code == 201 and escritas_ruta[-1][:2] == ("promover", "reiniciar_ont")
          and "Ana Perez" in escritas_ruta[-1][2], "con evidencia y autor: 201, y queda quien",
          f"{r.status_code} {escritas_ruta}")
n = len(escritas_ruta)
r = http.post("/autonomia-ganada/promover", json={"tenant": "rapilink", "accion": "reiniciar_ont"})
comprobar(r.status_code == 400 and len(escritas_ruta) == n, "sin autor de la sesion: 400 y nada escrito")
medicion.medir = lambda tenant, h, desde, hasta: m(revisadas=5, rechazadas=0)
r = http.post("/autonomia-ganada/promover", json={"tenant": "rapilink", "accion": "reiniciar_ont", **AUTOR})
comprobar(r.status_code == 409 and r.get_json()["error"] == "SIN_EVIDENCIA" and len(escritas_ruta) == n,
          "sin evidencia: 409 con lo que falta, y nada escrito", r.get_data(as_text=True)[:200])
r = http.post("/autonomia-ganada/retirar", json={"tenant": "rapilink", "accion": "reiniciar_ont",
                                                 "motivo": "la reviso", **AUTOR})
comprobar(r.status_code == 201 and escritas_ruta[-1][0] == "retirar" and escritas_ruta[-1][3] == "la reviso",
          "retirar: siempre se puede, con motivo", str(escritas_ruta[-1:]))
comprobar(http.post("/autonomia-ganada/retirar", json={"tenant": "rapilink", "accion": "reiniciar_ont",
                                                        **AUTOR}).status_code == 400,
          "retirar sin motivo: 400")
medicion.vigente = lambda t, h: {"id": "p9", "estado": "activa"}
medicion.medir = lambda tenant, h, desde, hasta: m()
d = http.get("/reportes/autonomia-ganada?tenant=rapilink").get_json()
reinicio = next(f for f in d["acciones"] if f["accion"] == "reiniciar_ont")
comprobar(reinicio.get("autonomia") == {"autonoma": True, "estado": "activa", "promocion_id": "p9"},
          "el reporte dice si ya es autonoma", str(reinicio.get("autonomia")))

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] La autonomia se calcula con evidencia, por empresa, y nunca bajo el piso.")
