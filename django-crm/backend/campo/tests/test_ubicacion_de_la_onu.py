# -*- coding: utf-8 -*-
"""Con la ONU activada, sus coordenadas en SmartOLT (26/11/2026). El usuario:
«que las mismas coordenadas tambien las ponga en SmartOLT».

  A  al quedar ACTIVADA se escriben las coordenadas DEL CONTRATO, identificando
     la ONU SOLO por su serial (no el servicio: ese ya las tiene), una vez.
  B  sin coordenadas no se pide nada; un fallo queda dicho y no rompe nada.
"""
import pytest

from campo import activacion_onu
from campo.activacion_onu import ActivacionDeOnu
from campo.services import ubicacion_al_isp
from campo.tests.test_instalacion_validada import _contrato, config, orden, version  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def guardar(monkeypatch):
    vistos = []

    def _guardar(orden, *, latitud, longitud, profile, identificadores=None):
        vistos.append({"lat": latitud, "lng": longitud, "identificadores": identificadores,
                       "profile": profile})
        return {"guardada": guardar.resultado, "codigo": "guardada"}

    guardar.resultado = True
    monkeypatch.setattr(ubicacion_al_isp, "guardar_ubicacion", _guardar)
    return vistos


def _activacion(orden, user_profile, **kw):
    datos = dict(org=orden.org, orden=orden, serial="ZTEGC1A2B3C4", zona="ZONA 1",
                 pedida_por=user_profile, estado=ActivacionDeOnu.EN_CURSO)
    datos.update(kw)
    return ActivacionDeOnu.objects.create(**datos)


def _con_gps(orden, user_profile, gps={"lat": 10.8982702, "lng": -74.8017717}):
    c = _contrato(orden, user_profile)
    c.datos = {**c.datos, "gps": gps}
    c.save(update_fields=["datos"])
    return c


def test_a1_al_quedar_activada_escribe_las_coordenadas_del_contrato_solo_por_el_serial(
        orden, user_profile, config, guardar):
    _con_gps(orden, user_profile)
    a = _activacion(orden, user_profile)
    activacion_onu._anotar(a, {"estado": "activada", "olt": "3", "placa": "3", "puerto": "15"})
    assert guardar == [{"lat": 10.8982702, "lng": -74.8017717,
                        "identificadores": {"sn_onu": "ZTEGC1A2B3C4"}, "profile": user_profile}]
    a.refresh_from_db()
    assert a.ubicacion_en_smartolt == "guardada"
    activacion_onu.ubicacion_en_smartolt(a)
    assert len(guardar) == 1, "ya guardada: no se vuelve a escribir"


def test_a2_tambien_cuando_la_activacion_se_confirma_despues(orden, user_profile, config, guardar,
                                                             monkeypatch):
    _con_gps(orden, user_profile)
    a = _activacion(orden, user_profile)
    monkeypatch.setattr(activacion_onu, "_llamar", lambda *a, **k: {"estado": "activada"})
    activacion_onu.comprobar(a)
    assert len(guardar) == 1 and guardar[0]["identificadores"] == {"sn_onu": "ZTEGC1A2B3C4"}


def test_b1_sin_coordenadas_en_el_contrato_no_se_pide_nada(orden, user_profile, config, guardar):
    _contrato(orden, user_profile)
    a = _activacion(orden, user_profile)
    activacion_onu._anotar(a, {"estado": "activada"})
    assert guardar == []


def test_b2_si_no_quedo_lo_dice(orden, user_profile, config, monkeypatch):
    monkeypatch.setattr(ubicacion_al_isp, "guardar_ubicacion",
                        lambda orden, **kw: {"guardada": False, "codigo": "fallo"})
    _con_gps(orden, user_profile)
    a = _activacion(orden, user_profile)
    activacion_onu._anotar(a, {"estado": "activada"})
    a.refresh_from_db()
    assert a.ubicacion_en_smartolt == "no_guardada"


def test_b3_una_activacion_que_NO_quedo_no_escribe(orden, user_profile, config, guardar):
    _con_gps(orden, user_profile)
    a = _activacion(orden, user_profile)
    activacion_onu._anotar(a, {"estado": "fallo", "motivo": "rechazada"})
    assert guardar == []


def test_b4_identificadores_dados_viajan_SOLO_esos_al_motor(orden, user_profile, config, monkeypatch):
    """Sin el doble: el cuerpo que sale hacia el motor lleva solo el serial."""
    enviados = []

    class R:
        status_code = 200
        content = b"{}"

        def json(self):
            return {"estado": "guardada", "destinos": []}

    monkeypatch.setattr(ubicacion_al_isp, "_tenant_de", lambda o: "tenant-x")
    monkeypatch.setattr(ubicacion_al_isp.requests, "post",
                        lambda url, **kw: enviados.append(kw["json"]) or R())
    ubicacion_al_isp.guardar_ubicacion(orden, latitud=10.9, longitud=-74.8, profile=user_profile,
                                       identificadores={"sn_onu": "ZTEGC1A2B3C4"})
    assert enviados and enviados[0]["identificadores"] == {"sn_onu": "ZTEGC1A2B3C4"}
