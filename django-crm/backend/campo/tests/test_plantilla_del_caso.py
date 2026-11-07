# -*- coding: utf-8 -*-
"""
================================================================================
 LA PLANTILLA DE UN CASO: UNA SOLA REGLA  --  21/10/2026
================================================================================

`campo.plantillas.plantilla_del_caso` decide con que plantilla sale un caso,
para Despacho y para el Supervisor cuando cree la orden solo. Fichas:
labores-propias-por-empresa (D9-D10, criterios 2.10-2.13) y
supervisor-arma-la-jornada (Fase 2.0). Orden D3: medido > asunto > grupo.

  A  el asunto elige, escrito de cualquier forma, aunque la labor del caso
     sea otra (el asunto le gana al grupo)
  B  la labor MEDIDA le gana al asunto: elige la unica de su labor
  C  sin asunto que marque: la UNICA plantilla de la labor
  D  sin una sola respuesta, NINGUNA, con su motivo: labor sin plantilla,
     varias sin el asunto, sin labor
  E  nunca una apagada ni una de otra empresa
  F  la ficha de Despacho devuelve lo mismo, con como y por que

    pytest campo/tests/test_plantilla_del_caso.py
================================================================================
"""

from unittest import mock

import pytest

from campo import plantillas as P
from campo.models import WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db


def _plantilla(org, codigo, labor, asuntos=()):
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo.title(),
                                   labor=labor, asuntos=list(asuntos))
    return WorkTypeVersion.objects.create(
        work_type=tipo, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [{"id": "foto", "tipo": "foto"}]})


# ---------------------------------------------------------------------------
# A · el asunto elige
# ---------------------------------------------------------------------------

def test_a_el_asunto_elige_escrito_de_cualquier_forma(org_a):
    _plantilla(org_a, "correctivo_fibra", "correctivo", ["Internet Lento"])
    traslado = _plantilla(org_a, "traslado", "correctivo", ["Cambio De Domicilio"])
    r = P.plantilla_del_caso(org_a, labor="correctivo",
                             asunto="  cambio de DOMICÍLIO ")
    assert r["version"] == traslado
    assert r["por"] == "asunto" and r["motivo"] == ""


def test_a2_el_asunto_le_gana_al_grupo(org_a):
    """Un retiro: el grupo dice «trabajo pedido» -> correctivo, pero el asunto
    es de la plantilla de retiro (trabajos). Lo dice el texto del proveedor."""
    _plantilla(org_a, "correctivo_fibra", "correctivo")
    retiro = _plantilla(org_a, "retiro", "trabajos", ["Retiro De Servicio"])
    r = P.plantilla_del_caso(org_a, labor="correctivo", asunto="Retiro De Servicio")
    assert r["version"] == retiro and r["por"] == "asunto"


# ---------------------------------------------------------------------------
# B · lo medido le gana al asunto
# ---------------------------------------------------------------------------

def test_b_la_labor_medida_le_gana_al_asunto(org_a):
    """Un ticket colgado del cliente de instalaciones es instalacion, diga lo
    que diga el asunto (D8)."""
    instalacion = _plantilla(org_a, "instalacion", "instalacion")
    _plantilla(org_a, "traslado", "correctivo", ["Cambio De Domicilio"])
    r = P.plantilla_del_caso(org_a, labor="instalacion",
                             asunto="Cambio De Domicilio", labor_medida=True)
    assert r["version"] == instalacion and r["por"] == "labor"


# ---------------------------------------------------------------------------
# C · la unica de la labor
# ---------------------------------------------------------------------------

def test_c_sin_asunto_que_marque_la_unica_de_la_labor(org_a):
    unica = _plantilla(org_a, "correctivo_fibra", "correctivo")
    _plantilla(org_a, "retiro", "trabajos")
    r = P.plantilla_del_caso(org_a, labor="correctivo", asunto="Algo Nuevo")
    assert r["version"] == unica and r["por"] == "labor"


# ---------------------------------------------------------------------------
# D · sin una sola respuesta, ninguna
# ---------------------------------------------------------------------------

def test_d_varias_en_la_labor_y_ninguna_tiene_el_asunto(org_a):
    _plantilla(org_a, "correctivo_fibra", "correctivo", ["Internet Lento"])
    _plantilla(org_a, "tv", "correctivo", ["Problemas De Tv"])
    r = P.plantilla_del_caso(org_a, labor="correctivo", asunto="Algo Nuevo")
    assert r["version"] is None
    assert r["motivo"] == P.VARIAS_SIN_ASUNTO
    assert "2 plantillas" in r["detalle"]


def test_d2_la_labor_no_tiene_plantilla(org_a):
    _plantilla(org_a, "correctivo_fibra", "correctivo")
    r = P.plantilla_del_caso(org_a, labor="instalacion", asunto="Algo Nuevo")
    assert r["version"] is None and r["motivo"] == P.LABOR_SIN_PLANTILLA


def test_d3_sin_labor_y_sin_asunto_que_marque(org_a):
    _plantilla(org_a, "correctivo_fibra", "correctivo")
    r = P.plantilla_del_caso(org_a, labor="", asunto="Algo Nuevo")
    assert r["version"] is None and r["motivo"] == P.SIN_LABOR


def test_d4_la_medida_sin_plantilla_no_cae_al_asunto(org_a):
    """Medido instalacion, sin plantilla de instalacion: NO se usa la del
    asunto (es de otra labor). Ninguna, con motivo."""
    _plantilla(org_a, "traslado", "correctivo", ["Cambio De Domicilio"])
    r = P.plantilla_del_caso(org_a, labor="instalacion",
                             asunto="Cambio De Domicilio", labor_medida=True)
    assert r["version"] is None and r["motivo"] == P.LABOR_SIN_PLANTILLA


# ---------------------------------------------------------------------------
# E · nunca apagada ni de otra empresa
# ---------------------------------------------------------------------------

def test_e_nunca_una_apagada(org_a):
    v = _plantilla(org_a, "traslado", "correctivo", ["Cambio De Domicilio"])
    WorkType.objects.filter(pk=v.work_type_id).update(activo=False)
    r = P.plantilla_del_caso(org_a, labor="correctivo", asunto="Cambio De Domicilio")
    assert r["version"] is None


def test_e2_nunca_una_de_otra_empresa(org_a, org_b):
    _plantilla(org_b, "traslado", "correctivo", ["Cambio De Domicilio"])
    r = P.plantilla_del_caso(org_a, labor="correctivo", asunto="Cambio De Domicilio")
    assert r["version"] is None


# ---------------------------------------------------------------------------
# F · la ficha de Despacho usa la misma regla
# ---------------------------------------------------------------------------

def _caso_en_despacho(org, asunto):
    from cases.models import Case
    from operaciones.models import PropuestaSupervisor
    caso = Case.objects.create(org=org, name=asunto, status="New",
                               priority="Normal", is_active=True)
    PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=PropuestaSupervisor.ACEPTADA, accion_propuesta="x", motivo="x",
        evidencia=[{"fuente": "lectura_ticket", "dato": "x",
                    "momento": "2026-10-21T03:00:00Z"}])
    return caso


@pytest.fixture
def sugiere_correctivo():
    with mock.patch(
            "campo.despacho_pantalla_views.CasosDespachablesView._sugerencia_de",
            return_value={"labor": "correctivo", "verificada": False,
                          "fuente": "", "porque": ""}), \
         mock.patch("campo.services.despacho.contexto_del_caso",
                    return_value={"cliente": {}}):
        yield


def test_f_la_ficha_elige_por_la_labor_y_lo_dice(admin_client, org_a,
                                                 sugiere_correctivo):
    unica = _plantilla(org_a, "correctivo_fibra", "correctivo")
    caso = _caso_en_despacho(org_a, "Algo Nuevo")
    d = admin_client.get(f"/api/campo/casos-despachables/{caso.id}/ficha/").json()
    assert d["plantilla_sugerida"] == str(unica.id)
    assert d["plantilla_por"] == "labor"


def test_f2_sin_respuesta_la_ficha_dice_por_que(admin_client, org_a,
                                               sugiere_correctivo):
    _plantilla(org_a, "correctivo_fibra", "correctivo")
    _plantilla(org_a, "tv", "correctivo")
    caso = _caso_en_despacho(org_a, "Algo Nuevo")
    d = admin_client.get(f"/api/campo/casos-despachables/{caso.id}/ficha/").json()
    assert d["plantilla_sugerida"] is None
    assert "2 plantillas" in d["plantilla_motivo"]
