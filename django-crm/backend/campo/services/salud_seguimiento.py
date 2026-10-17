# -*- coding: utf-8 -*-
"""¿Este trabajo esta reportando como deberia?

NO ES UN ESTADO. NO SE GUARDA. SE CALCULA.
------------------------------------------
No hay `estado_seguimiento = vencido` en ninguna tabla, y eso es la decision de
esta fase: seria el tercer eje que la ficha del objetivo prohibio en su primera
linea. `estado_operativo` dice DONDE esta el trabajo, `estado_validacion` dice si
alguien lo dio por bueno, y esto es SALUD DEL SEGUIMIENTO -- una lectura de hechos
que ya existen, hecha en el momento en que alguien pregunta.

Guardarlo obligaria a un proceso que lo recalcule, y un trabajo quedaria "al dia"
en la base mientras el reloj sigue corriendo. Un dato derivado que se guarda es un
dato que miente en cuanto nadie lo refresca.

QUIEN DECIDE Y QUIEN DIBUJA
---------------------------
Esto devuelve el veredicto y sus numeros; la pantalla los muestra. Reconstruir la
regla en el frontend seria repetir el defecto que la fase C encontro: la regla
viviria en dos lados y uno de los dos se quedaria viejo.

LAS CUATRO SITUACIONES, Y POR QUE SON CUATRO
--------------------------------------------
    AL_DIA         reporto dentro de la ventana
    VENCIDO        hay contacto reciente y NO reporto -- eso si es un atraso
    SIN_CONTACTO   no se sabe si el telefono puede hablar; NO se acusa a nadie
    PAUSADO_NOC    esta detenido esperando una gestion del NOC
    NO_APLICA      el trabajo ya no esta en ejecucion

"Vencido" y "sin contacto" son la distincion que justifica todo el archivo: la
primera dice "hay comunicacion y no reporto", la segunda dice "no lo se". Juntarlas
en un solo rojo acusa al tecnico que esta dentro de una camara subterranea
haciendo bien su trabajo.

LA HORA DEL TELEFONO NO DECIDE UN VENCIMIENTO
---------------------------------------------
La referencia es CUANDO LLEGO al servidor (`created_at`), no
`capturado_en_dispositivo`. Un AVANCE escrito a las 09:00 y recibido a las 09:47
--porque recien ahi hubo señal-- deja el trabajo AL DIA a las 09:47: para la
operacion, el servidor acaba de recibir una actualizacion.

La hora del dispositivo se guarda y se muestra en la historia, porque sirve para
reconstruir que paso; pero un reloj mal puesto no puede producir un atraso, y
ninguna medida sobre una persona deberia salir de un dato que su propio telefono
declara.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from campo.bloqueos import BloqueoDeTrabajo
from campo.models import EventoTrabajo, OrdenTrabajo
from campo.seguimiento import (
    MINUTOS_PARA_REPORTAR,
    ConfiguracionDeSeguimiento,
    ContactoDeDispositivo,
)
from campo.services import seguimiento_campo as seguimiento

AL_DIA = "al_dia"
VENCIDO = "vencido"
SIN_CONTACTO = "sin_contacto_reciente"
PAUSADO_NOC = "pausado_noc"
NO_APLICA = "no_aplica"

#: Como se lee cada uno. El texto vive aca y no en la pantalla porque es parte del
#: veredicto: "sin sincronizacion reciente" y "el tecnico no reporto" no son dos
#: formas de decir lo mismo, y dejar el rotulo del lado del frontend permitiria que
#: alguien "mejore" la redaccion y cambie la acusacion.
ETIQUETAS = {
    AL_DIA: "Al día",
    VENCIDO: "Seguimiento vencido",
    SIN_CONTACTO: "Sin sincronización reciente",
    PAUSADO_NOC: "Pausado, esperando al NOC",
    NO_APLICA: "No aplica",
}

#: Donde el seguimiento tiene sentido. Un trabajo completado, cerrado o cancelado
#: no tiene que reportar nada, y pedirle un avance seria ruido en la bandeja.
EN_EJECUCION = frozenset({
    OrdenTrabajo.ASIGNADA,
    OrdenTrabajo.EN_CAMINO,
    OrdenTrabajo.EN_SITIO,
    OrdenTrabajo.BLOQUEADA,
    OrdenTrabajo.CORRECCION_REQUERIDA,
})

#: Los hechos que cuentan como "este trabajo dio señales de vida".
#:
#: `bloqueo_resuelto` entra: al destrabarse empieza una ventana nueva, y no se
#: vuelve al reloj que corria antes del bloqueo -- si no, un trabajo destrabado
#: naceria vencido.
#:
#: `trabajo_iniciado` y las acciones operativas entran porque si NADIE reporto
#: nunca, el trabajo no puede quedar fuera del radar para siempre: la referencia
#: mas vieja que sirve es el momento en que se puso en marcha.
REFERENCIAS = (
    seguimiento.TIPOS[seguimiento.INICIO],
    seguimiento.TIPOS[seguimiento.AVANCE],
    seguimiento.TIPOS[seguimiento.BLOQUEO],
    seguimiento.TIPOS[seguimiento.CIERRE],
    "bloqueo_resuelto",
    "bloqueo_libero_el_trabajo",
    "trabajo_iniciado",
    "accion_marcar_llegada",
    "accion_marcar_en_camino",
    "accion_iniciar",
)


def configuracion_de(org):
    """Los umbrales de esta empresa. Si no tiene fila, los de fabrica.

    NO se crea la fila al leer: una lectura que escribe convierte cualquier
    consulta en una escritura, y con `--workers 1` eso se nota.
    """
    fila = ConfiguracionDeSeguimiento.objects.filter(org=org).first()
    if fila is not None:
        return fila.minutos_para_reportar, fila.minutos_contacto_reciente
    return MINUTOS_PARA_REPORTAR, None


def calcular(orden, *, ahora=None, config=None) -> dict:
    """La salud del seguimiento de UNA orden.

    EL ORDEN DE LAS PREGUNTAS ES LA MITAD DE LA REGLA. Una orden puede llevar 56
    minutos sin avance y el dispositivo 40 sin aparecer: decir "el tecnico no
    reporta hace 56 minutos" seria afirmar algo que no se midio. Primero se
    descarta lo que el sistema NO SABE, y solo despues se acusa un atraso.

        1. ¿el trabajo todavia tiene que reportar?        -> NO_APLICA
        2. ¿esta detenido esperando al NOC?               -> PAUSADO_NOC
        3. ¿no se sabe si el telefono puede hablar?       -> SIN_CONTACTO
        4. ¿paso la ventana desde la referencia?          -> VENCIDO
        5. en otro caso                                   -> AL_DIA
    """
    ahora = ahora or timezone.now()
    minutos_reporte, minutos_contacto = config if config else configuracion_de(orden.org)

    base = {
        "orden_id": str(orden.id),
        "estado_operativo": orden.estado_operativo,
        "minutos_para_reportar": minutos_reporte,
        # En nulo significa: este veredicto NO puede decir "sin sincronizacion".
        "minutos_contacto_reciente": minutos_contacto,
        "evalua_la_sincronizacion": minutos_contacto is not None,
    }

    # 1. ¿Tiene sentido pedirle un reporte?
    if orden.estado_operativo not in EN_EJECUCION:
        return {
            **base,
            "tipo": NO_APLICA,
            "etiqueta": ETIQUETAS[NO_APLICA],
            "motivo": (
                f"Un trabajo en '{orden.estado_operativo}' ya no está en ejecución: "
                "no tiene que reportar nada."
            ),
            "referencia": None,
            "minutos_desde_la_referencia": None,
            "vence_en": None,
            "minutos_vencido": None,
            "ultimo_contacto": None,
            "minutos_desde_el_contacto": None,
        }

    referencia, tipo_referencia = _referencia_de(orden)
    contacto = _contacto_de(orden)
    minutos_desde_contacto = (
        int((ahora - contacto).total_seconds() // 60) if contacto else None
    )

    comun = {
        **base,
        "referencia": referencia.isoformat() if referencia else None,
        "tipo_de_referencia": tipo_referencia,
        "minutos_desde_la_referencia": (
            int((ahora - referencia).total_seconds() // 60) if referencia else None
        ),
        "ultimo_contacto": contacto.isoformat() if contacto else None,
        "minutos_desde_el_contacto": minutos_desde_contacto,
    }

    # 2. ¿Detenido esperando al NOC? El reloj no corre: el NOC ya sabe.
    bloqueo = (
        BloqueoDeTrabajo.objects.filter(
            org=orden.org, orden=orden, resuelto_en__isnull=True, requiere_noc=True
        )
        .order_by("-abierto_en")
        .first()
    )
    if bloqueo is not None:
        minutos = int((ahora - bloqueo.abierto_en).total_seconds() // 60)
        return {
            **comun,
            "tipo": PAUSADO_NOC,
            "etiqueta": ETIQUETAS[PAUSADO_NOC],
            "motivo": (
                "Está detenido esperando una gestión del NOC, así que el reloj de "
                "reporte no corre: quien tiene que actuar ya está enterado."
            ),
            "vence_en": None,
            "minutos_vencido": None,
            "bloqueo": {
                "id": str(bloqueo.id),
                "abierto_en": bloqueo.abierto_en.isoformat(),
                "minutos_detenido": minutos,
                "necesita": bloqueo.necesita,
            },
        }

    vence_en = referencia + timedelta(minutes=minutos_reporte) if referencia else None

    # 3. ¿Se sabe si el telefono puede hablar?
    #
    # Con el umbral en nulo esta pregunta NO SE HACE, y no es un olvido: la
    # aplicacion no late, asi que la ausencia de contacto no prueba nada. Ver
    # campo/seguimiento.py.
    if minutos_contacto is not None:
        sin_noticias = contacto is None or minutos_desde_contacto >= minutos_contacto
        if sin_noticias:
            return {
                **comun,
                "tipo": SIN_CONTACTO,
                "etiqueta": ETIQUETAS[SIN_CONTACTO],
                "motivo": (
                    "El dispositivo no aparece desde hace un rato, así que no se "
                    "puede saber si hay un atraso de reporte o si no hay señal. "
                    "No se está diciendo que el técnico no reportó."
                ),
                "vence_en": vence_en.isoformat() if vence_en else None,
                "minutos_vencido": None,
            }

    # 4. Ahora si: hay con que comparar.
    if referencia is not None and ahora >= vence_en:
        return {
            **comun,
            "tipo": VENCIDO,
            "etiqueta": ETIQUETAS[VENCIDO],
            "motivo": (
                f"Pasaron {comun['minutos_desde_la_referencia']} minutos desde la "
                f"última actualización y la ventana es de {minutos_reporte}."
            ),
            "vence_en": vence_en.isoformat(),
            "minutos_vencido": int((ahora - vence_en).total_seconds() // 60),
        }

    # 5. Al dia. O sin referencia, que es otra cosa y se dice.
    if referencia is None:
        return {
            **comun,
            "tipo": AL_DIA,
            "etiqueta": ETIQUETAS[AL_DIA],
            "motivo": (
                "Todavía no hay ningún hecho con el que empezar a contar: la orden "
                "no registra puesta en marcha ni reportes."
            ),
            "vence_en": None,
            "minutos_vencido": None,
        }

    return {
        **comun,
        "tipo": AL_DIA,
        "etiqueta": ETIQUETAS[AL_DIA],
        "motivo": "Reportó dentro de la ventana.",
        "vence_en": vence_en.isoformat(),
        "minutos_vencido": None,
    }


def _referencia_de(orden):
    """Desde cuando se cuenta. Devuelve `(momento, tipo)`.

    Se usa `created_at` --cuando LLEGO-- y no la hora del dispositivo. Ver el
    encabezado: un reloj mal puesto no puede producir un atraso.
    """
    evento = (
        EventoTrabajo.objects.filter(org=orden.org, orden=orden, tipo__in=REFERENCIAS)
        .order_by("-created_at")
        .first()
    )
    if evento is not None:
        return evento.created_at, evento.tipo

    # Sin ningun hecho en la bitacora queda la marca de la propia orden, que es
    # cuando el sistema la vio arrancar.
    if orden.iniciada_en:
        return orden.iniciada_en, "iniciada_en"
    return None, None


def _contacto_de(orden):
    """Lo ultimo que se supo del telefono de quien la trabaja.

    Se mira al tecnico PRINCIPAL. Con una cuadrilla, que aparezca el ayudante no
    dice nada de quien tiene que reportar.
    """
    asignacion = orden.asignaciones.filter(es_principal=True).first()
    if asignacion is None:
        return None
    fila = ContactoDeDispositivo.objects.filter(profile_id=asignacion.profile_id).first()
    return fila.visto_en if fila else None


def resumen_de_org(org, *, ahora=None) -> dict:
    """La salud de todas las ordenes en ejecucion. Para la bandeja.

    Una consulta y un calculo por orden, en vez de que la pantalla pregunte de a
    una: con veinte lineas serian veinte viajes.
    """
    ahora = ahora or timezone.now()
    config = configuracion_de(org)
    ordenes = (
        OrdenTrabajo.objects.filter(org=org, estado_operativo__in=EN_EJECUCION)
        .prefetch_related("asignaciones")
    )
    filas = {}
    conteo = {AL_DIA: 0, VENCIDO: 0, SIN_CONTACTO: 0, PAUSADO_NOC: 0}
    for orden in ordenes:
        salud = calcular(orden, ahora=ahora, config=config)
        filas[str(orden.id)] = salud
        if salud["tipo"] in conteo:
            conteo[salud["tipo"]] += 1
    return {"por_orden": filas, "conteo": conteo, "evalua_la_sincronizacion": config[1] is not None}
