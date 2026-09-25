# -*- coding: utf-8 -*-
"""
================================================================================
 LISTAR LOS PLANES SEMANALES  --  GET /api/operaciones/programacion/
================================================================================

La brecha que cierra: 'POST /api/campo/trabajos/<pk>/programar/' exige un
'programacion_semanal_id' que hasta ahora no se podia averiguar por la API.

QUE SE AFIRMA ACA, Y QUE NO
---------------------------
No se afirma que la vista "tenga" un filtro por organizacion ni que el
serializer "declare" un campo: eso es presencia de mecanismo, y una prueba asi
sobrevive a que el mecanismo se invierta. Se afirma el EFECTO:

  * que los planes de la otra empresa NO aparecen, ni cambiando la URL;
  * que 'admite_lineas' dice exactamente lo que el SERVICIO va a aceptar --
    se comprueba llamando a 'programar_orden' y viendo que rechaza justo los
    que la bandera marca en False. Si alguien cambia una de las dos reglas sin
    la otra, esta prueba se cae;
  * que el GET no deja ni una fila nueva ni un 'updated_at' movido;
  * que no sale una sola llamada HTTP, con el espia que LEVANTA ademas de
    contar (una prueba que solo cuenta puede pasar con la llamada ya hecha).
================================================================================
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from conftest import rls_org

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Activity, Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones.models import (NovedadOperativa, ProgramacionOrden,
                                ProgramacionSemanal)
from operaciones.programacion import ErrorProgramacion, programar_orden

RUTA = "/api/operaciones/programacion/"
LUNES = date(2026, 10, 5)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
#  Datos
# ---------------------------------------------------------------------------
def _plan(org, *, lunes=LUNES, estado=ProgramacionSemanal.BORRADOR):
    return ProgramacionSemanal.objects.create(
        org=org, semana_inicio=lunes, estado=estado)


def _perfil(org, correo, rol="OPERACIONES"):
    u = User.objects.create_user(email=correo, password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=rol, is_active=True)


def _cliente(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


@pytest.fixture
def gestor_a(org_a):
    return _perfil(org_a, "jefe.a@m03h.test")


@pytest.fixture
def cliente_a(org_a, gestor_a):
    return _cliente(gestor_a[0], org_a, gestor_a[1])


@pytest.fixture
def espia_requests(monkeypatch):
    """Cuenta CUALQUIER salida HTTP, y levanta ademas de contar."""
    import requests
    import requests.sessions

    llamadas = []

    def _trampa(nombre):
        def _f(*a, **k):
            llamadas.append((nombre, str(a[:1])[:120]))
            raise AssertionError(f"salida externa: {nombre} {a[:1]}")
        return _f

    for m in ("get", "post", "put", "patch", "delete", "request", "head",
              "options"):
        monkeypatch.setattr(requests, m, _trampa(m))
    for m in ("get", "post", "put", "patch", "delete", "request", "head",
              "options", "send"):
        monkeypatch.setattr(requests.sessions.Session, m, _trampa(f"Session.{m}"))
    return llamadas


# ---------------------------------------------------------------------------
#  §1  Lo que devuelve
# ---------------------------------------------------------------------------
def test_devuelve_los_planes_de_la_organizacion(org_a, cliente_a):
    _plan(org_a, lunes=LUNES)
    _plan(org_a, lunes=LUNES + timedelta(days=7))

    r = cliente_a.get(RUTA)

    assert r.status_code == 200
    assert r.json()["count"] == 2
    assert len(r.json()["resultados"]) == 2


def test_cada_plan_trae_id_semana_inicio_y_estado(org_a, cliente_a):
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA)

    fila = cliente_a.get(RUTA).json()["resultados"][0]

    assert fila["id"] == str(plan.id)
    assert fila["semana_inicio"] == LUNES.isoformat()
    assert fila["estado"] == ProgramacionSemanal.PUBLICADA
    #  El estado viaja crudo Y con su etiqueta: la pantalla no tiene que
    #  traducir 'publicada' por su cuenta ni inventar un rotulo.
    assert fila["estado_display"] == "Publicada"


def test_la_semana_termina_seis_dias_despues_del_lunes(org_a, cliente_a):
    _plan(org_a)

    fila = cliente_a.get(RUTA).json()["resultados"][0]

    assert fila["semana_fin"] == (LUNES + timedelta(days=6)).isoformat()


def test_no_expone_campos_que_el_modelo_no_tiene(org_a, cliente_a):
    _plan(org_a)

    fila = cliente_a.get(RUTA).json()["resultados"][0]

    assert set(fila) == {"id", "semana_inicio", "semana_fin", "estado",
                         "estado_display", "admite_lineas", "publicada_en",
                         "created_at"}


# ---------------------------------------------------------------------------
#  §2  Orden
# ---------------------------------------------------------------------------
def test_el_orden_es_por_semana_descendente(org_a, cliente_a):
    for n in (0, 2, 1):
        _plan(org_a, lunes=LUNES + timedelta(days=7 * n))

    semanas = [f["semana_inicio"]
               for f in cliente_a.get(RUTA).json()["resultados"]]

    assert semanas == sorted(semanas, reverse=True)


def test_dos_lecturas_iguales_devuelven_la_misma_lista(org_a, cliente_a):
    for n in range(4):
        _plan(org_a, lunes=LUNES + timedelta(days=7 * n))

    #  Determinismo: lo que se afirma es que el orden NO depende de la corrida.
    #  Dentro de una organizacion no puede haber empate de 'semana_inicio'
    #  --lo impide unique(org, semana_inicio)--, asi que el desempate por 'id'
    #  es una garantia estructural, no algo que se pueda observar con datos.
    primera = [f["id"] for f in cliente_a.get(RUTA).json()["resultados"]]
    segunda = [f["id"] for f in cliente_a.get(RUTA).json()["resultados"]]

    assert primera == segunda
    assert len(primera) == 4


# ---------------------------------------------------------------------------
#  §3  'admite_lineas' contra el servicio real
# ---------------------------------------------------------------------------
def _orden_asignada(org, numero=9301):
    wt = WorkType.objects.create(org=org, codigo="m03h", nombre="Tipo M03-H")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Cliente M03-H", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA)


@pytest.mark.parametrize("estado,esperado", [
    (ProgramacionSemanal.BORRADOR, True),
    (ProgramacionSemanal.PUBLICADA, True),
    (ProgramacionSemanal.CERRADA, False),
])
def test_admite_lineas_dice_lo_mismo_que_el_servicio(org_a, gestor_a, cliente_a,
                                                     estado, esperado):
    """
    La bandera no se compara contra una lista escrita aca: se compara contra lo
    que 'programar_orden' HACE. Es la unica forma de que no se desincronicen.
    """
    plan = _plan(org_a, estado=estado)
    fila = cliente_a.get(RUTA).json()["resultados"][0]
    assert fila["admite_lineas"] is esperado

    orden = _orden_asignada(org_a)
    cuando = timezone.make_aware(
        datetime.combine(LUNES + timedelta(days=2), time(9, 0)))
    try:
        programar_orden(org=org_a, orden=orden, programacion=plan,
                        programada_para=cuando, actor=gestor_a[1],
                        #  Del catalogo cerrado de NovedadOperativa: un plan
                        #  PUBLICADO exige causa, y una inventada la rechaza el
                        #  propio servicio.
                        causa=NovedadOperativa.CAMBIO_PRIORIDAD,
                        motivo="prueba M03-H")
        acepto = True
    except ErrorProgramacion:
        acepto = False

    assert acepto is esperado


def test_el_filtro_deja_solo_los_que_admiten_ordenes(org_a, cliente_a):
    _plan(org_a, lunes=LUNES, estado=ProgramacionSemanal.CERRADA)
    vivo = _plan(org_a, lunes=LUNES + timedelta(days=7),
                 estado=ProgramacionSemanal.BORRADOR)

    r = cliente_a.get(RUTA, {"admite_lineas": "1"})

    assert [f["id"] for f in r.json()["resultados"]] == [str(vivo.id)]
    assert r.json()["count"] == 1


def test_un_estado_que_no_existe_devuelve_vacio_y_no_se_corrige(org_a, cliente_a):
    _plan(org_a)

    r = cliente_a.get(RUTA, {"estado": "archivada"})

    assert r.status_code == 200
    assert r.json()["count"] == 0


# ---------------------------------------------------------------------------
#  §4  Permisos
# ---------------------------------------------------------------------------
def test_un_rol_sin_gestion_no_entra(org_a):
    _plan(org_a)
    u, p = _perfil(org_a, "raso.a@m03h.test", rol="USER")

    r = _cliente(u, org_a, p).get(RUTA)

    assert r.status_code == 403


def test_sin_sesion_no_entra(org_a):
    _plan(org_a)

    r = APIClient().get(RUTA)

    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
#  §5  Aislamiento entre organizaciones
# ---------------------------------------------------------------------------
def test_no_se_ven_los_planes_de_la_otra_empresa(org_a, org_b, cliente_a):
    with rls_org(org_b):
        ajeno = _plan(org_b, lunes=LUNES + timedelta(days=14))
    propio = _plan(org_a)

    ids = [f["id"] for f in cliente_a.get(RUTA).json()["resultados"]]

    assert ids == [str(propio.id)]
    assert str(ajeno.id) not in ids


@pytest.mark.parametrize("parametro", ["organization_id", "org", "org_id"])
def test_la_querystring_no_cambia_de_empresa(org_a, org_b, cliente_a, parametro):
    with rls_org(org_b):
        ajeno = _plan(org_b, lunes=LUNES + timedelta(days=14))
    propio = _plan(org_a)

    r = cliente_a.get(RUTA, {parametro: str(org_b.id)})

    assert r.status_code == 200
    assert [f["id"] for f in r.json()["resultados"]] == [str(propio.id)]
    assert str(ajeno.id) not in r.content.decode()


def test_una_organizacion_sin_planes_devuelve_lista_vacia(org_a, org_b, cliente_a):
    with rls_org(org_b):
        _plan(org_b)

    r = cliente_a.get(RUTA)

    assert r.status_code == 200
    assert r.json() == {"count": 0, "resultados": []}


# ---------------------------------------------------------------------------
#  §6  Cero efectos
# ---------------------------------------------------------------------------
def test_el_get_no_escribe_nada(org_a, cliente_a):
    plan = _plan(org_a)
    antes = {
        "planes": ProgramacionSemanal.objects.count(),
        "lineas": ProgramacionOrden.objects.count(),
        "auditoria": Activity.objects.count(),
    }
    tocado_antes = ProgramacionSemanal.objects.get(pk=plan.pk).updated_at

    assert cliente_a.get(RUTA).status_code == 200

    assert {
        "planes": ProgramacionSemanal.objects.count(),
        "lineas": ProgramacionOrden.objects.count(),
        "auditoria": Activity.objects.count(),
    } == antes
    #  Ni una escritura disimulada de 'updated_at': leer no es tocar.
    assert ProgramacionSemanal.objects.get(pk=plan.pk).updated_at == tocado_antes
    assert ProgramacionSemanal.objects.get(pk=plan.pk).estado == \
        ProgramacionSemanal.BORRADOR


def test_el_get_no_llama_a_nadie(org_a, cliente_a, espia_requests):
    _plan(org_a)

    assert cliente_a.get(RUTA).status_code == 200

    assert espia_requests == []


def test_la_ruta_solo_acepta_leer_y_crear(org_a, cliente_a):
    """
    El POST dejó de ser 405 cuando la ruta ganó la creación de planes. Los
    otros tres siguen fuera: editar o borrar un plan por la API no existe --
    lo que cambia su estado son las transiciones (publicar, cerrar), cada una
    con su regla y su actor.
    """
    plan = _plan(org_a)

    for metodo, llamada in (
            ("PUT", cliente_a.put(RUTA, {}, format="json")),
            ("PATCH", cliente_a.patch(RUTA, {}, format="json")),
            ("DELETE", cliente_a.delete(RUTA))):
        assert llamada.status_code == 405, metodo

    assert ProgramacionSemanal.objects.filter(pk=plan.pk).exists()
