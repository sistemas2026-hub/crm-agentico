"""
================================================================================
 EL DIA PUBLICADO  --  28/10/2026
================================================================================
`campo/dia_publicado.py` y `GET /api/campo/dia-publicado/`: lo que quedo
publicado un dia, para la pantalla de Programacion. Cada punto, con su prueba:

  Q  QUIEN la asigno y a que hora: el Supervisor, una persona con el boton
     «Publicar» (que desde hoy lo deja escrito), una persona al Despachar, o
     «sin registro» cuando no hay evento --no se adivina--.
  A  el AVISO: enviado al telefono (Google lo acepto), sin telefono
     registrado, no llego al telefono, o sin aviso. Que exista la
     notificacion no alcanza para decir «avisado».
  C  cada orden en la cuadrilla cuya gente la tiene; aparte, lo que tiene a
     alguien que ese dia no sale y lo que espera sin nadie.
  D  el DIA: lo programado para otro dia no entra; lo terminado ese dia si,
     lo terminado otro dia no.
  P  solo quien gestiona, con fecha, y solo su empresa.
  R  POR REVISAR (31/10/2026): lo terminado en campo y sin cerrar de un dia
     anterior sale aparte, hasta que alguien lo apruebe y lo cierre. Y cada
     orden trae los recordatorios que el Supervisor le mando, terminada o no.
  B  el boton deja quien publico SIN congelar la orden para el reparto.

    pytest campo/tests/test_dia_publicado.py
================================================================================
"""
import datetime as dt
from unittest import mock

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
from campo.services import despacho, push_fcm
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

@pytest.fixture
def fcm():
    """El borde con Google. `fcm["contesta"]` decide que devuelve."""
    estado = {"contesta": push_fcm.ENTREGADO}

    def mandar(token, titulo, texto, enlace, *, aviso_id="", verbo="",
               contenido=None):
        return estado["contesta"]

    with mock.patch.object(push_fcm, "esta_configurado", return_value=True), \
            mock.patch.object(push_fcm, "mandar_a_un_telefono", side_effect=mandar):
        yield estado


def _telefono(org, profile):
    return DispositivoDeTecnico.objects.create(
        org=org, profile=profile, token=f"tok-{profile.id}", plataforma="android",
        activo=True)


def _persona(django_user_model, org, email):
    from common.models import Profile

    u = django_user_model.objects.create_user(email=email, password="testpass123")
    return Profile.objects.create(user=u, org=org, role="USER", is_active=True)


def test_a_el_aviso_avisado_sin_aviso_y_sin_telefono(
        org_a, version, norte, admin_profile, user_profile, django_user_model,
        fcm, django_capture_on_commit_callbacks):
    sin_tel = _persona(django_user_model, org_a, "sin.telefono@test.com")
    j = _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    _jornada(org_a, [norte], "Cuadrilla #2", user_profile)
    _jornada(org_a, [norte], "Cuadrilla #3", sin_tel)
    _telefono(org_a, admin_profile)
    _telefono(org_a, user_profile)
    publicada = _orden(org_a, version)
    with django_capture_on_commit_callbacks(execute=True):
        R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(publicada.id)]}])
    #  Con telefono y sin aviso.
    a_mano = _orden(org_a, version, de=user_profile)
    #  Sin aviso y nadie con telefono.
    nadie = _orden(org_a, version, de=sin_tel)

    f = _filas(D.del_dia(org_a, LUNES))

    assert f[publicada.numero]["aviso"] == D.AVISADO
    assert f[a_mano.numero]["aviso"] == D.SIN_AVISO
    assert f[nadie.numero]["aviso"] == D.SIN_TELEFONO


def test_a2_el_aviso_de_una_orden_despachada_a_mano_cuenta(
        org_a, version, norte, admin_profile, user_profile, fcm,
        django_capture_on_commit_callbacks):
    from common.models import Notification

    _jornada(org_a, [norte], "Cuadrilla #1", user_profile)
    _telefono(org_a, user_profile)
    o = _orden(org_a, version)
    with django_capture_on_commit_callbacks(execute=True):
        despacho.asignar(o, user_profile, admin_profile)
    #  Es el aviso de UNA orden: va atado a ella, no a una lista de numeros.
    n = Notification.objects.get(recipient=user_profile, verb="trabajo_asignado")
    assert str(n.entity_id) == str(o.id)
    assert "ordenes" not in (n.data or {})

    assert _filas(D.del_dia(org_a, LUNES))[o.numero]["aviso"] == D.AVISADO


def test_a3_sin_telefono_no_dice_avisado_aunque_exista_la_notificacion(
        org_a, version, norte, admin_profile, user_profile, fcm,
        django_capture_on_commit_callbacks):
    #  Lo que mostro produccion el 28/10/2026: el mismo tecnico, sin telefono,
    #  «Avisado» en dos ordenes y «Sin telefono registrado» en la tercera. La
    #  notificacion se crea igual; el envio no se intenta.
    from common.models import Notification

    j = _jornada(org_a, [norte], "Cuadrilla #1", user_profile)
    publicada, despachada = _orden(org_a, version), _orden(org_a, version)
    with django_capture_on_commit_callbacks(execute=True):
        R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(publicada.id)]}])
        despacho.asignar(despachada, user_profile, admin_profile)
    assert Notification.objects.filter(recipient=user_profile).count() == 2

    f = _filas(D.del_dia(org_a, LUNES))

    assert f[publicada.numero]["aviso"] == D.SIN_TELEFONO
    assert f[despachada.numero]["aviso"] == D.SIN_TELEFONO


def test_a4_con_telefono_y_sin_envio_aceptado_dice_que_no_llego(
        org_a, version, norte, admin_profile, user_profile, fcm,
        django_capture_on_commit_callbacks):
    j = _jornada(org_a, [norte], "Cuadrilla #1", user_profile)
    _jornada(org_a, [norte], "Cuadrilla #2", admin_profile)
    #  Google lo rechazo.
    _telefono(org_a, user_profile)
    fcm["contesta"] = push_fcm.FALLO
    rechazada = _orden(org_a, version)
    with django_capture_on_commit_callbacks(execute=True):
        R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(rechazada.id)]}])
    #  Se aviso cuando no tenia telefono, y lo registro despues: a ese
    #  telefono nunca le llego.
    fcm["contesta"] = push_fcm.ENTREGADO
    antes = _orden(org_a, version)
    with django_capture_on_commit_callbacks(execute=True):
        despacho.asignar(antes, admin_profile, admin_profile)
    _telefono(org_a, admin_profile)

    f = _filas(D.del_dia(org_a, LUNES))

    assert f[rechazada.numero]["aviso"] == D.NO_LLEGO
    assert f[antes.numero]["aviso"] == D.NO_LLEGO


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
# E · por que espera cuadrilla, con la cuenta con la que publica el Supervisor
#     (pregunta del usuario, 28/10/2026: «¿por que solo 4 a la cuadrilla 3?»)
# ---------------------------------------------------------------------------

def _esperan(d) -> dict:
    return {e["numero"]: e for e in d["esperan"]}


def _de_labor(org, labor, codigo):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo, labor=labor)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})


def test_e_cabe_y_cupo_lleno(org_a, version, norte, admin_profile, user_profile):
    llena = _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    Cuadrilla.objects.filter(pk=llena.cuadrilla_id).update(tope_diario=1)
    _orden(org_a, version, de=admin_profile)                 # su carga: 1 de 1
    libre = _orden(org_a, version)

    e = _esperan(D.del_dia(org_a, LUNES))[libre.numero]
    assert e["motivo"] == D.CUPO_LLENO
    assert "Norte" in e["por_que"]

    _jornada(org_a, [norte], "Cuadrilla #2", user_profile)

    e = _esperan(D.del_dia(org_a, LUNES))[libre.numero]
    assert e["motivo"] == D.CABE
    assert "Cuadrilla #2" in e["por_que"]


def test_e2_ninguna_cuadrilla_de_su_labor_y_la_que_no_recibe(
        org_a, version, norte, admin_profile):
    from campo.labores import nombres_de_labor

    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)   # instalacion
    trabajo = _orden(org_a, _de_labor(org_a, JornadaDeCuadrilla.TRABAJOS, "obra"))

    e = _esperan(D.del_dia(org_a, LUNES))[trabajo.numero]
    assert e["motivo"] == D.SIN_CUADRILLA
    T = JornadaDeCuadrilla.TRABAJOS
    assert nombres_de_labor(org_a).get(T, T) in e["por_que"]
    assert "Norte" in e["por_que"]

    #  Una cuadrilla de esa zona, sin nadie con cuenta, pero de OTRA labor: no
    #  es la que falta.
    sin_cuenta = _jornada(org_a, [norte], "Cuadrilla #7")

    assert _esperan(D.del_dia(org_a, LUNES))[trabajo.numero]["motivo"] == D.SIN_CUADRILLA

    #  De esa labor y esa zona, sin nadie con cuenta: esa es la que no recibe.
    JornadaDeCuadrilla.objects.filter(pk=sin_cuenta.pk).update(
        labor=JornadaDeCuadrilla.TRABAJOS)

    e = _esperan(D.del_dia(org_a, LUNES))[trabajo.numero]
    assert e["motivo"] == D.NO_RECIBE
    assert "Cuadrilla #7" in e["por_que"] and "cuenta" in e["por_que"]


def test_e3_sin_zona_y_sin_labor(org_a, version, norte, admin_profile):
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    rara = _orden(org_a, version)
    OrdenTrabajo.objects.filter(pk=rara.pk).update(zona="BARRIO QUE NO EXISTE")
    sin_labor = _orden(org_a, _de_labor(org_a, "", "sin-labor"))

    d = _esperan(D.del_dia(org_a, LUNES))

    assert d[rara.numero]["motivo"] == D.SIN_ZONA
    assert "BARRIO QUE NO EXISTE" in d[rara.numero]["por_que"]
    assert d[sin_labor.numero]["motivo"] == D.SIN_LABOR


def test_e4_si_la_cuenta_falla_no_inventa_un_motivo(
        org_a, version, norte, admin_profile, monkeypatch):
    from operaciones import publicacion_del_reparto as pub

    def falla(*a, **k):
        raise RuntimeError("caida")

    monkeypatch.setattr(pub, "propuesta", falla)
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    o = _orden(org_a, version)

    e = _esperan(D.del_dia(org_a, LUNES))[o.numero]
    assert (e["motivo"], e["por_que"]) == ("", "")


# ---------------------------------------------------------------------------
# G · por persona, lo que su app deberia tener (pregunta del usuario,
#     28/10/2026: «¿y si en Programacion le salen 5 y en la app menos?»)
# ---------------------------------------------------------------------------

def test_g_lo_publicado_va_a_todos_y_lo_de_a_mano_a_uno(
        org_a, version, norte, admin_profile, user_profile):
    j = _jornada(org_a, [norte], "Cuadrilla #1", admin_profile, user_profile)
    publicada = _orden(org_a, version)
    R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(publicada.id)]}])
    _orden(org_a, version, de=admin_profile)                   # a mano, a uno

    c = D.del_dia(org_a, LUNES)["cuadrillas"][0]

    assert len(c["ordenes"]) == 2
    assert {p["nombre"]: p["ordenes"] for p in c["personas"]} == {
        "Cuadrilla #1 0": 2, "Cuadrilla #1 1": 1}


def test_g2_lo_asignado_despues_del_ultimo_contacto_todavia_no_esta(
        org_a, version, norte, admin_profile, user_profile):
    from campo.seguimiento import ContactoDeDispositivo

    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    _jornada(org_a, [norte], "Cuadrilla #2", user_profile)
    DispositivoDeTecnico.objects.create(org=org_a, profile=admin_profile,
                                        token="tok-a", plataforma="android",
                                        activo=True)
    visto = timezone.now() - dt.timedelta(hours=3)
    ContactoDeDispositivo.objects.create(org=org_a, profile=admin_profile,
                                         visto_en=visto, ultima_ruta="/api/campo/")

    def asignada_en(o, cuando):
        AsignacionTrabajo.objects.filter(orden=o).update(created_at=cuando)

    antes = _orden(org_a, version, de=admin_profile)
    asignada_en(antes, visto - dt.timedelta(minutes=30))
    despues = _orden(org_a, version, de=admin_profile)
    asignada_en(despues, visto + dt.timedelta(hours=1))
    #  Dentro del freno con que se anota el contacto: no se sabe, no se afirma.
    en_el_freno = _orden(org_a, version, de=admin_profile)
    asignada_en(en_el_freno, visto + dt.timedelta(seconds=30))
    #  Terminada: ya la tuvo.
    terminada = _orden(org_a, version, de=admin_profile,
                       estado=OrdenTrabajo.COMPLETADA_CAMPO)
    OrdenTrabajo.objects.filter(pk=terminada.pk).update(
        completada_campo_en=timezone.make_aware(dt.datetime.combine(LUNES, dt.time(15, 0))))
    asignada_en(terminada, visto + dt.timedelta(hours=1))
    #  Quien nunca hablo con el servidor no tiene nada en el telefono.
    asignada_en(_orden(org_a, version, de=user_profile), visto)

    c1, c2 = D.del_dia(org_a, LUNES)["cuadrillas"]
    (a,), (u,) = c1["personas"], c2["personas"]

    assert (a["ordenes"], a["sin_bajar"], a["telefono"]) == (4, 1, True)
    assert a["ultimo_contacto"] == visto.astimezone(R._zona_de(org_a)).isoformat()
    assert a["ultimo_contacto"].endswith("-05:00")
    assert (u["ordenes"], u["sin_bajar"], u["telefono"], u["ultimo_contacto"]) == (
        1, 1, False, None)


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


def test_p3_del_cliente_solo_el_nombre_y_solo_en_lo_asignado(org_a, version, norte,
                                                            admin_profile):
    """DECISION DEL USUARIO, 29/10/2026: «en Programacion, donde muestra los
    tickets asignados, salgan los nombres». Hasta entonces esto afirmaba que no
    salia NINGUN dato del cliente; ahora sale el NOMBRE, y solo en las ordenes
    de una cuadrilla. El telefono y la direccion, nunca: no hacen falta para
    saber con cual empieza.

    CAMBIO DEL USUARIO, 30/10/2026: «donde dice todavia no sale deberia ir el
    asunto del ticket y la direccion» (el cuadro del seguimiento de cada
    cuadrilla). La DIRECCION sale, con el mismo alcance que el nombre: solo en
    las ordenes de una cuadrilla, nunca en las que esperan. El telefono sigue
    sin salir."""
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    asignada = _orden(org_a, version, de=admin_profile)
    espera = _orden(org_a, version)
    OrdenTrabajo.objects.filter(pk__in=[asignada.pk, espera.pk]).update(
        cliente_telefono="3113683499", cliente_direccion="Calle 38 # 78-33")

    d = D.del_dia(org_a, LUNES)

    assert _filas(d)[asignada.numero]["cliente"] == CLIENTE
    texto = str(d)
    assert texto.count(CLIENTE) == 1, "solo en la orden asignada, no en las que esperan"
    assert _filas(d)[asignada.numero]["direccion"] == "Calle 38 # 78-33"
    assert texto.count("Calle 38") == 1, "la direccion, solo en la orden asignada"
    assert "3113683499" not in texto, "el telefono, nunca"


# ---------------------------------------------------------------------------
# R · por revisar
# ---------------------------------------------------------------------------

def _terminada(org, version, de, dia, *, validacion=OrdenTrabajo.PENDIENTE,
               estado=OrdenTrabajo.COMPLETADA_CAMPO):
    o = _orden(org, version, de=de, estado=estado)
    OrdenTrabajo.objects.filter(pk=o.pk).update(
        estado_validacion=validacion,
        completada_campo_en=timezone.make_aware(dt.datetime.combine(dia, dt.time(14, 0))))
    return o


def test_r_lo_terminado_sin_cerrar_de_otro_dia_sale_por_revisar(
        org_a, org_b, version, norte, admin_profile):
    """31/10/2026, en produccion: la OT #4 se termino el 30 y el 31 no salia ni
    en Hoy ni en Cerradas. El usuario: «en la supervisor no sale el ticket»."""
    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    domingo = LUNES - dt.timedelta(days=1)
    pendiente = _terminada(org_a, version, admin_profile, domingo)
    vieja = _terminada(org_a, version, admin_profile, LUNES - dt.timedelta(days=9))
    aprobada = _terminada(org_a, version, admin_profile, domingo,
                          validacion=OrdenTrabajo.APROBADO)
    de_hoy = _terminada(org_a, version, admin_profile, LUNES)
    cerrada = _terminada(org_a, version, admin_profile, domingo,
                         validacion=OrdenTrabajo.APROBADO, estado=OrdenTrabajo.CERRADA)
    wt = WorkType.objects.create(org=org_b, codigo="ftth", nombre="FTTH",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    vb = WorkTypeVersion.objects.create(work_type=wt, version=1,
                                        estado=WorkTypeVersion.PUBLICADA,
                                        esquema={"campos": []})
    ajena = _terminada(org_b, vb, admin_profile, domingo)

    d = D.del_dia(org_a, LUNES)

    por_revisar = {f["numero"]: f for f in d["por_revisar"]}
    assert [f["numero"] for f in d["por_revisar"]] == [vieja.numero, pendiente.numero,
                                                       aprobada.numero], \
        "las de antes, la mas vieja primero; ni la de hoy, ni la cerrada, ni la ajena"
    assert de_hoy.numero in _filas(d), "la de hoy sigue en su cuadrilla"
    assert pendiente.numero not in _filas(d)
    assert cerrada.numero not in por_revisar and ajena.numero not in por_revisar
    assert por_revisar[pendiente.numero]["revision"] is not None, \
        "trae lo que dice el Supervisor, para aprobar o devolver"
    assert por_revisar[aprobada.numero]["validacion"] == OrdenTrabajo.APROBADO
    assert por_revisar[pendiente.numero]["terminada_el"].startswith("04/10")
    assert por_revisar[pendiente.numero]["tecnicos"]
    assert d["cuentas"]["por_revisar"] == 3
    assert d["cuentas"]["publicadas"] == 1, "las cuentas del dia siguen siendo del dia"


def test_r2_cada_orden_trae_sus_recordatorios_aunque_este_terminada(
        org_a, org_b, version, norte, admin_profile):
    """31/10/2026: el usuario probo la vibracion con la OT #4, la termino, y no
    habia donde ver si el Supervisor le mando el recordatorio: el log de la
    cuadrilla solo muestra lo abierto."""
    from campo.avisos import AvisoEnviado

    _jornada(org_a, [norte], "Cuadrilla #1", admin_profile)
    domingo = LUNES - dt.timedelta(days=1)
    terminada = _terminada(org_a, version, admin_profile, domingo)
    en_curso = _orden(org_a, version, de=admin_profile, estado=OrdenTrabajo.EN_CAMINO)
    callada = _orden(org_a, version, de=admin_profile, estado=OrdenTrabajo.EN_CAMINO)
    OrdenTrabajo.objects.filter(pk__in=[terminada.pk, en_curso.pk, callada.pk]).update(
        created_at=timezone.make_aware(dt.datetime.combine(domingo, dt.time(7, 0))))

    def recordo(orden, dia, hora, canales, org=org_a):
        a = AvisoEnviado.objects.create(org=org, clave=f"sin_reporte|{orden.id}|{dia}T{hora}",
                                        canales=canales)
        AvisoEnviado.objects.filter(pk=a.pk).update(created_at=timezone.make_aware(
            dt.datetime.combine(dia, dt.time(*map(int, hora.split(":"))))))

    recordo(terminada, domingo, "10:15", ["push"])
    recordo(en_curso, LUNES, "09:40", [])
    recordo(callada, LUNES, "09:50", ["push"], org=org_b)
    #  Otra clave de la misma orden no es un recordatorio.
    AvisoEnviado.objects.create(org=org_a, clave=f"asignacion|{callada.id}|1", canales=["push"])

    d = D.del_dia(org_a, LUNES)

    por_revisar = {f["numero"]: f for f in d["por_revisar"]}
    assert por_revisar[terminada.numero]["recordatorios"] == [
        {"cuando": "04/10 10:15", "llego": True}], "de otro dia, con su fecha"
    assert _filas(d)[en_curso.numero]["recordatorios"] == [
        {"cuando": "09:40", "llego": False}], "si no llego al telefono, se dice"
    assert _filas(d)[callada.numero]["recordatorios"] == [], \
        "ni lo de otra empresa ni otra clave cuentan"


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
