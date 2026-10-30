"""
================================================================================
 MI DIA  --  29/10/2026
================================================================================
`GET /api/campo/mi-dia/`: con que cuadrilla y que labor sale hoy el tecnico.
Pedido del usuario: que Inicio salude «Hola, Mario · tu labor para hoy es …» y
que «se actualice según esté en la plataforma de Dexter».

  L  quien sale con una cuadrilla hoy recibe su labor, la cuadrilla y las zonas
  N  quien no sale con ninguna recibe la clave en null, no un 404 ni nada;
     y la cuadrilla de otro no es la suya
  C  si Programacion cambia la labor, la respuesta cambia
  F  una jornada de otro dia no cuenta, y el dia es el de la empresa (a hora
     fija: a las 21:00 de Bogota en UTC ya es mañana)
  A  la jornada de otra empresa no se ve

    pytest campo/tests/test_mi_dia.py
================================================================================
"""
import datetime as dt
import zoneinfo

import pytest
from django.utils import timezone

from campo.cuadrillas import (
    Cuadrilla,
    IntegranteDeJornada,
    JornadaDeCuadrilla,
    PersonaDeCampo,
)
from campo.zonas import ZonaOperativa

pytestmark = pytest.mark.django_db

URL = "/api/campo/mi-dia/"
BOGOTA = zoneinfo.ZoneInfo("America/Bogota")


def _hoy():
    return timezone.now().astimezone(BOGOTA).date()


@pytest.fixture
def org(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    return org_a


def _jornada(org, profile, *, fecha, labor=JornadaDeCuadrilla.INSTALACION,
             nombre="Cuadrilla #1", zonas=("Norte",)):
    c = Cuadrilla.objects.create(org=org, nombre=nombre)
    j = JornadaDeCuadrilla.objects.create(org=org, cuadrilla=c, fecha=fecha, labor=labor)
    j.zonas.set([ZonaOperativa.objects.get_or_create(org=org, nombre=z)[0] for z in zonas])
    persona, _ = PersonaDeCampo.objects.get_or_create(org=org, profile=profile,
                                                     defaults={"nombre": "Mario"})
    IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona, rol="tecnico")
    return j


def test_l_quien_sale_hoy_recibe_su_labor_su_cuadrilla_y_sus_zonas(
        user_client, org, user_profile):
    _jornada(org, user_profile, fecha=_hoy(), zonas=("Soledad zona 2", "Norte"))

    r = user_client.get(URL).json()

    assert r["fecha"] == _hoy().isoformat()
    assert r["jornada"] == {"cuadrilla": "Cuadrilla #1", "labor": "instalacion",
                            "labor_nombre": "Instalacion",
                            "zonas": ["Norte", "Soledad zona 2"]}


def test_n_quien_no_sale_con_ninguna_recibe_null_y_no_un_error(user_client, org):
    r = user_client.get(URL)

    assert r.status_code == 200
    assert "jornada" in r.json() and r.json()["jornada"] is None


def test_n2_la_cuadrilla_de_otro_no_es_la_mia(user_client, org, admin_profile):
    """Hay jornada hoy, pero el tecnico no sale con ella: no se le atribuye."""
    _jornada(org, admin_profile, fecha=_hoy())

    assert user_client.get(URL).json()["jornada"] is None


def test_c_si_programacion_cambia_la_labor_la_respuesta_cambia(
        user_client, org, user_profile):
    j = _jornada(org, user_profile, fecha=_hoy())
    assert user_client.get(URL).json()["jornada"]["labor"] == "instalacion"

    j.labor = JornadaDeCuadrilla.CORRECTIVO
    j.save(update_fields=["labor"])

    assert user_client.get(URL).json()["jornada"]["labor"] == "correctivo"


def test_f_la_jornada_de_ayer_o_de_manana_no_cuenta(user_client, org, user_profile):
    _jornada(org, user_profile, fecha=_hoy() - dt.timedelta(days=1), nombre="Ayer")
    _jornada(org, user_profile, fecha=_hoy() + dt.timedelta(days=1), nombre="Mañana")

    assert user_client.get(URL).json()["jornada"] is None


def test_f2_a_las_nueve_de_la_noche_sigue_siendo_hoy(user_client, org, user_profile):
    """El servidor corre en UTC: a las 21:00 de Bogota alla ya es mañana. La
    jornada de hoy tiene que seguir siendo la de hoy. Hora FIJA: con el reloj
    de verdad esta prueba solo distinguiria de noche."""
    from types import SimpleNamespace
    from unittest import mock

    noche = dt.datetime(2026, 10, 29, 21, 0, tzinfo=BOGOTA)
    _jornada(org, user_profile, fecha=noche.date())
    reloj = SimpleNamespace(now=lambda: noche.astimezone(dt.timezone.utc))
    with mock.patch("campo.views.timezone", reloj):
        r = user_client.get(URL).json()

    assert r["fecha"] == "2026-10-29"
    assert r["jornada"] is not None


def test_a_la_jornada_de_otra_empresa_no_se_ve(org_b_client, org, user_profile):
    _jornada(org, user_profile, fecha=_hoy())

    assert org_b_client.get(URL).json()["jornada"] is None
