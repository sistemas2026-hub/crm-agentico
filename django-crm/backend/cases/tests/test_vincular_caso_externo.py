"""
UN CASO CREADO EN DEXTER QUEDA ATADO AL TICKET QUE SE LE CREO EN WISPHUB.

Un ticket creado desde "Nuevo ticket" nace aca y despues en el proveedor. Sin
la identidad del ticket, la importacion no lo reconoce y la proxima vuelta lo
traeria como un caso NUEVO. La prueba que importa es la ultima: una vez atado,
la importacion lo cuenta como conocido.

Run with: pytest cases/tests/test_vincular_caso_externo.py -v
"""

import pytest

from cases.models import EXTERNAL_AUTHOR_DEXTER, Case

CONOCIDOS = "/api/importacion/tickets-conocidos/"


def _url(caso):
    return f"/api/importacion/casos/{caso.pk}/vincular/"


def _caso(org, autor, nombre="Sin internet", **extra):
    return Case.objects.create(name=nombre, status="New", priority="Normal",
                               org=org, created_by=autor, **extra)


def _cuerpo(ticket="95001", **extra):
    return {"provider": "wisphub", "external_ticket_id": ticket,
            "external_service_id": "5832", "area": "soporte_tecnico", **extra}


@pytest.mark.django_db
class TestVincular:
    def test_ata_el_caso_y_la_importacion_lo_ve_como_conocido(
        self, admin_client, org_a, admin_user
    ):
        caso = _caso(org_a, admin_user)
        r = admin_client.post(_url(caso), _cuerpo(), format="json")
        assert r.status_code == 200, r.content
        assert r.json() == {"vinculado": True, "ya_estaba": False}
        caso.refresh_from_db()
        assert (caso.provider, caso.external_ticket_id, caso.external_service_id) == (
            "wisphub", "95001", "5832")
        assert caso.external_created_by_type == EXTERNAL_AUTHOR_DEXTER
        assert caso.area == "soporte_tecnico"
        #  EL EFECTO: la importacion ya no lo trae como un caso nuevo.
        c = admin_client.get(CONOCIDOS, {"provider": "wisphub", "ids": "95001"})
        assert c.status_code == 200
        assert c.json()["con_caso"] == ["95001"]

    def test_repetir_el_mismo_vinculo_es_un_200(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user)
        admin_client.post(_url(caso), _cuerpo(), format="json")
        r = admin_client.post(_url(caso), _cuerpo(), format="json")
        assert r.status_code == 200
        assert r.json()["ya_estaba"] is True

    def test_no_pisa_un_caso_atado_a_otro_ticket(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user)
        admin_client.post(_url(caso), _cuerpo("95001"), format="json")
        r = admin_client.post(_url(caso), _cuerpo("95002"), format="json")
        assert r.status_code == 409
        assert r.json()["error"] == "CASO_YA_VINCULADO"
        caso.refresh_from_db()
        assert caso.external_ticket_id == "95001"

    def test_un_ticket_no_tiene_dos_casos(self, admin_client, org_a, admin_user):
        uno = _caso(org_a, admin_user, "Uno")
        otro = _caso(org_a, admin_user, "Otro")
        admin_client.post(_url(uno), _cuerpo("95001"), format="json")
        r = admin_client.post(_url(otro), _cuerpo("95001"), format="json")
        assert r.status_code == 409
        assert r.json()["error"] == "TICKET_YA_TIENE_CASO"
        otro.refresh_from_db()
        assert otro.provider == ""

    def test_no_pisa_el_area_que_el_caso_ya_tiene(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user, area="cartera")
        admin_client.post(_url(caso), _cuerpo(), format="json")
        caso.refresh_from_db()
        assert caso.area == "cartera"

    def test_faltan_datos_o_sobran_campos(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user)
        r = admin_client.post(_url(caso), {"provider": "wisphub"}, format="json")
        assert r.status_code == 400
        r = admin_client.post(_url(caso), _cuerpo(status="Closed"), format="json")
        assert r.status_code == 400
        assert r.json()["error"] == "CAMPO_NO_PERMITIDO"
        caso.refresh_from_db()
        assert caso.provider == "" and caso.status == "New"

    def test_quien_no_administra_no_ata_nada(self, user_client, org_a, admin_user):
        caso = _caso(org_a, admin_user)
        r = user_client.post(_url(caso), _cuerpo(), format="json")
        assert r.status_code == 403
        caso.refresh_from_db()
        assert caso.provider == ""
