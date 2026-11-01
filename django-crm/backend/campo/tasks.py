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


@shared_task(name="campo.tasks.revisar_el_cierre_ya")
def revisar_el_cierre_ya(org_id: str, orden_id: str) -> dict:
    """El Supervisor mira ESTA orden apenas el tecnico manda su reporte.

    POR QUE UNA TAREA Y NO DENTRO DE LA PETICION  --  31/10/2026
    ------------------------------------------------------------
    Este camino le habla al ISP por HTTP (`campo/services/cierre_en_isp.py`).
    Hacerlo dentro del POST del tecnico lo dejaria esperando en la calle a que
    WispHub conteste, y dejaria una transaccion de base abierta mientras se
    espera una operacion externa -- lo que CLAUDE.md §12 prohibe con todas las
    letras.

    NUNCA LEVANTA. El reporte del tecnico ya quedo guardado (un hecho) y el
    cierre es otro: que el segundo falle no puede hacer que la app reintente
    el primero. Lo que pase queda en la bitacora de la orden, igual que en la
    fase horaria.

    ES UNA ACELERACION, NO UNA PUERTA: pasa por las mismas de siempre, y si
    algo no da, el ciclo de cada hora la vuelve a mirar.
    """
    from campo.cierre_por_el_supervisor import cerrar_esta_orden
    from campo.models import OrdenTrabajo
    from common.tasks import clear_rls_context, set_rls_context

    try:
        #  EL CONTEXTO ANTES DE LEER LA ORDEN: estas tablas tienen RLS, y sin
        #  esto el `get` no encuentra nada y la tarea informaria "ya no esta"
        #  siendo que no pudo verla.
        set_rls_context(org_id)
        try:
            orden = OrdenTrabajo.objects.get(pk=orden_id, org_id=org_id)
        except OrdenTrabajo.DoesNotExist:
            return {"resultado": "", "por_que": "la orden ya no esta"}
        return cerrar_esta_orden(orden)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("cierre inmediato: fallo (%s)", type(e).__name__)
        return {"resultado": "", "por_que": type(e).__name__}
    finally:
        #  La variable es de SESION y la conexion vuelve al pool: mismo motivo
        #  que el `finally` del ciclo del Supervisor.
        clear_rls_context()


def pedir_revision_del_cierre(orden) -> None:
    """Despierta al Supervisor sobre esta orden, DESPUES del commit.

    `on_commit` y no la llamada directa: la tarea vuelve a leer la orden de la
    base, en otro proceso. Encolada antes del commit, el worker puede ganarle
    a la escritura y leer el estado viejo -- el reporte que acaba de llegar no
    estaria todavia, y la revision diria que falta.

    NO TUMBA LA PETICION DEL TECNICO. Si el broker no esta --local sin Redis,
    o una corrida de pruebas-- el tecnico igual reporto, que es lo que vino a
    hacer. El ciclo horario es la red de atras.
    """
    def _encolar():
        try:
            revisar_el_cierre_ya.delay(str(orden.org_id), str(orden.id))
        except Exception as e:                                   # noqa: BLE001
            logger.warning("cierre inmediato: no se pudo encolar (%s)",
                           type(e).__name__)

    transaction.on_commit(_encolar)


@shared_task(name="campo.tasks.analizar_evidencia")
def analizar_evidencia(org_id: str, evidencia_id: str) -> dict:
    """Mira la foto que el tecnico acaba de confirmar (31/10/2026).

    MISMO CONTRATO QUE 'revisar_el_cierre_ya', y por los mismos motivos:
    fuera de la peticion porque le habla a un tercero por HTTP --el tecnico
    esta parado en la calle, y una transaccion de base abierta esperando una
    operacion externa es lo que CLAUDE.md §12 prohibe--, con el contexto RLS
    antes de leer, el 'finally' que lo limpia, y sin levantar nunca.

    APPEND-ONLY: cada intento es una fila. Si se reintenta quedan las dos, y
    es a proposito -- ver 'campo/analisis_de_evidencia.py'.
    """
    from campo import inspeccion_visual as IV
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo
    from common.tasks import clear_rls_context, set_rls_context

    try:
        set_rls_context(org_id)
        try:
            evidencia = (EvidenciaTrabajo.objects
                         .select_related("orden_trabajo__tipo_trabajo_version")
                         .get(pk=evidencia_id, org_id=org_id))
        except EvidenciaTrabajo.DoesNotExist:
            return {"estado": "", "motivo": "la evidencia ya no esta"}

        r = IV.analizar(evidencia)
        #  APAGADO NO DEJA RASTRO (revisor de PII, 31/10/2026, H1). Si la
        #  empresa no lo tiene habilitado, no se escribe fila: con la fila
        #  escrita, `punto_de_la_revision` veia "ninguna se pudo mirar",
        #  devolvia el punto en "no se sabe" y el veredicto pasaba a REVISAR
        #  -- o sea que la funcion APAGADA, que es el default, habria frenado
        #  el cierre autonomo del Supervisor en toda orden con evidencia.
        #
        #  Un FALLO si se guarda, y la diferencia importa: un fallo hay que
        #  poder verlo; "esta empresa no lo pidio" no es nada que haya pasado.
        if r["motivo"] == IV.MOTIVO_APAGADO:
            return {"estado": "", "motivo": r["motivo"]}

        #  'pide_atencion' LO ESCRIBE EL CODIGO, no el modelo: es la unica
        #  senal que llega a la revision del cierre.
        AnalisisDeEvidencia.objects.create(
            org_id=org_id, evidencia=evidencia, vuelta=evidencia.vuelta,
            origen=AnalisisDeEvidencia.IA,
            texto=r["texto"], motivo=r["motivo"],
            pide_atencion=_pide_atencion(r["texto"]),
            modelo=r["modelo"], segundos=r["segundos"] or 0,
            tokens=r["tokens"] or 0)
        return {"estado": r["estado"], "motivo": r["motivo"]}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("inspeccion visual: fallo (%s)", type(e).__name__)
        return {"estado": "", "motivo": type(e).__name__}
    finally:
        #  De SESION, y la conexion vuelve al pool.
        clear_rls_context()


#: Lo que hace que una foto se marque para mirar. Son palabras que el propio
#: analizador usa cuando algo no cuadra o no se puede determinar. Es un
#: criterio GRUESO y esta bien que lo sea: su unica consecuencia es que la
#: tarjeta diga "revisá las fotos", NUNCA que una orden no se cierre.
PALABRAS_QUE_PIDEN_MIRAR = (
    "suelto", "sueltos", "desconectad", "no se ve", "no se puede",
    "borros", "oscur", "tapad", "fuera de cuadro", "no se alcanza",
    "parece no", "sin fijar", "deteriorad", "dañad", "danad",
)


def _pide_atencion(texto: str) -> bool:
    """Si este analisis amerita que una persona lo lea. Falla hacia MIRAR.

    Sin texto no se marca --eso ya lo cuenta 'motivo' por separado-- y con
    texto, cualquier palabra de la lista alcanza. Preferir el falso positivo
    es lo correcto aca: el costo de marcar de mas es que alguien lea un
    parrafo; el de marcar de menos es que una foto mala pase sin que nadie la
    mire. Y marcar de mas no puede frenar nada.
    """
    bajo = (texto or "").lower()
    return any(p in bajo for p in PALABRAS_QUE_PIDEN_MIRAR)


def pedir_analisis_de_la_foto(evidencia) -> None:
    """Despierta el analisis de ESTA evidencia, DESPUES del commit.

    Mismo razonamiento que 'pedir_revision_del_cierre': la tarea vuelve a leer
    de la base en otro proceso, y encolada antes del commit puede ganarle a la
    escritura. Si el broker no esta, el tecnico igual subio su foto -- que es
    lo que vino a hacer.
    """
    def _encolar():
        try:
            analizar_evidencia.delay(str(evidencia.org_id), str(evidencia.id))
        except Exception as e:                                   # noqa: BLE001
            logger.warning("inspeccion visual: no se pudo encolar (%s)",
                           type(e).__name__)

    transaction.on_commit(_encolar)


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

    salida = {"corridas": [], "salteadas": 0, "errores": [], "posiciones_borradas": 0}
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
                #  DONDE ESTUVO CADA TECNICO NO VIVE PARA SIEMPRE (revisor
                #  de PII, 31/10/2026). Va ANTES del `_le_toca`: si colgara
                #  del ciclo que si le toca, la empresa cuyo ciclo no corre
                #  hoy no barreria nunca, que es justo el caso que deja una
                #  posicion vieja años. Barrer de mas no cuesta: es un delete
                #  por fecha sobre una tabla de una fila por persona.
                from campo.ubicacion_de_cuadrilla import purgar
                salida["posiciones_borradas"] += purgar(org)

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


@shared_task(name="campo.tasks.avisar_visita_al_cliente")
def avisar_visita_al_cliente(orden_id, org_id, fecha_iso, vuelta=0):
    """Le pide al motor el aviso de visita programada de una orden (PRD §8.17).

    Decide el motor (nucleo/seguimiento/avisos.py). Si contesta 'todavia_no'
    --la publicacion fue de madrugada--, se reagenda para cuando abre el
    horario. Un motor caido no rompe nada: el aviso no sale y queda en el log.
    """
    import datetime as dt

    from campo.models import OrdenTrabajo
    from campo.services.aviso_de_visita import pedido, por_que_no_avisar
    from common import avisos_al_cliente
    from common.tasks import _motor, clear_rls_context, set_rls_context
    from operaciones import areas_del_tenant

    url, _ = _motor(org_id)
    if not url:
        logger.info("avisar_visita_al_cliente: el asistente no esta configurado")
        return None
    #  LA EMPRESA DE LA ORDEN, no la del entorno: con dos empresas en la
    #  instalacion, el aviso de un cliente de la segunda saldria desde el
    #  WhatsApp de la primera. Sin empresa resuelta no se pide nada.
    tenant = areas_del_tenant.tenant_de_organizacion(org_id)
    if not tenant:
        logger.info("avisar_visita_al_cliente: sin empresa para la org, no se pide (orden=%s)", orden_id)
        return None
    set_rls_context(org_id)
    try:
        orden = OrdenTrabajo.objects.select_related("org").filter(id=orden_id, org_id=org_id).first()
        if orden is None:
            return None
        fecha = dt.date.fromisoformat(fecha_iso)
        motivo = por_que_no_avisar(orden, fecha)
        if motivo:
            logger.info("avisar_visita_al_cliente: orden=%s no se avisa (%s)", orden_id, motivo)
            return {"enviado": False, "motivo": motivo}
        cuerpo = pedido(orden, fecha, tenant)
    finally:
        clear_rls_context()
    datos = avisos_al_cliente.pedir(url, cuerpo, f"visita orden={orden_id}")
    espera = avisos_al_cliente.reagendar_en(datos, vuelta)
    if espera is not None:
        avisar_visita_al_cliente.apply_async(
            args=[orden_id, org_id, fecha_iso, vuelta + 1], countdown=espera)
    return datos
