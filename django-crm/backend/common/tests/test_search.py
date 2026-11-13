"""Tests for the org-scoped global search endpoint (GET /api/search/).

The two that matter most are tenant isolation (org A never sees org B) and
intra-org visibility (a non-admin never finds a record they could not open from
the list). Search is a classic place for both leaks.
"""

import pytest
from crum import impersonate

from accounts.models import Account
from cases.models import Case, Solution
from contacts.models import Contact
from invoices.models import Invoice
from leads.models import Lead
from opportunity.models import Opportunity

URL = "/api/search/"


def _seed_all(org, token="Zephyr"):
    """One record of every searchable type in `org`, all matching `token`."""
    Lead.objects.create(
        first_name="Zed",
        last_name="Example",
        email="zed@example.com",
        status="in process",
        company_name=f"{token} Ltd",
        org=org,
    )
    Account.objects.create(name=f"{token} Corp", org=org)
    Contact.objects.create(
        first_name=token, last_name="Person", email="c@example.com", org=org
    )
    Opportunity.objects.create(name=f"{token} deal", stage="PROSPECTING", org=org)
    Case.objects.create(
        name=f"{token} ticket", status="New", priority="Normal", org=org
    )
    billing = Account.objects.create(name="Billing Co", org=org)
    Invoice.objects.create(
        invoice_title=f"{token} invoice",
        client_name=f"{token} Client",
        account=billing,
        currency="USD",
        status="Draft",
        org=org,
    )
    Solution.objects.create(
        org=org,
        title=f"{token} guide",
        description="How to.",
        status="approved",
        is_published=True,
    )


@pytest.mark.django_db
class TestGlobalSearch:
    def test_short_query_returns_empty_even_with_matches(self, admin_client, org_a):
        _seed_all(org_a, token="Zephyr")
        # One character is below the floor, so it matches nothing on purpose...
        assert admin_client.get(f"{URL}?q=Z").json()["results"] == []
        assert admin_client.get(f"{URL}?q=").json()["results"] == []
        # ...two characters searches for real.
        assert len(admin_client.get(f"{URL}?q=Ze").json()["results"]) > 0

    def test_unauthenticated_rejected(self, unauthenticated_client):
        resp = unauthenticated_client.get(f"{URL}?q=zephyr")
        assert resp.status_code in (401, 403)

    def test_finds_every_type(self, admin_client, org_a):
        _seed_all(org_a)
        body = admin_client.get(f"{URL}?q=Zephyr").json()
        types = {r["type"] for r in body["results"]}
        assert types == {
            "lead",
            "deal",
            "account",
            "contact",
            "ticket",
            "invoice",
            "solution",
        }
        for row in body["results"]:
            assert row["id"] and row["title"]

    def test_cross_tenant_isolation(self, admin_client, org_b_client, org_a, org_b):
        """org A's admin must not find org B's record, and vice-versa."""
        Account.objects.create(name="SecretB Holdings", org=org_b)
        seen_by_a = admin_client.get(f"{URL}?q=SecretB").json()["results"]
        assert seen_by_a == []
        seen_by_b = org_b_client.get(f"{URL}?q=SecretB").json()["results"]
        assert any(
            r["type"] == "account" and "SecretB" in r["title"] for r in seen_by_b
        )

    def test_non_admin_sees_only_created_or_assigned(
        self, user_client, admin_user, regular_user, user_profile, org_a
    ):
        with impersonate(admin_user):
            Account.objects.create(name="Alpha AdminOnly", org=org_a)
        with impersonate(regular_user):
            Account.objects.create(name="Alpha Mine", org=org_a)
        assigned = Account.objects.create(name="Alpha Assigned", org=org_a)
        assigned.assigned_to.add(user_profile)

        titles = {
            r["title"] for r in user_client.get(f"{URL}?q=Alpha").json()["results"]
        }
        assert "Alpha Mine" in titles  # created by the user
        assert "Alpha Assigned" in titles  # assigned to the user
        assert "Alpha AdminOnly" not in titles  # neither → hidden

    def test_admin_sees_all_in_org(
        self, admin_client, admin_user, regular_user, user_profile, org_a
    ):
        with impersonate(admin_user):
            Account.objects.create(name="Beta AdminOwned", org=org_a)
        with impersonate(regular_user):
            Account.objects.create(name="Beta UserOwned", org=org_a)
        titles = {
            r["title"] for r in admin_client.get(f"{URL}?q=Beta").json()["results"]
        }
        assert {"Beta AdminOwned", "Beta UserOwned"} <= titles

    def test_solutions_visible_to_every_member(
        self, user_client, admin_user, user_profile, org_a
    ):
        """Knowledge base is org-wide, a non-admin who owns nothing still finds it."""
        with impersonate(admin_user):
            Solution.objects.create(
                org=org_a,
                title="SharedKB article",
                description="x",
                status="approved",
                is_published=True,
            )
        results = user_client.get(f"{URL}?q=SharedKB").json()["results"]
        assert any(r["type"] == "solution" for r in results)


# --- Solicitudes de instalacion y ordenes de campo (12/11/2026) -------------
#
# La paleta ⌘K llega a lo que trabaja un ISP. Las dos reglas de visibilidad son
# las que importan: una solicitud trae datos personales y la busca solo
# gestion; una orden la ve gestion entera y un tecnico solo si esta asignado.


def _solicitud(org, nombre, telefono, documento, token):
    import datetime as dt

    from django.utils import timezone

    from solicitudes.models import SolicitudServicio

    return SolicitudServicio.objects.create(
        org=org, token_hash=token, expira_en=timezone.now() + dt.timedelta(days=1),
        nombre=nombre, apellido="Rivera", telefono=telefono,
        tipo_documento="CC", numero_documento=documento,
        barrio="Centro", estado=SolicitudServicio.ENVIADA,
    )


def _orden(org, numero, nombre, abonado=""):
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    wt, _ = WorkType.objects.get_or_create(org=org, codigo="ftth", defaults={"nombre": "FTTH"})
    version = WorkTypeVersion.objects.filter(work_type=wt).first() or WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"campos": [], "evidencias": []},
    )
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre=nombre, cliente_direccion="Calle 1",
        cliente_id_abonado=abonado, revision=1,
    )


@pytest.mark.django_db
class TestBuscarLoDeUnISP:
    def test_gestion_encuentra_la_solicitud_por_nombre_telefono_o_documento(self, admin_client, org_a):
        _solicitud(org_a, "Quiteria", "3001112233", "99887766", "t1")
        for q in ("Quiteria", "3001112233", "99887766", "Quiteria Rivera"):
            res = [r for r in admin_client.get(URL, {"q": q}).json()["results"] if r["type"] == "solicitud"]
            assert len(res) == 1, q
            assert res[0]["title"] == "Quiteria Rivera"
            # Ni el telefono ni el documento viajan en el resultado.
            assert "3001112233" not in str(res[0]) and "99887766" not in str(res[0])

    def test_un_usuario_que_no_es_de_gestion_no_encuentra_solicitudes(self, user_client, org_a):
        _solicitud(org_a, "Quiteria", "3001112233", "99887766", "t2")
        res = user_client.get(URL, {"q": "Quiteria"}).json()["results"]
        assert [r for r in res if r["type"] == "solicitud"] == []

    def test_la_solicitud_de_otra_empresa_no_aparece(self, admin_client, org_b):
        _solicitud(org_b, "Ajenisima", "3009998877", "11223344", "t3")
        assert admin_client.get(URL, {"q": "Ajenisima"}).json()["results"] == []

    def test_gestion_encuentra_la_orden_por_numero_cliente_o_servicio(self, admin_client, org_a):
        o = _orden(org_a, 4321, "Teodomiro Paz", abonado="SV-778")
        for q in ("4321", "OT-4321", "Teodomiro", "SV-778"):
            res = [r for r in admin_client.get(URL, {"q": q}).json()["results"] if r["type"] == "orden"]
            assert [r["id"] for r in res] == [str(o.id)], q
        assert res[0]["title"] == "OT-4321 · Teodomiro Paz"
        assert res[0]["id_servicio"] == "SV-778"

    def test_un_tecnico_solo_encuentra_las_ordenes_que_tiene_asignadas(
        self, user_client, user_profile, org_a
    ):
        from campo.models import AsignacionTrabajo

        mia = _orden(org_a, 501, "Florinda Mia")
        _orden(org_a, 502, "Florinda Ajena")
        AsignacionTrabajo.objects.create(orden=mia, profile=user_profile, rol="tecnico_lider", es_principal=True)
        res = [r for r in user_client.get(URL, {"q": "Florinda"}).json()["results"] if r["type"] == "orden"]
        assert [r["id"] for r in res] == [str(mia.id)]

    def test_la_orden_de_otra_empresa_no_aparece(self, admin_client, org_b):
        _orden(org_b, 777, "Clienta Ajena")
        res = admin_client.get(URL, {"q": "Clienta Ajena"}).json()["results"]
        assert [r for r in res if r["type"] == "orden"] == []
