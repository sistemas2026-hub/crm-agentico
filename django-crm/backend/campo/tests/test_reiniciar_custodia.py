"""
================================================================================
 REINICIAR LA CUSTODIA  --  28/10/2026
================================================================================
`manage.py reiniciar_custodia`: deja en limpio el historial de material de UNA
cuenta usada para probar. Se reproduce el caso que lo pidio --un tecnico con el
cierre de jornada bloqueado por diferencias negativas y un equipo con serie sin
resolver-- y se afirma sobre el EFECTO:

  S  sin --aplicar no borra nada, y dice que haria.
  A  con --aplicar: su historial en cero, su cierre de jornada sin motivos, la
     bodega como antes de la prueba y cada equipo de vuelta en la bodega.
  N  no toca a nadie mas: otro tecnico, ni las entradas a bodega que registro
     esa misma cuenta.
  B  se niega, sin borrar nada, cuando borrar haria desaparecer material que
     existe o cambiaria la cuenta de otra persona.

    pytest campo/tests/test_reiniciar_custodia.py
================================================================================
"""
import io
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from campo.inventario import UbicacionDeActivo, UbicacionInventario
from campo.models import (
    AsignacionTrabajo,
    EntregaDeKit,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    TransferenciaDeMaterial,
    WorkType,
    WorkTypeVersion,
)
from campo.services import inventario as inv
from campo.services.cierre_jornada import motivos_para_no_cerrar
from campo.services.materiales import registrar_movimiento

pytestmark = pytest.mark.django_db


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central")


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

    u = django_user_model.objects.create_user(email="pedro@test.com", password="x1234567")
    return Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)


@pytest.fixture
def orden(org_a, user_profile):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalacion")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(org=org_a, numero=4832, tipo_trabajo_version=v,
                                    estado_operativo=OrdenTrabajo.ASIGNADA)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico",
                                     es_principal=True)
    return o


def _como_el_de_produccion(org, bodega, mario, conector, ont, orden):
    """Despacho, consumo en una orden, devolucion de MAS y una ONT sin volver:
    el cierre queda con una diferencia negativa y una serie pendiente."""
    inv.registrar_entrada(org=org, material=conector, cantidad=100, ubicacion_destino=bodega)
    for serie in ("S-1", "S-2"):
        inv.registrar_entrada(org=org, material=ont, cantidad=1, ubicacion_destino=bodega,
                              serie=serie)
    inv.despachar(org=org, ubicacion_origen=bodega, profile_destino=mario, acta="K-1",
                  lineas=[{"material": conector, "cantidad": 30},
                          {"material": ont, "serie": "S-1"},
                          {"material": ont, "serie": "S-2"}])
    registrar_movimiento(org=org, profile=mario, material=conector,
                         tipo=MovimientoDeMaterial.CONSUMO, cantidad=5,
                         idempotency_key="c-1", orden=orden)
    inv.recibir_devolucion(org=org, profile_origen=mario, ubicacion_destino=bodega,
                           lineas=[{"material": conector, "cantidad": 30},
                                   {"material": ont, "serie": "S-1"}])


def _correr(org, profile, *extra):
    salida = io.StringIO()
    call_command("reiniciar_custodia", "--org", str(org.id),
                 "--tecnico", profile.user.email, *extra, stdout=salida)
    return salida.getvalue()


def _de_su_custodia(org, mario):
    custodia = inv.ubicacion_de_tecnico(mario, org, crear=False)
    return MovimientoDeMaterial.objects.filter(org=org).filter(
        **({"ubicacion_destino": custodia} if custodia else {"profile": mario})).count()


@pytest.fixture
def escenario(org_a, bodega, user_profile, conector, ont, orden):
    _como_el_de_produccion(org_a, bodega, user_profile, conector, ont, orden)
    #  El punto de partida es el de la captura: no deja cerrar.
    assert motivos_para_no_cerrar(user_profile, org_a)
    return user_profile


# ---------------------------------------------------------------------------
# S · el simulacro no borra
# ---------------------------------------------------------------------------

def test_s_sin_aplicar_no_borra_nada_y_dice_que_haria(org_a, escenario, bodega, conector):
    antes = MovimientoDeMaterial.objects.filter(org=org_a).count()

    salida = _correr(org_a, escenario)

    assert "SIMULACRO" in salida
    #  El conector salio 30 y volvio 30: la bodega no cambia y no se lista. La
    #  ONT que nunca volvio SI: sin el despacho, el libro la deja en la bodega,
    #  y eso es lo que una persona tiene que confirmar que es verdad.
    assert "Conector UPC" not in salida.split("Cada bodega")[1].split("Equipos")[0]
    assert "Bodega Central · ONU WIFI: 1 -> 2" in salida
    assert "S-2 (ONU WIFI): vuelve a Bodega Central" in salida
    assert "#4832" in salida
    assert MovimientoDeMaterial.objects.filter(org=org_a).count() == antes
    assert EntregaDeKit.objects.filter(org=org_a).count() == 1
    assert motivos_para_no_cerrar(escenario, org_a)


# ---------------------------------------------------------------------------
# A · con --aplicar
# ---------------------------------------------------------------------------

def test_a_queda_en_cero_el_cierre_libre_y_la_bodega_como_antes(
        org_a, escenario, bodega, conector, ont):
    salida = _correr(org_a, escenario, "--aplicar")

    assert "Listo" in salida
    assert motivos_para_no_cerrar(escenario, org_a) == []
    assert EntregaDeKit.objects.filter(org=org_a, profile=escenario).count() == 0
    assert MovimientoDeMaterial.objects.filter(org=org_a, profile=escenario).count() == 0
    assert _de_su_custodia(org_a, escenario) == 0
    #  La bodega, como antes de la prueba: solo sus entradas.
    assert inv.existencia(bodega, conector) == Decimal("100")
    assert inv.existencia(bodega, ont) == Decimal("2")
    #  Cada equipo, de vuelta en la bodega, y el indice igual al libro.
    for serie in ("S-1", "S-2"):
        activo = inv.activo_de(org_a, ont, serie, crear=False)
        ua = UbicacionDeActivo.objects.get(activo=activo)
        ubicacion, movimiento = inv.posicion_recalculada(activo)
        assert ua.ubicacion_id == bodega.id == ubicacion.id
        assert ua.movimiento_id == movimiento.id
        assert movimiento.tipo == MovimientoDeMaterial.ENTRADA


def test_a2_dos_veces_no_rompe_nada(org_a, escenario):
    _correr(org_a, escenario, "--aplicar")

    assert "no hay nada que borrar" in _correr(org_a, escenario, "--aplicar")


# ---------------------------------------------------------------------------
# N · no toca a nadie mas
# ---------------------------------------------------------------------------

def test_n_otro_tecnico_queda_igual(org_a, escenario, bodega, conector, otro):
    inv.despachar(org=org_a, ubicacion_origen=bodega, profile_destino=otro, acta="K-P",
                  lineas=[{"material": conector, "cantidad": 7}])
    custodia_otro = inv.ubicacion_de_tecnico(otro, org_a, crear=False)

    _correr(org_a, escenario, "--aplicar")

    assert inv.existencia(custodia_otro, conector) == Decimal("7")
    assert EntregaDeKit.objects.filter(org=org_a, profile=otro).count() == 1
    assert inv.existencia(bodega, conector) == Decimal("93")


def test_n2_las_entradas_a_bodega_que_registro_esa_cuenta_no_se_tocan(
        org_a, escenario, bodega, conector):
    #  `inventario_views` guarda en una entrada la cuenta de quien la registra.
    inv.registrar_entrada(org=org_a, material=conector, cantidad=50,
                          ubicacion_destino=bodega, profile=escenario)

    salida = _correr(org_a, escenario, "--aplicar")

    assert "NO se tocan" in salida
    assert MovimientoDeMaterial.objects.filter(
        org=org_a, profile=escenario, tipo=MovimientoDeMaterial.ENTRADA).count() == 1
    assert inv.existencia(bodega, conector) == Decimal("150")


# ---------------------------------------------------------------------------
# B · se niega sin borrar nada
# ---------------------------------------------------------------------------

def test_b_material_que_entro_directo_a_su_custodia(org_a, escenario, bodega, conector):
    custodia = inv.ubicacion_de_tecnico(escenario, org_a, crear=False)
    inv.registrar_entrada(org=org_a, material=conector, cantidad=4,
                          ubicacion_destino=custodia)
    antes = MovimientoDeMaterial.objects.filter(org=org_a).count()

    with pytest.raises(CommandError):
        _correr(org_a, escenario, "--aplicar")

    assert MovimientoDeMaterial.objects.filter(org=org_a).count() == antes


def test_b2_una_transferencia_con_otra_persona(org_a, escenario, conector, otro):
    TransferenciaDeMaterial.objects.create(org=org_a, material=conector, entrega=escenario,
                                           recibe=otro, cantidad=1)
    antes = MovimientoDeMaterial.objects.filter(org=org_a).count()

    with pytest.raises(CommandError):
        _correr(org_a, escenario, "--aplicar")

    assert MovimientoDeMaterial.objects.filter(org=org_a).count() == antes


def test_b4_una_bodega_que_quedaria_en_negativo(org_a, bodega, user_profile, conector, otro):
    #  Salio de OTRA bodega, volvio a esta, y esta ya lo despacho a otro:
    #  borrar la devolucion la dejaria en -10.
    norte = UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Norte")
    inv.registrar_entrada(org=org_a, material=conector, cantidad=10, ubicacion_destino=norte)
    inv.despachar(org=org_a, ubicacion_origen=norte, profile_destino=user_profile,
                  acta="K-N", lineas=[{"material": conector, "cantidad": 10}])
    inv.recibir_devolucion(org=org_a, profile_origen=user_profile, ubicacion_destino=bodega,
                           lineas=[{"material": conector, "cantidad": 10}])
    inv.despachar(org=org_a, ubicacion_origen=bodega, profile_destino=otro, acta="K-O",
                  lineas=[{"material": conector, "cantidad": 10}])
    antes = MovimientoDeMaterial.objects.filter(org=org_a).count()

    with pytest.raises(CommandError):
        _correr(org_a, user_profile, "--aplicar")

    assert MovimientoDeMaterial.objects.filter(org=org_a).count() == antes


def test_b3_cuenta_u_organizacion_que_no_existen(org_a, org_b, escenario):
    with pytest.raises(CommandError):
        call_command("reiniciar_custodia", "--org", str(org_a.id),
                     "--tecnico", "nadie@test.com", stdout=io.StringIO())
    #  La cuenta existe, pero en OTRA empresa.
    with pytest.raises(CommandError):
        call_command("reiniciar_custodia", "--org", str(org_b.id),
                     "--tecnico", escenario.user.email, stdout=io.StringIO())
