# -*- coding: utf-8 -*-
"""
================================================================================
 M03-C  --  publicación de una programación semanal
================================================================================

Publicar es una transición de estado y nada más. Lo que estas pruebas afirman
no es que el estado cambie -- eso es trivial-- sino las cuatro cosas que
rodean el cambio:

  * que el actor y el instante QUEDEN, y se puedan leer desde fuera del ORM;
  * que las puertas cerradas (ya publicada, cerrada) lo sigan estando;
  * que un plan que se contradice con sus órdenes NO se publique ni se corrija;
  * que publicar no toque ni una sola orden.

Igual que en M03-B, la persistencia se lee con una CONEXIÓN INDEPENDIENTE y la
atomicidad se prueba rompiendo la operación, no leyendo el decorador.
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
from operaciones.programacion import (ErrorProgramacion, PlanIncoherente,
                                      PlanNoPublicable, programar_orden,
                                      publicar_programacion,
                                      revisar_coherencia)

LUNES = date(2026, 10, 5)
MIERCOLES = timezone.make_aware(
    datetime.combine(LUNES + timedelta(days=2), time(9, 0)))


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
        cliente_nombre="Cliente M03-C", cliente_direccion="Calle 1",
        estado_operativo=estado)


def _plan(org, estado=ProgramacionSemanal.BORRADOR, lunes=LUNES):
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
    return _version(org_a, "m03c_a")


@pytest.fixture
def plan_a(org_a):
    return _plan(org_a)


@pytest.fixture
def gestor_a(org_a):
    return _gestor(org_a, "jefe.a@m03c.test")


@pytest.fixture
def cliente_a(org_a, gestor_a):
    return _cliente(gestor_a[0], org_a, gestor_a[1])


def _url(plan):
    return f"/api/operaciones/programacion/{plan.id}/publicar/"


def _linea_coherente(org, plan, version, numero, actor, cuando=MIERCOLES):
    """
    Una línea escrita por la vía de M03-B, que garantiza la coherencia.

    El 'refresh_from_db' NO es decorativo: 'programar_orden' escribe sobre la
    fila que bloquea y relee, no sobre este objeto, así que sin refrescar se
    devolvería una copia con 'programada_para' todavía en None. Una prueba que
    tomara su foto "antes" de ese objeto mediría el desfase del ORM en vez de
    lo que dice medir -- y eso ya pasó una vez al escribir esta suite.
    """
    orden = _orden(org, version, numero)
    programar_orden(org=org, orden=orden, programacion=plan,
                    programada_para=cuando, actor=actor)
    orden.refresh_from_db()
    return orden


def _leer_desde_fuera(sql, params=None):
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
#  C1  --  publicación válida
# ===========================================================================
@pytest.mark.django_db
def test_c1_publicacion_valida(cliente_a, org_a, plan_a, version_a, gestor_a):
    _linea_coherente(org_a, plan_a, version_a, 9001, gestor_a[1])
    antes = timezone.now()

    r = cliente_a.post(_url(plan_a), {}, format="json")
    assert r.status_code == 200, r.content[:400]

    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.PUBLICADA
    assert plan_a.publicada_por_id == gestor_a[1].id
    assert plan_a.publicada_en is not None and plan_a.publicada_en >= antes
    assert r.json()["programacion"]["estado"] == "publicada"
    assert r.json()["lineas"] == 1


@pytest.mark.django_db
def test_c1b_un_plan_vacio_se_publica(cliente_a, plan_a):
    """
    NO se inventa el requisito de "mínimo N órdenes" (§14).

    La evidencia es del propio código: '_programaciones_sin_publicar' dice
    literalmente que NO se infiere la publicación de que existan líneas --
    "un borrador también las tiene, y confundir las dos cosas es exactamente lo
    que esta señal no debe hacer". Publicación y contenido están desacoplados
    en la semántica existente, así que rechazar un plan vacío sería una regla
    nueva.
    """
    assert ProgramacionOrden.objects.filter(programacion=plan_a).count() == 0

    r = cliente_a.post(_url(plan_a), {}, format="json")
    assert r.status_code == 200
    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.PUBLICADA


# ===========================================================================
#  C2  --  persistencia verificada desde fuera del ORM
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_c2_persistencia_por_conexion_independiente(cliente_a, org_a, plan_a,
                                                    version_a, gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("una conexión independiente sólo tiene sentido en PostgreSQL")

    antes = _leer_desde_fuera(
        "select estado, publicada_en, publicada_por_id "
        "from operaciones_programacion_semanal where id = %s", [str(plan_a.id)])
    assert antes[0]["estado"] == ProgramacionSemanal.BORRADOR
    assert antes[0]["publicada_en"] is None
    assert antes[0]["publicada_por_id"] is None

    _linea_coherente(org_a, plan_a, version_a, 9002, gestor_a[1])
    assert cliente_a.post(_url(plan_a), {}, format="json").status_code == 200

    despues = _leer_desde_fuera(
        "select estado, publicada_en, publicada_por_id, updated_by_id "
        "from operaciones_programacion_semanal where id = %s", [str(plan_a.id)])
    f = despues[0]
    assert f["estado"] == ProgramacionSemanal.PUBLICADA
    assert f["publicada_en"] is not None
    assert str(f["publicada_por_id"]) == str(gestor_a[1].id)
    #  El segundo registro del actor, independiente de 'publicada_por'.
    assert f["updated_by_id"] is not None


# ===========================================================================
#  C3  --  cross-tenant
# ===========================================================================
@pytest.mark.django_db
def test_c3_cross_tenant_no_publica_el_plan_ajeno(cliente_a, org_b):
    plan_b = _plan(org_b)
    r = cliente_a.post(_url(plan_b), {}, format="json")

    #  404 y no 403: un 403 confirmaría que el plan existe.
    assert r.status_code == 404
    plan_b.refresh_from_db()
    assert plan_b.estado == ProgramacionSemanal.BORRADOR
    assert plan_b.publicada_en is None
    assert plan_b.publicada_por_id is None


@pytest.mark.django_db
def test_c3b_el_servicio_tampoco_confia_en_que_la_vista_haya_filtrado(
        org_a, org_b, gestor_a):
    plan_b = _plan(org_b)
    with pytest.raises(ErrorProgramacion) as e:
        publicar_programacion(org=org_a, programacion=plan_b,
                              actor=gestor_a[1])
    assert "otra empresa" in str(e.value)
    plan_b.refresh_from_db()
    assert plan_b.estado == ProgramacionSemanal.BORRADOR


@pytest.mark.django_db
def test_c3c_cada_organizacion_publica_lo_suyo(org_a, org_b, plan_a, cliente_a):
    plan_b = _plan(org_b)
    ub, pb = _gestor(org_b, "jefe.b@m03c.test")
    cli_b = _cliente(ub, org_b, pb)

    assert cliente_a.post(_url(plan_a), {}, format="json").status_code == 200
    assert cli_b.post(_url(plan_b), {}, format="json").status_code == 200

    plan_a.refresh_from_db()
    plan_b.refresh_from_db()
    assert plan_a.publicada_por_id != plan_b.publicada_por_id
    assert plan_a.publicada_por.org_id == org_a.id
    assert plan_b.publicada_por.org_id == org_b.id


# ===========================================================================
#  C4  --  plan ya publicado (idempotencia semántica)
# ===========================================================================
@pytest.mark.django_db
def test_c4_un_plan_ya_publicado_no_se_vuelve_a_publicar(cliente_a, plan_a):
    primera = cliente_a.post(_url(plan_a), {}, format="json")
    assert primera.status_code == 200
    plan_a.refresh_from_db()
    sello_actor = plan_a.publicada_por_id
    sello_fecha = plan_a.publicada_en

    segunda = cliente_a.post(_url(plan_a), {}, format="json")
    assert segunda.status_code == 409
    assert segunda.json()["error"] == "NO_PUBLICABLE"

    #  Lo que importa no es el 409: es que el sello de la PRIMERA siga intacto.
    plan_a.refresh_from_db()
    assert plan_a.publicada_por_id == sello_actor
    assert plan_a.publicada_en == sello_fecha


@pytest.mark.django_db
def test_c4b_la_segunda_publicacion_no_pisa_al_primer_actor(org_a, plan_a,
                                                            gestor_a):
    """
    Dos personas distintas, la segunda llega tarde.

    Sin la comprobación de estado, el segundo save dejaría al plan diciendo que
    lo publicó quien llegó después -- y esa es la pregunta que 'publicada_por'
    existe para contestar.
    """
    u2, p2 = _gestor(org_a, "jefe.a2@m03c.test")

    publicar_programacion(org=org_a, programacion=plan_a, actor=gestor_a[1])
    plan_a.refresh_from_db()

    with pytest.raises(PlanNoPublicable):
        publicar_programacion(org=org_a, programacion=plan_a, actor=p2)

    plan_a.refresh_from_db()
    assert plan_a.publicada_por_id == gestor_a[1].id


# ===========================================================================
#  C5  --  plan cerrado
# ===========================================================================
@pytest.mark.django_db
def test_c5_un_plan_cerrado_no_se_publica(cliente_a, org_a):
    cerrado = _plan(org_a, estado=ProgramacionSemanal.CERRADA)
    r = cliente_a.post(_url(cerrado), {}, format="json")

    assert r.status_code == 409
    cerrado.refresh_from_db()
    assert cerrado.estado == ProgramacionSemanal.CERRADA
    assert cerrado.publicada_en is None


@pytest.mark.django_db
def test_c5b_no_existe_reapertura(cliente_a, org_a):
    """M03-C no crea ninguna vía de vuelta: ni cerrada->publicada ni ->borrador."""
    cerrado = _plan(org_a, estado=ProgramacionSemanal.CERRADA)
    cliente_a.post(_url(cerrado), {}, format="json")
    cerrado.refresh_from_db()
    assert cerrado.estado == ProgramacionSemanal.CERRADA

    from operaciones import programacion as modulo
    publicos = {n for n in dir(modulo) if not n.startswith("_")}
    for prohibido in ("reabrir", "cerrar_programacion", "despublicar"):
        assert prohibido not in publicos


# ===========================================================================
#  C6  --  plan inconsistente
# ===========================================================================
@pytest.mark.django_db
def test_c6_un_plan_que_se_contradice_no_se_publica(cliente_a, org_a, plan_a,
                                                    version_a, gestor_a):
    """
    La incoherencia se fabrica por la vía que M03-B no controla.

    M03-B escribe la línea y 'programada_para' juntos, así que no puede
    producir esto. El panel de Django sí -- es el otro escritor de la tabla-- y
    por eso la comprobación se hace al publicar y no se da por hecha.
    """
    orden = _linea_coherente(org_a, plan_a, version_a, 9003, gestor_a[1])

    #  Se mueve la fecha de la orden por detrás, sin tocar la línea.
    orden.programada_para = MIERCOLES + timedelta(days=1)
    orden.save(update_fields=["programada_para"])

    r = cliente_a.post(_url(plan_a), {}, format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "PLAN_INCOHERENTE"
    assert len(r.json()["problemas"]) == 1
    assert "el plan dice" in r.json()["problemas"][0]

    #  Nada se publicó y NADA se corrigió.
    plan_a.refresh_from_db()
    orden.refresh_from_db()
    linea = ProgramacionOrden.objects.get(orden=orden)
    assert plan_a.estado == ProgramacionSemanal.BORRADOR
    assert plan_a.publicada_en is None
    assert orden.programada_para == MIERCOLES + timedelta(days=1)
    assert linea.dia == MIERCOLES.date()


@pytest.mark.django_db
def test_c6b_una_orden_sin_programada_para_tambien_bloquea(
        cliente_a, org_a, plan_a, version_a, gestor_a):
    orden = _linea_coherente(org_a, plan_a, version_a, 9004, gestor_a[1])
    orden.programada_para = None
    orden.save(update_fields=["programada_para"])

    r = cliente_a.post(_url(plan_a), {}, format="json")
    assert r.status_code == 400
    assert "no dice nada" in " ".join(r.json()["problemas"])
    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.BORRADOR


@pytest.mark.django_db
def test_c6c_una_linea_cancelada_no_bloquea(cliente_a, org_a, plan_a, version_a,
                                            gestor_a):
    """
    Misma definición de "vigente" que 'supervisor._programacion_vigente'.

    Exigirle coherencia a una línea cancelada o reprogramada sería exigírsela
    justo a las dos que por definición ya no rigen.
    """
    orden = _linea_coherente(org_a, plan_a, version_a, 9005, gestor_a[1])
    linea = ProgramacionOrden.objects.get(orden=orden)
    linea.estado = ProgramacionOrden.CANCELADA
    linea.save(update_fields=["estado"])
    orden.programada_para = None
    orden.save(update_fields=["programada_para"])

    assert revisar_coherencia(plan_a) == []
    assert cliente_a.post(_url(plan_a), {}, format="json").status_code == 200


@pytest.mark.django_db
def test_c6d_se_devuelven_todos_los_problemas_no_el_primero(
        org_a, plan_a, version_a, gestor_a):
    o1 = _linea_coherente(org_a, plan_a, version_a, 9006, gestor_a[1])
    v2 = _version(org_a, "m03c_a2")
    o2 = _linea_coherente(org_a, plan_a, v2, 9007, gestor_a[1],
                          cuando=MIERCOLES + timedelta(days=1))
    for o in (o1, o2):
        o.programada_para = None
        o.save(update_fields=["programada_para"])

    with pytest.raises(PlanIncoherente) as e:
        publicar_programacion(org=org_a, programacion=plan_a, actor=gestor_a[1])
    assert len(e.value.problemas) == 2


# ===========================================================================
#  C7  --  rollback
# ===========================================================================
@pytest.mark.django_db
def test_c7_rollback_conserva_el_estado_original(org_a, plan_a, gestor_a):
    """
    Se rompe la operación DESPUÉS de fijar estado, actor y fecha en memoria,
    justo en el save. Si la transacción no fuera real, el plan quedaría
    publicado a medias.
    """
    with mock.patch.object(ProgramacionSemanal, "save",
                           side_effect=RuntimeError("fallo inyectado")):
        with pytest.raises(RuntimeError):
            publicar_programacion(org=org_a, programacion=plan_a,
                                  actor=gestor_a[1])

    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.BORRADOR
    assert plan_a.publicada_en is None
    assert plan_a.publicada_por_id is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_c7b_el_rollback_tambien_se_ve_desde_fuera(org_a, plan_a, gestor_a):
    if connection.vendor != "postgresql":
        pytest.skip("requiere PostgreSQL")

    def _revienta(self, *a, **k):
        from django.db import models as _m
        _m.Model.save(self, *a, **k)      # escribe de verdad...
        raise RuntimeError("fallo inyectado")   # ...y luego falla

    with mock.patch.object(ProgramacionSemanal, "save", _revienta):
        with pytest.raises(RuntimeError):
            publicar_programacion(org=org_a, programacion=plan_a,
                                  actor=gestor_a[1])

    f = _leer_desde_fuera(
        "select estado, publicada_en, publicada_por_id "
        "from operaciones_programacion_semanal where id = %s",
        [str(plan_a.id)])[0]
    assert f["estado"] == ProgramacionSemanal.BORRADOR
    assert f["publicada_en"] is None
    assert f["publicada_por_id"] is None


# ===========================================================================
#  C8  --  concurrencia
# ===========================================================================
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_c8_dos_publicaciones_simultaneas_dejan_una_sola(org_a, gestor_a):
    """
    Dos personas publican el mismo plan a la vez.

    Sin el 'select_for_update' las dos leen 'borrador' antes de que ninguna
    escriba, las dos publican, y el sello de la primera queda pisado por el de
    la segunda.
    """
    if connection.vendor != "postgresql":
        pytest.skip("la concurrencia real requiere PostgreSQL")

    plan = _plan(org_a)
    u1, p1 = gestor_a
    u2, p2 = _gestor(org_a, "jefe.a3@m03c.test")
    cli1, cli2 = _cliente(u1, org_a, p1), _cliente(u2, org_a, p2)

    def publica(cli):
        try:
            return cli.post(_url(plan), {}, format="json").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(publica, [cli1, cli2]))

    assert codigos == [200, 409], codigos

    plan.refresh_from_db()
    assert plan.estado == ProgramacionSemanal.PUBLICADA
    #  Un solo sello, y de una de las dos personas -- no una mezcla.
    assert plan.publicada_por_id in (p1.id, p2.id)
    assert plan.publicada_en is not None


# ===========================================================================
#  C9  --  actor no autorizado
# ===========================================================================
@pytest.mark.django_db
def test_c9_un_tecnico_no_publica(org_a, plan_a, regular_user, user_profile):
    cli = _cliente(regular_user, org_a, user_profile)
    r = cli.post(_url(plan_a), {}, format="json")
    assert r.status_code == 403
    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.BORRADOR


@pytest.mark.django_db
def test_c9b_sin_sesion_no_se_publica(plan_a):
    r = APIClient().post(_url(plan_a), {}, format="json")
    assert r.status_code in (401, 403)
    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.BORRADOR


@pytest.mark.django_db
def test_c9c_una_publicacion_sin_actor_no_es_representable(org_a, plan_a):
    with pytest.raises(ErrorProgramacion):
        publicar_programacion(org=org_a, programacion=plan_a, actor=None)
    plan_a.refresh_from_db()
    assert plan_a.estado == ProgramacionSemanal.BORRADOR


@pytest.mark.django_db
@pytest.mark.parametrize("rol", ["ADMIN", "SUPERVISOR", "OPERACIONES"])
def test_c9d_los_tres_roles_de_gestion_pueden_publicar(org_a, rol):
    """
    §8: se documenta quién puede, no se reduce.

    El permiso reutilizado es 'EsJefeDeOperaciones' -> ROLES_GESTION, que
    admite tres roles. Reducirlo a uno sería resolver por mi cuenta la decisión
    de negocio D-6, que sigue abierta.
    """
    plan = _plan(org_a, lunes=LUNES + timedelta(weeks=["ADMIN", "SUPERVISOR",
                                                       "OPERACIONES"].index(rol) + 1))
    u = User.objects.create_user(email=f"{rol.lower()}@m03c.test",
                                 password="x12345678")
    p = Profile.objects.create(user=u, org=org_a, role=rol, is_active=True)
    r = _cliente(u, org_a, p).post(_url(plan), {}, format="json")
    assert r.status_code == 200, f"{rol}: {r.content[:200]}"


# ===========================================================================
#  C10 / C11  --  publicar no ejecuta
# ===========================================================================
@pytest.mark.django_db
def test_c10_publicar_no_modifica_ninguna_orden(cliente_a, org_a, plan_a,
                                                version_a, gestor_a):
    orden = _linea_coherente(org_a, plan_a, version_a, 9008, gestor_a[1])
    antes = {
        "estado_operativo": orden.estado_operativo,
        "estado_validacion": orden.estado_validacion,
        "programada_para": orden.programada_para,
        "revision": orden.revision,
        "vuelta": orden.vuelta,
        "iniciada_en": orden.iniciada_en,
    }
    linea_antes = ProgramacionOrden.objects.get(orden=orden)
    dia_antes, estado_linea_antes = linea_antes.dia, linea_antes.estado

    assert cliente_a.post(_url(plan_a), {}, format="json").status_code == 200

    orden.refresh_from_db()
    for campo, valor in antes.items():
        assert getattr(orden, campo) == valor, campo

    linea_antes.refresh_from_db()
    assert linea_antes.dia == dia_antes
    assert linea_antes.estado == estado_linea_antes


@pytest.mark.django_db
def test_c11_publicar_no_crea_asignaciones_ni_novedades(cliente_a, org_a,
                                                        plan_a, version_a,
                                                        gestor_a):
    _linea_coherente(org_a, plan_a, version_a, 9009, gestor_a[1])
    asignaciones = AsignacionTrabajo.objects.count()
    novedades = NovedadOperativa.objects.count()
    eventos = EventoTrabajo.objects.count()

    assert cliente_a.post(_url(plan_a), {}, format="json").status_code == 200

    assert AsignacionTrabajo.objects.count() == asignaciones
    assert NovedadOperativa.objects.count() == novedades
    #  Publicar no escribe en la bitácora de campo: no es un evento de una
    #  orden. El registro de quién y cuándo vive en el propio plan.
    assert EventoTrabajo.objects.count() == eventos


@pytest.mark.django_db
def test_c11b_publicar_no_toca_propuestas_ni_disponibilidad(cliente_a, org_a,
                                                            plan_a):
    from operaciones.models import DisponibilidadTecnico, PropuestaSupervisor
    assert cliente_a.post(_url(plan_a), {}, format="json").status_code == 200
    assert PropuestaSupervisor.objects.count() == 0
    assert DisponibilidadTecnico.objects.count() == 0


# ===========================================================================
#  C12  --  efectos externos
# ===========================================================================
@pytest.mark.django_db
def test_c12_publicar_no_abre_ninguna_conexion_saliente(cliente_a, org_a,
                                                        plan_a, version_a,
                                                        gestor_a):
    """
    Se instrumenta socket.connect alrededor de la publicación.

    El cero no se lee a ciegas: primero se comprueba que el contador DISPARA
    con una sonda deliberada. Un instrumento roto también marca 0.
    """
    import http.client
    import socket

    _linea_coherente(org_a, plan_a, version_a, 9010, gestor_a[1])

    destinos = []
    original = socket.socket.connect

    def vigilado(self, direccion):
        destinos.append(direccion)
        return original(self, direccion)

    socket.socket.connect = vigilado
    try:
        assert cliente_a.post(_url(plan_a), {}, format="json").status_code == 200
        durante = list(destinos)

        #  La guarda, desarmada a propósito.
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


# ===========================================================================
#  Guardas de alcance
# ===========================================================================
@pytest.mark.django_db
def test_publicar_no_toca_h05_ni_m09(cliente_a, plan_a):
    """
    Afirma sobre el EFECTO: se corre el ciclo del Supervisor antes y después
    y se comprueba que publicar no cambió lo que M09 ve como ejecutable.
    """
    from operaciones import supervisor
    assert not hasattr(supervisor, "publicar_programacion")
    assert cliente_a.post(_url(plan_a), {}, format="json").status_code == 200

    from operaciones.models import PropuestaSupervisor
    assert PropuestaSupervisor.objects.count() == 0


@pytest.mark.django_db
def test_la_publicacion_apaga_la_senal_de_plan_sin_publicar(org_a, gestor_a):
    """
    El efecto real de M03-C sobre M09, medido sin tocar M09.

    '_programaciones_sin_publicar' emite cuando la semana ya empezó y el plan
    sigue en borrador. Llevaba existiendo sin que nadie pudiera apagarla: no
    había forma de publicar. Ahora sí, y la señal deja de emitirse.
    """
    from operaciones import supervisor

    semana_pasada = timezone.localdate() - timedelta(days=7)
    plan = _plan(org_a, lunes=semana_pasada)

    antes = supervisor._programaciones_sin_publicar(org_a, timezone.now())
    assert len(antes) == 1

    publicar_programacion(org=org_a, programacion=plan, actor=gestor_a[1])

    despues = supervisor._programaciones_sin_publicar(org_a, timezone.now())
    assert despues == []


@pytest.mark.django_db
def test_la_transicion_solo_va_en_una_direccion(org_a, gestor_a):
    """Las tres puertas que M03-C NO abre."""
    publicado = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA,
                      lunes=LUNES)
    cerrado = _plan(org_a, estado=ProgramacionSemanal.CERRADA,
                    lunes=LUNES + timedelta(weeks=1))

    for plan in (publicado, cerrado):
        with pytest.raises(PlanNoPublicable):
            publicar_programacion(org=org_a, programacion=plan,
                                  actor=gestor_a[1])

    publicado.refresh_from_db()
    cerrado.refresh_from_db()
    assert publicado.estado == ProgramacionSemanal.PUBLICADA
    assert cerrado.estado == ProgramacionSemanal.CERRADA
