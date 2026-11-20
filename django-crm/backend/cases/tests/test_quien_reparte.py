"""
QUIEN REPARTE VE LA COLA ENTERA Y ASIGNA; UN COLABORADOR SIGUE VIENDO LO SUYO.

Hasta el 23/10/2026 solo ADMIN veia y asignaba un ticket ajeno. SUPERVISOR y
OPERACIONES -- que en campo y en el Supervisor NOC ya despachan cuadrillas y
validan ordenes -- no podian ver un ticket sin asignar, y con 212 de 735 sin
responsable el reparto esperaba a una sola persona.

Se afirma sobre el EFECTO en las dos direcciones: quien reparte ve, abre y
asigna; quien no reparte (USER, BODEGA) sigue sin ver lo ajeno; y BORRAR no se
abrio para nadie nuevo. Una prueba que solo mirara el caso positivo seguiria
verde si la regla se abriera para todos.

Run with: pytest cases/tests/test_quien_reparte.py -v
"""

import pytest
from rest_framework import status

from cases.models import Case
from common.models import Profile, User
from conftest import _make_authenticated_client

CASES_URL = "/api/cases/"


def _cliente(org, rol, email):
    user = User.objects.create_user(email=email, password="testpass123")
    perfil = Profile.objects.create(user=user, org=org, role=rol, is_active=True)
    return _make_authenticated_client(user, org, perfil), perfil


@pytest.fixture
def ajeno(case_a):
    """Un caso que no es de nadie de los que prueban: lo creo admin y no tiene responsable."""
    assert case_a.assigned_to.count() == 0
    return case_a


def _ids(resp):
    return {c["id"] for c in resp.data.get("cases", [])}


@pytest.mark.django_db
class TestQuienReparte:
    @pytest.mark.parametrize("rol", ["SUPERVISOR", "OPERACIONES"])
    def test_ve_el_ticket_ajeno_en_la_cola_y_lo_abre(self, org_a, ajeno, rol):
        cliente, _ = _cliente(org_a, rol, f"{rol.lower()}@test.com")
        assert str(ajeno.id) in _ids(cliente.get(CASES_URL))
        assert cliente.get(f"{CASES_URL}{ajeno.id}/").status_code == status.HTTP_200_OK

    @pytest.mark.parametrize("rol", ["SUPERVISOR", "OPERACIONES"])
    def test_lo_asigna(self, org_a, ajeno, user_profile, rol):
        cliente, _ = _cliente(org_a, rol, f"{rol.lower()}@test.com")
        r = cliente.patch(
            f"{CASES_URL}{ajeno.id}/", {"assigned_to": [str(user_profile.id)]}, format="json"
        )
        assert r.status_code == status.HTTP_200_OK
        assert list(ajeno.assigned_to.values_list("id", flat=True)) == [user_profile.id]

    @pytest.mark.parametrize("rol", ["SUPERVISOR", "OPERACIONES"])
    def test_no_lo_borra(self, org_a, ajeno, rol):
        cliente, _ = _cliente(org_a, rol, f"{rol.lower()}@test.com")
        r = cliente.delete(f"{CASES_URL}{ajeno.id}/")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert Case.objects.filter(pk=ajeno.id).exists()

    @pytest.mark.parametrize("rol", ["USER", "BODEGA"])
    def test_quien_no_reparte_sigue_sin_ver_lo_ajeno(self, org_a, ajeno, rol):
        cliente, _ = _cliente(org_a, rol, f"{rol.lower()}@test.com")
        assert str(ajeno.id) not in _ids(cliente.get(CASES_URL))
        assert cliente.get(f"{CASES_URL}{ajeno.id}/").status_code == status.HTTP_403_FORBIDDEN
        r = cliente.patch(f"{CASES_URL}{ajeno.id}/", {"assigned_to": []}, format="json")
        assert r.status_code == status.HTTP_403_FORBIDDEN
