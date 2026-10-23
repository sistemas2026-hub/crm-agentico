# -*- coding: utf-8 -*-
"""
================================================================================
 M03-D3  --  reprogramación: normal, corrección y contingencia
================================================================================

Lo que estas pruebas afirman no es que la fecha cambie —eso es trivial— sino las
cuatro cosas que rodean el cambio:

  * que lo que dejó de ser cierto QUEDE, y se pueda leer desde fuera del ORM;
  * que una orden en curso NO entre por la ruta normal, ni siquiera por error;
  * que un trabajo devuelto por corrección SÍ pueda recibir fecha nueva;
  * que nada se escriba a medias.

MÉTODO
------
La escalera hasta 'correccion_requerida' se recorre por los SERVICIOS REALES
(ejecutar_accion_operativa → completar_campo → requerir_correccion), no
fabricando eventos a mano: si se fabricaran, la prueba mediría mi idea de cómo
se llega ahí en vez de cómo se llega de verdad.
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
from campo.services.transiciones import (completar_campo,
                                         ejecutar_accion_operativa,
                                         requerir_correccion)
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones.models import (NovedadOperativa, ProgramacionOrden,
                                ProgramacionSemanal)
from operaciones.programacion import (ErrorProgramacion, NoEstaProgramada,
                                      RequiereContingencia, YaEnEsaFecha,
                                      clasificar_ruta, programar_orden,
                                      registrar_contingencia,
                                      reprogramar_orden)

LUNES = date(2026, 10, 5)
SEM2 = LUNES + timedelta(weeks=1)


def _dt(lunes, dias, hora=9):
    return timezone.make_aware(
        datetime.combine(lunes + timedelta(days=dias), time(hora, 0)))


MIER = _dt(LUNES, 2)
VIER = _dt(LUNES, 4)
MAR2 = _dt(SEM2, 1, 14)


# ---------------------------------------------------------------------------
#  Datos
# ---------------------------------------------------------------------------
def _version(org, codigo):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=f"Tipo {codigo}")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        #  'evidencias' no es decorativo: 'requerir_correccion' valida los
        #  requisitos contra la plantilla inmutable de la orden.
        esquema={"campos": [], "evidencias": [{"id": "foto_ont",
                                               "tipo": "foto",
                                               "titulo": "ONT"}]})


def _orden(org, version, numero):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Cliente M03-D3", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA)


def _plan(org, lunes=LUNES, estado=ProgramacionSemanal.BORRADOR):
    return ProgramacionSemanal.objects.create(
        org=org, semana_inicio=lunes, estado=estado)


def _gestor(org, correo):
    u = User.objects.create_user(email=correo, password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role="OPERACIONES",
                                     is_active=True)


def _cliente(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


@pytest.fixture
def version_a(org_a):
    return _version(org_a, "m03d3_a")


@pytest.fixture
def plan_a(org_a):
    return _plan(org_a)


@pytest.fixture
def gestor_a(org_a):
    return _gestor(org_a, "jefe.a@m03d3.test")


@pytest.fixture
def cliente_a(org_a, gestor_a):
    return _cliente(gestor_a[0], org_a, gestor_a[1])


@pytest.fixture
def programada(org_a, version_a, plan_a, gestor_a):
    """Una OT asignada y ya programada para el miércoles, por la vía de M03-B."""
    orden = _orden(org_a, version_a, 9101)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    orden.refresh_from_db()
    return orden


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


def _hasta_correccion(orden, profile):
    """
    Recorre la escalera REAL hasta 'correccion_requerida'.

    asignada -> en_camino -> en_sitio -> completada_campo -> correccion_requerida
    """
    ejecutar_accion_operativa(orden, "marcar_en_camino", profile)
    ejecutar_accion_operativa(orden, "marcar_llegada", profile)
    completar_campo(orden, profile)
    requerir_correccion(orden, ["foto_ont"], profile, "faltó la foto")
    orden.refresh_from_db()
    return orden


# ===========================================================================
#  1-2  --  ruta normal
# ===========================================================================
@pytest.mark.django_db
def test_1_misma_semana_actualiza_la_linea(cliente_a, programada, plan_a):
    """
    La constraint unique(programacion, orden) impide una 2ª línea en el mismo
    plan, así que dentro de una semana la línea se ACTUALIZA. El historial no
    se pierde: vive en el evento, que es append-only.
    """
    linea_antes = ProgramacionOrden.objects.get(orden=programada)

    r = cliente_a.post(_url(programada), _cuerpo(plan_a, VIER), format="json")
    assert r.status_code == 200, r.content[:400]

    programada.refresh_from_db()
    assert programada.programada_para == VIER
    assert ProgramacionOrden.objects.filter(orden=programada).count() == 1

    linea_antes.refresh_from_db()
    assert linea_antes.dia == VIER.date()
    assert linea_antes.estado == ProgramacionOrden.PLANIFICADA

    ev = EventoTrabajo.objects.get(orden=programada, tipo="reprogramacion")
    assert ev.datos["ruta"] == "normal"
    assert ev.datos["anterior"]["dia"] == str(MIER.date())
    assert ev.datos["nuevo"]["dia"] == str(VIER.date())
    assert ev.datos["anterior"]["plan"] == ev.datos["nuevo"]["plan"]


@pytest.mark.django_db
def test_2_otra_semana_marca_la_anterior_y_crea_una_nueva(
        cliente_a, org_a, programada, plan_a):
    plan_b = _plan(org_a, lunes=SEM2)
    linea_vieja = ProgramacionOrden.objects.get(orden=programada)

    r = cliente_a.post(_url(programada), _cuerpo(plan_b, MAR2), format="json")
    assert r.status_code == 200, r.content[:400]

    linea_vieja.refresh_from_db()
    assert linea_vieja.estado == ProgramacionOrden.REPROGRAMADA
    assert linea_vieja.dia == MIER.date()      # la vieja NO se toca
    assert linea_vieja.programacion_id == plan_a.id   # NUNCA cambia de plan

    nueva = ProgramacionOrden.objects.get(orden=programada,
                                          estado=ProgramacionOrden.PLANIFICADA)
    assert nueva.programacion_id == plan_b.id
    assert nueva.dia == MAR2.date()

    programada.refresh_from_db()
    assert programada.programada_para == MAR2
    #  I-1: una sola línea vigente
    assert ProgramacionOrden.objects.filter(
        orden=programada,
        estado__in=(ProgramacionOrden.PLANIFICADA,
                    ProgramacionOrden.CONFIRMADA)).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_2b_persistencia_leida_desde_fuera_del_orm(cliente_a, org_a,
                                                   version_a, plan_a, gestor_a):
    #  'transaction=True' NO es decorativo: sin commit, una conexion
    #  independiente no ve nada y la prueba mediria el aislamiento de
    #  PostgreSQL en vez de lo que dice medir.
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    orden = _orden(org_a, version_a, 9102)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    orden.refresh_from_db()
    assert cliente_a.post(_url(orden), _cuerpo(plan_a, VIER),
                          format="json").status_code == 200

    f = _desde_fuera(
        "select po.dia, po.estado, o.programada_para, o.revision "
        "from operaciones_programacion_orden po "
        "join campo_orden_trabajo o on o.id = po.orden_id "
        "where po.orden_id = %s", [str(orden.id)])
    assert len(f) == 1
    assert f[0]["dia"] == VIER.date()
    #  I-2: la línea y programada_para dicen el mismo día
    assert f[0]["dia"] == timezone.localtime(f[0]["programada_para"]).date()


# ===========================================================================
#  3-4  --  motivo: obligatorio con compromiso, no en borrador
# ===========================================================================
@pytest.mark.django_db
def test_3_borrador_no_exige_causa(cliente_a, programada, plan_a):
    r = cliente_a.post(_url(programada), _cuerpo(plan_a, VIER), format="json")
    assert r.status_code == 200
    assert NovedadOperativa.objects.count() == 0
    ev = EventoTrabajo.objects.get(orden=programada, tipo="reprogramacion")
    assert ev.datos["causa"] == ""


@pytest.mark.django_db
def test_4_plan_publicado_exige_causa(cliente_a, org_a, programada, plan_a):
    plan_a.estado = ProgramacionSemanal.PUBLICADA
    plan_a.save(update_fields=["estado"])

    r = cliente_a.post(_url(programada), _cuerpo(plan_a, VIER), format="json")
    assert r.status_code == 400
    assert "por que" in r.json()["detalle"] or "por qué" in r.json()["detalle"]

    #  NADA se escribió.
    programada.refresh_from_db()
    assert programada.programada_para == MIER
    assert ProgramacionOrden.objects.get(orden=programada).dia == MIER.date()
    assert EventoTrabajo.objects.filter(tipo="reprogramacion").count() == 0


@pytest.mark.django_db
def test_4b_con_causa_el_plan_publicado_si_admite_la_reprogramacion(
        cliente_a, org_a, programada, plan_a):
    plan_a.estado = ProgramacionSemanal.PUBLICADA
    plan_a.save(update_fields=["estado"])

    r = cliente_a.post(_url(programada),
                       _cuerpo(plan_a, VIER, causa="ausencia",
                               motivo="el técnico se incapacitó"),
                       format="json")
    assert r.status_code == 200

    nov = NovedadOperativa.objects.get(orden=programada)
    #  Decisión C: la causa va en 'tipo'; NUNCA 'reprogramacion'.
    assert nov.tipo == NovedadOperativa.AUSENCIA
    assert nov.tipo != NovedadOperativa.REPROGRAMACION
    assert nov.programada_anterior == MIER
    assert nov.programada_nueva == VIER
    assert nov.registrada_por_id is not None

    ev = EventoTrabajo.objects.get(orden=programada, tipo="reprogramacion")
    assert ev.datos["novedad"] == str(nov.id)
    assert ev.datos["anterior"]["plan_estado"] == "publicada"


@pytest.mark.django_db
def test_4c_reprogramacion_no_sirve_como_causa(org_a, programada, plan_a,
                                               gestor_a):
    plan_a.estado = ProgramacionSemanal.PUBLICADA
    plan_a.save(update_fields=["estado"])
    with pytest.raises(ErrorProgramacion) as e:
        reprogramar_orden(org=org_a, orden=programada, programada_para=VIER,
                          programacion_destino=plan_a, actor=gestor_a[1],
                          causa=NovedadOperativa.REPROGRAMACION)
    assert "el efecto, no la causa" in str(e.value)
    assert NovedadOperativa.objects.count() == 0


# ===========================================================================
#  5  --  adición a un plan publicado (ajuste de M03-B)
# ===========================================================================
@pytest.mark.django_db
def test_5_agregar_a_un_plan_publicado_es_adicion_formal(
        cliente_a, org_a, version_a, gestor_a):
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    orden = _orden(org_a, version_a, 9103)

    #  sin causa -> rechazo
    sin = cliente_a.post(f"/api/campo/trabajos/{orden.id}/programar/",
                         _cuerpo(publicado, MIER), format="json")
    assert sin.status_code == 400
    assert ProgramacionOrden.objects.count() == 0

    #  con causa -> 201 y evento distinto
    con = cliente_a.post(f"/api/campo/trabajos/{orden.id}/programar/",
                         _cuerpo(publicado, MIER, causa="cambio_de_prioridad",
                                 motivo="entró un urgente"), format="json")
    assert con.status_code == 201, con.content[:300]

    ev = EventoTrabajo.objects.get(orden=orden, tipo="adicion_a_plan_publicado")
    assert ev.datos["anterior"] is None      # agregar no tiene fecha previa
    assert ev.datos["causa"] == "cambio_de_prioridad"
    assert ev.datos["estado_del_plan"] == "publicada"


@pytest.mark.django_db
def test_5b_el_borrador_sigue_sin_exigir_nada(cliente_a, org_a, version_a,
                                              plan_a):
    """La conducta que M03-B dejó validada no cambia."""
    orden = _orden(org_a, version_a, 9104)
    r = cliente_a.post(f"/api/campo/trabajos/{orden.id}/programar/",
                       _cuerpo(plan_a, MIER), format="json")
    assert r.status_code == 201
    assert EventoTrabajo.objects.filter(orden=orden,
                                        tipo="programacion").count() == 1
    assert NovedadOperativa.objects.count() == 0


# ===========================================================================
#  6-7  --  ruta de corrección
# ===========================================================================
@pytest.mark.django_db
def test_6_una_orden_devuelta_por_correccion_recibe_fecha_nueva(
        cliente_a, org_a, programada, plan_a, gestor_a):
    """
    El caso que la regla anterior hacía imposible.

    'iniciada_en' se escribe una sola vez, así que anclar la frontera ahí
    dejaba un trabajo devuelto sin poder recibir fecha NUNCA MÁS.
    """
    orden = _hasta_correccion(programada, gestor_a[1])
    assert orden.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA
    assert orden.iniciada_en is not None
    assert orden.vuelta == 2
    assert clasificar_ruta(orden) == "correccion"

    iniciada_antes = orden.iniciada_en

    r = cliente_a.post(_url(orden),
                       _cuerpo(plan_a, VIER, causa="dato_incompleto",
                               motivo="hay que volver con la foto"),
                       format="json")
    assert r.status_code == 200, r.content[:400]

    orden.refresh_from_db()
    assert orden.programada_para == VIER
    #  'iniciada_en' NO se toca: es el primer inicio histórico.
    assert orden.iniciada_en == iniciada_antes
    #  Y el estado tampoco: reprogramar no es una transición.
    assert orden.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA

    ev = EventoTrabajo.objects.get(orden=orden,
                                   tipo="reprogramacion_por_correccion")
    assert ev.datos["ruta"] == "correccion"
    assert ev.datos["vuelta"] == 2


@pytest.mark.django_db
def test_6b_la_correccion_siempre_exige_causa(cliente_a, programada, plan_a,
                                              gestor_a):
    orden = _hasta_correccion(programada, gestor_a[1])
    r = cliente_a.post(_url(orden), _cuerpo(plan_a, VIER), format="json")
    assert r.status_code == 400
    orden.refresh_from_db()
    assert orden.programada_para == MIER


@pytest.mark.django_db
def test_7_si_la_nueva_vuelta_ya_arranco_vuelve_a_ser_contingencia(
        cliente_a, programada, plan_a, gestor_a):
    orden = _hasta_correccion(programada, gestor_a[1])
    eventos_antes = EventoTrabajo.objects.filter(orden=orden).count()

    #  el técnico vuelve a salir: la vuelta 2 ya empezó
    ejecutar_accion_operativa(orden, "marcar_en_camino", gestor_a[1])
    orden.refresh_from_db()
    assert clasificar_ruta(orden) == "contingencia"

    r = cliente_a.post(_url(orden), _cuerpo(plan_a, VIER, causa="bloqueo"),
                       format="json")
    assert r.status_code == 409
    assert r.json()["error"] == "REQUIERE_CONTINGENCIA"

    orden.refresh_from_db()
    assert orden.programada_para == MIER
    #  Y ningún evento histórico desapareció.
    assert EventoTrabajo.objects.filter(orden=orden).count() > eventos_antes


# ===========================================================================
#  8-9  --  contingencia
# ===========================================================================
@pytest.mark.django_db
def test_8_una_orden_en_curso_no_entra_por_la_ruta_normal(
        cliente_a, programada, plan_a, gestor_a):
    ejecutar_accion_operativa(programada, "marcar_llegada", gestor_a[1])
    programada.refresh_from_db()
    assert clasificar_ruta(programada) == "contingencia"

    r = cliente_a.post(_url(programada), _cuerpo(plan_a, VIER, causa="bloqueo"),
                       format="json")
    assert r.status_code == 409
    assert r.json()["error"] == "REQUIERE_CONTINGENCIA"
    assert "contingencia" in r.json()["siguiente"]

    programada.refresh_from_db()
    assert programada.programada_para == MIER
    assert ProgramacionOrden.objects.filter(orden=programada).count() == 1


@pytest.mark.django_db
def test_9_la_contingencia_registra_y_no_reprograma(cliente_a, programada,
                                                    gestor_a):
    ejecutar_accion_operativa(programada, "marcar_llegada", gestor_a[1])
    programada.refresh_from_db()
    revision_antes = programada.revision
    linea_antes = ProgramacionOrden.objects.get(orden=programada)

    r = cliente_a.post(_url(programada, "contingencia"),
                       {"causa": "falta_material",
                        "motivo": "no llegó el drop"}, format="json")
    assert r.status_code == 201, r.content[:300]

    nov = NovedadOperativa.objects.get(orden=programada)
    assert nov.tipo == NovedadOperativa.FALTA_MATERIAL
    assert nov.programada_anterior == MIER
    #  Una contingencia NO propone fecha nueva.
    assert nov.programada_nueva is None

    programada.refresh_from_db()
    linea_antes.refresh_from_db()
    assert programada.programada_para == MIER          # intacto
    assert programada.estado_operativo == OrdenTrabajo.EN_SITIO
    assert programada.revision == revision_antes       # nada que re-sincronizar
    assert linea_antes.dia == MIER.date()
    assert linea_antes.estado == ProgramacionOrden.PLANIFICADA

    ev = EventoTrabajo.objects.get(orden=programada, tipo="contingencia")
    assert ev.datos["nuevo"] is None
    assert ev.datos["ruta"] == "contingencia"


@pytest.mark.django_db
def test_9b_la_contingencia_exige_causa(cliente_a, programada, gestor_a):
    ejecutar_accion_operativa(programada, "marcar_llegada", gestor_a[1])
    r = cliente_a.post(_url(programada, "contingencia"),
                       {"causa": ""}, format="json")
    assert r.status_code == 400
    assert NovedadOperativa.objects.count() == 0


# ===========================================================================
#  10  --  concurrencia
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_10_dos_reprogramaciones_simultaneas_dejan_una_sola_linea_vigente(
        org_a, version_a, gestor_a):
    """
    Dos supervisores mueven la MISMA orden a DOS SEMANAS DISTINTAS a la vez.

    POR QUE A DOS PLANES Y NO A DOS DIAS DE LA MISMA SEMANA
    -------------------------------------------------------
    La primera version de esta prueba movia la orden a dos dias de la misma
    semana, y PASABA CON EL LOCK DESARMADO -- medido. Dentro de un plan la
    constraint obliga a ACTUALIZAR la unica linea, asi que los dos hilos pisan
    la misma fila y el estado final queda coherente igual: hay actualizacion
    perdida, pero no incoherencia, y la prueba no veia nada.

    Con dos planes destino distintos, sin lock los dos hilos leen la misma
    linea vigente, los dos la marcan 'reprogramada' y cada uno crea la suya:
    la orden termina con DOS lineas vigentes y la invariante I-1 se rompe.
    """
    if connection.vendor != "postgresql":
        pytest.skip("la concurrencia real requiere PostgreSQL")

    u, perfil = gestor_a
    origen = _plan(org_a)
    destino_1 = _plan(org_a, lunes=SEM2)
    destino_2 = _plan(org_a, lunes=SEM2 + timedelta(weeks=1))
    orden = _orden(org_a, version_a, 9110)
    programar_orden(org=org_a, orden=orden, programacion=origen,
                    programada_para=MIER, actor=perfil)
    orden.refresh_from_db()
    cli = _cliente(u, org_a, perfil)

    def mueve(par):
        plan, cuando = par
        try:
            return cli.post(_url(orden), _cuerpo(plan, cuando),
                            format="json").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(
            mueve, [(destino_1, _dt(SEM2, 1, 14)),
                    (destino_2, _dt(SEM2 + timedelta(weeks=1), 1, 14))]))

    #  Las dos peticiones son legitimas por separado; lo que no puede pasar es
    #  que las dos queden vigentes.
    assert 200 in codigos, codigos

    orden.refresh_from_db()
    vigentes = ProgramacionOrden.objects.filter(
        orden=orden, estado__in=(ProgramacionOrden.PLANIFICADA,
                                 ProgramacionOrden.CONFIRMADA))
    #  I-1
    assert vigentes.count() == 1, (
        f"quedaron {vigentes.count()} lineas vigentes; codigos={codigos}")
    #  I-2: la linea vigente y programada_para dicen el mismo dia
    assert vigentes.first().dia == timezone.localtime(
        orden.programada_para).date()


# ===========================================================================
#  11  --  rollback
# ===========================================================================
@pytest.mark.django_db
def test_11_rollback_no_deja_estado_parcial(org_a, programada, plan_a,
                                            gestor_a):
    """Se rompe la operación en el ÚLTIMO paso, con todo lo demás ya escrito."""
    with mock.patch.object(EventoTrabajo.objects, "create",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            reprogramar_orden(org=org_a, orden=programada, programada_para=VIER,
                              programacion_destino=plan_a, actor=gestor_a[1])

    programada.refresh_from_db()
    assert programada.programada_para == MIER
    assert ProgramacionOrden.objects.get(orden=programada).dia == MIER.date()
    assert NovedadOperativa.objects.count() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_11b_el_rollback_se_ve_desde_fuera(org_a, version_a, plan_a, gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    orden = _orden(org_a, version_a, 9111)
    programar_orden(org=org_a, orden=orden, programacion=plan_a,
                    programada_para=MIER, actor=gestor_a[1])
    orden.refresh_from_db()
    plan_b = _plan(org_a, lunes=SEM2)

    with mock.patch.object(EventoTrabajo.objects, "create",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            reprogramar_orden(org=org_a, orden=orden, programada_para=MAR2,
                              programacion_destino=plan_b, actor=gestor_a[1])

    f = _desde_fuera(
        "select o.programada_para, "
        "(select count(*) from operaciones_programacion_orden po "
        "  where po.orden_id = o.id) lineas, "
        "(select count(*) from operaciones_programacion_orden po "
        "  where po.orden_id = o.id and po.estado = 'reprogramada') marcadas "
        "from campo_orden_trabajo o where o.id = %s", [str(orden.id)])[0]
    assert f["programada_para"] == MIER
    assert f["lineas"] == 1
    assert f["marcadas"] == 0


# ===========================================================================
#  12  --  multi-tenant
# ===========================================================================
@pytest.mark.django_db
def test_12_cross_tenant(cliente_a, org_a, org_b, programada):
    version_b = _version(org_b, "m03d3_b")
    plan_b = _plan(org_b)
    orden_b = _orden(org_b, version_b, 9120)
    ub, pb = _gestor(org_b, "jefe.b@m03d3.test")
    programar_orden(org=org_b, orden=orden_b, programacion=plan_b,
                    programada_para=MIER, actor=pb)
    orden_b.refresh_from_db()

    #  A -> orden de B
    assert cliente_a.post(_url(orden_b), _cuerpo(plan_b, VIER),
                          format="json").status_code == 404
    #  A -> su orden, plan de B
    assert cliente_a.post(_url(programada), _cuerpo(plan_b, VIER),
                          format="json").status_code == 404
    #  B -> lo suyo
    assert _cliente(ub, org_b, pb).post(
        _url(orden_b), _cuerpo(plan_b, VIER), format="json").status_code == 200

    programada.refresh_from_db()
    assert programada.programada_para == MIER


@pytest.mark.django_db
def test_12b_el_servicio_no_confia_en_la_vista(org_a, org_b, programada,
                                               gestor_a):
    plan_b = _plan(org_b)
    with pytest.raises(ErrorProgramacion) as e:
        reprogramar_orden(org=org_a, orden=programada, programada_para=VIER,
                          programacion_destino=plan_b, actor=gestor_a[1])
    assert "otra empresa" in str(e.value)


@pytest.mark.django_db
def test_12c_el_organization_id_del_cuerpo_no_decide(cliente_a, org_b,
                                                     programada, plan_a):
    cuerpo = _cuerpo(plan_a, VIER)
    cuerpo["organization_id"] = str(org_b.id)
    cuerpo["org"] = str(org_b.id)
    assert cliente_a.post(_url(programada), cuerpo,
                          format="json").status_code == 200
    assert ProgramacionOrden.objects.filter(org=org_b).count() == 0


# ===========================================================================
#  13-14  --  rechazos
# ===========================================================================
@pytest.mark.django_db
def test_13_una_orden_sin_programacion_no_se_reprograma(cliente_a, org_a,
                                                        version_a, plan_a):
    orden = _orden(org_a, version_a, 9130)
    r = cliente_a.post(_url(orden), _cuerpo(plan_a, VIER), format="json")
    assert r.status_code == 409
    assert r.json()["error"] == "NO_ESTA_PROGRAMADA"
    assert "programar" in r.json()["siguiente"]
    assert ProgramacionOrden.objects.count() == 0


@pytest.mark.django_db
def test_14_no_se_puede_dejar_dos_lineas_en_el_mismo_plan(
        cliente_a, org_a, programada, plan_a):
    """Ida y vuelta: al volver, el plan de origen ya tiene una línea marcada."""
    plan_b = _plan(org_a, lunes=SEM2)
    assert cliente_a.post(_url(programada), _cuerpo(plan_b, MAR2),
                          format="json").status_code == 200

    r = cliente_a.post(_url(programada), _cuerpo(plan_a, VIER), format="json")
    assert r.status_code == 400
    assert "una sola por plan" in r.json()["detalle"]

    programada.refresh_from_db()
    assert programada.programada_para == MAR2
    assert ProgramacionOrden.objects.filter(orden=programada).count() == 2


@pytest.mark.django_db
def test_14b_una_orden_terminada_no_se_reprograma(cliente_a, programada,
                                                  plan_a, gestor_a):
    ejecutar_accion_operativa(programada, "cancelar", gestor_a[1])
    programada.refresh_from_db()
    r = cliente_a.post(_url(programada), _cuerpo(plan_a, VIER, causa="bloqueo"),
                       format="json")
    assert r.status_code in (400, 409)
    programada.refresh_from_db()
    assert programada.programada_para == MIER


# ===========================================================================
#  15  --  SLA
# ===========================================================================
@pytest.mark.django_db
def test_15_el_sla_se_registra_como_no_evaluado_y_no_bloquea(
        cliente_a, programada, plan_a):
    lejos = _dt(LUNES, 4, 23)
    r = cliente_a.post(_url(programada), _cuerpo(plan_a, lejos), format="json")
    assert r.status_code == 200      # NUNCA se bloquea por SLA

    ev = EventoTrabajo.objects.get(orden=programada, tipo="reprogramacion")
    assert ev.datos["sla"]["evaluado"] is False
    assert ev.datos["sla"]["razon"] == "la orden no tiene caso vinculado"


@pytest.mark.django_db
def test_15b_con_referencia_de_caso_por_texto_tampoco_se_evalua(
        cliente_a, programada, plan_a):
    """El puente OT->Case es texto, no FK. Se dice, en vez de disimularlo."""
    programada.origen_sistema = "crm"
    programada.origen_tipo = "case"
    programada.origen_ref = "algun-uuid-de-caso"
    programada.save(update_fields=["origen_sistema", "origen_tipo",
                                   "origen_ref"])
    assert cliente_a.post(_url(programada), _cuerpo(plan_a, VIER),
                          format="json").status_code == 200

    ev = EventoTrabajo.objects.get(orden=programada, tipo="reprogramacion")
    assert ev.datos["sla"]["evaluado"] is False
    assert "no existe vinculo" in ev.datos["sla"]["razon"]


# ===========================================================================
#  16  --  idempotencia
# ===========================================================================
@pytest.mark.django_db
def test_16_la_misma_clave_no_reprograma_dos_veces(cliente_a, programada,
                                                   plan_a):
    cuerpo = _cuerpo(plan_a, VIER)
    p = cliente_a.post(_url(programada), cuerpo, format="json",
                       HTTP_IDEMPOTENCY_KEY="m03d3-clave-1")
    assert p.status_code == 200

    s = cliente_a.post(_url(programada), cuerpo, format="json",
                       HTTP_IDEMPOTENCY_KEY="m03d3-clave-1")
    assert s.status_code == 200
    assert s.get("Idempotent-Replay") == "true"

    #  Un solo evento: la segunda no ejecutó nada.
    assert EventoTrabajo.objects.filter(orden=programada,
                                        tipo="reprogramacion").count() == 1


# ===========================================================================
#  17  --  YaEnEsaFecha  [BLOQUEADO: decisión empresarial pendiente]
# ===========================================================================
@pytest.mark.django_db
def test_17_misma_fecha_y_mismo_plan_se_rechaza(cliente_a, programada, plan_a):
    """
    M03-D2 dejó este caso PENDIENTE de decisión empresarial.

    Se rechaza porque es la única salida REVERSIBLE: aceptarlo escribiría en
    una bitácora append-only un cambio que no ocurrió, y eso no se puede
    quitar después. La respuesta lo declara con 'pendiente'.
    """
    r = cliente_a.post(_url(programada), _cuerpo(plan_a, MIER), format="json")
    assert r.status_code == 409
    assert r.json()["error"] == "YA_EN_ESA_FECHA"
    assert r.json()["pendiente"] == "DECISION_EMPRESARIAL_YaEnEsaFecha"
    assert EventoTrabajo.objects.filter(tipo="reprogramacion").count() == 0


# ===========================================================================
#  Permisos y alcance
# ===========================================================================
@pytest.mark.django_db
def test_un_tecnico_no_reprograma(org_a, programada, plan_a, regular_user,
                                  user_profile):
    cli = _cliente(regular_user, org_a, user_profile)
    assert cli.post(_url(programada), _cuerpo(plan_a, VIER),
                    format="json").status_code == 403
    assert cli.post(_url(programada, "contingencia"), {"causa": "bloqueo"},
                    format="json").status_code == 403
    programada.refresh_from_db()
    assert programada.programada_para == MIER


@pytest.mark.django_db
def test_sin_sesion_no_se_reprograma(programada, plan_a):
    assert APIClient().post(_url(programada), _cuerpo(plan_a, VIER),
                            format="json").status_code in (401, 403)


@pytest.mark.django_db
def test_reprogramar_no_toca_asignaciones_ni_propuestas(cliente_a, programada,
                                                        plan_a):
    """Reprogramar cambia el CUÁNDO. El QUIÉN es otro módulo."""
    from operaciones.models import PropuestaSupervisor
    asignaciones = AsignacionTrabajo.objects.count()
    assert cliente_a.post(_url(programada), _cuerpo(plan_a, VIER),
                          format="json").status_code == 200
    assert AsignacionTrabajo.objects.count() == asignaciones
    assert PropuestaSupervisor.objects.count() == 0


@pytest.mark.django_db
def test_ningun_evento_historico_se_borra(cliente_a, programada, plan_a,
                                          gestor_a):
    orden = _hasta_correccion(programada, gestor_a[1])
    ids_antes = set(EventoTrabajo.objects.filter(orden=orden)
                    .values_list("id", flat=True))
    cliente_a.post(_url(orden), _cuerpo(plan_a, VIER, causa="dato_incompleto"),
                   format="json")
    ids_despues = set(EventoTrabajo.objects.filter(orden=orden)
                      .values_list("id", flat=True))
    assert ids_antes <= ids_despues          # solo se agrega
    assert len(ids_despues) > len(ids_antes)


# ===========================================================================
#  Efectos externos
# ===========================================================================
@pytest.mark.django_db
def test_ninguna_ruta_abre_una_conexion_saliente(cliente_a, programada, plan_a,
                                                 gestor_a):
    """El cero no se lee a ciegas: primero se comprueba que el contador DISPARA."""
    import http.client
    import socket

    destinos = []
    original = socket.socket.connect

    def vigilado(self, direccion):
        destinos.append(direccion)
        return original(self, direccion)

    socket.socket.connect = vigilado
    try:
        cliente_a.post(_url(programada), _cuerpo(plan_a, VIER), format="json")
        ejecutar_accion_operativa(programada, "marcar_llegada", gestor_a[1])
        cliente_a.post(_url(programada, "contingencia"),
                       {"causa": "bloqueo", "motivo": "x"}, format="json")
        durante = list(destinos)
        try:
            http.client.HTTPConnection("127.0.0.1", 9, timeout=2).request("GET", "/")
        except Exception:
            pass
        disparo = len(destinos) > len(durante)
    finally:
        socket.socket.connect = original

    assert disparo, "el instrumento no dispara: el 0 de abajo no probaría nada"
    externos = [d for d in durante
                if not (isinstance(d, tuple) and len(d) >= 2 and d[1] == 5432)]
    assert externos == []
