# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR ARMA LA JORNADA DEL DIA  --  17/10/2026
================================================================================

LO QUE AFIRMA
-------------
Que la fase del ciclo (`operaciones.armado_de_jornadas`):

  - sin la tarea delegada, o sin el nivel, o con el interruptor del motor
    detenido, NO escribe ninguna jornada y dice lo que armaria (la sombra);
  - con las tres puertas, la arma;
  - un dia que la empresa no trabaja, o despues de su cierre, no corre ni le
    pregunta nada al ISP;
  - le pide el barrio de cada caso de Despacho al motor UNA vez, con tope por
    vuelta, y reintenta solo lo que corresponde;
  - cuenta cada caso en su zona y con la labor de su grupo, y separa los que
    no puede contar;
  - corre dentro de `correr_ciclo`;
  - no deja en el log ni el barrio ni el cliente.

Cada prueba siembra lo que NO tiene que pasar junto a lo que si: un verde con
la cola vacia no diria nada.
================================================================================
"""
import datetime as dt
import logging
import uuid

import pytest
from django.utils import timezone

from campo.cuadrillas import (
    Cuadrilla,
    IntegranteDeJornada,
    JornadaDeCuadrilla,
    PersonaDeCampo,
)
from campo.zonas import AliasDeZona, ZonaOperativa
from cases.models import Case
from operaciones import armado_de_jornadas as adj
from operaciones import paso_a_despacho as pad
from operaciones import tareas_delegadas as td
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)
MARTES = dt.date(2026, 10, 6)
#: Martes 06/10 a las 10:00 de Bogota.
A_LAS_10 = dt.datetime(2026, 10, 6, 15, 0, tzinfo=dt.timezone.utc)
CLIENTE = "Zoraida Clientela"
BARRIO = "SOLEDAD CENTRO"


@pytest.fixture
def empresa(org_a):
    """Bogota, de 07:00 a 17:00 de lunes a viernes."""
    from business_hours.models import BusinessCalendar

    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    cal = BusinessCalendar.objects.create(org=org_a, name="Default",
                                          timezone="America/Bogota",
                                          is_default=True)
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        setattr(cal, f"{d}_open", dt.time(7, 0))
        setattr(cal, f"{d}_close", dt.time(17, 0))
    cal.save()
    #  Y es el HORARIO DE LAS CUADRILLAS (21/10/2026): sin el, el Supervisor
    #  no arma solo. Aca es la misma fila, para que lo que estas pruebas miden
    #  --el reloj, la apertura, el cierre-- siga siendo lo mismo.
    from campo.cuadrillas import ConfiguracionDeReparto
    ConfiguracionDeReparto.objects.update_or_create(
        org=org_a, defaults={"calendario_de_cuadrillas": cal})
    return org_a


@pytest.fixture
def soledad(empresa):
    z = ZonaOperativa.objects.create(org=empresa, nombre="SOLEDAD")
    AliasDeZona.objects.create(org=empresa, zona=z, localidad=BARRIO)
    return z


@pytest.fixture
def cuadrilla(empresa, admin_profile, soledad):
    """La #1: cubre SOLEDAD, es de instalacion, y el lunes salio con su pareja."""
    c = Cuadrilla.objects.create(org=empresa, nombre="Cuadrilla #1",
                                 lider=admin_profile, labor_habitual="instalacion")
    c.zonas_habituales.set([soledad])
    lunes = JornadaDeCuadrilla.objects.create(
        org=empresa, cuadrilla=c, fecha=LUNES, labor="instalacion")
    lunes.zonas.set([soledad])
    for nombre in ("PEDRO", "PABLO"):
        IntegranteDeJornada.objects.create(
            org=empresa, jornada=lunes, rol="tecnico",
            persona=PersonaDeCampo.objects.create(org=empresa, nombre=nombre))
    return c


def _en_despacho(org, grupo, *, barrio=None, status="Assigned"):
    """Un caso en la cola de Despacho: abierto y con su propuesta aceptada.

    `barrio` None = todavia nadie lo pidio; cadena = ya guardado.
    """
    caso = Case.objects.create(
        org=org, name="No tiene internet", status=status, priority="Normal",
        is_active=True, provider="wisphub", area="soporte_tecnico",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id=f"s{uuid.uuid4().hex[:6]}",
        external_client_name=CLIENTE)
    ahora = timezone.now().isoformat()
    evidencia = [{"fuente": pad.FUENTE_DE_LA_LECTURA, "id": str(caso.id),
                  "dato": "lectura", "observado_en": ahora, "grupo": grupo}]
    if barrio is not None:
        #  'cliente_nuevo' como lo guarda el codigo desde el 18/10/2026: una
        #  pieza sin la marca se vuelve a pedir una vez (ver test_cn4).
        evidencia.append({"fuente": adj.FUENTE_LOCALIDAD, "id": str(caso.id),
                          "dato": "barrio", "observado_en": ahora,
                          "localidad": barrio, "motivo": "",
                          "cliente_nuevo": False})
    P.objects.create(
        org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(caso.id), estado=P.ACEPTADA, revisado_en=timezone.now(),
        accion_propuesta="Revisar el servicio", motivo="x", prioridad=30,
        evidencia=evidencia)
    return caso


class _Motor:
    """El motor, de mentira: responde un barrio fijo y cuenta las preguntas."""

    def __init__(self, respuesta=(BARRIO, "")):
        self.respuesta = respuesta
        self.preguntas = []

    def __call__(self, caso_id):
        self.preguntas.append(str(caso_id))
        return self.respuesta


def _delegar_y_autorizar(org, perfil, monkeypatch):
    """Las tres puertas abiertas, por el camino real salvo el interruptor del
    motor, que en la base de pruebas no existe."""
    from operaciones import autonomia

    td.delegar(org, td.ARMAR_LA_JORNADA, actor=perfil,
               pedido_textual="arma la jornada de cada dia")
    autonomia.cambiar(org, 3, actor=perfil,
                      motivo="armar la jornada del dia",
                      criterios="sombra comparada dos dias")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))


# ---------------------------------------------------------------------------
# A · las puertas
# ---------------------------------------------------------------------------

def test_a_sin_la_tarea_delegada_queda_en_sombra_y_NO_escribe(
    empresa, cuadrilla
):
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO)

    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=_Motor())["jornadas_del_dia"]

    assert r["modo"] == adj.SOMBRA
    assert "delego" in r["porque"]
    #  Dice lo que armaria: la falla de SOLEDAD inclina a la #1 a correctivo.
    assert r["resultado"]["labores"] == {"Cuadrilla #1": "correctivo"}
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


def test_b_con_la_tarea_y_el_nivel_la_ARMA(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    _delegar_y_autorizar(empresa, admin_profile, monkeypatch)
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO)

    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=_Motor())["jornadas_del_dia"]

    assert r["modo"] == adj.ARMADO
    hoy = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=MARTES)
    assert hoy.labor == "correctivo"
    assert hoy.armada_por == JornadaDeCuadrilla.AUTOMATICA
    assert sorted(i.persona.nombre for i in hoy.integrantes.all()) == [
        "PABLO", "PEDRO"]


def test_a2_con_el_nivel_3_pero_SIN_la_tarea_tampoco_arma(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    """EL ESCENARIO DE PRODUCCION. Rapilink ya tiene el nivel 3 --lo usa el paso
    a Despacho--, asi que la tarea delegada es la UNICA puerta que mantiene
    esto en sombra el dia del deploy. `test_a` no lo mide: ahi falta tambien
    el nivel."""
    from operaciones import autonomia

    autonomia.cambiar(empresa, 3, actor=admin_profile,
                      motivo="pasar casos a Despacho", criterios="medido")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO)

    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=_Motor())["jornadas_del_dia"]

    assert r["modo"] == adj.SOMBRA
    assert "delego" in r["porque"]
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


def test_c_con_la_tarea_pero_SIN_el_nivel_queda_en_sombra(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    td.delegar(empresa, td.ARMAR_LA_JORNADA, actor=admin_profile,
               pedido_textual="arma la jornada")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))

    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=_Motor())["jornadas_del_dia"]

    assert r["modo"] == adj.SOMBRA
    assert "no tiene autorizado" in r["porque"]
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


def test_d_con_el_interruptor_del_motor_sin_responder_queda_en_sombra(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    """Falla CERRADO: el motor de pruebas no existe, y no poder leer el
    interruptor es lo mismo que tenerlo detenido."""
    from operaciones import autonomia

    td.delegar(empresa, td.ARMAR_LA_JORNADA, actor=admin_profile,
               pedido_textual="arma la jornada")
    autonomia.cambiar(empresa, 3, actor=admin_profile, motivo="x",
                      criterios="y")

    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=_Motor())["jornadas_del_dia"]

    assert r["modo"] == adj.SOMBRA
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


def test_e_un_dia_que_la_empresa_NO_trabaja_no_corre_ni_pregunta(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    """Domingo: ni jornada ni preguntas al ISP, aunque todo este delegado."""
    _delegar_y_autorizar(empresa, admin_profile, monkeypatch)
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO)
    motor = _Motor()
    domingo = dt.datetime(2026, 10, 4, 15, 0, tzinfo=dt.timezone.utc)

    r = adj.armar_las_jornadas_del_dia(empresa, domingo,
                                       leer=motor)["jornadas_del_dia"]

    assert r["modo"] == adj.NO_CORRIO
    assert motor.preguntas == []
    assert not JornadaDeCuadrilla.objects.filter(
        fecha=dt.date(2026, 10, 4)).exists()


def test_f_despues_del_cierre_de_la_empresa_no_corre(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    """Armar a las 18:00 la jornada de un dia que ya termino ensuciaria la
    historia que lee `informe_de_jornadas`."""
    _delegar_y_autorizar(empresa, admin_profile, monkeypatch)
    a_las_18 = dt.datetime(2026, 10, 6, 23, 0, tzinfo=dt.timezone.utc)

    r = adj.armar_las_jornadas_del_dia(empresa, a_las_18,
                                       leer=_Motor())["jornadas_del_dia"]

    assert r["modo"] == adj.NO_CORRIO
    assert "cerro" in r["porque"]
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


# ---------------------------------------------------------------------------
# B · el barrio de cada caso
# ---------------------------------------------------------------------------

def test_g_el_barrio_se_pide_UNA_vez_y_con_tope_por_vuelta(
    empresa, cuadrilla, monkeypatch
):
    monkeypatch.setattr(adj, "TOPE_LOCALIDADES_POR_VUELTA", 3)
    casos = [_en_despacho(empresa, pad.FALLA_DE_SERVICIO) for _ in range(5)]
    motor = _Motor()

    primera = adj.armar_las_jornadas_del_dia(
        empresa, A_LAS_10, leer=motor)["jornadas_del_dia"]
    assert len(motor.preguntas) == 3
    assert primera["barrios"]["esperan_el_tope"] == 2

    adj.armar_las_jornadas_del_dia(empresa, A_LAS_10, leer=motor)
    assert len(motor.preguntas) == 5
    adj.armar_las_jornadas_del_dia(empresa, A_LAS_10, leer=motor)
    #  La tercera vuelta no pregunta nada: los cinco ya lo tienen guardado.
    assert len(motor.preguntas) == 5
    assert sorted(motor.preguntas) == sorted(str(c.id) for c in casos)


def test_g2_un_barrio_guardado_no_se_vuelve_a_pedir_ni_dias_despues(
    empresa, cuadrilla
):
    """El reintento de 24 h es solo para los que el ISP no tenia. Medido con una
    mutacion el 17/10: borrar esa regla sobrevivia, porque todas las pruebas
    miraban dentro de las primeras 24 horas."""
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)
    motor = _Motor()

    adj.completar_localidades(adj.propuestas_en_despacho(empresa),
                              ahora=timezone.now() + dt.timedelta(days=3),
                              leer=motor)

    assert motor.preguntas == []


def test_h_si_el_motor_no_responde_no_se_guarda_y_se_reintenta(
    empresa, cuadrilla
):
    caso = _en_despacho(empresa, pad.FALLA_DE_SERVICIO)
    caido = _Motor(respuesta=(None, "ConnectionError"))

    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=caido)["jornadas_del_dia"]
    assert r["barrios"]["no_se_pudo"] == 1
    p = P.objects.get(origen_id=str(caso.id))
    assert adj.localidad_guardada(p) is None

    adj.armar_las_jornadas_del_dia(empresa, A_LAS_10, leer=caido)
    assert len(caido.preguntas) == 2


def test_i_sin_barrio_se_guarda_vacio_y_se_reintenta_al_dia_siguiente(
    empresa, cuadrilla
):
    caso = _en_despacho(empresa, pad.FALLA_DE_SERVICIO)
    sin_servicio = _Motor(respuesta=("", "caso_sin_servicio"))

    adj.armar_las_jornadas_del_dia(empresa, A_LAS_10, leer=sin_servicio)
    pieza = adj.localidad_guardada(P.objects.get(origen_id=str(caso.id)))
    assert pieza["localidad"] == "" and pieza["motivo"] == "caso_sin_servicio"

    #  Una hora despues no se vuelve a preguntar...
    adj.armar_las_jornadas_del_dia(
        empresa, A_LAS_10 + dt.timedelta(hours=1), leer=sin_servicio)
    assert len(sin_servicio.preguntas) == 1
    #  ...pero al dia siguiente si: alguien puede haberlo cargado en el ISP.
    adj.completar_localidades(adj.propuestas_en_despacho(empresa),
                              ahora=timezone.now() + dt.timedelta(hours=25),
                              leer=sin_servicio)
    assert len(sin_servicio.preguntas) == 2


# ---------------------------------------------------------------------------
# C · cuanto trabajo hay en cada zona
# ---------------------------------------------------------------------------

def test_j_cada_caso_se_cuenta_en_su_zona_con_la_labor_de_su_grupo(
    empresa, soledad
):
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio="soledad   centro")
    _en_despacho(empresa, pad.TRABAJO_PEDIDO, barrio=BARRIO)
    #  Sin grupo: no tiene labor. «Nada lo mide» la tiene de fabrica desde el
    #  25/10/2026 (informe de Despacho).
    _en_despacho(empresa, "", barrio=BARRIO)
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio="BARRIO SIN MAPEAR")
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO)
    #  Cerrado: ya no esta en la cola, y no cuenta para nada.
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO,
                 status="Closed")

    d = adj.demanda_de_despacho(empresa, adj.propuestas_en_despacho(empresa))

    #  El trabajo pedido de un cliente que ya existe es correctivo desde el
    #  18/10/2026 (correccion 1 del usuario); hasta ese dia contaba como
    #  instalacion. La instalacion de un cliente nuevo: test_cn2.
    assert d["por_zona"] == {str(soledad.id): {"correctivo": 3}}
    assert (d["casos"], d["contados"]) == (6, 3)
    assert (d["sin_labor"], d["sin_zona"], d["sin_barrio"]) == (1, 1, 1)


# ---------------------------------------------------------------------------
# D · corre en el ciclo, y el log no lleva al cliente
# ---------------------------------------------------------------------------

def test_k_corre_dentro_de_correr_ciclo(empresa, cuadrilla):
    from operaciones import supervisor as sup

    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)

    resumen = sup.correr_ciclo(empresa, A_LAS_10)

    assert "armado de la jornada del dia" not in [
        f["fase"] for f in resumen.get("fases_que_fallaron", [])]
    r = resumen["jornadas_del_dia"]
    assert r["modo"] == adj.SOMBRA
    assert r["resultado"]["labores"] == {"Cuadrilla #1": "correctivo"}


def test_l_el_log_NO_lleva_el_barrio_ni_el_cliente(
    empresa, cuadrilla, caplog
):
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO)

    with caplog.at_level(logging.INFO, logger="operaciones.armado_de_jornadas"):
        adj.armar_las_jornadas_del_dia(empresa, A_LAS_10, leer=_Motor())

    texto = caplog.text
    assert "jornadas del dia" in texto and "Cuadrilla #1" in texto
    assert BARRIO not in texto.upper()
    assert CLIENTE not in texto


def test_m_la_madrugada_usa_la_MISMA_regla_y_la_misma_demanda(
    empresa, cuadrilla
):
    """Una sola regla para los dos que arman. La madrugada no le pregunta al
    ISP: cuenta con los barrios ya guardados."""
    from campo import tasks
    from campo.cuadrillas import ConfiguracionDeReparto

    ConfiguracionDeReparto.objects.filter(org=empresa).update(
        activo=True, copia_la_jornada=True)
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)

    r = tasks.correr_para(
        empresa, ahora_local=dt.datetime(2026, 10, 6, 3, 5,
                                         tzinfo=dt.timezone.utc),
        avisar=False)

    #  La habitual de la #1 es instalacion: la falla de SOLEDAD la inclina.
    assert r["jornadas"]["labores"] == {"Cuadrilla #1": "correctivo"}
    assert JornadaDeCuadrilla.objects.get(
        cuadrilla=cuadrilla, fecha=MARTES).labor == "correctivo"


# ---------------------------------------------------------------------------
# E · lo que encontro el auditor de frontera (17/10/2026)
# ---------------------------------------------------------------------------

def test_n_el_nivel_sale_del_catalogo_y_con_nivel_2_no_arma(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    """Eran dos copias del mismo numero sin nada que las atara; con 2 en la
    constante, las demas pruebas seguian en verde."""
    from operaciones import autonomia

    assert adj.NIVEL_PARA_ARMAR == td.CATALOGO[td.ARMAR_LA_JORNADA][
        "exige_nivel"] == 3

    td.delegar(empresa, td.ARMAR_LA_JORNADA, actor=admin_profile,
               pedido_textual="arma la jornada")
    autonomia.cambiar(empresa, 2, actor=admin_profile, motivo="coordinar",
                      criterios="medido")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))

    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=_Motor())["jornadas_del_dia"]

    assert r["modo"] == adj.SOMBRA
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


def test_o_con_el_calendario_en_otra_zona_no_arma_un_dia_terminado(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    """El calendario en UTC y la empresa en Bogota, como midio D-4 en
    produccion el 28/09. La primera version armaba a las 20:07 de Bogota un
    dia que ya habia terminado."""
    from business_hours.models import BusinessCalendar

    BusinessCalendar.objects.filter(org=empresa).update(
        timezone="UTC", tuesday_open=dt.time(9, 0),
        tuesday_close=dt.time(17, 0))
    _delegar_y_autorizar(empresa, admin_profile, monkeypatch)

    a_las_20 = dt.datetime(2026, 10, 7, 1, 7, tzinfo=dt.timezone.utc)
    r = adj.armar_las_jornadas_del_dia(empresa, a_las_20,
                                       leer=_Motor())["jornadas_del_dia"]
    assert r["modo"] == adj.NO_CORRIO
    assert "otro dia" in r["porque"]
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()

    #  A las 10:07 de Bogota (15:07 en el calendario) arma, y avisa la zona.
    a_las_10 = dt.datetime(2026, 10, 6, 15, 7, tzinfo=dt.timezone.utc)
    r = adj.armar_las_jornadas_del_dia(empresa, a_las_10,
                                       leer=_Motor())["jornadas_del_dia"]
    assert r["modo"] == adj.ARMADO
    assert "UTC" in r["aviso"] and "America/Bogota" in r["aviso"]


def test_p_con_el_motor_caido_no_se_le_sigue_preguntando(empresa, cuadrilla):
    """Cada pedido son hasta 30 s: ocho seguidos contra un motor caido eran
    cuatro minutos por empresa y por vuelta."""
    for _ in range(3):
        _en_despacho(empresa, pad.FALLA_DE_SERVICIO)
    caido = _Motor(respuesta=(None, "motor_no_alcanzado"))

    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=caido)["jornadas_del_dia"]

    assert len(caido.preguntas) == 1
    assert (r["barrios"]["no_se_pudo"], r["barrios"]["motor_caido"]) == (1, 2)


def test_q_la_madrugada_fija_el_contexto_de_cada_empresa(
    empresa, cuadrilla, admin_profile
):
    """En el worker la madrugada corria SIN contexto RLS: no veia las
    ausencias --armaba con el lider ausente-- y el aviso fallaba. Se simula el
    worker borrando el contexto antes de correrla.

    Con el rol de pruebas (que salta el RLS) pasa igual: lo que la mide es la
    corrida con un rol que el RLS ata.
    """
    from campo import tasks
    from campo.cuadrillas import ConfiguracionDeReparto
    from common.tasks import clear_rls_context
    from operaciones.models import DisponibilidadTecnico

    hoy = tasks._ahora_local(empresa).date()
    #  ABIERTO TODOS LOS DIAS (25/10/2026): corre con la fecha real, y desde que
    #  la madrugada no arma los dias que las cuadrillas no trabajan, un
    #  domingo esta prueba media eso y no el contexto RLS.
    from business_hours.models import BusinessCalendar

    for cal in BusinessCalendar.objects.filter(org=empresa):
        for d in ("saturday", "sunday"):
            setattr(cal, f"{d}_open", dt.time(0, 0))
            setattr(cal, f"{d}_close", dt.time(23, 59))
        cal.save()
    DisponibilidadTecnico.objects.create(
        org=empresa, profile=admin_profile, fecha=hoy,
        hora_inicio=dt.time(0, 0), hora_fin=dt.time(23, 59),
        disponible=False, motivo="vacaciones")
    ConfiguracionDeReparto.objects.filter(org=empresa).update(
        activo=True, hora_local=0)
    clear_rls_context()

    r = tasks.ciclo_de_la_madrugada()

    assert r["errores"] == []
    corrida = next(c for c in r["corridas"] if c["org"] == str(empresa.id))
    assert corrida["jornadas"]["lider_ausente"] == ["Cuadrilla #1"]
    assert not JornadaDeCuadrilla.objects.filter(cuadrilla=cuadrilla,
                                                 fecha=hoy).exists()


def test_r_lo_que_arma_el_supervisor_queda_auditado_con_su_tarea(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    from common.models import Activity
    from operaciones import auditoria

    _delegar_y_autorizar(empresa, admin_profile, monkeypatch)

    adj.armar_las_jornadas_del_dia(empresa, A_LAS_10, leer=_Motor())

    hoy = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=MARTES)
    fila = Activity.objects.get(entity_type=auditoria.ENTIDAD_JORNADA,
                                entity_id=hoy.id)
    assert fila.action == "CREATE" and fila.user_id is None
    assert fila.metadata["origen"] == td.ARMAR_LA_JORNADA


# ---------------------------------------------------------------------------
# F · lo que encontro el auditor independiente (17/10/2026)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("respuesta, esperado", [
    ({"contexto_disponible": True, "cliente": {"localidad": " SOLEDAD CENTRO "}},
     ("SOLEDAD CENTRO", "")),
    ({"contexto_disponible": True, "cliente": {"nombre": "x", "localidad": ""}},
     ("", "el_isp_no_tiene_barrio")),
    #  El motor contesto sin ficha (se trago el error del ISP): se reintenta.
    ({"contexto_disponible": True, "cliente": {}},
     (None, "sin_ficha_del_cliente")),
    ({"contexto_disponible": False, "motor_alcanzado": False,
      "motivo": "ConnectionError"}, (None, "motor_no_alcanzado")),
    ({"contexto_disponible": False, "motor_alcanzado": False,
      "motivo": "ConnectTimeout"}, (None, "motor_no_alcanzado")),
    ({"contexto_disponible": False, "motor_alcanzado": False,
      "motivo": "HTTPError"}, (None, "fallo_del_caso")),
    ({"contexto_disponible": False, "motor_alcanzado": True,
      "motivo": "caso_sin_servicio"}, ("", "caso_sin_servicio")),
    #  Un motivo que no es una clave conocida no se guarda tal cual.
    ({"contexto_disponible": False, "motor_alcanzado": True,
      "motivo": "Zoraida no contesto"}, ("", "sin_contexto")),
    #  INSTALACION NUEVA (18/10/2026): el ticket cuelga del cliente de
    #  instalaciones del ISP, y el barrio de esa ficha es el del cliente
    #  ficticio, no el de la casa. No se guarda.
    ({"contexto_disponible": True, "servicio": "999",
      "id_servicio_instalaciones": "999",
      "cliente": {"nombre": "INSTALACIONES NUEVAS", "localidad": "OFICINA"}},
     ("", "instalacion_nueva")),
    #  Y el marcador solo cuenta si coincide: otro servicio es un cliente.
    ({"contexto_disponible": True, "servicio": "3614",
      "id_servicio_instalaciones": "999",
      "cliente": {"nombre": "x", "localidad": "SOLEDAD CENTRO"}},
     ("SOLEDAD CENTRO", "")),
])
def test_s_leer_localidad_lee_la_ficha_tal_como_la_trae_el_motor(
    monkeypatch, respuesta, esperado
):
    """El unico adaptador entre la respuesta real y el barrio. Todas las demas
    pruebas inyectan `leer`, y cambiar 'localidad' por otra clave las dejaba
    en verde (auditor independiente, 17/10)."""
    monkeypatch.setattr("campo.services.despacho.contexto_del_caso",
                        lambda caso_id: respuesta)

    assert adj.leer_localidad("caso-1") == esperado


def test_s2_si_la_consulta_explota_no_se_guarda_nada(monkeypatch):
    def explota(caso_id):
        raise RuntimeError("se cayo")

    monkeypatch.setattr("campo.services.despacho.contexto_del_caso", explota)

    assert adj.leer_localidad("caso-1") == (None, "RuntimeError")


def test_t_un_caso_que_falla_no_deja_sin_barrio_a_los_demas(empresa, cuadrilla):
    """Cortar la vuelta en el primer fallo dejaba a toda la cola detras de un
    caso roto, para siempre: el orden es estable."""
    primero = _en_despacho(empresa, pad.FALLA_DE_SERVICIO)
    for _ in range(2):
        _en_despacho(empresa, pad.FALLA_DE_SERVICIO)

    class _UnoRoto(_Motor):
        def __call__(self, caso_id):
            self.preguntas.append(str(caso_id))
            if str(caso_id) == str(primero.id):
                return None, "fallo_del_caso"
            return BARRIO, ""

    motor = _UnoRoto()
    r = adj.armar_las_jornadas_del_dia(empresa, A_LAS_10,
                                       leer=motor)["jornadas_del_dia"]

    assert len(motor.preguntas) == 3
    assert (r["barrios"]["leidas"], r["barrios"]["motor_caido"]) == (2, 0)


def _orden_del_caso(org, caso, *, estado="asignada", a_quien=None):
    from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

    n = OrdenTrabajo.objects.count() + 1
    wt = WorkType.objects.create(org=org, codigo=f"t{n}", nombre="T",
                                 labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=n, tipo_trabajo_version=version,
        estado_operativo=estado, zona=BARRIO, origen_sistema="crm",
        origen_ref=str(caso.id))
    if a_quien is not None:
        AsignacionTrabajo.objects.create(orden=orden, profile=a_quien,
                                         rol=AsignacionTrabajo.TECNICO_LIDER,
                                         es_principal=True)
    return orden


def test_v_lo_ya_despachado_no_pide_cuadrilla(empresa, soledad, admin_profile):
    """La cola es "aceptado y no cerrado": un caso sigue ahi con su orden hecha
    o en manos de alguien, y contarlo inclinaba la labor hacia trabajo hecho."""
    from campo.models import OrdenTrabajo

    con_alguien = _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)
    _orden_del_caso(empresa, con_alguien, a_quien=admin_profile)
    hecha = _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)
    _orden_del_caso(empresa, hecha, estado=OrdenTrabajo.COMPLETADA_CAMPO)
    #  Una orden sin nadie todavia ES trabajo que pide cuadrilla.
    sin_nadie = _en_despacho(empresa, pad.TRABAJO_PEDIDO, barrio=BARRIO)
    _orden_del_caso(empresa, sin_nadie)
    #  Y la cancelada no cuenta como despacho.
    cancelada = _en_despacho(empresa, pad.TRABAJO_PEDIDO, barrio=BARRIO)
    _orden_del_caso(empresa, cancelada, estado=OrdenTrabajo.CANCELADA)

    d = adj.demanda_de_despacho(empresa, adj.propuestas_en_despacho(empresa))

    assert d["ya_despachados"] == 2
    #  Dos trabajos pedidos de clientes que ya existen: correctivo (18/10).
    assert d["por_zona"] == {str(soledad.id): {"correctivo": 2}}


def test_u_la_visita_que_pidio_una_medicion_cuenta_con_su_labor(
    empresa, soledad
):
    """Esos casos entran sin lectura del reclamo, y por lo tanto sin grupo:
    quedaban todos en "sin labor". La accion la escribe `supervisor.analizar`,
    y la prueba la toma DE AHI: si alguien cambia esa frase, esto falla."""
    from operaciones import supervisor as sup

    caso = Case.objects.create(
        org=empresa, name="Sin señal", status="Assigned", priority="Normal",
        is_active=True, provider="wisphub", area="soporte_tecnico",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id=f"s{uuid.uuid4().hex[:6]}")
    analisis = sup.analizar(sup.Senal(
        tipo=P.CASO_REQUIERE_VISITA, origen_tipo="case",
        origen_id=str(caso.id),
        datos={"labor_sugerida": "correctivo", "fuente_de_la_sugerencia": "x"}))
    ahora = timezone.now().isoformat()
    P.objects.create(
        org=empresa, tipo_senal=P.CASO_REQUIERE_VISITA, origen_tipo="case",
        origen_id=str(caso.id), estado=P.ACEPTADA, revisado_en=timezone.now(),
        accion_propuesta=analisis["accion_propuesta"], motivo="x",
        prioridad=30, evidencia=[{
            "fuente": adj.FUENTE_LOCALIDAD, "id": str(caso.id), "dato": "b",
            "observado_en": ahora, "localidad": BARRIO, "motivo": ""}])

    d = adj.demanda_de_despacho(empresa, adj.propuestas_en_despacho(empresa))

    assert d["por_zona"] == {str(soledad.id): {"correctivo": 1}}
    assert d["sin_labor"] == 0


def test_w_antes_de_que_abra_la_empresa_no_arma(
    empresa, cuadrilla, admin_profile, monkeypatch
):
    """A las 00:07 se armaba la del dia, y una ausencia cargada esa mañana ya
    no sacaba al lider: una jornada armada sola solo se reajusta de labor."""
    _delegar_y_autorizar(empresa, admin_profile, monkeypatch)
    a_las_5 = dt.datetime(2026, 10, 6, 10, 7, tzinfo=dt.timezone.utc)

    r = adj.armar_las_jornadas_del_dia(empresa, a_las_5,
                                       leer=_Motor())["jornadas_del_dia"]

    assert r["modo"] == adj.NO_CORRIO
    assert "no abrio" in r["porque"]
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


# ---------------------------------------------------------------------------
# VP · la vista previa  --  21/10/2026
# ---------------------------------------------------------------------------
#  Pedido del usuario: ver YA lo que armaria el Supervisor, sin esperar al
#  dia siguiente. El mismo planificador y la misma demanda, SIN escribir nada.

VISTA_PREVIA = "/api/operaciones/jornada/vista-previa/"


def test_vp_muestra_lo_que_armaria_y_no_escribe(admin_client, empresa,
                                                cuadrilla, monkeypatch):
    def _no(*a, **k):
        raise AssertionError("la vista previa no le pregunta nada al motor")

    monkeypatch.setattr(adj, "completar_localidades", _no)
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)
    antes = JornadaDeCuadrilla.objects.count()

    r = admin_client.get(VISTA_PREVIA, {"fecha": MARTES.isoformat()})
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["trabaja"] is True and (d["apertura"], d["cierre"]) == ("07:00", "17:00")
    [c] = d["cuadrillas"]
    assert c["cuadrilla"] == "Cuadrilla #1"
    assert c["que_haria"] == "Se arma con la gente de su última jornada"
    assert c["zonas"] == ["SOLEDAD"]
    assert sorted(g["nombre"] for g in c["gente"]) == ["PABLO", "PEDRO"]
    #  La labor de la mayoria de los casos de su zona: una falla de servicio.
    assert c["labor"] == "Correctivo"
    assert d["demanda"]["contados"] == 1
    assert d["por_zona"] == [{"zona": "SOLEDAD",
                              "labores": [{"labor": "Correctivo", "casos": 1}]}]
    assert JornadaDeCuadrilla.objects.count() == antes


def test_vp2_sin_horario_de_cuadrillas_lo_dice(admin_client, empresa, cuadrilla):
    from campo.cuadrillas import ConfiguracionDeReparto
    ConfiguracionDeReparto.objects.filter(org=empresa).update(
        calendario_de_cuadrillas=None)
    d = admin_client.get(VISTA_PREVIA, {"fecha": MARTES.isoformat()}).json()
    assert d["trabaja"] is False and "horario de las cuadrillas" in d["porque"]
    assert d["cuadrillas"] == []


def test_vp3_un_dia_que_no_se_trabaja_lo_dice(admin_client, empresa, cuadrilla):
    domingo = MARTES + dt.timedelta(days=5)
    d = admin_client.get(VISTA_PREVIA, {"fecha": domingo.isoformat()}).json()
    assert d["trabaja"] is False and "no trabajan" in d["porque"]


def test_vp4_la_fecha_mal_escrita_es_400(admin_client, empresa):
    assert admin_client.get(VISTA_PREVIA, {"fecha": "21/10"}).status_code == 400


def test_vp5_solo_gestion(user_client, empresa):
    assert user_client.get(VISTA_PREVIA).status_code == 403


def test_vp6_nombra_los_barrios_sin_zona(admin_client, empresa, cuadrilla,
                                         admin_profile):
    """La vista previa del 21/10 mostro 21 casos con barrio sin zona: sin el
    nombre no se sabe que cargar en Zonas operativas."""
    from campo.zonas import normalizar_localidad
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio="Villa Nueva")
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio="Villa Nueva")
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)
    #  Uno ya despachado no cuenta, como en la demanda: ya tiene a alguien.
    hecho = _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio="Villa Nueva")
    _orden_del_caso(empresa, hecho, a_quien=admin_profile)
    d = admin_client.get(VISTA_PREVIA, {"fecha": MARTES.isoformat()}).json()
    assert d["barrios_sin_zona"] == [
        {"barrio": normalizar_localidad("Villa Nueva"), "casos": 2}]


def test_vp7_una_ya_armada_muestra_su_gente_y_dice_que_no_cambia(
        admin_client, empresa, cuadrilla, soledad):
    j = JornadaDeCuadrilla.objects.create(
        org=empresa, cuadrilla=cuadrilla, fecha=MARTES, labor="correctivo",
        armada_por=JornadaDeCuadrilla.AUTOMATICA)
    j.zonas.set([soledad])
    IntegranteDeJornada.objects.create(
        org=empresa, jornada=j, rol="tecnico",
        persona=PersonaDeCampo.objects.create(org=empresa, nombre="JUAN"))
    _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)
    [c] = admin_client.get(VISTA_PREVIA, {"fecha": MARTES.isoformat()}).json()["cuadrillas"]
    assert c["que_haria"] == "Ya está armada con la labor que corresponde"
    assert [g["nombre"] for g in c["gente"]] == ["JUAN"]


# ---------------------------------------------------------------------------
# LDC · la labor de un caso, una sola regla  --  21/10/2026 (Fase 2.1)
# ---------------------------------------------------------------------------
#  Extraida de `demanda_de_despacho`: la usa la demanda de la jornada y la va a
#  usar el Supervisor al crear la orden (2.3). Tienen que dar LO MISMO.

def test_ldc_la_labor_de_cada_caso(empresa):
    from campo.cuadrillas import labor_de_cada_grupo

    labores = labor_de_cada_grupo(empresa)
    falla = _en_despacho(empresa, pad.FALLA_DE_SERVICIO, barrio=BARRIO)
    pedido = _en_despacho(empresa, pad.TRABAJO_PEDIDO, barrio=BARRIO)
    nuevo = _en_despacho(empresa, pad.TRABAJO_PEDIDO, barrio=BARRIO)
    #  El trabajo pedido de un CLIENTE NUEVO es instalacion (correccion 1, 18/10).
    p = P.objects.get(origen_id=str(nuevo.id))
    ev = [dict(e, cliente_nuevo=True) if e.get("fuente") == adj.FUENTE_LOCALIDAD
          else e for e in p.evidencia]
    P.objects.filter(pk=p.pk).update(evidencia=ev)

    ps = adj.propuestas_en_despacho(empresa)
    assert adj.labor_del_caso(ps[str(falla.id)], labores) == "correctivo"
    assert adj.labor_del_caso(ps[str(pedido.id)], labores) == "correctivo"
    assert adj.labor_del_caso(ps[str(nuevo.id)], labores) == "instalacion"
    #  Un corte de red es obra de red, sea cual sea su lectura.
    assert adj.labor_del_caso(ps[str(falla.id)], labores, es_corte=True) == "trabajos"
