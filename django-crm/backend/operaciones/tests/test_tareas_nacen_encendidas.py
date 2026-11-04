"""
Una empresa nueva nace con las tareas no criticas del Supervisor encendidas
(04/11/2026, PRD §1, §2 y §8.18).

El objetivo del producto es reemplazar la mano de obra; una persona solo en lo
critico. Hasta hoy cada una de las diez tareas nacia apagada y alguien tenia
que encenderla, una por una. Ahora, al dar de alta una empresa, las que no son
criticas quedan delegadas a nombre de quien la creo -- delegar exige una
persona: el Supervisor no se da trabajo a si mismo --. Encendida no es
actuando: siguen el nivel, el interruptor y la frontera del motor.

Lo que se afirma es el EFECTO, por la ruta real de alta (POST /api/org/).
"""

import pytest

from common.models import Org, Profile
from operaciones import tareas_delegadas as td
from operaciones.tareas_modelos import TareaDelegada

URL = "/api/org/"


@pytest.fixture(autouse=True)
def _autorregistro_abierto(settings):
    """Mismo criterio que common/tests/test_organizations.py: se prueba la
    mecanica del alta con un ADMIN comun."""
    settings.PERMITIR_AUTORREGISTRO = True


def _activas(org):
    return set(TareaDelegada.objects.filter(org=org, activa=True).values_list("clave", flat=True))


def test_toda_tarea_del_catalogo_dice_si_es_critica():
    #  Sin la marca, la tarea quedaria a merced de un default. Una nueva que
    #  mueva dinero tiene que poder decir que es critica y nacer apagada.
    sin_marca = [c for c, t in td.CATALOGO.items() if "critica" not in t]
    assert sin_marca == []


@pytest.mark.django_db
def test_una_empresa_nueva_nace_con_las_no_criticas_encendidas(admin_client, admin_user):
    r = admin_client.post(URL, {"name": "ISP Nuevo"}, format="json")
    assert r.status_code == 200
    org = Org.objects.get(name="ISP Nuevo")
    perfil = Profile.objects.get(user=admin_user, org=org)
    esperadas = {c for c, t in td.CATALOGO.items() if not t["critica"]}
    assert esperadas, "el catalogo tiene que tener alguna no critica para que esto mida algo"
    assert _activas(org) == esperadas
    assert set(TareaDelegada.objects.filter(org=org).values_list("delegada_por_id", flat=True)) == {perfil.id}


@pytest.mark.django_db
def test_una_critica_nace_apagada(admin_client, monkeypatch):
    clave = next(iter(td.CATALOGO))
    catalogo = {c: dict(t) for c, t in td.CATALOGO.items()}
    catalogo[clave]["critica"] = True
    monkeypatch.setattr(td, "CATALOGO", catalogo)
    admin_client.post(URL, {"name": "ISP Con Critica"}, format="json")
    org = Org.objects.get(name="ISP Con Critica")
    assert clave not in _activas(org)
    assert _activas(org)  # las demas si


@pytest.mark.django_db
def test_si_no_se_pueden_encender_la_empresa_igual_se_crea(admin_client, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("la base no contesta")

    monkeypatch.setattr(td, "delegar", falla)
    r = admin_client.post(URL, {"name": "ISP Sin Tareas"}, format="json")
    assert r.status_code == 200
    org = Org.objects.get(name="ISP Sin Tareas")
    assert _activas(org) == set()


@pytest.mark.django_db
def test_una_empresa_existente_no_cambia(admin_client, org_a):
    #  Encenderlas es del ALTA: una empresa que ya opera no ve encenderse nada
    #  por un despliegue. Lo suyo lo decide su gente en Ajustes del Supervisor.
    antes = _activas(org_a)
    admin_client.post(URL, {"name": "Otra Empresa"}, format="json")
    assert _activas(org_a) == antes
