# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR LE RECUERDA AL TECNICO QUE REPORTE  --  30/10/2026
================================================================================
El usuario: «el supervisor no solo debe dejar notificado en la pantalla de
programacion, sino que le manda el mensaje al tecnico». Ver
`campo/recordatorio_de_reporte.py`.

Se afirma sobre lo que SALE hacia el telefono (`push_fcm.mandar_a_un_telefono`)
y sobre la notificacion que queda en la plataforma:

  R1  vencida hoy: UN aviso, con el numero y los minutos, sin datos del
      cliente; la vuelta siguiente no repite ni el push ni la notificacion.
  R2  el tecnico reporta y vuelve a pasar la ventana: otro atraso, otro aviso.
  R3  lo que no se acusa: al dia, pausada por una novedad, empezada otro dia.
  R4  la empresa lo apago: nada.
  R5  sin telefono: queda en la app y el log dice que no llego al telefono.
  R6  el log del dia de la cuadrilla dice que el Supervisor se lo recordo.
  R7  la tarea recorre las empresas con su contexto.

    pytest campo/tests/test_recordatorio_de_reporte.py
================================================================================
"""
import datetime as dt
import json
import zoneinfo
from unittest import mock

import pytest
from django.utils import timezone

from campo import novedades as N
from campo import recordatorio_de_reporte as RR
from campo import tiempos_del_dia as TD
from campo.avisos import DispositivoDeTecnico
from campo.models import AsignacionTrabajo, EventoTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.seguimiento import ConfiguracionDeSeguimiento
from campo.services import avisos, push_fcm
from common.models import Notification

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")


@pytest.fixture
def org(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    return org_a


@pytest.fixture
def mediodia():
    """Hoy a las 12:00 en Bogota: el reloj fijo de la regla."""
    return timezone.now().astimezone(BOGOTA).replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture
def fcm():
    enviados = []

    def mandar(token, titulo, texto, enlace, *, aviso_id="", verbo="", contenido=None):
        enviados.append({"token": token, "titulo": titulo, "texto": texto, "enlace": enlace,
                         "aviso_id": aviso_id, "verbo": verbo, "contenido": contenido or {}})
        return push_fcm.ENTREGADO

    with mock.patch.object(push_fcm, "esta_configurado", return_value=True), \
            mock.patch.object(push_fcm, "mandar_a_un_telefono", side_effect=mandar):
        yield enviados


@pytest.fixture
def orden(org, user_profile):
    wt = WorkType.objects.create(org=org, codigo="sop", nombre="Soporte")
    v = WorkTypeVersion.objects.create(work_type=wt, version=1,
                                       estado=WorkTypeVersion.PUBLICADA, esquema={"campos": []})
    o = OrdenTrabajo.objects.create(
        org=org, numero=4321, tipo_trabajo_version=v, estado_operativo=OrdenTrabajo.EN_SITIO,
        cliente_nombre="Beatriz Pinzón", cliente_direccion="Calle 50 # 10-20")
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico",
                                     es_principal=True)
    return o


def _telefono(org, profile):
    return DispositivoDeTecnico.objects.create(org=org, profile=profile, token="tok-1",
                                               plataforma="android", activo=True)


def _reporte(orden, cuando, tipo="accion_marcar_llegada"):
    ev = EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo, datos={})
    EventoTrabajo.objects.filter(pk=ev.pk).update(created_at=cuando)


def test_r1_vencida_hoy_un_aviso_y_la_vuelta_siguiente_no_repite(
        org, orden, user_profile, fcm, mediodia):
    _telefono(org, user_profile)
    _reporte(orden, mediodia - dt.timedelta(minutes=40))

    r = RR.recordar_para(org, ahora=mediodia)

    assert r == {"vencidas": 1, "avisadas": 1}
    assert len(fcm) == 1
    m = fcm[0]
    assert (m["verbo"], m["texto"], m["enlace"]) == (
        avisos.VERBO_SIN_REPORTE,
        "⏱ OT #4321: 40 min sin reportar. Mandá un avance desde la app.",
        f"/ot/{orden.id}")
    assert m["contenido"] == {"orden_numero": 4321, "minutos": 40}
    n = Notification.objects.get(recipient=user_profile, verb=avisos.VERBO_SIN_REPORTE)
    assert str(n.id) == m["aviso_id"], "el push es LA notificacion, no una copia"
    crudo = json.dumps(m, ensure_ascii=False)
    assert "Beatriz" not in crudo and "Calle 50" not in crudo

    #  Cinco minutos despues, el mismo atraso: ni push ni notificacion nueva.
    r2 = RR.recordar_para(org, ahora=mediodia + dt.timedelta(minutes=5))
    assert r2 == {"vencidas": 1, "avisadas": 0}
    assert len(fcm) == 1
    assert Notification.objects.filter(recipient=user_profile,
                                       verb=avisos.VERBO_SIN_REPORTE).count() == 1


def test_r2_reporta_y_vuelve_a_pasar_la_ventana_es_otro_aviso(
        org, orden, user_profile, fcm, mediodia):
    _telefono(org, user_profile)
    _reporte(orden, mediodia - dt.timedelta(minutes=40))
    RR.recordar_para(org, ahora=mediodia)
    _reporte(orden, mediodia + dt.timedelta(minutes=1), tipo="avance_campo")

    assert RR.recordar_para(org, ahora=mediodia + dt.timedelta(minutes=10))["avisadas"] == 0
    r = RR.recordar_para(org, ahora=mediodia + dt.timedelta(minutes=35))

    assert r["avisadas"] == 1
    assert len(fcm) == 2
    assert fcm[1]["texto"].startswith("⏱ OT #4321: 34 min sin reportar")


def test_r3_lo_que_no_se_acusa(org, orden, user_profile, fcm, mediodia):
    _telefono(org, user_profile)
    #  Al dia: reporto hace 10 minutos.
    _reporte(orden, mediodia - dt.timedelta(minutes=10))
    assert RR.recordar_para(org, ahora=mediodia) == {"vencidas": 0, "avisadas": 0}

    #  Pausada: la cuadrilla aviso una novedad.
    N.NovedadDeCuadrilla.objects.create(
        org=org, profile=user_profile, tipo=N.LLANTA, afecta=N.UNA_HORA,
        fecha=mediodia.date(), avisada_en=mediodia + dt.timedelta(minutes=20), clave="n-1")
    assert RR.recordar_para(org, ahora=mediodia + dt.timedelta(minutes=45))["vencidas"] == 0

    #  Empezada otro dia (la OT #3 del 15/10): no es un atraso de hoy.
    EventoTrabajo.objects.filter(orden=orden).update(
        created_at=mediodia - dt.timedelta(days=15))
    N.NovedadDeCuadrilla.objects.all().delete()
    assert RR.recordar_para(org, ahora=mediodia) == {"vencidas": 0, "avisadas": 0}
    assert fcm == []


def test_r4_la_empresa_lo_apago(org, orden, user_profile, fcm, mediodia):
    _telefono(org, user_profile)
    _reporte(orden, mediodia - dt.timedelta(minutes=40))
    ConfiguracionDeSeguimiento.objects.create(org=org, recordar_al_tecnico=False)

    assert RR.recordar_para(org, ahora=mediodia) == {"vencidas": 0, "avisadas": 0}
    assert fcm == []
    assert not Notification.objects.filter(verb=avisos.VERBO_SIN_REPORTE).exists()


def test_r5_y_r6_sin_telefono_queda_en_la_app_y_el_log_lo_dice(
        org, orden, user_profile, fcm, mediodia):
    _reporte(orden, mediodia - dt.timedelta(minutes=40))

    assert RR.recordar_para(org, ahora=mediodia)["avisadas"] == 1
    assert fcm == []
    assert Notification.objects.filter(recipient=user_profile,
                                       verb=avisos.VERBO_SIN_REPORTE).count() == 1

    log = TD.log_del_dia([orden], fecha=timezone.now().astimezone(BOGOTA).date(),
                         zona=BOGOTA, tiempos={})
    assert [e["texto"] for e in log if e["de"] == "supervisor"] == [
        "El Supervisor le recordó reportar en OT #4321 (no llegó al teléfono)"]


def test_r6_con_telefono_el_log_no_dice_que_no_llego(org, orden, user_profile, fcm, mediodia):
    _telefono(org, user_profile)
    _reporte(orden, mediodia - dt.timedelta(minutes=40))
    RR.recordar_para(org, ahora=mediodia)

    log = TD.log_del_dia([orden], fecha=timezone.now().astimezone(BOGOTA).date(),
                         zona=BOGOTA, tiempos={})
    assert "El Supervisor le recordó reportar en OT #4321" in [e["texto"] for e in log]


def test_r7_la_tarea_recorre_las_empresas_con_su_contexto(org, orden, user_profile, fcm):
    from campo import tasks

    with mock.patch("common.tasks.set_rls_context") as fijar, \
            mock.patch("common.tasks.clear_rls_context") as limpiar, \
            mock.patch.object(RR, "recordar_para",
                              return_value={"vencidas": 2, "avisadas": 1}) as recordar:
        salida = tasks.recordar_reportes()

    assert recordar.call_count >= 1
    assert mock.call(org.id) in fijar.call_args_list
    assert limpiar.called
    assert salida["avisadas"] >= 1 and salida["errores"] == []
