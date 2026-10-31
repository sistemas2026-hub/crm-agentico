# -*- coding: utf-8 -*-
"""
================================================================================
 POST /avisos/evento  --  la ruta por la que el CRM pide un aviso (30/10/2026)
================================================================================

Lo que se protege en la RUTA (la decision la cubre test_avisos_proactivos.py):

  - pide tenant, evento del catalogo y clave; sin clave no hay "una sola vez";
  - un evento que no es para el cliente no entra por aca;
  - lo que contesta la decision viaja tal cual (incluido 'reintentar_en'), para
    que el CRM reagende;
  - si la base no contesta (la baja no se pudo comprobar), no sale: 503.

Sin base: la config, el chat del caso y el envio se sustituyen.

    py -3.13 tests/test_avisos_endpoint.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                              # noqa: E402
from nucleo.seguimiento import avisos                       # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


llamadas: list[dict] = []
respuesta = {"enviado": True, "motivo": None}


def falso_avisar(config, tenant, evento, clave, **kw):
    llamadas.append({"tenant": tenant, "evento": evento, "clave": clave, **kw})
    if isinstance(respuesta, Exception):
        raise respuesta
    return respuesta


api._config_de = lambda tenant: SimpleNamespace()
avisos.avisar = falso_avisar
api._TOKEN_SERVICIO = None
http = api.app.test_client()

print("\nlo que pide la ruta")
r = http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "visita_programada",
                                       "clave": "visita:o-1:2026-10-31", "caso_id": "c-1",
                                       "telefono": "3001234567", "contexto": {"franja": "8 a 12"}})
comprobar(r.status_code == 200 and r.get_json() == {"enviado": True, "motivo": None},
          "un pedido completo pasa a la decision", r.get_data(as_text=True)[:200])
comprobar(llamadas and llamadas[-1]["clave"] == "visita:o-1:2026-10-31"
          and llamadas[-1]["telefono_crudo"] == "3001234567" and llamadas[-1]["caso_id"] == "c-1"
          and llamadas[-1]["contexto"] == {"franja": "8 a 12"},
          "con la clave, el caso, el telefono y el contexto", str(llamadas[-1:]))
for falta in ("tenant", "evento", "clave"):
    cuerpo = {"tenant": "rapilink", "evento": "visita_programada", "clave": "k"}
    cuerpo.pop(falta)
    comprobar(http.post("/avisos/evento", json=cuerpo).status_code == 400, f"sin '{falta}': 400")
comprobar(http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "no_existe",
                                             "clave": "k"}).status_code == 400,
          "un evento que no esta en el catalogo: 400")
comprobar(http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "confirmacion_pago",
                                             "clave": "k", "contexto": {"total": "$ 1"}}).status_code == 400,
          "un aviso de cliente que no es proactivo (una confirmacion de pago) no entra: 400")
comprobar(http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "ticket_creado_tecnico",
                                             "clave": "k"}).status_code == 400,
          "un aviso para el tecnico no entra por la ruta de clientes: 400")

print("\nel ticket creado desde Dexter, con el servicio y sin telefono")
respuesta = {"enviado": True, "motivo": None}
lecturas_ficha: list[tuple] = []
api.importacion_io.contacto_del_servicio = (
    lambda config, tenant, s: lecturas_ficha.append((tenant, s)) or {"nombre": "X", "telefono": "3001234567"})
r = http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "ticket_creado_cliente",
                                       "clave": "ticket:wisphub:95001", "caso_id": "c-2",
                                       "servicio": "5832", "contexto": {"ticket_numero": "95001"}})
comprobar(r.status_code == 200 and llamadas[-1]["evento"] == "ticket_creado_cliente"
          and llamadas[-1].get("servicio") == "5832",
          "ticket_creado_cliente entra, y el servicio pasa a la decision", str(llamadas[-1:]))
ficha_de = llamadas[-1].get("ficha_de")
comprobar(callable(ficha_de) and ficha_de("5832") == {"nombre": "X", "telefono": "3001234567"}
          and lecturas_ficha == [("rapilink", "5832")],
          "y la ficha la lee el motor para ESE tenant, solo cuando la decision la pide",
          str(lecturas_ficha))
for malo in ("58 32", "5832; drop", "abc", "1" * 40):
    comprobar(http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "ticket_creado_cliente",
                                                 "clave": "k", "servicio": malo}).status_code == 400,
              f"un servicio que no es un numero no entra: {malo[:12]!r}")

print("\nlo que contesta")
respuesta = {"enviado": False, "motivo": "todavia_no", "reintentar_en": 3600}
r = http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "visita_programada", "clave": "k"})
comprobar(r.get_json() == respuesta, "'todavia_no' viaja con sus segundos, para reagendar", str(r.get_json()))
respuesta = RuntimeError("la base no contesto")
r = http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "visita_programada", "clave": "k"})
comprobar(r.status_code == 503, f"si no se puede decidir, no sale: 503 ({r.status_code})")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] La ruta de avisos pasa el pedido entero y no decide por su cuenta.")
