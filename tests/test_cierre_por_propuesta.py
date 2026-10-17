# -*- coding: utf-8 -*-
"""
================================================================================
 EL CIERRE QUE AUTORIZA UNA PERSONA  --  que de verdad SALGA, y una sola vez
================================================================================

    py -3.13 tests/test_cierre_por_propuesta.py

POR QUE ESTE ARCHIVO EXISTE, Y POR QUE NO EXISTIA ANTES
-------------------------------------------------------
'nucleo/seguimiento/cierre_por_propuesta.py' no tenia NINGUNA prueba. Las 189
del lado de Django sustituyen '_pedirle_al_motor', asi que validan las doce
condiciones, la trazabilidad y que el caso no se mueva -- y nunca cruzan al
motor. El modulo entero quedo sin guarda.

Lo destapo una prueba real en produccion el 30/09/2026, ticket 93223: las doce
validaciones pasaron, la lectura estaba fresca, y la bitacora quedo en
'NO_EJECUTADA / ACCION_EXTERNA_SIN_AUTORIZAR' con CERO filas en
'asistente.operaciones_externas'. El cierre no se habia caido: nunca se habia
intentado.

La causa era un orden invertido. 'idempotencia.ejecutar' comprueba el permiso
de la frontera ANTES de llamar a lo que se le pasa (paso 10.14A), y este modulo
abria la puerta DENTRO de esa funcion. O sea que la puerta se abria despues de
que alguien ya habia preguntado si estaba abierta. El cierre NUNCA pudo
ejecutarse.

QUE SE AFIRMA, Y COMO
---------------------
Sobre el EFECTO: que la mutacion le llega al proveedor. No sobre la presencia
del 'with' ni sobre el orden de las lineas -- un test que leyera el codigo
volveria a pasar el dia que alguien lo reordene con la misma buena intencion
que la primera vez.

Lo que NO se sustituye, a proposito, es 'idempotencia.ejecutar': es justo la
pieza que consulta el permiso, y reemplazarla volveria a esconder el defecto.
Se sustituye la capa de ABAJO --el registro en la base-- y la de ARRIBA --la
llamada HTTP-- que son las dos que necesitan infraestructura.

Y no se abre ningun permiso desde la suite: si esta prueba pasara con un
permiso abierto por el andamio, no estaria probando nada. La unica puerta que
puede abrirse es la que abre el modulo bajo prueba.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.persistencia import db as persistencia          # noqa: E402
from nucleo.seguimiento import cierre_por_propuesta as cierre  # noqa: E402
from nucleo.seguridad import frontera                       # noqa: E402
from nucleo.seguridad import idempotencia                   # noqa: E402

TENANT = "tenant-de-prueba"
PROPUESTA = "11111111-2222-3333-4444-555555555555"
CASO = "99999999-8888-7777-6666-555555555555"

_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


# ===========================================================================
#  andamio  --  lo minimo para que el modulo corra sin base ni red
# ===========================================================================

class Herramienta:
    """La declaracion de 'cerrar_caso_crm', con lo que el modulo le pide."""

    nombre = "cerrar_caso_crm"
    cierra_caso = True
    argumentos_fijos = {"status": "Closed"}
    fechas_automaticas: dict = {}
    formato_fechas_automaticas = "%Y-%m-%d"


class Config:
    herramientas = [Herramienta()]
    variables_tenant: dict = {}


class Veredicto:
    def __init__(self, permitido=True, estado="activo", motivo=""):
        self.permitido = permitido
        self.estado = estado
        self.motivo = motivo


class Registro:
    """
    'asistente.operaciones_externas' en memoria, con su misma semantica.

    Lo unico que imita es la decision: la primera vez 'ejecutar', y despues
    'repetida' para la MISMA clave. La exclusion real la da la clave primaria
    en Postgres y eso se prueba en 'tests/test_idempotencia_externa.py'; aca
    lo que importa es que este modulo reaccione bien a cada decision.
    """

    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.reclamos: list[str] = []
        self.finalizados: list[tuple] = []

    def reclamar(self, tenant, clave, herramienta, argumentos_hash, origen,
                 segundos_vencida, reintentar_fallida=False):
        self.reclamos.append(clave)
        fila = self.filas.get(clave)
        if fila is None:
            self.filas[clave] = {"intentos": 1, "estado": "ejecutando",
                                 "respuesta": None}
            return {"decision": "ejecutar", "fila": self.filas[clave]}
        if fila["estado"] == "exitosa":
            return {"decision": "repetida", "fila": fila}
        return {"decision": "en_curso", "fila": fila}

    def finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        self.finalizados.append((clave, estado))
        fila = self.filas.setdefault(clave, {"intentos": 1})
        fila["estado"] = estado
        fila["respuesta"] = respuesta


class Proveedor:
    """Cuenta cuantas veces le llego la mutacion, y con que permiso vigente."""

    def __init__(self):
        self.llamadas: list[dict] = []
        self.permisos: list = []

    def ejecutar(self, herramienta, argumentos, tenant, variables_tenant=None):
        self.llamadas.append(dict(argumentos))
        self.permisos.append(frontera.permiso_vigente())
        return {"id": argumentos.get("id_caso"), "status": "Closed"}


@contextlib.contextmanager
def escenario(registro: Registro, proveedor: Proveedor,
              permitido: bool = True):
    """
    Sustituye la base, la red y el interruptor. NO abre ningun permiso.

    Que la suite no abra la puerta es la mitad de lo que esta prueba mide: si
    la abriera, el modulo podria seguir teniendo el orden invertido y pasar
    igual, que es exactamente como el defecto sobrevivio hasta produccion.
    """
    #  El modulo importa 'interruptor' y 'http' DENTRO de la funcion, asi que
    #  se sustituyen en su modulo de origen: es lo que el import va a resolver.
    import nucleo.herramientas.http as ejecutor_http
    from nucleo.seguridad import interruptor

    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa,
                  interruptor.veredicto,
                  interruptor.anotar_bloqueo,
                  ejecutor_http.ejecutar)
    persistencia.reclamar_operacion_externa = registro.reclamar
    persistencia.finalizar_operacion_externa = registro.finalizar
    interruptor.veredicto = lambda t: Veredicto(permitido)
    interruptor.anotar_bloqueo = lambda *a, **k: None
    ejecutor_http.ejecutar = proveedor.ejecutar
    try:
        afirmar(frontera.permiso_vigente() is None,
                "el andamio NO deja ningun permiso abierto: la unica puerta "
                "posible es la que abra el modulo bajo prueba")
        yield
    finally:
        (persistencia.reclamar_operacion_externa,
         persistencia.finalizar_operacion_externa,
         interruptor.veredicto,
         interruptor.anotar_bloqueo,
         ejecutor_http.ejecutar) = originales


def cerrar(actor="jefe-de-operaciones", propuesta=PROPUESTA):
    return cierre.cerrar_caso_de_propuesta(
        Config(), TENANT, propuesta_id=propuesta, id_caso=CASO, actor=actor)


# ===========================================================================
seccion("1. el flujo real: la mutacion SALE, y sale con permiso humano")
# ===========================================================================
#  La regresion del 30/09/2026 en una sola afirmacion: 'llamadas == 1'. Con el
#  orden invertido este numero era 0 y el resultado 'NO_EJECUTADA'.

registro = Registro()
proveedor = Proveedor()
with escenario(registro, proveedor):
    r = cerrar()

afirmar(r.cerrado, "la propuesta aceptada cierra el caso")
afirmar(r.codigo == cierre.CERRADO, f"el codigo es CERRADO (fue {r.codigo!r})")
afirmar(len(proveedor.llamadas) == 1,
        f"'cerrar_caso_crm' se alcanzo UNA vez (fueron {len(proveedor.llamadas)})")

# ---------------------------------------------------------------------------
#  EL CORAZON DE LA GUARDA. No se afirma que exista un 'with' en el fuente: se
#  afirma que, EN EL MOMENTO en que la mutacion salio, habia un permiso humano
#  vigente con su actor y su evidencia. Es lo que 'idempotencia.ejecutar'
#  comprueba, y es lo que el orden invertido rompia.
permiso = proveedor.permisos[0] if proveedor.permisos else None
afirmar(permiso is not None,
        "habia un permiso de la frontera vigente cuando salio la mutacion")
afirmar(permiso is not None and permiso.clase == "humana",
        "y es un permiso HUMANO, no autonomo: lo decidio una persona")
afirmar(permiso is not None and permiso.actor == "jefe-de-operaciones",
        "el permiso dice QUIEN decidio")
afirmar(permiso is not None and permiso.evidencia == f"propuesta:{PROPUESTA}",
        "y contra que registro se comprueba: el id de la propuesta")

afirmar(len(registro.reclamos) == 1,
        "la idempotencia reclamo la operacion una vez")
#  Sin el 'and' de guarda, una regresion que deja 'reclamos' vacio revienta con
#  IndexError y la suite muere en la mitad, sin decir las afirmaciones que
#  faltaban. Una prueba que falla tiene que seguir contando lo que mide.
afirmar(bool(registro.reclamos)
        and registro.finalizados == [(registro.reclamos[0], "exitosa")],
        "y la cerro como exitosa")

# ---------------------------------------------------------------------------
#  Lo que se manda es lo que declara la herramienta, no lo que trae el
#  llamador: 'status' sale de 'argumentos_fijos' y el unico aporte es el caso.
enviado = proveedor.llamadas[0] if proveedor.llamadas else {}
afirmar(enviado.get("status") == "Closed",
        "el estado de cierre sale de la declaracion de la herramienta")
afirmar(enviado.get("id_caso") == CASO, "y apunta al caso que se autorizo")
afirmar(set(enviado) == {"status", "id_caso"},
        "y nada mas viaja: ni el llamador ni el modelo agregan parametros")

# ---------------------------------------------------------------------------
#  TRAZABILIDAD. 'referencia' es la clave idempotente, que es lo que el CRM
#  guarda en 'accion_propuesta_ref' -- no un id inventado aca.
afirmar(r.referencia == f"propuesta:{PROPUESTA}",
        "la referencia que vuelve es el origen, que es la clave idempotente")

# ---------------------------------------------------------------------------
#  Y el permiso NO queda abierto despues: se cierra con el 'with'.
afirmar(frontera.permiso_vigente() is None,
        "al terminar no queda ningun permiso colgado en el contexto")


# ===========================================================================
seccion("2. idempotencia: la misma propuesta no cierra el caso dos veces")
# ===========================================================================
#  Mismo origen -> misma clave -> el registro contesta 'repetida'. Lo que se
#  mide es que el PROVEEDOR no reciba una segunda llamada, no que el codigo
#  diga algo.

registro2 = Registro()
proveedor2 = Proveedor()
with escenario(registro2, proveedor2):
    primero = cerrar()
    segundo = cerrar()

afirmar(primero.cerrado and segundo.cerrado,
        "los dos intentos contestan 'cerrado'")
afirmar(len(proveedor2.llamadas) == 1,
        f"pero la mutacion salio UNA sola vez (salieron "
        f"{len(proveedor2.llamadas)})")
afirmar(segundo.motivo == "ya se habia ejecutado antes",
        "y el segundo lo dice: no se repitio el efecto")
afirmar(len(registro2.finalizados) == 1,
        "el registro solo se finalizo una vez")
afirmar(len(registro2.reclamos) == 2
        and registro2.reclamos[0] == registro2.reclamos[1],
        "las dos pasadas usaron la MISMA clave -- es el 'origen' lo que la "
        "hace estable, no el intento")

# ---------------------------------------------------------------------------
#  Y una propuesta DISTINTA sobre el mismo caso si es otra operacion: la clave
#  la forma el origen, y dos decisiones humanas distintas no se colapsan.
registro3 = Registro()
proveedor3 = Proveedor()
with escenario(registro3, proveedor3):
    cerrar(propuesta=PROPUESTA)
    cerrar(propuesta="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

afirmar(len(proveedor3.llamadas) == 2,
        "dos propuestas distintas son dos operaciones distintas")


# ===========================================================================
seccion("3. sin permiso no hay cierre, y el modulo no puede fabricarlo")
# ===========================================================================
#  La otra mitad: que la exigencia siga viva. Si alguien quitara la puerta del
#  modulo, la idempotencia tiene que negarse -- y este es el codigo exacto que
#  produccion registro el 30/09/2026.

registro4 = Registro()
proveedor4 = Proveedor()
with escenario(registro4, proveedor4):
    sin_puerta = idempotencia.ejecutar(
        TENANT, "cerrar_caso_crm", {"id_caso": CASO},
        f"propuesta:{PROPUESTA}", lambda: proveedor4.ejecutar(
            None, {"id_caso": CASO}, TENANT))

afirmar(not sin_puerta.ejecutada,
        "llamar a la idempotencia sin pasar por la frontera NO ejecuta")
afirmar(sin_puerta.codigo == frontera.SIN_AUTORIZAR,
        f"y el codigo es el que produccion registro: "
        f"{frontera.SIN_AUTORIZAR} (fue {sin_puerta.codigo!r})")
afirmar(len(proveedor4.llamadas) == 0,
        "el proveedor no recibio nada")
afirmar(len(registro4.reclamos) == 0,
        "y la operacion ni siquiera se reclamo -- por eso en produccion "
        "'operaciones_externas' tenia CERO filas para esa propuesta")


# ===========================================================================
seccion("4. el interruptor sigue mandando, y falla CERRADO")
# ===========================================================================

registro5 = Registro()
proveedor5 = Proveedor()
with escenario(registro5, proveedor5, permitido=False):
    detenido = cerrar()

afirmar(detenido.codigo == cierre.BLOQUEADO_POR_INTERRUPTOR,
        "con el interruptor detenido no se cierra")
afirmar(len(proveedor5.llamadas) == 0,
        "y la mutacion no sale")


# ===========================================================================
print("\n" + "=" * 74)
if _fallos:
    print(f"  {len(_fallos)} AFIRMACIONES FALLARON")
    for f in _fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  todas las afirmaciones pasaron")
