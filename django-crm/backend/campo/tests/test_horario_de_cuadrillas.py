# -*- coding: utf-8 -*-
"""
================================================================================
 EL HORARIO DE LAS CUADRILLAS NO ES EL DE ATENCION AL CLIENTE  --  21/10/2026
================================================================================

Pedido del usuario: «ese horario seria de CRM atencion al cliente». El
Supervisor leia el calendario por defecto para saber cuando trabajan las
cuadrillas. Ficha: supervisor-arma-la-jornada.md (decision del 21/10).

  A  guardar crea un calendario PROPIO, que no es el por defecto, y el de
     atencion al cliente no cambia
  B  con el horario cargado, la jornada de campo sale de el
  C  sin el: lo que ya corria sigue con el por defecto (sin cambio de
     conducta); lo que el Supervisor hace solo recibe la jornada cerrada con
     su motivo, y el armado horario no corre y lo dice
  D  lo mal escrito no se guarda, y no deja nada a medias
  E  los feriados se reemplazan enteros, y un feriado cierra el dia
  F  la hora de corte se guarda y se lee
  G  cambiarlo exige un rol de gestion

    pytest campo/tests/test_horario_de_cuadrillas.py
================================================================================
"""

import datetime as dt

import pytest

from business_hours.models import BusinessCalendar
from campo import horario_de_cuadrillas as H
from operaciones import capacidad

pytestmark = pytest.mark.django_db

RUTA = "/api/campo/cuadrillas/horario/"
MARTES = dt.date(2026, 10, 6)
SEMANA_7_A_17 = {d: {"abre": "07:00", "cierra": "17:00"}
                 for d in ("lunes", "martes", "miercoles", "jueves", "viernes")}


def _atencion_al_cliente(org):
    """El calendario por defecto, como esta en produccion: UTC, 09 a 17."""
    cal = BusinessCalendar.objects.create(org=org, name="Default",
                                          timezone="UTC", is_default=True)
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        setattr(cal, f"{d}_open", dt.time(9, 0))
        setattr(cal, f"{d}_close", dt.time(17, 0))
    cal.save()
    return cal


def _guardar(cliente, **extra):
    return cliente.put(RUTA, {"zona_horaria": "America/Bogota",
                              "dias": SEMANA_7_A_17, **extra}, format="json")


# ---------------------------------------------------------------------------
# A · un calendario propio
# ---------------------------------------------------------------------------

def test_a_guardar_crea_uno_propio_y_no_toca_el_de_atencion(admin_client, org_a):
    atencion = _atencion_al_cliente(org_a)
    r = _guardar(admin_client)
    assert r.status_code == 200, r.content
    assert r.json()["configurado"] is True

    propio = H.calendario_de_cuadrillas(org_a)
    assert propio is not None and propio.pk != atencion.pk
    assert propio.is_default is False and propio.timezone == "America/Bogota"
    atencion.refresh_from_db()
    assert atencion.timezone == "UTC" and atencion.monday_open == dt.time(9, 0)


# ---------------------------------------------------------------------------
# B · la jornada de campo sale del horario de las cuadrillas
# ---------------------------------------------------------------------------

def test_b_con_el_horario_la_jornada_es_la_de_las_cuadrillas(admin_client, org_a):
    _atencion_al_cliente(org_a)
    _guardar(admin_client, dias={**SEMANA_7_A_17,
                                 "sabado": {"abre": "07:00", "cierra": "12:00"}})

    martes = capacidad.jornada_de(org_a, MARTES)
    assert martes.abierta and martes.apertura == dt.time(7, 0)
    assert martes.zona_horaria == "America/Bogota"
    #  El sabado: cerrado en atencion al cliente, abierto para las cuadrillas.
    sabado = capacidad.jornada_de(org_a, MARTES + dt.timedelta(days=4))
    assert sabado.abierta and sabado.cierre == dt.time(12, 0)


# ---------------------------------------------------------------------------
# C · sin el horario
# ---------------------------------------------------------------------------

def test_c_sin_el_horario_lo_que_ya_corria_sigue_igual(org_a):
    _atencion_al_cliente(org_a)
    j = capacidad.jornada_de(org_a, MARTES)
    assert j.abierta and j.apertura == dt.time(9, 0) and j.zona_horaria == "UTC"


def test_c2_lo_que_hace_el_supervisor_solo_no_corre_y_lo_dice(org_a):
    from operaciones import armado_de_jornadas as adj

    _atencion_al_cliente(org_a)
    j = capacidad.jornada_de(org_a, MARTES, solo_de_cuadrillas=True)
    assert not j.abierta and j.motivo == capacidad.SIN_HORARIO_DE_CUADRILLAS

    a_las_10 = dt.datetime(2026, 10, 6, 15, 0, tzinfo=dt.timezone.utc)
    porque, _ = adj._la_empresa_trabaja(org_a, MARTES, a_las_10)
    assert "horario de las cuadrillas" in porque


def test_c3_con_el_horario_el_armado_si_corre(admin_client, org_a):
    from operaciones import armado_de_jornadas as adj

    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    _atencion_al_cliente(org_a)
    _guardar(admin_client)
    a_las_10 = dt.datetime(2026, 10, 6, 15, 0, tzinfo=dt.timezone.utc)
    porque, aviso = adj._la_empresa_trabaja(org_a, MARTES, a_las_10)
    assert porque == "" and aviso == ""


# ---------------------------------------------------------------------------
# D · lo mal escrito no se guarda
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cuerpo", [
    {"zona_horaria": "Bogota/Inventada", "dias": SEMANA_7_A_17},
    {"zona_horaria": "America/Bogota",
     "dias": {"lunes": {"abre": "17:00", "cierra": "07:00"}}},
    {"zona_horaria": "America/Bogota", "dias": {}},
    {"zona_horaria": "America/Bogota", "dias": {"lunes": {"abre": "7am",
                                                          "cierra": "17:00"}}},
    {"zona_horaria": "America/Bogota", "dias": SEMANA_7_A_17,
     "feriados": [{"fecha": "25/12/2026", "nombre": "Navidad"}]},
], ids=["zona", "cierra_antes", "ningun_dia", "hora", "feriado"])
def test_d_lo_mal_escrito_no_se_guarda(admin_client, org_a, cuerpo):
    r = admin_client.put(RUTA, cuerpo, format="json")
    assert r.status_code == 400, r.content
    assert r.json()["detail"]
    assert H.calendario_de_cuadrillas(org_a) is None
    assert not BusinessCalendar.objects.filter(org=org_a).exists()


# ---------------------------------------------------------------------------
# E · feriados
# ---------------------------------------------------------------------------

def test_e_los_feriados_se_reemplazan_y_cierran_el_dia(admin_client, org_a):
    _guardar(admin_client, feriados=[{"fecha": "2026-10-06", "nombre": "Prueba"},
                                     {"fecha": "2026-12-25", "nombre": "Navidad"}])
    assert not capacidad.jornada_de(org_a, MARTES).abierta

    r = _guardar(admin_client, feriados=[{"fecha": "2026-12-25",
                                          "nombre": "Navidad"}])
    assert [f["fecha"] for f in r.json()["feriados"]] == ["2026-12-25"]
    assert capacidad.jornada_de(org_a, MARTES).abierta


# ---------------------------------------------------------------------------
# F · hora de corte
# ---------------------------------------------------------------------------

def test_f_la_hora_de_corte_se_guarda_y_se_lee(admin_client, org_a):
    _guardar(admin_client, hora_de_corte="14:00")
    d = admin_client.get(RUTA).json()
    assert d["hora_de_corte"] == "14:00"
    assert d["dias"]["martes"] == {"abre": "07:00", "cierra": "17:00"}
    assert d["dias"]["domingo"] is None


# ---------------------------------------------------------------------------
# G · permisos
# ---------------------------------------------------------------------------

def test_g_cambiarlo_exige_gestion(user_client, org_a):
    r = _guardar(user_client)
    assert r.status_code == 403, r.content
    assert H.calendario_de_cuadrillas(org_a) is None
