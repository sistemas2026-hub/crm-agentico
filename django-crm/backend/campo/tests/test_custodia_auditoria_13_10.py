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


# ---------------------------------------------------------------------------
# D1 · una devolucion se cuenta UNA vez
# ---------------------------------------------------------------------------

def _con_conectores(org, bodega, conector, profile, n=18):
    inv.registrar_entrada(org=org, material=conector, cantidad=100,
                          ubicacion_destino=bodega)
    inv.despachar(org=org, ubicacion_origen=bodega, profile_destino=profile,
                  lineas=[{"material": conector, "cantidad": n}])
    return inv.ubicacion_de_tecnico(profile, org, crear=False)


def _devolver_por_app(cliente, cantidad, clave="dv1", serie=None, material="CON-SC-APC"):
    cuerpo = {"clave": clave, "material": material, "tipo": "devolucion",
              "cantidad": str(cantidad)}
    if serie:
        cuerpo["serie"] = serie
    r = cliente.post(MOVIMIENTOS, cuerpo, format="json")
    assert r.status_code in (200, 201), r.content


def test_d1_app_y_web_dejan_la_custodia_en_cero_y_la_bodega_UNA_vez(
        user_client, org_a, bodega, conector, user_profile):
    custodia = _con_conectores(org_a, bodega, conector, user_profile)
    antes = inv.existencia(bodega, conector)

    _devolver_por_app(user_client, 18)
    inv.recibir_devolucion(org=org_a, profile_origen=user_profile,
                           ubicacion_destino=bodega,
                           lineas=[{"material": conector, "cantidad": 18}])

    assert inv.existencia(custodia, conector) == Decimal("0")          # antes: -18
    assert inv.existencia(bodega, conector) == antes + Decimal("18")
    from campo.services.materiales import movido_por
    assert movido_por(user_profile, conector,
                      MovimientoDeMaterial.DEVOLUCION) == Decimal("18")  # antes: 36


def test_d1b_lo_declarado_y_no_recibido_queda_A_LA_VISTA(
        user_client, org_a, bodega, conector, user_profile):
    custodia = _con_conectores(org_a, bodega, conector, user_profile)
    _devolver_por_app(user_client, 18)
    assert inv.existencia(custodia, conector) == Decimal("0")
    assert inv._declarado_sin_recibir(org_a, user_profile, conector,
                                      custodia) == Decimal("18")


def test_d1c_parte_declarada_y_parte_no(
        user_client, org_a, bodega, conector, user_profile):
    """Declaro 10 por la app y llegaron 18 a la bodega: 10 se consumen de lo
    declarado y solo 8 salen de la custodia."""
    custodia = _con_conectores(org_a, bodega, conector, user_profile)
    antes = inv.existencia(bodega, conector)
    _devolver_por_app(user_client, 10)
    movs, _ = inv.recibir_devolucion(
        org=org_a, profile_origen=user_profile, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 18}])
    assert sorted(m.cantidad for m in movs) == [Decimal("8"), Decimal("10")]
    assert inv.existencia(custodia, conector) == Decimal("0")
    assert inv.existencia(bodega, conector) == antes + Decimal("18")


def test_d1d_una_serie_devuelta_por_la_app_y_recibida_queda_en_bodega(
        user_client, org_a, bodega, ont, user_profile):
    _dar_onts(org_a, bodega, ont, user_profile, "ONT-DV")
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)
    _devolver_por_app(user_client, 1, serie="ONT-DV", material="ONT-HG8145")
    inv.recibir_devolucion(org=org_a, profile_origen=user_profile,
                           ubicacion_destino=bodega,
                           lineas=[{"material": ont, "serie": "ONT-DV"}])
    assert inv.existencia(custodia, ont) == Decimal("0")
    assert UbicacionDeActivo.objects.get(activo__serie="ONT-DV").ubicacion_id == bodega.id


def test_d1e_sin_declaracion_todo_sale_de_la_custodia_como_antes(
        org_a, bodega, conector, user_profile):
    custodia = _con_conectores(org_a, bodega, conector, user_profile)
    inv.recibir_devolucion(org=org_a, profile_origen=user_profile,
                           ubicacion_destino=bodega,
                           lineas=[{"material": conector, "cantidad": 5}])
    assert inv.existencia(custodia, conector) == Decimal("13")


def test_d1f_un_reintento_con_referencia_no_escribe_otra_vez(
        user_client, org_a, bodega, conector, user_profile):
    """Antes chocaba contra el unique y terminaba en un 500."""
    _con_conectores(org_a, bodega, conector, user_profile)
    _devolver_por_app(user_client, 10)
    kw = dict(org=org_a, profile_origen=user_profile, ubicacion_destino=bodega,
              lineas=[{"material": conector, "cantidad": 18}], referencia="ACTA-9")
    primera, _ = inv.recibir_devolucion(**kw)
    total = MovimientoDeMaterial.objects.count()
    segunda, _ = inv.recibir_devolucion(**kw)
    assert MovimientoDeMaterial.objects.count() == total
    assert {m.id for m in segunda} == {m.id for m in primera}


# ---------------------------------------------------------------------------
# D3 · el aviso al ISP no sale por una orden ajena
# ---------------------------------------------------------------------------

def test_d3_un_consumo_atado_a_una_orden_ajena_no_avisa_al_isp(
        org_a, bodega, ont, otro_profile, orden, monkeypatch):
    """`orden` esta asignada a user_profile; consume otro_profile."""
    from campo.services import lazo_isp
    from campo.services.materiales import registrar_movimiento

    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    orden.cliente_id_abonado = "5832"
    orden.save(update_fields=["cliente_id_abonado"])
    _dar_onts(org_a, bodega, ont, otro_profile, "AJENA-1")
    mov, _ = registrar_movimiento(
        org=org_a, profile=otro_profile, material=ont,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("1"),
        idempotency_key="aj-1", serie="AJENA-1", orden=orden)
    assert mov.estado == MovimientoDeMaterial.ACEPTADO

    import requests
    llamado = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: llamado.append(1))
    r = lazo_isp.intentar_avisar(mov)
    assert r.estado == lazo_isp.ResultadoAviso.NO_CORRESPONDE
    assert "no esta asignado" in r.detalle
    assert llamado == []


# ---------------------------------------------------------------------------
# D2 · el rol BODEGA se puede asignar, y no es admin
# ---------------------------------------------------------------------------

def test_d2_bodega_es_un_rol_asignable_y_no_da_admin(user_profile):
    from common.serializer import CreateProfileSerializer

    s = CreateProfileSerializer(data={"role": "BODEGA"}, instance=user_profile,
                                can_grant_privileges=True, partial=True)
    assert s.is_valid(), s.errors
    perfil = s.save()
    perfil.refresh_from_db()
    assert perfil.role == "BODEGA"
    assert perfil.is_organization_admin is False


# ---------------------------------------------------------------------------
# D9 · una entrada o una devolucion no resta
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cantidad", [0, -50, "NaN"])
def test_d9_una_entrada_no_positiva_se_rechaza(org_a, bodega, conector, cantidad):
    with pytest.raises(DespachoInvalido, match="mayor que cero|no es un numero"):
        inv.registrar_entrada(org=org_a, material=conector, cantidad=cantidad,
                              ubicacion_destino=bodega)
    assert not MovimientoDeMaterial.objects.filter(org=org_a).exists()


def test_d9b_una_devolucion_negativa_no_escribe_NINGUNA_linea(
        org_a, bodega, conector, ont, user_profile):
    """Atomica: la linea buena tampoco queda escrita si otra no lo es."""
    _con_conectores(org_a, bodega, conector, user_profile)
    antes = MovimientoDeMaterial.objects.count()
    with pytest.raises(DespachoInvalido):
        inv.recibir_devolucion(
            org=org_a, profile_origen=user_profile, ubicacion_destino=bodega,
            lineas=[{"material": conector, "cantidad": 5},
                    {"material": conector, "cantidad": -5}])
    assert MovimientoDeMaterial.objects.count() == antes


# ---------------------------------------------------------------------------
# P2 · el motivo del tecnico llega tapado al reporte
# ---------------------------------------------------------------------------

def test_p2_el_reporte_de_descuadres_no_trae_el_celular(
        org_a, conector, user_profile, orden):
    from campo.services.inventario_operacion import descuadres_abiertos
    from campo.services.materiales import registrar_movimiento

    mov, _ = registrar_movimiento(
        org=org_a, profile=user_profile, material=conector,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("3"),
        idempotency_key="p2-1", orden=orden,
        motivo_tecnico="use de mas, el cliente 3001234567 pidio otro punto")
    assert mov.estado == MovimientoDeMaterial.DESCUADRE
    fila = next(f for f in descuadres_abiertos(org_a) if f["id"] == str(mov.id))
    assert "3001234567" not in fila["motivo_tecnico"]
    assert "pidio otro punto" in fila["motivo_tecnico"]


# ---------------------------------------------------------------------------
# D8 · una serie re-entregada vuelve a estar pendiente
# ---------------------------------------------------------------------------

def test_d8_devuelta_y_re_entregada_vuelve_a_figurar_pendiente(
        user_client, org_a, bodega, ont, user_profile):
    from campo.services.cierre_jornada import series_sin_devolver

    _dar_onts(org_a, bodega, ont, user_profile, "IDA-Y-VUELTA")
    inv.recibir_devolucion(org=org_a, profile_origen=user_profile,
                           ubicacion_destino=bodega,
                           lineas=[{"material": ont, "serie": "IDA-Y-VUELTA"}])
    assert "IDA-Y-VUELTA" not in [s["serie"] if isinstance(s, dict) else s
                                  for s in series_sin_devolver(user_profile, org_a)]

    inv.despachar(org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
                  lineas=[{"material": ont, "serie": "IDA-Y-VUELTA"}])
    pendientes = [s["serie"] if isinstance(s, dict) else s
                  for s in series_sin_devolver(user_profile, org_a)]
    assert "IDA-Y-VUELTA" in pendientes


def test_d9c_si_una_linea_falla_a_mitad_de_camino_no_queda_media_devolucion(
        org_a, bodega, conector, user_profile, monkeypatch):
    """La validacion previa no cubre todo lo que puede fallar al escribir. Si la
    segunda linea revienta, la primera no puede quedar: seria media
    devolucion, y un reintento duplicaria la mitad que si entro."""
    _con_conectores(org_a, bodega, conector, user_profile)
    antes = MovimientoDeMaterial.objects.count()
    real = inv._declarado_sin_recibir
    llamadas = []

    def falla_en_la_segunda(*a, **k):
        llamadas.append(1)
        if len(llamadas) == 2:
            raise RuntimeError("se cayo la base a mitad de camino")
        return real(*a, **k)

    monkeypatch.setattr(inv, "_declarado_sin_recibir", falla_en_la_segunda)
    with pytest.raises(RuntimeError):
        inv.recibir_devolucion(
            org=org_a, profile_origen=user_profile, ubicacion_destino=bodega,
            lineas=[{"material": conector, "cantidad": 5},
                    {"material": conector, "cantidad": 3}])
    assert MovimientoDeMaterial.objects.count() == antes
