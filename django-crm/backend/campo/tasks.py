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


#  `max_retries=None` VA EN EL DECORADOR, no en la llamada a `retry` (21/11/2026,
#  medido por el auditor con un worker real): pasarlo a `self.retry(...)` NO
#  significa «sin tope», significa «usa el de la tarea», y el de la tarea es 3.
#  Con eso esta tarea esperaba 9 s y moria con MaxRetriesExceededError, sin
#  cerrar y sin rastro. El tope de verdad es `TOPE_DE_ESPERAS`.
@shared_task(bind=True, max_retries=None,
             name="campo.tasks.revisar_el_cierre_ya")
def revisar_el_cierre_ya(self, org_id: str, orden_id: str) -> dict:
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

    #  EL CIERRE NO LE GANA AL REPORTE  --  21/11/2026
    #
    #  Desde hoy la nota del tecnico al ISP sale por su propia tarea
    #  (`anotar_en_el_isp`), no dentro de su peticion. Cada nota deja el
    #  ticket En Progreso; si este camino cerrara el ticket ANTES de que esa
    #  nota llegue, la nota lo reabriria y nadie lo veria. Mientras haya una
    #  nota de esta orden en vuelo, esta tarea se reprograma. FUERA del `try`
    #  de abajo a proposito: ese `try` se traga todo, y se tragaria tambien
    #  el reintento.
    if _hay_que_esperar_a_las_notas(self, orden_id):
        raise self.retry(countdown=ESPERA_ENTRE_NOTAS)

    try:
        #  EL CONTEXTO ANTES DE LEER LA ORDEN: estas tablas tienen RLS, y sin
        #  esto el `get` no encuentra nada y la tarea informaria "ya no esta"
        #  siendo que no pudo verla.
        set_rls_context(org_id)
        try:
            orden = OrdenTrabajo.objects.get(pk=orden_id, org_id=org_id)
        except OrdenTrabajo.DoesNotExist:
            return {"resultado": "", "por_que": "la orden ya no esta"}
        #  LA MEDICION PRIMERO, Y EN ESTE MISMO WORKER  --  06/11/2026
        #
        #  El usuario: «el supervisor debe medir cuando le llega el reporte».
        #  Hasta hoy esta tarea corria enseguida y se encontraba con que la
        #  senal despues del arreglo todavia no estaba: la media el ciclo
        #  horario, que es otro proceso. La aceleracion llegaba a una pieza
        #  que nadie habia acelerado.
        #
        #  AQUI DENTRO Y NO EN OTRA TAREA, a proposito: dos tareas encoladas a
        #  la vez no tienen orden garantizado, y el cierre podia ganarle a la
        #  medicion y volver a decir que falta. Secuencial en un solo worker,
        #  con el contexto RLS ya puesto arriba.
        #
        #  ENVUELTO: si la medicion falla, el cierre igual se intenta. Puede
        #  cerrar por otro camino, y el ciclo horario reintenta la medicion.
        try:
            from operaciones.verificacion_de_arreglos import medir_este_arreglo

            medir_este_arreglo(orden)
        except Exception as e:                                   # noqa: BLE001
            logger.warning("medicion inmediata: fallo (%s)", type(e).__name__)

        #  Y LAS FOTOS, POR EL MISMO MOTIVO EXACTO  --  09/11/2026
        #
        #  Subir la foto encola una tarea; mandar el reporte encola esta. Sin
        #  esto, cuando el cierre le gana al analisis la revision decide sobre
        #  una foto que nadie miro -- y `punto_de_la_revision` ni la ve, asi
        #  que una orden con el resto en orden salia CERRAR. Ver
        #  `mirar_las_que_faltan`, que lo cuenta entero.
        #
        #  ENVUELTO IGUAL QUE LA MEDICION: si el modelo no contesta, el cierre
        #  se intenta y la foto sin fila deja el veredicto en REVISAR.
        try:
            mirar_las_que_faltan(orden)
        except Exception as e:                                   # noqa: BLE001
            logger.warning("mirada inmediata: fallo (%s)", type(e).__name__)

        #  Y EL COTEJO CONTRA EL TICKET  --  12/11/2026
        #
        #  El usuario: «no puede haber una respuesta correcta en un asunto
        #  que ni por ahi iba al caso». Va AQUI y no dentro de `revisar()`
        #  porque Programacion se refresca cada 15 segundos y cada refresco
        #  pasa por ahi: serian ~1.920 llamadas al modelo por orden y por
        #  dia, por cada supervisor con la pantalla abierta. Se calcula una
        #  vez, cuando el reporte llega, y la revision LEE la fila.
        #
        #  ANTES DE `cerrar_esta_orden` Y NO DESPUES: el cierre automatico
        #  consulta la revision, y la revision lee esta fila. Despues, la
        #  orden ya habria cerrado sin el punto -- el mismo error que el
        #  analisis de fotos tuvo el 09/11.
        #
        #  ENVUELTO, como la medicion y las fotos: si el motor no contesta,
        #  el cierre se intenta igual. Sin fila, el punto no aparece y la
        #  orden queda como estaba, que es lo correcto -- nunca se cierra de
        #  mas por un cotejo que no se pudo hacer.
        try:
            from campo.cotejo_del_reporte import cotejar_y_anotar

            cotejar_y_anotar(orden)
        except Exception as e:                                   # noqa: BLE001
            logger.warning("cotejo inmediato: fallo (%s)", type(e).__name__)

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


# ---------------------------------------------------------------------------
#  LA NOTA AL ISP SALE DESPUES DE CONTESTARLE AL TECNICO  --  21/11/2026
# ---------------------------------------------------------------------------
#
#  EL ERROR QUE LO ORIGINO. El usuario: «demoran en llegar los reportes del
#  tecnico que manda por app», y en el telefono «10 cambios necesitan que
#  alguien los revise». Leido en el codigo: marcar "en camino", "llegada" y
#  mandar el reporte le escribian al ISP DENTRO de la peticion del tecnico, y
#  esa llamada espera hasta 45 s (`nota_al_isp._pedir`). La app espera 20
#  (`api_client.dart`). Con el ISP lento la app se rendia, reintentaba con la
#  misma clave, recibia 409 «en curso» y dejaba el cambio como conflicto --
#  aunque el servidor SI lo habia aplicado.
#
#  Es ademas lo que CLAUDE.md §12 prohibe con todas las letras: esperar una
#  operacion externa con el tecnico parado en la calle. `revisar_el_cierre_ya`
#  y `analizar_evidencia` ya habian salido de la peticion por lo mismo; estas
#  dos notas habian quedado adentro.
#
#  LO QUE NO PUEDE PERDERSE AL SACARLAS: EL ORDEN. Dentro de la peticion las
#  notas salian una detras de otra porque la app no manda el cambio siguiente
#  hasta que le contestan el anterior. Un telefono que estuvo sin senal manda
#  "en camino", "llegada" y el reporte en el mismo segundo, y un worker de
#  Celery corre varias tareas a la vez: sin cuidado, el ticket diria "llego"
#  antes que "va en camino". Y cada nota deja el ticket En Progreso, asi que
#  una nota que llegue DESPUES del cierre lo reabre.
#
#  COMO SE CUIDA: cada nota pedida deja una MARCA en la cache compartida
#  hasta que su tarea termina. Una tarea no escribe mientras haya una marca
#  de un momento ANTERIOR de la misma orden: se reprograma. La marca vence
#  sola, asi que una tarea perdida no deja a las demas esperando para
#  siempre: pasado el tope, la siguiente sale igual.
#
#  LO QUE ESTO NO PROMETE (y la auditoria del 21/11/2026 lo dejo escrito):
#
#    - Si la cache no contesta, las marcas no existen y las notas salen sin
#      esperarse: pueden quedar desordenadas.
#    - Si el broker no esta, la nota no sale y queda dicho en la bitacora de
#      la orden (`nota_isp_no_anotada`, codigo `sin_cola`).
#    - Si el worker MUERE con la nota a medio escribir --un despliegue--, esa
#      nota se pierde SIN rastro: la tarea ya estaba tomada y nadie la
#      reintenta. Las que venian detras esperan su tope y salen. Antes del
#      cambio pasaba lo mismo si el despliegue cortaba la peticion.
#    - Una persona que aprueba y cierra en el mismo segundo en que el reporte
#      se esta escribiendo puede ganarle. La tarea no escribe si el ticket ya
#      cerro, pero entre mirar y escribir hay una llamada de hasta 45 s.

#: Segundos entre un intento y el siguiente mientras se espera a otra nota.
ESPERA_ENTRE_NOTAS = 3
#: Cuanto vive la marca de una nota en vuelo si NADIE la suelta. La suelta la
#: tarea al terminar, asi que esto solo cuenta para una tarea que se perdio.
#:
#: LARGA A PROPOSITO, y separada del tope de abajo (auditoria del 21/11/2026).
#: Con 120 s la marca vencia mientras la tarea todavia esperaba su turno en la
#: cola --un worker reiniciado por un despliegue, u ocupado con el ciclo del
#: Supervisor-- y al liberarse corrian las tres notas y el cierre a la vez,
#: sin orden. Una marca que dura no deja a nadie esperando de mas: lo que
#: acota la espera de cada tarea es `TOPE_DE_ESPERAS`, no esto.
VIDA_DE_LA_MARCA = 900
#: Cuantas veces se reprograma una tarea antes de salir igual: 60 x 3 s = 180 s.
#: Por encima de la cadena mas larga que puede tener adelante --tres notas de
#: 45 s cada una, 135 s--, para que el cierre no salga con el reporte todavia
#: escribiendose.
TOPE_DE_ESPERAS = 60


def _orden_de_las_notas() -> tuple:
    """En que orden se escriben en el ticket las notas de UNA orden."""
    from campo.services import nota_al_isp

    return (nota_al_isp.EN_CAMINO, nota_al_isp.EN_SITIO,
            nota_al_isp.REPORTE_DEL_TECNICO)


def _marca_de_nota(orden_id, momento: str) -> str:
    return f"campo:nota_isp_en_vuelo:{orden_id}:{momento}"


def _notas_en_vuelo(orden_id, antes_de: str | None = None) -> list:
    """Los momentos de esta orden con una nota todavia sin terminar.

    Con `antes_de`, solo los ANTERIORES a ese momento. Sin el, todos: es lo
    que pregunta el cierre, que va despues de cualquier nota.

    Si la cache no contesta devuelve vacio. Es la direccion correcta de
    fallar: no saber si hay algo en vuelo no puede dejar una nota sin salir.
    """
    from django.core.cache import cache

    momentos = _orden_de_las_notas()
    if antes_de is not None:
        if antes_de not in momentos:
            return []
        momentos = momentos[:momentos.index(antes_de)]
    if not momentos:
        return []
    try:
        vivas = cache.get_many([_marca_de_nota(orden_id, m) for m in momentos])
    except Exception as e:                                       # noqa: BLE001
        logger.warning("nota al ISP: la cache no contesto (%s)",
                       type(e).__name__)
        return []
    return [m for m in momentos if _marca_de_nota(orden_id, m) in vivas]


def _hay_que_esperar_a_las_notas(tarea, orden_id,
                                 antes_de: str | None = None) -> bool:
    """¿Esta tarea tiene que reprogramarse porque otra nota va primero?

    Tiene tope: una tarea que ya espero `TOPE_DE_ESPERAS` veces sale igual.
    Sin el, una marca que alguien dejara viva de mas seria una nota --o un
    cierre-- que no sale nunca, y eso es peor que un ticket desordenado.
    """
    intentos = int(getattr(getattr(tarea, "request", None), "retries", 0) or 0)
    if intentos >= TOPE_DE_ESPERAS:
        return False
    return bool(_notas_en_vuelo(orden_id, antes_de))


def _soltar_la_marca(orden_id, momento: str) -> None:
    from django.core.cache import cache

    try:
        cache.delete(_marca_de_nota(orden_id, momento))
    except Exception as e:                                       # noqa: BLE001
        logger.warning("nota al ISP: no se pudo soltar la marca (%s)",
                       type(e).__name__)


def pedir_nota_al_isp(orden, momento: str, profile=None) -> bool:
    """Deja pedida la nota al ISP y vuelve enseguida. Devuelve si se pidio.

    Es lo unico que hace la peticion del tecnico: nada de lo que sigue le
    habla a un tercero. La nota la escribe `anotar_en_el_isp`, despues del
    commit y en otro proceso.

    NO SE PIDE LO QUE NO VA A SALIR. Una orden que no nacio de un ticket del
    ISP, o una instalacion con la nota apagada, no encola nada: una tarea por
    cada "en camino" de cada orden, para que conteste «sin ticket», es
    trafico que no trae nada.

    NUNCA LEVANTA: el tecnico ya hizo lo que vino a hacer.
    """
    from django.core.cache import cache

    from campo.services import nota_al_isp

    try:
        if momento not in _orden_de_las_notas():
            return False
        if not nota_al_isp.hay_a_quien_anotar(orden):
            return False
        org_id, orden_id = str(orden.org_id), str(orden.id)
        vuelta = nota_al_isp._vuelta_de(orden)
        profile_id = str(profile.pk) if profile is not None else ""
    except Exception as e:                                       # noqa: BLE001
        logger.warning("nota al ISP: no se pudo pedir (%s)", type(e).__name__)
        return False

    #  LA MARCA SE DEJA AQUI Y NO EN LA TAREA: la tarea siguiente puede
    #  arrancar antes que esta, y tiene que encontrarla ya puesta.
    try:
        cache.set(_marca_de_nota(orden_id, momento), 1, VIDA_DE_LA_MARCA)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("nota al ISP: no se pudo marcar (%s)", type(e).__name__)

    def _encolar():
        try:
            anotar_en_el_isp.delay(org_id, orden_id, momento, vuelta,
                                   profile_id)
        except Exception as e:                                   # noqa: BLE001
            #  SIN COLA NO HAY NOTA, Y TIENE QUE QUEDAR DICHO. Hacerla aca
            #  mismo seria volver a esperar al ISP dentro de la peticion,
            #  justo cuando algo ya anda mal. Se suelta la marca para que
            #  nadie la espere, y la bitacora de la orden dice por que el
            #  ISP no se entero.
            logger.warning("nota al ISP: no se pudo encolar (%s)",
                           type(e).__name__)
            _soltar_la_marca(orden_id, momento)
            nota_al_isp._anotar_evento(
                orden, profile, nota_al_isp.EVENTO_NO_ANOTADA,
                {"momento": momento, "vuelta": vuelta, "codigo": "sin_cola",
                 "detalle": type(e).__name__})

    transaction.on_commit(_encolar)
    return True


#  `max_retries=None` EN EL DECORADOR: ver `revisar_el_cierre_ya`. Sin esto la
#  nota esperaba 9 s a la anterior y moria sin escribirse ni dejar rastro.
@shared_task(bind=True, max_retries=None, name="campo.tasks.anotar_en_el_isp")
def anotar_en_el_isp(self, org_id: str, orden_id: str, momento: str,
                     vuelta: int, profile_id: str = "") -> dict:
    """Escribe en el ticket del ISP lo que el tecnico acaba de hacer.

    MISMO CONTRATO QUE `revisar_el_cierre_ya`: fuera de la peticion porque le
    habla a un tercero, con el contexto RLS antes de leer, el `finally` que
    lo limpia, y sin levantar nunca -- salvo para reprogramarse.

    UNA SOLA VEZ AUNQUE CORRA DOS: el motor excluye por
    `orden|momento|vuelta` (`nucleo/seguimiento/nota_en_el_ticket.py`), asi
    que una tarea entregada dos veces contesta `ya_anotada` la segunda.

    LO QUE LLEGA TARDE NO SE ESCRIBE. La tarea vuelve a leer la orden, y si
    ya esta cerrada o cancelada, o ya va por otra vuelta, la nota no sale:
    dejaria En Progreso un ticket que ya cerro, o firmaria con la vuelta
    equivocada. Queda en la bitacora como `llego_tarde`.
    """
    from campo.models import OrdenTrabajo
    from campo.services import nota_al_isp
    from common.tasks import clear_rls_context, set_rls_context

    #  PRIMERO LAS ANTERIORES. Fuera del `try`, igual que en el cierre.
    if _hay_que_esperar_a_las_notas(self, orden_id, antes_de=momento):
        raise self.retry(countdown=ESPERA_ENTRE_NOTAS)

    try:
        #  La marca se renueva al empezar: lo que venga detras tiene que
        #  esperar mientras ESTA llamada dure, no solo desde que se pidio.
        try:
            from django.core.cache import cache

            cache.set(_marca_de_nota(orden_id, momento), 1, VIDA_DE_LA_MARCA)
        except Exception:                                        # noqa: BLE001
            pass

        set_rls_context(org_id)
        try:
            orden = OrdenTrabajo.objects.get(pk=orden_id, org_id=org_id)
        except OrdenTrabajo.DoesNotExist:
            return {"anotada": False, "codigo": "sin_orden"}
        profile = (Profile.objects.filter(pk=profile_id, org_id=org_id).first()
                   if profile_id else None)

        tarde = ""
        if orden.estado_operativo in (OrdenTrabajo.CERRADA,
                                      OrdenTrabajo.CANCELADA):
            tarde = f"la orden ya esta {orden.estado_operativo}"
        elif nota_al_isp._vuelta_de(orden) != int(vuelta or 1):
            tarde = (f"se pidio en la vuelta {vuelta} y la orden va por la "
                     f"{nota_al_isp._vuelta_de(orden)}")
        else:
            #  EL TICKET PUEDE CERRAR CON LA ORDEN TODAVIA ABIERTA (auditoria
            #  del 21/11/2026). Aprobar a mano y el ciclo de cada hora cierran
            #  el ticket del ISP sin mirar las marcas, y la orden sigue en
            #  `completada_campo` hasta el paso siguiente. Mirar solo el
            #  estado de la orden dejaba pasar esta nota por ese hueco, y
            #  reabria el ticket. Lo que dice si el ticket cerro es su evento.
            from campo.services import cierre_en_isp

            if cierre_en_isp._ya_cerrado(orden):
                tarde = "el ticket del ISP ya se cerro"
        if tarde:
            nota_al_isp._anotar_evento(
                orden, profile, nota_al_isp.EVENTO_NO_ANOTADA,
                {"momento": momento, "vuelta": vuelta,
                 "codigo": "llego_tarde", "detalle": tarde})
            return {"anotada": False, "codigo": "llego_tarde",
                    "detalle": tarde}

        if momento == nota_al_isp.REPORTE_DEL_TECNICO:
            return nota_al_isp.anotar_reporte_del_tecnico(orden, profile)
        return nota_al_isp.anotar_avance(orden, momento, profile=profile)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("nota al ISP: fallo (%s)", type(e).__name__)
        return {"anotada": False, "codigo": "fallo",
                "detalle": type(e).__name__}
    finally:
        _soltar_la_marca(orden_id, momento)
        clear_rls_context()


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
    from campo.models import EvidenciaTrabajo
    from common.tasks import clear_rls_context, set_rls_context

    try:
        set_rls_context(org_id)
        try:
            evidencia = (EvidenciaTrabajo.objects
                         .select_related("orden_trabajo__tipo_trabajo_version")
                         .get(pk=evidencia_id, org_id=org_id))
        except EvidenciaTrabajo.DoesNotExist:
            return {"estado": "", "motivo": "la evidencia ya no esta"}

        return _mirar_y_anotar(evidencia)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("inspeccion visual: fallo (%s)", type(e).__name__)
        return {"estado": "", "motivo": type(e).__name__}
    finally:
        #  De SESION, y la conexion vuelve al pool.
        clear_rls_context()


#: LO QUE EL MODELO ESCRIBE AL FINAL  --  05/11/2026
#:
#: La instruccion de evidencia (`nucleo/canales/vision.py::MARCA_ATENCION`) le
#: pide terminar con "ATENCION: si" o "ATENCION: no". Eso es lo que se lee.
#:
#: ES UN CONTRATO ENTRE DOS SERVICIOS y la cadena esta escrita en los dos
#: lados --el motor no importa de Django ni al reves--. Una prueba las ata:
#: `tests/test_vision_propositos.py`.
MARCA_ATENCION = "atencion:"

#: EL RESPALDO, para cuando el modelo no escribe la marca. Es GUIA, no
#: garantia (PRD 7.4), asi que no se puede depender de que siempre este.
#:
#: LO QUE SE SACO DE ESTA LISTA, Y POR QUE  --  medido el 04/11/2026
#: -----------------------------------------------------------------
#: Tenia tambien "no se ve", "no se puede", "borros", "oscur", "tapad" y
#: "fuera de cuadro". Y la instruccion de evidencia PIDE esas frases: sus
#: reglas dicen "si algo esta borroso, oscuro, tapado o fuera de cuadro,
#: decilo, y deci que no se puede determinar por eso" y "contesta si eso se
#: ve o no se ve". O sea: se le pedian las palabras y despues se usaban como
#: alarma.
#:
#: Resultado en produccion, OT 100: **4 de 4 fotos pedian una mirada**, y asi
#: iba a ser en todas. El costo no fue el ruido: el veredicto quedaba en
#: REVISAR y el cierre autonomo del Supervisor exige CERRAR, de modo que
#: ninguna orden con fotos se cerraba sola. Y un aviso que aparece siempre
#: deja de avisar: en una semana se aprueba sin leerlo, y el dia que una foto
#: este de verdad mal, pasa igual.
#:
#: Lo que queda son defectos del TRABAJO, no de la foto. Ninguno de estos
#: aparece en la instruccion, y una prueba lo comprueba.
#: Y POR QUE NO ESTAN "suelto" NI "sueltos", que son el defecto mas comun:
#: la regla 4 de la instruccion le PIDE al modelo decir «si hay cables
#: sueltos o conectores que parecen no estar puestos», asi que escribe la
#: palabra tambien cuando NO los hay --«no hay cables sueltos»-- y el
#: respaldo se equivocaria. Lo caza una prueba, que es como aparecio.
#:
#: Eso deja el respaldo mas flaco, y es la decision correcta: un cable suelto
#: lo reporta la MARCA, que es el juicio del modelo sobre lo que acaba de
#: mirar. El respaldo solo cubre palabras que la instruccion no le pide
#: nunca, y existe para el caso en que el modelo no escriba la marca.
PALABRAS_QUE_PIDEN_MIRAR = (
    "desconectad", "sin fijar", "deteriorad",
    "dañad", "danad", "mal instalad", "no sirve",
)


#: La marca que el modelo escribe cuando se le dijo QUE tenia que mostrar la
#: foto (`nucleo/canales/vision.py`, regla 12). Ver `muestra_lo_pedido`.
MARCA_MUESTRA = "muestra:"

#: La marca de la regla 13: si la imagen es material de producto en vez de una
#: foto del trabajo. Las dos grafias, con y sin tilde.
MARCAS_CATALOGO = ("catalogo:", "catálogo:")


def es_de_catalogo(texto: str):
    """`True` si la imagen es material de producto, `False` si no, `None` si
    el modelo no lo dijo.

    POR QUE SE BUSCA AL PRINCIPIO DE UNA LINEA, y no con `rfind` sobre todo el
    texto como `muestra_lo_pedido`  --  09/11/2026
    -----------------------------------------------------------------------
    Porque la palabra aparece en la prosa de estas mismas fotos. El analisis
    real que origino esto dice: «Equipo sobre fondo blanco, sin entorno de
    instalacion; imagen de catalogo.» Un `rfind("catalogo")` pegaria ahi, y
    de ahi en adelante el veredicto dependeria de como redacto el modelo esa
    frase, no de la marca que se le pidio. `muestra_lo_pedido` no tiene ese
    problema: nadie escribe «muestra:» en prosa.

    SIN MARCA, `None` -- nunca `True`. Un analisis viejo, de antes de la
    regla 13, no la trae, y tratar esa ausencia como «es de catalogo»
    devolveria ordenes por fotos que nadie miro con este criterio.
    """
    for linea in (texto or "").splitlines():
        bajo = linea.strip().lower()
        for marca in MARCAS_CATALOGO:
            if not bajo.startswith(marca):
                continue
            resto = bajo[len(marca):].strip()
            if resto.startswith(("si", "sí")):
                return True
            if resto.startswith("no"):
                return False
    return None


#: Lo que se puede afirmar de la correspondencia entre la foto y el requisito.
#: `None` NO es "esta bien": es "no se sabe", y esa diferencia es el motivo de
#: que esta funcion devuelva tres cosas y no un booleano. Un `False` por
#: defecto haria que una plantilla sin instrucciones --donde el modelo no
#: escribe la marca-- apareciera como si la foto no correspondiera.
def muestra_lo_pedido(texto: str):
    """`True` si la foto es lo que se pidio, `False` si no, `None` si no se sabe.

    SE LEE LA ULTIMA MARCA Y NO LA PRIMERA, igual que `_pide_atencion`: si el
    modelo la escribio dos veces, la de abajo es su conclusion.

    SIN MARCA SE DEVUELVE None, nunca False. La regla 12 le pide la marca
    SOLO cuando se le dijo que tenia que mostrar la foto, y una plantilla sin
    instrucciones no se la dice. Tratar esa ausencia como "no corresponde"
    marcaria en rojo cada foto de cada plantilla que todavia no escribio sus
    instrucciones.
    """
    bajo = (texto or "").lower()
    pos = bajo.rfind(MARCA_MUESTRA)
    if pos == -1:
        return None
    resto = bajo[pos + len(MARCA_MUESTRA):].strip()
    #  "no se sabe" ANTES que "no": empieza igual, y mirar "no" primero
    #  convertiria todo "no se sabe" en un "no corresponde".
    if resto.startswith(("no se sabe", "no se sabé", "nose sabe")):
        return None
    if resto.startswith(("si", "sí")):
        return True
    if resto.startswith("no"):
        return False
    return None


def _pide_atencion(texto: str) -> bool:
    """Si este analisis amerita que una persona lo lea.

    Primero LA MARCA, que es el juicio del modelo sobre lo que acaba de
    describir. Si no la escribio, se cae a las palabras --que ya no incluyen
    las que la propia instruccion exige--.

    Sin texto no se marca: eso ya lo cuenta `motivo` por separado.
    """
    bajo = (texto or "").lower()
    if not bajo.strip():
        return False
    #  La marca gana sobre todo lo demas: si el modelo dijo que no hace falta
    #  mirar, una palabra suelta en su descripcion no lo contradice.
    pos = bajo.rfind(MARCA_ATENCION)
    if pos != -1:
        resto = bajo[pos + len(MARCA_ATENCION):].strip()
        return resto.startswith(("si", "sí"))
    return any(p in bajo for p in PALABRAS_QUE_PIDEN_MIRAR)


def _mirar_y_anotar(evidencia) -> dict:
    """Mira UNA evidencia y escribe su analisis. El contexto RLS ya esta puesto.

    Esta afuera de la tarea para que la mirada inmediata del Supervisor
    (`mirar_las_que_faltan`) use EXACTAMENTE este codigo y no una copia: lo
    que se escriba por el camino acelerado tiene que ser indistinguible de lo
    que escribe la tarea, o el veredicto dependeria de quien miro la foto.
    """
    from campo import inspeccion_visual as IV
    from campo.models import AnalisisDeEvidencia

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
    if r["motivo"] in (IV.MOTIVO_APAGADO, IV.MOTIVO_DOCUMENTO):
        return {"estado": "", "motivo": r["motivo"]}

    #  'pide_atencion' LO ESCRIBE EL CODIGO, no el modelo: es la unica
    #  senal que llega a la revision del cierre.
    AnalisisDeEvidencia.objects.create(
        org_id=evidencia.org_id, evidencia=evidencia, vuelta=evidencia.vuelta,
        origen=AnalisisDeEvidencia.IA,
        texto=r["texto"], motivo=r["motivo"],
        pide_atencion=_pide_atencion(r["texto"]),
        modelo=r["modelo"], segundos=r["segundos"] or 0,
        tokens=r["tokens"] or 0)
    return {"estado": r["estado"], "motivo": r["motivo"]}


#: Cuantas fotos mira el camino acelerado antes de darse por vencido. Las
#: plantillas de hoy piden entre 4 y 8; el tope existe para que una plantilla
#: con treinta evidencias no deje la tarea colgada hablandole al modelo. Lo
#: que no alcance a mirar lo mira la tarea por foto, que sigue existiendo, y
#: el ciclo horario vuelve a revisar.
MAX_FOTOS_EN_EL_MOMENTO = 12

#: Cuantas veces se intenta mirar UNA foto antes de dejarla para una persona.
#: Cada intento deja su fila (append-only), asi que contarlas es contar los
#: intentos. Tres porque lo que se esta esquivando es un fallo transitorio de
#: red --el ReadTimeout de la OT #200--: si tres pasadas separadas por una
#: hora fallan, el problema no es el momento y reintentar mas solo le pega al
#: motor. Agotado el tope, el punto de la inspeccion dice que esa foto no se
#: pudo mirar y la orden espera a una persona, que es el desenlace correcto.
INTENTOS_POR_FOTO = 3


def mirar_las_que_faltan(orden) -> dict:
    """Las fotos de esta orden que todavia no tienen analisis, mirADAS AHORA.

    POR QUE ESTO EXISTE  --  09/11/2026
    -----------------------------------
    El usuario, despues de ver que una foto equivocada esperaba hasta el
    ciclo de la hora siguiente:

        «la orden no puede esperar cierto tiempo para devolverse. El proceso
        correcto es que apenas el tecnico mande el reporte el supervisor
        revisa y si encuentra algo malo devolver el ticket en ese mismo
        momento, para que el tecnico no se mueva hacia otro ticket y tenga
        que devolverse».

    Y el camino inmediato ya existia --`revisar_el_cierre_ya`-- pero decidia
    sobre fotos que nadie habia mirado todavia. Subir una foto encola
    `analizar_evidencia`; mandar el reporte encola `revisar_el_cierre_ya`.
    Son dos tareas en la cola SIN ORDEN GARANTIZADO, y cuando el cierre le
    gana al analisis, `inspeccion_visual.punto_de_la_revision` se encuentra
    sin ninguna fila y hace `if not analisis: return None`: la foto no
    aparece ni como «no se pudo mirar» -- NO APARECE. El veredicto se calcula
    sin ella.

    Eso tenia dos consecuencias, y la segunda es la grave:
      · la foto equivocada no se nombraba, y la devolucion automatica no
        pasaba hasta el ciclo horario -- lo que el usuario vio;
      · y el punto de la inspeccion quedaba fuera del veredicto, de modo que
        una orden con el checklist y la medicion en orden daba CERRAR. Con el
        cierre autonomo encendido, se cerraba sola SIN HABER MIRADO NINGUNA
        FOTO.

    ES EL MISMO ARREGLO QUE YA SE ELIGIO PARA LA MEDICION el 06/11 en esta
    misma tarea, con las mismas palabras: aqui dentro y no en otra tarea,
    secuencial, en un solo worker, con el contexto RLS ya puesto. «La
    aceleracion llegaba a una pieza que nadie habia acelerado.»

    NO ES UNA PUERTA NUEVA. No decide nada: solo hace que exista el dato que
    la revision ya iba a leer. Si el modelo no contesta, se escribe la fila
    con su motivo y el punto dice «no se pudieron mirar» -- que deja el
    veredicto en REVISAR y NO cierra. Falla cerrado.

    QUE MIRA: las evidencias con archivo recibido cuya ULTIMA vuelta no tiene
    analisis. Por requisito y no por `vuelta=orden.vuelta`, porque en una
    orden devuelta el tecnico rehace solo algunas fotos y las demas siguen en
    la vuelta anterior con su analisis ya escrito: filtrar por la vuelta
    actual las haria mirar de nuevo en cada devolucion, y pagar el modelo de
    nuevo por una foto que no cambio.
    """
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo

    #  La ultima evidencia de cada requisito: la vuelta pesa primero, igual
    #  que en `revision_del_cierre`. La app encola y reintenta, asi que una
    #  foto de la vuelta anterior puede llegar DESPUES de la rehecha.
    ultima = {}
    for ev in (EvidenciaTrabajo.objects
               .filter(org=orden.org, orden_trabajo=orden,
                       estado_archivo=EvidenciaTrabajo.RECIBIDO)
               .order_by("vuelta", "recibida_en_servidor")):
        ultima[ev.requisito_id] = ev
    #  Los documentos del cliente no se miran (inspeccion_visual): tampoco
    #  cuentan como «faltan por mirar».
    from campo import inspeccion_visual as _IV
    ultima = {k: v for k, v in ultima.items() if not _IV.es_documento_privado(v)}

    if not ultima:
        return {"miradas": 0, "faltaban": 0}

    #  UNA FILA DE UN INTENTO FALLIDO NO ES UN ANALISIS  --  10/11/2026, #200
    #
    #  EL CASO, MEDIDO EN PRODUCCION. La foto de `medicion_al_salir` de la OT
    #  #200 quedo con esta fila:
    #
    #      ia 15:17:31 v1  motivo=no se pudo hablar con el motor (ReadTimeout)
    #
    #  Texto vacio: el motor no contesto. La version anterior contaba
    #  CUALQUIER fila como «ya mirada», asi que esa foto no volvio a mirarse
    #  nunca. A las 16:33 --una hora y cuarto despues-- la orden seguia
    #  esperando a una persona, y nada iba a destrabarla: no habia tarea
    #  pendiente que terminar.
    #
    #  El docstring de arriba decia «la red de atras es la tarea por foto y
    #  el ciclo horario». `analizar_evidencia` no reintenta --devuelve el
    #  motivo y termina-- y el ciclo horario no llamaba a esta funcion. La
    #  red no existia. Eso es lo que CLAUDE.md §6 llama codigo construido que
    #  no corre, con el agravante de estar prometido por escrito.
    #
    #  CON TOPE, y por eso no basta con mirar el texto: si el motor esta
    #  caido de verdad, reintentar sin limite le pega a cada pasada del ciclo
    #  y por cada foto. Agotado el tope, la foto queda sin texto, el punto
    #  dice que no se pudo mirar y la orden espera a una persona -- que es el
    #  desenlace correcto para un fallo que ya no es transitorio.
    #
    #  APPEND-ONLY: cada intento suma una fila, nunca pisa la anterior, asi
    #  que contarlas ES contar los intentos (ver `analisis_de_evidencia.py`).
    filas = (AnalisisDeEvidencia.objects
             .filter(org=orden.org,
                     evidencia_id__in=[e.id for e in ultima.values()])
             .values_list("evidencia_id", "texto"))
    mirada, intentos = set(), {}
    for evidencia_id, texto in filas:
        intentos[evidencia_id] = intentos.get(evidencia_id, 0) + 1
        if (texto or "").strip():
            mirada.add(evidencia_id)
    faltan = [e for e in ultima.values()
              if e.id not in mirada
              and intentos.get(e.id, 0) < INTENTOS_POR_FOTO]

    miradas = _mirar_estas(faltan)

    #  SEGUNDA PASADA: LA MEDICION QUE NO SE SOSTIENE  --  11/11/2026
    #
    #  POR QUE  --  pedido del usuario, tras ver cerrar la OT #200
    #  -----------------------------------------------------------
    #  «o si mejor ese datos llene la app con la lectura que toma de la
    #  foto». La precondicion de eso es una lectura confiable, y hoy no lo
    #  es: el modelo le corre el punto decimal y lee «-2.10» donde la
    #  pantalla dice «-21.0». Medido 3 de cada 7 veces el 10/11, y en la
    #  propia #200 las dos veces que se miro esa foto.
    #
    #  El sistema hacia lo correcto con una lectura imposible --descartarla--
    #  pero descartar deja la medicion SIN VERIFICAR, y asi cerro la #200:
    #  el tecnico escribio -18.0, la pantalla marcaba -21.0, y nadie los
    #  comparo nunca. Una lectura sola no tiene con que validarse; dos si.
    #
    #  POR QUE ES UNA SEGUNDA PASADA Y NO LA MISMA LISTA. Las dos cosas
    #  pasan en esta misma llamada y en este orden a proposito: en el camino
    #  acelerado la cola puede no haber mirado ninguna foto todavia --que es
    #  exactamente como quedo atrapada la #200-- y `mediciones_para_releer`
    #  necesita las lecturas YA ESCRITAS para poder juzgarlas. Preguntando
    #  despues de la primera pasada, la relectura sale en el mismo momento en
    #  que el tecnico manda el reporte, que es lo que el usuario pidio el
    #  09/11: que la devolucion no espere al ciclo de la hora siguiente.
    #
    #  SE RECUENTAN LOS INTENTOS, no se reusa `intentos`: la primera pasada
    #  acaba de sumar filas y el tope tiene que verlas. Con el tope viejo una
    #  foto recien mirada podria releerse una vez de mas.
    #
    #  QUIEN DECIDE NO ES ESTA FUNCION. `revision_del_cierre` dice cuales y
    #  por que --es donde vive la comparacion, con su tolerancia y su filtro
    #  de lecturas imposibles-- y aca solo se ejecuta. Copiar ese criterio
    #  seria tener dos.
    relecturas = 0
    try:
        from campo import revision_del_cierre as RC

        pedidas = RC.mediciones_para_releer(orden)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("mirada inmediata: no se pudo decidir que releer (%s)",
                       type(e).__name__)
        pedidas = []
    if pedidas:
        ahora = dict(_intentos_por_evidencia(
            orden, [ultima[r].id for r in pedidas if r in ultima]))
        de_nuevo = [ultima[r] for r in pedidas
                    if r in ultima
                    and ahora.get(ultima[r].id, 0) < INTENTOS_POR_FOTO]
        relecturas = _mirar_estas(de_nuevo)

    return {"miradas": miradas, "faltaban": len(faltan),
            "relecturas": relecturas}


def _intentos_por_evidencia(orden, ids) -> dict:
    """Cuantas filas de analisis tiene cada evidencia. APPEND-ONLY: contarlas
    es contar los intentos (ver `campo/analisis_de_evidencia.py`)."""
    from campo.models import AnalisisDeEvidencia

    cuenta = {}
    for evidencia_id in (AnalisisDeEvidencia.objects
                         .filter(org=orden.org, evidencia_id__in=list(ids))
                         .values_list("evidencia_id", flat=True)):
        cuenta[evidencia_id] = cuenta.get(evidencia_id, 0) + 1
    return cuenta


def _mirar_estas(evidencias) -> int:
    """Mira esta lista de evidencias, con el tope por pasada. Devuelve
    cuantas se miraron.

    Se extrajo del cuerpo de `mirar_las_que_faltan` el 11/11/2026 porque
    ahora hay dos pasadas --las que no tienen analisis y las que hay que
    releer-- y lo que escriba cada una tiene que ser indistinguible: mismo
    `_mirar_y_anotar`, mismo tope, mismo manejo del fallo. Dos copias
    divergen, y el veredicto dependeria de por que camino se miro la foto.
    """
    miradas = 0
    for evidencia in list(evidencias)[:MAX_FOTOS_EN_EL_MOMENTO]:
        try:
            _mirar_y_anotar(evidencia)
            miradas += 1
        except Exception as e:                                   # noqa: BLE001
            #  UNA FOTO QUE FALLA NO FRENA A LAS DEMAS. Sin fila, el punto de
            #  la inspeccion no la ve, y eso ya quedaba igual que antes: la
            #  red de atras es la tarea por foto y el ciclo horario.
            logger.warning("mirada inmediata: fallo una foto (%s)",
                           type(e).__name__)
    return miradas


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


# =============================================================================
#  EL ALTA DEL CLIENTE EN EL ISP  --  25/11/2026
# =============================================================================
#: Cada cuanto se vuelve a mirar un alta que no termino, y cuantas veces. Doce
#: vueltas de medio minuto son seis minutos: mas que lo que el proveedor tarda
#: en crear, y menos que lo que un tecnico espera parado en una casa.
ESPERA_DEL_ALTA = 30
VUELTAS_DEL_ALTA = 12

#: Activar la ONU (26/11/2026): cada cuanto se vuelve a mirar y hasta cuando.
ESPERA_DE_LA_ONU = 20
VUELTAS_DE_LA_ONU = 9


@shared_task(name="campo.tasks.activar_onu_en_la_red")
def activar_onu_en_la_red(org_id: str, activacion_id: str, vuelta: int = 0) -> dict:
    """Pide la activacion de la ONU y sigue hasta saber (26/11/2026).

    Igual que el alta: una vuelta hace UNA cosa --pedir si esta `pedida`,
    mirar si esta `en_curso`-- y se encola de nuevo hasta el tope; ahi queda
    `por_revisar`, nunca «fallida» por no saber. NUNCA LEVANTA.
    """
    from campo import activacion_onu as A
    from common.tasks import clear_rls_context, set_rls_context

    try:
        set_rls_context(org_id)
        a = (A.ActivacionDeOnu.objects.select_related("orden", "pedida_por__user")
             .filter(pk=activacion_id, org_id=org_id).first())
        if a is None:
            return {"resultado": "", "por_que": "la activacion ya no esta"}
        if a.estado == A.ActivacionDeOnu.PEDIDA:
            A.ejecutar(a)
        elif a.estado == A.ActivacionDeOnu.EN_CURSO:
            A.comprobar(a)
        if a.estado == A.ActivacionDeOnu.EN_CURSO:
            if int(vuelta or 0) >= VUELTAS_DE_LA_ONU:
                A.rendirse(a)
            else:
                try:
                    activar_onu_en_la_red.apply_async(
                        args=[org_id, activacion_id, int(vuelta or 0) + 1],
                        countdown=ESPERA_DE_LA_ONU)
                except Exception as e:                           # noqa: BLE001
                    logger.warning("onu: no se pudo volver a encolar (%s)", type(e).__name__)
                    A.rendirse(a)
        return {"resultado": a.estado}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("activar la onu: fallo (%s)", type(e).__name__)
        return {"resultado": "", "por_que": type(e).__name__}
    finally:
        clear_rls_context()


@shared_task(name="campo.tasks.crear_cliente_en_el_isp")
def crear_cliente_en_el_isp(org_id: str, contrato_id: str, vuelta: int = 0) -> dict:
    """Crea en el ISP al cliente de un contrato firmado, y sigue hasta saber.

    POR QUE UNA TAREA Y NO DENTRO DE LA FIRMA. La app espera 20 segundos una
    respuesta y el proveedor crea en segundo plano; y CLAUDE.md 12 no deja una
    transaccion abierta mientras se espera una operacion externa. La firma ya
    quedo guardada (un hecho); el alta es otro.

    UNA VUELTA HACE UNA SOLA COSA: si el alta esta `pedida`, la pide; si esta
    `en_curso`, mira si el cliente ya aparecio. Si despues de eso sigue sin
    resolverse, se encola a si misma para dentro de medio minuto. Al llegar al
    tope se rinde y queda `por_revisar`, para que una persona de gestion la
    mire en el proveedor: un alta colgada en silencio es un cliente que nadie
    sabe si existe, y darla por fallida invitaria a crear otro.

    NINGUNA VUELTA «REINTENTA»: todas mandan el mismo numero de pedido, y el
    motor no saca dos veces el mismo ni reejecuta uno que fallo.

    NUNCA LEVANTA: lo que pase queda escrito en el contrato.
    """
    from campo.contrato import ContratoDeServicio
    from campo.services import alta_en_el_isp
    from common.tasks import clear_rls_context, set_rls_context

    try:
        #  EL CONTEXTO ANTES DE LEER: estas tablas tienen RLS, y sin esto el
        #  `get` no encuentra nada.
        set_rls_context(org_id)
        try:
            contrato = (ContratoDeServicio.objects
                        .select_related("firmado_por__user")
                        .get(pk=contrato_id, org_id=org_id))
        except ContratoDeServicio.DoesNotExist:
            return {"resultado": "", "por_que": "el contrato ya no esta"}

        if contrato.alta_estado == ContratoDeServicio.ALTA_PEDIDA:
            alta_en_el_isp.pedir(contrato)
        elif contrato.alta_estado == ContratoDeServicio.ALTA_EN_CURSO:
            alta_en_el_isp.comprobar(contrato)

        if (contrato.estado == ContratoDeServicio.FIRMADO
                and contrato.alta_estado in ContratoDeServicio.ALTA_EN_VUELO):
            if int(vuelta or 0) >= VUELTAS_DEL_ALTA:
                alta_en_el_isp.rendirse(contrato)
            else:
                try:
                    crear_cliente_en_el_isp.apply_async(
                        args=[org_id, contrato_id, int(vuelta or 0) + 1],
                        countdown=ESPERA_DEL_ALTA)
                except Exception as e:                           # noqa: BLE001
                    logger.warning("alta: no se pudo volver a encolar (%s)",
                                   type(e).__name__)
                    alta_en_el_isp.rendirse(contrato)
        return {"resultado": contrato.estado, "alta": contrato.alta_estado,
                "codigo": contrato.alta_codigo}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("alta del cliente: fallo (%s)", type(e).__name__)
        return {"resultado": "", "por_que": type(e).__name__}
    finally:
        clear_rls_context()


@shared_task(name="campo.tasks.activar_cliente_en_el_isp")
def activar_cliente_en_el_isp(org_id: str, contrato_id: str, vuelta: int = 0) -> dict:
    """Pasa a cliente la instalacion que aprobo una persona, y sigue hasta
    saber (26/11/2026). El mismo patron que `crear_cliente_en_el_isp`: una
    vuelta hace una cosa, se vuelve a encolar, y al tope queda «por revisar».
    NUNCA LEVANTA. Ver campo/instalacion.py."""
    from campo import instalacion
    from campo.contrato import ContratoDeServicio
    from common.tasks import clear_rls_context, set_rls_context

    try:
        set_rls_context(org_id)
        try:
            contrato = (ContratoDeServicio.objects
                        .select_related("activado_por__user", "orden")
                        .get(pk=contrato_id, org_id=org_id))
        except ContratoDeServicio.DoesNotExist:
            return {"resultado": "", "por_que": "el contrato ya no esta"}
        if contrato.activacion_estado == ContratoDeServicio.ACTIVACION_PEDIDA:
            instalacion.pedir(contrato)
        elif contrato.activacion_estado == ContratoDeServicio.ACTIVACION_EN_CURSO:
            instalacion.comprobar(contrato)
        if (contrato.estado == ContratoDeServicio.INSTALACION
                and contrato.activacion_estado in ContratoDeServicio.ACTIVACION_SIN_RESOLVER):
            if int(vuelta or 0) >= instalacion.VUELTAS_DE_LA_ACTIVACION:
                instalacion.rendirse(contrato)
            else:
                try:
                    activar_cliente_en_el_isp.apply_async(
                        args=[org_id, contrato_id, int(vuelta or 0) + 1],
                        countdown=instalacion.ESPERA_DE_LA_ACTIVACION)
                except Exception as e:                           # noqa: BLE001
                    logger.warning("activacion: no se pudo volver a encolar (%s)",
                                   type(e).__name__)
        return {"resultado": contrato.estado, "activacion": contrato.activacion_estado}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("activacion: fallo la vuelta (%s)", type(e).__name__)
        return {"resultado": "", "por_que": type(e).__name__}
    finally:
        clear_rls_context()


@shared_task(name="campo.tasks.preparar_contrato_del_proveedor")
def preparar_contrato_del_proveedor(org_id: str, contrato_id: str, vuelta: int = 0) -> dict:
    """Guarda el contrato del proveedor de un contrato confirmado sin firma
    (26/11/2026). Mismo patron que la activacion: una vuelta hace una cosa, se
    vuelve a encolar mientras siga `pedida`, y al tope queda «por revisar».
    NUNCA LEVANTA. Ver campo/contrato_del_proveedor.py."""
    from campo import contrato_del_proveedor
    from campo.contrato import ContratoDeServicio
    from common.tasks import clear_rls_context, set_rls_context

    try:
        set_rls_context(org_id)
        try:
            contrato = (ContratoDeServicio.objects
                        .select_related("firmado_por__user", "firma_proveedor_pedida_por__user",
                                        "orden")
                        .get(pk=contrato_id, org_id=org_id))
        except ContratoDeServicio.DoesNotExist:
            return {"resultado": "", "por_que": "el contrato ya no esta"}
        contrato_del_proveedor.preparar(contrato)
        if contrato.firma_proveedor_estado == ContratoDeServicio.FIRMA_PROVEEDOR_PEDIDA:
            if int(vuelta or 0) >= contrato_del_proveedor.VUELTAS:
                contrato_del_proveedor.rendirse(contrato)
            else:
                try:
                    preparar_contrato_del_proveedor.apply_async(
                        args=[org_id, contrato_id, int(vuelta or 0) + 1],
                        countdown=contrato_del_proveedor.ESPERA_ENTRE_VUELTAS)
                except Exception as e:                           # noqa: BLE001
                    logger.warning("contrato_del_proveedor: no se pudo volver a encolar (%s)",
                                   type(e).__name__)
        return {"resultado": contrato.firma_proveedor_estado}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("contrato_del_proveedor: fallo la vuelta (%s)", type(e).__name__)
        return {"resultado": "", "por_que": type(e).__name__}
    finally:
        clear_rls_context()


@shared_task(name="campo.tasks.completar_cliente_en_el_isp")
def completar_cliente_en_el_isp(org_id: str, contrato_id: str, vuelta: int = 0) -> dict:
    """Escribe el costo y el serial en el cliente recien activado (26/11/2026).
    Mismo patron que la activacion. NUNCA LEVANTA. Ver campo/instalacion.py."""
    from campo import instalacion
    from campo.contrato import ContratoDeServicio
    from common.tasks import clear_rls_context, set_rls_context

    try:
        set_rls_context(org_id)
        try:
            contrato = (ContratoDeServicio.objects
                        .select_related("activado_por__user", "orden")
                        .get(pk=contrato_id, org_id=org_id))
        except ContratoDeServicio.DoesNotExist:
            return {"resultado": "", "por_que": "el contrato ya no esta"}
        instalacion.completar(contrato)
        if contrato.completar_estado == ContratoDeServicio.COMPLETAR_PEDIDO:
            if int(vuelta or 0) >= instalacion.VUELTAS_DE_COMPLETAR:
                instalacion.rendirse_completar(contrato)
            else:
                try:
                    completar_cliente_en_el_isp.apply_async(
                        args=[org_id, contrato_id, int(vuelta or 0) + 1],
                        countdown=instalacion.ESPERA_DE_COMPLETAR)
                except Exception as e:                           # noqa: BLE001
                    logger.warning("completar: no se pudo volver a encolar (%s)", type(e).__name__)
        return {"resultado": contrato.completar_estado}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("completar: fallo la vuelta (%s)", type(e).__name__)
        return {"resultado": "", "por_que": type(e).__name__}
    finally:
        clear_rls_context()


@shared_task(name="campo.tasks.subir_fotos_del_trabajo")
def subir_fotos_del_trabajo(org_id: str, contrato_id: str, vuelta: int = 0) -> dict:
    """Sube las fotos del trabajo a los archivos del cliente en el proveedor
    (26/11/2026). Mismo patron que el contrato. NUNCA LEVANTA."""
    from campo import contrato_del_proveedor
    from campo.contrato import ContratoDeServicio
    from common.tasks import clear_rls_context, set_rls_context

    try:
        set_rls_context(org_id)
        try:
            contrato = (ContratoDeServicio.objects.select_related("firmado_por__user", "orden")
                        .get(pk=contrato_id, org_id=org_id))
        except ContratoDeServicio.DoesNotExist:
            return {"resultado": "", "por_que": "el contrato ya no esta"}
        contrato_del_proveedor.subir_fotos(contrato)
        if contrato.fotos_proveedor_estado == ContratoDeServicio.FOTOS_PEDIDAS:
            if int(vuelta or 0) >= contrato_del_proveedor.VUELTAS_DE_FOTOS:
                contrato_del_proveedor.rendirse_fotos(contrato)
            else:
                try:
                    subir_fotos_del_trabajo.apply_async(
                        args=[org_id, contrato_id, int(vuelta or 0) + 1],
                        countdown=contrato_del_proveedor.ESPERA_ENTRE_VUELTAS)
                except Exception as e:                           # noqa: BLE001
                    logger.warning("fotos: no se pudo volver a encolar (%s)", type(e).__name__)
        return {"resultado": contrato.fotos_proveedor_estado}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("fotos: fallo la vuelta (%s)", type(e).__name__)
        return {"resultado": "", "por_que": type(e).__name__}
    finally:
        clear_rls_context()


# =============================================================================
#  LAS IP LIBRES SE LEEN SOLAS  --  27/11/2026
# =============================================================================
#: La tarea corre cada hora; una lectura tarda alrededor de un minuto en
#: guardarse. Sin esta holgura, «cada 1 hora» se leeria cada DOS: a la hora
#: siguiente faltarian unos segundos para cumplirse los 60 minutos.
HOLGURA_DE_LA_LECTURA_S = 10 * 60
#: Lo que se espera a que el motor recorra el catalogo del proveedor
#: (decenas de paginas seguidas, ~1 minuto medido).
ESPERA_DE_LA_LECTURA_S = 300
ESPERA_DE_LA_PREGUNTA_S = 30


def _toca_leer(ocupacion: dict, ahora) -> bool:
    """Si a esta empresa ya le toca leer de nuevo sus IP ocupadas.

    Lo decide ella: `cada_horas` (0 = solo con el boton). Sin herramienta que
    lea, nunca. Sin lectura anterior o con una fecha ilegible, ya.
    """
    from django.utils.dateparse import parse_datetime

    try:
        cada = int(ocupacion.get("cada_horas") or 0)
    except (TypeError, ValueError):
        return False
    if cada <= 0 or not ocupacion.get("se_puede_leer"):
        return False
    ultima = parse_datetime(str(ocupacion.get("actualizado_en") or ""))
    if ultima is None:
        return True
    if timezone.is_naive(ultima):
        from datetime import timezone as zona

        ultima = ultima.replace(tzinfo=zona.utc)
    return (ahora - ultima).total_seconds() >= cada * 3600 - HOLGURA_DE_LA_LECTURA_S


@shared_task(name="campo.tasks.leer_ocupacion_de_ip")
def leer_ocupacion_de_ip() -> dict:
    """Lee las IP ocupadas en el proveedor de cada empresa que lo pidio.

    Pedido del usuario (27/11/2026): que las IP libres se actualicen solas. La
    lista solo PROPONE candidatas: la IP de un contrato se decide al confirmar,
    se pregunta en vivo al proveedor y la base no acepta dos contratos con la
    misma (`una_ip_por_contrato_vigente`). Una lista de hace una hora no
    repite IP; solo hace que el tecnico se salte alguna ya tomada.

    POR QUE HORAS Y NO MINUTOS (medido el 27/11/2026): cada lectura recorre el
    catalogo entero del proveedor y guarda una version de la config de 241 KB.
    Cada 5 minutos serian 288 versiones al dia (~1 GB al mes).

    CADA EMPRESA EN SU try/except, como `ciclo_de_la_madrugada`: una que no
    contesta no deja sin lectura a las demas. Nada de lo que vuelve del motor
    va al log: solo el tenant, cuantas leyo y el tipo de error.
    """
    import requests

    from campo.services.ips_libres import _motor
    from operaciones.areas_del_tenant import tenant_de

    base, cabeceras = _motor()
    ahora = timezone.now()
    salida = {"leidas": [], "al_dia": 0, "errores": []}
    for org in Org.objects.filter(is_active=True):
        tenant = ""
        try:
            tenant = tenant_de(org)
            if not tenant:
                continue
            r = requests.get(f"{base}/configuracion/rangos-de-ip", headers=cabeceras,
                             params={"tenant": tenant}, timeout=ESPERA_DE_LA_PREGUNTA_S)
            r.raise_for_status()
            if not _toca_leer((r.json() or {}).get("ocupacion") or {}, ahora):
                salida["al_dia"] += 1
                continue
            r = requests.post(f"{base}/configuracion/ocupacion-ip/sincronizar",
                              headers=cabeceras, json={"tenant": tenant},
                              timeout=ESPERA_DE_LA_LECTURA_S)
            r.raise_for_status()
            d = r.json() or {}
            salida["leidas"].append({"tenant": tenant, "leidos": d.get("leidos"),
                                     "completa": d.get("completa")})
            logger.info("ip libres: leidas tenant=%s leidos=%s completa=%s",
                        tenant, d.get("leidos"), d.get("completa"))
        except Exception as e:                                   # noqa: BLE001
            salida["errores"].append({"tenant": tenant, "error": type(e).__name__})
            logger.warning("ip libres: no se pudo leer tenant=%s (%s)", tenant, type(e).__name__)
    return salida
