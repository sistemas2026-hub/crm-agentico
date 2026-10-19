# -*- coding: utf-8 -*-
"""
================================================================================
 EL ARMADO DEL DIA  --  la regla del 17/10/2026
================================================================================

Objetivo `SPEC/objetivos/supervisor-arma-la-jornada.md`, Fase 1. La regla la
decidio el usuario con 60 dias de produccion a la vista: lo que se repite es la
PAREJA de cada cuadrilla, no las zonas ni la labor.

Se afirma sobre el EFECTO --la jornada que queda escrita, o lo que el plan dice
que se armaria-- y cada prueba siembra tambien lo que NO tiene que pasar: una
zona del ultimo dia que no es la habitual, una labor que pierde, una persona
que no tiene que ir.

    pytest campo/tests/test_armado_del_dia.py
================================================================================
"""

import datetime as dt

import pytest

from campo import jornada_automatica as ja
from campo.cuadrillas import (
    ConfiguracionDeReparto,
    Cuadrilla,
    IntegranteDeJornada,
    JornadaDeCuadrilla,
    PersonaDeCampo,
    labor_de_cada_grupo,
)
from campo.zonas import ZonaOperativa
from common.models import Profile, User

pytestmark = pytest.mark.django_db

VIERNES = dt.date(2026, 10, 2)
LUNES = dt.date(2026, 10, 5)
MARTES = dt.date(2026, 10, 6)
COR, INS, TRA = "correctivo", "instalacion", "trabajos"
JORNADA = "/api/campo/cuadrillas/jornada/"


@pytest.fixture
def soledad(org_a):
    return ZonaOperativa.objects.create(org=org_a, nombre="SOLEDAD")


@pytest.fixture
def sabanagrande(org_a):
    return ZonaOperativa.objects.create(org=org_a, nombre="SABANAGRANDE")


def _cuenta(org, email):
    u = User.objects.create_user(email=email, password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org, role="USER", is_active=True)


def _cuadrilla(org, nombre, lider, zonas, labor=INS):
    c = Cuadrilla.objects.create(org=org, nombre=nombre, lider=lider,
                                 labor_habitual=labor)
    c.zonas_habituales.set(zonas)
    return c


def _persona(org, nombre, profile=None):
    return PersonaDeCampo.objects.create(org=org, nombre=nombre,
                                         profile=profile)


def _jornada(org, cuadrilla, fecha, zonas=(), gente=(), labor=COR,
             armada_por=JornadaDeCuadrilla.PERSONA):
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=cuadrilla, fecha=fecha, labor=labor,
        armada_por=armada_por)
    j.zonas.set(zonas)
    for persona, rol in gente:
        IntegranteDeJornada.objects.create(org=org, jornada=j,
                                           persona=persona, rol=rol)
    return j


def _calendario(org):
    """La empresa trabaja de 07:00 a 17:00 de lunes a viernes."""
    from business_hours.models import BusinessCalendar

    cal = BusinessCalendar.objects.create(org=org, name="Default",
                                          timezone="America/Bogota",
                                          is_default=True)
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        setattr(cal, f"{d}_open", dt.time(7, 0))
        setattr(cal, f"{d}_close", dt.time(17, 0))
    cal.save()
    return cal


def _ausencia(org, profile, fecha, desde=dt.time(7, 0), hasta=dt.time(17, 0)):
    from operaciones.models import DisponibilidadTecnico

    return DisponibilidadTecnico.objects.create(
        org=org, profile=profile, fecha=fecha, hora_inicio=desde,
        hora_fin=hasta, disponible=False, motivo="vacaciones")


def _de(planes, nombre):
    return next(p for p in planes if p.cuadrilla.nombre == nombre)


# ---------------------------------------------------------------------------
# A · quien va, y adonde
# ---------------------------------------------------------------------------

def test_a_va_la_pareja_de_su_ultima_jornada_a_sus_zonas_HABITUALES(
    org_a, admin_profile, soledad, sabanagrande
):
    """Las zonas del ultimo dia NO: eso era lo que no se repetia."""
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    vieja = _persona(org_a, "Ya No Va")
    pedro, pablo = _persona(org_a, "PEDRO"), _persona(org_a, "PABLO")
    _jornada(org_a, c, VIERNES, zonas=[soledad], gente=[(vieja, "tecnico")])
    _jornada(org_a, c, LUNES, zonas=[sabanagrande],
             gente=[(pedro, "tecnico"), (pablo, "ayudante")])

    r = ja.asegurar_jornadas(org_a, MARTES)

    assert [x["cuadrilla"] for x in r["copiadas"]] == ["Cuadrilla #1"]
    assert r["copiadas"][0]["desde"] == LUNES.isoformat()
    nueva = JornadaDeCuadrilla.objects.get(cuadrilla=c, fecha=MARTES)
    assert [z.nombre for z in nueva.zonas.all()] == ["SOLEDAD"]
    assert sorted(i.persona.nombre for i in nueva.integrantes.all()) == [
        "PABLO", "PEDRO"]
    assert nueva.lider_id == admin_profile.id
    assert nueva.armada_por == JornadaDeCuadrilla.AUTOMATICA


def test_b_una_cuadrilla_dada_de_baja_no_se_arma(org_a, admin_profile, soledad):
    c = _cuadrilla(org_a, "Cuadrilla #9", admin_profile, [soledad])
    c.activa = False
    c.save()

    ja.asegurar_jornadas(org_a, MARTES)

    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


# ---------------------------------------------------------------------------
# B · la labor
# ---------------------------------------------------------------------------

def test_c_sin_casos_sale_con_su_labor_habitual(org_a, admin_profile, soledad):
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad], labor=TRA)

    planes = ja.planear_el_dia(org_a, MARTES, demanda={})

    assert _de(planes, "Cuadrilla #1").labor == TRA


def test_d_con_casos_toma_la_labor_de_la_MAYORIA_de_sus_zonas(
    org_a, admin_profile, soledad, sabanagrande
):
    """Y no la de otra zona: los casos de SABANAGRANDE no la inclinan."""
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad], labor=INS)
    demanda = {str(soledad.id): {COR: 3, INS: 1},
               str(sabanagrande.id): {INS: 9}}

    planes = ja.planear_el_dia(org_a, MARTES, demanda=demanda)

    assert _de(planes, "Cuadrilla #1").labor == COR


def test_e_en_empate_gana_su_habitual(org_a, admin_profile, soledad):
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad], labor=INS)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(soledad.id): {COR: 2, INS: 2}})

    assert _de(planes, "Cuadrilla #1").labor == INS


def test_f_dos_en_la_misma_zona_con_dos_labores_se_reparten_una_cada_una(
    org_a, admin_profile, user_profile, soledad
):
    """Decidido por el usuario: la segunda toma la otra.

    Y SIN CRUZARLAS POR EL ORDEN ALFABETICO: la #1 es de instalacion y la #2
    de correctivo, asi que cada una se queda con la suya aunque correctivo
    tenga mas casos y la #1 se mire primero.
    """
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad], labor=INS)
    _cuadrilla(org_a, "Cuadrilla #2", user_profile, [soledad], labor=COR)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(soledad.id): {COR: 5, INS: 2}})

    assert _de(planes, "Cuadrilla #1").labor == INS
    assert _de(planes, "Cuadrilla #2").labor == COR


def test_f2_si_las_dos_son_de_la_misma_labor_la_segunda_toma_la_otra(
    org_a, admin_profile, user_profile, soledad
):
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad], labor=COR)
    _cuadrilla(org_a, "Cuadrilla #2", user_profile, [soledad], labor=COR)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(soledad.id): {COR: 5, INS: 2}})

    assert _de(planes, "Cuadrilla #1").labor == COR
    assert _de(planes, "Cuadrilla #2").labor == INS


def test_g_si_la_zona_tiene_una_sola_labor_las_dos_ayudan_con_esa(
    org_a, admin_profile, user_profile, soledad
):
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad], labor=INS)
    _cuadrilla(org_a, "Cuadrilla #2", user_profile, [soledad], labor=INS)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(soledad.id): {COR: 4}})

    assert [_de(planes, n).labor for n in ("Cuadrilla #1", "Cuadrilla #2")] \
        == [COR, COR]


def test_h_lo_que_ya_cubre_una_jornada_armada_a_mano_cuenta(
    org_a, admin_profile, user_profile, soledad
):
    """La #1 ya sale de correctivo, armada por una persona: la #2 toma la otra."""
    c1 = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad], labor=INS)
    _cuadrilla(org_a, "Cuadrilla #2", user_profile, [soledad], labor=COR)
    _jornada(org_a, c1, MARTES, zonas=[soledad], labor=COR)

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(soledad.id): {COR: 5, INS: 2}})

    assert _de(planes, "Cuadrilla #1").accion == ja.DEJAR
    assert _de(planes, "Cuadrilla #2").labor == INS


# ---------------------------------------------------------------------------
# C · lo que no se arma, y se dice por que
# ---------------------------------------------------------------------------

def test_i_sin_zonas_habituales_no_se_arma(org_a, admin_profile, soledad):
    c = _cuadrilla(org_a, "Cuadrilla #3", admin_profile, [])
    _jornada(org_a, c, LUNES, zonas=[soledad])

    r = ja.asegurar_jornadas(org_a, MARTES,
                             demanda={str(soledad.id): {COR: 4}})

    assert r["sin_zona"] == ["Cuadrilla #3"]
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


def test_j_con_el_lider_ausente_no_se_arma(org_a, soledad):
    _calendario(org_a)
    lider = _cuenta(org_a, "lider@x.test")
    c = _cuadrilla(org_a, "Cuadrilla #1", lider, [soledad])
    _jornada(org_a, c, LUNES, zonas=[soledad],
             gente=[(_persona(org_a, "AUX"), "ayudante")])
    _ausencia(org_a, lider, MARTES)

    r = ja.asegurar_jornadas(org_a, MARTES)

    assert r["lider_ausente"] == ["Cuadrilla #1"]
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


def test_k_un_integrante_ausente_queda_afuera_y_se_cuenta(
    org_a, admin_profile, soledad
):
    _calendario(org_a)
    tecnico = _cuenta(org_a, "tecnico@x.test")
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    _jornada(org_a, c, LUNES, zonas=[soledad], gente=[
        (_persona(org_a, "TECNICO", profile=tecnico), "tecnico"),
        (_persona(org_a, "AUX"), "ayudante")])
    _ausencia(org_a, tecnico, MARTES)

    r = ja.asegurar_jornadas(org_a, MARTES)

    assert r["copiadas"][0]["ausentes"] == 1
    nueva = JornadaDeCuadrilla.objects.get(cuadrilla=c, fecha=MARTES)
    assert [i.persona.nombre for i in nueva.integrantes.all()] == ["AUX"]


def test_l_una_ausencia_de_media_manana_no_saca_a_nadie(
    org_a, admin_profile, soledad
):
    """Sale tarde, pero sale."""
    _calendario(org_a)
    tecnico = _cuenta(org_a, "tecnico@x.test")
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    _jornada(org_a, c, LUNES, zonas=[soledad], gente=[
        (_persona(org_a, "TECNICO", profile=tecnico), "tecnico")])
    _ausencia(org_a, tecnico, MARTES, desde=dt.time(7, 0),
              hasta=dt.time(9, 0))

    ja.asegurar_jornadas(org_a, MARTES)

    nueva = JornadaDeCuadrilla.objects.get(cuadrilla=c, fecha=MARTES)
    assert [i.persona.nombre for i in nueva.integrantes.all()] == ["TECNICO"]


def test_m_quien_una_persona_ya_puso_en_otra_cuadrilla_hoy_no_se_duplica(
    org_a, admin_profile, user_profile, soledad
):
    c1 = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    c2 = _cuadrilla(org_a, "Cuadrilla #2", user_profile, [soledad])
    pedro, pablo = _persona(org_a, "PEDRO"), _persona(org_a, "PABLO")
    _jornada(org_a, c1, LUNES, zonas=[soledad],
             gente=[(pedro, "tecnico"), (pablo, "ayudante")])
    #  Hoy una persona ya puso a PEDRO en la #2.
    _jornada(org_a, c2, MARTES, zonas=[soledad], gente=[(pedro, "tecnico")])

    r = ja.asegurar_jornadas(org_a, MARTES)

    assert r["copiadas"][0]["en_otra_cuadrilla"] == 1
    nueva = JornadaDeCuadrilla.objects.get(cuadrilla=c1, fecha=MARTES)
    assert [i.persona.nombre for i in nueva.integrantes.all()] == ["PABLO"]


# ---------------------------------------------------------------------------
# D · lo que no pisa, y el reajuste de la labor
# ---------------------------------------------------------------------------

def test_n_una_jornada_armada_por_una_persona_no_se_toca(
    org_a, admin_profile, soledad
):
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    a_mano = _jornada(org_a, c, MARTES, zonas=[soledad], labor=TRA)

    r = ja.asegurar_jornadas(org_a, MARTES,
                             demanda={str(soledad.id): {COR: 9}})

    a_mano.refresh_from_db()
    assert a_mano.labor == TRA
    assert r["ya_estaban"] == ["Cuadrilla #1"]


def test_o_una_armada_sola_y_SIN_ordenes_se_reajusta_de_labor(
    org_a, admin_profile, soledad
):
    """Lo que entra a Despacho a la tarde con otra labor sale ese dia."""
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    sola = _jornada(org_a, c, MARTES, zonas=[soledad], labor=INS,
                    armada_por=JornadaDeCuadrilla.AUTOMATICA)

    r = ja.asegurar_jornadas(org_a, MARTES,
                             demanda={str(soledad.id): {COR: 3}})

    sola.refresh_from_db()
    assert sola.labor == COR
    assert r["reajustadas"] == [{"cuadrilla": "Cuadrilla #1", "de": INS, "a": COR}]


def test_p_pero_CON_ordenes_ya_no(org_a, admin_profile, soledad):
    """Cambiarle la labor a una cuadrilla que ya salio con trabajo seria
    repartirle otro."""
    from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    sola = _jornada(org_a, c, MARTES, zonas=[soledad], labor=INS,
                    armada_por=JornadaDeCuadrilla.AUTOMATICA)
    wt = WorkType.objects.create(org=org_a, codigo="inst", nombre="INST",
                                 labor=INS)
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=1, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA, zona="CENTRO")
    AsignacionTrabajo.objects.create(orden=orden, profile=admin_profile,
                                     rol=AsignacionTrabajo.TECNICO_LIDER,
                                     es_principal=True)

    r = ja.asegurar_jornadas(org_a, MARTES,
                             demanda={str(soledad.id): {COR: 3}})

    sola.refresh_from_db()
    assert sola.labor == INS
    assert r["reajustadas"] == []


def test_q_corregirla_desde_la_pantalla_la_vuelve_de_una_persona(
    org_a, admin_profile, admin_client, soledad
):
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    sola = _jornada(org_a, c, MARTES, zonas=[soledad], labor=INS,
                    armada_por=JornadaDeCuadrilla.AUTOMATICA)

    r = admin_client.post(JORNADA, {
        "cuadrilla": str(c.id), "fecha": MARTES.isoformat(), "labor": TRA,
        "zonas": [str(soledad.id)], "integrantes": []}, format="json")

    assert r.status_code in (200, 201), r.content
    sola.refresh_from_db()
    assert sola.armada_por == JornadaDeCuadrilla.PERSONA
    assert r.json()["armada_por"] == JornadaDeCuadrilla.PERSONA
    #  Y desde ahi el armado ya no la toca.
    ja.asegurar_jornadas(org_a, MARTES, demanda={str(soledad.id): {COR: 9}})
    sola.refresh_from_db()
    assert sola.labor == TRA


def test_r_correrlo_dos_veces_deja_lo_mismo(org_a, admin_profile, soledad):
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    _jornada(org_a, c, LUNES, zonas=[soledad],
             gente=[(_persona(org_a, "PEDRO"), "tecnico")])
    demanda = {str(soledad.id): {COR: 2}}

    ja.asegurar_jornadas(org_a, MARTES, demanda=demanda)
    segunda = ja.asegurar_jornadas(org_a, MARTES, demanda=demanda)

    assert segunda["ya_estaban"] == ["Cuadrilla #1"]
    assert segunda["copiadas"] == [] and segunda["reajustadas"] == []
    assert JornadaDeCuadrilla.objects.filter(fecha=MARTES).count() == 1
    assert IntegranteDeJornada.objects.filter(jornada__fecha=MARTES).count() == 1


def test_s_el_plan_NO_escribe(org_a, admin_profile, soledad):
    """Es lo que la sombra muestra: lo que se armaria, sin armarlo."""
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    _jornada(org_a, c, LUNES, zonas=[soledad])

    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(soledad.id): {COR: 2}})

    assert ja.resumen(planes)["labores"] == {"Cuadrilla #1": COR}
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


# ---------------------------------------------------------------------------
# E · de que labor es cada grupo, por empresa
# ---------------------------------------------------------------------------

def test_t_la_tabla_de_fabrica_y_la_de_la_empresa(org_a):
    #  Desde el 18/10/2026 (correccion 1 del usuario) el trabajo pedido de un
    #  cliente que ya existe es correctivo, y la instalacion es solo para uno
    #  nuevo: la fila 'instalacion_nueva'.
    assert labor_de_cada_grupo(org_a) == {
        "falla_de_servicio": COR, "obra_de_red": TRA, "trabajo_pedido": COR,
        "instalacion_nueva": INS}

    ConfiguracionDeReparto.objects.create(org=org_a, labor_por_grupo={
        "trabajo_pedido": TRA,        # la empresa lo cambia
        "obra_de_red": "pintura",   # una labor que no existe: vale la de fabrica
        "falla_de_servicio": "",    # vacio a proposito: no inclina nada
    })

    assert labor_de_cada_grupo(org_a) == {"obra_de_red": TRA,
                                          "trabajo_pedido": TRA,
                                          "instalacion_nueva": INS}


def test_u_la_tabla_es_de_CADA_empresa(org_a, org_b):
    from conftest import set_rls_context

    set_rls_context(org_b)
    ConfiguracionDeReparto.objects.create(org=org_b, labor_por_grupo={
        "trabajo_pedido": TRA})
    set_rls_context(org_a)

    assert labor_de_cada_grupo(org_a)["trabajo_pedido"] == COR


# ---------------------------------------------------------------------------
# F · la tabla se edita desde la pantalla
# ---------------------------------------------------------------------------

CONFIG = "/api/campo/cuadrillas/configuracion/"
LO_DE_SIEMPRE = {"activo": False, "hora_local": 3, "tope_por_cuadrilla": 8,
                 "copia_la_jornada": True}


def test_v_la_pantalla_lee_y_guarda_la_tabla_y_sin_la_clave_no_la_toca(
    org_a, admin_client
):
    assert admin_client.get(CONFIG).json()["labor_por_grupo"] == {
        "falla_de_servicio": COR, "obra_de_red": TRA, "trabajo_pedido": COR,
        "instalacion_nueva": INS}

    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "labor_por_grupo": {
        "trabajo_pedido": TRA, "instalacion_nueva": COR, "obra_de_red": ""}},
        format="json")
    assert r.status_code == 200, r.content
    esperada = {"falla_de_servicio": COR, "trabajo_pedido": TRA,
                "instalacion_nueva": COR}
    assert r.json()["labor_por_grupo"] == esperada

    #  Una pantalla vieja que no manda la tabla no la borra.
    r = admin_client.put(CONFIG, LO_DE_SIEMPRE, format="json")
    assert r.json()["labor_por_grupo"] == esperada
    assert labor_de_cada_grupo(org_a) == esperada


def test_w_un_grupo_o_una_labor_que_no_existe_no_se_guarda(org_a, admin_client):
    for mala in ({"pintura": COR}, {"trabajo_pedido": "pintura"},
                 ["trabajo_pedido"]):
        r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "labor_por_grupo": mala},
                             format="json")
        assert r.status_code == 400, mala
    assert not ConfiguracionDeReparto.objects.filter(org=org_a).exists()


# ---------------------------------------------------------------------------
# G · lo que encontro el auditor de frontera (17/10/2026)
# ---------------------------------------------------------------------------

def _orden_del_lider(org, lider, *, estado="asignada", hace_dias=0):
    from django.utils import timezone

    from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

    n = OrdenTrabajo.objects.count() + 1
    wt = WorkType.objects.create(org=org, codigo=f"inst{n}", nombre="INST",
                                 labor=INS)
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=n, tipo_trabajo_version=version,
        estado_operativo=estado, zona="CENTRO")
    a = AsignacionTrabajo.objects.create(orden=orden, profile=lider,
                                         rol=AsignacionTrabajo.TECNICO_LIDER,
                                         es_principal=True)
    if hace_dias:
        AsignacionTrabajo.objects.filter(pk=a.pk).update(
            asignado_en=timezone.now() - dt.timedelta(days=hace_dias))
    return orden


def _sola(org, cuadrilla, zonas, labor=INS):
    return _jornada(org, cuadrilla, MARTES, zonas=zonas, labor=labor,
                    armada_por=JornadaDeCuadrilla.AUTOMATICA)


def test_p2_una_orden_ABIERTA_asignada_antes_de_hoy_tambien_congela(
    org_a, admin_profile, soledad
):
    """La primera version miraba solo lo asignado desde las 00:00: una orden
    para hoy asignada anoche no congelaba la labor."""
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    sola = _sola(org_a, c, [soledad])
    _orden_del_lider(org_a, admin_profile, hace_dias=2)

    r = ja.asegurar_jornadas(org_a, MARTES,
                             demanda={str(soledad.id): {COR: 3}})

    sola.refresh_from_db()
    assert sola.labor == INS
    assert r["reajustadas"] == []


def test_p3_pero_una_orden_TERMINADA_no_congela(org_a, admin_profile, soledad):
    from campo.models import OrdenTrabajo

    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    sola = _sola(org_a, c, [soledad])
    _orden_del_lider(org_a, admin_profile, estado=OrdenTrabajo.COMPLETADA_CAMPO)

    ja.asegurar_jornadas(org_a, MARTES, demanda={str(soledad.id): {COR: 3}})

    sola.refresh_from_db()
    assert sola.labor == COR


def test_p4_si_publican_entre_el_plan_y_la_escritura_no_se_reajusta(
    org_a, admin_profile, soledad
):
    """Entre el plan y `aplicar` hay una llamada de red; alguien puede publicar
    el reparto en ese hueco. `aplicar` vuelve a mirar las ordenes."""
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    sola = _sola(org_a, c, [soledad])
    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(soledad.id): {COR: 3}})
    assert _de(planes, "Cuadrilla #1").accion == ja.REAJUSTAR

    _orden_del_lider(org_a, admin_profile)
    r = ja.aplicar(org_a, MARTES, planes)

    sola.refresh_from_db()
    assert sola.labor == INS
    assert r["ya_estaban"] == ["Cuadrilla #1"]


def test_q2_la_persona_que_la_corrige_entre_el_plan_y_la_escritura_gana(
    org_a, admin_profile, admin_client, soledad
):
    """Aunque deje la MISMA labor: solo la condicion por `armada_por` la
    protege. Sin ella, todas las demas pruebas seguian en verde (auditor de
    frontera, 17/10)."""
    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    sola = _sola(org_a, c, [soledad])
    planes = ja.planear_el_dia(org_a, MARTES,
                               demanda={str(soledad.id): {COR: 3}})
    assert _de(planes, "Cuadrilla #1").accion == ja.REAJUSTAR

    r = admin_client.post(JORNADA, {
        "cuadrilla": str(c.id), "fecha": MARTES.isoformat(), "labor": INS,
        "zonas": [str(soledad.id)], "integrantes": []}, format="json")
    assert r.status_code in (200, 201), r.content
    ja.aplicar(org_a, MARTES, planes)

    sola.refresh_from_db()
    assert (sola.labor, sola.armada_por) == (INS, JornadaDeCuadrilla.PERSONA)


def test_x_armar_y_reajustar_dejan_su_fila_de_auditoria(
    org_a, admin_profile, soledad
):
    """El nivel 3 es ejecutar algo reversible, y revertir se apoya en poder ver
    que se hizo: de un reajuste no quedaba ni la labor anterior."""
    from common.models import Activity
    from operaciones import auditoria

    c = _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad])
    _jornada(org_a, c, LUNES, zonas=[soledad])
    ja.asegurar_jornadas(org_a, MARTES, origen="prueba")
    hoy = JornadaDeCuadrilla.objects.get(cuadrilla=c, fecha=MARTES)

    armada = Activity.objects.get(entity_type=auditoria.ENTIDAD_JORNADA,
                                  entity_id=hoy.id, action="CREATE")
    assert armada.user_id is None
    assert armada.metadata["origen"] == "prueba"
    assert armada.metadata["estado_nuevo"] == INS

    ja.asegurar_jornadas(org_a, MARTES, demanda={str(soledad.id): {COR: 2}},
                         origen="prueba")
    reajuste = Activity.objects.get(entity_type=auditoria.ENTIDAD_JORNADA,
                                    entity_id=hoy.id, action="UPDATE")
    assert (reajuste.metadata["estado_anterior"],
            reajuste.metadata["estado_nuevo"]) == (INS, COR)


def test_f3_la_habitual_solo_si_lo_que_deja_lo_toma_otra(
    org_a, admin_profile, user_profile, soledad, sabanagrande
):
    """La #1 cubre las dos zonas y la #2 solo SOLEDAD. Si la #1 se quedara con
    su habitual (correctivo), las cinco instalaciones de SABANAGRANDE no las
    tomaria nadie: la #2 no va alla (auditor independiente, 17/10)."""
    _cuadrilla(org_a, "Cuadrilla #1", admin_profile, [soledad, sabanagrande],
               labor=COR)
    _cuadrilla(org_a, "Cuadrilla #2", user_profile, [soledad], labor=COR)

    planes = ja.planear_el_dia(org_a, MARTES, demanda={
        str(soledad.id): {COR: 1}, str(sabanagrande.id): {INS: 5}})

    assert _de(planes, "Cuadrilla #1").labor == INS
    assert _de(planes, "Cuadrilla #2").labor == COR
