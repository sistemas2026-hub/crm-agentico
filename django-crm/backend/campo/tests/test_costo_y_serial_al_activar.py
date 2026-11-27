# -*- coding: utf-8 -*-
"""El costo de instalacion y el serial, en el cliente cuando la oficina aprueba
(26/11/2026). Ver campo/instalacion.py → completar.

  A  AL ACTIVAR se pide, una vez, despues del commit.
  B  LO QUE VIAJA: quien aprobo, lo minimo para reconocer al cliente y solo el
     costo y el serial; como queda segun lo que conteste el motor.
"""
import pytest

from campo import instalacion
from campo.contrato import ContratoDeServicio
from campo.services import alta_en_el_isp
from campo.tests.test_instalacion_validada import _contrato, config, orden, version  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def motor(monkeypatch):
    class Motor:
        def __init__(self):
            self.llamadas = []
            self.respuesta = ("completado", {"estado": "completado"})

        def __call__(self, contrato, ruta, cuerpo, espera):
            self.llamadas.append((ruta, cuerpo))
            return self.respuesta

    m = Motor()
    monkeypatch.setattr(alta_en_el_isp, "_llamar", m)
    monkeypatch.setattr(instalacion, "costo_y_serial",
                        lambda orden: {"costo_instalacion": 50000, "serial_onu": "ZTEGC1A2B3C4"})
    return m


def _activo(orden, user_profile, **kw):
    return _contrato(orden, user_profile, estado=ContratoDeServicio.EN_EL_ISP,
                     servicio_isp="8039", activado_por=user_profile, **kw)


def test_a1_al_activar_se_pide_completar_una_vez(orden, user_profile, config, monkeypatch,
                                                 django_capture_on_commit_callbacks):
    from campo import tasks

    encolados = []
    monkeypatch.setattr(tasks.completar_cliente_en_el_isp, "delay",
                        lambda org, cid: encolados.append(cid))
    c = _activo(orden, user_profile)
    with django_capture_on_commit_callbacks(execute=True):
        assert instalacion.pedir_completar(c) is True
    assert c.completar_estado == "pedido" and c.completar_intento == 1
    assert encolados == [str(c.id)]
    assert instalacion.pedir_completar(c) is False, "con uno pedido no se pide otro"


def test_a2_el_paso_de_activar_lo_pide(orden, user_profile, config, monkeypatch):
    from campo.services import avisos as A

    pedidos = []
    monkeypatch.setattr(A, "avisar_instalacion_aprobada", lambda orden: True)
    monkeypatch.setattr(instalacion, "pedir_completar", lambda c: pedidos.append(c.id) or True)
    from campo.models import OrdenTrabajo
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO, estado_validacion=OrdenTrabajo.PENDIENTE)
    orden.refresh_from_db()
    c = _contrato(orden, user_profile, estado=ContratoDeServicio.INSTALACION,
                  servicio_isp="8039", activado_por=user_profile)
    instalacion._activada(c)
    c.refresh_from_db()
    assert c.estado == ContratoDeServicio.EN_EL_ISP and pedidos == [c.id]


def test_b1_viaja_quien_aprobo_lo_minimo_y_solo_costo_y_serial(orden, user_profile, config, motor):
    c = _activo(orden, user_profile, completar_estado="pedido", completar_intento=1)
    instalacion.completar(c)
    ruta, cuerpo = motor.llamadas[0]
    assert ruta == "completar-cliente"
    assert cuerpo["valores"] == {"costo_instalacion": 50000, "serial_onu": "ZTEGC1A2B3C4"}
    assert cuerpo["id_servicio"] == "8039" and cuerpo["intento"] == 1 and cuerpo["actor"]
    assert set(cuerpo["datos"]["cliente"]) == {"nombre", "apellido", "documento"}
    c.refresh_from_db()
    assert c.completar_estado == "hecho"
    assert c.como_dict()["instalacion"]["costo_y_serial"] == "hecho"


@pytest.mark.parametrize("respuesta,esperado", [
    (("ya_estaba", {"estado": "ya_estaba"}), "hecho"),
    (("nada_que_completar", {"estado": "nada_que_completar"}), "nada"),
    (("fallo", {"estado": "fallo"}), "fallido"),
    (("no_encontrada", {"estado": "no_encontrada"}), "fallido"),
    ((None, {}), "pedido"),
    (("en_curso", {"estado": "en_curso"}), "pedido"),
])
def test_b2_como_queda_segun_el_motor(orden, user_profile, config, motor, respuesta, esperado):
    motor.respuesta = respuesta
    c = _activo(orden, user_profile, completar_estado="pedido", completar_intento=1)
    instalacion.completar(c)
    c.refresh_from_db()
    assert c.completar_estado == esperado


def test_b3_al_tope_queda_por_revisar_y_no_se_vuelve_a_pedir_solo(orden, user_profile, config, motor):
    motor.respuesta = (None, {})
    c = _activo(orden, user_profile, completar_estado="pedido", completar_intento=1)
    instalacion.rendirse_completar(c)
    c.refresh_from_db()
    assert c.completar_estado == "por_revisar"
    assert instalacion.pedir_completar(c) is False
