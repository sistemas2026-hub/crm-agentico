# -*- coding: utf-8 -*-
"""
================================================================================
 PRIMERA RESPUESTA DESDE LA BANDEJA  --  el motor le avisa al caso del CRM
================================================================================
    py -3.13 tests/test_primera_respuesta_bandeja.py              (sin base)

Por que existe
--------------
Hasta el 25/10/2026 un ticket que nacia por WhatsApp y se contestaba desde la
Bandeja figuraba en el CRM "sin primera respuesta" para siempre: la respuesta
la guardaba y la entregaba el motor, y el CRM no se enteraba. La copia que va
al ticket del ISP tampoco volvia, porque el caso de un chat no esta atado a
ese ticket como los importados.

Lo que se afirma, sobre el EFECTO y en las dos direcciones:

  1. la ruta real avisa al caso cuando la respuesta fue ACEPTADA, y no cuando
     la entrega fallo (ventana de 24 h cerrada: el cliente no recibio nada);
  2. una conversacion sin caso no avisa nada; respondiendo desde el ticket,
     el caso es el del ticket;
  3. que el aviso falle no rompe la respuesta, que ya salio;
  4. la llamada que sale es la que el CRM espera: POST a
     /api/cases/<id>/primera-respuesta/ con {"momento": <ISO con zona>};
  5. la herramienta esta en el catalogo del tenant y NINGUN rol la ve: la
     ejecuta el codigo, nunca el modelo.
================================================================================
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.pop("MOTOR_SERVICE_TOKEN", None)

import yaml                                                       # noqa: E402

fallos: list[str] = []
TENANT = "rapilink"
CONV = "11111111-2222-3333-4444-555555555555"
CASO = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
AUTOR = {"autor": "Operador de prueba",
         "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


from nucleo.canales import api                                    # noqa: E402
from nucleo.config.schema import Herramienta                      # noqa: E402
from nucleo.herramientas import http as ejecutor_http             # noqa: E402
from nucleo.seguimiento import operativo                          # noqa: E402

api.app.config["TESTING"] = True
cliente = api.app.test_client()


class Espia:
    def __init__(self, *, canal="whatsapp", resultado="aceptado", caso=CASO,
                 aviso_rompe=False):
        self.canal, self.resultado, self.caso = canal, resultado, caso
        self.aviso_rompe = aviso_rompe
        self.avisos: list[tuple] = []


def montar(espia, parches):
    def guardar(tenant, conv, contenido, autor, **kw):
        return {"canal": espia.canal, "usuario_externo": "573001112233",
                "ticket_operativo": None, "mensaje_id": "m-1"}

    def entregar(*a, **k):
        return {"resultado": espia.resultado,
                "aceptado_por_meta": espia.resultado == "aceptado",
                "aceptacion_registrada": espia.resultado == "aceptado"}

    def avisar(config, tenant, caso, momento, autor=""):
        if espia.aviso_rompe:
            raise RuntimeError("el CRM no contesto")
        espia.avisos.append((caso, momento, autor))
        return True

    for obj, nombre, valor in (
            (api, "_exigir_control_humano", lambda *a, **k: None),
            (api.persistencia, "agregar_mensaje_humano", guardar),
            (api.persistencia, "caso_de_conversacion", lambda t, c: espia.caso),
            (api, "_entregar_y_registrar", entregar),
            (api, "_config_de", lambda tenant: None),
            (api.operativo, "sellar_primera_respuesta", avisar)):
        parches.append((obj, nombre, getattr(obj, nombre)))
        setattr(obj, nombre, valor)


def responder(espia, ruta=f"/conversaciones/{CONV}/mensajes", extra=None):
    parches: list = []
    montar(espia, parches)
    for obj, nombre, valor in (extra or []):
        parches.append((obj, nombre, getattr(obj, nombre)))
        setattr(obj, nombre, valor)
    try:
        r = cliente.post(ruta, json={"tenant": TENANT, "mensaje": "Ya lo reviso, un momento.",
                                     "clave_idempotencia": "k-1", **AUTOR})
        return r.status_code, (r.get_json() or {})
    finally:
        for obj, nombre, original in reversed(parches):
            setattr(obj, nombre, original)


# =============================================================================
titulo("1. Se avisa cuando la respuesta SALIO, no cuando se guardo")
# =============================================================================
e = Espia()
codigo, cuerpo = responder(e)
revisar(codigo == 201 and len(e.avisos) == 1 and e.avisos[0][0] == CASO,
        "una respuesta aceptada le avisa al caso de la conversacion", f"{codigo} {e.avisos}")
if e.avisos:
    momento = datetime.fromisoformat(e.avisos[0][1])
    revisar(momento.tzinfo is not None, "el momento viaja con zona", e.avisos[0][1])
    revisar(e.avisos[0][2] == AUTOR["autor"], "y con quien respondio", f"{e.avisos[0]}")
revisar(cuerpo.get("primera_respuesta_avisada") is True,
        "la respuesta dice que se aviso", f"{cuerpo}")

for resultado in ("rechazado", "fallido", "incierto"):
    e = Espia(resultado=resultado)
    codigo, _ = responder(e)
    revisar(codigo == 201 and e.avisos == [],
            f"una entrega '{resultado}' NO cuenta como respuesta", f"{e.avisos}")

e = Espia(canal="simulador")
codigo, _ = responder(e)
revisar(codigo == 201 and len(e.avisos) == 1,
        "un canal sin entrega externa (se lee en la misma pantalla) si avisa", f"{e.avisos}")

# =============================================================================
titulo("2. De que caso")
# =============================================================================
e = Espia(caso=None)
codigo, _ = responder(e)
revisar(codigo == 201 and e.avisos == [],
        "una conversacion sin caso no avisa nada", f"{e.avisos}")

e = Espia(caso="otro-caso-de-la-conversacion")
codigo, _ = responder(e, ruta=f"/casos/{CASO}/mensajes", extra=[
    (api.persistencia, "conversacion_de_caso", lambda t, c: {"id": CONV}),
    (api.persistencia, "control_efectivo_de", lambda t, c: "humano")])
revisar(codigo == 201 and [a[0] for a in e.avisos] == [CASO],
        "respondiendo desde el ticket, el aviso va a ESE caso", f"{codigo} {e.avisos}")

# =============================================================================
titulo("3. Que el aviso falle no rompe la respuesta")
# =============================================================================
e = Espia(aviso_rompe=True)
codigo, cuerpo = responder(e)
revisar(codigo == 201 and cuerpo.get("primera_respuesta_avisada") is False,
        "el CRM caido no tumba la respuesta: sale 201 y lo dice", f"{codigo} {cuerpo}")

# =============================================================================
titulo("4. La llamada que sale es la que el CRM espera")
# =============================================================================
herramienta = Herramienta(
    nombre="avisar_primera_respuesta_crm", tipo="http", sella_primera_respuesta=True,
    descripcion="prueba", solo_lectura=False, requiere_confirmacion=True,
    roles_permitidos=["soporte"], base_url="http://backend:8000",
    endpoint="/api/cases/{id_caso}/primera-respuesta/", metodo="POST",
    auth_ref="BOTTLECRM_API_TOKEN", auth_esquema="Bearer")


class Config:
    herramientas = [herramienta]


salidas: list = []


class Respuesta:
    status_code = 200
    ok = True
    text = "{}"
    headers = {"content-type": "application/json"}

    def json(self):
        return {"error": False}

    def raise_for_status(self):
        return None


def pedido(metodo, url, **kw):
    salidas.append((metodo, url, kw.get("json")))
    return Respuesta()


originales = [(ejecutor_http, "headers_de", ejecutor_http.headers_de),
              (ejecutor_http.requests, "request", ejecutor_http.requests.request)]
ejecutor_http.headers_de = lambda h, t: {}
ejecutor_http.requests.request = pedido
try:
    hecho = operativo.sellar_primera_respuesta(
        Config, TENANT, CASO, "2026-10-25T14:00:00+00:00", "Operador de prueba")
finally:
    for obj, nombre, original in originales:
        setattr(obj, nombre, original)

revisar(hecho is True, "operativo devuelve que aviso")
revisar(salidas == [("POST", f"http://backend:8000/api/cases/{CASO}/primera-respuesta/",
                     {"momento": "2026-10-25T14:00:00+00:00"})],
        "POST a /api/cases/<id>/primera-respuesta/ con el momento en el cuerpo", f"{salidas}")


class SinHerramienta:
    herramientas: list = []


revisar(operativo.sellar_primera_respuesta(SinHerramienta, TENANT, CASO, "x") is False,
        "un tenant sin la herramienta no avisa nada (y no falla)")

# =============================================================================
titulo("5. En el catalogo del tenant, y fuera del alcance del modelo")
# =============================================================================
crudo = yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))
con_bandera = [h for h in crudo.get("herramientas", []) if h.get("sella_primera_respuesta")]
revisar(len(con_bandera) == 1, "el tenant declara una sola herramienta que sella",
        f"{[h.get('nombre') for h in con_bandera]}")
nombre = con_bandera[0]["nombre"] if con_bandera else ""
roles = crudo.get("roles", {})
roles = list(roles.values() if isinstance(roles, dict) else roles)
visibles = [r.get("nombre", "?") for r in roles if nombre in (r.get("puede_consultar") or [])]
#  Control de la lectura: si 'roles' se leyera mal, "nadie la ve" saldria
#  verde siempre. Una herramienta que el modelo SI usa tiene que aparecer.
revisar(any("consultar_ticket" in (r.get("puede_consultar") or []) for r in roles),
        "control: la misma lectura SI encuentra una herramienta que el modelo usa")
revisar(nombre and visibles == [],
        "ningun rol la tiene en 'puede_consultar': el modelo no la puede llamar", f"{visibles}")

print(f"\n{'=' * 76}\n  {'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}\n{'=' * 76}")
sys.exit(1 if fallos else 0)
