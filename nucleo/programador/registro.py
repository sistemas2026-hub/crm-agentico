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
Nada. P2 entrega el scheduler, no los trabajos. 'importacion_tickets' y
'cerrar_vencidas' NO estan registrados a proposito -- cablearlos es P5, y
'cerrar_vencidas' ademas esta bloqueado por no ser idempotente (ver
nucleo/reloj.py: dos pasadas simultaneas dejan el texto de cierre dos veces en
el ticket del proveedor).

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

# La firma de un trabajo: recibe el turno ya derivado de la base y devuelve un
# diccionario con lo que hizo (o None). Si falla, levanta.
Handler = Callable[["object"], "dict | None"]

PREFIJO_PRUEBA = "prueba_"


class JobSinImplementacion(LookupError):
    """El catalogo declara un job que este despliegue no sabe hacer."""


# -----------------------------------------------------------------------------
#  EL MAPA. Literal, revisable de un vistazo, vacio en P2.
# -----------------------------------------------------------------------------
_PRODUCCION: dict[str, Handler] = {
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
