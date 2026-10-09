# -*- coding: utf-8 -*-
"""
================================================================================
 EL REGISTRO DE TRABAJOS  --  cerrado, y cerrado en serio
================================================================================

Por que existe
--------------
La primera version del coordinador recibia los trabajos como parametro:

    un_tick({"importacion_tickets": alguna_funcion})

Eso parece inocente en una prueba y es una puerta abierta en produccion: un
'job_code' que llega de una fila de la base terminando en una busqueda que
resuelve a un callable convierte al catalogo --un dato-- en codigo ejecutable.
El catalogo lo edita un operador; el codigo lo revisa alguien.

Aca la relacion 'job_code -> funcion' vive en ESTE archivo, en un diccionario
literal, y se congela al importar. No hay registro dinamico, no hay
'importlib', no hay nombre de modulo que venga de afuera, y 'resolver' no
construye nada: busca en un mapa y falla si no esta.

Que hay hoy
-----------
DOS, los dos del 02/10/2026 y los dos de LECTURA hacia afuera:

  'supervisor_latido'   le pregunta al Supervisor que senales ve y guarda
                        conteos. No escribe nada, en ninguna parte. Se cableo
                        primero por eso -- demuestra el circuito completo del
                        scheduler (tick, reclamo, ejecucion, 'job_run') sin que
                        el peor caso sea otra cosa que no leer nada.

  'supervisor_sondeo'   lo despierta para que consulte SUS fuentes y deje
                        escrito el estado y la frescura de cada una. Escribe DOS
                        TABLAS PROPIAS del Supervisor y nada afuera: a los
                        sistemas externos se les consulta con herramientas
                        'solo_lectura' por el camino que ya existia.

                        CUALES son esas fuentes no se enumera aca: este archivo
                        es el motor generico, y una lista de sistemas concretos
                        se vuelve falsa el dia que entre otro. El catalogo vive
                        en 'operaciones/fuentes_modelos.py::Fuente'.

Hasta el 02/10/2026 el mapa estaba VACIO, y esta seccion decia "Nada". Si vuelve
a quedar vacio, o si cambia la cuenta, decirlo aca: un archivo que afirma lo
contrario de lo que hace es peor que uno sin docstring.

'importacion_tickets' y 'cerrar_vencidas' siguen SIN registrar a proposito --
cablear el primero es P5, y 'cerrar_vencidas' ademas esta bloqueado por no ser
idempotente (ver nucleo/reloj.py: dos pasadas simultaneas dejan el texto de
cierre dos veces en el ticket del proveedor).

Y CABLEAR NO ES ENCENDER. Este mapa dice que el despliegue SABE hacer algo; lo
que lo hace correr es una fila en 'asistente.job_catalogo', que sigue vacio (lo
afirma tests/test_p2_inerte.py). Son dos interruptores a proposito: uno es
codigo revisado, el otro es una decision de operacion.

La consecuencia practica, y es la buscada: si alguien agrega
'cerrar_vencidas' al catalogo de produccion hoy, el coordinador lo ve, no lo
encuentra aca, y NO lo reclama. Lo cuenta como omitido con motivo. No hay
forma de encenderlo por configuracion.

El handler hermetico de pruebas
-------------------------------
'registrar_para_prueba' existe para las suites y solo acepta codigos que
empiezan con 'prueba_'. No es una convencion amable: es un 'if' que levanta
ValueError. Un test no puede registrar 'importacion_tickets' ni por error ni a
proposito, asi que la puerta de pruebas no puede volverse la puerta de
produccion.
================================================================================
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Callable, Mapping

from nucleo.programador import trabajos

# La firma de un trabajo: recibe el turno ya derivado de la base y devuelve un
# diccionario con lo que hizo (o None). Si falla, levanta.
Handler = Callable[["object"], "dict | None"]

PREFIJO_PRUEBA = "prueba_"


class JobSinImplementacion(LookupError):
    """El catalogo declara un job que este despliegue no sabe hacer."""


# -----------------------------------------------------------------------------
#  EL MAPA. Literal y revisable de un vistazo -- dos trabajos hoy, y
#  tests/test_programador.py afirma el conjunto EXACTO, no "al menos uno".
# -----------------------------------------------------------------------------
_PRODUCCION: dict[str, Handler] = {
    #  El unico cableado hoy. Es de LECTURA: pregunta al Supervisor que ve y
    #  guarda conteos. No escribe, no toca casos, no llama a ningun proveedor.
    #  Se cablea primero justamente por eso -- demuestra el circuito entero sin
    #  que el peor caso sea otra cosa que no leer nada.
    #
    #  CABLEADO NO ES ENCENDIDO. Este mapa dice que el despliegue SABE hacerlo;
    #  lo que lo hace correr es una fila en 'asistente.job_catalogo', y el
    #  catalogo sigue vacio (lo afirma tests/test_p2_inerte.py). Son dos
    #  interruptores a proposito: uno es codigo revisado, el otro es operacion.
    "supervisor_latido": trabajos.latido_supervisor,
    #  El segundo, desde el 02/10/2026. Despierta al Supervisor para que
    #  consulte sus fuentes y deje escrito el estado de cada una. Escribe DOS
    #  TABLAS PROPIAS del Supervisor --estado y captura por fuente-- y nada
    #  afuera: a SmartOLT y WispHub se les consulta con herramientas
    #  'solo_lectura' por el camino que ya existia.
    #
    #  UNO Y NO SEIS, a proposito: la frecuencia de cada fuente vive en una fila
    #  editable del lado del Supervisor, no en este mapa. Asi este archivo
    #  --que es el motor generico-- no nombra ningun sistema externo.
    "supervisor_sondeo": trabajos.sondeo_de_fuentes,
    #  EL CICLO DEL SUPERVISOR ESTUVO AQUI y se quito el 08/10/2026. No por
    #  inutil: nunca se pudo encender. Reclamar un turno exige el rol
    #  'scheduler_coordinator', y concederlo exige la opcion ADMIN sobre el,
    #  que no tiene ninguna credencial del despliegue. El ciclo paso a correr
    #  por 'celery-beat' del CRM --que ya andaba, y cuyo usuario ya podia todo
    #  lo necesario-- y este trabajo quedo sin llamador posible.
    #
    #  No se deja "por si acaso": un camino que nadie usa y nadie corre se
    #  pudre en silencio, y el proximo que lo encuentre no va a saber si falta
    #  encenderlo o si sobra. Volver a ponerlo es facil si algun dia hay una
    #  credencial con ADMIN -- pero entonces habria DOS relojes despertando lo
    #  mismo, y lo que corresponde es elegir uno.
    # "importacion_tickets": ...,   <- P5
    # "cerrar_vencidas": BLOQUEADO  <- no es idempotente; no se cablea
}

# Los de prueba viven aparte para que la separacion se vea, no se deduzca.
_PRUEBAS: dict[str, Handler] = {}


def conocido(job_code: str) -> bool:
    """Si este despliegue sabe hacer ese job. No construye nada."""
    return job_code in _PRODUCCION or job_code in _PRUEBAS


def resolver(job_code: str) -> Handler:
    """
    El handler, o JobSinImplementacion.

    Busca en dos diccionarios y nada mas. No importa modulos, no evalua
    cadenas, no arma nombres: 'job_code' es una CLAVE, nunca una ruta.
    """
    if not isinstance(job_code, str):
        raise JobSinImplementacion(f"job_code no es texto: {type(job_code).__name__}")
    h = _PRODUCCION.get(job_code) or _PRUEBAS.get(job_code)
    if h is None:
        raise JobSinImplementacion(
            f"'{job_code}' no esta registrado en este despliegue. "
            f"Registrados: {sorted(_PRODUCCION)}")
    return h


def registrados() -> Mapping[str, Handler]:
    """Solo lectura, para inspeccion y para las pruebas."""
    return MappingProxyType({**_PRODUCCION, **_PRUEBAS})


def registrar_para_prueba(job_code: str, handler: Handler) -> None:
    """
    Registra un handler hermetico. SOLO codigos que empiezan con 'prueba_'.

    Es un 'if', no una convencion: sin el, la puerta de pruebas seria la puerta
    de produccion con otro nombre.
    """
    if not job_code.startswith(PREFIJO_PRUEBA):
        raise ValueError(
            f"'{job_code}' no se puede registrar desde una prueba: los "
            f"handlers de prueba tienen que empezar con '{PREFIJO_PRUEBA}'. "
            f"Cablear un job real es un cambio de codigo revisado, no una "
            f"llamada en tiempo de ejecucion.")
    if not callable(handler):
        raise ValueError("el handler no es invocable")
    _PRUEBAS[job_code] = handler


def olvidar_pruebas() -> None:
    """Deja el registro como estaba. Para que una suite no contamine a otra."""
    _PRUEBAS.clear()
