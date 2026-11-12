# -*- coding: utf-8 -*-
"""
================================================================================
 EL ERROR QUE QUEDA EN LA BASE  --  un metadato, nunca el eco del proveedor
================================================================================

    py -3.13 tests/test_error_guardado_sin_pii.py

QUE SE PRUEBA
-------------
Que cuando una llamada a un sistema externo falla, lo que queda ESCRITO en
nuestras dos tablas de auditoria no lleva datos del cliente.

Las dos columnas:

  * `asistente.operaciones_externas.error`  -- la escribe idempotencia.py
  * `asistente.tool_calls.codigo_error`     -- la escriben tres sitios de
                                               motor.py

CLAUDE.md 5 lo dice de la segunda sin dejar lugar a interpretacion: "la
auditoria (tool_calls) guarda solo metadatos: que se consulto, quien y cuando
-- nunca que decia la respuesta".

EL DEFECTO QUE ESTA GUARDA MATA  --  12/11/2026
-----------------------------------------------
Los cuatro sitios guardaban `f"{type(e).__name__}: {e}"`. El `{e}` de un
`requests.HTTPError` --que es la excepcion que llega cuando el ISP contesta
mal-- es "400 Client Error: Bad Request for url: <LA URL ENTERA>", con la
query puesta. Medido antes del arreglo, con la URL que de verdad arma el
ejecutor al escribir una ubicacion:

  HTTPError: 400 Client Error: Bad Request for url:
  https://api.wisphub.net/api/clientes/5832/?cedula=1098765432
  &localizacion=10.472918,-73.253611

La cedula y el domicilio de una persona, en claro, en una tabla nuestra.
Despues: `HTTPError http_status=400 donde=herramientas/http.py:343`.

Es el mismo defecto que D19/D23 sacaron de la RESPUESTA y D20 del LOG. Esta
capa faltaba, y no se veia desde ninguna de las dos: ni la respuesta HTTP ni
el log pasan por aca.

COMO SE MIDE, Y POR QUE ASI
---------------------------
Por el EFECTO y en el camino real: se corre `idempotencia.ejecutar()` y
`motor.ejecutar_accion_aprobada()` de verdad, con un proveedor que levanta un
`HTTPError` de verdad, y se lee EL VALOR QUE SE LE PASA A LA COLUMNA.

Una prueba que afirmara "el codigo llama a error_para_guardar" no serviria:
es la presencia del mecanismo, y sobrevive intacta el dia que alguien agregue
un quinto sitio con el texto crudo. Lo que se afirma aca es que la cedula y la
coordenada NO estan en el valor que se escribe.

EL DOBLE, Y QUE NO PRUEBA
-------------------------
Se sustituye `db.sesion()` --el cursor-- para poder LEER lo que se escribe sin
una base. Corre el SQL real de `finalizar_operacion_externa`. Lo que esto no
prueba es que la columna exista con ese nombre ni que Postgres la acepte; eso
lo cubren las pruebas con base real.

El cursor es TOLERANTE con las sentencias que no son de esta tabla, al
contrario del de `test_idempotencia_externa.py` que se niega a verlas: aca no
se esta midiendo la superficie SQL, y la frontera manda su propia auditoria
por el mismo camino.
================================================================================
"""
from __future__ import annotations

import contextlib
import copy
import pathlib
import re
import sys
from datetime import datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import requests                                                  # noqa: E402

from nucleo.config.fuente import cargar_config                    # noqa: E402
from nucleo.observabilidad.registro import error_para_guardar     # noqa: E402
from nucleo.persistencia import db as persistencia                # noqa: E402

FALLOS: list[str] = []


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {que}")
    else:
        FALLOS.append(que)
        print(f"  [FALLA] {que}")
        if detalle:
            print(f"          {detalle}")


def seccion(titulo: str) -> None:
    print()
    print("-" * 78)
    print(f"  {titulo}")
    print("-" * 78)


# =============================================================================
#  LOS DATOS  --  inventados, ninguno de un cliente real
# =============================================================================
CEDULA = "1098765432"
LAT, LNG = "10.472918", "-73.253611"
URL_CON_TODO = (f"https://api.wisphub.net/api/clientes/5832/"
                f"?cedula={CEDULA}&localizacion={LAT},{LNG}")

#  Lo que NO puede aparecer en ninguna de las dos columnas.
PROHIBIDOS = ((CEDULA, "la cedula"), (LAT, "la latitud"), (LNG, "la longitud"),
              ("://", "la URL"), ("wisphub", "el proveedor"))


def error_http(status: int = 400) -> requests.HTTPError:
    """Un HTTPError como el que levanta `r.raise_for_status()` de verdad.

    Se LEVANTA y se atrapa en vez de construirse: sin traza no hay
    `archivo:linea`, y una de las cosas que se afirma es que ese dato sigue
    estando.
    """
    r = requests.Response()
    r.status_code = status
    r.reason = "Bad Request"
    r.url = URL_CON_TODO
    try:
        raise requests.HTTPError(
            f"{status} Client Error: Bad Request for url: {URL_CON_TODO}",
            response=r)
    except requests.HTTPError as e:
        return e


def sin_datos_del_cliente(valor: str, donde: str) -> None:
    """Afirma, dato por dato, que ninguno sobrevivio."""
    for dato, como in PROHIBIDOS:
        afirmar(dato not in valor, f"{donde}: no lleva {como}",
                f"quedo: {valor!r}")


# =============================================================================
#  1 . EL REDUCTOR  --  que saca y que deja
# =============================================================================
seccion("1 . el reductor: saca el texto ajeno, deja con que diagnosticar")

e = error_http(400)
guardado = error_para_guardar(e)
print(f"  texto crudo : {type(e).__name__}: {e}"[:150])
print(f"  guardado    : {guardado}")

sin_datos_del_cliente(guardado, "el reductor")

#  Y LO QUE TIENE QUE SEGUIR ESTANDO. Un reductor que devuelva "" cumpliria lo
#  de arriba y no serviria para nada: estas tres afirmaciones son las que lo
#  impiden.
afirmar("HTTPError" in guardado, "el reductor: dice de que tipo fue el fallo")
afirmar("http_status=400" in guardado,
        "el reductor: dice que contesto el proveedor", guardado)

#  `donde=` NO SE AFIRMA ACA, Y EL MOTIVO IMPORTA. `_donde()` solo reporta
#  cuadros de la traza que son codigo del nucleo, y la excepcion de esta
#  seccion se levanta en este archivo de prueba -- que no lo es. Afirmarlo aca
#  seria afirmar algo sobre el entorno de la prueba.
#
#  Se afirma en las secciones 2 y 3, donde el `raise` ocurre de verdad dentro
#  del nucleo. Ahi vale, y ahi es donde sirve.

#  EL LIMITE SE RESPETA, y no por prolijidad: la columna recorta a 2000 y el
#  codigo_error de tool_calls lo lee una pantalla.
largo = error_para_guardar(e, limite=12)
afirmar(len(largo) <= 12, "el reductor: respeta el limite que se le pide", largo)

#  UNA EXCEPCION DE POSTGRES: su texto trae el VALOR de la fila que la rompio.
#  Lo que sirve --el sqlstate y la restriccion-- no es el texto.
class _Diag:
    constraint_name = "operaciones_externas_pkey"
    table_name = "operaciones_externas"


class ErrorDeBase(Exception):
    sqlstate = "23505"
    diag = _Diag()


try:
    raise ErrorDeBase(f"duplicate key value violates unique constraint: "
                      f"Key (cedula)=({CEDULA}) already exists.")
except ErrorDeBase as eb:
    de_base = error_para_guardar(eb)
print(f"  de Postgres : {de_base}")
sin_datos_del_cliente(de_base, "un error de Postgres")
afirmar("23505" in de_base and "operaciones_externas_pkey" in de_base,
        "un error de Postgres: deja el sqlstate y la restriccion", de_base)


# =============================================================================
#  EL DOBLE  --  para poder leer lo que se escribe, sin una base
# =============================================================================
class Columna:
    """Lo ultimo que se le paso a `operaciones_externas.error`."""

    def __init__(self):
        self.error: str | None = None
        self.estado: str | None = None
        self.filas: dict[tuple, dict] = {}


class Cursor:
    def __init__(self, col: Columna, org: str):
        self.col = col
        self.org = org
        self._fila = None

    def execute(self, sql: str, params=()):
        s = " ".join(sql.split()).lower()
        self._fila = None
        if s.startswith("insert into asistente.operaciones_externas"):
            org, clave, herr, huella, origen = params
            ahora = datetime.now(timezone.utc)
            if (org, clave) in self.col.filas:
                return
            self.col.filas[(org, clave)] = {
                "clave": clave, "herramienta": herr, "argumentos_hash": huella,
                "estado": "ejecutando", "origen": origen, "intentos": 1,
                "respuesta": None, "error": None, "creado_en": ahora,
                "ejecutado_en": None, "actualizado_en": ahora}
            self._fila = dict(self.col.filas[(org, clave)])
            return
        if "from asistente.operaciones_externas" in s and "for update" in s:
            org, clave = params
            fila = self.col.filas.get((org, clave))
            self._fila = dict(fila) if fila else None
            return
        if "update asistente.operaciones_externas" in s and "set estado = %s" in s:
            estado, _respuesta, error, org, clave = params
            fila = self.col.filas.get((org, clave))
            if fila is not None and fila["estado"] == "ejecutando":
                fila["estado"] = estado
                fila["error"] = error
                #  LO QUE ESTA PRUEBA MIDE: el valor que viaja a la columna.
                self.col.estado = estado
                self.col.error = error
            return
        #  Cualquier otra: la frontera manda su auditoria por este mismo
        #  camino. No se afirma nada sobre ella aca.
        return

    def fetchone(self):
        return self._fila

    def fetchall(self):
        return []


@contextlib.contextmanager
def banco(col: Columna):
    original = persistencia.sesion

    @contextlib.contextmanager
    def _sesion(tenant: str):
        yield Cursor(col, f"org-{tenant}"), f"org-{tenant}"

    persistencia.sesion = _sesion
    try:
        yield
    finally:
        persistencia.sesion = original


# =============================================================================
#  2 . EL CAMINO REAL DE idempotencia  --  operaciones_externas.error
# =============================================================================
seccion("2 . el camino real: que queda en operaciones_externas.error")

from nucleo.seguridad import frontera, idempotencia              # noqa: E402

CONFIG = copy.deepcopy(cargar_config(RAIZ / "tenants" / "rapilink.config.yaml"))
TENANT = CONFIG.identidad.slug

col = Columna()
reventó = False
with banco(col):
    def _falla():
        raise error_http(502)

    try:
        with frontera.humana(TENANT, "prueba_de_error", actor="suite",
                             evidencia="test_error_guardado_sin_pii",
                             origen="test_error_guardado_sin_pii"):
            idempotencia.ejecutar(TENANT, "prueba_de_error",
                                  {"localizacion": f"{LAT},{LNG}"},
                                  "test_error_guardado_sin_pii", _falla)
    except requests.HTTPError:
        #  Se vuelve a levantar a proposito: quien llama tiene que enterarse.
        #  Lo que se mide es lo que quedo escrito ANTES de eso.
        reventó = True

afirmar(reventó, "la excepcion se sigue propagando a quien llamo")
afirmar(col.estado == "fallida",
        "la operacion queda marcada 'fallida'", str(col.estado))
afirmar(col.error is not None,
        "y con un error escrito -- si fuera None esto no probaria nada",
        str(col.error))
print(f"  en la columna: {col.error}")
if col.error:
    sin_datos_del_cliente(col.error, "operaciones_externas.error")
    afirmar("HTTPError" in col.error and "502" in col.error,
            "operaciones_externas.error: sigue sirviendo para diagnosticar",
            col.error)
    #  ACA SI SE AFIRMA `donde=`: el `raise` paso por dentro del nucleo, que
    #  es la unica condicion en la que `_donde()` tiene algo que decir.
    afirmar(re.search(r"donde=[\w/.]+\.py:\d+", col.error) is not None,
            "operaciones_externas.error: dice en que archivo y linea",
            col.error)


# =============================================================================
#  3 . EL CAMINO REAL DE motor  --  tool_calls.codigo_error
# =============================================================================
seccion("3 . el camino real: que queda en tool_calls.codigo_error")

from nucleo.herramientas import http as ejecutor_http            # noqa: E402
from nucleo.modelo import motor                                   # noqa: E402

#  Una herramienta http que NO sea irreversible: una irreversible por este
#  camino la frena M06-A antes de llegar al proveedor, y entonces el codigo
#  seria el del gate y no el del error -- la prueba mediria otra cosa.
candidata = next((h for h in CONFIG.herramientas
                  if getattr(h, "tipo", None) == "http"
                  and not getattr(h, "irreversible", False)
                  and not getattr(h, "asincrona", False)), None)
afirmar(candidata is not None,
        "el tenant declara alguna herramienta http no irreversible")

if candidata is not None:
    original_ejecutar = ejecutor_http.ejecutar

    def _ejecutar_que_falla(*_a, **_k):
        raise error_http(404)

    col3 = Columna()
    ejecutor_http.ejecutar = _ejecutar_que_falla
    try:
        with banco(col3):
            _salida, codigo = motor.ejecutar_accion_aprobada(
                CONFIG, {"id": "propuesta-de-prueba",
                         "herramienta": candidata.nombre,
                         "argumentos": {"localizacion": f"{LAT},{LNG}"},
                         "aprobada_por": "suite"})
    finally:
        ejecutor_http.ejecutar = original_ejecutar

    print(f"  codigo_error : {codigo}")
    afirmar(codigo is not None,
            "la accion aprobada que falla devuelve un codigo_error",
            str(codigo))
    if codigo:
        sin_datos_del_cliente(str(codigo), "tool_calls.codigo_error")
        afirmar("HTTPError" in str(codigo),
                "tool_calls.codigo_error: sigue diciendo que fallo", str(codigo))
        afirmar(re.search(r"donde=[\w/.]+\.py:\d+", str(codigo)) is not None,
                "tool_calls.codigo_error: dice en que archivo y linea",
                str(codigo))


# =============================================================================
#  4 . QUE NO VUELVA A ENTRAR  --  un rastreo, y se dice que es un rastreo
# =============================================================================
seccion("4 . ningun sitio que ESCRIBA en la base interpola la excepcion")

#  ESTO ES UN RASTREO DE TEXTO, NO UNA AFIRMACION SOBRE EL EFECTO, y la
#  diferencia se declara porque CLAUDE.md 6 la exige: lo que mide es que
#  nadie vuelva a escribir el patron en estos archivos. Un quinto sitio en un
#  archivo nuevo no lo veria. Las secciones 2 y 3 son las que prueban que lo
#  que se escribe esta limpio.
PATRON = re.compile(r"__name__\}:\s*\{e(?:xc)?\}")
ESCRIBEN_EN_LA_BASE = (
    "nucleo/seguridad/idempotencia.py",
    "nucleo/modelo/motor.py",
)
#  LOS COMENTARIOS NO CUENTAN, y lo descubrio esta misma prueba en su primera
#  corrida: el comentario que explica el arreglo CITA el patron viejo, y el
#  rastreo lo marco como defecto. Un rastreo que castiga explicar el defecto
#  enseña a borrar la explicacion, que es lo contrario de lo que este
#  repositorio hace.
for rel in ESCRIBEN_EN_LA_BASE:
    texto = (RAIZ / rel).read_text(encoding="utf-8")
    apariciones = [n for n, linea in enumerate(texto.splitlines(), 1)
                   if PATRON.search(linea)
                   and not linea.lstrip().startswith("#")]
    afirmar(not apariciones,
            f"{rel}: no interpola el texto de la excepcion",
            f"lineas {apariciones}" if apariciones else "")


# =============================================================================
print()
print("=" * 78)
if FALLOS:
    print(f"  {len(FALLOS)} FALLO(S):")
    for f in FALLOS:
        print(f"    - {f}")
    sys.exit(1)
print("  TODO EN VERDE -- el error que queda en la base es un metadato")
print("=" * 78)
