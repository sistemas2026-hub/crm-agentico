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
    if r["motivo"] == IV.MOTIVO_APAGADO:
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

    if not ultima:
        return {"miradas": 0, "faltaban": 0}

    ya = set(AnalisisDeEvidencia.objects
             .filter(org=orden.org, evidencia_id__in=[e.id for e in ultima.values()])
             .values_list("evidencia_id", flat=True))
    faltan = [e for e in ultima.values() if e.id not in ya]

    miradas = 0
    for evidencia in faltan[:MAX_FOTOS_EN_EL_MOMENTO]:
        try:
            _mirar_y_anotar(evidencia)
            miradas += 1
        except Exception as e:                                   # noqa: BLE001
            #  UNA FOTO QUE FALLA NO FRENA A LAS DEMAS. Sin fila, el punto de
            #  la inspeccion no la ve, y eso ya quedaba igual que antes: la
            #  red de atras es la tarea por foto y el ciclo horario.
            logger.warning("mirada inmediata: fallo una foto (%s)",
                           type(e).__name__)
    return {"miradas": miradas, "faltaban": len(faltan)}


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
