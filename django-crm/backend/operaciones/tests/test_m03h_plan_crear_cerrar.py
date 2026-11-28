# -*- coding: utf-8 -*-
"""
================================================================================
 EL CICLO DEL PLAN SEMANAL, DE PUNTA A PUNTA
================================================================================

M03 declaraba 'borrador -> publicada -> cerrada' y le faltaban las dos puntas:

  * CREAR un plan solo se podía desde el admin de Django. El efecto medible es
    que producción tenía CERO planes, y con eso todo M03 bloqueado:
    'programar_orden' exige un 'programacion_semanal_id' que no existía, así
    que ninguna orden podía programarse desde la aplicación.
  * CERRAR no lo hacía nadie. 'cerrada' estaba en ESTADOS y ninguna función la
    asignaba: la semana pasada seguía figurando como 'publicada' para siempre.

Lo que estas pruebas afirman es el EFECTO, y sobre todo el efecto de lo que NO
debe pasar: que un plan no nazca publicado, que dos peticiones simultáneas no
creen dos planes de la misma semana, que cerrar no toque ninguna orden y que
el segundo cierre no vuelva a escribir.
================================================================================
"""

from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta

import pytest
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from conftest import rls_org
from operaciones.models import ProgramacionOrden, ProgramacionSemanal
from operaciones.programacion import programar_orden

pytestmark = pytest.mark.django_db

RUTA = "/api/operaciones/programacion/"
LUNES = date(2026, 10, 5)            # lunes
MIERCOLES = date(2026, 10, 7)


def _perfil(org, correo, rol="OPERACIONES"):
    u = User.objects.create_user(email=correo, password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=rol, is_active=True)


def _cliente(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


@pytest.fixture
def gestor(org_a):
    return _perfil(org_a, "jefe@planes.test")


@pytest.fixture
def cliente(org_a, gestor):
    return _cliente(gestor[0], org_a, gestor[1])


def _plan(org, *, lunes=LUNES, estado=ProgramacionSemanal.BORRADOR):
    return ProgramacionSemanal.objects.create(
        org=org, semana_inicio=lunes, estado=estado)


def _orden(org, numero=7100):
    wt = WorkType.objects.create(org=org, codigo=f"pl{numero}", nombre="Tipo plan")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"campos": [], "evidencias": []})
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Cliente plan", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA)


# =============================================================================
#  §1  Crear
# =============================================================================

def test_se_crea_el_plan_de_una_semana(org_a, cliente):
    r = cliente.post(RUTA, {"semana_inicio": str(LUNES)}, format="json")

    assert r.status_code == 201
    plan = ProgramacionSemanal.objects.get(org=org_a)
    assert plan.semana_inicio == LUNES
    assert r.json()["programacion"]["id"] == str(plan.id)


def test_un_plan_nace_siempre_en_borrador(org_a, cliente):
    """Publicar es una decisión posterior, con su actor y su sello."""
    r = cliente.post(RUTA, {"semana_inicio": str(LUNES)}, format="json")

    assert r.json()["programacion"]["estado"] == ProgramacionSemanal.BORRADOR
    assert ProgramacionSemanal.objects.get(org=org_a).publicada_en is None


def test_el_estado_no_se_puede_elegir_desde_el_cuerpo(org_a, cliente):
    """
    Si 'estado' entrara por el cuerpo, se podría crear un plan ya publicado sin
    que nadie hubiera revisado su coherencia.
    """
    r = cliente.post(RUTA, {"semana_inicio": str(LUNES),
                            "estado": ProgramacionSemanal.PUBLICADA}, format="json")

    assert r.status_code == 201
    assert ProgramacionSemanal.objects.get(org=org_a).estado == ProgramacionSemanal.BORRADOR


def test_un_plan_recien_creado_ya_admite_ordenes(org_a, cliente, gestor):
    """
    El punto de todo el bloque: que desde la aplicación se pueda crear un plan
    y programar una orden dentro, sin pasar por el admin.
    """
    respuesta = cliente.post(RUTA, {"semana_inicio": str(LUNES)}, format="json")
    plan = ProgramacionSemanal.objects.get(id=respuesta.json()["programacion"]["id"])
    orden = _orden(org_a)

    linea = programar_orden(
        org=org_a, orden=orden, programacion=plan,
        programada_para=timezone.make_aware(
            datetime.combine(LUNES + timedelta(days=2), time(9, 0))),
        actor=gestor[1])

    assert linea.programacion_id == plan.id
    assert respuesta.json()["programacion"]["admite_lineas"] is True


def test_una_semana_que_no_empieza_en_lunes_se_rechaza_diciendo_cual_es(org_a, cliente):
    """
    'programar_orden' cuenta siete días desde 'semana_inicio'. Con un miércoles,
    la semana sería miércoles→martes y dos planes solapados podrían convivir sin
    violar la unicidad.
    """
    r = cliente.post(RUTA, {"semana_inicio": str(MIERCOLES)}, format="json")

    assert r.status_code == 400
    assert "lunes" in str(r.json()).lower()
    #  Y no se corrige en silencio: no se crea nada.
    assert not ProgramacionSemanal.objects.exists()


def test_la_fecha_es_obligatoria(org_a, cliente):
    assert cliente.post(RUTA, {}, format="json").status_code == 400
    assert not ProgramacionSemanal.objects.exists()


# =============================================================================
#  §2  Una semana, un plan
# =============================================================================

def test_la_segunda_vez_devuelve_el_plan_que_ya_estaba(org_a, cliente):
    """
    Un 500 de IntegrityError no le sirve a nadie: se contesta 409 CON el plan
    existente, para que quien llamó pueda usarlo en vez de reintentar a ciegas.
    """
    primera = cliente.post(RUTA, {"semana_inicio": str(LUNES)}, format="json")
    segunda = cliente.post(RUTA, {"semana_inicio": str(LUNES)}, format="json")

    assert primera.status_code == 201
    assert segunda.status_code == 409
    assert segunda.json()["error"] == "YA_EXISTE"
    assert segunda.json()["programacion"]["id"] == primera.json()["programacion"]["id"]
    assert ProgramacionSemanal.objects.filter(org=org_a).count() == 1


@pytest.mark.django_db(transaction=True)
def test_dos_peticiones_simultaneas_dejan_un_solo_plan():
    """
    La carrera vive entre comprobar "no existe" y crear. No se resuelve con un
    'select' previo: se deja que la restricción de la base decida, y el que
    pierde lee el que ganó.
    """
    from common.models import Org

    org = Org.objects.create(name="Org carrera planes")
    u, p = _perfil(org, "carrera@planes.test")
    partida = threading.Barrier(2)
    resultados = []

    def crear():
        try:
            partida.wait(timeout=10)
            c = _cliente(u, org, p)
            resultados.append(c.post(RUTA, {"semana_inicio": str(LUNES)},
                                     format="json").status_code)
        except Exception as e:                       # pragma: no cover
            resultados.append(f"error: {type(e).__name__}: {e}")
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=crear) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=20)

    assert ProgramacionSemanal.objects.filter(org=org).count() == 1, resultados
    assert sorted(resultados) == [201, 409], resultados


def test_dos_organizaciones_pueden_tener_la_misma_semana(org_a, org_b, cliente):
    """La unicidad es POR organización: el plan de una no bloquea el de la otra."""
    with rls_org(org_b):
        _plan(org_b)

    r = cliente.post(RUTA, {"semana_inicio": str(LUNES)}, format="json")

    assert r.status_code == 201
    assert ProgramacionSemanal.objects.count() == 2


# =============================================================================
#  §3  Cerrar
# =============================================================================

def _url_cerrar(plan):
    return f"{RUTA}{plan.id}/cerrar/"


def test_un_plan_publicado_se_cierra(org_a, cliente):
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)

    r = cliente.post(_url_cerrar(plan), {}, format="json")

    assert r.status_code == 200
    plan.refresh_from_db()
    assert plan.estado == ProgramacionSemanal.CERRADA


def test_un_plan_cerrado_ya_no_admite_ordenes_nuevas(org_a, cliente, gestor):
    """
    La regla no se reimplementa aquí: la aplica 'programar_orden' con la MISMA
    constante que el serializer expone como 'admite_lineas'.
    """
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    cliente.post(_url_cerrar(plan), {}, format="json")
    plan.refresh_from_db()
    orden = _orden(org_a, numero=7101)

    from operaciones.programacion import ErrorProgramacion
    with pytest.raises(ErrorProgramacion):
        programar_orden(org=org_a, orden=orden, programacion=plan,
                        programada_para=timezone.make_aware(
                            datetime.combine(LUNES + timedelta(days=1), time(9, 0))),
                        actor=gestor[1])


def test_no_se_cierra_un_borrador(org_a, cliente):
    """Cerrar un borrador archivaría un plan que nadie llegó a ver."""
    plan = _plan(org_a)

    r = cliente.post(_url_cerrar(plan), {}, format="json")

    assert r.status_code == 409
    assert r.json()["estado_actual"] == ProgramacionSemanal.BORRADOR
    plan.refresh_from_db()
    assert plan.estado == ProgramacionSemanal.BORRADOR


def test_el_segundo_cierre_no_vuelve_a_escribir(org_a, cliente):
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)

    primera = cliente.post(_url_cerrar(plan), {}, format="json")
    plan.refresh_from_db()
    sello = plan.updated_at
    segunda = cliente.post(_url_cerrar(plan), {}, format="json")

    assert primera.status_code == 200
    assert segunda.status_code == 409
    plan.refresh_from_db()
    #  Ni un UPDATE de más: el estado ES el registro de que ya ocurrió.
    assert plan.updated_at == sello


def test_cerrar_el_plan_no_cierra_ningun_trabajo(org_a, cliente, gestor):
    """
    Una orden a medias sigue a medias. Cerrar el plan dice que la semana
    terminó, no que el trabajo se hizo.
    """
    plan = _plan(org_a)
    orden = _orden(org_a, numero=7102)
    programar_orden(org=org_a, orden=orden, programacion=plan,
                    programada_para=timezone.make_aware(
                        datetime.combine(LUNES + timedelta(days=1), time(8, 0))),
                    actor=gestor[1])
    ProgramacionSemanal.objects.filter(id=plan.id).update(
        estado=ProgramacionSemanal.PUBLICADA)
    plan.refresh_from_db()
    antes = OrdenTrabajo.objects.get(id=orden.id).estado_operativo

    cliente.post(_url_cerrar(plan), {}, format="json")

    orden.refresh_from_db()
    assert orden.estado_operativo == antes
    #  Y la línea del plan sigue donde estaba.
    assert ProgramacionOrden.objects.get(orden=orden).estado == ProgramacionOrden.PLANIFICADA


def test_no_se_cierra_un_plan_que_no_existe(org_a, cliente):
    import uuid
    r = cliente.post(f"{RUTA}{uuid.uuid4()}/cerrar/", {}, format="json")
    assert r.status_code == 404


# =============================================================================
#  §4  Permisos y aislamiento
# =============================================================================

@pytest.mark.parametrize("accion", ["crear", "cerrar"])
def test_un_rol_sin_gestion_no_entra(org_a, accion):
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)
    u, p = _perfil(org_a, f"raso.{accion}@planes.test", rol="USER")
    c = _cliente(u, org_a, p)

    r = (c.post(RUTA, {"semana_inicio": str(LUNES + timedelta(days=7))}, format="json")
         if accion == "crear" else c.post(_url_cerrar(plan), {}, format="json"))

    assert r.status_code == 403
    plan.refresh_from_db()
    assert plan.estado == ProgramacionSemanal.PUBLICADA


def test_no_se_cierra_el_plan_de_otra_empresa(org_a, org_b, cliente):
    with rls_org(org_b):
        ajeno = _plan(org_b, estado=ProgramacionSemanal.PUBLICADA)

    r = cliente.post(_url_cerrar(ajeno), {}, format="json")

    #  404 y no 403: un 403 confirmaría que ese plan existe.
    assert r.status_code == 404
    ajeno.refresh_from_db()
    assert ajeno.estado == ProgramacionSemanal.PUBLICADA


def test_el_plan_se_crea_en_la_organizacion_de_la_sesion_y_no_en_la_del_cuerpo(
        org_a, org_b, cliente):
    r = cliente.post(RUTA, {"semana_inicio": str(LUNES),
                            "org": str(org_b.id),
                            "organization_id": str(org_b.id)}, format="json")

    assert r.status_code == 201
    assert ProgramacionSemanal.objects.filter(org=org_b).count() == 0
    assert ProgramacionSemanal.objects.get().org_id == org_a.id


# =============================================================================
#  §5  Ninguna de las dos llama a nadie
# =============================================================================

@pytest.fixture
def espia_requests(monkeypatch):
    import requests
    import requests.sessions

    llamadas = []

    def _trampa(nombre):
        def _f(*a, **k):
            llamadas.append(nombre)
            raise AssertionError(f"salida externa: {nombre}")
        return _f

    for m in ("get", "post", "put", "patch", "delete", "request"):
        monkeypatch.setattr(requests, m, _trampa(m))
        monkeypatch.setattr(requests.sessions.Session, m, _trampa(f"Session.{m}"))
    return llamadas


def test_crear_y_cerrar_no_llaman_a_ningun_sistema_externo(org_a, cliente, espia_requests):
    creado = cliente.post(RUTA, {"semana_inicio": str(LUNES)}, format="json")
    plan = ProgramacionSemanal.objects.get(id=creado.json()["programacion"]["id"])
    ProgramacionSemanal.objects.filter(id=plan.id).update(
        estado=ProgramacionSemanal.PUBLICADA)
    cliente.post(_url_cerrar(plan), {}, format="json")

    assert espia_requests == []
