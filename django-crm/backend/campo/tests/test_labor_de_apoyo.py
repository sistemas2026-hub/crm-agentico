"""
================================================================================
 LA LABOR DE APOYO  --  30/10/2026
================================================================================
SPEC/objetivos/labor-de-apoyo.md. El usuario: «en caso de que no haya tanto
ticket de soporte y haya instalaciones, ¿cómo hacer para que el Supervisor
pueda programar al mismo técnico soporte e instalaciones?».

  J  el Supervisor la elige al armar: con el cupo que la labor principal deja
     libre, la labor que mas casos tiene SIN CUBRIR en sus zonas; nunca le
     gana a la principal de otra; no la toca en una jornada de una persona; y
     se escribe con su auditoria.
  R  el reparto, en dos pasadas: primero las principales de todas; lo que
     quedo sin cuadrilla o sin lugar va al apoyo de esa zona con cupo.
  K  el kit del dia suma el de la labor de apoyo, y el material repetido una
     vez.

    pytest campo/tests/test_labor_de_apoyo.py
================================================================================
"""
import datetime as dt

import pytest

from campo import jornada_automatica as ja
from campo import material_del_dia as M
from campo.cuadrillas import Cuadrilla, JornadaDeCuadrilla
from campo.inventario import UbicacionInventario
from campo.inventario_operacion import LineaDePlantilla, PlantillaDeKit
from campo.labores import Labor
from campo.models import MaterialCatalogo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.reparto import proponer
from campo.zonas import AliasDeZona, ZonaOperativa
from common.models import Profile, User

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)
MARTES = dt.date(2026, 10, 6)
COR, INS = "correctivo", "instalacion"


@pytest.fixture
def norte(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="MARTHA GISELA")
    return z


@pytest.fixture
def sur(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Sur")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="EL CARMEN")
    return z


def _cuenta(org, email):
    u = User.objects.create_user(email=email, password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org, role="USER", is_active=True)


def _cuadrilla(org, nombre, zonas, *, tope=8, labor=COR, lider=None):
    c = Cuadrilla.objects.create(org=org, nombre=nombre, labor_habitual=labor,
                                 tope_diario=tope,
                                 lider=lider or _cuenta(org, f"{nombre.lower().replace(' ', '')}@t.co"))
    c.zonas_habituales.set(zonas)
    return c


def _de(planes, nombre):
    return next(p for p in planes if p.cuadrilla.nombre == nombre)


# ---------------------------------------------------------------------------
# J · el Supervisor la elige al armar
# ---------------------------------------------------------------------------

def test_j_con_cupo_libre_toma_de_apoyo_lo_que_quedo_sin_cubrir(org_a, norte):
    """Pocos de soporte, varias instalaciones: sale de instalacion (la que mas
    tiene) y con el cupo que le sobra apoya soporte."""
    _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=8)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(norte.id): {COR: 3, INS: 4}})

    p = _de(planes, "Cuadrilla 1")
    assert (p.labor, p.labor_de_apoyo) == (INS, COR)


def test_j2_el_apoyo_solo_toma_lo_que_la_principal_de_otra_no_cubre(org_a, norte):
    """La #1 cubre 5 de 6 de soporte; la #2 sale de instalacion (2) y apoya
    con el UNO de soporte que quedo. La #1, sin cupo, sin apoyo."""
    _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=5)
    _cuadrilla(org_a, "Cuadrilla 2", [norte], tope=5, labor=INS)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(norte.id): {COR: 6, INS: 2}})

    assert (_de(planes, "Cuadrilla 1").labor, _de(planes, "Cuadrilla 1").labor_de_apoyo) == (COR, "")
    assert (_de(planes, "Cuadrilla 2").labor, _de(planes, "Cuadrilla 2").labor_de_apoyo) == (INS, COR)


def test_j6_lo_que_ya_cubre_la_principal_de_otra_no_se_toma_de_apoyo(org_a, norte):
    """El soporte lo cubre entero la #1: la #2, con cupo libre, no se lleva
    apoyo de soporte -- le quitaria casos a la #1."""
    _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=5)
    _cuadrilla(org_a, "Cuadrilla 2", [norte], tope=5, labor=INS)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(norte.id): {COR: 4, INS: 2}})

    assert _de(planes, "Cuadrilla 2").labor_de_apoyo == ""


def test_j7_sin_cupo_libre_no_hay_apoyo_aunque_sobren_casos(org_a, norte):
    """Su labor le llena el tope: las instalaciones esperan, no se suman."""
    _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=3)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(norte.id): {COR: 4, INS: 2}})

    p = _de(planes, "Cuadrilla 1")
    assert (p.labor, p.labor_de_apoyo) == (COR, "")


def test_j3_sin_casos_de_otra_labor_en_SUS_zonas_no_hay_apoyo(org_a, norte, sur):
    _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=8)

    planes = ja.planear_el_dia(org_a, MARTES, demanda={
        str(norte.id): {COR: 2}, str(sur.id): {INS: 5}})

    assert _de(planes, "Cuadrilla 1").labor_de_apoyo == ""


def test_j4_la_jornada_de_una_persona_no_se_toca(org_a, norte):
    c = _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=8)
    j = JornadaDeCuadrilla.objects.create(org=org_a, cuadrilla=c, fecha=MARTES,
                                          labor=COR, armada_por=JornadaDeCuadrilla.PERSONA)
    j.zonas.set([norte])

    demanda = {str(norte.id): {COR: 1, INS: 5}}
    #  Dos guardas: el plan ni la toca, y al escribir solo se reajusta una
    #  automatica. Cada una con su prueba.
    plan = _de(ja.planear_el_dia(org_a, MARTES, demanda=demanda), "Cuadrilla 1")
    assert (plan.accion, plan.motivo) == (ja.DEJAR, ja.ARMADA_POR_UNA_PERSONA)
    r = ja.asegurar_jornadas(org_a, MARTES, demanda=demanda)

    j.refresh_from_db()
    assert j.labor_de_apoyo == "", "una persona la armo: ni la labor ni el apoyo se tocan"
    assert "Cuadrilla 1" in r["ya_estaban"]


def test_j5_se_escribe_con_su_auditoria_y_se_quita_si_ya_no_hace_falta(org_a, norte):
    from common.models import Activity

    c = _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=8)

    r = ja.asegurar_jornadas(org_a, MARTES, demanda={str(norte.id): {COR: 2, INS: 3}})
    j = JornadaDeCuadrilla.objects.get(cuadrilla=c, fecha=MARTES)
    assert (j.labor, j.labor_de_apoyo) == (INS, COR)
    assert r["apoyos"] == {"Cuadrilla 1": COR}
    fila = Activity.objects.filter(org=org_a, entity_id=j.id).latest("created_at")
    assert "apoyo: correctivo" in fila.description

    #  Mas tarde, sin ordenes todavia: lo de soporte ya no esta en Despacho.
    ja.asegurar_jornadas(org_a, MARTES, demanda={str(norte.id): {INS: 3}})
    j.refresh_from_db()
    assert (j.labor, j.labor_de_apoyo) == (INS, "")


# ---------------------------------------------------------------------------
# R · el reparto, en dos pasadas
# ---------------------------------------------------------------------------

def _version(org, codigo, labor):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo, labor=labor)
    return WorkTypeVersion.objects.create(work_type=wt, version=1,
                                          estado=WorkTypeVersion.PUBLICADA,
                                          esquema={"campos": []})


def _orden(org, version, numero, localidad="MARTHA GISELA"):
    return OrdenTrabajo.objects.create(org=org, numero=numero, tipo_trabajo_version=version,
                                       estado_operativo=OrdenTrabajo.ASIGNADA, zona=localidad)


def _jornada(org, nombre, zonas, *, labor, apoyo="", tope=8):
    c = Cuadrilla.objects.create(org=org, nombre=nombre, tope_diario=tope)
    j = JornadaDeCuadrilla.objects.create(org=org, cuadrilla=c, fecha=LUNES,
                                          labor=labor, labor_de_apoyo=apoyo)
    j.zonas.set(zonas)
    return j


def _primero(numeros):
    """Un plazo que pone primero los numeros dados (mas urgentes)."""
    def _plazo(orden, ahora=None, **kw):
        if orden.numero in numeros:
            return {"minutos_restantes": None, "minutos_atraso": 1000 - orden.numero}
        return {"minutos_restantes": 600, "minutos_atraso": None}
    return _plazo


def _de_la(propuesta, nombre):
    for a in propuesta["asignaciones"]:
        if a["cuadrilla"].nombre == nombre:
            return [o.numero for o in a["ordenes"]]
    return None


def test_r_primero_su_labor_y_con_lo_que_sobra_el_apoyo(org_a, norte):
    """Las instalaciones son MAS urgentes y aun asi no le quitan lugar al
    soporte: van en la segunda pasada, y la que no cabe queda nombrada."""
    sop, ins = _version(org_a, "sop", COR), _version(org_a, "ins", INS)
    _jornada(org_a, "Cuadrilla 1", [norte], labor=COR, apoyo=INS, tope=3)
    for n in (1, 2):
        _orden(org_a, ins, n)
    for n in (3, 4):
        _orden(org_a, sop, n)

    p = proponer(org_a, LUNES, plazo_de=_primero({1, 2}))

    assert _de_la(p, "Cuadrilla 1") == [3, 4, 1]
    assert [o.numero for o in p["sin_cuadrilla"]] == [2]


def test_r2_la_principal_de_otra_va_antes_que_el_apoyo(org_a, norte):
    """La de instalacion se lleva la primera; la de soporte con apoyo, la que
    a la otra no le cupo."""
    ins = _version(org_a, "ins", INS)
    _jornada(org_a, "Cuadrilla 1", [norte], labor=COR, apoyo=INS)
    _jornada(org_a, "Cuadrilla 2", [norte], labor=INS, tope=1)
    for n in (1, 2):
        _orden(org_a, ins, n)

    p = proponer(org_a, LUNES, plazo_de=_primero({1, 2}))

    assert _de_la(p, "Cuadrilla 2") == [1]
    assert _de_la(p, "Cuadrilla 1") == [2]


def test_r3_el_apoyo_no_sale_de_sus_zonas(org_a, norte, sur):
    ins = _version(org_a, "ins", INS)
    _jornada(org_a, "Cuadrilla 1", [norte], labor=COR, apoyo=INS)
    _orden(org_a, ins, 1, localidad="EL CARMEN")

    p = proponer(org_a, LUNES, plazo_de=_primero(set()))

    assert _de_la(p, "Cuadrilla 1") == []
    assert [o.numero for o in p["sin_cuadrilla"]] == [1]


# ---------------------------------------------------------------------------
# K · el kit del dia suma el de la labor de apoyo
# ---------------------------------------------------------------------------

def test_k_el_kit_suma_el_de_apoyo_y_lo_repetido_va_una_vez(org_a, admin_profile):
    bodega = UbicacionInventario.objects.create(org=org_a, tipo=UbicacionInventario.BODEGA,
                                                nombre="BOG-SOLEDAD")
    cable = MaterialCatalogo.objects.create(org=org_a, codigo="DROP", nombre="CABLE DROP",
                                            clase=MaterialCatalogo.CONSUMIBLE, unidad="m")
    ont = MaterialCatalogo.objects.create(org=org_a, codigo="ONU", nombre="ONU WIFI",
                                          clase=MaterialCatalogo.SERIALIZADO, unidad="unidades")
    soporte = PlantillaDeKit.objects.create(org=org_a, nombre="Kit de soporte")
    LineaDePlantilla.objects.create(plantilla=soporte, material=cable, cantidad=50)
    instalacion = PlantillaDeKit.objects.create(org=org_a, nombre="Kit de instalacion")
    LineaDePlantilla.objects.create(plantilla=instalacion, material=cable, cantidad=150)
    LineaDePlantilla.objects.create(plantilla=instalacion, material=ont, cantidad=2)
    for codigo, kit in ((COR, soporte), (INS, instalacion)):
        lab, _ = Labor.objects.get_or_create(org=org_a, codigo=codigo,
                                             defaults={"nombre": codigo, "de_fabrica": True})
        lab.plantilla_de_kit = kit
        lab.save()
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1", lider=admin_profile,
                                 bodega=bodega)
    JornadaDeCuadrilla.objects.create(org=org_a, cuadrilla=c, fecha=LUNES,
                                      labor=COR, labor_de_apoyo=INS)

    fila = M.calcular(org_a, LUNES)["cuadrillas"][0]

    assert fila["kit"] == "Kit de soporte" and fila["kit_apoyo"] == "Kit de instalacion"
    kit = {ln["material"]: ln["kit"] for ln in fila["lineas"]}
    assert kit == {"CABLE DROP": 200, "ONU WIFI": 2}, "el cable de los dos kits, sumado una vez"


def test_k2_sin_apoyo_el_kit_es_el_de_siempre(org_a, admin_profile):
    bodega = UbicacionInventario.objects.create(org=org_a, tipo=UbicacionInventario.BODEGA,
                                                nombre="BOG-SOLEDAD")
    cable = MaterialCatalogo.objects.create(org=org_a, codigo="DROP", nombre="CABLE DROP",
                                            clase=MaterialCatalogo.CONSUMIBLE, unidad="m")
    soporte = PlantillaDeKit.objects.create(org=org_a, nombre="Kit de soporte")
    LineaDePlantilla.objects.create(plantilla=soporte, material=cable, cantidad=50)
    lab, _ = Labor.objects.get_or_create(org=org_a, codigo=COR,
                                         defaults={"nombre": COR, "de_fabrica": True})
    lab.plantilla_de_kit = soporte
    lab.save()
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1", lider=admin_profile,
                                 bodega=bodega)
    JornadaDeCuadrilla.objects.create(org=org_a, cuadrilla=c, fecha=LUNES, labor=COR)

    fila = M.calcular(org_a, LUNES)["cuadrillas"][0]

    assert fila["kit_apoyo"] == ""
    assert {ln["material"]: ln["kit"] for ln in fila["lineas"]} == {"CABLE DROP": 50}


# ---------------------------------------------------------------------------
# V · lo que se ve, y lo que pone una persona
# ---------------------------------------------------------------------------

JORNADA = "/api/campo/cuadrillas/jornada/"


def test_v_programacion_y_la_app_dicen_el_apoyo(org_a, norte, user_client, user_profile):
    from campo import dia_publicado as D
    from campo.cuadrillas import IntegranteDeJornada, PersonaDeCampo

    j = _jornada(org_a, "Cuadrilla 1", [norte], labor=COR, apoyo=INS)
    persona = PersonaDeCampo.objects.create(org=org_a, profile=user_profile, nombre="Uno")
    IntegranteDeJornada.objects.create(org=org_a, jornada=j, persona=persona, rol="tecnico")

    cuadrilla = D.del_dia(org_a, LUNES)["cuadrillas"][0]
    assert cuadrilla["apoyo"] == "Instalacion"

    yo = D.de_la_persona(org_a, user_profile, LUNES)
    assert (yo["apoyo"], yo["apoyo_nombre"]) == (INS, "Instalacion")


def test_v2_una_persona_lo_pone_lo_quita_y_si_no_lo_manda_no_lo_borra(admin_client, org_a, norte):
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    base = {"cuadrilla": str(c.id), "fecha": LUNES.isoformat(), "labor": COR,
            "zonas": [str(norte.id)], "integrantes": []}

    r = admin_client.post(JORNADA, {**base, "labor_de_apoyo": INS}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["labor_de_apoyo"] == INS

    r = admin_client.post(JORNADA, base, format="json")
    assert r.json()["labor_de_apoyo"] == INS, "una pantalla que no lo manda no lo borra"

    r = admin_client.post(JORNADA, {**base, "labor_de_apoyo": ""}, format="json")
    assert r.json()["labor_de_apoyo"] == ""


def test_v3_el_apoyo_no_puede_ser_la_principal_ni_una_labor_que_no_existe(admin_client, org_a):
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    base = {"cuadrilla": str(c.id), "fecha": LUNES.isoformat(), "labor": COR,
            "integrantes": []}

    assert admin_client.post(JORNADA, {**base, "labor_de_apoyo": COR},
                             format="json").status_code == 400
    assert admin_client.post(JORNADA, {**base, "labor_de_apoyo": "no-existe"},
                             format="json").status_code == 400
    assert not JornadaDeCuadrilla.objects.filter(cuadrilla=c).exists()


# ---------------------------------------------------------------------------
# L · que labor se toma de apoyo: lo dice la empresa
# ---------------------------------------------------------------------------

def test_l_la_obra_de_red_no_se_toma_de_apoyo(org_a, norte):
    """Un corte de fibra pide equipo de empalme: la de soporte con cupo no se
    lo lleva (la regla de `test_simular_el_dia::test_l`)."""
    _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=8)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(norte.id): {COR: 3, "trabajos": 2}})

    assert _de(planes, "Cuadrilla 1").labor_de_apoyo == ""


def test_l2_la_empresa_lo_cambia_en_la_configuracion(org_a, norte, admin_client):
    from campo.labores import sembrar_de_fabrica

    sembrar_de_fabrica(org_a)
    _cuadrilla(org_a, "Cuadrilla 1", [norte], tope=8)
    demanda = {str(norte.id): {COR: 3, INS: 2}}
    assert _de(ja.planear_el_dia(org_a, MARTES, demanda=demanda), "Cuadrilla 1").labor_de_apoyo == INS

    r = admin_client.put("/api/campo/material-del-dia/configuracion/",
                         {"apoyos": {INS: False}}, format="json")
    assert r.status_code == 200, r.content
    assert {lab["codigo"]: lab["de_apoyo"] for lab in r.json()["labores"]}[INS] is False
    assert _de(ja.planear_el_dia(org_a, MARTES, demanda=demanda), "Cuadrilla 1").labor_de_apoyo == ""

    assert admin_client.put("/api/campo/material-del-dia/configuracion/",
                            {"apoyos": {INS: "tal vez"}}, format="json").status_code == 400

