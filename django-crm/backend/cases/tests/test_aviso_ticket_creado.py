"""
================================================================================
 EL CLIENTE SE ENTERA DE QUE LE ABRIERON UN TICKET  --  30/10/2026 (PRD §8.17)
================================================================================
Cuando una persona abre un ticket desde "Nuevo ticket", el cliente no esta en
el chat: no sabe que su pedido quedo registrado, y vuelve a escribir para
preguntar. Al atar el caso a su ticket del ISP (la UNICA via por la que nace un
ticket desde Dexter), el CRM le pide al motor el aviso `ticket_creado_cliente`.

  A  atar un caso NUEVO pide UN aviso, despues del commit; repetir el vinculo
     o un vinculo rechazado no pide nada. Los tickets IMPORTADOS no pasan por
     aca: los abrio una persona en el sistema del ISP (ficha de avisos).
  B  el pedido lleva la clave del ticket, el servicio (el motor lee el movil
     de la ficha del ISP: el CRM no lo tiene), el numero y el asunto -- y NO
     la descripcion, que es texto libre de quien atiende.
  C  la tarea reagenda cuando el motor dice cuando volver, no pide nada por un
     caso que ya se cerro (al cerrar sale la encuesta) y sale a nombre de la
     empresa de la org, no la del entorno.

    pytest cases/tests/test_aviso_ticket_creado.py
================================================================================
"""
from unittest import mock

import pytest

from cases import tasks
from cases.models import Case

pytestmark = pytest.mark.django_db


def _url(caso):
    return f"/api/importacion/casos/{caso.pk}/vincular/"


def _caso(org, autor, nombre="Sin internet", **extra):
    return Case.objects.create(name=nombre, status="New", priority="Normal",
                               org=org, created_by=autor,
                               description="La señora dice que el vecino le robó la clave", **extra)


def _cuerpo(ticket="95001"):
    return {"provider": "wisphub", "external_ticket_id": ticket,
            "external_service_id": "5832", "area": "soporte_tecnico"}


# ---------------------------------------------------------------------------
# A · atar el caso pide el aviso, una vez, despues del commit
# ---------------------------------------------------------------------------

def test_a_atar_un_caso_nuevo_pide_un_aviso_despues_del_commit(
        admin_client, org_a, admin_user, django_capture_on_commit_callbacks):
    caso = _caso(org_a, admin_user)
    with mock.patch.object(tasks.avisar_ticket_creado, "delay") as pedir:
        with django_capture_on_commit_callbacks(execute=True):
            r = admin_client.post(_url(caso), _cuerpo(), format="json")
    assert r.status_code == 200, r.content
    assert [c.args for c in pedir.call_args_list] == [(str(caso.id), str(org_a.id))]


def test_a2_repetir_el_vinculo_o_uno_rechazado_no_pide_nada(
        admin_client, org_a, admin_user, django_capture_on_commit_callbacks):
    caso = _caso(org_a, admin_user)
    otro = _caso(org_a, admin_user, "Otro")
    admin_client.post(_url(caso), _cuerpo("95001"), format="json")
    with mock.patch.object(tasks.avisar_ticket_creado, "delay") as pedir:
        with django_capture_on_commit_callbacks(execute=True):
            assert admin_client.post(_url(caso), _cuerpo("95001"), format="json").json()["ya_estaba"]
            assert admin_client.post(_url(otro), _cuerpo("95001"), format="json").status_code == 409
    assert pedir.call_count == 0


# ---------------------------------------------------------------------------
# B y C · la tarea
# ---------------------------------------------------------------------------

class _R:
    def __init__(self, datos, status=200):
        self._d, self.status_code, self.content = datos, status, b"x"

    def json(self):
        return self._d


@pytest.fixture
def motor(monkeypatch):
    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
    monkeypatch.setenv("ASISTENTE_TENANT", "OTRA_EMPRESA_DEL_ENTORNO")
    with mock.patch("operaciones.areas_del_tenant.tenant_de_organizacion",
                    return_value="rapilink") as resolver:
        yield resolver


def _atado(org, autor, **extra):
    return _caso(org, autor, provider="wisphub", external_ticket_id="95001",
                 external_service_id="5832", **extra)


def test_b_el_pedido_lleva_clave_servicio_numero_y_asunto_y_no_la_descripcion(
        org_a, admin_user, motor):
    caso = _atado(org_a, admin_user)
    with mock.patch("requests.post", return_value=_R({"enviado": True, "motivo": None})) as post:
        tasks.avisar_ticket_creado(str(caso.id), str(org_a.id))
    assert post.call_args.args[0] == "http://motor:5000/avisos/evento"
    cuerpo = post.call_args.kwargs["json"]
    assert cuerpo["tenant"] == "rapilink", "la empresa de la org, no la del entorno"
    assert cuerpo["evento"] == "ticket_creado_cliente"
    assert cuerpo["clave"] == "ticket:wisphub:95001"
    assert cuerpo["caso_id"] == str(caso.id)
    assert cuerpo["servicio"] == "5832"
    assert cuerpo["contexto"] == {"ticket_numero": "95001", "ticket_asunto": "Sin internet"}
    assert "telefono" not in cuerpo
    assert "robó" not in str(cuerpo), "la descripcion no viaja"
    motor.assert_called_with(str(org_a.id))


@pytest.mark.parametrize("motivo", ["todavia_no", "isp_no_contesta"])
def test_c_reagenda_cuando_el_motor_dice_cuando_volver(org_a, admin_user, motor, motivo):
    caso = _atado(org_a, admin_user)
    with mock.patch("requests.post", return_value=_R({"enviado": False, "motivo": motivo,
                                                     "reintentar_en": 900})), \
            mock.patch.object(tasks.avisar_ticket_creado, "apply_async") as reagendar:
        tasks.avisar_ticket_creado(str(caso.id), str(org_a.id))
    assert reagendar.call_args.kwargs["countdown"] == 900
    assert reagendar.call_args.kwargs["args"] == [str(caso.id), str(org_a.id), 1]


def test_c2_con_las_vueltas_agotadas_no_reagenda_mas(org_a, admin_user, motor):
    caso = _atado(org_a, admin_user)
    with mock.patch("requests.post", return_value=_R({"enviado": False, "motivo": "todavia_no",
                                                     "reintentar_en": 900})), \
            mock.patch.object(tasks.avisar_ticket_creado, "apply_async") as reagendar:
        tasks.avisar_ticket_creado(str(caso.id), str(org_a.id), 3)
    assert reagendar.call_count == 0


@pytest.mark.parametrize("cambio", ["cerrado", "sin_vinculo", "sin_empresa"])
def test_c3_no_se_pide_por_un_caso_cerrado_sin_ticket_o_sin_empresa(org_a, admin_user, motor, cambio):
    caso = _atado(org_a, admin_user) if cambio != "sin_vinculo" else _caso(org_a, admin_user)
    if cambio == "cerrado":
        Case.objects.filter(id=caso.id).update(status="Closed")
    if cambio == "sin_empresa":
        motor.return_value = ""
    with mock.patch("requests.post") as post:
        tasks.avisar_ticket_creado(str(caso.id), str(org_a.id))
    assert post.call_count == 0, cambio


def test_c4_el_motor_caido_no_rompe(org_a, admin_user, motor):
    caso = _atado(org_a, admin_user)
    with mock.patch("requests.post", side_effect=ConnectionError("caido")):
        assert tasks.avisar_ticket_creado(str(caso.id), str(org_a.id)) is None
