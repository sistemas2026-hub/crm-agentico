# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CIERRA SOLO LO QUE SU REVISION DIO POR BUENO  --  30/10/2026
================================================================================
SPEC/objetivos/revision-del-cierre.md. Ver `campo/cierre_por_el_supervisor.py`.
El motor se sustituye en el borde (`requests.post`): se afirma sobre lo que
SALE hacia el motor y sobre lo que queda en Dexter.

  P   las puertas, como las otras tareas de accion: sin la tarea delegada, sin
      el nivel 3 (con el interruptor), o sin MOTOR_TENANT, SOMBRA: no le pide
      nada al motor y dice cuantas cerraria.
  S2  abiertas y el motor cierra el ticket: la orden queda APROBADA y CERRADA
      a nombre del Supervisor, por la ruta AUTONOMA, sin `actor`.
  S3  el motor se niega (la quinta compuerta): queda para una persona, con el
      motivo; no se reintenta antes de una hora.
  S4  «Revisalo» y «No se cierra» no se tocan.
  S5  si una persona la devolvio en el medio, no se pisa y queda una ALERTA.
  S6  sin ticket del ISP: la cierra adentro (y con el interruptor detenido, no).
  V   una orden ya devuelta (vuelta 2) no la cierra solo.
  M   una de falla cuya medicion todavia no llego: «Revisalo», no se cierra; si
      no se puede saber cuales esperan, no cierra ninguna.
  C   el interruptor de la pantalla ya no habilita el cierre: solo recordar.
  L   Programacion dice por que no pudo, y el log que la cerro.
  H2  la ruta humana no se pide sin una persona.

    pytest campo/tests/test_cierre_por_el_supervisor.py
================================================================================
"""
import datetime as dt
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from campo import cierre_por_el_supervisor as CS
from campo import revision_del_cierre as RC
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
from campo.services import cierre_en_isp
from operaciones import autonomia
from operaciones import tareas_delegadas as td

pytestmark = pytest.mark.django_db


class _Respuesta:
    def __init__(self, status=200, cuerpo=None):
        self.status_code = status
        self._cuerpo = cuerpo if cuerpo is not None else {"cerrado": True, "referencia": "x"}
        self.content = b"{}"

    def json(self):
        return self._cuerpo


QUINTA = _Respuesta(409, {"cerrado": False, "codigo": "NO_AUTORIZADA_PARA_EL_SUPERVISOR",
                          "motivo": "APROBACION_HUMANA_REQUERIDA: la herramienta declara "
                                    "aprobacion humana (M06-E)"})


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    monkeypatch.delenv(cierre_en_isp.BANDERA, raising=False)
    #  Nada espera medicion salvo que la prueba lo diga.
    monkeypatch.setattr(RC, "pendientes_de_medir", lambda org, ahora=None: set())


@pytest.fixture
def abierto(org_a, admin_profile, monkeypatch):
    """Las puertas abiertas por el camino real, salvo el interruptor del motor,
    que en la base de pruebas no existe (como en `ordenes_de_despacho`)."""
    td.delegar(org_a, td.CERRAR_LO_REVISADO, actor=admin_profile,
               pedido_textual="aprobá y cerrá lo que des por bueno")
    autonomia.cambiar(org_a, 3, actor=admin_profile, motivo="cerrar lo revisado",
                      criterios="la revision del cierre en codigo")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))
    monkeypatch.setenv("MOTOR_TENANT", "tenant-de-prueba")
    return org_a


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


def _fase(org, **kw):
    return CS.cerrar_lo_revisado(org, **kw)["cierre_de_lo_revisado"]


# ---------------------------------------------------------------------------
# P · las puertas
# ---------------------------------------------------------------------------

def test_p_sin_la_tarea_queda_en_sombra(org_a, orden, admin_profile, monkeypatch):
    autonomia.cambiar(org_a, 3, actor=admin_profile, motivo="x", criterios="y")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))
    monkeypatch.setenv("MOTOR_TENANT", "t")
    with mock.patch("requests.post") as post:
        r = _fase(org_a)
    assert (r["modo"], r["cerraria"], r["cerradas"]) == (CS.SOMBRA, 1, 0)
    assert "delego" in r["por_que"]
    post.assert_not_called()
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO


def test_p2_sin_el_nivel_o_con_el_interruptor_detenido_tampoco(
        org_a, orden, admin_profile, monkeypatch):
    td.delegar(org_a, td.CERRAR_LO_REVISADO, actor=admin_profile)
    monkeypatch.setenv("MOTOR_TENANT", "t")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))
    with mock.patch("requests.post") as post:
        assert _fase(org_a)["modo"] == CS.SOMBRA, "sin nivel 3"
        autonomia.cambiar(org_a, 3, actor=admin_profile, motivo="x", criterios="y")
        monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                            lambda org: (False, "detenido por una persona"))
        assert _fase(org_a)["modo"] == CS.SOMBRA, "con el interruptor detenido"
    post.assert_not_called()


def test_p3_sin_motor_tenant_tampoco(abierto, orden, monkeypatch):
    monkeypatch.delenv("MOTOR_TENANT")
    with mock.patch("requests.post") as post:
        assert _fase(abierto)["modo"] == CS.SOMBRA
    post.assert_not_called()


# ---------------------------------------------------------------------------
# S · lo que hace con las puertas abiertas
# ---------------------------------------------------------------------------

def test_s2_el_motor_cierra_y_la_orden_queda_aprobada_y_cerrada(abierto, orden):
    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        r = _fase(abierto)

    assert (r["modo"], r["cerradas"], r["bloqueadas"]) == (CS.ACCION, 1, 0)
    url = post.call_args.args[0]
    assert url.endswith(f"/interno/orden/{orden.id}/cerrar-ticket-supervisor"), url
    assert set(post.call_args.kwargs["json"]) == {"ticket", "texto"}, "sin actor"
    orden.refresh_from_db()
    assert (orden.estado_operativo, orden.estado_validacion) == (
        OrdenTrabajo.CERRADA, OrdenTrabajo.APROBADO)
    aprobada = EventoTrabajo.objects.get(orden=orden, tipo="validacion_aprobada")
    assert aprobada.profile is None and "Aprobada por el Supervisor" in aprobada.datos["observacion"]
    assert EventoTrabajo.objects.filter(orden=orden, tipo=CS.EVENTO_CERRADA).exists()


def test_s3_el_motor_se_niega_y_queda_para_una_persona(abierto, orden):
    ahora = timezone.now()
    with mock.patch("requests.post", return_value=QUINTA) as post:
        r = _fase(abierto, ahora=ahora)
        assert (r["cerradas"], r["bloqueadas"]) == (0, 1)
        orden.refresh_from_db()
        assert (orden.estado_operativo, orden.estado_validacion) == (
            OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.PENDIENTE)
        anotado = EventoTrabajo.objects.get(orden=orden, tipo=CS.EVENTO_BLOQUEADO)
        assert "APROBACION_HUMANA_REQUERIDA" in anotado.datos["detalle"]
        _fase(abierto, ahora=ahora + dt.timedelta(minutes=10))
        assert post.call_count == 1
        _fase(abierto, ahora=ahora + dt.timedelta(minutes=61))
        assert post.call_count == 2


def test_s4_lo_que_pide_una_persona_no_se_toca(abierto, orden):
    EventoTrabajo.objects.filter(orden=orden, tipo="cierre_campo").update(
        datos={"definicion": [{"id": "servicio_validado"}],
               "respuestas": {"servicio_validado": False}})
    with mock.patch("requests.post") as post:
        assert _fase(abierto)["cerraria"] == 0
    post.assert_not_called()


def test_s5_si_una_persona_la_devolvio_en_el_medio_no_se_pisa_y_queda_alerta(abierto, orden):
    def la_devolvio_alguien(*a, **k):
        OrdenTrabajo.objects.filter(pk=orden.pk).update(
            estado_validacion=OrdenTrabajo.REQUIERE_CORRECCION)
        return _Respuesta()

    with mock.patch("requests.post", side_effect=la_devolvio_alguien):
        r = _fase(abierto)

    assert r["cerradas"] == 0
    orden.refresh_from_db()
    assert orden.estado_validacion == OrdenTrabajo.REQUIERE_CORRECCION
    assert not EventoTrabajo.objects.filter(orden=orden, tipo=CS.EVENTO_CERRADA).exists()
    assert EventoTrabajo.objects.filter(orden=orden, tipo=CS.EVENTO_DIVERGENCIA).exists(), (
        "el ticket quedo cerrado y la orden cambio: tiene que quedar una alerta")


def test_s6_sin_ticket_del_isp_la_cierra_adentro(abierto, orden):
    OrdenTrabajo.objects.filter(pk=orden.pk).update(contexto={})
    with mock.patch("requests.post") as post:
        assert _fase(abierto)["cerradas"] == 1
    post.assert_not_called()
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CERRADA


def test_v_una_orden_ya_devuelta_no_la_cierra_solo(abierto, orden):
    OrdenTrabajo.objects.filter(pk=orden.pk).update(vuelta=2)
    EvidenciaTrabajo.objects.filter(orden_trabajo=orden).update(vuelta=2)
    with mock.patch("requests.post") as post:
        assert _fase(abierto)["cerraria"] == 0
    post.assert_not_called()


def test_m_sin_la_medicion_que_espera_no_la_cierra(abierto, orden, monkeypatch):
    monkeypatch.setattr(RC, "pendientes_de_medir", lambda org, ahora=None: {str(orden.id)})
    r = RC.revisar(orden, pendientes={str(orden.id)})
    assert (r["veredicto"], {p["clave"]: p["ok"] for p in r["puntos"]}["medicion"]) == (
        RC.REVISAR, None)
    with mock.patch("requests.post") as post:
        assert _fase(abierto)["cerraria"] == 0
    post.assert_not_called()

    monkeypatch.setattr(RC, "pendientes_de_medir", lambda org, ahora=None: None)
    with mock.patch("requests.post") as post:
        r = _fase(abierto)
    assert (r["modo"], r["cerradas"]) == (CS.SOMBRA, 0), "sin saber cuales esperan, ninguna"
    post.assert_not_called()


def test_c_la_pantalla_ya_no_habilita_el_cierre(admin_client, user_client, org_a):
    URL = "/api/campo/seguimiento/configuracion/"
    assert admin_client.get(URL).json() == {"recordar_al_tecnico": True}
    r = admin_client.put(URL, {"recordar_al_tecnico": False,
                               "supervisor_cierra_solo": True}, format="json")
    assert r.status_code == 200 and r.json() == {"recordar_al_tecnico": False}
    assert admin_client.put(URL, {"recordar_al_tecnico": "si"},
                            format="json").status_code == 400
    assert user_client.put(URL, {"recordar_al_tecnico": True},
                           format="json").status_code in (403, 404)


def test_l_programacion_dice_por_que_no_pudo_y_el_log_que_la_cerro(
        abierto, orden, user_profile):
    import zoneinfo

    from campo import dia_publicado as D
    from campo import tiempos_del_dia as TD
    from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                                  JornadaDeCuadrilla, PersonaDeCampo)

    abierto.timezone = "America/Bogota"
    abierto.save(update_fields=["timezone"])
    bogota = zoneinfo.ZoneInfo("America/Bogota")
    hoy = timezone.now().astimezone(bogota).date()
    c = Cuadrilla.objects.create(org=abierto, nombre="Cuadrilla #5")
    j = JornadaDeCuadrilla.objects.create(org=abierto, cuadrilla=c, fecha=hoy,
                                          labor=JornadaDeCuadrilla.CORRECTIVO)
    persona = PersonaDeCampo.objects.create(org=abierto, profile=user_profile, nombre="T")
    IntegranteDeJornada.objects.create(org=abierto, jornada=j, persona=persona, rol="tecnico")

    with mock.patch("requests.post", return_value=QUINTA):
        _fase(abierto)
    fila = D.del_dia(abierto, hoy)["cuadrillas"][0]["ordenes"][0]
    assert "APROBACION_HUMANA_REQUERIDA" in fila["revision"]["supervisor_no_pudo"]["detalle"]

    EventoTrabajo.objects.filter(orden=orden, tipo=CS.EVENTO_BLOQUEADO).delete()
    EventoTrabajo.objects.create(org=abierto, orden=orden, tipo="transicion",
                                 datos={"nuevo_estado": "completada_campo"})
    with mock.patch("requests.post", return_value=_Respuesta()):
        _fase(abierto)
    textos = [e["texto"] for e in TD.log_del_dia([orden], fecha=hoy, zona=bogota, tiempos={})]
    assert "El Supervisor aprobó y cerró OT #3" in textos
    assert sum(t.startswith("Terminó OT #3") for t in textos) == 1, textos


def test_h2_la_ruta_humana_no_se_pide_sin_una_persona(abierto, orden):
    """Auditoria de frontera, H2: sin perfil no se inventa «Oficina de
    operaciones» para entrar por la puerta humana del motor."""
    with mock.patch("requests.post") as post:
        r = cierre_en_isp._cerrar(orden, None)
    assert r["estado"] == "no_cerrado" and "persona" in r["detalle"]
    post.assert_not_called()


def test_la_fase_corre_en_el_ciclo_despues_de_la_medicion(org_a, monkeypatch):
    """Se CORRE el ciclo y se mira en que orden se llamaron las dos fases: no
    alcanza con que el codigo las nombre (auditoria, 30/10/2026)."""
    from operaciones import supervisor

    llamadas = []
    monkeypatch.setattr(supervisor, "_verificar_los_arreglos",
                        lambda org, desatendido=False: llamadas.append("medicion") or {})
    monkeypatch.setattr(supervisor, "_cerrar_lo_revisado",
                        lambda org: llamadas.append("cierre") or {})

    supervisor.correr_ciclo(org_a)

    assert llamadas == ["medicion", "cierre"]


def test_m2_una_falla_nunca_medida_sigue_esperando_pasadas_las_48_horas(
        abierto, orden, monkeypatch):
    """La ventana de la medicion es de 48 h; la de «no se sabe» no tiene
    limite: una falla sin medicion concluyente no se cierra sola nunca."""
    from operaciones import paso_a_despacho as pad
    from operaciones.models import PropuestaSupervisor

    monkeypatch.undo()
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))
    monkeypatch.setenv("MOTOR_TENANT", "tenant-de-prueba")
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        origen_sistema="crm", origen_ref="caso-falla",
        completada_campo_en=timezone.now() - dt.timedelta(days=5))
    p = PropuestaSupervisor.objects.create(
        org=abierto, origen_id="caso-falla", estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[{"fuente": "lectura_del_ticket", "texto": "sin internet"}])
    monkeypatch.setattr(pad, "propuestas_que_llevan_a_despacho",
                        lambda org: PropuestaSupervisor.objects.filter(pk=p.pk))
    monkeypatch.setattr(pad, "_ultima_lectura_con_grupo",
                        lambda prop: {"grupo": pad.FALLA_DE_SERVICIO})

    assert RC.pendientes_de_medir(abierto) == {str(orden.id)}
    with mock.patch("requests.post") as post:
        assert _fase(abierto)["cerraria"] == 0
    post.assert_not_called()


def test_l2_la_alerta_de_divergencia_se_ve_en_el_log(abierto, orden):
    import zoneinfo

    from campo import tiempos_del_dia as TD

    bogota = zoneinfo.ZoneInfo("America/Bogota")
    EventoTrabajo.objects.create(org=abierto, orden=orden, tipo=CS.EVENTO_DIVERGENCIA, datos={})
    log = TD.log_del_dia([orden], fecha=timezone.now().astimezone(bogota).date(),
                         zona=bogota, tiempos={})
    alertas = [e["texto"] for e in log if e["de"] == "alerta"]
    assert any("cerró el ticket de OT #3 y la orden cambió" in t for t in alertas), log


def test_l3_sin_saber_que_espera_medicion_la_tarjeta_no_dice_se_puede_cerrar(
        abierto, orden, user_profile, monkeypatch):
    import zoneinfo

    from campo import dia_publicado as D
    from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                                  JornadaDeCuadrilla, PersonaDeCampo)

    monkeypatch.setattr(RC, "pendientes_de_medir", lambda org, ahora=None: None)
    abierto.timezone = "America/Bogota"
    abierto.save(update_fields=["timezone"])
    hoy = timezone.now().astimezone(zoneinfo.ZoneInfo("America/Bogota")).date()
    c = Cuadrilla.objects.create(org=abierto, nombre="Cuadrilla #5")
    j = JornadaDeCuadrilla.objects.create(org=abierto, cuadrilla=c, fecha=hoy,
                                          labor=JornadaDeCuadrilla.CORRECTIVO)
    persona = PersonaDeCampo.objects.create(org=abierto, profile=user_profile, nombre="T")
    IntegranteDeJornada.objects.create(org=abierto, jornada=j, persona=persona, rol="tecnico")

    r = D.del_dia(abierto, hoy)["cuadrillas"][0]["ordenes"][0]["revision"]

    assert r["veredicto"] == RC.REVISAR
    assert any(p["clave"] == "medicion" and p["ok"] is None for p in r["puntos"])
