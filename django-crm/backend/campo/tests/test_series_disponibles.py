# -*- coding: utf-8 -*-
"""
================================================================================
 QUE SERIES HAY EN ESTA BODEGA  --  para elegirlas en vez de escribirlas
================================================================================

Por que existe el endpoint
--------------------------
Despachar una ONT pedia teclear su numero a mano teniendo la bodega el dato:
doce caracteres sin separadores, leidos de una etiqueta. Un error de tipeo no se
nota hasta que el aparato aparece "en otra custodia", que es el peor momento.

Que se afirma aca
-----------------
El EFECTO: que la lista traiga las que de verdad estan en esa ubicacion y NO las
que estan en otra. No que el endpoint exista.
"""

import pytest

from campo.inventario import UbicacionInventario
from campo.models import MaterialCatalogo
from campo.services import inventario as inv

pytestmark = pytest.mark.django_db

SERIES = "/api/campo/inventario/series/"


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="BOG-SOLEDAD"
    )


@pytest.fixture
def otra_bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="BOG-NORTE"
    )


@pytest.fixture
def onu(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONU-CATV", nombre="ONU CATV",
        clase=MaterialCatalogo.SERIALIZADO, unidad="unidades",
    )


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-APC", nombre="CONECTOR APC",
        clase=MaterialCatalogo.CONSUMIBLE, unidad="unidades",
    )


def _entrar(org, material, serie, ubicacion):
    inv.registrar_entrada(
        org=org, material=material, cantidad=1, ubicacion_destino=ubicacion,
        serie=serie, origen_ref=f"FAC-{serie}",
    )


def test_a_trae_las_series_de_esa_ubicacion(admin_client, org_a, bodega, onu):
    for x in ("HWTCA6FB5263", "HWTCA6FB5264", "HWTCA6FB5265"):
        _entrar(org_a, onu, x, bodega)

    r = admin_client.get(SERIES, {"ubicacion": str(bodega.id),
                                  "material": "ONU-CATV"})
    assert r.status_code == 200, r.content
    assert r.json()["series"] == [
        "HWTCA6FB5263", "HWTCA6FB5264", "HWTCA6FB5265",
    ]


def test_b_no_trae_las_de_OTRA_ubicacion(
    admin_client, org_a, bodega, otra_bodega, onu
):
    # El caso que importa: una serie de otra bodega haria que la pantalla
    # ofrezca despachar algo que no esta ahi.
    _entrar(org_a, onu, "HWTCA6FB5263", bodega)
    _entrar(org_a, onu, "HWTCA6FB9999", otra_bodega)

    r = admin_client.get(SERIES, {"ubicacion": str(bodega.id),
                                  "material": "ONU-CATV"})
    assert r.json()["series"] == ["HWTCA6FB5263"]


def test_c_un_consumible_devuelve_vacio_y_no_un_error(
    admin_client, bodega, conector
):
    # La pantalla puede preguntar sin saber de antemano que clase es; un 400
    # la obligaria a ramificar antes de preguntar.
    r = admin_client.get(SERIES, {"ubicacion": str(bodega.id),
                                  "material": "CON-APC"})
    assert r.status_code == 200
    assert r.json()["series"] == []


def test_d_sin_ubicacion_lo_dice(admin_client, onu):
    r = admin_client.get(SERIES, {"material": "ONU-CATV"})
    assert r.status_code == 400


def test_e_una_bodega_vacia_devuelve_vacio(admin_client, bodega, onu):
    r = admin_client.get(SERIES, {"ubicacion": str(bodega.id),
                                  "material": "ONU-CATV"})
    assert r.status_code == 200
    assert r.json()["series"] == []
