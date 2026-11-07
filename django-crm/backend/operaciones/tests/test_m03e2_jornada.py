# -*- coding: utf-8 -*-
"""
================================================================================
 M03-E2  --  la jornada, legible y en orden reproducible
================================================================================

Lo que estas pruebas afirman no es que el endpoint devuelva filas, sino las tres
cosas que E2 existe para conseguir:

  * que 'secuencia' se pueda LEER -- hasta ahora era de solo escritura;
  * que dos consultas idénticas devuelvan el MISMO orden, incluso con empates;
  * que los empates se CUENTEN y se declaren, sin resolverlos.

Y una que E2 existe para NO hacer: leer la jornada no cambia nada.
================================================================================
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones.models import ProgramacionOrden, ProgramacionSemanal
from operaciones.programacion import (ORDEN_JORNADA, lineas_de_jornada,
                                      programar_orden, reprogramar_orden,
                                      resumen_de_jornada, revisar_coherencia)

LUNES = date(2026, 10, 5)
SEM2 = LUNES + timedelta(weeks=1)
URL = "/api/operaciones/programacion/jornada/"


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


def _orden(org, numero, version=None):
    version = version or _version(org, f"e2_{numero}")
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
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
    return _gestor(org_a, "jefe.a@e2.test")


@pytest.fixture
def cliente_a(org_a, gestor_a):
    return _cli(gestor_a[0], org_a, gestor_a[1])


def _programa(org, plan, numero, cuando, actor, secuencia=None, **extra):
    orden = _orden(org, numero)
    programar_orden(org=org, orden=orden, programacion=plan,
                    programada_para=cuando, actor=actor,
                    secuencia=secuencia, **extra)
    orden.refresh_from_db()
    return orden


# ===========================================================================
#  1  --  lectura de la jornada
# ===========================================================================
@pytest.mark.django_db
def test_1_la_jornada_se_puede_leer(cliente_a, org_a, plan_a, gestor_a):
    """
    Lo que E2 viene a resolver: 'secuencia' era de SOLO ESCRITURA.
    """
    _programa(org_a, plan_a, 9301, MIER, gestor_a[1], secuencia=2, zona="Norte")

    r = cliente_a.get(URL, {"dia": str(MIER.date())})
    assert r.status_code == 200, r.content[:300]
    d = r.json()
    assert d["count"] == 1

    fila = d["resultados"][0]
    #  Los tres campos de planificación, legibles por primera vez.
    assert fila["secuencia"] == 2
    assert fila["zona"] == "Norte"
    assert "prioridad" in fila
    #  Y lo justo de la orden para poder leer la línea.
    assert fila["numero"] == 9301
    assert fila["cliente"] == "Cliente 9301"
    assert fila["estado_orden"] == OrdenTrabajo.ASIGNADA
    assert fila["plan_semana"] == str(LUNES)
    assert fila["plan_estado"] == ProgramacionSemanal.BORRADOR


@pytest.mark.django_db
def test_1b_no_expone_datos_del_cliente_que_nadie_pidio(cliente_a, org_a,
                                                        plan_a, gestor_a):
    _programa(org_a, plan_a, 9302, MIER, gestor_a[1])
    fila = cliente_a.get(URL, {"dia": str(MIER.date())}).json()["resultados"][0]
    for prohibido in ("cliente_telefono", "cliente_direccion",
                      "gps_lat", "gps_lng", "datos", "contexto"):
        assert prohibido not in fila


@pytest.mark.django_db
def test_1c_se_puede_pedir_por_plan(cliente_a, org_a, plan_a, gestor_a):
    _programa(org_a, plan_a, 9303, MIER, gestor_a[1])
    _programa(org_a, plan_a, 9304, VIER, gestor_a[1])
    r = cliente_a.get(URL, {"plan": str(plan_a.id)})
    assert r.status_code == 200
    assert r.json()["count"] == 2


@pytest.mark.django_db
def test_1d_sin_filtro_se_rechaza(cliente_a):
    r = cliente_a.get(URL)
    assert r.status_code == 400
    assert r.json()["error"] == "FALTA_FILTRO"


@pytest.mark.django_db
def test_1e_leer_no_cambia_nada(cliente_a, org_a, plan_a, gestor_a):
    """E2 es observabilidad. Afirmado sobre el efecto, no sobre la intención."""
    orden = _programa(org_a, plan_a, 9305, MIER, gestor_a[1], secuencia=3)
    linea = ProgramacionOrden.objects.get(orden=orden)
    antes = (linea.dia, linea.secuencia, linea.estado, linea.updated_at,
             orden.programada_para, orden.revision)

    cliente_a.get(URL, {"dia": str(MIER.date())})
    cliente_a.get(URL, {"plan": str(plan_a.id)})

    linea.refresh_from_db()
    orden.refresh_from_db()
    assert (linea.dia, linea.secuencia, linea.estado, linea.updated_at,
            orden.programada_para, orden.revision) == antes


# ===========================================================================
#  2-3  --  multi-tenant y permisos
# ===========================================================================
@pytest.mark.django_db
def test_2_una_organizacion_no_ve_la_jornada_de_otra(cliente_a, org_a, org_b,
                                                     plan_a, gestor_a):
    _programa(org_a, plan_a, 9310, MIER, gestor_a[1])
    plan_b = _plan(org_b)
    ub, pb = _gestor(org_b, "jefe.b@e2.test")
    _programa(org_b, plan_b, 9311, MIER, pb)

    de_a = cliente_a.get(URL, {"dia": str(MIER.date())}).json()
    assert de_a["count"] == 1
    assert de_a["resultados"][0]["numero"] == 9310

    de_b = _cli(ub, org_b, pb).get(URL, {"dia": str(MIER.date())}).json()
    assert de_b["count"] == 1
    assert de_b["resultados"][0]["numero"] == 9311


@pytest.mark.django_db
def test_2b_el_plan_de_otra_organizacion_no_existe(cliente_a, org_b):
    plan_b = _plan(org_b)
    r = cliente_a.get(URL, {"plan": str(plan_b.id)})
    #  404 y no 403: un 403 confirmaría que el plan existe.
    assert r.status_code == 404


@pytest.mark.django_db
def test_3_un_tecnico_no_lee_la_jornada(org_a, plan_a, regular_user,
                                        user_profile):
    r = _cli(regular_user, org_a, user_profile).get(
        URL, {"dia": str(MIER.date())})
    assert r.status_code == 403


@pytest.mark.django_db
def test_3b_sin_sesion_no_se_lee(plan_a):
    assert APIClient().get(URL, {"dia": str(MIER.date())}).status_code in (401, 403)


# ===========================================================================
#  4-7  --  secuencias: distintas, todas 0, duplicadas, mezcladas
# ===========================================================================
@pytest.mark.django_db
def test_4_dia_con_secuencias_distintas(cliente_a, org_a, plan_a, gestor_a):
    _programa(org_a, plan_a, 9320, MIER, gestor_a[1], secuencia=3)
    _programa(org_a, plan_a, 9321, MIER, gestor_a[1], secuencia=1)
    _programa(org_a, plan_a, 9322, MIER, gestor_a[1], secuencia=2)

    d = cliente_a.get(URL, {"dia": str(MIER.date())}).json()
    assert [f["secuencia"] for f in d["resultados"]] == [1, 2, 3]
    assert [f["numero"] for f in d["resultados"]] == [9321, 9322, 9320]
    assert d["resumen"]["lineas_en_empate"] == 0
    assert d["resumen"]["dias"][0]["orden_arbitrario"] is False


@pytest.mark.django_db
def test_5_dia_con_todas_las_secuencias_en_cero(cliente_a, org_a, plan_a,
                                                gestor_a):
    """
    El caso POR DEFECTO, no un borde: 'secuencia' es opcional y su default es 0.
    """
    for n in (9330, 9331, 9332):
        _programa(org_a, plan_a, n, MIER, gestor_a[1])   # sin secuencia

    d = cliente_a.get(URL, {"dia": str(MIER.date())}).json()
    assert [f["secuencia"] for f in d["resultados"]] == [0, 0, 0]

    res = d["resumen"]
    assert res["secuencia_cero"] == 3
    assert res["secuencia_mayor_que_cero"] == 0
    #  CORREGIDO EN M03-E5-B. Esta prueba afirmaba 'lineas_en_empate == 3' y
    #  'secuencias_empatadas == [0]', que era la semántica ANTERIOR a la
    #  decisión E-2: entonces el 0 no significaba nada y repetirlo parecía un
    #  empate. Aprobada E-2 --0 = SIN SECUENCIAR-- varias líneas sin secuenciar
    #  NO compiten por ninguna posición, así que no hay empate que contar.
    assert res["lineas_en_empate"] == 0
    dia = res["dias"][0]
    assert dia["secuencias_empatadas"] == []
    #  Pero el orden SIGUE sin significar nada: el día entero está sin
    #  secuenciar, y eso se dice igual.
    assert dia["orden_arbitrario"] is True


@pytest.mark.django_db
def test_6_secuencias_duplicadas_se_cuentan_y_no_se_resuelven(
        cliente_a, org_a, plan_a, gestor_a):
    _programa(org_a, plan_a, 9340, MIER, gestor_a[1], secuencia=1)
    _programa(org_a, plan_a, 9341, MIER, gestor_a[1], secuencia=1)
    _programa(org_a, plan_a, 9342, MIER, gestor_a[1], secuencia=5)

    d = cliente_a.get(URL, {"dia": str(MIER.date())}).json()
    dia = d["resumen"]["dias"][0]
    assert dia["secuencias_empatadas"] == [1]
    assert dia["lineas_en_empate"] == 2
    assert dia["orden_arbitrario"] is False     # no TODAS empatan

    #  Y NO se resolvió: las dos líneas siguen valiendo 1.
    assert sorted(ProgramacionOrden.objects
                  .filter(dia=MIER.date())
                  .values_list("secuencia", flat=True)) == [1, 1, 5]


@pytest.mark.django_db
def test_7_mezcla_de_cero_y_mayores_que_cero(cliente_a, org_a, plan_a,
                                             gestor_a):
    _programa(org_a, plan_a, 9350, MIER, gestor_a[1])            # 0
    _programa(org_a, plan_a, 9351, MIER, gestor_a[1], secuencia=4)
    _programa(org_a, plan_a, 9352, MIER, gestor_a[1])            # 0

    res = cliente_a.get(URL, {"dia": str(MIER.date())}).json()["resumen"]
    assert res["secuencia_cero"] == 2
    assert res["secuencia_mayor_que_cero"] == 1
    #  CORREGIDO EN M03-E5-B: antes esto afirmaba 2. Aprobada la decisión E-2
    #  --0 = SIN SECUENCIAR-- dos líneas sin secuenciar no empatan entre sí.
    assert res["lineas_en_empate"] == 0
    #  No se etiqueta el 0 como "sin ordenar" ni como "primera": E-2 sigue
    #  pendiente y el informe solo cuenta.
    assert "sin ordenar" not in str(res).lower()
    assert "primera" not in str(res).lower()


# ===========================================================================
#  8-9  --  desempate determinista
# ===========================================================================
@pytest.mark.django_db
def test_8_el_desempate_es_por_identificador_estable(org_a, plan_a, gestor_a):
    """
    Tres claves: dia -> secuencia -> id. 'id' se elige por NO significar nada.
    """
    assert ORDEN_JORNADA == ("dia", "secuencia", "id")

    for n in (9360, 9361, 9362):
        _programa(org_a, plan_a, n, MIER, gestor_a[1])   # todas en 0

    lineas = list(lineas_de_jornada(org_a, dia=MIER.date()))
    ids = [str(x.id) for x in lineas]
    assert ids == sorted(ids), "con secuencia empatada el orden debe salir por id"


@pytest.mark.django_db
def test_9_la_misma_consulta_devuelve_el_mismo_orden(cliente_a, org_a, plan_a,
                                                     gestor_a):
    """
    Dos consultas idénticas devuelven el mismo orden. Se repite cinco veces.

    LO QUE ESTA PRUEBA NO PRUEBA, Y HAY QUE DECIRLO
    ------------------------------------------------
    Se verificó quitando el desempate: con estas cinco filas, esta prueba
    SIGUE PASANDO. Con tan pocos registros PostgreSQL devuelve un orden
    estable por casualidad --un recorrido secuencial-- y la falta de tercera
    clave no se nota.

    O sea: esto es un control de humo, no la garantía. La garantía la da
    'test_8', que afirma que el orden ES por 'id'; sin esa afirmación, la
    reproducibilidad que se observa aquí sería incidental y podría cambiar con
    otro plan de ejecución, otro volumen o un índice nuevo.
    """
    for n in (9370, 9371, 9372, 9373, 9374):
        _programa(org_a, plan_a, n, MIER, gestor_a[1])   # todas empatadas en 0

    corridas = [
        [f["id"] for f in cliente_a.get(
            URL, {"dia": str(MIER.date())}).json()["resultados"]]
        for _ in range(5)
    ]
    assert all(c == corridas[0] for c in corridas), corridas
    assert len(corridas[0]) == 5


@pytest.mark.django_db
def test_9b_el_desempate_no_reordena_lo_que_ya_estaba_ordenado(
        cliente_a, org_a, plan_a, gestor_a):
    """El desempate solo actúa en el empate: no toca el orden por secuencia."""
    _programa(org_a, plan_a, 9380, MIER, gestor_a[1], secuencia=9)
    _programa(org_a, plan_a, 9381, MIER, gestor_a[1], secuencia=1)

    d = cliente_a.get(URL, {"dia": str(MIER.date())}).json()
    assert [f["secuencia"] for f in d["resultados"]] == [1, 9]


# ===========================================================================
#  10-11  --  plan borrador y publicado
# ===========================================================================
@pytest.mark.django_db
def test_10_plan_borrador(cliente_a, org_a, plan_a, gestor_a):
    _programa(org_a, plan_a, 9390, MIER, gestor_a[1])
    d = cliente_a.get(URL, {"plan": str(plan_a.id)}).json()
    assert d["resultados"][0]["plan_estado"] == ProgramacionSemanal.BORRADOR


@pytest.mark.django_db
def test_11_plan_publicado(cliente_a, org_a, gestor_a):
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    _programa(org_a, publicado, 9391, MIER, gestor_a[1],
              causa="cambio_de_prioridad", motivo="entró un urgente")

    d = cliente_a.get(URL, {"plan": str(publicado.id)}).json()
    assert d["count"] == 1
    assert d["resultados"][0]["plan_estado"] == ProgramacionSemanal.PUBLICADA


# ===========================================================================
#  12  --  una línea REPROGRAMADA no es vigente
# ===========================================================================
@pytest.mark.django_db
def test_12_la_linea_reprogramada_no_aparece(cliente_a, org_a, plan_a,
                                             gestor_a):
    orden = _programa(org_a, plan_a, 9400, MIER, gestor_a[1], secuencia=2)
    plan_b = _plan(org_a, lunes=SEM2)
    reprogramar_orden(org=org_a, orden=orden, programada_para=MAR2,
                      programacion_destino=plan_b, actor=gestor_a[1])

    assert ProgramacionOrden.objects.filter(orden=orden).count() == 2

    #  El plan viejo ya no la muestra...
    assert cliente_a.get(URL, {"plan": str(plan_a.id)}).json()["count"] == 0
    #  ...y el nuevo sí, conservando la secuencia (M03-D3.2).
    d = cliente_a.get(URL, {"plan": str(plan_b.id)}).json()
    assert d["count"] == 1
    assert d["resultados"][0]["secuencia"] == 2


# ===========================================================================
#  13  --  I-1 sigue detectándose
# ===========================================================================
@pytest.mark.django_db
def test_13_i1_sigue_funcionando(org_a, plan_a, gestor_a):
    orden = _programa(org_a, plan_a, 9410, MIER, gestor_a[1])
    plan_b = _plan(org_a, lunes=SEM2)
    ProgramacionOrden.objects.create(
        org=org_a, programacion=plan_b, orden=orden,
        dia=MAR2.date(), estado=ProgramacionOrden.PLANIFICADA)

    problemas = revisar_coherencia(plan_a)
    assert any("2 lineas vigentes" in p for p in problemas), problemas


@pytest.mark.django_db
def test_13b_un_empate_de_secuencia_NO_es_un_problema_de_coherencia(
        org_a, plan_a, gestor_a):
    """
    E-5 sigue pendiente: E2 mide el empate, no lo convierte en error.
    """
    _programa(org_a, plan_a, 9411, MIER, gestor_a[1], secuencia=1)
    _programa(org_a, plan_a, 9412, MIER, gestor_a[1], secuencia=1)

    assert revisar_coherencia(plan_a) == []


# ===========================================================================
#  14  --  las rutas de D3 siguen siendo legibles
# ===========================================================================
@pytest.mark.django_db
def test_14_la_lectura_es_compatible_con_las_rutas_de_d3(
        cliente_a, org_a, plan_a, gestor_a):
    """
    Programación inicial · reprogramación en el plan · a otro plan ·
    adición formal a plan publicado. Los cuatro se leen.
    """
    #  inicial
    o1 = _programa(org_a, plan_a, 9420, MIER, gestor_a[1], secuencia=1)
    #  reprogramación dentro del plan
    o2 = _programa(org_a, plan_a, 9421, MIER, gestor_a[1], secuencia=2)
    reprogramar_orden(org=org_a, orden=o2, programada_para=VIER,
                      programacion_destino=plan_a, actor=gestor_a[1])
    #  reprogramación a otro plan
    o3 = _programa(org_a, plan_a, 9422, MIER, gestor_a[1], secuencia=3)
    plan_b = _plan(org_a, lunes=SEM2)
    reprogramar_orden(org=org_a, orden=o3, programada_para=MAR2,
                      programacion_destino=plan_b, actor=gestor_a[1])
    #  adición formal a plan publicado
    publicado = _plan(org_a, lunes=SEM2 + timedelta(weeks=1),
                      estado=ProgramacionSemanal.PUBLICADA)
    _programa(org_a, publicado, 9423,
              _dt(SEM2 + timedelta(weeks=1), 2), gestor_a[1],
              causa="falta_material", motivo="llegó el material")

    del_miercoles = cliente_a.get(URL, {"dia": str(MIER.date())}).json()
    assert [f["numero"] for f in del_miercoles["resultados"]] == [9420]

    del_viernes = cliente_a.get(URL, {"dia": str(VIER.date())}).json()
    assert [f["numero"] for f in del_viernes["resultados"]] == [9421]
    assert del_viernes["resultados"][0]["secuencia"] == 2

    del_plan_b = cliente_a.get(URL, {"plan": str(plan_b.id)}).json()
    assert del_plan_b["resultados"][0]["secuencia"] == 3

    del_publicado = cliente_a.get(URL, {"plan": str(publicado.id)}).json()
    assert del_publicado["count"] == 1


# ===========================================================================
#  Alcance: lo que E2 NO hace
# ===========================================================================
@pytest.mark.django_db
def test_el_resumen_no_interpreta_el_cero_ni_el_empate(org_a, plan_a,
                                                       gestor_a):
    for n in (9430, 9431):
        _programa(org_a, plan_a, n, MIER, gestor_a[1])
    res = resumen_de_jornada(lineas_de_jornada(org_a, dia=MIER.date()))

    #  Cuenta, no clasifica.
    assert res["secuencia_cero"] == 2
    #  CORREGIDO EN M03-E5-B, por la decisión E-2: el 0 no empata con nada.
    assert res["lineas_en_empate"] == 0
    for veredicto in ("error", "warning", "invalido", "incorrecto"):
        assert veredicto not in str(res).lower()


@pytest.mark.django_db
def test_e2_no_toca_m09(cliente_a, org_a, plan_a, gestor_a):
    from operaciones import supervisor
    from operaciones.models import PropuestaSupervisor
    _programa(org_a, plan_a, 9440, MIER, gestor_a[1])
    cliente_a.get(URL, {"dia": str(MIER.date())})
    assert PropuestaSupervisor.objects.count() == 0
    assert not hasattr(supervisor, "lineas_de_jornada")


@pytest.mark.django_db
def test_ninguna_conexion_saliente(cliente_a, org_a, plan_a, gestor_a):
    import http.client
    import socket

    _programa(org_a, plan_a, 9450, MIER, gestor_a[1])
    destinos = []
    original = socket.socket.connect

    def vigilado(self, direccion):
        destinos.append(direccion)
        return original(self, direccion)

    socket.socket.connect = vigilado
    try:
        cliente_a.get(URL, {"dia": str(MIER.date())})
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
