# -*- coding: utf-8 -*-
"""
================================================================================
 M03-E5-B  --  secuenciar una jornada entera, de una sola vez
================================================================================

Lo que estas pruebas afirman, más allá de que los números cambien:

  * que la jornada quede COMO EL USUARIO LA DEJÓ o no quede de ninguna forma --
    nunca a medias;
  * que nadie sobrescriba en silencio lo que otro acaba de cambiar;
  * que cada línea modificada tenga su evento, todas con el mismo lote, y que
    las que NO cambiaron no generen ninguno;
  * que nada fuera de 'secuencia' se mueva.

MÉTODO
------
La concurrencia se prueba con dos peticiones HTTP reales contra PostgreSQL, y
el estado final se verifica con una CONEXIÓN INDEPENDIENTE del ORM: si el
servicio se equivocara, el ORM podría repetir el error.
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
from operaciones.models import (NovedadOperativa, ProgramacionOrden,
                                ProgramacionSemanal)
from operaciones.programacion import (ErrorProgramacion, JornadaCambio,
                                      JornadaIncompleta, programar_orden,
                                      secuenciar_jornada)

LUNES = date(2026, 10, 5)
SEM2 = LUNES + timedelta(weeks=1)
URL = "/api/operaciones/programacion/jornada/secuenciar/"
JORNADA = "/api/operaciones/programacion/jornada/"


def _dt(lunes, dias, hora=9):
    return timezone.make_aware(
        datetime.combine(lunes + timedelta(days=dias), time(hora, 0)))


MIER = _dt(LUNES, 2)
JUEV = _dt(LUNES, 3)
MAR2 = _dt(SEM2, 1, 14)


def _version(org, codigo):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})


def _orden(org, numero):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=_version(org, f"e5_{numero}"),
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
    return _gestor(org_a, "jefe.a@e5.test")


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


def _item(linea, secuencia, leida="auto"):
    if leida == "auto":
        leida = linea.secuencia
    return {"linea": str(linea.id), "secuencia": secuencia,
            "secuencia_leida": leida}


def _cuerpo(plan, dia, items, **extra):
    d = {"plan": str(plan.id), "dia": str(dia), "lineas": items}
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
#  1-7  --  las formas de una jornada
# ===========================================================================
@pytest.mark.django_db
def test_1_jornada_vacia(cliente_a, plan_a):
    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(), []), format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "sin_cambios"
    assert r.json()["recibidas"] == 0
    assert EventoTrabajo.objects.count() == 0


@pytest.mark.django_db
def test_2_una_linea(cliente_a, org_a, plan_a, gestor_a):
    l1 = _linea(org_a, plan_a, 9801, MIER, gestor_a[1])
    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(), [_item(l1, 1)]),
                       format="json")
    assert r.status_code == 200
    assert r.json()["modificadas"] == 1
    l1.refresh_from_db()
    assert l1.secuencia == 1


@pytest.mark.django_db
def test_3_varias_lineas(cliente_a, org_a, plan_a, gestor_a):
    ls = [_linea(org_a, plan_a, 9810 + i, MIER, gestor_a[1]) for i in range(3)]
    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(l, i + 1) for i, l in enumerate(ls)]),
                       format="json")
    assert r.status_code == 200
    d = r.json()
    assert (d["recibidas"], d["modificadas"], d["sin_cambio"]) == (3, 3, 0)


@pytest.mark.django_db
def test_4_secuencia_1_2_3(cliente_a, org_a, plan_a, gestor_a):
    """El caso del encargo: A 1→3, B 2→1, C 3→2, reconstruible línea a línea."""
    a = _linea(org_a, plan_a, 9820, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9821, MIER, gestor_a[1], secuencia=2)
    c = _linea(org_a, plan_a, 9822, MIER, gestor_a[1], secuencia=3)

    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(a, 3), _item(b, 1), _item(c, 2)]),
                       format="json")
    assert r.status_code == 200

    a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
    assert (a.secuencia, b.secuencia, c.secuencia) == (3, 1, 2)

    transiciones = {
        e.datos["linea"]: (e.datos["anterior"], e.datos["nuevo"])
        for e in EventoTrabajo.objects.filter(tipo="secuencia_jornada")}
    assert transiciones[str(a.id)] == (1, 3)
    assert transiciones[str(b.id)] == (2, 1)
    assert transiciones[str(c.id)] == (3, 2)


@pytest.mark.django_db
def test_5_secuencias_repetidas_se_permiten(cliente_a, org_a, plan_a, gestor_a):
    a = _linea(org_a, plan_a, 9830, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9831, MIER, gestor_a[1], secuencia=2)

    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(a, 1, leida=1), _item(b, 1)]),
                       format="json")
    assert r.status_code == 200
    b.refresh_from_db()
    assert b.secuencia == 1
    #  El filtro lleva 'tipo': 'programar_orden' tambien escribe un evento
    #  con la clave 'linea' en 'datos', asi que sin el tipo la consulta
    #  devuelve dos.
    ev = EventoTrabajo.objects.get(tipo="secuencia_jornada",
                                   datos__linea=str(b.id))
    assert ev.datos["empate"]["hay_empate"] is True


@pytest.mark.django_db
def test_6_varias_lineas_en_cero(cliente_a, org_a, plan_a, gestor_a):
    """Dessecuenciar la jornada entera es legítimo, y 0 no produce empate."""
    ls = [_linea(org_a, plan_a, 9840 + i, MIER, gestor_a[1], secuencia=i + 1)
          for i in range(3)]
    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(l, 0) for l in ls]), format="json")
    assert r.status_code == 200
    for e in EventoTrabajo.objects.filter(tipo="secuencia_jornada"):
        assert e.datos["nuevo_sin_secuenciar"] is True
        assert e.datos["empate"]["hay_empate"] is False
    assert r.json()["resumen"]["lineas_en_empate"] == 0


@pytest.mark.django_db
def test_7_mezcla_de_cero_y_mayores(cliente_a, org_a, plan_a, gestor_a):
    a = _linea(org_a, plan_a, 9850, MIER, gestor_a[1], secuencia=5)
    b = _linea(org_a, plan_a, 9851, MIER, gestor_a[1])
    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(a, 0), _item(b, 1)]), format="json")
    assert r.status_code == 200
    res = r.json()["resumen"]
    assert res["secuencia_cero"] == 1
    assert res["secuencia_mayor_que_cero"] == 1


# ===========================================================================
#  8-9  --  sin cambio  (G-1)
# ===========================================================================
@pytest.mark.django_db
def test_8_todas_sin_cambio_responde_200_y_no_escribe(cliente_a, org_a, plan_a,
                                                      gestor_a):
    """G-1 aprobada: 200, sin eventos, sin modificar nada."""
    a = _linea(org_a, plan_a, 9860, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9861, MIER, gestor_a[1], secuencia=2)
    tocado = (a.updated_at, b.updated_at)

    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(a, 1), _item(b, 2)]), format="json")
    assert r.status_code == 200
    d = r.json()
    assert d["resultado"] == "sin_cambios"
    assert (d["modificadas"], d["sin_cambio"]) == (0, 2)
    assert d["lote"] is None

    assert EventoTrabajo.objects.filter(tipo__startswith="secuencia").count() == 0
    a.refresh_from_db(); b.refresh_from_db()
    assert (a.updated_at, b.updated_at) == tocado      # ni se tocó la fila


@pytest.mark.django_db
def test_9_una_sin_cambio_y_otras_modificadas(cliente_a, org_a, plan_a,
                                              gestor_a):
    a = _linea(org_a, plan_a, 9870, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9871, MIER, gestor_a[1], secuencia=2)
    c = _linea(org_a, plan_a, 9872, MIER, gestor_a[1], secuencia=3)

    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(a, 1), _item(b, 5), _item(c, 6)]),
                       format="json")
    assert r.status_code == 200
    d = r.json()
    assert (d["recibidas"], d["modificadas"], d["sin_cambio"]) == (3, 2, 1)

    #  Regla 23: la que no cambió NO genera evento.
    lineas_con_evento = {e.datos["linea"] for e in
                         EventoTrabajo.objects.filter(tipo="secuencia_jornada")}
    assert lineas_con_evento == {str(b.id), str(c.id)}
    for e in EventoTrabajo.objects.filter(tipo="secuencia_jornada"):
        assert e.datos["lote_sin_cambio"] == 1


# ===========================================================================
#  10-12  --  conjunto incorrecto
# ===========================================================================
@pytest.mark.django_db
def test_10_linea_inexistente(cliente_a, org_a, plan_a, gestor_a):
    import uuid
    l1 = _linea(org_a, plan_a, 9880, MIER, gestor_a[1], secuencia=1)
    fantasma = str(uuid.uuid4())

    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(), [
        _item(l1, 2),
        {"linea": fantasma, "secuencia": 1, "secuencia_leida": 0}]),
        format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "JORNADA_INCOMPLETA"
    assert fantasma in r.json()["desconocidas"]

    l1.refresh_from_db()
    assert l1.secuencia == 1                 # sin cambios parciales
    assert EventoTrabajo.objects.filter(tipo="secuencia_jornada").count() == 0


@pytest.mark.django_db
def test_11_linea_de_otra_jornada(cliente_a, org_a, plan_a, gestor_a):
    """Otro día, el mismo plan."""
    mier = _linea(org_a, plan_a, 9890, MIER, gestor_a[1], secuencia=1)
    juev = _linea(org_a, plan_a, 9891, JUEV, gestor_a[1], secuencia=1)

    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(mier, 2), _item(juev, 3)]),
                       format="json")
    assert r.status_code == 400
    assert str(juev.id) in [x["linea"] for x in r.json()["sobrantes"]]

    mier.refresh_from_db(); juev.refresh_from_db()
    assert (mier.secuencia, juev.secuencia) == (1, 1)


@pytest.mark.django_db
def test_12_linea_de_otro_plan(cliente_a, org_a, plan_a, gestor_a):
    plan_b = _plan(org_a, lunes=SEM2)
    aqui = _linea(org_a, plan_a, 9900, MIER, gestor_a[1], secuencia=1)
    alla = _linea(org_a, plan_b, 9901, MAR2, gestor_a[1], secuencia=1)

    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(aqui, 2), _item(alla, 3)]),
                       format="json")
    assert r.status_code == 400
    aqui.refresh_from_db(); alla.refresh_from_db()
    assert (aqui.secuencia, alla.secuencia) == (1, 1)


@pytest.mark.django_db
def test_12b_falta_una_linea_de_la_jornada(cliente_a, org_a, plan_a, gestor_a):
    """G-2: la petición representa el día ENTERO; omitir una es un error."""
    a = _linea(org_a, plan_a, 9910, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9911, MIER, gestor_a[1], secuencia=2)

    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(), [_item(a, 5)]),
                       format="json")
    assert r.status_code == 400
    assert str(b.id) in r.json()["faltantes"]
    a.refresh_from_db()
    assert a.secuencia == 1


# ===========================================================================
#  13-16  --  borrador, publicado y motivo
# ===========================================================================
@pytest.mark.django_db
def test_13_plan_borrador_no_exige_motivo(cliente_a, org_a, plan_a, gestor_a):
    l1 = _linea(org_a, plan_a, 9920, MIER, gestor_a[1])
    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(), [_item(l1, 1)]),
                       format="json")
    assert r.status_code == 200
    assert NovedadOperativa.objects.count() == 0
    assert EventoTrabajo.objects.filter(tipo="secuencia_jornada").count() == 1


@pytest.mark.django_db
def test_14_15_plan_publicado_con_motivo(cliente_a, org_a, gestor_a):
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    a = _linea(org_a, publicado, 9930, MIER, gestor_a[1], secuencia=1,
               causa="falta_material", motivo="ya llegó")
    b = _linea(org_a, publicado, 9931, MIER, gestor_a[1], secuencia=2,
               causa="falta_material", motivo="ya llegó")

    r = cliente_a.post(URL, _cuerpo(publicado, MIER.date(),
                                    [_item(a, 2), _item(b, 1)],
                                    causa="cambio_de_prioridad",
                                    motivo="el cliente pidió otro orden"),
                       format="json")
    assert r.status_code == 200

    eventos = list(EventoTrabajo.objects.filter(
        tipo="secuencia_jornada_en_plan_publicado"))
    assert len(eventos) == 2
    for e in eventos:
        assert e.datos["jornada"]["plan_estado"] == ProgramacionSemanal.PUBLICADA
        assert e.datos["causa"] == "cambio_de_prioridad"
        assert e.datos["novedad"] is not None

    #  UNA novedad por lote, no una por línea.
    assert NovedadOperativa.objects.filter(
        tipo=NovedadOperativa.CAMBIO_PRIORIDAD).count() == 1


@pytest.mark.django_db
def test_16_plan_publicado_sin_motivo_se_rechaza(cliente_a, org_a, gestor_a):
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    a = _linea(org_a, publicado, 9940, MIER, gestor_a[1], secuencia=1,
               causa="bloqueo", motivo="x")

    r = cliente_a.post(URL, _cuerpo(publicado, MIER.date(), [_item(a, 4)]),
                       format="json")
    assert r.status_code == 400
    a.refresh_from_db()
    assert a.secuencia == 1
    assert EventoTrabajo.objects.filter(
        tipo__startswith="secuencia_jornada").count() == 0


@pytest.mark.django_db
def test_16b_publicado_sin_cambios_no_exige_motivo(cliente_a, org_a, gestor_a):
    """
    Una petición que no cambia nada no tiene nada que justificar -- y exigirlo
    haría imposible el caso G-1.
    """
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    a = _linea(org_a, publicado, 9945, MIER, gestor_a[1], secuencia=3,
               causa="bloqueo", motivo="x")
    r = cliente_a.post(URL, _cuerpo(publicado, MIER.date(), [_item(a, 3)]),
                       format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "sin_cambios"


# ===========================================================================
#  17-18  --  concurrencia real
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_17_A_no_sobrescribe_el_cambio_de_B(org_a, gestor_a):
    """
    A lee la jornada · B cambia una línea · A intenta aplicar lo que leyó.

    A NO debe sobrescribir a B. Sin 'secuencia_leida' esto sería imposible de
    detectar: 'ProgramacionOrden' no tiene campo de concurrencia optimista.
    """
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")

    u, perfil = gestor_a
    plan = _plan(org_a)
    a = _linea(org_a, plan, 9950, MIER, perfil, secuencia=1)
    b = _linea(org_a, plan, 9951, MIER, perfil, secuencia=2)
    cli = _cli(u, org_a, perfil)

    #  A lee la jornada (1 y 2).
    leido = [_item(a, 2, leida=1), _item(b, 1, leida=2)]

    #  B cambia la línea 'b' de 2 a 7, por la vía individual de E4.
    otro = cli.post(f"/api/operaciones/programacion/linea/{b.id}/secuencia/",
                    {"secuencia": 7}, format="json")
    assert otro.status_code == 200

    #  A aplica lo que había leído.
    r = cli.post(URL, _cuerpo(plan, MIER.date(), leido), format="json")
    assert r.status_code == 409
    assert r.json()["error"] == "JORNADA_CAMBIO"
    assert r.json()["conflictos"][0]["leida"] == 2
    assert r.json()["conflictos"][0]["actual"] == 7

    #  NADA se aplicó -- ni la línea que sí coincidía.
    f = {str(x["id"]): x["secuencia"] for x in _desde_fuera(
        "select id, secuencia from operaciones_programacion_orden "
        "where dia = %s", [MIER.date()])}
    assert f[str(a.id)] == 1          # A no movió la suya
    assert f[str(b.id)] == 7          # B sobrevive


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_18_dos_secuenciaciones_concurrentes_de_la_misma_jornada(org_a,
                                                                 gestor_a):
    """
    Dos procesos reales aplican la misma jornada a la vez, a órdenes distintos.

    Una gana; la otra tiene que ver el trabajo de la primera. Lo que NO puede
    pasar es que queden mezcladas, ni que la bitácora afirme una transición que
    no ocurrió.
    """
    if connection.vendor != "postgresql":
        pytest.skip("la concurrencia real requiere PostgreSQL")

    u, perfil = gestor_a
    plan = _plan(org_a)
    a = _linea(org_a, plan, 9960, MIER, perfil, secuencia=1)
    b = _linea(org_a, plan, 9961, MIER, perfil, secuencia=2)
    cli = _cli(u, org_a, perfil)

    def aplica(par):
        sa, sb = par
        try:
            return cli.post(URL, _cuerpo(plan, MIER.date(),
                                         [_item(a, sa, leida=1),
                                          _item(b, sb, leida=2)]),
                            format="json").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(aplica, [(3, 4), (5, 6)]))

    #  La segunda ve la jornada ya cambiada y se rechaza: 200 + 409.
    assert codigos == [200, 409], codigos

    filas = {str(x["id"]): x["secuencia"] for x in _desde_fuera(
        "select id, secuencia from operaciones_programacion_orden "
        "where dia = %s", [MIER.date()])}
    #  Un solo par coherente, nunca una mezcla de las dos peticiones.
    assert (filas[str(a.id)], filas[str(b.id)]) in [(3, 4), (5, 6)], filas

    #  Un solo lote de eventos.
    lotes = {e.datos["lote"] for e in
             EventoTrabajo.objects.filter(tipo="secuencia_jornada")}
    assert len(lotes) == 1, lotes


# ===========================================================================
#  19-20  --  rollback
# ===========================================================================
@pytest.mark.django_db
def test_19_rollback_por_fallo_de_escritura(org_a, plan_a, gestor_a):
    a = _linea(org_a, plan_a, 9970, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9971, MIER, gestor_a[1], secuencia=2)

    original = ProgramacionOrden.save
    llamadas = {"n": 0}

    def revienta_la_segunda(self, *args, **kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise RuntimeError("fallo inyectado en la segunda línea")
        return original(self, *args, **kwargs)

    with mock.patch.object(ProgramacionOrden, "save", revienta_la_segunda):
        with pytest.raises(RuntimeError):
            secuenciar_jornada(org=org_a, plan=plan_a, dia=MIER.date(),
                               lineas=[_item(a, 8), _item(b, 9)],
                               actor=gestor_a[1])

    a.refresh_from_db(); b.refresh_from_db()
    #  Ni siquiera la primera, que sí se había escrito.
    assert (a.secuencia, b.secuencia) == (1, 2)
    assert EventoTrabajo.objects.filter(tipo="secuencia_jornada").count() == 0


@pytest.mark.django_db
def test_20_rollback_por_fallo_de_auditoria(org_a, plan_a, gestor_a):
    a = _linea(org_a, plan_a, 9980, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9981, MIER, gestor_a[1], secuencia=2)

    with mock.patch.object(EventoTrabajo.objects, "create",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            secuenciar_jornada(org=org_a, plan=plan_a, dia=MIER.date(),
                               lineas=[_item(a, 8), _item(b, 9)],
                               actor=gestor_a[1])

    a.refresh_from_db(); b.refresh_from_db()
    assert (a.secuencia, b.secuencia) == (1, 2)
    assert NovedadOperativa.objects.count() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_20b_el_rollback_se_ve_desde_fuera(org_a, plan_a, gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    a = _linea(org_a, plan_a, 9982, MIER, gestor_a[1], secuencia=1)

    with mock.patch.object(EventoTrabajo.objects, "create",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            secuenciar_jornada(org=org_a, plan=plan_a, dia=MIER.date(),
                               lineas=[_item(a, 8)], actor=gestor_a[1])

    f = _desde_fuera("select secuencia from operaciones_programacion_orden "
                     "where id = %s", [str(a.id)])[0]
    assert f["secuencia"] == 1


# ===========================================================================
#  21-22  --  idempotencia
# ===========================================================================
@pytest.mark.django_db
def test_21_22_idempotencia_y_replay(cliente_a, org_a, plan_a, gestor_a):
    a = _linea(org_a, plan_a, 9990, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9991, MIER, gestor_a[1], secuencia=2)
    cuerpo = _cuerpo(plan_a, MIER.date(), [_item(a, 4), _item(b, 5)])

    p = cliente_a.post(URL, cuerpo, format="json",
                       HTTP_IDEMPOTENCY_KEY="e5-clave-1")
    assert p.status_code == 200
    lote = p.json()["lote"]

    s = cliente_a.post(URL, cuerpo, format="json",
                       HTTP_IDEMPOTENCY_KEY="e5-clave-1")
    assert s.status_code == 200
    assert s.get("Idempotent-Replay") == "true"
    assert s.json()["lote"] == lote          # el mismo, no uno nuevo

    #  Sin eventos duplicados: 2 líneas, 2 eventos, 1 lote.
    eventos = list(EventoTrabajo.objects.filter(tipo="secuencia_jornada"))
    assert len(eventos) == 2
    assert {e.datos["lote"] for e in eventos} == {lote}


# ===========================================================================
#  23-24  --  aislamiento y permisos
# ===========================================================================
@pytest.mark.django_db
def test_23_otra_organizacion(cliente_a, org_b):
    plan_b = _plan(org_b)
    ub, pb = _gestor(org_b, "jefe.b@e5.test")
    lb = _linea(org_b, plan_b, 9995, MIER, pb, secuencia=1)

    r = cliente_a.post(URL, _cuerpo(plan_b, MIER.date(), [_item(lb, 5)]),
                       format="json")
    assert r.status_code == 404          # el plan no existe para A
    lb.refresh_from_db()
    assert lb.secuencia == 1


@pytest.mark.django_db
def test_23b_el_servicio_no_confia_en_la_vista(org_a, org_b, gestor_a):
    plan_b = _plan(org_b)
    with pytest.raises(ErrorProgramacion) as e:
        secuenciar_jornada(org=org_a, plan=plan_b, dia=MIER.date(),
                           lineas=[], actor=gestor_a[1])
    assert "otra empresa" in str(e.value)


@pytest.mark.django_db
def test_24_permiso_insuficiente(org_a, plan_a, gestor_a, regular_user,
                                 user_profile):
    l1 = _linea(org_a, plan_a, 9996, MIER, gestor_a[1], secuencia=1)
    r = _cli(regular_user, org_a, user_profile).post(
        URL, _cuerpo(plan_a, MIER.date(), [_item(l1, 5)]), format="json")
    assert r.status_code == 403
    l1.refresh_from_db()
    assert l1.secuencia == 1


@pytest.mark.django_db
def test_24b_sin_sesion(org_a, plan_a, gestor_a):
    l1 = _linea(org_a, plan_a, 9997, MIER, gestor_a[1])
    assert APIClient().post(URL, _cuerpo(plan_a, MIER.date(), [_item(l1, 1)]),
                            format="json").status_code in (401, 403)


# ===========================================================================
#  25-28  --  lo que NO se toca
# ===========================================================================
@pytest.mark.django_db
def test_25_a_28_no_toca_nada_de_la_orden(cliente_a, org_a, plan_a, gestor_a):
    l1 = _linea(org_a, plan_a, 9998, MIER, gestor_a[1], secuencia=1,
                zona="Norte", prioridad=10)
    orden = l1.orden
    AsignacionTrabajo.objects.create(orden=orden, profile=gestor_a[1],
                                     rol="tecnico", es_principal=True)
    antes_orden = (orden.programada_para, orden.estado_operativo,
                   orden.estado_validacion, orden.revision, orden.vuelta)
    antes_asig = list(AsignacionTrabajo.objects.filter(orden=orden)
                      .values_list("profile_id", "rol", "es_principal"))
    antes_linea = (l1.dia, l1.hora_inicio, l1.zona, l1.prioridad, l1.estado,
                   l1.programacion_id, l1.orden_id)

    assert cliente_a.post(URL, _cuerpo(plan_a, MIER.date(), [_item(l1, 7)]),
                          format="json").status_code == 200

    orden.refresh_from_db(); l1.refresh_from_db()
    assert (orden.programada_para, orden.estado_operativo,       # 25, 26
            orden.estado_validacion, orden.revision,
            orden.vuelta) == antes_orden
    assert list(AsignacionTrabajo.objects.filter(orden=orden)     # 27
                .values_list("profile_id", "rol", "es_principal")) == antes_asig
    assert (l1.dia, l1.hora_inicio, l1.zona, l1.prioridad,        # 28
            l1.estado, l1.programacion_id, l1.orden_id) == antes_linea
    assert l1.secuencia == 7


# ===========================================================================
#  29-33  --  auditoría y esquema
# ===========================================================================
@pytest.mark.django_db
def test_29_30_un_evento_por_linea_con_lote_comun(cliente_a, org_a, plan_a,
                                                  gestor_a):
    ls = [_linea(org_a, plan_a, 9700 + i, MIER, gestor_a[1], secuencia=i + 1)
          for i in range(3)]
    r = cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                    [_item(l, 10 + i) for i, l in enumerate(ls)]),
                       format="json")
    assert r.status_code == 200
    lote = r.json()["lote"]

    eventos = list(EventoTrabajo.objects.filter(tipo="secuencia_jornada"))
    assert len(eventos) == 3                              # 29
    assert {e.datos["lote"] for e in eventos} == {lote}   # 30

    #  Auditoría completa, evento por evento.
    por_linea = {e.datos["linea"]: e for e in eventos}
    for i, l in enumerate(ls):
        e = por_linea[str(l.id)]
        assert e.orden_id == l.orden_id
        assert e.profile_id == gestor_a[1].id
        assert e.created_at is not None
        assert e.datos["anterior"] == i + 1
        assert e.datos["nuevo"] == 10 + i
        assert e.datos["anterior_sin_secuenciar"] is False
        assert e.datos["jornada"]["dia"] == str(MIER.date())
        assert e.datos["lote_tamano"] == 3
        assert e.datos["lote_cambiadas"] == 3


@pytest.mark.django_db
def test_31_las_lineas_sin_cambio_no_generan_evento(cliente_a, org_a, plan_a,
                                                    gestor_a):
    a = _linea(org_a, plan_a, 9710, MIER, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9711, MIER, gestor_a[1], secuencia=2)
    cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                [_item(a, 1), _item(b, 9)]), format="json")
    assert EventoTrabajo.objects.filter(tipo="secuencia_jornada").count() == 1
    assert EventoTrabajo.objects.get(
        tipo="secuencia_jornada").datos["linea"] == str(b.id)


@pytest.mark.django_db
def test_32_sin_eventos_duplicados(cliente_a, org_a, plan_a, gestor_a):
    ls = [_linea(org_a, plan_a, 9720 + i, MIER, gestor_a[1]) for i in range(4)]
    cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                [_item(l, i + 1) for i, l in enumerate(ls)]),
                   format="json")
    claves = [e.datos["linea"] for e in
              EventoTrabajo.objects.filter(tipo="secuencia_jornada")]
    assert len(claves) == len(set(claves)) == 4


@pytest.mark.django_db
@pytest.mark.postgres_only
def test_33_no_existe_unique_sobre_secuencia(org_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    with connection.cursor() as c:
        c.execute("""
            select conname, pg_get_constraintdef(oid)
            from pg_constraint
            where conrelid = 'operaciones_programacion_orden'::regclass
              and contype = 'u'""")
        uniques = c.fetchall()
        c.execute("""
            select indexname, indexdef from pg_indexes
            where tablename = 'operaciones_programacion_orden'
              and indexdef ilike '%%unique%%'""")
        indices = c.fetchall()

    for _, definicion in uniques:
        assert "secuencia" not in definicion, definicion
    for _, definicion in indices:
        assert "secuencia" not in definicion, definicion


# ===========================================================================
#  Alcance
# ===========================================================================
@pytest.mark.django_db
def test_la_lectura_de_e2_muestra_el_resultado(cliente_a, org_a, plan_a,
                                               gestor_a):
    a = _linea(org_a, plan_a, 9730, MIER, gestor_a[1], secuencia=3)
    b = _linea(org_a, plan_a, 9731, MIER, gestor_a[1], secuencia=1)
    cliente_a.post(URL, _cuerpo(plan_a, MIER.date(),
                                [_item(a, 1), _item(b, 2)]), format="json")

    d = cliente_a.get(JORNADA, {"dia": str(MIER.date())}).json()
    assert [f["numero"] for f in d["resultados"]] == [9730, 9731]


@pytest.mark.django_db
def test_e5_no_toca_m09(cliente_a, org_a, plan_a, gestor_a):
    import inspect
    from operaciones import supervisor
    from operaciones.models import PropuestaSupervisor
    assert "secuencia" not in inspect.getsource(supervisor)

    l1 = _linea(org_a, plan_a, 9740, MIER, gestor_a[1])
    cliente_a.post(URL, _cuerpo(plan_a, MIER.date(), [_item(l1, 1)]),
                   format="json")
    assert PropuestaSupervisor.objects.count() == 0


@pytest.mark.django_db
def test_ninguna_conexion_saliente(cliente_a, org_a, plan_a, gestor_a):
    import http.client
    import socket

    l1 = _linea(org_a, plan_a, 9750, MIER, gestor_a[1])
    destinos = []
    original = socket.socket.connect

    def vigilado(self, direccion):
        destinos.append(direccion)
        return original(self, direccion)

    socket.socket.connect = vigilado
    try:
        cliente_a.post(URL, _cuerpo(plan_a, MIER.date(), [_item(l1, 2)]),
                       format="json")
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
