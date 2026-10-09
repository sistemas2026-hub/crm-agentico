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

from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from common.models import Notification, Org, Profile


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
    """Una notificacion por cada administrador. Devuelve cuantas se crearon.

    A los ADMIN y no a un rol "supervisor": `Profile.role` solo tiene
    ADMIN/USER, asi que inventar un destinatario por nombre seria adivinar.
    """
    destinatarios = list(
        Profile.objects.filter(org=org, role="ADMIN", is_active=True)
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

    if config.copia_la_jornada:
        resumen["jornadas"] = jornada_automatica.asegurar_jornadas(org, fecha)

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
        "sin_cuadrilla": [o.numero for o in propuesta["sin_cuadrilla"]],
        "sobrantes": [o.numero for o in propuesta["sobrantes"]],
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

    salida = {"corridas": [], "salteadas": 0, "errores": []}
    for org in Org.objects.filter(is_active=True):
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
        except Exception as e:                                   # noqa: BLE001
            # El tipo y no el texto: un mensaje de excepcion puede arrastrar
            # datos de cliente, y esto queda en el log del worker.
            salida["errores"].append({"org": str(org.id),
                                      "error": type(e).__name__})
    return salida
