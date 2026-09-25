# -*- coding: utf-8 -*-
"""
================================================================================
 M03-E5-C  --  validación de cierre de la secuenciación
================================================================================

E5-C no agrega funcionalidad: comprueba lo que las suites de E4, E5-B y B-1 NO
llegaban a afirmar. Aquí van solo esos huecos, para no duplicar lo ya probado:

  * el ORDEN REAL de los locks, medido sobre el SQL que se ejecuta;
  * el rollback por fallo de VALIDACIÓN y por fallo de IDEMPOTENCIA
    (las suites previas cubren el de escritura y el de auditoría);
  * las dos protecciones de idempotencia que faltaban: clave reutilizada con
    otro cuerpo, y cuerpo distinto como operación nueva;
  * multi-tenant y protección de la OT verificados desde CONEXIÓN
    INDEPENDIENTE, no por ORM;
  * que E4 y E5 coincidan también en "aplicado", no solo en "sin_cambios";
  * deriva de arquitectura: que E5 no haya traído sistemas paralelos.
================================================================================
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest import mock

import psycopg
import pytest
from django.db import connection
from django.utils import timezone
from psycopg.rows import dict_row
from rest_framework.test import APIClient

from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones.models import (NovedadOperativa, ProgramacionOrden,
                                ProgramacionSemanal)
from operaciones.programacion import (ErrorProgramacion, programar_orden,
                                      secuenciar_jornada)

LUNES = date(2026, 10, 5)
SECUENCIAR = "/api/operaciones/programacion/jornada/secuenciar/"


def _dt(dias, hora=9):
    return timezone.make_aware(
        datetime.combine(LUNES + timedelta(days=dias), time(hora, 0)))


MIER = _dt(2)


def _version(org, codigo):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})


def _orden(org, numero):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero,
        tipo_trabajo_version=_version(org, f"e5c_{numero}"),
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
    return _gestor(org_a, "jefe.a@e5c.test")


@pytest.fixture
def cliente_a(org_a, gestor_a):
    return _cli(gestor_a[0], org_a, gestor_a[1])


def _linea(org, plan, numero, actor, secuencia=None, cuando=None, **extra):
    orden = _orden(org, numero)
    programar_orden(org=org, orden=orden, programacion=plan,
                    programada_para=cuando or MIER, actor=actor,
                    secuencia=secuencia, **extra)
    orden.refresh_from_db()
    return ProgramacionOrden.objects.get(orden=orden)


def _item(linea, secuencia, leida="auto"):
    if leida == "auto":
        leida = linea.secuencia
    return {"linea": str(linea.id), "secuencia": secuencia,
            "secuencia_leida": leida}


def _cuerpo(plan, items, dia=None):
    return {"plan": str(plan.id), "dia": str(dia or MIER.date()),
            "lineas": items}


def _url_linea(linea):
    return f"/api/operaciones/programacion/linea/{linea.id}/secuencia/"


def _desde_fuera(sql, params=None):
    """Lee la base con una conexión ajena al ORM de la prueba."""
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
#  §6  --  EL ORDEN REAL DE LOS LOCKS
# ===========================================================================
@pytest.mark.django_db
def test_6_el_lock_de_lineas_va_antes_que_el_del_plan(org_a, plan_a, gestor_a):
    """
    El orden se afirma sobre el SQL QUE SE EJECUTA, no sobre el orden de las
    líneas del fuente.

    POR QUÉ NO DEBE INVERTIRSE
    --------------------------
    M03-E4 bloquea 'ProgramacionOrden' y después el plan. Si E5 lo hiciera al
    revés, E4 sostendría la línea pidiendo el plan mientras E5 sostiene el plan
    pidiendo la línea: ciclo, y un interbloqueo que solo aparece bajo carga.
    Por eso el plan es el ÚLTIMO lock en las seis operaciones del módulo.
    """
    import django.db.backends.utils as dbutils

    a = _linea(org_a, plan_a, 9101, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9102, gestor_a[1], secuencia=2)

    sentencias = []
    original = dbutils.CursorWrapper.execute

    def espiado(self, sql, params=None):
        sentencias.append(" ".join(str(sql).split()).lower())
        return original(self, sql, params)

    dbutils.CursorWrapper.execute = espiado
    try:
        secuenciar_jornada(org=org_a, plan=plan_a, dia=MIER.date(),
                           lineas=[_item(a, 5), _item(b, 6)],
                           actor=gestor_a[1])
    finally:
        dbutils.CursorWrapper.execute = original

    bloqueos = [(i, s) for i, s in enumerate(sentencias) if "for update" in s]
    assert bloqueos, "no se emitió ningún FOR UPDATE"

    de_lineas = [i for i, s in bloqueos
                 if "operaciones_programacion_orden" in s]
    de_plan = [i for i, s in bloqueos
               if "operaciones_programacion_semanal" in s]
    assert de_lineas, "no se bloquearon las líneas"
    assert de_plan, "no se bloqueó el plan"
    #  El orden REAL: toda línea se bloquea antes que el plan.
    assert max(de_lineas) < min(de_plan), (
        f"el plan se bloqueó antes que las líneas: {bloqueos}")

    #  Y las líneas se piden ordenadas por id, que es lo que evita el ciclo
    #  entre dos secuenciaciones concurrentes.
    sql_lineas = sentencias[de_lineas[0]]
    assert 'order by' in sql_lineas and '."id" asc' in sql_lineas, sql_lineas


# ===========================================================================
#  §4A y §4D  --  los dos rollbacks que faltaban
# ===========================================================================
@pytest.mark.django_db
def test_4a_rollback_por_fallo_de_validacion(org_a, plan_a, gestor_a):
    """
    La validación ocurre DESPUÉS de bloquear y releer. Un fallo ahí no debe
    dejar rastro -- ni siquiera de las líneas que sí eran correctas.
    """
    a = _linea(org_a, plan_a, 9110, gestor_a[1], secuencia=1)
    otro_dia = _linea(org_a, plan_a, 9111, gestor_a[1], secuencia=1,
                      cuando=_dt(3))

    with pytest.raises(ErrorProgramacion):
        #  'otro_dia' es del jueves: el conjunto no es la jornada del miércoles.
        secuenciar_jornada(org=org_a, plan=plan_a, dia=MIER.date(),
                           lineas=[_item(a, 7), _item(otro_dia, 8)],
                           actor=gestor_a[1])

    a.refresh_from_db(); otro_dia.refresh_from_db()
    assert (a.secuencia, otro_dia.secuencia) == (1, 1)
    assert EventoTrabajo.objects.filter(
        tipo__startswith="secuencia").count() == 0
    assert NovedadOperativa.objects.count() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_4d_la_frontera_de_la_idempotencia_esta_fuera_de_la_transaccion(
        cliente_a, org_a, plan_a, gestor_a):
    """
    §4D del encargo, medido -- y el resultado NO es el que la pregunta suponía.

    LO QUE SE MIDIÓ
    ---------------
    'manejar_idempotencia' trabaja en TRES transacciones separadas
    (campo/services/idempotencia.py):

        1. crear la MutacionIdempotente en PROCESANDO   (transaction.atomic propio)
        2. ejecutar la vista                            (su propio atomic)
        3. marcarla COMPLETADA

    Así que un fallo en el paso 3 ocurre DESPUÉS de que la operación de negocio
    ya hizo commit: el dato queda cambiado y la mutación se queda en
    PROCESANDO. Un reintento con la misma clave recibiría 409 OPERACION_EN_CURSO
    indefinidamente.

    ESTO NO LO INTRODUJO E5
    -----------------------
    Es una propiedad del mecanismo existente, usado por M03-B, M03-D3, M03-E4 y
    los endpoints de campo desde antes. La prueba lo FIJA para que la frontera
    quede documentada en vez de suponerse.

    La atomicidad que E5 sí garantiza --y que las suites de E5-B prueban-- es la
    de la OPERACIÓN: si la vista falla, el paso 2 borra la mutación y no queda
    ni un cambio ni un evento.
    """
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    from campo.models import MutacionIdempotente

    a = _linea(org_a, plan_a, 9120, gestor_a[1], secuencia=1)

    #  (i) fallo ANTES de ejecutar la vista: nada se aplica.
    with mock.patch.object(MutacionIdempotente.objects, "create",
                           side_effect=RuntimeError("fallo antes")):
        with pytest.raises(RuntimeError):
            cliente_a.post(SECUENCIAR, _cuerpo(plan_a, [_item(a, 9)]),
                           format="json", HTTP_IDEMPOTENCY_KEY="e5c-antes")
    assert _desde_fuera("select secuencia from operaciones_programacion_orden "
                        "where id = %s", [str(a.id)])[0]["secuencia"] == 1
    assert _desde_fuera("select count(*) n from campo_evento_trabajo "
                        "where tipo like 'secuencia%%'")[0]["n"] == 0

    #  (ii) fallo DESPUÉS de que la vista aplicó: el cambio SÍ queda.
    original = MutacionIdempotente.objects.filter
    llamadas = {"n": 0}

    def revienta_al_completar(*args, **kwargs):
        llamadas["n"] += 1
        raise RuntimeError("fallo al marcar COMPLETADA")

    with mock.patch.object(MutacionIdempotente.objects, "filter",
                           revienta_al_completar):
        with pytest.raises(RuntimeError):
            cliente_a.post(SECUENCIAR, _cuerpo(plan_a, [_item(a, 9)]),
                           format="json", HTTP_IDEMPOTENCY_KEY="e5c-despues")

    #  [MEDIDO] La operación de negocio hizo commit antes del fallo.
    f = _desde_fuera("select secuencia from operaciones_programacion_orden "
                     "where id = %s", [str(a.id)])[0]
    assert f["secuencia"] == 9, (
        "la operación de negocio debería haber hecho commit antes del fallo "
        "de la idempotencia; si esto falla, la frontera cambió")
    #  Y su evento también: la operación fue completa y coherente.
    assert _desde_fuera("select count(*) n from campo_evento_trabajo "
                        "where tipo like 'secuencia%%'")[0]["n"] == 1


# ===========================================================================
#  §7.5 y §7.6  --  las dos protecciones de idempotencia que faltaban
# ===========================================================================
@pytest.mark.django_db
def test_7_5_otro_cuerpo_con_otra_clave_es_otra_operacion(cliente_a, org_a,
                                                          plan_a, gestor_a):
    a = _linea(org_a, plan_a, 9130, gestor_a[1], secuencia=1)

    p = cliente_a.post(SECUENCIAR, _cuerpo(plan_a, [_item(a, 4)]),
                       format="json", HTTP_IDEMPOTENCY_KEY="e5c-k1")
    assert p.status_code == 200 and p.json()["resultado"] == "aplicado"

    a.refresh_from_db()
    s = cliente_a.post(SECUENCIAR, _cuerpo(plan_a, [_item(a, 7)]),
                       format="json", HTTP_IDEMPOTENCY_KEY="e5c-k2")
    assert s.status_code == 200 and s.json()["resultado"] == "aplicado"
    assert s.get("Idempotent-Replay") is None
    assert s.json()["lote"] != p.json()["lote"]

    a.refresh_from_db()
    assert a.secuencia == 7
    assert EventoTrabajo.objects.filter(tipo="secuencia_jornada").count() == 2


@pytest.mark.django_db
def test_7_6_la_misma_clave_con_otro_cuerpo_sigue_protegida(cliente_a, org_a,
                                                            plan_a, gestor_a):
    """La protección existente de 'manejar_idempotencia', intacta."""
    a = _linea(org_a, plan_a, 9140, gestor_a[1], secuencia=1)

    p = cliente_a.post(SECUENCIAR, _cuerpo(plan_a, [_item(a, 3)]),
                       format="json", HTTP_IDEMPOTENCY_KEY="e5c-misma")
    assert p.status_code == 200

    a.refresh_from_db()
    s = cliente_a.post(SECUENCIAR, _cuerpo(plan_a, [_item(a, 8)]),
                       format="json", HTTP_IDEMPOTENCY_KEY="e5c-misma")
    assert s.status_code == 409
    assert s.json()["error"] == "IDEMPOTENCY_KEY_REUSED"

    a.refresh_from_db()
    assert a.secuencia == 3          # la segunda no se aplicó
    assert EventoTrabajo.objects.filter(tipo="secuencia_jornada").count() == 1


# ===========================================================================
#  §1.6  --  E4 y E5 coinciden también en "aplicado"
# ===========================================================================
@pytest.mark.django_db
def test_1_6_las_dos_rutas_dicen_aplicado_igual(cliente_a, org_a, plan_a,
                                                gestor_a):
    a = _linea(org_a, plan_a, 9150, gestor_a[1], secuencia=1)
    b = _linea(org_a, plan_a, 9151, gestor_a[1], secuencia=1)

    por_linea = cliente_a.post(_url_linea(a), {"secuencia": 5}, format="json")
    b.refresh_from_db()
    a.refresh_from_db()
    por_jornada = cliente_a.post(
        SECUENCIAR, _cuerpo(plan_a, [_item(a, 5, leida=5), _item(b, 6)]),
        format="json")

    assert por_linea.status_code == por_jornada.status_code == 200
    assert (por_linea.json()["resultado"]
            == por_jornada.json()["resultado"] == "aplicado")


# ===========================================================================
#  §3  --  duplicados A=1, B=1, C=2
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_3_duplicados_son_validos_y_no_se_tocan(cliente_a, org_a, plan_a,
                                                gestor_a):
    #  'transaction=True' porque la comprobacion es por conexion independiente:
    #  sin commit, esa conexion no ve nada y la prueba mediria el aislamiento
    #  de PostgreSQL en vez de lo que dice medir.
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    a = _linea(org_a, plan_a, 9160, gestor_a[1])
    b = _linea(org_a, plan_a, 9161, gestor_a[1])
    c = _linea(org_a, plan_a, 9162, gestor_a[1])

    r = cliente_a.post(SECUENCIAR,
                       _cuerpo(plan_a, [_item(a, 1), _item(b, 1), _item(c, 2)]),
                       format="json")
    assert r.status_code == 200

    filas = {x["id"]: x["secuencia"] for x in _desde_fuera(
        "select id, secuencia from operaciones_programacion_orden "
        "where dia = %s", [MIER.date()])}
    assert sorted(filas.values()) == [1, 1, 2]     # ni compactado ni reordenado

    #  Y sigue sin existir UNIQUE sobre secuencia.
    uniques = _desde_fuera(
        "select pg_get_constraintdef(oid) d from pg_constraint "
        "where conrelid = 'operaciones_programacion_orden'::regclass "
        "and contype = 'u'")
    for u in uniques:
        assert "secuencia" not in u["d"], u["d"]


# ===========================================================================
#  §10  --  la OT, verificada desde fuera del ORM
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_10_la_orden_no_cambia_leida_desde_fuera(cliente_a, org_a, plan_a,
                                                 gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    a = _linea(org_a, plan_a, 9170, gestor_a[1], secuencia=1,
               zona="Norte", prioridad=10)
    AsignacionTrabajo.objects.create(orden=a.orden, profile=gestor_a[1],
                                     rol="tecnico", es_principal=True)

    antes = _desde_fuera(
        "select programada_para, estado_operativo, estado_validacion, revision "
        "from campo_orden_trabajo where id = %s", [str(a.orden_id)])[0]
    asig_antes = _desde_fuera(
        "select profile_id, rol, es_principal from campo_asignacion_trabajo "
        "where orden_id = %s", [str(a.orden_id)])

    assert cliente_a.post(SECUENCIAR, _cuerpo(plan_a, [_item(a, 9)]),
                          format="json").status_code == 200

    despues = _desde_fuera(
        "select programada_para, estado_operativo, estado_validacion, revision "
        "from campo_orden_trabajo where id = %s", [str(a.orden_id)])[0]
    asig_despues = _desde_fuera(
        "select profile_id, rol, es_principal from campo_asignacion_trabajo "
        "where orden_id = %s", [str(a.orden_id)])
    linea = _desde_fuera(
        "select secuencia, zona, prioridad, dia from "
        "operaciones_programacion_orden where id = %s", [str(a.id)])[0]

    assert antes == despues
    assert asig_antes == asig_despues
    assert linea["secuencia"] == 9              # lo único que cambió
    assert (linea["zona"], linea["prioridad"]) == ("Norte", 10)


# ===========================================================================
#  §11  --  multi-tenant, verificado en los datos
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_11_el_tenant_ajeno_no_toca_nada(cliente_a, org_a, org_b, plan_a,
                                         gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")
    mia = _linea(org_a, plan_a, 9180, gestor_a[1], secuencia=1)
    plan_b = _plan(org_b)
    ub, pb = _gestor(org_b, "jefe.b@e5c.test")
    suya = _linea(org_b, plan_b, 9181, pb, secuencia=1)

    #  A intenta secuenciar el plan de B.
    r = cliente_a.post(SECUENCIAR, _cuerpo(plan_b, [_item(suya, 9)]),
                       format="json")
    assert r.status_code == 404

    #  A intenta colar la línea de B en SU propia jornada.
    r2 = cliente_a.post(SECUENCIAR,
                        _cuerpo(plan_a, [_item(mia, 3), _item(suya, 4)]),
                        format="json")
    assert r2.status_code == 400

    #  Los datos, desde fuera del ORM: nada se movió en ninguna de las dos.
    filas = {str(x["id"]): x["secuencia"] for x in _desde_fuera(
        "select id, secuencia from operaciones_programacion_orden")}
    assert filas[str(mia.id)] == 1
    assert filas[str(suya.id)] == 1
    assert _desde_fuera(
        "select count(*) n from campo_evento_trabajo "
        "where tipo like 'secuencia%%'")[0]["n"] == 0

    #  Y B sí puede con lo suyo.
    assert _cli(ub, org_b, pb).post(
        _cuerpo(plan_b, [])["plan"] and SECUENCIAR,
        _cuerpo(plan_b, [_item(suya, 9)]), format="json").status_code == 200


# ===========================================================================
#  §12  --  permisos: nada se amplió
# ===========================================================================
@pytest.mark.django_db
def test_12_no_se_crearon_ni_ampliaron_roles():
    from campo.permissions import ROLES_GESTION
    from common.utils import ROLES
    from operaciones.permissions import EsJefeDeOperaciones

    assert ROLES_GESTION == {"ADMIN", "SUPERVISOR", "OPERACIONES"}
    #  El catálogo de roles del sistema no creció: cuatro, los de siempre.
    assert {r for r, _ in ROLES} == {"ADMIN", "SUPERVISOR", "OPERACIONES",
                                     "USER"}
    #  Y las dos vistas de secuenciación usan el permiso existente.
    from operaciones.views import JornadaView, SecuenciaLineaView, \
        SecuenciarJornadaView
    for vista in (JornadaView, SecuenciaLineaView, SecuenciarJornadaView):
        assert vista.permission_classes == [EsJefeDeOperaciones]


# ===========================================================================
#  §17  --  deriva de arquitectura
# ===========================================================================
@pytest.mark.django_db
def test_17_e5_no_trajo_ningun_sistema_paralelo():
    """
    Afirma sobre el CÓDIGO, no sobre la intención: se lee el fuente del módulo
    y se comprueba que no aparecieron mecanismos nuevos donde ya había uno.
    """
    import inspect
    from operaciones import programacion, views

    fuente = inspect.getsource(programacion) + inspect.getsource(views)

    #  Ninguna llamada directa a un sistema externo.
    for externo in ("wisphub", "smartolt", "whatsapp", "requests.",
                    "httpx.", "urllib.request"):
        assert externo not in fuente.lower(), externo

    #  Un solo mecanismo de idempotencia, y es el que ya existía.
    assert "manejar_idempotencia" in fuente
    assert "MutacionIdempotente" not in fuente   # no se reimplementa

    #  Ninguna cola ni planificador nuevo.
    for tarea in ("celery", "shared_task", "apply_async", "schedule("):
        assert tarea not in fuente.lower(), tarea

    #  La auditoría de M03 sigue siendo EventoTrabajo + NovedadOperativa.
    #
    #  La comprobación de "no hay auditoría paralela" se lee sobre
    #  'programacion' y no sobre 'views': views.py aloja las vistas de VARIOS
    #  módulos, y desde M02 también las de ActividadOperativa, que audita en
    #  common.Activity -- la superficie que 'operaciones/auditoria.py' declara
    #  para este módulo y que PropuestaSupervisor ya usaba. Eso no es un
    #  sistema paralelo: es el que ya existía. Lo que este guarda vigila --que
    #  M03-E5 no inventara otro-- se sigue midiendo igual de fuerte sobre el
    #  módulo donde vive su código.
    fuente_m03 = inspect.getsource(programacion)
    assert "EventoTrabajo" in fuente_m03
    assert "Activity" not in fuente_m03

    #  Ninguna entidad nueva para secuencias.
    from django.apps import apps
    modelos = {m.__name__ for m in apps.get_app_config("operaciones").get_models()}
    assert modelos == {"ActividadOperativa", "DisponibilidadTecnico",
                       "ProgramacionSemanal", "ProgramacionOrden",
                       "NovedadOperativa", "PropuestaSupervisor"}, modelos


@pytest.mark.django_db
def test_17b_el_modulo_no_toca_m09_ni_revisar_coherencia(cliente_a, org_a,
                                                         plan_a, gestor_a):
    from operaciones.models import PropuestaSupervisor
    a = _linea(org_a, plan_a, 9190, gestor_a[1])
    cliente_a.post(SECUENCIAR, _cuerpo(plan_a, [_item(a, 2)]), format="json")
    assert PropuestaSupervisor.objects.count() == 0


# ===========================================================================
#  §18  --  G-3: la deuda de contrato, medida
# ===========================================================================
@pytest.mark.django_db
def test_18_g3_sin_secuencia_leida_la_linea_pierde_su_proteccion(
        cliente_a, org_a, plan_a, gestor_a):
    """
    [DECISIÓN PENDIENTE — G-3] NO se corrige aquí: se MIDE.

    'secuencia_leida' es opcional. Cuando el cliente no la envía, esa línea NO
    participa de la comprobación de concurrencia: vuelve a la conducta "el
    último gana". Esta prueba fija el hecho para que la deuda sea visible y no
    se descubra en producción.
    """
    a = _linea(org_a, plan_a, 9200, gestor_a[1], secuencia=1)

    #  Alguien cambia la línea por la vía individual.
    assert cliente_a.post(_url_linea(a), {"secuencia": 7},
                          format="json").status_code == 200

    #  Un cliente que NO manda 'secuencia_leida' aplica igual, sin conflicto.
    r = cliente_a.post(SECUENCIAR, {
        "plan": str(plan_a.id), "dia": str(MIER.date()),
        "lineas": [{"linea": str(a.id), "secuencia": 3}]}, format="json")
    assert r.status_code == 200
    assert r.json()["resultado"] == "aplicado"

    a.refresh_from_db()
    assert a.secuencia == 3        # <- el cambio a 7 se perdió, sin aviso

    #  Y con 'secuencia_leida' desfasada, el mismo caso SÍ da conflicto.
    b = _linea(org_a, plan_a, 9201, gestor_a[1], secuencia=1)
    cliente_a.post(_url_linea(b), {"secuencia": 7}, format="json")
    r2 = cliente_a.post(SECUENCIAR,
                        _cuerpo(plan_a, [_item(a, 3, leida=3),
                                         _item(b, 4, leida=1)]),
                        format="json")
    assert r2.status_code == 409
    assert r2.json()["error"] == "JORNADA_CAMBIO"
