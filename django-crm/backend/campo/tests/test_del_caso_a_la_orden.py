# -*- coding: utf-8 -*-
"""
================================================================================
 DEL CASO A LA ORDEN: UNA SOLA TRADUCCION  --  21/10/2026
================================================================================

Fase 2.1 de SPEC/objetivos/supervisor-arma-la-jornada.md: lo que la vista de
«Despachar» hacia adentro, extraido a funciones para que el Supervisor (2.3)
traduzca el caso EXACTAMENTE como el boton. Sin cambio de conducta: las
pruebas de la vista (test_despacho_api, test_crear_orden_textos_largos, ...)
siguen afirmando lo de siempre; estas afirman las piezas.

  A  `ordenes_vivas_del_caso`: ni cerradas ni canceladas, solo del CRM, solo
     de esa empresa
  B  `cliente_para_la_orden`: lo escrito gana; si no, la ficha, recortada al
     largo de la columna; el telefono va con sus comas
  C  `anotar_labor_sugerida`: solo con ficha; nunca levanta

    pytest campo/tests/test_del_caso_a_la_orden.py
================================================================================
"""

from unittest import mock

import pytest

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import despacho as D

pytestmark = pytest.mark.django_db


def _orden(org, ref, estado=OrdenTrabajo.ASIGNADA, origen="crm"):
    tipo = WorkType.objects.get_or_create(org=org, codigo="t", defaults={
        "nombre": "T", "labor": "correctivo"})[0]
    v = WorkTypeVersion.objects.get_or_create(
        work_type=tipo, version=1, defaults={
            "estado": WorkTypeVersion.PUBLICADA,
            "esquema": {"campos": [{"id": "x", "tipo": "texto"}]}})[0]
    o = D.crear_orden(org=org, profile=None, version=v,
                      cliente={"nombre": "Cliente"}, origen_sistema=origen,
                      origen_ref=ref)
    OrdenTrabajo.objects.filter(pk=o.pk).update(estado_operativo=estado)
    return o


# ---------------------------------------------------------------------------
# A · las ordenes vivas
# ---------------------------------------------------------------------------

def test_a_ni_cerradas_ni_canceladas_ni_de_otro_origen(org_a):
    viva = _orden(org_a, "caso-1")
    _orden(org_a, "caso-1", estado=OrdenTrabajo.CERRADA)
    _orden(org_a, "caso-1", estado=OrdenTrabajo.CANCELADA)
    _orden(org_a, "caso-1", origen="manual")
    _orden(org_a, "caso-2")
    assert list(D.ordenes_vivas_del_caso(org_a, "caso-1")) == [viva]


def test_a2_otra_empresa_no(org_a, org_b):
    _orden(org_a, "caso-1")
    assert not D.ordenes_vivas_del_caso(org_b, "caso-1").exists()


# ---------------------------------------------------------------------------
# B · el cliente
# ---------------------------------------------------------------------------

FICHA = {"servicio": 4986, "contexto_disponible": True,
         "cliente": {"nombre": "Ana", "telefono": "300 111 2222, 301 333 4444",
                     "direccion": "Calle " + "x" * 300}}


def test_b_sin_lo_escrito_va_la_ficha_recortada(org_a):
    c = D.cliente_para_la_orden(FICHA)
    assert c["nombre"] == "Ana"
    assert c["telefono"] == "300 111 2222, 301 333 4444"
    assert len(c["direccion"]) == 255
    assert c["id_abonado"] == "4986"


def test_b2_lo_escrito_gana(org_a):
    c = D.cliente_para_la_orden(FICHA, {"cliente_nombre": "Ana María",
                                        "cliente_direccion": "Cra 1",
                                        "cliente_detalle_acceso": "Apto 302"})
    assert (c["nombre"], c["direccion"], c["detalle_acceso"]) == (
        "Ana María", "Cra 1", "Apto 302")


def test_b3_sin_ficha_queda_vacio_y_no_rompe(org_a):
    c = D.cliente_para_la_orden({"contexto_disponible": False})
    assert c["nombre"] == c["telefono"] == c["direccion"] == c["id_abonado"] == ""


# ---------------------------------------------------------------------------
# C · la labor sugerida
# ---------------------------------------------------------------------------

def test_c_solo_con_ficha():
    sin = {"contexto_disponible": False}
    D.anotar_labor_sugerida(sin, "Internet lento")
    assert "labor_sugerida" not in sin

    con = dict(FICHA)
    with mock.patch("operaciones.clasificacion_de_trabajo.clasificar",
                    return_value={"labor": "correctivo"}) as clasificar:
        D.anotar_labor_sugerida(con, "  Internet lento ")
    assert con["labor_sugerida"] == {"labor": "correctivo"}
    assert clasificar.call_args.kwargs["texto"] == "Internet lento"


def test_c2_si_clasificar_falla_no_levanta():
    con = dict(FICHA)
    with mock.patch("operaciones.clasificacion_de_trabajo.clasificar",
                    side_effect=RuntimeError("x")):
        D.anotar_labor_sugerida(con, "x")
    assert "labor_sugerida" not in con
