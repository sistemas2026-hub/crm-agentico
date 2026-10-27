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
  5. el catalogo del tenant declara los asuntos y la herramienta de vinculo.
================================================================================
"""

from __future__ import annotations

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


class Espia:
    def __init__(self, *, titular=True, vinculo_rompe=False, responsable=None,
                 id_ticket="95001"):
        self.titular, self.vinculo_rompe = titular, vinculo_rompe
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
        espia.creaciones.append({"herramienta": herr.nombre, "args": args, **kw,
                                 "servicio_sesion": getattr(sesion, "id_cliente", None)})
        return {"id_ticket": espia.id_ticket}

    def ejecutar_http(herr, args, tenant, **kw):
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
    try:
        return tdd.crear(config, TENANT, CASO, datos["servicio"], datos["asunto"],
                         datos["descripcion"], datos["autor"]), None
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
              (api.ticket_desde_dexter, "crear", api.ticket_desde_dexter.crear)]
llamadas: list = []


def crear_falso(config, tenant, caso_id, servicio, asunto, descripcion, autor):
    llamadas.append((caso_id, servicio, asunto, autor))
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
    r = cliente.get(f"/tickets-desde-dexter/asuntos?tenant={TENANT}")
    nombres = [a["asunto"] for a in (r.get_json() or {}).get("asuntos", [])]
    revisar(r.status_code == 200 and "No Tiene Internet" in nombres and len(nombres) == 15,
            "la pantalla recibe la lista de asuntos", f"{r.status_code} {len(nombres)}")
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


def pedido_http(metodo, url, **kw):
    pedidos.append((metodo, url))
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

# =============================================================================
titulo("5. El catalogo del tenant")
# =============================================================================
vinc = [h for h in CONFIG.herramientas if h.vincula_caso_externo]
revisar(len(vinc) == 1 and vinc[0].endpoint.endswith("/vincular/"),
        "una herramienta de vinculo, apuntando a la ruta de importacion", f"{vinc}")
roles = list(CONFIG.roles.values()) if isinstance(CONFIG.roles, dict) else list(CONFIG.roles)
visibles = [getattr(r, "nombre", "?") for r in roles
            if "vincular_caso_externo" in (getattr(r, "puede_consultar", None) or [])]
revisar(visibles == [], "ningun rol del modelo la ve", f"{visibles}")
revisar(any("consultar_ticket" in (getattr(r, "puede_consultar", None) or []) for r in roles),
        "control: la misma lectura SI ve una herramienta que el modelo usa")

print(f"\n{'=' * 76}\n  {'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}\n{'=' * 76}")
sys.exit(1 if fallos else 0)
