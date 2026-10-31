# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR LE RECUERDA AL TECNICO QUE REPORTE  --  30/10/2026
================================================================================

El usuario: «el supervisor no solo debe dejar notificado en la pantalla de
programacion, sino que le manda el mensaje al tecnico». Hasta hoy la regla de
los 30 minutos (`services/salud_seguimiento.py`) se calculaba solo cuando
alguien abria Programacion: el atraso se veia en la oficina y el tecnico no se
enteraba.

QUE HACE
--------
Cada 5 minutos (`campo.tasks.recordar_reportes`), por empresa: las ordenes en
ejecucion que la regla da por VENCIDAS reciben un aviso en el telefono de
quienes la tienen asignada --«⏱ OT #12: 38 min sin reportar»--, y queda en el
log del dia de su cuadrilla.

UNO POR ATRASO, NO UNO CADA 5 MINUTOS
-------------------------------------
La clave del aviso lleva la REFERENCIA de la regla: el ultimo reporte (o la
entrada en ejecucion). Mientras el tecnico no reporte, la referencia no cambia
y la clave tampoco: un solo aviso. Cuando reporta, la referencia se mueve; si
vuelve a pasar la ventana, es otro atraso y otro aviso. La clave se reclama
por clave primaria (`AvisoEnviado`), no con un `select` previo.

LO QUE NO SE RECUERDA
---------------------
- Lo que la regla no da por VENCIDO: pausado por el NOC, por una novedad de la
  cuadrilla, o sin contacto con el telefono (no se acusa lo que no se midio).
- Lo que empezo OTRO dia (la referencia no es de hoy): una orden en sitio
  desde hace dos semanas no es un atraso de hoy, es una orden sin cerrar, y
  avisarla a las 2 de la mañana del dia del deploy seria ruido.
- Si la empresa lo apago (`ConfiguracionDeSeguimiento.recordar_al_tecnico`).

Sin datos del cliente: el numero de la orden y los minutos.
================================================================================
"""
from __future__ import annotations

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def recuerda_al_tecnico(org) -> bool:
    from campo.seguimiento import ConfiguracionDeSeguimiento

    fila = ConfiguracionDeSeguimiento.objects.filter(org=org).first()
    return True if fila is None else bool(fila.recordar_al_tecnico)


def recordar_para(org, *, ahora=None) -> dict:
    """Recorre las ordenes en ejecucion de UNA empresa y avisa las vencidas.
    `{"vencidas": n, "avisadas": n}`: avisadas son las que reclamaron su clave
    en esta vuelta (las ya avisadas antes no cuentan)."""
    from campo import reparto as R
    from campo.models import OrdenTrabajo
    from campo.services import avisos
    from campo.services import salud_seguimiento as SS

    ahora = ahora or timezone.now()
    salida = {"vencidas": 0, "avisadas": 0}
    if not recuerda_al_tecnico(org):
        return salida
    zona = R._zona_de(org)
    hoy = ahora.astimezone(zona).date()
    config = SS.configuracion_de(org)
    for orden in (OrdenTrabajo.objects.filter(org=org, estado_operativo__in=SS.EN_EJECUCION)
                  .prefetch_related("asignaciones__profile")):
        s = SS.calcular(orden, ahora=ahora, config=config)
        if s["tipo"] != SS.VENCIDO or not s.get("referencia"):
            continue
        referencia = parse_datetime(s["referencia"])
        if referencia is None or referencia.astimezone(zona).date() != hoy:
            continue
        salida["vencidas"] += 1
        if avisos.avisar_sin_reporte(orden, s["minutos_desde_la_referencia"], s["referencia"]):
            salida["avisadas"] += 1
    return salida
