# -*- coding: utf-8 -*-
"""
================================================================================
 ERRORES HTTP  --  ninguna respuesta lleva el texto de una excepcion ajena
================================================================================

    py -3.13 tests/test_errores_http.py          (sin base, sin red)

Por que existe (D19 + D23, 17/09/2026)
--------------------------------------
46 respuestas del motor devolvian str(e), f"...: {e}" o el cuerpo crudo de un
proveedor. D19: la sincronizacion de localidades devolvia en un 502 lo que
contestaba el ISP. D23: las rutas de administracion devolvian el texto de
errores de base y de bibliotecas. Ver nucleo/canales/errores.py.

  1. el CODIGO: dentro de un except, una respuesta solo usa la excepcion por
     mensaje_publico(), fallo(e=...) o estado_http_de(); nunca str(e), {e},
     repr, .args ni el .text/.content de una respuesta de proveedor
  2. el ORIGEN: ninguna excepcion se construye interpolando otra atrapada
     (salvo su tipo) -- si no, "publica" dejaria de significar "escrita por
     Dexter"
  3. la SALIDA: canarios inyectados en los caminos reales (D19, guardado,
     herramienta interna, carga de config, diagnostico, plantillas, adjuntos,
     secretos, conversaciones) no aparecen ni en la respuesta ni en el log, y
     los mensajes propios de Dexter SI siguen llegando
================================================================================
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.pop("MOTOR_SERVICE_TOKEN", None)

import requests                                                   # noqa: E402

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


CANARIO = "TEXTO_AJENO_NO_DEBE_SALIR_573014445566"
USOS_PERMITIDOS = {"mensaje_publico", "estado_http_de", "registrar"}


# =============================================================================
titulo("1. el codigo: las respuestas no usan el texto de la excepcion")
# =============================================================================
#: Atributos de una excepcion que NO son su mensaje y si se pueden devolver.
#:
#: POR QUE UNA LISTA Y NO "cualquier atributo"  --  12/11/2026
#: ----------------------------------------------------------
#: Estos tres los ponen NUESTRAS excepciones a proposito para que la respuesta
#: pueda decir que paso sin copiar ningun texto: `e.codigo` es un codigo
#: estable, `e.http` el estado que le corresponde, `e.faltan` que requisitos no
#: se cumplieron. Son metadatos.
#:
#: Lo que queda AFUERA es lo que importa: `e.args`, `e.msg`, `e.message`,
#: `e.reason`, `e.response`, `e.text` SI son el mensaje o el cuerpo del
#: proveedor, y siguen marcandose. Una regla de "cualquier atributo es seguro"
#: dejaria pasar `e.args[0]`, que es `str(e)` escrito distinto.
ATRIBUTOS_DE_METADATO = {"codigo", "http", "faltan"}


def _metadato_seguro(nodo: ast.AST, nombre: str) -> set[int]:
    """Los ids de los usos de 'nombre' que NO dejan salir su texto.

    POR QUE ESTO EXISTE  --  12/11/2026
    -----------------------------------
    Esta seccion estuvo en ROJO con 16 sitios reportados, y 10 de ellos NO eran
    defectos: `type(e).__name__` es justo lo seguro --el nombre de la clase, que
    es lo que `registrar()` deja en el log-- y `e.codigo`/`e.http` son
    metadatos que nuestras propias excepciones traen para esto.

    Una guarda que marca lo correcto junto con lo incorrecto no se arregla: se
    deja de mirar. Y mientras se dejaba de mirar, los 6 que SI eran defectos
    --`str(e)` en un `except ValueError`, que atrapa tanto el nuestro como el
    de una biblioteca-- vivieron ahi a la vista de todos.

    La regla pasa a ser "QUE SALE" en vez de "aparece 'e'".
    """
    seguros: set[int] = set()
    for n in ast.walk(nodo):
        #  type(e).__name__  -- sale el nombre de la CLASE, nunca el mensaje.
        if (isinstance(n, ast.Attribute) and n.attr == "__name__"
                and isinstance(n.value, ast.Call)
                and ast.unparse(n.value.func) == "type"
                and len(n.value.args) == 1
                and isinstance(n.value.args[0], ast.Name)
                and n.value.args[0].id == nombre):
            seguros.add(id(n.value.args[0]))
        #  e.codigo / e.http / e.faltan  -- metadato, no texto.
        if (isinstance(n, ast.Attribute) and n.attr in ATRIBUTOS_DE_METADATO
                and isinstance(n.value, ast.Name) and n.value.id == nombre):
            seguros.add(id(n.value))
    return seguros


def usos_prohibidos(nodo: ast.AST, nombre: str) -> list[str]:
    """Usos de 'nombre' dentro de 'nodo' que no pasan por un helper permitido."""
    permitidos = _metadato_seguro(nodo, nombre)
    for n in ast.walk(nodo):
        if isinstance(n, ast.Call):
            f = ast.unparse(n.func).split(".")[-1]
            if f in USOS_PERMITIDOS:
                permitidos |= {id(x) for a in n.args for x in ast.walk(a)}
            if f == "fallo":
                permitidos |= {id(x) for k in n.keywords if k.arg == "e" for x in ast.walk(k.value)}
                permitidos |= {id(x) for k in n.keywords if k.arg != "e"
                               for x in ast.walk(k.value)
                               if isinstance(k.value, ast.Call)
                               and ast.unparse(k.value.func).split(".")[-1] in USOS_PERMITIDOS}
                permitidos |= {id(x) for a in n.args if isinstance(a, ast.Call)
                               and ast.unparse(a.func).split(".")[-1] in USOS_PERMITIDOS
                               for x in ast.walk(a)}
    return [ast.unparse(n) for n in ast.walk(nodo)
            if isinstance(n, ast.Name) and n.id == nombre and id(n) not in permitidos]


malos = []
for ruta in sorted((RAIZ / "nucleo" / "canales").glob("*.py")):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    rel = ruta.relative_to(RAIZ).as_posix()
    for h in (n for n in ast.walk(arbol) if isinstance(n, ast.ExceptHandler)):
        for n in (x for s in h.body for x in ast.walk(s)):
            if not isinstance(n, ast.Call):
                continue
            f = ast.unparse(n.func).split(".")[-1]
            if f not in ("jsonify", "fallo", "Response", "make_response"):
                continue
            if h.name and usos_prohibidos(n, h.name):
                malos.append(f"{rel}:{n.lineno} usa '{h.name}' directo")
            if any(isinstance(x, ast.Attribute) and x.attr in ("text", "content")
                   for x in ast.walk(n)):
                malos.append(f"{rel}:{n.lineno} devuelve .text/.content de una respuesta")
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and ast.unparse(n.func).split(".")[-1] == "jsonify" and any(
                isinstance(x, ast.Attribute) and x.attr in ("text",) and "r" == ast.unparse(x.value)
                for x in ast.walk(n)):
            malos.append(f"{rel}:{n.lineno} devuelve r.text")
revisar(not malos, "ninguna respuesta de error usa el texto de la excepcion ni el cuerpo de un proveedor",
        "\n         ".join(malos))


# --- LA GUARDA SE PRUEBA A SI MISMA  --  12/11/2026 ------------------------
#
# Se acaba de aflojar: `type(e).__name__` y tres atributos de metadato dejaron
# de marcarse. Aflojar una guarda sin demostrar que sigue atrapando lo que
# importa es como borrarla, y mas peligroso: queda en verde.
#
# Cada canario es un fragmento REAL que se pasa por el mismo analizador. Los de
# arriba TIENEN que marcarse; los de abajo NO.
def _marca(fragmento: str) -> bool:
    """True si el analizador marcaria este fragmento."""
    arbol = ast.parse(fragmento)
    for h in (n for n in ast.walk(arbol) if isinstance(n, ast.ExceptHandler)):
        for n in (x for s in h.body for x in ast.walk(s)):
            if (isinstance(n, ast.Call)
                    and ast.unparse(n.func).split(".")[-1] in
                    ("jsonify", "fallo", "Response", "make_response")
                    and h.name and usos_prohibidos(n, h.name)):
                return True
    return False


_ENVOLTORIO = "try:\n    pass\nexcept ValueError as e:\n    %s\n"

DEBEN_MARCARSE = [
    ('return jsonify({"error": str(e)})', "str(e) pelado"),
    ('return jsonify({"error": f"fallo: {e}"})', "interpolado en una f-string"),
    ('return jsonify({"error": "fallo: " + str(e)})', "concatenado"),
    ('return jsonify({"error": e.args[0]})', "e.args, que es str(e) escrito distinto"),
    ('return jsonify({"error": e.msg})', "un atributo que SI es el mensaje"),
    ('return jsonify({"error": repr(e)})', "repr, que trae el mensaje adentro"),
    ('return fallo(500, "x", str(e), componente="c")', "por fallo(), en el mensaje"),
]

NO_DEBEN_MARCARSE = [
    ('return jsonify({"error": type(e).__name__})', "el nombre de la clase"),
    ('return jsonify({"error": e.codigo})', "un codigo estable"),
    ('return jsonify({"error": e.codigo, "faltan": e.faltan}), e.http',
     "codigo, faltan y http juntos"),
    ('return jsonify({"error": mensaje_publico(e, "fijo")})',
     "por el registro de clases publicas"),
    ('return fallo(500, "x", "mensaje fijo", componente="c", e=e)',
     "por fallo(), que lo manda al log"),
]

for fragmento, que in DEBEN_MARCARSE:
    revisar(_marca(_ENVOLTORIO % fragmento),
            f"canario: la guarda SIGUE marcando {que}",
            f"no la marco: {fragmento}")

for fragmento, que in NO_DEBEN_MARCARSE:
    revisar(not _marca(_ENVOLTORIO % fragmento),
            f"canario: la guarda NO marca {que}",
            f"la marco de mas: {fragmento}")


# =============================================================================
titulo("2. el origen: ninguna excepcion se arma con el texto de otra")
# =============================================================================
armadas = []
for ruta in sorted((RAIZ / "nucleo").rglob("*.py")):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    rel = ruta.relative_to(RAIZ).as_posix()
    for h in (n for n in ast.walk(arbol) if isinstance(n, ast.ExceptHandler) and n.name):
        for r in (x for s in h.body for x in ast.walk(s)):
            if not (isinstance(r, ast.Raise) and isinstance(r.exc, ast.Call)):
                continue
            tipos = {id(a.value.args[0]) for a in ast.walk(r.exc) if isinstance(a, ast.Attribute)
                     and a.attr == "__name__" and isinstance(a.value, ast.Call)
                     and ast.unparse(a.value.func) == "type" and a.value.args}
            if any(isinstance(x, ast.Name) and x.id == h.name and id(x) not in tipos
                   for x in ast.walk(r.exc)):
                armadas.append(f"{rel}:{r.lineno} {ast.unparse(r.exc)[:90]}")
revisar(not armadas, "ninguna excepcion interpola una atrapada (solo su tipo)",
        "\n         ".join(armadas))


# =============================================================================
titulo("3. la salida: canarios en los caminos reales")
# =============================================================================
from nucleo.canales import api, errores, whatsapp                 # noqa: E402
from nucleo.config import fusion                                  # noqa: E402
from nucleo.persistencia import db                                # noqa: E402
from nucleo.seguridad import secretos                             # noqa: E402

cliente = api.app.test_client()
TENANT = "tenant-prueba-d23"


@contextlib.contextmanager
def parches(*trios):
    viejos = [(o, n, getattr(o, n)) for o, n, _ in trios]
    for o, n, v in trios:
        setattr(o, n, v)
    try:
        yield
    finally:
        for o, n, v in reversed(viejos):
            setattr(o, n, v)


def lanza(e):
    def _f(*a, **k):
        raise e
    return _f


def http_error(status):
    r = requests.Response()
    r.status_code = status
    r._content = CANARIO.encode()
    return requests.HTTPError(f"{status} Server Error: {CANARIO} for url: https://isp/{CANARIO}",
                              response=r)


herramienta_localidades = types.SimpleNamespace(nombre="listar_localidades", sincroniza_localidades=True)
CONFIG = types.SimpleNamespace(herramientas=[herramienta_localidades], variables_tenant={},
                               roles={}, identidad=types.SimpleNamespace(slug=TENANT))


def pedir(nombre, funcion, estado, *extra, debe_contener=None, codigo=None):
    buf = io.StringIO()
    with parches((api, "_config_de", lambda t: CONFIG), *extra), \
            contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        r = funcion()
    cuerpo = r.get_data(as_text=True)
    datos = r.get_json(silent=True) or {}
    # Las cabeceras enteras (nombre y valor): Location, WWW-Authenticate,
    # Set-Cookie, X-*... No se espera que el texto ajeno llegue ahi; se revisa
    # para cerrar el borde HTTP completo y no solo el cuerpo.
    cabeceras = "\n".join(f"{k}: {v}" for k, v in r.headers.items())
    revisar(r.status_code == estado and CANARIO not in cuerpo and CANARIO not in buf.getvalue()
            and CANARIO not in cabeceras
            and (debe_contener is None or debe_contener in cuerpo)
            and (codigo is None or datos.get("codigo") == codigo),
            f"{nombre}: {estado}, sin el texto ajeno en cuerpo, cabeceras ni log"
            + (f", con '{debe_contener}'" if debe_contener else ""),
            f"status={r.status_code} cuerpo={cuerpo[:200]!r} cabeceras={cabeceras[:200]!r} "
            f"log={buf.getvalue()[:200]!r}")
    return datos


datos = pedir("D19 localidades: el proveedor falla",
              lambda: cliente.post("/configuracion/localidades/sincronizar", json={"tenant": TENANT}),
              502, (api.sincronizador_localidades, "sincronizar", lanza(http_error(503))),
              codigo="proveedor_no_sincronizo")
revisar(datos.get("estado_proveedor") == 503,
        "D19: se devuelve el codigo HTTP del proveedor (metadata), no su texto", f"{datos}")

try:
    import psycopg
    error_base = psycopg.errors.UniqueViolation(f"Key (x)=({CANARIO}) already exists")
except ImportError:                                               # pragma: no cover
    error_base = RuntimeError(CANARIO)
pedir("guardar localidades: la base falla",
      lambda: cliente.post("/configuracion/localidades/sincronizar", json={"tenant": TENANT}),
      500, (api.sincronizador_localidades, "sincronizar", lambda *a: []),
      (api.editor, "guardar_localidades", lanza(error_base)), codigo="guardado_fallido")

pedir("herramienta invocada por servicio falla",
      lambda: cliente.post(f"/interno/herramienta/x?tenant={TENANT}", json={}),
      502, (api, "_config_de", lambda t: types.SimpleNamespace(
          herramientas=[types.SimpleNamespace(nombre="x", invocable_por_servicio=True)])),
      (api.motor, "ejecutar_para_servicio", lanza(RuntimeError(CANARIO))), codigo="herramienta_fallo")

pedir("cargar la config falla",
      lambda: cliente.get(f"/configuracion/variables?tenant={TENANT}"),
      500, (api, "_config_de", lanza(RuntimeError(CANARIO))), codigo="config_no_cargada")

pedir("diagnostico: excepcion inesperada",
      lambda: cliente.post("/diagnostico/smartolt", json={"base_url": "https://x", "api_key": "k"}),
      200, (requests, "get", lanza(ValueError(CANARIO))))
pedir("diagnostico: el proveedor responde 500 con cuerpo",
      lambda: cliente.post("/diagnostico/smartolt", json={"base_url": "https://x", "api_key": "k"}),
      200, (requests, "get", lambda *a, **k: types.SimpleNamespace(status_code=500, text=CANARIO)),
      debe_contener="HTTP 500")

pedir("plantillas: la red falla",
      lambda: cliente.get(f"/canales/plantillas?tenant={TENANT}"),
      502, (api.whatsapp, "plantillas_aprobadas", lanza(requests.ConnectionError(CANARIO))),
      codigo="plantillas_no_leidas")
pedir("plantillas: WhatsApp rechaza con mensaje de Dexter",
      lambda: cliente.get(f"/canales/plantillas?tenant={TENANT}"),
      502, (api.whatsapp, "plantillas_aprobadas",
            lanza(whatsapp.ErrorWhatsApp("WhatsApp rechazo el listado (codigo 190)."))),
      debe_contener="WhatsApp rechazo el listado")

pedir("adjunto: una validacion ajena falla",
      lambda: cliente.post("/conversaciones/c1/humano/media",
                           data={"tenant": TENANT, "tipo": "image", "autor": "Operador",
                                 "autor_usuario_id": "5a9e996e-2a9f-4cd0-9677-db33165c5fd0",
                                 "archivo": (io.BytesIO(b"x"), "a.png", "image/png")},
                           content_type="multipart/form-data"),
      400, (api.whatsapp, "_validar_media", lanza(ValueError(CANARIO))),
      (api, "_exigir_control_humano", lambda *a, **k: None))
pedir("adjunto: el mensaje propio de WhatsApp sigue llegando",
      lambda: cliente.post("/conversaciones/c1/humano/media",
                           data={"tenant": TENANT, "tipo": "sticker", "autor": "Operador",
                                 "autor_usuario_id": "5a9e996e-2a9f-4cd0-9677-db33165c5fd0",
                                 "archivo": (io.BytesIO(b"x"), "a.png", "image/png")},
                           content_type="multipart/form-data"),
      400, (api.whatsapp, "_validar_media",
            lanza(whatsapp.ErrorWhatsApp("WhatsApp no acepta envios de tipo 'sticker'."))),
      (api, "_exigir_control_humano", lambda *a, **k: None),
      debe_contener="no acepta envios de tipo")

pedir("adjunto sin autor: el mensaje propio del relevo sigue llegando",
      lambda: cliente.post("/conversaciones/c1/humano/media",
                           data={"tenant": TENANT, "tipo": "image",
                                 "archivo": (io.BytesIO(b"x"), "a.png", "image/png")},
                           content_type="multipart/form-data"),
      400, debe_contener="falta el nombre de quien escribe")

pedir("conversaciones: un RuntimeError ajeno",
      lambda: cliente.get(f"/conversaciones?tenant={TENANT}"),
      404, (api.persistencia, "ultima_actividad", lanza(RuntimeError(CANARIO))))
pedir("conversaciones: tenant sin configuracion (mensaje de Dexter)",
      lambda: cliente.get(f"/conversaciones?tenant={TENANT}"),
      404, (api.persistencia, "ultima_actividad",
            lanza(db.TenantSinConfiguracion(f"El tenant '{TENANT}' no tiene configuracion cargada"))),
      debe_contener="no tiene configuracion cargada")


class SesionQueFalla:
    def __enter__(self):
        raise error_base

    def __exit__(self, *a):
        return False


secretos._CACHE.clear()
pedir("secretos: la base falla al leerlos",
      lambda: cliente.get(f"/secretos?tenant={TENANT}"),
      500, (db, "sesion", lambda tenant: SesionQueFalla()),
      debe_contener="No se pudieron leer los secretos")

# Control de la propia prueba: una respuesta que SI mete el texto ajeno en una
# cabecera tiene que ser detectada. Sin esto, 'sin canario en cabeceras' podria
# pasar porque la comprobacion no mira donde cree.
from flask import jsonify as _jsonify                            # noqa: E402


def _con_cabecera_filtrada():
    r = _jsonify({"error": "fijo"})
    r.headers["X-Detalle"] = CANARIO
    return r


with api.app.test_request_context():
    control = _con_cabecera_filtrada()
revisar(CANARIO in "\n".join(f"{k}: {v}" for k, v in control.headers.items()),
        "control: la revision de cabeceras detecta un canario puesto en una X-*")

revisar(isinstance(fusion.FusionInvalida("x"), ValueError)
        and isinstance(db.TenantSinConfiguracion("x"), RuntimeError),
        "las clases publicas nuevas heredan de las de antes: ningun except existente deja de atraparlas")
revisar(errores.mensaje_publico(ValueError(CANARIO), "generico") == "generico"
        and errores.mensaje_publico(fusion.FusionInvalida("propio"), "generico") == "propio",
        "mensaje_publico decide por la clase real de la instancia, no por la del except")

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("OK: ninguna respuesta HTTP lleva texto de excepciones ni de proveedores")
