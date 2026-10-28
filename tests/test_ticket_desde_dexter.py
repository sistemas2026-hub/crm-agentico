# -*- coding: utf-8 -*-
"""
================================================================================
 UN TICKET CREADO EN DEXTER NACE TAMBIEN EN EL ISP  --  y queda atado a su caso
================================================================================
    py -3.13 tests/test_ticket_desde_dexter.py                    (sin base)

Lo que se afirma, sobre el EFECTO:

  1. nada sale afuera si falta algo: asunto fuera de la lista, servicio mal
     escrito o inexistente, sin autor, o sin la herramienta que ata el caso
     (un ticket sin atar lo importaria duplicado);
  2. el ticket sale con la herramienta del escalamiento, por la puerta HUMANA
     con quien lleno el formulario, UNA vez por caso, con el asunto, la
     prioridad y el tecnico del area, y firmado al pie;
  3. el caso se ata con el id que DEVOLVIO el ISP, el proveedor de la config y
     el area del asunto; si atarlo falla, se dice (no se esconde);
  4. la ruta del motor exige autor y traduce cada motivo a su codigo;
  5. el catalogo del tenant declara los asuntos y la herramienta de vinculo;
  7. el adjunto (27/10/2026): se valida antes de escribir nada, va DESPUES
     de atar, al ticket creado, por la puerta humana, con un nombre
     aleatorio; si falla, el ticket queda y se dice;
  8. el catalogo COMPLETO del proveedor (28/10/2026): los frecuentes primero,
     el resto con el area por defecto, leido una vez; sin catalogo, uno de
     fuera de los frecuentes no se crea y se dice por que;
  9. buscar al cliente por servicio, cedula o nombre: solo servicio, nombre y
     estado salen; el padron recorre todas las paginas, se arma aparte, no
     guarda datos de mas y la busqueda nunca va al log.
================================================================================
"""

from __future__ import annotations

import base64
import contextlib
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.pop("MOTOR_SERVICE_TOKEN", None)

fallos: list[str] = []
TENANT = "rapilink"
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


from nucleo.config.schema import cargar_config                    # noqa: E402
from nucleo.seguimiento import ticket_desde_dexter as tdd          # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")


#  La forma REAL de /api/tickets/asuntos-tickets/ (medida el 28/10/2026): una
#  sola fila, con la lista adentro. 'next' es una cadena fuera de una lista y
#  no puede colarse como asunto.
CATALOGO_FALSO = ["No Tiene Internet", "Cable Bajito", "Ampliación", "Cable Bajito"]


def respuesta_catalogo(lista):
    return {"count": 1, "next": "https://isp.invalid/pagina-2", "previous": None,
            "results": [{"asuntos_tickets": list(lista)}]}


class Espia:
    def __init__(self, *, titular=True, vinculo_rompe=False, responsable=None,
                 id_ticket="95001", adjunto_rompe=False, catalogo=CATALOGO_FALSO):
        self.titular, self.vinculo_rompe = titular, vinculo_rompe
        self.adjunto_rompe = adjunto_rompe
        self.catalogo, self.lecturas_catalogo = catalogo, 0
        self.responsable, self.id_ticket = responsable, id_ticket
        self.creaciones: list[dict] = []
        self.vinculos: list[dict] = []
        self.puertas: list[dict] = []


def montar(espia, parches):
    @contextlib.contextmanager
    def puerta(tenant, herramienta, actor="", evidencia="", origen="", **kw):
        espia.puertas.append({"herramienta": herramienta, "actor": actor,
                              "evidencia": evidencia})
        yield

    def ejecutar_tool(herr, sesion, args, tenant, **kw):
        if herr.adjunta_archivo_ticket and espia.adjunto_rompe:
            raise RuntimeError("500 de WispHub")
        espia.creaciones.append({"herramienta": herr.nombre, "args": args, **kw,
                                 "servicio_sesion": getattr(sesion, "id_cliente", None)})
        return {"id_ticket": espia.id_ticket}

    def ejecutar_http(herr, args, tenant, **kw):
        if herr.lista_asuntos_ticket:
            espia.lecturas_catalogo += 1
            if espia.catalogo is None:
                raise RuntimeError("WispHub no contesta")
            return respuesta_catalogo(espia.catalogo)
        if espia.vinculo_rompe:
            raise RuntimeError("409 TICKET_YA_TIENE_CASO")
        espia.vinculos.append({"herramienta": herr.nombre, "args": dict(args)})
        return {"vinculado": True}

    def titular(config, tenant, servicio):
        tdd._servicio(servicio)
        return {"nombre": "Cliente", "estado": "Activo"} if espia.titular else None

    for obj, nombre, valor in (
            (tdd.frontera, "puerta", puerta),
            (tdd, "_ejecutar_tool", ejecutar_tool),
            (tdd.ejecutor_http, "ejecutar", ejecutar_http),
            (tdd, "titular", titular),
            (tdd.agendamiento, "responsable_de",
             lambda t, area, sistema, **k: espia.responsable)):
        parches.append((obj, nombre, getattr(obj, nombre)))
        setattr(obj, nombre, valor)


def crear(espia, config=CONFIG, **kw):
    datos = {"servicio": "5832", "asunto": "No Tiene Internet",
             "descripcion": "El cliente llamo: sin internet desde ayer.",
             "autor": AUTOR["autor"], **kw}
    parches: list = []
    montar(espia, parches)
    tdd._CATALOGOS.clear()
    try:
        return tdd.crear(config, TENANT, CASO, datos["servicio"], datos["asunto"],
                         datos["descripcion"], datos["autor"],
                         archivo=datos.get("archivo")), None
    except tdd.TicketNoCreado as e:
        return None, e.codigo
    finally:
        for obj, nombre, original in reversed(parches):
            setattr(obj, nombre, original)


# =============================================================================
titulo("1. Nada sale afuera si falta algo")
# =============================================================================
for kw, codigo in (({"asunto": "Asunto Inventado"}, "ASUNTO_NO_PERMITIDO"),
                   ({"servicio": "58 32"}, "SERVICIO_INVALIDO"),
                   ({"servicio": ""}, "SERVICIO_INVALIDO"),
                   ({"descripcion": "  "}, "FALTA_DESCRIPCION"),
                   ({"autor": ""}, "FALTA_AUTOR")):
    e = Espia()
    _, cod = crear(e, **kw)
    revisar(cod == codigo and not e.creaciones and not e.vinculos,
            f"{kw} -> {codigo}, y no se creo nada", f"{cod} {e.creaciones}")

e = Espia(titular=False)
_, cod = crear(e)
revisar(cod == "SERVICIO_NO_EXISTE" and not e.creaciones,
        "un servicio que no existe en el ISP no abre ticket", f"{cod}")

sin_vinculo = CONFIG.model_copy(update={"herramientas": [
    h for h in CONFIG.herramientas if not h.vincula_caso_externo]})
e = Espia()
_, cod = crear(e, config=sin_vinculo)
revisar(cod == "NO_CONFIGURADO" and not e.creaciones,
        "SIN la herramienta que ata el caso no se crea el ticket (lo duplicaria)", f"{cod}")

# =============================================================================
titulo("2. El ticket que sale")
# =============================================================================
e = Espia(responsable=("1500111", "Tecnica de soporte"))
r, cod = crear(e)
revisar(cod is None and r == {"id_ticket": "95001", "vinculado": True},
        "crea y ata", f"{r} {cod}")
c = e.creaciones[0] if e.creaciones else {}
revisar(c.get("herramienta") == "crear_ticket_caso",
        "con la herramienta del escalamiento, ya verificada", f"{c.get('herramienta')}")
revisar(c.get("aprobada_por_humano") is True and c.get("origen") == f"ticket_desde_dexter:{CASO}",
        "como accion de una persona, y UNA vez por caso (origen = el caso)", f"{c}")
revisar(e.puertas and e.puertas[0] == {"herramienta": "crear_ticket_caso",
                                       "actor": AUTOR["autor"], "evidencia": f"caso:{CASO}"},
        "por la puerta humana, con quien lleno el formulario como actor", f"{e.puertas}")
sob = c.get("sobrescribir") or {}
revisar(sob.get("asunto") == "No Tiene Internet" == sob.get("asuntos_default")
        and sob.get("prioridad") == "3" and sob.get("tecnico") == "1500111",
        "asunto (y su par obligatorio), prioridad y tecnico del area", f"{sob}")
revisar(c.get("args", {}).get("servicio") == "5832" and c.get("servicio_sesion") == "5832",
        "sobre el servicio que se verifico", f"{c.get('args')}")
revisar(c.get("args", {}).get("descripcion", "").endswith("-- Creado en Dexter por Operador de prueba"),
        "firmado al pie con quien lo abrio", f"{c.get('args', {}).get('descripcion')}")

e = Espia(responsable=None)
crear(e)
sob = (e.creaciones[0] if e.creaciones else {}).get("sobrescribir") or {}
revisar("tecnico" not in sob, "sin responsable del area, va al tecnico fijo de la herramienta",
        f"{sob}")

# =============================================================================
titulo("3. El vinculo")
# =============================================================================
e = Espia(id_ticket="95777")
crear(e)
v = e.vinculos[0] if e.vinculos else {}
revisar(v.get("herramienta") == "vincular_caso_externo"
        and v.get("args", {}).get("id_caso") == CASO
        and v.get("args", {}).get("external_ticket_id") == "95777"
        and v.get("args", {}).get("provider") == "wisphub"
        and v.get("args", {}).get("external_service_id") == "5832"
        and v.get("args", {}).get("area") == "soporte_tecnico",
        "el caso se ata con el id que DEVOLVIO el ISP, el proveedor y el area", f"{v}")

e = Espia(vinculo_rompe=True)
r, cod = crear(e)
revisar(cod is None and r == {"id_ticket": "95001", "vinculado": False},
        "si atarlo falla, el ticket existe y se DICE que no quedo atado", f"{r}")

# =============================================================================
titulo("4. La ruta del motor")
# =============================================================================
from nucleo.canales import api                                    # noqa: E402

api.app.config["TESTING"] = True
cliente = api.app.test_client()
originales = [(api, "_config_de", api._config_de),
              (api.ticket_desde_dexter, "crear", api.ticket_desde_dexter.crear),
              (api.ticket_desde_dexter, "_catalogo", api.ticket_desde_dexter._catalogo)]
api.ticket_desde_dexter._catalogo = lambda c, t: ["Cable Bajito", "No Tiene Internet"]
llamadas: list = []
archivos: list = []


def crear_falso(config, tenant, caso_id, servicio, asunto, descripcion, autor, archivo=None):
    llamadas.append((caso_id, servicio, asunto, autor))
    archivos.append(archivo)
    if asunto == "malo":
        raise tdd.TicketNoCreado("ASUNTO_NO_PERMITIDO")
    if servicio == "999":
        raise tdd.TicketNoCreado("SERVICIO_NO_EXISTE", 404)
    return {"id_ticket": "95001", "vinculado": True}


api._config_de = lambda t: CONFIG
api.ticket_desde_dexter.crear = crear_falso
try:
    url = f"/casos/{CASO}/ticket-operativo"
    base = {"tenant": TENANT, "servicio": "5832", "asunto": "No Tiene Internet",
            "descripcion": "x"}
    r = cliente.post(url, json=base)
    revisar(r.status_code == 400 and not llamadas, "sin autor no se crea nada (D2)",
            f"{r.status_code}")
    r = cliente.post(url, json={**base, **AUTOR})
    revisar(r.status_code == 201 and r.get_json() == {"id_ticket": "95001", "vinculado": True}
            and llamadas[-1] == (CASO, "5832", "No Tiene Internet", AUTOR["autor"]),
            "con autor crea: 201 y el autor viaja como actor", f"{r.status_code} {llamadas}")
    r = cliente.post(url, json={**base, **AUTOR, "asunto": "malo"})
    revisar(r.status_code == 400 and r.get_json() == {"error": "ASUNTO_NO_PERMITIDO"},
            "cada motivo sale con su codigo", f"{r.status_code} {r.get_json()}")
    r = cliente.post(url, json={**base, **AUTOR, "servicio": "999"})
    revisar(r.status_code == 404, "servicio inexistente -> 404", f"{r.status_code}")
    adj = {"nombre": "x.pdf", "tipo": "application/pdf", "base64": "eA=="}
    cliente.post(url, json={**base, **AUTOR, "archivo": adj})
    revisar(archivos[-1] == adj, "el archivo de la pantalla llega al modulo", f"{archivos[-1:]}")
    r = cliente.get(f"/tickets-desde-dexter/asuntos?tenant={TENANT}")
    nombres = [a["asunto"] for a in (r.get_json() or {}).get("asuntos", [])]
    revisar(r.status_code == 200 and nombres[:1] == ["No Tiene Internet"]
            and nombres[-1] == "Cable Bajito" and len(nombres) == 16,
            "la pantalla recibe los frecuentes y despues el resto del catalogo, sin repetir",
            f"{r.status_code} {len(nombres)} {nombres[-2:]}")
finally:
    for obj, nombre, original in originales:
        setattr(obj, nombre, original)

# =============================================================================
titulo("6. Con la frontera y el ejecutor REALES (solo la red y la base dobladas)")
# =============================================================================
#  Las secciones de arriba doblan la puerta. Aca va la de verdad: que la
#  creacion encuentre un permiso HUMANO vigente a nombre de quien lleno el
#  formulario, y que el ultimo metro del ejecutor (frontera.exigir) deje salir
#  la creacion y el vinculo. Si el camino entrara por la puerta autonoma, el
#  interruptor podria frenarlo; si no entrara por ninguna, exigir() lo frena.
from nucleo.modelo import motor as motor_mod                      # noqa: E402
from nucleo.seguridad import frontera as frontera_real            # noqa: E402

pedidos: list = []
permisos: list = []


class RespuestaHttp:
    def __init__(self, cuerpo):
        self.status_code, self.ok, self._c = 200, True, cuerpo
        self.text, self.headers = "{}", {"content-type": "application/json"}

    def json(self):
        return self._c

    def raise_for_status(self):
        return None


partes: list = []


def pedido_http(metodo, url, **kw):
    pedidos.append((metodo, url))
    partes.append(kw.get("files") or {})
    if "/vincular/" in url:
        return RespuestaHttp({"vinculado": True, "ya_estaba": False})
    return RespuestaHttp({"id_ticket": 95888})


class Resultado:
    def __init__(self, respuesta):
        self.hubo_respuesta, self.respuesta = True, respuesta


def una_vez(tenant, herramienta, argumentos, origen, hacer, **kw):
    p = frontera_real.permiso_vigente()
    permisos.append((herramienta, getattr(p, "clase", None), getattr(p, "actor", None),
                     origen))
    return Resultado(hacer())


reales = [(tdd.ejecutor_http, "headers_de", tdd.ejecutor_http.headers_de),
          (tdd.ejecutor_http.requests, "request", tdd.ejecutor_http.requests.request),
          (motor_mod.idempotencia, "ejecutar", motor_mod.idempotencia.ejecutar),
          (tdd, "titular", tdd.titular),
          (tdd.agendamiento, "responsable_de", tdd.agendamiento.responsable_de)]
tdd.ejecutor_http.headers_de = lambda h, t: {}
tdd.ejecutor_http.requests.request = pedido_http
motor_mod.idempotencia.ejecutar = una_vez
tdd.titular = lambda c, t, s: {"nombre": "Cliente", "estado": "Activo"}
tdd.agendamiento.responsable_de = lambda *a, **k: None
try:
    r = tdd.crear(CONFIG, TENANT, CASO, "5832", "Reconexion", "Pide reconexion.",
                  AUTOR["autor"])
finally:
    for obj, nombre, original in reales:
        setattr(obj, nombre, original)

revisar(r == {"id_ticket": "95888", "vinculado": True},
        "la cadena real crea y ata", f"{r}")
revisar(permisos == [("crear_ticket_caso", "humana", AUTOR["autor"],
                      f"ticket_desde_dexter:{CASO}")],
        "la creacion corre con permiso HUMANO a nombre de quien lo pidio, una vez por caso",
        f"{permisos}")
revisar([m for m, _ in pedidos] == ["POST", "POST"]
        and pedidos[0][1].endswith("/api/tickets/")
        and pedidos[1][1].endswith(f"/importacion/casos/{CASO}/vincular/"),
        "salen exactamente dos escrituras: el ticket y el vinculo", f"{pedidos}")

#  La misma cadena real, con un archivo: tres escrituras, y el adjunto
#  tambien con permiso HUMANO y por el PATCH ya verificado.
pedidos.clear()
partes.clear()
permisos.clear()
PDF = base64.b64encode(b"%PDF-1.4 prueba").decode()
tdd.ejecutor_http.headers_de = lambda h, t: {}
tdd.ejecutor_http.requests.request = pedido_http
motor_mod.idempotencia.ejecutar = una_vez
tdd.titular = lambda c, t, s: {"nombre": "Cliente", "estado": "Activo"}
tdd.agendamiento.responsable_de = lambda *a, **k: None
try:
    r = tdd.crear(CONFIG, TENANT, CASO, "5832", "Reconexion", "Pide reconexion.",
                  AUTOR["autor"],
                  archivo={"nombre": "Cedula Juan Perez.pdf", "tipo": "application/pdf",
                           "base64": PDF})
finally:
    for obj, nombre, original in reales:
        setattr(obj, nombre, original)

revisar(r == {"id_ticket": "95888", "vinculado": True, "adjunto": True},
        "con archivo: crea, ata y adjunta", f"{r}")
revisar([m for m, _ in pedidos] == ["POST", "POST", "PATCH"]
        and pedidos[2][1].endswith("/api/tickets/95888/"),
        "la tercera escritura es el PATCH al ticket que DEVOLVIO el ISP", f"{pedidos}")
tercera = partes[2] if len(partes) > 2 else {}
archivo_ticket = tercera.get("archivo_ticket") or ()
revisar(len(archivo_ticket) == 3 and archivo_ticket[1] == b"%PDF-1.4 prueba"
        and archivo_ticket[2] == "application/pdf" and "_adjunto" in tercera,
        "viaja como archivo de verdad, con el campo acompañante (sin el, 500)",
        f"{list(tercera)}")
nombre_subido = archivo_ticket[0] if archivo_ticket else ""
revisar(nombre_subido.startswith("adjunto-") and nombre_subido.endswith(".pdf")
        and "Juan" not in nombre_subido and "Cedula" not in nombre_subido,
        "el nombre original NO viaja (queda en una URL publica): uno aleatorio", nombre_subido)
revisar(("adjuntar_archivo_ticket", "humana", AUTOR["autor"],
         f"ticket_desde_dexter:{CASO}:adjunto") in permisos,
        "el adjunto corre con permiso HUMANO, una vez por caso", f"{permisos}")

# =============================================================================
titulo("7. El adjunto, con la puerta doblada")
# =============================================================================
for archivo, codigo in (({"nombre": "a.pdf", "base64": "esto no es base64!!"}, "ADJUNTO_INVALIDO"),
                        ({"nombre": "a.pdf", "base64": "    "}, "ADJUNTO_INVALIDO"),
                        ("texto suelto", "ADJUNTO_INVALIDO")):
    e = Espia()
    _, cod = crear(e, archivo=archivo)
    revisar(cod == codigo and not e.creaciones and not e.vinculos,
            f"un adjunto roto ({codigo}) no deja NADA creado afuera", f"{cod} {e.creaciones}")

tope = tdd.ADJUNTO_MAX_BYTES
tdd.ADJUNTO_MAX_BYTES = 3
try:
    e = Espia()
    _, cod = crear(e, archivo={"nombre": "a.pdf", "base64": base64.b64encode(b"1234").decode()})
finally:
    tdd.ADJUNTO_MAX_BYTES = tope
revisar(cod == "ADJUNTO_MUY_GRANDE" and not e.creaciones,
        "uno de mas del tope no deja nada creado", f"{cod}")

ARCHIVO = {"nombre": "foto.JPG", "tipo": "image/jpeg", "base64": base64.b64encode(b"jpg").decode()}
e = Espia()
r, cod = crear(e, archivo=ARCHIVO)
nombres = [c["herramienta"] for c in e.creaciones]
revisar(r == {"id_ticket": "95001", "vinculado": True, "adjunto": True}
        and nombres == ["crear_ticket_caso", "adjuntar_archivo_ticket"],
        "con archivo: el ticket primero, el adjunto despues", f"{r} {nombres}")
sob = (e.creaciones[1] if len(e.creaciones) > 1 else {}).get("sobrescribir") or {}
revisar(sob.get("id_ticket") == "95001"
        and (sob.get("archivo_ticket") or {}).get("base64") == ARCHIVO["base64"]
        and (sob.get("archivo_ticket") or {}).get("nombre", "").endswith(".jpg"),
        "al ticket que devolvio el ISP, con los mismos bytes y su extension", f"{sob}")
revisar([p["herramienta"] for p in e.puertas] ==
        ["crear_ticket_caso", "vincular_caso_externo", "adjuntar_archivo_ticket"]
        and all(p["actor"] == AUTOR["autor"] for p in e.puertas),
        "las tres por la puerta humana, con quien lleno el formulario", f"{e.puertas}")

e = Espia(adjunto_rompe=True)
r, cod = crear(e, archivo=ARCHIVO)
revisar(cod is None and r == {"id_ticket": "95001", "vinculado": True, "adjunto": False},
        "si el adjunto falla, el ticket queda y se DICE", f"{r} {cod}")

sin_adjuntar = CONFIG.model_copy(update={"herramientas": [
    h for h in CONFIG.herramientas if not h.adjunta_archivo_ticket]})
e = Espia()
r, cod = crear(e, config=sin_adjuntar, archivo=ARCHIVO)
revisar(cod is None and (r or {}).get("adjunto") is False and len(e.creaciones) == 1,
        "sin la herramienta de adjuntar, el ticket se crea igual y dice que el archivo no fue",
        f"{r} {cod}")

# =============================================================================
titulo("8. El catalogo COMPLETO de asuntos del proveedor (28/10/2026)")
# =============================================================================
revisar(tdd._cadenas(respuesta_catalogo(["A", " B ", "A"])) == ["A", "B"],
        "de la respuesta real salen las cadenas de la lista, sin repetir; 'next' no se cuela",
        f"{tdd._cadenas(respuesta_catalogo(['A', ' B ', 'A']))}")


def con_espia(espia, hacer):
    parches: list = []
    montar(espia, parches)
    tdd._CATALOGOS.clear()
    try:
        return hacer()
    finally:
        for obj, nombre, original in reversed(parches):
            setattr(obj, nombre, original)


e = Espia()
lista = con_espia(e, lambda: tdd.asuntos(CONFIG, TENANT))
frecuentes = [a.asunto for a in CONFIG.tickets_desde_dexter.asuntos]
revisar([a["asunto"] for a in lista[:15]] == frecuentes
        and all(a["frecuente"] for a in lista[:15]),
        "primero los 15 frecuentes, en el orden de la config", f"{lista[:2]}")
revisar([a["asunto"] for a in lista[15:]] == ["Ampliación", "Cable Bajito"]
        and all(not a["frecuente"] and a["area"] == "soporte_tecnico" for a in lista[15:]),
        "despues el resto del catalogo: alfabetico, sin repetir un frecuente, area por defecto",
        f"{lista[15:]}")

e = Espia()
lecturas = con_espia(e, lambda: (tdd.asuntos(CONFIG, TENANT), tdd.asuntos(CONFIG, TENANT),
                                 e.lecturas_catalogo)[2])
revisar(lecturas == 1, "el catalogo se lee UNA vez y se guarda (la pantalla lo pide cada vez)",
        f"{lecturas}")

e = Espia(catalogo=None)
lista = con_espia(e, lambda: tdd.asuntos(CONFIG, TENANT))
revisar(len(lista) == 15, "si el proveedor no contesta, la pantalla sigue con los frecuentes",
        f"{len(lista)}")

e = Espia(responsable=("1500111", "Tecnica de soporte"))
r, cod = crear(e, asunto="Cable Bajito")
sob = (e.creaciones[0] if e.creaciones else {}).get("sobrescribir") or {}
v = e.vinculos[0] if e.vinculos else {}
revisar(cod is None and sob.get("asunto") == "Cable Bajito" == sob.get("asuntos_default")
        and sob.get("prioridad") == "2" and sob.get("tecnico") == "1500111"
        and v.get("args", {}).get("area") == "soporte_tecnico",
        "un asunto del catalogo sale tal cual, con la prioridad y el area por defecto",
        f"{cod} {sob} {v}")

e = Espia(catalogo=None)
_, cod = crear(e, asunto="Cable Bajito")
revisar(cod == "ISP_NO_CONTESTA" and not e.creaciones,
        "sin catalogo, uno de fuera de los frecuentes NO se crea, y no se dice 'no permitido'",
        f"{cod}")
e = Espia(catalogo=None)
r, cod = crear(e)
revisar(cod is None and e.creaciones and e.lecturas_catalogo == 0,
        "un frecuente no necesita el catalogo: se crea aunque el proveedor no lo mande",
        f"{cod} {e.lecturas_catalogo}")

apagado = CONFIG.model_copy(update={"tickets_desde_dexter":
    CONFIG.tickets_desde_dexter.model_copy(update={"catalogo_del_proveedor": False})})
e = Espia()
_, cod = crear(e, config=apagado, asunto="Cable Bajito")
revisar(cod == "ASUNTO_NO_PERMITIDO" and e.lecturas_catalogo == 0 and not e.creaciones,
        "con el catalogo apagado vale solo la lista de la config, sin leer nada", f"{cod}")

# =============================================================================
titulo("9. Buscar al cliente por servicio, cedula o nombre (28/10/2026)")
# =============================================================================
import threading                                                  # noqa: E402

from nucleo.seguimiento import buscar_cliente as bc               # noqa: E402

#  Filas como las del listado de clientes: con los datos que NO pueden salir.
def fila(sid, nombre, estado="Activo"):
    return {"id_servicio": sid, "nombre": nombre, "estado": estado,
            "cedula": "1234567", "telefono": "3001234567", "password_router": "x"}


PADRON = ([fila(1000 + i, f"CLIENTE NUMERO {i}") for i in range(640)]
          + [fila(9001, "JOSE MARIA PEREZ"), fila(9002, "MARÍA LÓPEZ GÓMEZ"),
             fila(9003, "MARIA LOPEZ ZAPATA", "Suspendido")])


class Proveedor:
    def __init__(self, padron=PADRON, rompe=False):
        self.padron, self.rompe = padron, rompe
        self.paginas: list = []
        self.cedulas: list = []

    def ejecutar(self, herr, args, tenant, **kw):
        if "cedula" in args:
            self.cedulas.append(args["cedula"])
            return {"count": 2, "results": [fila(5832, "TITULAR CEDULA"),
                                             fila(7001, "TITULAR CEDULA")]}
        if self.rompe:
            raise RuntimeError("WispHub no contesta")
        self.paginas.append((args.get("limit"), args.get("offset")))
        o, n = args["offset"], args["limit"]
        return {"count": len(self.padron), "results": self.padron[o:o + n]}


registros: list = []


def con_proveedor(prov, hacer, servicio=None):
    parches = [(bc.ejecutor_http, "ejecutar", bc.ejecutor_http.ejecutar),
               (bc, "registrar", bc.registrar),
               (bc.importacion_io, "resolver_servicios", bc.importacion_io.resolver_servicios)]
    bc.ejecutor_http.ejecutar = prov.ejecutar
    bc.registrar = lambda comp, ev, **k: registros.append((comp, ev, k))
    bc.importacion_io.resolver_servicios = lambda c, t: (
        lambda ids: {ids[0]: {"nombre": "TITULAR SERVICIO", "estado": "Activo",
                              "sn_onu": "x"}} if ids[0] == servicio else {})
    try:
        return hacer()
    finally:
        for obj, nombre, original in reversed(parches):
            setattr(obj, nombre, original)


def esperar_carga():
    for h in threading.enumerate():
        if h.name.startswith("padron-"):
            h.join(10)


def limpio():
    bc._PADRONES.clear()
    bc._CARGANDO.clear()


limpio()
for q in ("", "ab", "  a  ", "1" * 13):
    try:
        bc.buscar(CONFIG, TENANT, q)
        cod = None
    except bc.BusquedaInvalida as e:
        cod = e.codigo
    revisar(cod == "BUSQUEDA_CORTA", f"{q!r} -> BUSQUEDA_CORTA, sin salir a nadie", f"{cod}")

prov = Proveedor()
r = con_proveedor(prov, lambda: bc.buscar(CONFIG, TENANT, "5832"), servicio="5832")
revisar([x["servicio"] for x in r["resultados"]] == ["5832", "7001"] and prov.cedulas == ["5832"],
        "solo digitos: como servicio Y como cedula, sin repetir el mismo servicio", f"{r}")
revisar(all(set(x) == {"servicio", "nombre", "estado"} for x in r["resultados"]),
        "de cada cliente salen SOLO servicio, nombre y estado", f"{r['resultados'][:1]}")
revisar(not prov.paginas, "buscar por numero no arma el padron", f"{prov.paginas}")

limpio()
prov = Proveedor()
r = con_proveedor(prov, lambda: bc.buscar(CONFIG, TENANT, "maria lopez"))
revisar(r == {"resultados": [], "mas": False, "cargando": True},
        "la primera busqueda por nombre contesta 'cargando' en vez de colgar", f"{r}")
con_proveedor(prov, esperar_carga)
revisar(prov.paginas == [(300, 0), (300, 300), (300, 600)],
        "el padron recorre TODAS las paginas del proveedor, de a 300", f"{prov.paginas}")
filas = (bc._PADRONES.get(TENANT) or {}).get("filas") or []
revisar(len(filas) == len(PADRON) and all("cedula" not in f and "telefono" not in f for f in filas),
        "el padron guarda a todos, sin cedula, telefono ni claves", f"{len(filas)}")
revisar(TENANT not in bc._CARGANDO, "al terminar, deja de figurar como cargando")

r = con_proveedor(prov, lambda: bc.buscar(CONFIG, TENANT, "Maria  LOPEZ"))
revisar([x["servicio"] for x in r["resultados"]] == ["9002", "9003"] and r["cargando"] is False,
        "por nombre: todas las palabras, sin importar tildes ni mayusculas, por apellido tambien",
        f"{r}")
r = con_proveedor(prov, lambda: bc.buscar(CONFIG, TENANT, "maria"))
revisar([x["servicio"] for x in r["resultados"]] == ["9002", "9003", "9001"],
        "primero los que EMPIEZAN asi, despues los que lo contienen", f"{r}")
r = con_proveedor(prov, lambda: bc.buscar(CONFIG, TENANT, "cliente numero"))
revisar(len(r["resultados"]) == bc.MAXIMO and r["mas"] is True,
        "mas de 15: los primeros 15 y 'mas', para que se afine", f"{len(r['resultados'])}")
revisar(len(prov.paginas) == 3, "con el padron vigente no se vuelve a leer al proveedor",
        f"{len(prov.paginas)}")
revisar(not any("maria" in str(k).lower() or "cliente numero" in str(k).lower()
                for _, _, k in registros),
        "la busqueda NUNCA va al log", f"{registros}")

bc._PADRONES[TENANT]["cuando"] -= 7 * 3600
prov2 = Proveedor(padron=[fila(9100, "MARIA NUEVA")])
r = con_proveedor(prov2, lambda: bc.buscar(CONFIG, TENANT, "maria lopez"))
revisar([x["servicio"] for x in r["resultados"]] == ["9002", "9003"],
        "vencido: contesta con el viejo mientras arma el nuevo", f"{r}")
con_proveedor(prov2, esperar_carga)
r = con_proveedor(prov2, lambda: bc.buscar(CONFIG, TENANT, "maria"))
revisar([x["servicio"] for x in r["resultados"]] == ["9100"], "y despues usa el nuevo", f"{r}")

limpio()
prov = Proveedor(rompe=True)
con_proveedor(prov, lambda: (bc.buscar(CONFIG, TENANT, "maria"), esperar_carga()))
revisar(TENANT not in bc._PADRONES and TENANT not in bc._CARGANDO
        and any(ev == "no se pudo cargar el padron" for _, ev, _ in registros),
        "si el proveedor falla: queda dicho en el log y la proxima busqueda reintenta",
        f"{bc._CARGANDO} {registros[-1:]}")

limpio()
sin_nombre = CONFIG.model_copy(update={"tickets_desde_dexter":
    CONFIG.tickets_desde_dexter.model_copy(update={"buscar_por_nombre": False})})
prov = Proveedor()
try:
    con_proveedor(prov, lambda: bc.buscar(sin_nombre, TENANT, "maria"))
    cod = None
except bc.BusquedaInvalida as e:
    cod = e.codigo
revisar(cod == "SIN_BUSQUEDA_POR_NOMBRE" and not prov.paginas and TENANT not in bc._CARGANDO,
        "con la busqueda por nombre apagada no se arma ningun padron", f"{cod}")

#  La ruta del motor: traduce cada caso a su codigo.
originales = [(api, "_config_de", api._config_de),
              (api.buscar_cliente, "buscar", api.buscar_cliente.buscar)]
api._config_de = lambda t: CONFIG
try:
    api.buscar_cliente.buscar = lambda c, t, q: {"resultados": [{"servicio": "1", "nombre": q,
                                                                "estado": "Activo"}],
                                                 "mas": False, "cargando": False}
    r = cliente.get(f"/clientes/buscar?tenant={TENANT}&q=mario%20saba")
    revisar(r.status_code == 200 and r.get_json()["resultados"][0]["nombre"] == "mario saba",
            "la ruta pasa la busqueda y devuelve lo que encontro", f"{r.status_code}")
    r = cliente.get("/clientes/buscar?q=mario")
    revisar(r.status_code == 400, "sin tenant -> 400", f"{r.status_code}")

    def corta(c, t, q):
        raise bc.BusquedaInvalida("BUSQUEDA_CORTA")
    api.buscar_cliente.buscar = corta
    r = cliente.get(f"/clientes/buscar?tenant={TENANT}&q=ma")
    revisar(r.status_code == 400 and r.get_json() == {"error": "BUSQUEDA_CORTA"},
            "una busqueda invalida sale con su codigo", f"{r.get_json()}")
finally:
    for obj, nombre, original in originales:
        setattr(obj, nombre, original)

# =============================================================================
titulo("5. El catalogo del tenant")
# =============================================================================
lista_h = [h for h in CONFIG.herramientas if h.lista_asuntos_ticket]
revisar(len(lista_h) == 1 and lista_h[0].solo_lectura and lista_h[0].metodo == "GET",
        "una sola herramienta de catalogo, de solo lectura", f"{lista_h}")
vinc = [h for h in CONFIG.herramientas if h.vincula_caso_externo]
revisar(len(vinc) == 1 and vinc[0].endpoint.endswith("/vincular/"),
        "una herramienta de vinculo, apuntando a la ruta de importacion", f"{vinc}")
roles = list(CONFIG.roles.values()) if isinstance(CONFIG.roles, dict) else list(CONFIG.roles)
visibles = [getattr(r, "nombre", "?") for r in roles
            if {"vincular_caso_externo", "listar_asuntos_ticket"}
            & set(getattr(r, "puede_consultar", None) or [])]
revisar(visibles == [], "ningun rol del modelo la ve", f"{visibles}")
revisar(any("consultar_ticket" in (getattr(r, "puede_consultar", None) or []) for r in roles),
        "control: la misma lectura SI ve una herramienta que el modelo usa")

print(f"\n{'=' * 76}\n  {'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}\n{'=' * 76}")
sys.exit(1 if fallos else 0)
