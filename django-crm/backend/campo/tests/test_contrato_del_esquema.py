# -*- coding: utf-8 -*-
"""`version` y `schema_version` son dos numeros distintos.

LO QUE PASO (05/10/2026)
------------------------
Alguien publico la **revision 6** de `ftth_correctivo` y le puso
`schema_version = 6`. Las consecuencias no se parecen a un numero mal escrito:

1. La aplicacion de campo **bloquea** toda orden con un contrato que no sabe
   ejecutar --fail-closed, y esta bien que lo haga--. El tecnico abre la OT
   #1843 y lee *«Esta orden necesita una version mas nueva de la aplicacion»*.
   No hay version mas nueva: el contrato 6 no existe en ningun lado, y ninguna
   actualizacion lo va a arreglar.

2. Peor, y mas silencioso: `clean()` solo validaba la plantilla cuando
   `schema_version == 1`. Esa puerta --pensada para un contrato futuro-- era
   tambien la unica forma de SALTEARSE la validacion. Un numero cualquiera
   apagaba las dos cosas de una vez.

Medido sobre el caso real: esa plantilla habria pasado la validacion igual, asi
que no entro nada malo. **Esta vez.** El riesgo no era teorico: dependia de que
quien se equivoco de campo tuviera ademas una plantilla correcta.

QUE SE AFIRMA
-------------
Que publicar un contrato que no existe **se rechaza**, por cualquier camino; que
subir la REVISION de una plantilla sigue siendo gratis; y que la validacion de
la plantilla ya no se puede apagar escribiendo un numero.
"""

import pytest
from django.core.exceptions import ValidationError

from campo.models import WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

ESQUEMA = {
    "pasos": [{"id": "p1", "titulo": "Llegada"}],
    "campos": [],
    "evidencias": [
        {"id": "foto_cto", "titulo": "Fotografía de la caja CTO", "tipo": "foto"}
    ],
}


@pytest.fixture
def tipo(org_a):
    return WorkType.objects.create(
        org=org_a, codigo="contrato_test", nombre="Reparación"
    )


def test_a_el_contrato_1_se_publica_sin_problema(tipo):
    v = WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA,
    )

    assert v.pk is not None


def test_b_SUBIR_LA_REVISION_sigue_siendo_gratis(tipo):
    """Lo que hay que poder hacer todos los dias: publicar un cambio de
    formulario. La revision sube; el contrato NO."""
    WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA,
    )
    v6 = WorkTypeVersion.objects.create(
        work_type=tipo, version=6, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA,
    )

    assert v6.version == 6
    assert v6.schema_version == 1


def test_c_un_contrato_QUE_NO_EXISTE_se_rechaza(tipo):
    """LA GUARDA.

    Un `objects.create()` tambien pasa por `clean()` --`save()` lo llama-- y es
    justo por donde entro la fila que bloqueo la OT #1843.
    """
    with pytest.raises(ValidationError):
        WorkTypeVersion.objects.create(
            work_type=tipo, version=6, schema_version=6,
            estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA,
        )


def test_d_tambien_se_rechaza_en_BORRADOR(tipo):
    """Un borrador con el contrato mal se publica igual de mal mas tarde, y
    entonces el error aparece lejos de donde se cometio."""
    with pytest.raises(ValidationError):
        WorkTypeVersion.objects.create(
            work_type=tipo, version=2, schema_version=3,
            estado=WorkTypeVersion.BORRADOR, esquema=ESQUEMA,
        )


def test_e_el_mensaje_NOMBRA_LA_CONFUSION(tipo):
    """Quien se equivoca esta publicando la revision N de una plantilla. Un
    mensaje que solo diga «valor invalido» lo deja probando numeros."""
    with pytest.raises(ValidationError) as e:
        WorkTypeVersion.objects.create(
            work_type=tipo, version=6, schema_version=6,
            estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA,
        )

    texto = str(e.value)
    assert "version" in texto
    assert "schema_version" in texto
    assert "BLOQUEADA" in texto


def test_f_LA_VALIDACION_DE_LA_PLANTILLA_YA_NO_SE_PUEDE_APAGAR(tipo):
    """LA MITAD QUE NO SE VEIA.

    Antes, `clean()` validaba la plantilla solo si `schema_version == 1`. Una
    plantilla rota con `schema_version = 2` se publicaba sin que nadie la
    mirara. Ahora el contrato raro se rechaza antes, asi que la validacion
    corre siempre.
    """
    rota = {"pasos": [{"id": "p1", "titulo": "Llegada"}], "campos": [
        {"id": "x", "titulo": "X", "tipo": "un_tipo_que_no_existe"}
    ], "evidencias": []}

    # Por el camino de antes: contrato raro. Ahora se rechaza por el contrato.
    with pytest.raises(ValidationError):
        WorkTypeVersion.objects.create(
            work_type=tipo, version=2, schema_version=2,
            estado=WorkTypeVersion.PUBLICADA, esquema=rota,
        )

    # Y por el camino normal: contrato 1 y plantilla rota. Se rechaza por la
    # plantilla. Las dos puertas cerradas, no una.
    with pytest.raises(ValidationError):
        WorkTypeVersion.objects.create(
            work_type=tipo, version=3, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA, esquema=rota,
        )


def test_g_los_contratos_conocidos_son_los_que_la_app_sabe_leer():
    """Hoy es uno solo, y agregarlo aca antes de que la app lo entienda seria
    publicar para telefonos que no existen.

    Si alguna vez cambia, que cambie a proposito y rompiendo esta linea.
    """
    assert WorkTypeVersion.CONTRATOS_CONOCIDOS == frozenset({1})
