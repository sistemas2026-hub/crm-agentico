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

print("\nel contexto que manda quien pide: solo lo que el evento acepta")
r = http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "visita_programada", "clave": "k",
                                       "telefono": "3001234567",
                                       "contexto": {"franja": "8 a 12", "empresa": "OTRA EMPRESA",
                                                    "fecha": "01/01/1999", "enlace_factura": "http://x"}})
comprobar(llamadas[-1]["contexto"] == {"franja": "8 a 12"},
          "la empresa, la fecha o un dato de otro evento no se pueden pisar desde afuera",
          str(llamadas[-1]["contexto"]))

print("\nel ticket creado: el motor confirma el hecho contra el ISP")
respuesta = {"enviado": True, "motivo": None}
lecturas_ficha: list[tuple] = []
hechos: list[str] = []
api.importacion_io.contacto_del_servicio = (
    lambda config, tenant, s: lecturas_ficha.append((tenant, s)) or {"nombre": "X", "telefono": "3001234567"})
avisos.hecho_del_ticket = lambda config, numero, leer, asuntos: (
    hechos.append(numero) or {"clave": f"ticket:wisphub:{numero}", "servicio": "5832",
                              "contexto": {"ticket_numero": numero, "ticket_asunto": "Sin internet"}})
r = http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "ticket_creado_cliente",
                                       "ticket": "95001", "clave": "LA-QUE-YO-QUIERA",
                                       "caso_id": "caso-de-otro", "servicio": "1", "telefono": "3159999999",
                                       "contexto": {"ticket_asunto": "Pague en http://estafa",
                                                    "cliente_nombre": "Inventado"}})
ult = llamadas[-1]
comprobar(r.status_code == 200 and hechos == ["95001"] and ult["evento"] == "ticket_creado_cliente",
          "entra con el numero de ticket, y el motor lo lee", f"{r.status_code} {hechos}")
comprobar(ult["clave"] == "ticket:wisphub:95001" and ult.get("servicio") == "5832"
          and ult["contexto"] == {"ticket_numero": "95001", "ticket_asunto": "Sin internet"},
          "clave, servicio y asunto salen del ISP, no del pedido", str(ult))
comprobar(ult.get("caso_id") is None and not ult.get("telefono_crudo"),
          "ni el chat de otro caso ni un telefono suelto deciden el destino", str(ult))
ficha_de = ult.get("ficha_de")
comprobar(callable(ficha_de) and ficha_de("5832") == {"nombre": "X", "telefono": "3001234567"}
          and lecturas_ficha == [("rapilink", "5832")],
          "y la ficha la lee el motor para ESE tenant, solo cuando la decision la pide",
          str(lecturas_ficha))
avisos.hecho_del_ticket = lambda config, numero, leer, asuntos: {"enviado": False,
                                                                 "motivo": "ticket_no_existe"}
n = len(llamadas)
r = http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "ticket_creado_cliente",
                                       "ticket": "99999"})
comprobar(r.get_json() == {"enviado": False, "motivo": "ticket_no_existe"} and len(llamadas) == n,
          "un ticket que el ISP no confirma no llega a la decision", str(r.get_json()))
for malo in ("95 001", "95001; drop", "abc", "1" * 40, None):
    comprobar(http.post("/avisos/evento", json={"tenant": "rapilink", "evento": "ticket_creado_cliente",
                                                 "ticket": malo}).status_code == 400,
              f"un ticket que no es un numero no entra: {str(malo)[:12]!r}")

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
