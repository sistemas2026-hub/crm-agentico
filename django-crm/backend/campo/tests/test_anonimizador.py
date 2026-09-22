# -*- coding: utf-8 -*-
"""
El anonimizador conserva la forma y borra a las personas.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
Para probar la aplicación con volumen real hace falta una copia de la base, y
una copia de la base es la libreta de clientes de la empresa. Este comando la
vacía de personas sin vaciarla de estructura.

Las dos cosas que se prueban acá son las dos que, si fallan, hacen daño: que
**no quede ningún dato personal** y que **no pueda correr contra algo que no
sea local**.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalación")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )


@pytest.fixture
def orden_con_persona(org_a, user_profile, version):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=5001, tipo_trabajo_version=version,
        cliente_nombre="María Fernández Restrepo",
        cliente_telefono="+57 300 999 8877",
        cliente_direccion="Cra. 48 # 12-30, Apto 402",
        cliente_id_abonado="WH-10984214",
        gps_lat=6.2087, gps_lng=-75.5678,
        contexto={
            "cliente": {"nombre": "María Fernández Restrepo", "ip": "190.24.7.11"},
            "sn_onu": "ZTEG-48A9B0C1",
        },
        estado_operativo=OrdenTrabajo.ASIGNADA,
    )
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return o


def test_1_no_queda_ningun_dato_personal(orden_con_persona):
    call_command("anonimizar_campo", "--si-estoy-seguro", verbosity=0)
    orden_con_persona.refresh_from_db()

    assert "María" not in orden_con_persona.cliente_nombre
    assert "Fernández" not in orden_con_persona.cliente_nombre
    assert orden_con_persona.cliente_telefono != "+57 300 999 8877"
    assert "Cra. 48 # 12-30" not in orden_con_persona.cliente_direccion
    assert orden_con_persona.cliente_id_abonado != "WH-10984214"
    # El snapshot técnico también trae al cliente y su IP.
    assert "María" not in str(orden_con_persona.contexto)
    assert "190.24.7.11" not in str(orden_con_persona.contexto)


def test_2_las_coordenadas_dejan_de_senalar_la_casa(orden_con_persona):
    lat_original, lng_original = 6.2087, -75.5678

    call_command("anonimizar_campo", "--si-estoy-seguro", verbosity=0)
    orden_con_persona.refresh_from_db()

    assert orden_con_persona.gps_lat != lat_original
    assert orden_con_persona.gps_lng != lng_original
    # Pero siguen en la misma ciudad: una lista ordenada por distancia tiene
    # que seguir teniendo sentido al probar.
    assert abs(orden_con_persona.gps_lat - lat_original) < 0.05
    assert abs(orden_con_persona.gps_lng - lng_original) < 0.05


def test_3_la_forma_de_la_jornada_no_cambia(orden_con_persona, version):
    """Cantidad, tipo, estado y fechas son lo que se quiere mirar al probar."""
    antes = {
        "numero": orden_con_persona.numero,
        "estado": orden_con_persona.estado_operativo,
        "tipo": orden_con_persona.tipo_trabajo_version_id,
        "creada": orden_con_persona.created_at,
        "sn_onu": orden_con_persona.contexto["sn_onu"],
    }

    call_command("anonimizar_campo", "--si-estoy-seguro", verbosity=0)
    orden_con_persona.refresh_from_db()

    assert orden_con_persona.numero == antes["numero"]
    assert orden_con_persona.estado_operativo == antes["estado"]
    assert orden_con_persona.tipo_trabajo_version_id == antes["tipo"]
    assert orden_con_persona.created_at == antes["creada"]
    # El serial del equipo no es un dato personal: identifica una ONU.
    assert orden_con_persona.contexto["sn_onu"] == antes["sn_onu"]
    assert OrdenTrabajo.objects.count() == 1


def test_4_el_mismo_cliente_sigue_pareciendo_el_mismo(org_a, version, user_profile):
    """
    El reemplazo es estable: dos órdenes del mismo domicilio siguen agrupadas.
    Si cada una recibiera un nombre distinto, la lista dejaría de parecerse a
    una jornada real.
    """
    for numero in (5002, 5003):
        o = OrdenTrabajo.objects.create(
            org=org_a, numero=numero, tipo_trabajo_version=version,
            cliente_nombre="Cliente Repetido",
            cliente_direccion="Calle 1",
            estado_operativo=OrdenTrabajo.ASIGNADA,
        )
        AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                         rol="tecnico", es_principal=True)

    call_command("anonimizar_campo", "--si-estoy-seguro", verbosity=0)

    # Cada orden recibe su propio seudónimo estable; correr dos veces no
    # cambia el resultado.
    nombres_primera = list(
        OrdenTrabajo.objects.order_by("numero").values_list("cliente_nombre", flat=True)
    )
    call_command("anonimizar_campo", "--si-estoy-seguro", verbosity=0)
    nombres_segunda = list(
        OrdenTrabajo.objects.order_by("numero").values_list("cliente_nombre", flat=True)
    )

    assert nombres_primera == nombres_segunda


def test_5_sin_la_confirmacion_no_hace_nada(orden_con_persona):
    with pytest.raises(CommandError) as error:
        call_command("anonimizar_campo", verbosity=0)

    assert "si-estoy-seguro" in str(error.value)
    orden_con_persona.refresh_from_db()
    assert orden_con_persona.cliente_nombre == "María Fernández Restrepo"


def test_6_se_niega_a_correr_contra_una_base_que_no_sea_local(
    orden_con_persona, settings
):
    """
    La guarda que importa. El 22/09/2026 un arranque que se creía local escribió
    en producción porque `manage.py` pisaba la configuración; un comando que
    reescribe nombres de clientes no puede depender de que nadie se equivoque.
    """
    settings.DATABASES["default"] = {
        **settings.DATABASES["default"],
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "crm.empresa-de-verdad.co",
    }

    with pytest.raises(CommandError) as error:
        call_command("anonimizar_campo", "--si-estoy-seguro", verbosity=0)

    assert "no es local" in str(error.value)
    orden_con_persona.refresh_from_db()
    assert orden_con_persona.cliente_nombre == "María Fernández Restrepo"
