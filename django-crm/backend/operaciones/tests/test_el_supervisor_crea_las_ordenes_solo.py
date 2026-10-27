# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CREA LAS ORDENES, DE VERDAD  --  24/10/2026
================================================================================

Fase 2.3, entrega 2: `ordenes_de_despacho.crear_las_ordenes`, la fase del
ciclo. Afirma:

  P  las puertas: sin la tarea, sin el nivel, sin MOTOR_TENANT o sin hora de
     corte NO crea nada (la sombra)
  C  con las puertas, crea la orden como el boton: plantilla, prioridad, dia,
     barrio y cliente de la ficha, y deja escrito que la creo el Supervisor
  U  una sola orden por caso: dos vueltas no crean dos, y si alguien la creo
     mientras se pedia la ficha, no se crea otra
  T  el tope por vuelta, el motor caido y el caso sin ficha
  I  la instalacion de un cliente nuevo no copia la ficha del cliente ficticio
  R  el corte de red: la orden la lleva uno, y los demas quedan atados
  K  corre dentro de `correr_ciclo`, y el log no lleva clientes
  F  lo que encontro la auditoria de frontera del 24/10: el nivel exacto y el
     interruptor, el bloqueo por caso que comparte con el boton Despachar,
     las puertas releidas antes de cada orden, el caso que se cerro, la
     propuesta rechazada, el motor lento y la ficha que no llega

    pytest operaciones/tests/test_el_supervisor_crea_las_ordenes_solo.py
================================================================================
"""
import datetime as dt
import logging

import pytest

from campo.models import EventoTrabajo, OrdenTrabajo
from operaciones import ordenes_de_despacho as O
from operaciones import paso_a_despacho as pad
from operaciones import tareas_delegadas as td
from operaciones.models import PropuestaSupervisor as P
from operaciones.tests import test_el_supervisor_crea_las_ordenes as _base
from operaciones.tests.test_el_supervisor_crea_las_ordenes import (
    A_LAS_3,
    BARRIO,
    BOGOTA,
    CORTE,
    _bogota,
    _caso,
)

pytestmark = pytest.mark.django_db

#  Las fixtures de la entrega 1 (la empresa con hora de corte y SOLEDAD, y las
#  tres plantillas), las mismas, sin copiarlas.
empresa = _base.empresa
plantillas = _base.plantillas

CLIENTE = "Zoraida Clientela"


class _Motor:
    """La ficha, de mentira: cuenta las preguntas."""

    def __init__(self, ficha=None):
        self.ficha = ficha
        self.preguntas = []

    def __call__(self, caso_id):
        self.preguntas.append(str(caso_id))
        if self.ficha is not None:
            return self.ficha
        return {"contexto_disponible": True, "motor_alcanzado": True,
                "servicio": "5267",
                "cliente": {"nombre": CLIENTE, "telefono": "300 111 2222",
                            "direccion": "Calle 38 # 78-33", "localidad": BARRIO}}


@pytest.fixture
def abierto(empresa, admin_profile, monkeypatch):
    """Las cuatro puertas abiertas, por el camino real salvo el interruptor del
    motor, que en la base de pruebas no existe."""
    from operaciones import autonomia

    td.delegar(empresa, td.CREAR_LAS_ORDENES, actor=admin_profile,
               pedido_textual="crea las ordenes de despacho")
    autonomia.cambiar(empresa, 3, actor=admin_profile,
                      motivo="crear las ordenes", criterios="vista previa")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))
    monkeypatch.setenv("MOTOR_TENANT", "una-empresa")
    return empresa


def _correr(org, motor=None):
    return O.crear_las_ordenes(org, A_LAS_3, leer=motor or _Motor())[
        "ordenes_de_despacho"]


# ---------------------------------------------------------------------------
# P · las puertas
# ---------------------------------------------------------------------------

def test_p_sin_la_tarea_queda_en_sombra_y_no_crea(empresa, plantillas, monkeypatch):
    monkeypatch.setenv("MOTOR_TENANT", "una-empresa")
    _caso(empresa)
    motor = _Motor()

    r = _correr(empresa, motor)

    assert (r["modo"], r["crearia"], r["creadas"]) == (O.SOMBRA, 1, 0)
    assert "delegó" in r["porque"]
    assert OrdenTrabajo.objects.count() == 0
    assert motor.preguntas == []


def test_p2_sin_el_nivel_tampoco(empresa, plantillas, admin_profile, monkeypatch):
    td.delegar(empresa, td.CREAR_LAS_ORDENES, actor=admin_profile)
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))
    monkeypatch.setenv("MOTOR_TENANT", "una-empresa")
    _caso(empresa)

    r = _correr(empresa)

    assert (r["modo"], r["creadas"]) == (O.SOMBRA, 0)
    assert OrdenTrabajo.objects.count() == 0


def test_p3_sin_motor_tenant_tampoco(abierto, plantillas, monkeypatch):
    monkeypatch.delenv("MOTOR_TENANT")
    _caso(abierto)

    r = _correr(abierto)

    assert (r["modo"], r["creadas"]) == (O.SOMBRA, 0)
    assert "MOTOR_TENANT" in r["porque"]


def test_p4_sin_hora_de_corte_no_corre(abierto, plantillas):
    from campo.cuadrillas import ConfiguracionDeReparto

    ConfiguracionDeReparto.objects.filter(org=abierto).update(hora_de_corte=None)
    _caso(abierto)

    r = _correr(abierto)

    assert (r["modo"], r["creadas"]) == (O.NO_CORRIO, 0)
    assert OrdenTrabajo.objects.count() == 0


# ---------------------------------------------------------------------------
# C · crea como el boton
# ---------------------------------------------------------------------------

def test_c_crea_la_orden_como_el_boton(abierto, plantillas):
    from campo import niveles as N

    #  Urgente: alta igual que por vencida, y queda escrito de donde salio.
    N.decidir_por_persona(abierto, "No tiene internet", N.URGENTE)
    caso = _caso(abierto, creado=_bogota(3, 9))     # vencida: alta
    motor = _Motor()

    r = _correr(abierto, motor)

    assert (r["modo"], r["creadas"]) == (O.CREO, 1)
    assert motor.preguntas == [str(caso.id)]
    o = OrdenTrabajo.objects.get()
    assert (o.origen_sistema, o.origen_ref, o.tipo_trabajo_version_id) == (
        "crm", str(caso.id), plantillas["soporte"].id)
    assert (o.prioridad, o.zona) == ("alta", BARRIO)
    assert (o.cliente_nombre, o.cliente_telefono, o.cliente_direccion) == (
        CLIENTE, "300 111 2222", "Calle 38 # 78-33")
    #  El dia de la empresa: entro antes del corte, sale el martes.
    assert o.programada_para.astimezone(BOGOTA).date() == dt.date(2026, 10, 6)
    #  Sin persona, y escrito que fue el Supervisor y con que tarea.
    ev = EventoTrabajo.objects.get(orden=o, tipo="creada_por_el_supervisor")
    assert (ev.profile_id, ev.datos["tarea"]) == (None, td.CREAR_LAS_ORDENES)
    #  Por que esa prioridad (26/10/2026): el nivel puede cambiar despues.
    assert (ev.datos["nivel"], ev.datos["equipo_caido"]) == (N.URGENTE, False)
    pieza = [x for x in P.objects.get(origen_id=str(caso.id)).evidencia
             if x.get("fuente") == O.FUENTE_ORDEN]
    assert [x["orden"] for x in pieza] == [o.numero]


def test_c2_lo_que_entro_despues_del_corte_sale_mañana(abierto, plantillas):
    _caso(abierto, entro=_bogota(6, 13))

    _correr(abierto)

    o = OrdenTrabajo.objects.get()
    assert o.programada_para.astimezone(BOGOTA).date() == dt.date(2026, 10, 7)


# ---------------------------------------------------------------------------
# U · una sola orden por caso
# ---------------------------------------------------------------------------

def test_u_dos_vueltas_no_crean_dos(abierto, plantillas):
    _caso(abierto)

    primera, segunda = _correr(abierto), _correr(abierto)

    assert (primera["creadas"], segunda["creadas"], segunda["crearia"]) == (1, 0, 0)
    assert OrdenTrabajo.objects.count() == 1


def test_u2_si_alguien_la_creo_mientras_se_pedia_la_ficha_no_crea_otra(
        abierto, plantillas):
    caso = _caso(abierto)

    def motor_lento(caso_id):
        #  Mientras el motor contesta, una persona la despacha a mano.
        OrdenTrabajo.objects.create(
            org=abierto, numero=900, tipo_trabajo_version=plantillas["soporte"],
            origen_sistema="crm", origen_ref=str(caso.id))
        return _Motor()(caso_id)

    r = _correr(abierto, motor_lento)

    assert (r["creadas"], r["ya_tenian"]) == (0, 1)
    assert list(OrdenTrabajo.objects.values_list("numero", flat=True)) == [900]


@pytest.mark.django_db(transaction=True)
def test_u3_el_bloqueo_tiene_efecto_con_dos_transacciones(abierto, plantillas):
    """Otra vuelta tiene la propuesta bloqueada y crea la orden; esta espera,
    y al entrar ve que ya existe. Sin el `select_for_update`, no espera: lee
    antes de que la otra confirme, y crea una segunda."""
    import threading
    import time

    from django.db import connection, transaction

    caso = _caso(abierto)
    f = O.decidir(abierto, A_LAS_3)["crear"][0]
    propuesta = P.objects.get(origen_id=str(caso.id))
    listo, errores = threading.Event(), []

    def la_otra_vuelta():
        try:
            #  Su propia conexion: sin el contexto de la empresa, el aislamiento
            #  (RLS) no le deja ver la propuesta.
            from conftest import _apply_rls_context
            _apply_rls_context(abierto.id)
            with transaction.atomic():
                P.objects.select_for_update().get(pk=propuesta.pk)
                listo.set()
                time.sleep(2)
                OrdenTrabajo.objects.create(
                    org=abierto, numero=900,
                    tipo_trabajo_version=plantillas["soporte"],
                    origen_sistema="crm", origen_ref=str(caso.id))
        except Exception as e:                                   # noqa: BLE001
            errores.append(repr(e))
            listo.set()
        finally:
            connection.close()

    hilo = threading.Thread(target=la_otra_vuelta)
    hilo.start()
    assert listo.wait(15)
    r = O._crear_una(abierto, propuesta, f, _Motor()(str(caso.id)),
                     ahora=A_LAS_3, zona=BOGOTA)
    hilo.join()

    assert not errores
    assert r == "ya_tenia"
    assert list(OrdenTrabajo.objects.values_list("numero", flat=True)) == [900]


# ---------------------------------------------------------------------------
# T · el tope, el motor caido y el caso sin ficha
# ---------------------------------------------------------------------------

def test_t_el_tope_por_vuelta(abierto, plantillas, monkeypatch):
    monkeypatch.setattr(O, "TOPE_POR_VUELTA", 1)
    _caso(abierto)
    _caso(abierto)

    r = _correr(abierto)

    assert (r["creadas"], r["esperan_el_tope"]) == (1, 1)


def test_t2_con_el_motor_caido_no_le_sigue_preguntando(abierto, plantillas):
    _caso(abierto)
    _caso(abierto)
    motor = _Motor({"contexto_disponible": False, "motor_alcanzado": False,
                    "motivo": "ConnectionError"})

    r = _correr(abierto, motor)

    assert (r["creadas"], r["motor_caido"], len(motor.preguntas)) == (0, 2, 1)
    assert OrdenTrabajo.objects.count() == 0


def test_t3_sin_ficha_no_se_crea_y_se_reintenta_en_unas_horas(abierto, plantillas):
    caso = _caso(abierto)
    motor = _Motor({"contexto_disponible": False, "motor_alcanzado": True,
                    "motivo": "sin_identidad_resoluble"})

    r = _correr(abierto, motor)

    assert (r["creadas"], r["sin_ficha"]) == (0, 1)
    pieza = [x for x in P.objects.get(origen_id=str(caso.id)).evidencia
             if x.get("fuente") == O.FUENTE_SIN_FICHA]
    assert [x["motivo"] for x in pieza] == ["sin_identidad_resoluble"]
    #  Enseguida no se le vuelve a preguntar: no ocupa el tope de otros.
    otra = _Motor()
    assert O.crear_las_ordenes(abierto, A_LAS_3, leer=otra)[
        "ordenes_de_despacho"]["sin_ficha_reciente"] == 1
    assert otra.preguntas == []
    #  Pasadas las horas, si.
    mas_tarde = A_LAS_3 + dt.timedelta(hours=O.HORAS_PARA_VOLVER_A_PEDIR_LA_FICHA + 1)
    assert O.crear_las_ordenes(abierto, mas_tarde, leer=_Motor())[
        "ordenes_de_despacho"]["creadas"] == 1


# ---------------------------------------------------------------------------
# I · la instalacion de un cliente nuevo
# ---------------------------------------------------------------------------

def test_i_la_instalacion_nueva_no_copia_al_cliente_ficticio(abierto, plantillas):
    _caso(abierto, asunto="Instalacion nueva", grupo=pad.TRABAJO_PEDIDO,
          barrio="", nuevo=True)

    _correr(abierto)

    o = OrdenTrabajo.objects.get()
    assert (o.cliente_nombre, o.cliente_telefono, o.cliente_direccion) == ("", "", "")
    assert o.resumen.startswith("Llamar al cliente para ubicarlo")
    assert o.contexto.get("cliente") == {}


# ---------------------------------------------------------------------------
# R · el corte de red
# ---------------------------------------------------------------------------

def test_r_el_corte_lleva_una_orden_y_ata_a_los_demas(abierto, plantillas):
    lleva = _caso(abierto, asunto="Sin servicio", creado=_bogota(4, 9),
                  medicion=CORTE)
    atado = _caso(abierto, creado=_bogota(5, 9), medicion=CORTE)

    primera = _correr(abierto)
    segunda = _correr(abierto)

    o = OrdenTrabajo.objects.get()
    assert o.origen_ref == str(lleva.id)
    pieza = [x for x in P.objects.get(origen_id=str(atado.id)).evidencia
             if x.get("fuente") == O.FUENTE_ATADURA]
    assert [(x["orden"], x["a_caso"]) for x in pieza] == [(o.numero, str(lleva.id))]
    #  La segunda vuelta no la vuelve a escribir.
    assert (primera["atadas"], segunda["atadas"]) == (1, 0)


# ---------------------------------------------------------------------------
# K · el ciclo y el log
# ---------------------------------------------------------------------------

def test_k_corre_dentro_de_correr_ciclo(empresa, plantillas):
    from operaciones import supervisor as sup

    _caso(empresa)

    resumen = sup.correr_ciclo(empresa, A_LAS_3)

    assert "creacion de las ordenes de Despacho" not in [
        f["fase"] for f in resumen.get("fases_que_fallaron", [])]
    assert resumen["ordenes_de_despacho"]["modo"] == O.SOMBRA


def test_k2_el_log_no_lleva_el_cliente(abierto, plantillas, caplog):
    _caso(abierto)

    with caplog.at_level(logging.INFO):
        _correr(abierto)

    assert CLIENTE not in caplog.text
    assert BARRIO not in caplog.text


# ---------------------------------------------------------------------------
# F · lo que encontro la auditoria de frontera del 24/10/2026
# ---------------------------------------------------------------------------

def _delegada(org, perfil, monkeypatch, *, nivel, interruptor):
    from operaciones import autonomia

    td.delegar(org, td.CREAR_LAS_ORDENES, actor=perfil)
    autonomia.cambiar(org, nivel, actor=perfil, motivo="probar",
                      criterios="medido")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: interruptor)
    monkeypatch.setenv("MOTOR_TENANT", "una-empresa")


def test_f_con_nivel_2_no_crea(empresa, plantillas, admin_profile, monkeypatch):
    """El nivel que exige es EXACTAMENTE 3: con el 2 y todo lo demas abierto,
    sombra."""
    _delegada(empresa, admin_profile, monkeypatch, nivel=2, interruptor=(True, ""))
    _caso(empresa)

    r = _correr(empresa)

    assert (r["modo"], r["creadas"]) == (O.SOMBRA, 0)


def test_f2_con_el_interruptor_detenido_no_crea(
        empresa, plantillas, admin_profile, monkeypatch):
    _delegada(empresa, admin_profile, monkeypatch, nivel=3,
              interruptor=(False, "detenido"))
    _caso(empresa)

    r = _correr(empresa)

    assert (r["modo"], r["creadas"]) == (O.SOMBRA, 0)
    assert OrdenTrabajo.objects.count() == 0


def test_f3_si_le_quitan_la_tarea_a_mitad_de_vuelta_para(
        abierto, plantillas, admin_profile):
    _caso(abierto)
    _caso(abierto)

    def motor_y_quitar(caso_id):
        #  Mientras se pide la primera ficha, una persona le quita la tarea.
        td.quitar(abierto, td.CREAR_LAS_ORDENES, actor=admin_profile)
        return _Motor()(caso_id)

    r = _correr(abierto, motor_y_quitar)

    assert (r["creadas"], r["se_apago"]) == (1, 1)


def test_f4_un_caso_que_se_cerro_mientras_tanto_no_recibe_orden(
        abierto, plantillas):
    from cases.models import Case

    caso = _caso(abierto)

    def motor_y_cerrar(caso_id):
        Case.objects.filter(pk=caso.pk).update(status="Closed")
        return _Motor()(caso_id)

    r = _correr(abierto, motor_y_cerrar)

    assert (r["creadas"], r["ya_tenian"]) == (0, 1)
    assert OrdenTrabajo.objects.count() == 0


def test_f5_una_propuesta_rechazada_mientras_tanto_no_recibe_orden(
        abierto, plantillas):
    caso = _caso(abierto)

    def motor_y_rechazar(caso_id):
        P.objects.filter(origen_id=str(caso.id)).update(estado=P.RECHAZADA)
        return _Motor()(caso_id)

    r = _correr(abierto, motor_y_rechazar)

    assert (r["creadas"], r["ya_tenian"]) == (0, 1)
    assert OrdenTrabajo.objects.count() == 0


def test_f6_un_motor_lento_cuenta_como_caido(abierto, plantillas):
    _caso(abierto)
    _caso(abierto)
    motor = _Motor({"contexto_disponible": False, "motor_alcanzado": False,
                    "motivo": "ReadTimeout"})

    r = _correr(abierto, motor)

    assert (r["motor_caido"], len(motor.preguntas)) == (2, 1)


def _otra_transaccion(org, quien, espera=2):
    """Corre `quien` en su propia conexion, dentro de una transaccion que
    queda abierta `espera` segundos despues. Devuelve (hilo, errores)."""
    import threading
    import time

    from django.db import connection, transaction

    listo, errores = threading.Event(), []

    def correr():
        try:
            from conftest import _apply_rls_context
            _apply_rls_context(org.id)
            with transaction.atomic():
                quien()
                listo.set()
                time.sleep(espera)
        except Exception as e:                                   # noqa: BLE001
            errores.append(repr(e))
            listo.set()
        finally:
            connection.close()

    hilo = threading.Thread(target=correr)
    hilo.start()
    assert listo.wait(15)
    return hilo, errores


@pytest.mark.django_db(transaction=True)
def test_f7_el_supervisor_espera_al_boton_despachar(abierto, plantillas):
    """Una persona tiene el caso bloqueado y esta creando su orden: el
    Supervisor espera y despues ve que ya existe. Sin el bloqueo por caso, la
    leia sin confirmar y salian dos."""
    from campo.services.despacho import bloquear_el_caso

    caso = _caso(abierto)
    f = O.decidir(abierto, A_LAS_3)["crear"][0]
    propuesta = P.objects.get(origen_id=str(caso.id))

    def el_boton():
        bloquear_el_caso(abierto, str(caso.id))
        OrdenTrabajo.objects.create(
            org=abierto, numero=900, tipo_trabajo_version=plantillas["soporte"],
            origen_sistema="crm", origen_ref=str(caso.id))

    hilo, errores = _otra_transaccion(abierto, el_boton)
    r = O._crear_una(abierto, propuesta, f, _Motor()(str(caso.id)),
                     ahora=A_LAS_3, zona=BOGOTA)
    hilo.join()

    assert not errores
    assert r == "ya_tenia"
    assert OrdenTrabajo.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_f8_el_boton_despachar_espera_al_supervisor_y_lo_avisa(
        abierto, plantillas, admin_client, monkeypatch):
    """Al reves: el Supervisor tiene el caso bloqueado y crea; la persona que
    aprieta Despachar espera, y la respuesta le dice que ya habia una."""
    from campo import despacho_views
    from campo.services.despacho import bloquear_el_caso

    monkeypatch.setattr(despacho_views, "contexto_del_caso",
                        lambda case_id: _Motor()(case_id))
    caso = _caso(abierto)

    def el_supervisor():
        bloquear_el_caso(abierto, str(caso.id))
        OrdenTrabajo.objects.create(
            org=abierto, numero=900, tipo_trabajo_version=plantillas["soporte"],
            origen_sistema="crm", origen_ref=str(caso.id))

    import time

    #  8 s y no 2: armar la peticion de prueba ya tarda un par de segundos, y
    #  con 2 la otra transaccion confirmaba antes de que la vista mirara --
    #  la prueba pasaba sin el bloqueo (mutacion F18, 25/10/2026). Ahora se
    #  mide ademas que el boton ESPERO.
    hilo, errores = _otra_transaccion(abierto, el_supervisor, espera=8)
    t0 = time.monotonic()
    r = admin_client.post("/api/campo/trabajos/crear/", {
        "work_type_version_id": str(plantillas["soporte"].id),
        "case_id": str(caso.id)}, format="json")
    espero = time.monotonic() - t0
    hilo.join()

    assert not errores
    assert r.status_code == 201, r.content
    assert r.json()["ordenes_activas_del_caso"] == [900]
    assert espero >= 4, espero
