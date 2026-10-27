"""
================================================================================
 EL TELEFONO SE ENTERA CUANDO LE ASIGNAN TRABAJO  --  27/10/2026
================================================================================
Fase 3.1 de SPEC/objetivos/supervisor-arma-la-jornada.md, decision del usuario
del 21/10: aviso al telefono del tecnico CADA VEZ que le asignan una visita, la
asigne el Supervisor o una persona. Hasta hoy la veia recien cuando la app
sincronizaba.

Se afirma sobre lo que SALE hacia el telefono (`push_fcm.mandar_a_un_telefono`,
el borde con Google) y sobre la notificacion que queda en la plataforma:

  A  publicar el reparto: UN aviso por persona, con lo que ESTA publicacion le
     dio --cuantas y que dia--; con una sola orden, la nombra y abre esa orden.
     Sin datos del cliente. El push lleva el id de LA notificacion.
  B  lo que la persona ya tenia no se vuelve a avisar.
  C  `mover=False`: lo que ya tiene gente queda quieto y solo se suma lo nuevo.
  D  `por_el_supervisor`: queda escrito que asigno el Supervisor, sin persona,
     y la proxima vuelta NO lo cuenta como asignado a mano.
  E  Despachar (un tecnico, o la cuadrilla) y agregar un integrante: un aviso
     que nombra la orden, solo a quien la recibe por primera vez.
  F  solo al telefono: el chat de la empresa no recibe las asignaciones.
  G  si la publicacion se deshace, no sale ningun aviso.

    pytest campo/tests/test_aviso_al_asignar.py
================================================================================
"""
import datetime as dt
import json
from unittest import mock

import pytest
from django.db import transaction

from campo import reparto as R
from campo.avisos import CanalDeAvisos, DispositivoDeTecnico
from campo.cuadrillas import (
    Cuadrilla,
    IntegranteDeJornada,
    JornadaDeCuadrilla,
    PersonaDeCampo,
)
from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import avisos, despacho, push_fcm
from campo.zonas import AliasDeZona, ZonaOperativa
from common.models import Notification, Profile

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})


@pytest.fixture
def norte(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="MARTHA GISELA")
    return z


@pytest.fixture
def otro(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="otro.aviso@test.com", password="testpass123")
    return Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)


@pytest.fixture
def fcm():
    """El borde con Google: lo que sale, tal cual."""
    enviados = []

    def mandar(token, titulo, texto, enlace, *, aviso_id="", verbo="",
               contenido=None):
        enviados.append({"token": token, "titulo": titulo, "texto": texto,
                         "enlace": enlace, "aviso_id": aviso_id, "verbo": verbo,
                         "contenido": contenido or {}})
        return push_fcm.ENTREGADO

    with mock.patch.object(push_fcm, "esta_configurado", return_value=True), \
            mock.patch.object(push_fcm, "mandar_a_un_telefono", side_effect=mandar):
        yield enviados


def _telefono(org, profile, token):
    return DispositivoDeTecnico.objects.create(
        org=org, profile=profile, token=token, plataforma="android", activo=True)


def _orden(org, version, numero):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA, zona="MARTHA GISELA",
        prioridad=OrdenTrabajo.PRIORIDAD_MEDIA,
        cliente_nombre="Beatriz Pinzón", cliente_direccion="Calle 50 # 10-20",
        cliente_telefono="+57 312 455 8901")


def _de(orden, profile):
    AsignacionTrabajo.objects.create(orden=orden, profile=profile,
                                     rol="tecnico", es_principal=True)
    return orden


def _jornada_de(org, zonas, *profiles):
    c = Cuadrilla.objects.create(org=org, nombre="Cuadrilla norte")
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=c, fecha=LUNES, labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set(zonas)
    for i, profile in enumerate(profiles):
        persona, _ = PersonaDeCampo.objects.get_or_create(
            org=org, profile=profile, defaults={"nombre": f"Persona {i}"})
        IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona,
                                           rol="tecnico")
    return j


def _publicar(org, jornada, ordenes, capturar, **kw):
    with capturar(execute=True):
        return R.publicar(org, [{"jornada": str(jornada.id),
                                 "ordenes": [str(o.id) for o in ordenes]}], **kw)


# ---------------------------------------------------------------------------
# A · publicar avisa una vez por persona
# ---------------------------------------------------------------------------

def test_a_publicar_avisa_una_vez_por_persona_con_lo_que_le_dio(
        org_a, version, norte, admin_profile, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, admin_profile, "tok-a")
    ordenes = [_orden(org_a, version, 100 + i) for i in range(3)]
    j = _jornada_de(org_a, [norte], admin_profile)

    r = _publicar(org_a, j, ordenes, django_capture_on_commit_callbacks)

    assert r["publicadas"] == 3
    assert len(fcm) == 1
    m = fcm[0]
    assert (m["verbo"], m["texto"], m["enlace"]) == (
        avisos.VERBO_JORNADA, "📋 Te asignaron 3 visitas para el lunes 05/10", "")
    assert m["contenido"]["ordenes"] == [100, 101, 102]
    #  El push es LA notificacion de la plataforma, no una copia.
    n = Notification.objects.get(recipient=admin_profile)
    assert (n.verb, str(n.id)) == (avisos.VERBO_JORNADA, m["aviso_id"])
    #  Sin datos del cliente.
    crudo = json.dumps(m, ensure_ascii=False)
    assert "Beatriz" not in crudo and "Calle 50" not in crudo and "312" not in crudo


def test_a2_con_una_sola_orden_la_nombra_y_la_abre(
        org_a, version, norte, admin_profile, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, admin_profile, "tok-a")
    o = _orden(org_a, version, 200)
    j = _jornada_de(org_a, [norte], admin_profile)

    _publicar(org_a, j, [o], django_capture_on_commit_callbacks)

    assert [(m["texto"], m["enlace"]) for m in fcm] == [
        ("📋 Te asignaron la OT #200 para el lunes 05/10", f"/ot/{o.id}")]


# ---------------------------------------------------------------------------
# B · lo que ya tenia no se avisa otra vez
# ---------------------------------------------------------------------------

def test_b_lo_que_ya_tenia_no_se_vuelve_a_avisar(
        org_a, version, norte, admin_profile, user_profile, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, admin_profile, "tok-a")
    _telefono(org_a, user_profile, "tok-u")
    suya = _orden(org_a, version, 300)
    movida = _de(_orden(org_a, version, 301), user_profile)
    j = _jornada_de(org_a, [norte], admin_profile)
    #  «Ya la tenia» = la recibio en una publicacion anterior.
    _publicar(org_a, j, [suya], django_capture_on_commit_callbacks)
    fcm.clear()

    r = _publicar(org_a, j, [suya, movida], django_capture_on_commit_callbacks)

    assert (r["sin_cambio"], r["reasignadas"]) == ([300], [301])
    #  Solo quien la recibe por primera vez, y solo por la que es nueva.
    assert [(m["token"], m["contenido"]["ordenes"]) for m in fcm] == [
        ("tok-a", [301])]


def test_b2_si_se_suma_alguien_solo_se_le_avisa_al_que_llega(
        org_a, version, norte, admin_profile, otro, fcm,
        django_capture_on_commit_callbacks):
    """La orden cambia de manos (la cuadrilla ahora es de dos), pero quien ya
    la tenia sigue: a el no se le avisa de nuevo."""
    _telefono(org_a, admin_profile, "tok-a")
    _telefono(org_a, otro, "tok-o")
    o = _de(_orden(org_a, version, 310), admin_profile)
    j = _jornada_de(org_a, [norte], admin_profile, otro)

    r = _publicar(org_a, j, [o], django_capture_on_commit_callbacks)

    assert r["reasignadas"] == [310]
    assert [m["token"] for m in fcm] == ["tok-o"]


# ---------------------------------------------------------------------------
# C · mover=False: lo publicado queda quieto
# ---------------------------------------------------------------------------

def test_c_sin_mover_lo_que_tiene_gente_queda_quieto(
        org_a, version, norte, admin_profile, user_profile, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, admin_profile, "tok-a")
    con_gente = _de(_orden(org_a, version, 400), user_profile)
    nueva = _orden(org_a, version, 401)
    j = _jornada_de(org_a, [norte], admin_profile)

    r = _publicar(org_a, j, [con_gente, nueva], django_capture_on_commit_callbacks,
                  mover=False)

    assert (r["quietas"], r["publicadas"], r["reasignadas"]) == ([400], 1, [])
    assert [a.profile_id for a in con_gente.asignaciones.all()] == [user_profile.id]
    assert [a.profile_id for a in nueva.asignaciones.all()] == [admin_profile.id]
    assert [m["contenido"]["ordenes"] for m in fcm] == [[401]]


def test_c2_el_boton_sigue_moviendo(
        org_a, version, norte, admin_profile, user_profile,
        django_capture_on_commit_callbacks):
    con_gente = _de(_orden(org_a, version, 410), user_profile)
    j = _jornada_de(org_a, [norte], admin_profile)

    r = _publicar(org_a, j, [con_gente], django_capture_on_commit_callbacks)

    assert (r["reasignadas"], r["quietas"]) == ([410], [])


# ---------------------------------------------------------------------------
# D · lo que asigno el Supervisor queda escrito, y no se congela
# ---------------------------------------------------------------------------

def test_d_queda_escrito_que_asigno_el_supervisor_y_no_cuenta_como_a_mano(
        org_a, version, norte, admin_profile, django_capture_on_commit_callbacks):
    o = _orden(org_a, version, 500)
    j = _jornada_de(org_a, [norte], admin_profile)

    _publicar(org_a, j, [o], django_capture_on_commit_callbacks,
              por_el_supervisor={"tarea": "publicar_el_reparto_del_dia"})

    ev = EventoTrabajo.objects.get(orden=o, tipo="asignada_por_el_supervisor")
    assert ev.profile_id is None
    assert (ev.datos["tarea"], ev.datos["cuadrilla"], ev.datos["jornada"]) == (
        "publicar_el_reparto_del_dia", "Cuadrilla norte", str(j.id))
    assert R._asignadas_a_mano(org_a, [o.id]) == set()


def test_d2_el_boton_no_deja_ese_evento(
        org_a, version, norte, admin_profile, django_capture_on_commit_callbacks):
    o = _orden(org_a, version, 510)
    j = _jornada_de(org_a, [norte], admin_profile)

    _publicar(org_a, j, [o], django_capture_on_commit_callbacks)

    assert not EventoTrabajo.objects.filter(
        orden=o, tipo="asignada_por_el_supervisor").exists()


# ---------------------------------------------------------------------------
# E · los otros caminos que asignan
# ---------------------------------------------------------------------------

def test_e_asignar_un_tecnico_avisa_con_la_orden_y_una_sola_vez(
        org_a, version, admin_profile, user_profile, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, user_profile, "tok-u")
    o = _orden(org_a, version, 600)

    with django_capture_on_commit_callbacks(execute=True):
        despacho.asignar(o, user_profile, admin_profile)
    with django_capture_on_commit_callbacks(execute=True):
        despacho.asignar(o, user_profile, admin_profile)     # ya es suya

    assert [(m["verbo"], m["texto"], m["enlace"]) for m in fcm] == [
        (avisos.VERBO_ASIGNADO, "📋 Te asignaron la OT #600", f"/ot/{o.id}")]


def test_e4_reasignar_la_misma_orden_avisa_al_nuevo(
        org_a, version, admin_profile, user_profile, otro, fcm,
        django_capture_on_commit_callbacks):
    """La clave del aviso es la ASIGNACION (lleva la revision): la misma orden
    asignada a otra persona es otro hecho, y no la tapa la idempotencia."""
    _telefono(org_a, user_profile, "tok-u")
    _telefono(org_a, otro, "tok-o")
    o = _orden(org_a, version, 605)

    with django_capture_on_commit_callbacks(execute=True):
        despacho.asignar(o, user_profile, admin_profile)
    with django_capture_on_commit_callbacks(execute=True):
        despacho.asignar(o, otro, admin_profile)

    assert [m["token"] for m in fcm] == ["tok-u", "tok-o"]


def test_e5_pasar_de_ayudante_a_principal_no_es_una_visita_nueva(
        org_a, version, admin_profile, user_profile, otro, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, otro, "tok-o")
    o = _de(_orden(org_a, version, 607), user_profile)

    with django_capture_on_commit_callbacks(execute=True):
        despacho.agregar_integrante(o, otro, admin_profile)
    #  Releida, como la manda la vista: con la revision vieja, la clave del
    #  aviso coincidiria con la anterior y lo taparia por la razon equivocada.
    o.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        despacho.asignar(o, otro, admin_profile)        # ya estaba: sube a principal

    assert [m["token"] for m in fcm] == ["tok-o"]


def test_e2_despachar_a_la_cuadrilla_avisa_a_quien_la_recibe_por_primera_vez(
        org_a, version, norte, admin_profile, user_profile, otro, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, user_profile, "tok-u")
    _telefono(org_a, otro, "tok-o")
    o = _de(_orden(org_a, version, 610), user_profile)
    j = _jornada_de(org_a, [norte], user_profile, otro)

    with django_capture_on_commit_callbacks(execute=True):
        despacho.asignar_a_jornada(o, j, admin_profile)

    assert [m["token"] for m in fcm] == ["tok-o"]


def test_e3_agregar_un_integrante_le_avisa_a_el(
        org_a, version, admin_profile, user_profile, otro, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, user_profile, "tok-u")
    _telefono(org_a, otro, "tok-o")
    o = _de(_orden(org_a, version, 620), user_profile)

    with django_capture_on_commit_callbacks(execute=True):
        despacho.agregar_integrante(o, otro, admin_profile)

    assert [(m["token"], m["texto"]) for m in fcm] == [
        ("tok-o", "📋 Te asignaron la OT #620")]


# ---------------------------------------------------------------------------
# F · solo al telefono
# ---------------------------------------------------------------------------

def test_f_el_chat_de_la_empresa_no_recibe_las_asignaciones(
        org_a, version, norte, admin_profile, fcm,
        django_capture_on_commit_callbacks):
    CanalDeAvisos.objects.create(
        org=org_a, tipo=CanalDeAvisos.GOOGLE_CHAT, nombre="Cuadrilla norte",
        destino="https://chat.googleapis.com/v1/spaces/XXX/messages?key=k")
    _telefono(org_a, admin_profile, "tok-a")
    j = _jornada_de(org_a, [norte], admin_profile)

    with mock.patch.object(avisos, "enviar_por", return_value=True) as chat:
        _publicar(org_a, j, [_orden(org_a, version, 700)],
                  django_capture_on_commit_callbacks)

    assert chat.call_count == 0
    assert len(fcm) == 1


# ---------------------------------------------------------------------------
# G · si la publicacion se deshace, no sale nada
# ---------------------------------------------------------------------------

def test_g_una_publicacion_deshecha_no_avisa(
        org_a, version, norte, admin_profile, fcm,
        django_capture_on_commit_callbacks):
    _telefono(org_a, admin_profile, "tok-a")
    o = _orden(org_a, version, 800)
    j = _jornada_de(org_a, [norte], admin_profile)

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(o.id)]}])
                raise RuntimeError("algo fallo despues de publicar")

    assert fcm == []
    assert not Notification.objects.filter(recipient=admin_profile).exists()
