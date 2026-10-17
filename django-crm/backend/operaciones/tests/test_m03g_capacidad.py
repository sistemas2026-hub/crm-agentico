# -*- coding: utf-8 -*-
"""
================================================================================
 M03-G  --  capacidad operacional
================================================================================

Las pruebas afirman sobre VALORES, no sobre HTTP 200: un endpoint que responde
200 con un numero inventado pasa cualquier prueba de codigo de estado.

El nucleo de lo que se comprueba aqui es la asimetria del veredicto:

    con datos parciales SE PUEDE afirmar la sobrecarga
    con datos parciales NO SE PUEDE afirmar que no la hay

Una prueba que aceptara "sin sobrecarga" sobre duraciones desconocidas estaria
validando exactamente la falsa conclusion que este modulo existe para evitar.
================================================================================
"""

from __future__ import annotations

import socket
import threading
from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from business_hours.models import BusinessCalendar, BusinessHoliday
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones import capacidad as cap
from operaciones.capacidad import (capacidad_de_jornada, capacidad_de_persona,
                                   duracion_de_linea, jornada_de)
from operaciones.models import (DisponibilidadTecnico, ProgramacionOrden,
                                ProgramacionSemanal)
from operaciones.programacion import programar_orden

LUNES = date(2026, 10, 5)          # lunes
SABADO = date(2026, 10, 10)
URL = "/api/operaciones/capacidad/jornada/"

_n = [4000]
_c = [0]


def _dt(dias=0, hora=9, minuto=0):
    return timezone.make_aware(
        datetime.combine(LUNES + timedelta(days=dias), time(hora, minuto)))


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"g{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


def _cli(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


def _version(org, codigo, duracion=None):
    """Si 'duracion' es None el esquema NO lleva la clave: duracion desconocida."""
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo)
    esquema = {"campos": [], "evidencias": []}
    if duracion is not None:
        esquema[cap.CLAVE_DURACION] = duracion
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=esquema)


def _orden(org, duracion=None, version=None):
    _n[0] += 1
    return OrdenTrabajo.objects.create(
        org=org, numero=_n[0],
        tipo_trabajo_version=version or _version(org, f"g_{_n[0]}", duracion),
        cliente_nombre=f"Cliente {_n[0]}", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA)


def _calendario(org, abre=time(8, 0), cierra=time(17, 0), tz="UTC",
                sabado=False):
    cal = BusinessCalendar.objects.create(
        org=org, name="Default", timezone=tz, is_default=True)
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        setattr(cal, f"{d}_open", abre)
        setattr(cal, f"{d}_close", cierra)
    if sabado:
        cal.saturday_open, cal.saturday_close = abre, cierra
    cal.save()
    return cal


def _plan(org):
    return ProgramacionSemanal.objects.create(
        org=org, semana_inicio=LUNES, estado=ProgramacionSemanal.BORRADOR)


def _programar(org, orden, actor, plan, dias=0, hora=9, secuencia=None,
               prioridad=None):
    return programar_orden(org=org, orden=orden, programacion=plan,
                           programada_para=_dt(dias, hora), actor=actor,
                           secuencia=secuencia, prioridad=prioridad)


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


# ==================================================== 1-2. jornada
@pytest.mark.django_db
def test_1_jornada_valida(org_a):
    _calendario(org_a, time(8, 0), time(17, 0))
    j = jornada_de(org_a, LUNES)
    assert j.abierta is True
    assert j.minutos == 540, "08:00-17:00 son 540 minutos, no 480"
    assert j.zona_horaria == "UTC"


@pytest.mark.django_db
def test_2_jornada_cerrada(org_a, actor):
    """Sabado sin horario, feriado y sin calendario: tres motivos distintos."""
    _calendario(org_a, sabado=False)
    j = jornada_de(org_a, SABADO)
    assert j.abierta is False and j.motivo == cap.CERRADA

    BusinessHoliday.objects.create(
        org=org_a, calendar=BusinessCalendar.objects.get(org=org_a),
        date=LUNES, name="Festivo")
    j = jornada_de(org_a, LUNES)
    assert j.abierta is False and j.motivo == cap.FERIADO


@pytest.mark.django_db
def test_2b_sin_calendario_la_capacidad_no_es_determinable(org_a, actor):
    """Sin jornada no se inventa una de ocho horas: no se puede determinar."""
    o = _orden(org_a, duracion=120)
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor, plan)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["resultado"] == cap.NO_DETERMINABLE
    assert r["capacidad_minutos"] is None
    assert r["riesgo"] == cap.INDETERMINADO
    assert cap.SIN_CALENDARIO in r["faltantes"]


@pytest.mark.django_db
def test_2c_jornada_invalida_no_se_arregla_sola(org_a):
    """Cierra antes de abrir: no se supone un turno noche."""
    _calendario(org_a, abre=time(17, 0), cierra=time(8, 0))
    j = jornada_de(org_a, LUNES)
    assert j.abierta is False and j.motivo == cap.INVALIDA


# ==================================================== 3-5. disponibilidad
@pytest.mark.django_db
def test_3_disponibilidad_declarada(org_a):
    _calendario(org_a, time(8, 0), time(17, 0))
    _, p1 = _persona(org_a)
    DisponibilidadTecnico.objects.create(
        org=org_a, profile=p1, fecha=LUNES, hora_inicio=time(8, 0),
        hora_fin=time(12, 0), disponible=True, motivo="")
    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["disponibilidad"]["estado"] == cap.PARCIAL
    assert r["capacidad_minutos"] == 240


@pytest.mark.django_db
def test_4_ausencia_reduce_la_capacidad(org_a):
    _calendario(org_a, time(8, 0), time(17, 0))
    _, p1 = _persona(org_a)
    DisponibilidadTecnico.objects.create(
        org=org_a, profile=p1, fecha=LUNES, hora_inicio=time(12, 0),
        hora_fin=time(13, 0), disponible=False, motivo="almuerzo")
    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["capacidad_minutos"] == 480, "la ausencia no descontó"
    assert r["disponibilidad"]["estado"] == cap.PARCIAL

    #  ausente todo el dia
    _, p2 = _persona(org_a)
    DisponibilidadTecnico.objects.create(
        org=org_a, profile=p2, fecha=LUNES, hora_inicio=time(8, 0),
        hora_fin=time(17, 0), disponible=False, motivo="incapacidad")
    r2 = capacidad_de_persona(org_a, p2, LUNES)
    assert r2["capacidad_minutos"] == 0
    assert r2["disponibilidad"]["estado"] == cap.AUSENTE


@pytest.mark.django_db
def test_5_sin_registro_declara_el_supuesto(org_a):
    """
    Sin franjas se toma la jornada completa -- pero eso es un SUPUESTO y tiene
    que venir dicho, o el que lee lo confunde con un dato.
    """
    _calendario(org_a, time(8, 0), time(17, 0))
    _, p1 = _persona(org_a)
    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["disponibilidad"]["estado"] == cap.SIN_REGISTRO
    assert r["capacidad_minutos"] == 540
    assert r["disponibilidad"]["supuesto"], "el supuesto no se declaró"
    assert "SIN_REGISTRO_DISPONIBILIDAD" in r["faltantes"]


# ==================================================== 6-10. carga
@pytest.mark.django_db
def test_6_una_ot(org_a, actor):
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor, plan)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["carga"]["ordenes"] == 1
    assert r["carga"]["minutos_conocidos"] == 120
    assert r["disponible_restante_minutos"] == 420
    assert r["riesgo"] == cap.SIN_SOBRECARGA
    assert r["estado_datos"] == cap.SUFICIENTES


@pytest.mark.django_db
def test_7_8_varias_ots_carga_menor_que_capacidad(org_a, actor):
    """El ejemplo del encargo: 120 + 180 + 120 = 420."""
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    for minutos, hora in ((120, 8), (180, 10), (120, 14)):
        o = _orden(org_a, duracion=minutos)
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        _programar(org_a, o, actor, plan, hora=hora)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["carga"]["ordenes"] == 3
    assert r["carga"]["minutos_conocidos"] == 420
    assert r["capacidad_minutos"] == 540
    assert r["disponible_restante_minutos"] == 120
    assert r["riesgo"] == cap.SIN_SOBRECARGA


@pytest.mark.django_db
def test_8b_el_ejemplo_del_encargo_con_descanso_declarado(org_a, actor):
    """
    El encargo ejemplifica 08:00-17:00 -> 480 minutos, que supone un descanso
    de 60. El sistema NO inventa descansos: 08:00-17:00 son 540. Los 480 salen
    cuando el descanso se DECLARA, y para eso ya existe DisponibilidadTecnico.
    """
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    DisponibilidadTecnico.objects.create(
        org=org_a, profile=p1, fecha=LUNES, hora_inicio=time(12, 0),
        hora_fin=time(13, 0), disponible=False, motivo="descanso")
    for minutos, hora in ((120, 8), (180, 13), (120, 15)):
        o = _orden(org_a, duracion=minutos)
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        _programar(org_a, o, actor, plan, hora=hora)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["capacidad_minutos"] == 480
    assert r["carga"]["minutos_conocidos"] == 420
    assert r["disponible_restante_minutos"] == 60
    assert r["riesgo"] == cap.SIN_SOBRECARGA


@pytest.mark.django_db
def test_9_carga_igual_a_capacidad_no_es_sobrecarga(org_a, actor):
    _calendario(org_a, time(8, 0), time(16, 0))      # 480
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    for minutos, hora in ((240, 8), (240, 12)):
        o = _orden(org_a, duracion=minutos)
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        _programar(org_a, o, actor, plan, hora=hora)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["capacidad_minutos"] == 480 and r["carga"]["minutos_conocidos"] == 480
    assert r["disponible_restante_minutos"] == 0
    assert r["exceso_minutos"] == 0
    assert r["riesgo"] == cap.SIN_SOBRECARGA, "igual no es mayor"


@pytest.mark.django_db
def test_10_carga_mayor_a_capacidad(org_a, actor):
    """El caso §16: capacidad 480, carga 560, exceso 80."""
    _calendario(org_a, time(8, 0), time(16, 0))      # 480
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    for minutos, hora in ((280, 8), (280, 12)):
        o = _orden(org_a, duracion=minutos)
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        _programar(org_a, o, actor, plan, hora=hora)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["capacidad_minutos"] == 480
    assert r["carga"]["minutos_conocidos"] == 560
    assert r["exceso_minutos"] == 80
    assert r["riesgo"] == cap.SOBRECARGA
    #  y NO ejecuta nada
    assert ProgramacionOrden.objects.filter(programacion=plan).count() == 2


# ==================================================== 11-12. datos faltantes
@pytest.mark.django_db
def test_11_duracion_faltante_no_vale_cero(org_a, actor):
    """
    LA REGLA CENTRAL. Una OT sin duracion no aporta 0: aporta desconocido, y el
    veredicto pasa a INDETERMINADO en vez de 'sin sobrecarga'.
    """
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    o1 = _orden(org_a, duracion=120)
    o2 = _orden(org_a, duracion=None)          # sin duracion
    for o, hora in ((o1, 8), (o2, 11)):
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        _programar(org_a, o, actor, plan, hora=hora)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["carga"]["minutos_conocidos"] == 120, "la desconocida sumó 0"
    assert r["carga"]["ordenes"] == 2
    assert r["carga"]["ordenes_sin_duracion"] == 1
    assert r["carga"]["es_cota_inferior"] is True
    assert r["estado_datos"] == cap.PARCIALES
    assert r["riesgo"] == cap.INDETERMINADO, (
        "afirmó 'sin sobrecarga' sin conocer todas las duraciones")
    assert "DURACION_DESCONOCIDA" in r["faltantes"]
    assert o2.numero in r["carga"]["numeros_sin_duracion"]


@pytest.mark.django_db
def test_11b_con_datos_parciales_la_sobrecarga_SI_se_puede_afirmar(org_a, actor):
    """
    La otra mitad de la asimetria: si lo ya conocido no cabe, agregar lo
    desconocido tampoco va a caber. Ahi SI se concluye SOBRECARGA.
    """
    _calendario(org_a, time(8, 0), time(16, 0))      # 480
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    o1 = _orden(org_a, duracion=500)
    o2 = _orden(org_a, duracion=None)
    for o, hora in ((o1, 8), (o2, 12)):
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        _programar(org_a, o, actor, plan, hora=hora)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["estado_datos"] == cap.PARCIALES
    assert r["riesgo"] == cap.SOBRECARGA
    assert r["exceso_minutos"] == 20


@pytest.mark.django_db
def test_12_datos_insuficientes(org_a, actor):
    """Sin jornada no hay capacidad, y se dice con el motivo."""
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=None)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor, plan)

    r = capacidad_de_persona(org_a, p1, LUNES)
    assert r["estado_datos"] == cap.INSUFICIENTES
    assert r["resultado"] == cap.NO_DETERMINABLE
    assert r["capacidad_minutos"] is None
    assert r["disponible_restante_minutos"] is None


@pytest.mark.django_db
def test_12b_las_dos_fuentes_de_duracion(org_a, actor):
    """La franja de la linea manda sobre el estimado del tipo de trabajo."""
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    linea = _programar(org_a, o, actor, plan, hora=9)

    minutos, fuente = duracion_de_linea(linea)
    assert (minutos, fuente) == (120, "tipo_de_trabajo")

    linea.hora_inicio, linea.hora_fin = time(9, 0), time(12, 30)
    linea.save(update_fields=["hora_inicio", "hora_fin"])
    minutos, fuente = duracion_de_linea(linea)
    assert (minutos, fuente) == (210, "franja_de_la_linea")


@pytest.mark.django_db
def test_12c_un_esquema_con_basura_no_se_toma_como_duracion(org_a, actor):
    """True es int en Python y valdria 1 minuto; 0 y negativos no son duración."""
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    for valor in (True, 0, -30, "120", None, 12.5):
        #  El esquema se arma ANTES de publicar: WorkTypeVersion lo declara
        #  inmutable una vez PUBLICADA (campo/models.py:133), asi que una
        #  duracion no se le puede pegar despues a una version ya publicada.
        _n[0] += 1
        wt = WorkType.objects.create(org=org_a, codigo=f"basura_{_n[0]}",
                                     nombre="basura")
        v = WorkTypeVersion.objects.create(
            work_type=wt, version=1, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA,
            esquema={"campos": [], "evidencias": [], cap.CLAVE_DURACION: valor})
        o = _orden(org_a, version=v)
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        linea = _programar(org_a, o, actor, plan, hora=9)
        minutos, fuente = duracion_de_linea(linea)
        assert minutos is None, f"{valor!r} se tomó como {minutos} minutos"
        assert fuente == "desconocida"


# ==================================================== 13-14. individual y cuadrilla
@pytest.mark.django_db
def test_13_tecnico_individual(org_a, actor):
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=200)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor, plan)

    j = capacidad_de_jornada(org_a, LUNES)
    assert j["personas"] == 1
    assert j["resultados"][0]["carga"]["minutos_conocidos"] == 200


@pytest.mark.django_db
def test_14_cuadrilla_sin_coeficientes_inventados(org_a, actor):
    """
    Una OT de 200 minutos con dos personas ocupa 200 minutos a CADA una. Ni se
    divide entre dos (eso supondria que rinden el doble) ni se multiplica.
    """
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    o = _orden(org_a, duracion=200)
    AsignacionTrabajo.objects.create(orden=o, profile=pa,
                                     rol="tecnico_lider", es_principal=True)
    AsignacionTrabajo.objects.create(orden=o, profile=pb, rol="ayudante")
    _programar(org_a, o, actor, plan)

    j = capacidad_de_jornada(org_a, LUNES)
    assert j["personas"] == 2
    for r in j["resultados"]:
        assert r["carga"]["minutos_conocidos"] == 200, (
            "se repartió la duración entre la cuadrilla")
        assert r["carga"]["ordenes"] == 1
    #  el auxiliar cuenta igual que el principal: los dos estan ocupados
    assert {r["profile"]["id"] for r in j["resultados"]} == {str(pa.id), str(pb.id)}


# ==================================================== 15-18. programacion
@pytest.mark.django_db
def test_15_16_17_18_secuencia_y_prioridad_no_alteran_nada(org_a, actor):
    """
    §10: ni 'secuencia' ni 'prioridad' son duracion. Se comprueba variandolas
    y midiendo que la capacidad NO cambia.
    """
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    lineas = []
    for minutos, hora in ((120, 8), (180, 11)):
        o = _orden(org_a, duracion=minutos)
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        lineas.append(_programar(org_a, o, actor, plan, hora=hora))

    base = capacidad_de_persona(org_a, p1, LUNES)
    assert base["carga"]["minutos_conocidos"] == 300
    #  sin secuencia (0 = SIN SECUENCIAR, decision E-2)
    assert all(l.secuencia == 0 for l in lineas), "la programación puso secuencia sola"

    for i, l in enumerate(lineas):
        l.secuencia = 99 - i
        l.prioridad = 3 * (i + 1)
        l.save(update_fields=["secuencia", "prioridad"])

    despues = capacidad_de_persona(org_a, p1, LUNES)
    assert despues["carga"]["minutos_conocidos"] == base["carga"]["minutos_conocidos"]
    assert despues["capacidad_minutos"] == base["capacidad_minutos"]
    assert despues["riesgo"] == base["riesgo"]


@pytest.mark.django_db
def test_23_consultar_no_modifica_la_programacion(org_a, actor):
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    linea = _programar(org_a, o, actor, plan, hora=9)
    o.refresh_from_db(); linea.refresh_from_db()
    antes = (o.programada_para, o.revision, o.estado_operativo, linea.secuencia,
             linea.dia, linea.zona, linea.prioridad, linea.estado,
             linea.updated_at, linea.hora_inicio, linea.hora_fin)

    for _ in range(3):
        capacidad_de_jornada(org_a, LUNES)

    o.refresh_from_db(); linea.refresh_from_db()
    despues = (o.programada_para, o.revision, o.estado_operativo, linea.secuencia,
               linea.dia, linea.zona, linea.prioridad, linea.estado,
               linea.updated_at, linea.hora_inicio, linea.hora_fin)
    assert antes == despues, "consultar la capacidad movió la programación"


# ==================================================== 19-21. tenants
@pytest.mark.django_db
def test_19_20_21_aislamiento_entre_tenants(org_a, org_b, actor):
    _calendario(org_a, time(8, 0), time(17, 0))
    _calendario(org_b, time(8, 0), time(12, 0))
    plan_a, plan_b = _plan(org_a), _plan(org_b)
    _, pa = _persona(org_a)
    _, actor_b = _persona(org_b, "OPERACIONES")
    _, pb = _persona(org_b)

    oa = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=oa, profile=pa, es_principal=True)
    _programar(org_a, oa, actor, plan_a)

    ob = _orden(org_b, duracion=300)
    AsignacionTrabajo.objects.create(orden=ob, profile=pb, es_principal=True)
    _programar(org_b, ob, actor_b, plan_b)

    ja = capacidad_de_jornada(org_a, LUNES)
    jb = capacidad_de_jornada(org_b, LUNES)
    assert ja["personas"] == 1 and jb["personas"] == 1
    assert ja["resultados"][0]["profile"]["id"] == str(pa.id)
    assert jb["resultados"][0]["profile"]["id"] == str(pb.id)
    assert ja["jornada"]["minutos"] == 540
    assert jb["jornada"]["minutos"] == 240, "se usó el calendario de la otra empresa"
    assert ja["ordenes_programadas"] == 1, "vio órdenes del otro tenant"


@pytest.mark.django_db
def test_21b_la_api_no_deja_consultar_a_alguien_de_otra_empresa(org_a, org_b):
    _calendario(org_a)
    ug, g = _persona(org_a, "OPERACIONES")
    _, ajeno = _persona(org_b)
    cli = _cli(ug, org_a, g)
    r = cli.get(URL, {"dia": str(LUNES), "profile_id": str(ajeno.id)})
    assert r.status_code == 404, "confirmó la existencia de un perfil ajeno"


# ==================================================== 22. concurrencia
@pytest.mark.django_db(transaction=True)
def test_22_consultas_concurrentes(org_a):
    """Dos lecturas simultáneas dan el mismo resultado y no escriben nada."""
    from django.db import connection
    _calendario(org_a, time(8, 0), time(17, 0))
    _, act = _persona(org_a, "OPERACIONES")
    _, p1 = _persona(org_a)
    plan = _plan(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    linea = _programar(org_a, o, act, plan)
    linea.refresh_from_db()
    antes = linea.updated_at

    salidas, fallos = [], []

    def hilo():
        try:
            r = capacidad_de_persona(org_a, p1, LUNES)
            salidas.append((r["capacidad_minutos"],
                            r["carga"]["minutos_conocidos"], r["riesgo"]))
        except Exception as e:
            fallos.append(f"{type(e).__name__}: {e}")
        finally:
            connection.close()

    hs = [threading.Thread(target=hilo) for _ in range(4)]
    for h in hs: h.start()
    for h in hs: h.join(timeout=30)

    assert not fallos, fallos
    assert len(set(salidas)) == 1, f"lecturas concurrentes discrepan: {salidas}"
    linea.refresh_from_db()
    assert linea.updated_at == antes, "una lectura escribió"


# ==================================================== 24. efectos externos
@pytest.mark.django_db
def test_24_sin_efectos_externos(org_a, actor):
    _calendario(org_a, time(8, 0), time(17, 0))
    plan = _plan(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor, plan)

    salidas = []
    original = socket.socket.connect

    def espia(self, addr, *a, **k):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("pg-g", "127.0.0.1", "localhost", "::1"):
            salidas.append(host)
        return original(self, addr, *a, **k)

    socket.socket.connect = espia
    try:
        #  el instrumento tiene que disparar antes de creerle su cero
        try:
            s = socket.socket(); s.settimeout(1)
            s.connect(("example.invalid", 80))
        except Exception:
            pass
        assert salidas, "el espía no dispara: su cero no probaría nada"
        salidas.clear()

        capacidad_de_jornada(org_a, LUNES)
        capacidad_de_persona(org_a, p1, LUNES)
    finally:
        socket.socket.connect = original

    assert salidas == [], f"hubo llamadas externas: {salidas}"


# ==================================================== API
@pytest.mark.django_db
def test_api_devuelve_valores_no_solo_200(org_a, actor):
    _calendario(org_a, time(8, 0), time(16, 0))      # 480
    plan = _plan(org_a)
    ug, g = _persona(org_a, "OPERACIONES")
    _, p1 = _persona(org_a)
    for minutos, hora in ((280, 8), (280, 12)):
        o = _orden(org_a, duracion=minutos)
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        _programar(org_a, o, actor, plan, hora=hora)
    cli = _cli(ug, org_a, g)

    r = cli.get(URL, {"dia": str(LUNES)})
    assert r.status_code == 200
    assert r.data["ordenes_programadas"] == 2
    assert r.data["con_sobrecarga"] == 1
    fila = [x for x in r.data["resultados"] if x["profile"]["id"] == str(p1.id)][0]
    assert fila["capacidad_minutos"] == 480
    assert fila["carga"]["minutos_conocidos"] == 560
    assert fila["exceso_minutos"] == 80
    assert fila["riesgo"] == "SOBRECARGA"


@pytest.mark.django_db
def test_api_valida_el_dia_y_exige_permiso(org_a):
    _calendario(org_a)
    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)
    assert cli.get(URL).status_code == 400
    assert cli.get(URL, {"dia": "ayer"}).status_code == 400

    ut, t = _persona(org_a, "USER")
    assert _cli(ut, org_a, t).get(
        URL, {"dia": str(LUNES)}).status_code == 403


@pytest.mark.django_db
def test_api_una_persona_sin_trabajo_responde_carga_cero(org_a):
    """'No tiene nada' es una respuesta útil, y distinta de 'no se sabe'."""
    _calendario(org_a, time(8, 0), time(17, 0))
    ug, g = _persona(org_a, "OPERACIONES")
    _, p1 = _persona(org_a)
    cli = _cli(ug, org_a, g)
    r = cli.get(URL, {"dia": str(LUNES), "profile_id": str(p1.id)})
    assert r.status_code == 200
    fila = r.data["resultados"][0]
    assert fila["carga"]["ordenes"] == 0
    assert fila["carga"]["minutos_conocidos"] == 0
    assert fila["riesgo"] == "SIN_SOBRECARGA"
    assert fila["estado_datos"] == cap.SUFICIENTES
