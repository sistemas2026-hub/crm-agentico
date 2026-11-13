"""
================================================================================
 LA RECEPCION DEL KIT  --  28/10/2026
================================================================================
`campo/recepcion_del_kit.py` y `/api/campo/kit/recepcion/`, fase 2 de
SPEC/objetivos/material-del-dia.md.

  P  lo pendiente: sus actas de los ultimos dias sin confirmar, y los equipos
     apartados a su nombre.
  C  confirmar: conforme, o lo recibido de cada material con su motivo (lo que
     no llego queda como incidencia). Idempotente; solo lo suyo.
  E  escanear: de la bodega a su custodia con su serie, cerrando SU reserva y
     no la de otra cuadrilla aunque sea mas antigua.

    pytest campo/tests/test_recepcion_del_kit.py
================================================================================
"""
import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from campo import recepcion_del_kit as R
from campo.inventario import UbicacionInventario
from campo.inventario_operacion import ReservaDeMaterial
from campo.models import EntregaDeKit, IncidenciaDeMaterial, MaterialCatalogo
from campo.services import inventario as inv
from campo.services.inventario_operacion import reservar

pytestmark = pytest.mark.django_db

RUTA = "/api/campo/kit/recepcion/"


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="BOG-SOLEDAD")


@pytest.fixture
def otra_bodega(org_a):
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


@pytest.fixture
def otro(org_a, django_user_model):
    from common.models import Profile

    u = django_user_model.objects.create_user(email="lider2@test.com", password="x1234567")
    return Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)


def _kit(org, bodega, conector, profile, acta="K-1", cantidad=10):
    inv.registrar_entrada(org=org, material=conector, cantidad=cantidad,
                          ubicacion_destino=bodega)
    entrega, _ = inv.despachar(org=org, ubicacion_origen=bodega, profile_destino=profile,
                               acta=acta, lineas=[{"material": conector, "cantidad": cantidad}])
    return entrega


def _apartar(org, bodega, ont, profile, series, acta="MAT-20261028-aaaa"):
    for s in series:
        inv.registrar_entrada(org=org, material=ont, cantidad=1, ubicacion_destino=bodega,
                              serie=s)
    return reservar(org=org, ubicacion=bodega, material=ont, cantidad=len(series),
                    reservada_por=profile, motivo=f"{acta} · equipos del día")


# ---------------------------------------------------------------------------
# P · lo pendiente
# ---------------------------------------------------------------------------

def test_p_lo_pendiente_es_lo_suyo_y_reciente(org_a, bodega, conector, ont, user_profile, otro):
    reciente = _kit(org_a, bodega, conector, user_profile, acta="K-HOY")
    vieja = _kit(org_a, bodega, conector, user_profile, acta="K-VIEJA")
    EntregaDeKit.objects.filter(pk=vieja.pk).update(
        entregado_en=timezone.now() - dt.timedelta(days=4))
    _kit(org_a, bodega, conector, otro, acta="K-OTRO")
    _apartar(org_a, bodega, ont, user_profile, ["S-1", "S-2"])

    p = R.pendiente_de(user_profile, org_a)

    assert [e["acta"] for e in p["por_confirmar"]] == ["K-HOY"]
    assert p["por_confirmar"][0]["id"] == str(reciente.id)
    assert p["por_confirmar"][0]["bodega"] == "BOG-SOLEDAD"
    assert p["por_confirmar"][0]["lineas"] == [
        {"codigo": "CON-UPC", "nombre": "Conector UPC", "unidad": "unidades",
         "cantidad": "10", "serie": ""}]
    assert p["por_escanear"] == [{"codigo": "ONU-WIFI", "nombre": "ONU WIFI",
                                  "bodega": "BOG-SOLEDAD", "cantidad": "2"}]


# ---------------------------------------------------------------------------
# C · confirmar
# ---------------------------------------------------------------------------

def test_c_conforme_y_dos_veces_no_repite(org_a, bodega, conector, user_profile, user_client):
    e = _kit(org_a, bodega, conector, user_profile)

    r = user_client.post(f"{RUTA}{e.id}/confirmar/", {"conforme": True}, format="json")
    assert r.status_code == 200, r.content
    e.refresh_from_db()
    assert e.confirmado_en is not None and "Al recibir: conforme." in e.notas

    r2 = user_client.post(f"{RUTA}{e.id}/confirmar/", {"conforme": True}, format="json")
    assert r2.json()["ya_estaba"] is True
    assert R.pendiente_de(user_profile, org_a)["por_confirmar"] == []


def test_c2_lo_que_no_llego_queda_explicado(org_a, bodega, conector, user_profile):
    e = _kit(org_a, bodega, conector, user_profile)

    R.confirmar(user_profile, org_a, e.id, conforme=False, diferencias=[
        {"codigo": "CON-UPC", "recibido": "7", "motivo": "en bodega solo había 7"}])

    inc = IncidenciaDeMaterial.objects.get(org=org_a, profile=user_profile)
    assert inc.cantidad == Decimal("3") and "No llegó en la entrega K-1" in inc.motivo
    e.refresh_from_db()
    assert "faltó: 3 unidades de Conector UPC" in e.notas


@pytest.mark.parametrize("diferencias, frase", [
    ([{"codigo": "OTRO", "recibido": "1", "motivo": "x"}], "no está en esta entrega"),
    ([{"codigo": "CON-UPC", "recibido": "11", "motivo": "x"}], "va de 0 a 10"),
    ([{"codigo": "CON-UPC", "recibido": "7", "motivo": ""}], "por qué"),
    ([{"codigo": "CON-UPC", "recibido": "10", "motivo": "x"}], "coincide"),
    ([], "qué no coincide"),
])
def test_c3_lo_que_se_rechaza_no_escribe_nada(org_a, bodega, conector, user_profile,
                                              diferencias, frase):
    e = _kit(org_a, bodega, conector, user_profile)

    with pytest.raises(R.RecepcionInvalida, match=frase):
        R.confirmar(user_profile, org_a, e.id, conforme=False, diferencias=diferencias)

    e.refresh_from_db()
    assert e.confirmado_en is None
    assert not IncidenciaDeMaterial.objects.filter(org=org_a).exists()


def test_c4_la_de_otro_no_se_confirma(org_a, bodega, conector, otro, user_client):
    e = _kit(org_a, bodega, conector, otro)

    r = user_client.post(f"{RUTA}{e.id}/confirmar/", {"conforme": True}, format="json")

    assert r.status_code == 400
    e.refresh_from_db()
    assert e.confirmado_en is None


# ---------------------------------------------------------------------------
# E · escanear
# ---------------------------------------------------------------------------

def test_e_escanear_es_recibir(org_a, bodega, ont, user_profile, user_client):
    reserva = _apartar(org_a, bodega, ont, user_profile, ["CDTC505AEA5F"])

    r = user_client.post(f"{RUTA}escanear/", {"serie": " cdtc505aea5f "}, format="json")

    assert r.status_code == 200, r.content
    assert r.json()["serie"] == "CDTC505AEA5F"
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)
    assert inv.existencia(custodia, ont) == Decimal("1")
    reserva.refresh_from_db()
    assert reserva.resuelta_en is not None
    entrega = EntregaDeKit.objects.get(org=org_a, acta="MAT-20261028-aaaa:CDTC505AEA5F")
    assert entrega.confirmado_en is not None
    assert R.pendiente_de(user_profile, org_a)["por_escanear"] == []


def test_e2_cierra_su_reserva_y_no_la_del_otro(org_a, bodega, ont, user_profile, otro):
    #  La del otro es MAS ANTIGUA: antes se cerraba esa.
    del_otro = _apartar(org_a, bodega, ont, otro, ["S-OTRO"], acta="MAT-20261028-bbbb")
    suya = _apartar(org_a, bodega, ont, user_profile, ["S-MIA"])

    R.escanear(user_profile, org_a, "S-MIA")

    suya.refresh_from_db()
    del_otro.refresh_from_db()
    assert suya.resuelta_en is not None
    assert del_otro.resuelta_en is None


def test_e3_lo_que_se_rechaza(org_a, bodega, otra_bodega, ont, conector, user_profile):
    _apartar(org_a, bodega, ont, user_profile, ["S-1"])
    inv.registrar_entrada(org=org_a, material=ont, cantidad=1, ubicacion_destino=otra_bodega,
                          serie="S-LEJOS")

    with pytest.raises(R.RecepcionInvalida, match="no está registrada"):
        R.escanear(user_profile, org_a, "NO-EXISTE")
    with pytest.raises(R.RecepcionInvalida, match="BOF-SAB_GRANDE"):
        R.escanear(user_profile, org_a, "S-LEJOS")
    #  Un equipo de un material que no tiene apartado.
    otra = MaterialCatalogo.objects.create(org=org_a, codigo="ONU-CATV", nombre="ONU CATV",
                                           clase=MaterialCatalogo.SERIALIZADO,
                                           unidad="unidades")
    inv.registrar_entrada(org=org_a, material=otra, cantidad=1, ubicacion_destino=bodega,
                          serie="S-CATV")
    with pytest.raises(R.RecepcionInvalida, match="No tenés ONU CATV"):
        R.escanear(user_profile, org_a, "S-CATV")
    assert ReservaDeMaterial.objects.get(org=org_a, material=ont).resuelta_en is None
