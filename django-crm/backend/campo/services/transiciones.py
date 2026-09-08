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
    OrdenTrabajo.COMPLETADA_CAMPO: {OrdenTrabajo.CERRADA},
    OrdenTrabajo.CERRADA: set(),
    OrdenTrabajo.CANCELADA: set(),
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
    return _aplicar_transicion(
        orden=orden,
        nuevo_estado=OrdenTrabajo.COMPLETADA_CAMPO,
        tipo_evento="trabajo_completado_campo",
        profile=profile,
        metadatos=metadatos or {},
        establecer_fecha_completada=True,
    )


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
