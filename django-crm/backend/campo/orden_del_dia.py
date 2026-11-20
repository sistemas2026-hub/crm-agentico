# -*- coding: utf-8 -*-
"""
================================================================================
 EL ORDEN DEL DIA  --  29/10/2026
================================================================================
Pedido del usuario, mirando Programacion: «que indique con cual iniciaria la
jornada» y «en la app, cuando este haciendo un ticket, le indique con cual
sigue, y asi que el mismo Supervisor le arme el orden en que trabaja los
tickets».

QUIEN DECIDE EL ORDEN: EL SUPERVISOR, UNA VEZ, EN EL SERVIDOR. Al publicar el
reparto (`operaciones.publicacion_del_reparto`), a cada orden viva de cada
cuadrilla le guarda su lugar del dia (`OrdenTrabajo.orden_del_dia`, con su
fecha). La app lo sigue y Programacion muestra el mismo: dos reglas, una en el
telefono y otra en la pantalla, terminarian diciendo cosas distintas.

EL ORDEN DE UNA CUADRILLA:
  1. lo empezado: en sitio, despues en camino. Lo que el tecnico ya empezo no
     se mueve: dejarlo a medias es lo que hace que no cierre;
  2. lo que falta, por urgencia --
       a. lo que ya paso su vencimiento, lo mas atrasado primero;
       b. la prioridad: alta, media, baja;
       c. dentro de cada prioridad, lo que vence antes (sin fecha, al final);
       d. el numero, para que dos vueltas iguales den lo mismo.
Cada vuelta del ciclo lo vuelve a armar: si entra algo urgente, pasa adelante
de lo que todavia no empezo.

EL VENCIMIENTO es el compromiso con el cliente (`sla_vence_en`: el dia del
ticket mas el plazo del nivel de su asunto), no la duracion del trabajo
contada desde que se creo la orden --esa medida decia «vencida» de toda orden
de ayer (ver `supervisor.SOLO_SE_CUENTAN`)--.
================================================================================
"""
from __future__ import annotations

import datetime as dt

#: Lejos en el futuro: lo que no vence va al final de su prioridad.
_NUNCA = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
_RANGO_PRIORIDAD = {"alta": 0, "media": 1, "baja": 2}


def _empezadas():
    from campo.models import OrdenTrabajo
    return (OrdenTrabajo.EN_SITIO, OrdenTrabajo.EN_CAMINO)


def _vivas():
    from campo.dia_publicado import _activas
    return _activas()


def urgencia(o, ahora) -> tuple:
    """La clave de lo que falta: menor es mas urgente. Ver el encabezado."""
    vence = o.sla_vence_en
    if vence is not None and vence <= ahora:
        return (0, vence, 0, o.numero)
    return (1, _RANGO_PRIORIDAD.get(o.prioridad or "", 1), vence or _NUNCA, o.numero)


def ordenadas(ordenes, ahora) -> list:
    """Las ordenes VIVAS de una cuadrilla en su orden del dia. Las terminadas
    no entran: ya no tienen lugar."""
    from campo.models import OrdenTrabajo

    vivas = [o for o in ordenes if o.estado_operativo in _vivas()]
    empezadas = sorted(
        (o for o in vivas if o.estado_operativo in _empezadas()),
        #  En sitio antes que en camino; entre iguales, el lugar que ya tenian.
        key=lambda o: (o.estado_operativo != OrdenTrabajo.EN_SITIO,
                       o.orden_del_dia or 9999, o.numero))
    faltan = sorted((o for o in vivas if o.estado_operativo not in _empezadas()),
                    key=lambda o: urgencia(o, ahora))
    return empezadas + faltan


def ordenar(org, fecha, ahora) -> int:
    """Le guarda a cada orden viva de cada cuadrilla de `fecha` su lugar del
    dia. Devuelve cuantas cambiaron. Solo escribe lo que cambia."""
    from django.db import transaction

    from campo.dia_publicado import jornadas_y_ordenes, por_jornada_de
    from campo.models import OrdenTrabajo

    jornadas, _reciben, receptores, ordenes = jornadas_y_ordenes(org, fecha)
    por, _sin = por_jornada_de(jornadas, receptores, ordenes)
    cambian = []
    for lista in por.values():
        for lugar, o in enumerate(ordenadas(lista, ahora), start=1):
            if (o.orden_del_dia, o.orden_del_dia_fecha) != (lugar, fecha):
                o.orden_del_dia, o.orden_del_dia_fecha = lugar, fecha
                o.updated_at = ahora
                cambian.append(o)
    if cambian:
        with transaction.atomic():
            OrdenTrabajo.objects.bulk_update(
                cambian, ["orden_del_dia", "orden_del_dia_fecha", "updated_at"])
    return len(cambian)


def como_la_app(o, fecha) -> tuple:
    """La MISMA regla con que la app ordena la lista del tecnico
    (`apps/tecnicos-mobile/lib/features/trabajo/orden_operativo.dart`), para
    que Programacion diga lo mismo que el telefono: en sitio, en camino, el
    orden del dia de ESA fecha, y sin el, lo que vence antes, la prioridad y
    el orden de llegada (el de la lista que baja: lo mas nuevo primero). Lo
    terminado al final."""
    from campo.dia_publicado import _terminadas
    from campo.models import OrdenTrabajo

    llegada = -(o.created_at.timestamp() if o.created_at else 0)
    if o.estado_operativo in _terminadas():
        return (6, 0, llegada)
    if o.estado_operativo == OrdenTrabajo.EN_SITIO:
        return (0, 0, llegada)
    if o.estado_operativo == OrdenTrabajo.EN_CAMINO:
        return (1, 0, llegada)
    if o.orden_del_dia and o.orden_del_dia_fecha == fecha:
        return (2, o.orden_del_dia, llegada)
    if o.sla_vence_en is not None:
        return (3, o.sla_vence_en.timestamp(), llegada)
    if o.prioridad in _RANGO_PRIORIDAD:
        return (4, _RANGO_PRIORIDAD[o.prioridad], llegada)
    return (5, 0, llegada)
