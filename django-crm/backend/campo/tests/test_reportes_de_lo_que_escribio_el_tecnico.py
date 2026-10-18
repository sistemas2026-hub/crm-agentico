# -*- coding: utf-8 -*-
"""
Los pedidos a bodega, los faltantes explicados y las actas llegan a la oficina.

18/10/2026: los tres se guardaban y ninguna pantalla de la web los mostraba. El
pedido llegaba solo si la empresa tenia un canal de avisos, y la explicacion de
un faltante quedaba escrita sin que nadie pudiera leerla. Ahora son tres
reportes de `GET /inventario/reportes/`, que la web pasa enteros a la pantalla.

Lo que cuidan estas pruebas, ademas de que el dato llegue: que el texto libre
viaje tapado, que un tecnico no lea lo que escribio otro, y que otra empresa no
vea nada.
"""

from datetime import date

import pytest
from django.utils import timezone

from campo.models import (
    ActaDeDevolucion,
    IncidenciaDeMaterial,
    MaterialCatalogo,
    PedidoDeMaterial,
)

pytestmark = pytest.mark.django_db

REPORTES = "/api/campo/inventario/reportes/"


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC", unidad="unidades")


@pytest.fixture
def pedido(org_a, user_profile, conector):
    return PedidoDeMaterial.objects.create(
        org=org_a, profile=user_profile, material=conector, cantidad=20,
        motivo="se acabaron, llamar al 3001234567", idempotency_key="p-1")


def _filas(client, de, **params):
    r = client.get(REPORTES, {"de": de, **params})
    assert r.status_code == 200, r.content
    return r.json()["filas"]


def test_1_bodega_ve_el_pedido_con_quien_lo_pidio(admin_client, pedido, regular_user):
    fila = _filas(admin_client, "pedidos")[0]
    assert (fila["material"], fila["cantidad"], fila["unidad"], fila["estado"]) == (
        "CON-SC-APC", "20", "unidades", "pendiente")
    assert fila["persona"] == (regular_user.name or regular_user.email)


def test_2_el_texto_libre_viaja_tapado(admin_client, pedido):
    motivo = _filas(admin_client, "pedidos")[0]["motivo"]
    assert "se acabaron" in motivo
    assert "3001234567" not in motivo


def test_3_un_tecnico_no_lee_lo_que_escribio_otro(user_client, pedido):
    for de in ("pedidos", "faltantes", "cierres"):
        assert user_client.get(REPORTES, {"de": de}).status_code == 403, de
    # Los de antes siguen abiertos a cualquier sesion de campo.
    assert user_client.get(REPORTES, {"de": "consumo"}).status_code == 200


def test_4_otra_empresa_no_ve_nada(org_b_client, pedido):
    assert _filas(org_b_client, "pedidos") == []


def test_5_hasta_cuenta_el_dia_entero(admin_client, pedido):
    hoy = timezone.localdate().isoformat()
    assert len(_filas(admin_client, "pedidos", desde=hoy, hasta=hoy)) == 1


def test_6_el_faltante_dice_que_paso_y_por_que(admin_client, org_a, user_profile, conector):
    IncidenciaDeMaterial.objects.create(
        org=org_a, profile=user_profile, material=conector,
        tipo=IncidenciaDeMaterial.DANADO, cantidad=3,
        motivo="se partieron al pelar la fibra", idempotency_key="i-1")

    fila = _filas(admin_client, "faltantes")[0]

    assert fila["tipo"] == "danado"
    assert fila["tipo_texto"] == dict(IncidenciaDeMaterial.TIPOS)["danado"]
    assert (fila["material"], fila["cantidad"]) == ("CON-SC-APC", "3")
    assert fila["motivo"] == "se partieron al pelar la fibra"
    assert fila["jornada"] is None


def test_7_el_acta_muestra_lo_que_se_congelo_no_un_recalculo(admin_client, org_a, user_profile):
    ActaDeDevolucion.objects.create(
        org=org_a, profile=user_profile, jornada=date(2026, 10, 17),
        estado=ActaDeDevolucion.CONFIRMADA, confirmada_en=timezone.now(),
        resumen={
            "ordenes": {"asignadas": 3, "completadas": 3, "pendientes": 0},
            "material": {"por_unidad": [{"unidad": "m", "recibido": "100"}]},
            "detalle": [{"codigo": "DROP", "nombre": "Cable drop", "unidad": "m",
                         "entregado": "100", "consumido": "35",
                         "esperado_devolver": "65", "devuelto": "65",
                         "diferencia": "0"}],
        })
    # Una pendiente no es un acta: no se firmó.
    ActaDeDevolucion.objects.create(org=org_a, profile=user_profile,
                                    jornada=date(2026, 10, 18))

    filas = _filas(admin_client, "cierres")

    assert [f["jornada"] for f in filas] == ["2026-10-17"]
    assert filas[0]["ordenes"]["completadas"] == 3
    assert filas[0]["materiales"][0]["consumido"] == "35"
    assert filas[0]["por_unidad"] == [{"unidad": "m", "recibido": "100"}]


def test_8_otra_empresa_no_ve_las_actas_ni_los_faltantes(org_b_client, org_a, user_profile, conector):
    IncidenciaDeMaterial.objects.create(
        org=org_a, profile=user_profile, material=conector, cantidad=1,
        motivo="x", idempotency_key="i-2")
    ActaDeDevolucion.objects.create(
        org=org_a, profile=user_profile, jornada=date(2026, 10, 17),
        estado=ActaDeDevolucion.CONFIRMADA)
    assert _filas(org_b_client, "faltantes") == []
    assert _filas(org_b_client, "cierres") == []
