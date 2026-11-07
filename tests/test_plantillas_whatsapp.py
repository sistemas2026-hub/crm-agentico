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
from datetime import datetime, timezone
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
        # Lo que el esquema real siempre trae: sin esto el doble no sigue al
        # original y cualquier campo nuevo da un falso rojo.
        self.mensajes_automaticos = {}
        self.respaldos_mensajes = {}
        self.plantillas_desactivadas = []


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


# =============================================================================
titulo("3. Crear y borrar plantillas desde Dexter")
# =============================================================================
BIEN = {"nombre": "seguimiento_caso", "categoria": "utility", "idioma": "es",
        "cuerpo": "Hola {{1}}, sobre tu caso: {{2}}. Gracias.", "ejemplos": ["Juan", "listo"],
        "pie": "Equipo de soporte", "botones": ["Bien", "Mal"]}
pedido = whatsapp.armar_plantilla_nueva(BIEN)
revisar(pedido == {"name": "seguimiento_caso", "language": "es", "category": "UTILITY",
                   "components": [
                       {"type": "BODY", "text": "Hola {{1}}, sobre tu caso: {{2}}. Gracias.",
                        "example": {"body_text": [["Juan", "listo"]]}},
                       {"type": "FOOTER", "text": "Equipo de soporte"},
                       {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Bien"},
                                                       {"type": "QUICK_REPLY", "text": "Mal"}]}]},
        "arma el pedido de Meta: cuerpo con ejemplos, pie y botones de respuesta", f"{pedido}")


def invalida(**cambio):
    try:
        whatsapp.armar_plantilla_nueva({**BIEN, **cambio})
        return None
    except whatsapp.PlantillaInvalida as e:
        return str(e)


for cambio, que in (
        ({"nombre": "Seguimiento Caso"}, "nombre con mayusculas o espacios (lo medido: 2388046)"),
        ({"categoria": "AUTHENTICATION"}, "categoria que Dexter no arma"),
        ({"cuerpo": ""}, "sin texto"),
        ({"cuerpo": "x" * 1025, "ejemplos": []}, "texto de mas de 1024"),
        ({"cuerpo": "Hola {{1}} y {{3}}.", "ejemplos": ["a", "b"]}, "variables con salto ({{1}}, {{3}})"),
        ({"cuerpo": "Hola {{2}} y {{1}}.", "ejemplos": ["a", "b"]}, "variables fuera de orden"),
        ({"cuerpo": "Hola {{nombre}}.", "ejemplos": ["a"]}, "variables con nombre"),
        ({"cuerpo": "{{1}} te escribimos.", "ejemplos": ["a"]}, "empieza con una variable"),
        ({"cuerpo": "Te escribimos {{1}}", "ejemplos": ["a"]}, "termina con una variable"),
        ({"ejemplos": ["Juan"]}, "una variable sin ejemplo"),
        ({"pie": "Hola {{1}}"}, "variable en el pie"),
        ({"botones": ["Muy bien"] * 2}, "dos botones iguales"),
        ({"botones": ["x" * 26]}, "boton de mas de 25"),
        ({"botones": [str(i) for i in range(11)]}, "mas de 10 botones")):
    motivo = invalida(**cambio)
    revisar(bool(motivo), f"rechaza ANTES de llamar a Meta: {que}", f"{motivo}")

red = Red([Respuesta(200, {"id": "tpl-1", "status": "PENDING", "category": "MARKETING"})])
c = con_red(red, lambda: whatsapp.crear_plantilla(Config(), TENANT, BIEN))
p = red.pedidos[0]
revisar(p["metodo"] == "POST" and p["url"].endswith("/999888777/message_templates")
        and p["json"] == pedido,
        "la manda a revision a la cuenta (waba) de la empresa", f"{p['url']}")
revisar(c == {"nombre": "seguimiento_caso", "estado": "PENDING", "categoria": "MARKETING"},
        "devuelve el estado y la categoria QUE DIJO META (la puede cambiar)", f"{c}")

red = Red([])
try:
    con_red(red, lambda: whatsapp.crear_plantilla(Config(), TENANT, {**BIEN, "nombre": "Mal Nombre"}))
except whatsapp.PlantillaInvalida:
    pass
revisar(not red.pedidos, "una invalida no sale a Meta", f"{red.pedidos}")

red = Red([Respuesta(400, {"error": {"code": 100, "error_subcode": 2388046,
                                     "message": "texto de Meta"}})])
e = con_red(red, lambda: levanta(lambda: whatsapp.crear_plantilla(Config(), TENANT, BIEN)))
revisar(e is not None and "minúsculas" in str(e) and "texto de Meta" not in str(e),
        "un subcodigo ya medido se dice en palabras de Dexter, no las de Meta", f"{e}")
red = Red([Respuesta(400, {"error": {"code": 100, "error_subcode": 99, "message": "texto de Meta"}})])
e = con_red(red, lambda: levanta(lambda: whatsapp.crear_plantilla(Config(), TENANT, BIEN)))
revisar(e is not None and "100" in str(e) and "texto de Meta" not in str(e),
        "uno desconocido: solo el codigo", f"{e}")

red = Red([Respuesta(200, {"success": True})])
con_red(red, lambda: whatsapp.borrar_plantilla(Config(), TENANT, "seguimiento_caso"))
p = red.pedidos[0]
revisar(p["metodo"] == "DELETE" and p["url"].endswith("/999888777/message_templates")
        and p["params"] == {"name": "seguimiento_caso"},
        "el borrado va por nombre a la cuenta de la empresa", f"{p}")
red = Red([])
try:
    con_red(red, lambda: whatsapp.borrar_plantilla(Config(), TENANT, "../otra cuenta"))
    raro = True
except whatsapp.PlantillaInvalida:
    raro = False
revisar(not raro and not red.pedidos, "un nombre raro no se manda a borrar", f"{red.pedidos}")

#  Las rutas.
registros: list = []
orig = [(api, "_config_de", api._config_de), (api, "registrar", api.registrar),
        (api.whatsapp, "plantillas_aprobadas", api.whatsapp.plantillas_aprobadas)]
api._config_de = lambda t: Config()
api.registrar = lambda comp, ev, **k: registros.append((comp, ev, k))
api.whatsapp.plantillas_aprobadas = lambda c, t: [{"nombre": "bienvenida", "estado": "APPROVED"},
                                                  {"nombre": "nueva", "estado": "PENDING"}]
try:
    r = cliente.get(f"/canales/plantillas/todas?tenant={TENANT}")
    revisar(r.status_code == 200 and [p["estado"] for p in r.get_json()["plantillas"]] == ["APPROVED", "PENDING"],
            "Ajustes ve TODAS, en cualquier estado", f"{r.get_json()}")
    r = cliente.get(f"/canales/plantillas?tenant={TENANT}")
    revisar([p["nombre"] for p in r.get_json()["plantillas"]] == ["bienvenida"],
            "y al cliente se le sigue ofreciendo solo las aprobadas", f"{r.get_json()}")

    red = Red([Respuesta(200, {"id": "t", "status": "PENDING", "category": "UTILITY"})])
    r = con_red(red, lambda: cliente.post("/canales/plantillas",
                                          json={"tenant": TENANT, "plantilla": BIEN, **AUTOR}))
    revisar(r.status_code == 201 and r.get_json()["estado"] == "PENDING"
            and any(ev == "plantilla mandada a revision" for _, ev, _ in registros),
            "crear: 201 con el estado de Meta, y queda en el log", f"{r.status_code} {r.get_json()}")
    revisar(all("Ana" not in str(k) for _, _, k in registros),
            "el log no lleva el nombre de quien la creo", f"{registros}")
    red = Red([])
    r = con_red(red, lambda: cliente.post("/canales/plantillas",
                                          json={"tenant": TENANT, "plantilla": {**BIEN, "cuerpo": ""}, **AUTOR}))
    revisar(r.status_code == 400 and r.get_json()["codigo"] == "plantilla_invalida" and not red.pedidos,
            "invalida: 400 con el motivo, sin salir a Meta", f"{r.status_code} {r.get_json()}")
    r = con_red(Red([]), lambda: cliente.post("/canales/plantillas", json={"tenant": TENANT, "plantilla": BIEN}))
    revisar(r.status_code == 400, "crear sin autor: 400", f"{r.status_code}")

    red = Red([Respuesta(200, {"success": True})])
    r = con_red(red, lambda: cliente.delete("/canales/plantillas/seguimiento_caso",
                                            json={"tenant": TENANT, **AUTOR}))
    revisar(r.status_code == 200 and red.pedidos and red.pedidos[0]["metodo"] == "DELETE",
            "borrar: 200 y sale el DELETE", f"{r.status_code}")
    r = con_red(Red([]), lambda: cliente.delete("/canales/plantillas/seguimiento_caso",
                                                json={"tenant": TENANT}))
    revisar(r.status_code == 400, "borrar sin autor: 400", f"{r.status_code}")
finally:
    for obj, nombre, original in orig:
        setattr(obj, nombre, original)


# =============================================================================
titulo("4. La encuesta: el boton tocado, el envio y el webhook")
# =============================================================================
from nucleo.seguimiento import encuesta as enc            # noqa: E402
from nucleo.config.schema import EncuestaWhatsApp, MensajeAutomatico  # noqa: E402


def sobre(mensaje):
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "573001112233", "profile": {"name": "Juana"}}],
        "messages": [mensaje]}}]}]}


m = whatsapp.mensajes_entrantes(sobre({"id": "wamid.R", "type": "button",
                                       "context": {"id": "wamid.ENC"},
                                       "button": {"text": "Excelente", "payload": "Excelente"}}))[0]
revisar(m["texto"] == "Excelente" and m["contexto"] == "wamid.ENC" and m["tipo"] == "button",
        "un boton de plantilla llega como TEXTO, con el mensaje al que responde", f"{m}")
m = whatsapp.mensajes_entrantes(sobre({"id": "wamid.I", "type": "interactive",
                                       "interactive": {"type": "button_reply",
                                                       "button_reply": {"id": "b1", "title": "Buena"}}}))[0]
revisar(m["texto"] == "Buena" and m["contexto"] is None, "un boton interactivo tambien", f"{m}")
m = whatsapp.mensajes_entrantes(sobre({"id": "wamid.T", "type": "text", "text": {"body": "hola"}}))[0]
revisar(m["texto"] == "hola" and m["contexto"] is None, "el texto de siempre no cambia", f"{m}")

CFG = EncuestaWhatsApp()
revisar(enc.puntaje_de(CFG, "Excelente") == 5 and enc.puntaje_de(CFG, " mala ") == 1
        and enc.puntaje_de(CFG, "Otra") is None,
        "el puntaje sale de la config: exacto o sin mayusculas; uno desconocido, None")


class Encuestador:
    """Dobla la base y a Meta alrededor de seguimiento/encuesta.py."""

    def __init__(self, *, destino=True, baja=False, aprobada=True, ya=False, meta="ok",
                 variables=1, canal="whatsapp"):
        self.destino = ({"id": "conv-1", "canal": canal, "usuario_externo": "573001112233",
                         "nombre_cliente": "Juana Perez"} if destino else None)
        self.baja, self.aprobada, self.ya, self.meta = baja, aprobada, ya, meta
        self.variables = variables
        self.reservas: list = []
        self.envios: list = []
        self.marcas: list = []

    def montar(self):
        p = [(enc.encuestas, n, getattr(enc.encuestas, n)) for n in
             ("destino_del_caso", "reservar", "marcar_enviada", "marcar_fallida")]
        p += [(enc.persistencia, "esta_de_baja", enc.persistencia.esta_de_baja),
              (enc.whatsapp, "plantillas_aprobadas", enc.whatsapp.plantillas_aprobadas),
              (enc.whatsapp, "enviar_plantilla_aprobada", enc.whatsapp.enviar_plantilla_aprobada),
              (enc.whatsapp, "activo", enc.whatsapp.activo)]
        enc.encuestas.destino_del_caso = lambda t, c: self.destino
        enc.encuestas.reservar = lambda t, c, conv, pl, vig, **kw: (
            self.reservas.append((c, conv, pl, vig, kw)) or (None if self.ya else "enc-1"))
        enc.encuestas.marcar_enviada = lambda t, i, w: self.marcas.append(("enviada", i, w))
        enc.encuestas.marcar_fallida = lambda t, i: self.marcas.append(("fallida", i))
        enc.persistencia.esta_de_baja = lambda t, n, c: self.baja
        enc.whatsapp.activo = lambda c: True
        enc.whatsapp.plantillas_aprobadas = lambda c, t: (
            [{"nombre": "encuesta_satisfaccion", "estado": "APPROVED", "idioma": "es",
              "variables": self.variables, "formato_variables": "posicional"}] if self.aprobada else [])

        def mandar(c, t, numero, nombre, valores, idioma, plantilla=None):
            self.envios.append((numero, nombre, valores))
            if self.meta == "rechaza":
                raise whatsapp.ErrorWhatsApp("WhatsApp rechazo", codigo=131026)
            if self.meta == "corta":
                raise TimeoutError("sin respuesta")
            return "wamid.ENC"
        enc.whatsapp.enviar_plantilla_aprobada = mandar
        return p

    def correr(self, config, **kw):
        p = self.montar()
        try:
            return enc.enviar(config, TENANT, "caso-1", responsable_id="p-1",
                              responsable_nombre="Ana", area="soporte_tecnico", **kw)
        finally:
            for obj, nombre, original in reversed(p):
                setattr(obj, nombre, original)


class Identidad:
    nombre_comercial, nombre_legal, zona_horaria = "Empresa", "Empresa SAS", "America/Bogota"


class ConfigEnc(Config):
    """La encuesta es un mensaje automatico mas: su plantilla, datos y si esta
    encendida van en mensajes_automaticos['encuesta_cierre'] (28/10/2026)."""

    def __init__(self, activo=True, datos=("cliente_nombre",), respaldos=None, **kw):
        super().__init__()
        self.identidad = Identidad()
        self.encuesta_whatsapp = EncuestaWhatsApp(**kw)
        self.mensajes_automaticos = {"encuesta_cierre": MensajeAutomatico(
            activo=activo, plantilla="encuesta_satisfaccion", datos=list(datos))}
        self.respaldos_mensajes = dict(respaldos or {})


e = Encuestador()
r = e.correr(ConfigEnc())
revisar(r == {"enviada": True, "motivo": None} and e.envios == [("573001112233", "encuesta_satisfaccion", ["Juana"])]
        and e.marcas == [("enviada", "enc-1", "wamid.ENC")],
        "sale al numero del chat, con el PRIMER nombre del cliente, y queda el wamid", f"{r} {e.envios} {e.marcas}")
revisar(e.reservas and e.reservas[0][4] == {"responsable_id": "p-1", "responsable_nombre": "Ana",
                                            "area": "soporte_tecnico"},
        "la reserva lleva al responsable y el area que mando el CRM", f"{e.reservas}")

for armado, cfg, motivo, que in (
        (dict(), ConfigEnc(activo=False), "apagada", "apagada en la config: no sale"),
        (dict(destino=False), ConfigEnc(), "sin_chat", "un caso sin chat: no sale"),
        (dict(canal="web"), ConfigEnc(), "sin_chat", "un chat que no es WhatsApp: no sale"),
        (dict(baja=True), ConfigEnc(), "de_baja", "el numero pidio no recibir avisos: no sale"),
        (dict(aprobada=False), ConfigEnc(), "plantilla_no_aprobada", "la plantilla sin aprobar: no sale"),
        (dict(variables=2), ConfigEnc(), "plantilla_no_coincide", "la plantilla pide otros valores: no sale"),
        (dict(ya=True), ConfigEnc(), "ya_enviada", "el caso ya tenia encuesta: no sale otra")):
    e = Encuestador(**armado)
    r = e.correr(cfg)
    revisar(r == {"enviada": False, "motivo": motivo} and not e.envios, que, f"{r} {e.envios}")

e2 = Encuestador()
e2.destino = {**e2.destino, "nombre_cliente": None} if e2.destino else None
e2.correr(ConfigEnc(respaldos={"cliente_nombre": "vecino"}))
revisar(e2.envios and e2.envios[0][2] == ["vecino"], "sin nombre en el perfil, el respaldo de la empresa",
        f"{e2.envios}")
e3 = Encuestador(variables=2)
r = e3.correr(ConfigEnc(datos=("cliente_nombre", "responsable")))
revisar(r["enviada"] and e3.envios[0][2] == ["Juana", "Ana"],
        "los datos de la plantilla salen del armado de la empresa, en orden", f"{r} {e3.envios}")

e = Encuestador(meta="rechaza")
r = e.correr(ConfigEnc())
revisar(r == {"enviada": False, "motivo": "rechazada"} and e.marcas == [("fallida", "enc-1")],
        "Meta la rechaza: queda fallida", f"{r} {e.marcas}")
e = Encuestador(meta="corta")
r = e.correr(ConfigEnc())
revisar(r == {"enviada": False, "motivo": "incierto"} and e.marcas == [],
        "sin respuesta de Meta: incierta, ni enviada ni fallida (no se reintenta)", f"{r} {e.marcas}")

#  responder_boton: lo que decide si un toque es una encuesta.
llamadas_r: list = []
orig_r = enc.encuestas.responder
try:
    enc.encuestas.responder = lambda t, w, o, p: (llamadas_r.append((w, o, p)) or
                                                  ({"encuesta": w == "wamid.ENC", "registrada": w == "wamid.ENC",
                                                    "motivo": None, "caso_id": "caso-1"}))
    cfg = ConfigEnc()
    r = enc.responder_boton(cfg, TENANT, {"tipo": "button", "texto": "Buena", "contexto": "wamid.ENC"})
    revisar(r and r["registrada"] and llamadas_r[-1] == ("wamid.ENC", "Buena", 4),
            "un toque a una encuesta: se registra con su puntaje", f"{r} {llamadas_r}")
    r = enc.responder_boton(cfg, TENANT, {"tipo": "button", "texto": "Si", "contexto": "wamid.OTRA"})
    revisar(r is None, "un toque a otra plantilla: None (sigue al turno)")
    n = len(llamadas_r)
    r = enc.responder_boton(cfg, TENANT, {"tipo": "text", "texto": "Excelente", "contexto": "wamid.ENC"})
    revisar(r is None and len(llamadas_r) == n, "un TEXTO que dice 'Excelente' no es un toque: ni se consulta")
    r = enc.responder_boton(ConfigEnc(activo=False), TENANT,
                            {"tipo": "button", "texto": "Mala", "contexto": "wamid.ENC"})
    revisar(r and r["registrada"], "con la encuesta apagada despues, las ya enviadas se siguen contando")
finally:
    enc.encuestas.responder = orig_r

#  El webhook: el toque a una encuesta NO llega al modelo.
turnos: list = []
textos: list = []
orig_w = [(api, "atender_turno", api.atender_turno),
          (api.whatsapp, "enviar_texto", api.whatsapp.enviar_texto),
          (api.whatsapp, "marcar_leido", api.whatsapp.marcar_leido),
          (api.encuesta, "responder_boton", api.encuesta.responder_boton),
          (api, "_atendio_baja_o_alta", api._atendio_baja_o_alta),
          (api, "_guardar_adjunto", api._guardar_adjunto),
          (api, "_transcribir_si_es_voz", api._transcribir_si_es_voz),
          (api, "_analizar_si_es_imagen", api._analizar_si_es_imagen),
          (api.consumo, "estado_del_gasto", api.consumo.estado_del_gasto)]
try:
    api.atender_turno = lambda config, tenant, rol, de, texto, canal, **kw: (
        turnos.append(texto) or {"respuesta": "", "conversacion_id": None})
    api.whatsapp.enviar_texto = lambda c, t, de, texto: textos.append(texto)
    api.whatsapp.marcar_leido = lambda c, t, w: None
    api._atendio_baja_o_alta = lambda c, t, de, texto: False
    api._guardar_adjunto = lambda *a, **k: None
    api._transcribir_si_es_voz = lambda *a, **k: {}
    api._analizar_si_es_imagen = lambda *a, **k: {}
    api.consumo.estado_del_gasto = lambda c, t: {"accion": "seguir"}
    cfgw = ConfigEnc(agradecimiento="Gracias, de verdad")
    entrada = {"de": "573001112233", "telefono": "573001112233", "wamid": "wamid.R",
               "tipo": "button", "texto": "Excelente", "contexto": "wamid.ENC"}

    api.encuesta.responder_boton = lambda c, t, e: {"encuesta": True, "registrada": True,
                                                    "motivo": None, "caso_id": "caso-1"}
    api._procesar_mensaje_whatsapp(cfgw, TENANT, "cliente_final", dict(entrada))
    revisar(turnos == [] and textos == ["Gracias, de verdad"],
            "el toque a una encuesta: se agradece y NO va al modelo", f"{turnos} {textos}")

    turnos.clear(); textos.clear()
    api.encuesta.responder_boton = lambda c, t, e: None
    api._procesar_mensaje_whatsapp(cfgw, TENANT, "cliente_final", dict(entrada))
    revisar(turnos == ["Excelente"] and "no puedo leer" not in " ".join(textos),
            "un boton que no es encuesta va al modelo como texto, no como 'archivo'", f"{turnos} {textos}")

    turnos.clear(); textos.clear()

    def rompe(c, t, e):
        raise RuntimeError("la base no contesta")
    api.encuesta.responder_boton = rompe
    api._procesar_mensaje_whatsapp(cfgw, TENANT, "cliente_final", dict(entrada))
    revisar(turnos == ["Excelente"], "si la base no contesta, el cliente igual recibe respuesta (va al turno)",
            f"{turnos}")
finally:
    for obj, nombre, original in orig_w:
        setattr(obj, nombre, original)

#  Las rutas.
orig_x = [(api, "_config_de", api._config_de), (api.encuesta, "enviar", api.encuesta.enviar),
          (api.encuestas_db, "filas", api.encuestas_db.filas)]
try:
    api._config_de = lambda t: ConfigEnc()
    pedidos_e: list = []
    api.encuesta.enviar = lambda c, t, caso, **kw: pedidos_e.append((caso, kw)) or {"enviada": True, "motivo": None}
    r = cliente.post("/casos/caso-1/encuesta", json={"tenant": TENANT, "responsable_id": "p-1",
                                                     "responsable_nombre": "Ana", "area": "soporte_tecnico",
                                                     "ticket_numero": "95001"})
    revisar(r.status_code == 200 and pedidos_e == [("caso-1", {"responsable_id": "p-1",
                                                               "responsable_nombre": "Ana",
                                                               "area": "soporte_tecnico",
                                                               "ticket_numero": "95001",
                                                               "cerrado_en": None})],
            "la ruta pasa el caso y el responsable", f"{r.status_code} {pedidos_e}")

    def cae(c, t, caso, **kw):
        raise RuntimeError("base caida")
    api.encuesta.enviar = cae
    r = cliente.post("/casos/caso-1/encuesta", json={"tenant": TENANT})
    revisar(r.status_code == 503, "si la base no contesta, 503: no sale nada (falla cerrado)", f"{r.status_code}")

    ahora = datetime.now(timezone.utc)
    api.encuestas_db.filas = lambda t, d, h: [
        {"caso_id": "c1", "estado": "respondida", "opcion": "Excelente", "puntaje": 5,
         "responsable_id": "p-1", "responsable_nombre": "Ana", "area": "soporte_tecnico",
         "enviada_en": ahora, "respondida_en": ahora},
        {"caso_id": "c2", "estado": "respondida", "opcion": "Mala", "puntaje": 1,
         "responsable_id": "p-2", "responsable_nombre": "Luis", "area": "soporte_tecnico",
         "enviada_en": ahora, "respondida_en": ahora},
        {"caso_id": "c3", "estado": "enviada", "opcion": None, "puntaje": None,
         "responsable_id": "p-1", "responsable_nombre": "Ana", "area": "cartera",
         "enviada_en": ahora, "respondida_en": None}]
    r = cliente.get(f"/encuestas/resumen?tenant={TENANT}")
    d = r.get_json()
    revisar(r.status_code == 200 and d["total"] == {"enviadas": 3, "respondidas": 2, "tasa_respuesta": 66.7,
                                                    "promedio": 3.0, "satisfaccion": 50.0},
            "el resumen: 3 enviadas, 2 respondidas, promedio 3, 50% satisfechos", f"{d.get('total')}")
    revisar([x["nombre"] for x in d["por_responsable"]] == ["Luis", "Ana"],
            "por responsable, de peor a mejor", f"{d['por_responsable']}")
    cart = next(x for x in d["por_area"] if x["clave"] == "cartera")
    revisar(cart["promedio"] is None and cart["satisfaccion"] is None and cart["enviadas"] == 1,
            "un area sin respuestas va con None, no con cero", f"{cart}")
    revisar(all(set(x) <= {"caso_id", "opcion", "puntaje", "responsable", "area", "respondida_en"}
                for x in d["recientes"]), "las recientes no traen datos del cliente", f"{d['recientes'][:1]}")
    for q, que in (("desde=2026-13-01", "fecha mal escrita"), ("desde=2026-10-10&hasta=2026-10-01", "desde despues de hasta"),
                   ("desde=2024-01-01&hasta=2026-01-01", "mas de un año")):
        r = cliente.get(f"/encuestas/resumen?tenant={TENANT}&{q}")
        revisar(r.status_code == 400, f"resumen con {que}: 400", f"{r.status_code}")
finally:
    for obj, nombre, original in orig_x:
        setattr(obj, nombre, original)


# =============================================================================
titulo("5. Mensajes automaticos: el armado comun de todos los avisos")
# =============================================================================
from nucleo.seguimiento import mensajes_automaticos as mens  # noqa: E402
from nucleo.config.schema import TenantConfig, cargar_config  # noqa: E402
from pydantic import ValidationError                        # noqa: E402


class ConfigMens(Config):
    def __init__(self, evento="ticket_creado_cliente", activo=True, datos=("cliente_nombre", "ticket_numero"),
                 respaldos=None):
        super().__init__()
        self.identidad = Identidad()
        self.mensajes_automaticos = {evento: MensajeAutomatico(activo=activo, plantilla="ticket_creado",
                                                               datos=list(datos))}
        self.respaldos_mensajes = dict(respaldos or {})


class Avisador:
    def __init__(self, *, baja=False, aprobada=True, variables=2, ya=False, meta="ok"):
        self.baja, self.aprobada, self.variables, self.ya, self.meta = baja, aprobada, variables, ya, meta
        self.envios: list = []
        self.marcas: list = []
        self.bajas_consultadas: list = []

    def correr(self, config, evento="ticket_creado_cliente", para="573001112233", contexto=None,
               clave="caso:c1"):
        p = [(mens.persistencia, "esta_de_baja", mens.persistencia.esta_de_baja),
             (mens.whatsapp, "plantillas_aprobadas", mens.whatsapp.plantillas_aprobadas),
             (mens.whatsapp, "enviar_plantilla_aprobada", mens.whatsapp.enviar_plantilla_aprobada),
             (mens.whatsapp, "activo", mens.whatsapp.activo),
             (mens.registro_envios, "reservar", mens.registro_envios.reservar),
             (mens.registro_envios, "marcar", mens.registro_envios.marcar)]
        mens.persistencia.esta_de_baja = lambda t, n, c: self.bajas_consultadas.append(n) or self.baja
        mens.whatsapp.activo = lambda c: True
        mens.whatsapp.plantillas_aprobadas = lambda c, t: (
            [{"nombre": "ticket_creado", "estado": "APPROVED", "idioma": "es",
              "variables": self.variables, "formato_variables": "posicional"}] if self.aprobada else [])

        def mandar(c, t, numero, nombre, valores, idioma, plantilla=None):
            self.envios.append((numero, valores))
            if self.meta == "rechaza":
                raise whatsapp.ErrorWhatsApp("x", codigo=131026)
            if self.meta == "corta":
                raise TimeoutError()
            return "wamid.A"
        mens.whatsapp.enviar_plantilla_aprobada = mandar
        mens.registro_envios.reservar = lambda t, ev, cl, pl: None if self.ya else "res-1"
        mens.registro_envios.marcar = lambda t, i, est, w=None: self.marcas.append((est, w))
        try:
            return mens.enviar(config, TENANT, evento, para,
                               contexto if contexto is not None else
                               {"cliente_nombre": "Juana", "ticket_numero": "95001"}, clave)
        finally:
            for obj, nombre, original in reversed(p):
                setattr(obj, nombre, original)


a = Avisador()
r = a.correr(ConfigMens())
revisar(r == {"enviado": True, "motivo": None} and a.envios == [("573001112233", ["Juana", "95001"])]
        and a.marcas == [("enviado", "wamid.A")],
        "sale con los datos en el orden que armo la empresa, y queda el wamid", f"{r} {a.envios} {a.marcas}")
for armado, cfg, kw, motivo, que in (
        (dict(), ConfigMens(activo=False), {}, "apagado", "apagado: no sale"),
        (dict(), ConfigMens(evento="bienvenida"), {}, "apagado", "un momento que la empresa no configuro: no sale"),
        (dict(), ConfigMens(), {"para": "  "}, "sin_numero", "sin numero: no sale"),
        (dict(baja=True), ConfigMens(), {}, "de_baja", "el cliente pidio no recibir avisos: no sale"),
        (dict(aprobada=False), ConfigMens(), {}, "plantilla_no_aprobada", "plantilla sin aprobar: no sale"),
        (dict(variables=3), ConfigMens(), {}, "plantilla_no_coincide", "la plantilla pide otra cantidad: no sale"),
        (dict(), ConfigMens(), {"contexto": {"ticket_numero": "95001"}}, None, None),
        (dict(), ConfigMens(datos=("ticket_asunto", "ticket_numero")), {"contexto": {"ticket_numero": "1"}},
         "dato_faltante:ticket_asunto", "un dato vacio sin respaldo: no sale a medias"),
        (dict(ya=True), ConfigMens(), {}, "ya_enviado", "el mismo motivo no lo dispara dos veces")):
    if que is None:
        continue
    a = Avisador(**armado)
    r = a.correr(cfg, **kw)
    revisar(r == {"enviado": False, "motivo": motivo} and not a.envios, que, f"{r} {a.envios}")

a = Avisador()
r = a.correr(ConfigMens(), contexto={"ticket_numero": "95001"})
revisar(r["enviado"] and a.envios[0][1] == ["cliente", "95001"],
        "un nombre vacio cae al respaldo ('cliente')", f"{a.envios}")
a = Avisador()
a.correr(ConfigMens(respaldos={"cliente_nombre": "vecino"}), contexto={"ticket_numero": "1"})
revisar(a.envios and a.envios[0][1][0] == "vecino", "la empresa cambia el respaldo", f"{a.envios}")
a = Avisador()
a.correr(ConfigMens(), contexto={"cliente_nombre": "Juana\n\tPerez   Gomez", "ticket_numero": "1"})
revisar(a.envios and a.envios[0][1][0] == "Juana Perez Gomez",
        "un valor con saltos o tabuladores se aplana (Meta lo rechaza)", f"{a.envios}")
a = Avisador()
a.correr(ConfigMens(datos=("empresa", "fecha")), contexto={})
revisar(a.envios and a.envios[0][1][0] == "Empresa" and len(a.envios[0][1][1]) == 10,
        "la empresa y la fecha salen solas", f"{a.envios}")
a = Avisador(baja=True)
r = a.correr(ConfigMens(evento="ticket_creado_tecnico", datos=("tecnico_nombre", "ticket_numero")),
             evento="ticket_creado_tecnico", contexto={"tecnico_nombre": "Luis", "ticket_numero": "1"})
revisar(r["enviado"] and not a.bajas_consultadas,
        "al tecnico no se le aplica la baja de avisos de clientes", f"{r} {a.bajas_consultadas}")
a = Avisador(meta="rechaza")
r = a.correr(ConfigMens())
revisar(r == {"enviado": False, "motivo": "rechazado"} and a.marcas == [("fallido", None)],
        "Meta lo rechaza: fallido", f"{r} {a.marcas}")
a = Avisador(meta="corta")
r = a.correr(ConfigMens())
revisar(r == {"enviado": False, "motivo": "incierto"} and a.marcas == [],
        "sin respuesta: queda reservado y no se reintenta", f"{r} {a.marcas}")

#  El esquema: lo que la config no acepta.
BASE_YAML = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml").model_dump()
for cambio, que in (
        ({"mensajes_automaticos": {"cumpleanos": {"activo": False}}}, "un momento que no existe"),
        ({"mensajes_automaticos": {"ticket_cerrado_cliente": {"datos": ["total"]}}},
         "un dato que ese momento no tiene (total al cerrar un ticket)"),
        ({"mensajes_automaticos": {"bienvenida": {"activo": True, "plantilla": ""}}}, "encendido sin plantilla"),
        ({"respaldos_mensajes": {"inventado": "x"}}, "un respaldo de un dato que no existe")):
    try:
        TenantConfig(**{**BASE_YAML, **cambio})
        rechazo = False
    except ValidationError:
        rechazo = True
    revisar(rechazo, f"la config rechaza {que}")

#  Las rutas de la pantalla.
from nucleo.config.mensajes_catalogo import EVENTOS  # noqa: E402

guardados: list = []
orig_m = [(api, "_config_de", api._config_de),
          (api.whatsapp, "plantillas_aprobadas", api.whatsapp.plantillas_aprobadas),
          (api.editor, "guardar_mensaje_automatico", api.editor.guardar_mensaje_automatico),
          (api, "olvidar_config", api.olvidar_config)]
try:
    cfg_real = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
    api._config_de = lambda t: cfg_real
    lecturas_meta: list = []
    api.whatsapp.plantillas_aprobadas = lambda c, t: lecturas_meta.append(1) or [
        {"nombre": "ticket_creado", "estado": "APPROVED", "variables": 2},
        {"nombre": "pausada", "estado": "PAUSED", "variables": 1}]

    solos: list = []

    def guardar(t, ev, activo, plantilla, datos, solo_a=None):
        guardados.append((ev, activo, plantilla, datos))
        solos.append(solo_a)
        return cfg_real.model_copy(update={"mensajes_automaticos": {
            ev: MensajeAutomatico(activo=activo, plantilla=plantilla, datos=datos,
                                  solo_a=solo_a or [])}})
    api.editor.guardar_mensaje_automatico = guardar
    api.olvidar_config = lambda t: None

    r = cliente.get(f"/mensajes-automaticos?tenant={TENANT}")
    d = r.get_json()
    revisar(r.status_code == 200 and [e["clave"] for e in d["eventos"]] == list(EVENTOS)
            and d["campos"]["cliente_nombre"]["etiqueta"] == "Nombre del cliente",
            "la pantalla recibe los 11 momentos del catalogo y los nombres de los datos", f"{r.status_code}")
    seg = next(e for e in d["eventos"] if e["clave"] == "seguimiento_ticket")
    revisar(seg["config"] == {"activo": True, "plantilla": "seguimiento_caso",
                              "datos": ["cliente_nombre", "escrito"], "solo_a": []},
            "con lo que la empresa ya configuro", f"{seg['config']}")
    revisar(seg["sugerencia"]["nombre"] == "seguimiento_caso"
            and seg["sugerencia"]["datos"] == ["cliente_nombre", "escrito"]
            and len(seg["sugerencia"]["ejemplos"]) == 2,
            "y su plantilla de partida, con el dato de cada lugar y un ejemplo", f"{seg.get('sugerencia')}")
    revisar(len(d["plantillas"]) == 2, "y TODAS sus plantillas, para avisar si una en uso se pauso")

    url = "/mensajes-automaticos/ticket_creado_cliente"
    r = cliente.put(url, json={"tenant": TENANT, "activo": True, "plantilla": "ticket_creado",
                               "datos": ["cliente_nombre"]})
    revisar(r.status_code == 400 and "pide 2" in r.get_json()["error"] and not guardados,
            "encender con menos datos de los que pide: 400, y no se guarda", f"{r.get_json()}")
    r = cliente.put(url, json={"tenant": TENANT, "activo": True, "plantilla": "pausada", "datos": ["empresa"]})
    revisar(r.status_code == 400 and not guardados, "encender con una plantilla no aprobada: 400")
    r = cliente.put(url, json={"tenant": TENANT, "activo": True, "plantilla": "ticket_creado",
                               "datos": ["cliente_nombre", "ticket_numero"]})
    revisar(r.status_code == 200 and guardados[-1] == ("ticket_creado_cliente", True, "ticket_creado",
                                                       ["cliente_nombre", "ticket_numero"]),
            "con la plantilla aprobada y los datos justos: se guarda", f"{r.status_code} {guardados}")
    n = len(lecturas_meta)
    r = cliente.put(url, json={"tenant": TENANT, "activo": False, "plantilla": "", "datos": []})
    revisar(r.status_code == 200 and len(lecturas_meta) == n,
            "apagado se guarda como borrador, sin consultar a Meta", f"{r.status_code}")
    r = cliente.put("/mensajes-automaticos/cumpleanos", json={"tenant": TENANT})
    revisar(r.status_code == 404, "un momento que no existe: 404")
    r = cliente.put(url, json={"tenant": TENANT, "activo": False, "plantilla": "", "datos": [],
                               "solo_a": ["573001112233"]})
    revisar(r.status_code == 200 and solos[-1] == ["573001112233"]
            and r.get_json()["solo_a"] == ["573001112233"],
            "los numeros de prueba viajan cuando el pedido los trae", f"{solos[-1]} {r.get_json()}")
    r = cliente.put(url, json={"tenant": TENANT, "activo": False, "plantilla": "", "datos": []})
    revisar(solos[-1] is None, "sin 'solo_a' en el pedido (el interruptor): se conservan, no se borran",
            f"{solos[-1]}")

    api.whatsapp.plantillas_aprobadas = lambda c, t: [
        {"nombre": "seguimiento_caso", "estado": "APPROVED", "variables": 2}]
    r = cliente.get(f"/canales/plantillas?tenant={TENANT}")
    d = r.get_json()
    revisar(d["armados"].get("seguimiento_caso") == {"evento": "seguimiento_ticket",
                                                     "datos": ["cliente_nombre", "escrito"]}
            and d["campos"]["cliente_nombre"] == "Nombre del cliente",
            "el ticket recibe el armado de la plantilla: que dato es cada {{n}}", f"{d.get('armados')}")
finally:
    for obj, nombre, original in orig_m:
        setattr(obj, nombre, original)


# =============================================================================
titulo("6. Una plantilla desactivada por la empresa no se usa en ningun lado")
# =============================================================================
#  En el motor, no solo en la pantalla: no se ofrece, no se manda pidiendola
#  por su nombre, no la manda un aviso automatico ni la encuesta, y no se
#  puede encender un momento con ella.
c6 = ConfigMens()
c6.plantillas_desactivadas = ["ticket_creado"]
a = Avisador()
r = a.correr(c6)
revisar(r == {"enviado": False, "motivo": "plantilla_desactivada"} and not a.envios,
        "un aviso automatico con su plantilla desactivada no sale", f"{r}")
ce = ConfigEnc()
ce.plantillas_desactivadas = ["encuesta_satisfaccion"]
e = Encuestador()
r = e.correr(ce)
revisar(r == {"enviada": False, "motivo": "plantilla_desactivada"} and not e.envios and not e.reservas,
        "la encuesta con su plantilla desactivada no sale (ni reserva)", f"{r}")

orig_6 = [(api, "_config_de", api._config_de),
          (api.whatsapp, "plantillas_aprobadas", api.whatsapp.plantillas_aprobadas),
          (api.editor, "guardar_uso_de_plantilla", api.editor.guardar_uso_de_plantilla),
          (api, "olvidar_config", api.olvidar_config)]
try:
    c_api = Config()
    c_api.plantillas_desactivadas = ["seguimiento_caso"]
    api._config_de = lambda t: c_api
    api.whatsapp.plantillas_aprobadas = lambda c, t: [
        {"nombre": "seguimiento_caso", "estado": "APPROVED", "variables": 1},
        {"nombre": "bienvenida", "estado": "APPROVED", "variables": 0}]
    r = cliente.get(f"/canales/plantillas?tenant={TENANT}")
    revisar([p["nombre"] for p in r.get_json()["plantillas"]] == ["bienvenida"],
            "no se ofrece para mandar", f"{r.get_json()['plantillas']}")
    r = cliente.get(f"/canales/plantillas/todas?tenant={TENANT}")
    revisar({p["nombre"]: p["en_uso"] for p in r.get_json()["plantillas"]}
            == {"seguimiento_caso": False, "bienvenida": True},
            "en Ajustes se ve, con su estado de uso", f"{r.get_json()}")

    m = Motor()
    p = montar(m)
    try:
        api._config_de = lambda t: c_api
        api.whatsapp.plantillas_aprobadas = lambda c, t: [PLANTILLA]
        r = cliente.post("/casos/caso-1/plantilla", json=CUERPO)
    finally:
        for obj, nombre, original in reversed(p):
            setattr(obj, nombre, original)
    revisar(r.status_code == 400 and not m.guardados and "desactiv" in r.get_json()["error"],
            "pedirla por su nombre desde el ticket: 400, y no se guarda ni se manda", f"{r.status_code}")

    cfg_real2 = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml").model_copy(
        update={"plantillas_desactivadas": ["ticket_creado"]})
    api._config_de = lambda t: cfg_real2
    api.whatsapp.plantillas_aprobadas = lambda c, t: [
        {"nombre": "ticket_creado", "estado": "APPROVED", "variables": 1}]
    r = cliente.put("/mensajes-automaticos/ticket_creado_cliente",
                    json={"tenant": TENANT, "activo": True, "plantilla": "ticket_creado",
                          "datos": ["cliente_nombre"]})
    revisar(r.status_code == 400 and "desactivada" in r.get_json()["error"],
            "no se enciende un momento con una plantilla desactivada", f"{r.get_json()}")

    usos: list = []

    def guardar_uso(t, nombre, en_uso):
        usos.append((nombre, en_uso))
        return cfg_real2.model_copy(update={
            "plantillas_desactivadas": [] if en_uso else [nombre],
            "mensajes_automaticos": {"seguimiento_ticket": MensajeAutomatico(
                activo=True, plantilla="seguimiento_caso", datos=["cliente_nombre", "escrito"])}})
    api.editor.guardar_uso_de_plantilla = guardar_uso
    api.olvidar_config = lambda t: None
    r = cliente.put("/canales/plantillas/seguimiento_caso/uso", json={"tenant": TENANT, "en_uso": False})
    revisar(r.status_code == 200 and usos == [("seguimiento_caso", False)]
            and r.get_json() == {"plantilla": "seguimiento_caso", "en_uso": False,
                                 "momentos_que_la_usan": ["seguimiento_ticket"]},
            "desactivarla: se guarda y dice que momentos encendidos la usan", f"{r.get_json()}")
finally:
    for obj, nombre, original in orig_6:
        setattr(obj, nombre, original)

#  El editor, de verdad: entra y sale de la lista sin duplicarse.
from nucleo.config import editor as editor_real               # noqa: E402

doc: dict = {"plantillas_desactivadas": ["b"]}
editor_real._mutar_uso_de_plantilla(doc, "a", False)
editor_real._mutar_uso_de_plantilla(doc, "a", False)
revisar(doc["plantillas_desactivadas"] == ["a", "b"], "desactivar dos veces no la duplica", f"{doc}")
editor_real._mutar_uso_de_plantilla(doc, "a", True)
revisar(doc["plantillas_desactivadas"] == ["b"], "activarla la saca de la lista", f"{doc}")


# =============================================================================
titulo("7. Cada momento trae una plantilla de partida que Meta puede aceptar")
# =============================================================================
#  La pantalla de Plantillas ofrece una por momento, con el orden de sus datos
#  ya puesto. Si una no pasa el mismo armado que el formulario, el boton
#  "Usar" llevaria a un rechazo seguro.
from nucleo.config import mensajes_catalogo as cat            # noqa: E402
from nucleo.canales import whatsapp as wa                    # noqa: E402

revisar(set(cat.SUGERENCIAS) == set(cat.EVENTOS), "hay una sugerencia por cada momento del catalogo",
        f"{set(cat.EVENTOS) ^ set(cat.SUGERENCIAS)}")
nombres = [s["nombre"] for s in cat.SUGERENCIAS.values()]
revisar(len(nombres) == len(set(nombres)), "ningun nombre se repite entre momentos", f"{nombres}")
for ev, s in cat.SUGERENCIAS.items():
    lista = cat.sugerencia(ev)
    try:
        wa.armar_plantilla_nueva({**lista, "idioma": "es"})
        armo = ""
    except wa.PlantillaInvalida as e:
        armo = str(e)
    huecos = wa._HUECO.findall(s["cuerpo"])
    revisar(not armo and len(huecos) == len(s["datos"]) == len(lista["ejemplos"])
            and all(d in cat.EVENTOS[ev]["campos"] for d in s["datos"]),
            f"{ev}: se arma, y cada {{{{n}}}} tiene un dato que ese momento ofrece",
            f"{armo or (huecos, s['datos'])}")
revisar(cat.sugerencia("no_existe") is None, "un momento desconocido no tiene sugerencia")


# =============================================================================
titulo("8. Modo prueba: un aviso encendido sale SOLO a los numeros de prueba")
# =============================================================================
#  En el motor: mientras 'solo_a' tenga numeros, a un cliente real no le llega
#  nada. Y lo que no salio por estar en prueba no queda reservado: al abrirlo
#  a todos, ese motivo todavia puede salir.
from nucleo.config.schema import MensajeAutomatico as MA      # noqa: E402

revisar(MA(solo_a=["+57 300 111 2233", "573001112233", " "]).solo_a == ["573001112233"],
        "se guarda solo con digitos, sin repetir ni vacios")
for malo in ("3001112", "57300abc2233", "5730011122334455"):
    try:
        MA(solo_a=[malo])
        revisar(False, f"'{malo}' no es un numero valido y se rechaza")
    except ValidationError:
        revisar(True, f"'{malo}' no es un numero valido y se rechaza")

cp = ConfigMens()
cp.mensajes_automaticos["ticket_creado_cliente"].solo_a = ["573009998877"]
a = Avisador()
r = a.correr(cp, para="573001112233")
revisar(r == {"enviado": False, "motivo": "fuera_de_prueba"} and not a.envios and not a.marcas,
        "encendido en prueba: a un cliente que no esta en la lista no le llega", f"{r} {a.envios}")
a = Avisador()
r = a.correr(cp, para="+57 300 999 8877")
revisar(r["enviado"] and a.envios and a.envios[0][0] == "+57 300 999 8877",
        "al numero de prueba si le llega (se compara por los digitos)", f"{r} {a.envios}")
a = Avisador(ya=True)
r = a.correr(cp, para="573001112233")
revisar(r["motivo"] == "fuera_de_prueba",
        "fuera de prueba ni llega a reservar: el motivo queda libre para cuando se abra", f"{r}")
a = Avisador()
r = a.correr(ConfigMens(), para="573001112233")
revisar(r["enviado"], "sin numeros de prueba sale a todos, como antes", f"{r}")

ce8 = ConfigEnc()
ce8.mensajes_automaticos["encuesta_cierre"].solo_a = ["573009998877"]
e = Encuestador()
r = e.correr(ce8)
revisar(r == {"enviada": False, "motivo": "fuera_de_prueba"} and not e.envios and not e.reservas,
        "la encuesta en prueba tampoco le llega a un cliente real (ni reserva)", f"{r}")
ce8.mensajes_automaticos["encuesta_cierre"].solo_a = ["573001112233"]
e = Encuestador()
r = e.correr(ce8)
revisar(r["enviada"], "y al numero de prueba si", f"{r}")

doc8: dict = {"mensajes_automaticos": {"bienvenida": {
    "activo": True, "plantilla": "b", "datos": [], "solo_a": ["573001112233"]}}}
editor_real._mutar_mensaje_automatico(doc8, "bienvenida", False, "b", [])
revisar(doc8["mensajes_automaticos"]["bienvenida"]["solo_a"] == ["573001112233"],
        "apagar con el interruptor no borra los numeros de prueba", f"{doc8}")
editor_real._mutar_mensaje_automatico(doc8, "bienvenida", True, "b", [], [])
revisar(doc8["mensajes_automaticos"]["bienvenida"]["solo_a"] == [],
        "guardar la lista vacia a proposito la abre a todos", f"{doc8}")


# =============================================================================
titulo("9. La espera de la encuesta la elige la empresa")
# =============================================================================
#  Era fija en el CRM (30 minutos). Ahora el CRM avisa el cierre en el acto y
#  el motor dice "todavia no, volve en N segundos" hasta que pase la espera
#  de la empresa. Sin 'cerrado_en' (un CRM de antes) sale como salia.
from datetime import timedelta as _td                         # noqa: E402

ahora9 = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)
ce9 = ConfigEnc(espera_minutos=10)
e = Encuestador()
r = e.correr(ce9, cerrado_en=ahora9 - _td(minutes=4), ahora=ahora9)
revisar(r == {"enviada": False, "motivo": "todavia_no", "reintentar_en": 360}
        and not e.envios and not e.reservas,
        "cerrado hace 4 de 10 minutos: no sale, ni reserva, y dice volver en 6 minutos", f"{r}")
e = Encuestador()
r = e.correr(ce9, cerrado_en=ahora9 - _td(minutes=10), ahora=ahora9)
revisar(r["enviada"], "pasada la espera, sale", f"{r}")
e = Encuestador()
r = e.correr(ConfigEnc(espera_minutos=0), cerrado_en=ahora9, ahora=ahora9)
revisar(r["enviada"], "con espera 0, sale en cuanto se cierra", f"{r}")
e = Encuestador()
r = e.correr(ce9)
revisar(r["enviada"], "sin 'cerrado_en' (un CRM de antes, que ya espero): sale como salia", f"{r}")
e = Encuestador()
r = e.correr(ConfigEnc(activo=False, espera_minutos=10), cerrado_en=ahora9, ahora=ahora9)
revisar(r["motivo"] == "apagada", "apagada no pide volver: no hay nada que esperar", f"{r}")
for malo in (-1, 1441):
    try:
        EncuestaWhatsApp(espera_minutos=malo)
        revisar(False, f"una espera de {malo} minutos se rechaza")
    except ValidationError:
        revisar(True, f"una espera de {malo} minutos se rechaza")

orig_9 = [(api, "_config_de", api._config_de), (api.encuesta, "enviar", api.encuesta.enviar),
          (api.editor, "guardar_espera_encuesta", api.editor.guardar_espera_encuesta),
          (api, "olvidar_config", api.olvidar_config)]
try:
    api._config_de = lambda t: ce9
    pedidos9: list = []
    api.encuesta.enviar = lambda c, t, caso, **kw: pedidos9.append(kw) or {"enviada": False,
                                                                           "motivo": "todavia_no"}
    cliente.post("/casos/caso-1/encuesta", json={"tenant": TENANT, "cerrado_en": "2026-10-29T15:00:00Z"})
    cliente.post("/casos/caso-1/encuesta", json={"tenant": TENANT, "cerrado_en": "ayer"})
    revisar(pedidos9[0]["cerrado_en"] == ahora9 and pedidos9[1]["cerrado_en"] is None,
            "la ruta entiende la hora del cierre, y una que no entiende la ignora", f"{pedidos9}")
    esperas9: list = []
    api.editor.guardar_espera_encuesta = lambda t, m: esperas9.append(m) or ConfigEnc(espera_minutos=m)
    api.olvidar_config = lambda t: None
    r = cliente.put("/encuestas/espera", json={"tenant": TENANT, "espera_minutos": "5"})
    revisar(r.status_code == 200 and esperas9 == [5] and r.get_json() == {"espera_minutos": 5},
            "la empresa cambia la espera desde la pantalla", f"{r.get_json()}")
    r = cliente.put("/encuestas/espera", json={"tenant": TENANT, "espera_minutos": "cinco"})
    revisar(r.status_code == 400 and esperas9 == [5], "una espera que no es un numero: 400, no se guarda")
finally:
    for obj, nombre, original in orig_9:
        setattr(obj, nombre, original)

doc9: dict = {}
editor_real._mutar_espera_encuesta(doc9, 5)
revisar(doc9 == {"encuesta_whatsapp": {"espera_minutos": 5}}, "el editor la escribe en la encuesta", f"{doc9}")


print(f"\n{'=' * 76}\n  {'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}\n{'=' * 76}")
sys.exit(1 if fallos else 0)
