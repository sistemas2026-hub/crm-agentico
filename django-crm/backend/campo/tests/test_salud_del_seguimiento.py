# -*- coding: utf-8 -*-
"""¿Este trabajo esta reportando como deberia?

LA DISTINCION QUE DEFIENDE ESTE ARCHIVO
---------------------------------------
    VENCIDO        hay contacto reciente y NO reporto     -> eso si es un atraso
    SIN_CONTACTO   no se sabe si el telefono puede hablar -> no se acusa a nadie

Juntarlas en un solo rojo acusa al tecnico que esta dentro de una camara
subterranea haciendo bien su trabajo. La mitad de estas pruebas existen para que
nadie las vuelva a juntar, y varias afirman sobre el ORDEN de las preguntas, que es
donde vive esa diferencia: una orden puede llevar 56 minutos sin avance y el
dispositivo 40 sin aparecer, y ahi el veredicto tiene que ser "no lo se".

LO OTRO QUE SE DEFIENDE
-----------------------
  * el umbral exacto: 29:59 esta al dia, 30:00 esta vencido. Un off-by-one aca
    manda un tecnico a la bandeja roja un minuto antes;
  * la hora del TELEFONO no produce vencimientos, ni adelantada ni atrasada dos
    horas: la referencia es cuando el reporte LLEGO;
  * un AVANCE sin INICIO sirve como referencia -- la decision de la fase B no se
    reinterpreta aca;
  * un bloqueo que espera al NOC no vence nunca; uno que no lo espera si;
  * resolver un bloqueo abre una ventana NUEVA, no devuelve el reloj viejo;
  * nada de esto se guarda: es un calculo, no un tercer eje de estado.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from campo.bloqueos import BloqueoDeTrabajo
from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.seguimiento import ConfiguracionDeSeguimiento, ContactoDeDispositivo
from campo.services import bloqueos as serv_bloqueos
from campo.services import salud_seguimiento as salud
from campo.services import seguimiento_campo as seg
from common.models import Profile

pytestmark = pytest.mark.django_db


ESQUEMA = {
    "pasos": [], "campos": [], "evidencias": [],
    "seguimiento": {
        "bloqueo": {
            "campos": [
                {"id": "motivo", "titulo": "Motivo", "tipo": "texto",
                 "reglas": {"required": True}},
            ]
        }
    },
}


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tec.salud@test.com", password="testpass123"
    )
    return user, Profile.objects.create(
        user=user, org=org_a, role="USER", is_active=True
    )


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="salud", nombre="Trabajo")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA,
    )


def _orden(org, version, profile, numero=7001, estado=OrdenTrabajo.EN_SITIO):
    o = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzon", cliente_direccion="Calle 50",
        estado_operativo=estado, revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=profile, rol="tecnico", es_principal=True
    )
    return o


@pytest.fixture
def orden(org_a, version, tecnico):
    return _orden(org_a, version, tecnico[1])


def _evento(orden, profile, tipo, hace_minutos=0):
    """Un hecho en la bitacora, corrido hacia atras en el tiempo.

    `created_at` es `auto_now_add`, asi que se reescribe con `update`: con `save()`
    el auto_now_add lo volveria a pisar y la prueba mediria otra cosa.
    """
    e = EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo=tipo, profile=profile, datos={}
    )
    if hace_minutos:
        cuando = timezone.now() - timedelta(minutes=hace_minutos)
        EventoTrabajo.objects.filter(pk=e.pk).update(created_at=cuando)
        e.refresh_from_db()
    return e


def _contacto(profile, org, hace_minutos=0):
    fila, _ = ContactoDeDispositivo.objects.update_or_create(
        profile=profile,
        defaults={
            "org": org,
            "visto_en": timezone.now() - timedelta(minutes=hace_minutos),
        },
    )
    return fila


def _config(org, reportar=30, contacto=None):
    fila, _ = ConfiguracionDeSeguimiento.objects.update_or_create(
        org=org,
        defaults={
            "minutos_para_reportar": reportar,
            "minutos_contacto_reciente": contacto,
        },
    )
    return fila


# --------------------------------------------------------------------------- #
# A-D. El umbral exacto
# --------------------------------------------------------------------------- #

def test_a_a_los_29_59_todavia_esta_al_dia(orden, tecnico, org_a):
    """El off-by-one importa: un minuto antes manda a alguien a la bandeja roja."""
    _config(org_a, reportar=30)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(
        created_at=ahora - timedelta(minutes=29, seconds=59)
    )
    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.AL_DIA, r


def test_b_a_los_30_00_esta_vencido(orden, tecnico, org_a):
    _config(org_a, reportar=30)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=30))
    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.VENCIDO, r
    assert r["minutos_vencido"] == 0
    assert r["vence_en"]


def test_c_la_ventana_la_pone_la_empresa_no_el_codigo(orden, tecnico, org_a):
    """Otra empresa exige 45 minutos: a los 40 sigue al dia."""
    _config(org_a, reportar=45)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=40))
    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.AL_DIA
    assert r["minutos_para_reportar"] == 45


def test_d_sin_fila_de_configuracion_usa_los_30_de_fabrica(orden, tecnico, org_a):
    """Y no crea la fila al leer: una lectura que escribe no es una lectura."""
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=31))
    r = salud.calcular(orden, ahora=ahora)
    assert r["minutos_para_reportar"] == 30
    assert r["tipo"] == salud.VENCIDO
    assert not ConfiguracionDeSeguimiento.objects.filter(org=org_a).exists()


# --------------------------------------------------------------------------- #
# E-H. De donde se empieza a contar
# --------------------------------------------------------------------------- #

def test_e_un_avance_sin_inicio_sirve_como_referencia(orden, tecnico, org_a):
    """La decision de la fase B no se reinterpreta aca."""
    _config(org_a, reportar=30)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=10))
    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.AL_DIA
    assert r["tipo_de_referencia"] == "avance_campo"


def test_f_sin_ningun_reporte_cuenta_la_puesta_en_marcha(orden, tecnico, org_a):
    """Si nadie reporto nunca, el trabajo no puede quedar fuera del radar."""
    _config(org_a, reportar=30)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "accion_marcar_llegada")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=31))
    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.VENCIDO
    assert r["tipo_de_referencia"] == "accion_marcar_llegada"


def test_g_el_reloj_no_empieza_al_asignar(org_a, version, tecnico):
    """Una orden recien creada, sin puesta en marcha, no nace vencida."""
    _config(org_a, reportar=30)
    o = _orden(org_a, version, tecnico[1], numero=7002, estado=OrdenTrabajo.ASIGNADA)
    OrdenTrabajo.objects.filter(pk=o.pk).update(
        created_at=timezone.now() - timedelta(hours=5)
    )
    o.refresh_from_db()
    r = salud.calcular(o)
    assert r["tipo"] == salud.AL_DIA
    assert r["referencia"] is None
    assert "ningún hecho" in r["motivo"]


def test_h_el_hecho_mas_reciente_es_el_que_manda(orden, tecnico, org_a):
    _config(org_a, reportar=30)
    ahora = timezone.now()
    viejo = _evento(orden, tecnico[1], "inicio_campo")
    EventoTrabajo.objects.filter(pk=viejo.pk).update(created_at=ahora - timedelta(minutes=50))
    nuevo = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=nuevo.pk).update(created_at=ahora - timedelta(minutes=5))
    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.AL_DIA
    assert r["minutos_desde_la_referencia"] == 5


# --------------------------------------------------------------------------- #
# I-L. Los bloqueos
# --------------------------------------------------------------------------- #

def test_i_un_bloqueo_que_espera_al_noc_no_vence_nunca(orden, tecnico, org_a):
    """Cuatro horas detenido y sigue pausado: quien tiene que actuar ya lo sabe."""
    _config(org_a, reportar=30)
    bloqueo, _e, _d = serv_bloqueos.bloquear(
        orden, profile=tecnico[1], respuestas={"motivo": "sin acceso"},
        requiere_noc=True,
    )
    BloqueoDeTrabajo.objects.filter(pk=bloqueo.pk).update(
        abierto_en=timezone.now() - timedelta(hours=4)
    )
    orden.refresh_from_db()
    r = salud.calcular(orden)
    assert r["tipo"] == salud.PAUSADO_NOC, r
    assert r["minutos_vencido"] is None
    assert r["bloqueo"]["minutos_detenido"] >= 239


def test_j_un_bloqueo_que_no_es_del_noc_si_vence(org_a, version, tecnico):
    """Esperando al cliente: es una actualizacion valida, pero el reloj sigue."""
    _config(org_a, reportar=30, contacto=15)
    o = _orden(org_a, version, tecnico[1], numero=7003)
    _contacto(tecnico[1], org_a, hace_minutos=1)
    bloqueo, _evento_b, _d = serv_bloqueos.bloquear(
        o, profile=tecnico[1], respuestas={"motivo": "el cliente no esta"},
        requiere_noc=False,
    )
    ahora = timezone.now()
    EventoTrabajo.objects.filter(orden=o).update(created_at=ahora - timedelta(minutes=31))
    BloqueoDeTrabajo.objects.filter(pk=bloqueo.pk).update(
        abierto_en=ahora - timedelta(minutes=31)
    )
    o.refresh_from_db()
    r = salud.calcular(o, ahora=ahora)
    assert r["tipo"] == salud.VENCIDO, r


def test_k_resolver_un_bloqueo_abre_una_ventana_nueva(org_a, version, tecnico):
    """No se vuelve al reloj de antes: un trabajo destrabado no nace vencido."""
    _config(org_a, reportar=30)
    o = _orden(org_a, version, tecnico[1], numero=7004)
    bloqueo, _e, _d = serv_bloqueos.bloquear(
        o, profile=tecnico[1], respuestas={"motivo": "sin acceso"}, requiere_noc=True
    )
    ahora = timezone.now()
    BloqueoDeTrabajo.objects.filter(pk=bloqueo.pk).update(
        abierto_en=ahora - timedelta(hours=2)
    )
    EventoTrabajo.objects.filter(orden=o).update(created_at=ahora - timedelta(hours=2))
    bloqueo.refresh_from_db()
    serv_bloqueos.resolver(bloqueo, profile=tecnico[1], que_se_hizo="se gestiono")

    o.refresh_from_db()
    r = salud.calcular(o)
    assert r["tipo"] == salud.AL_DIA, r
    assert r["tipo_de_referencia"] in ("bloqueo_resuelto", "bloqueo_libero_el_trabajo")


def test_l_un_bloqueo_resuelto_hace_31_minutos_esta_vencido(org_a, version, tecnico):
    _config(org_a, reportar=30)
    o = _orden(org_a, version, tecnico[1], numero=7005)
    bloqueo, _e, _d = serv_bloqueos.bloquear(
        o, profile=tecnico[1], respuestas={"motivo": "sin acceso"}, requiere_noc=True
    )
    bloqueo.refresh_from_db()
    serv_bloqueos.resolver(bloqueo, profile=tecnico[1], que_se_hizo="se gestiono")
    ahora = timezone.now()
    EventoTrabajo.objects.filter(orden=o).update(created_at=ahora - timedelta(minutes=31))
    o.refresh_from_db()
    r = salud.calcular(o, ahora=ahora)
    assert r["tipo"] == salud.VENCIDO, r


# --------------------------------------------------------------------------- #
# M-N. La hora del telefono NO decide
# --------------------------------------------------------------------------- #

def test_m_un_avance_capturado_hace_50_min_y_recibido_ahora_esta_al_dia(
    orden, tecnico, org_a
):
    """Recupero señal y sincronizo: para la operacion, acaba de llegar algo."""
    _config(org_a, reportar=30)
    evento = seg.registrar(
        orden, profile=tecnico[1], momento=seg.AVANCE,
        respuestas={"nota": "lo escribi sin señal"},
        capturado_en_dispositivo=(timezone.now() - timedelta(minutes=50)).isoformat(),
    )
    r = salud.calcular(orden)
    assert r["tipo"] == salud.AL_DIA, r
    assert evento.datos["capturado_en_dispositivo"]
    assert evento.datos["recibido_en_servidor"]


@pytest.mark.parametrize("desfase_horas", [2, -2])
def test_n_un_reloj_mal_puesto_no_cambia_el_veredicto(
    orden, tecnico, org_a, desfase_horas
):
    """Adelantado o atrasado dos horas: da lo mismo."""
    _config(org_a, reportar=30)
    falso = (timezone.now() + timedelta(hours=desfase_horas)).isoformat()
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.AVANCE,
        respuestas={"nota": "con el reloj mal"},
        capturado_en_dispositivo=falso,
    )
    r = salud.calcular(orden)
    assert r["tipo"] == salud.AL_DIA, r


# --------------------------------------------------------------------------- #
# O-T. Sin contacto: lo que el sistema NO afirma
# --------------------------------------------------------------------------- #

def test_o_con_el_umbral_apagado_nunca_dice_sin_sincronizacion(orden, tecnico, org_a):
    """La condicion previa de esta fase, y la mas importante.

    Mientras la app no tenga latido regular, la ausencia de contacto no distingue
    "sin señal" de "app cerrada en el bolsillo". Con el umbral en nulo el sistema NO
    afirma nada sobre la sincronizacion: dice vencido o al dia, que es lo que si
    puede medir.
    """
    _config(org_a, reportar=30, contacto=None)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=45))
    assert not ContactoDeDispositivo.objects.filter(profile=tecnico[1]).exists()

    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.VENCIDO
    assert r["evalua_la_sincronizacion"] is False
    assert r["minutos_contacto_reciente"] is None


def test_p_con_el_umbral_encendido_y_sin_contacto_no_acusa_a_nadie(
    orden, tecnico, org_a
):
    """45 min sin reportar y 40 sin aparecer: el veredicto es "no lo se"."""
    _config(org_a, reportar=30, contacto=15)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=45))
    _contacto(tecnico[1], org_a, hace_minutos=40)

    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.SIN_CONTACTO, r
    assert r["minutos_vencido"] is None
    assert "No se está diciendo que el técnico no reportó" in r["motivo"]
    assert r["minutos_desde_la_referencia"] == 45


def test_q_con_contacto_reciente_y_sin_reportar_si_esta_vencido(orden, tecnico, org_a):
    """Ahi si: hay comunicacion y no reporto."""
    _config(org_a, reportar=30, contacto=15)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=37))
    _contacto(tecnico[1], org_a, hace_minutos=2)

    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.VENCIDO, r
    assert r["minutos_vencido"] == 7


def test_r_el_orden_importa_sin_contacto_gana_sobre_vencido(orden, tecnico, org_a):
    """Si se preguntara al reves, el veredicto seria una acusacion sin medicion."""
    _config(org_a, reportar=30, contacto=20)
    ahora = timezone.now()
    e = _evento(orden, tecnico[1], "avance_campo")
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=ahora - timedelta(minutes=56))
    _contacto(tecnico[1], org_a, hace_minutos=40)
    r = salud.calcular(orden, ahora=ahora)
    assert r["tipo"] == salud.SIN_CONTACTO
    assert r["minutos_desde_la_referencia"] == 56


def test_s_pausado_por_noc_gana_sobre_sin_contacto(org_a, version, tecnico):
    """El NOC ya sabe que esta detenido: eso manda sobre la sincronizacion."""
    _config(org_a, reportar=30, contacto=10)
    o = _orden(org_a, version, tecnico[1], numero=7006)
    serv_bloqueos.bloquear(
        o, profile=tecnico[1], respuestas={"motivo": "sin acceso"}, requiere_noc=True
    )
    _contacto(tecnico[1], org_a, hace_minutos=120)
    o.refresh_from_db()
    r = salud.calcular(o)
    assert r["tipo"] == salud.PAUSADO_NOC


def test_t_los_dos_umbrales_son_independientes(orden, tecnico, org_a):
    """30 y 15 no se mezclan: vienen de cosas que cambian por motivos distintos."""
    _config(org_a, reportar=30, contacto=15)
    r = salud.calcular(orden)
    assert r["minutos_para_reportar"] == 30
    assert r["minutos_contacto_reciente"] == 15


# --------------------------------------------------------------------------- #
# U-X. No aplica, y que nada se guarda
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "estado",
    [OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA],
)
def test_u_un_trabajo_terminado_no_aplica(org_a, version, tecnico, estado):
    _config(org_a, reportar=30)
    o = _orden(org_a, version, tecnico[1], numero=7010 + len(estado), estado=estado)
    _evento(o, tecnico[1], "avance_campo", hace_minutos=200)
    r = salud.calcular(o)
    assert r["tipo"] == salud.NO_APLICA
    assert r["minutos_vencido"] is None


def test_v_bloqueada_si_aplica():
    """Un trabajo detenido sigue en ejecucion: por eso se lo mira."""
    assert OrdenTrabajo.BLOQUEADA in salud.EN_EJECUCION


def test_w_nada_de_esto_se_guarda(orden):
    """Es un calculo, no un tercer eje de estado.

    La guarda: ninguna tabla de campo tiene una columna con el veredicto. Si alguien
    la agrega, esta prueba lo dice.
    """
    from django.apps import apps

    prohibidas = {"estado_seguimiento", "salud_seguimiento", "seguimiento_vencido"}
    encontradas = []
    for modelo in apps.get_app_config("campo").get_models():
        for campo in modelo._meta.get_fields():
            if getattr(campo, "name", "") in prohibidas:
                encontradas.append(f"{modelo.__name__}.{campo.name}")
    assert not encontradas, (
        "El veredicto de seguimiento se guardo en una columna: es derivado y "
        "guardarlo lo vuelve un dato que miente en cuanto nadie lo refresca. "
        + ", ".join(encontradas)
    )


def test_x_calcular_no_escribe_nada(orden, tecnico, org_a):
    """Ni la fila de configuracion: una lectura que escribe no es una lectura."""
    _evento(orden, tecnico[1], "avance_campo", hace_minutos=10)
    antes = (
        ConfiguracionDeSeguimiento.objects.count(),
        ContactoDeDispositivo.objects.count(),
        EventoTrabajo.objects.count(),
        BloqueoDeTrabajo.objects.count(),
    )
    for _ in range(3):
        salud.calcular(orden)
    despues = (
        ConfiguracionDeSeguimiento.objects.count(),
        ContactoDeDispositivo.objects.count(),
        EventoTrabajo.objects.count(),
        BloqueoDeTrabajo.objects.count(),
    )
    assert antes == despues


# --------------------------------------------------------------------------- #
# Y-Z. El resumen de la bandeja y el aislamiento
# --------------------------------------------------------------------------- #

def test_y_el_resumen_cuenta_cada_situacion(org_a, version, tecnico):
    _config(org_a, reportar=30, contacto=15)
    ahora = timezone.now()

    al_dia = _orden(org_a, version, tecnico[1], numero=7101)
    _evento(al_dia, tecnico[1], "avance_campo", hace_minutos=5)

    vencida = _orden(org_a, version, tecnico[1], numero=7102)
    _evento(vencida, tecnico[1], "avance_campo", hace_minutos=40)

    pausada = _orden(org_a, version, tecnico[1], numero=7103)
    serv_bloqueos.bloquear(
        pausada, profile=tecnico[1], respuestas={"motivo": "sin acceso"},
        requiere_noc=True,
    )

    terminada = _orden(org_a, version, tecnico[1], numero=7104,
                       estado=OrdenTrabajo.CERRADA)

    _contacto(tecnico[1], org_a, hace_minutos=1)
    r = salud.resumen_de_org(org_a, ahora=ahora)

    assert r["conteo"][salud.AL_DIA] >= 1
    assert r["conteo"][salud.VENCIDO] >= 1
    assert r["conteo"][salud.PAUSADO_NOC] >= 1
    assert str(terminada.id) not in r["por_orden"]
    assert r["evalua_la_sincronizacion"] is True


def test_z_el_resumen_de_otra_empresa_devuelve_cero(org_a, org_b, version, tecnico):
    """Cero filas, no "no aparece en la lista"."""
    o = _orden(org_a, version, tecnico[1], numero=7201)
    _evento(o, tecnico[1], "avance_campo", hace_minutos=40)
    r = salud.resumen_de_org(org_b)
    assert r["por_orden"] == {}
    assert sum(r["conteo"].values()) == 0
