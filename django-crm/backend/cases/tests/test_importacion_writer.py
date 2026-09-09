# -*- coding: utf-8 -*-
"""
El writer de casos importados: la ultima frontera antes de la base.

    uv run pytest cases/tests/test_importacion_writer.py --no-cov -v

QUE DEFIENDE
------------
Que el motor no sea creido. Ya eligio responsable, ya clasifico autoria, ya
decidio el estado inicial -- y aun asi todo eso se revalida aca, porque este es
el ultimo punto antes del INSERT y "viene de un servicio nuestro" es
exactamente el razonamiento con el que se cruzan los tenants.

Y que la reconciliacion no pueda mover 'Case.status' ni por error ni por
descuido: no lo ignora, lo RECHAZA. Un campo ignorado en silencio deja al
llamante creyendo que lo escribio.
"""

import uuid

import pytest
from rest_framework.test import APIClient

from cases.models import (EXTERNAL_AUTHOR_DEXTER, EXTERNAL_AUTHOR_HUMAN,
                          EXTERNAL_AUTHOR_UNKNOWN, Case)
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db

IMPORTAR = "/api/importacion/casos/"


def _reconciliar(caso):
    return f"/api/importacion/casos/{caso.id}/reconciliar/"


def _cliente(user, org, profile):
    c = APIClient()
    token = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return c


@pytest.fixture
def cliente_a(admin_client):
    return admin_client


def cuerpo(**extra):
    base = {
        "provider": "wisphub",
        "external_ticket_id": "92100",
        "external_service_id": "5832",
        "external_status": "Nuevo",
        "external_created_by": "SHEILA - licencia@rapilink-sas",
        "external_created_by_type": EXTERNAL_AUTHOR_HUMAN,
        "name": "No Tiene Internet",
        "description": "Reportado por telefono.",
        "priority": "Normal",
        "status": "New",
    }
    base.update(extra)
    return base


# --- el camino feliz, y que la identidad quede en el INSERT ---------------

def test_crea_el_caso_con_su_identidad_externa(cliente_a, org_a):
    r = cliente_a.post(IMPORTAR, cuerpo(), format="json")
    assert r.status_code == 201, r.content
    assert r.json()["created"] is True

    caso = Case.objects.get(id=r.json()["case_id"])
    assert (caso.provider, caso.external_ticket_id) == ("wisphub", "92100")
    assert caso.external_service_id == "5832"
    assert caso.external_status == "Nuevo"
    assert caso.org_id == org_a.id
    assert caso.status == "New"


def test_el_reintento_no_duplica_y_no_pisa_nada(cliente_a, admin_profile):
    primero = cliente_a.post(IMPORTAR, cuerpo(), format="json").json()
    caso = Case.objects.get(id=primero["case_id"])
    # Alguien trabajo el caso entre las dos pasadas.
    caso.status = "Pending"
    caso.name = "Editado a mano"
    caso.save(update_fields=["status", "name"])

    segundo = cliente_a.post(IMPORTAR, cuerpo(status="New", name="No Tiene Internet"),
                             format="json")
    assert segundo.status_code == 200
    assert segundo.json()["created"] is False
    assert segundo.json()["case_id"] == primero["case_id"]

    caso.refresh_from_db()
    assert caso.status == "Pending", "el reintento piso el estado trabajado"
    assert caso.name == "Editado a mano", "el reintento piso el texto editado"
    assert Case.objects.filter(external_ticket_id="92100").count() == 1


# --- lo que NO se acepta ---------------------------------------------------

@pytest.mark.parametrize("extra", [
    {"stage": "algo"}, {"closed_on": "2026-01-01"}, {"parent": str(uuid.uuid4())},
    {"custom_fields": {"x": 1}}, {"org": str(uuid.uuid4())},
    {"created_by": str(uuid.uuid4())}, {"is_sample": True},
])
def test_campos_no_previstos_se_rechazan(cliente_a, extra):
    r = cliente_a.post(IMPORTAR, cuerpo(**extra), format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "CAMPO_NO_PERMITIDO"
    assert not Case.objects.filter(external_ticket_id="92100").exists()


@pytest.mark.parametrize("cambio,codigo", [
    ({"provider": ""}, "REFERENCIA_EXTERNA_INCOMPLETA"),
    # Las DOS vacias tambien. El modelo lo permite -- asi son los casos
    # nativos-- pero esta puerta no crea casos nativos: si lo aceptara seria
    # una segunda via para crear casos normales sin pasar por el serializer
    # publico ni por sus validaciones.
    ({"provider": "", "external_ticket_id": ""}, "REFERENCIA_EXTERNA_INCOMPLETA"),
    ({"external_ticket_id": ""}, "REFERENCIA_EXTERNA_INCOMPLETA"),
    ({"priority": "Altisima"}, "PRIORIDAD_INVALIDA"),
    ({"status": "Closed"}, "ESTADO_INICIAL_INVALIDO"),
    ({"status": "Rejected"}, "ESTADO_INICIAL_INVALIDO"),
    ({"external_created_by_type": "humano"}, "TIPO_DE_AUTOR_INVALIDO"),
    ({"name": "   "}, "NOMBRE_REQUERIDO"),
])
def test_validaciones_del_servidor(cliente_a, cambio, codigo):
    r = cliente_a.post(IMPORTAR, cuerpo(**cambio), format="json")
    assert r.status_code == 400, r.content
    assert r.json()["error"] == codigo
    assert not Case.objects.filter(external_ticket_id="92100").exists()


def test_no_se_puede_importar_un_caso_ya_cerrado(cliente_a):
    """La decision de producto es no traer historia resuelta, y el writer la
    sostiene: 'Closed' no es un estado con el que un caso pueda nacer."""
    r = cliente_a.post(IMPORTAR, cuerpo(status="Closed"), format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "ESTADO_INICIAL_INVALIDO"


# --- aislamiento entre organizaciones --------------------------------------

def test_un_responsable_de_otra_organizacion_se_rechaza(cliente_a, profile_b):
    r = cliente_a.post(IMPORTAR, cuerpo(assigned_to=str(profile_b.id)),
                       format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "RESPONSABLE_INVALIDO"
    assert not Case.objects.filter(external_ticket_id="92100").exists()


def test_el_mismo_ticket_en_dos_orgs_son_dos_casos(cliente_a, org_b_client, org_b):
    cliente_a.post(IMPORTAR, cuerpo(), format="json")
    r = org_b_client.post(IMPORTAR, cuerpo(), format="json")
    assert r.status_code == 201 and r.json()["created"] is True
    assert Case.objects.filter(external_ticket_id="92100").count() == 2


def test_la_org_del_cuerpo_no_se_mira(cliente_a, org_a, org_b):
    """Se rechaza por campo no permitido, que es mas fuerte que ignorarlo: la
    organizacion la decide la credencial, no el payload."""
    r = cliente_a.post(IMPORTAR, cuerpo(org=str(org_b.id)), format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "CAMPO_NO_PERMITIDO"


def test_sin_credencial_no_se_entra(org_a):
    r = APIClient().post(IMPORTAR, cuerpo(), format="json")
    assert r.status_code in (401, 403)
    assert not Case.objects.filter(external_ticket_id="92100").exists()


# --- reconciliacion --------------------------------------------------------

@pytest.fixture
def importado(cliente_a):
    r = cliente_a.post(IMPORTAR, cuerpo(), format="json")
    return Case.objects.get(id=r.json()["case_id"])


def test_reconciliar_actualiza_lo_externo_y_solo_eso(cliente_a, importado):
    r = cliente_a.post(_reconciliar(importado), {
        "external_status": "Cerrado",
        "external_status_at": "2026-09-01T10:00:00-05:00",
        "external_fetched_at": "2026-09-09T12:00:00Z",
        "external_fetch_error": "",
    }, format="json")
    assert r.status_code == 200, r.content

    importado.refresh_from_db()
    assert importado.external_status == "Cerrado"
    assert importado.status == "New", "la reconciliacion movio el estado de Dexter"


@pytest.mark.parametrize("prohibido", [
    {"status": "Closed"}, {"assigned_to": str(uuid.uuid4())},
    {"stage": "x"}, {"priority": "High"}, {"name": "otro"},
])
def test_la_reconciliacion_rechaza_lo_que_no_le_toca(cliente_a, importado, prohibido):
    r = cliente_a.post(_reconciliar(importado),
                       {"external_status": "Cerrado", **prohibido}, format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "CAMPO_NO_PERMITIDO"
    importado.refresh_from_db()
    assert importado.status == "New"
    assert importado.external_status == "Nuevo", "escribio pese a rechazar"


def test_dexter_no_se_degrada_ni_aunque_lo_pidan(cliente_a, importado):
    importado.external_created_by_type = EXTERNAL_AUTHOR_DEXTER
    importado.save(update_fields=["external_created_by_type"])

    cliente_a.post(_reconciliar(importado), {
        "external_created_by_type": EXTERNAL_AUTHOR_UNKNOWN,
        "external_created_by": "Rapilink SAS - admin@rapilink-sas",
    }, format="json")

    importado.refresh_from_db()
    assert importado.external_created_by_type == EXTERNAL_AUTHOR_DEXTER, (
        "el proveedor contesta con la cuenta compartida tambien para lo nuestro: "
        "degradarlo perderia la unica evidencia especifica que tenemos")


def test_una_lectura_pobre_no_borra_el_estado_externo_bueno(cliente_a, importado):
    cliente_a.post(_reconciliar(importado), {"external_status": ""}, format="json")
    importado.refresh_from_db()
    assert importado.external_status == "Nuevo"


def test_un_error_de_lectura_se_anota_sin_tocar_nada_mas(cliente_a, importado):
    r = cliente_a.post(_reconciliar(importado),
                       {"external_fetch_error": "502 del proveedor"}, format="json")
    assert r.status_code == 200
    importado.refresh_from_db()
    assert importado.external_fetch_error == "502 del proveedor"
    assert importado.status == "New"
    assert importado.external_status == "Nuevo"


def test_no_se_reconcilia_un_caso_de_otra_org(cliente_a, org_b_client, importado):
    r = org_b_client.post(_reconciliar(importado), {"external_status": "Cerrado"},
                  format="json")
    assert r.status_code == 404, "404 y no 403: quien no puede verlo no se entera"
    importado.refresh_from_db()
    assert importado.external_status == "Nuevo"
