# -*- coding: utf-8 -*-
"""
================================================================================
 LAS RUTAS DEL AVISO DE CAIDA  --  /avisos/caida/* (30/10/2026)
================================================================================
La decision la cubre test_aviso_de_caida.py. Lo que se protege en las RUTAS:

  - afectados: pide un puerto de digitos; contesta conteos y servicios, nunca
    seriales; 'cargando' y 'no configurado' se distinguen de "no hay nadie";
  - lote: exige quien aprobo (una persona, PRD §8.17), una situacion y el
    puerto; NO le cree la lista al CRM -- la cruza con lo que lee en ese
    momento --; respeta el tamaño de lote de la empresa; cada aviso sale por
    la puerta comun con la clave (situacion, servicio) y sin contexto de afuera.

Sin base ni red: la config, la lectura y el envio se sustituyen.

    py -3.13 tests/test_aviso_de_caida_rutas.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                              # noqa: E402
from nucleo.seguimiento import aviso_de_caida, avisos       # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


CONFIG = SimpleNamespace(aviso_de_caida=SimpleNamespace(lote=3))
api._config_de = lambda tenant: CONFIG
api._TOKEN_SERVICIO = None
lecturas: list[tuple] = []
vigentes = {"servicios": ["101", "102", "103", "104"], "equipos_en_falla": 5, "sin_cliente": 1,
            "fuera_de_estado": 0, "desde": "2026-10-30 07:16:44"}


def falso_afectados(config, tenant, olt, board, port, leer=None):
    lecturas.append((tenant, olt, board, port))
    if isinstance(vigentes, Exception):
        raise vigentes
    return vigentes


aviso_de_caida.afectados = falso_afectados
from nucleo.seguimiento import mensajes_automaticos         # noqa: E402

estado_aviso = {"listo": None}
mensajes_automaticos.listo = lambda config, tenant, evento: estado_aviso["listo"]
mensajes_automaticos.en_prueba = lambda config, evento: False
pedidos: list[dict] = []


def falso_avisar(config, tenant, evento, clave, **kw):
    pedidos.append({"evento": evento, "clave": clave, **kw})
    return {"enviado": True, "motivo": None}


avisos.avisar = falso_avisar
http = api.app.test_client()
PUERTO = {"olt": "3", "board": "2", "port": "11"}

print("\nafectados")
r = http.post("/avisos/caida/afectados", json={"tenant": "rapilink", **PUERTO})
comprobar(r.status_code == 200
          and r.get_json() == {**vigentes, "lote": 3, "no_listo": None, "modo_prueba": False}
          and lecturas[-1] == ("rapilink", "3", "2", "11"),
          "un puerto valido devuelve conteos, servicios, el lote y si el aviso puede salir",
          r.get_data(as_text=True)[:200])
estado_aviso["listo"] = "apagado"
r = http.post("/avisos/caida/afectados", json={"tenant": "rapilink", **PUERTO})
comprobar(r.get_json().get("no_listo") == "apagado",
          "si el aviso esta apagado, lo dice ANTES de que alguien apruebe", str(r.get_json()))
estado_aviso["listo"] = None
for campo, malo in (("olt", "3; drop"), ("board", ""), ("port", "a1")):
    r = http.post("/avisos/caida/afectados", json={"tenant": "rapilink", **{**PUERTO, campo: malo}})
    comprobar(r.status_code == 400, f"'{campo}' que no es un numero: 400")
vigentes = {"cargando": True}
r = http.post("/avisos/caida/afectados", json={"tenant": "rapilink", **PUERTO})
comprobar(r.status_code == 202 and r.get_json() == {"cargando": True},
          "con el padron armandose: 202 'cargando', no una lista vacia", str(r.status_code))
vigentes = aviso_de_caida.CaidaNoAvisable("NO_CONFIGURADO", 503)
r = http.post("/avisos/caida/afectados", json={"tenant": "rapilink", **PUERTO})
comprobar(r.status_code == 503 and r.get_json() == {"error": "NO_CONFIGURADO"},
          "sin configurar: 503 con el codigo", str(r.get_json()))

print("\nlote")
vigentes = {"servicios": ["101", "102", "104"], "equipos_en_falla": 3}
pedidos.clear()
cuerpo = {"tenant": "rapilink", **PUERTO, "situacion": "sit-9", "autor": "Ana NOC",
          "servicios": ["101", "103", "104"], "contexto": {"cliente_nombre": "Inventado"}}
r = http.post("/avisos/caida/lote", json=cuerpo)
d = r.get_json() or {}
comprobar(r.status_code == 200 and [p["servicio"] for p in pedidos] == ["101", "104"],
          "solo se avisa a los que SIGUEN en la falla (el 103 volvio o nunca estuvo)",
          f"{r.status_code} {[p.get('servicio') for p in pedidos]}")
comprobar(d.get("enviados") == 2 and d.get("descartados") == 1,
          "y dice cuantos descarto", str(d))
comprobar(all(p["clave"] == f"caida:sit-9:{p['servicio']}" and p["evento"] == "caida_masiva"
              and p["contexto"] == {} and p["telefono_crudo"] is None and p["caso_id"] is None
              for p in pedidos),
          "cada uno con su clave, sin contexto ni destino de afuera", str(pedidos[:1]))
for falta in ("autor", "situacion", "servicios"):
    c = dict(cuerpo)
    c.pop(falta)
    comprobar(http.post("/avisos/caida/lote", json=c).status_code == 400, f"sin '{falta}': 400")
comprobar(http.post("/avisos/caida/lote", json={**cuerpo, "autor": "   "}).status_code == 400,
          "un autor en blanco no es una persona: 400")
comprobar(http.post("/avisos/caida/lote", json={**cuerpo, "servicios": ["1", "2", "3", "4"]}).status_code == 400,
          "mas que el lote de la empresa: 400")
comprobar(http.post("/avisos/caida/lote", json={**cuerpo, "servicios": ["10 1"]}).status_code == 400,
          "un servicio que no es un numero: 400")
comprobar(http.post("/avisos/caida/lote", json={**cuerpo, "situacion": "a b/c"}).status_code == 400,
          "una situacion con caracteres raros: 400")
vigentes = {"cargando": True}
pedidos.clear()
r = http.post("/avisos/caida/lote", json=cuerpo)
comprobar(r.get_json().get("reintentar_en") and r.get_json().get("pendientes") == cuerpo["servicios"]
          and pedidos == [], "con el padron armandose, el lote entero vuelve despues", str(r.get_json()))

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Las rutas del aviso de caida no le creen la lista a quien la manda.")
