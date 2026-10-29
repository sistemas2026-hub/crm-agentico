"""
================================================================================
 EL REPORTE DE ENTREGAS  --  28/10/2026
================================================================================
`GET /api/campo/inventario/reportes/?de=entregas`: cada acta de entrega a un
tecnico, tal como quedo. Pedido del usuario: «¿donde puedo ver el registro de
lo entregado a los tecnicos? Se tiene que guardar por entrega».

  E  cada entrega con su tecnico, su bodega, quien la despacho, su material
     (con la serie de cada equipo) y si el tecnico la confirmo.
  B  la bodega sale tambien sin acta (el despacho guarda el id de la entrega);
     una entrega vieja que no se puede atar dice que no se sabe.
  F  las fechas se cortan en el dia de la EMPRESA.
  P  solo quien gestiona o atiende bodega, y solo su empresa.

    pytest campo/tests/test_reporte_entregas.py
================================================================================
"""
import datetime as dt

import pytest

from campo.inventario import UbicacionInventario
from campo.models import EntregaDeKit, MaterialCatalogo, MovimientoDeMaterial
from campo.services import inventario as inv
from campo.services import inventario_operacion as op

pytestmark = pytest.mark.django_db

RUTA = "/api/campo/inventario/reportes/"


@pytest.fixture
def soledad(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="BOG-SOLEDAD")


@pytest.fixture
def sabana(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="BOF-SAB_GRANDE")


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-UPC", nombre="Conector UPC",
        clase=MaterialCatalogo.CONSUMIBLE, unidad="unidades")


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONU-WIFI", nombre="ONU WIFI",
        clase=MaterialCatalogo.SERIALIZADO, unidad="unidades")


def _entrada(org, bodega, material, cantidad=1, serie=""):
    inv.registrar_entrada(org=org, material=material, cantidad=cantidad,
                          ubicacion_destino=bodega, serie=serie)


def test_e_cada_entrega_con_su_material_y_su_bodega(
        org_a, soledad, sabana, conector, ont, admin_profile, user_profile):
    _entrada(org_a, soledad, conector, 20)
    _entrada(org_a, soledad, ont, serie="ONT-1")
    _entrada(org_a, sabana, conector, 5)
    inv.despachar(org=org_a, ubicacion_origen=soledad, profile_destino=user_profile,
                  acta="K-1", despachado_por=admin_profile,
                  lineas=[{"material": conector, "cantidad": 10},
                          {"material": ont, "serie": "ONT-1"}])
    #  Sin acta: la bodega sale igual, por el id de la entrega.
    inv.despachar(org=org_a, ubicacion_origen=sabana, profile_destino=admin_profile,
                  lineas=[{"material": conector, "cantidad": 3}])

    filas = op.entregas_a_tecnicos(org_a)

    assert [f["bodega"] for f in filas] == ["BOF-SAB_GRANDE", "BOG-SOLEDAD"]   # la ultima primero
    k1 = filas[1]
    assert (k1["acta"], k1["confirmado_en"]) == ("K-1", None)
    assert k1["tecnico"] and k1["despachado_por"]
    assert k1["lineas"] == [
        {"material": "Conector UPC", "unidad": "unidades", "cantidad": "10", "serie": ""},
        {"material": "ONU WIFI", "unidad": "unidades", "cantidad": "1", "serie": "ONT-1"},
    ]


def test_b_una_entrega_vieja_que_no_se_puede_atar_dice_que_no_se_sabe(
        org_a, soledad, conector, user_profile):
    _entrada(org_a, soledad, conector, 5)
    e, _ = inv.despachar(org=org_a, ubicacion_origen=soledad, profile_destino=user_profile,
                         lineas=[{"material": conector, "cantidad": 2}])
    #  Como antes del 28/10/2026: sin acta, el movimiento no guardaba nada.
    MovimientoDeMaterial.objects.filter(org=org_a, tipo=MovimientoDeMaterial.DESPACHO).update(
        datos={})

    (fila,) = op.entregas_a_tecnicos(org_a)

    assert fila["id"] == str(e.id) and fila["bodega"] is None


def test_f_el_dia_es_el_de_la_empresa(org_a, soledad, conector, user_profile):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    _entrada(org_a, soledad, conector, 5)
    e, _ = inv.despachar(org=org_a, ubicacion_origen=soledad, profile_destino=user_profile,
                         acta="NOCHE", lineas=[{"material": conector, "cantidad": 1}])
    #  22:00 del 28 en Bogota = 03:00 del 29 en UTC.
    EntregaDeKit.objects.filter(pk=e.pk).update(
        entregado_en=dt.datetime(2026, 10, 29, 3, 0, tzinfo=dt.timezone.utc))
    dia = dt.datetime(2026, 10, 28)

    assert [f["acta"] for f in op.entregas_a_tecnicos(org_a, desde=dia, hasta=dia)] == ["NOCHE"]
    otro = dt.datetime(2026, 10, 29)
    assert op.entregas_a_tecnicos(org_a, desde=otro, hasta=otro) == []
    (fila,) = op.entregas_a_tecnicos(org_a)
    assert fila["entregado_en"].startswith("2026-10-28T22:00")


def test_p_solo_quien_gestiona_y_solo_su_empresa(
        org_a, org_b, soledad, conector, user_profile, admin_client, user_client,
        django_user_model):
    from common.models import Profile

    _entrada(org_a, soledad, conector, 5)
    inv.despachar(org=org_a, ubicacion_origen=soledad, profile_destino=user_profile,
                  acta="K-A", lineas=[{"material": conector, "cantidad": 1}])
    #  Una entrega de OTRA empresa, que no tiene que aparecer.
    ajena = UbicacionInventario.objects.create(org=org_b, tipo=UbicacionInventario.BODEGA,
                                               nombre="Ajena")
    otro_mat = MaterialCatalogo.objects.create(org=org_b, codigo="X", nombre="X",
                                               clase=MaterialCatalogo.CONSUMIBLE,
                                               unidad="unidades")
    _entrada(org_b, ajena, otro_mat, 5)
    u = django_user_model.objects.create_user(email="ajeno@test.com", password="x1234567")
    ajeno = Profile.objects.create(user=u, org=org_b, role="USER", is_active=True)
    inv.despachar(org=org_b, ubicacion_origen=ajena, profile_destino=ajeno, acta="K-B",
                  lineas=[{"material": otro_mat, "cantidad": 1}])
    assert [f["acta"] for f in op.entregas_a_tecnicos(org_b)] == ["K-B"]

    assert user_client.get(RUTA, {"de": "entregas"}).status_code == 403
    r = admin_client.get(RUTA, {"de": "entregas"})
    assert r.status_code == 200, r.content
    assert [f["acta"] for f in r.json()["filas"]] == ["K-A"]
