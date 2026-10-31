"""
EL REGISTRO ESTA CERRADO POR DEFECTO: NINGUN INICIO DE SESION CREA UNA CUENTA,
Y SOLO LA PLATAFORMA CREA ORGANIZACIONES.

Hasta el 23/10/2026 cualquier correo conseguia una cuenta (enlace magico,
codigo, Google) y con ella una organizacion propia como ADMIN, en produccion.
Con ``PERMITIR_AUTORREGISTRO`` apagado -- el default -- las cuentas las crea un
administrador desde Equipo y las organizaciones un superusuario.

Se afirma sobre el EFECTO -- que la cuenta y la organizacion no existan despues
--, no sobre el codigo de respuesta solamente: un 403 que igual dejara la fila
creada seria el mismo agujero con otro numero.

Las pruebas de la mecanica de cada via (vencimientos, reuso, limites) viven en
test_magic_link.py, test_auth.py y test_organizations.py, que corren con el
autorregistro prendido a proposito.

Run with: pytest common/tests/test_registro_cerrado.py -v
"""

import secrets
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework import status

from common.models import MagicLinkToken, Org, User
from common.tests.test_auth import _make_fake_id_token

DESCONOCIDO = "alguien-de-internet@example.com"


@pytest.fixture(autouse=True)
def _registro_cerrado(settings):
    # Explicito aunque sea el default: si alguien cambia el default, esta
    # prueba sigue afirmando el comportamiento cerrado y no pasa por casualidad.
    settings.PERMITIR_AUTORREGISTRO = False


def _token_de_enlace(email):
    return MagicLinkToken.objects.create(
        email=email,
        token=secrets.token_hex(32),
        expires_at=timezone.now() + timedelta(minutes=10),
    )


def _token_de_codigo(email, code):
    return MagicLinkToken.objects.create(
        email=email,
        token=secrets.token_hex(32),
        delivery="code",
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=10),
    )


@pytest.mark.django_db
class TestEnlaceMagico:
    def test_pedir_enlace_para_un_correo_sin_cuenta_no_manda_nada(
        self, unauthenticated_client
    ):
        with patch("common.tasks.send_magic_link_email") as tarea:
            tarea.delay = MagicMock()
            r = unauthenticated_client.post(
                "/api/auth/magic-link/request/", {"email": DESCONOCIDO}, format="json"
            )
        # Misma respuesta de siempre: no revela que correos tienen cuenta.
        assert r.status_code == status.HTTP_200_OK
        assert not MagicLinkToken.objects.filter(email=DESCONOCIDO).exists()
        tarea.delay.assert_not_called()

    def test_pedir_enlace_para_una_cuenta_que_existe_si_lo_manda(
        self, unauthenticated_client, admin_user
    ):
        with patch("common.tasks.send_magic_link_email") as tarea:
            tarea.delay = MagicMock()
            unauthenticated_client.post(
                "/api/auth/magic-link/request/", {"email": admin_user.email}, format="json"
            )
        assert MagicLinkToken.objects.filter(email=admin_user.email).exists()
        tarea.delay.assert_called_once()

    def test_abrir_un_enlace_de_un_correo_sin_cuenta_no_crea_la_cuenta(
        self, unauthenticated_client
    ):
        t = _token_de_enlace(DESCONOCIDO)
        r = unauthenticated_client.post(
            "/api/auth/magic-link/verify/", {"token": t.token}, format="json"
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert "access_token" not in r.data
        assert not User.objects.filter(email=DESCONOCIDO).exists()

    def test_una_cuenta_que_existe_sigue_entrando(
        self, unauthenticated_client, admin_user, admin_profile
    ):
        t = _token_de_enlace(admin_user.email)
        r = unauthenticated_client.post(
            "/api/auth/magic-link/verify/", {"token": t.token}, format="json"
        )
        assert r.status_code == status.HTTP_200_OK
        assert "access_token" in r.data

    def test_un_codigo_de_un_correo_sin_cuenta_no_crea_la_cuenta(
        self, unauthenticated_client
    ):
        _token_de_codigo(DESCONOCIDO, "654321")
        r = unauthenticated_client.post(
            "/api/auth/magic-link/verify-code/",
            {"email": DESCONOCIDO, "code": "654321"},
            format="json",
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert not User.objects.filter(email=DESCONOCIDO).exists()


@pytest.mark.django_db
class TestGoogle:
    @patch("common.views.auth_views.requests.post")
    def test_google_por_redireccion_no_crea_la_cuenta(
        self, mock_post, unauthenticated_client
    ):
        respuesta = MagicMock()
        respuesta.status_code = 200
        respuesta.json.return_value = {
            "id_token": _make_fake_id_token(DESCONOCIDO),
            "access_token": "at",
        }
        mock_post.return_value = respuesta
        r = unauthenticated_client.post(
            "/api/auth/google/callback/",
            {
                "code": "authcode",
                "code_verifier": "verifier",
                "redirect_uri": "http://localhost:3000/callback",
            },
            format="json",
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert not User.objects.filter(email=DESCONOCIDO).exists()

    @patch("google.oauth2.id_token.verify_oauth2_token")
    @patch("google.auth.transport.requests.Request")
    def test_google_por_id_token_no_crea_la_cuenta(
        self, mock_request_cls, mock_verify, unauthenticated_client
    ):
        mock_verify.return_value = {"email": DESCONOCIDO, "email_verified": True}
        r = unauthenticated_client.post(
            "/api/auth/google/", {"idToken": "valid-token"}, format="json"
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert not User.objects.filter(email=DESCONOCIDO).exists()


@pytest.mark.django_db
class TestCrearOrganizacion:
    def test_un_admin_comun_no_crea_organizaciones(self, admin_client):
        antes = Org.objects.count()
        r = admin_client.post("/api/org/", {"name": "Mi ISP propio"}, format="json")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert Org.objects.count() == antes
        assert not Org.objects.filter(name="Mi ISP propio").exists()

    def test_la_plataforma_si(self, admin_client, admin_user):
        admin_user.is_superuser = True
        admin_user.save(update_fields=["is_superuser"])
        r = admin_client.post("/api/org/", {"name": "ISP dado de alta"}, format="json")
        assert r.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
        assert Org.objects.filter(name="ISP dado de alta").exists()
