# -*- coding: utf-8 -*-
"""
================================================================================
 EL CICLO DE LA MADRUGADA  --  deja el dia armado y dice que hay que mirar
================================================================================

QUE HACE, Y QUE NO
------------------
Hace dos cosas que SOLO se pueden hacer de noche:

    1. deja armada la jornada de cada cuadrilla (ver `jornada_automatica`)
    2. mira que quedo empezado y sin cerrar, y POR QUE (ver `pendientes_de_ayer`)

y despues avisa. **No publica el reparto.** `reparto.proponer()` no escribe
nada y se recalcula cuando alguien abre la pantalla, asi que guardar aqui una
propuesta de las tres de la mañana solo lograria servirla vieja a las siete.
Se calcula igual, pero para CONTAR -- para que el aviso diga cuantas se
repartirian y cuantas no, no para dejarla escrita.

Eso mantiene el shadow mode intacto: el Supervisor NOC recomienda, nunca hace.
Una persona sigue publicando.

POR QUE CORRE SEGUIDO Y NO A UNA HORA FIJA
------------------------------------------
Celery beat corre en UTC (`TIME_ZONE = "UTC"`) y cada empresa lleva su propia
`Org.timezone`. Una entrada `crontab(hour=3)` serian las 3 UTC: las 10 de la
noche ANTERIOR en Bogota, y otra hora distinta para la siguiente empresa.

Entonces la tarea se dispara cada hora y cada empresa decide si ya es SU hora.
El dia que entre un ISP en otro huso funciona sin tocar codigo -- que es la
regla de multi-tenant que este proyecto ya aprendio con el subdominio de
SmartOLT.

QUE NO SE REPITE
----------------
`ultima_corrida` guarda el ultimo dia LOCAL en que corrio. Sin eso, todas las
disparadas posteriores a la hora volverian a avisar: armar jornadas es
idempotente y no duplicaria nada, pero el supervisor abriria la plataforma con
el mismo aviso veinte veces y dejaria de leerlos.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from common.models import Notification, Org, Profile

logger = logging.getLogger(__name__)


def _ahora_local(org):
    """La hora de ESA empresa, no la del servidor.

    `Org.timezone` existe justamente porque el dia de una empresa no puede
    depender de donde este desplegado el contenedor -- ver el comentario de
    `TIME_ZONE` en settings, que cuenta cuando esto estuvo mal.
    """
    import zoneinfo

    nombre = (getattr(org, "timezone", "") or "UTC").strip() or "UTC"
    try:
        zona = zoneinfo.ZoneInfo(nombre)
    except Exception:                                            # noqa: BLE001
        # Una zona mal escrita no puede dejar a la empresa sin ciclo: se cae a
        # UTC y el aviso dira una hora rara, que es visible. Saltearla seria
        # un silencio.
        zona = zoneinfo.ZoneInfo("UTC")
    return timezone.now().astimezone(zona)


def _las_cuadrillas_no_trabajan(org, fecha) -> str:
    """Por que las cuadrillas no trabajan ese dia, o "" si trabajan o si la
    empresa no cargo su horario (sin el no se sabe, y se arma como siempre)."""
    from campo.horario_de_cuadrillas import calendario_de_cuadrillas
    from operaciones import capacidad

    try:
        if calendario_de_cuadrillas(org) is None:
            return ""
        jornada = capacidad.jornada_de(org, fecha, solo_de_cuadrillas=True)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("Ciclo de la madrugada: no se pudo leer el horario de "
                       "las cuadrillas (%s)", type(e).__name__)
        return ""
    return "" if jornada.abierta else (jornada.motivo or "cerrada")


def _le_toca(config, ahora_local) -> bool:
    """Si a esta empresa le toca ahora, y no corrio ya hoy."""
    if not config.activo:
        return False
    if config.ultima_corrida == ahora_local.date():
        return False
    # `>=` y no `==`: la tarea corre cada hora, y si una corrida se perdio
    # --el worker estaba caido, el despliegue tardo-- a la hora siguiente se
    # recupera en vez de saltearse el dia entero.
    return ahora_local.hour >= config.hora_local


def _avisar(org, resumen) -> int:
    """Una notificacion por cada persona que PUEDE publicar. Devuelve cuantas.

    A `ROLES_GESTION`, NO solo a los ADMIN  --  13/10/2026
    -----------------------------------------------------
    Esta funcion avisaba unicamente a `role="ADMIN"`, y lo justificaba
    diciendo que «`Profile.role` solo tiene ADMIN/USER, asi que inventar un
    destinatario por nombre seria adivinar». **Eso dejo de ser cierto en
    M09-D**: `common/utils.py::ROLES` tiene CUATRO
    --ADMIN, SUPERVISOR, OPERACIONES, USER-- y el propio paso M09-D existe
    para que alguien pueda *revisar sin administrar*
    (`Profile.save()` deja a un OPERACIONES con `is_organization_admin=False`
    a proposito).

    La consecuencia era silenciosa y exacta: la empresa que le da el rol
    OPERACIONES a su Jefe de Operaciones --la persona cuyo trabajo es mirar y
    publicar el reparto-- no recibia NINGUN aviso de que la jornada estaba
    lista. El ciclo corria, armaba todo, y nadie se enteraba.

    El conjunto no se escribe de nuevo aca: se importa el MISMO que decide
    quien puede publicar (`campo/permissions.py::ROLES_GESTION`, el que ya usa
    `operaciones/permissions.py` y la pantalla de cuadrillas). Dos listas con
    el mismo proposito se separan en silencio el dia que alguna cambie --y es
    justo lo que acababa de pasar.
    """
    from campo.permissions import ROLES_GESTION

    destinatarios = list(
        Profile.objects.filter(org=org, role__in=sorted(ROLES_GESTION),
                               is_active=True)
    )
    if not destinatarios:
        return 0

    Notification.objects.bulk_create([
        Notification(
            org=org,
            recipient=p,
            verb="reparto_de_la_madrugada",
            entity_type="campo.reparto",
            entity_name=f"Jornada del {resumen['fecha']}",
            data=resumen,
            link=f"/supervisor-noc/cuadrillas?dia={resumen['fecha']}&reparto=1",
        )
        for p in destinatarios
    ])
    return len(destinatarios)


def correr_para(org, *, ahora_local=None, avisar=True) -> dict:
    """El ciclo de una empresa. Separado de la tarea para poder correrlo a mano.

    Devuelve lo que paso, con nombres y numeros: un resumen sin nombres
    obliga a salir a buscar cual cuadrilla quedo sin zona.
    """
    from campo.cuadrillas import configuracion_de_reparto
    from campo import jornada_automatica, pendientes_de_ayer, reparto

    if ahora_local is None:
        ahora_local = _ahora_local(org)
    fecha = ahora_local.date()
    config = configuracion_de_reparto(org)

    resumen = {"fecha": fecha.isoformat(), "jornadas": None,
               "reparto": None, "pendientes": None}

    #  UN DIA QUE LAS CUADRILLAS NO TRABAJAN NO SE ARMA  --  25/10/2026. La
    #  simulacion del dia mostro las cinco cuadrillas armadas un domingo: la
    #  madrugada armaba todos los dias y el Supervisor no (el mira el horario,
    #  `armado_de_jornadas._la_empresa_trabaja`). Solo cuando la empresa cargo
    #  el horario de las cuadrillas: sin el, la madrugada sigue como estaba
    #  (decision del 21/10).
    no_se_trabaja = _las_cuadrillas_no_trabajan(org, fecha)
    if config.copia_la_jornada and no_se_trabaja:
        resumen["jornadas"] = {"no_se_arma": no_se_trabaja}
    elif config.copia_la_jornada:
        #  LA MISMA REGLA QUE EL SUPERVISOR  --  17/10/2026: la labor sale de
        #  los casos de Despacho de cada zona. Con los barrios ya guardados y
        #  sin pedir ninguno: a esta hora no se le pregunta al ISP. Si contar
        #  falla, cada cuadrilla sale con su labor habitual.
        try:
            from operaciones import armado_de_jornadas as adj
            demanda = adj.demanda_de_despacho(
                org, adj.propuestas_en_despacho(org))["por_zona"]
        except Exception as e:                                   # noqa: BLE001
            logger.warning("Ciclo de la madrugada: no se pudo contar la "
                           "demanda de Despacho (%s)", type(e).__name__)
            demanda = {}
        resumen["jornadas"] = jornada_automatica.asegurar_jornadas(
            org, fecha, demanda=demanda)

    #  SE CALCULA PARA CONTAR, NO PARA GUARDAR. La propuesta se recalcula sola
    #  cuando alguien abre la pantalla; esto es para que el aviso pueda decir
    #  cuanto quedaria sin repartir, que es lo que hace falta mirar.
    propuesta = reparto.proponer(org, fecha)
    resumen["reparto"] = {
        "repartibles": sum(len(a["ordenes"]) for a in propuesta["asignaciones"]),
        "cuadrillas": len(propuesta["asignaciones"]),
        # Las tres formas de NO repartir, separadas: cada una se arregla de
        # una manera distinta y juntarlas en un numero las vuelve inaccionables.
        "sin_zona": [o.numero for o in propuesta["sin_zona"]],
        "a_mano": [o.numero for o in propuesta.get("a_mano", [])],
        "sin_cuadrilla": [o.numero for o in propuesta["sin_cuadrilla"]],
        "sobrantes": [o.numero for o in propuesta["sobrantes"]],
        "otro_dia": [o.numero for o in propuesta.get("otro_dia", [])],
        "empezadas": [o.numero for o in propuesta.get("empezadas", [])],
        # El tipo de trabajo sin labor declarada. Va en el aviso porque se
        # arregla UNA vez en el catalogo y despues no vuelve a aparecer --
        # pero mientras nadie lo haga, esas ordenes no se reparten.
        "sin_clasificar": [o.numero for o in propuesta["sin_clasificar"]],
        "tipos_sin_clasificar": sorted({
            o.tipo_trabajo_version.work_type.codigo
            for o in propuesta["sin_clasificar"]
            if getattr(getattr(o, "tipo_trabajo_version", None),
                       "work_type", None)
        }),
    }

    resumen["pendientes"] = pendientes_de_ayer.revisar(org)

    avisados = 0
    if avisar:
        avisados = _avisar(org, resumen)
    resumen["avisados"] = avisados

    #  La marca se escribe AL FINAL y solo si hubo fila de configuracion: con
    #  los valores de fabrica no hay nada que marcar, y escribir una fila
    #  nueva aqui encenderia el ciclo de una empresa que nunca lo pidio.
    from campo.cuadrillas import ConfiguracionDeReparto
    with transaction.atomic():
        ConfiguracionDeReparto.objects.filter(org=org).update(
            ultima_corrida=fecha
        )
    return resumen


@shared_task(name="campo.tasks.recordar_reportes")
def recordar_reportes() -> dict:
    """Cada 5 minutos: el Supervisor le recuerda al tecnico la orden que paso la
    ventana sin reporte (`campo/recordatorio_de_reporte.py`). Cada empresa con
    su contexto y en su propio try/except, como el ciclo de abajo."""
    from campo.recordatorio_de_reporte import recordar_para
    from common.tasks import clear_rls_context, set_rls_context

    salida = {"vencidas": 0, "avisadas": 0, "errores": []}
    try:
        for org in Org.objects.filter(is_active=True):
            set_rls_context(org.id)
            try:
                r = recordar_para(org)
                salida["vencidas"] += r["vencidas"]
                salida["avisadas"] += r["avisadas"]
            except Exception as e:                               # noqa: BLE001
                salida["errores"].append({"org": str(org.id),
                                          "error": type(e).__name__})
    finally:
        clear_rls_context()
    return salida


@shared_task(name="campo.tasks.ciclo_de_la_madrugada")
def ciclo_de_la_madrugada() -> dict:
    """Recorre las empresas y corre el ciclo de las que les toca.

    CADA EMPRESA EN SU PROPIO try/except, y no es opcional: una config rota o
    una zona horaria mal escrita no pueden dejar sin jornada a las demas. Es
    el mismo aislamiento que `nucleo/reloj.py` ya aprendio a tener, y por el
    mismo motivo -- alla una excepcion dejo un trabajo muerto un mes entero,
    sin log y sin sintoma.
    """
    from campo.cuadrillas import configuracion_de_reparto
    from common.tasks import clear_rls_context, set_rls_context

    salida = {"corridas": [], "salteadas": 0, "errores": []}
    #  EL CONTEXTO DE CADA EMPRESA  --  auditor de frontera, 17/10/2026. Esta
    #  tarea nunca lo fijaba: las tablas de Cuadrillas no tienen RLS y por eso
    #  la jornada se armaba igual, pero las ausencias, los casos de Despacho y
    #  las notificaciones si la tienen, y sin contexto devuelven cero filas sin
    #  error. Armaba con el lider ausente y el aviso fallaba. Mismo patron que
    #  `operaciones.tasks.ciclo_del_supervisor`, con el `finally` por el mismo
    #  motivo: la variable es de sesion y la conexion vuelve al pool.
    try:
        for org in Org.objects.filter(is_active=True):
            set_rls_context(org.id)
            try:
                config = configuracion_de_reparto(org)
                ahora_local = _ahora_local(org)
                if not _le_toca(config, ahora_local):
                    salida["salteadas"] += 1
                    continue
                salida["corridas"].append({
                    "org": str(org.id),
                    **correr_para(org, ahora_local=ahora_local),
                })
            except Exception as e:                               # noqa: BLE001
                # El tipo y no el texto: un mensaje de excepcion puede
                # arrastrar datos de cliente, y esto queda en el log del worker.
                salida["errores"].append({"org": str(org.id),
                                          "error": type(e).__name__})
    finally:
        clear_rls_context()
    return salida
