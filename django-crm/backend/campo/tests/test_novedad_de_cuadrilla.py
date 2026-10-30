"""
================================================================================
 LA NOVEDAD DE LA CUADRILLA Y EL SEGUIMIENTO EN PROGRAMACION  --  30/10/2026
================================================================================
SPEC/objetivos/novedad-de-cuadrilla.md. El usuario: «¿cómo el técnico reporta
alguna novedad sin escribir en el ticket, por ejemplo se pinchó la llanta?», y
«unos cuadros con la cuadrilla, qué tiene en progreso, qué tiempo lleva, y un
log contraíble de los seguimientos».

  A  avisar: con la jornada del tecnico, aviso a quien gestiona, idempotente,
     y lo invalido se rechaza
  V  vigente: la corta vence sola; la del resto del dia, hasta «Ya seguí»
  R  resolver: quien la aviso o quien gestiona; otra empresa, 404
  F  la del resto del dia saca a la cuadrilla de hoy; la corta no
  S  la regla de los 30 minutos queda pausada mientras dura
  P  Programacion: los tiempos de cada orden, y por cuadrilla el resumen, las
     novedades y el log del dia

    pytest campo/tests/test_novedad_de_cuadrilla.py
================================================================================
"""
import datetime as dt
import zoneinfo

import pytest
from django.utils import timezone

from campo import dia_publicado as D
from campo import novedades as N
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
from common.models import Notification

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")
URL = "/api/campo/novedades/"


@pytest.fixture
def org(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    return org_a


def _hoy():
    return timezone.now().astimezone(BOGOTA).date()


def _jornada(org, profile, nombre="Cuadrilla 1", fecha=None):
    c = Cuadrilla.objects.create(org=org, nombre=nombre)
    j = JornadaDeCuadrilla.objects.create(org=org, cuadrilla=c, fecha=fecha or _hoy(),
                                          labor=JornadaDeCuadrilla.CORRECTIVO)
    persona = PersonaDeCampo.objects.create(org=org, profile=profile, nombre=nombre)
    IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona, rol="tecnico")
    return j


def _avisar(cliente, clave="k-1", **cuerpo):
    datos = {"tipo": "llanta", "afecta": "media_hora", **cuerpo}
    return cliente.post(URL, datos, format="json", HTTP_IDEMPOTENCY_KEY=clave)


# ---------------------------------------------------------------------------
# A · avisar
# ---------------------------------------------------------------------------

def test_a_avisa_con_su_jornada_y_le_llega_a_quien_gestiona(org, user_client, user_profile,
                                                           admin_profile):
    j = _jornada(org, user_profile)

    r = _avisar(user_client, texto="  en la autopista  ")

    assert r.status_code == 201, r.content
    n = N.NovedadDeCuadrilla.objects.get()
    assert (n.jornada_id, n.profile_id, n.texto) == (j.id, user_profile.id, "en la autopista")
    assert r.json()["cuadrilla"] == "Cuadrilla 1"
    avisos = Notification.objects.filter(verb="novedad_de_cuadrilla")
    assert list(avisos.values_list("recipient_id", flat=True)) == [admin_profile.id]


def test_a4_la_carrera_de_dos_reintentos_deja_una_y_no_la_cuenta_como_nueva(
        org, user_profile, monkeypatch):
    """Entre «¿ya está?» y crearla, otro reintento la creó: la restricción de la
    base la frena, y la segunda devuelve la que ya estaba, como no nueva."""
    _jornada(org, user_profile)
    primera, _ = N.avisar(org, user_profile, tipo="llanta", afecta="media_hora", clave="k")
    real = N.NovedadDeCuadrilla.objects.filter

    def ciega(*args, **kwargs):
        #  «Todavía no está»: solo para la pregunta del reintento.
        if set(kwargs) == {"org", "clave"}:
            return real(pk__in=[])
        return real(*args, **kwargs)

    monkeypatch.setattr(N.NovedadDeCuadrilla.objects, "filter", ciega)
    segunda, creada = N.avisar(org, user_profile, tipo="llanta", afecta="media_hora", clave="k")

    assert (segunda.id, creada) == (primera.id, False)
    assert N.NovedadDeCuadrilla.objects.count() == 1


def test_a2_un_reintento_no_la_duplica_ni_repite_el_aviso(org, user_client, user_profile,
                                                         admin_profile):
    _jornada(org, user_profile)
    assert _avisar(user_client).status_code == 201
    r = _avisar(user_client)

    assert r.status_code == 200
    assert N.NovedadDeCuadrilla.objects.count() == 1
    assert Notification.objects.filter(verb="novedad_de_cuadrilla").count() == 1


def test_a3_lo_invalido_se_rechaza(org, user_client):
    assert _avisar(user_client, tipo="ovni").status_code == 400
    assert _avisar(user_client, afecta="").status_code == 400
    assert _avisar(user_client, texto="x" * 281).status_code == 400
    assert user_client.post(URL, {"tipo": "llanta", "afecta": "media_hora"},
                            format="json").status_code == 400, "sin clave no entra"
    assert not N.NovedadDeCuadrilla.objects.exists()


# ---------------------------------------------------------------------------
# V · vigente   R · resolver
# ---------------------------------------------------------------------------

def _novedad(org, profile, afecta, *, hace=dt.timedelta(0), jornada=None, clave="k"):
    ahora = timezone.now()
    return N.NovedadDeCuadrilla.objects.create(
        org=org, profile=profile, jornada=jornada, tipo=N.LLANTA, afecta=afecta,
        fecha=ahora.astimezone(BOGOTA).date(), avisada_en=ahora - hace, clave=clave)


def test_v_la_corta_vence_sola_y_la_del_resto_del_dia_no(org, user_profile):
    ahora = timezone.now()
    corta = _novedad(org, user_profile, N.MEDIA_HORA, hace=dt.timedelta(minutes=29), clave="a")
    vieja = _novedad(org, user_profile, N.MEDIA_HORA, hace=dt.timedelta(minutes=31), clave="b")
    larga = _novedad(org, user_profile, N.RESTO_DEL_DIA, hace=dt.timedelta(hours=6), clave="c")

    assert (corta.vigente(ahora), vieja.vigente(ahora), larga.vigente(ahora)) == (True, False, True)


def test_r_la_cierra_quien_la_aviso_o_quien_gestiona_y_nadie_de_otra_empresa(
        org, user_client, user_profile, admin_client, org_b_client):
    n = _novedad(org, user_profile, N.RESTO_DEL_DIA)
    ruta = f"{URL}{n.id}/resolver/"

    assert org_b_client.post(ruta).status_code == 404
    assert user_client.post(ruta).status_code == 200
    n.refresh_from_db()
    assert n.resuelta_en is not None and not n.vigente()
    otra = _novedad(org, user_profile, N.RESTO_DEL_DIA, clave="otra")
    assert admin_client.post(f"{URL}{otra.id}/resolver/").status_code == 200


def test_r2_el_tecnico_ve_las_suyas_y_quien_gestiona_todas(org, user_client, admin_client,
                                                          user_profile, admin_profile):
    _novedad(org, user_profile, N.MEDIA_HORA, clave="mia")
    _novedad(org, admin_profile, N.MEDIA_HORA, clave="de-otro")

    assert len(user_client.get(URL).json()["novedades"]) == 1
    assert len(admin_client.get(URL).json()["novedades"]) == 2


# ---------------------------------------------------------------------------
# F · el resto del dia saca a la cuadrilla   S · la regla de los 30 minutos
# ---------------------------------------------------------------------------

def test_f_el_resto_del_dia_saca_a_la_cuadrilla_y_la_corta_no(org, user_profile, admin_profile):
    j = _jornada(org, user_profile)
    ahora = timezone.now()
    _novedad(org, admin_profile, N.MEDIA_HORA, jornada=j, clave="corta")
    assert N.fuera_por_novedad(org, _hoy(), ahora) == set()

    _novedad(org, admin_profile, N.RESTO_DEL_DIA, jornada=j, clave="larga")
    assert N.fuera_por_novedad(org, _hoy(), ahora) == {admin_profile.id, user_profile.id}


@pytest.fixture
def version(org):
    wt = WorkType.objects.create(org=org, codigo="sop", nombre="Soporte",
                                 labor=JornadaDeCuadrilla.CORRECTIVO)
    return WorkTypeVersion.objects.create(work_type=wt, version=1,
                                          estado=WorkTypeVersion.PUBLICADA,
                                          esquema={"campos": []})


_numero = iter(range(700, 9999))


def _orden(org, version, de, estado=OrdenTrabajo.EN_SITIO):
    o = OrdenTrabajo.objects.create(org=org, numero=next(_numero), tipo_trabajo_version=version,
                                    estado_operativo=estado, zona="X")
    AsignacionTrabajo.objects.create(orden=o, profile=de, rol="tecnico", es_principal=True)
    return o


def test_s_la_regla_de_los_30_minutos_queda_pausada_mientras_dura(org, version, user_profile):
    from campo.services import salud_seguimiento as SS

    j = _jornada(org, user_profile)
    o = _orden(org, version, user_profile)
    EventoTrabajo.objects.filter(orden=o).update(created_at=timezone.now() - dt.timedelta(hours=2))
    OrdenTrabajo.objects.filter(pk=o.pk).update(iniciada_en=timezone.now() - dt.timedelta(hours=2))
    o.refresh_from_db()
    antes = SS.calcular(o)["tipo"]

    _novedad(org, user_profile, N.UNA_HORA, jornada=j)

    assert antes != SS.PAUSADO_NOVEDAD
    assert SS.calcular(o)["tipo"] == SS.PAUSADO_NOVEDAD


# ---------------------------------------------------------------------------
# P · Programacion: tiempos, resumen, novedades y log
# ---------------------------------------------------------------------------

def _paso(o, estado, cuando):
    ev = EventoTrabajo.objects.create(org=o.org, orden=o, tipo="transicion",
                                      datos={"nuevo_estado": estado})
    EventoTrabajo.objects.filter(pk=ev.pk).update(created_at=cuando)


def test_p_programacion_dice_cuanto_lleva_cada_orden_y_el_dia_de_la_cuadrilla(
        org, version, user_profile):
    j = _jornada(org, user_profile)
    base = timezone.now().astimezone(BOGOTA).replace(hour=8, minute=0, second=0, microsecond=0)
    hecha = _orden(org, version, user_profile, estado=OrdenTrabajo.COMPLETADA_CAMPO)
    _paso(hecha, "en_camino", base)
    _paso(hecha, "en_sitio", base + dt.timedelta(minutes=23))
    _paso(hecha, "completada_campo", base + dt.timedelta(minutes=63))
    #  Una terminada entra en el dia por la hora en que se termino.
    OrdenTrabajo.objects.filter(pk=hecha.pk).update(
        completada_campo_en=base + dt.timedelta(minutes=63))
    ahora_en = _orden(org, version, user_profile, estado=OrdenTrabajo.EN_SITIO)
    _paso(ahora_en, "en_camino", base + dt.timedelta(minutes=70))
    _paso(ahora_en, "en_sitio", base + dt.timedelta(minutes=80))
    #  ENTRE dos pasos del tecnico: el log tiene que ordenarla por hora.
    _novedad(org, user_profile, N.MEDIA_HORA, jornada=j,
             hace=timezone.now() - (base + dt.timedelta(minutes=30)))

    c = D.del_dia(org, _hoy())["cuadrillas"][0]

    filas = {f["numero"]: f for f in c["ordenes"]}
    assert (filas[hecha.numero]["tiempos"]["traslado_min"],
            filas[hecha.numero]["tiempos"]["en_sitio_min"]) == (23, 40)
    r = c["resumen_del_dia"]
    assert (r["salio"], r["hechas"], r["total"]) == ("08:00", 1, 2)
    assert (r["en_curso"]["numero"], r["en_curso"]["estado"]) == (ahora_en.numero, "en_sitio")
    assert c["novedades"][0]["tipo"] == "llanta"
    textos = [e["texto"] for e in c["log"]]
    assert f"Llegó a OT #{hecha.numero} (23 min de camino)" in textos
    assert f"Terminó OT #{hecha.numero} (40 min en sitio)" in textos
    assert any(t.startswith("Avisó novedad: se pinchó una llanta") for t in textos)
    horas = [e["hora"] for e in c["log"]]
    assert horas == sorted(horas), "el log va en orden de hora"
