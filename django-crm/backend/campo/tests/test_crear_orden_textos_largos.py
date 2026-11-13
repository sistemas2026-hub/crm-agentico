# -*- coding: utf-8 -*-
"""
================================================================================
 CREAR UNA ORDEN CON TEXTOS LARGOS NO DA 500
================================================================================

13/10/2026, el primer despacho real despues de precargar la lectura del
Supervisor: «HTTP 500: Internal Server Error» al crear la orden. `resumen` era
varchar(255) y la lectura pasaba de 300 caracteres; el serializer no validaba
largos, asi que Postgres rechazaba el guardado entero.

  A  un «que hay que hacer» de un parrafo SE GUARDA entero (es texto)
  B  uno absurdo vuelve como 400 con su campo, nunca como 500
  C  un telefono o una direccion largos de la FICHA del ISP no tumban la orden:
     se recortan al largo de la columna
  D  lo que escribe la persona fuera de largo vuelve como 400

    pytest campo/tests/test_crear_orden_textos_largos.py
================================================================================
"""

from unittest import mock

import pytest

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

CREAR = "/api/campo/trabajos/crear/"

#: La lectura de la captura, tal cual llego: 330 caracteres.
LECTURA = ("Según el Supervisor: El cliente pide un cambio de credenciales "
           "(clave) y el servicio no tiene una falla de red asociada; el ticket "
           "es una solicitud administrativa, no un incidente técnico. (confianza "
           "media). Recomienda: Decidir qué se hace con este ticket, que sigue "
           "abierto, y confirmar con el cliente antes de mandar a nadie.")


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="trabajo_general",
                                 nombre="Trabajo general", labor="trabajos")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})


def _crear(cliente, version, **extra):
    cuerpo = {"work_type_version_id": str(version.id), "zona": "CACARAMOA", **extra}
    return cliente.post(CREAR, cuerpo, format="json")


def test_a_un_parrafo_se_guarda_entero(admin_client, org_a, version):
    assert len(LECTURA) > 255
    r = _crear(admin_client, version, resumen=LECTURA)
    assert r.status_code in (200, 201), r.content
    assert OrdenTrabajo.objects.get(org=org_a).resumen == LECTURA


def test_b_un_texto_absurdo_es_400_no_500(admin_client, org_a, version):
    r = _crear(admin_client, version, resumen="x" * 2001)
    assert r.status_code == 400, r.content
    assert "resumen" in r.json() or "resumen" in str(r.content)
    assert not OrdenTrabajo.objects.filter(org=org_a).exists()


def test_c_la_ficha_larga_del_isp_se_recorta(admin_client, org_a, version):
    ficha = {"cliente": {"nombre": "Cliente", "telefono": ",".join(["3001234567"] * 9),
                         "direccion": "Calle " + "larga " * 60}}
    with mock.patch("campo.despacho_views.contexto_del_caso", return_value=ficha):
        r = _crear(admin_client, version, case_id="caso-1")
    assert r.status_code in (200, 201), r.content
    orden = OrdenTrabajo.objects.get(org=org_a)
    assert 0 < len(orden.cliente_telefono) <= 64
    assert 0 < len(orden.cliente_direccion) <= 255


@pytest.mark.parametrize("campo,largo", [
    ("cliente_telefono", 65), ("cliente_direccion", 256),
    ("cliente_detalle_acceso", 256), ("zona", 129),
])
def test_d_lo_que_escribe_la_persona_fuera_de_largo_es_400(
        admin_client, version, campo, largo):
    r = _crear(admin_client, version, **{campo: "x" * largo})
    assert r.status_code == 400, r.content
