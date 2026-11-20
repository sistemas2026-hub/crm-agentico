"""Mentions in a Bandeja internal note (30/10/2026).

POST /api/notifications/mencion-conversacion/ — what it must do and, as much,
what it must not: notify the author of their own mention, notify someone of
another org, notify twice within a minute, or take the link from the body.
"""

import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from common.models import Notification, Org, Profile, User
from common.serializer import OrgAwareRefreshToken
from conftest import set_rls_context

URL = "/api/notifications/mencion-conversacion/"


class MencionConversacionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Org.objects.create(name="Org A")
        cls.otra = Org.objects.create(name="Org B")
        cls.ana = Profile.objects.create(
            user=User.objects.create_user(email="ana@empresa.co", password="x"),
            org=cls.org, role="USER", is_active=True)
        cls.luis = Profile.objects.create(
            user=User.objects.create_user(email="luis@empresa.co", password="x"),
            org=cls.org, role="USER", is_active=True)
        cls.ajeno = Profile.objects.create(
            user=User.objects.create_user(email="pedro@otra.co", password="x"),
            org=cls.otra, role="USER", is_active=True)

    def setUp(self):
        set_rls_context(self.org)
        self.client = APIClient()
        token = OrgAwareRefreshToken.for_user_and_org(self.ana.user, self.org)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        self.conv = uuid.uuid4()

    def _mencionar(self, texto, conv=None):
        return self.client.post(
            URL, {"conversation_id": str(conv or self.conv), "texto": texto}, format="json")

    def test_avisa_al_mencionado_con_enlace_a_la_conversacion(self):
        r = self._mencionar("@luis mirá esta, no levanta la ONT")
        assert r.status_code == 200 and r.json() == {"avisados": 1}
        n = Notification.objects.get(recipient=self.luis)
        assert n.verb == "conversacion.mencion"
        assert n.link == f"/conversaciones/{self.conv}"
        assert n.actor_id == self.ana.id
        assert "no levanta" in n.data["comment_excerpt"]

    def test_no_se_avisa_a_si_mismo(self):
        assert self._mencionar("anoto para @ana").json() == {"avisados": 0}

    def test_no_alcanza_a_otra_organizacion(self):
        assert self._mencionar("@pedro").json() == {"avisados": 0}
        assert not Notification.objects.filter(recipient=self.ajeno).exists()

    def test_no_repite_en_menos_de_un_minuto(self):
        self._mencionar("@luis una")
        assert self._mencionar("@luis dos").json() == {"avisados": 0}
        assert Notification.objects.filter(recipient=self.luis).count() == 1

    def test_otra_conversacion_si_avisa(self):
        self._mencionar("@luis una")
        assert self._mencionar("@luis otra", conv=uuid.uuid4()).json() == {"avisados": 1}

    def test_id_invalido_es_400_y_no_escribe(self):
        r = self.client.post(URL, {"conversation_id": "../../admin", "texto": "@luis"}, format="json")
        assert r.status_code == 400
        assert not Notification.objects.exists()

    def test_sin_sesion_no_entra(self):
        r = APIClient().post(URL, {"conversation_id": str(self.conv), "texto": "@luis"}, format="json")
        assert r.status_code in (401, 403)
