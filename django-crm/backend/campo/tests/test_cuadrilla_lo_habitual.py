"""
================================================================================
 LO HABITUAL DE UNA CUADRILLA SE MARCA DESDE LA PANTALLA  --  17/10/2026
================================================================================
De las zonas y la labor habituales arma el Supervisor la jornada de cada dia
(SPEC/objetivos/supervisor-arma-la-jornada.md). La API ya las aceptaba al
editar, pero la pantalla no dejaba marcarlas, y el alta las ignoraba.
================================================================================
"""
import pytest

from campo.cuadrillas import Cuadrilla
from campo.zonas import ZonaOperativa

pytestmark = pytest.mark.django_db

CUADRILLAS = "/api/campo/cuadrillas/"


def test_a_el_alta_guarda_zonas_y_labor_habituales(admin_client, org_a):
    soledad = ZonaOperativa.objects.create(org=org_a, nombre="SOLEDAD")

    r = admin_client.post(CUADRILLAS, {
        "nombre": "Cuadrilla #9", "labor_habitual": "correctivo",
        "zonas_habituales": [str(soledad.id)]}, format="json")

    assert r.status_code == 201, r.content
    assert r.json()["labor_habitual"] == "correctivo"
    assert [z["nombre"] for z in r.json()["zonas_habituales"]] == ["SOLEDAD"]
    c = Cuadrilla.objects.get(org=org_a, nombre="Cuadrilla #9")
    assert list(c.zonas_habituales.values_list("nombre", flat=True)) == ["SOLEDAD"]


def test_b_una_labor_que_no_existe_no_deja_una_cuadrilla_a_medias(admin_client,
                                                                   org_a):
    r = admin_client.post(CUADRILLAS, {"nombre": "Cuadrilla #9",
                                       "labor_habitual": "pintura"},
                          format="json")

    assert r.status_code == 400, r.content
    assert not Cuadrilla.objects.filter(org=org_a, nombre="Cuadrilla #9").exists()


def test_c_editar_reemplaza_la_lista_entera(admin_client, org_a):
    soledad = ZonaOperativa.objects.create(org=org_a, nombre="SOLEDAD")
    sabanagrande = ZonaOperativa.objects.create(org=org_a, nombre="SABANAGRANDE")
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla #1")
    c.zonas_habituales.set([soledad])
    url = f"{CUADRILLAS}{c.id}/"

    r = admin_client.patch(url, {"zonas_habituales": [str(sabanagrande.id)],
                                 "labor_habitual": "trabajos"}, format="json")
    assert r.status_code == 200, r.content
    c.refresh_from_db()
    assert list(c.zonas_habituales.values_list("nombre", flat=True)) == ["SABANAGRANDE"]
    assert c.labor_habitual == "trabajos"

    r = admin_client.patch(url, {"zonas_habituales": []}, format="json")
    assert r.status_code == 200, r.content
    assert not c.zonas_habituales.exists(), "desmarcar todas tiene que vaciarla"


def test_d_una_zona_de_otra_empresa_no_se_engancha(admin_client, org_a, org_b):
    from conftest import set_rls_context

    set_rls_context(org_b)
    ajena = ZonaOperativa.objects.create(org=org_b, nombre="AJENA")
    set_rls_context(org_a)

    r = admin_client.post(CUADRILLAS, {"nombre": "Cuadrilla #9",
                                       "zonas_habituales": [str(ajena.id)]},
                          format="json")

    assert r.status_code == 201, r.content
    assert r.json()["zonas_habituales"] == []


def test_e_sin_lo_habitual_el_alta_sigue_como_antes(admin_client, org_a):
    r = admin_client.post(CUADRILLAS, {"nombre": "Cuadrilla #9"}, format="json")

    assert r.status_code == 201, r.content
    assert r.json()["labor_habitual"] == "instalacion"
    assert r.json()["zonas_habituales"] == []
