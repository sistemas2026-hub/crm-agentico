# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL RESUMEN DE ESTABILIDAD DEL ENLACE
================================================================================

El caso que esta herramienta atiende es el mas facil de dar por bueno sin
serlo: el cliente dice "a veces anda mal", el agente mide y todo da perfecto
-- porque midio justo cuando estaba andando. La evidencia esta en el historial,
y contarlo es codigo (PRD 12.5).

Desde el 10/11/2026 el historial sale de get_onu_status_history. Lo que se
protege aca, en orden de importancia:

  - Que una ausencia de datos NUNCA se lea como "estable": si SmartOLT no sabe
    que paso en buena parte de la ventana, se dice eso (la trampa del
    'online_percent' de 99,99 % con 21 dias sin datos, 13/10/2026).
  - Que un equipo caido todo el dia no salga como "sin caidas".
  - Que una caida sea pasar de online a caido: LOS y despues offline son UNA.
  - Que un reinicio de la OLT no cuente como caida del cliente.
  - Que la forma hexadecimal del serial se pruebe solo ante un rechazo del
    identificador, y un 429 salga como su propio error.

Sin red: la parte pura con historiales armados con la forma medida en vivo, y
el despacho con `requests.get` sustituido.

    py -3.13 tests/test_estabilidad.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.herramientas import estabilidad                   # noqa: E402
from nucleo.herramientas import http as ejecutor_http         # noqa: E402
from nucleo.herramientas.estabilidad import (                 # noqa: E402
    CAIDAS_PARA_INESTABLE, VENTANA_HORAS, resumir_historial)

fallos: list[str] = []


def comprobar(condicion, descripcion):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


DIA = 24 * 3600


def historial(periodos, conocidos=DIA):
    """La forma medida el 10/11/2026 (claves de un periodo: cause, from,
    seconds, status, to)."""
    return {"status": True, "detail": "transitions", "timezone": "America/Bogota",
            "periods": [{"status": s, "from": f"2026-11-09 {h}", "to": "x", "seconds": 60,
                         "cause": c} for s, h, c in periodos],
            "summary": {"known_seconds": conocidos, "online_percent": 99.9,
                        "interruptions": 0, "seconds": {}}}


print("\nlo que se cuenta")
r = resumir_historial(historial([
    ("online", "08:00:00", None), ("los", "09:00:00", None), ("online", "09:10:00", None),
    ("los", "10:00:00", None), ("offline", "10:05:00", None), ("online", "10:30:00", None),
    ("power_fail", "12:00:00", None), ("online", "12:20:00", None),
    ("los", "15:00:00", None), ("online", "15:05:00", None)]))
comprobar(r["caidas_en_ventana"] == 4, f"cuatro caidas: LOS y despues offline son UNA ({r})")
comprobar(r["enlace_inestable"] is True, "con 3 o mas, inestable")
comprobar(r["causa_dominante"] == estabilidad.CAUSAS["los"] and r["veces_la_causa_dominante"] == 3,
          "la causa dominante se nombra legible: perdida de señal, 3 veces")
comprobar(r["ultima_caida"] == "2026-11-09 15:00:00 (America/Bogota)",
          "la ultima caida va con la zona que declara la respuesta")

r = resumir_historial(historial([
    ("online", "08:00:00", None), ("offline", "09:00:00", "olt_reboot"), ("online", "09:05:00", None)]))
comprobar(r["caidas_en_ventana"] == 0, "un reinicio de la OLT no es una caida del cliente")

r = resumir_historial(historial([("online", "08:00:00", None), ("power_fail", "09:00:00", None),
                                 ("online", "09:30:00", None)]))
comprobar(r["enlace_inestable"] is False and r["caidas_en_ventana"] == 1,
          "una sola caida no es inestable (puede ser un corte de luz)")

print("\nla ausencia de datos no se lee como estable")
r = resumir_historial(historial([("online", "08:00:00", None)], conocidos=DIA * 0.3))
comprobar(r["enlace_inestable"] is False and "no tiene datos" in r["motivo"]
          and "caidas_en_ventana" not in r,
          "con 30% de la ventana conocida: se dice que no hay datos, no 'cero caidas'")
r = resumir_historial({"periods": [], "summary": {}})
comprobar("no tiene datos" in r["motivo"], "una respuesta vacia tampoco afirma nada")
r = resumir_historial(historial([("los", "00:00:00", None)]))
comprobar(r["caidas_en_ventana"] == 0 and "caido desde antes" in r["motivo"],
          "caido todo el dia: no sale como 'sin caidas', sale como caida que sigue")
r = resumir_historial(historial([("online", "00:00:00", None)]))
comprobar(r["motivo"] == "sin caidas registradas en la ventana", "sano todo el dia: sin caidas")

print("\nlos umbrales")
comprobar(VENTANA_HORAS == 24, "la ventana es de un dia")
comprobar(CAIDAS_PARA_INESTABLE >= 3, "hacen falta 3 o mas caidas")

print("\nel despacho: endpoint, forma hexadecimal y 429")
pedidos: list[str] = []
respuestas: list = []


class Resp:
    def __init__(self, codigo, cuerpo=None, cabeceras=None):
        self.status_code, self._cuerpo, self.headers = codigo, cuerpo or {}, cabeceras or {}

    def json(self):
        return self._cuerpo


def falso_get(url, headers=None, timeout=None, **kw):
    pedidos.append(url.rsplit("/api/", 1)[-1])
    return respuestas.pop(0)


estabilidad.requests.get = falso_get
herr = SimpleNamespace(nombre="consultar_estabilidad_enlace", base_url="https://olt.ejemplo.test",
                       base_url_ref=None, auth_ref=None, auth_esquema="", auth_header="X-Token",
                       reintentar_identificador_como={"sn_onu": "gpon_hex"})
ejecutor_http.base_url_de = lambda h, v: "https://olt.ejemplo.test"
ejecutor_http.headers_de = lambda h, t: {}

respuestas[:] = [Resp(400), Resp(200, historial([("online", "00:00:00", None)]))]
r = estabilidad.resumir(herr, {"sn_onu": "DC90E681213E"})
comprobar(pedidos == ["onu/get_onu_status_history/DC90E681213E",
                      "onu/get_onu_status_history/44433930E681213E"],
          f"lee el historial, y ante un 400 prueba la forma hexadecimal ({pedidos})")
comprobar(r["motivo"] == "sin caidas registradas en la ventana", "y resume lo que trajo")

pedidos.clear()
respuestas[:] = [Resp(503)]
try:
    estabilidad.resumir(herr, {"sn_onu": "DC90E681213E"})
    comprobar(False, "un 503 no se disfraza de dato")
except estabilidad.ErrorEstabilidad:
    comprobar(pedidos == ["onu/get_onu_status_history/DC90E681213E"],
              "un 503 es un error y NO reintenta con el otro serial")

pedidos.clear()
respuestas[:] = [Resp(429, cabeceras={"Retry-After": "120"})]
try:
    estabilidad.resumir(herr, {"sn_onu": "DC90E681213E"})
    comprobar(False, "un 429 levanta")
except ejecutor_http.LimiteDelProveedor as e:
    comprobar(e.retry_after == "120" and len(pedidos) == 1,
              "un 429 es su propio error, con el Retry-After, sin reintento")

comprobar(estabilidad.resumir(herr, {})["motivo"].startswith("no hay una ONU"),
          "sin serial no se consulta nada")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] El resumen de estabilidad cuenta lo que hay que contar.")
