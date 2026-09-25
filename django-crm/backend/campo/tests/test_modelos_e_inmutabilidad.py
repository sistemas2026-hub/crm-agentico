# -*- coding: utf-8 -*-
"""Pruebas de modelos, inmutabilidad de versiones, unicidad de origen y cuadrilla única."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from campo.models import AsignacionTrabajo, EventoTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion


@pytest.fixture
def work_type_ftth(org_a):
    return WorkType.objects.create(
        org=org_a,
        codigo="ftth_instalacion",
        nombre="Instalación Fibra Óptica",
    )


@pytest.fixture
def esquema_basico():
    return {
        "pasos": [{"id": "datos", "titulo": "Datos Técnicos"}],
        "campos": [
            {"id": "serial_ont", "tipo": "texto", "reglas": {"required": True, "min": 5}},
            {"id": "potencia_rx", "tipo": "decimal", "reglas": {"required": True, "min": -28.0, "max": -8.0}},
        ],
        "evidencias": [
            {"id": "foto_ont", "titulo": "ONT Instalada", "tipo": "foto", "obligatorio": True},
            {"id": "foto_fachada", "titulo": "Fachada", "tipo": "foto", "obligatorio": False},
        ],
    }


def test_work_type_version_ciclo_vida_e_inmutabilidad(work_type_ftth, esquema_basico):
    """Prueba que una versión en BORRADOR se edite, al PUBLICAR congele hash, y una vez PUBLICADA sea inmutable."""
    version = WorkTypeVersion.objects.create(
        work_type=work_type_ftth,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.BORRADOR,
        esquema=esquema_basico,
    )

    # 1. En borrador se puede modificar
    version.esquema["campos"].append({"id": "nap", "tipo": "texto"})
    version.save()
    assert len(version.esquema["campos"]) == 3

    # 2. Publicar la versión congela schema_hash y fecha
    version.estado = WorkTypeVersion.PUBLICADA
    version.save()
    assert version.publicada_en is not None
    assert len(version.schema_hash) == 64

    # 3. Intentar mutar el esquema de una versión PUBLICADA debe lanzar ValidationError
    version.esquema = {"mutado": True}
    with pytest.raises(ValidationError) as exc:
        version.save()
    assert "no puede modificarse" in str(exc.value).lower() or "inmutable" in str(exc.value).lower()

    # 4. Intentar devolver a BORRADOR debe fallar
    version.refresh_from_db()
    version.estado = WorkTypeVersion.BORRADOR
    with pytest.raises(ValidationError):
        version.save()

    # 5. La ÚNICA transición permitida para una publicada es a RETIRADA
    version.refresh_from_db()
    version.estado = WorkTypeVersion.RETIRADA
    version.save()
    assert version.estado == WorkTypeVersion.RETIRADA

    # 6. Intentar bypass con .update() masivo de ORM sobre versión congelada debe fallar
    with pytest.raises(ValidationError) as exc_update:
        WorkTypeVersion.objects.filter(pk=version.pk).update(esquema={"bypass": True})
    assert "operación prohibida" in str(exc_update.value).lower()


def test_origen_externo_unico(org_a, work_type_ftth, esquema_basico):
    """Evita crear dos órdenes de trabajo para el mismo ticket de WispHub."""
    version = WorkTypeVersion.objects.create(
        work_type=work_type_ftth,
        version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=esquema_basico,
    )

    OrdenTrabajo.objects.create(
        org=org_a,
        numero=1001,
        tipo_trabajo_version=version,
        origen_sistema="wisphub",
        origen_tipo="ticket",
        origen_ref="91288",
        cliente_nombre="Carlos Prueba",
        cliente_direccion="Calle 10 # 5-20",
    )

    # El mismo ticket para la misma org debe disparar IntegrityError
    with pytest.raises(IntegrityError):
        OrdenTrabajo.objects.create(
            org=org_a,
            numero=1002,
            tipo_trabajo_version=version,
            origen_sistema="wisphub",
            origen_tipo="ticket",
            origen_ref="91288",
            cliente_nombre="Carlos Prueba Duplicado",
            cliente_direccion="Calle 10 # 5-20",
        )


def test_asignacion_cuadrilla_y_tecnico_principal_unico(org_a, admin_profile, user_profile, work_type_ftth, esquema_basico):
    """Garantiza que AsignacionTrabajo sea la fuente de verdad y solo exista un es_principal=True por orden."""
    version = WorkTypeVersion.objects.create(
        work_type=work_type_ftth,
        version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=esquema_basico,
    )

    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=1003,
        tipo_trabajo_version=version,
        cliente_nombre="Juan Pérez",
        cliente_direccion="Av 123",
    )

    # 1. Asignar técnico principal
    AsignacionTrabajo.objects.create(
        orden=orden,
        profile=user_profile,
        rol="tecnico_lider",
        es_principal=True,
    )
    assert orden.tecnico_principal == user_profile

    # 2. Asignar ayudante (es_principal=False)
    AsignacionTrabajo.objects.create(
        orden=orden,
        profile=admin_profile,
        rol="ayudante",
        es_principal=False,
    )
    assert orden.asignaciones.count() == 2
    assert orden.tecnico_principal == user_profile

    # 3. Intentar asignar un SEGUNDO técnico con es_principal=True debe violar la restricción única
    with pytest.raises(IntegrityError):
        AsignacionTrabajo.objects.create(
            orden=orden,
            profile=admin_profile,
            rol="segundo_lider",
            es_principal=True,
        )


def test_evento_trabajo_append_only(org_a, user_profile, work_type_ftth, esquema_basico):
    """Verifica que los eventos registren auditoría histórica."""
    version = WorkTypeVersion.objects.create(
        work_type=work_type_ftth,
        version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=esquema_basico,
    )

    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=1004,
        tipo_trabajo_version=version,
        cliente_nombre="Ana Gómez",
        cliente_direccion="Carrera 45",
    )

    EventoTrabajo.objects.create(
        org=org_a,
        orden=orden,
        tipo="llegada_registrada",
        profile=user_profile,
        datos={"gps_lat": 4.6097, "gps_lng": -74.0817},
    )

    assert orden.eventos.count() == 1
    assert orden.eventos.first().tipo == "llegada_registrada"
