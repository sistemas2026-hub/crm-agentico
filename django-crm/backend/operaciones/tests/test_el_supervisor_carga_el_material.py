"""
================================================================================
 EL SUPERVISOR CARGA EL MATERIAL DEL DIA  --  28/10/2026
================================================================================
`operaciones/carga_del_material.py`, fase 3 de SPEC/objetivos/material-del-dia.md.

  P  las puertas: sin la tarea delegada o sin el nivel, la sombra no escribe.
  C  carga al LIDER lo asignado, con `despachar` (acta, custodia, bodega); los
     equipos con serie quedan RESERVADOS en su bodega, no despachados.
  U  una sola vez por dia y cuadrilla, tambien cuando solo habia equipos.
  F  si la bodega no alcanza, carga lo que hay.
  V  la ventana: no antes de dos horas antes de abrir.
  K  corre dentro del ciclo, despues de publicar.
  R  el reporte de entregas dice que la cargo el Supervisor, y la propuesta,
     que ya se cargo.

    pytest operaciones/tests/test_el_supervisor_carga_el_material.py
================================================================================
"""
import datetime as dt
import zoneinfo
from decimal import Decimal

import pytest

from campo import material_del_dia as M
from campo.cuadrillas import ConfiguracionDeReparto, Cuadrilla, JornadaDeCuadrilla
from campo.inventario import UbicacionInventario
from campo.inventario_operacion import (
    LineaDePlantilla,
    PlantillaDeKit,
    ReservaDeMaterial,
)
from campo.labores import Labor
from campo.models import EntregaDeKit, MaterialCatalogo
from campo.services import inventario as inv
from campo.services import inventario_operacion as op
from operaciones import carga_del_material as CM
from operaciones import tareas_delegadas as td

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")
MARTES = dt.date(2026, 10, 27)


def _a_las(hora, minuto=0):
    return dt.datetime.combine(MARTES, dt.time(hora, minuto), tzinfo=BOGOTA)


@pytest.fixture
def empresa(org_a):
    """Bogota; las cuadrillas trabajan de lunes a viernes, de 07:00 a 17:00."""
    from business_hours.models import BusinessCalendar

    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    cal = BusinessCalendar.objects.create(org=org_a, name="Cuadrillas",
                                          timezone="America/Bogota")
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        setattr(cal, f"{d}_open", dt.time(7, 0))
        setattr(cal, f"{d}_close", dt.time(17, 0))
    cal.save()
    ConfiguracionDeReparto.objects.update_or_create(
        org=org_a, defaults={"calendario_de_cuadrillas": cal})
    return org_a


@pytest.fixture
def bodega(empresa):
    return UbicacionInventario.objects.create(
        org=empresa, tipo=UbicacionInventario.BODEGA, nombre="BOG-SOLEDAD")


@pytest.fixture
def conector(empresa):
    return MaterialCatalogo.objects.create(
        org=empresa, codigo="CON-UPC", nombre="Conector UPC",
        clase=MaterialCatalogo.CONSUMIBLE, unidad="unidades")


@pytest.fixture
def ont(empresa):
    return MaterialCatalogo.objects.create(
        org=empresa, codigo="ONU-WIFI", nombre="ONU WIFI",
        clase=MaterialCatalogo.SERIALIZADO, unidad="unidades")


def _kit(org, *lineas):
    """La labor de soporte con su kit, como en Rapilink: lo elige el Supervisor
    por el nombre."""
    k = PlantillaDeKit.objects.create(org=org, nombre="Kit de soporte técnico")
    for material, cantidad in lineas:
        LineaDePlantilla.objects.create(plantilla=k, material=material, cantidad=cantidad)
    Labor.objects.get_or_create(org=org, codigo="correctivo",
                                defaults={"nombre": "Soporte en campo", "de_fabrica": True})
    return k


@pytest.fixture
def jornada(empresa, bodega, admin_profile):
    c = Cuadrilla.objects.create(org=empresa, nombre="Cuadrilla #1", lider=admin_profile)
    return JornadaDeCuadrilla.objects.create(org=empresa, cuadrilla=c, fecha=MARTES,
                                             labor="correctivo")


@pytest.fixture
def abierto(empresa, admin_profile, monkeypatch):
    """Las puertas abiertas, por el camino real salvo el interruptor del motor."""
    from operaciones import autonomia

    td.delegar(empresa, td.CARGAR_EL_MATERIAL, actor=admin_profile,
               pedido_textual="cargale el material a las cuadrillas")
    autonomia.cambiar(empresa, 3, actor=admin_profile, motivo="cargar material",
                      criterios="material del dia")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))
    return empresa


def _stock(org, bodega, conector, ont, conectores, series=()):
    if conectores:
        inv.registrar_entrada(org=org, material=conector, cantidad=conectores,
                              ubicacion_destino=bodega)
    for s in series:
        inv.registrar_entrada(org=org, material=ont, cantidad=1, ubicacion_destino=bodega,
                              serie=s)


def _custodia(org, profile, material):
    c = inv.ubicacion_de_tecnico(profile, org, crear=False)
    return inv.existencia(c, material) if c else Decimal("0")


# ---------------------------------------------------------------------------
# P · las puertas
# ---------------------------------------------------------------------------

def test_p_sin_la_tarea_queda_en_sombra_y_no_escribe(
        empresa, bodega, conector, ont, jornada, admin_profile):
    _kit(empresa, (conector, 10), (ont, 1))
    _stock(empresa, bodega, conector, ont, 50, ["S-1"])

    r = CM.cargar_el_material(empresa, _a_las(6))["material_del_dia"]

    assert (r["modo"], r["cargaria"], r["cargadas"]) == (CM.SOMBRA, 1, 0)
    assert EntregaDeKit.objects.filter(org=empresa).count() == 0
    assert ReservaDeMaterial.objects.filter(org=empresa).count() == 0


def test_p2_sin_el_nivel_tampoco(empresa, bodega, conector, ont, jornada, admin_profile,
                                 monkeypatch):
    from operaciones import autonomia

    _kit(empresa, (conector, 10))
    _stock(empresa, bodega, conector, ont, 50)
    td.delegar(empresa, td.CARGAR_EL_MATERIAL, actor=admin_profile, pedido_textual="x")
    autonomia.cambiar(empresa, 2, actor=admin_profile, motivo="x", criterios="x")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))

    r = CM.cargar_el_material(empresa, _a_las(6))["material_del_dia"]

    assert r["modo"] == CM.SOMBRA
    assert EntregaDeKit.objects.filter(org=empresa).count() == 0


# ---------------------------------------------------------------------------
# C · carga al lider; los equipos con serie, reservados
# ---------------------------------------------------------------------------

def test_c_carga_al_lider_y_reserva_los_equipos(
        abierto, bodega, conector, ont, jornada, admin_profile):
    _kit(abierto, (conector, 10), (ont, 1))
    _stock(abierto, bodega, conector, ont, 50, ["S-1", "S-2"])

    r = CM.cargar_el_material(abierto, _a_las(6))["material_del_dia"]

    assert (r["modo"], r["cargadas"], r["reservas"]) == (CM.PUBLICO, 1, 1)
    acta = M.acta_de(MARTES, jornada.id)
    entrega = EntregaDeKit.objects.get(org=abierto, acta=acta)
    assert entrega.profile_id == admin_profile.id and entrega.despachado_por_id is None
    assert [(i.material_id, i.cantidad) for i in entrega.items.all()] == [
        (conector.id, Decimal("10"))]
    assert _custodia(abierto, admin_profile, conector) == Decimal("10")
    assert inv.existencia(bodega, conector) == Decimal("40")
    #  La ONT no salio de la bodega: quedo reservada a nombre del acta.
    assert _custodia(abierto, admin_profile, ont) == Decimal("0")
    reserva = ReservaDeMaterial.objects.get(org=abierto, material=ont)
    assert reserva.cantidad == Decimal("1") and reserva.motivo.startswith(acta)
    assert op.libre(bodega, ont) == Decimal("1")


# ---------------------------------------------------------------------------
# U · una sola vez
# ---------------------------------------------------------------------------

def test_u_la_vuelta_siguiente_no_carga_otra_vez(abierto, bodega, conector, ont, jornada):
    _kit(abierto, (conector, 10), (ont, 1))
    _stock(abierto, bodega, conector, ont, 50, ["S-1", "S-2"])
    CM.cargar_el_material(abierto, _a_las(6))

    r = CM.cargar_el_material(abierto, _a_las(7))["material_del_dia"]

    assert (r["cargadas"], r["ya_cargadas"]) == (0, 1)
    assert EntregaDeKit.objects.filter(org=abierto).count() == 1
    assert ReservaDeMaterial.objects.filter(org=abierto).count() == 1


def test_u2_cuando_solo_habia_equipos_tampoco_repite(abierto, bodega, conector, ont,
                                                     jornada):
    _kit(abierto, (ont, 1))
    _stock(abierto, bodega, conector, ont, 0, ["S-1", "S-2"])
    CM.cargar_el_material(abierto, _a_las(6))

    r = CM.cargar_el_material(abierto, _a_las(7))["material_del_dia"]

    assert r["ya_cargadas"] == 1
    assert EntregaDeKit.objects.filter(org=abierto).count() == 0
    assert ReservaDeMaterial.objects.filter(org=abierto).count() == 1


# ---------------------------------------------------------------------------
# F · si no alcanza, lo que hay
# ---------------------------------------------------------------------------

def test_f_si_la_bodega_no_alcanza_carga_lo_que_hay(
        abierto, bodega, conector, ont, jornada, admin_profile):
    _kit(abierto, (conector, 10))
    _stock(abierto, bodega, conector, ont, 4)

    r = CM.cargar_el_material(abierto, _a_las(6))["material_del_dia"]

    assert (r["cargadas"], r["con_faltantes"]) == (1, 1)
    assert _custodia(abierto, admin_profile, conector) == Decimal("4")
    assert inv.existencia(bodega, conector) == Decimal("0")


# ---------------------------------------------------------------------------
# V · la ventana
# ---------------------------------------------------------------------------

def test_v_antes_de_la_ventana_no_corre(abierto, bodega, conector, ont, jornada):
    _kit(abierto, (conector, 10))
    _stock(abierto, bodega, conector, ont, 50)

    r = CM.cargar_el_material(abierto, _a_las(4, 59))["material_del_dia"]

    assert (r["modo"], r["cargadas"]) == (CM.NO_CORRIO, 0)
    assert EntregaDeKit.objects.filter(org=abierto).count() == 0


# ---------------------------------------------------------------------------
# K · dentro del ciclo
# ---------------------------------------------------------------------------

def test_k_corre_dentro_del_ciclo_despues_de_publicar(
        abierto, bodega, conector, ont, jornada, admin_profile):
    from operaciones import supervisor as sup

    _kit(abierto, (conector, 10))
    _stock(abierto, bodega, conector, ont, 50)

    resumen = sup.correr_ciclo(abierto, _a_las(6))

    assert "carga del material del dia" not in [
        f["fase"] for f in resumen.get("fases_que_fallaron", [])]
    assert resumen["material_del_dia"]["cargadas"] == 1
    assert _custodia(abierto, admin_profile, conector) == Decimal("10")


# ---------------------------------------------------------------------------
# R · lo que se ve despues
# ---------------------------------------------------------------------------

def test_r_el_reporte_y_la_propuesta_dicen_que_ya_se_cargo(
        abierto, bodega, conector, ont, jornada):
    _kit(abierto, (conector, 10))
    _stock(abierto, bodega, conector, ont, 50)
    CM.cargar_el_material(abierto, _a_las(6))

    (entrega,) = op.entregas_a_tecnicos(abierto)
    assert (entrega["despachado_por"], entrega["bodega"]) == ("el Supervisor", "BOG-SOLEDAD")
    fila = M.propuesta(abierto, MARTES)["cuadrillas"][0]
    #  Lo que va a la pantalla no lleva los objetos internos de la carga.
    assert not [k for k in fila if k.startswith("_")]
    assert not [k for linea in fila["lineas"] for k in linea if k.startswith("_")]
    assert fila["acta"] == M.acta_de(MARTES, jornada.id)
    assert fila["cargado_en"] is not None
    #  Ya lo tiene en mano: no hay nada mas que cargarle.
    assert fila["lineas"][0]["necesita"] == "0"
