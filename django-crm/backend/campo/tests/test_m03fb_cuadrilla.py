# -*- coding: utf-8 -*-
"""
================================================================================
 M03-F-B  --  cuadrilla ad-hoc por OT
================================================================================

Lo que estas pruebas afirman NO es que exista un mecanismo, sino que produce el
efecto. Donde hace falta, la guarda se DESARMA para comprobar que la prueba
sabe fallar: una prueba que pasa con y sin la proteccion no prueba nada.

Dos son obligatorias por encargo y estan marcadas como tales:

  * CRITICA DE ATOMICIDAD (§19): se fuerza una excepcion despues de mover las
    dos asignaciones y antes del commit, y el estado se lee con una CONEXION
    INDEPENDIENTE del ORM -- no con el mismo cursor que podria estar viendo su
    propia transaccion.

  * FALLA SILENCIOSA (§20): el estado que M03-F-A.3 midio como legal e
    invisible --principal retirado y sucesor que se quedo de auxiliar-- no debe
    poder existir por ningun camino.
================================================================================
"""

from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta
from unittest import mock

import psycopg
import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from psycopg.rows import dict_row
from rest_framework.test import APIClient

import campo.services.despacho as _despacho
from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.serializers import OrdenTrabajoDetailSerializer
from campo.services.despacho import (ConflictoDeCuadrilla, ErrorDespacho,
                                     RequiereSucesor, agregar_integrante,
                                     asignar, cambiar_principal, desasignar,
                                     retirar_integrante)
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones.models import (DisponibilidadTecnico, ProgramacionOrden,
                                ProgramacionSemanal)
from operaciones.programacion import programar_orden

LUNES = date(2026, 10, 5)


# ------------------------------------------------------------------ utilidades
def _dt(dias=0, hora=9):
    return timezone.make_aware(
        datetime.combine(LUNES + timedelta(days=dias), time(hora, 0)))


def _version(org, codigo):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})


_n = [6000]


def _orden(org, estado=OrdenTrabajo.ASIGNADA):
    _n[0] += 1
    return OrdenTrabajo.objects.create(
        org=org, numero=_n[0],
        tipo_trabajo_version=_version(org, f"fb_{_n[0]}"),
        cliente_nombre=f"Cliente {_n[0]}", cliente_direccion="Calle 1",
        estado_operativo=estado)


_c = [0]


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"fb{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


def _cli(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


def _invariante(orden):
    """F-2: 0 integrantes valido; con >=1 hay EXACTAMENTE un principal."""
    n = orden.asignaciones.count()
    p = orden.asignaciones.filter(es_principal=True).count()
    return (p == 0 if n == 0 else p == 1), n, p


def _independiente():
    """
    Conexion propia, fuera del ORM. Leer con el mismo cursor que ejecuto la
    transaccion puede mostrar lo que esa transaccion ve, no lo que quedo.
    """
    d = connection.settings_dict
    return psycopg.connect(
        host=d["HOST"] or "localhost", port=d["PORT"] or 5432,
        user=d["USER"], password=d["PASSWORD"], dbname=d["NAME"],
        row_factory=dict_row)


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


# ============================================================ 1-3. los estados
@pytest.mark.django_db
def test_1_ot_sin_integrantes_es_valida(org_a):
    """0 asignaciones es un estado legitimo, no un accidente."""
    o = _orden(org_a)
    ok, n, p = _invariante(o)
    assert (n, p) == (0, 0) and ok
    assert o.tecnico_principal is None
    assert OrdenTrabajoDetailSerializer(o).data["cuadrilla"] == []


@pytest.mark.django_db
def test_2_primera_asignacion(org_a, actor):
    o = _orden(org_a)
    _, p1 = _persona(org_a)
    asignar(o, p1, actor, rol="tecnico")
    assert o.asignaciones.count() == 1


@pytest.mark.django_db
def test_3_la_primera_asignacion_queda_principal(org_a, actor):
    """
    Contrato F-2. No es preferencia: M03-F-A.2 midio que con es_principal=False
    la OT tiene tecnico y H-05 no emite ninguna senal aunque este ausente.
    """
    o = _orden(org_a)
    _, p1 = _persona(org_a)
    a = asignar(o, p1, actor)
    assert a.es_principal is True
    o.refresh_from_db()
    assert o.tecnico_principal == p1
    #  y no hay forma de dejar una individual sin principal por el servicio
    o2 = _orden(org_a)
    with pytest.raises(ErrorDespacho, match="no tiene a nadie asignado"):
        agregar_integrante(o2, p1, actor)


# ================================================== 4-6. agregar sin desplazar
@pytest.mark.django_db
def test_4_segunda_asignacion(org_a, actor):
    o = _orden(org_a)
    _, p1 = _persona(org_a)
    _, p2 = _persona(org_a)
    asignar(o, p1, actor, rol="tecnico_lider")
    agregar_integrante(o, p2, actor, rol="ayudante")
    assert o.asignaciones.count() == 2
    ok, n, p = _invariante(o)
    assert ok and (n, p) == (2, 1)


@pytest.mark.django_db
def test_5_tercera_asignacion(org_a, actor):
    o = _orden(org_a)
    _, p1 = _persona(org_a)
    _, p2 = _persona(org_a)
    _, p3 = _persona(org_a)
    asignar(o, p1, actor, rol="tecnico_lider")
    agregar_integrante(o, p2, actor, rol="ayudante")
    agregar_integrante(o, p3, actor, rol="chofer")
    ok, n, p = _invariante(o)
    assert ok and (n, p) == (3, 1)
    assert o.tecnico_principal == p1


@pytest.mark.django_db
def test_6_agregar_no_cambia_el_principal(org_a, actor):
    """
    El hallazgo de M03-F-A.1: la unica via que existia hacia lo contrario --
    agregar un ayudante le robaba la principalia al lider. Se comprueba el
    efecto, y ademas que la via vieja SIGUE haciendolo (no se rompio nada, se
    separo en dos actos).
    """
    o = _orden(org_a)
    _, p1 = _persona(org_a)
    _, p2 = _persona(org_a)
    asignar(o, p1, actor, rol="tecnico_lider")
    agregar_integrante(o, p2, actor, rol="ayudante")
    o.refresh_from_db()
    assert o.tecnico_principal == p1, "agregar movio al principal"
    assert o.asignaciones.get(profile=p2).es_principal is False

    #  'asignar' conserva su significado: pone o CAMBIA al responsable
    o2 = _orden(org_a)
    asignar(o2, p1, actor, rol="tecnico_lider")
    asignar(o2, p2, actor, rol="ayudante")
    o2.refresh_from_db()
    assert o2.tecnico_principal == p2


# ================================================== 7. cambiar principal
@pytest.mark.django_db
def test_7_cambiar_principal(org_a, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    agregar_integrante(o, pb, actor, rol="ayudante")

    _, cambio = cambiar_principal(o, pb, actor, motivo="rota el turno")
    o.refresh_from_db()
    assert cambio is True
    assert o.tecnico_principal == pb
    assert o.asignaciones.get(profile=pa).es_principal is False
    assert o.asignaciones.count() == 2, "cambiar principal retiro a alguien"
    #  F-3: 'rol' es descriptivo y NO se toca al cambiar el principal
    assert o.asignaciones.get(profile=pb).rol == "ayudante"
    assert o.asignaciones.get(profile=pa).rol == "tecnico_lider"


@pytest.mark.django_db
def test_7b_cambiar_al_que_ya_es_principal_es_no_op(org_a, actor):
    """Mismo contrato que M03-B1: un no-op no escribe, no audita, no es 409."""
    o = _orden(org_a)
    _, pa = _persona(org_a)
    asignar(o, pa, actor)
    n = EventoTrabajo.objects.filter(orden=o).count()
    _, cambio = cambiar_principal(o, pa, actor)
    assert cambio is False
    assert EventoTrabajo.objects.filter(orden=o).count() == n


# ================================================== 8-13. retiro
@pytest.mark.django_db
def test_8_retirar_auxiliar(org_a, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    agregar_integrante(o, pb, actor, rol="ayudante")

    r = retirar_integrante(o, pb, actor)
    o.refresh_from_db()
    assert r["cambio_principal"] is False
    assert o.tecnico_principal == pa, "retirar al auxiliar movio al principal"
    ok, n, p = _invariante(o)
    assert ok and (n, p) == (1, 1)


@pytest.mark.django_db
def test_9_retirar_principal_con_sucesor(org_a, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    agregar_integrante(o, pb, actor, rol="ayudante")

    r = retirar_integrante(o, pa, actor, nuevo_principal=pb, motivo="se retira")
    o.refresh_from_db()
    assert r["cambio_principal"] is True
    assert not o.asignaciones.filter(profile=pa).exists()
    assert o.tecnico_principal == pb
    ok, n, p = _invariante(o)
    assert ok and (n, p) == (1, 1)


@pytest.mark.django_db
def test_10_retirar_principal_sin_sucesor_se_rechaza(org_a, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    agregar_integrante(o, pb, actor, rol="ayudante")

    with pytest.raises(RequiereSucesor):
        retirar_integrante(o, pa, actor)
    o.refresh_from_db()
    assert o.tecnico_principal == pa, "el rechazo dejo la orden tocada"
    assert o.asignaciones.count() == 2


@pytest.mark.django_db
def test_10b_retirar_al_ultimo_no_exige_sucesor(org_a, actor):
    """Queda en 0 integrantes, que F-2 declara valido."""
    o = _orden(org_a)
    _, pa = _persona(org_a)
    asignar(o, pa, actor)
    r = retirar_integrante(o, pa, actor, motivo="se cancela la salida")
    o.refresh_from_db()
    assert r["principal"] is None
    ok, n, p = _invariante(o)
    assert ok and (n, p) == (0, 0)


@pytest.mark.django_db
def test_11_sucesor_de_otra_ot_se_rechaza(org_a, actor):
    o1, o2 = _orden(org_a), _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    _, pc = _persona(org_a)
    asignar(o1, pa, actor, rol="tecnico_lider")
    agregar_integrante(o1, pb, actor, rol="ayudante")
    asignar(o2, pc, actor)          # pc esta en la OTRA orden

    with pytest.raises(ErrorDespacho, match="no esta asignada a esta orden"):
        retirar_integrante(o1, pa, actor, nuevo_principal=pc)
    o1.refresh_from_db()
    assert o1.tecnico_principal == pa and o1.asignaciones.count() == 2


@pytest.mark.django_db
def test_12_sucesor_inexistente_se_rechaza(org_a, actor):
    """Por la API: un UUID que no es de nadie de esta empresa da 404."""
    o = _orden(org_a)
    ug, g = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, g, rol="tecnico_lider")
    agregar_integrante(o, pb, g, rol="ayudante")
    cli = _cli(ug, org_a, g)

    r = cli.post(f"/api/campo/trabajos/{o.id}/cuadrilla/retirar/",
                 {"profile_id": str(pa.id),
                  "nuevo_principal_id": "11111111-1111-1111-1111-111111111111"},
                 format="json")
    assert r.status_code == 404
    o.refresh_from_db()
    assert o.tecnico_principal == pa and o.asignaciones.count() == 2


@pytest.mark.django_db
def test_13_sucesor_igual_al_retirado_se_rechaza(org_a, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    agregar_integrante(o, pb, actor, rol="ayudante")

    with pytest.raises(ErrorDespacho, match="no puede ser la misma persona"):
        retirar_integrante(o, pa, actor, nuevo_principal=pa)
    o.refresh_from_db()
    assert o.tecnico_principal == pa and o.asignaciones.count() == 2


# ================================================== 14-15. catalogo de roles
@pytest.mark.django_db
def test_14_rol_valido(org_a):
    """Los CINCO del catalogo, no solo uno."""
    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)
    for rol, _n_ in AsignacionTrabajo.ROLES_CUADRILLA:
        o = _orden(org_a)
        _, p1 = _persona(org_a)
        r = cli.post(f"/api/campo/trabajos/{o.id}/asignar/",
                     {"profile_id": str(p1.id), "rol": rol}, format="json")
        assert r.status_code == 200, (rol, r.data)
        assert AsignacionTrabajo.objects.get(orden=o, profile=p1).rol == rol


@pytest.mark.django_db
def test_15_rol_invalido_se_rechaza(org_a):
    """
    F-4. Este es el caso que M03-F-A.1 midio respondiendo 200 y persistiendo
    la cadena tal cual. Se prueba por las DOS puertas que aceptan rol.
    """
    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)
    o = _orden(org_a)
    _, p1 = _persona(org_a)
    _, p2 = _persona(org_a)

    r = cli.post(f"/api/campo/trabajos/{o.id}/asignar/",
                 {"profile_id": str(p1.id),
                  "rol": "capitan_pirata_que_no_existe"}, format="json")
    assert r.status_code == 400, "la API acepto un rol fuera del catalogo"
    assert not AsignacionTrabajo.objects.filter(orden=o).exists()

    asignar(o, p1, g, rol="tecnico_lider")
    r = cli.post(f"/api/campo/trabajos/{o.id}/cuadrilla/agregar/",
                 {"profile_id": str(p2.id),
                  "rol": "capitan_pirata_que_no_existe"}, format="json")
    assert r.status_code == 400
    assert o.asignaciones.count() == 1


# ================================================== 16-17. los dos imposibles
@pytest.mark.django_db
def test_16_dos_principales_es_imposible(org_a, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AsignacionTrabajo.objects.create(orden=o, profile=pb,
                                             es_principal=True)


@pytest.mark.django_db
def test_17_cero_principales_con_integrantes_es_imposible(org_a, actor):
    """
    Ninguna operacion del servicio puede producirlo. Se recorren TODAS y se
    comprueba el invariante despues de cada una.
    """
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    _, pc = _persona(org_a)

    pasos = [
        ("asignar", lambda: asignar(o, pa, actor, rol="tecnico_lider")),
        ("agregar b", lambda: agregar_integrante(o, pb, actor, rol="ayudante")),
        ("agregar c", lambda: agregar_integrante(o, pc, actor, rol="chofer")),
        ("cambiar principal", lambda: cambiar_principal(o, pb, actor)),
        ("retirar auxiliar", lambda: retirar_integrante(o, pc, actor)),
        ("retirar principal", lambda: retirar_integrante(
            o, pb, actor, nuevo_principal=pa)),
        ("retirar ultimo", lambda: retirar_integrante(o, pa, actor)),
    ]
    for nombre, paso in pasos:
        paso()
        o.refresh_from_db()
        ok, n, p = _invariante(o)
        assert ok, f"tras '{nombre}': {n} integrantes y {p} principales"


# ================================================== 18-19. concurrencia
@pytest.mark.django_db(transaction=True)
def test_18_concurrencia_cambio_de_principal(org_a):
    """
    Dos cambios simultaneos. Con el lock quedan serializados y coherentes.

    HONESTIDAD SOBRE ESTA PRUEBA: este escenario tambien queda coherente sin el
    lock de la OT, porque el UPDATE sobre la fila del principal ya serializa a
    nivel de fila. La prueba que demuestra que el lock es necesario es la 19.
    """
    o = _orden(org_a)
    _, act = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    _, pc = _persona(org_a)
    asignar(o, pa, act, rol="tecnico_lider")
    agregar_integrante(o, pb, act, rol="ayudante")
    agregar_integrante(o, pc, act, rol="ayudante")

    barrera = threading.Barrier(2)
    fallos = []

    def hilo(nuevo):
        try:
            barrera.wait(timeout=10)
            cambiar_principal(o, nuevo, act)
        except Exception as e:
            fallos.append(f"{type(e).__name__}: {str(e).splitlines()[0][:60]}")
        finally:
            connection.close()

    hs = [threading.Thread(target=hilo, args=(p,)) for p in (pb, pc)]
    for h in hs: h.start()
    for h in hs: h.join(timeout=30)

    o.refresh_from_db()
    ok, n, p = _invariante(o)
    assert not fallos, fallos
    assert ok and (n, p) == (3, 1)


@pytest.mark.django_db(transaction=True)
@pytest.mark.django_db(transaction=True)
def test_19_concurrencia_retiro_y_reemplazo(org_a):
    """
    ESTE es el escenario que el lock existe para evitar, y se demuestra
    DESARMANDOLO.

    OT: A principal, B auxiliar, C auxiliar.
      operacion 1: retirar A nombrando sucesor a B
      operacion 2: retirar B (auxiliar)

    Sin lock, la 1 comprueba que B esta, la 2 borra a B, y el 'update' de la 1
    no encuentra a quien ascender: queda C solo y SIN principal -- el estado
    prohibido.

    La rama sin lock NO se deja al azar del planificador: se entrelaza a mano
    en el punto exacto del hueco (entre la comprobacion del sucesor y la
    escritura). Una prueba de concurrencia que depende del timing pasa o falla
    por lo que no importa.
    """
    def montar():
        o = _orden(org_a)
        _, act = _persona(org_a, "OPERACIONES")
        _, pa = _persona(org_a)
        _, pb = _persona(org_a)
        _, pc = _persona(org_a)
        asignar(o, pa, act, rol="tecnico_lider")
        agregar_integrante(o, pb, act, rol="ayudante")
        agregar_integrante(o, pc, act, rol="ayudante")
        return o, act, pa, pb, pc

    #  ---- 1. CON el lock: dos hilos de verdad, el invariante aguanta -------
    o, act, pa, pb, pc = montar()
    barrera = threading.Barrier(2)
    errores = []

    def h1():
        try:
            barrera.wait(timeout=10)
            retirar_integrante(o, pa, act, nuevo_principal=pb)
        except Exception as e:
            errores.append(type(e).__name__)
        finally:
            connection.close()

    def h2():
        try:
            barrera.wait(timeout=10)
            retirar_integrante(o, pb, act)
        except Exception as e:
            errores.append(type(e).__name__)
        finally:
            connection.close()

    ts = [threading.Thread(target=h1), threading.Thread(target=h2)]
    for t in ts: t.start()
    for t in ts: t.join(timeout=30)
    o.refresh_from_db()
    ok, n, p = _invariante(o)
    assert ok, f"con lock quedaron {n} integrantes y {p} principales"

    #  ---- 2. SIN el lock: entrelazado deterministic en el hueco -----------
    o2, act2, pa2, pb2, pc2 = montar()
    real_foto = _despacho._foto_cuadrilla
    disparado = []

    def foto_que_entrelaza(orden):
        #  '_foto_cuadrilla' se llama justo despues de validar al sucesor y
        #  justo antes de borrar/ascender: es exactamente el hueco.
        if not disparado:
            disparado.append(True)
            otro = threading.Thread(
                target=lambda: (retirar_integrante(o2, pb2, act2),
                                connection.close()))
            otro.start()
            otro.join(timeout=30)
        return real_foto(orden)

    sin_lock = lambda orden: OrdenTrabajo.objects.get(pk=orden.pk)
    with mock.patch.object(_despacho, "_bloquear", sin_lock), \
         mock.patch.object(_despacho, "_foto_cuadrilla", foto_que_entrelaza):
        try:
            retirar_integrante(o2, pa2, act2, nuevo_principal=pb2)
        except Exception:
            pass

    o2.refresh_from_db()
    ok2, n2, p2 = _invariante(o2)
    assert disparado, "el entrelazado no llego a ejecutarse"
    assert not ok2, (
        "el escenario quedo coherente SIN el lock: la prueba no demuestra "
        f"que el lock sirva ({n2} integrantes, {p2} principales)")
    assert (n2, p2) == (1, 0), (
        f"se esperaba 1 integrante huerfano y 0 principales; hubo {n2} y {p2}")


# ================================================== 20. rollback / atomicidad
@pytest.mark.django_db(transaction=True)
def test_20_CRITICA_atomicidad_del_retiro_del_principal(org_a):
    """
    §19 DEL ENCARGO -- OBLIGATORIA.

    Se fuerza una excepcion DESPUES de mover las dos asignaciones y ANTES del
    commit, y el estado se verifica con una CONEXION INDEPENDIENTE del ORM.
    """
    o = _orden(org_a)
    _, act = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, act, rol="tecnico_lider")
    agregar_integrante(o, pb, act, rol="ayudante")
    eventos_antes = EventoTrabajo.objects.filter(orden=o).count()

    #  '_evento' corre despues del delete del saliente y del update del sucesor
    with mock.patch("campo.services.despacho._evento",
                    side_effect=RuntimeError("fallo antes del commit")):
        with pytest.raises(RuntimeError):
            retirar_integrante(o, pa, act, nuevo_principal=pb)

    con = _independiente()
    try:
        cur = con.cursor()
        cur.execute(
            "select profile_id, es_principal, rol from campo_asignacion_trabajo "
            "where orden_id = %s order by asignado_en", (str(o.id),))
        filas = cur.fetchall()
        cur.execute("select count(*) n from campo_evento_trabajo "
                    "where orden_id = %s", (str(o.id),))
        eventos = cur.fetchone()["n"]
    finally:
        con.close()

    por_persona = {str(f["profile_id"]): f for f in filas}
    assert len(filas) == 2, f"quedo un estado parcial: {filas}"
    assert por_persona[str(pa.id)]["es_principal"] is True, "A dejo de ser principal"
    assert por_persona[str(pb.id)]["es_principal"] is False, "B quedo ascendido"
    assert eventos == eventos_antes, "se escribio un evento de una operacion fallida"


@pytest.mark.django_db(transaction=True)
def test_20b_FALLA_SILENCIOSA_nunca_retirado_sin_sucesor_ascendido(org_a):
    """
    §20 DEL ENCARGO.

    El estado que M03-F-A.3 midio como legal e invisible:
        A retirado  +  B sigue auxiliar
    No debe existir por ningun camino. O pasan las dos cosas, o ninguna.
    """
    def estado(o, pa, pb):
        o.refresh_from_db()
        return (o.asignaciones.filter(profile=pa).exists(),
                o.asignaciones.filter(profile=pb, es_principal=True).exists())

    #  camino que falla
    o = _orden(org_a)
    _, act = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, act, rol="tecnico_lider")
    agregar_integrante(o, pb, act, rol="ayudante")
    with mock.patch("campo.services.despacho._evento",
                    side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            retirar_integrante(o, pa, act, nuevo_principal=pb)
    a_esta, b_manda = estado(o, pa, pb)
    assert (a_esta, b_manda) == (True, False), "estado parcial tras el fallo"

    #  camino que funciona
    retirar_integrante(o, pa, act, nuevo_principal=pb)
    a_esta, b_manda = estado(o, pa, pb)
    assert (a_esta, b_manda) == (False, True)

    #  la combinacion prohibida no aparecio en ninguno de los dos
    assert not (a_esta is False and b_manda is False), (
        "se alcanzo el estado prohibido: principal retirado y sucesor auxiliar")


# ================================================== 21-22. idempotencia
@pytest.mark.django_db
def test_21_idempotencia_replay(org_a):
    """La MISMA peticion repetida no agrega dos veces ni duplica el evento."""
    o = _orden(org_a)
    ug, g = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, g, rol="tecnico_lider")
    cli = _cli(ug, org_a, g)
    cuerpo = {"profile_id": str(pb.id), "rol": "ayudante"}
    url = f"/api/campo/trabajos/{o.id}/cuadrilla/agregar/"

    r1 = cli.post(url, cuerpo, format="json", HTTP_IDEMPOTENCY_KEY="fb-21")
    r2 = cli.post(url, cuerpo, format="json", HTTP_IDEMPOTENCY_KEY="fb-21")
    assert r1.status_code == 200 and r2.status_code == 200
    assert o.asignaciones.count() == 2, "el replay agrego dos veces"
    assert EventoTrabajo.objects.filter(
        orden=o, tipo="integrante_agregado").count() == 1


@pytest.mark.django_db
def test_22_idempotencia_misma_clave_otro_cuerpo(org_a):
    o = _orden(org_a)
    ug, g = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    _, pc = _persona(org_a)
    asignar(o, pa, g, rol="tecnico_lider")
    cli = _cli(ug, org_a, g)
    url = f"/api/campo/trabajos/{o.id}/cuadrilla/agregar/"

    cli.post(url, {"profile_id": str(pb.id), "rol": "ayudante"},
             format="json", HTTP_IDEMPOTENCY_KEY="fb-22")
    r = cli.post(url, {"profile_id": str(pc.id), "rol": "chofer"},
                 format="json", HTTP_IDEMPOTENCY_KEY="fb-22")
    assert r.status_code == 409
    assert r.data["error"] == "IDEMPOTENCY_KEY_REUSED"
    assert o.asignaciones.count() == 2, "el cuerpo distinto igual se ejecuto"


# ================================================== 23. composicion visible
@pytest.mark.django_db
def test_23_composicion_visible_en_el_serializer(org_a):
    o = _orden(org_a)
    ug, g = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, g, rol="tecnico_lider")
    agregar_integrante(o, pb, g, rol="ayudante")
    cli = _cli(ug, org_a, g)

    r = cli.get(f"/api/campo/trabajos/{o.id}/")
    assert r.status_code == 200
    cuadrilla = r.data["cuadrilla"]
    assert len(cuadrilla) == 2
    por_id = {str(x["profile_id"]): x for x in cuadrilla}
    assert por_id[str(pa.id)]["es_principal"] is True
    assert por_id[str(pa.id)]["rol"] == "tecnico_lider"
    assert por_id[str(pb.id)]["es_principal"] is False
    for x in cuadrilla:
        assert x["nombre"] and x["rol_display"] and x["asignado_en"]
    #  'tecnico_principal' se conserva: la bandeja y H-05 lo consumen
    assert r.data["tecnico_principal"]["id"] == str(pa.id)


# ================================================== 24-25. permisos y tenant
@pytest.mark.django_db
def test_24_tenant_a_no_opera_sobre_ot_de_tenant_b(org_a, org_b):
    o_b = _orden(org_b)
    _, pb1 = _persona(org_b)
    ug, g = _persona(org_a, "OPERACIONES")
    AsignacionTrabajo.objects.create(orden=o_b, profile=pb1,
                                     rol="tecnico", es_principal=True)
    cli = _cli(ug, org_a, g)

    for ruta, cuerpo in (
            ("cuadrilla/agregar/", {"profile_id": str(pb1.id)}),
            ("cuadrilla/principal/", {"profile_id": str(pb1.id)}),
            ("cuadrilla/retirar/", {"profile_id": str(pb1.id)}),
            ("cuadrilla/desasignar/", {})):
        r = cli.post(f"/api/campo/trabajos/{o_b.id}/{ruta}", cuerpo,
                     format="json")
        assert r.status_code == 404, f"{ruta} devolvio {r.status_code}, no 404"
    assert o_b.asignaciones.count() == 1


@pytest.mark.django_db
def test_25_usuario_sin_permiso_no_opera(org_a):
    o = _orden(org_a)
    _, g = _persona(org_a, "OPERACIONES")
    ut, t = _persona(org_a, "USER")
    _, pa = _persona(org_a)
    asignar(o, pa, g, rol="tecnico_lider")
    cli = _cli(ut, org_a, t)

    for ruta, cuerpo in (
            ("cuadrilla/agregar/", {"profile_id": str(t.id)}),
            ("cuadrilla/principal/", {"profile_id": str(pa.id)}),
            ("cuadrilla/retirar/", {"profile_id": str(pa.id)}),
            ("cuadrilla/desasignar/", {})):
        r = cli.post(f"/api/campo/trabajos/{o.id}/{ruta}", cuerpo, format="json")
        assert r.status_code == 403, f"{ruta} dejo pasar a un tecnico"
    assert o.asignaciones.count() == 1


# ================================================== 26-27. programacion intacta
@pytest.mark.django_db
def test_26_27_la_programacion_no_se_mueve(org_a):
    """
    Las dos exigencias juntas, sobre la MISMA linea: ninguna operacion de
    composicion toca fecha, plan, secuencia, dia, zona, prioridad ni estado.
    Se compara tambien 'updated_at' de la linea: los valores podrian coincidir
    y aun asi haberse reescrito.
    """
    o = _orden(org_a)
    _, act = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    _, pc = _persona(org_a)
    plan = ProgramacionSemanal.objects.create(
        org=org_a, semana_inicio=LUNES, estado=ProgramacionSemanal.BORRADOR)
    asignar(o, pa, act, rol="tecnico_lider")
    linea = programar_orden(org=org_a, orden=o, programacion=plan,
                            programada_para=_dt(2, 11), actor=act,
                            secuencia=5, zona="sur", prioridad=2)

    def foto():
        o.refresh_from_db(); linea.refresh_from_db()
        return (o.programada_para, o.estado_operativo, linea.secuencia,
                linea.dia, linea.zona, linea.prioridad, linea.estado,
                linea.updated_at,
                ProgramacionOrden.objects.filter(programacion=plan).count())

    antes = foto()
    agregar_integrante(o, pb, act, rol="ayudante")
    agregar_integrante(o, pc, act, rol="chofer")
    cambiar_principal(o, pb, act)
    retirar_integrante(o, pc, act)
    retirar_integrante(o, pb, act, nuevo_principal=pa)
    assert foto() == antes, "una operacion de cuadrilla movio la programacion"


# ================================================== 28. disponibilidad
@pytest.mark.django_db
def test_28_la_disponibilidad_no_modifica_la_composicion(org_a):
    o = _orden(org_a)
    _, act = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, act, rol="tecnico_lider")
    agregar_integrante(o, pb, act, rol="ayudante")
    o.programada_para = _dt(1)
    o.save(update_fields=["programada_para"])
    antes = list(o.asignaciones.order_by("asignado_en")
                 .values_list("profile_id", "es_principal"))

    DisponibilidadTecnico.objects.create(
        org=org_a, profile=pa, fecha=LUNES + timedelta(days=1),
        hora_inicio=time(8, 0), hora_fin=time(18, 0),
        disponible=False, motivo="incapacidad")

    o.refresh_from_db()
    despues = list(o.asignaciones.order_by("asignado_en")
                   .values_list("profile_id", "es_principal"))
    assert antes == despues, "declarar una ausencia cambio la cuadrilla"
    assert o.tecnico_principal == pa


# ================================================== 29. auditoria
@pytest.mark.django_db
def test_29_auditoria_completa(org_a):
    """
    Cada operacion deja UN evento, con antes, despues, actor y timestamp --
    informacion suficiente para reconstruir la transicion, no solo para
    enterarse de que hubo una.
    """
    o = _orden(org_a)
    _, act = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    _, pc = _persona(org_a)

    asignar(o, pa, act, rol="tecnico_lider")
    agregar_integrante(o, pb, act, rol="ayudante")
    agregar_integrante(o, pc, act, rol="chofer")
    cambiar_principal(o, pb, act, motivo="rota")
    retirar_integrante(o, pc, act, motivo="no hace falta chofer")
    retirar_integrante(o, pb, act, nuevo_principal=pa, motivo="se va")
    desasignar(o, act, motivo="se cancela")

    tipos = list(EventoTrabajo.objects.filter(orden=o)
                 .order_by("created_at").values_list("tipo", flat=True))
    assert tipos == ["asignacion", "integrante_agregado", "integrante_agregado",
                     "cambio_principal", "integrante_retirado",
                     "principal_retirado", "cuadrilla_desasignada"], tipos

    for ev in EventoTrabajo.objects.filter(orden=o).exclude(tipo="asignacion"):
        assert ev.profile_id == act.id, f"{ev.tipo} sin actor"
        assert ev.created_at is not None
        assert "antes" in ev.datos and "despues" in ev.datos, ev.tipo
        assert isinstance(ev.datos["antes"], list)

    pr = EventoTrabajo.objects.get(orden=o, tipo="principal_retirado")
    assert pr.datos["integrante_retirado"] == str(pb.id)
    assert pr.datos["principal_anterior"] == str(pb.id)
    assert pr.datos["principal_nuevo"] == str(pa.id)
    assert pr.datos["motivo"] == "se va"
    #  la transicion se reconstruye: antes mandaba pb, despues manda pa
    assert [x for x in pr.datos["antes"] if x["es_principal"]][0]["profile"] == str(pb.id)
    assert [x for x in pr.datos["despues"] if x["es_principal"]][0]["profile"] == str(pa.id)

    #  'cambio_principal' usa las MISMAS claves, para que una sola consulta
    #  sobre 'principal_nuevo' cubra los dos tipos de evento
    cp = EventoTrabajo.objects.get(orden=o, tipo="cambio_principal")
    assert cp.datos["principal_anterior"] == str(pa.id)
    assert cp.datos["principal_nuevo"] == str(pb.id)


# ================================================== 30. desasignacion total
@pytest.mark.django_db
def test_30_desasignacion_total(org_a):
    o = _orden(org_a)
    _, act = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, act, rol="tecnico_lider")
    agregar_integrante(o, pb, act, rol="ayudante")

    cuantos = desasignar(o, act, motivo="se pospone")
    o.refresh_from_db()
    assert cuantos == 2
    ok, n, p = _invariante(o)
    assert ok and (n, p) == (0, 0)
    assert o.tecnico_principal is None
    ev = EventoTrabajo.objects.get(orden=o, tipo="cuadrilla_desasignada")
    assert len(ev.datos["antes"]) == 2 and ev.datos["despues"] == []
    #  repetir sobre una orden vacia es un no-op, no un error
    assert desasignar(o, act) == 0


@pytest.mark.django_db
def test_30b_desasignar_no_es_atajo_para_sacar_al_principal(org_a):
    """
    §7 del encargo: no puede usarse como sustituto del retiro con sucesor.
    Es estructural -- se lleva a TODOS, asi que no puede dejar integrantes
    huerfanos de principal.
    """
    o = _orden(org_a)
    _, act = _persona(org_a, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, act, rol="tecnico_lider")
    agregar_integrante(o, pb, act, rol="ayudante")
    desasignar(o, act)
    o.refresh_from_db()
    assert o.asignaciones.count() == 0, "desasignar dejo gente sin principal"


# ================================================== extras de contrato
@pytest.mark.django_db
def test_31_no_se_toca_la_cuadrilla_de_una_orden_terminada(org_a, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    agregar_integrante(o, pb, actor, rol="ayudante")
    o.estado_operativo = OrdenTrabajo.CERRADA
    o.save(update_fields=["estado_operativo"])

    for fn in (lambda: agregar_integrante(o, _persona(org_a)[1], actor),
               lambda: cambiar_principal(o, pb, actor),
               lambda: retirar_integrante(o, pb, actor),
               lambda: desasignar(o, actor)):
        with pytest.raises(ErrorDespacho, match="trabajo terminado"):
            fn()
    assert o.asignaciones.count() == 2


@pytest.mark.django_db
def test_32_sucesor_con_foto_vieja_da_conflicto(org_a, actor):
    """
    Se pide retirar a un auxiliar nombrando un sucesor que NO es el principal
    actual: la foto del solicitante quedo vieja. Se rechaza, no se adivina.
    """
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    _, pc = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    agregar_integrante(o, pb, actor, rol="ayudante")
    agregar_integrante(o, pc, actor, rol="chofer")

    with pytest.raises(ConflictoDeCuadrilla):
        retirar_integrante(o, pb, actor, nuevo_principal=pc)
    assert o.asignaciones.count() == 3


@pytest.mark.django_db
def test_33_no_se_agrega_dos_veces_a_la_misma_persona(org_a, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    agregar_integrante(o, pb, actor, rol="ayudante")
    with pytest.raises(ErrorDespacho, match="ya esta en la cuadrilla"):
        agregar_integrante(o, pb, actor, rol="chofer")
    assert o.asignaciones.count() == 2


@pytest.mark.django_db
def test_34_persona_de_otra_empresa_se_rechaza(org_a, org_b, actor):
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, ajena = _persona(org_b)
    asignar(o, pa, actor, rol="tecnico_lider")
    with pytest.raises(ErrorDespacho, match="otra empresa"):
        agregar_integrante(o, ajena, actor)
    assert o.asignaciones.count() == 1


@pytest.mark.django_db
def test_35_la_revision_sube_para_la_cola_offline(org_a, actor):
    """
    'revision' es el contador que sincroniza la app del tecnico. Si cambia la
    cuadrilla, el dispositivo tiene que enterarse -- es la unica escritura
    sobre la OT que estas operaciones si deben hacer.
    """
    o = _orden(org_a)
    _, pa = _persona(org_a)
    _, pb = _persona(org_a)
    asignar(o, pa, actor, rol="tecnico_lider")
    o.refresh_from_db()
    r0 = o.revision
    agregar_integrante(o, pb, actor, rol="ayudante")
    o.refresh_from_db()
    assert o.revision == r0 + 1
    cambiar_principal(o, pb, actor)
    o.refresh_from_db()
    assert o.revision == r0 + 2
