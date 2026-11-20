# -*- coding: utf-8 -*-
"""
================================================================================
 LA MEDICION DESPUES DEL ARREGLO  --  18/10/2026
================================================================================

LO QUE AFIRMA
-------------
Que cuando un tecnico completa en campo la orden de una falla de servicio, el
Supervisor vuelve a medir el equipo (correccion 2 del usuario, regla 3) y deja
en la propuesta si la señal quedo en rango; que no mide lo que no corresponde
--una orden vieja, una sin completar, un trabajo pedido--, que no repite lo
que ya midio y que reintenta lo que no pudo; y que corre en el ciclo.

Sobre el EFECTO: la pieza escrita y las llamadas al motor.
================================================================================
"""
import logging
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from operaciones import paso_a_despacho as pad
from operaciones import supervisor as sup
from operaciones import verificacion_de_arreglos as vda
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

CLIENTE = "Zoraida Clientela"


def _respuesta(estado, *, causa="", dbm=None):
    if dbm is None:
        senal = "sin_dato"
    else:
        senal = "buena" if -25.0 <= dbm <= -8.0 else "debil"
    return {"id_servicio": "3614", "equipo_registrado": True, "estado": estado,
            "causa_caida": causa if estado == "caido" else "",
            "senal_dbm": dbm, "senal": senal, "estado_config": "match",
            "motivo": ""}


BIEN = _respuesta("en_linea", dbm=-21.5)
MAL = _respuesta("en_linea", dbm=-27.9)
SIN_MEDIR = {"id_servicio": "3614", "equipo_registrado": False,
             "estado": "desconocido", "causa_caida": "", "senal_dbm": None,
             "senal": "sin_dato", "estado_config": "",
             "motivo": "el proveedor optico no respondio"}


class _Motor:
    def __init__(self, respuesta=BIEN):
        self.respuesta = respuesta
        self.llamadas = []

    def __call__(self, org, id_servicio):
        self.llamadas.append(id_servicio)
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


def _caso_en_despacho(org, grupo=pad.FALLA_DE_SERVICIO, *, servicio="3614"):
    from cases.models import Case

    caso = Case.objects.create(
        org=org, name="No tiene internet", status="Assigned",
        priority="Normal", is_active=True, provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id=servicio, external_client_name=CLIENTE)
    P.objects.create(
        org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(caso.id), estado=P.ACEPTADA, revisado_en=timezone.now(),
        accion_propuesta="Revisar el servicio", motivo="x", prioridad=30,
        evidencia=[{"fuente": pad.FUENTE_DE_LA_LECTURA, "id": str(caso.id),
                    "dato": "lectura", "grupo": grupo,
                    "observado_en": timezone.now().isoformat()}])
    return caso


def _orden(org, caso, *, estado="completada_campo", hace_horas=2,
           con_fecha=None):
    """'con_fecha' fuerza la fecha de completada aunque el estado no lo sea:
    una orden devuelta a campo la conserva."""
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    n = OrdenTrabajo.objects.count() + 1
    wt = WorkType.objects.create(org=org, codigo=f"t{n}", nombre="T",
                                 labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})
    if con_fecha is None:
        con_fecha = estado in ("completada_campo", "cerrada")
    completada = (timezone.now() - timedelta(hours=hace_horas)
                  if con_fecha else None)
    return OrdenTrabajo.objects.create(
        org=org, numero=n, tipo_trabajo_version=version,
        estado_operativo=estado, zona="SOLEDAD", origen_sistema="crm",
        origen_ref=str(caso.id), completada_campo_en=completada)


def _pieza(caso):
    return vda.ultima_verificacion(P.objects.get(origen_id=str(caso.id)))


def _correr(org, motor):
    return vda.verificar_los_arreglos(
        org, medir=motor, presupuesto_=sup.presupuesto(tope=10, segundos=600))


def test_a_mide_la_falla_arreglada_y_nada_mas(org_a):
    arreglada = _caso_en_despacho(org_a)
    _orden(org_a, arreglada)
    vieja = _caso_en_despacho(org_a)
    _orden(org_a, vieja, hace_horas=vda.HORAS_PARA_VERIFICAR + 1)
    #  DEVUELTA A CAMPO: conserva la fecha de completada, y el arreglo no esta
    #  hecho. Sin la fecha, la descartaba el filtro de las 48 horas y esta
    #  prueba no veia el del estado (mutacion V1, 19/10).
    sin_terminar = _caso_en_despacho(org_a)
    _orden(org_a, sin_terminar, estado="asignada", con_fecha=True)
    trabajo = _caso_en_despacho(org_a, pad.TRABAJO_PEDIDO)
    _orden(org_a, trabajo)
    motor = _Motor()

    informe = _correr(org_a, motor)

    assert motor.llamadas == ["3614"], "solo la falla arreglada en las 48 h"
    pieza = _pieza(arreglada)
    assert pieza["quedo_en_rango"] is True
    assert "quedo en rango despues del arreglo" in pieza["dato"]
    for otro in (vieja, sin_terminar, trabajo):
        assert _pieza(otro) is None
    assert (informe["medidas"], informe["quedaron_en_rango"]) == (1, 1)


def test_b_si_no_quedo_en_rango_lo_dice_y_no_vuelve_a_medir(org_a, monkeypatch):
    caso = _caso_en_despacho(org_a)
    _orden(org_a, caso)
    motor = _Motor(MAL)

    _correr(org_a, motor)
    #  PASADA LA HORA DEL REINTENTO: lo concluyente no se repite nunca, no
    #  solo dentro de la hora (mutacion V4, 19/10).
    luego = timezone.now() + timedelta(minutes=vda.MINUTOS_PARA_REINTENTAR + 1)
    monkeypatch.setattr(timezone, "now", lambda: luego)
    _correr(org_a, motor)

    pieza = _pieza(caso)
    assert pieza["quedo_en_rango"] is False
    assert "NO quedo en rango" in pieza["dato"] and "(-27.9 dBm)" in pieza["dato"]
    assert motor.llamadas == ["3614"], "lo que ya se midio no se repite"


def test_c_lo_que_no_se_pudo_medir_se_reintenta_a_la_hora(org_a, monkeypatch):
    caso = _caso_en_despacho(org_a)
    _orden(org_a, caso)
    motor = _Motor(SIN_MEDIR)

    _correr(org_a, motor)
    _correr(org_a, motor)
    assert _pieza(caso)["quedo_en_rango"] is None
    assert len(motor.llamadas) == 1, "antes de la hora no se repite"

    luego = timezone.now() + timedelta(minutes=vda.MINUTOS_PARA_REINTENTAR + 1)
    monkeypatch.setattr(timezone, "now", lambda: luego)
    motor.respuesta = BIEN
    _correr(org_a, motor)

    assert len(motor.llamadas) == 2
    assert _pieza(caso)["quedo_en_rango"] is True


def test_c2_lo_que_nunca_se_puede_medir_tiene_tope(org_a, monkeypatch):
    """Auditor independiente, 19/10/2026: se pedia cada hora durante dos dias
    --polling de un endpoint que el proveedor prohibe usar asi--."""
    caso = _caso_en_despacho(org_a)
    _orden(org_a, caso)
    motor = _Motor(SIN_MEDIR)
    base = timezone.now()

    for i in range(vda.INTENTOS_MAXIMOS + 2):
        luego = base + timedelta(minutes=(vda.MINUTOS_PARA_REINTENTAR + 1) * i)
        monkeypatch.setattr(timezone, "now", lambda t=luego: t)
        _correr(org_a, motor)

    assert len(motor.llamadas) == vda.INTENTOS_MAXIMOS
    assert "no se vuelve a pedir" in _pieza(caso)["dato"]


def test_c3_lo_nuevo_va_antes_que_los_reintentos(org_a, monkeypatch):
    """Con el tope de la vuelta, cinco que no se pueden medir ocupaban todas
    las plazas y la orden nueva no se media nunca."""
    vieja = _caso_en_despacho(org_a, servicio="1111")
    _orden(org_a, vieja, hace_horas=40)
    _correr(org_a, _Motor(SIN_MEDIR))
    nueva = _caso_en_despacho(org_a, servicio="2222")
    _orden(org_a, nueva, hace_horas=1)
    luego = timezone.now() + timedelta(minutes=vda.MINUTOS_PARA_REINTENTAR + 1)
    monkeypatch.setattr(timezone, "now", lambda: luego)
    motor = _Motor()

    vda.verificar_los_arreglos(
        org_a, medir=motor, presupuesto_=sup.presupuesto(tope=1, segundos=600))

    assert motor.llamadas == ["2222"]


def test_c4_no_se_mide_un_cambio_de_equipo(org_a):
    """Con la accion autorizada (cambio de equipo o de router) lo mas
    probable es que el ISP siga con el serial viejo: se mediria el equipo que
    se retiro."""
    caso = _caso_en_despacho(org_a)
    P.objects.filter(origen_id=str(caso.id)).update(evidencia=[{
        "fuente": pad.FUENTE_DE_LA_LECTURA, "id": str(caso.id),
        "dato": "lectura", "grupo": pad.FALLA_DE_SERVICIO,
        "accion_autorizada": "si",
        "observado_en": timezone.now().isoformat()}])
    _orden(org_a, caso)
    motor = _Motor()

    _correr(org_a, motor)

    assert motor.llamadas == [] and _pieza(caso) is None


def test_d_un_error_del_motor_no_deja_pieza(org_a):
    caso = _caso_en_despacho(org_a)
    _orden(org_a, caso)

    informe = _correr(org_a, _Motor(ConnectionError("motor caido")))

    assert _pieza(caso) is None
    assert informe["errores"] == 1


def test_e_una_segunda_visita_se_vuelve_a_medir(org_a):
    caso = _caso_en_despacho(org_a)
    _orden(org_a, caso, hace_horas=30)
    motor = _Motor(MAL)
    _correr(org_a, motor)

    segunda = _orden(org_a, caso, hace_horas=1)
    motor.respuesta = BIEN
    _correr(org_a, motor)

    pieza = _pieza(caso)
    assert pieza["orden"] == str(segunda.id) and pieza["quedo_en_rango"] is True
    assert len(motor.llamadas) == 2


def test_f_corre_en_el_ciclo_y_el_log_no_lleva_al_cliente(
        org_a, monkeypatch, caplog):
    from operaciones import medicion_de_fallas as mdf

    caso = _caso_en_despacho(org_a)
    _orden(org_a, caso)
    motor = _Motor()
    monkeypatch.setattr(mdf, "_medir_con_el_motor", motor)

    with caplog.at_level(logging.INFO, logger="operaciones.supervisor"):
        resumen = sup.correr_ciclo(org_a)

    assert "medicion despues del arreglo" not in [
        f["fase"] for f in resumen.get("fases_que_fallaron", [])]
    assert resumen["despues_del_arreglo"]["quedaron_en_rango"] == 1
    assert _pieza(caso)["quedo_en_rango"] is True
    assert "medicion despues del arreglo · candidatas=1" in caplog.text
    assert CLIENTE not in caplog.text
