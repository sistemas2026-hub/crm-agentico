"""What closing a case through the API actually does, twice.

B6 asked a narrow question before writing any executor: can Dexter's queue
(`cerrar_caso`, contract §3.6) close a CRM case, check afterwards that it
closed, and retry without causing harm? The answer has to come from running
the endpoint, not from reading it — this project has been wrong about that
before.

These are the four properties the queue depends on. If someone changes the
close path, this file is where they find out they broke a retry contract that
lives in another repository.
"""

import pytest
from django.utils import timezone
from rest_framework import status

from cases.approvals import Approval, ApprovalRule


def _detail(pk):
    return f"/api/cases/{pk}/"


@pytest.mark.django_db
class TestCerrarCasoEsReintentable:
    """The four capabilities `cerrar_caso` would need."""

    def test_1_se_puede_cerrar(self, admin_client, case_a):
        """PATCH {status, closed_on} — what the `cierra_caso` tool sends."""
        r = admin_client.patch(
            _detail(case_a.id),
            {"status": "Closed", "closed_on": "2026-09-20"},
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        case_a.refresh_from_db()
        assert case_a.status == "Closed"

    def test_2_se_puede_verificar_despues(self, admin_client, case_a):
        """GET returns `status`, so "did it close?" is answerable.

        This is what `crear_ticket` does NOT have, and the whole reason Q2 is
        red: an effect you cannot ask about cannot be retried safely.
        """
        admin_client.patch(
            _detail(case_a.id),
            {"status": "Closed", "closed_on": "2026-09-20"},
            format="json",
        )
        r = admin_client.get(_detail(case_a.id))
        assert r.status_code == status.HTTP_200_OK
        cuerpo = r.json()
        caso = cuerpo.get("cases_obj", cuerpo)
        assert caso["status"] == "Closed"

    def test_3_cerrar_dos_veces_no_falla(self, admin_client, case_a, org_a):
        """A repeat close is accepted, even with an approval rule armed.

        The gate is on the TRANSITION: `old_status == "Closed"` returns early.
        That is what makes a retry safe — a rule added between the first
        attempt and the retry does not turn the retry into a 400.
        """
        admin_client.patch(
            _detail(case_a.id),
            {"status": "Closed", "closed_on": "2026-09-20"},
            format="json",
        )
        ApprovalRule.objects.create(
            org=org_a, name="Close needs sign-off", trigger_event="pre_close"
        )
        r = admin_client.patch(
            _detail(case_a.id),
            {"status": "Closed", "closed_on": "2026-09-20"},
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        case_a.refresh_from_db()
        assert case_a.status == "Closed"

    def test_4_pero_un_reintento_CIEGO_mueve_la_fecha_de_cierre(
        self, admin_client, case_a
    ):
        """The one real harm, and the reason the executor must read first.

        `closed_on` is taken from the request whenever it is present, so a
        retry three days later re-dates the close. Nothing errors; the case
        simply claims it was closed on a day it was not, and every
        resolution-time metric built on that column drifts with it.

        This is why `cerrar_caso` consults before writing instead of just
        retrying: if the case is already Closed it adopts that fact and
        touches nothing.
        """
        admin_client.patch(
            _detail(case_a.id),
            {"status": "Closed", "closed_on": "2026-09-20"},
            format="json",
        )
        case_a.refresh_from_db()
        assert str(case_a.closed_on) == "2026-09-20"

        admin_client.patch(
            _detail(case_a.id),
            {"status": "Closed", "closed_on": "2026-09-23"},
            format="json",
        )
        case_a.refresh_from_db()
        assert str(case_a.closed_on) == "2026-09-23", (
            "if this ever stops moving, the read-first rule in "
            "nucleo/relevo/efectos_externos.py can be relaxed"
        )


@pytest.mark.django_db
class TestCerrarCasoPuedeSerRechazado:
    """A refusal that is legitimate, and must never be retried as a failure."""

    def test_una_regla_de_aprobacion_bloquea_el_cierre(
        self, admin_client, case_a, org_a
    ):
        """400, and the case stays open. For Dexter's queue this is
        `permanente`: repeating it gives the same answer forever. It needs a
        person to approve, not a timer."""
        ApprovalRule.objects.create(
            org=org_a, name="Close needs sign-off", trigger_event="pre_close"
        )
        r = admin_client.patch(
            _detail(case_a.id),
            {"status": "Closed", "closed_on": "2026-09-20"},
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        case_a.refresh_from_db()
        assert case_a.status == "New"

    def test_con_la_aprobacion_pasa(self, admin_client, case_a, org_a, admin_profile):
        rule = ApprovalRule.objects.create(
            org=org_a, name="Close needs sign-off", trigger_event="pre_close"
        )
        Approval.objects.create(
            org=org_a,
            case=case_a,
            rule=rule,
            requested_by=admin_profile,
            state="approved",
        )
        r = admin_client.patch(
            _detail(case_a.id),
            {"status": "Closed", "closed_on": "2026-09-20"},
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestElCasoPuedeReabrirse:
    """Closed is not final, and the queue must not assume it is."""

    def test_un_caso_cerrado_puede_volver_a_abrirse(self, admin_client, case_a):
        case_a.status = "Closed"
        case_a.closed_on = timezone.localdate()
        case_a.save()
        r = admin_client.patch(_detail(case_a.id), {"status": "New"}, format="json")
        assert r.status_code == status.HTTP_200_OK
        case_a.refresh_from_db()
        assert case_a.status == "New", (
            "a reopened case means a 'hecha' sync no longer describes reality; "
            "the queue records what it did, never what is true now"
        )
