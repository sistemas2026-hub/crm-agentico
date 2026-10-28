"""
================================================================================
 EL MATERIAL DEL DIA  --  28/10/2026
================================================================================
`campo/material_del_dia.py` (fase 1: solo propone) y su configuracion.
SPEC/objetivos/material-del-dia.md. Cada regla, con su prueba:

  K  el kit de la labor, de la bodega de la cuadrilla, al LIDER; si alcanza,
     cada una recibe lo suyo.
  M  el kit MENOS lo que el lider ya tiene en custodia.
  R  si no alcanza, lo libre se reparte por el trabajo publicado del dia,
     pesando la prioridad (alta 3, media 2, baja 1), sin pasarse de lo que
     cada una necesita; lo que falta se dice, y salir sin un equipo con serie
     es una alerta.
  A  avisos de configuracion: labor sin kit, cuadrilla sin bodega, sin lider.
  N  la propuesta NO mueve material.
  C  la configuracion: solo lo de esta empresa, todo o nada, solo quien gestiona.

    pytest campo/tests/test_material_del_dia.py
================================================================================
"""
import datetime as dt
from decimal import Decimal

import pytest

from campo import material_del_dia as M
from campo.cuadrillas import Cuadrilla, JornadaDeCuadrilla
from campo.inventario import UbicacionInventario
from campo.inventario_operacion import LineaDePlantilla, PlantillaDeKit
from campo.labores import Labor
from campo.models import (
    AsignacionTrabajo,
    EntregaDeKit,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import inventario as inv

pytestmark = pytest.mark.django_db

HOY = dt.date(2026, 10, 29)
RUTA = "/api/campo/material-del-dia/"


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="BOG-SOLEDAD")


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
def kit(org_a, conector, ont):
    k = PlantillaDeKit.objects.create(org=org_a, nombre="Kit de soporte técnico")
    LineaDePlantilla.objects.create(plantilla=k, material=conector, cantidad=10)
    LineaDePlantilla.objects.create(plantilla=k, material=ont, cantidad=1)
    labor, _ = Labor.objects.get_or_create(
        org=org_a, codigo="correctivo", defaults={"nombre": "Soporte en campo",
                                                  "de_fabrica": True})
    labor.plantilla_de_kit = k
    labor.save()
    return k


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="sop", nombre="Soporte",
                                 labor="correctivo")
    return WorkTypeVersion.objects.create(work_type=wt, version=1,
                                          estado=WorkTypeVersion.PUBLICADA,
                                          esquema={"campos": []})


@pytest.fixture
def otro(org_a, django_user_model):
    from common.models import Profile

    u = django_user_model.objects.create_user(email="lider2@test.com", password="x1234567")
    return Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)


def _cuadrilla(org, nombre, lider, bodega, labor="correctivo"):
    c = Cuadrilla.objects.create(org=org, nombre=nombre, lider=lider, bodega=bodega)
    return JornadaDeCuadrilla.objects.create(org=org, cuadrilla=c, fecha=HOY, labor=labor)


_numero = iter(range(700, 9999))


def _ordenes(org, version, de, *prioridades):
    for p in prioridades:
        o = OrdenTrabajo.objects.create(org=org, numero=next(_numero),
                                        tipo_trabajo_version=version,
                                        estado_operativo=OrdenTrabajo.ASIGNADA, prioridad=p)
        AsignacionTrabajo.objects.create(orden=o, profile=de, rol="tecnico", es_principal=True)


def _stock(org, bodega, conector, ont, conectores, series):
    if conectores:
        inv.registrar_entrada(org=org, material=conector, cantidad=conectores,
                              ubicacion_destino=bodega)
    for s in series:
        inv.registrar_entrada(org=org, material=ont, cantidad=1, ubicacion_destino=bodega,
                              serie=s)


def _lineas(p, cuadrilla) -> dict:
    fila = next(c for c in p["cuadrillas"] if c["cuadrilla"] == cuadrilla)
    return {linea["material"]: linea for linea in fila["lineas"]}


def _avisos(p, cuadrilla) -> list:
    return next(c for c in p["cuadrillas"] if c["cuadrilla"] == cuadrilla)["avisos"]


# ---------------------------------------------------------------------------
# K · si alcanza, cada una recibe su kit
# ---------------------------------------------------------------------------

def test_k_si_alcanza_cada_una_recibe_su_kit_al_lider(
        org_a, bodega, conector, ont, kit, admin_profile, otro):
    _stock(org_a, bodega, conector, ont, 100, ["S-1", "S-2"])
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, bodega)
    _cuadrilla(org_a, "Cuadrilla #2", otro, bodega)

    p = M.propuesta(org_a, HOY)

    for nombre in ("Cuadrilla #1", "Cuadrilla #2"):
        lineas = _lineas(p, nombre)
        assert (lineas["Conector UPC"]["asignado"], lineas["Conector UPC"]["falta"]) == ("10", "0")
        assert lineas["ONU WIFI"]["asignado"] == "1"
        assert _avisos(p, nombre) == []
    fila = next(c for c in p["cuadrillas"] if c["cuadrilla"] == "Cuadrilla #1")
    assert (fila["kit"], fila["bodega"]) == ("Kit de soporte técnico", "BOG-SOLEDAD")
    assert fila["lider"]
    assert p["cuentas"]["completas"] == 2


# ---------------------------------------------------------------------------
# M · el kit menos lo que ya tiene en mano
# ---------------------------------------------------------------------------

def test_m_carga_lo_que_le_falta_para_completar_el_kit(
        org_a, bodega, conector, ont, kit, admin_profile):
    _stock(org_a, bodega, conector, ont, 100, ["S-1"])
    inv.despachar(org=org_a, ubicacion_origen=bodega, profile_destino=admin_profile,
                  acta="AYER", lineas=[{"material": conector, "cantidad": 4}])
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, bodega)

    linea = _lineas(M.propuesta(org_a, HOY), "Cuadrilla #1")["Conector UPC"]

    assert (linea["en_mano"], linea["necesita"], linea["asignado"]) == ("4", "6", "6")


# ---------------------------------------------------------------------------
# R · si no alcanza
# ---------------------------------------------------------------------------

def test_r_lo_que_hay_se_reparte_por_el_trabajo_del_dia(
        org_a, bodega, conector, ont, kit, version, admin_profile, otro):
    _stock(org_a, bodega, conector, ont, 12, ["S-1", "S-2"])
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, bodega)
    _cuadrilla(org_a, "Cuadrilla #2", otro, bodega)
    _ordenes(org_a, version, admin_profile, "alta", "alta")      # peso 6
    _ordenes(org_a, version, otro, "baja")                       # peso 1
    #  Lo terminado hoy no pide material: no suma peso.
    _ordenes(org_a, version, otro, "alta")
    terminada = OrdenTrabajo.objects.filter(asignaciones__profile=otro,
                                            prioridad="alta").get()
    OrdenTrabajo.objects.filter(pk=terminada.pk).update(
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        completada_campo_en=dt.datetime(2026, 10, 29, 15, 0, tzinfo=dt.timezone.utc))

    p = M.propuesta(org_a, HOY)

    uno, dos = _lineas(p, "Cuadrilla #1"), _lineas(p, "Cuadrilla #2")
    assert (uno["Conector UPC"]["asignado"], dos["Conector UPC"]["asignado"]) == ("10", "2")
    assert dos["Conector UPC"]["falta"] == "8"
    assert "Faltan 8 unidades de Conector UPC." in _avisos(p, "Cuadrilla #2")
    resumen = next(b for b in p["bodegas"] if b["material"] == "Conector UPC")
    assert (resumen["disponible"], resumen["pedido"], resumen["falta"]) == ("12", "20", "8")


def test_r1_lo_reservado_no_se_reparte(org_a, bodega, conector, ont, kit, admin_profile):
    from campo.services.inventario_operacion import reservar

    _stock(org_a, bodega, conector, ont, 12, ["S-1"])
    reservar(org=org_a, ubicacion=bodega, material=conector, cantidad=8,
             motivo="instalación del jueves")
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, bodega)

    linea = _lineas(M.propuesta(org_a, HOY), "Cuadrilla #1")["Conector UPC"]

    assert (linea["asignado"], linea["falta"]) == ("4", "6")


def test_r2_salir_sin_un_equipo_con_serie_es_una_alerta(
        org_a, bodega, conector, ont, kit, version, admin_profile, otro):
    _stock(org_a, bodega, conector, ont, 100, ["S-1"])
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, bodega)
    _cuadrilla(org_a, "Cuadrilla #2", otro, bodega)
    _ordenes(org_a, version, otro, "alta")

    p = M.propuesta(org_a, HOY)

    assert _lineas(p, "Cuadrilla #2")["ONU WIFI"]["asignado"] == "1"
    assert ("Sale sin ONU WIFI: no puede hacer el trabajo que lo necesita."
            in _avisos(p, "Cuadrilla #1"))
    assert p["cuentas"]["con_faltantes"] == 1


def test_r3_el_reparto_puro():
    assert M.repartir_lo_que_hay([("a", 3, 1), ("b", 2, 5)], Decimal("10")) == {
        "a": Decimal("3"), "b": Decimal("2")}
    assert M.repartir_lo_que_hay([("a", 3, 1), ("b", 2, 5)], Decimal("0")) == {
        "a": Decimal("0"), "b": Decimal("0")}
    #  Lo libre puede ser negativo (se reservo de mas): nadie recibe.
    assert M.repartir_lo_que_hay([("a", 3, 1)], Decimal("-4")) == {"a": Decimal("0")}
    #  Sin trabajo publicado, recibe lo que sobra despues de los que tienen.
    assert M.repartir_lo_que_hay([("a", 5, 0), ("b", 5, 2)], Decimal("6")) == {
        "a": Decimal("1"), "b": Decimal("5")}
    #  Metros con decimales.
    assert M.repartir_lo_que_hay([("a", Decimal("2.5"), 1)], Decimal("2.5")) == {
        "a": Decimal("2.5")}


# ---------------------------------------------------------------------------
# A · avisos de configuracion
# ---------------------------------------------------------------------------

def test_a_sin_kit_sin_bodega_sin_lider(org_a, bodega, kit, admin_profile, otro):
    _cuadrilla(org_a, "Trabajos", admin_profile, bodega, labor="trabajos")
    _cuadrilla(org_a, "Sin bodega", otro, None)
    _cuadrilla(org_a, "Sin lider", None, bodega)

    p = M.propuesta(org_a, HOY)

    assert _avisos(p, "Trabajos") == ["Su labor no tiene kit: no carga material."]
    assert _avisos(p, "Sin bodega") == ["La cuadrilla no tiene bodega: no se sabe de dónde carga."]
    assert _avisos(p, "Sin lider") == ["No tiene líder con cuenta activa: no hay a quién cargarle."]
    assert p["cuentas"]["sin_carga"] == 3


# ---------------------------------------------------------------------------
# N · no mueve material
# ---------------------------------------------------------------------------

def test_n_la_propuesta_no_mueve_nada(org_a, bodega, conector, ont, kit, admin_profile):
    _stock(org_a, bodega, conector, ont, 3, [])
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, bodega)
    antes = (MovimientoDeMaterial.objects.count(), EntregaDeKit.objects.count())

    M.propuesta(org_a, HOY)

    assert (MovimientoDeMaterial.objects.count(), EntregaDeKit.objects.count()) == antes
    assert inv.existencia(bodega, conector) == Decimal("3")


# ---------------------------------------------------------------------------
# C · la configuracion
# ---------------------------------------------------------------------------

def test_c_se_lee_y_se_cambia_solo_lo_que_viene(
        org_a, bodega, kit, admin_profile, admin_client):
    j = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, None)
    Labor.objects.get_or_create(org=org_a, codigo="instalacion",
                                defaults={"nombre": "Instalación", "de_fabrica": True})

    r = admin_client.put(RUTA + "configuracion/", {
        "kits": {"instalacion": str(kit.id)},
        "bodegas": {str(j.cuadrilla_id): str(bodega.id)}}, format="json")

    assert r.status_code == 200, r.content
    d = r.json()
    kits = {lab["codigo"]: lab["kit"] for lab in d["labores"]}
    assert kits["instalacion"] == kits["correctivo"] == str(kit.id)   # correctivo, intacto
    assert {c["nombre"]: c["bodega"] for c in d["cuadrillas"]}["Cuadrilla #1"] == str(bodega.id)
    assert {b["nombre"] for b in d["bodegas"]} == {"BOG-SOLEDAD"}


def test_c2_lo_de_otra_empresa_o_que_no_es_bodega_se_rechaza_entero(
        org_a, org_b, bodega, kit, admin_profile, admin_client):
    j = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, None)
    ajeno = PlantillaDeKit.objects.create(org=org_b, nombre="Kit ajeno")
    custodia = inv.ubicacion_de_tecnico(admin_profile, org_a)

    r = admin_client.put(RUTA + "configuracion/", {
        "bodegas": {str(j.cuadrilla_id): str(bodega.id)},
        "kits": {"correctivo": str(ajeno.id)}}, format="json")
    assert r.status_code == 400
    r2 = admin_client.put(RUTA + "configuracion/", {
        "bodegas": {str(j.cuadrilla_id): str(custodia.id)}}, format="json")
    assert r2.status_code == 400

    j.cuadrilla.refresh_from_db()
    assert j.cuadrilla.bodega_id is None                      # todo o nada
    assert Labor.objects.get(org=org_a, codigo="correctivo").plantilla_de_kit_id == kit.id


def test_c3_solo_quien_gestiona_y_con_fecha(org_a, admin_client, user_client):
    assert user_client.get(RUTA, {"fecha": HOY.isoformat()}).status_code == 403
    assert user_client.get(RUTA + "configuracion/").status_code == 403
    assert admin_client.get(RUTA).status_code == 400
    assert admin_client.get(RUTA, {"fecha": HOY.isoformat()}).status_code == 200
