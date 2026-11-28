# -*- coding: utf-8 -*-
"""
================================================================================
 «HECHO · DESHACER»: lo que el Supervisor hizo solo se ve, y se revierte
 donde el backend sabe hacerlo  --  12/11/2026
================================================================================

Por la API de verdad ('/api/operaciones/actividad-supervisor/'), que es lo que
lee la capa servidor del frontend: el pase a Despacho que el Supervisor hizo
SOLO aparece como hecho deshacible, deshacerlo saca el caso de la cola con el
nombre y el motivo de la persona, y lo que no se puede deshacer lo dice con su
porque y contesta 409 si igual se intenta.
================================================================================
"""

import pytest

from common.models import Activity
from operaciones import auditoria, deshacer
from operaciones import paso_a_despacho as pad
from operaciones.models import PropuestaSupervisor as P
from operaciones.tests import test_el_supervisor_crea_las_ordenes as _base
from operaciones.tests.test_lo_no_critico_nace_delegado import (_falla,
                                                                _pasar,
                                                                interruptor)

pytestmark = pytest.mark.django_db
empresa = _base.empresa
plantillas = _base.plantillas
#  Re-exportado para que pytest lo encuentre en este modulo.
interruptor = interruptor

ACTIVIDAD = "/api/operaciones/actividad-supervisor/"


def _pase_hecho_solo(org):
    """Un pase a Despacho que el Supervisor hizo SOLO, por el camino real."""
    p = _falla(org)
    _pasar(org)
    p.refresh_from_db()
    assert p.estado == P.ACEPTADA
    fila = Activity.objects.get(org=org, entity_id=p.id, action="APPROVED")
    assert fila.user_id is None
    return p, fila


def _fila_del_feed(admin_client, actividad_id):
    cuerpo = admin_client.get(ACTIVIDAD, {"limite": 50}).json()
    return next(r for r in cuerpo["resultados"] if r["id"] == str(actividad_id))


def test_el_pase_hecho_solo_se_ve_como_hecho_deshacible(admin_client, org_a,
                                                        interruptor):
    _, fila = _pase_hecho_solo(org_a)

    r = _fila_del_feed(admin_client, fila.id)

    assert r["hecho_solo"] == {"tipo": deshacer.PASE_A_DESPACHO,
                               "se_puede": True, "por_que_no": ""}


def test_deshacerlo_saca_el_caso_de_despacho_con_quien_y_por_que(
        admin_client, admin_profile, org_a, interruptor):
    p, fila = _pase_hecho_solo(org_a)
    caso = p.origen_id
    assert pad.casos_en_despacho(org_a).filter(id=caso).exists()

    resp = admin_client.post(f"{ACTIVIDAD}{fila.id}/deshacer/",
                             {"motivo": "lo atiendo por telefono"},
                             format="json")

    assert resp.status_code == 200, resp.content
    p.refresh_from_db()
    assert p.estado == P.RECHAZADA
    assert p.revisado_por_id == admin_profile.id
    assert not pad.casos_en_despacho(org_a).filter(id=caso).exists()
    rastro = Activity.objects.get(org=org_a, entity_id=p.id, action="REJECTED")
    assert rastro.user_id == admin_profile.id
    assert rastro.metadata["deshace"] == str(fila.id)
    assert rastro.description == "lo atiendo por telefono"


def test_el_supervisor_no_lo_vuelve_a_pasar_en_la_vuelta_siguiente(
        admin_client, org_a, interruptor):
    """Rechazada y no devuelta a PROPUESTA: en PROPUESTA, el mismo ciclo la
    pasaria otra vez en una hora."""
    p, fila = _pase_hecho_solo(org_a)
    admin_client.post(f"{ACTIVIDAD}{fila.id}/deshacer/", {"motivo": "no"},
                      format="json")

    _pasar(org_a)

    p.refresh_from_db()
    assert p.estado == P.RECHAZADA


def test_con_orden_ya_creada_no_se_deshace_y_dice_donde(
        admin_client, org_a, plantillas, interruptor):
    from campo.models import OrdenTrabajo

    p, fila = _pase_hecho_solo(org_a)
    OrdenTrabajo.objects.create(
        org=org_a, numero=901, tipo_trabajo_version=plantillas["soporte"],
        origen_sistema="crm", origen_ref=str(p.origen_id))

    resp = admin_client.post(f"{ACTIVIDAD}{fila.id}/deshacer/",
                             {"motivo": "x"}, format="json")

    assert resp.status_code == 409
    assert resp.json()["error"] == "YA_TIENE_ORDEN"
    p.refresh_from_db()
    assert p.estado == P.ACEPTADA


def test_sin_motivo_no_se_deshace(admin_client, org_a, interruptor):
    p, fila = _pase_hecho_solo(org_a)

    resp = admin_client.post(f"{ACTIVIDAD}{fila.id}/deshacer/", {},
                             format="json")

    assert resp.status_code == 400
    p.refresh_from_db()
    assert p.estado == P.ACEPTADA


def test_un_cierre_de_caso_es_hecho_sin_boton_y_con_el_porque(admin_client,
                                                              org_a):
    fila = auditoria.registrar(
        org=org_a, actor=None, accion="STATUS_CHANGED",
        entidad=auditoria.ENTIDAD_CASO, entidad_id=org_a.id, nombre="Caso")

    r = _fila_del_feed(admin_client, fila.id)
    assert r["hecho_solo"]["se_puede"] is False
    assert "sistema del ISP" in r["hecho_solo"]["por_que_no"]

    resp = admin_client.post(f"{ACTIVIDAD}{fila.id}/deshacer/",
                             {"motivo": "x"}, format="json")
    assert resp.status_code == 409


def test_la_jornada_armada_sola_ahora_sale_en_el_feed(admin_client, org_a):
    fila = auditoria.registrar(
        org=org_a, actor=None, accion="CREATE",
        entidad=auditoria.ENTIDAD_JORNADA, entidad_id=org_a.id,
        nombre="Cuadrilla 1 · 2026-11-12")

    r = _fila_del_feed(admin_client, fila.id)
    assert r["hecho_solo"]["tipo"] == "jornada"
    assert r["hecho_solo"]["se_puede"] is False


def test_lo_que_hizo_una_persona_o_una_propuesta_no_es_un_hecho_solo(
        admin_client, admin_profile, org_a):
    de_persona = auditoria.registrar(
        org=org_a, actor=admin_profile, accion="APPROVED",
        entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=org_a.id,
        extra={"tarea": auditoria.TAREA_PASO_A_DESPACHO})
    propuesta = auditoria.registrar(
        org=org_a, actor=None, accion="CREATE",
        entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=org_a.id)

    assert _fila_del_feed(admin_client, de_persona.id)["hecho_solo"] is None
    assert _fila_del_feed(admin_client, propuesta.id)["hecho_solo"] is None
    resp = admin_client.post(f"{ACTIVIDAD}{de_persona.id}/deshacer/",
                             {"motivo": "x"}, format="json")
    assert resp.status_code == 409


def test_el_hecho_de_otra_empresa_no_se_deshace(org_a, org_b_client,
                                                interruptor):
    """Un ADMIN de OTRA empresa, con el id del hecho en la mano, no lo
    deshace: 'deshacer' busca la fila filtrando por la empresa del pedido."""
    p, fila = _pase_hecho_solo(org_a)

    resp = org_b_client.post(f"{ACTIVIDAD}{fila.id}/deshacer/",
                             {"motivo": "x"}, format="json")

    assert resp.status_code == 409
    p.refresh_from_db()
    assert p.estado == P.ACEPTADA
