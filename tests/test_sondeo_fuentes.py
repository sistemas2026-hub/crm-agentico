# -*- coding: utf-8 -*-
"""
================================================================================
 EL TRABAJO DEL SONDEO  --  el motor pide, no interpreta
================================================================================

    py -3.13 tests/test_sondeo_fuentes.py

QUE SE PRUEBA
-------------
'nucleo/programador/trabajos.py::sondeo_de_fuentes', el segundo trabajo cableado.
Lo que importa afirmar:

  * que el motor NO sepa que es SmartOLT. Para este modulo las fuentes son
    nombres que vienen en la respuesta; si manana se agrega una septima, este
    archivo no se toca. Es lo que mantiene generico a 'nucleo/'.
  * que un fallo sea un FALLO -- "no se pudo pedir el sondeo" no es "ninguna
    fuente tiene novedades".
  * que lo que vuelve no lleve datos de cliente ni el resumen entero: solo
    estado, frescura y si se puede concluir.
  * que cuente cuantas fuentes NO permiten concluir nada, que es el numero que
    de un vistazo dice si el Supervisor esta ciego.
  * que cablearlo no lo encienda.

POR QUE NO SE PRUEBA CONTRA DJANGO
----------------------------------
Porque lo que esta en duda es el CONTRATO del trabajo. El lado de Django tiene 77
pruebas propias (operaciones/tests/test_p2_fuentes.py), varias de ellas contra
Postgres real.
================================================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.programador import registro, trabajos          # noqa: E402

_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


ORG = "11111111-2222-3333-4444-555555555555"
OTRA_ORG = "99999999-8888-7777-6666-555555555555"


class Turno:
    def __init__(self, organization_id=ORG, job_code="supervisor_sondeo"):
        self.organization_id = organization_id
        self.job_code = job_code
        self.run_id = "run-1"


class Respuesta:
    def __init__(self, status_code=200, cuerpo=None, revienta_json=False):
        self.status_code = status_code
        self._cuerpo = cuerpo if cuerpo is not None else {}
        self._revienta = revienta_json

    def json(self):
        if self._revienta:
            raise ValueError("no es JSON")
        return self._cuerpo


#  Lo que contesta la ruta del Supervisor. Las claves son las que devuelve
#  'SondeoFuentesView' de verdad.
OK = {
    "organizacion": ORG,
    "sondeadas": 3,
    "fuentes_creadas": 0,
    "escrituras_externas": 0,
    "fuente": "operaciones.fuentes.sondear",
    "por_fuente": {
        "smartolt": {"estado": "no_disponible", "frescura": "sin_dato",
                     "registros": None, "concluyente": False,
                     "dato_en": None, "proxima_consulta_en": "2026-10-02T12:05:00+00:00",
                     "cambio": {"comparable": False, "motivo": "no hay captura anterior",
                                "aparecieron": 0, "desaparecieron": 0, "cambiaron": 0}},
        "dexter": {"estado": "con_datos", "frescura": "fresca", "registros": 4,
                   "concluyente": True, "dato_en": "2026-10-02T11:59:00+00:00",
                   "proxima_consulta_en": "2026-10-02T12:05:00+00:00",
                   "cambio": {"comparable": True, "motivo": "",
                              "aparecieron": 0, "desaparecieron": 0, "cambiaron": 1}},
        "m02": {"estado": "sin_registros", "frescura": "sin_dato",
                "registros": 0, "concluyente": True, "dato_en": None,
                "proxima_consulta_en": "2026-10-02T12:15:00+00:00",
                "cambio": {"comparable": True, "motivo": "",
                           "aparecieron": 0, "desaparecieron": 0, "cambiaron": 0}},
    },
}


class Red:
    """Sustituye la red entera y CUENTA todo lo que salio."""

    def __init__(self, respuesta=None, excepcion=None):
        self.respuesta = respuesta
        self.excepcion = excepcion
        self.posts: list[dict] = []
        self.otros: list[str] = []

    def post(self, url, params=None, headers=None, timeout=None, **k):
        self.posts.append({"url": url, "params": params or {},
                           "headers": headers or {}, "timeout": timeout})
        if self.excepcion is not None:
            raise self.excepcion
        return self.respuesta

    def _prohibido(self, nombre):
        def falso(*a, **k):
            self.otros.append(nombre)
            raise AssertionError(f"el sondeo uso requests.{nombre}")
        return falso


def correr(red, turno=None, token="tok-de-prueba", url=None):
    import os
    import requests

    originales = {v: os.environ.get(v) for v in
                  (trabajos.VARIABLE_TOKEN, trabajos.VARIABLE_URL_SONDEO)}
    verbos = ("get", "post", "put", "patch", "delete", "request")
    guardados = {v: getattr(requests, v, None) for v in verbos}

    if token is None:
        os.environ.pop(trabajos.VARIABLE_TOKEN, None)
    else:
        os.environ[trabajos.VARIABLE_TOKEN] = token
    if url is None:
        os.environ.pop(trabajos.VARIABLE_URL_SONDEO, None)
    else:
        os.environ[trabajos.VARIABLE_URL_SONDEO] = url

    requests.post = red.post
    for v in verbos:
        if v != "post":
            setattr(requests, v, red._prohibido(v))
    try:
        return trabajos.sondeo_de_fuentes(turno or Turno())
    finally:
        for v, f in guardados.items():
            if f is not None:
                setattr(requests, v, f)
        for v, previo in originales.items():
            if previo is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = previo


# ===========================================================================
seccion("1. el camino que tiene que funcionar")
# ===========================================================================

red = Red(Respuesta(200, OK))
r = correr(red)

afirmar(len(red.posts) == 1,
        f"salio UNA sola peticion (fueron {len(red.posts)})")
afirmar(red.otros == [], "y por ningun otro verbo")
afirmar(r["fuentes_sondeadas"] == 3, "devuelve cuantas fuentes se sondearon")
afirmar(set(r["estados"]) == {"smartolt", "dexter", "m02"},
        "y el estado de cada una, con su nombre")

#  EL NUMERO QUE MAS IMPORTA. Dos de las tres fuentes del ejemplo no permiten
#  concluir nada (SmartOLT no disponible). Si esto fuera 0, un tablero diria que
#  todo esta en orden teniendo una fuente ciega.
afirmar(r["no_concluyentes"] == 1,
        "cuenta cuantas fuentes NO permiten concluir nada")
afirmar(r["estados"]["smartolt"]["concluyente"] is False,
        "una fuente no disponible no es concluyente")
afirmar(r["estados"]["m02"]["concluyente"] is True,
        "y una vacia SI lo es: se pudo preguntar y no hay nada")

pedido = red.posts[0]
afirmar(pedido["params"].get("organization_id") == ORG,
        "la organizacion del TURNO viaja en la peticion")
red_otra = Red(Respuesta(200, OK))
correr(red_otra, Turno(organization_id=OTRA_ORG))
afirmar(red_otra.posts[0]["params"].get("organization_id") == OTRA_ORG,
        "y un turno de otra organizacion manda la suya")
afirmar(pedido["headers"].get("Authorization", "").startswith("Bearer "),
        "se autentica con la credencial que el motor ya tiene para el CRM")
afirmar(pedido["timeout"] == trabajos.SEGUNDOS_TIMEOUT_SONDEO,
        f"con timeout declarado ({trabajos.SEGUNDOS_TIMEOUT_SONDEO}s)")
afirmar(trabajos.SEGUNDOS_TIMEOUT_SONDEO > trabajos.SEGUNDOS_TIMEOUT,
        "mas largo que el del latido, porque consulta seis fuentes y dos salen "
        "a un tercero")


# ===========================================================================
seccion("2. el motor no sabe que es SmartOLT")
# ===========================================================================
#  Lo que mantiene generico a 'nucleo/'. Una fuente nueva del otro lado no
#  obliga a tocar este archivo.

fuente_trabajos = (RAIZ / "nucleo" / "programador" / "trabajos.py").read_text(
    encoding="utf-8")

#  SE MIDE EL CODIGO, NO EL TEXTO. Un nombre de sistema en una CADENA o en un
#  identificador seria una dependencia de verdad --el motor decidiendo por
#  fuente--; en un docstring no es nada, y aqui los docstrings precisamente
#  EXPLICAN por que el motor no decide por fuente. La primera version de esta
#  prueba buscaba la palabra y se puso en rojo por esa explicacion: el mismo
#  error que ya aparecio con 'scheduler' y con 'interruptor' el mismo dia.
import ast as _ast  # noqa: E402

_arbol = _ast.parse(fuente_trabajos)
#  Los docstrings son el primer Expr-Constant del cuerpo de un modulo, funcion o
#  clase; se excluyen por posicion, que es como el propio Python los distingue.
_docs = {id(n.body[0].value) for n in _ast.walk(_arbol)
         if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.ClassDef))
         and n.body and isinstance(n.body[0], _ast.Expr)
         and isinstance(n.body[0].value, _ast.Constant)}
_cadenas = [n.value.lower() for n in _ast.walk(_arbol)
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)
            and id(n) not in _docs]
_nombres = {n.id for n in _ast.walk(_arbol) if isinstance(n, _ast.Name)}
_nombres |= {n.attr for n in _ast.walk(_arbol)
             if isinstance(n, _ast.Attribute)}

for sistema in ("smartolt", "wisphub", "dexter"):
    afirmar(not any(sistema in c for c in _cadenas),
            f"ninguna CADENA del motor nombra a '{sistema}'")
    afirmar(not any(sistema in n.lower() for n in _nombres),
            f"ningun identificador del motor nombra a '{sistema}'")

sorpresa = {"sondeadas": 1, "por_fuente": {
    "una_fuente_que_nadie_implemento": {
        "estado": "con_datos", "frescura": "fresca", "concluyente": True}}}
r2 = correr(Red(Respuesta(200, sorpresa)))
afirmar("una_fuente_que_nadie_implemento" in r2["estados"],
        "una fuente que el motor no conoce pasa igual: son nombres, no codigo")


# ===========================================================================
seccion("3. un fallo es un FALLO, nunca 'sin novedades'")
# ===========================================================================

def levanta(red_, **kw):
    try:
        correr(red_, **kw)
        return None
    except trabajos.SondeoFallido as e:
        return e
    except Exception as e:                                        # noqa: BLE001
        return e


e = levanta(Red(Respuesta(200, OK)), token=None)
afirmar(isinstance(e, trabajos.SondeoFallido),
        "sin credencial levanta, no devuelve cero fuentes")
afirmar("BOTTLECRM_API_TOKEN" in str(e), "y dice QUE falta")

for codigo in (403, 409, 500, 502):
    e = levanta(Red(Respuesta(codigo, {})))
    afirmar(isinstance(e, trabajos.SondeoFallido),
            f"un HTTP {codigo} levanta")

import requests as _rq  # noqa: E402

e = levanta(Red(excepcion=_rq.exceptions.Timeout("tardo mucho")))
afirmar(isinstance(e, trabajos.SondeoFallido), "un timeout levanta")
afirmar("Timeout" in str(e), "y se identifica por TIPO")
afirmar("tardo mucho" not in str(e),
        "sin el texto de la excepcion: puede traer la URL, y la URL el id de "
        "la organizacion")

e = levanta(Red(excepcion=_rq.exceptions.ConnectionError(
    "http://backend:8000/api/operaciones/supervisor/sondeo/")))
afirmar(isinstance(e, trabajos.SondeoFallido), "un backend caido levanta")
afirmar("backend:8000" not in str(e), "y la URL no viaja al mensaje")

e = levanta(Red(Respuesta(200, None, revienta_json=True)))
afirmar(isinstance(e, trabajos.SondeoFallido), "un 200 que no es JSON levanta")

e = levanta(Red(Respuesta(200, {})))
afirmar(isinstance(e, trabajos.SondeoFallido),
        "un 200 vacio NO se interpreta como 'ninguna fuente sondeada'")

e = levanta(Red(Respuesta(200, {"sondeadas": "tres", "por_fuente": {}})))
afirmar(isinstance(e, trabajos.SondeoFallido),
        "un conteo que no es numero levanta en vez de inventarlo")

e = levanta(Red(Respuesta(200, {"sondeadas": 2})))
afirmar(isinstance(e, trabajos.SondeoFallido),
        "y un conteo sin el desglose tampoco alcanza")


# ===========================================================================
seccion("4. lo que vuelve no lleva datos de cliente ni el resumen entero")
# ===========================================================================

#  La respuesta del Supervisor podria crecer del otro lado. Lo que el motor
#  guarda se acota ACA tambien, en vez de reenviar lo que venga.
con_evidencia = {
    "sondeadas": 1,
    "por_fuente": {"dexter": {
        "estado": "con_datos", "frescura": "fresca", "concluyente": True,
        #  Cosas que NO tienen por que llegar al informe del tick.
        "evidencia": [{"caso": "CS-1893f29f", "cliente": "Sofia Munoz"}],
        "datos": {"telefono": "3001234567", "direccion": "Calle 1"},
    }},
}
r3 = correr(Red(Respuesta(200, con_evidencia)))
plano = json.dumps(r3)
#  'datos' NO esta en esta lista a proposito: es subcadena de 'con_datos', que
#  es un estado legitimo, y buscarlo da un falso positivo. Lo que de verdad
#  cierra la puerta es la afirmacion de abajo sobre el conjunto EXACTO de claves.
for prohibido in ("evidencia", "cliente", "Sofia", "telefono", "direccion",
                  "CS-1893f29f"):
    afirmar(prohibido not in plano,
            f"lo que vuelve del sondeo no trae '{prohibido}'")
afirmar(set(r3["estados"]["dexter"]) == {"estado", "frescura", "concluyente"},
        "de cada fuente se conservan TRES claves y nada mas")


# ===========================================================================
seccion("5. cablear no es encender")
# ===========================================================================

afirmar(registro.conocido("supervisor_sondeo"),
        "el despliegue SABE hacer 'supervisor_sondeo'")
afirmar(registro.resolver("supervisor_sondeo") is trabajos.sondeo_de_fuentes,
        "y resuelve a esta funcion")
afirmar(sorted(registro.registrados()) == ["supervisor_latido",
                                           "supervisor_sondeo"],
        f"los dos trabajos del Supervisor, y nada mas "
        f"(hay {sorted(registro.registrados())})")
afirmar(not registro.conocido("cerrar_vencidas"),
        "'cerrar_vencidas' sigue SIN cablear: no es idempotente")

try:
    registro.registrar_para_prueba("supervisor_sondeo", lambda t: None)
    afirmar(False, "una prueba NO puede registrar un job real")
except ValueError:
    afirmar(True, "una prueba no puede registrar un job real")

for prohibido in ("while True", "time.sleep", "threading.Thread",
                  "import schedule", "apscheduler", "croniter"):
    afirmar(prohibido not in fuente_trabajos,
            f"el trabajo no trae '{prohibido}': no programa, se deja llamar")


# ===========================================================================
print("\n" + "=" * 74)
if _fallos:
    print(f"  {len(_fallos)} AFIRMACIONES FALLARON")
    for f in _fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  todas las afirmaciones pasaron")
