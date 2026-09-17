# -*- coding: utf-8 -*-
"""
Si un efecto del turno de la IA todavia puede empezar. D25.

POR QUE EXISTE (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, D24, D25, C11)
-----------------------------------------------------------------
D24 cerro la RESPUESTA: si una persona interviene mientras el modelo piensa, lo
que el modelo contesta no se guarda ni se envia. Pero mientras piensa, el modelo
tambien llama herramientas, y algunas escriben afuera (reiniciar un equipo,
crear un ticket, registrar un pago). Descartar la respuesta al final no deshace
una accion que se inicio DESPUES de que el control ya habia pasado a una
persona.

Este modulo es el punto de consulta. Quien atiende el turno (api.atender_turno)
instala un autorizador mientras dura el turno; el motor le pregunta antes de
iniciar cualquier efecto que escribe. El autorizador relee la base: si la
conversacion cambio de control o de relevo_version, el efecto no empieza.

QUE NO HACE
-----------
- No sostiene ninguna transaccion ni lock mientras corre la llamada externa
  (P-A). Punto de no retorno (C11): una llamada que ya empezo puede completar.
- No toca lecturas. Consultar una señal o una deuda despues de una intervencion
  no cambia nada afuera.
- Fuera de un turno (una bateria de casos dorados, una accion que aprobo una
  persona desde la bandeja) no hay autorizador instalado y todo sigue igual:
  quien decide ahi no es la IA.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable

_autorizador: ContextVar[Callable[[str], bool] | None] = ContextVar(
    "autorizador_de_efectos_del_turno", default=None)


@contextmanager
def autorizando(autorizador: Callable[[str], bool]):
    """Instala el autorizador del turno mientras dura el bloque."""
    token = _autorizador.set(autorizador)
    try:
        yield
    finally:
        _autorizador.reset(token)


def efecto_autorizado(que: str) -> bool:
    """
    True si el efecto 'que' (el nombre de la herramienta o del paso) puede
    empezar. Sin autorizador instalado, True: no hay un turno de la IA que
    proteger.
    """
    autorizador = _autorizador.get()
    return True if autorizador is None else bool(autorizador(que))
