"""
================================================================================
 DONDE ESTA CADA CUADRILLA  --  31/10/2026
================================================================================
`campo/ubicacion_de_cuadrilla.py` y `POST /api/campo/ubicacion/`. Cada punto,
con su prueba:

  J  LA JORNADA MANDA, Y EN CODIGO: la posicion de quien NO sale hoy no se
     guarda. Es la garantia de "solo durante la jornada": si viviera solo en el
     telefono, una version vieja seguiria mandando a las once de la noche.
  H  Y EL HORARIO, NO SOLO LA FECHA (revisor de PII, 31/10/2026): con jornada
     de hoy pero a las 22:00, la posicion es la CASA del tecnico. Sin horario
     de cuadrillas cargado no se guarda nada.
  B  lo viejo se BORRA, y lo hace el ciclo que ya corre.
  U  UNA SOLA FILA por persona: la ultima pisa a la anterior. NO hay recorrido.
  V  lo que llega se VALIDA: sin coordenada no se guarda; la bateria ilegible
     no cuesta la posicion; una medicion del futuro se recorta.
  L  la LECTURA dice la edad: lo viejo se muestra como viejo, nunca como ahora.
  P  solo el dueño de la cuenta escribe la suya, y solo su empresa la lee.

    pytest campo/tests/test_ubicacion_de_cuadrilla.py
================================================================================
"""
import datetime as dt

import pytest
from django.utils import timezone

from campo import ubicacion_de_cuadrilla as U
from campo.cuadrillas import (
    Cuadrilla,
    IntegranteDeJornada,
    JornadaDeCuadrilla,
    PersonaDeCampo,
)

pytestmark = pytest.mark.django_db

RUTA = "/api/campo/ubicacion/"
#  Soledad, Atlantico: donde trabajan las cuadrillas de la prueba.
LAT, LON = 10.9185, -74.7668


@pytest.fixture
def hoy():
    from campo import reparto as R
    return timezone.now().astimezone(R._zona_de(None) if False else
                                     dt.timezone(dt.timedelta(hours=-5))).date()


#  Desde el 31/10/2026 no alcanza con la jornada: hace falta el HORARIO de
#  las cuadrillas de la empresa, porque la hora tambien manda.
def _horario(org, abre=dt.time(7, 0), cierra=dt.time(17, 0)):
    from business_hours.models import BusinessCalendar
    from campo.cuadrillas import ConfiguracionDeReparto

    cal = BusinessCalendar.objects.create(
        org=org, name="Cuadrillas", timezone="America/Bogota",
        **{f"{d}_open": abre for d in _COLUMNAS},
        **{f"{d}_close": cierra for d in _COLUMNAS})
    fila, _ = ConfiguracionDeReparto.objects.get_or_create(org=org)
    fila.calendario_de_cuadrillas = cal
    fila.save(update_fields=["calendario_de_cuadrillas"])
    return cal


_COLUMNAS = ("monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday")

#: Las 10 de la mañana de hoy en Bogota: dentro de cualquier horario normal.
def _en_horario(fecha):
    return dt.datetime.combine(fecha, dt.time(10, 0),
                               tzinfo=dt.timezone(dt.timedelta(hours=-5)))


def _jornada(org, profile, fecha, nombre="Cuadrilla #1"):
    c = Cuadrilla.objects.create(org=org, nombre=nombre)
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=c, fecha=fecha, labor=JornadaDeCuadrilla.INSTALACION)
    #  UNA PersonaDeCampo POR CUENTA (restriccion unica): una prueba que arma
    #  la jornada de ayer y la de hoy para la MISMA persona la pedia dos veces
    #  y reventaba. Lo destapo la regresion completa, no la corrida del
    #  archivo solo --y de paso mostro que la mutacion de H3 habia "muerto"
    #  por este error y no por lo que decia medir (31/10/2026)--.
    persona, _ = PersonaDeCampo.objects.get_or_create(
        org=org, profile=profile, defaults={"nombre": nombre})
    IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona,
                                       rol="tecnico")
    return j


# ---------------------------------------------------------------------------
# J · la jornada manda, y en codigo
# ---------------------------------------------------------------------------

def test_j_sin_jornada_de_hoy_la_posicion_NO_se_guarda(org_a, admin_profile, hoy):
    """La garantia de «solo durante la jornada» vive aca, no en el telefono."""
    _horario(org_a)
    with pytest.raises(U.FueraDeLaJornada) as e:
        U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                    medida_en=_en_horario(hoy), ahora=_en_horario(hoy))
    assert e.value.motivo == U.SIN_JORNADA

    assert U.PosicionDeTecnico.objects.count() == 0, "ni una fila"


def test_j2_con_jornada_de_hoy_si_se_guarda_y_queda_atada_a_ella(
        org_a, admin_profile, hoy):
    _horario(org_a)
    j = _jornada(org_a, admin_profile, hoy)

    fila = U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                       medida_en=_en_horario(hoy), ahora=_en_horario(hoy),
                       precision_m=8, bateria=72)

    assert (fila.latitud, fila.longitud) == (LAT, LON)
    assert (fila.precision_m, fila.bateria) == (8, 72)
    assert fila.jornada_id == j.id


def test_j3_la_jornada_de_AYER_no_habilita_la_de_hoy(org_a, admin_profile, hoy):
    """El dia de la jornada es el de hoy en la hora de la empresa, no
    «existe alguna jornada»."""
    _horario(org_a)
    _jornada(org_a, admin_profile, hoy - dt.timedelta(days=1))

    with pytest.raises(U.FueraDeLaJornada) as e:
        U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                    medida_en=_en_horario(hoy), ahora=_en_horario(hoy))
    assert e.value.motivo == U.SIN_JORNADA


# ---------------------------------------------------------------------------
# U · una sola fila: la ultima. No hay recorrido
# ---------------------------------------------------------------------------

def test_u_la_posicion_nueva_pisa_a_la_anterior_y_no_deja_rastro(
        org_a, admin_profile, hoy):
    """DECISION (31/10/2026): se guarda DONDE ESTA, no por donde anduvo. Un
    rastro permanente de un empleado es otro dato y otra decision."""
    _horario(org_a)
    _jornada(org_a, admin_profile, hoy)
    ahora = _en_horario(hoy)

    U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                medida_en=ahora - dt.timedelta(minutes=10), ahora=ahora)
    U.registrar(org_a, admin_profile, latitud=LAT + 0.01, longitud=LON + 0.01,
                medida_en=ahora, ahora=ahora)

    filas = U.PosicionDeTecnico.objects.filter(profile=admin_profile)
    assert filas.count() == 1, "UNA fila por persona: no se acumula el recorrido"
    assert filas.first().latitud == pytest.approx(LAT + 0.01)


# ---------------------------------------------------------------------------
# V · lo que llega se valida
# ---------------------------------------------------------------------------

def test_v_una_medicion_del_futuro_se_recorta_a_ahora(org_a, admin_profile, hoy):
    """Un reloj mal puesto dejaria una posicion con minutos NEGATIVOS, que
    parece eternamente fresca."""
    _horario(org_a)
    _jornada(org_a, admin_profile, hoy)
    ahora = _en_horario(hoy)

    fila = U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                       medida_en=ahora + dt.timedelta(hours=3), ahora=ahora)

    assert fila.medida_en == ahora
    assert fila.minutos(ahora) == 0


@pytest.mark.parametrize("cuerpo,guardada", [
    ({"latitud": LAT, "longitud": LON}, True),
    ({"latitud": LAT}, False),
    ({"latitud": "no soy un numero", "longitud": LON}, False),
    ({"latitud": 95.0, "longitud": LON}, False),
    ({"latitud": LAT, "longitud": 200.0}, False),
])
def test_v2_sin_una_coordenada_valida_no_se_guarda(
        org_a, admin_profile, admin_client, hoy, cuerpo, guardada):
    _horario(org_a, abre=dt.time(0, 1), cierra=dt.time(23, 58))
    _jornada(org_a, admin_profile, hoy)

    r = admin_client.post(RUTA, cuerpo, content_type="application/json")

    assert (r.status_code == 200) is guardada, r.content
    assert U.PosicionDeTecnico.objects.exists() is guardada


def test_v3_una_bateria_ilegible_no_cuesta_la_posicion(
        org_a, admin_profile, admin_client, hoy):
    """Que el telefono no sepa su bateria es informacion de menos, no un
    motivo para perder donde esta la cuadrilla."""
    _horario(org_a, abre=dt.time(0, 1), cierra=dt.time(23, 58))
    _jornada(org_a, admin_profile, hoy)

    r = admin_client.post(RUTA, {"latitud": LAT, "longitud": LON,
                                 "bateria": "ni idea", "precision_m": None},
                          content_type="application/json")

    assert r.status_code == 200 and r.json()["guardada"] is True
    fila = U.PosicionDeTecnico.objects.get()
    assert fila.bateria is None and fila.precision_m is None


def test_v4_fuera_de_jornada_responde_200_y_no_guarda(
        org_a, admin_profile, admin_client):
    """200 con `guardada: false`, no un 4xx: para la aplicacion no es una
    falla, y un error la haria reintentar en un bucle."""
    r = admin_client.post(RUTA, {"latitud": LAT, "longitud": LON},
                          content_type="application/json")

    assert r.status_code == 200
    assert r.json() == {"guardada": False, "motivo": U.SIN_JORNADA}
    assert U.PosicionDeTecnico.objects.count() == 0


# ---------------------------------------------------------------------------
# L · la lectura dice la edad
# ---------------------------------------------------------------------------

def test_l_lo_viejo_se_lee_como_viejo_y_no_como_ahora(org_a, admin_profile, hoy):
    """«Nunca mostrar una ubicacion antigua como si fuera actual» (el pedido)."""
    _horario(org_a)
    _jornada(org_a, admin_profile, hoy)
    ahora = _en_horario(hoy)
    U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                medida_en=ahora - dt.timedelta(minutes=45), ahora=ahora)

    leido = U.de_las_cuadrillas(org_a, hoy, ahora=ahora)[str(admin_profile.id)]

    assert leido["minutos"] == 45
    assert leido["fresca"] is False, "45 min no es donde esta: es donde estuvo"


def test_l2_lo_reciente_es_fresco_y_dice_si_la_precision_es_pobre(
        org_a, admin_profile, hoy):
    _horario(org_a)
    _jornada(org_a, admin_profile, hoy)
    ahora = _en_horario(hoy)
    U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON, precision_m=350,
                medida_en=ahora - dt.timedelta(minutes=2), ahora=ahora)

    leido = U.de_las_cuadrillas(org_a, hoy, ahora=ahora)[str(admin_profile.id)]

    assert leido["fresca"] is True and leido["minutos"] == 2
    assert leido["precision_pobre"] is True, "350 m es el barrio, no la casa"


def test_l3_sin_nadie_que_salga_la_lectura_es_vacia_y_no_revienta(org_a, hoy):
    assert U.de_las_cuadrillas(org_a, hoy) == {}


def test_l4_pedir_una_fecha_PASADA_no_devuelve_la_posicion_de_ahora(
        org_a, admin_profile, hoy):
    """EL HALLAZGO H3 (revisor de PII, 31/10/2026): la lectura usaba `fecha`
    solo para armar a quien preguntar, y despues traia la ULTIMA fila de cada
    uno. Pedir el mapa del 25 devolvia la posicion de ESTE minuto rotulada
    bajo aquella fecha: una vista que parece historial sin serlo, y la
    posicion en vivo servida por un camino que nadie leyo como «en vivo».

    Coherente con no guardar recorrido: una fecha pasada no muestra nada."""
    ayer = hoy - dt.timedelta(days=1)
    _horario(org_a)
    _jornada(org_a, admin_profile, ayer, nombre="Cuadrilla de ayer")
    _jornada(org_a, admin_profile, hoy)
    ahora = _en_horario(hoy)
    U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                medida_en=ahora, ahora=ahora)

    assert U.de_las_cuadrillas(org_a, hoy, ahora=ahora), "hoy si se ve"
    assert U.de_las_cuadrillas(org_a, ayer, ahora=ahora) == {}, \
        "ayer no muestra donde esta la cuadrilla AHORA"


# ---------------------------------------------------------------------------
# P · cada quien la suya, cada empresa la suya
# ---------------------------------------------------------------------------

def test_p_la_posicion_se_guarda_para_QUIEN_PIDE_no_para_quien_diga_el_cuerpo(
        org_a, admin_profile, user_profile, admin_client, hoy):
    """Mandar `profile` en el cuerpo no puede mover a otra persona en el mapa."""
    _horario(org_a, abre=dt.time(0, 1), cierra=dt.time(23, 58))
    _jornada(org_a, admin_profile, hoy)
    _jornada(org_a, user_profile, hoy, nombre="Cuadrilla #2")

    admin_client.post(RUTA, {"latitud": LAT, "longitud": LON,
                             "profile": str(user_profile.id)},
                      content_type="application/json")

    assert U.PosicionDeTecnico.objects.get().profile_id == admin_profile.id


def test_p2_una_empresa_no_lee_la_posicion_de_la_otra(
        org_a, org_b, admin_profile, user_profile, hoy):
    _horario(org_a)
    _jornada(org_a, admin_profile, hoy)
    U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                medida_en=_en_horario(hoy), ahora=_en_horario(hoy))

    assert U.de_las_cuadrillas(org_b, hoy) == {}


def test_p2b_una_fila_con_OTRA_empresa_no_se_sirve_aunque_la_persona_salga(
        org_a, org_b, user_profile, hoy):
    """LA SEGUNDA BARRERA, atacada de frente (31/10/2026).

    La lectura filtra por empresa Y por quien sale hoy. El filtro de personas
    tapa al de empresa en el camino normal --sin jornadas no hay a quien
    preguntar-- asi que quitar `org=org` sobrevivia a todas las pruebas. Aca se
    fuerza la unica forma de llegar: una fila cuya empresa NO es la que lee.

    Que devuelva nada es lo correcto: una fila con la empresa cambiada es un
    dato inconsistente, y ante eso se sirve CERO, no todo (CLAUDE.md §5)."""
    j = _jornada(org_b, user_profile, hoy)
    U.PosicionDeTecnico.objects.create(
        org=org_a, profile=user_profile, latitud=LAT, longitud=LON,
        medida_en=timezone.now(), jornada=j)

    assert U.de_las_cuadrillas(org_b, hoy) == {}, "la empresa tambien filtra"


def test_p3_sin_cuenta_no_se_escribe_una_posicion(client, org_a):
    r = client.post(RUTA, {"latitud": LAT, "longitud": LON},
                    content_type="application/json")

    assert r.status_code in (401, 403), r.status_code
    assert U.PosicionDeTecnico.objects.count() == 0


# ---------------------------------------------------------------------------
# H · el horario tambien manda, no solo la fecha
# ---------------------------------------------------------------------------

def test_h0_el_dia_se_mide_con_el_reloj_de_las_cuadrillas_no_con_UTC(
        org_a, admin_profile, hoy):
    """`Org.timezone` trae «UTC» por omision. A las 22:00 de Bogota el servidor
    ya esta en MAÑANA, y el dia de la jornada salia distinto del dia del
    horario: la posicion se rechazaba por el motivo equivocado, que es la
    forma mas facil de perseguir el error que no es."""
    _horario(org_a, abre=dt.time(7, 0), cierra=dt.time(23, 59))
    _jornada(org_a, admin_profile, hoy)
    noche = dt.datetime.combine(hoy, dt.time(22, 0),
                                tzinfo=dt.timezone(dt.timedelta(hours=-5)))

    fila = U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                       medida_en=noche, ahora=noche)

    assert fila.pk is not None, "la jornada es la de HOY en Bogota, no la de mañana en UTC"


def test_h_con_jornada_de_hoy_pero_a_las_22_NO_se_guarda(org_a, admin_profile, hoy):
    """EL HALLAZGO (revisor de PII, 31/10/2026). Mirar la FECHA no es mirar la
    jornada: a las 22:00 el telefono del tecnico esta en su CASA, y el modulo
    ponia justamente eso como el contraejemplo que no debia pasar."""
    _horario(org_a, abre=dt.time(7, 0), cierra=dt.time(17, 0))
    _jornada(org_a, admin_profile, hoy)
    noche = dt.datetime.combine(hoy, dt.time(22, 0),
                                tzinfo=dt.timezone(dt.timedelta(hours=-5)))

    with pytest.raises(U.FueraDeLaJornada) as e:
        U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                    medida_en=noche, ahora=noche)

    assert e.value.motivo == U.FUERA_DE_HORARIO
    assert U.PosicionDeTecnico.objects.count() == 0, "ni una fila de la casa"


def test_h2_el_turno_que_se_estira_una_hora_SI_se_guarda(org_a, admin_profile, hoy):
    """El margen existe a proposito: un tecnico que desaparece del mapa justo
    cuando se le hizo tarde es peor que inutil."""
    _horario(org_a, abre=dt.time(7, 0), cierra=dt.time(17, 0))
    _jornada(org_a, admin_profile, hoy)
    tarde = dt.datetime.combine(hoy, dt.time(17, 40),
                                tzinfo=dt.timezone(dt.timedelta(hours=-5)))

    fila = U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                       medida_en=tarde, ahora=tarde)

    assert fila.pk is not None, "40 min pasado el cierre todavia es el turno"


def test_h3_sin_horario_de_cuadrillas_cargado_no_se_guarda_nada(
        org_a, admin_profile, hoy):
    """Falla CERRADO: la empresa que no declaro cuando trabaja su gente
    tampoco declaro cuando NO, y ante eso no se rastrea."""
    _jornada(org_a, admin_profile, hoy)          # jornada si, horario no

    with pytest.raises(U.FueraDeLaJornada) as e:
        U.registrar(org_a, admin_profile, latitud=LAT, longitud=LON,
                    medida_en=_en_horario(hoy), ahora=_en_horario(hoy))

    assert e.value.motivo == U.SIN_HORARIO
    assert U.PosicionDeTecnico.objects.count() == 0


def test_h4_una_fecha_imposible_no_tumba_la_peticion(
        org_a, admin_profile, admin_client, hoy):
    """`parse_datetime` LEVANTA con una fecha bien formada pero imposible. Sin
    atraparla era un 500: la app reintentaba en bucle y, con DEBUG encendido,
    Django devolvia la coordenada en el cuerpo del error."""
    _horario(org_a, abre=dt.time(0, 1), cierra=dt.time(23, 58))
    _jornada(org_a, admin_profile, hoy)

    r = admin_client.post(RUTA, {"latitud": LAT, "longitud": LON,
                                 "medida_en": "2026-02-31T10:00:00"},
                          content_type="application/json")

    assert r.status_code == 200, r.content
    assert r.json()["guardada"] is True


# ---------------------------------------------------------------------------
# B · lo viejo se borra, y lo borra el ciclo que ya corre
# ---------------------------------------------------------------------------

def test_b_lo_mas_viejo_que_la_retencion_se_borra(org_a, admin_profile, hoy):
    """Sin esto, la ultima posicion de quien renuncio seguia en la tabla --y en
    cada respaldo-- el año siguiente, sin que nada la señalara."""
    _horario(org_a)
    j = _jornada(org_a, admin_profile, hoy)
    ahora = timezone.now()
    vieja = U.PosicionDeTecnico.objects.create(
        org=org_a, profile=admin_profile, latitud=LAT, longitud=LON,
        medida_en=ahora - dt.timedelta(days=U.DIAS_QUE_SE_CONSERVA + 1), jornada=j)

    assert U.purgar(org_a, ahora=ahora) == 1
    assert not U.PosicionDeTecnico.objects.filter(pk=vieja.pk).exists()


def test_b2_la_de_hoy_no_se_borra(org_a, admin_profile, hoy):
    _horario(org_a)
    j = _jornada(org_a, admin_profile, hoy)
    U.PosicionDeTecnico.objects.create(
        org=org_a, profile=admin_profile, latitud=LAT, longitud=LON,
        medida_en=timezone.now(), jornada=j)

    assert U.purgar(org_a) == 0
    assert U.PosicionDeTecnico.objects.count() == 1


def test_b3_el_ciclo_de_la_madrugada_LO_CORRE_de_verdad(org_a, admin_profile, hoy):
    """CODIGO CONSTRUIDO NO ES CODIGO QUE CORRE (CLAUDE.md §6). Un barrido sin
    llamador no borra nada y no da error: se comprueba que la tarea que YA
    recorre las empresas lo ejecute, no que la funcion exista."""
    from campo import tasks

    _horario(org_a)
    j = _jornada(org_a, admin_profile, hoy)
    vieja = U.PosicionDeTecnico.objects.create(
        org=org_a, profile=admin_profile, latitud=LAT, longitud=LON,
        medida_en=timezone.now() - dt.timedelta(days=30), jornada=j)

    salida = tasks.ciclo_de_la_madrugada()

    assert salida["posiciones_borradas"] >= 1
    assert not U.PosicionDeTecnico.objects.filter(pk=vieja.pk).exists()


# ---------------------------------------------------------------------------
# A · el anonimizador no miente
# ---------------------------------------------------------------------------

def test_a_anonimizar_campo_BORRA_las_posiciones(org_a, admin_profile, hoy):
    """El comando decia por escrito que reemplazaba «coordenadas» y dejaba esta
    tabla intacta: una copia de produccion en un portatil conservaba el GPS
    real de cada empleado (revisor de PII, 31/10/2026)."""
    from unittest import mock

    from django.core.management import call_command

    from campo.management.commands.anonimizar_campo import Command

    _horario(org_a)
    j = _jornada(org_a, admin_profile, hoy)
    U.PosicionDeTecnico.objects.create(
        org=org_a, profile=admin_profile, latitud=LAT, longitud=LON,
        medida_en=timezone.now(), jornada=j)

    #  La guarda de base local es correcta y no se toca: la base de pruebas
    #  vive en el compose, no en localhost. Se saltea SOLO esa comprobacion,
    #  para que lo que se mida sea que `handle` borra las posiciones.
    with mock.patch.object(Command, "_exigir_base_local"):
        call_command("anonimizar_campo", "--si-estoy-seguro")

    assert U.PosicionDeTecnico.objects.count() == 0, "no queda donde estuvo nadie"
