# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CIERRA SOLO LO QUE SU REVISION DIO POR BUENO  --  30/10/2026
================================================================================

SPEC/objetivos/revision-del-cierre.md. El usuario: «¿de que manera hacemos
para que el supervisor cierre solo?». Una FASE del ciclo del Supervisor
(`operaciones/supervisor.py::correr_ciclo`), despues de la medicion despues
del arreglo: una vez por hora, como las demas.

LAS PUERTAS, las mismas que las otras tareas de accion y todas fail-closed
(`operaciones/ordenes_de_despacho._puertas`):

    la tarea `aprobar_y_cerrar_lo_que_dio_por_bueno`, delegada por una
    persona desde el chat del Supervisor (`tareas_delegadas`)
    el nivel 3 de la empresa (`autonomia.puede`): con el interruptor de
    emergencia detenido no se cierra NADA, tampoco lo de adentro
    `MOTOR_TENANT` (la empresa atada al tenant del motor, D5)

Sin alguna, SOMBRA: no escribe nada y dice cuantas cerraria. Y del lado del
motor, el ticket pasa por cinco compuertas mas (interruptor, techo, Autonomia 2
con B-7, autorizacion de la herramienta, y que la herramienta no exija
aprobacion humana -- hoy la exige: M06-E).

QUE CIERRA: lo que `revision_del_cierre` marca «Se puede cerrar». Primero el
ticket afuera; SOLO si quedo cerrado (o no habia ticket), aprobar y cerrar
adentro, bajo bloqueo. Si el motor se niega o no se sabe, queda para una
persona y la tarjeta dice por que.

QUE NO (auditoria de frontera, 30/10/2026):
- «Revisalo» y «No se cierra»: una persona.
- Una orden ya DEVUELTA al tecnico (vuelta > 1): su ticket pudo cerrarse y
  reabrirse en el ISP en la vuelta anterior, y nadie lo sabe desde aca (H4).
- Una de falla cuya medicion despues del arreglo todavia no llego: la revision
  la marca «Revisalo» (H6). Si no se pudo saber cuales esperan medicion, no se
  cierra ninguna.

SI CAMBIO EN EL MEDIO: el ticket quedo cerrado y, mientras tanto, una persona
devolvio o valido la orden. No se pisa lo que hizo la persona; se deja una
ALERTA en la orden, porque el ticket del ISP dice una cosa y Dexter otra (H4).
================================================================================
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

SOMBRA = "sombra"
ACCION = "accion"

#: Lo que se anota en la bitacora de la orden.
EVENTO_BLOQUEADO = "cierre_del_supervisor_bloqueado"
EVENTO_CERRADA = "cerrada_por_el_supervisor"
EVENTO_DIVERGENCIA = "ticket_cerrado_con_la_orden_cambiada"
#: Se tomo ESTA orden para intentarla. Se escribe ANTES de hablarle al motor.
EVENTO_INTENTO = "cierre_del_supervisor_en_curso"

#: Cada cuanto se vuelve a intentar una orden que el motor no dejo cerrar. Una
#: persona puede despertar el ciclo con el boton; esto evita que cada toque
#: sea otro intento.
MINUTOS_ENTRE_INTENTOS = 60

#: Lo que el CRM le contesta a este lado y deja seguir: el ticket quedo
#: cerrado, ya lo estaba, o la orden no tiene ticket del ISP.
SIGUE = ("cerrado", "ya_cerrado", "sin_ticket")


def _tarea():
    from operaciones import tareas_delegadas as td
    return td.CERRAR_LO_REVISADO


def puertas(org) -> str:
    """Por que NO puede cerrar, o "" si puede. Texto fijo: va a un log."""
    import os

    from operaciones import autonomia
    from operaciones import tareas_delegadas as td

    if not (os.environ.get("MOTOR_TENANT", "") or "").strip():
        return "falta MOTOR_TENANT: sin saber de que empresa es el ticket, no se cierra"
    try:
        if not td.esta_delegada(org, _tarea()):
            return ("nadie le delego al Supervisor que cierre lo que da por "
                    "bueno: se le pide desde su chat")
    except Exception as e:                                       # noqa: BLE001
        return f"no se pudo comprobar la tarea ({type(e).__name__})"
    try:
        veredicto = autonomia.puede(org, td.CATALOGO[_tarea()]["exige_nivel"]) or {}
    except Exception as e:                                       # noqa: BLE001
        veredicto = {"puede": False, "motivo": type(e).__name__}
    if not veredicto.get("puede"):
        return "la empresa no tiene autorizado que el Supervisor cierre ordenes"
    return ""


def _reclamar(orden, ahora) -> bool:
    """Toma ESTA orden para intentarla, o dice que ya la tomo alguien.

    POR QUE UN RECLAMO Y NO UN 'select' PREVIO  --  auditoria de frontera,
    31/10/2026 (H6)
    ----------------------------------------------------------------------
    El reporte del tecnico y el "finalizar" son DOS peticiones, segundos
    aparte, y cada una despierta esta fase. Los dos filtros que habia se
    pueden pasar a la vez: `EVENTO_BLOQUEADO` solo existe si ya fallo, y el
    `_ya_cerrado` de `cierre_en_isp` es un select cuyo evento se escribe
    DESPUES del 200. La clave primaria del motor garantiza que a WispHub le
    llegue un solo POST --eso ya andaba-- pero el desenlace de la segunda
    tarea no era inocuo: escribia una alerta de divergencia falsa sobre el
    camino feliz, o apagaba los reintentos una hora, o dejaba la clave
    quemada y la orden sin poder cerrarse sola nunca mas.

    Esto serializa las dos sobre la FILA de la orden: la segunda espera a que
    la primera escriba su marca, la lee y se va. La transaccion se cierra
    ANTES de hablarle al motor -- ninguna transaccion abierta mientras se
    espera una operacion externa (CLAUDE.md §12).

    LA MARCA CADUCA con la misma ventana que los bloqueos: una tarea que se
    muera dejandola puesta no puede congelar la orden para siempre.
    """
    from campo.models import EventoTrabajo

    desde = ahora - timedelta(minutes=MINUTOS_ENTRE_INTENTOS)
    with transaction.atomic():
        #  El lock es sobre la orden y no sobre los eventos: es la fila que
        #  las dos tareas tienen en comun.
        type(orden).objects.select_for_update().filter(pk=orden.pk).first()
        if EventoTrabajo.objects.filter(
                org=orden.org, orden=orden,
                tipo__in=(EVENTO_BLOQUEADO, EVENTO_INTENTO),
                created_at__gte=desde).exists():
            return False
        EventoTrabajo.objects.create(org=orden.org, orden=orden,
                                     tipo=EVENTO_INTENTO, datos={})
    return True


def listas_para_cerrar(org, ahora, *, solo=None) -> list | None:
    """[(orden, revision)] que dio por buenas, o None si no se pudo saber
    cuales esperan medicion (y entonces no se cierra ninguna).

    `solo` acota a UNA orden (su pk) sin cambiar ni un criterio: lo usa el
    disparo inmediato de `cerrar_esta_orden`. Que el filtro viva en UN solo
    lugar es lo que evita que las dos entradas --el ciclo horario y el reporte
    recien llegado-- se separen el dia que se agregue una condicion.
    """
    from campo import revision_del_cierre as RC
    from campo.models import OrdenTrabajo

    pendientes = RC.pendientes_de_medir(org, ahora)
    if pendientes is None:
        return None
    candidatas = OrdenTrabajo.objects.filter(
        org=org, estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion__in=(OrdenTrabajo.PENDIENTE, OrdenTrabajo.REQUIERE_REVISION),
        vuelta__lte=1)
    if solo is not None:
        candidatas = candidatas.filter(pk=solo)
    salida = []
    for orden in candidatas:
        revision = RC.revisar(orden, pendientes=pendientes)
        if revision and revision["veredicto"] == RC.CERRAR:
            salida.append((orden, revision))
    return salida


def _intentar(orden, revision, ahora) -> str:
    """Cerrar UNA: afuera primero, adentro despues. Devuelve que paso.

    'salteada' | 'cerrada' | 'bloqueada' | 'divergencia' | 'cambio'. Lo
    comparten la fase horaria y el disparo inmediato: un camino nuevo que
    repitiera estos pasos a mano es como se pierde una de las guardas.
    """
    from campo.models import EventoTrabajo
    from campo.services import cierre_en_isp

    if not _reclamar(orden, ahora):
        return "salteada"
    ticket = cierre_en_isp.cerrar_ticket_por_el_supervisor(orden, revision)
    if ticket["estado"] not in SIGUE:
        EventoTrabajo.objects.create(
            org=orden.org, orden=orden, tipo=EVENTO_BLOQUEADO,
            datos={"estado": ticket["estado"], "detalle": ticket.get("detalle", "")})
        return "bloqueada"
    if _aprobar_y_cerrar(orden, revision, ticket):
        return "cerrada"
    if ticket["estado"] == "cerrado":
        EventoTrabajo.objects.create(
            org=orden.org, orden=orden, tipo=EVENTO_DIVERGENCIA,
            datos={"ticket_isp": ticket["estado"]})
        return "divergencia"
    return "cambio"


def cerrar_esta_orden(orden, *, ahora=None) -> dict:
    """EL MISMO CIERRE, APENAS LLEGA EL REPORTE  --  31/10/2026

    El usuario: «que después que el supervisor revise el ticket que mandó el
    técnico lo revise enseguida e indique si lo cierra o no». La fase de abajo
    corre una vez por hora; esto corre a los segundos, para ESTA orden.

    NO ES UNA SEGUNDA PUERTA. Pasa por `puertas()` y por `listas_para_cerrar`
    igual que la fase, con los mismos filtros --la vuelta, la medicion que
    falta, el veredicto-- y por `_intentar`, que es el mismo codigo. Lo unico
    que cambia es QUIEN la despierta y CUANTAS mira.

    Si todavia no corresponde --el reporte llego pero la orden aun no esta
    completada, o espera la medicion-- no escribe nada y lo dice. El ciclo
    horario la vuelve a mirar, que es la red de atras.
    """
    ahora = ahora or timezone.now()
    motivo = puertas(orden.org)
    if motivo:
        logger.info("Supervisor: cierre inmediato en sombra (%s)", motivo)
        return {"modo": SOMBRA, "por_que": motivo, "resultado": ""}
    listas = listas_para_cerrar(orden.org, ahora, solo=orden.pk)
    if listas is None:
        return {"modo": ACCION, "por_que": "no se pudo saber si espera la medicion",
                "resultado": ""}
    if not listas:
        #  TEXTO FIJO: puede ser que el veredicto no sea "se puede cerrar", que
        #  ya este validada, o que sea una vuelta posterior. La tarjeta ya
        #  muestra el veredicto con su detalle; aca solo interesa que no salio.
        return {"modo": ACCION, "por_que": "la revision no la dio por buena ahora",
                "resultado": ""}
    una, revision = listas[0]
    return {"modo": ACCION, "por_que": "", "resultado": _intentar(una, revision, ahora)}


def cerrar_lo_revisado(org, *, ahora=None) -> dict:
    """La fase. `{"cierre_de_lo_revisado": {...}}` para el resumen del ciclo."""
    ahora = ahora or timezone.now()
    listas = listas_para_cerrar(org, ahora)
    motivo = puertas(org)
    if listas is None:
        motivo = motivo or "no se pudo saber que ordenes esperan la medicion"
        listas = []
    if motivo:
        #  TEXTO FIJO y conteos: nada de la orden ni del cliente al log.
        logger.info("Supervisor: cierre de lo revisado en sombra (%s): cerraria %d",
                    motivo, len(listas))
        return {"cierre_de_lo_revisado": {"modo": SOMBRA, "por_que": motivo,
                                          "cerraria": len(listas), "cerradas": 0,
                                          "bloqueadas": 0}}
    cerradas = bloqueadas = 0
    for orden, revision in listas:
        paso = _intentar(orden, revision, ahora)
        if paso == "cerrada":
            cerradas += 1
        elif paso == "bloqueada":
            bloqueadas += 1
    return {"cierre_de_lo_revisado": {"modo": ACCION, "por_que": "",
                                      "cerraria": len(listas), "cerradas": cerradas,
                                      "bloqueadas": bloqueadas}}


def _aprobar_y_cerrar(orden, revision, ticket) -> bool:
    """Adentro, en una transaccion: aprobar y cerrar, a nombre del Supervisor
    (`profile=None`, y la bitacora lo dice). Si una persona la valido o la
    devolvio en el medio, no se pisa: se lee bajo bloqueo."""
    from campo.models import EventoTrabajo, OrdenTrabajo
    from campo.services.transiciones import aprobar, cerrar_orden

    motivos = "; ".join(p["texto"] for p in revision["puntos"])
    with transaction.atomic():
        fresca = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
        if (fresca.estado_operativo != OrdenTrabajo.COMPLETADA_CAMPO
                or fresca.estado_validacion not in (OrdenTrabajo.PENDIENTE,
                                                    OrdenTrabajo.REQUIERE_REVISION)
                or fresca.vuelta != orden.vuelta):
            return False
        from campo.revision_del_cierre import guardar_foto

        guardar_foto(fresca, revision)
        fresca = aprobar(fresca, profile=None,
                         observacion=f"Aprobada por el Supervisor: {motivos}")
        fresca = cerrar_orden(fresca, profile=None,
                              metadatos={"por": "supervisor", "ticket_isp": ticket["estado"]})
        EventoTrabajo.objects.create(
            org=fresca.org, orden=fresca, tipo=EVENTO_CERRADA,
            datos={"veredicto": revision["veredicto"], "ticket_isp": ticket["estado"],
                   "puntos": [p["clave"] for p in revision["puntos"]]})
    return True
