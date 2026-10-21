# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR PROPONE SI SE TRABAJA UN FERIADO  --  21/10/2026
================================================================================

Decision del usuario: «no todos los festivos se trabaja, eso se define por
cantidad de ticket y eso si lo propone el supervisor». Eligio: el dia habil
ANTERIOR, recomendar si la cola supera un dia de trabajo, y que el horario lo
ponga quien aprueba. Habilidad H-20. Ficha: supervisor-arma-la-jornada.md.

  A  el dia habil anterior propone, con los numeros; recomienda trabajarlo si
     la cola supera lo que sacan las cuadrillas en un dia (la cuenta es del
     codigo)
  B  con la cola chica, propone NO trabajarlo
  C  el dia habil anterior se cuenta con el horario: con el sabado abierto,
     el viernes no propone y el sabado si
  D  no propone: otro dia, un feriado que ya tiene horario, uno que cae en
     un dia que no se trabaja, sin horario de cuadrillas
  E  el texto dice como trabajarlo y entra por `detectar()`

    pytest operaciones/tests/test_el_supervisor_propone_feriados.py
================================================================================
"""

import datetime as dt

import pytest

from campo.cuadrillas import ConfiguracionDeReparto, Cuadrilla
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db

LUNES_FERIADO = dt.date(2026, 11, 16)
#: Viernes 13/11 a las 10:00 de Bogota.
VIERNES_10 = dt.datetime(2026, 11, 13, 15, 0, tzinfo=dt.timezone.utc)
JUEVES_10 = dt.datetime(2026, 11, 12, 15, 0, tzinfo=dt.timezone.utc)
SABADO_10 = dt.datetime(2026, 11, 14, 15, 0, tzinfo=dt.timezone.utc)


def _horario(org, *, sabado=False, feriado_con_horario=False):
    from business_hours.models import BusinessCalendar, BusinessHoliday

    cal = BusinessCalendar.objects.create(org=org, name="Cuadrillas",
                                          timezone="America/Bogota",
                                          is_default=False)
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        setattr(cal, f"{d}_open", dt.time(7, 0))
        setattr(cal, f"{d}_close", dt.time(17, 0))
    if sabado:
        cal.saturday_open, cal.saturday_close = dt.time(7, 0), dt.time(12, 0)
    cal.save()
    BusinessHoliday.objects.create(calendar=cal, org=org, date=LUNES_FERIADO,
                                   name="Independencia de Cartagena")
    ConfiguracionDeReparto.objects.update_or_create(org=org, defaults={
        "calendario_de_cuadrillas": cal, "tope_por_cuadrilla": 8,
        "feriados_trabajados": ({LUNES_FERIADO.isoformat(): {
            "abre": "07:00", "cierra": "12:00"}} if feriado_con_horario else {}),
    })
    return cal


def _cuadrillas(org, n=2):
    for i in range(n):
        Cuadrilla.objects.create(org=org, nombre=f"Cuadrilla #{i + 1}")


def _en_despacho(org, n):
    from cases.models import Case
    for i in range(n):
        caso = Case.objects.create(org=org, name="No Tiene Internet",
                                   status="New", priority="Normal",
                                   is_active=True)
        PropuestaSupervisor.objects.create(
            org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
            origen_tipo="case", origen_id=str(caso.id),
            estado=PropuestaSupervisor.ACEPTADA, accion_propuesta="x",
            motivo="x", evidencia=[{"fuente": "lectura_ticket", "dato": "x",
                                    "momento": "2026-11-13T10:00:00Z"}])


def _feriados(org, ahora):
    return sup._feriados_por_decidir(org, ahora)


# ---------------------------------------------------------------------------
# A · la cola supera un dia: propone trabajarlo
# ---------------------------------------------------------------------------

def test_a_el_dia_habil_anterior_recomienda_trabajarlo(org_a):
    _horario(org_a)
    _cuadrillas(org_a, 2)          # 2 x 8 = 16 por dia
    _en_despacho(org_a, 17)

    [s] = _feriados(org_a, VIERNES_10)
    assert s.tipo == PropuestaSupervisor.FERIADO_POR_DECIDIR
    assert s.origen_id == "2026-11-16" and s.huella == "feriado:2026-11-16"
    assert (s.datos["cola"], s.datos["capacidad"], s.datos["cuadrillas"]) == (17, 16, 2)
    assert s.datos["recomienda"] is True


def test_a2_el_tope_propio_de_una_cuadrilla_cuenta(org_a):
    _horario(org_a)
    _cuadrillas(org_a, 2)
    Cuadrilla.objects.filter(nombre="Cuadrilla #1").update(tope_diario=12)
    _en_despacho(org_a, 17)
    [s] = _feriados(org_a, VIERNES_10)
    assert s.datos["capacidad"] == 20 and s.datos["recomienda"] is False


# ---------------------------------------------------------------------------
# B · la cola entra en un dia: propone no trabajarlo
# ---------------------------------------------------------------------------

def test_b_con_la_cola_chica_propone_no_trabajarlo(org_a):
    _horario(org_a)
    _cuadrillas(org_a, 2)
    _en_despacho(org_a, 3)
    [s] = _feriados(org_a, VIERNES_10)
    assert s.datos["recomienda"] is False


# ---------------------------------------------------------------------------
# C · el dia habil anterior sale del horario
# ---------------------------------------------------------------------------

def test_c_con_el_sabado_abierto_propone_el_sabado(org_a):
    _horario(org_a, sabado=True)
    _cuadrillas(org_a, 1)
    assert _feriados(org_a, VIERNES_10) == []
    assert len(_feriados(org_a, SABADO_10)) == 1


# ---------------------------------------------------------------------------
# D · cuando no propone
# ---------------------------------------------------------------------------

def test_d_otro_dia_no_propone(org_a):
    _horario(org_a)
    _cuadrillas(org_a, 1)
    assert _feriados(org_a, JUEVES_10) == []


def test_d2_un_feriado_que_ya_tiene_horario_no_se_pregunta(org_a):
    _horario(org_a, feriado_con_horario=True)
    _cuadrillas(org_a, 1)
    assert _feriados(org_a, VIERNES_10) == []


def test_d3_un_feriado_en_un_dia_que_no_se_trabaja_no_se_pregunta(org_a):
    from business_hours.models import BusinessHoliday
    cal = _horario(org_a)
    BusinessHoliday.objects.filter(calendar=cal).update(
        date=dt.date(2026, 11, 15))          # domingo, cerrado de todos modos
    _cuadrillas(org_a, 1)
    assert _feriados(org_a, VIERNES_10) == []


def test_d4_sin_horario_de_cuadrillas_no_propone(org_a):
    from business_hours.models import BusinessCalendar, BusinessHoliday
    cal = BusinessCalendar.objects.create(org=org_a, name="Default",
                                          timezone="America/Bogota",
                                          is_default=True,
                                          friday_open=dt.time(7, 0),
                                          friday_close=dt.time(17, 0))
    BusinessHoliday.objects.create(calendar=cal, org=org_a, date=LUNES_FERIADO,
                                   name="Independencia de Cartagena")
    _cuadrillas(org_a, 1)
    assert _feriados(org_a, VIERNES_10) == []


# ---------------------------------------------------------------------------
# E · el texto, y que entra por detectar()
# ---------------------------------------------------------------------------

def test_e_el_texto_dice_los_numeros_y_como_trabajarlo(org_a):
    _horario(org_a)
    _cuadrillas(org_a, 2)
    _en_despacho(org_a, 17)
    [s] = _feriados(org_a, VIERNES_10)
    p = sup.analizar(s)
    assert p["accion_propuesta"] == "Trabajar el feriado del lunes 16/11"
    assert "17 casos" in p["motivo"] and "16 por dia" in p["motivo"]
    assert "07:00-12:00" in p["motivo"]
    assert p["nivel"] == PropuestaSupervisor.NIVEL_RECOMENDAR


def test_e2_entra_por_detectar(org_a):
    _horario(org_a)
    _cuadrillas(org_a, 1)
    tipos = {s.tipo for s in sup.detectar(org_a, VIERNES_10)}
    assert PropuestaSupervisor.FERIADO_POR_DECIDIR in tipos
