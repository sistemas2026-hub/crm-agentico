# -*- coding: utf-8 -*-
"""
================================================================================
 consultar_incidente_red NO BAJA EL INVENTARIO ENTERO  --  10/11/2026
================================================================================

Hasta ese dia, cada conversacion cuyo puerto estaba caido bajaba
get_all_onus_details SIN paginar: ~11,7 MB con nombre, direccion y contacto de
toda la base. Ese export tiene un cupo propio de 15 por hora que BLOQUEA al
pasarse (documentado por SmartOLT). En una caida masiva escriben muchos
clientes a la vez: la llamada 16 de la hora dejaba sin dato a todos.

Lo que se afirma, sobre el EFECTO (las URLs y parametros que salen):

  - nunca se pide el export sin paginar;
  - se pide SOLO el puerto, paginado de a 100 y con 'fields' (sin datos de
    clientes);
  - veinte conversaciones del mismo puerto en un minuto hacen UNA consulta;
  - el conteo de caidas simultaneas sigue dando lo mismo;
  - la forma hexadecimal del serial solo se prueba ante un rechazo del
    identificador; un 429 sale como su propio error.

Sin red.

    py -3.13 tests/test_incidente_red_sin_export.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.herramientas import http as ejecutor_http       # noqa: E402
from nucleo.herramientas import incidentes                  # noqa: E402

fallos: list[str] = []


def comprobar(condicion, que, detalle=""):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


class Resp:
    def __init__(self, codigo, cuerpo=None):
        self.status_code, self._cuerpo, self.headers = codigo, cuerpo or {}, {}
        self.ok = 200 <= codigo < 300

    def json(self):
        return self._cuerpo

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(f"{self.status_code}")


pedidos: list[tuple[str, dict]] = []
estado = {"detalle": None}

PUERTO = [  # 7 caidas a la vez + 1 que lleva meses + una en linea
    *({"sn": f"ONU{i}", "status": "LOS", "last_status_change": "2026-11-10 07:16:0%d" % i}
      for i in range(7)),
    {"sn": "VIEJA", "status": "LOS", "last_status_change": "2026-03-01 10:00:00"},
    {"sn": "SANA", "status": "Online", "last_status_change": "2026-11-01 10:00:00"},
]


def falso_get(url, headers=None, timeout=None, params=None, **kw):
    ruta = url.split("/api/", 1)[-1]
    pedidos.append((ruta, dict(params or {})))
    if ruta.startswith("onu/get_onu_details/"):
        return estado["detalle"](ruta.rsplit("/", 1)[-1])
    if ruta.startswith("system/get_outage_pons/"):
        return Resp(200, {"response": {"sections": [{"key": "partial_los", "groups": [{"pons": [
            {"board": "1", "port": "3", "alert_kind": "partial_los", "affected_onus": 8}]}]}]}})
    if ruta == "onu/get_all_onus_details":
        pagina = int((params or {}).get("page") or 0)
        return Resp(200, {"onus": PUERTO if pagina == 1 else [], "total_pages": 1})
    raise AssertionError(ruta)


incidentes.requests.get = falso_get
ejecutor_http.base_url_de = lambda h, v: "https://olt.ejemplo.test"
ejecutor_http.headers_de = lambda h, t: {}
herr = SimpleNamespace(nombre="consultar_incidente_red")
ubicado = lambda sn: Resp(200, {"onu_details": {"olt_id": "3", "board": 1, "port": 3}})

print("\nlo que se pide")
estado["detalle"] = ubicado
r = incidentes.detectar(herr, {"sn_onu": "ONU0"})
export = [p for ruta, p in pedidos if ruta == "onu/get_all_onus_details"]
comprobar(export and all("page" in p for p in export), "nunca el export sin paginar", str(export))
comprobar(export and export[0].get("olt_id") == "3" and export[0].get("board") == 1
          and export[0].get("port") == 3, "solo el puerto del cliente", str(export))
comprobar(export and export[0].get("page_size") == 100, "de a 100, el maximo documentado")
comprobar(export and "name" not in export[0].get("fields", "") and "sn" in export[0].get("fields", ""),
          "con 'fields': sin nombre, direccion ni contacto")

print("\nlo que se calcula")
comprobar(r["es_incidente_de_red"] is True, "sigue detectando el incidente")
comprobar(r.get("clientes_caidos_a_la_vez") == 7,
          f"7 caidas a la vez, sin contar la de hace meses ni la sana ({r.get('clientes_caidos_a_la_vez')})")

print("\nen una caida masiva, una consulta por minuto y no una por cliente")
pedidos.clear()
for i in range(20):
    incidentes.detectar(herr, {"sn_onu": f"ONU{i % 7}"})
cuantas = sum(1 for ruta, _ in pedidos if ruta == "onu/get_all_onus_details")
comprobar(cuantas == 0, f"veinte conversaciones del mismo puerto en el minuto: 0 consultas nuevas ({cuantas})")
incidentes._cache_puerto.clear()
incidentes.detectar(herr, {"sn_onu": "ONU1"})
cuantas = sum(1 for ruta, _ in pedidos if ruta == "onu/get_all_onus_details")
comprobar(cuantas == 1, "vencida la foto, se vuelve a pedir")

print("\nel serial hexadecimal y el 429")
incidentes._cache_puerto.clear()
pedidos.clear()
estado["detalle"] = lambda sn: Resp(400) if sn == "DC90E681213E" else ubicado(sn)
incidentes.detectar(herr, {"sn_onu": "DC90E681213E"})
detalles = [ruta for ruta, _ in pedidos if ruta.startswith("onu/get_onu_details/")]
comprobar(detalles == ["onu/get_onu_details/DC90E681213E", "onu/get_onu_details/44433930E681213E"],
          "ante un 400 prueba la forma hexadecimal", str(detalles))

pedidos.clear()
estado["detalle"] = lambda sn: Resp(503)
try:
    incidentes.detectar(herr, {"sn_onu": "DC90E681213E"})
    comprobar(False, "un 503 levanta")
except Exception:
    detalles = [ruta for ruta, _ in pedidos if ruta.startswith("onu/get_onu_details/")]
    comprobar(len(detalles) == 1, "un 503 NO reintenta con el otro serial", str(detalles))

estado["detalle"] = lambda sn: Resp(429)
try:
    incidentes.detectar(herr, {"sn_onu": "DC90E681213E"})
    comprobar(False, "un 429 levanta")
except ejecutor_http.LimiteDelProveedor:
    comprobar(True, "un 429 es su propio error")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s)")
    sys.exit(1)
print("\n[OK] Un puerto caido cuesta una consulta paginada por minuto, no un inventario por cliente.")
