# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CIERRA SOLO LO QUE SU REVISION DIO POR BUENO  --  30/10/2026
================================================================================
SPEC/objetivos/revision-del-cierre.md. Ver `campo/cierre_por_el_supervisor.py`.
El motor se sustituye en el borde (`requests.post`): se afirma sobre lo que
SALE hacia el motor y sobre lo que queda en Dexter.

  S1  apagado (por omision): no le pide nada al motor.
  S2  encendido y el motor cierra el ticket: la orden queda APROBADA y
      CERRADA a nombre del Supervisor, por la ruta AUTONOMA, sin `actor`.
  S3  el motor se niega (B7_REQUERIDO): la orden queda como estaba, para una
      persona, con el motivo anotado; no se reintenta antes de una hora.
  S4  «Revisalo» y «No se cierra» no se tocan.
  S5  si una persona la valido en el medio, no se pisa.
  S6  sin ticket del ISP: no hay nada afuera; la cierra adentro.
  S7  la tarea recorre las empresas con su contexto.
  S8  el interruptor se edita desde la pantalla, solo quien gestiona.
  S9  Programacion dice por que no pudo, y el log que el Supervisor la cerro
      (con «Terminó» una sola vez).

    pytest campo/tests/test_cierre_por_el_supervisor.py
================================================================================
"""
import datetime as dt
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from campo import cierre_por_el_supervisor as CS
from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    EvidenciaTrabajo,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.seguimiento import ConfiguracionDeSeguimiento
from campo.services import cierre_en_isp

pytestmark = pytest.mark.django_db


class _Respuesta:
    def __init__(self, status=200, cuerpo=None):
        self.status_code = status
        self._cuerpo = cuerpo if cuerpo is not None else {"cerrado": True, "referencia": "x"}
        self.content = b"{}"

    def json(self):
        return self._cuerpo


B7 = _Respuesta(409, {"cerrado": False, "codigo": "NO_AUTORIZADA_PARA_EL_SUPERVISOR",
                      "motivo": "B7_REQUERIDO: el secreto de firma sigue en la base"})


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    monkeypatch.setenv("MOTOR_TENANT", "tenant-de-prueba")
    monkeypatch.delenv(cierre_en_isp.BANDERA, raising=False)


@pytest.fixture
def encendido(org_a):
    return ConfiguracionDeSeguimiento.objects.create(org=org_a, supervisor_cierra_solo=True)


@pytest.fixture
def orden(org_a, user_profile):
    """Terminada, con todo bien: la revision dice «Se puede cerrar»."""
    wt = WorkType.objects.create(org=org_a, codigo="sop", nombre="Soporte")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_ont", "titulo": "Foto de la ONT", "tipo": "foto", "obligatorio": True}]})
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=3, tipo_trabajo_version=v, zona="X",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE, completada_campo_en=timezone.now(),
        contexto={"ticket": "94721"})
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico",
                                     es_principal=True)
    EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=o, requisito_id="foto_ont", vuelta=o.vuelta, sha256="s",
        storage_key="k/f", nombre_original="f.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    EventoTrabajo.objects.create(
        org=org_a, orden=o, tipo="cierre_campo",
        datos={"definicion": [{"id": "servicio_validado"}],
               "respuestas": {"solucion": "Cambié el conector", "servicio_validado": True}})
    m = MaterialCatalogo.objects.create(org=org_a, codigo="CON", nombre="Conector", unidad="u")
    MovimientoDeMaterial.objects.create(
        org=org_a, material=m, orden=o, tipo=MovimientoDeMaterial.CONSUMO,
        cantidad=Decimal("1"), profile=user_profile, idempotency_key="cs-1")
    return o


def test_s1_apagado_no_pide_nada(org_a, orden):
    with mock.patch("requests.post") as post:
        r = CS.cerrar_lo_revisado(org_a)
    assert r == {"cerradas": 0, "bloqueadas": 0, "apagado": True}
    post.assert_not_called()


def test_s2_el_motor_cierra_y_la_orden_queda_aprobada_y_cerrada(org_a, orden, encendido):
    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        r = CS.cerrar_lo_revisado(org_a)

    assert (r["cerradas"], r["bloqueadas"]) == (1, 0)
    url = post.call_args.args[0]
    assert url.endswith(f"/interno/orden/{orden.id}/cerrar-ticket-supervisor"), url
    cuerpo = post.call_args.kwargs["json"]
    assert set(cuerpo) == {"ticket", "texto"}, "la ruta del Supervisor no lleva actor"
    assert cuerpo["ticket"] == "94721"
    orden.refresh_from_db()
    assert (orden.estado_operativo, orden.estado_validacion) == (
        OrdenTrabajo.CERRADA, OrdenTrabajo.APROBADO)
    tipos = set(EventoTrabajo.objects.filter(orden=orden).values_list("tipo", flat=True))
    assert {cierre_en_isp.EVENTO_CERRADO, CS.EVENTO_CERRADA, "validacion_aprobada",
            "orden_cerrada"} <= tipos
    aprobada = EventoTrabajo.objects.get(orden=orden, tipo="validacion_aprobada")
    assert aprobada.profile is None and "Aprobada por el Supervisor" in aprobada.datos["observacion"]


def test_s3_el_motor_se_niega_y_queda_para_una_persona(org_a, orden, encendido):
    ahora = timezone.now()
    with mock.patch("requests.post", return_value=B7) as post:
        r = CS.cerrar_lo_revisado(org_a, ahora=ahora)
        assert (r["cerradas"], r["bloqueadas"]) == (0, 1)
        orden.refresh_from_db()
        assert (orden.estado_operativo, orden.estado_validacion) == (
            OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.PENDIENTE)
        anotado = EventoTrabajo.objects.get(orden=orden, tipo=CS.EVENTO_BLOQUEADO)
        assert "B7_REQUERIDO" in anotado.datos["detalle"]

        #  Diez minutos despues no se vuelve a pedir; una hora despues, si.
        CS.cerrar_lo_revisado(org_a, ahora=ahora + dt.timedelta(minutes=10))
        assert post.call_count == 1
        CS.cerrar_lo_revisado(org_a, ahora=ahora + dt.timedelta(minutes=61))
        assert post.call_count == 2


def test_s4_lo_que_pide_una_persona_no_se_toca(org_a, orden, encendido):
    EventoTrabajo.objects.filter(orden=orden, tipo="cierre_campo").update(
        datos={"definicion": [{"id": "servicio_validado"}],
               "respuestas": {"servicio_validado": False}})
    with mock.patch("requests.post") as post:
        r = CS.cerrar_lo_revisado(org_a)
    assert (r["cerradas"], r["bloqueadas"]) == (0, 0)
    post.assert_not_called()

    MovimientoDeMaterial.objects.filter(orden=orden).delete()
    EventoTrabajo.objects.filter(orden=orden, tipo="cierre_campo").update(
        datos={"definicion": [], "respuestas": {}})
    with mock.patch("requests.post") as post:
        CS.cerrar_lo_revisado(org_a)
    post.assert_not_called()


def test_s5_si_una_persona_la_valido_en_el_medio_no_se_pisa(org_a, orden, encendido):
    def la_valido_alguien(*a, **k):
        OrdenTrabajo.objects.filter(pk=orden.pk).update(
            estado_validacion=OrdenTrabajo.REQUIERE_CORRECCION)
        return _Respuesta()

    with mock.patch("requests.post", side_effect=la_valido_alguien):
        r = CS.cerrar_lo_revisado(org_a)

    assert r["cerradas"] == 0
    orden.refresh_from_db()
    assert orden.estado_validacion == OrdenTrabajo.REQUIERE_CORRECCION
    assert not EventoTrabajo.objects.filter(orden=orden, tipo=CS.EVENTO_CERRADA).exists()


def test_s6_sin_ticket_del_isp_la_cierra_adentro(org_a, orden, encendido):
    OrdenTrabajo.objects.filter(pk=orden.pk).update(contexto={})
    with mock.patch("requests.post") as post:
        r = CS.cerrar_lo_revisado(org_a)
    post.assert_not_called()
    assert r["cerradas"] == 1
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CERRADA


def test_s7_la_tarea_recorre_las_empresas_con_su_contexto(org_a):
    from campo import tasks

    with mock.patch("common.tasks.set_rls_context") as fijar, \
            mock.patch("common.tasks.clear_rls_context") as limpiar, \
            mock.patch.object(CS, "cerrar_lo_revisado",
                              return_value={"cerradas": 1, "bloqueadas": 2,
                                            "apagado": False}) as cerrar:
        salida = tasks.cerrar_lo_revisado()

    assert cerrar.call_count >= 1
    assert mock.call(org_a.id) in fijar.call_args_list
    assert limpiar.called
    assert (salida["cerradas"] >= 1, salida["errores"]) == (True, [])


URL = "/api/campo/seguimiento/configuracion/"


def test_s8_el_interruptor_se_edita_desde_la_pantalla(admin_client, user_client, org_a):
    assert admin_client.get(URL).json() == {"recordar_al_tecnico": True,
                                            "supervisor_cierra_solo": False}
    r = admin_client.put(URL, {"supervisor_cierra_solo": True}, format="json")
    assert r.status_code == 200 and r.json()["supervisor_cierra_solo"] is True
    assert CS.cierra_solo(org_a)

    assert admin_client.put(URL, {"supervisor_cierra_solo": "si"},
                            format="json").status_code == 400
    assert user_client.put(URL, {"supervisor_cierra_solo": False},
                           format="json").status_code in (403, 404)
    assert CS.cierra_solo(org_a), "quien no gestiona no lo apaga"


def test_s9_programacion_dice_por_que_no_pudo_y_el_log_que_la_cerro(
        org_a, orden, encendido, user_profile):
    import zoneinfo

    from campo import dia_publicado as D
    from campo import tiempos_del_dia as TD
    from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                                  JornadaDeCuadrilla, PersonaDeCampo)

    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    bogota = zoneinfo.ZoneInfo("America/Bogota")
    hoy = timezone.now().astimezone(bogota).date()
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla #5")
    j = JornadaDeCuadrilla.objects.create(org=org_a, cuadrilla=c, fecha=hoy,
                                          labor=JornadaDeCuadrilla.CORRECTIVO)
    persona = PersonaDeCampo.objects.create(org=org_a, profile=user_profile, nombre="T")
    IntegranteDeJornada.objects.create(org=org_a, jornada=j, persona=persona, rol="tecnico")

    with mock.patch("requests.post", return_value=B7):
        CS.cerrar_lo_revisado(org_a)
    fila = D.del_dia(org_a, hoy)["cuadrillas"][0]["ordenes"][0]
    assert "B7_REQUERIDO" in fila["revision"]["supervisor_no_pudo"]["detalle"]

    EventoTrabajo.objects.filter(orden=orden, tipo=CS.EVENTO_BLOQUEADO).delete()
    EventoTrabajo.objects.create(org=org_a, orden=orden, tipo="transicion",
                                 datos={"nuevo_estado": "completada_campo"})
    with mock.patch("requests.post", return_value=_Respuesta()):
        CS.cerrar_lo_revisado(org_a)
    textos = [e["texto"] for e in TD.log_del_dia([orden], fecha=hoy, zona=bogota, tiempos={})]
    assert "El Supervisor aprobó y cerró OT #3" in textos
    assert sum(t.startswith("Terminó OT #3") for t in textos) == 1, textos
