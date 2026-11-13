# -*- coding: utf-8 -*-
"""
================================================================================
 ARMAR EL DIA DE UNA CUADRILLA DESDE LA PLATAFORMA
================================================================================

Se afirma sobre el EFECTO: que armar el dia dos veces deje lo mismo que armarlo
una, que cambiar de labor no borre lo de ayer, y que repartirle el dia a la
misma persona dos veces no se pueda.
"""

import datetime as dt

import pytest

from campo.cuadrillas import Cuadrilla, JornadaDeCuadrilla

pytestmark = pytest.mark.django_db

CUADRILLAS = "/api/campo/cuadrillas/"
JORNADA = "/api/campo/cuadrillas/jornada/"

LUNES = "2026-10-05"
MARTES = "2026-10-06"


@pytest.fixture
def cuadrilla(org_a):
    return Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")


def _armar(client, cuadrilla, fecha, labor, integrantes=()):
    return client.post(
        JORNADA,
        {
            "cuadrilla": str(cuadrilla.id),
            "fecha": fecha,
            "labor": labor,
            "integrantes": list(integrantes),
        },
        format="json",
    )


# ---------------------------------------------------------------------------
# A · la cuadrilla
# ---------------------------------------------------------------------------

def test_a_crear_y_listar(admin_client):
    r = admin_client.post(CUADRILLAS, {"nombre": "Cuadrilla Norte"},
                          format="json")
    assert r.status_code == 201, r.content

    lista = admin_client.get(CUADRILLAS).json()["cuadrillas"]
    assert [c["nombre"] for c in lista] == ["Cuadrilla Norte"]


def test_b_dos_cuadrillas_no_se_llaman_igual(admin_client, cuadrilla):
    """El nombre es lo que la gente usa para hablar de ella."""
    r = admin_client.post(CUADRILLAS, {"nombre": "Cuadrilla 1"}, format="json")
    assert r.status_code == 409
    assert "Cuadrilla 1" in r.json()["detail"]


def test_c_dar_de_baja_la_saca_de_la_lista_pero_no_la_borra(
    admin_client, cuadrilla
):
    admin_client.patch(f"{CUADRILLAS}{cuadrilla.id}/", {"activa": False},
                       format="json")

    assert admin_client.get(CUADRILLAS).json()["cuadrillas"] == []
    todas = admin_client.get(CUADRILLAS, {"todas": "1"}).json()["cuadrillas"]
    assert [c["nombre"] for c in todas] == ["Cuadrilla 1"]


# ---------------------------------------------------------------------------
# B · la jornada
# ---------------------------------------------------------------------------

def test_d_armar_el_dia_con_su_labor_y_su_gente(
    admin_client, cuadrilla, admin_profile, user_profile
):
    r = _armar(
        admin_client, cuadrilla, LUNES, "instalacion",
        [{"profile": str(admin_profile.id), "rol": "tecnico_lider"},
         {"profile": str(user_profile.id), "rol": "ayudante"}],
    )
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["labor"] == "instalacion"
    assert {i["rol"] for i in d["integrantes"]} == {"tecnico_lider", "ayudante"}


def test_e_armarlo_dos_veces_deja_lo_mismo_que_armarlo_una(
    admin_client, cuadrilla, admin_profile
):
    """Armar el dia se corrige varias veces antes de que empiece."""
    gente = [{"profile": str(admin_profile.id), "rol": "tecnico"}]
    _armar(admin_client, cuadrilla, LUNES, "instalacion", gente)
    _armar(admin_client, cuadrilla, LUNES, "instalacion", gente)

    assert JornadaDeCuadrilla.objects.filter(cuadrilla=cuadrilla).count() == 1
    jornada = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla)
    assert jornada.integrantes.count() == 1, "no se duplican los integrantes"


def test_f_cambiar_de_labor_el_martes_no_toca_el_lunes(
    admin_client, cuadrilla, admin_profile
):
    """El caso que motivo que la jornada sea una tabla aparte."""
    gente = [{"profile": str(admin_profile.id), "rol": "tecnico"}]
    _armar(admin_client, cuadrilla, LUNES, "instalacion", gente)
    _armar(admin_client, cuadrilla, MARTES, "correctivo", gente)

    del_lunes = admin_client.get(JORNADA, {"fecha": LUNES}).json()["jornadas"]
    del_martes = admin_client.get(JORNADA, {"fecha": MARTES}).json()["jornadas"]

    assert del_lunes[0]["labor"] == "instalacion"
    assert del_martes[0]["labor"] == "correctivo"


def test_g_cambiar_el_auxiliar_reescribe_SOLO_ese_dia(
    admin_client, cuadrilla, admin_profile, user_profile
):
    _armar(admin_client, cuadrilla, LUNES, "instalacion",
           [{"profile": str(admin_profile.id), "rol": "ayudante"}])
    _armar(admin_client, cuadrilla, LUNES, "instalacion",
           [{"profile": str(user_profile.id), "rol": "ayudante"}])

    jornada = admin_client.get(JORNADA, {"fecha": LUNES}).json()["jornadas"][0]
    #  Se compara por CUENTA y no por el id del integrante: desde que el
    #  integrante es una `PersonaDeCampo`, su id ya no es el del `Profile`.
    assert ([i["profile"] for i in jornada["integrantes"]]
            == [str(user_profile.id)])


def test_h_una_persona_en_dos_cuadrillas_el_mismo_dia_se_rechaza(
    admin_client, org_a, cuadrilla, admin_profile
):
    """Las dos contarian con ella y una se quedaria corta a la mañana."""
    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    gente = [{"profile": str(admin_profile.id), "rol": "tecnico"}]

    assert _armar(admin_client, cuadrilla, LUNES, "instalacion",
                  gente).status_code == 200
    r = _armar(admin_client, otra, LUNES, "correctivo", gente)

    assert r.status_code == 409
    assert "Cuadrilla 1" in r.json()["detail"], "tiene que decir DONDE está"


def test_i_la_misma_persona_SI_puede_cambiar_de_cuadrilla_mañana(
    admin_client, org_a, cuadrilla, admin_profile
):
    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    gente = [{"profile": str(admin_profile.id), "rol": "tecnico"}]

    _armar(admin_client, cuadrilla, LUNES, "instalacion", gente)
    r = _armar(admin_client, otra, MARTES, "correctivo", gente)
    assert r.status_code == 200, r.content


def test_j_una_labor_que_no_existe_se_rechaza(admin_client, cuadrilla):
    r = _armar(admin_client, cuadrilla, LUNES, "lo_que_sea")
    assert r.status_code == 400
    assert "instalacion" in r.json()["detail"], "dice cuales son las validas"


def test_k_un_tecnico_no_puede_armar_cuadrillas(user_client, cuadrilla):
    """Repartir trabajo es decidir el dia de otras personas."""
    r = user_client.post(CUADRILLAS, {"nombre": "La mia"}, format="json")
    assert r.status_code == 403

    r2 = _armar(user_client, cuadrilla, LUNES, "instalacion")
    assert r2.status_code == 403


def test_l_pero_SI_puede_mirar_quien_trabaja_hoy(user_client, cuadrilla):
    """Mirar no es repartir: el lider tiene que poder ver su propia jornada."""
    assert user_client.get(CUADRILLAS).status_code == 200
    assert user_client.get(JORNADA, {"fecha": LUNES}).status_code == 200


# ---------------------------------------------------------------------------
# C · el historial: quien estuvo con quien, y que dia
# ---------------------------------------------------------------------------

MIERCOLES = "2026-10-07"


def test_m_un_rango_trae_los_dias_en_orden(
    admin_client, cuadrilla, admin_profile
):
    """Lo que antes obligaba a cambiar la fecha de a un dia."""
    gente = [{"profile": str(admin_profile.id), "rol": "tecnico"}]
    _armar(admin_client, cuadrilla, LUNES, "instalacion", gente)
    _armar(admin_client, cuadrilla, MARTES, "instalacion", gente)
    _armar(admin_client, cuadrilla, MIERCOLES, "correctivo", gente)

    r = admin_client.get(JORNADA, {"desde": LUNES, "hasta": MIERCOLES})
    assert r.status_code == 200, r.content
    dias = [(j["fecha"], j["labor"]) for j in r.json()["jornadas"]]
    assert dias == [
        (LUNES, "instalacion"),
        (MARTES, "instalacion"),
        (MIERCOLES, "correctivo"),
    ]


def test_n_el_historial_de_UNA_cuadrilla(
    admin_client, org_a, cuadrilla, admin_profile, user_profile
):
    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    _armar(admin_client, cuadrilla, LUNES, "instalacion",
           [{"profile": str(admin_profile.id), "rol": "tecnico"}])
    _armar(admin_client, otra, LUNES, "correctivo",
           [{"profile": str(user_profile.id), "rol": "tecnico"}])

    r = admin_client.get(JORNADA, {
        "desde": LUNES, "hasta": MIERCOLES, "cuadrilla": str(cuadrilla.id),
    })
    jornadas = r.json()["jornadas"]
    assert [j["cuadrilla"]["nombre"] for j in jornadas] == ["Cuadrilla 1"]


def test_o_con_quien_trabajo_UNA_persona(
    admin_client, org_a, cuadrilla, admin_profile, user_profile
):
    """La vista que contesta «quien estaba en esa instalacion».

    El auxiliar cambia de cuadrilla entre el lunes y el miercoles, y las dos
    cosas tienen que quedar escritas.
    """
    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    _armar(admin_client, cuadrilla, LUNES, "instalacion", [
        {"profile": str(admin_profile.id), "rol": "tecnico_lider"},
        {"profile": str(user_profile.id), "rol": "ayudante"},
    ])
    _armar(admin_client, otra, MIERCOLES, "correctivo", [
        {"profile": str(user_profile.id), "rol": "tecnico"},
    ])

    r = admin_client.get(JORNADA, {
        "desde": LUNES, "hasta": MIERCOLES, "profile": str(user_profile.id),
    })
    jornadas = r.json()["jornadas"]
    assert [(j["fecha"], j["cuadrilla"]["nombre"]) for j in jornadas] == [
        (LUNES, "Cuadrilla 1"),
        (MIERCOLES, "Cuadrilla 2"),
    ]

    # Y el rol que tuvo cada dia viaja: paso de ayudante a tecnico.
    roles = []
    for j in jornadas:
        roles += [i["rol"] for i in j["integrantes"]
                  if i["profile"] == str(user_profile.id)]
    assert roles == ["ayudante", "tecnico"]


def test_p_una_jornada_donde_NO_estuvo_no_aparece(
    admin_client, cuadrilla, admin_profile, user_profile
):
    """Si colara, el historial de una persona diria que estuvo donde no."""
    _armar(admin_client, cuadrilla, LUNES, "instalacion",
           [{"profile": str(admin_profile.id), "rol": "tecnico"}])

    r = admin_client.get(JORNADA, {
        "desde": LUNES, "hasta": MIERCOLES, "profile": str(user_profile.id),
    })
    assert r.json()["jornadas"] == []


def test_q_un_rango_demasiado_largo_se_rechaza(admin_client):
    r = admin_client.get(JORNADA, {"desde": "2026-01-01", "hasta": "2026-12-31"})
    assert r.status_code == 400
    assert "92" in r.json()["detail"], "dice cual es el tope"


def test_r_sin_fecha_ni_rango_lo_dice(admin_client):
    r = admin_client.get(JORNADA)
    assert r.status_code == 400
    assert "desde" in r.json()["detail"]


def test_s_hasta_anterior_a_desde_se_rechaza(admin_client):
    r = admin_client.get(JORNADA, {"desde": MIERCOLES, "hasta": LUNES})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# D · la zona del dia
# ---------------------------------------------------------------------------

def test_t_la_jornada_guarda_las_zonas_que_cubre(admin_client, org_a, cuadrilla):
    from campo.zonas import ZonaOperativa

    norte = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    sur = ZonaOperativa.objects.create(org=org_a, nombre="Sur")

    r = admin_client.post(JORNADA, {
        "cuadrilla": str(cuadrilla.id), "fecha": LUNES,
        "labor": "instalacion", "integrantes": [],
        "zonas": [str(norte.id), str(sur.id)],
    }, format="json")
    assert r.status_code == 200, r.content
    assert {z["nombre"] for z in r.json()["zonas"]} == {"Norte", "Sur"}


def test_u_cambiar_la_zona_el_martes_no_toca_el_lunes(
    admin_client, org_a, cuadrilla
):
    """Igual que la labor: por eso vive en la jornada."""
    from campo.zonas import ZonaOperativa

    norte = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    sur = ZonaOperativa.objects.create(org=org_a, nombre="Sur")

    for fecha, zona in ((LUNES, norte), (MARTES, sur)):
        admin_client.post(JORNADA, {
            "cuadrilla": str(cuadrilla.id), "fecha": fecha,
            "labor": "instalacion", "integrantes": [],
            "zonas": [str(zona.id)],
        }, format="json")

    del_lunes = admin_client.get(JORNADA, {"fecha": LUNES}).json()["jornadas"][0]
    del_martes = admin_client.get(JORNADA, {"fecha": MARTES}).json()["jornadas"][0]
    assert [z["nombre"] for z in del_lunes["zonas"]] == ["Norte"]
    assert [z["nombre"] for z in del_martes["zonas"]] == ["Sur"]


def test_v_una_zona_de_OTRA_empresa_no_entra(
    admin_client, org_b, cuadrilla
):
    """Se ignora en vez de romper el armado: lo que queda escrito es lo que
    de verdad se pudo asignar."""
    from campo.zonas import ZonaOperativa

    ajena = ZonaOperativa.objects.create(org=org_b, nombre="Ajena")
    r = admin_client.post(JORNADA, {
        "cuadrilla": str(cuadrilla.id), "fecha": LUNES,
        "labor": "instalacion", "integrantes": [],
        "zonas": [str(ajena.id)],
    }, format="json")
    assert r.status_code == 200
    assert r.json()["zonas"] == []


def test_w_sin_zonas_la_jornada_se_arma_igual(admin_client, cuadrilla):
    """Vacio es «sin zona asignada», y es un estado valido."""
    r = _armar(admin_client, cuadrilla, LUNES, "instalacion")
    assert r.status_code == 200
    assert r.json()["zonas"] == []
