# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CIERRA SOLO LO QUE SU REVISION DIO POR BUENO  --  30/10/2026
================================================================================
SPEC/objetivos/revision-del-cierre.md. Ver `campo/cierre_por_el_supervisor.py`.
El motor se sustituye en el borde (`requests.post`): se afirma sobre lo que
SALE hacia el motor y sobre lo que queda en Dexter.

  P   las puertas, como las otras tareas de accion: sin la tarea delegada, sin
      el nivel 3 (con el interruptor), o sin empresa en el motor, SOMBRA: no le pide
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
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de_organizacion", lambda org_id: "tenant-de-prueba")
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
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de_organizacion", lambda org_id: "t")
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
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de_organizacion", lambda org_id: "t")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))
    with mock.patch("requests.post") as post:
        assert _fase(org_a)["modo"] == CS.SOMBRA, "sin nivel 3"
        autonomia.cambiar(org_a, 3, actor=admin_profile, motivo="x", criterios="y")
        monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                            lambda org: (False, "detenido por una persona"))
        assert _fase(org_a)["modo"] == CS.SOMBRA, "con el interruptor detenido"
    post.assert_not_called()


def test_p3_sin_motor_tenant_tampoco(abierto, orden, monkeypatch):
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de_organizacion", lambda org_id: "")
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
    #  'revision' desde el 31/10/2026 (H1): la ruta autonoma la exige. 'actor'
    #  sigue sin estar -- quien cierra no lo elige el CRM.
    cuerpo = post.call_args.kwargs["json"]
    assert set(cuerpo) == {"ticket", "texto", "revision"}, cuerpo
    assert "se_puede_cerrar" in cuerpo["revision"], cuerpo["revision"]
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

    #  Se limpian las DOS marcas del intento: el bloqueo y el reclamo que
    #  `_reclamar` escribe antes de hablarle al motor (H6, 31/10/2026). Las dos
    #  apagan los reintentos la misma hora.
    EventoTrabajo.objects.filter(
        orden=orden, tipo__in=(CS.EVENTO_BLOQUEADO, CS.EVENTO_INTENTO)).delete()
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
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de_organizacion", lambda org_id: "tenant-de-prueba")
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


# ---------------------------------------------------------------------------
# I · ENSEGUIDA, no dentro de una hora  --  31/10/2026
# ---------------------------------------------------------------------------
#  El usuario: «que después que el supervisor revise el ticket que mandó el
#  técnico lo revise enseguida e indique si lo cierra o no». La fase horaria
#  sigue siendo la red de atrás; esto la adelanta para UNA orden.
#
#  Se afirma sobre el EFECTO en los dos tramos, que es donde se puede romper:
#  que el reporte del técnico ENCOLE (I3/I4), y que lo encolado CIERRE (I1).
#  Afirmar solo que la función existe la dejaría pasar sin llamador, que es
#  exactamente el defecto que CLAUDE.md §6 llama «construido no es que corre».

def test_i1_el_disparo_inmediato_cierra_esa_orden(abierto, orden):
    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        r = CS.cerrar_esta_orden(orden)

    assert (r["modo"], r["resultado"]) == (CS.ACCION, "cerrada"), r
    assert post.call_args.args[0].endswith(
        f"/interno/orden/{orden.id}/cerrar-ticket-supervisor")
    orden.refresh_from_db()
    assert (orden.estado_operativo, orden.estado_validacion) == (
        OrdenTrabajo.CERRADA, OrdenTrabajo.APROBADO)


def test_i2_el_disparo_inmediato_pasa_por_las_mismas_puertas(org_a, orden):
    """Sin la tarea delegada no le pide NADA al motor. Si esto fallara, el
    camino nuevo sería una puerta de atrás a la que no le aplican las puertas."""
    with mock.patch("requests.post") as post:
        r = CS.cerrar_esta_orden(orden)

    assert r["modo"] == CS.SOMBRA, r
    post.assert_not_called()
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO


def test_i2b_una_orden_que_la_revision_no_dio_por_buena_no_sale(abierto, orden):
    """Mismo filtro que la fase: «Revisalo» no se cierra ni por este camino."""
    EvidenciaTrabajo.objects.filter(orden_trabajo=orden).delete()
    with mock.patch("requests.post") as post:
        r = CS.cerrar_esta_orden(orden)

    assert (r["modo"], r["resultado"]) == (CS.ACCION, ""), r
    post.assert_not_called()


def test_i3_el_reporte_de_cierre_del_tecnico_lo_encola(
        user_client, orden, org_a, django_capture_on_commit_callbacks):
    """El técnico manda el reporte por la app -> se despierta al Supervisor.

    Se captura el `on_commit`: encolar ANTES del commit dejaría al worker
    leyendo el estado viejo.
    """
    with mock.patch("campo.tasks.revisar_el_cierre_ya.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            r = user_client.post(
                f"/api/campo/trabajos/{orden.id}/seguimiento/",
                {"momento": "cierre",
                 "respuestas": {"solucion": "Cambié el conector",
                                "servicio_validado": True}},
                format="json")

    assert r.status_code == 201, r.content
    delay.assert_called_once_with(str(org_a.id), str(orden.id))


def test_i4_al_finalizar_en_campo_tambien_lo_encola(
        user_client, orden, org_a, django_capture_on_commit_callbacks):
    """La otra mitad: cuál de las dos llega última depende de la app."""
    orden.estado_operativo = OrdenTrabajo.EN_SITIO
    orden.save(update_fields=["estado_operativo"])
    with mock.patch("campo.tasks.revisar_el_cierre_ya.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            r = user_client.post(f"/api/campo/trabajos/{orden.id}/completar/",
                                 {}, format="json")

    assert r.status_code == 200, r.content
    delay.assert_called_once_with(str(org_a.id), str(orden.id))


def test_i5_si_no_se_puede_encolar_el_tecnico_igual_reporto(abierto, orden):
    """El broker caído no puede tumbar el reporte: ya es un hecho guardado."""
    from campo import tasks as T

    with mock.patch("campo.tasks.revisar_el_cierre_ya.delay",
                    side_effect=RuntimeError("sin broker")):
        with mock.patch("django.db.transaction.on_commit",
                        side_effect=lambda fn, *a, **k: fn()):
            T.pedir_revision_del_cierre(orden)   # no levanta


def test_i6_la_tarea_con_una_orden_que_ya_no_esta_no_revienta(abierto):
    import uuid as _uuid

    from campo import tasks as T

    r = T.revisar_el_cierre_ya(str(abierto.id), str(_uuid.uuid4()))
    assert r["resultado"] == "" and r["por_que"], r


def test_i7_una_orden_ya_reclamada_no_se_vuelve_a_intentar(abierto, orden):
    """H6 (auditoría de frontera, 31/10/2026). El reporte y el «finalizar» son
    dos peticiones segundos aparte, y las dos despiertan esta fase.

    LO QUE ESTO MIDE, y lo que no. Mide que una orden ya reclamada no llega al
    motor por segunda vez: se reclama a mano (como haría la tarea A) y se
    corre la fase (la tarea B). Sin el reclamo, B le habla al motor.

    NO reproduce el entrelazado real de dos conexiones a la vez. Esa parte la
    sostiene el `select_for_update` de `_reclamar`, que serializa las dos
    sobre la fila de la orden, y está verificada leyendo el código, no
    corriendo la carrera. Se dice acá porque una prueba secuencial que diga
    «la carrera está cerrada» sería el falso verde que §6 describe: con el
    reclamo quitado, la segunda llamada secuencial no encuentra nada que
    hacer igual --la orden ya quedó cerrada-- y la prueba pasaría sin medir.
    """
    assert CS._reclamar(orden, timezone.now()) is True, "la tarea A reclama"

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        r = CS.cerrar_esta_orden(orden)

    post.assert_not_called()
    assert r["resultado"] == "salteada", r
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO


def test_i8_el_reclamo_caduca_y_no_congela_la_orden(abierto, orden):
    """Una tarea que se muera dejando la marca puesta no puede dejar la orden
    sin cerrarse para siempre: la marca vence con la misma ventana."""
    ahora = timezone.now()
    assert CS._reclamar(orden, ahora) is True
    assert CS._reclamar(orden, ahora + dt.timedelta(minutes=10)) is False
    assert CS._reclamar(
        orden, ahora + dt.timedelta(minutes=CS.MINUTOS_ENTRE_INTENTOS + 1)) is True


# ---------------------------------------------------------------------------
# V · LO QUE LA IA VIO EN LAS FOTOS  --  31/10/2026
# ---------------------------------------------------------------------------
#  El sexto punto de la revisión. LA GARANTÍA ENTERA es que nunca puede valer
#  `False`: cualquier `False` se convierte en NO_CERRAR, y ese veredicto
#  además alimenta el cierre autónomo. Una opinión no verificada de un modelo
#  no puede frenar el trabajo de un técnico (CLAUDE.md §4).

def _analisis(orden, org, **kw):
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo

    ev = EvidenciaTrabajo.objects.filter(orden_trabajo=orden).first()
    datos = {"texto": "Se ve una ONT con la luz PON fija.", "motivo": "",
             "pide_atencion": False}
    datos.update(kw)
    return AnalisisDeEvidencia.objects.create(
        org=org, evidencia=ev, vuelta=orden.vuelta,
        origen=AnalisisDeEvidencia.IA, **datos)


def test_v1_sin_analisis_la_revision_queda_igual(abierto, orden):
    """Si esta empresa no lo tiene encendido, el punto NO aparece."""
    r = RC.revisar(orden, pendientes=set())
    assert r["veredicto"] == RC.CERRAR, r
    assert not [p for p in r["puntos"] if p["clave"] == "fotos"]


def test_v1b_apagado_NO_DEJA_RASTRO_y_el_cierre_autonomo_sigue(abierto, orden):
    """EL CASO QUE LA v1 NO MODELABA (revisor de PII, 31/10/2026, H1).

    `v1` modela «apagado» como «no hay filas». El apagado real produce otra
    cosa: la tarea corría igual y escribía una fila con `motivo` y sin
    `texto`. Con eso, `punto_de_la_revision` veía «ninguna se pudo mirar»,
    devolvía el punto en «no se sabe» y el veredicto pasaba a REVISAR — o
    sea que la función APAGADA, que es el default y lo que va a producción,
    frenaba el cierre autónomo del Supervisor en TODA orden con evidencia.

    Se afirma sobre el efecto en los dos extremos: que no quede fila, y que
    el veredicto siga siendo el que era.
    """
    from campo import inspeccion_visual as IV
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo
    from campo import tasks as T

    ev = EvidenciaTrabajo.objects.filter(orden_trabajo=orden).first()
    #  El motor contesta que esta empresa no lo tiene habilitado.
    with mock.patch.object(IV, "_esta_habilitado", return_value=False):
        with mock.patch("requests.post") as post:
            T.analizar_evidencia(str(abierto.id), str(ev.id))
            post.assert_not_called(), "la foto no tiene que salir del CRM"

    assert not AnalisisDeEvidencia.objects.filter(org=abierto).exists(),         "apagado no deja fila"
    r = RC.revisar(orden, pendientes=set())
    assert not [p for p in r["puntos"] if p["clave"] == "fotos"]
    assert r["veredicto"] == RC.CERRAR, r


def test_v1c_el_interruptor_falla_CERRADO(abierto, orden):
    """Si no se puede comprobar el consentimiento, la foto no sale.

    Es lo contrario de como falla casi todo lo demás del proyecto, y es a
    propósito: no poder comprobar un consentimiento no es permiso.
    """
    from campo import inspeccion_visual as IV

    class _Rota:
        status_code = 500

        def json(self):
            return {}

    with mock.patch("requests.get", return_value=_Rota()):
        assert IV._esta_habilitado("rapilink") is False
    with mock.patch("requests.get", side_effect=RuntimeError("sin red")):
        assert IV._esta_habilitado("rapilink") is False
    with mock.patch("requests.get",
                    return_value=type("R", (), {"status_code": 200,
                                                "json": lambda s: {}})()):
        assert IV._esta_habilitado("rapilink") is False


def test_v1d_la_empresa_sale_de_la_orden_no_del_entorno(abierto, orden, monkeypatch):
    """H2: `MOTOR_TENANT` es UNA por instalación. Con dos empresas, la foto
    de la segunda se habría mandado con el consentimiento de la primera."""
    from campo import inspeccion_visual as IV
    from campo.models import EvidenciaTrabajo

    monkeypatch.setenv("MOTOR_TENANT", "la-empresa-equivocada")
    ev = EvidenciaTrabajo.objects.filter(orden_trabajo=orden).first()
    vistos = []

    def _ver(tenant):
        vistos.append(tenant)
        return False

    with mock.patch.object(IV, "_esta_habilitado", side_effect=_ver):
        IV.analizar(ev)

    assert vistos and "la-empresa-equivocada" not in vistos, vistos


def test_v2_fotos_miradas_y_limpias_suman_un_punto_en_si(abierto, orden):
    _analisis(orden, abierto)
    r = RC.revisar(orden, pendientes=set())
    punto = next(p for p in r["puntos"] if p["clave"] == "fotos")
    assert punto["ok"] is True, punto
    assert r["veredicto"] == RC.CERRAR, r


def test_v3_una_foto_que_pide_atencion_lleva_a_REVISAR_no_a_NO_CERRAR(
        abierto, orden):
    """EL CASO QUE DEFINE EL ALCANCE. La IA pide una mirada; no niega nada."""
    _analisis(orden, abierto, pide_atencion=True,
              texto="Se ve un cable suelto junto a la ONT.")
    r = RC.revisar(orden, pendientes=set())
    punto = next(p for p in r["puntos"] if p["clave"] == "fotos")
    assert punto["ok"] is None, punto
    assert r["veredicto"] == RC.REVISAR, r
    assert r["veredicto"] != RC.NO_CERRAR


def test_v4_una_foto_que_no_se_pudo_mirar_tampoco_niega(abierto, orden):
    _analisis(orden, abierto, texto="", motivo="el analizador solo mira JPEG y PNG, y esto es HEIC")
    r = RC.revisar(orden, pendientes=set())
    punto = next(p for p in r["puntos"] if p["clave"] == "fotos")
    assert punto["ok"] is None, punto
    assert "HEIC" in punto["texto"]
    assert r["veredicto"] == RC.REVISAR


def test_v5_el_punto_NUNCA_puede_valer_False(abierto, orden):
    """La guarda, sobre TODAS las combinaciones. Si alguna diera `False`, una
    orden dejaría de poder cerrarse por lo que dijo un modelo."""
    from campo.models import AnalisisDeEvidencia

    combinaciones = [
        {"texto": "ok", "motivo": "", "pide_atencion": False},
        {"texto": "ok", "motivo": "", "pide_atencion": True},
        {"texto": "", "motivo": "no se pudo leer", "pide_atencion": False},
        {"texto": "", "motivo": "no se pudo leer", "pide_atencion": True},
        {"texto": "cable suelto", "motivo": "x", "pide_atencion": True},
    ]
    for combo in combinaciones:
        AnalisisDeEvidencia.objects.filter(org=abierto).delete()
        _analisis(orden, abierto, **combo)
        r = RC.revisar(orden, pendientes=set())
        punto = next((p for p in r["puntos"] if p["clave"] == "fotos"), None)
        assert punto is None or punto["ok"] is not False, (combo, punto)
        assert r["veredicto"] != RC.NO_CERRAR, (combo, r["veredicto"])


def test_v6_el_analisis_de_otra_vuelta_no_cuenta(abierto, orden):
    """Una orden devuelta y rehecha tiene otras fotos: el análisis de la
    vuelta anterior no dice nada de ésta."""
    _analisis(orden, abierto, pide_atencion=True)
    from campo.models import AnalisisDeEvidencia

    AnalisisDeEvidencia.objects.filter(org=abierto).update(vuelta=99)
    r = RC.revisar(orden, pendientes=set())
    assert not [p for p in r["puntos"] if p["clave"] == "fotos"]


def test_v7_confirmar_la_foto_encola_el_analisis(
        user_client, orden, org_a, django_capture_on_commit_callbacks):
    """El enganche: sin esto el módulo entero estaría construido y sin
    llamador -- «construido no es que corre» (CLAUDE.md §6)."""
    from campo.models import EvidenciaTrabajo

    ev = EvidenciaTrabajo.objects.filter(orden_trabajo=orden).first()
    ev.estado_archivo = EvidenciaTrabajo.SUBIENDO
    ev.save(update_fields=["estado_archivo"])

    with mock.patch("campo.services.storage.CampoStorage.verify_upload",
                    return_value=True):
        with mock.patch("campo.tasks.analizar_evidencia.delay") as delay:
            with django_capture_on_commit_callbacks(execute=True):
                r = user_client.post(
                    f"/api/campo/evidencias/{ev.id}/confirmar/", {}, format="json")

    assert r.status_code == 200, r.content
    delay.assert_called_once_with(str(org_a.id), str(ev.id))


def test_v8_un_formato_que_el_analizador_no_mira_se_dice_antes_de_pagar(orden):
    """HEIC y WebP se suben bien y el analizador los rechaza. Se detecta de
    este lado para no pagar un viaje HTTP, y el motivo nombra el formato."""
    from campo import inspeccion_visual as IV

    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    webp = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 32
    assert IV.formato_legible(heic) == "HEIC"
    assert IV.formato_legible(webp) == "WebP"
    assert "HEIC" in IV.se_puede_mirar(heic)
    assert "WebP" in IV.se_puede_mirar(webp)
    assert IV.se_puede_mirar(bytes([0xFF, 0xD8, 0xFF]) + b"\x00" * 32) == ""
    grande = bytes([0xFF, 0xD8, 0xFF]) + b"\x00" * (IV.MAX_BYTES + 1)
    assert "acepta hasta" in IV.se_puede_mirar(grande)


# ---------------------------------------------------------------------------
# A · CUÁNDO UNA FOTO PIDE QUE ALGUIEN LA MIRE  --  05/11/2026
# ---------------------------------------------------------------------------
#  EL DEFECTO QUE ESTO CIERRA, medido en producción (OT 100): **4 de 4 fotos
#  pedían una mirada**, y así iba a ser en todas las órdenes. El detector
#  buscaba «borroso», «no se ve», «no se puede»… y la instrucción le PIDE al
#  modelo que diga exactamente eso. Se le pedían las frases y después se
#  usaban como alarma.
#
#  El costo no fue el ruido: el veredicto quedaba en REVISAR, el cierre
#  autónomo exige CERRAR, y ninguna orden con fotos se cerraba sola.
#
#  Hay una guarda estática del contrato en `tests/test_vision_propositos.py`.
#  Ésta prueba la CONDUCTA: aquélla no veía que la marca dejara de leerse.

def test_a1_la_marca_del_modelo_manda_sobre_las_palabras():
    """Si el modelo dijo que no hace falta mirar, una palabra suelta en su
    descripción no lo contradice."""
    from campo.tasks import _pide_atencion

    assert _pide_atencion("Se ve una ONT con tres luces verdes. ATENCION: no") is False
    assert _pide_atencion("Se ve un cable suelto junto a la caja. ATENCION: si") is True
    #  Lo que fallaba antes: la foto borrosa ya no alarma por sí sola.
    assert _pide_atencion(
        "La foto está borrosa y no se puede determinar el serial. ATENCION: no") is False


def test_a2_sin_marca_cae_al_respaldo_y_el_respaldo_no_se_dispara_solo():
    """El modelo puede no escribir la marca: es guía, no garantía (PRD 7.4).
    Entonces manda la lista -- que ya no tiene las palabras que la propia
    instrucción exige."""
    from campo.tasks import _pide_atencion

    assert _pide_atencion("Se ve una ONT, todo normal.") is False
    #  LAS CUATRO QUE FALLABAN. Cada una venía de una regla de la instrucción.
    assert _pide_atencion("La foto está borrosa.") is False
    assert _pide_atencion("No se puede determinar el serial.") is False
    assert _pide_atencion("No se ve la etiqueta.") is False
    assert _pide_atencion("El equipo está tapado y fuera de cuadro.") is False
    #  Y «no hay cables sueltos» tampoco, que es por lo que «suelto» salió
    #  del respaldo: la regla 4 le pide decirlo también cuando no los hay.
    assert _pide_atencion("No hay cables sueltos ni conectores a la vista.") is False
    #  Lo que sí queda: defectos que la instrucción nunca le pide nombrar.
    assert _pide_atencion("El equipo está sin fijar a la pared.") is True
    assert _pide_atencion("Se ve material deteriorado.") is True


def test_a3_sin_texto_no_se_marca():
    """Un análisis que no se pudo hacer lo cuenta `motivo`, no esto."""
    from campo.tasks import _pide_atencion

    assert _pide_atencion("") is False
    assert _pide_atencion("   ") is False
    assert _pide_atencion(None) is False


def test_a4_el_comando_pone_al_dia_lo_que_el_detector_viejo_marco(abierto, orden):
    """El comando que limpia las marcas viejas.

    RECALCULA, no borra: una foto cuyo análisis sí nombra un defecto sigue
    marcada. Poner todo en `False` habría tapado las de verdad junto con el
    ruido, que es la forma fácil y equivocada de arreglar esto.
    """
    from io import StringIO

    from django.core.management import call_command

    from campo.models import AnalisisDeEvidencia

    #  Tres filas como las que dejó el detector viejo: las tres marcadas,
    #  pero solo una nombra un defecto de verdad.
    ruido1 = _analisis(orden, abierto, pide_atencion=True,
                       texto="La foto está borrosa y no se puede determinar el serial.")
    ruido2 = _analisis(orden, abierto, pide_atencion=True,
                       texto="No hay cables sueltos. Se ve la ONT con luz verde.")
    real = _analisis(orden, abierto, pide_atencion=True,
                     texto="El equipo está sin fijar a la pared.")

    salida = StringIO()
    call_command("recalcular_atencion_fotos", "--org", str(abierto.id), stdout=salida)
    #  SIN --aplicar NO ESCRIBE.
    assert "SIMULACRO" in salida.getvalue()
    for f in (ruido1, ruido2, real):
        f.refresh_from_db()
        assert f.pide_atencion is True

    call_command("recalcular_atencion_fotos", "--org", str(abierto.id),
                 "--aplicar", stdout=StringIO())
    for f in (ruido1, ruido2):
        f.refresh_from_db()
        assert f.pide_atencion is False, f.texto
    real.refresh_from_db()
    assert real.pide_atencion is True, "un defecto de verdad no se puede perder"


def test_a5_el_comando_no_toca_lo_que_corrigio_una_persona(abierto, orden):
    """Su `pide_atencion` es un juicio humano, no un cálculo del código."""
    from io import StringIO

    from django.core.management import call_command

    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo

    ev = EvidenciaTrabajo.objects.filter(orden_trabajo=orden).first()
    humano = AnalisisDeEvidencia.objects.create(
        org=abierto, evidencia=ev, vuelta=orden.vuelta,
        origen=AnalisisDeEvidencia.PERSONA, pide_atencion=True,
        texto="La foto está borrosa.")

    call_command("recalcular_atencion_fotos", "--org", str(abierto.id),
                 "--aplicar", stdout=StringIO())

    humano.refresh_from_db()
    assert humano.pide_atencion is True


def test_a6_un_id_mal_escrito_dice_que_hacer_en_vez_de_una_traza(abierto):
    """Visto en producción el 05/11/2026: pegaron un id de ejemplo y el
    comando escupió 40 líneas de traza de Django. `ValidationError` la lanza
    Django ANTES de consultar, así que no la atrapaba el `except`."""
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    for malo in ("1234abcd-...", "", "no-soy-un-uuid", "<tu-org-id>"):
        try:
            call_command("recalcular_atencion_fotos", "--org", malo,
                         stdout=StringIO())
            assert False, f"{malo!r} tendría que haber fallado"
        except CommandError as e:
            assert "UUID" in str(e), str(e)


# ---------------------------------------------------------------------------
# T · EL TICKET DEL ISP SE LEE COMO LO ESCRIBE QUIEN LO GUARDA  --  05/11/2026
# ---------------------------------------------------------------------------
#  EL DEFECTO, medido en producción: «en Programación dice cerrado, en la
#  lista de tickets sigue abierto, y tampoco cierra en el proveedor».
#
#  `contexto["ticket"]` NO es un número: es el dict que arma
#  `despacho._ticket_del_proveedor` ({numero, proveedor, estado, ...}).
#  Se leía con `str(...)`, así que al motor viajaba el repr del diccionario,
#  el endpoint quedaba con llaves sin resolver y el ejecutor reventaba ANTES
#  de llamar a WispHub → FALLO_AL_CERRAR. Y en la ruta del Supervisor un
#  fallo del ISP corta antes de `cerrar_orden`, así que tampoco se cerraba
#  la orden ni su caso.
#
#  POR QUÉ NINGUNA PRUEBA LO VIO, y es lo que estas arreglan: las dos suites
#  del cierre construían la orden con `contexto={"ticket": "94721"}`, un
#  string. Nunca con la forma que el productor escribe. Era deriva entre
#  quien guarda el dato y quien lo lee, y ninguna prueba cruzaba los dos.

def test_t1_el_numero_sale_del_dict_que_guarda_despacho():
    """Se construye con la MISMA función que llena el contexto en producción,
    no con un literal: un literal vuelve a quedarse viejo en cuanto el
    productor cambie de forma."""
    from campo.services.cierre_en_isp import numero_de_ticket
    from campo.services.despacho import _ticket_del_proveedor

    class _Caso:
        external_ticket_id = "94721"
        provider = "wisphub"
        external_status = "Nuevo"
        external_created_by = "Mario"

    contexto = {"ticket": _ticket_del_proveedor(_Caso())}
    assert isinstance(contexto["ticket"], dict), "si esto cambia, revisar los lectores"
    assert numero_de_ticket(contexto) == "94721"


def test_t2_tambien_lee_las_ordenes_viejas_con_el_ticket_suelto():
    """Hay órdenes ya guardadas de las dos formas. Rechazar una dejaría
    órdenes sin poder cerrarse por cómo quedó escrito su contexto."""
    from campo.services.cierre_en_isp import numero_de_ticket

    assert numero_de_ticket({"ticket": "94721"}) == "94721"


def test_t3_sin_ticket_devuelve_vacio_y_no_el_texto_de_un_dict():
    from campo.services.cierre_en_isp import numero_de_ticket

    for contexto in ({}, None, {"ticket": None}, {"ticket": {}},
                     {"ticket": {"proveedor": "wisphub"}}):
        assert numero_de_ticket(contexto) == "", contexto


def test_t4_con_el_contexto_REAL_el_cierre_le_llega_a_wisphub(abierto, orden):
    """La prueba de punta a punta del defecto: la orden lleva el dict, como
    en producción, y el motor tiene que recibir el NÚMERO."""
    from campo.services.despacho import _ticket_del_proveedor

    class _Caso:
        external_ticket_id = "94721"
        provider = "wisphub"
        external_status = "Nuevo"
        external_created_by = "Mario"

    orden.contexto = {"ticket": _ticket_del_proveedor(_Caso())}
    orden.save(update_fields=["contexto"])

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        r = _fase(abierto)

    assert (r["cerradas"], r["bloqueadas"]) == (1, 0), r
    #  Lo que de verdad importa: el número, no el repr de un diccionario.
    assert post.call_args.kwargs["json"]["ticket"] == "94721", \
        post.call_args.kwargs["json"]["ticket"]
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CERRADA
