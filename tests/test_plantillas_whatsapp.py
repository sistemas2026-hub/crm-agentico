# -*- coding: utf-8 -*-
"""
================================================================================
 WHATSAPP DESDE DEXTER: SALUD DEL NUMERO Y PLANTILLAS  --  28/10/2026
================================================================================
    py -3.13 tests/test_plantillas_whatsapp.py                    (sin base)

Lo que se afirma, sobre el EFECTO (no llama a Meta: se dobla 'requests'):

  1. la salud del numero: se le piden a Meta los campos medidos, sale solo el
     final del numero, lo que Meta no manda queda en None y un rechazo de
     Meta se levanta con su codigo -- nunca un estado inventado;
     la ruta del motor lo devuelve tal cual, o 502 con un mensaje publico.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import whatsapp                       # noqa: E402
from nucleo.config.schema import CanalWhatsApp            # noqa: E402

TENANT = "tenant-de-prueba"
fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


class Config:
    """Lo minimo que miran las funciones del canal, armado a mano: la prueba
    no depende de si una empresa tiene el canal activo hoy."""

    def __init__(self, **kw):
        opciones = dict(activo=True, phone_number_id_ref="WA_TEL", token_ref="WA_TOKEN",
                        waba_id_ref="WA_WABA", app_secret_ref="WA_APP",
                        verify_token_ref="WA_VERIFY")
        opciones.update(kw)
        self.canales = type("C", (), {"whatsapp": CanalWhatsApp(**opciones)})()


SECRETOS = {"WA_TEL": "1112223334", "WA_TOKEN": "tok-secreto", "WA_WABA": "999888777"}


class Respuesta:
    def __init__(self, status, cuerpo):
        self.status_code, self._c = status, cuerpo
        self.ok = status < 400
        self.text = str(cuerpo)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._c


class Red:
    """Dobla 'requests' dentro de whatsapp.py y anota cada pedido."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.pedidos: list[dict] = []

    def _anotar(self, metodo, url, kw):
        self.pedidos.append({"metodo": metodo, "url": url, **kw})
        return self.respuestas.pop(0)

    def get(self, url, **kw):
        return self._anotar("GET", url, kw)

    def post(self, url, **kw):
        return self._anotar("POST", url, kw)

    def delete(self, url, **kw):
        return self._anotar("DELETE", url, kw)


def con_red(red, hacer):
    originales = (whatsapp.requests.get, whatsapp.requests.post,
                  getattr(whatsapp.requests, "delete"), whatsapp.secretos.obtener)
    whatsapp.requests.get, whatsapp.requests.post = red.get, red.post
    whatsapp.requests.delete = red.delete
    whatsapp.secretos.obtener = lambda t, ref: SECRETOS.get(ref)
    try:
        return hacer()
    finally:
        (whatsapp.requests.get, whatsapp.requests.post,
         whatsapp.requests.delete, whatsapp.secretos.obtener) = originales


def levanta(hacer):
    try:
        hacer()
        return None
    except whatsapp.ErrorWhatsApp as e:
        return e


# =============================================================================
titulo("1. La salud del numero")
# =============================================================================
META = {"display_phone_number": "+57 300 123 3423", "verified_name": "Empresa",
        "quality_rating": "YELLOW", "status": "CONNECTED", "name_status": "APPROVED",
        "platform_type": "CLOUD_API", "throughput": {"level": "STANDARD"},
        "account_mode": "LIVE", "is_official_business_account": False,
        "id": "1112223334"}
red = Red([Respuesta(200, META)])
s = con_red(red, lambda: whatsapp.salud_del_numero(Config(), TENANT))
p = red.pedidos[0]
revisar(p["url"].endswith("/v23.0/1112223334") and p["params"]["fields"] == whatsapp.CAMPOS_SALUD,
        "pide el numero emisor, con los campos medidos", f"{p['url']} {p['params']}")
revisar(p["headers"]["Authorization"] == "Bearer tok-secreto",
        "con la credencial de envio de la empresa")
revisar(s == {"numero_final": "3423", "nombre_visible": "Empresa", "estado_nombre": "APPROVED",
              "calidad": "YELLOW", "estado": "CONNECTED", "modo": "LIVE",
              "plataforma": "CLOUD_API", "nivel_envio": "STANDARD", "limite_diario": None,
              "cuenta_oficial": False},
        "traduce la respuesta; el limite que Meta no manda queda en None, no inventado", f"{s}")
revisar("id" not in s and "3001" not in str(s),
        "no sale el id del numero ni el numero entero", f"{s}")

red = Red([Respuesta(200, {})])
s = con_red(red, lambda: whatsapp.salud_del_numero(Config(), TENANT))
revisar(s["calidad"] is None and s["numero_final"] is None and s["nivel_envio"] is None,
        "con una respuesta vacia, todo en None -- ningun 'verde' por defecto", f"{s}")

red = Red([Respuesta(401, {"error": {"code": 190, "message": "token vencido"}})])
e = con_red(red, lambda: levanta(lambda: whatsapp.salud_del_numero(Config(), TENANT)))
revisar(e is not None and e.codigo == 190, "si Meta rechaza, se levanta con su codigo",
        f"{e!r}")

e = levanta(lambda: whatsapp.salud_del_numero(Config(activo=False), TENANT))
revisar(e is not None, "con el canal apagado no se consulta nada")

#  La ruta del motor.
from nucleo.canales import api                            # noqa: E402

api.app.config["TESTING"] = True
cliente = api.app.test_client()
originales = [(api, "_config_de", api._config_de),
              (api.whatsapp, "salud_del_numero", api.whatsapp.salud_del_numero)]
api._config_de = lambda t: Config()
try:
    api.whatsapp.salud_del_numero = lambda c, t: {"calidad": "GREEN", "numero_final": "3423"}
    r = cliente.get(f"/canales/whatsapp/salud?tenant={TENANT}")
    revisar(r.status_code == 200 and r.get_json() == {"calidad": "GREEN", "numero_final": "3423"},
            "la ruta devuelve lo que leyo", f"{r.status_code} {r.get_json()}")

    #  Un rechazo REAL de Meta, cuyo mensaje trae el numero: por la funcion de
    #  verdad, con la red doblada. Lo que dijo Meta no puede salir de la ruta.
    api.whatsapp.salud_del_numero = originales[1][2]
    red = Red([Respuesta(401, {"error": {"code": 190,
                                          "message": "Token de 1112223334 vencido"}})])
    r = con_red(red, lambda: cliente.get(f"/canales/whatsapp/salud?tenant={TENANT}"))
    texto = r.get_data(as_text=True)
    revisar(r.status_code == 502 and "1112223334" not in texto and "vencido" not in texto
            and "190" in texto,
            "si Meta rechaza: 502 con el codigo, sin lo que dijo Meta", f"{r.status_code} {texto}")
    r = cliente.get("/canales/whatsapp/salud")
    revisar(r.status_code == 400, "sin tenant: 400", f"{r.status_code}")
finally:
    for obj, nombre, original in originales:
        setattr(obj, nombre, original)


# =============================================================================
titulo("2. Plantilla desde el ticket (la ventana de 24 h cerrada)")
# =============================================================================
#  Se dobla lo que toca la base y a Meta; la ruta, la resolucion del caso y el
#  armado del texto son los de verdad.
PLANTILLA = {"nombre": "seguimiento_caso", "estado": "APPROVED", "idioma": "es",
             "variables": 1, "variables_encabezado": [], "variables_cuerpo": ["1"],
             "encabezado": "", "cuerpo": "Hola, sobre tu caso: {{1}}",
             "formato_variables": "posicional"}
AUTOR = {"autor": "Ana Operadora", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}


class Motor:
    def __init__(self, *, resultado="aceptado", caso=True, ticket_en_chat="T-9"):
        self.resultado, self.caso, self.ticket_en_chat = resultado, caso, ticket_en_chat
        self.copias: list = []
        self.avisos: list = []
        self.guardados: list = []


def montar(m: Motor):
    p = [(api, "_config_de", api._config_de),
         (api, "_exigir_control_humano", api._exigir_control_humano),
         (api, "_entregar_y_registrar", api._entregar_y_registrar),
         (api, "_avisar_primera_respuesta", api._avisar_primera_respuesta),
         (api.whatsapp, "plantillas_aprobadas", api.whatsapp.plantillas_aprobadas),
         (api.persistencia, "conversacion_de_caso", api.persistencia.conversacion_de_caso),
         (api.persistencia, "control_efectivo_de", api.persistencia.control_efectivo_de),
         (api.persistencia, "agregar_mensaje_humano", api.persistencia.agregar_mensaje_humano),
         (api.operativo, "responder", api.operativo.responder)]
    api._config_de = lambda t: Config()
    api._exigir_control_humano = lambda t, c: None
    api._entregar_y_registrar = lambda *a, **k: {"resultado": m.resultado,
                                                 "aceptado_por_meta": m.resultado == "aceptado",
                                                 "aceptacion_registrada": True}
    api._avisar_primera_respuesta = lambda t, conv, caso, autor: m.avisos.append((conv, caso)) or True
    api.whatsapp.plantillas_aprobadas = lambda c, t: [PLANTILLA]
    api.persistencia.conversacion_de_caso = lambda t, c: {"id": "conv-1"} if m.caso else None
    api.persistencia.control_efectivo_de = lambda t, c: "humano"

    def guardar(t, conv, texto, autor, **kw):
        m.guardados.append((conv, texto))
        return {"mensaje_id": "m-1", "usuario_externo": "573001112233",
                "ticket_operativo": m.ticket_en_chat, "existente": False}
    api.persistencia.agregar_mensaje_humano = guardar
    api.operativo.responder = lambda c, t, ticket, texto, autor: m.copias.append((ticket, texto)) or True
    return p


def correr(m: Motor, url, cuerpo):
    p = montar(m)
    try:
        return cliente.post(url, json=cuerpo)
    finally:
        for obj, nombre, original in reversed(p):
            setattr(obj, nombre, original)


CUERPO = {"tenant": TENANT, "plantilla": "seguimiento_caso",
          "variables": ["ya revisamos el equipo"], **AUTOR}

m = Motor()
r = correr(m, "/casos/caso-1/plantilla", CUERPO)
revisar(r.status_code == 201 and m.guardados == [("conv-1", "Hola, sobre tu caso: ya revisamos el equipo")],
        "desde el ticket: va a la conversacion del caso, con el texto armado", f"{r.status_code} {m.guardados}")
revisar(m.copias == [("T-9", "Hola, sobre tu caso: ya revisamos el equipo")],
        "la copia va al ticket del ISP, como una respuesta de texto", f"{m.copias}")
revisar(m.avisos == [("conv-1", "caso-1")] and r.get_json().get("primera_respuesta_avisada") is True,
        "si Meta la acepto, es la primera respuesta de ESTE caso", f"{m.avisos}")

m = Motor(resultado="rechazado")
r = correr(m, "/casos/caso-1/plantilla", CUERPO)
revisar(r.status_code == 201 and m.avisos == [] and r.get_json()["resultado"] == "rechazado",
        "si no salio, NO cuenta como primera respuesta, y se dice", f"{m.avisos} {r.get_json()}")

m = Motor(caso=False)
r = correr(m, "/casos/caso-1/plantilla", CUERPO)
revisar(r.status_code == 404 and r.get_json().get("sin_conversacion") is True and not m.guardados,
        "un ticket sin chat: 404 'sin_conversacion', y no se guarda nada", f"{r.status_code}")

m = Motor()
r = correr(m, "/casos/caso-1/plantilla", {**CUERPO, "variables": []})
revisar(r.status_code == 400 and not m.guardados and not m.copias,
        "con variables de menos no se guarda ni se copia nada", f"{r.status_code}")

m = Motor()
r = correr(m, "/casos/caso-1/plantilla", {k: v for k, v in CUERPO.items() if k not in AUTOR})
revisar(r.status_code == 400 and not m.guardados, "sin autor no sale nada (D2)", f"{r.status_code}")

#  La Bandeja, por la conversacion: tambien copia y tambien cuenta.
m = Motor()
r = correr(m, "/conversaciones/conv-1/plantilla", CUERPO)
revisar(r.status_code == 201 and m.copias and m.avisos == [("conv-1", None)],
        "desde la Bandeja: copia al ticket del chat, y la primera respuesta sale de la conversacion",
        f"{m.copias} {m.avisos}")
m = Motor(ticket_en_chat=None)
r = correr(m, "/conversaciones/conv-1/plantilla", CUERPO)
revisar(r.status_code == 201 and m.copias == [], "un chat sin ticket no copia a ningun lado",
        f"{m.copias}")

#  La respuesta de TEXTO por caso comparte la resolucion (_destino_del_caso):
#  tiene que seguir yendo al mismo chat, con el mismo caso.
llamadas: list = []
orig = [(api, "conversaciones_responder_humano", api.conversaciones_responder_humano),
        (api.persistencia, "conversacion_de_caso", api.persistencia.conversacion_de_caso),
        (api.persistencia, "control_efectivo_de", api.persistencia.control_efectivo_de),
        (api.persistencia, "datos_del_chat", api.persistencia.datos_del_chat)]
try:
    api.conversaciones_responder_humano = (
        lambda conv, ticket_del_caso=None, caso_del_caso=None:
        llamadas.append((conv, ticket_del_caso, caso_del_caso)) or ({"ok": True}, 201))
    api.persistencia.conversacion_de_caso = lambda t, c: {"id": "conv-vieja"}
    api.persistencia.control_efectivo_de = lambda t, c: "cerrada"
    api.persistencia.datos_del_chat = lambda t, c: {"abierta_id": "conv-nueva",
                                                     "ticket_operativo": "T-7"}
    r = cliente.post("/casos/caso-1/mensajes", json={"tenant": TENANT, "mensaje": "hola", **AUTOR})
    revisar(r.status_code == 201 and llamadas == [("conv-nueva", "T-7", "caso-1")],
            "texto por caso: con la del caso cerrada va a la abierta del chat, con su ticket",
            f"{r.status_code} {llamadas}")
    api.persistencia.conversacion_de_caso = lambda t, c: None
    r = cliente.post("/casos/caso-1/mensajes", json={"tenant": TENANT, "mensaje": "hola", **AUTOR})
    revisar(r.status_code == 404 and r.get_json().get("sin_conversacion") is True,
            "texto por caso sin chat: el mismo 404 de siempre", f"{r.status_code}")
finally:
    for obj, nombre, original in orig:
        setattr(obj, nombre, original)


print(f"\n{'=' * 76}\n  {'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}\n{'=' * 76}")
sys.exit(1 if fallos else 0)
