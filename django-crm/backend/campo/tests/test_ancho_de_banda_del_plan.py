# -*- coding: utf-8 -*-
"""EL ANCHO DE BANDA DEL PLAN, AL ACTIVAR LA ONU  --  27/11/2026.

El usuario: «en SmartOLT tambien hay que ponerle el ancho de banda de descarga
y carga». La empresa elige en Programacion el perfil de bajada y el de subida
de cada plan; al activar la ONU viajan los del plan del contrato. El motor
comprueba que existan en el proveedor antes de escribir (tests/test_activar_onu.py
seccion 7); aca, lo de este lado:

  A  LA TABLA -- se valida, una fila vacia se descarta, y no mandarla la deja.
  B  AL PEDIR -- sin tabla, como hasta hoy; con tabla, los del plan; un plan
     sin su fila NO se activa (quedaria con el perfil por defecto).
  C  AL EJECUTAR -- viajan los perfiles con los que SE PIDIO.
"""
import pytest

from campo import activacion_onu as A
from campo.contrato import ConfiguracionDeContrato
from campo.tests.test_activacion_onu import cola, config, contrato, motor, orden  # noqa: F401

pytestmark = pytest.mark.django_db

URL = "/api/campo/contrato/configuracion/"
TABLA = [{"plan": "PLAN FAMILIA", "bajada": "PLAN_200MB_SV", "subida": "PLAN_100MB"},
         {"plan": "PLAN ULTRA", "bajada": "PLAN_500MB", "subida": "PLAN_250MB"}]


def _con_plan(contrato, plan):
    contrato.datos = {**(contrato.datos or {}), "plan": plan}
    contrato.save(update_fields=["datos"])
    return contrato


# --------------------------------------------------------------------------- #
#  A. LA TABLA
# --------------------------------------------------------------------------- #
def test_a1_se_guarda_limpia_y_una_fila_sin_perfiles_se_descarta(admin_client):
    r = admin_client.put(URL, {"perfiles_de_velocidad": [
        {"plan": "  PLAN   FAMILIA ", "bajada": " PLAN_200MB_SV ", "subida": "PLAN_100MB"},
        {"plan": "PLAN HOGAR", "bajada": "", "subida": ""}]}, format="json")
    assert r.status_code == 200, r.content
    assert admin_client.get(URL).json()["perfiles_de_velocidad"] == [
        {"plan": "PLAN FAMILIA", "bajada": "PLAN_200MB_SV", "subida": "PLAN_100MB"}]


@pytest.mark.parametrize("malo", [
    "PLAN FAMILIA",
    [{"plan": "", "bajada": "X"}],
    [{"plan": "PLAN FAMILIA", "bajada": "PLAN;DROP"}],
    [{"plan": "PLAN FAMILIA", "bajada": "A"}, {"plan": "plan familia", "subida": "B"}],
])
def test_a2_lo_que_no_se_acepta(admin_client, malo):
    assert admin_client.put(URL, {"perfiles_de_velocidad": malo}, format="json").status_code == 400


def test_a3_un_guardado_SIN_la_tabla_no_la_borra(admin_client):
    admin_client.put(URL, {"perfiles_de_velocidad": TABLA}, format="json")
    r = admin_client.put(URL, {"nit": "900"}, format="json")
    assert r.status_code == 200 and r.json()["perfiles_de_velocidad"] == TABLA


# --------------------------------------------------------------------------- #
#  B. AL PEDIR
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tabla,plan,esperado", [
    ([], "PLAN FAMILIA", {}),                                          # no la usa: como hoy
    (TABLA, "plan  familia", {"bajada": "PLAN_200MB_SV", "subida": "PLAN_100MB"}),
    (TABLA, "PLAN HOGAR", None),                                       # la usa y falta: NO
])
def test_b1_los_perfiles_del_plan(tabla, plan, esperado):
    assert A.perfiles_del_plan({"perfiles_de_velocidad": tabla}, plan) == esperado


def test_b2_con_la_tabla_un_plan_SIN_su_fila_no_se_activa(orden, user_profile, config, contrato,
                                                          cola):
    ConfiguracionDeContrato.objects.filter(pk=config.pk).update(perfiles_de_velocidad=TABLA)
    _con_plan(contrato, "PLAN HOGAR")
    with pytest.raises(A.NoSePuedeActivar, match="ancho de banda del plan «PLAN HOGAR»"):
        A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    assert cola == [] and not A.ActivacionDeOnu.objects.filter(orden=orden).exists()


# --------------------------------------------------------------------------- #
#  C. AL EJECUTAR
# --------------------------------------------------------------------------- #
def test_c1_al_motor_van_los_perfiles_con_los_que_SE_PIDIO(orden, user_profile, config, contrato,
                                                           cola, motor):
    ConfiguracionDeContrato.objects.filter(pk=config.pk).update(perfiles_de_velocidad=TABLA)
    _con_plan(contrato, "PLAN FAMILIA")
    a = A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    assert (a.perfil_bajada, a.perfil_subida) == ("PLAN_200MB_SV", "PLAN_100MB")
    #  La empresa cambia la tabla mientras el pedido espera: sale lo pedido.
    ConfiguracionDeContrato.objects.filter(pk=config.pk).update(perfiles_de_velocidad=[
        {"plan": "PLAN FAMILIA", "bajada": "PLAN_300MB", "subida": "PLAN_300MB"}])
    motor.respuestas = {"activar-onu": {"estado": "activada", "olt": "3", "placa": "3",
                                        "puerto": "6"}}
    A.ejecutar(a)
    _, cuerpo = motor.llamadas[0]
    assert cuerpo["datos"] == {"serial": "FHTT12345678", "zona": "VILLA ADELA 2", "vlan": 300,
                               "nombre": "LAURA MARCELA PINEDA",
                               "perfil_bajada": "PLAN_200MB_SV", "perfil_subida": "PLAN_100MB"}
    assert a.como_dict()["perfil_bajada"] == "PLAN_200MB_SV"


def test_c2_sin_la_tabla_no_viaja_ningun_perfil(orden, user_profile, config, contrato, cola,
                                                motor):
    _con_plan(contrato, "PLAN FAMILIA")
    a = A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    motor.respuestas = {"activar-onu": {"estado": "activada"}}
    A.ejecutar(a)
    _, cuerpo = motor.llamadas[0]
    assert "perfil_bajada" not in cuerpo["datos"] and "perfil_subida" not in cuerpo["datos"]
