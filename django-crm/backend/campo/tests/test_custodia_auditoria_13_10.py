# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE LA AUDITORIA DE CUSTODIA ENCONTRO, CON SU ESCENARIO (13/10/2026)
================================================================================

Tres pasadas independientes sobre el inventario -- adversarial (F14), frontera
(F12) y PII -- coincidieron en huecos que ninguna prueba cazaba, porque las
pruebas afirmaban que el mecanismo EXISTIA y no que frenara el caso.

  A  el telefono solo manda lo que el telefono hace: consumo y devolucion. Un
     `ajuste` por API creaba material en la custodia propia, sin aprobacion.
  B  un consumo de una serie que el sistema sabe que esta en OTRO lado no
     entra ACEPTADO ni mueve el indice. Con el lazo al ISP encendido, ese
     serial terminaba en la ficha de un cliente.
  C  una serie INSTALADA no se vuelve a despachar como si estuviera libre.

    pytest campo/tests/test_custodia_auditoria_13_10.py
================================================================================
"""

from decimal import Decimal

import pytest

from campo.models import (AsignacionTrabajo, MaterialCatalogo,
                          MovimientoDeMaterial, OrdenTrabajo,
                          UbicacionDeActivo, UbicacionInventario, WorkType,
                          WorkTypeVersion)
from campo.services import inventario as inv
from campo.services.inventario import DespachoInvalido

pytestmark = pytest.mark.django_db

MOVIMIENTOS = "/api/campo/materiales/movimientos/"


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central")


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-HG8145", nombre="ONT Huawei",
        clase=MaterialCatalogo.SERIALIZADO)


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC")


@pytest.fixture
def otro_profile(org_a, django_user_model):
    from common.models import Profile

    user = django_user_model.objects.create_user(
        email="tec2@test.com", password="testpass123")
    return Profile.objects.create(user=user, org=org_a, role="USER",
                                  is_active=True)


@pytest.fixture
def orden(org_a, user_profile):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalacion")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=7001, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return o


def _dar_onts(org, bodega, ont, profile, *series):
    for s in series:
        inv.registrar_entrada(org=org, material=ont, cantidad=1,
                              ubicacion_destino=bodega, serie=s)
    inv.despachar(org=org, ubicacion_origen=bodega, profile_destino=profile,
                  lineas=[{"material": ont, "serie": s} for s in series])


def _consumir(cliente, orden, serie, clave="c1"):
    return cliente.post(MOVIMIENTOS, {
        "clave": clave, "material": "ONT-HG8145", "tipo": "consumo",
        "cantidad": "1", "serie": serie, "orden_id": str(orden.id),
    }, format="json")


# ---------------------------------------------------------------------------
# A · el telefono no ajusta existencias
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tipo", ["ajuste", "entrada", "despacho", "traslado", "baja"])
def test_a_un_tecnico_no_manda_movimientos_de_bodega(user_client, org_a,
                                                     conector, tipo):
    r = user_client.post(MOVIMIENTOS, {
        "clave": f"x-{tipo}", "material": "CON-SC-APC", "tipo": tipo,
        "cantidad": "50"}, format="json")
    assert r.status_code == 400, r.content
    assert not MovimientoDeMaterial.objects.filter(org=org_a).exists()


def test_a2_consumo_y_devolucion_siguen_entrando(user_client, org_a, bodega,
                                                 conector, user_profile, orden):
    inv.registrar_entrada(org=org_a, material=conector, cantidad=10,
                          ubicacion_destino=bodega)
    inv.despachar(org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
                  lineas=[{"material": conector, "cantidad": 10}])
    c = user_client.post(MOVIMIENTOS, {
        "clave": "k1", "material": "CON-SC-APC", "tipo": "consumo",
        "cantidad": "2", "orden_id": str(orden.id)}, format="json")
    d = user_client.post(MOVIMIENTOS, {
        "clave": "k2", "material": "CON-SC-APC", "tipo": "devolucion",
        "cantidad": "1"}, format="json")
    assert c.status_code in (200, 201), c.content
    assert d.status_code in (200, 201), d.content


# ---------------------------------------------------------------------------
# B · la serie tiene que estar en SU custodia
# ---------------------------------------------------------------------------

def test_b_consumir_una_serie_que_esta_en_bodega_no_entra_aceptado(
        user_client, org_a, bodega, ont, user_profile, orden):
    """Tiene UNA ont propia, y tipea la serie de otra que sigue en bodega."""
    _dar_onts(org_a, bodega, ont, user_profile, "MIA-1")
    inv.registrar_entrada(org=org_a, material=ont, cantidad=1,
                          ubicacion_destino=bodega, serie="EN-BODEGA")

    r = _consumir(user_client, orden, "EN-BODEGA")
    assert r.status_code in (200, 201), r.content

    mov = MovimientoDeMaterial.objects.get(serie="EN-BODEGA",
                                           tipo=MovimientoDeMaterial.CONSUMO)
    assert mov.estado == MovimientoDeMaterial.CONFLICTO
    assert "Bodega Central" in mov.motivo
    #  El indice NO se movio: la bodega la sigue ofreciendo.
    pos = UbicacionDeActivo.objects.get(activo__serie="EN-BODEGA")
    assert pos.ubicacion_id == bodega.id


def test_b2_la_serie_de_OTRO_tecnico_tampoco(
        user_client, org_a, bodega, ont, user_profile, otro_profile, orden):
    _dar_onts(org_a, bodega, ont, user_profile, "MIA-1")
    _dar_onts(org_a, bodega, ont, otro_profile, "DEL-OTRO")

    _consumir(user_client, orden, "DEL-OTRO")
    mov = MovimientoDeMaterial.objects.get(serie="DEL-OTRO",
                                           tipo=MovimientoDeMaterial.CONSUMO)
    assert mov.estado == MovimientoDeMaterial.CONFLICTO
    otra = inv.ubicacion_de_tecnico(otro_profile, org_a, crear=False)
    assert UbicacionDeActivo.objects.get(activo__serie="DEL-OTRO").ubicacion_id == otra.id


def test_b3_la_propia_entra_aceptada_y_sale_del_indice(
        user_client, org_a, bodega, ont, user_profile, orden):
    """El arreglo no puede frenar el caso normal."""
    _dar_onts(org_a, bodega, ont, user_profile, "MIA-1")
    _consumir(user_client, orden, "MIA-1")
    mov = MovimientoDeMaterial.objects.get(serie="MIA-1",
                                           tipo=MovimientoDeMaterial.CONSUMO)
    assert mov.estado == MovimientoDeMaterial.ACEPTADO
    assert UbicacionDeActivo.objects.get(activo__serie="MIA-1").ubicacion is None


def test_b4_una_serie_nunca_vista_sigue_entrando(
        user_client, org_a, bodega, ont, user_profile, orden):
    """Es como llega el aparato que nadie dio de alta: rechazarla dejaria la
    instalacion sin registrar."""
    _dar_onts(org_a, bodega, ont, user_profile, "MIA-1")
    _consumir(user_client, orden, "NUNCA-VISTA")
    mov = MovimientoDeMaterial.objects.get(serie="NUNCA-VISTA")
    assert mov.estado == MovimientoDeMaterial.ACEPTADO


# ---------------------------------------------------------------------------
# C · instalado no es libre
# ---------------------------------------------------------------------------

def test_c_una_serie_instalada_no_se_vuelve_a_despachar(
        user_client, org_a, bodega, ont, user_profile, otro_profile, orden):
    _dar_onts(org_a, bodega, ont, user_profile, "MIA-1")
    _consumir(user_client, orden, "MIA-1")

    with pytest.raises(DespachoInvalido, match="instalada"):
        inv.despachar(org=org_a, ubicacion_origen=bodega,
                      profile_destino=otro_profile,
                      lineas=[{"material": ont, "serie": "MIA-1"}])


def test_c2_si_volvio_del_cliente_y_entro_a_bodega_si(
        user_client, org_a, bodega, ont, user_profile, otro_profile, orden):
    """El camino legitimo de reuso: registrar su entrada primero."""
    _dar_onts(org_a, bodega, ont, user_profile, "MIA-1")
    _consumir(user_client, orden, "MIA-1")
    inv.registrar_entrada(org=org_a, material=ont, cantidad=1,
                          ubicacion_destino=bodega, serie="MIA-1")

    inv.despachar(org=org_a, ubicacion_origen=bodega,
                  profile_destino=otro_profile,
                  lineas=[{"material": ont, "serie": "MIA-1"}])
    otra = inv.ubicacion_de_tecnico(otro_profile, org_a, crear=False)
    assert inv.existencia(otra, ont) == Decimal("1")
