"""Un cierre frenado por `pre_close` deja una solicitud, y aprobarla lo completa.

12/11/2026. Las reglas se quedan (decision del dueño). Lo que se prueba es lo
que pasaba alrededor de ellas, contra la API real y no contra las funciones:

  * el intento de Dexter (token de acceso personal, el mismo camino que
    `cerrar_caso_crm`) respondia 400 en ingles y no dejaba NADA en
    Tickets -> Aprobaciones;
  * aprobar no cerraba: habia que volver a cerrar a mano;
  * la regla 'MANAGER' no la podia resolver ningun perfil.

Ver cases/cierre_con_aprobacion.py.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from cases.approvals import Approval, ApprovalRule
from cases.cierre_con_aprobacion import completar_cierre
from common.models import Activity, PersonalAccessToken, Profile

FECHA_PEDIDA = "2026-11-10"


def _detalle(pk):
    return f"/api/cases/{pk}/"


@pytest.fixture
def regla(org_a):
    return ApprovalRule.objects.create(
        org=org_a, name="Cierre con visto bueno", trigger_event="pre_close"
    )


@pytest.fixture
def dexter(org_a):
    """El perfil dueño del token con el que el motor entra al CRM."""
    usuario = get_user_model().objects.create_user(
        email="dexter@test.com", password="x"
    )
    perfil = Profile.objects.create(user=usuario, org=org_a, role="ADMIN", is_active=True)
    crudo, _ = PersonalAccessToken.generate(perfil, "motor")
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {crudo}")
    return cliente, perfil


def _cerrar(cliente, caso, fecha=FECHA_PEDIDA):
    return cliente.patch(
        _detalle(caso.id), {"status": "Closed", "closed_on": fecha}, format="json"
    )


@pytest.mark.django_db
class TestElIntentoFrenadoDejaLaSolicitud:
    def test_el_intento_de_dexter_crea_la_solicitud_visible(
        self, dexter, admin_client, case_a, regla
    ):
        cliente, perfil = dexter
        r = _cerrar(cliente, case_a)

        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert r.data["codigo"] == "cierre_requiere_aprobacion"
        # En español, y dice que ya quedo pedida.
        texto = r.data["errors"]["status"][0]
        assert "necesita una aprobación" in texto and "Ya quedó pedida" in texto

        case_a.refresh_from_db()
        assert case_a.status != "Closed"

        a = Approval.objects.get(id=r.data["approval_id"])
        assert a.state == "pending"
        assert a.requested_by_id == perfil.id
        assert a.origen == "agente"
        assert a.cerrar_al_aprobar is True
        assert a.fecha_cierre_pedida == datetime.date(2026, 11, 10)
        assert "Dexter intentó cerrar" in a.note
        assert Activity.objects.filter(
            entity_id=case_a.id, action="APPROVAL_REQUESTED"
        ).exists()

        # Y la ve quien aprueba, con «Dexter» como solicitante.
        filas = admin_client.get("/api/cases/approvals/?state=pending").data["approvals"]
        fila = next(f for f in filas if f["id"] == str(a.id))
        assert fila["solicitante"] == "Dexter"
        assert fila["origen"] == "agente"
        assert fila["cerrar_al_aprobar"] is True
        assert fila["can_act"] is True

    def test_un_reintento_no_duplica_la_solicitud(self, dexter, case_a, regla):
        cliente, _ = dexter
        primero = _cerrar(cliente, case_a)
        segundo = _cerrar(cliente, case_a)
        assert primero.data["approval_id"] == segundo.data["approval_id"]
        assert Approval.objects.filter(case=case_a, state="pending").count() == 1

    def test_una_persona_tambien_deja_la_solicitud(self, user_client, case_a, regla, user_profile):
        case_a.assigned_to.add(user_profile)
        r = _cerrar(user_client, case_a)
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        a = Approval.objects.get(id=r.data["approval_id"])
        assert a.origen == "persona"
        assert a.requested_by_id == user_profile.id

    def test_sin_regla_cierra_como_siempre(self, dexter, case_a):
        cliente, _ = dexter
        r = _cerrar(cliente, case_a)
        assert r.status_code == status.HTTP_200_OK
        assert not Approval.objects.filter(case=case_a).exists()

    def test_el_detalle_dice_el_estado_de_la_solicitud(self, dexter, case_a, regla):
        cliente, _ = dexter
        assert cliente.get(_detalle(case_a.id)).data["aprobacion_de_cierre"] is None
        r = _cerrar(cliente, case_a)
        d = cliente.get(_detalle(case_a.id)).data["aprobacion_de_cierre"]
        assert d == {"id": r.data["approval_id"], "estado": "pending", "cerrar_al_aprobar": True}


@pytest.mark.django_db
class TestAprobarCompletaElCierre:
    def test_aprobar_cierra_el_caso_con_la_fecha_pedida(
        self, dexter, admin_client, case_a, regla
    ):
        cliente, _ = dexter
        aid = _cerrar(cliente, case_a).data["approval_id"]

        r = admin_client.post(f"/api/cases/approvals/{aid}/approve/", {}, format="json")
        assert r.status_code == status.HTTP_200_OK
        assert r.data["caso_cerrado"] is True

        case_a.refresh_from_db()
        assert case_a.status == "Closed"
        assert case_a.closed_on == datetime.date(2026, 11, 10)
        # Lo que el motor lee en su proximo ciclo: cerrado, y lo adopta.
        assert cliente.get(_detalle(case_a.id)).data["cases_obj"]["status"] == "Closed"

    def test_un_cierre_aprobado_dos_veces_no_reescribe_closed_on(
        self, dexter, admin_client, case_a, regla
    ):
        cliente, _ = dexter
        aid = _cerrar(cliente, case_a).data["approval_id"]
        admin_client.post(f"/api/cases/approvals/{aid}/approve/", {}, format="json")
        case_a.refresh_from_db()
        antes = case_a.closed_on

        # Segunda aprobacion por la API: rechazada, y no toca el caso.
        otra = admin_client.post(f"/api/cases/approvals/{aid}/approve/", {}, format="json")
        assert otra.status_code == status.HTTP_400_BAD_REQUEST
        assert "ya está aprobada" in otra.data["errors"]

        # Y la funcion misma, llamada otra vez sobre un caso ya cerrado y con
        # otra fecha pedida, no escribe nada.
        a = Approval.objects.get(id=aid)
        a.fecha_cierre_pedida = datetime.date(2030, 1, 1)
        assert completar_cierre(a) is False
        case_a.refresh_from_db()
        assert case_a.closed_on == antes

    def test_si_alguien_ya_lo_cerro_aprobar_no_le_corre_la_fecha(
        self, dexter, admin_client, case_a, regla, admin_profile
    ):
        cliente, _ = dexter
        aid = _cerrar(cliente, case_a).data["approval_id"]
        # Otra persona lo cerro por su cuenta con otra regla satisfecha.
        Approval.objects.create(
            org=case_a.org, case=case_a, rule=regla,
            requested_by=admin_profile, state="approved",
        )
        admin_client.patch(
            _detalle(case_a.id), {"status": "Closed", "closed_on": "2026-11-05"}, format="json"
        )
        r = admin_client.post(f"/api/cases/approvals/{aid}/approve/", {}, format="json")
        assert r.status_code == status.HTTP_200_OK
        assert r.data["caso_cerrado"] is False
        case_a.refresh_from_db()
        assert case_a.closed_on == datetime.date(2026, 11, 5)

    def test_rechazar_deja_el_caso_abierto(self, dexter, admin_client, case_a, regla):
        cliente, _ = dexter
        aid = _cerrar(cliente, case_a).data["approval_id"]
        r = admin_client.post(
            f"/api/cases/approvals/{aid}/reject/", {"reason": "falta la visita"}, format="json"
        )
        assert r.status_code == status.HTTP_200_OK
        case_a.refresh_from_db()
        assert case_a.status != "Closed"
        d = cliente.get(_detalle(case_a.id)).data["aprobacion_de_cierre"]
        assert d["estado"] == "rejected" and d["id"] == aid


@pytest.mark.django_db
class TestLaReglaDeGestion:
    def _perfil(self, org, rol, correo):
        u = get_user_model().objects.create_user(email=correo, password="x")
        return Profile.objects.create(user=u, org=org, role=rol, is_active=True)

    def test_manager_la_resuelve_un_perfil_de_gestion_y_no_un_miembro(
        self, org_a, case_a, admin_profile
    ):
        regla = ApprovalRule.objects.create(
            org=org_a, name="Gestion", trigger_event="pre_close", approver_role="MANAGER"
        )
        a = Approval.objects.create(
            org=org_a, case=case_a, rule=regla, requested_by=admin_profile
        )
        for rol in ("SUPERVISOR", "OPERACIONES", "ADMIN"):
            assert a.can_be_acted_on_by(self._perfil(org_a, rol, f"{rol}@t.com")), rol
        for rol in ("USER", "BODEGA"):
            assert not a.can_be_acted_on_by(self._perfil(org_a, rol, f"{rol}@t.com")), rol

    def test_un_supervisor_aprueba_por_la_api(self, org_a, dexter, case_a):
        ApprovalRule.objects.create(
            org=org_a, name="Gestion", trigger_event="pre_close", approver_role="MANAGER"
        )
        cliente, _ = dexter
        aid = _cerrar(cliente, case_a).data["approval_id"]

        from conftest import _make_authenticated_client

        perfil = self._perfil(org_a, "SUPERVISOR", "sup@t.com")
        sup = _make_authenticated_client(perfil.user, org_a, perfil)
        r = sup.post(f"/api/cases/approvals/{aid}/approve/", {}, format="json")
        assert r.status_code == status.HTTP_200_OK, r.data
        case_a.refresh_from_db()
        assert case_a.status == "Closed"
