# -*- coding: utf-8 -*-
"""
================================================================================
 CADA EMPRESA NOMBRA SUS LABORES  --  20/10/2026
================================================================================

Pedido del usuario: en Rapilink la cuadrilla de instalacion solo hace clientes
nuevos; los traslados los hace la de correctivo, «pero un cambio de domicilio
no es un correctivo». Se cambia el NOMBRE que se ve, no la labor: el valor
interno ('correctivo') lo usan el reparto, el Supervisor y las jornadas.

Se afirma sobre el EFECTO: que el nombre guardado llega a las tres pantallas
que listan labores (Plantillas, Despacho, Cuadrillas), con el id de siempre.

    pytest campo/tests/test_nombres_de_labor.py
================================================================================
"""

import pytest

pytestmark = pytest.mark.django_db

CONFIG = "/api/campo/cuadrillas/configuracion/"
LO_DE_SIEMPRE = {"activo": False, "hora_local": 3, "tope_por_cuadrilla": 8,
                 "copia_la_jornada": True}
PANTALLAS = ("/api/campo/plantillas-de-trabajo/",   # Despacho
             "/api/campo/tipos-de-trabajo/",        # Cuadrillas
             "/api/campo/plantillas/")              # Plantillas


def _nombres(client, url):
    return {l["id"]: l["texto"] for l in client.get(url).json()["labores"]}


def test_a_sin_cambios_cada_labor_tiene_su_nombre_de_siempre(admin_client):
    assert admin_client.get(CONFIG).json()["nombres_de_labor"] == {}
    for url in PANTALLAS:
        assert _nombres(admin_client, url) == {
            "instalacion": "Instalacion", "correctivo": "Correctivo",
            "trabajos": "Trabajos"}, url


def test_b_el_nombre_nuevo_llega_a_las_tres_pantallas_con_el_mismo_id(
        admin_client):
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "nombres_de_labor": {
        "correctivo": "  Correctivos y   traslados ", "instalacion": ""}},
        format="json")
    assert r.status_code == 200, r.content
    #  Solo queda escrito lo que cambio; el vacio vuelve al de siempre.
    assert r.json()["nombres_de_labor"] == {"correctivo": "Correctivos y traslados"}

    for url in PANTALLAS:
        nombres = _nombres(admin_client, url)
        assert nombres["correctivo"] == "Correctivos y traslados", url
        assert nombres["instalacion"] == "Instalacion", url


def test_c_sin_la_clave_no_se_tocan(admin_client):
    admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "nombres_de_labor": {
        "correctivo": "Correctivos y traslados"}}, format="json")
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "tope_por_cuadrilla": 9},
                         format="json")
    assert r.json()["nombres_de_labor"] == {"correctivo": "Correctivos y traslados"}


def test_d_el_nombre_de_siempre_no_queda_escrito(admin_client):
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "nombres_de_labor": {
        "trabajos": "Trabajos"}}, format="json")
    assert r.json()["nombres_de_labor"] == {}


@pytest.mark.parametrize("nombres", [
    {"traslados": "Traslados"},          # una labor que no existe
    {"correctivo": "x" * 41},            # demasiado largo
    {"correctivo": 7},                   # no es texto
    ["correctivo"],                      # no es una tabla
])
def test_e_lo_que_no_se_guarda(admin_client, nombres):
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "nombres_de_labor": nombres},
                         format="json")
    assert r.status_code == 400, r.content
    assert admin_client.get(CONFIG).json()["nombres_de_labor"] == {}
