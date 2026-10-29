"""
================================================================================
 EL ORDEN DEL DIA  --  29/10/2026
================================================================================
`campo/orden_del_dia.py`: el Supervisor le arma a cada cuadrilla el orden en que
trabaja sus ordenes, la app lo sigue y Programacion muestra el mismo. Pedido del
usuario: «que indique con cual iniciaria la jornada» y «que el mismo Supervisor
le arme el orden en que trabaja los tickets».

  O  el orden: lo empezado primero (en sitio, en camino); lo que falta por
     urgencia (lo vencido, la prioridad, lo que vence antes, el numero).
  G  se guarda con su fecha, solo lo que cambia, y lo urgente que entra pasa
     adelante de lo que no empezo.
  P  Programacion lo muestra igual que la app, con el cliente, cuando vence y
     la siguiente marcada.
  V  el vencimiento: el dia del ticket mas el plazo de su nivel.
  R  la publicacion lo arma en cada vuelta, solo con la tarea delegada.
  K  el comando que completa el vencimiento de las ordenes de antes.

    pytest campo/tests/test_orden_del_dia.py
================================================================================
"""
import datetime as dt
import io
import zoneinfo
from types import SimpleNamespace

import pytest
from django.core.management import call_command

from campo import dia_publicado as D
from campo import orden_del_dia as OD
from campo.cuadrillas import (
    Cuadrilla,
    IntegranteDeJornada,
    JornadaDeCuadrilla,
    PersonaDeCampo,
)
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.zonas import AliasDeZona, ZonaOperativa
from operaciones.ordenes_de_despacho import vencimiento_del_caso

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")
LUNES = dt.date(2026, 10, 5)
AHORA = dt.datetime(2026, 10, 5, 9, 0, tzinfo=BOGOTA)
AYER = AHORA - dt.timedelta(days=1)
TARDE = AHORA + dt.timedelta(hours=6)
MANANA = AHORA + dt.timedelta(days=1)
CLIENTE = "Beatriz Pinzón"


def _o(numero, estado="asignada", prioridad="media", vence=None, lugar=None):
    return SimpleNamespace(numero=numero, estado_operativo=estado, prioridad=prioridad,
                           sla_vence_en=vence, orden_del_dia=lugar,
                           orden_del_dia_fecha=None, created_at=None)


# ---------------------------------------------------------------------------
# O · el orden
# ---------------------------------------------------------------------------

def test_o_lo_empezado_primero_y_lo_que_falta_por_urgencia():
    lista = [_o(1, prioridad="alta", vence=MANANA), _o(2, vence=AYER),
             _o(3, estado="en_sitio", prioridad="baja"), _o(4, prioridad="baja"),
             _o(5, prioridad="alta", vence=TARDE),
             _o(6, estado="completada_campo", prioridad="alta", vence=AYER),
             _o(7, estado="en_camino")]
    #  En sitio, en camino; lo vencido; alta que vence hoy, alta que vence
    #  mañana; baja sin fecha. Lo terminado no tiene lugar.
    assert [o.numero for o in OD.ordenadas(lista, AHORA)] == [3, 7, 2, 5, 1, 4]


def test_o2_lo_mas_atrasado_primero_y_la_prioridad_antes_que_la_fecha():
    lista = [_o(1, vence=AYER), _o(2, vence=AYER - dt.timedelta(days=2)),
             _o(3, prioridad="media", vence=TARDE),
             _o(4, prioridad="alta", vence=MANANA + dt.timedelta(days=2))]
    assert [o.numero for o in OD.ordenadas(lista, AHORA)] == [2, 1, 4, 3]


# ---------------------------------------------------------------------------
# G · guardado
# ---------------------------------------------------------------------------

@pytest.fixture
def version(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    return WorkTypeVersion.objects.create(work_type=wt, version=1,
                                          estado=WorkTypeVersion.PUBLICADA,
                                          esquema={"campos": []})


@pytest.fixture
def cuadrilla(org_a, version, admin_profile):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="MARTHA GISELA")
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla #1")
    j = JornadaDeCuadrilla.objects.create(org=org_a, cuadrilla=c, fecha=LUNES,
                                          labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set([z])
    persona = PersonaDeCampo.objects.create(org=org_a, profile=admin_profile, nombre="Uno")
    IntegranteDeJornada.objects.create(org=org_a, jornada=j, persona=persona, rol="tecnico")
    return j


_numero = iter(range(600, 9999))


def _orden(org, version, de, *, estado=OrdenTrabajo.ASIGNADA, prioridad="media",
           vence=None):
    o = OrdenTrabajo.objects.create(
        org=org, numero=next(_numero), tipo_trabajo_version=version, estado_operativo=estado,
        zona="MARTHA GISELA", prioridad=prioridad, cliente_nombre=CLIENTE, sla_vence_en=vence)
    AsignacionTrabajo.objects.create(orden=o, profile=de, rol="tecnico", es_principal=True)
    return o


def _lugares(*ordenes):
    return [(OrdenTrabajo.objects.get(pk=o.pk).orden_del_dia,
             OrdenTrabajo.objects.get(pk=o.pk).orden_del_dia_fecha) for o in ordenes]


def test_g_se_guarda_con_su_fecha_y_la_segunda_vuelta_no_escribe(
        org_a, version, cuadrilla, admin_profile):
    a = _orden(org_a, version, admin_profile, prioridad="alta", vence=MANANA)
    b = _orden(org_a, version, admin_profile, vence=AYER)
    c = _orden(org_a, version, admin_profile, estado=OrdenTrabajo.EN_SITIO, prioridad="baja")

    assert OD.ordenar(org_a, LUNES, AHORA) == 3
    assert _lugares(c, b, a) == [(1, LUNES), (2, LUNES), (3, LUNES)]
    assert OD.ordenar(org_a, LUNES, AHORA) == 0, "sin cambios no escribe"


def test_g2_lo_urgente_que_entra_pasa_adelante_y_lo_empezado_no_se_mueve(
        org_a, version, cuadrilla, admin_profile):
    a = _orden(org_a, version, admin_profile, prioridad="alta", vence=MANANA)
    c = _orden(org_a, version, admin_profile, estado=OrdenTrabajo.EN_SITIO, prioridad="baja")
    OD.ordenar(org_a, LUNES, AHORA)

    d = _orden(org_a, version, admin_profile, vence=AYER)
    assert OD.ordenar(org_a, LUNES, AHORA) == 2
    assert _lugares(c, d, a) == [(1, LUNES), (2, LUNES), (3, LUNES)]


# ---------------------------------------------------------------------------
# P · Programacion
# ---------------------------------------------------------------------------

def test_p_programacion_muestra_el_orden_el_cliente_cuando_vence_y_la_siguiente(
        org_a, version, cuadrilla, admin_profile):
    a = _orden(org_a, version, admin_profile, prioridad="alta", vence=MANANA)
    b = _orden(org_a, version, admin_profile, vence=AYER)
    c = _orden(org_a, version, admin_profile, estado=OrdenTrabajo.EN_SITIO, prioridad="baja")
    OD.ordenar(org_a, LUNES, AHORA)

    filas = D.del_dia(org_a, LUNES)["cuadrillas"][0]["ordenes"]

    assert [f["numero"] for f in filas] == [c.numero, b.numero, a.numero]
    assert [f["orden_del_dia"] for f in filas] == [1, 2, 3]
    #  La siguiente es la primera que no empezo: la que hace al terminar.
    assert [f["siguiente"] for f in filas] == [False, True, False]
    assert {f["cliente"] for f in filas} == {CLIENTE}
    assert filas[2]["vence_en"].startswith("2026-10-06T09:00:00-05:00")
    assert filas[0]["vence_en"] is None


def test_p2_sin_orden_del_supervisor_ordena_como_la_app_y_lo_de_otro_dia_no_cuenta(
        org_a, version, cuadrilla, admin_profile):
    viejo = _orden(org_a, version, admin_profile, prioridad="alta")
    OrdenTrabajo.objects.filter(pk=viejo.pk).update(orden_del_dia=1,
                                                    orden_del_dia_fecha=LUNES - dt.timedelta(days=1))
    vence = _orden(org_a, version, admin_profile, prioridad="baja", vence=MANANA)

    filas = D.del_dia(org_a, LUNES)["cuadrillas"][0]["ordenes"]

    #  Como la app sin orden de hoy: primero lo que tiene vencimiento, aunque
    #  la otra tenga más prioridad.
    assert [f["numero"] for f in filas] == [vence.numero, viejo.numero]
    assert [f["orden_del_dia"] for f in filas] == [None, None]


# ---------------------------------------------------------------------------
# V · el vencimiento
# ---------------------------------------------------------------------------

def test_v_el_dia_del_ticket_mas_el_plazo_hasta_el_final_del_dia():
    #  En UTC, como llega de la base: las 04:30 del 6 son las 23:30 del 5 en
    #  Bogota, y el dia del ticket es el 5.
    creado = dt.datetime(2026, 10, 6, 4, 30, tzinfo=dt.timezone.utc)
    fin = dt.time(23, 59, 59)
    assert vencimiento_del_caso(creado, nivel={"plazo_dias": 2}, plazo_de_la_plantilla=9,
                                zona=BOGOTA) == dt.datetime.combine(dt.date(2026, 10, 7), fin,
                                                                    tzinfo=BOGOTA)
    #  Sin nivel, el plazo de la plantilla; sin ninguno, o sin fecha, nada.
    assert vencimiento_del_caso(creado, nivel=None, plazo_de_la_plantilla=5,
                                zona=BOGOTA).date() == dt.date(2026, 10, 10)
    assert vencimiento_del_caso(creado, nivel=None, plazo_de_la_plantilla=None,
                                zona=BOGOTA) is None
    assert vencimiento_del_caso(None, nivel={"plazo_dias": 2}, plazo_de_la_plantilla=None,
                                zona=BOGOTA) is None


def test_v2_la_app_recibe_el_orden_del_dia_con_su_fecha(org_a, version, cuadrilla, admin_profile):
    from campo.serializers import _compromiso

    o = _orden(org_a, version, admin_profile)
    OD.ordenar(org_a, LUNES, AHORA)
    o.refresh_from_db()

    compromiso = _compromiso(o)
    assert (compromiso["orden_del_dia"], compromiso["orden_del_dia_fecha"]) == (1, LUNES)


# ---------------------------------------------------------------------------
# R · la publicacion lo arma
# ---------------------------------------------------------------------------

def _publicacion(monkeypatch, puertas):
    from operaciones import publicacion_del_reparto as pub

    monkeypatch.setattr(pub, "cuando", lambda org, ahora: (LUNES, "", ""))
    monkeypatch.setattr(pub, "_puertas", lambda org: puertas)
    monkeypatch.setattr(pub, "propuesta", lambda org, hoy, ahora: {
        "asignaciones": [], "trabajan_hoy": set(), "publicaria": 0, "libera": 0,
        "sobrantes": 0, "sin_cuadrilla": 0, "sin_zona": 0, "sin_nadie_con_cuenta": 0,
        "con_ausentes": 0, "detalle": {}})
    return pub


def test_r_cada_vuelta_publicada_arma_el_orden(org_a, monkeypatch):
    pub = _publicacion(monkeypatch, "")
    pedidos = []
    monkeypatch.setattr(OD, "ordenar", lambda org, fecha, ahora: pedidos.append(fecha) or 4)

    salida = pub.publicar_el_reparto(org_a, AHORA)["reparto_del_dia"]

    assert (salida["modo"], salida["ordenadas"], pedidos) == (pub.PUBLICO, 4, [LUNES])


def test_r2_en_la_sombra_no_escribe_y_si_falla_lo_publicado_queda(org_a, monkeypatch):
    def rompe(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(OD, "ordenar", rompe)
    pub = _publicacion(monkeypatch, "nadie le delegó al Supervisor que publique")
    assert pub.publicar_el_reparto(org_a, AHORA)["reparto_del_dia"]["modo"] == pub.SOMBRA

    pub = _publicacion(monkeypatch, "")
    salida = pub.publicar_el_reparto(org_a, AHORA)["reparto_del_dia"]
    assert (salida["modo"], salida["ordenadas"]) == (pub.PUBLICO, 0)


# ---------------------------------------------------------------------------
# K · el comando de las ordenes de antes
# ---------------------------------------------------------------------------

def test_k_completa_solo_las_vivas_del_supervisor_sin_vencimiento(org_a, version, admin_profile):
    from cases.models import Case

    WorkType.objects.filter(pk=version.work_type_id).update(plazo_dias=2)
    caso = Case.objects.create(org=org_a, name="Sin internet", status="New", priority="Normal",
                               is_active=True)
    Case.objects.filter(pk=caso.pk).update(created_at=dt.datetime(2026, 10, 1, 10, 0, tzinfo=BOGOTA))

    def orden(**k):
        o = _orden(org_a, version, admin_profile, **k)
        OrdenTrabajo.objects.filter(pk=o.pk).update(origen_tipo="case", origen_ref=str(caso.id))
        return o

    sin = orden()
    con = orden(vence=MANANA)
    terminada = orden(estado=OrdenTrabajo.COMPLETADA_CAMPO)

    salida = io.StringIO()
    call_command("completar_vencimientos", org=str(org_a.id), stdout=salida)
    assert "Se completarían 1 de 1" in salida.getvalue()
    assert OrdenTrabajo.objects.get(pk=sin.pk).sla_vence_en is None, "un simulacro no escribe"

    call_command("completar_vencimientos", org=str(org_a.id), aplicar=True, stdout=io.StringIO())
    assert OrdenTrabajo.objects.get(pk=sin.pk).sla_vence_en == dt.datetime(
        2026, 10, 3, 23, 59, 59, tzinfo=BOGOTA)
    assert OrdenTrabajo.objects.get(pk=con.pk).sla_vence_en == MANANA, "no pisa una fecha"
    assert OrdenTrabajo.objects.get(pk=terminada.pk).sla_vence_en is None
