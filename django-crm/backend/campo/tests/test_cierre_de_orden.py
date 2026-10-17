# -*- coding: utf-8 -*-
"""
================================================================================
 EL ÚLTIMO PASO DEL RECORRIDO, QUE NO TENÍA PUERTA
================================================================================

El flujo declarado es: caso → programación → ejecución → evidencia →
validación → **cierre**. Los cinco primeros tenían ruta; el sexto no.

'transiciones.cerrar_orden' estaba escrita, la máquina de estados declaraba
'completada_campo → cerrada', y **ninguna vista, servicio ni comando la
llamaba** — se comprobó buscando en todo el repositorio. El efecto medible:
una orden aprobada se quedaba en 'completada_campo' para siempre, y el
recorrido no terminaba nunca.

Lo que se afirma aquí es el EFECTO: que una orden aprobada llega a 'cerrada'
con su fecha y su evento, que una sin aprobar NO llega, y que cerrar no toca
ningún sistema externo.
================================================================================
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from conftest import rls_org

pytestmark = pytest.mark.django_db


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
    return _perfil(org_a, "jefe@cierre.test")


@pytest.fixture
def cliente(org_a, gestor):
    return _cliente(gestor[0], org_a, gestor[1])


def _orden(org, numero=9500, *, estado=OrdenTrabajo.COMPLETADA_CAMPO,
           validacion=OrdenTrabajo.APROBADO):
    wt = WorkType.objects.create(org=org, codigo=f"cie{numero}", nombre="Tipo cierre")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"campos": [], "evidencias": []})
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Cliente cierre", cliente_direccion="Calle 1",
        estado_operativo=estado, estado_validacion=validacion)


def _url(orden):
    return f"/api/campo/trabajos/{orden.id}/cerrar/"


# =============================================================================
#  §1  El cierre ocurre de verdad
# =============================================================================

def test_una_orden_aprobada_se_cierra(org_a, cliente):
    orden = _orden(org_a)

    r = cliente.post(_url(orden), {}, format="json")

    assert r.status_code == 200
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CERRADA


def test_el_cierre_sella_la_fecha(org_a, cliente):
    """Sin fecha de cierre no se puede medir cuánto duró nada."""
    orden = _orden(org_a, numero=9501)
    assert orden.cerrada_en is None

    cliente.post(_url(orden), {}, format="json")

    orden.refresh_from_db()
    assert orden.cerrada_en is not None
    assert orden.cerrada_en <= timezone.now()


def test_el_cierre_queda_en_la_bitacora(org_a, cliente):
    orden = _orden(org_a, numero=9502)

    cliente.post(_url(orden), {"observacion": "conciliado con el cliente"}, format="json")

    evento = EventoTrabajo.objects.filter(orden=orden, tipo="orden_cerrada").first()
    assert evento is not None
    assert evento.profile is not None, "el cierre tiene que decir quién lo firmó"


# =============================================================================
#  §2  Lo que el cierre NO permite
# =============================================================================

def test_no_se_cierra_lo_que_nadie_valido(org_a, cliente):
    """
    Cerrar sin validar sacaría la orden de la bandeja del supervisor sin que
    nadie haya mirado la evidencia — justo lo que la validación existe para
    impedir.
    """
    orden = _orden(org_a, numero=9503, validacion=OrdenTrabajo.PENDIENTE)

    r = cliente.post(_url(orden), {}, format="json")

    assert r.status_code == 409
    assert r.json()["error"] == "SIN_VALIDAR"
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO


def test_no_se_cierra_una_orden_que_el_tecnico_todavia_tiene(org_a, cliente):
    """La máquina de estados manda: de 'en_sitio' no se salta al cierre."""
    orden = _orden(org_a, numero=9504, estado=OrdenTrabajo.EN_SITIO)

    r = cliente.post(_url(orden), {}, format="json")

    assert r.status_code == 400
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.EN_SITIO


def test_cerrar_dos_veces_no_deja_dos_cierres(org_a, cliente):
    """
    El segundo cierre es INOCUO, no un error: '_aplicar_transicion' devuelve la
    orden tal cual cuando ya está en el estado pedido. Un doble clic o un
    reintento no puede dejar dos cierres en la bitácora, y tampoco tiene por
    qué asustar a quien lo hizo con un 400.
    """
    orden = _orden(org_a, numero=9505)

    primera = cliente.post(_url(orden), {}, format="json")
    segunda = cliente.post(_url(orden), {}, format="json")

    assert primera.status_code == 200
    assert segunda.status_code == 200
    #  Lo que de verdad importa: un solo cierre registrado.
    assert EventoTrabajo.objects.filter(orden=orden, tipo="orden_cerrada").count() == 1
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CERRADA


# =============================================================================
#  §3  Permisos y aislamiento
# =============================================================================

def test_un_tecnico_no_cierra_su_propio_trabajo(org_a):
    """
    El mismo criterio que validar: quien ejecuta no se aprueba ni se cierra a
    sí mismo.
    """
    orden = _orden(org_a, numero=9506)
    u, p = _perfil(org_a, "tecnico@cierre.test", rol="USER")
    AsignacionTrabajo.objects.create(orden=orden, profile=p, rol="tecnico",
                                     es_principal=True)

    r = _cliente(u, org_a, p).post(_url(orden), {}, format="json")

    assert r.status_code == 403
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO


def test_no_se_cierra_una_orden_de_otra_empresa(org_a, org_b, cliente):
    with rls_org(org_b):
        ajena = _orden(org_b, numero=9507)

    r = cliente.post(_url(ajena), {}, format="json")

    #  404 y no 403: un 403 confirmaría que esa orden existe.
    assert r.status_code == 404
    ajena.refresh_from_db()
    assert ajena.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO


# =============================================================================
#  §4  Cerrar no ejecuta nada
# =============================================================================

def test_cerrar_no_llama_a_ningun_sistema_externo(org_a, cliente, monkeypatch):
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

    orden = _orden(org_a, numero=9508)
    assert cliente.post(_url(orden), {}, format="json").status_code == 200

    assert llamadas == []
