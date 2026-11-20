# -*- coding: utf-8 -*-
"""
================================================================================
 M03-D3.2  --  las cuatro correcciones de cierre
================================================================================

  1. YaEnEsaFecha deja de ser provisional: rechaza, y NADA se mueve.
  2. 'secuencia' se trata igual en los dos casos de reprogramación.
  3. I-1 -- una orden con dos líneas vigentes -- bloquea la publicación.
  4. 'updated_by' se persiste al programar.

Las pruebas de la 4 pasan por una PETICIÓN REAL: el campo se escribe desde
'crum', que solo tiene usuario dentro del ciclo de request. Llamar al servicio
directo mediría otra cosa.
================================================================================
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import psycopg
import pytest
from django.db import connection
from django.utils import timezone
from psycopg.rows import dict_row
from rest_framework.test import APIClient

from campo.models import EventoTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones.models import ProgramacionOrden, ProgramacionSemanal
from operaciones.programacion import (programar_orden, reprogramar_orden,
                                      revisar_coherencia)

LUNES = date(2026, 10, 5)
SEM2 = LUNES + timedelta(weeks=1)


def _dt(lunes, dias, hora=9):
    return timezone.make_aware(
        datetime.combine(lunes + timedelta(days=dias), time(hora, 0)))


MIER = _dt(LUNES, 2)
VIER = _dt(LUNES, 4)
MAR2 = _dt(SEM2, 1, 14)


def _version(org, codigo):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})


def _orden(org, version, numero):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Cliente D3.2", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA)


def _plan(org, lunes=LUNES, estado=ProgramacionSemanal.BORRADOR):
    return ProgramacionSemanal.objects.create(
        org=org, semana_inicio=lunes, estado=estado)


@pytest.fixture
def version_a(org_a):
    return _version(org_a, "d32_a")


@pytest.fixture
def plan_a(org_a):
    return _plan(org_a)


@pytest.fixture
def gestor_a(org_a):
    u = User.objects.create_user(email="jefe.a@d32.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org_a, role="OPERACIONES",
                                     is_active=True)


@pytest.fixture
def cliente_a(org_a, gestor_a):
    u, p = gestor_a
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org_a, p).access_token}"))
    return c


def _url(orden, accion="reprogramar"):
    return f"/api/campo/trabajos/{orden.id}/{accion}/"


def _cuerpo(plan, cuando, **extra):
    d = {"programacion_semanal_id": str(plan.id),
         "programada_para": cuando.isoformat()}
    d.update(extra)
    return d


def _desde_fuera(sql, params=None):
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
#  1  --  YaEnEsaFecha: decisión aprobada, ya no provisional
# ===========================================================================
@pytest.mark.django_db
def test_1_misma_fecha_y_plan_no_mueve_absolutamente_nada(
        cliente_a, org_a, version_a, plan_a, gestor_a):
    """
    Los cinco 'no' de la decisión aprobada, comprobados uno por uno.
    """
    orden = _orden(org_a, version_a, 9201)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1], secuencia=7)
    orden.refresh_from_db()

    linea_antes = ProgramacionOrden.objects.get(orden=orden)
    revision_antes = orden.revision
    lineas_antes = ProgramacionOrden.objects.count()
    eventos_antes = EventoTrabajo.objects.filter(orden=orden).count()

    r = cliente_a.post(_url(orden), _cuerpo(plan_a, MIER), format="json")

    assert r.status_code == 409
    assert r.json()["error"] == "YA_EN_ESA_FECHA"
    #  La referencia se conserva, pero la conducta ya no es provisional.
    assert r.json()["pendiente"] == "DECISION_EMPRESARIAL_YaEnEsaFecha"

    orden.refresh_from_db()
    linea_antes.refresh_from_db()
    assert orden.programada_para == MIER                      # no se modifica
    assert orden.revision == revision_antes                   # no se modifica
    assert ProgramacionOrden.objects.count() == lineas_antes  # no se crea línea
    assert linea_antes.dia == MIER.date()
    assert linea_antes.secuencia == 7
    #  No se registra evento de reprogramación como si hubiera habido cambio.
    assert EventoTrabajo.objects.filter(
        orden=orden, tipo__startswith="reprogramacion").count() == 0
    assert EventoTrabajo.objects.filter(orden=orden).count() == eventos_antes


@pytest.mark.django_db
def test_1b_cambiar_solo_la_hora_del_mismo_dia_si_reprograma(
        cliente_a, org_a, version_a, plan_a, gestor_a):
    """La guarda compara el INSTANTE, no el día: mover la hora es un cambio."""
    orden = _orden(org_a, version_a, 9202)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    orden.refresh_from_db()

    otra_hora = _dt(LUNES, 2, 15)
    assert cliente_a.post(_url(orden), _cuerpo(plan_a, otra_hora),
                          format="json").status_code == 200
    orden.refresh_from_db()
    assert orden.programada_para == otra_hora


# ===========================================================================
#  2  --  secuencia: el mismo trato en los dos casos
# ===========================================================================
@pytest.mark.django_db
def test_2_el_caso_a_conserva_la_secuencia(cliente_a, org_a, version_a, plan_a,
                                           gestor_a):
    orden = _orden(org_a, version_a, 9210)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1],
                    zona="Norte", prioridad=10, secuencia=4)
    orden.refresh_from_db()

    assert cliente_a.post(_url(orden), _cuerpo(plan_a, VIER),
                          format="json").status_code == 200

    linea = ProgramacionOrden.objects.get(orden=orden)
    assert linea.dia == VIER.date()
    assert linea.secuencia == 4
    assert linea.prioridad == 10
    assert linea.zona == "Norte"


@pytest.mark.django_db
def test_2b_el_caso_b_ahora_tambien_la_conserva(cliente_a, org_a, version_a,
                                                plan_a, gestor_a):
    """
    La asimetría que D3.1 midió: 'zona' y 'prioridad' se arrastraban y
    'secuencia' se perdía, así que la misma operación se comportaba distinto
    según el caso. Los tres atributos de planificación viajan juntos.
    """
    orden = _orden(org_a, version_a, 9211)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1],
                    zona="Sur", prioridad=20, secuencia=6)
    orden.refresh_from_db()
    plan_b = _plan(org_a, lunes=SEM2)

    assert cliente_a.post(_url(orden), _cuerpo(plan_b, MAR2),
                          format="json").status_code == 200

    nueva = ProgramacionOrden.objects.get(
        orden=orden, estado=ProgramacionOrden.PLANIFICADA)
    assert nueva.programacion_id == plan_b.id
    assert nueva.secuencia == 6       # <- lo que antes se perdía
    assert nueva.prioridad == 20
    assert nueva.zona == "Sur"

    #  Y la vieja queda intacta, marcada.
    vieja = ProgramacionOrden.objects.get(
        orden=orden, estado=ProgramacionOrden.REPROGRAMADA)
    assert vieja.secuencia == 6
    assert vieja.dia == MIER.date()


@pytest.mark.django_db
def test_2c_los_dos_casos_dan_el_mismo_resultado(org_a, version_a, gestor_a):
    """La comprobación directa de la simetría: A y B, misma secuencia final."""
    plan_1 = _plan(org_a)
    plan_2 = _plan(org_a, lunes=SEM2)

    o_a = _orden(org_a, version_a, 9212)
    programar_orden(org=org_a, orden=o_a, programacion=plan_1,
                    programada_para=MIER, actor=gestor_a[1], secuencia=9)
    o_a.refresh_from_db()
    reprogramar_orden(org=org_a, orden=o_a, programada_para=VIER,
                      programacion_destino=plan_1, actor=gestor_a[1])

    v_b = _version(org_a, "d32_b")
    o_b = _orden(org_a, v_b, 9213)
    programar_orden(org=org_a, orden=o_b, programacion=plan_1,
                    programada_para=MIER, actor=gestor_a[1], secuencia=9)
    o_b.refresh_from_db()
    reprogramar_orden(org=org_a, orden=o_b, programada_para=MAR2,
                      programacion_destino=plan_2, actor=gestor_a[1])

    sec_a = ProgramacionOrden.objects.get(
        orden=o_a, estado=ProgramacionOrden.PLANIFICADA).secuencia
    sec_b = ProgramacionOrden.objects.get(
        orden=o_b, estado=ProgramacionOrden.PLANIFICADA).secuencia
    assert sec_a == sec_b == 9


@pytest.mark.django_db
def test_2d_sin_linea_previa_valen_los_defaults(org_a, version_a, plan_a,
                                                gestor_a):
    """
    Una orden con 'programada_para' puesto al crearla y sin línea de plan.
    No hay nada que arrastrar: valen los defaults del modelo.
    """
    orden = _orden(org_a, version_a, 9214)
    orden.programada_para = MIER
    orden.save(update_fields=["programada_para"])

    reprogramar_orden(org=org_a, orden=orden, programada_para=VIER,
                      programacion_destino=plan_a, actor=gestor_a[1])

    linea = ProgramacionOrden.objects.get(orden=orden)
    assert linea.secuencia == ProgramacionOrden._meta.get_field(
        "secuencia").default
    assert linea.prioridad == ProgramacionOrden._meta.get_field(
        "prioridad").default
    assert linea.zona == ""


# ===========================================================================
#  3  --  I-1 en revisar_coherencia
# ===========================================================================
@pytest.mark.django_db
def test_3_una_sola_linea_vigente_no_produce_error(org_a, version_a, plan_a,
                                                   gestor_a):
    orden = _orden(org_a, version_a, 9220)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    assert revisar_coherencia(plan_a) == []


@pytest.mark.django_db
def test_3b_una_reprogramada_no_es_falso_positivo(org_a, version_a, plan_a,
                                                  gestor_a):
    """
    Tras una reprogramación entre planes quedan DOS filas, pero una está
    'reprogramada'. 'Vigente' es la definición del modelo --planificada o
    confirmada-- y la historia no cuenta.
    """
    orden = _orden(org_a, version_a, 9221)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    orden.refresh_from_db()
    plan_b = _plan(org_a, lunes=SEM2)
    reprogramar_orden(org=org_a, orden=orden, programada_para=MAR2,
                      programacion_destino=plan_b, actor=gestor_a[1])

    assert ProgramacionOrden.objects.filter(orden=orden).count() == 2
    assert revisar_coherencia(plan_a) == []
    assert revisar_coherencia(plan_b) == []


@pytest.mark.django_db
def test_3c_dos_lineas_vigentes_en_planes_distintos_son_ERROR(
        org_a, version_a, plan_a, gestor_a):
    """
    La incoherencia se fabrica por la vía que los servicios no pueden producir:
    escribiendo la segunda línea directo, como haría el panel de Django.
    """
    orden = _orden(org_a, version_a, 9222)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    orden.refresh_from_db()
    plan_b = _plan(org_a, lunes=SEM2)
    ProgramacionOrden.objects.create(
        org=org_a, programacion=plan_b, orden=orden,
        dia=MAR2.date(), estado=ProgramacionOrden.PLANIFICADA)

    problemas = revisar_coherencia(plan_a)
    assert len(problemas) == 1
    p = problemas[0]
    #  El mensaje identifica OT, líneas y planes.
    assert "OT #9222" in p
    assert "2 lineas vigentes" in p
    assert str(plan_a.semana_inicio) in p and str(plan_b.semana_inicio) in p
    assert "no lo elige" in p

    #  Y se detecta desde CUALQUIERA de los dos planes: cruza planes.
    #
    #  Desde plan_b hay DOS problemas, y los dos son ciertos: la linea escrita
    #  a mano tambien deja incoherente el dia contra 'programada_para', que
    #  sigue apuntando a la fecha original. 'revisar_coherencia' devuelve
    #  TODOS, asi que se afirma que I-1 esta entre ellos, no cuantos hay.
    desde_b = revisar_coherencia(plan_b)
    assert any("2 lineas vigentes" in x for x in desde_b), desde_b
    assert any("el plan dice" in x for x in desde_b), desde_b


@pytest.mark.django_db
def test_3d_dos_vigentes_bloquean_la_publicacion(cliente_a, org_a, version_a,
                                                 plan_a, gestor_a):
    orden = _orden(org_a, version_a, 9223)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    orden.refresh_from_db()
    plan_b = _plan(org_a, lunes=SEM2)
    ProgramacionOrden.objects.create(
        org=org_a, programacion=plan_b, orden=orden,
        dia=MAR2.date(), estado=ProgramacionOrden.PLANIFICADA)

    r = cliente_a.post(f"/api/operaciones/programacion/{plan_a.id}/publicar/",
                       {}, format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "PLAN_INCOHERENTE"
    assert any("2 lineas vigentes" in x for x in r.json()["problemas"])

    #  ERROR, no aviso: el plan NO se publicó, y nada se corrigió.
    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.BORRADOR
    assert ProgramacionOrden.objects.filter(
        orden=orden, estado=ProgramacionOrden.PLANIFICADA).count() == 2


@pytest.mark.django_db
def test_3e_no_resuelve_ni_borra_nada(org_a, version_a, plan_a, gestor_a):
    orden = _orden(org_a, version_a, 9224)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    orden.refresh_from_db()
    plan_b = _plan(org_a, lunes=SEM2)
    ProgramacionOrden.objects.create(
        org=org_a, programacion=plan_b, orden=orden,
        dia=MAR2.date(), estado=ProgramacionOrden.PLANIFICADA)
    ids = set(ProgramacionOrden.objects.values_list("id", flat=True))
    fecha = OrdenTrabajo.objects.get(pk=orden.pk).programada_para

    revisar_coherencia(plan_a)
    revisar_coherencia(plan_b)

    assert set(ProgramacionOrden.objects.values_list("id", flat=True)) == ids
    assert OrdenTrabajo.objects.get(pk=orden.pk).programada_para == fecha


@pytest.mark.django_db
def test_3f_un_plan_vacio_sigue_siendo_coherente(plan_a):
    assert revisar_coherencia(plan_a) == []


@pytest.mark.django_db
def test_3g_la_deteccion_no_cruza_organizaciones(org_a, org_b, version_a,
                                                 plan_a, gestor_a):
    """Dos organizaciones pueden tener cada una su línea sin interferir."""
    orden = _orden(org_a, version_a, 9225)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])

    version_b = _version(org_b, "d32_ob")
    plan_ob = _plan(org_b)
    ub = User.objects.create_user(email="jefe.b@d32.test", password="x12345678")
    pb = Profile.objects.create(user=ub, org=org_b, role="OPERACIONES",
                                is_active=True)
    orden_b = _orden(org_b, version_b, 9226)
    programar_orden(org=org_b, orden=orden_b, programacion=plan_ob,
                    programada_para=MIER, actor=pb)

    assert revisar_coherencia(plan_a) == []
    assert revisar_coherencia(plan_ob) == []


# ===========================================================================
#  4  --  updated_by
# ===========================================================================
@pytest.mark.django_db
def test_4_programar_persiste_updated_by(cliente_a, org_a, version_a, plan_a,
                                         gestor_a):
    """
    Por PETICIÓN REAL: 'crum' solo tiene usuario dentro del ciclo de request.
    Llamar al servicio directo mediría otra cosa.
    """
    orden = _orden(org_a, version_a, 9230)
    assert orden.updated_by_id is None
    revision_antes = orden.revision

    r = cliente_a.post(f"/api/campo/trabajos/{orden.id}/programar/",
                       _cuerpo(plan_a, MIER), format="json")
    assert r.status_code == 201

    orden.refresh_from_db()
    assert orden.updated_by_id == gestor_a[0].id    # el actor real
    assert orden.programada_para == MIER            # no se perdió la programación
    assert orden.revision == revision_antes + 1     # revision sigue funcionando
    assert ProgramacionOrden.objects.filter(orden=orden).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_4b_updated_by_leido_desde_fuera_del_orm(cliente_a, org_a, version_a,
                                                 plan_a, gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    orden = _orden(org_a, version_a, 9231)
    assert cliente_a.post(f"/api/campo/trabajos/{orden.id}/programar/",
                          _cuerpo(plan_a, MIER), format="json").status_code == 201

    f = _desde_fuera(
        "select updated_by_id, programada_para, revision "
        "from campo_orden_trabajo where id = %s", [str(orden.id)])[0]
    assert str(f["updated_by_id"]) == str(gestor_a[0].id)
    assert f["programada_para"] is not None


@pytest.mark.django_db
def test_4c_reprogramar_tambien_lo_persiste(cliente_a, org_a, version_a,
                                            plan_a, gestor_a):
    orden = _orden(org_a, version_a, 9232)
    cliente_a.post(f"/api/campo/trabajos/{orden.id}/programar/",
                   _cuerpo(plan_a, MIER), format="json")
    cliente_a.post(_url(orden), _cuerpo(plan_a, VIER), format="json")
    orden.refresh_from_db()
    assert orden.updated_by_id == gestor_a[0].id
    assert orden.programada_para == VIER


@pytest.mark.django_db
def test_4d_fuera_de_una_peticion_no_cambia_nada(org_a, version_a, plan_a,
                                                 gestor_a):
    """
    Sin request, 'crum' no tiene usuario: 'BaseModel.save' ni entra en la rama
    que asigna, y el UPDATE escribe el valor que el campo ya tenía. Nombrar
    'updated_by' en update_fields NO cambia el comportamiento de estos objetos.
    """
    orden = _orden(org_a, version_a, 9233)
    assert orden.updated_by_id is None

    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])

    orden.refresh_from_db()
    assert orden.updated_by_id is None       # sigue siendo None, no falla
    assert orden.programada_para == MIER
