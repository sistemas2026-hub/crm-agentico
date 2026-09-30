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


# --- las reglas, en un solo lugar ---------------------------------------------
#
# Tres clases de efecto. La clase la decide QUIEN origina el efecto, no que
# sistema toca:
#
#   AUTONOMO_IA          lo decide la IA en su turno: una herramienta del modelo
#                        que escribe, una propuesta, la visita que se agenda
#                        sola, cerrar porque el cliente confirmo. Exige que la IA
#                        siga controlando y que nadie haya movido relevo_version.
#
#   SYNC_ESCALADA        el ticket y el caso del CRM de una escalada que ESTE
#                        turno ya dejo durable. La obligacion nacio con la
#                        escalada: tomarla, soltarla o reasignarla cambia QUIEN
#                        atiende, no la borra. Solo una transicion que deja la
#                        escalada obsoleta -- devolverla a la IA, cerrarla --
#                        impide un efecto que todavia no empezo.
#
#   AUTOMATICO_EN_PAUSA  lo que el motor hace solo mientras la conversacion esta
#                        en manos de personas (cerrar porque el cliente confirmo
#                        durante la pausa). Nadie lo pidio en este turno: si
#                        alguien movio el relevo mientras se evaluaba, no empieza.
#
# B4 convierte SYNC_ESCALADA en una sincronizacion durable y reconciliable; hasta
# entonces la regla vive aca y no en cada llamador.
AUTONOMO_IA = "autonomo_ia"
SYNC_ESCALADA = "sync_escalada"
AUTOMATICO_EN_PAUSA = "automatico_en_pausa"

# Las transiciones que dejan obsoleta una escalada. Tomar, soltar o reasignar NO.
INVALIDAN_ESCALADA = ("devuelta_a_ia", "cerrada")


def regla_turno(autorizacion: dict, actual: dict | None, *, exigir_ia: bool) -> bool:
    """
    AUTONOMO_IA (exigir_ia) y AUTOMATICO_EN_PAUSA (sin exigir_ia): la misma
    conversacion abierta, la misma relevo_version y, si se pide, control ia.
    'actual' es lo que leyo db.control_de_conversacion_abierta (None si no hay
    ninguna abierta).
    """
    esperado = autorizacion.get("conversation_id")
    if actual is None:
        return esperado is None
    if esperado is not None and actual["conversation_id"] != esperado:
        return False
    if exigir_ia and actual["control_efectivo"] != "ia":
        return False
    return actual["relevo_version"] == autorizacion.get("relevo_version")


def regla_escalada(vigencia: dict | None) -> bool:
    """
    SYNC_ESCALADA: la escalada originadora sigue vigente. 'vigencia' es lo que
    leyo db.vigencia_de_escalada: la conversacion sigue abierta y en manos de
    personas, el evento de ESA escalada existe, y despues de el no hubo ninguna
    transicion de INVALIDAN_ESCALADA. La version actual puede ser mayor.
    """
    return bool(vigencia and vigencia["originada"] and vigencia["estado"] == "abierta"
                and vigencia["control_efectivo"] == "humano" and not vigencia["invalidada"])


def efecto_autorizado(que: str) -> bool:
    """
    True si el efecto 'que' (el nombre de la herramienta o del paso) puede
    empezar. Sin autorizador instalado, True: no hay un turno de la IA que
    proteger.
    """
    autorizador = _autorizador.get()
    return True if autorizador is None else bool(autorizador(que))
