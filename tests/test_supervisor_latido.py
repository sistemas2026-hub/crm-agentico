# -*- coding: utf-8 -*-
"""
================================================================================
 EL LATIDO DEL SUPERVISOR  --  que el scheduler lo despierte, y nada mas
================================================================================

    py -3.13 tests/test_supervisor_latido.py

QUE SE PRUEBA
-------------
El primer trabajo cableado en 'nucleo/programador/registro.py'. Es de LECTURA:
le pregunta al Supervisor que ve y guarda conteos. Lo que hay que afirmar no es
que "funcione", sino las cosas que podrian salir mal sin que nadie las note:

  * que NO produzca ningun efecto -- ni una escritura, ni una llamada a un
    proveedor, ni nada que no sea el GET al backend;
  * que un fallo sea un FALLO y no un cero -- "no se pudo preguntar" no es "no
    hay senales", y confundirlos es como un tablero empieza a mentir;
  * que el tenant viaje y se compruebe;
  * que lo que vuelve no lleve datos de cliente -- va al informe del tick y
    al log, NO a una tabla: 'job_run' no tiene columna de salida (medido el
    02/10/2026, ver tests/test_latido_extremo_a_extremo.py);
  * que cablear el trabajo NO lo encienda.

LA ULTIMA ES LA QUE MAS IMPORTA. El scheduler sigue inerte: el catalogo decide
que corre, y el catalogo esta vacio. Esta suite afirma que el cableado no abrio
esa puerta -- es lo mismo que mide 'tests/test_p2_inerte.py', comprobado aqui
desde el otro lado.

POR QUE NO SE PRUEBA CONTRA UN BACKEND DE VERDAD
------------------------------------------------
Porque lo que esta en duda es el CONTRATO del trabajo, no si Django responde.
Se sustituye 'requests.get' y se mide que se le pidio y que se hizo con lo que
contesto. El lado de Django tiene su propia suite.
================================================================================
"""

from __future__ import annotations

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


# ===========================================================================
#  andamio
# ===========================================================================

ORG = "11111111-2222-3333-4444-555555555555"
OTRA_ORG = "99999999-8888-7777-6666-555555555555"


class Turno:
    """Lo minimo que el trabajo le pide al turno real."""

    def __init__(self, organization_id=ORG, job_code="supervisor_latido"):
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


OK = {
    "organizacion": ORG,
    "leido_en": "2026-10-02T12:00:00+00:00",
    "senales_vigentes": 3,
    "senales_por_tipo": {"caso_desincronizado": 2, "caso_abierto_antiguo": 1},
    "escrituras": 0,
    "fuente": "operaciones.supervisor.detectar",
}


class Red:
    """Sustituye la red entera y CUENTA todo lo que salio."""

    def __init__(self, respuesta=None, excepcion=None):
        self.respuesta = respuesta
        self.excepcion = excepcion
        self.gets: list[tuple] = []
        self.otros: list[str] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.gets.append({"url": url, "params": params or {},
                          "headers": headers or {}, "timeout": timeout})
        if self.excepcion is not None:
            raise self.excepcion
        return self.respuesta

    def _prohibido(self, nombre):
        def falso(*a, **k):
            self.otros.append(nombre)
            raise AssertionError(
                f"el latido uso requests.{nombre}: tiene que ser una LECTURA")
        return falso


def correr(red, turno=None, token="tok-de-prueba", url=None):
    """Corre el trabajo con la red y el entorno sustituidos. Devuelve lo que sea."""
    import os
    import requests

    originales = {v: os.environ.get(v) for v in
                  (trabajos.VARIABLE_TOKEN, trabajos.VARIABLE_URL)}
    verbos = ("get", "post", "put", "patch", "delete", "request")
    guardados = {v: getattr(requests, v, None) for v in verbos}

    if token is None:
        os.environ.pop(trabajos.VARIABLE_TOKEN, None)
    else:
        os.environ[trabajos.VARIABLE_TOKEN] = token
    if url is None:
        os.environ.pop(trabajos.VARIABLE_URL, None)
    else:
        os.environ[trabajos.VARIABLE_URL] = url

    requests.get = red.get
    for v in verbos:
        if v != "get":
            setattr(requests, v, red._prohibido(v))
    try:
        return trabajos.latido_supervisor(turno or Turno())
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

afirmar(len(red.gets) == 1,
        f"salio UNA sola peticion (fueron {len(red.gets)})")
afirmar(red.otros == [],
        "y ninguna de escritura: el latido solo LEE")
afirmar(r["senales_vigentes"] == 3, "devuelve cuantas senales ve el Supervisor")
afirmar(r["senales_por_tipo"] == {"caso_desincronizado": 2,
                                  "caso_abierto_antiguo": 1},
        "y el desglose por tipo")
afirmar(r["escrituras"] == 0,
        "declara que no hubo escrituras, copiandolo del backend")

# ---------------------------------------------------------------------------
#  EL TENANT VIAJA. Sale del turno --que se deriva de la base-- y no de una
#  variable de entorno ni del coordinador.
pedido = red.gets[0]
afirmar(pedido["params"].get("organization_id") == ORG,
        "la organizacion del TURNO viaja en la peticion")
red_otra = Red(Respuesta(200, OK))
correr(red_otra, Turno(organization_id=OTRA_ORG))
afirmar(red_otra.gets[0]["params"].get("organization_id") == OTRA_ORG,
        "y un turno de otra organizacion manda la suya, no la de antes")

# ---------------------------------------------------------------------------
#  AUTENTICACION
afirmar(pedido["headers"].get("Authorization", "").startswith("Bearer "),
        "se autentica con la credencial que el motor ya tiene para el CRM")
afirmar("tok-de-prueba" in pedido["headers"].get("Authorization", ""),
        "y manda el token, no otra cosa")
afirmar(pedido["timeout"] == trabajos.SEGUNDOS_TIMEOUT,
        f"con timeout declarado ({trabajos.SEGUNDOS_TIMEOUT}s), no sin limite")

# ---------------------------------------------------------------------------
#  LO QUE VUELVE NO LLEVA DATOS DE CLIENTE. Se afirma sobre el contenido
#  SERIALIZADO, no sobre las claves: una evidencia anidada no se veria mirando
#  solo el primer nivel.
#
#  A DONDE VA: al informe en memoria del tick y a la linea de log. NO a una
#  tabla -- 'job_run' no tiene columna de salida. Igual importa, y por el mismo
#  motivo: ese informe se imprime y se registra.
import json  # noqa: E402

plano = json.dumps(r)
for prohibido in ("origen_id", "evidencia", "cliente", "telefono", "cedula",
                  "direccion", "coordenadas"):
    afirmar(prohibido not in plano,
            f"lo que vuelve del latido no trae '{prohibido}'")


# ===========================================================================
seccion("2. un fallo es un FALLO, nunca un cero")
# ===========================================================================
#  La distincion que el proyecto ya hace en otros lados: "no se pudo medir" no
#  es "no hay". Si el latido devolviera 0 ante un error, un tablero diria
#  "ninguna senal" justo cuando el Supervisor esta ciego.

def levanta(red_, **kw):
    try:
        correr(red_, **kw)
        return None
    except trabajos.LatidoFallido as e:
        return e
    except Exception as e:                                    # noqa: BLE001
        return e


e = levanta(Red(Respuesta(200, OK)), token=None)
afirmar(isinstance(e, trabajos.LatidoFallido),
        "sin credencial levanta, no devuelve cero")
afirmar("BOTTLECRM_API_TOKEN" in str(e),
        "y dice QUE falta, para que nadie lo busque en el codigo")

e = levanta(Red(Respuesta(500, {})))
afirmar(isinstance(e, trabajos.LatidoFallido), "un 500 del backend levanta")
afirmar("500" in str(e), "y el codigo HTTP queda en el motivo")

e = levanta(Red(Respuesta(403, {})))
afirmar(isinstance(e, trabajos.LatidoFallido),
        "un 403 --credencial sin alcance-- tambien levanta")

e = levanta(Red(Respuesta(409, {})))
afirmar(isinstance(e, trabajos.LatidoFallido),
        "y un 409 --el turno apunta a otra organizacion-- no se toma como exito")

#  TIMEOUT. Se simula la excepcion que 'requests' levanta de verdad.
import requests as _rq  # noqa: E402

e = levanta(Red(excepcion=_rq.exceptions.Timeout("tardo")))
afirmar(isinstance(e, trabajos.LatidoFallido), "un timeout levanta")
afirmar("Timeout" in str(e), "y se identifica por TIPO")
afirmar("tardo" not in str(e),
        "sin el texto de la excepcion: puede traer la URL, y la URL el id de "
        "la organizacion")

e = levanta(Red(excepcion=_rq.exceptions.ConnectionError("http://backend:8000/...")))
afirmar(isinstance(e, trabajos.LatidoFallido), "un backend caido levanta")
afirmar("backend:8000" not in str(e), "y la URL no viaja al mensaje")

e = levanta(Red(Respuesta(200, None, revienta_json=True)))
afirmar(isinstance(e, trabajos.LatidoFallido), "un 200 que no es JSON levanta")

e = levanta(Red(Respuesta(200, {"senales_vigentes": "tres"})))
afirmar(isinstance(e, trabajos.LatidoFallido),
        "un 200 con conteos que no son numeros levanta en vez de inventarlos")

e = levanta(Red(Respuesta(200, {})))
afirmar(isinstance(e, trabajos.LatidoFallido),
        "y un 200 vacio tampoco se interpreta como 'cero senales'")


# ===========================================================================
seccion("3. recuperacion: el trabajo no guarda estado entre turnos")
# ===========================================================================
#  Tras un fallo, el siguiente turno funciona sin que nadie limpie nada. El
#  estado del scheduler vive en la base, no en este modulo.

levanta(Red(Respuesta(500, {})))
r2 = correr(Red(Respuesta(200, OK)))
afirmar(r2["senales_vigentes"] == 3,
        "despues de un fallo, el turno siguiente corre normal")

#  IDEMPOTENCIA POR NATURALEZA: dos turnos iguales no acumulan nada, porque el
#  trabajo no escribe. Se afirma sobre el efecto -- misma salida, y cero
#  peticiones que no sean GET.
red_a, red_b = Red(Respuesta(200, OK)), Red(Respuesta(200, OK))
afirmar(correr(red_a) == correr(red_b),
        "dos turnos identicos dan el mismo resultado")
afirmar(red_a.otros == [] and red_b.otros == [],
        "y ninguno escribio nada: repetirlo no tiene efecto que deshacer")


# ===========================================================================
seccion("4. cablear no es encender")
# ===========================================================================

afirmar(registro.conocido("supervisor_latido"),
        "el despliegue SABE hacer 'supervisor_latido'")
afirmar(registro.resolver("supervisor_latido") is trabajos.latido_supervisor,
        "y resuelve a esta funcion, no a otra")

#  Lo que sigue bloqueado, y es la garantia de que el cableado no abrio la
#  puerta de par en par.
afirmar(not registro.conocido("cerrar_vencidas"),
        "'cerrar_vencidas' sigue SIN cablear: no es idempotente")
afirmar(not registro.conocido("importacion_tickets"),
        "'importacion_tickets' sigue sin cablear: es P5")
afirmar(sorted(registro.registrados()) == ["supervisor_latido"],
        f"hay UN solo trabajo cableado "
        f"(hay {sorted(registro.registrados())})")

#  Y la puerta de pruebas sigue sin poder registrar un job real.
try:
    registro.registrar_para_prueba("supervisor_latido", lambda t: None)
    afirmar(False, "una prueba NO puede registrar un job real")
except ValueError:
    afirmar(True, "una prueba no puede registrar un job real: levanta ValueError")


# ===========================================================================
seccion("5. no se creo un segundo scheduler")
# ===========================================================================
#  Afirmado sobre el codigo, no sobre la intencion: se cuenta quien define un
#  bucle de turnos. Si manana alguien agrega otro, esto se pone en rojo.

import re  # noqa: E402

fuentes = [p for p in (RAIZ / "nucleo").rglob("*.py")]
fuentes += [p for p in (RAIZ / "cli").rglob("*.py")]
coordinadores = [p for p in fuentes
                 if re.search(r"^def correr\(.*tick", p.read_text(encoding="utf-8"),
                              re.M)]
afirmar(len(coordinadores) == 1,
        f"hay UN solo bucle de turnos en el repo "
        f"({[p.name for p in coordinadores]})")
afirmar(coordinadores and coordinadores[0].name == "coordinador.py",
        "y es 'nucleo/programador/coordinador.py', el que ya existia")

fuente_trabajos = (RAIZ / "nucleo" / "programador" / "trabajos.py").read_text(
    encoding="utf-8")
#  'schedule'/'apscheduler'/'croniter' se buscan como IMPORT y no como palabra:
#  el docstring dice "scheduler" a proposito, y una afirmacion que no distingue
#  una mencion de una dependencia se pone en rojo por lo que no importa.
for prohibido in ("while True", "time.sleep", "threading.Thread",
                  "import schedule", "apscheduler", "croniter"):
    afirmar(prohibido not in fuente_trabajos,
            f"el trabajo nuevo no trae '{prohibido}': no programa, se deja llamar")


# ===========================================================================
print("\n" + "=" * 74)
if _fallos:
    print(f"  {len(_fallos)} AFIRMACIONES FALLARON")
    for f in _fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  todas las afirmaciones pasaron")
