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

INSISTE HASTA QUE LLEGA EL REPORTE, NO UNO CADA 5 MINUTOS  --  11/11/2026
------------------------------------------------------------------------
Hasta el 11/11 era UNO POR ATRASO, y el usuario midio que eso no alcanza: «si
despues del reporte no mandan nada queda asi, no vuelve a notificar». Un aviso
que se manda una vez y no se repite se pierde entre las notificaciones del
telefono, y la orden se queda igual.

La clave del aviso lleva la REFERENCIA de la regla --el ultimo reporte, o la
entrada en ejecucion-- MAS que recordatorio es: `...|2`, `...|3`. El primero
no lleva sufijo, y eso no es inconsistencia: conserva la clave vieja para que
el deploy no re-disparara el aviso 1 de cada orden ya notificada.

Cual toca lo decide `cual_recordatorio()` sobre los minutos desde la
referencia, en una REJILLA FIJA (ventana, ventana+cada, ventana+2*cada...), no
encadenado al aviso anterior. Por eso es idempotente sin consultar nada: la
misma pasada, repetida, calcula el mismo numero y la clave ya esta tomada. Y
no acumula deriva: un worker que se atrasa no corre la rejilla.

Cuando el tecnico reporta, la referencia se mueve y la cuenta vuelve a cero:
eso es lo que APAGA la insistencia, sin que nadie borre nada.

La clave se reclama por clave primaria (`AvisoEnviado`), no con un `select`
previo.

EL PISO DE PRECISION NO ES LA CONFIGURACION, ES BEAT
----------------------------------------------------
`recordar_reportes` corre cada 5 minutos (`crm/celery.py`). Con la repeticion
en 15, el segundo aviso sale entre el minuto 45 y el 50, no a los 45 exactos.
Un valor mas chico que 5 no lo hace mas fino.

LO QUE NO SE RECUERDA
---------------------
- Lo que la regla no da por VENCIDO: pausado por el NOC, por una novedad de la
  cuadrilla, o sin contacto con el telefono (no se acusa lo que no se midio).
- Lo que empezo OTRO dia (la referencia no es de hoy): una orden en sitio
  desde hace dos semanas no es un atraso de hoy, es una orden sin cerrar, y
  avisarla a las 2 de la mañana del dia del deploy seria ruido.
- Si la empresa lo apago (`ConfiguracionDeSeguimiento.recordar_al_tecnico`).
- Volver a insistir, si la empresa puso la repeticion en 0: ahi es uno por
  atraso, como era antes del 11/11.

NO PASA POR LA AUTONOMIA NI POR EL MODELO
-----------------------------------------
Esto es codigo, no una decision del Supervisor como agente: no lee el nivel de
autonomia, no consulta el interruptor y no llama al motor. Se enciende y se
apaga con la casilla de la empresa, y nada mas. Que la pantalla lo agrupe bajo
«lo que el Supervisor hace solo» es el nombre del grupo, no una capacidad del
agente.

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


def cada_cuanto_insiste(org) -> int:
    """Minutos entre un recordatorio y el siguiente. 0 = uno solo."""
    from campo.seguimiento import (MINUTOS_ENTRE_RECORDATORIOS,
                                   ConfiguracionDeSeguimiento)

    fila = ConfiguracionDeSeguimiento.objects.filter(org=org).first()
    if fila is None:
        return MINUTOS_ENTRE_RECORDATORIOS
    return int(fila.repetir_recordatorio_cada_minutos or 0)


def cual_recordatorio(minutos, ventana, cada) -> int:
    """Que numero de recordatorio toca a esta altura del atraso.

    LA CUENTA, CON LOS NUMEROS DEL USUARIO (ventana 30, cada 15):

        minuto 30  ->  1     el primero, el que ya existia
        minuto 44  ->  1     todavia no pasaron 15 del anterior
        minuto 45  ->  2
        minuto 60  ->  3     y asi hasta que reporte

    ES LO QUE HACE QUE EL AVISO SE REPITA, y no una cuenta decorativa: este
    numero entra en la CLAVE de idempotencia (`avisos.avisar_sin_reporte`).
    Mientras devuelva lo mismo, la clave ya esta tomada y no sale nada; en
    cuanto sube, es un aviso nuevo. Sin esto la clave solo lleva la
    referencia, que no se mueve hasta que el tecnico reporta -- que es
    exactamente por que hasta hoy avisaba una sola vez.

    LA TAREA CORRE CADA 5 MINUTOS, asi que el aviso 2 sale entre el minuto
    45 y el 50. El retraso es del muestreo, no de la cuenta.
    """
    if cada <= 0:
        return 1
    return 1 + max(0, int(minutos) - int(ventana)) // int(cada)


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
    cada = cada_cuanto_insiste(org)
    for orden in (OrdenTrabajo.objects.filter(org=org, estado_operativo__in=SS.EN_EJECUCION)
                  .prefetch_related("asignaciones__profile")):
        s = SS.calcular(orden, ahora=ahora, config=config)
        if s["tipo"] != SS.VENCIDO or not s.get("referencia"):
            continue
        referencia = parse_datetime(s["referencia"])
        if referencia is None or referencia.astimezone(zona).date() != hoy:
            continue
        salida["vencidas"] += 1
        #  `SS.configuracion_de` devuelve una TUPLA
        #  `(minutos_para_reportar, minutos_contacto_reciente)`, no la fila.
        #  La primera version leyo `config.minutos_para_reportar` y reviento
        #  toda llamada que llegaba a avisar -- diez guardas en rojo de una.
        cual = cual_recordatorio(s["minutos_desde_la_referencia"],
                                 config[0], cada)
        if avisos.avisar_sin_reporte(orden, s["minutos_desde_la_referencia"],
                                     s["referencia"], cual=cual):
            salida["avisadas"] += 1
    return salida
