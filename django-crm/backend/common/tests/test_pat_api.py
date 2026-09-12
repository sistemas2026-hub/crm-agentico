import uuid

import pytest

from common.models import PersonalAccessToken, Profile, User
from common.serializer import PersonalAccessTokenListSerializer


@pytest.mark.django_db
def test_list_serializer_hides_secret(admin_profile):
    raw, pat = PersonalAccessToken.generate(profile=admin_profile, name="cli")
    data = PersonalAccessTokenListSerializer(pat).data
    assert "token_hash" not in data
    assert data["token_prefix"] == pat.token_prefix
    assert data["name"] == "cli"
    assert raw not in str(data)


@pytest.fixture
def other_profile(org_a):
    """A second, distinct profile in the SAME org as admin_profile.

    Used for IDOR tests: the acting user (admin_profile) must never be able
    to see or revoke this profile's tokens even though they share an org.
    """
    user = User.objects.create_user(email="other@test.com", password="testpass123")
    return Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)


@pytest.mark.django_db
class TestPATApi:
    """Auth approach: the suite already ships a JWT-backed ``admin_client``
    fixture (conftest._make_authenticated_client) used by every other API
    test. We reuse it so request.profile == admin_profile and HasOrgContext
    is satisfied exactly as in production. The IDOR "other" tokens are minted
    directly on ``other_profile`` (a different profile in the same org), so the
    acting user and the token owner are genuinely distinct identities.
    """

    LIST_URL = "/api/profile/tokens/"

    def _detail_url(self, pk):
        return f"/api/profile/tokens/{pk}/"

    def test_create_returns_raw_token_once(self, admin_client, admin_profile):
        resp = admin_client.post(self.LIST_URL, {"name": "Claude"}, format="json")
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body["token"].startswith("bcrm_pat_")
        assert body["error"] is False
        assert "token_hash" not in body

        lst = admin_client.get(self.LIST_URL).json()
        assert lst["error"] is False
        assert len(lst["tokens"]) == 1
        assert all("token" not in t for t in lst["tokens"])
        assert all("token_hash" not in t for t in lst["tokens"])

    def test_create_rejects_blank_name(self, admin_client, admin_profile):
        resp = admin_client.post(self.LIST_URL, {"name": "  "}, format="json")
        assert resp.status_code == 400, resp.content
        body = resp.json()
        assert body["error"] is True
        assert "name" in body["errors"]

    def test_create_rejects_too_many_scopes(self, admin_client, admin_profile):
        resp = admin_client.post(
            self.LIST_URL, {"name": "x", "scopes": ["s"] * 100}, format="json"
        )
        assert resp.status_code == 400, resp.content

    def test_create_rejects_past_expiry(self, admin_client, admin_profile):
        resp = admin_client.post(
            self.LIST_URL,
            {"name": "x", "expires_at": "2020-01-01T00:00:00Z"},
            format="json",
        )
        assert resp.status_code == 400, resp.content

    def test_create_ignores_injected_protected_fields(
        self, admin_client, admin_profile, org_a
    ):
        # A client must not be able to set org / profile / token_hash / revoked_at.
        resp = admin_client.post(
            self.LIST_URL,
            {
                "name": "Injected",
                "token_hash": "attacker-controlled",
                "revoked_at": "2020-01-01T00:00:00Z",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        pat = PersonalAccessToken.objects.get(name="Injected")
        assert pat.token_hash != "attacker-controlled"
        assert pat.revoked_at is None
        assert pat.org == org_a
        assert pat.profile == admin_profile

    def test_list_only_own_tokens(self, admin_client, admin_profile, other_profile):
        _, own = PersonalAccessToken.generate(profile=admin_profile, name="mine")
        _, foreign = PersonalAccessToken.generate(profile=other_profile, name="theirs")

        lst = admin_client.get(self.LIST_URL).json()
        ids = {t["id"] for t in lst["tokens"]}
        assert str(own.id) in ids
        assert str(foreign.id) not in ids
        assert len(lst["tokens"]) == 1

    def test_cannot_revoke_others_token(
        self, admin_client, admin_profile, other_profile
    ):
        _, foreign = PersonalAccessToken.generate(profile=other_profile, name="theirs")
        resp = admin_client.delete(self._detail_url(foreign.id))
        assert resp.status_code == 404, resp.content
        foreign.refresh_from_db()
        assert foreign.revoked_at is None

    def test_revoke_own_token(self, admin_client, admin_profile):
        _, own = PersonalAccessToken.generate(profile=admin_profile, name="mine")
        resp = admin_client.delete(self._detail_url(own.id))
        assert resp.status_code == 200, resp.content
        own.refresh_from_db()
        assert own.revoked_at is not None

    def test_revoke_nonexistent_uuid_is_404(self, admin_client, admin_profile):
        resp = admin_client.delete(self._detail_url(uuid.uuid4()))
        assert resp.status_code == 404, resp.content

    def test_list_empty_for_fresh_user(self, admin_client, admin_profile):
        # admin_profile has no tokens minted in this test.
        resp = admin_client.get(self.LIST_URL)
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["error"] is False
        assert body["tokens"] == []

    def test_unauthenticated_list_is_401(self, unauthenticated_client):
        resp = unauthenticated_client.get(self.LIST_URL)
        # The org-context middleware short-circuits a credential-less request
        # with a 403 ("Organization context is required") BEFORE DRF's auth
        # layer would emit a 401. Asserting the framework's real behavior here;
        # either way the unauthenticated caller is denied (no data leak).
        assert resp.status_code == 403, resp.content


# =============================================================================
#  EL VOCABULARIO DE ALCANCES  --  para poder emitir minimo privilegio
# =============================================================================
#
# La pantalla ofrecia dos opciones: "solo lectura" o "todo lo que puede hacer el
# dueño". Su propio comentario remitia a "quien quiera scopes finos lo crea por
# la API" -- pero esa API esta cerrada para credenciales (una credencial no
# puede acuñar otra) y el JWT no sale del servidor, asi que la unica salida real
# era una sesion de consola. Dar de alta una empresa no puede depender de eso.
#
# Esta vista existe para que el formulario ofrezca los alcances reales sin
# repetir la lista: repetirla dejaria una pantalla que ofrece un recurso que el
# middleware rechaza, o que esconde uno que existe.

import pytest

from common import scopes as vocabulario


@pytest.mark.django_db
class TestVocabularioDeAlcances:
    RUTA = "/api/profile/tokens/scopes/"

    def test_devuelve_lo_que_el_enforcement_entiende(self, admin_client):
        r = admin_client.get(self.RUTA)
        assert r.status_code == 200, r.content
        d = r.json()
        assert set(d["resources"]) == set(vocabulario.API_RESOURCES), (
            "la pantalla ofreceria recursos que el middleware no reconoce")
        assert set(d["actions"]) == set(vocabulario.SCOPE_ACTIONS)
        assert d["wildcard"] == vocabulario.WILDCARD

    def test_incluye_el_recurso_de_importacion(self, admin_client):
        """El caso que motivo todo esto: sin 'importacion' en el vocabulario,
        el token dedicado del importador no se puede emitir desde la interfaz."""
        assert "importacion" in admin_client.get(self.RUTA).json()["resources"]

    def test_sin_sesion_no_se_lee(self, unauthenticated_client):
        assert unauthenticated_client.get(self.RUTA).status_code in (401, 403)

    def test_la_ruta_no_se_confunde_con_un_id(self, admin_client):
        """'scopes' va declarada ANTES de '<uuid:pk>'. Si se leyera como un id,
        esto daria 404 en vez del vocabulario."""
        assert admin_client.get(self.RUTA).status_code == 200


@pytest.mark.django_db
class TestEmitirConAlcancesFinos:
    def test_se_puede_crear_un_token_de_minimo_privilegio(self, admin_client):
        """Lo que antes solo se podia hacer por consola."""
        r = admin_client.post(
            "/api/profile/tokens/",
            {"name": "importacion-wisphub",
             "scopes": ["importacion:read", "importacion:write"]},
            format="json")
        assert r.status_code == 201, r.content
        assert sorted(r.json()["scopes"]) == ["importacion:read", "importacion:write"]
        assert "cases:write" not in r.json()["scopes"]

    def test_un_recurso_inventado_se_rechaza(self, admin_client):
        r = admin_client.post(
            "/api/profile/tokens/",
            {"name": "roto", "scopes": ["inventado:read"]}, format="json")
        assert r.status_code == 400, (
            "un recurso que el enforcement no conoce da un token que no sirve "
            "para nada, y nadie se entera hasta que falla")
