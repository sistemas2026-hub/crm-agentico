"""
================================================================================
 EL DIA PUBLICADO  --  28/10/2026
================================================================================
`campo/dia_publicado.py` y `GET /api/campo/dia-publicado/`: lo que quedo
publicado un dia, para la pantalla de Programacion. Cada punto, con su prueba:

  Q  QUIEN la asigno y a que hora: el Supervisor, una persona con el boton
     «Publicar» (que desde hoy lo deja escrito), una persona al Despachar, o
     «sin registro» cuando no hay evento --no se adivina--.
  A  el AVISO: avisado, sin aviso, o sin telefono registrado.
  C  cada orden en la cuadrilla cuya gente la tiene; aparte, lo que tiene a
     alguien que ese dia no sale y lo que espera sin nadie.
  D  el DIA: lo programado para otro dia no entra; lo terminado ese dia si,
     lo terminado otro dia no.
  P  solo quien gestiona, con fecha, y solo su empresa.
  B  el boton deja quien publico SIN congelar la orden para el reparto.

    pytest campo/tests/test_dia_publicado.py
================================================================================
"""
import datetime as dt

import pytest
from django.utils import timezone

from campo import dia_publicado as D
from campo import reparto as R
from campo.avisos import DispositivoDeTecnico
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
from campo.services import despacho
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)
RUTA = "/api/campo/dia-publicado/"
CLIENTE = "Beatriz Pinzón"


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


_numero = iter(range(500, 9999))


def _orden(org, version, *, de=None, estado=OrdenTrabajo.ASIGNADA,
           prioridad=OrdenTrabajo.PRIORIDAD_MEDIA):
    o = OrdenTrabajo.objects.create(
        org=org, numero=next(_numero), tipo_trabajo_version=version,
        estado_operativo=estado, zona="MARTHA GISELA", prioridad=prioridad,
        cliente_nombre=CLIENTE)
    if de is not None:
        AsignacionTrabajo.objects.create(orden=o, profile=de, rol="tecnico",
                                         es_principal=True)
    return o


def _jornada(org, zonas, nombre, *profiles):
    c = Cuadrilla.objects.create(org=org, nombre=nombre)
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=c, fecha=LUNES, labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set(zonas)
    for i, profile in enumerate(profiles):
        persona = PersonaDeCampo.objects.create(org=org, profile=profile,
                                                nombre=f"{nombre} {i}")
        IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona,
                                           rol="tecnico")
    return j


def _filas(d) -> dict:
    """{numero: fila} de todas las cuadrillas."""
    return {f["numero"]: f for c in d["cuadrillas"] for f in c["ordenes"]}


# ---------------------------------------------------------------------------
# Q · quien la asigno
# ---------------------------------------------------------------------------

def test_q_lo_que_publico_el_supervisor_dice_supervisor_y_la_hora(
        org_a, version, norte, admin_profile, django_capture_on_commit_callbacks):
    j = _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    o = _orden(org_a, version)
    with django_capture_on_commit_callbacks(execute=True):
        R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(o.id)]}],
                   mover=False, por_el_supervisor={"tarea": "x"})

    f = _filas(D.del_dia(org_a, LUNES))[o.numero]

    assert (f["asignada_por"], f["asignada_por_nombre"]) == (D.SUPERVISOR, "Supervisor")
    assert f["asignada_en"] is not None
    assert f["tecnicos"] == [admin_profile.user.name or admin_profile.user.email]


def test_q2_el_boton_publicar_deja_quien_publico(
        org_a, version, norte, admin_profile, admin_client):
    j = _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    o = _orden(org_a, version)

    r = admin_client.post("/api/campo/cuadrillas/reparto/", {
        "asignaciones": [{"jornada": str(j.id), "ordenes": [str(o.id)]}]},
        format="json")
    assert r.status_code == 200, r.content

    ev = EventoTrabajo.objects.get(orden=o, tipo="publicada_por_una_persona")
    assert ev.profile_id == admin_profile.id
    f = _filas(D.del_dia(org_a, LUNES))[o.numero]
    assert (f["asignada_por"], f["asignada_por_nombre"]) == (
        D.PERSONA, admin_profile.user.name or admin_profile.user.email)


def test_q3_despachar_a_mano_dice_quien_la_asigno(
        org_a, version, norte, admin_profile, user_profile):
    _jornada(org_a, [norte], "Cuadrilla #1", user_profile)
    o = _orden(org_a, version)
    despacho.asignar(o, user_profile, admin_profile)

    f = _filas(D.del_dia(org_a, LUNES))[o.numero]

    assert f["asignada_por"] == D.PERSONA
    assert f["asignada_por_nombre"] == (admin_profile.user.name
                                        or admin_profile.user.email)


def test_q4_sin_evento_dice_sin_registro_y_no_adivina(
        org_a, version, norte, admin_profile):
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    o = _orden(org_a, version, de=admin_profile)

    d = D.del_dia(org_a, LUNES)

    assert _filas(d)[o.numero]["asignada_por"] == ""
    assert d["cuentas"]["sin_registro"] == 1


def test_q5_manda_el_ultimo_evento_y_la_hora_es_la_de_la_empresa(
        org_a, version, norte, admin_profile):
    #  El Supervisor la publico y despues una persona la paso a otro: manda
    #  la persona. Y la hora se dice en el reloj de la empresa, no en UTC.
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    o = _orden(org_a, version, de=admin_profile)
    EventoTrabajo.objects.create(org=org_a, orden=o,
                                 tipo="asignada_por_el_supervisor", datos={})
    ultimo = EventoTrabajo.objects.create(org=org_a, orden=o, tipo="reasignacion",
                                          profile=admin_profile, datos={})

    f = _filas(D.del_dia(org_a, LUNES))[o.numero]

    assert f["asignada_por"] == D.PERSONA
    assert f["asignada_en"] == ultimo.created_at.astimezone(
        R._zona_de(org_a)).isoformat()
    assert f["asignada_en"].endswith("-05:00")


# ---------------------------------------------------------------------------
# A · el aviso
# ---------------------------------------------------------------------------

def test_a_el_aviso_avisado_sin_aviso_y_sin_telefono(
        org_a, version, norte, admin_profile, user_profile,
        django_capture_on_commit_callbacks):
    j = _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    _jornada(org_a, [norte], "Cuadrilla #2", user_profile)
    publicada = _orden(org_a, version)
    with django_capture_on_commit_callbacks(execute=True):
        R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(publicada.id)]}])
    #  Sin aviso, con telefono.
    DispositivoDeTecnico.objects.create(org=org_a, profile=user_profile,
                                        token="tok-u", plataforma="android",
                                        activo=True)
    a_mano = _orden(org_a, version, de=user_profile)
    #  Sin aviso y nadie con telefono.
    sin_tel = _orden(org_a, version, de=admin_profile)

    f = _filas(D.del_dia(org_a, LUNES))

    assert f[publicada.numero]["aviso"] == D.AVISADO
    assert f[a_mano.numero]["aviso"] == D.SIN_AVISO
    assert f[sin_tel.numero]["aviso"] == D.SIN_TELEFONO


def test_a2_el_aviso_de_una_orden_despachada_a_mano_cuenta(
        org_a, version, norte, admin_profile, user_profile):
    from common.models import Notification

    _jornada(org_a, [norte], "Cuadrilla #1", user_profile)
    o = _orden(org_a, version)
    despacho.asignar(o, user_profile, admin_profile)
    #  Es el aviso de UNA orden: va atado a ella, no a una lista de numeros.
    n = Notification.objects.get(recipient=user_profile, verb="trabajo_asignado")
    assert str(n.entity_id) == str(o.id)
    assert "ordenes" not in (n.data or {})

    assert _filas(D.del_dia(org_a, LUNES))[o.numero]["aviso"] == D.AVISADO


# ---------------------------------------------------------------------------
# C · cada orden en su cuadrilla, y lo que queda aparte
# ---------------------------------------------------------------------------

def test_c_cada_orden_en_la_cuadrilla_de_su_gente_y_lo_demas_aparte(
        org_a, version, norte, admin_profile, user_profile, django_user_model):
    from common.models import Profile

    u = django_user_model.objects.create_user(email="otro.dia@test.com",
                                              password="testpass123")
    no_sale = Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    _jornada(org_a, [norte], "Cuadrilla #2", user_profile)
    de_1 = _orden(org_a, version, de=admin_profile)
    de_2 = _orden(org_a, version, de=user_profile)
    trabada = _orden(org_a, version, de=no_sale)
    espera = _orden(org_a, version, prioridad=OrdenTrabajo.PRIORIDAD_ALTA)

    d = D.del_dia(org_a, LUNES)

    por_cuadrilla = {c["cuadrilla"]: [f["numero"] for f in c["ordenes"]]
                     for c in d["cuadrillas"]}
    assert por_cuadrilla == {"Cuadrilla #1": [de_1.numero],
                             "Cuadrilla #2": [de_2.numero]}
    assert [f["numero"] for f in d["con_alguien_que_no_sale"]] == [trabada.numero]
    assert [e["numero"] for e in d["esperan"]] == [espera.numero]
    assert d["cuentas"]["esperan"] == 1


# ---------------------------------------------------------------------------
# D · el dia
# ---------------------------------------------------------------------------

def test_d_otro_dia_no_entra_y_lo_terminado_solo_ese_dia(
        org_a, version, norte, admin_profile):
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    mañana = _orden(org_a, version, de=admin_profile)
    OrdenTrabajo.objects.filter(pk=mañana.pk).update(
        programada_para=timezone.make_aware(
            dt.datetime.combine(LUNES + dt.timedelta(days=1), dt.time(0, 0))))
    hoy = _orden(org_a, version, de=admin_profile,
                 estado=OrdenTrabajo.COMPLETADA_CAMPO)
    OrdenTrabajo.objects.filter(pk=hoy.pk).update(completada_campo_en=timezone.make_aware(
        dt.datetime.combine(LUNES, dt.time(14, 0))))
    ayer = _orden(org_a, version, de=admin_profile,
                  estado=OrdenTrabajo.COMPLETADA_CAMPO)
    OrdenTrabajo.objects.filter(pk=ayer.pk).update(completada_campo_en=timezone.make_aware(
        dt.datetime.combine(LUNES - dt.timedelta(days=1), dt.time(14, 0))))
    sin_fecha_espera = _orden(org_a, version)
    OrdenTrabajo.objects.filter(pk=sin_fecha_espera.pk).update(
        programada_para=timezone.make_aware(
            dt.datetime.combine(LUNES + dt.timedelta(days=2), dt.time(0, 0))))

    d = D.del_dia(org_a, LUNES)

    numeros = set(_filas(d))
    assert hoy.numero in numeros
    assert mañana.numero not in numeros and ayer.numero not in numeros
    assert _filas(d)[hoy.numero]["estado"] == OrdenTrabajo.COMPLETADA_CAMPO
    assert sin_fecha_espera.numero not in [e["numero"] for e in d["esperan"]]


def test_d2_el_tope_es_el_de_la_cuadrilla_y_si_no_el_de_la_empresa(
        org_a, norte, admin_profile, user_profile):
    from campo.cuadrillas import configuracion_de_reparto

    propia = _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    Cuadrilla.objects.filter(pk=propia.cuadrilla_id).update(tope_diario=3)
    _jornada(org_a, [norte], "Cuadrilla #2", user_profile)
    de_la_empresa = configuracion_de_reparto(org_a).tope_por_cuadrilla
    assert de_la_empresa != 3

    d = D.del_dia(org_a, LUNES)

    assert {c["cuadrilla"]: c["tope"] for c in d["cuadrillas"]} == {
        "Cuadrilla #1": 3, "Cuadrilla #2": de_la_empresa}


# ---------------------------------------------------------------------------
# P · permisos, fecha y empresa
# ---------------------------------------------------------------------------

def test_p_solo_quien_gestiona_y_con_fecha(org_a, admin_client, user_client):
    assert user_client.get(RUTA, {"fecha": LUNES.isoformat()}).status_code == 403
    assert admin_client.get(RUTA).status_code == 400
    r = admin_client.get(RUTA, {"fecha": LUNES.isoformat()})
    assert r.status_code == 200 and r.json()["fecha"] == LUNES.isoformat()


def test_p2_otra_empresa_no_aparece(org_a, org_b, version, norte, admin_profile,
                                     admin_client):
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    wt = WorkType.objects.create(org=org_b, codigo="ftth", nombre="FTTH",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    vb = WorkTypeVersion.objects.create(work_type=wt, version=1,
                                        estado=WorkTypeVersion.PUBLICADA,
                                        esquema={"campos": []})
    ajena = _orden(org_b, vb, de=admin_profile)

    d = admin_client.get(RUTA, {"fecha": LUNES.isoformat()}).json()

    assert ajena.numero not in _filas(d)
    assert ajena.numero not in [f["numero"] for f in d["con_alguien_que_no_sale"]]


def test_p3_sin_datos_del_cliente(org_a, version, norte, admin_profile):
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    _orden(org_a, version, de=admin_profile)
    _orden(org_a, version)

    assert CLIENTE not in str(D.del_dia(org_a, LUNES))


# ---------------------------------------------------------------------------
# B · el boton deja quien publico sin congelar la orden
# ---------------------------------------------------------------------------

def test_b_publicar_con_el_boton_no_congela_la_orden(
        org_a, version, norte, admin_profile):
    j = _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    o = _orden(org_a, version)

    R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(o.id)]}],
               por_una_persona=admin_profile)

    assert EventoTrabajo.objects.filter(orden=o, tipo="publicada_por_una_persona",
                                        profile=admin_profile).count() == 1
    assert R._asignadas_a_mano(org_a, [o.id]) == set()
