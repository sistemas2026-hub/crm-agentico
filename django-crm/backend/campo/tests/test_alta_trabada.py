# -*- coding: utf-8 -*-
"""LA INSTALACION QUE NO QUEDO CREADA SE VE, AVISA Y SE DESTRABA  --  27/11/2026.

El usuario, despues de la OT-502: «cuando se vuelva a presentar, ¿toca volver a
ejecutar un comando? Que reporte este error y el encargado revise, y con un
boton permita volver a crear».

La OT-502 salio de un ticket: su contrato no tiene solicitud, y los botones
(«No quedo creado», «Volver a crear») vivian solo en la tarjeta de una
solicitud. Trabado, no habia como destrabarlo sin un comando.

  A  LA LISTA -- Instalaciones → Por activar trae TODOS los contratos firmados
     con el alta fallida o por revisar, con o sin solicitud.
  B  EL AVISO -- al ENTRAR a fallida o por revisar, una vez, sin datos del
     cliente; no cuando una persona dice «no quedo creado».
"""
import pytest

from campo.contrato import ContratoDeServicio
from campo.services import alta_en_el_isp, avisos
from campo.tests.test_instalacion_validada import _contrato, config, orden, version  # noqa: F401

pytestmark = pytest.mark.django_db

URL = "/api/campo/instalaciones/por-activar/"


# --------------------------------------------------------------------------- #
#  A. LA LISTA
# --------------------------------------------------------------------------- #
def test_a1_un_contrato_SIN_solicitud_y_por_revisar_aparece_con_lo_que_se_puede_hacer(
        admin_client, orden, user_profile, config):
    c = _contrato(orden, user_profile, alta_estado=ContratoDeServicio.ALTA_POR_REVISAR,
                  alta_codigo="sin_confirmar", alta_emitida=True)
    assert c.solicitud_id is None, "como la OT-502: sale del ticket"
    r = admin_client.get(URL)
    assert r.status_code == 200, r.content
    trabadas = r.json()["trabadas"]
    assert [t["contrato"]["numero"] for t in trabadas] == [c.numero]
    assert trabadas[0]["numero"] == orden.numero
    assert trabadas[0]["cliente"] == "LAURA GOMEZ"
    assert trabadas[0]["contrato"]["alta"]["por_revisar"] is True


def test_a2_una_FALLIDA_se_puede_volver_a_crear_y_una_ya_creada_no_aparece(
        admin_client, orden, user_profile, config):
    c = _contrato(orden, user_profile, alta_estado=ContratoDeServicio.ALTA_FALLIDA,
                  alta_codigo="rechazado_por_el_motor")
    trabadas = admin_client.get(URL).json()["trabadas"]
    assert trabadas[0]["contrato"]["alta"]["se_puede_pedir"] is True
    ContratoDeServicio.objects.filter(pk=c.pk).update(estado=ContratoDeServicio.EN_EL_ISP,
                                                      alta_estado="")
    assert admin_client.get(URL).json()["trabadas"] == []


def test_a3_un_tecnico_no_ve_la_lista(user_client, orden, user_profile, config):
    _contrato(orden, user_profile, alta_estado=ContratoDeServicio.ALTA_FALLIDA)
    assert user_client.get(URL).status_code == 403


# --------------------------------------------------------------------------- #
#  B. EL AVISO
# --------------------------------------------------------------------------- #
@pytest.fixture
def enviados(monkeypatch):
    lista = []
    monkeypatch.setattr(avisos, "_despachar", lambda **k: lista.append(k))
    return lista


def test_b1_al_quedar_POR_REVISAR_avisa_UNA_vez_y_sin_datos_del_cliente(
        orden, user_profile, config, enviados):
    c = _contrato(orden, user_profile, alta_estado=ContratoDeServicio.ALTA_PEDIDA,
                  alta_intento=1)
    alta_en_el_isp._por_revisar(c, alta_en_el_isp.SIN_CONFIRMAR)
    alta_en_el_isp._por_revisar(c, alta_en_el_isp.SIN_CONFIRMAR)    # otra vuelta igual
    assert len(enviados) == 1, "una vez: la segunda no cambia nada"
    texto = enviados[0]["texto"]
    assert f"OT #{orden.numero}" in texto and "Instalaciones → Por activar" in texto
    for dato in ("LAURA", "GOMEZ", "1043"):
        assert dato not in texto and dato not in enviados[0]["asunto"]
    assert enviados[0]["enlace_interno"] == "/instalaciones?vista=por_activar"


def test_b2_al_quedar_FALLIDA_avisa_y_el_no_quedo_creado_de_una_persona_no(
        orden, user_profile, config, enviados):
    c = _contrato(orden, user_profile, alta_estado=ContratoDeServicio.ALTA_PEDIDA)
    alta_en_el_isp._fallida(c, alta_en_el_isp.RECHAZADO_POR_EL_MOTOR, "un alta no acepta ['x']")
    assert len(enviados) == 1 and "NO quedó creada" in enviados[0]["texto"]

    ContratoDeServicio.objects.filter(pk=c.pk).update(
        alta_estado=ContratoDeServicio.ALTA_POR_REVISAR)
    c.refresh_from_db()
    enviados.clear()
    alta_en_el_isp._fallida(c, alta_en_el_isp.NO_QUEDO_CREADO)
    assert enviados == [], "quien lo dijo ya lo está mirando"


def test_b3_si_el_aviso_falla_el_alta_queda_igual(orden, user_profile, config, monkeypatch):
    def rompe(**k):
        raise RuntimeError("el chat no contesta")

    monkeypatch.setattr(avisos, "_despachar", rompe)
    c = _contrato(orden, user_profile, alta_estado=ContratoDeServicio.ALTA_PEDIDA)
    alta_en_el_isp._fallida(c, alta_en_el_isp.FALLO)
    c.refresh_from_db()
    assert c.alta_estado == ContratoDeServicio.ALTA_FALLIDA
