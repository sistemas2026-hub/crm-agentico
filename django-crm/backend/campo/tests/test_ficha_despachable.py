# -*- coding: utf-8 -*-
"""
================================================================================
 AL DESPACHAR UN CASO, LO QUE EL SISTEMA YA SABE VIENE CARGADO
================================================================================

Pedido del usuario (13/10/2026): al despachar habia que escribir el barrio, como
se entra y que hay que hacer, con el barrio en la ficha del ISP y la lectura del
Supervisor ya hecha. `GET /campo/casos-despachables/<id>/ficha/` trae, para UN
caso aprobado:

  A  el barrio de la ficha del cliente (lo que el reparto mapea a una zona)
  B  la lectura del Supervisor de la propuesta ACEPTADA: hipotesis y
     recomendacion
  C  la descripcion del ticket TAPADA -- como se entra no se extrae solo
  D  un caso no aprobado, o de otra empresa, no existe (404)

La ficha del motor se sustituye: es la unica pieza externa.

    pytest campo/tests/test_ficha_despachable.py
================================================================================
"""

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db


def _ruta(caso):
    return f"/api/campo/casos-despachables/{caso.id}/ficha/"


def _caso(org, **extra):
    from cases.models import Case

    campos = {"org": org, "name": "Internet intermitente", "status": "New",
              "priority": "Normal", "is_active": True,
              "description": ("Cliente reporta cortes. Vive en el apto 302, la "
                              "porteria pide cedula 1045678901, llamar al "
                              "300 123 4567 antes de ir.")}
    campos.update(extra)
    return Case.objects.create(**campos)


def _propuesta(org, caso, estado=None):
    from operaciones.diagnostico_de_ticket import ETIQUETA_LECTURA
    from operaciones.models import PropuestaSupervisor

    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=estado or PropuestaSupervisor.ACEPTADA,
        accion_propuesta="Revisar el conector de la roseta",
        motivo="Revisar el conector de la roseta. Puede ser la acometida.",
        evidencia=[{"fuente": "lectura_ticket", "dato": f"{ETIQUETA_LECTURA}"
                    "probable conector dañado (confianza media)",
                    "momento": "2026-10-13T03:00:00Z"}])


@pytest.fixture
def ficha_del_motor():
    contexto = {"cliente": {"localidad": "MARTHA GISELA", "nombre": "X"}}
    with mock.patch("campo.services.despacho.contexto_del_caso",
                    return_value=contexto):
        yield


def test_a_b_c_trae_barrio_lectura_y_descripcion_tapada(
        admin_client, org_a, ficha_del_motor):
    caso = _caso(org_a)
    _propuesta(org_a, caso)

    r = admin_client.get(_ruta(caso))
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["localidad"] == "MARTHA GISELA"                         # A
    assert d["lectura"]["hipotesis"] == "probable conector dañado (confianza media)"
    assert d["lectura"]["recomendacion"] == "Revisar el conector de la roseta"  # B
    assert "apto 302" in d["descripcion"]                            # C: lo util
    assert "1045678901" not in d["descripcion"]                      # C: tapado
    assert "300 123 4567" not in d["descripcion"]


def test_d_un_caso_sin_propuesta_aceptada_no_existe(admin_client, org_a,
                                                    ficha_del_motor):
    from operaciones.models import PropuestaSupervisor

    caso = _caso(org_a)
    _propuesta(org_a, caso, estado=PropuestaSupervisor.RECHAZADA)
    assert admin_client.get(_ruta(caso)).status_code == 404
    otro = _caso(org_a)
    assert admin_client.get(_ruta(otro)).status_code == 404


def test_d2_un_caso_de_otra_empresa_no_existe(admin_client, org_a, org_b,
                                              ficha_del_motor):
    """El caso existe y esta aprobado, pero en OTRA empresa. Se crea con el
    contexto RLS de esa empresa -- sin eso la base ni siquiera deja crearlo --
    y se vuelve al de la sesion antes de pedirlo."""
    from conftest import set_rls_context

    set_rls_context(org_b)
    caso = _caso(org_b)
    _propuesta(org_b, caso)
    set_rls_context(org_a)
    assert admin_client.get(_ruta(caso)).status_code == 404


def test_e_si_el_motor_no_responde_la_ficha_sale_igual_sin_barrio(
        admin_client, org_a):
    caso = _caso(org_a)
    _propuesta(org_a, caso)
    with mock.patch("campo.services.despacho.contexto_del_caso",
                    side_effect=RuntimeError("motor caido")):
        r = admin_client.get(_ruta(caso))
    assert r.status_code == 200, r.content
    assert r.json()["localidad"] == ""
    assert r.json()["lectura"]["recomendacion"]       # lo que vive en el CRM llega
