# -*- coding: utf-8 -*-
"""
================================================================================
 M03-B  --  la primera programación real de una orden
================================================================================

Lo que estas pruebas afirman NO es que exista un endpoint: es que después de
llamarlo, la línea de plan y 'programada_para' dicen lo mismo, y que cuando algo
falla no queda escrita ni una de las dos.

DOS DECISIONES DE MÉTODO
------------------------
1. La persistencia no se lee del ORM que acaba de escribir. Varias pruebas
   abren una CONEXIÓN psycopg INDEPENDIENTE y leen la tabla desde fuera. Si el
   servicio se equivocara, el ORM podría repetir el error; otra conexión, no.

2. La atomicidad no se afirma leyendo 'transaction.atomic' en el código: se
   rompe la operación a propósito en su último paso y se comprueba que los dos
   primeros tampoco quedaron.
================================================================================
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from unittest import mock

import psycopg
import pytest
from django.db import connection, connections
from django.utils import timezone
from psycopg.rows import dict_row
from rest_framework.test import APIClient

from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones.models import ProgramacionOrden, ProgramacionSemanal
from operaciones.programacion import (ErrorProgramacion, YaProgramada,
                                      programar_orden)

#  El lunes de una semana futura fija. Fija y no 'hoy' porque la semana a la que
#  pertenece 'hoy' cambia según el día en que se corra la suite, y entonces la
#  comprobación de pertenencia a la semana pasaría o fallaría por el calendario.
LUNES = date(2026, 10, 5)
CUANDO = timezone.make_aware(datetime.combine(LUNES + timedelta(days=2),
                                              time(9, 0)))


# ---------------------------------------------------------------------------
#  Datos
# ---------------------------------------------------------------------------
def _version(org, codigo):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=f"Tipo {codigo}")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})


def _orden(org, version, numero, estado=OrdenTrabajo.ASIGNADA):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Cliente M03-B", cliente_direccion="Calle 1",
        estado_operativo=estado)


def _plan(org, estado=ProgramacionSemanal.BORRADOR, lunes=LUNES):
    return ProgramacionSemanal.objects.create(
        org=org, semana_inicio=lunes, estado=estado)


@pytest.fixture
def version_a(org_a):
    return _version(org_a, "m03b_a")


@pytest.fixture
def orden_a(org_a, version_a):
    return _orden(org_a, version_a, 7001)


@pytest.fixture
def plan_a(org_a):
    return _plan(org_a)


@pytest.fixture
def gestor_a(org_a):
    """Un perfil con rol de gestión: programar es de quien coordina."""
    u = User.objects.create_user(email="jefe.m03b@test.com", password="x12345678")
    return u, Profile.objects.create(user=u, org=org_a, role="OPERACIONES",
                                     is_active=True)


@pytest.fixture
def cliente_a(org_a, gestor_a):
    u, p = gestor_a
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(u, org_a, p)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    return c


def _url(orden):
    return f"/api/campo/trabajos/{orden.id}/programar/"


def _cuerpo(plan, cuando=CUANDO, **extra):
    d = {"programacion_semanal_id": str(plan.id),
         "programada_para": cuando.isoformat()}
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
#  La conexión testigo
# ---------------------------------------------------------------------------
def _leer_desde_fuera(sql, params=None):
    """
    Lee la base con una conexión propia, ajena al ORM de la prueba.

    Solo sirve en pruebas con 'transaction=True': sin commit, otra conexión no
    ve nada, y la prueba mediría el aislamiento de PostgreSQL en vez de lo que
    dice medir.
    """
    cfg = connection.settings_dict
    con = psycopg.connect(host=cfg["HOST"], port=cfg["PORT"], dbname=cfg["NAME"],
                          user=cfg["USER"], password=cfg["PASSWORD"],
                          row_factory=dict_row)
    try:
        with con.cursor() as c:
            c.execute(sql, params)
            return c.fetchall()
    finally:
        con.close()


# ===========================================================================
#  B1  --  programación válida
# ===========================================================================
@pytest.mark.django_db
def test_b1_programacion_valida(cliente_a, orden_a, plan_a):
    r = cliente_a.post(_url(orden_a), _cuerpo(plan_a), format="json")
    assert r.status_code == 201, r.content[:400]

    orden_a.refresh_from_db()
    linea = ProgramacionOrden.objects.get(orden=orden_a)

    assert orden_a.programada_para == CUANDO
    assert linea.programacion_id == plan_a.id
    assert linea.estado == ProgramacionOrden.PLANIFICADA
    #  La coherencia que M03-B existe para garantizar, con la MISMA conversión
    #  que usa H-05.
    assert linea.dia == timezone.localtime(orden_a.programada_para).date()


@pytest.mark.django_db
def test_b1b_el_evento_de_auditoria_queda_con_actor(cliente_a, orden_a, plan_a,
                                                    gestor_a):
    cliente_a.post(_url(orden_a), _cuerpo(plan_a), format="json")
    ev = EventoTrabajo.objects.get(orden=orden_a, tipo="programacion")
    assert ev.profile_id == gestor_a[1].id
    assert ev.org_id == orden_a.org_id
    assert ev.datos["dia"] == str(CUANDO.date())
    assert ev.created_at is not None


# ===========================================================================
#  B2  --  persistencia verificada desde fuera del ORM
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_b2_persistencia_por_conexion_independiente(cliente_a, orden_a, plan_a):
    if connection.vendor != "postgresql":
        pytest.skip("una conexión independiente sólo tiene sentido en PostgreSQL")

    r = cliente_a.post(_url(orden_a), _cuerpo(plan_a), format="json")
    assert r.status_code == 201

    filas = _leer_desde_fuera(
        "select po.dia, po.estado, o.programada_para "
        "from operaciones_programacion_orden po "
        "join campo_orden_trabajo o on o.id = po.orden_id "
        "where po.orden_id = %s", [str(orden_a.id)])

    assert len(filas) == 1
    fila = filas[0]
    assert fila["programada_para"] is not None
    assert fila["estado"] == ProgramacionOrden.PLANIFICADA
    #  La comprobación del §16, leída de la base y no del objeto en memoria.
    assert fila["dia"] == timezone.localtime(fila["programada_para"]).date()


# ===========================================================================
#  B3  --  organización incorrecta
# ===========================================================================
@pytest.mark.django_db
def test_b3_orden_de_a_con_plan_de_b(cliente_a, orden_a, org_b):
    plan_b = _plan(org_b)
    r = cliente_a.post(_url(orden_a), _cuerpo(plan_b), format="json")

    #  404 y no 403: el plan de otra empresa no se confirma que exista.
    assert r.status_code == 404
    orden_a.refresh_from_db()
    assert orden_a.programada_para is None
    assert ProgramacionOrden.objects.count() == 0


@pytest.mark.django_db
def test_b3b_el_servicio_tambien_lo_rechaza_sin_pasar_por_la_vista(
        org_a, org_b, orden_a, gestor_a):
    """La vista filtra por organización; el servicio no confía en que lo haya hecho."""
    plan_b = _plan(org_b)
    with pytest.raises(ErrorProgramacion) as e:
        programar_orden(org=org_a, orden=orden_a, programacion=plan_b,
                        programada_para=CUANDO, actor=gestor_a[1])
    assert "otra empresa" in str(e.value)
    assert ProgramacionOrden.objects.count() == 0


@pytest.mark.django_db
def test_b3c_el_organization_id_del_cuerpo_no_decide_nada(
        cliente_a, orden_a, plan_a, org_b):
    cuerpo = _cuerpo(plan_a)
    cuerpo["organization_id"] = str(org_b.id)
    cuerpo["org"] = str(org_b.id)
    cuerpo["org_id"] = str(org_b.id)

    r = cliente_a.post(_url(orden_a), cuerpo, format="json")
    assert r.status_code == 201

    linea = ProgramacionOrden.objects.get(orden=orden_a)
    assert linea.org_id == orden_a.org_id     # la de la sesión
    assert ProgramacionOrden.objects.filter(org=org_b).count() == 0


# ===========================================================================
#  B4 / B5  --  no existe
# ===========================================================================
@pytest.mark.django_db
def test_b4_orden_inexistente(cliente_a, plan_a):
    import uuid
    r = cliente_a.post(f"/api/campo/trabajos/{uuid.uuid4()}/programar/",
                       _cuerpo(plan_a), format="json")
    assert r.status_code == 404
    assert ProgramacionOrden.objects.count() == 0


@pytest.mark.django_db
def test_b5_programacion_inexistente(cliente_a, orden_a):
    import uuid

    class _Falso:
        id = uuid.uuid4()
    r = cliente_a.post(_url(orden_a), {
        "programacion_semanal_id": str(uuid.uuid4()),
        "programada_para": CUANDO.isoformat()}, format="json")
    assert r.status_code == 404
    orden_a.refresh_from_db()
    assert orden_a.programada_para is None


# ===========================================================================
#  B6  --  ya programada: no se sobrescribe
# ===========================================================================
@pytest.mark.django_db
def test_b6_orden_ya_programada_se_rechaza(cliente_a, orden_a, plan_a):
    primera = cliente_a.post(_url(orden_a), _cuerpo(plan_a), format="json")
    assert primera.status_code == 201

    otro_dia = CUANDO + timedelta(days=1)
    segunda = cliente_a.post(_url(orden_a), _cuerpo(plan_a, cuando=otro_dia),
                             format="json")

    assert segunda.status_code == 409
    assert segunda.json()["error"] == "YA_PROGRAMADA"
    assert segunda.json()["pendiente"] == "REPROGRAMACION"

    #  Y lo que importa: nada se movió.
    orden_a.refresh_from_db()
    assert orden_a.programada_para == CUANDO
    assert ProgramacionOrden.objects.filter(orden=orden_a).count() == 1


@pytest.mark.django_db
def test_b6b_tambien_si_solo_estaba_poblado_programada_para(
        org_a, orden_a, plan_a, gestor_a):
    """
    La incoherencia que M03-B existe para no producir, vista desde el otro lado.

    Una orden con 'programada_para' puesto y sin línea de plan es exactamente
    lo que hoy hay en producción (0 de 3, pero el campo es escribible al crear).
    Programarla encima dejaría una línea nueva junto a una fecha que nadie
    puede explicar.
    """
    orden_a.programada_para = CUANDO
    orden_a.save(update_fields=["programada_para"])

    with pytest.raises(YaProgramada):
        programar_orden(org=org_a, orden=orden_a, programacion=plan_a,
                        programada_para=CUANDO, actor=gestor_a[1])
    assert ProgramacionOrden.objects.count() == 0


# ===========================================================================
#  B7  --  rollback real
# ===========================================================================
@pytest.mark.django_db
def test_b7_si_falla_el_ultimo_paso_no_queda_nada(org_a, orden_a, plan_a,
                                                  gestor_a):
    """
    Se rompe la operación DESPUÉS de sus dos escrituras.

    El evento de auditoría es el último paso: si revienta ahí, la línea de plan
    y 'programada_para' ya están escritos en la transacción. Que no queden es lo
    único que prueba que la atomicidad es real y no un decorador decorativo.
    """
    with mock.patch.object(EventoTrabajo.objects, "create",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            programar_orden(org=org_a, orden=orden_a, programacion=plan_a,
                            programada_para=CUANDO, actor=gestor_a[1])

    orden_a.refresh_from_db()
    assert orden_a.programada_para is None
    assert ProgramacionOrden.objects.count() == 0
    assert EventoTrabajo.objects.filter(tipo="programacion").count() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_b7b_el_rollback_tambien_se_ve_desde_fuera(org_a, orden_a, plan_a,
                                                   gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")

    with mock.patch.object(EventoTrabajo.objects, "create",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            programar_orden(org=org_a, orden=orden_a, programacion=plan_a,
                            programada_para=CUANDO, actor=gestor_a[1])

    lineas = _leer_desde_fuera(
        "select count(*) n from operaciones_programacion_orden "
        "where orden_id = %s", [str(orden_a.id)])
    fechas = _leer_desde_fuera(
        "select programada_para from campo_orden_trabajo where id = %s",
        [str(orden_a.id)])
    assert lineas[0]["n"] == 0
    assert fechas[0]["programada_para"] is None


# ===========================================================================
#  B8  --  concurrencia
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_b8_dos_peticiones_simultaneas_programan_una_sola_vez(
        org_a, version_a, gestor_a):
    """
    Dos supervisores programan la misma orden a la vez, con fechas distintas.

    Sin el 'select_for_update' las dos comprueban "no está programada" antes de
    que ninguna escriba, y la orden termina con dos líneas y dos fechas. Con el
    lock, la segunda ve el trabajo de la primera y se rechaza.
    """
    if connection.vendor != "postgresql":
        pytest.skip("la concurrencia real requiere PostgreSQL")

    u, perfil = gestor_a
    orden = _orden(org_a, version_a, 7777)
    plan = _plan(org_a)
    cli = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(u, org_a, perfil)
    cli.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")

    def programa(delta_dias):
        try:
            r = cli.post(_url(orden),
                         _cuerpo(plan, cuando=CUANDO + timedelta(days=delta_dias)),
                         format="json")
            return r.status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(programa, [0, 1]))

    #  Una crea, la otra choca. Nunca dos 201, y nunca un 500.
    assert codigos == [201, 409], codigos
    assert ProgramacionOrden.objects.filter(orden=orden).count() == 1

    orden.refresh_from_db()
    linea = ProgramacionOrden.objects.get(orden=orden)
    assert linea.dia == timezone.localtime(orden.programada_para).date()


# ===========================================================================
#  B9  --  programar no asigna
# ===========================================================================
@pytest.mark.django_db
def test_b9_una_orden_queda_programada_y_sin_tecnico(cliente_a, orden_a, plan_a):
    """Es deliberado: M03-B programa, no asigna (§9 del encargo)."""
    assert AsignacionTrabajo.objects.filter(orden=orden_a).count() == 0

    r = cliente_a.post(_url(orden_a), _cuerpo(plan_a), format="json")
    assert r.status_code == 201

    orden_a.refresh_from_db()
    assert orden_a.programada_para is not None
    assert AsignacionTrabajo.objects.filter(orden=orden_a).count() == 0
    assert orden_a.tecnico_principal is None


# ===========================================================================
#  B10  --  no toca lo que no le toca
# ===========================================================================
@pytest.mark.django_db
def test_b10_no_cambia_estado_ni_inventa_transiciones(cliente_a, orden_a,
                                                      plan_a):
    antes_op = orden_a.estado_operativo
    antes_val = orden_a.estado_validacion
    antes_vuelta = orden_a.vuelta
    antes_iniciada = orden_a.iniciada_en

    cliente_a.post(_url(orden_a), _cuerpo(plan_a), format="json")

    orden_a.refresh_from_db()
    assert orden_a.estado_operativo == antes_op
    assert orden_a.estado_validacion == antes_val
    assert orden_a.vuelta == antes_vuelta
    assert orden_a.iniciada_en == antes_iniciada


@pytest.mark.django_db
@pytest.mark.parametrize("estado", [
    OrdenTrabajo.EN_CAMINO,
    OrdenTrabajo.EN_SITIO,
    OrdenTrabajo.COMPLETADA_CAMPO,
    OrdenTrabajo.CORRECCION_REQUERIDA,
    OrdenTrabajo.CERRADA,
    OrdenTrabajo.CANCELADA,
])
def test_b10b_solo_se_programa_lo_que_no_arranco(cliente_a, org_a, version_a,
                                                 plan_a, estado):
    orden = _orden(org_a, version_a, 7100 + hash(estado) % 800, estado=estado)
    r = cliente_a.post(_url(orden), _cuerpo(plan_a), format="json")

    assert r.status_code == 400
    orden.refresh_from_db()
    assert orden.programada_para is None
    assert ProgramacionOrden.objects.filter(orden=orden).count() == 0


# ===========================================================================
#  B11 / B12  --  cross-tenant y segunda organización
# ===========================================================================
@pytest.mark.django_db
def test_b11_cross_tenant_en_las_dos_direcciones(org_a, org_b, gestor_a):
    version_b = _version(org_b, "m03b_b")
    orden_b = _orden(org_b, version_b, 7501)
    plan_b = _plan(org_b)
    version_a2 = _version(org_a, "m03b_a2")
    orden_a2 = _orden(org_a, version_a2, 7502)
    plan_a2 = _plan(org_a)

    u, perfil_a = gestor_a
    cli_a = APIClient()
    cli_a.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org_a, perfil_a).access_token}"))

    ub = User.objects.create_user(email="jefe.b.m03b@test.com", password="x12345678")
    perfil_b = Profile.objects.create(user=ub, org=org_b, role="OPERACIONES",
                                      is_active=True)
    cli_b = APIClient()
    cli_b.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(ub, org_b, perfil_b).access_token}"))

    #  A -> A : permitido
    assert cli_a.post(_url(orden_a2), _cuerpo(plan_a2),
                      format="json").status_code == 201
    #  A -> B : la orden de B no existe para A
    assert cli_a.post(_url(orden_b), _cuerpo(plan_b),
                      format="json").status_code == 404
    #  B -> A : simétrico
    assert cli_b.post(_url(orden_a2), _cuerpo(plan_a2),
                      format="json").status_code == 404

    orden_b.refresh_from_db()
    assert orden_b.programada_para is None
    assert ProgramacionOrden.objects.filter(org=org_b).count() == 0


@pytest.mark.django_db
def test_b12_la_segunda_organizacion_programa_lo_suyo_sin_ver_lo_ajeno(
        org_a, org_b, orden_a, plan_a, cliente_a):
    assert cliente_a.post(_url(orden_a), _cuerpo(plan_a),
                          format="json").status_code == 201

    version_b = _version(org_b, "m03b_b2")
    orden_b = _orden(org_b, version_b, 7601)
    plan_b = _plan(org_b)
    ub = User.objects.create_user(email="jefe.b2.m03b@test.com", password="x12345678")
    perfil_b = Profile.objects.create(user=ub, org=org_b, role="OPERACIONES",
                                      is_active=True)
    cli_b = APIClient()
    cli_b.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(ub, org_b, perfil_b).access_token}"))

    assert cli_b.post(_url(orden_b), _cuerpo(plan_b),
                      format="json").status_code == 201

    assert ProgramacionOrden.objects.filter(org=org_a).count() == 1
    assert ProgramacionOrden.objects.filter(org=org_b).count() == 1
    a = ProgramacionOrden.objects.get(org=org_a)
    b = ProgramacionOrden.objects.get(org=org_b)
    assert a.orden_id == orden_a.id and b.orden_id == orden_b.id
    assert a.id != b.id


# ===========================================================================
#  Guardas de alcance  --  lo que M03-B NO debe hacer
# ===========================================================================
@pytest.mark.django_db
def test_un_plan_cerrado_no_admite_lineas(cliente_a, orden_a, org_a):
    cerrado = _plan(org_a, estado=ProgramacionSemanal.CERRADA)
    r = cliente_a.post(_url(orden_a), _cuerpo(cerrado), format="json")
    assert r.status_code == 400
    assert ProgramacionOrden.objects.count() == 0


@pytest.mark.django_db
def test_una_fecha_fuera_de_la_semana_del_plan_se_rechaza(cliente_a, orden_a,
                                                          plan_a):
    fuera = CUANDO + timedelta(days=14)
    r = cliente_a.post(_url(orden_a), _cuerpo(plan_a, cuando=fuera),
                       format="json")
    assert r.status_code == 400
    assert "fuera del plan" in r.json()["detalle"]
    orden_a.refresh_from_db()
    assert orden_a.programada_para is None


@pytest.mark.django_db
def test_un_tecnico_no_puede_programar(org_a, orden_a, plan_a, regular_user,
                                       user_profile):
    """Programar es de quien coordina, igual que asignar y validar."""
    cli = APIClient()
    cli.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(regular_user, org_a, user_profile).access_token}"))
    r = cli.post(_url(orden_a), _cuerpo(plan_a), format="json")
    assert r.status_code == 403
    assert ProgramacionOrden.objects.count() == 0


@pytest.mark.django_db
def test_sin_sesion_no_se_programa(orden_a, plan_a):
    r = APIClient().post(_url(orden_a), _cuerpo(plan_a), format="json")
    assert r.status_code in (401, 403)
    assert ProgramacionOrden.objects.count() == 0


@pytest.mark.django_db
def test_una_programacion_sin_actor_no_es_representable(org_a, orden_a, plan_a):
    with pytest.raises(ErrorProgramacion):
        programar_orden(org=org_a, orden=orden_a, programacion=plan_a,
                        programada_para=CUANDO, actor=None)
    assert ProgramacionOrden.objects.count() == 0


@pytest.mark.django_db
def test_m03b_no_escribe_novedades_ni_asignaciones(cliente_a, orden_a, plan_a):
    """
    Afirma sobre el EFECTO, no sobre la intención.

    Novedades es reprogramación (fase posterior) y asignación es otro módulo.
    Que el código no las llame hoy no impide que alguien las llame mañana sin
    darse cuenta de que cambia el alcance de la fase.
    """
    from operaciones.models import NovedadOperativa
    cliente_a.post(_url(orden_a), _cuerpo(plan_a), format="json")

    assert NovedadOperativa.objects.count() == 0
    assert AsignacionTrabajo.objects.count() == 0
    assert ProgramacionSemanal.objects.filter(
        estado=ProgramacionSemanal.PUBLICADA).count() == 0
