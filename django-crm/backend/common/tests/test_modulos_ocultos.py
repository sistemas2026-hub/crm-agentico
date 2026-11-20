"""Los modulos que una empresa saca de su menu (12/11/2026, common/modulos.py).

Lo que se afirma es el EFECTO por la ruta real (`/api/org/settings/`, la misma
que el cascaron del frontend lee en cada navegacion):

* una empresa nace con todo visible (lista vacia), asi el despliegue no le
  cambia el menu a nadie;
* lo escribe solo un ADMIN: un USER recibe 403 y la fila no cambia;
* solo se aceptan claves del catalogo cerrado;
* lo que oculta una empresa no lo ve la otra.
"""

import pytest

from common.models import Org
from common.modulos import MODULOS_OCULTABLES

URL = "/api/org/settings/"


@pytest.mark.django_db
class TestModulosOcultos:
    def test_el_catalogo_es_el_de_las_nueve_pantallas_heredadas(self):
        # La misma lista fija la prueba del frontend (lib/v2/modulos.test.js).
        assert MODULOS_OCULTABLES == (
            "accounts", "contacts", "solutions", "documents", "tasks",
            "pipeline", "goals", "invoices", "timesheet",
        )

    def test_nace_con_todo_visible(self, user_client):
        resp = user_client.get(URL)
        assert resp.status_code == 200
        assert resp.json()["modulos_ocultos"] == []

    def test_un_admin_lo_guarda_y_cualquiera_lo_lee(self, admin_client, user_client, org_a):
        resp = admin_client.patch(
            URL, {"modulos_ocultos": ["timesheet", "accounts", "accounts"]}, format="json"
        )
        assert resp.status_code == 200, resp.content
        # Sin repetidos y en el orden del catalogo, no en el que llego.
        assert resp.json()["modulos_ocultos"] == ["accounts", "timesheet"]
        org_a.refresh_from_db()
        assert org_a.modulos_ocultos == ["accounts", "timesheet"]
        # Un miembro lo lee: el menu de todos depende de esto.
        assert user_client.get(URL).json()["modulos_ocultos"] == ["accounts", "timesheet"]

    def test_un_usuario_que_no_es_admin_no_lo_cambia(self, user_client, org_a):
        resp = user_client.patch(URL, {"modulos_ocultos": ["invoices"]}, format="json")
        assert resp.status_code == 403
        org_a.refresh_from_db()
        assert org_a.modulos_ocultos == []

    def test_una_clave_desconocida_se_rechaza_y_no_se_guarda(self, admin_client, org_a):
        resp = admin_client.patch(
            URL, {"modulos_ocultos": ["accounts", "conversaciones"]}, format="json"
        )
        assert resp.status_code == 400
        assert "conversaciones" in str(resp.json()["modulos_ocultos"])
        org_a.refresh_from_db()
        assert org_a.modulos_ocultos == []

    def test_un_texto_suelto_no_es_una_lista(self, admin_client, org_a):
        resp = admin_client.patch(URL, {"modulos_ocultos": "accounts"}, format="json")
        assert resp.status_code == 400
        org_a.refresh_from_db()
        assert org_a.modulos_ocultos == []

    def test_lo_que_oculta_una_empresa_no_lo_ve_la_otra(
        self, admin_client, org_b_client, org_b
    ):
        assert admin_client.patch(
            URL, {"modulos_ocultos": ["goals"]}, format="json"
        ).status_code == 200
        assert org_b_client.get(URL).json()["modulos_ocultos"] == []
        assert Org.objects.get(pk=org_b.pk).modulos_ocultos == []
