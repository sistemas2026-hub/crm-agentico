"""
================================================================================
 EL SUPERVISOR PUBLICA EL REPARTO DEL DIA  --  27/10/2026
================================================================================
Fase 3.1 de SPEC/objetivos/supervisor-arma-la-jornada.md
(`operaciones/publicacion_del_reparto.py`). Cada punto, con su prueba:

  P  las puertas: sin la tarea delegada, sin el nivel 3, con el interruptor
     apagado o ilegible, o sin poder leer la tarea, la sombra.
  V  la ventana: en un dia que las cuadrillas trabajan, desde dos horas antes
     de la apertura hasta el cierre, con una zona horaria que se puede leer.
  Q  lo que tiene a alguien que hoy trabaja NO se mueve nunca, ni antes de la
     apertura (auditorias de frontera e independiente del 27/10).
  L  lo que tiene a alguien que hoy NO trabaja se libera: si no, queda en el
     telefono de quien no sale y le ocupa el cupo a quien si.
  T  el tope es la carga del dia, no la de la vuelta.
  N  una cuadrilla sin nadie que reciba, o con alguien ausente, no entra.
  R  publica de verdad: la asignacion, el evento sin persona, el aviso.
  S  la sombra cuenta solo lo que cambiaria de manos.
  K  corre dentro de `correr_ciclo`, con la hora real al publicar, y el log
     no lleva clientes.

    pytest operaciones/tests/test_el_supervisor_publica_el_reparto.py
================================================================================
"""
import datetime as dt
import logging
import zoneinfo
from unittest import mock

import pytest

from campo.avisos import DispositivoDeTecnico
from campo.cuadrillas import (
    ConfiguracionDeReparto,
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
from campo.services import push_fcm
from campo.zonas import AliasDeZona, ZonaOperativa
from common.models import Profile
from operaciones import publicacion_del_reparto as PR
from operaciones import tareas_delegadas as td

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")
MARTES = dt.date(2026, 10, 27)
SABADO = dt.date(2026, 10, 31)
BARRIO = "SOLEDAD CENTRO"
CLIENTE = "Zoraida Clientela"


def _a_las(hora, minuto=0, dia=MARTES):
    return dt.datetime.combine(dia, dt.time(hora, minuto), tzinfo=BOGOTA)


@pytest.fixture
def empresa(org_a):
    """Bogota; las cuadrillas trabajan de lunes a viernes, de 07:00 a 17:00."""
    from business_hours.models import BusinessCalendar

    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    cal = BusinessCalendar.objects.create(org=org_a, name="Cuadrillas",
                                          timezone="America/Bogota")
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        setattr(cal, f"{d}_open", dt.time(7, 0))
        setattr(cal, f"{d}_close", dt.time(17, 0))
    cal.save()
    ConfiguracionDeReparto.objects.update_or_create(
        org=org_a, defaults={"calendario_de_cuadrillas": cal})
    return org_a


@pytest.fixture
def version(empresa):
    wt = WorkType.objects.create(org=empresa, codigo="ftth", nombre="FTTH",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})


@pytest.fixture
def soledad(empresa):
    z = ZonaOperativa.objects.create(org=empresa, nombre="SOLEDAD")
    AliasDeZona.objects.create(org=empresa, zona=z, localidad=BARRIO)
    return z


def _jornada(org, zona, nombre, *profiles, telefono=True):
    c = Cuadrilla.objects.create(org=org, nombre=nombre)
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=c, fecha=MARTES, labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set([zona])
    for i, profile in enumerate(profiles):
        persona = PersonaDeCampo.objects.create(
            org=org, profile=profile, nombre=f"{nombre} {i}")
        IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona,
                                           rol="tecnico")
        if telefono:
            DispositivoDeTecnico.objects.create(
                org=org, profile=profile, token=f"tok-{profile.id}",
                plataforma="android", activo=True)
    return j


@pytest.fixture
def jornada(empresa, soledad, admin_profile):
    """La cuadrilla del martes: cubre SOLEDAD, instalacion, una persona con
    cuenta y su telefono."""
    return _jornada(empresa, soledad, "Cuadrilla #1", admin_profile)


@pytest.fixture
def otro(empresa, django_user_model):
    user = django_user_model.objects.create_user(
        email="otro.reparto@test.com", password="testpass123")
    return Profile.objects.create(user=user, org=empresa, role="USER",
                                  is_active=True)


@pytest.fixture
def abierto(empresa, admin_profile, monkeypatch):
    """Las puertas abiertas, por el camino real salvo el interruptor del motor,
    que en la base de pruebas no existe."""
    from operaciones import autonomia

    td.delegar(empresa, td.PUBLICAR_EL_REPARTO, actor=admin_profile,
               pedido_textual="publicá el reparto del día")
    autonomia.cambiar(empresa, 3, actor=admin_profile,
                      motivo="publicar el reparto", criterios="simular el dia")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))
    return empresa


@pytest.fixture
def fcm():
    enviados = []

    def mandar(token, titulo, texto, enlace, *, aviso_id="", verbo="",
               contenido=None):
        enviados.append({"token": token, "texto": texto, "verbo": verbo})
        return push_fcm.ENTREGADO

    with mock.patch.object(push_fcm, "esta_configurado", return_value=True), \
            mock.patch.object(push_fcm, "mandar_a_un_telefono", side_effect=mandar):
        yield enviados


_numero = iter(range(900, 9999))


def _orden(org, version, *, de=None, estado=OrdenTrabajo.ASIGNADA):
    o = OrdenTrabajo.objects.create(
        org=org, numero=next(_numero), tipo_trabajo_version=version,
        estado_operativo=estado, zona=BARRIO,
        prioridad=OrdenTrabajo.PRIORIDAD_MEDIA, cliente_nombre=CLIENTE)
    if de is not None:
        AsignacionTrabajo.objects.create(orden=o, profile=de, rol="tecnico",
                                         es_principal=True)
    return o


def _correr(org, ahora, capturar):
    with capturar(execute=True):
        return PR.publicar_el_reparto(org, ahora)["reparto_del_dia"]


def _de_quien(orden):
    return [a.profile_id for a in orden.asignaciones.all()]


def _ausente(org, profile):
    from operaciones.models import DisponibilidadTecnico
    DisponibilidadTecnico.objects.create(
        org=org, profile=profile, fecha=MARTES, hora_inicio=dt.time(7, 0),
        hora_fin=dt.time(17, 0), disponible=False, motivo="cita medica")


# ---------------------------------------------------------------------------
# P · las puertas
# ---------------------------------------------------------------------------

def test_p_sin_la_tarea_queda_en_sombra_y_no_escribe(
        empresa, version, jornada, fcm, django_capture_on_commit_callbacks):
    o = _orden(empresa, version)

    r = _correr(empresa, _a_las(6), django_capture_on_commit_callbacks)

    assert (r["modo"], r["publicaria"], r["publicadas"]) == (PR.SOMBRA, 1, 0)
    assert "delegó" in r["porque"]
    assert _de_quien(o) == [] and fcm == []


def test_p2_sin_el_nivel_tampoco(
        empresa, version, jornada, admin_profile, fcm, monkeypatch,
        django_capture_on_commit_callbacks):
    td.delegar(empresa, td.PUBLICAR_EL_REPARTO, actor=admin_profile)
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))
    o = _orden(empresa, version)

    r = _correr(empresa, _a_las(6), django_capture_on_commit_callbacks)

    assert (r["modo"], r["publicadas"]) == (PR.SOMBRA, 0)
    assert _de_quien(o) == [] and fcm == []


def test_p3_crear_las_ordenes_no_habilita_publicarlas(
        empresa, version, jornada, admin_profile, monkeypatch,
        django_capture_on_commit_callbacks):
    from operaciones import autonomia

    td.delegar(empresa, td.CREAR_LAS_ORDENES, actor=admin_profile)
    autonomia.cambiar(empresa, 3, actor=admin_profile, motivo="x", criterios="y")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))
    _orden(empresa, version)

    r = _correr(empresa, _a_las(6), django_capture_on_commit_callbacks)

    assert r["modo"] == PR.SOMBRA


def test_p4_el_interruptor_apagado_la_deja_en_sombra(
        abierto, version, jornada, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (False, "lo apago una persona"))
    o = _orden(abierto, version)

    r = _correr(abierto, _a_las(8), django_capture_on_commit_callbacks)

    assert (r["modo"], r["publicadas"]) == (PR.SOMBRA, 0)
    assert "lo apago" not in r["porque"]       # texto fijo, va a un log
    assert _de_quien(o) == []


def test_p5_el_interruptor_ilegible_tambien(
        abierto, version, jornada, monkeypatch, django_capture_on_commit_callbacks):
    def roto(org):
        raise ConnectionError("motor caido")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", roto)
    o = _orden(abierto, version)

    r = _correr(abierto, _a_las(8), django_capture_on_commit_callbacks)

    assert (r["modo"], r["publicadas"]) == (PR.SOMBRA, 0)
    assert _de_quien(o) == []


def test_p6_sin_poder_leer_la_tarea_tambien(
        abierto, version, jornada, monkeypatch, django_capture_on_commit_callbacks):
    def roto(org, tarea):
        raise RuntimeError("base caida")
    monkeypatch.setattr("operaciones.tareas_delegadas.esta_delegada", roto)
    o = _orden(abierto, version)

    r = _correr(abierto, _a_las(8), django_capture_on_commit_callbacks)

    assert (r["modo"], r["publicadas"]) == (PR.SOMBRA, 0)
    assert "RuntimeError" in r["porque"]
    assert _de_quien(o) == []


# ---------------------------------------------------------------------------
# V · la ventana
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hora, minuto, corre", [
    (4, 59, False),   # mas de dos horas antes de abrir
    (5, 0, True),     # dos horas antes
    (16, 59, True),
    (17, 0, False),   # cerro
])
def test_v_la_ventana(abierto, version, jornada, hora, minuto, corre,
                      django_capture_on_commit_callbacks):
    _orden(abierto, version)

    r = _correr(abierto, _a_las(hora, minuto), django_capture_on_commit_callbacks)

    assert (r["modo"] == PR.PUBLICO) is corre, r


def test_v2_un_dia_que_las_cuadrillas_no_trabajan_no_publica(
        abierto, version, jornada, django_capture_on_commit_callbacks):
    _orden(abierto, version)

    r = _correr(abierto, _a_las(8, dia=SABADO), django_capture_on_commit_callbacks)

    assert (r["modo"], r["publicadas"]) == (PR.NO_CORRIO, 0)
    assert "no trabajan" in r["porque"]


def test_v3_sin_horario_de_cuadrillas_no_publica(
        abierto, version, jornada, django_capture_on_commit_callbacks):
    ConfiguracionDeReparto.objects.filter(org=abierto).update(
        calendario_de_cuadrillas=None)
    _orden(abierto, version)

    r = _correr(abierto, _a_las(8), django_capture_on_commit_callbacks)

    assert r["modo"] == PR.NO_CORRIO


def test_v4_una_zona_horaria_que_no_se_puede_leer_no_publica(
        abierto, version, jornada, django_capture_on_commit_callbacks):
    from business_hours.models import BusinessCalendar
    BusinessCalendar.objects.filter(org=abierto).update(timezone="Marte/Olympus")
    o = _orden(abierto, version)

    r = _correr(abierto, _a_las(8), django_capture_on_commit_callbacks)

    assert r["modo"] == PR.NO_CORRIO and "zona horaria" in r["porque"]
    assert _de_quien(o) == []


# ---------------------------------------------------------------------------
# Q · lo que tiene a alguien que hoy trabaja no se mueve
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hora", [5, 9])
def test_q_lo_de_alguien_que_hoy_trabaja_no_se_mueve_ni_antes_de_abrir(
        abierto, version, soledad, jornada, otro, hora,
        django_capture_on_commit_callbacks):
    """`otro` sale hoy con la #2 en la misma zona y tiene tres ordenes; la #1
    no tiene ninguna. Reacomodarlas «para balancear» es lo que mandaba avisos
    contradictorios y deshacia lo que decidio una persona."""
    _jornada(abierto, soledad, "Cuadrilla #2", otro)
    suyas = [_orden(abierto, version, de=otro) for _ in range(3)]

    r = _correr(abierto, _a_las(hora), django_capture_on_commit_callbacks)

    assert (r["publicaria"], r["publicadas"], r["liberadas"]) == (0, 0, 0)
    assert all(_de_quien(o) == [otro.id] for o in suyas)


# ---------------------------------------------------------------------------
# L · lo trabado con alguien que hoy no trabaja se libera
# ---------------------------------------------------------------------------

def test_l_lo_de_alguien_que_hoy_no_sale_se_libera_aunque_ya_abrio(
        abierto, version, jornada, admin_profile, otro, fcm,
        django_capture_on_commit_callbacks):
    trabada = _orden(abierto, version, de=otro)      # otro no esta en ninguna jornada

    r = _correr(abierto, _a_las(10), django_capture_on_commit_callbacks)

    assert (r["libera"], r["publicadas"], r["liberadas"]) == (1, 1, 1)
    assert _de_quien(trabada) == [admin_profile.id]


def test_l2_la_cuadrilla_con_alguien_ausente_no_recibe_y_lo_suyo_se_libera(
        abierto, version, soledad, jornada, admin_profile, otro,
        django_capture_on_commit_callbacks):
    _jornada(abierto, soledad, "Cuadrilla #2", otro)
    _ausente(abierto, otro)
    trabada = _orden(abierto, version, de=otro)
    nueva = _orden(abierto, version)

    r = _correr(abierto, _a_las(10), django_capture_on_commit_callbacks)

    assert r["con_ausentes"] == 1
    assert _de_quien(trabada) == [admin_profile.id]
    assert _de_quien(nueva) == [admin_profile.id]


def test_l3_la_novedad_del_resto_del_dia_es_como_una_ausencia(
        abierto, version, soledad, jornada, admin_profile, otro,
        django_capture_on_commit_callbacks):
    """30/10/2026, novedad-de-cuadrilla.md: «se pincho la llanta, el resto del
    dia». Su jornada no recibe y lo suyo SIN EMPEZAR pasa a otra; lo empezado
    se queda con quien lo tiene."""
    from campo.novedades import RESTO_DEL_DIA, NovedadDeCuadrilla

    j2 = _jornada(abierto, soledad, "Cuadrilla #2", otro)
    NovedadDeCuadrilla.objects.create(
        org=abierto, jornada=j2, profile=otro, tipo="llanta", afecta=RESTO_DEL_DIA,
        fecha=MARTES, avisada_en=_a_las(9), clave="llanta-1")
    sin_empezar = _orden(abierto, version, de=otro)
    empezada = _orden(abierto, version, de=otro, estado=OrdenTrabajo.EN_SITIO)

    r = _correr(abierto, _a_las(10), django_capture_on_commit_callbacks)

    assert r["con_ausentes"] == 1
    assert _de_quien(sin_empezar) == [admin_profile.id]
    assert _de_quien(empezada) == [otro.id], "lo empezado no se mueve"


def test_l4_la_novedad_corta_no_mueve_nada(
        abierto, version, soledad, jornada, admin_profile, otro,
        django_capture_on_commit_callbacks):
    from campo.novedades import MEDIA_HORA, NovedadDeCuadrilla

    j2 = _jornada(abierto, soledad, "Cuadrilla #2", otro)
    NovedadDeCuadrilla.objects.create(
        org=abierto, jornada=j2, profile=otro, tipo="llanta", afecta=MEDIA_HORA,
        fecha=MARTES, avisada_en=_a_las(9, 50), clave="llanta-2")
    suya = _orden(abierto, version, de=otro)

    r = _correr(abierto, _a_las(10), django_capture_on_commit_callbacks)

    assert r["con_ausentes"] == 0
    assert _de_quien(suya) == [otro.id]


# ---------------------------------------------------------------------------
# T · el tope es la carga del dia
# ---------------------------------------------------------------------------

def test_t_lo_que_entra_despues_no_pasa_el_tope(
        abierto, version, jornada, admin_profile, django_capture_on_commit_callbacks):
    jornada.cuadrilla.tope_diario = 2
    jornada.cuadrilla.save(update_fields=["tope_diario"])
    [_orden(abierto, version) for _ in range(2)]
    _correr(abierto, _a_las(6), django_capture_on_commit_callbacks)
    urgente = _orden(abierto, version)
    OrdenTrabajo.objects.filter(pk=urgente.pk).update(
        prioridad=OrdenTrabajo.PRIORIDAD_ALTA)

    r = _correr(abierto, _a_las(8), django_capture_on_commit_callbacks)

    assert (r["publicadas"], r["sobrantes"]) == (0, 1)
    assert OrdenTrabajo.objects.filter(
        asignaciones__profile=admin_profile).count() == 2
    assert _de_quien(urgente) == []


def test_t2_lo_empezado_tambien_ocupa_el_cupo(
        abierto, version, jornada, admin_profile, django_capture_on_commit_callbacks):
    jornada.cuadrilla.tope_diario = 1
    jornada.cuadrilla.save(update_fields=["tope_diario"])
    _orden(abierto, version, de=admin_profile, estado=OrdenTrabajo.EN_CAMINO)
    nueva = _orden(abierto, version)

    r = _correr(abierto, _a_las(9), django_capture_on_commit_callbacks)

    assert (r["publicadas"], r["sobrantes"]) == (0, 1)
    assert _de_quien(nueva) == []


# ---------------------------------------------------------------------------
# N · una cuadrilla sin nadie que reciba no se lleva ordenes
# ---------------------------------------------------------------------------

def test_n_la_cuadrilla_sin_nadie_con_cuenta_no_le_quita_ordenes_a_la_otra(
        abierto, version, soledad, jornada, admin_profile,
        django_capture_on_commit_callbacks):
    c = Cuadrilla.objects.create(org=abierto, nombre="Cuadrilla #0")
    j = JornadaDeCuadrilla.objects.create(
        org=abierto, cuadrilla=c, fecha=MARTES, labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set([soledad])
    persona = PersonaDeCampo.objects.create(org=abierto, nombre="Auxiliar sin cuenta")
    IntegranteDeJornada.objects.create(org=abierto, jornada=j, persona=persona,
                                       rol="auxiliar")
    ordenes = [_orden(abierto, version) for _ in range(4)]

    r = _correr(abierto, _a_las(8), django_capture_on_commit_callbacks)

    assert (r["sin_nadie_con_cuenta"], r["publicadas"]) == (1, 4)
    assert all(_de_quien(o) == [admin_profile.id] for o in ordenes)


# ---------------------------------------------------------------------------
# R · publica de verdad
# ---------------------------------------------------------------------------

def test_r_publica_con_su_evento_y_su_aviso(
        abierto, version, jornada, admin_profile, fcm,
        django_capture_on_commit_callbacks):
    ordenes = [_orden(abierto, version) for _ in range(2)]

    r = _correr(abierto, _a_las(6), django_capture_on_commit_callbacks)

    assert (r["modo"], r["publicaria"], r["publicadas"]) == (PR.PUBLICO, 2, 2)
    for o in ordenes:
        assert _de_quien(o) == [admin_profile.id]
        ev = EventoTrabajo.objects.get(orden=o, tipo="asignada_por_el_supervisor")
        assert ev.profile_id is None
        assert (ev.datos["tarea"], ev.datos["fecha"]) == (
            td.PUBLICAR_EL_REPARTO, MARTES.isoformat())
    assert [(m["token"], m["texto"]) for m in fcm] == [
        (f"tok-{admin_profile.id}", "📋 Te asignaron 2 visitas para el martes 27/10")]


def test_r2_la_vuelta_siguiente_no_repite_ni_avisa_otra_vez(
        abierto, version, jornada, fcm, django_capture_on_commit_callbacks):
    _orden(abierto, version)
    _correr(abierto, _a_las(6), django_capture_on_commit_callbacks)
    fcm.clear()

    r = _correr(abierto, _a_las(7, 30), django_capture_on_commit_callbacks)

    assert (r["publicaria"], r["publicadas"], r["quietas"]) == (0, 0, 0)
    assert fcm == []


def test_r3_lo_que_el_tecnico_empezo_no_se_toca(
        abierto, version, jornada, otro, django_capture_on_commit_callbacks):
    empezada = _orden(abierto, version, de=otro)
    OrdenTrabajo.objects.filter(pk=empezada.pk).update(
        estado_operativo=OrdenTrabajo.EN_CAMINO, iniciada_en=_a_las(5, 30))

    r = _correr(abierto, _a_las(6), django_capture_on_commit_callbacks)

    assert r["publicadas"] == 0
    assert _de_quien(empezada) == [otro.id]


# ---------------------------------------------------------------------------
# S · la sombra cuenta lo que cambiaria de manos
# ---------------------------------------------------------------------------

def test_s_la_sombra_no_cuenta_lo_que_ya_esta_con_quien_trabaja(
        empresa, version, jornada, admin_profile, otro,
        django_capture_on_commit_callbacks):
    _orden(empresa, version, de=admin_profile)      # ya esta donde va
    _orden(empresa, version)                         # la asignaria
    _orden(empresa, version, de=otro)                # la liberaria

    r = _correr(empresa, _a_las(8), django_capture_on_commit_callbacks)

    assert (r["modo"], r["publicaria"], r["libera"]) == (PR.SOMBRA, 2, 1)


# ---------------------------------------------------------------------------
# K · el ciclo, la hora real y el log
# ---------------------------------------------------------------------------

def test_k_corre_dentro_de_correr_ciclo_en_sombra(empresa, version, jornada):
    from operaciones import supervisor as sup

    _orden(empresa, version)

    resumen = sup.correr_ciclo(empresa, _a_las(6))

    assert "publicacion del reparto del dia" not in [
        f["fase"] for f in resumen.get("fases_que_fallaron", [])]
    assert (resumen["reparto_del_dia"]["modo"],
            resumen["reparto_del_dia"]["publicaria"]) == (PR.SOMBRA, 1)


def test_k2_y_publica_de_verdad_dentro_del_ciclo(
        abierto, version, jornada, admin_profile, django_capture_on_commit_callbacks):
    from operaciones import supervisor as sup

    o = _orden(abierto, version)

    with django_capture_on_commit_callbacks(execute=True):
        resumen = sup.correr_ciclo(abierto, _a_las(8))

    assert (resumen["reparto_del_dia"]["modo"],
            resumen["reparto_del_dia"]["publicadas"]) == (PR.PUBLICO, 1)
    assert _de_quien(o) == [admin_profile.id]


def test_k3_sin_hora_pedida_publica_con_la_hora_real(empresa, version, jornada):
    """El ciclo le pasa la hora PEDIDA; sin ninguna, la fase toma la de su
    propio momento, no la de cuando arranco la vuelta."""
    from operaciones import supervisor as sup

    with mock.patch.object(PR, "publicar_el_reparto",
                           return_value={"reparto_del_dia": {}}) as fase:
        sup.correr_ciclo(empresa)
    assert fase.call_args.args[1] is None

    with mock.patch("operaciones.publicacion_del_reparto.timezone.now",
                    return_value=_a_las(3)):
        r = PR.publicar_el_reparto(empresa)["reparto_del_dia"]
    assert "temprano" in r["porque"]


def test_k4_el_log_no_lleva_el_cliente(
        abierto, version, jornada, caplog, django_capture_on_commit_callbacks):
    _orden(abierto, version)

    with caplog.at_level(logging.INFO):
        _correr(abierto, _a_las(6), django_capture_on_commit_callbacks)

    assert "reparto del dia" in caplog.text
    assert CLIENTE not in caplog.text and BARRIO not in caplog.text
