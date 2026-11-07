"""
================================================================================
 EL CLIENTE SE ENTERA DE QUE SU VISITA ES HOY  --  30/10/2026 (PRD §8.17, Ola 2)
================================================================================
"A que hora viene el tecnico" es de lo que mas pregunta un cliente. Al publicar
el dia, el CRM le pide al motor el aviso `visita_programada` de cada orden. El
motor decide si sale (interruptor, horario, baja, una sola vez por clave); esto
prueba lo que el CRM le PIDE:

  A  publicar pide UN aviso por orden publicada, con la fecha de la jornada,
     y solo despues del commit: si la publicacion se deshace, no se pide nada;
  B  el pedido lleva la clave del hecho (orden + fecha), el telefono crudo, el
     caso solo si el origen es un caso, y la franja en la hora de LA EMPRESA;
  C  la tarea reagenda si el motor contesta 'todavia_no', no rompe si el motor
     no contesta, y sin motor configurado no pide nada.

    pytest campo/tests/test_aviso_de_visita.py
================================================================================
"""
import datetime as dt
from unittest import mock

import pytest
from django.db import transaction

from campo import reparto as R
from campo import tasks
from campo.cuadrillas import Cuadrilla, IntegranteDeJornada, JornadaDeCuadrilla, PersonaDeCampo
from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import aviso_de_visita
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)
UTC = dt.timezone.utc


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA, esquema={"campos": []})


@pytest.fixture
def norte(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="MARTHA GISELA")
    return z


@pytest.fixture
def bogota(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    return org_a


def _orden(org, version, numero, **extra):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA, zona="MARTHA GISELA",
        prioridad=OrdenTrabajo.PRIORIDAD_MEDIA,
        cliente_nombre="Beatriz Pinzón", cliente_direccion="Calle 50 # 10-20",
        cliente_telefono="+57 312 455 8901", **extra)


def _jornada(org, zonas, profile):
    c = Cuadrilla.objects.create(org=org, nombre="Cuadrilla norte")
    j = JornadaDeCuadrilla.objects.create(org=org, cuadrilla=c, fecha=LUNES,
                                          labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set(zonas)
    persona, _ = PersonaDeCampo.objects.get_or_create(org=org, profile=profile,
                                                      defaults={"nombre": "Tecnico"})
    IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona, rol="tecnico")
    return j


# ---------------------------------------------------------------------------
# A · publicar pide un aviso por orden, despues del commit
# ---------------------------------------------------------------------------

def test_a_publicar_pide_un_aviso_por_orden_con_la_fecha_de_la_jornada(
        org_a, user_profile, version, norte, django_capture_on_commit_callbacks):
    j = _jornada(org_a, [norte], user_profile)
    o1, o2 = _orden(org_a, version, 901), _orden(org_a, version, 902)
    with mock.patch.object(tasks.avisar_visita_al_cliente, "delay") as pedir:
        with django_capture_on_commit_callbacks(execute=True):
            R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(o1.id), str(o2.id)]}])
    pedidos = sorted(c.args for c in pedir.call_args_list)
    assert pedidos == sorted([(str(o1.id), str(org_a.id), LUNES.isoformat()),
                              (str(o2.id), str(org_a.id), LUNES.isoformat())])


def test_a2_si_la_publicacion_se_deshace_no_se_pide_nada(
        org_a, user_profile, version, norte, django_capture_on_commit_callbacks):
    j = _jornada(org_a, [norte], user_profile)
    o = _orden(org_a, version, 903)
    with mock.patch.object(tasks.avisar_visita_al_cliente, "delay") as pedir:
        with django_capture_on_commit_callbacks(execute=True):
            try:
                with transaction.atomic():
                    R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(o.id)]}])
                    raise RuntimeError("se deshace")
            except RuntimeError:
                pass
    assert pedir.call_count == 0


# ---------------------------------------------------------------------------
# B · lo que lleva el pedido
# ---------------------------------------------------------------------------

def test_b_el_pedido_lleva_la_clave_el_telefono_crudo_y_la_franja_local(
        bogota, version):
    o = _orden(bogota, version, 904, origen_tipo="case", origen_ref="caso-77",
               ventana_inicio=dt.datetime(2026, 10, 5, 14, 0, tzinfo=UTC),
               ventana_fin=dt.datetime(2026, 10, 5, 16, 30, tzinfo=UTC))
    p = aviso_de_visita.pedido(o, LUNES, "rapilink")
    assert p["evento"] == "visita_programada"
    assert p["clave"] == f"visita:{o.id}:{LUNES.isoformat()}"
    assert p["telefono"] == "+57 312 455 8901"
    assert p["caso_id"] == "caso-77"
    assert p["contexto"]["fecha_visita"] == "05/10/2026"
    assert p["contexto"]["franja"] == "9:00 a 11:30"      # 14:00 UTC = 9:00 en Bogota
    assert p["contexto"]["cliente_nombre"] == "Beatriz"
    assert p["contexto"]["cliente_nombre_completo"] == "Beatriz Pinzón"
    assert "cliente_direccion" not in p["contexto"], "la direccion no viaja junto con la hora de la visita"


def test_b2_sin_franja_no_se_inventa_y_un_ticket_no_es_un_caso(bogota, version):
    o = _orden(bogota, version, 905, origen_tipo="ticket", origen_ref="91288")
    p = aviso_de_visita.pedido(o, LUNES, "rapilink")
    assert "franja" not in p["contexto"]
    assert p["caso_id"] is None


# ---------------------------------------------------------------------------
# C · la tarea
# ---------------------------------------------------------------------------

class _R:
    def __init__(self, datos, status=200):
        self._d, self.status_code, self.content = datos, status, b"x"

    def json(self):
        return self._d


@pytest.fixture
def motor(monkeypatch):
    """El motor configurado, y la empresa de la orden resuelta por su org."""
    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
    monkeypatch.setenv("ASISTENTE_TENANT", "OTRA_EMPRESA_DEL_ENTORNO")
    with mock.patch("operaciones.areas_del_tenant.tenant_de_organizacion",
                    return_value="rapilink") as resolver:
        yield resolver


def _hoy_o_futuro():
    return dt.date.today() + dt.timedelta(days=1)


def test_c_todavia_no_reagenda_con_los_segundos_del_motor(org_a, user_profile, version, motor):
    o = _orden(org_a, version, 906)
    from campo.models import AsignacionTrabajo
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico", es_principal=True)
    fecha = _hoy_o_futuro()
    with mock.patch("requests.post", return_value=_R({"enviado": False, "motivo": "todavia_no",
                                                     "reintentar_en": 3600})) as post, \
            mock.patch.object(tasks.avisar_visita_al_cliente, "apply_async") as reagendar:
        tasks.avisar_visita_al_cliente(str(o.id), str(org_a.id), fecha.isoformat())
    url = post.call_args.args[0]
    assert url == "http://motor:5000/avisos/evento"
    assert post.call_args.kwargs["json"]["clave"] == f"visita:{o.id}:{fecha.isoformat()}"
    assert reagendar.call_args.kwargs["countdown"] == 2700,         "una hora se parte en tramos de 45 min: Redis reentrega lo que espera mas que su visibility_timeout"


def test_c1_la_empresa_sale_de_la_organizacion_de_la_orden_no_del_entorno(org_a, user_profile,
                                                                         version, motor):
    o = _orden(org_a, version, 910)
    from campo.models import AsignacionTrabajo
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico", es_principal=True)
    with mock.patch("requests.post", return_value=_R({"enviado": True, "motivo": None})) as post:
        tasks.avisar_visita_al_cliente(str(o.id), str(org_a.id), _hoy_o_futuro().isoformat())
    assert post.call_args.kwargs["json"]["tenant"] == "rapilink"
    motor.assert_called_with(str(org_a.id))
    motor.return_value = ""
    with mock.patch("requests.post") as post:
        tasks.avisar_visita_al_cliente(str(o.id), str(org_a.id), _hoy_o_futuro().isoformat())
    assert post.call_count == 0, "sin empresa resuelta para la org, no se pide nada"


@pytest.mark.parametrize("cambio", ["cancelada", "otro_dia", "vencida", "sin_asignar"])
def test_c3_una_visita_que_ya_no_existe_no_se_avisa(org_a, user_profile, version, motor, cambio):
    """Se publico de noche, el aviso quedo para la manana, y en el medio cambio."""
    o = _orden(org_a, version, 911)
    from campo.models import AsignacionTrabajo
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico", es_principal=True)
    fecha = _hoy_o_futuro()
    if cambio == "cancelada":
        OrdenTrabajo.objects.filter(id=o.id).update(estado_operativo=OrdenTrabajo.CANCELADA)
    elif cambio == "otro_dia":
        OrdenTrabajo.objects.filter(id=o.id).update(
            programada_para=dt.datetime.combine(fecha + dt.timedelta(days=3), dt.time(15), tzinfo=UTC))
    elif cambio == "vencida":
        fecha = dt.date.today() - dt.timedelta(days=2)
    elif cambio == "sin_asignar":
        AsignacionTrabajo.objects.filter(orden=o).delete()
    with mock.patch("requests.post") as post:
        tasks.avisar_visita_al_cliente(str(o.id), str(org_a.id), fecha.isoformat())
    assert post.call_count == 0, cambio


def test_c4_la_que_sigue_programada_si_se_avisa(org_a, user_profile, version, motor):
    o = _orden(org_a, version, 912)
    from campo.models import AsignacionTrabajo
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico", es_principal=True)
    with mock.patch("requests.post", return_value=_R({"enviado": True, "motivo": None})) as post:
        tasks.avisar_visita_al_cliente(str(o.id), str(org_a.id), _hoy_o_futuro().isoformat())
    assert post.call_count == 1


def test_c2_el_motor_caido_no_rompe_y_sin_motor_no_se_pide(org_a, user_profile, version, motor,
                                                           monkeypatch):
    o = _orden(org_a, version, 907)
    from campo.models import AsignacionTrabajo
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico", es_principal=True)
    fecha = _hoy_o_futuro().isoformat()
    monkeypatch.delenv("ASISTENTE_URL", raising=False)
    with mock.patch("requests.post") as post:
        assert tasks.avisar_visita_al_cliente(str(o.id), str(org_a.id), fecha) is None
    assert post.call_count == 0
    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
    with mock.patch("requests.post", side_effect=ConnectionError("caido")):
        assert tasks.avisar_visita_al_cliente(str(o.id), str(org_a.id), fecha) is None


# ---------------------------------------------------------------------------
# D · la asignacion a mano desde Despacho tambien avisa (31/10/2026)
# ---------------------------------------------------------------------------
#  Hasta hoy solo avisaba publicar el dia. Una orden que una persona le da a
#  una cuadrilla, o a un tecnico con fecha, es la misma visita: mismo aviso,
#  misma clave (orden, fecha) -- si despues se publica, no sale dos veces.

def test_d_dar_la_orden_a_una_cuadrilla_pide_el_aviso_con_la_fecha_de_la_jornada(
        org_a, user_profile, admin_profile, version, norte, django_capture_on_commit_callbacks):
    from campo.services import despacho
    j = _jornada(org_a, [norte], user_profile)
    o = _orden(org_a, version, 920)
    with mock.patch.object(tasks.avisar_visita_al_cliente, "delay") as pedir:
        with django_capture_on_commit_callbacks(execute=True):
            despacho.asignar_a_jornada(o, j, admin_profile)
    assert [c.args for c in pedir.call_args_list] == [(str(o.id), str(org_a.id), LUNES.isoformat())]


def test_d2_dar_la_orden_a_un_tecnico_avisa_solo_si_tiene_fecha(
        org_a, user_profile, admin_profile, version, bogota, django_capture_on_commit_callbacks):
    from campo.services import despacho
    con = _orden(org_a, version, 921,
                 programada_para=dt.datetime(2026, 10, 5, 15, 0, tzinfo=UTC))   # 10:00 en Bogota
    sin = _orden(org_a, version, 922)
    with mock.patch.object(tasks.avisar_visita_al_cliente, "delay") as pedir:
        with django_capture_on_commit_callbacks(execute=True):
            despacho.asignar(con, user_profile, admin_profile)
            despacho.asignar(sin, user_profile, admin_profile)
    assert [c.args for c in pedir.call_args_list] == [(str(con.id), str(org_a.id), "2026-10-05")], \
        "sin fecha programada no hay dia que avisar"


def test_d3_si_la_asignacion_se_deshace_no_se_pide_nada(
        org_a, user_profile, admin_profile, version, norte, django_capture_on_commit_callbacks):
    from campo.services import despacho
    j = _jornada(org_a, [norte], user_profile)
    o = _orden(org_a, version, 923)
    with mock.patch.object(tasks.avisar_visita_al_cliente, "delay") as pedir:
        with django_capture_on_commit_callbacks(execute=True):
            try:
                with transaction.atomic():
                    despacho.asignar_a_jornada(o, j, admin_profile)
                    raise RuntimeError("se deshace")
            except RuntimeError:
                pass
    assert pedir.call_count == 0
