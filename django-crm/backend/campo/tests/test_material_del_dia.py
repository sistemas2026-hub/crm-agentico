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
    #  UN mensaje, primero, y no una linea por material (28/10/2026).
    assert _avisos(p, "Cuadrilla #2") == [
        "Le falta material para completar el kit (1 de 2 materiales): sale con lo que "
        "hay en bodega."]
    assert _avisos(p, "Cuadrilla #1") == []
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


def _d(**kw):
    return {k: Decimal(str(v)) for k, v in kw.items()}


def test_e_primero_una_entrega_a_cada_una_con_trabajo():
    """Pedido del usuario el 29/10/2026: «distribución equitativa en caso de
    escasez». Antes, con 15 conectores la de más trabajo se llevaba 10, la
    siguiente 5 y la de una orden salía sin ninguno."""
    pedidos = [("dos", 10, 12), ("tres", 6, 6), ("cuatro", 10, 1), ("cinco", 10, 0)]
    assert M.repartir_lo_que_hay(pedidos, Decimal("15")) == _d(dos=10, tres=4, cuatro=1, cinco=0)


def test_e2_el_drop_de_a_50_nunca_10_metros_sueltos():
    """La simulación del 29/10: 200 m entre cuatro que piden 150. Antes
    127 / 63 / 10 / 0; los 10 m no servían para ninguna acometida."""
    pedidos = [("dos", 150, 12), ("tres", 150, 6), ("cuatro", 150, 1), ("cinco", 150, 0)]
    assert M.repartir_lo_que_hay(pedidos, Decimal("200"), de_a=50) == _d(
        dos=100, tres=50, cuatro=50, cinco=0)


def test_e3_un_resto_menor_que_de_a_solo_sirve_para_completar():
    #  70 m: 50 a la de más peso y los 20 que le faltan a la otra para completar.
    assert M.repartir_lo_que_hay([("a", 150, 2), ("b", 20, 1)], Decimal("70"), de_a=50) == _d(
        a=50, b=20)
    #  30 m: no alcanza para una entrega de 50; completa a la que le faltan 20, y
    #  los otros 10 se quedan en la bodega.
    assert M.repartir_lo_que_hay([("a", 150, 2), ("b", 20, 1)], Decimal("30"), de_a=50) == _d(
        a=0, b=20)


def test_e4_si_no_alcanza_para_una_a_cada_una_van_las_de_mas_trabajo():
    #  Dos ONU para tres cuadrillas: a las dos de más peso, y en el orden dado
    #  si empatan.
    assert M.repartir_lo_que_hay([("a", 1, 1), ("b", 1, 6), ("c", 1, 6)], Decimal("2")) == _d(
        a=0, b=1, c=1)


def test_e5_despues_de_la_primera_entrega_manda_el_peso_sin_pasarse():
    #  12 de peso contra 1: la primera vuelta da 1 y 1, y los 8 que quedan van
    #  casi todos a la de 12, que no recibe más de los 10 que necesita.
    assert M.repartir_lo_que_hay([("a", 10, 12), ("b", 10, 1)], Decimal("10")) == _d(a=9, b=1)


def test_e5b_de_a_50_el_peso_cuenta_entregas_y_no_metros():
    #  250 m de a 50 = 5 entregas, peso 12 contra 5. La primera vuelta da una
    #  a cada una; las tres que quedan, por peso sobre ENTREGAS: 12/2, 12/3,
    #  12/4 le ganan a 5/2. Contadas en metros (12/151 contra 5/51) la quinta
    #  se iria a la de menos trabajo.
    assert M.repartir_lo_que_hay([("a", 1000, 12), ("b", 1000, 5)], Decimal("250"),
                                 de_a=50) == _d(a=200, b=50)


def test_e6_la_propuesta_reparte_cada_material_de_a_lo_suyo(
        org_a, bodega, conector, ont, kit, version, admin_profile, otro):
    """Por el camino real: el drop del kit, de a 50; los conectores, de a uno."""
    drop = MaterialCatalogo.objects.create(
        org=org_a, codigo="DROP", nombre="Cable drop", clase=MaterialCatalogo.BOBINA,
        unidad="m", se_entrega_de_a=Decimal("50"))
    LineaDePlantilla.objects.create(plantilla=kit, material=drop, cantidad=150)
    inv.registrar_entrada(org=org_a, material=drop, cantidad=120, ubicacion_destino=bodega)
    _stock(org_a, bodega, conector, ont, 12, ["S-1", "S-2"])
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, bodega)
    _cuadrilla(org_a, "Cuadrilla #2", otro, bodega)
    _ordenes(org_a, version, admin_profile, "alta", "alta")      # peso 6
    _ordenes(org_a, version, otro, "baja")                       # peso 1

    p = M.propuesta(org_a, HOY)

    uno, dos = _lineas(p, "Cuadrilla #1"), _lineas(p, "Cuadrilla #2")
    #  120 m: 50 a cada una y los 20 que sobran no completan a nadie.
    assert (uno["Cable drop"]["asignado"], dos["Cable drop"]["asignado"]) == ("50", "50")
    assert (uno["Conector UPC"]["asignado"], dos["Conector UPC"]["asignado"]) == ("10", "2")


# ---------------------------------------------------------------------------
# A · avisos de configuracion
# ---------------------------------------------------------------------------

def test_a_sin_kit_sin_bodega_sin_lider(org_a, bodega, kit, admin_profile, otro):
    #  Con dos bodegas y ninguna pista, el Supervisor no puede elegir.
    UbicacionInventario.objects.create(org=org_a, tipo=UbicacionInventario.BODEGA,
                                       nombre="BOF-SAB_GRANDE")
    #  Como en produccion: las labores de fabrica estan sembradas con su nombre.
    Labor.objects.get_or_create(org=org_a, codigo="trabajos",
                                defaults={"nombre": "Trabajos", "de_fabrica": True})
    _cuadrilla(org_a, "Trabajos", admin_profile, bodega, labor="trabajos")
    _cuadrilla(org_a, "Sin bodega", otro, None)
    _cuadrilla(org_a, "Sin lider", None, bodega)

    p = M.propuesta(org_a, HOY)

    assert _avisos(p, "Trabajos") == [
        "Ningún kit se parece a «Trabajos»: no carga material."]
    assert _avisos(p, "Sin bodega") == [
        "No sé de qué bodega carga: su zona no nombra ninguna y a su líder no le "
        "despacharon antes."]
    assert _avisos(p, "Sin lider") == ["No tiene líder con cuenta activa: no hay a quién cargarle."]
    assert p["cuentas"]["sin_carga"] == 3


# ---------------------------------------------------------------------------
# D · lo que elige el Supervisor cuando nadie eligio («la idea era que lo
#     hiciera el Supervisor», 28/10/2026)
# ---------------------------------------------------------------------------

class _Kit:
    def __init__(self, nombre):
        self.nombre = nombre


KITS = [_Kit("Kit de soporte técnico"), _Kit("Kit de instalaciones nuevas")]


def test_d_el_kit_por_el_nombre_de_la_labor():
    assert M.kit_que_elige("Soporte en campo", KITS)[0].nombre == "Kit de soporte técnico"
    assert M.kit_que_elige("Instalación", KITS)[0].nombre == "Kit de instalaciones nuevas"
    kit, motivo = M.kit_que_elige("Trabajos", KITS)
    assert kit is None and "no carga material" in motivo
    #  Dos igual de parecidos: no elige.
    kit, motivo = M.kit_que_elige("Soporte", KITS + [_Kit("Kit soporte nocturno")])
    assert kit is None and "más de un kit" in motivo


def test_d2_en_la_propuesta_elige_el_supervisor_y_dice_por_que(
        org_a, bodega, conector, ont, admin_profile):
    _stock(org_a, bodega, conector, ont, 50, ["S-1"])
    soporte = PlantillaDeKit.objects.create(org=org_a, nombre="Kit de soporte técnico")
    LineaDePlantilla.objects.create(plantilla=soporte, material=conector, cantidad=5)
    PlantillaDeKit.objects.create(org=org_a, nombre="Kit de instalaciones nuevas")
    Labor.objects.get_or_create(org=org_a, codigo="correctivo",
                                defaults={"nombre": "Soporte en campo", "de_fabrica": True})
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, None)

    fila = next(c for c in M.propuesta(org_a, HOY)["cuadrillas"])

    assert (fila["kit"], fila["bodega"]) == ("Kit de soporte técnico", "BOG-SOLEDAD")
    assert "se parece por el nombre" in fila["kit_por"]
    assert fila["bodega_por"] == "es la única bodega"
    assert _lineas({"cuadrillas": [fila]}, "Cuadrilla #1")["Conector UPC"]["asignado"] == "5"


def test_d3_lo_que_eligio_una_persona_manda(org_a, bodega, kit, admin_profile):
    otra = UbicacionInventario.objects.create(org=org_a, tipo=UbicacionInventario.BODEGA,
                                              nombre="BOF-SAB_GRANDE")
    PlantillaDeKit.objects.create(org=org_a, nombre="Kit de soporte nocturno")
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, otra)

    fila = next(c for c in M.propuesta(org_a, HOY)["cuadrillas"])

    assert (fila["kit"], fila["kit_por"]) == ("Kit de soporte técnico", M.POR_UNA_PERSONA)
    assert (fila["bodega"], fila["bodega_por"]) == ("BOF-SAB_GRANDE", M.POR_UNA_PERSONA)


def test_d4_la_bodega_que_nombra_su_zona_y_si_no_la_de_su_historial(
        org_a, bodega, conector, admin_profile):
    sab = UbicacionInventario.objects.create(org=org_a, tipo=UbicacionInventario.BODEGA,
                                             nombre="BOF-SAB_GRANDE")
    bodegas = [bodega, sab]

    assert M.bodega_que_elige(org_a, ["Soledad zona 1"], None, bodegas) == (
        bodega, "su zona la nombra")
    assert M.bodega_que_elige(org_a, ["SABANAGRANDE"], None, bodegas) == (
        sab, "su zona la nombra")
    #  Sin zona que la nombre: la de la que ya le despacharon a su lider.
    inv.registrar_entrada(org=org_a, material=conector, cantidad=5, ubicacion_destino=sab)
    inv.despachar(org=org_a, ubicacion_origen=sab, profile_destino=admin_profile, acta="A-1",
                  lineas=[{"material": conector, "cantidad": 2}])
    assert M.bodega_que_elige(org_a, ["Malambo"], admin_profile, bodegas) == (
        sab, "de ahí le despacharon antes a su líder")
    #  Una zona que nombra a dos: no elige.
    norte = UbicacionInventario.objects.create(org=org_a, tipo=UbicacionInventario.BODEGA,
                                               nombre="SOLEDAD-NORTE")
    eleccion, motivo = M.bodega_que_elige(org_a, ["Soledad zona 1"], None, bodegas + [norte])
    assert eleccion is None and "más de una bodega" in motivo


def test_d6_mandan_las_zonas_del_dia_sobre_las_habituales(
        org_a, bodega, conector, ont, kit, admin_profile):
    #  La captura del usuario: hoy sale a Sabanagrande, pero entre sus
    #  habituales esta Soledad. Sumadas nombraban a las dos bodegas.
    from campo.zonas import ZonaOperativa

    sab = UbicacionInventario.objects.create(org=org_a, tipo=UbicacionInventario.BODEGA,
                                             nombre="BOF-SAB_GRANDE")
    sabana = ZonaOperativa.objects.create(org=org_a, nombre="SABANAGRANDE")
    soledad = ZonaOperativa.objects.create(org=org_a, nombre="Soledad zona 1")
    j = _cuadrilla(org_a, "Cuadrilla #5", admin_profile, None)
    j.zonas.set([sabana])
    j.cuadrilla.zonas_habituales.set([sabana, soledad])

    fila = next(c for c in M.propuesta(org_a, HOY)["cuadrillas"])

    assert (fila["bodega"], fila["bodega_por"]) == ("BOF-SAB_GRANDE", "su zona la nombra")
    assert sab.nombre == fila["bodega"]


def test_d5_el_panel_muestra_lo_que_elegiria_el_supervisor(org_a, bodega, kit, admin_client):
    PlantillaDeKit.objects.create(org=org_a, nombre="Kit de instalaciones nuevas")
    Labor.objects.get_or_create(org=org_a, codigo="instalacion",
                                defaults={"nombre": "Instalación", "de_fabrica": True})

    d = admin_client.get(RUTA + "configuracion/").json()

    instalacion = next(lab for lab in d["labores"] if lab["codigo"] == "instalacion")
    assert instalacion["kit"] is None
    assert instalacion["elige_el_supervisor"] == "Kit de instalaciones nuevas"


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
