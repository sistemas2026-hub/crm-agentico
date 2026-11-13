# -*- coding: utf-8 -*-
"""A quien mas llamar si el cliente no esta.

LO QUE PIDIO EL TECNICO
-----------------------
«Cuando el cliente no esta, necesito a quien mas llamar. Hoy tengo un solo
numero. En un edificio eso significa porteria, y la app no la tiene.»

POR QUE SON DOS CAMPOS Y NO UNO
-------------------------------
Un numero tiene que poder marcarse de un toque, y «Porteria 3001234567 preguntar
por Don Luis» no se marca. El nombre dice a quien pedir; el telefono es lo que el
marcador necesita limpio.

LO QUE SE AFIRMA
----------------
Que viajan hasta el telefono, que viajan **aunque esten vacios** --la app
distingue «no hay contacto» de «el servidor viejo no lo manda», y si la clave
falta las dos cosas se ven igual-- y que no se confunden con el telefono del
cliente, que es otro numero y otra persona.
"""

import pytest

from campo.models import (
    AsignacionTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.serializers import OrdenTrabajoDetailSerializer
from common.models import Profile

pytestmark = pytest.mark.django_db

ESQUEMA = {"pasos": [], "campos": [], "evidencias": []}


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.contacto@test.com", password="testpass123", name="Carlos"
    )
    return Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="contacto_test", nombre="Reparación")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA,
    )


def _orden(org, version, **extra):
    return OrdenTrabajo.objects.create(
        org=org, numero=8001, tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzón",
        cliente_telefono="+57 312 455 8901",
        cliente_direccion="Calle 50 # 10-20, Torre 4 Apto 1202",
        estado_operativo=OrdenTrabajo.ASIGNADA, revision=1,
        **extra,
    )


def test_a_el_contacto_alterno_viaja_hasta_el_telefono(org_a, version, tecnico):
    o = _orden(
        org_a, version,
        contacto_alterno_nombre="Portería — Don Luis",
        contacto_alterno_telefono="+57 300 111 2233",
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=tecnico, rol="tecnico", es_principal=True
    )

    cliente = OrdenTrabajoDetailSerializer(o).data["cliente"]

    assert cliente["contacto_alterno_nombre"] == "Portería — Don Luis"
    assert cliente["contacto_alterno_telefono"] == "+57 300 111 2233"


def test_b_viaja_TAMBIEN_vacio(org_a, version):
    """La app distingue «no hay contacto alterno» de «el servidor viejo no lo
    manda», y si la clave falta las dos cosas se ven igual."""
    o = _orden(org_a, version)

    cliente = OrdenTrabajoDetailSerializer(o).data["cliente"]

    assert "contacto_alterno_nombre" in cliente
    assert "contacto_alterno_telefono" in cliente
    assert cliente["contacto_alterno_telefono"] == ""


def test_c_NO_se_confunde_con_el_telefono_del_cliente(org_a, version):
    """Son dos numeros y dos personas. Llamar al portero creyendo que es el
    cliente es peor que no tener el numero."""
    o = _orden(
        org_a, version,
        contacto_alterno_nombre="Portería",
        contacto_alterno_telefono="+57 300 111 2233",
    )

    cliente = OrdenTrabajoDetailSerializer(o).data["cliente"]

    assert cliente["telefono"] == "+57 312 455 8901"
    assert cliente["contacto_alterno_telefono"] == "+57 300 111 2233"
    assert cliente["telefono"] != cliente["contacto_alterno_telefono"]


def test_d_un_nombre_sin_numero_se_guarda_igual(org_a, version):
    """La ORDEN puede tener solo el nombre --alguien lo cargo a medias-- y eso
    no es un error del servidor. Quien decide no dibujarlo es la app: un nombre
    sin telefono no sirve para nada parado en la puerta."""
    o = _orden(org_a, version, contacto_alterno_nombre="Portería")

    cliente = OrdenTrabajoDetailSerializer(o).data["cliente"]

    assert cliente["contacto_alterno_nombre"] == "Portería"
    assert cliente["contacto_alterno_telefono"] == ""
