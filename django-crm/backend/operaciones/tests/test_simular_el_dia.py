# -*- coding: utf-8 -*-
"""
================================================================================
 SIMULAR EL DIA  --  24/10/2026
================================================================================

`operaciones.simulacion_del_dia.simular`: arma las cuadrillas, crea en memoria
las ordenes de Despacho y las reparte, sin escribir nada. Afirma:

  S  que cada orden nueva cae en la cuadrilla de su labor y su zona, con su
     ticket, y que la cuadrilla sale con la gente que armaria el Supervisor
  T  que el tope se respeta y lo que no entra se nombra
  L  que lo de una labor sin cuadrilla ese dia se nombra con su labor y zona
  E  que las ordenes que ya esperan entran al mismo reparto
  M  que lo que entro despues de la hora de corte no sale hoy
  N  que no escribe nada ni le pregunta al motor, que un dia cerrado lo dice,
     y que la pantalla la pide solo quien gestiona
  A  lo que encontro la auditoria del 24/10: el desempate con el numero que
     tendria, las cuadrillas que no salen, la labor reajustada, un dia
     futuro, las cuentas, el tope de la empresa, sin hora de corte, y las
     jornadas que el plan no mira (dia cerrado, cuadrilla inactiva)

    pytest operaciones/tests/test_simular_el_dia.py
================================================================================
"""
import datetime as dt
from unittest import mock

import pytest

from campo.cuadrillas import ConfiguracionDeReparto, Cuadrilla, JornadaDeCuadrilla
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from cases.models import Case
from operaciones import paso_a_despacho as pad
from operaciones.models import PropuestaSupervisor as P
from operaciones.simulacion_del_dia import simular
from operaciones.tests import test_el_supervisor_arma_la_jornada as _arma
from operaciones.tests.test_el_supervisor_arma_la_jornada import (
    BARRIO,
    MARTES,
    _en_despacho,
)

#  Las fixtures del armado de la jornada (la empresa en Bogota con su horario,
#  SOLEDAD y la Cuadrilla #1 con su jornada del lunes), las mismas, sin copiarlas.
empresa = _arma.empresa
soledad = _arma.soledad
cuadrilla = _arma.cuadrilla

pytestmark = pytest.mark.django_db

#: Martes 06/10/2026 a las 15:00 de Bogota.
A_LAS_3 = dt.datetime(2026, 10, 6, 20, 0, tzinfo=dt.timezone.utc)
SIMULACION = "/api/operaciones/dia/simulacion/"


@pytest.fixture
def con_corte(empresa):
    ConfiguracionDeReparto.objects.filter(org=empresa).update(
        hora_de_corte=dt.time(12, 0))
    return empresa


def _plantilla(org, codigo, labor, asuntos):
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo.title(),
                                   labor=labor, asuntos=list(asuntos))
    return WorkTypeVersion.objects.create(
        work_type=tipo, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [{"id": "x", "tipo": "texto"}]})


@pytest.fixture
def plantillas(empresa):
    return {
        "soporte": _plantilla(empresa, "soporte", "correctivo",
                              ["No tiene internet"]),
        "red": _plantilla(empresa, "red", "trabajos", ["Corte de fibra"]),
    }


def _caso(org, grupo=pad.FALLA_DE_SERVICIO, *, asunto=None, entro=None,
          barrio=BARRIO):
    """Un caso en Despacho que entro a las 9 de la mañana del martes.
    `barrio` None = todavia nadie le pidio el barrio al motor."""
    caso = _en_despacho(org, grupo, barrio=barrio)
    cambios = {"created_at": A_LAS_3 - dt.timedelta(days=1)}
    if asunto:
        cambios["name"] = asunto
    Case.objects.filter(pk=caso.pk).update(**cambios)
    P.objects.filter(origen_id=str(caso.id)).update(
        revisado_en=entro or dt.datetime(2026, 10, 6, 14, 0, tzinfo=dt.timezone.utc))
    caso.refresh_from_db()
    return caso


def _de(salida, nombre="Cuadrilla #1"):
    return next(c for c in salida["cuadrillas"] if c["cuadrilla"] == nombre)


# ---------------------------------------------------------------------------
# S · arma, crea y reparte
# ---------------------------------------------------------------------------

def test_s_cada_orden_nueva_va_a_su_cuadrilla(con_corte, cuadrilla, plantillas):
    a, b = _caso(con_corte), _caso(con_corte)

    s = simular(con_corte, MARTES, A_LAS_3)

    assert s["trabaja"] is True
    c = _de(s)
    assert (c["carga"], c["tope"]) == (2, 8)
    assert {o["ticket"] for o in c["ordenes"]} == {
        a.external_ticket_id, b.external_ticket_id}
    assert all(o["nueva"] and o["plantilla"] == "Soporte" for o in c["ordenes"])
    #  La gente que armaria el Supervisor: la de su ultima jornada.
    assert sorted(g["nombre"] for g in c["gente"]) == ["PABLO", "PEDRO"]
    assert s["cuentas"]["nuevas"] == s["cuentas"]["repartidas"] == 2
    assert (s["cuentas"]["repartidas_nuevas"],
            s["cuentas"]["repartidas_existentes"]) == (2, 0)


# ---------------------------------------------------------------------------
# T · el tope
# ---------------------------------------------------------------------------

def test_t_lo_que_no_entra_por_el_tope_se_nombra(con_corte, cuadrilla, plantillas):
    Cuadrilla.objects.filter(pk=cuadrilla.pk).update(tope_diario=1)
    _caso(con_corte)
    _caso(con_corte)

    s = simular(con_corte, MARTES, A_LAS_3)

    assert (_de(s)["carga"], _de(s)["tope"]) == (1, 1)
    assert len(s["fuera"]["sobrantes"]) == 1


def test_t2_con_el_tope_lleno_entra_la_mas_urgente(con_corte, cuadrilla, empresa):
    """La nueva Alta le gana el lugar a una mas vieja pero Baja: el reparto las
    ordena con la prioridad que les pone la regla del 23/10."""
    Cuadrilla.objects.filter(pk=cuadrilla.pk).update(tope_diario=1)
    tipo = WorkType.objects.create(org=empresa, codigo="soporte", nombre="Soporte",
                                   labor="correctivo", plazo_dias=0,
                                   asuntos=["No tiene internet"])
    WorkTypeVersion.objects.create(work_type=tipo, version=1,
                                   estado=WorkTypeVersion.PUBLICADA,
                                   esquema={"campos": [{"id": "x", "tipo": "texto"}]})
    tipo = WorkType.objects.create(org=empresa, codigo="traslado", nombre="Traslado",
                                   labor="correctivo", plazo_dias=30,
                                   asuntos=["Cambio de domicilio"])
    WorkTypeVersion.objects.create(work_type=tipo, version=1,
                                   estado=WorkTypeVersion.PUBLICADA,
                                   esquema={"campos": [{"id": "x", "tipo": "texto"}]})
    vieja_y_baja = _caso(con_corte, asunto="Cambio de domicilio")
    Case.objects.filter(pk=vieja_y_baja.pk).update(
        created_at=A_LAS_3 - dt.timedelta(days=3))
    nueva_y_alta = _caso(con_corte, asunto="No tiene internet")

    s = simular(con_corte, MARTES, A_LAS_3)

    [o] = _de(s)["ordenes"]
    assert (o["ticket"], o["prioridad"]) == (nueva_y_alta.external_ticket_id, "alta")
    assert [x["ticket"] for x in s["fuera"]["sobrantes"]] == [
        vieja_y_baja.external_ticket_id]


# ---------------------------------------------------------------------------
# L · la labor
# ---------------------------------------------------------------------------

def test_l_una_labor_sin_cuadrilla_ese_dia_se_nombra(con_corte, cuadrilla, plantillas):
    _caso(con_corte)
    _caso(con_corte)
    red = _caso(con_corte, pad.OBRA_DE_RED, asunto="Corte de fibra")

    s = simular(con_corte, MARTES, A_LAS_3)

    #  La unica cuadrilla sale en la labor de la mayoria: la obra de red no
    #  tiene quien la haga ese dia, y no se le da a la de soporte.
    assert red.external_ticket_id not in {o["ticket"] for o in _de(s)["ordenes"]}
    fuera = s["fuera"]["sin_cuadrilla"]
    assert [(f["ticket"], f["labor"], f["zona"]) for f in fuera] == [
        (red.external_ticket_id, "Trabajos", "SOLEDAD")]


# ---------------------------------------------------------------------------
# E · las que ya esperan
# ---------------------------------------------------------------------------

def test_e_la_orden_que_ya_existe_entra_al_mismo_reparto(
        con_corte, cuadrilla, plantillas):
    caso = _caso(con_corte)
    OrdenTrabajo.objects.create(
        org=con_corte, numero=501, tipo_trabajo_version=plantillas["soporte"],
        estado_operativo=OrdenTrabajo.ASIGNADA, zona=BARRIO,
        origen_sistema="crm", origen_ref=str(caso.id))

    s = simular(con_corte, MARTES, A_LAS_3)

    [o] = _de(s)["ordenes"]
    assert (o["nueva"], o["orden"], o["ticket"]) == (
        False, 501, caso.external_ticket_id)
    #  Y no se crea una segunda para el mismo caso.
    assert s["cuentas"]["nuevas"] == 0
    assert (s["cuentas"]["ya_esperaban"], s["cuentas"]["repartidas_existentes"],
            s["cuentas"]["repartidas_nuevas"]) == (1, 1, 0)


# ---------------------------------------------------------------------------
# M · la hora de corte
# ---------------------------------------------------------------------------

def test_m_lo_que_entro_despues_del_corte_sale_mañana(
        con_corte, cuadrilla, plantillas):
    #  13:00 de Bogota: despues del corte de las 12.
    _caso(con_corte, entro=dt.datetime(2026, 10, 6, 18, 0, tzinfo=dt.timezone.utc))

    s = simular(con_corte, MARTES, A_LAS_3)

    assert _de(s)["carga"] == 0
    assert s["cuentas"]["nuevas_para_otro_dia"] == 1


# ---------------------------------------------------------------------------
# N · lo que no hace
# ---------------------------------------------------------------------------

def test_n_no_escribe_ni_le_pregunta_al_motor(con_corte, cuadrilla, plantillas):
    _caso(con_corte)
    _caso(con_corte, pad.OBRA_DE_RED, asunto="Corte de fibra")
    #  Uno SIN barrio: es al que la fase de cada hora le pediria el barrio.
    _caso(con_corte, barrio=None)
    antes = (OrdenTrabajo.objects.count(), JornadaDeCuadrilla.objects.count(),
             AsignacionTrabajo.objects.count(),
             list(P.objects.order_by("id").values_list("evidencia", flat=True)))

    #  Se CUENTAN las llamadas: un AssertionError adentro se lo traga el
    #  `except Exception` de `leer_localidad` (auditoria del 24/10/2026).
    with mock.patch("campo.services.despacho.contexto_del_caso",
                    return_value={}) as motor:
        s = simular(con_corte, MARTES, A_LAS_3)

    assert motor.call_count == 0
    assert s["cuentas"]["repartidas"] == 1
    assert (OrdenTrabajo.objects.count(), JornadaDeCuadrilla.objects.count(),
            AsignacionTrabajo.objects.count(),
            list(P.objects.order_by("id").values_list("evidencia", flat=True))
            ) == antes


def test_n2_un_dia_que_no_se_trabaja_lo_dice(con_corte, cuadrilla, plantillas):
    _caso(con_corte)
    sabado = dt.date(2026, 10, 10)

    s = simular(con_corte, sabado, A_LAS_3)

    assert s["trabaja"] is False
    assert s["porque"]
    assert s["cuadrillas"] == []


def test_n3_la_pantalla_la_pide_quien_gestiona(
        admin_client, user_client, con_corte, cuadrilla, plantillas):
    r = admin_client.get(SIMULACION, {"fecha": MARTES.isoformat()})
    assert r.status_code == 200
    assert r.json()["fecha"] == MARTES.isoformat()
    assert admin_client.get(SIMULACION, {"fecha": "mal"}).status_code == 400
    assert user_client.get(SIMULACION).status_code == 403


# ---------------------------------------------------------------------------
# A · lo que encontro la auditoria del 24/10/2026
# ---------------------------------------------------------------------------

def test_a_en_un_empate_gana_la_que_ya_existia(con_corte, cuadrilla, plantillas):
    """La nueva lleva el numero que tendria creada de verdad (el siguiente):
    sin el, valia 0 y le ganaba el lugar a la vieja en un empate."""
    Cuadrilla.objects.filter(pk=cuadrilla.pk).update(tope_diario=1)
    con_orden = _caso(con_corte)
    OrdenTrabajo.objects.create(
        org=con_corte, numero=501, tipo_trabajo_version=plantillas["soporte"],
        estado_operativo=OrdenTrabajo.ASIGNADA, zona=BARRIO,
        prioridad=OrdenTrabajo.PRIORIDAD_MEDIA,
        origen_sistema="crm", origen_ref=str(con_orden.id))
    nuevo = _caso(con_corte)            # un dia esperando, sin plazo: media

    s = simular(con_corte, MARTES, A_LAS_3)

    assert [o["orden"] for o in _de(s)["ordenes"]] == [501]
    assert [o["ticket"] for o in s["fuera"]["sobrantes"]] == [nuevo.external_ticket_id]


def test_a2_la_cuadrilla_que_no_sale_se_nombra(
        con_corte, cuadrilla, plantillas, user_profile):
    Cuadrilla.objects.create(org=con_corte, nombre="Cuadrilla #2",
                             lider=user_profile, labor_habitual="correctivo")
    _caso(con_corte)

    s = simular(con_corte, MARTES, A_LAS_3)

    assert s["no_salen"] == [{"cuadrilla": "Cuadrilla #2",
                              "porque": "No se arma: no tiene zonas habituales"}]
    assert [c["cuadrilla"] for c in s["cuadrillas"]] == ["Cuadrilla #1"]


def test_a3_la_jornada_que_el_supervisor_reajusta_sale_con_la_labor_nueva(
        con_corte, cuadrilla, soledad, plantillas):
    hoy = JornadaDeCuadrilla.objects.create(
        org=con_corte, cuadrilla=cuadrilla, fecha=MARTES, labor="instalacion",
        armada_por=JornadaDeCuadrilla.AUTOMATICA)
    hoy.zonas.set([soledad])
    _caso(con_corte)
    _caso(con_corte)

    s = simular(con_corte, MARTES, A_LAS_3)

    c = _de(s)
    assert (c["carga"], c["que_haria"]) == (2, "Ya está armada: le cambia la labor")
    assert s["fuera"]["sin_cuadrilla"] == []


def test_a4_un_dia_futuro_no_repite_lo_que_sale_hoy(con_corte, cuadrilla, plantillas):
    _caso(con_corte)                    # entro antes del corte: sale el martes

    miercoles = simular(con_corte, MARTES + dt.timedelta(days=1), A_LAS_3)

    assert _de(miercoles)["carga"] == 0
    assert miercoles["cuentas"]["nuevas_para_otro_dia"] == 1


def test_a5_lo_asignado_a_mano_se_cuenta_como_lo_que_ya_tiene(
        con_corte, cuadrilla, plantillas, admin_profile):
    from campo.models import EventoTrabajo

    caso = _caso(con_corte)
    orden = OrdenTrabajo.objects.create(
        org=con_corte, numero=601, tipo_trabajo_version=plantillas["soporte"],
        estado_operativo=OrdenTrabajo.ASIGNADA, zona=BARRIO,
        origen_sistema="crm", origen_ref=str(caso.id))
    AsignacionTrabajo.objects.create(orden=orden, profile=admin_profile,
                                     rol="tecnico", es_principal=True)
    EventoTrabajo.objects.create(org=con_corte, orden=orden, tipo="asignacion")

    s = simular(con_corte, MARTES, A_LAS_3)

    #  El lider de la #1 la tiene: no la mueve el reparto, pero es su carga.
    assert (_de(s)["carga"], _de(s)["ya_tiene"]) == (0, 1)
    assert s["cuentas"]["a_mano"] == 1


def test_a6_el_tope_de_la_empresa(con_corte, cuadrilla, plantillas):
    ConfiguracionDeReparto.objects.filter(org=con_corte).update(tope_por_cuadrilla=3)
    _caso(con_corte)

    assert _de(simular(con_corte, MARTES, A_LAS_3))["tope"] == 3


def test_a7_sin_hora_de_corte_lo_dice_y_no_crea(con_corte, cuadrilla, plantillas):
    ConfiguracionDeReparto.objects.filter(org=con_corte).update(hora_de_corte=None)
    _caso(con_corte)

    s = simular(con_corte, MARTES, A_LAS_3)

    assert "hora de corte" in s["sin_crear_porque"]
    assert s["cuentas"]["nuevas"] == 0


def test_a8_un_dia_cerrado_muestra_la_jornada_armada_a_mano(
        con_corte, cuadrilla, soledad, plantillas):
    """Publicar le da trabajo igual: la simulacion tambien."""
    sabado = dt.date(2026, 10, 10)
    j = JornadaDeCuadrilla.objects.create(org=con_corte, cuadrilla=cuadrilla,
                                          fecha=sabado, labor="correctivo")
    j.zonas.set([soledad])
    caso = _caso(con_corte)
    OrdenTrabajo.objects.create(
        org=con_corte, numero=701, tipo_trabajo_version=plantillas["soporte"],
        estado_operativo=OrdenTrabajo.ASIGNADA, zona=BARRIO,
        origen_sistema="crm", origen_ref=str(caso.id))

    s = simular(con_corte, sabado, A_LAS_3)

    assert s["trabaja"] is False and s["porque"]
    assert [o["orden"] for o in _de(s)["ordenes"]] == [701]


def test_a9_la_jornada_de_una_cuadrilla_inactiva_tambien_recibe(
        con_corte, cuadrilla, soledad, plantillas):
    inactiva = Cuadrilla.objects.create(org=con_corte, nombre="Cuadrilla #0",
                                        activa=False)
    j = JornadaDeCuadrilla.objects.create(org=con_corte, cuadrilla=inactiva,
                                          fecha=MARTES, labor="correctivo")
    j.zonas.set([soledad])
    _caso(con_corte)
    _caso(con_corte)

    s = simular(con_corte, MARTES, A_LAS_3)

    cero = _de(s, "Cuadrilla #0")
    assert cero["que_haria"] == "Ya está armada (la cuadrilla está inactiva)"
    #  El reparto les da una a cada una: la menos cargada, y en empate, la
    #  primera por nombre -- igual que «Cómo quedaría la jornada».
    assert (cero["carga"], _de(s)["carga"]) == (1, 1)
