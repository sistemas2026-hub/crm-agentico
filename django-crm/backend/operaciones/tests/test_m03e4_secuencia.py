# -*- coding: utf-8 -*-
"""
================================================================================
 M03-E4  --  cambiar el orden propuesto de una línea
================================================================================

Cambiar la secuencia NO es reprogramar. Lo que estas pruebas afirman, además de
que el número cambie:

  * que NADA más cambie -- ni 'programada_para', ni el día, ni el plan, ni la
    zona, ni la prioridad, ni ninguna otra línea;
  * que 'secuencia = 0' signifique SIN SECUENCIAR, y que varios ceros no sean
    un empate;
  * que los duplicados > 0 se permitan y queden visibles;
  * que un plan publicado deje traza formal.

DECISIONES EMPRESARIALES APROBADAS que estas pruebas fijan: E-2 (el 0), E-1
(duplicados), E-4 (publicado no congela), E-5 (I-1 es independiente), E-6
(prioridad no ordena), E-7 (zona no ordena).
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

from campo.models import EventoTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones.models import (NovedadOperativa, ProgramacionOrden,
                                ProgramacionSemanal)
from operaciones.programacion import (ErrorProgramacion,
                                      actualizar_secuencia, programar_orden,
                                      reprogramar_orden, revisar_coherencia)

LUNES = date(2026, 10, 5)
SEM2 = LUNES + timedelta(weeks=1)
JORNADA = "/api/operaciones/programacion/jornada/"


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


def _orden(org, numero):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=_version(org, f"e4_{numero}"),
        cliente_nombre=f"Cliente {numero}", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA)


def _plan(org, lunes=LUNES, estado=ProgramacionSemanal.BORRADOR):
    return ProgramacionSemanal.objects.create(
        org=org, semana_inicio=lunes, estado=estado)


def _gestor(org, correo):
    u = User.objects.create_user(email=correo, password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role="OPERACIONES",
                                     is_active=True)


def _cli(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


@pytest.fixture
def plan_a(org_a):
    return _plan(org_a)


@pytest.fixture
def gestor_a(org_a):
    return _gestor(org_a, "jefe.a@e4.test")


@pytest.fixture
def cliente_a(org_a, gestor_a):
    return _cli(gestor_a[0], org_a, gestor_a[1])


def _linea(org, plan, numero, cuando, actor, secuencia=None, **extra):
    orden = _orden(org, numero)
    programar_orden(org=org, orden=orden, programacion=plan,
                    programada_para=cuando, actor=actor,
                    secuencia=secuencia, **extra)
    orden.refresh_from_db()
    return ProgramacionOrden.objects.get(orden=orden)


def _url(linea):
    return f"/api/operaciones/programacion/linea/{linea.id}/secuencia/"


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
#  1-4  --  los cuatro cambios básicos
# ===========================================================================
@pytest.mark.django_db
def test_1_de_cero_a_uno(cliente_a, org_a, plan_a, gestor_a):
    linea = _linea(org_a, plan_a, 9501, MIER, gestor_a[1])   # nace en 0
    assert linea.secuencia == 0

    r = cliente_a.post(_url(linea), {"secuencia": 1}, format="json")
    assert r.status_code == 200, r.content[:300]

    linea.refresh_from_db()
    assert linea.secuencia == 1
    ev = EventoTrabajo.objects.get(orden=linea.orden, tipo="secuencia")
    assert ev.datos["anterior"] == 0
    assert ev.datos["nuevo"] == 1
    assert ev.datos["anterior_sin_secuenciar"] is True
    assert ev.datos["nuevo_sin_secuenciar"] is False


@pytest.mark.django_db
def test_2_de_uno_a_cero_es_dessecuenciar(cliente_a, org_a, plan_a, gestor_a):
    """
    Poner 0 es una operación legítima: 'sin secuenciar' es un estado, no un
    error ni una posición.
    """
    linea = _linea(org_a, plan_a, 9502, MIER, gestor_a[1], secuencia=1)

    r = cliente_a.post(_url(linea), {"secuencia": 0}, format="json")
    assert r.status_code == 200

    linea.refresh_from_db()
    assert linea.secuencia == 0
    ev = EventoTrabajo.objects.get(orden=linea.orden, tipo="secuencia")
    assert ev.datos["nuevo_sin_secuenciar"] is True
    #  Y el 0 nunca es empate.
    assert ev.datos["empate"]["hay_empate"] is False
    assert "sin secuenciar" in ev.datos["empate"]["razon"]


@pytest.mark.django_db
def test_3_de_uno_a_dos(cliente_a, org_a, plan_a, gestor_a):
    linea = _linea(org_a, plan_a, 9503, MIER, gestor_a[1], secuencia=1)
    assert cliente_a.post(_url(linea), {"secuencia": 2},
                          format="json").status_code == 200
    linea.refresh_from_db()
    assert linea.secuencia == 2


@pytest.mark.django_db
def test_4_mantener_la_misma_secuencia_responde_200(cliente_a, org_a, plan_a,
                                                    gestor_a):
    """
    DECISION B-1 (M03-B1). Hasta entonces esta vía devolvía 409 mientras la de
    jornada devolvía 200 al mismo hecho: un cliente que usara las dos veía dos
    respuestas distintas para lo mismo.

    Pedir el estado que ya rige no es un error. Lo que NO cambia es lo que se
    escribe: nada.
    """
    linea = _linea(org_a, plan_a, 9504, MIER, gestor_a[1], secuencia=3)
    tocado = linea.updated_at

    r = cliente_a.post(_url(linea), {"secuencia": 3}, format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "sin_cambios"
    assert r.json()["traza"] is None

    linea.refresh_from_db()
    assert linea.secuencia == 3
    assert linea.updated_at == tocado          # ni se tocó la fila
    assert EventoTrabajo.objects.filter(tipo="secuencia").count() == 0
    assert NovedadOperativa.objects.count() == 0


@pytest.mark.django_db
def test_4b_mantener_el_cero_tambien_responde_200(cliente_a, org_a, plan_a,
                                                  gestor_a):
    """0 → 0 es un no-op igual que cualquier otro: 0 significa SIN SECUENCIAR."""
    linea = _linea(org_a, plan_a, 9505, MIER, gestor_a[1])
    r = cliente_a.post(_url(linea), {"secuencia": 0}, format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "sin_cambios"
    assert EventoTrabajo.objects.filter(tipo="secuencia").count() == 0


@pytest.mark.django_db
def test_4c_un_noop_en_plan_publicado_no_exige_motivo(cliente_a, org_a,
                                                      gestor_a):
    """
    Una petición que no cambia nada no tiene nada que justificar. Es la misma
    regla que E5 aplica a un lote sin cambios (`test_16b` de esa suite).
    """
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    linea = _linea(org_a, publicado, 9506, MIER, gestor_a[1], secuencia=4,
                   causa="bloqueo", motivo="x")

    r = cliente_a.post(_url(linea), {"secuencia": 4}, format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "sin_cambios"
    assert EventoTrabajo.objects.filter(
        tipo__startswith="secuencia").count() == 0


@pytest.mark.django_db
def test_4d_un_cambio_real_sigue_dando_aplicado(cliente_a, org_a, plan_a,
                                                gestor_a):
    """La otra mitad de B-1: lo que SÍ cambia se comporta igual que antes."""
    linea = _linea(org_a, plan_a, 9507, MIER, gestor_a[1], secuencia=1)
    r = cliente_a.post(_url(linea), {"secuencia": 2}, format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "aplicado"
    assert r.json()["traza"]["anterior"] == 1
    assert r.json()["traza"]["nuevo"] == 2
    assert EventoTrabajo.objects.filter(tipo="secuencia").count() == 1


@pytest.mark.django_db
def test_4e_a_cero_sigue_generando_evento_con_su_semantica(cliente_a, org_a,
                                                           plan_a, gestor_a):
    linea = _linea(org_a, plan_a, 9508, MIER, gestor_a[1], secuencia=2)
    r = cliente_a.post(_url(linea), {"secuencia": 0}, format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "aplicado"

    ev = EventoTrabajo.objects.get(tipo="secuencia")
    assert (ev.datos["anterior"], ev.datos["nuevo"]) == (2, 0)
    assert ev.datos["anterior_sin_secuenciar"] is False
    assert ev.datos["nuevo_sin_secuenciar"] is True
    assert ev.datos["empate"]["hay_empate"] is False


# ===========================================================================
#  5-7  --  ceros múltiples y duplicados > 0
# ===========================================================================
@pytest.mark.django_db
def test_5_varias_lineas_en_cero_no_son_empate(cliente_a, org_a, plan_a,
                                               gestor_a):
    """
    E-2 aprobada: 0 = SIN SECUENCIAR. Varias sin secuenciar no compiten por
    ninguna posición.
    """
    _linea(org_a, plan_a, 9510, MIER, gestor_a[1])
    _linea(org_a, plan_a, 9511, MIER, gestor_a[1])
    l3 = _linea(org_a, plan_a, 9512, MIER, gestor_a[1], secuencia=4)

    r = cliente_a.post(_url(l3), {"secuencia": 0}, format="json")
    assert r.status_code == 200
    assert r.json()["empate"]["hay_empate"] is False

    #  Las tres quedan en 0 y ninguna es un problema.
    assert ProgramacionOrden.objects.filter(
        dia=MIER.date(), secuencia=0).count() == 3
    assert revisar_coherencia(plan_a) == []


@pytest.mark.django_db
def test_6_varias_lineas_en_uno_si_son_empate_y_se_permiten(
        cliente_a, org_a, plan_a, gestor_a):
    _linea(org_a, plan_a, 9520, MIER, gestor_a[1], secuencia=1)
    l2 = _linea(org_a, plan_a, 9521, MIER, gestor_a[1], secuencia=7)

    r = cliente_a.post(_url(l2), {"secuencia": 1}, format="json")
    assert r.status_code == 200          # PERMITIDO

    empate = r.json()["empate"]
    assert empate["hay_empate"] is True
    assert empate["con"][0]["orden"] == 9520

    #  Y la otra línea NO se tocó: nada de recompactar ni desplazar.
    otra = ProgramacionOrden.objects.get(orden__numero=9520)
    assert otra.secuencia == 1


@pytest.mark.django_db
def test_7_los_duplicados_no_son_error_de_coherencia(org_a, plan_a, gestor_a):
    """E-5 aprobada: el duplicado de secuencia NO es el ERROR de I-1."""
    l1 = _linea(org_a, plan_a, 9530, MIER, gestor_a[1], secuencia=2)
    l2 = _linea(org_a, plan_a, 9531, MIER, gestor_a[1], secuencia=9)
    actualizar_secuencia(org=org_a, linea=l2, secuencia=2, actor=gestor_a[1])

    assert revisar_coherencia(plan_a) == []
    l1.refresh_from_db(); l2.refresh_from_db()
    assert (l1.secuencia, l2.secuencia) == (2, 2)


# ===========================================================================
#  8-11  --  borrador, publicado y trazabilidad
# ===========================================================================
@pytest.mark.django_db
def test_8_plan_borrador_no_exige_causa(cliente_a, org_a, plan_a, gestor_a):
    linea = _linea(org_a, plan_a, 9540, MIER, gestor_a[1])
    r = cliente_a.post(_url(linea), {"secuencia": 5}, format="json")
    assert r.status_code == 200
    assert NovedadOperativa.objects.count() == 0
    ev = EventoTrabajo.objects.get(orden=linea.orden, tipo="secuencia")
    assert ev.datos["causa"] == ""


@pytest.mark.django_db
def test_9_plan_publicado_exige_causa(cliente_a, org_a, gestor_a):
    """
    D1.1-D aprobada: el motivo es obligatorio cuando hay compromiso operativo,
    y un plan publicado lo es -- ya lo vieron las cuadrillas.
    """
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    linea = _linea(org_a, publicado, 9550, MIER, gestor_a[1],
                   causa="cambio_de_prioridad", motivo="entró un urgente")

    sin = cliente_a.post(_url(linea), {"secuencia": 2}, format="json")
    assert sin.status_code == 400
    linea.refresh_from_db()
    assert linea.secuencia == 0        # nada cambió


@pytest.mark.django_db
def test_10_plan_publicado_con_causa_deja_traza_formal(cliente_a, org_a,
                                                       gestor_a):
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    l1 = _linea(org_a, publicado, 9560, MIER, gestor_a[1], secuencia=1,
                causa="falta_material", motivo="ya llegó")
    l2 = _linea(org_a, publicado, 9561, MIER, gestor_a[1], secuencia=8,
                causa="falta_material", motivo="ya llegó")

    r = cliente_a.post(_url(l2), {"secuencia": 1, "causa": "cambio_de_prioridad",
                                  "motivo": "el cliente cambió la hora"},
                       format="json")
    assert r.status_code == 200

    ev = EventoTrabajo.objects.get(orden=l2.orden,
                                   tipo="secuencia_en_plan_publicado")
    #  Los ocho datos que el encargo exige registrar.
    assert ev.datos["anterior"] == 8
    assert ev.datos["nuevo"] == 1
    assert ev.datos["plan"] == str(publicado.id)
    assert ev.datos["plan_estado"] == ProgramacionSemanal.PUBLICADA
    assert ev.orden_id == l2.orden_id
    assert ev.profile_id == gestor_a[1].id
    assert ev.created_at is not None
    assert ev.datos["empate"]["hay_empate"] is True
    assert ev.datos["empate"]["con"][0]["orden"] == 9560

    #  La causa va a NovedadOperativa, no al evento como tipo.
    nov = NovedadOperativa.objects.get(tipo=NovedadOperativa.CAMBIO_PRIORIDAD)
    assert ev.datos["novedad"] == str(nov.id)
    assert nov.tipo != NovedadOperativa.REPROGRAMACION


@pytest.mark.django_db
def test_11_el_valor_anterior_queda_bien_registrado(org_a, plan_a, gestor_a):
    linea = _linea(org_a, plan_a, 9570, MIER, gestor_a[1], secuencia=6)
    actualizar_secuencia(org=org_a, linea=linea, secuencia=2, actor=gestor_a[1])
    actualizar_secuencia(org=org_a, linea=linea, secuencia=9, actor=gestor_a[1])

    eventos = list(EventoTrabajo.objects
                   .filter(orden=linea.orden, tipo="secuencia")
                   .order_by("created_at"))
    assert [(e.datos["anterior"], e.datos["nuevo"]) for e in eventos] == [(6, 2),
                                                                         (2, 9)]


# ===========================================================================
#  12-14  --  rollback, concurrencia, idempotencia
# ===========================================================================
@pytest.mark.django_db
def test_12_rollback_no_deja_estado_parcial(org_a, plan_a, gestor_a):
    """Se rompe en el ÚLTIMO paso, con la secuencia ya escrita."""
    linea = _linea(org_a, plan_a, 9580, MIER, gestor_a[1], secuencia=4)

    with mock.patch.object(EventoTrabajo.objects, "create",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            actualizar_secuencia(org=org_a, linea=linea, secuencia=7,
                                 actor=gestor_a[1])

    linea.refresh_from_db()
    assert linea.secuencia == 4                       # ni secuencia sin evento
    assert EventoTrabajo.objects.filter(tipo="secuencia").count() == 0
    assert NovedadOperativa.objects.count() == 0      # ni evento sin cambio


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_12b_el_rollback_se_ve_desde_fuera(org_a, plan_a, gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    linea = _linea(org_a, plan_a, 9581, MIER, gestor_a[1], secuencia=4)

    with mock.patch.object(EventoTrabajo.objects, "create",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            actualizar_secuencia(org=org_a, linea=linea, secuencia=7,
                                 actor=gestor_a[1])

    f = _desde_fuera("select secuencia from operaciones_programacion_orden "
                     "where id = %s", [str(linea.id)])[0]
    assert f["secuencia"] == 4


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_13_dos_cambios_simultaneos_no_pierden_actualizacion(org_a, gestor_a):
    """
    Dos supervisores cambian la misma línea a la vez, a valores distintos.

    Sin el lock las dos leen la secuencia vieja, las dos escriben, y el evento
    de la segunda dice que venía del valor VIEJO -- o sea, la bitácora afirma
    una transición que no ocurrió y el cambio de la primera desaparece del
    historial.
    """
    if connection.vendor != "postgresql":
        pytest.skip("la concurrencia real requiere PostgreSQL")

    u, perfil = gestor_a
    plan = _plan(org_a)
    linea = _linea(org_a, plan, 9590, MIER, perfil, secuencia=1)
    cli = _cli(u, org_a, perfil)

    def cambia(valor):
        try:
            return cli.post(_url(linea), {"secuencia": valor},
                            format="json").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(cambia, [5, 9]))

    assert 200 in codigos, codigos
    linea.refresh_from_db()

    eventos = list(EventoTrabajo.objects
                   .filter(orden=linea.orden, tipo="secuencia")
                   .order_by("created_at"))
    #  La cadena de anterior->nuevo tiene que encadenar: el 'anterior' de cada
    #  evento es el 'nuevo' del anterior, y el último coincide con la fila.
    assert eventos[0].datos["anterior"] == 1
    for previo, siguiente in zip(eventos, eventos[1:]):
        assert siguiente.datos["anterior"] == previo.datos["nuevo"], (
            [(e.datos["anterior"], e.datos["nuevo"]) for e in eventos])
    assert eventos[-1].datos["nuevo"] == linea.secuencia


@pytest.mark.django_db
def test_14_idempotencia_por_cabecera(cliente_a, org_a, plan_a, gestor_a):
    linea = _linea(org_a, plan_a, 9600, MIER, gestor_a[1], secuencia=1)
    cuerpo = {"secuencia": 4}

    p = cliente_a.post(_url(linea), cuerpo, format="json",
                       HTTP_IDEMPOTENCY_KEY="e4-clave-1")
    assert p.status_code == 200
    s = cliente_a.post(_url(linea), cuerpo, format="json",
                       HTTP_IDEMPOTENCY_KEY="e4-clave-1")
    assert s.status_code == 200
    assert s.get("Idempotent-Replay") == "true"

    assert EventoTrabajo.objects.filter(tipo="secuencia").count() == 1
    linea.refresh_from_db()
    assert linea.secuencia == 4


# ===========================================================================
#  15-16  --  multi-tenant y permisos
# ===========================================================================
@pytest.mark.django_db
def test_15_no_se_puede_tocar_la_linea_de_otra_organizacion(cliente_a, org_b):
    plan_b = _plan(org_b)
    ub, pb = _gestor(org_b, "jefe.b@e4.test")
    linea_b = _linea(org_b, plan_b, 9610, MIER, pb, secuencia=1)

    r = cliente_a.post(_url(linea_b), {"secuencia": 5}, format="json")
    assert r.status_code == 404        # no 403: no se confirma que exista
    linea_b.refresh_from_db()
    assert linea_b.secuencia == 1


@pytest.mark.django_db
def test_15b_el_servicio_no_confia_en_la_vista(org_a, org_b, gestor_a):
    plan_b = _plan(org_b)
    ub, pb = _gestor(org_b, "jefe.b2@e4.test")
    linea_b = _linea(org_b, plan_b, 9611, MIER, pb, secuencia=1)

    with pytest.raises(ErrorProgramacion) as e:
        actualizar_secuencia(org=org_a, linea=linea_b, secuencia=5,
                             actor=gestor_a[1])
    assert "otra empresa" in str(e.value)


@pytest.mark.django_db
def test_16_un_tecnico_no_cambia_la_secuencia(org_a, plan_a, gestor_a,
                                              regular_user, user_profile):
    linea = _linea(org_a, plan_a, 9620, MIER, gestor_a[1], secuencia=1)
    r = _cli(regular_user, org_a, user_profile).post(
        _url(linea), {"secuencia": 5}, format="json")
    assert r.status_code == 403
    linea.refresh_from_db()
    assert linea.secuencia == 1


@pytest.mark.django_db
def test_16b_sin_sesion_tampoco(org_a, plan_a, gestor_a):
    linea = _linea(org_a, plan_a, 9621, MIER, gestor_a[1])
    assert APIClient().post(_url(linea), {"secuencia": 5},
                            format="json").status_code in (401, 403)


@pytest.mark.django_db
def test_16c_una_secuencia_negativa_se_rechaza(cliente_a, org_a, plan_a,
                                               gestor_a):
    linea = _linea(org_a, plan_a, 9622, MIER, gestor_a[1], secuencia=1)
    r = cliente_a.post(_url(linea), {"secuencia": -1}, format="json")
    assert r.status_code == 400
    linea.refresh_from_db()
    assert linea.secuencia == 1


# ===========================================================================
#  17  --  la lectura de E2 después del cambio
# ===========================================================================
@pytest.mark.django_db
def test_17_la_jornada_muestra_el_cambio(cliente_a, org_a, plan_a, gestor_a):
    l1 = _linea(org_a, plan_a, 9630, MIER, gestor_a[1], secuencia=3)
    l2 = _linea(org_a, plan_a, 9631, MIER, gestor_a[1], secuencia=1)

    antes = cliente_a.get(JORNADA, {"dia": str(MIER.date())}).json()
    assert [f["numero"] for f in antes["resultados"]] == [9631, 9630]

    cliente_a.post(_url(l1), {"secuencia": 0}, format="json")

    despues = cliente_a.get(JORNADA, {"dia": str(MIER.date())}).json()
    #  El 0 se muestra como 0 y sale primero por el ordering; el resumen lo
    #  cuenta como 'sin secuenciar' sin llamarlo así ni juzgarlo.
    assert [f["secuencia"] for f in despues["resultados"]] == [0, 1]
    assert despues["resumen"]["secuencia_cero"] == 1
    assert despues["resumen"]["secuencia_mayor_que_cero"] == 1
    assert despues["resumen"]["lineas_en_empate"] == 0


@pytest.mark.django_db
def test_17b_los_duplicados_siguen_visibles_y_el_desempate_es_estable(
        cliente_a, org_a, plan_a, gestor_a):
    _linea(org_a, plan_a, 9640, MIER, gestor_a[1], secuencia=2)
    l2 = _linea(org_a, plan_a, 9641, MIER, gestor_a[1], secuencia=8)
    cliente_a.post(_url(l2), {"secuencia": 2}, format="json")

    corridas = [
        [f["id"] for f in cliente_a.get(
            JORNADA, {"dia": str(MIER.date())}).json()["resultados"]]
        for _ in range(3)]
    assert all(c == corridas[0] for c in corridas)

    resumen = cliente_a.get(JORNADA,
                            {"dia": str(MIER.date())}).json()["resumen"]
    assert resumen["dias"][0]["secuencias_empatadas"] == [2]
    assert resumen["lineas_en_empate"] == 2


# ===========================================================================
#  18-20  --  I-1, reprogramación y publicación no se ven afectadas
# ===========================================================================
@pytest.mark.django_db
def test_18_i1_sigue_siendo_independiente(org_a, plan_a, gestor_a):
    linea = _linea(org_a, plan_a, 9650, MIER, gestor_a[1], secuencia=1)
    plan_b = _plan(org_a, lunes=SEM2)
    ProgramacionOrden.objects.create(
        org=org_a, programacion=plan_b, orden=linea.orden,
        dia=MAR2.date(), secuencia=1, estado=ProgramacionOrden.PLANIFICADA)

    problemas = revisar_coherencia(plan_a)
    assert any("2 lineas vigentes" in p for p in problemas)
    #  Y ninguno habla de secuencia: son invariantes distintas.
    assert not any("secuencia" in p for p in problemas)


@pytest.mark.django_db
def test_19_cambiar_la_secuencia_no_reprograma(cliente_a, org_a, plan_a,
                                               gestor_a):
    """La afirmación central de E4, sobre el efecto."""
    linea = _linea(org_a, plan_a, 9660, MIER, gestor_a[1], secuencia=1,
                   zona="Norte", prioridad=10)
    orden = linea.orden
    antes_orden = (orden.programada_para, orden.estado_operativo,
                   orden.estado_validacion, orden.revision, orden.vuelta)
    antes_linea = (linea.dia, linea.hora_inicio, linea.zona, linea.prioridad,
                   linea.estado, linea.programacion_id, linea.orden_id)

    assert cliente_a.post(_url(linea), {"secuencia": 6},
                          format="json").status_code == 200

    orden.refresh_from_db()
    linea.refresh_from_db()
    assert (orden.programada_para, orden.estado_operativo,
            orden.estado_validacion, orden.revision,
            orden.vuelta) == antes_orden
    assert (linea.dia, linea.hora_inicio, linea.zona, linea.prioridad,
            linea.estado, linea.programacion_id,
            linea.orden_id) == antes_linea
    assert linea.secuencia == 6
    #  Y no se creó ninguna línea nueva.
    assert ProgramacionOrden.objects.filter(orden=orden).count() == 1


@pytest.mark.django_db
def test_19b_la_reprogramacion_de_d3_sigue_funcionando(org_a, plan_a,
                                                       gestor_a):
    linea = _linea(org_a, plan_a, 9670, MIER, gestor_a[1], secuencia=2)
    actualizar_secuencia(org=org_a, linea=linea, secuencia=5, actor=gestor_a[1])

    orden = linea.orden
    orden.refresh_from_db()
    plan_b = _plan(org_a, lunes=SEM2)
    reprogramar_orden(org=org_a, orden=orden, programada_para=MAR2,
                      programacion_destino=plan_b, actor=gestor_a[1])

    #  La línea nueva arrastra la secuencia YA EDITADA (M03-D3.2).
    nueva = ProgramacionOrden.objects.get(
        orden=orden, estado=ProgramacionOrden.PLANIFICADA)
    assert nueva.secuencia == 5
    assert nueva.programacion_id == plan_b.id


@pytest.mark.django_db
def test_20_la_publicacion_de_m03c_no_se_ve_afectada(cliente_a, org_a, plan_a,
                                                     gestor_a):
    l1 = _linea(org_a, plan_a, 9680, MIER, gestor_a[1])
    l2 = _linea(org_a, plan_a, 9681, MIER, gestor_a[1])
    #  Dos en 0 y luego dos en 1: ni los ceros ni el empate bloquean publicar.
    actualizar_secuencia(org=org_a, linea=l1, secuencia=1, actor=gestor_a[1])
    actualizar_secuencia(org=org_a, linea=l2, secuencia=1, actor=gestor_a[1])

    r = cliente_a.post(f"/api/operaciones/programacion/{plan_a.id}/publicar/",
                       {}, format="json")
    assert r.status_code == 200
    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.PUBLICADA


# ===========================================================================
#  Alcance
# ===========================================================================
@pytest.mark.django_db
def test_no_se_toca_ninguna_otra_linea(cliente_a, org_a, plan_a, gestor_a):
    """No recompacta, no desplaza, no reasigna."""
    otras = [_linea(org_a, plan_a, 9690 + i, MIER, gestor_a[1], secuencia=i)
             for i in range(1, 4)]
    objetivo = _linea(org_a, plan_a, 9699, MIER, gestor_a[1], secuencia=9)
    antes = {l.id: l.secuencia for l in otras}

    cliente_a.post(_url(objetivo), {"secuencia": 2}, format="json")

    for l in otras:
        l.refresh_from_db()
        assert l.secuencia == antes[l.id]


@pytest.mark.django_db
def test_m09_no_consume_secuencia(cliente_a, org_a, plan_a, gestor_a):
    from operaciones import supervisor
    from operaciones.models import PropuestaSupervisor
    import inspect
    assert "secuencia" not in inspect.getsource(supervisor)

    linea = _linea(org_a, plan_a, 9700, MIER, gestor_a[1])
    cliente_a.post(_url(linea), {"secuencia": 3}, format="json")
    assert PropuestaSupervisor.objects.count() == 0


@pytest.mark.django_db
def test_ninguna_conexion_saliente(cliente_a, org_a, plan_a, gestor_a):
    import http.client
    import socket

    linea = _linea(org_a, plan_a, 9710, MIER, gestor_a[1])
    destinos = []
    original = socket.socket.connect

    def vigilado(self, direccion):
        destinos.append(direccion)
        return original(self, direccion)

    socket.socket.connect = vigilado
    try:
        cliente_a.post(_url(linea), {"secuencia": 2}, format="json")
        durante = list(destinos)
        try:
            http.client.HTTPConnection("127.0.0.1", 9, timeout=2).request("GET", "/")
        except Exception:
            pass
        disparo = len(destinos) > len(durante)
    finally:
        socket.socket.connect = original

    assert disparo, "el instrumento no dispara: el 0 de abajo no probaría nada"
    assert [d for d in durante
            if not (isinstance(d, tuple) and len(d) >= 2 and d[1] == 5432)] == []


# ===========================================================================
#  B-1  --  las tres cosas que se parecen y NO son lo mismo
# ===========================================================================
#  El encargo de M03-B1 pide demostrar que el sistema distingue tres
#  situaciones que un cliente podría confundir:
#
#    A. NO-OP                 el estado pedido ya rige         -> 200
#    B. REPLAY IDEMPOTENTE    la MISMA petición ya se ejecutó  -> 200 + cabecera
#    C. CONFLICTO             otro cambió la línea en medio    -> 409 / rechazo
#
#  Son tres mecanismos distintos, y se prueban por separado para que no se
#  tape uno con otro.

@pytest.mark.django_db
def test_b1_A_noop_no_es_replay(cliente_a, org_a, plan_a, gestor_a):
    """Sin cabecera de idempotencia: 200 sin nada escrito, y SIN replay."""
    linea = _linea(org_a, plan_a, 9760, MIER, gestor_a[1], secuencia=5)

    r = cliente_a.post(_url(linea), {"secuencia": 5}, format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "sin_cambios"
    #  Lo que lo distingue de un replay: no hay cabecera.
    assert r.get("Idempotent-Replay") is None
    assert EventoTrabajo.objects.filter(tipo="secuencia").count() == 0


@pytest.mark.django_db
def test_b1_B_replay_conserva_su_comportamiento(cliente_a, org_a, plan_a,
                                                gestor_a):
    """
    Un replay NO es un no-op: la primera petición SÍ cambió algo, y la segunda
    devuelve la respuesta guardada de aquella -- con 'resultado: aplicado'.
    """
    linea = _linea(org_a, plan_a, 9761, MIER, gestor_a[1], secuencia=1)

    p = cliente_a.post(_url(linea), {"secuencia": 9}, format="json",
                       HTTP_IDEMPOTENCY_KEY="b1-clave-1")
    assert p.status_code == 200
    assert p.json()["resultado"] == "aplicado"

    s = cliente_a.post(_url(linea), {"secuencia": 9}, format="json",
                       HTTP_IDEMPOTENCY_KEY="b1-clave-1")
    assert s.status_code == 200
    assert s.get("Idempotent-Replay") == "true"
    #  Devuelve lo que devolvió la PRIMERA, no un 'sin_cambios' nuevo.
    assert s.json()["resultado"] == "aplicado"
    assert EventoTrabajo.objects.filter(tipo="secuencia").count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_b1_C_el_conflicto_sigue_siendo_conflicto(org_a, gestor_a):
    """
    B-1 libera el 409 del no-op, pero NO toca la concurrencia: dos cambios
    simultáneos siguen encadenando sin perder historial.
    """
    if connection.vendor != "postgresql":
        pytest.skip("la concurrencia real requiere PostgreSQL")

    u, perfil = gestor_a
    plan = _plan(org_a)
    linea = _linea(org_a, plan, 9762, MIER, perfil, secuencia=1)
    cli = _cli(u, org_a, perfil)

    def cambia(valor):
        try:
            return cli.post(_url(linea), {"secuencia": valor},
                            format="json").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(cambia, [4, 8]))

    assert 200 in codigos, codigos
    linea.refresh_from_db()

    eventos = list(EventoTrabajo.objects
                   .filter(orden=linea.orden, tipo="secuencia")
                   .order_by("created_at"))
    assert eventos[0].datos["anterior"] == 1
    for previo, siguiente in zip(eventos, eventos[1:]):
        assert siguiente.datos["anterior"] == previo.datos["nuevo"]
    assert eventos[-1].datos["nuevo"] == linea.secuencia


@pytest.mark.django_db
def test_b1_e4_y_e5_responden_igual_al_mismo_hecho(cliente_a, org_a, plan_a,
                                                   gestor_a):
    """
    La inconsistencia que B-1 vino a eliminar, comprobada de frente: el MISMO
    hecho --pedir el estado que ya rige-- por las dos rutas.
    """
    linea = _linea(org_a, plan_a, 9763, MIER, gestor_a[1], secuencia=2)

    por_linea = cliente_a.post(_url(linea), {"secuencia": 2}, format="json")
    por_jornada = cliente_a.post(
        "/api/operaciones/programacion/jornada/secuenciar/",
        {"plan": str(plan_a.id), "dia": str(MIER.date()),
         "lineas": [{"linea": str(linea.id), "secuencia": 2,
                     "secuencia_leida": 2}]}, format="json")

    assert por_linea.status_code == por_jornada.status_code == 200
    assert (por_linea.json()["resultado"]
            == por_jornada.json()["resultado"] == "sin_cambios")
    assert EventoTrabajo.objects.filter(
        tipo__startswith="secuencia").count() == 0
    assert NovedadOperativa.objects.count() == 0


@pytest.mark.django_db
def test_b1_un_noop_no_produce_efectos_externos(cliente_a, org_a, plan_a,
                                                gestor_a):
    import http.client
    import socket

    linea = _linea(org_a, plan_a, 9764, MIER, gestor_a[1], secuencia=3)
    destinos = []
    original = socket.socket.connect

    def vigilado(self, direccion):
        destinos.append(direccion)
        return original(self, direccion)

    socket.socket.connect = vigilado
    try:
        r = cliente_a.post(_url(linea), {"secuencia": 3}, format="json")
        assert r.status_code == 200
        durante = list(destinos)
        try:
            http.client.HTTPConnection("127.0.0.1", 9, timeout=2).request("GET", "/")
        except Exception:
            pass
        disparo = len(destinos) > len(durante)
    finally:
        socket.socket.connect = original

    assert disparo, "el instrumento no dispara: el 0 de abajo no probaría nada"
    assert [d for d in durante
            if not (isinstance(d, tuple) and len(d) >= 2 and d[1] == 5432)] == []
