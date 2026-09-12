# -*- coding: utf-8 -*-
"""Máquina de estados y transiciones operativas de OrdenTrabajo."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from campo.models import EventoTrabajo, OrdenTrabajo


class TransicionInvalidaError(ValidationError):
    """Excepción para saltos de estado no permitidos."""
    pass


# Matriz de transiciones operativas válidas
TRANSICIONES_PERMITIDAS = {
    OrdenTrabajo.ASIGNADA: {OrdenTrabajo.EN_CAMINO, OrdenTrabajo.EN_SITIO, OrdenTrabajo.CANCELADA},
    OrdenTrabajo.EN_CAMINO: {OrdenTrabajo.EN_SITIO, OrdenTrabajo.CANCELADA},
    OrdenTrabajo.EN_SITIO: {OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.CANCELADA},
    # El unico camino de vuelta del ciclo. Antes 'completada_campo' solo podia
    # ir a 'cerrada': una ejecucion mal hecha no tenia forma de volver al
    # tecnico, asi que la unica salida era corregirla desde la oficina, que no
    # puede fabricar una foto ni repetir una medicion.
    OrdenTrabajo.COMPLETADA_CAMPO: {OrdenTrabajo.CERRADA,
                                    OrdenTrabajo.CORRECCION_REQUERIDA},
    OrdenTrabajo.CORRECCION_REQUERIDA: {OrdenTrabajo.EN_CAMINO,
                                        OrdenTrabajo.EN_SITIO,
                                        OrdenTrabajo.CANCELADA},
    OrdenTrabajo.CERRADA: set(),
    OrdenTrabajo.CANCELADA: set(),
}

# La maquina de VALIDACION, que hasta hoy no existia: 'estado_validacion' tenia
# seis valores declarados y ningun codigo que los moviera, asi que toda orden
# completada quedaba en 'sin_evaluar' para siempre.
#
# Es una segunda maquina y no un campo mas de la primera porque responden
# preguntas distintas: la operativa dice DONDE ESTA el trabajo, esta dice SI
# ALGUIEN LO DIO POR BUENO. Un trabajo puede estar completado en campo y
# rechazado, y las dos cosas son ciertas a la vez.
#
# 'aprobable' queda declarado y sin uso a proposito: nadie lo escribia y no
# esta claro que significaba. Inventarle una semantica ahora seria peor que
# dejarlo quieto.
TRANSICIONES_VALIDACION = {
    OrdenTrabajo.SIN_EVALUAR: {OrdenTrabajo.PENDIENTE},
    OrdenTrabajo.PENDIENTE: {OrdenTrabajo.APROBADO,
                             OrdenTrabajo.REQUIERE_CORRECCION,
                             OrdenTrabajo.REQUIERE_REVISION},
    OrdenTrabajo.REQUIERE_CORRECCION: {OrdenTrabajo.PENDIENTE},
    OrdenTrabajo.REQUIERE_REVISION: {OrdenTrabajo.APROBADO,
                                     OrdenTrabajo.REQUIERE_CORRECCION},
    OrdenTrabajo.APROBADO: set(),
    OrdenTrabajo.APROBABLE: set(),
}

# Mapa de nombres de acciones intermedias permitidas en /acciones/
ACCIONES_OPERATIVAS = {
    "marcar_en_camino": OrdenTrabajo.EN_CAMINO,
    "marcar_llegada": OrdenTrabajo.EN_SITIO,
    "iniciar": OrdenTrabajo.EN_SITIO,
    "cancelar": OrdenTrabajo.CANCELADA,
}


@transaction.atomic
def ejecutar_accion_operativa(
    orden: OrdenTrabajo,
    accion: str,
    profile=None,
    metadatos: dict | None = None,
) -> OrdenTrabajo:
    """
    Ejecuta una acción intermedia (/acciones/).
    IMPORTANTE: 'completar_campo' no pasa por acá; tiene su propio validador y endpoint.
    """
    if accion not in ACCIONES_OPERATIVAS:
        raise TransicionInvalidaError(
            f"Acción '{accion}' no permitida en este endpoint. Acciones válidas: {list(ACCIONES_OPERATIVAS.keys())}"
        )

    nuevo_estado = ACCIONES_OPERATIVAS[accion]
    return _aplicar_transicion(
        orden=orden,
        nuevo_estado=nuevo_estado,
        tipo_evento=f"accion_{accion}",
        profile=profile,
        metadatos=metadatos or {},
    )


@transaction.atomic
def completar_campo(
    orden: OrdenTrabajo,
    profile=None,
    metadatos: dict | None = None,
) -> OrdenTrabajo:
    """
    Finaliza el trabajo técnico en campo (transición a COMPLETADA_CAMPO).
    Invocada EXCLUSIVAMENTE tras verificar checklist y evidencias.
    """
    # El cable que faltaba. Completar el trabajo pasa la orden a PENDIENTE de
    # validacion; sin esto la orden quedaba completada y 'sin_evaluar' para
    # siempre, o sea invisible para cualquier bandeja de supervision.
    #
    # Vale igual para la primera presentacion (sin_evaluar -> pendiente) que
    # para una re-presentacion despues de una devolucion
    # (requiere_correccion -> pendiente): las dos estan en el mapa.
    metadatos = dict(metadatos or {})
    metadatos["vuelta"] = orden.vuelta
    orden = _aplicar_transicion(
        orden=orden,
        nuevo_estado=OrdenTrabajo.COMPLETADA_CAMPO,
        tipo_evento="trabajo_completado_campo",
        profile=profile,
        metadatos=metadatos,
        establecer_fecha_completada=True,
    )
    return _aplicar_validacion(
        orden=orden,
        nuevo_estado=OrdenTrabajo.PENDIENTE,
        tipo_evento="presentado_a_validacion",
        profile=profile,
        metadatos={"vuelta": orden.vuelta},
    )


@transaction.atomic
def aprobar(
    orden: OrdenTrabajo,
    profile=None,
    observacion: str = "",
) -> OrdenTrabajo:
    """
    El supervisor da el trabajo por bueno.

    NO toca 'estado_operativo': la orden sigue 'completada_campo', que es
    donde esta. Aprobar es un juicio sobre el trabajo, no un movimiento del
    trabajo -- mezclarlos haria imposible responder "cuantas completadas estan
    sin revisar".
    """
    return _aplicar_validacion(
        orden=orden,
        nuevo_estado=OrdenTrabajo.APROBADO,
        tipo_evento="validacion_aprobada",
        profile=profile,
        metadatos={"vuelta": orden.vuelta, "observacion": observacion},
    )


@transaction.atomic
def requerir_correccion(
    orden: OrdenTrabajo,
    requisitos: list[str],
    profile=None,
    observacion: str = "",
) -> OrdenTrabajo:
    """
    El supervisor devuelve el trabajo, diciendo QUE hay que rehacer.

    Las tres cosas pasan juntas o no pasa ninguna: sube la vuelta, la orden
    vuelve a estar disponible para el tecnico y la validacion queda en
    'requiere_correccion'. Si se hicieran por separado, una caida en el medio
    dejaria una orden devuelta que el tecnico no puede tomar, o una vuelta
    contada sin devolucion.

    'requisitos' no se guarda en una columna: vive en los datos de ESTE evento.
    La bitacora ya es append-only y ordenada por fecha, asi que el evento es
    una fuente de verdad determinista -- y ademas conserva lo que se pidio en
    CADA vuelta, que una columna sobrescribiria.

    La lista se valida contra la plantilla inmutable de la orden: devolver un
    requisito que no existe dejaria un trabajo imposible de completar, porque
    el checklist esperaria para siempre una evidencia que nadie puede subir.
    """
    esquema = orden.tipo_trabajo_version.esquema
    validos = {e["id"] for e in esquema.get("evidencias", [])}
    desconocidos = [r for r in requisitos if r not in validos]
    if desconocidos:
        raise TransicionInvalidaError(
            f"Estos requisitos no existen en la plantilla de esta orden: "
            f"{desconocidos}. Validos: {sorted(validos)}"
        )
    if not requisitos:
        raise TransicionInvalidaError(
            "Hay que decir QUE se devuelve. Una devolucion sin requisitos "
            "deja al tecnico adivinando, y el checklist no exigiria nada nuevo."
        )

    vuelta_anterior = orden.vuelta
    orden.vuelta = vuelta_anterior + 1
    orden.save(update_fields=["vuelta", "updated_at"])

    orden = _aplicar_validacion(
        orden=orden,
        nuevo_estado=OrdenTrabajo.REQUIERE_CORRECCION,
        tipo_evento="correccion_requerida",
        profile=profile,
        metadatos={
            "vuelta_anterior": vuelta_anterior,
            "vuelta_nueva": orden.vuelta,
            "requisitos_a_corregir": sorted(set(requisitos)),
            "observacion": observacion,
        },
    )
    return _aplicar_transicion(
        orden=orden,
        nuevo_estado=OrdenTrabajo.CORRECCION_REQUERIDA,
        tipo_evento="reapertura_correccion",
        profile=profile,
        metadatos={"vuelta": orden.vuelta},
    )


def _aplicar_validacion(
    orden: OrdenTrabajo,
    nuevo_estado: str,
    tipo_evento: str,
    profile,
    metadatos: dict,
) -> OrdenTrabajo:
    """Mueve 'estado_validacion' contra su mapa, y lo anota en la bitacora."""
    actual = orden.estado_validacion
    if actual == nuevo_estado:
        return orden

    permitidos = TRANSICIONES_VALIDACION.get(actual, set())
    if nuevo_estado not in permitidos:
        raise TransicionInvalidaError(
            f"Validacion no permitida: de '{actual}' a '{nuevo_estado}'."
        )

    orden.estado_validacion = nuevo_estado
    orden.revision += 1
    orden.save(update_fields=["estado_validacion", "revision", "updated_at"])

    EventoTrabajo.objects.create(
        org=orden.org,
        orden=orden,
        tipo=tipo_evento,
        profile=profile,
        datos={**metadatos, "estado_validacion_anterior": actual,
               "estado_validacion_nuevo": nuevo_estado},
    )
    return orden


@transaction.atomic
def cerrar_orden(
    orden: OrdenTrabajo,
    profile=None,
    metadatos: dict | None = None,
) -> OrdenTrabajo:
    """Cierre definitivo de la orden (por supervisor o conciliación posterior)."""
    return _aplicar_transicion(
        orden=orden,
        nuevo_estado=OrdenTrabajo.CERRADA,
        tipo_evento="orden_cerrada",
        profile=profile,
        metadatos=metadatos or {},
        establecer_fecha_cierre=True,
    )


def _aplicar_transicion(
    orden: OrdenTrabajo,
    nuevo_estado: str,
    tipo_evento: str,
    profile,
    metadatos: dict,
    establecer_fecha_completada: bool = False,
    establecer_fecha_cierre: bool = False,
) -> OrdenTrabajo:
    estado_actual = orden.estado_operativo

    if estado_actual == nuevo_estado:
        # Idempotente a nivel de estado: si ya está en ese estado, no falla
        return orden

    permitidos = TRANSICIONES_PERMITIDAS.get(estado_actual, set())
    if nuevo_estado not in permitidos:
        raise TransicionInvalidaError(
            f"Transición no permitida: de '{estado_actual}' a '{nuevo_estado}'."
        )

    ahora = timezone.now()
    orden.estado_operativo = nuevo_estado
    orden.revision += 1

    if nuevo_estado in (OrdenTrabajo.EN_SITIO, OrdenTrabajo.EN_CAMINO) and not orden.iniciada_en:
        orden.iniciada_en = ahora

    if establecer_fecha_completada:
        orden.completada_campo_en = ahora

    if establecer_fecha_cierre:
        orden.cerrada_en = ahora

    orden.save(
        update_fields=[
            "estado_operativo",
            "revision",
            "iniciada_en",
            "completada_campo_en",
            "cerrada_en",
            "updated_at",
        ]
    )

    # Registrar evento en la bitácora append-only
    EventoTrabajo.objects.create(
        org=orden.org,
        orden=orden,
        tipo=tipo_evento,
        profile=profile,
        datos={
            "estado_anterior": estado_actual,
            "nuevo_estado": nuevo_estado,
            "revision": orden.revision,
            **metadatos,
        },
    )

    return orden
