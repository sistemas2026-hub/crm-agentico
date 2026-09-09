# -*- coding: utf-8 -*-
"""
Las dos lecturas internas del importador: que sabe ya Dexter de estos tickets.

    uv run pytest cases/tests/test_importacion_lecturas.py --no-cov -v

POR QUE EXISTEN ESTOS ENDPOINTS
-------------------------------
El motor no puede leer las tablas de Django: corre con su propio usuario de
base desde el incidente del 18/08/2026, en que compartia credencial con el
CRM. El primer dry-run en produccion se cayo asi:

    psycopg.errors.InsufficientPrivilege:
    permission denied for table solicitudes_solicitudservicio

La salida no fue un GRANT -- habria deshecho esa separacion y atado 'nucleo/'
al esquema interno de otra app. Django contesta lo que sabe, y por dentro
cambia lo que quiera.

Estas pruebas fijan que la frontera devuelva PERTENENCIA y nada mas, y que no
se filtre entre organizaciones.
"""

import pytest
from rest_framework.test import APIClient

from cases.models import EXTERNAL_AUTHOR_HUMAN, Case

pytestmark = pytest.mark.django_db

CONOCIDOS = "/api/importacion/tickets-conocidos/"
EXTERNOS = "/api/importacion/casos-externos/"


def _caso(org, autor, ticket, provider="wisphub", **extra):
    return Case.objects.create(
        name=f"Ticket {ticket}", status=extra.pop("status", "New"),
        priority="Normal", org=org, created_by=autor, provider=provider,
        external_ticket_id=ticket, external_service_id="5832",
        external_status="Nuevo", external_created_by_type=EXTERNAL_AUTHOR_HUMAN,
        **extra)


# --- tickets-conocidos ----------------------------------------------------

def test_un_ticket_con_caso_aparece_en_con_caso(admin_client, org_a, admin_user):
    _caso(org_a, admin_user, "91865")
    r = admin_client.get(CONOCIDOS, {"provider": "wisphub", "ids": "91865,99999"})
    assert r.status_code == 200, r.content
    assert r.json()["con_caso"] == ["91865"]
    assert "99999" not in r.json()["con_caso"]


def test_un_ticket_de_solicitudes_aparece_como_creado_por_dexter(
        admin_client, org_a, admin_user):
    from solicitudes.models import SolicitudServicio

    from django.utils import timezone
    from datetime import timedelta

    SolicitudServicio.objects.create(
        org=org_a, created_by=admin_user, telefono="3000000000",
        ticket_wisphub="91750",
        expira_en=timezone.now() + timedelta(days=30))
    r = admin_client.get(CONOCIDOS, {"provider": "wisphub", "ids": "91750,91865"})
    assert r.status_code == 200, r.content
    assert r.json()["creados_por_dexter"] == ["91750"]


def test_no_devuelve_nada_de_la_solicitud_ni_del_caso(admin_client, org_a, admin_user):
    """Solo pertenencia. Un endpoint que devolviera las filas seria una via
    para leer 'solicitudes' entera desde afuera, que es lo que se evita."""
    _caso(org_a, admin_user, "91865")
    cuerpo = admin_client.get(
        CONOCIDOS, {"provider": "wisphub", "ids": "91865"}).json()
    assert set(cuerpo) == {"con_caso", "creados_por_dexter"}
    assert all(isinstance(v, list) and all(isinstance(x, str) for x in v)
               for v in cuerpo.values())


def test_otra_organizacion_no_se_filtra(admin_client, org_b, user_b, org_a):
    """Sin el filtro por org, un ticket con el mismo numero en otro ISP se
    reportaria como conocido y el importador lo saltearia: un ticket que no se
    importa nunca, y en silencio."""
    _caso(org_b, user_b, "91865")
    r = admin_client.get(CONOCIDOS, {"provider": "wisphub", "ids": "91865"})
    assert r.json()["con_caso"] == []


def test_otro_proveedor_es_independiente(admin_client, org_a, admin_user):
    _caso(org_a, admin_user, "91865", provider="otro_isp")
    assert admin_client.get(
        CONOCIDOS, {"provider": "wisphub", "ids": "91865"}).json()["con_caso"] == []
    assert admin_client.get(
        CONOCIDOS, {"provider": "otro_isp", "ids": "91865"}).json()["con_caso"] == ["91865"]


@pytest.mark.parametrize("params,codigo", [
    ({"ids": "1"}, "PROVEEDOR_REQUERIDO"),
    ({"provider": "wisphub"}, "IDS_REQUERIDOS"),
    ({"provider": "wisphub", "ids": ",".join(str(i) for i in range(300))},
     "DEMASIADOS_IDS"),
    ({"provider": "wisphub", "ids": ",".join("x" * 64 for _ in range(150))},
     "IDS_DEMASIADO_LARGOS"),
])
def test_limites_de_la_consulta(admin_client, params, codigo):
    """El limite de LARGO existe aparte del de cantidad: la columna admite 64
    caracteres, asi que '200 ids' pueden ser 200 bytes o 13.000, y de eso
    depende que la URL pase por todos los proxies de la cadena."""
    r = admin_client.get(CONOCIDOS, params)
    assert r.status_code == 400
    assert r.json()["error"] == codigo


def test_sin_credencial_no_se_entra():
    r = APIClient().get(CONOCIDOS, {"provider": "wisphub", "ids": "1"})
    assert r.status_code in (401, 403)


def test_la_lectura_no_escribe(admin_client, org_a, admin_user):
    _caso(org_a, admin_user, "91865")
    antes = Case.objects.count()
    admin_client.get(CONOCIDOS, {"provider": "wisphub", "ids": "91865,1,2,3"})
    assert Case.objects.count() == antes


# --- casos-externos -------------------------------------------------------

def test_lista_solo_los_de_su_org_y_proveedor(admin_client, org_a, org_b,
                                              admin_user, user_b):
    _caso(org_a, admin_user, "91865")
    _caso(org_a, admin_user, "91866", provider="otro_isp")
    _caso(org_b, user_b, "91867")
    cuerpo = admin_client.get(EXTERNOS, {"provider": "wisphub"}).json()
    assert [c["external_ticket_id"] for c in cuerpo["casos"]] == ["91865"]
    assert cuerpo["total"] == 1


def test_devuelve_exactamente_los_campos_de_la_politica(admin_client, org_a,
                                                        admin_user):
    _caso(org_a, admin_user, "91865")
    caso = admin_client.get(EXTERNOS, {"provider": "wisphub"}).json()["casos"][0]
    assert set(caso) == {"id", "external_ticket_id", "status", "closed_on",
                         "external_status", "external_created_by",
                         "external_created_by_type", "external_fetch_error"}
    assert "name" not in caso and "description" not in caso


def test_pagina_sin_repetir_ni_saltear(admin_client, org_a, admin_user):
    for i in range(5):
        _caso(org_a, admin_user, f"9200{i}")
    vistos, desde = [], 0
    while desde is not None:
        c = admin_client.get(EXTERNOS, {"provider": "wisphub", "limit": 2,
                                        "offset": desde}).json()
        vistos += [x["external_ticket_id"] for x in c["casos"]]
        desde = c["next_offset"]
    assert vistos == sorted(vistos) == ["92000", "92001", "92002", "92003", "92004"]
    assert len(vistos) == len(set(vistos)), "una fila salio dos veces al paginar"


@pytest.mark.parametrize("params", [
    {"provider": "wisphub", "limit": 0}, {"provider": "wisphub", "limit": 9999},
    {"provider": "wisphub", "offset": -1}, {"provider": "wisphub", "limit": "x"},
])
def test_paginacion_invalida_se_rechaza(admin_client, params):
    r = admin_client.get(EXTERNOS, params)
    assert r.status_code == 400
    assert r.json()["error"] in ("PAGINACION_INVALIDA",)


def test_casos_externos_sin_credencial(admin_client):
    assert APIClient().get(EXTERNOS, {"provider": "wisphub"}).status_code in (401, 403)
    assert admin_client.get(EXTERNOS).status_code == 400
