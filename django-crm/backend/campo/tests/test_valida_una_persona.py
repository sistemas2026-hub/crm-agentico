# -*- coding: utf-8 -*-
"""SI LA ORDEN LA VALIDA UNA PERSONA LO DICE EL SERVIDOR  --  27/11/2026.

El usuario: «el tecnico termina y debe haber un boton de mandar a validar,
pasar a validacion, y si confirman que esta bien finaliza el trabajo».

La app lo adivinaba por el CODIGO de la plantilla («contiene instalacion») y en
produccion la de instalaciones se llama `traslado_servicio`: en la OT-501 el
tecnico nunca vio el boton para entregar y el ticket no se cerro. Ahora el
detalle de la orden trae `tipo.valida_una_persona`.

  A  EL DETALLE -- con el codigo de produccion, ANTES de firmar el contrato
     (la app lo usa para nombrar el boton del final).
  B  LOS CONTROLES -- empresa sin la validacion; un trabajo que no es
     instalacion (salvo que ya tenga contrato).
  C  EL AVISO -- al aprobar, el telefono nombra el boton que hay que tocar.
"""
import pytest

from campo.contrato import ContratoDeServicio
from campo.models import OrdenTrabajo, WorkType
from campo.serializers import OrdenTrabajoDetailSerializer
from campo.services import avisos as A
from campo.tests.test_instalacion_validada import _contrato, config, orden, version  # noqa: F401

pytestmark = pytest.mark.django_db


def _tipo(orden):
    return OrdenTrabajoDetailSerializer(orden).data["tipo"]


# --------------------------------------------------------------------------- #
#  A. EL DETALLE
# --------------------------------------------------------------------------- #
def test_a1_con_el_codigo_de_produccion_y_SIN_contrato_todavia(user_client, orden, config):
    WorkType.objects.filter(pk=orden.tipo_trabajo_version.work_type_id).update(
        codigo="traslado_servicio")
    r = user_client.get(f"/api/campo/trabajos/{orden.id}/")
    assert r.status_code == 200, r.content
    tipo = r.json()["tipo"]
    assert tipo["codigo"] == "traslado_servicio" and tipo["labor"] == "instalacion"
    assert tipo["valida_una_persona"] is True, "la OT-501: el código no dice «instalacion»"


# --------------------------------------------------------------------------- #
#  B. LOS CONTROLES
# --------------------------------------------------------------------------- #
def test_b1_una_empresa_SIN_la_validacion_finaliza_como_siempre(orden, config):
    config.validar_antes_de_activar = False
    config.save()
    assert _tipo(orden)["valida_una_persona"] is False


def test_b2_un_trabajo_que_no_es_instalacion_no_va_a_validacion(orden, config, user_profile):
    WorkType.objects.filter(pk=orden.tipo_trabajo_version.work_type_id).update(labor="correctivo")
    orden.refresh_from_db()
    assert _tipo(orden)["valida_una_persona"] is False
    #  ...salvo que ya tenga un contrato firmado: entonces es una instalacion
    #  aunque la plantilla diga otra cosa, y la entrega la va a pedir.
    _contrato(orden, user_profile, estado=ContratoDeServicio.FIRMADO)
    assert _tipo(orden)["valida_una_persona"] is True


def test_b3_si_no_se_puede_saber_NO_tumba_el_detalle(orden, config, monkeypatch):
    import campo.contrato as C

    def roto(_org):
        raise RuntimeError("la base no contesto")

    monkeypatch.setattr(C, "configuracion_de", roto)
    assert _tipo(orden)["valida_una_persona"] is False


# --------------------------------------------------------------------------- #
#  C. EL AVISO AL APROBAR
# --------------------------------------------------------------------------- #
def test_c1_el_aviso_nombra_el_boton_que_hay_que_tocar(orden, user_profile, monkeypatch):
    enviados = []
    monkeypatch.setattr(A, "_notificar", lambda *a, **k: {})
    monkeypatch.setattr(A, "_despachar", lambda **k: enviados.append(k))
    assert A.avisar_instalacion_aprobada(orden) is True
    assert "«Finalizar trabajo»" in enviados[0]["texto"], enviados[0]["texto"]
    assert OrdenTrabajo.objects.filter(pk=orden.pk).exists()
