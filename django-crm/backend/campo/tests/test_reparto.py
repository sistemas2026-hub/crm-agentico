# -*- coding: utf-8 -*-
"""
================================================================================
 EL REPARTO DE LA MADRUGADA  --  que proponga lo mismo dos veces, y nada mas
================================================================================

Se afirma sobre el EFECTO: que el orden sea el declarado, que la zona de verdad
acote, que lo que no se puede repartir quede NOMBRADO en vez de desaparecer, y
que dos corridas con los mismos datos den el mismo resultado.

Y sobre lo que NO hace: no escribe asignaciones ni publica nada.
"""

import datetime as dt

import pytest

from campo.cuadrillas import Cuadrilla, JornadaDeCuadrilla
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.reparto import proponer
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)


# --- un plazo inyectado, para no depender del calendario de la empresa ------
def plazo_falso(minutos_por_numero):
    """Devuelve un `plazo_de` que lee el riesgo de un dict por numero de orden."""
    def _plazo(orden, ahora=None, **kw):
        m = minutos_por_numero.get(orden.numero)
        if m is None:
            return {"minutos_restantes": None, "minutos_atraso": None}
        if m < 0:
            return {"minutos_restantes": None, "minutos_atraso": -m}
        return {"minutos_restantes": m, "minutos_atraso": None}
    return _plazo


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []},
    )


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


def _orden(org, version, numero, localidad, estado=OrdenTrabajo.ASIGNADA):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        estado_operativo=estado, zona=localidad,
    )


def _jornada(org, nombre, zonas, fecha=LUNES):
    c = Cuadrilla.objects.create(org=org, nombre=nombre)
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=c, fecha=fecha,
        labor=JornadaDeCuadrilla.INSTALACION,
    )
    j.zonas.set(zonas)
    return j


def _de(propuesta, nombre):
    for a in propuesta["asignaciones"]:
        if a["cuadrilla"].nombre == nombre:
            return [o.numero for o in a["ordenes"]]
    return None


# ---------------------------------------------------------------------------
# A · el orden
# ---------------------------------------------------------------------------

def test_a_lo_vencido_va_primero_y_despues_lo_que_menos_tiempo_tiene(
    org_a, version, norte
):
    _jornada(org_a, "Cuadrilla 1", [norte])
    for n in (10, 20, 30):
        _orden(org_a, version, n, "MARTHA GISELA")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({
        10: 600,     # diez horas por delante
        20: -90,     # vencida hace hora y media
        30: 30,      # media hora
    }))
    assert _de(p, "Cuadrilla 1") == [20, 30, 10]


def test_b_entre_dos_iguales_manda_el_numero_y_el_reparto_es_reproducible(
    org_a, version, norte
):
    """Sin un desempate estable, dos corridas pueden repartir distinto."""
    _jornada(org_a, "Cuadrilla 1", [norte])
    for n in (30, 10, 20):
        _orden(org_a, version, n, "MARTHA GISELA")

    plazo = plazo_falso({10: 100, 20: 100, 30: 100})
    primera = _de(proponer(org_a, LUNES, plazo_de=plazo), "Cuadrilla 1")
    segunda = _de(proponer(org_a, LUNES, plazo_de=plazo), "Cuadrilla 1")

    assert primera == [10, 20, 30]
    assert primera == segunda


def test_c_una_orden_sin_plazo_no_se_cuela_adelante(org_a, version, norte):
    """De las que tienen plazo se sabe que urgen; de esta no se sabe nada."""
    _jornada(org_a, "Cuadrilla 1", [norte])
    for n in (10, 20):
        _orden(org_a, version, n, "MARTHA GISELA")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({10: 500}))
    assert _de(p, "Cuadrilla 1") == [10, 20]


# ---------------------------------------------------------------------------
# B · la zona, que es dura
# ---------------------------------------------------------------------------

def test_d_una_cuadrilla_NO_recibe_ordenes_de_otra_zona(
    org_a, version, norte, sur
):
    _jornada(org_a, "Cuadrilla 1", [norte])
    _jornada(org_a, "Cuadrilla 2", [sur])
    _orden(org_a, version, 10, "MARTHA GISELA")
    _orden(org_a, version, 20, "EL CARMEN")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({10: 100, 20: 100}))
    assert _de(p, "Cuadrilla 1") == [10]
    assert _de(p, "Cuadrilla 2") == [20]


def test_e_un_barrio_SIN_MAPEAR_queda_nombrado_y_no_se_reparte(
    org_a, version, norte
):
    """Repartirla la mandaria a cualquier lado; esconderla la dejaria sin hacer."""
    _jornada(org_a, "Cuadrilla 1", [norte])
    _orden(org_a, version, 10, "MARTHA GISELA")
    _orden(org_a, version, 20, "VILLA NUEVA")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({10: 100, 20: 50}))
    assert _de(p, "Cuadrilla 1") == [10]
    assert [o.numero for o in p["sin_zona"]] == [20]


def test_f_una_zona_que_nadie_cubre_hoy_queda_nombrada(org_a, version, norte, sur):
    """No es lo mismo que «sin zona»: ésta tiene zona, falta quien la trabaje."""
    _jornada(org_a, "Cuadrilla 1", [norte])
    _orden(org_a, version, 20, "EL CARMEN")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({20: 100}))
    assert [o.numero for o in p["sin_cuadrilla"]] == [20]
    assert p["sin_zona"] == []


def test_g_una_cuadrilla_SIN_zonas_no_recibe_nada(org_a, version, norte):
    """Vacío es «sin zona asignada», nunca «cubre todas»."""
    _jornada(org_a, "Cuadrilla 1", [])
    _orden(org_a, version, 10, "MARTHA GISELA")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({10: 100}))
    assert _de(p, "Cuadrilla 1") == []
    assert [o.numero for o in p["sin_cuadrilla"]] == [10]


# ---------------------------------------------------------------------------
# C · el reparto
# ---------------------------------------------------------------------------

def test_h_se_reparte_entre_las_que_cubren_la_misma_zona(org_a, version, norte):
    _jornada(org_a, "Cuadrilla 1", [norte])
    _jornada(org_a, "Cuadrilla 2", [norte])
    for n in (10, 20, 30, 40):
        _orden(org_a, version, n, "MARTHA GISELA")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso(
        {10: 100, 20: 200, 30: 300, 40: 400}))
    assert _de(p, "Cuadrilla 1") == [10, 30]
    assert _de(p, "Cuadrilla 2") == [20, 40]


def test_i_lo_que_pasa_el_tope_queda_nombrado(org_a, version, norte):
    """Sin esto, el reparto le volcaria treinta visitas a una cuadrilla."""
    _jornada(org_a, "Cuadrilla 1", [norte])
    for n in (10, 20, 30):
        _orden(org_a, version, n, "MARTHA GISELA")

    p = proponer(org_a, LUNES, tope=2,
                 plazo_de=plazo_falso({10: 100, 20: 200, 30: 300}))
    assert _de(p, "Cuadrilla 1") == [10, 20]
    assert [o.numero for o in p["sobrantes"]] == [30]


def test_j_una_orden_YA_ASIGNADA_no_se_vuelve_a_repartir(
    org_a, version, norte, admin_profile
):
    _jornada(org_a, "Cuadrilla 1", [norte])
    ya = _orden(org_a, version, 10, "MARTHA GISELA")
    AsignacionTrabajo.objects.create(
        orden=ya, profile=admin_profile, rol="tecnico", es_principal=True
    )
    _orden(org_a, version, 20, "MARTHA GISELA")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({10: 10, 20: 999}))
    assert _de(p, "Cuadrilla 1") == [20]


def test_k_una_orden_BLOQUEADA_no_entra(org_a, version, norte):
    """Esta detenida por algo que no se resuelve repartiendola de nuevo."""
    _jornada(org_a, "Cuadrilla 1", [norte])
    _orden(org_a, version, 10, "MARTHA GISELA", estado=OrdenTrabajo.BLOQUEADA)

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({10: 10}))
    assert _de(p, "Cuadrilla 1") == []


def test_l_una_CORRECCION_REQUERIDA_si_entra(org_a, version, norte):
    """El supervisor la devolvio: vuelve a necesitar a alguien."""
    _jornada(org_a, "Cuadrilla 1", [norte])
    _orden(org_a, version, 10, "MARTHA GISELA",
           estado=OrdenTrabajo.CORRECCION_REQUERIDA)

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({10: 10}))
    assert _de(p, "Cuadrilla 1") == [10]


# ---------------------------------------------------------------------------
# D · lo que NO hace
# ---------------------------------------------------------------------------

def test_m_proponer_no_escribe_NINGUNA_asignacion(org_a, version, norte):
    """Shadow mode: recomienda, nunca hace. Una persona publica."""
    _jornada(org_a, "Cuadrilla 1", [norte])
    _orden(org_a, version, 10, "MARTHA GISELA")

    antes = AsignacionTrabajo.objects.count()
    proponer(org_a, LUNES, plazo_de=plazo_falso({10: 100}))
    assert AsignacionTrabajo.objects.count() == antes


def test_n_tampoco_toca_el_estado_de_la_orden(org_a, version, norte):
    _jornada(org_a, "Cuadrilla 1", [norte])
    o = _orden(org_a, version, 10, "MARTHA GISELA")

    proponer(org_a, LUNES, plazo_de=plazo_falso({10: 100}))
    o.refresh_from_db()
    assert o.estado_operativo == OrdenTrabajo.ASIGNADA


def test_o_las_ordenes_de_OTRA_empresa_no_entran(
    org_a, org_b, version, norte
):
    _jornada(org_a, "Cuadrilla 1", [norte])
    wt = WorkType.objects.create(org=org_b, codigo="x", nombre="X")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []},
    )
    _orden(org_b, v, 10, "MARTHA GISELA")

    p = proponer(org_a, LUNES, plazo_de=plazo_falso({10: 10}))
    assert _de(p, "Cuadrilla 1") == []
    assert p["sin_zona"] == []


# ---------------------------------------------------------------------------
# E · la API: proponer no escribe, publicar escribe lo que se vio
# ---------------------------------------------------------------------------

REPARTO = "/api/campo/cuadrillas/reparto/"


def _con_gente(org, jornada, profile, rol="tecnico"):
    from campo.cuadrillas import IntegranteDeJornada

    IntegranteDeJornada.objects.create(
        org=org, jornada=jornada, profile=profile, rol=rol
    )
    return jornada


def test_p_proponer_devuelve_la_jornada_y_no_escribe(
    admin_client, org_a, version, norte, admin_profile
):
    j = _con_gente(org_a, _jornada(org_a, "Cuadrilla 1", [norte]), admin_profile)
    _orden(org_a, version, 10, "MARTHA GISELA")

    antes = AsignacionTrabajo.objects.count()
    r = admin_client.get(REPARTO, {"fecha": LUNES.isoformat()})

    assert r.status_code == 200, r.content
    d = r.json()
    assert d["asignaciones"][0]["cuadrilla"]["nombre"] == "Cuadrilla 1"
    assert [o["numero"] for o in d["asignaciones"][0]["ordenes"]] == [10]
    assert AsignacionTrabajo.objects.count() == antes, "proponer no escribe"
    assert j.id


def test_q_lo_que_no_se_reparte_viaja_nombrado(
    admin_client, org_a, version, norte, admin_profile
):
    _con_gente(org_a, _jornada(org_a, "Cuadrilla 1", [norte]), admin_profile)
    _orden(org_a, version, 20, "VILLA NUEVA")

    d = admin_client.get(REPARTO, {"fecha": LUNES.isoformat()}).json()
    assert [o["numero"] for o in d["sin_zona"]] == [20]


def test_r_publicar_crea_UNA_asignacion_por_integrante(
    admin_client, org_a, version, norte, admin_profile, user_profile
):
    j = _jornada(org_a, "Cuadrilla 1", [norte])
    _con_gente(org_a, j, admin_profile, "tecnico_lider")
    _con_gente(org_a, j, user_profile, "ayudante")
    o = _orden(org_a, version, 10, "MARTHA GISELA")

    r = admin_client.post(REPARTO, {
        "asignaciones": [{"jornada": str(j.id), "ordenes": [str(o.id)]}],
    }, format="json")

    assert r.status_code == 200, r.content
    assert r.json()["publicadas"] == 1
    assert o.asignaciones.count() == 2, "una por cada integrante del dia"
    assert set(o.asignaciones.values_list("rol", flat=True)) == {
        "tecnico_lider", "ayudante"
    }


def test_s_una_orden_YA_ASIGNADA_no_se_pisa_y_se_nombra(
    admin_client, org_a, version, norte, admin_profile, user_profile
):
    """Entre mirar y publicar alguien pudo asignarla a mano, y esa decision gana."""
    j = _con_gente(org_a, _jornada(org_a, "Cuadrilla 1", [norte]), admin_profile)
    o = _orden(org_a, version, 10, "MARTHA GISELA")
    AsignacionTrabajo.objects.create(
        orden=o, profile=user_profile, rol="tecnico", es_principal=True
    )

    r = admin_client.post(REPARTO, {
        "asignaciones": [{"jornada": str(j.id), "ordenes": [str(o.id)]}],
    }, format="json")

    assert r.json()["publicadas"] == 0
    assert r.json()["ya_tenian"] == [10], "se nombra: si no, la cuenta no cuadra"
    assert o.asignaciones.count() == 1, "la de antes queda intacta"


def test_t_una_cuadrilla_sin_gente_no_recibe_trabajo(
    admin_client, org_a, version, norte
):
    """La orden quedaria asignada a nadie."""
    j = _jornada(org_a, "Cuadrilla 1", [norte])     # sin integrantes
    o = _orden(org_a, version, 10, "MARTHA GISELA")

    r = admin_client.post(REPARTO, {
        "asignaciones": [{"jornada": str(j.id), "ordenes": [str(o.id)]}],
    }, format="json")

    assert r.json()["publicadas"] == 0
    assert o.asignaciones.count() == 0


def test_u_un_tecnico_puede_PROPONER_pero_no_publicar(
    user_client, org_a, version, norte
):
    _jornada(org_a, "Cuadrilla 1", [norte])
    assert user_client.get(REPARTO, {"fecha": LUNES.isoformat()}).status_code == 200
    r = user_client.post(REPARTO, {"asignaciones": [{"jornada": "x", "ordenes": []}]},
                         format="json")
    assert r.status_code == 403
