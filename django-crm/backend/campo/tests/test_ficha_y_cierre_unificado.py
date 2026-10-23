# -*- coding: utf-8 -*-
"""
================================================================================
 LA FICHA DEL EQUIPO SE PUEDE VOLVER A PEDIR, Y EL CIERRE ES UNO SOLO
================================================================================

Tanda 2 de la app de campo (17/10/2026).

  A  la ficha del equipo se vuelve a pedir desde el teléfono. Hasta acá, si el
     motor no contestaba al crear la orden, la orden quedaba SIN niveles y SIN
     serial para siempre -- y sin serial tampoco se puede «Volver a medir». La
     app prometía «Se reintenta al sincronizar», y `refrescar_contexto` no
     tenía ningún llamador.
  B  un refresco que falla no borra la ficha que había
  C  el permiso es el de la orden: otro técnico de la empresa no puede
  D  «no usé materiales» queda en el reporte de cierre como dato de
     plataforma, y la bitácora lo muestra; ausente no quiere decir «sí usó»

    pytest campo/tests/test_ficha_y_cierre_unificado.py
================================================================================
"""

from unittest import mock

import pytest
from rest_framework.test import APIClient

from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.services import seguimiento_campo as seg
from common.models import Profile
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db

FICHA = {
    "contexto_disponible": True,
    "capturado_en": "2026-10-17T15:00:00+00:00",
    "fuente": "motor/contexto_tecnico",
    "servicio": "WH-1",
    "sn_onu": "ZTEGC0A1B2C3",
    "equipo": {"onu_status": "Online", "onu_signal_1490": "-21.19 dBm",
               "onu_signal_1490_veredicto": "aceptable"},
}
SIN_FICHA = {"contexto_disponible": False, "motivo": "ReadTimeout",
             "motor_alcanzado": False}


def _cliente(user, org, profile):
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    return c


@pytest.fixture
def tecnico(org_a, django_user_model):
    u = django_user_model.objects.create_user(email="t.ficha@test.com", password="x")
    return u, Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)


@pytest.fixture
def otro(org_a, django_user_model):
    u = django_user_model.objects.create_user(email="o.ficha@test.com", password="x")
    return u, Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)


@pytest.fixture
def orden(org_a, tecnico):
    wt = WorkType.objects.create(org=org_a, codigo="corr", nombre="Correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=9401, tipo_trabajo_version=v,
        cliente_nombre="Cliente", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
        origen_sistema="crm", origen_ref="11111111-1111-1111-1111-111111111111",
        contexto=dict(SIN_FICHA))
    AsignacionTrabajo.objects.create(orden=o, profile=tecnico[1],
                                     rol="tecnico_lider", es_principal=True)
    return o


def _ruta(o):
    return f"/api/campo/trabajos/{o.id}/ficha/refrescar/"


def test_a_la_ficha_que_falto_se_vuelve_a_pedir_y_trae_el_serial(orden, tecnico, org_a):
    c = _cliente(tecnico[0], org_a, tecnico[1])
    with mock.patch("campo.services.despacho.contexto_del_caso", return_value=dict(FICHA)):
        r = c.post(_ruta(orden), {}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["ok"] is True
    orden.refresh_from_db()
    assert orden.contexto["sn_onu"] == "ZTEGC0A1B2C3"
    assert orden.contexto["equipo"]["onu_signal_1490"] == "-21.19 dBm"
    # La orden actualizada viaja en la respuesta: el teléfono la guarda sin
    # esperar a otra sincronización.
    assert r.json()["orden"]["id"] == str(orden.id)
    # Y la ficha anterior queda en la bitácora.
    assert EventoTrabajo.objects.filter(orden=orden, tipo="contexto_refrescado").exists()


def test_b_un_refresco_que_falla_no_borra_la_ficha_que_habia(orden, tecnico, org_a):
    orden.contexto = dict(FICHA)
    orden.save(update_fields=["contexto"])
    c = _cliente(tecnico[0], org_a, tecnico[1])
    with mock.patch("campo.services.despacho.contexto_del_caso", return_value=dict(SIN_FICHA)):
        r = c.post(_ruta(orden), {}, format="json")
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["motor_alcanzado"] is False
    orden.refresh_from_db()
    assert orden.contexto["sn_onu"] == "ZTEGC0A1B2C3"


def test_c_otro_tecnico_no_puede_y_otra_empresa_tampoco(orden, otro, org_a, org_b_client):
    with mock.patch("campo.services.despacho.contexto_del_caso",
                    return_value=dict(FICHA)) as llamado:
        assert _cliente(otro[0], org_a, otro[1]).post(_ruta(orden), {}, format="json").status_code == 404
        assert org_b_client.post(_ruta(orden), {}, format="json").status_code == 404
    llamado.assert_not_called()


def test_c2_una_orden_cerrada_no_se_refresca(orden, tecnico, org_a):
    orden.estado_operativo = OrdenTrabajo.CERRADA
    orden.save(update_fields=["estado_operativo"])
    r = _cliente(tecnico[0], org_a, tecnico[1]).post(_ruta(orden), {}, format="json")
    assert r.status_code == 409


def test_d_no_use_materiales_queda_en_el_cierre_y_en_la_bitacora(orden, tecnico, org_a):
    c = _cliente(tecnico[0], org_a, tecnico[1])
    r = c.post(f"/api/campo/trabajos/{orden.id}/seguimiento/",
               {"momento": "cierre",
                "respuestas": {"solucion": "Se cambió el conector",
                               "servicio_validado": True},
                "sin_material_confirmado": True},
               format="json", HTTP_IDEMPOTENCY_KEY="cierre-1")
    assert r.status_code == 201, r.content
    ev = EventoTrabajo.objects.get(id=r.json()["id"])
    assert ev.datos["sin_material_confirmado"] is True

    fila = next(e for e in seg.linea_de_tiempo(orden)["eventos"] if e["id"] == str(ev.id))
    assert fila["sin_material_confirmado"] is True


def test_d2_sin_la_confirmacion_no_se_afirma_nada(orden, tecnico, org_a):
    ev = seg.registrar(orden, profile=tecnico[1], momento=seg.CIERRE,
                       respuestas={"solucion": "Se cambió el conector",
                                   "servicio_validado": True})
    assert "sin_material_confirmado" not in ev.datos
    # Y un avance no lo guarda aunque llegue: solo vale en el cierre.
    av = seg.registrar(orden, profile=tecnico[1], momento=seg.AVANCE,
                       respuestas={"nota": "sigo"}, sin_material_confirmado=True)
    assert "sin_material_confirmado" not in av.datos
