# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CIERRA SOLO LO QUE SU REVISION DIO POR BUENO  --  30/10/2026
================================================================================

SPEC/objetivos/revision-del-cierre.md. El usuario: «¿de que manera hacemos
para que el supervisor cierre solo?».

QUE HACE
--------
Cada 10 minutos (`campo.tasks.cerrar_lo_revisado`), por empresa que lo
encendio (`ConfiguracionDeSeguimiento.supervisor_cierra_solo`): las ordenes
terminadas sin validar cuya revision dice «Se puede cerrar»
(`revision_del_cierre.py`):

    1. le pide al motor que cierre el ticket del ISP por la puerta AUTONOMA
       (`/interno/orden/<id>/cerrar-ticket-supervisor`): interruptor, techo,
       Autonomia 2 con B-7 y la autorizacion de la herramienta
    2. SOLO si el ticket quedo cerrado (o no habia ticket): aprueba la orden
       y la cierra en Dexter, a nombre del Supervisor

EL ORDEN ES LA GARANTIA. Primero afuera, despues adentro: si el motor se
niega, la orden queda sin validar, para una persona, con el motivo anotado.
Al reves, Dexter diria «cerrada» con el ticket abierto en el ISP, que es lo
que el cierre por validacion existe para no tener. Si se cae entre los dos
pasos, la vuelta siguiente lo completa: el motor contesta «ya se habia
cerrado» y Dexter aprueba.

«Revisalo» y «No se cierra» NO se tocan: siguen siendo de una persona.

UN INTENTO POR HORA Y POR ORDEN. Con las compuertas cerradas (hoy en
produccion), cada intento queda anotado una vez por hora --«el Supervisor la
habria cerrado, pero B7_REQUERIDO»--: es la medicion de lo que haria, sin
llenar la bitacora cada 10 minutos.
================================================================================
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

#: Lo que se anota en la bitacora de la orden.
EVENTO_BLOQUEADO = "cierre_del_supervisor_bloqueado"
EVENTO_CERRADA = "cerrada_por_el_supervisor"

#: Cada cuanto se vuelve a intentar una orden que el motor no dejo cerrar.
MINUTOS_ENTRE_INTENTOS = 60

#: Lo que el motor contesta y deja seguir a Dexter: el ticket quedo cerrado,
#: ya lo estaba, o la orden no tiene ticket del ISP que cerrar.
SIGUE = ("cerrado", "ya_cerrado", "sin_ticket")


def cierra_solo(org) -> bool:
    from campo.seguimiento import ConfiguracionDeSeguimiento

    fila = ConfiguracionDeSeguimiento.objects.filter(org=org).first()
    return bool(fila and fila.supervisor_cierra_solo)


def _intento_reciente(orden, ahora) -> bool:
    from campo.models import EventoTrabajo

    return EventoTrabajo.objects.filter(
        org=orden.org, orden=orden, tipo=EVENTO_BLOQUEADO,
        created_at__gte=ahora - timedelta(minutes=MINUTOS_ENTRE_INTENTOS)).exists()


def cerrar_lo_revisado(org, *, ahora=None) -> dict:
    """`{"cerradas": n, "bloqueadas": n, "apagado": bool}`."""
    from campo import revision_del_cierre as RC
    from campo.models import EventoTrabajo, OrdenTrabajo
    from campo.services import cierre_en_isp

    ahora = ahora or timezone.now()
    salida = {"cerradas": 0, "bloqueadas": 0, "apagado": False}
    if not cierra_solo(org):
        salida["apagado"] = True
        return salida
    candidatas = OrdenTrabajo.objects.filter(
        org=org, estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion__in=(OrdenTrabajo.PENDIENTE, OrdenTrabajo.REQUIERE_REVISION))
    for orden in candidatas:
        revision = RC.revisar(orden)
        if not revision or revision["veredicto"] != RC.CERRAR:
            continue
        if _intento_reciente(orden, ahora):
            continue
        ticket = cierre_en_isp.cerrar_ticket_por_el_supervisor(orden)
        if ticket["estado"] not in SIGUE:
            EventoTrabajo.objects.create(
                org=org, orden=orden, tipo=EVENTO_BLOQUEADO,
                datos={"estado": ticket["estado"], "detalle": ticket.get("detalle", "")})
            salida["bloqueadas"] += 1
            continue
        if _aprobar_y_cerrar(orden, revision, ticket):
            salida["cerradas"] += 1
    return salida


def _aprobar_y_cerrar(orden, revision, ticket) -> bool:
    """Adentro, en una transaccion: aprobar y cerrar, a nombre del Supervisor
    (`profile=None`, y la bitacora lo dice). Si una persona la valido en el
    medio, no se pisa: se lee bajo bloqueo."""
    from campo.models import EventoTrabajo, OrdenTrabajo
    from campo.services.transiciones import aprobar, cerrar_orden

    motivos = "; ".join(p["texto"] for p in revision["puntos"])
    with transaction.atomic():
        fresca = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
        if (fresca.estado_operativo != OrdenTrabajo.COMPLETADA_CAMPO
                or fresca.estado_validacion not in (OrdenTrabajo.PENDIENTE,
                                                    OrdenTrabajo.REQUIERE_REVISION)):
            return False
        fresca = aprobar(fresca, profile=None,
                         observacion=f"Aprobada por el Supervisor: {motivos}")
        fresca = cerrar_orden(fresca, profile=None,
                              metadatos={"por": "supervisor", "ticket_isp": ticket["estado"]})
        EventoTrabajo.objects.create(
            org=fresca.org, orden=fresca, tipo=EVENTO_CERRADA,
            datos={"veredicto": revision["veredicto"], "ticket_isp": ticket["estado"],
                   "puntos": [p["clave"] for p in revision["puntos"]]})
    return True
