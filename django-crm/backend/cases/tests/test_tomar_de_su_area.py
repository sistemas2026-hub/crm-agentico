"""
UN COLABORADOR VE Y TOMA LO SIN ASIGNAR DE SU AREA, Y NADA MAS.

Desde el 24/10/2026 un colaborador (USER) ve, ademas de lo suyo, los tickets
SIN RESPONSABLE cuya area escrita es la suya, y puede tomarlos -- asignarselos
a si mismo -- por POST /api/cases/<id>/tomar/. Ver ese ticket no le deja
editarlo ni asignarselo a otro: tomar es la unica escritura nueva.

Se afirma el EFECTO en las dos direcciones, porque una prueba que solo mirara
el caso positivo seguiria verde con la regla abierta para todos:

* ve y toma lo de su area; no ve ni toma lo de otra area, lo que ya tiene
  responsable, ni lo que no tiene area escrita;
* dos que toman el mismo: el segundo recibe 409 y no queda con dos;
* sin saber el area (el motor no contesta) vuelve a ver solo lo suyo;
* cada organizacion lee las areas de SU empresa, no las de MOTOR_TENANT;
* POST /assignees/ ya no deja a quien solo VE sumar a cualquiera.

Run with: pytest cases/tests/test_tomar_de_su_area.py -v
"""

import pytest
from django.core.cache import cache
from rest_framework import status

from cases.models import Case, CaseWatcher
from cases.tests.conftest import _set_rls
from common.models import Profile, User
from conftest import _make_authenticated_client
from operaciones import areas_del_tenant

CASES_URL = "/api/cases/"

#  La funcion real, tomada al importar: el conftest raiz la reemplaza por un
#  mapa vacio en cada prueba para que nadie salga a la red.
_AREAS_DE_ORG = areas_del_tenant.area_por_persona_de_org


def _cliente(org, rol, email):
    user = User.objects.create_user(email=email, password="testpass123")
    perfil = Profile.objects.create(user=user, org=org, role=rol, is_active=True)
    return _make_authenticated_client(user, org, perfil), perfil


def _caso(org, creador, area, nombre):
    return Case.objects.create(
        name=nombre, status="New", priority="High", case_type="Bug",
        created_by=creador, org=org, area=area,
    )


def _ids(resp):
    return {c["id"] for c in resp.data.get("cases", [])}


@pytest.fixture
def mapa(monkeypatch):
    """El mapa persona -> area que serviria el motor. Vacio = no contesto."""
    actual = {}
    monkeypatch.setattr(areas_del_tenant, "area_por_persona_de_org",
                        lambda org_id: dict(actual))
    return actual


@pytest.fixture
def tecnico(org_a, mapa):
    cliente, perfil = _cliente(org_a, "USER", "tecnico@test.com")
    mapa[str(perfil.id)] = "soporte_tecnico"
    return cliente, perfil


@pytest.fixture
def casos(org_a, admin_user, admin_profile):
    return {
        "soporte": _caso(org_a, admin_user, "soporte_tecnico", "Sin internet"),
        # Mayusculas y espacios alrededor no son otra area.
        "soporte_grafia": _caso(org_a, admin_user, " Soporte_Tecnico ", "Lento"),
        "cartera": _caso(org_a, admin_user, "cartera", "Descuento programado"),
        "sin_area": _caso(org_a, admin_user, "", "Sin clasificar"),
    }


@pytest.mark.django_db
class TestVeLoSinAsignarDeSuArea:
    def test_ve_lo_de_su_area_y_no_lo_ajeno(self, tecnico, casos):
        cliente, _ = tecnico
        vistos = _ids(cliente.get(CASES_URL))
        assert str(casos["soporte"].id) in vistos
        assert str(casos["soporte_grafia"].id) in vistos
        assert str(casos["cartera"].id) not in vistos
        assert str(casos["sin_area"].id) not in vistos

    def test_lo_abre_pero_no_lo_edita_sin_tomarlo(self, tecnico, casos):
        cliente, _ = tecnico
        url = f"{CASES_URL}{casos['soporte'].id}/"
        assert cliente.get(url).status_code == status.HTTP_200_OK
        r = cliente.patch(url, {"priority": "Low"}, format="json")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        casos["soporte"].refresh_from_db()
        assert casos["soporte"].priority == "High"

    def test_lo_de_su_area_con_responsable_no_lo_ve(self, tecnico, casos, user_profile):
        cliente, _ = tecnico
        casos["soporte"].assigned_to.add(user_profile)
        assert str(casos["soporte"].id) not in _ids(cliente.get(CASES_URL))
        url = f"{CASES_URL}{casos['soporte'].id}/"
        assert cliente.get(url).status_code == status.HTTP_403_FORBIDDEN

    def test_sin_saber_su_area_ve_solo_lo_suyo(self, tecnico, casos, mapa):
        cliente, _ = tecnico
        mapa.clear()  # el motor no contesto
        assert _ids(cliente.get(CASES_URL)) == set()
        url = f"{CASES_URL}{casos['soporte'].id}/"
        assert cliente.get(url).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTomar:
    def test_toma_lo_de_su_area(self, tecnico, casos):
        cliente, perfil = tecnico
        r = cliente.post(f"{CASES_URL}{casos['soporte'].id}/tomar/")
        assert r.status_code == status.HTTP_200_OK
        assert list(casos["soporte"].assigned_to.values_list("id", flat=True)) == [perfil.id]
        # Ya es responsable: escribe como cualquiera.
        r = cliente.patch(f"{CASES_URL}{casos['soporte'].id}/", {"priority": "Low"},
                          format="json")
        assert r.status_code == status.HTTP_200_OK

    @pytest.mark.parametrize("cual", ["cartera", "sin_area"])
    def test_no_toma_lo_que_no_es_de_su_area(self, tecnico, casos, cual):
        cliente, _ = tecnico
        r = cliente.post(f"{CASES_URL}{casos[cual].id}/tomar/")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert not casos[cual].assigned_to.exists()

    def test_el_segundo_que_toma_recibe_409_y_no_queda_con_dos(
        self, tecnico, casos, org_a, mapa
    ):
        cliente, perfil = tecnico
        otro, perfil_otro = _cliente(org_a, "USER", "otro@test.com")
        mapa[str(perfil_otro.id)] = "soporte_tecnico"
        url = f"{CASES_URL}{casos['soporte'].id}/tomar/"
        assert cliente.post(url).status_code == status.HTTP_200_OK
        r = otro.post(url)
        assert r.status_code == status.HTTP_409_CONFLICT
        assert r.data["codigo"] == "YA_TIENE_RESPONSABLE"
        assert list(casos["soporte"].assigned_to.values_list("id", flat=True)) == [perfil.id]

    def test_sin_saber_su_area_no_toma_nada(self, tecnico, casos, mapa):
        cliente, _ = tecnico
        mapa.clear()
        r = cliente.post(f"{CASES_URL}{casos['soporte'].id}/tomar/")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert not casos["soporte"].assigned_to.exists()

    @pytest.mark.parametrize("rol", ["SUPERVISOR", "OPERACIONES"])
    def test_quien_reparte_toma_cualquiera_sin_responsable(self, org_a, casos, mapa, rol):
        cliente, perfil = _cliente(org_a, rol, f"{rol.lower()}@test.com")
        r = cliente.post(f"{CASES_URL}{casos['sin_area'].id}/tomar/")
        assert r.status_code == status.HTTP_200_OK
        assert list(casos["sin_area"].assigned_to.values_list("id", flat=True)) == [perfil.id]

    def test_quien_lo_creo_lo_toma_aunque_no_sea_de_su_area(self, org_a, mapa):
        cliente, perfil = _cliente(org_a, "USER", "creador@test.com")
        propio = _caso(org_a, perfil.user, "cartera", "Lo abri yo")
        r = cliente.post(f"{CASES_URL}{propio.id}/tomar/")
        assert r.status_code == status.HTTP_200_OK
        assert list(propio.assigned_to.values_list("id", flat=True)) == [perfil.id]

    def test_un_caso_de_otra_organizacion_es_404(self, tecnico, org_a, org_b):
        cliente, _ = tecnico
        _set_rls(org_b)
        ajeno = Case.objects.create(name="De otra empresa", status="New", priority="High",
                                    case_type="Bug", org=org_b, area="soporte_tecnico")
        _set_rls(org_a)
        r = cliente.post(f"{CASES_URL}{ajeno.id}/tomar/")
        assert r.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestAgregarExigeEscribir:
    def test_quien_solo_ve_no_suma_a_nadie(self, tecnico, casos, user_profile):
        cliente, _ = tecnico
        r = cliente.post(f"{CASES_URL}{casos['soporte'].id}/assignees/",
                         {"profile_id": str(user_profile.id)}, format="json")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert not casos["soporte"].assigned_to.exists()

    def test_quien_sigue_un_ticket_no_suma_a_nadie(self, org_a, casos, user_profile, mapa):
        cliente, perfil = _cliente(org_a, "USER", "seguidor@test.com")
        CaseWatcher.objects.create(case=casos["cartera"], profile=perfil, org=org_a,
                                   subscribed_via="manual")
        r = cliente.post(f"{CASES_URL}{casos['cartera'].id}/assignees/",
                         {"profile_id": str(user_profile.id)}, format="json")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert not casos["cartera"].assigned_to.exists()


class _Resp:
    def __init__(self, codigo, cuerpo):
        self.status_code = codigo
        self.ok = 200 <= codigo < 300
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


@pytest.mark.django_db
class TestCadaOrganizacionLeeSuEmpresa:
    def test_las_areas_salen_de_la_empresa_de_la_organizacion(self, monkeypatch):
        """Con MOTOR_TENANT apuntando a una, cada organizacion lee la suya. Una
        clave de cache unica para todas le serviria a la segunda el mapa de la
        primera."""
        cache.clear()
        monkeypatch.setenv("MOTOR_TENANT", "empresa_uno")
        tenants = {"org-1": "empresa_uno", "org-2": "empresa_dos"}
        mapas = {"empresa_uno": {"p1": "soporte_tecnico"},
                 "empresa_dos": {"p2": "cartera"}}

        def falso_get(url, params=None, **kw):
            if "/tenant-de-organizacion/" in url:
                org = url.rsplit("/", 1)[-1]
                if org in tenants:
                    return _Resp(200, {"tenant": tenants[org]})
                return _Resp(404, {"error": "SIN_TENANT"})
            return _Resp(200, {"areas_por_persona": mapas[params["tenant"]]})

        monkeypatch.setattr(areas_del_tenant.requests, "get", falso_get)
        assert _AREAS_DE_ORG("org-1") == {"p1": "soporte_tecnico"}
        assert _AREAS_DE_ORG("org-2") == {"p2": "cartera"}
        # Sin empresa configurada no hay default: ni MOTOR_TENANT.
        assert _AREAS_DE_ORG("org-3") == {}

    def test_si_el_motor_no_contesta_no_se_sabe(self, monkeypatch):
        cache.clear()

        def roto(*a, **kw):
            raise ConnectionError("motor caido")

        monkeypatch.setattr(areas_del_tenant.requests, "get", roto)
        assert areas_del_tenant.tenant_de_organizacion("org-1") == ""
        assert _AREAS_DE_ORG("org-1") == {}
