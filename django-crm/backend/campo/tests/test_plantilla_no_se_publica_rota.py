# -*- coding: utf-8 -*-
"""
Una plantilla no se publica si la aplicación no la sabe ejecutar.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
`validar_esquema_plantilla` estaba escrita desde el principio, con el
vocabulario completo de `schema_version=1`… y **no la llamaba nadie** (hallazgo
del inventario del 22/09/2026). Se podía publicar una plantilla con un tipo de
campo que la aplicación no entiende, y el error no aparecía en el admin:
aparecía en la calle, cuando el técnico abría la orden y el formulario no se
podía responder.

El momento de validar es al **publicar**, no antes: una plantilla en borrador
puede estar a medias a propósito. Publicar es lo que la vuelve inmutable y la
manda a los teléfonos.
"""

import pytest
from django.core.exceptions import ValidationError

from campo.models import WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def work_type(org_a):
    return WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalación")


def _esquema(campos=None, evidencias=None):
    return {
        "pasos": [{"id": "p1", "titulo": "Ejecución"}],
        "campos": campos if campos is not None else [],
        "evidencias": evidencias if evidencias is not None else [],
    }


def test_1_un_tipo_que_la_app_no_entiende_no_se_publica(work_type):
    """
    'numero' no existe en el vocabulario: la aplicación dibujaría el campo
    como texto o lo saltearía, y el técnico no podría contestarlo.
    """
    version = WorkTypeVersion(
        work_type=work_type, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=_esquema(campos=[{"id": "potencia", "tipo": "numero"}]),
    )

    with pytest.raises(ValidationError) as error:
        version.save()

    assert "numero" in str(error.value)
    assert not WorkTypeVersion.objects.filter(work_type=work_type).exists()


def test_2_una_regla_inventada_tampoco_se_publica(work_type):
    version = WorkTypeVersion(
        work_type=work_type, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=_esquema(
            campos=[{"id": "serial", "tipo": "texto", "reglas": {"obligatorio": True}}]
        ),
    )

    with pytest.raises(ValidationError) as error:
        version.save()

    # La regla se llama 'required'; 'obligatorio' no la entiende nadie.
    assert "obligatorio" in str(error.value)


def test_3_dos_campos_con_el_mismo_id_no_se_publican(work_type):
    """Con ids repetidos, una respuesta pisaría a la otra al guardar."""
    version = WorkTypeVersion(
        work_type=work_type, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=_esquema(
            campos=[
                {"id": "potencia", "tipo": "decimal"},
                {"id": "potencia", "tipo": "texto"},
            ]
        ),
    )

    with pytest.raises(ValidationError):
        version.save()


def test_4_en_borrador_se_puede_guardar_a_medias(work_type):
    """
    Un borrador es trabajo en curso. Bloquearlo obligaría a escribir la
    plantilla entera de una sola vez.
    """
    version = WorkTypeVersion.objects.create(
        work_type=work_type, version=1, schema_version=1,
        estado=WorkTypeVersion.BORRADOR,
        esquema=_esquema(campos=[{"id": "potencia", "tipo": "numero"}]),
    )

    assert version.pk is not None
    assert version.estado == WorkTypeVersion.BORRADOR


def test_5_un_borrador_roto_no_puede_pasar_a_publicada(work_type):
    """El momento de la verdad es el paso a publicada, venga de donde venga."""
    version = WorkTypeVersion.objects.create(
        work_type=work_type, version=1, schema_version=1,
        estado=WorkTypeVersion.BORRADOR,
        esquema=_esquema(campos=[{"id": "potencia", "tipo": "numero"}]),
    )

    version.estado = WorkTypeVersion.PUBLICADA
    with pytest.raises(ValidationError):
        version.save()

    version.refresh_from_db()
    assert version.estado == WorkTypeVersion.BORRADOR


def test_6_una_plantilla_correcta_se_publica_y_queda_sellada(work_type):
    """La guarda no estorba a lo que sí está bien."""
    version = WorkTypeVersion.objects.create(
        work_type=work_type, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=_esquema(
            campos=[
                {"id": "potencia_rx", "tipo": "decimal", "reglas": {"required": True}},
                {"id": "serial_ont", "tipo": "texto"},
            ],
            evidencias=[{"id": "foto_cto", "titulo": "Foto CTO", "obligatorio": True}],
        ),
    )

    assert version.publicada_en is not None
    assert version.schema_hash != ""
