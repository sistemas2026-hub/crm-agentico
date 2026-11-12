# -*- coding: utf-8 -*-
"""
===============================================================================
 «HECHO · DESHACER»  --  lo que el Supervisor hizo solo, y como se revierte
===============================================================================

POR QUE EXISTE  --  12/11/2026
------------------------------
Desde hoy lo no critico nace delegado ('tareas_delegadas.py'): el Supervisor
deja de pedir permiso y lo hace. La contraparte de no preguntar antes es poder
revertir despues, y que la pantalla lo diga sin que haya que adivinar: cada
hecho que el Supervisor hizo solo se muestra en Actividad como «hecho», con un
boton «deshacer» SOLO donde el backend sabe deshacerlo, y donde no, el porque.

Dos funciones, una por lado:

    como_se_deshace(fila)   PURA. Que se le puede ofrecer a una persona sobre
                            una fila de la auditoria. No consulta nada: el
                            feed pinta veinte filas y no puede pagar veinte
                            consultas. Lo que depende del estado de hoy (ya
                            tiene orden, ya lo cambio alguien) lo decide
                            'deshacer' en el momento, con el bloqueo puesto.
    deshacer(...)           Lo hace, o dice por que no.

LO QUE SE PUEDE DESHACER HOY, Y LO QUE NO
-----------------------------------------
    pase a Despacho     SI, mientras el caso no tenga orden: la propuesta
                        queda RECHAZADA por esa persona y el caso sale de la
                        cola. Rechazada y no vuelta a PROPUESTA a proposito: de
                        vuelta en PROPUESTA el mismo ciclo la pasaria otra vez
                        en una hora, porque las reglas siguen dandose.
    cierre de un caso   NO: el caso ya estaba cerrado en el sistema del ISP;
    desincronizado      reabrirlo solo en Dexter lo volveria a desincronizar.
    jornada armada      NO desde aca: se corrige en Cuadrillas, y una jornada
                        que toca una persona el Supervisor no la vuelve a tocar.

Cualquier otro hecho del Supervisor cae en "no se deshace desde aca" con su
motivo generico: nunca se ofrece un boton que el backend no sabe cumplir.
===============================================================================
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from operaciones import auditoria

#: El unico tipo que hoy tiene boton.
PASE_A_DESPACHO = "pase_a_despacho"

_POR_QUE_NO_CIERRE = (
    "El caso ya estaba cerrado en el sistema del ISP: reabrirlo solo en Dexter "
    "lo volvería a desincronizar. Si el problema sigue, se abre un ticket nuevo.")
_POR_QUE_NO_JORNADA = (
    "Se corrige en Cuadrillas: una jornada que toca una persona, el Supervisor "
    "no la vuelve a tocar.")
_POR_QUE_NO_OTRO = "Este hecho no se deshace desde acá."


class NoSeDeshace(Exception):
    """No se pudo deshacer. El mensaje lo lee una persona; 'codigo' es fijo."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo


def _es_del_supervisor(fila) -> bool:
    #  'user=None' es la marca del Supervisor en toda esta auditoria, no un
    #  usuario de sistema inventado ('auditoria.registrar').
    return getattr(fila, "user_id", None) is None


def como_se_deshace(fila) -> dict | None:
    """
    Sobre UNA fila de 'common.Activity': None si no es algo que el Supervisor
    hizo solo; si lo es, {"tipo", "se_puede", "por_que_no"}.

    Una propuesta CREADA por la IA no es un hecho: es una pregunta a una
    persona, y sigue en la bandeja. Solo cuentan los efectos.
    """
    if not _es_del_supervisor(fila):
        return None
    entidad, accion = fila.entity_type, fila.action
    meta = fila.metadata or {}
    if (entidad == auditoria.ENTIDAD_PROPUESTA and accion == "APPROVED"
            and meta.get("tarea") == auditoria.TAREA_PASO_A_DESPACHO):
        return {"tipo": PASE_A_DESPACHO, "se_puede": True, "por_que_no": ""}
    if entidad == auditoria.ENTIDAD_CASO and accion == "STATUS_CHANGED":
        return {"tipo": "cierre_de_caso", "se_puede": False,
                "por_que_no": _POR_QUE_NO_CIERRE}
    if entidad == auditoria.ENTIDAD_JORNADA:
        return {"tipo": "jornada", "se_puede": False,
                "por_que_no": _POR_QUE_NO_JORNADA, "donde": "cuadrillas"}
    if accion in ("APPROVED", "UPDATE", "STATUS_CHANGED") and \
            entidad == auditoria.ENTIDAD_PROPUESTA and meta.get("tarea"):
        return {"tipo": "otro", "se_puede": False,
                "por_que_no": _POR_QUE_NO_OTRO}
    return None


def deshacer(org, actividad_id, *, actor, motivo: str) -> dict:
    """
    Deshace UN hecho del Supervisor. Exige persona y motivo.

    Todo se decide adentro de una transaccion con el caso bloqueado
    ('campo.services.despacho.bloquear_el_caso', el mismo que toman el boton
    Despachar y el Supervisor al crear una orden): sin eso, la orden podria
    crearse entre "no tiene orden" y "la saco de la cola", y quedaria una
    visita de un caso que ya no esta en Despacho.
    """
    from common.models import Activity

    from campo.models import OrdenTrabajo
    from campo.services.despacho import bloquear_el_caso
    from operaciones.models import PropuestaSupervisor as P

    if actor is None:
        raise NoSeDeshace("SIN_PERSONA",
                          "Deshacer necesita la persona que lo decide.")
    motivo = " ".join(str(motivo or "").split())[:500]
    if not motivo:
        raise NoSeDeshace("SIN_MOTIVO",
                          "Escribí el motivo: queda registrado con tu nombre.")

    fila = Activity.objects.filter(org=org, id=actividad_id).first()
    forma = como_se_deshace(fila) if fila is not None else None
    if forma is None:
        raise NoSeDeshace("NO_ES_UN_HECHO_DEL_SUPERVISOR",
                          "Ese hecho no lo hizo el Supervisor solo.")
    if not forma["se_puede"]:
        raise NoSeDeshace("NO_SE_DESHACE", forma["por_que_no"])

    with transaction.atomic():
        propuesta = (P.objects.select_for_update()
                     .filter(org=org, id=fila.entity_id).first())
        if propuesta is None:
            raise NoSeDeshace("NO_ESTA", "La propuesta ya no existe.")
        caso_id = str(propuesta.origen_id)
        bloquear_el_caso(org, caso_id)
        if propuesta.estado not in (P.ACEPTADA, P.MODIFICADA):
            raise NoSeDeshace(
                "YA_CAMBIO",
                "Alguien ya la cambió: el caso no está en Despacho por este pase.")
        if OrdenTrabajo.objects.filter(org=org, origen_sistema="crm",
                                       origen_ref=caso_id).exists():
            raise NoSeDeshace(
                "YA_TIENE_ORDEN",
                "El caso ya tiene orden de trabajo: se cancela en Despacho, y "
                "con eso sale de la cola.")
        anterior = propuesta.estado
        propuesta.estado = P.RECHAZADA
        propuesta.revisado_por = actor
        propuesta.revisado_en = timezone.now()
        propuesta.save(update_fields=["estado", "revisado_por",
                                      "revisado_en", "updated_at"])
        auditoria.registrar(
            org=org, actor=actor, accion="REJECTED",
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=propuesta.id,
            #  Texto fijo, como el del pase: 'accion_propuesta' la redacto el
            #  modelo leyendo el ticket.
            nombre="Pase a Despacho deshecho por una persona",
            descripcion=motivo, estado_anterior=anterior,
            estado_nuevo=propuesta.estado, motivo=motivo,
            extra={"deshace": str(fila.id),
                   "tarea": auditoria.TAREA_PASO_A_DESPACHO})
    return {"deshecho": True, "tipo": forma["tipo"]}
