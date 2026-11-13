# -*- coding: utf-8 -*-
"""
================================================================================
 AL DESPACHAR SE VE LA ZONA Y QUE CUADRILLA LA CUBRE, Y SE ASIGNA A ESA CUADRILLA
================================================================================

Correccion del usuario (13/10/2026): «el supervisor en el momento de despachar
debe tener claro la zona del ticket para ver a que cuadrilla asignarlo». Hasta
ahi se veia el barrio y no la zona, y «Asignar a» listaba tecnicos sueltos de
toda la empresa.

  A  cobertura: barrio -> zona -> las cuadrillas de ESE dia con ESA labor
  B  si la cubren con otra labor, o nadie, lo dice -- y quien la trabaja
     habitualmente
  C  un barrio fuera de toda zona trae los parecidos
  D  crear la orden con la cuadrilla la asigna a su gente CON CUENTA, el lider
     como principal, y el reparto la respeta despues
  E  una cuadrilla sin lider, o un tecnico que no existe, se
     rechazan ANTES de crear: antes la orden quedaba creada y la respuesta
     decia error, y un reintento creaba otra
  F  la cuadrilla real -- un lider con celular y un auxiliar sin el --: la
     recibe el lider del dia (o el de la cuadrilla) aunque no este anotado
     entre los integrantes (correccion del usuario, 15/10/2026)

    pytest campo/tests/test_cobertura_al_despachar.py
================================================================================
"""

import datetime as dt

import pytest

from campo import reparto
from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada, JornadaDeCuadrilla,
                              PersonaDeCampo)
from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

HOY = dt.date(2026, 10, 14)
COBERTURA = "/api/campo/despacho/cobertura/"
CREAR = "/api/campo/trabajos/crear/"


@pytest.fixture
def norte(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="CACARAMOA")
    return z


@pytest.fixture
def cuadrilla(org_a, admin_profile, norte):
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1",
                                 lider=admin_profile, labor_habitual="correctivo")
    c.zonas_habituales.set([norte])
    return c


def _jornada(org, cuadrilla, zona, labor, *, lider_profile=None, con_aux=True):
    j = JornadaDeCuadrilla.objects.create(org=org, cuadrilla=cuadrilla,
                                          fecha=HOY, labor=labor)
    j.zonas.set([zona])
    if lider_profile is not None:
        lider = PersonaDeCampo.objects.create(org=org, nombre="La Lider",
                                              profile=lider_profile)
        IntegranteDeJornada.objects.create(org=org, jornada=j, persona=lider,
                                           rol="tecnico_lider")
    if con_aux:
        aux = PersonaDeCampo.objects.create(org=org, nombre="Pedro Ayudante")
        IntegranteDeJornada.objects.create(org=org, jornada=j, persona=aux,
                                           rol="ayudante")
    return j


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="correctivo_fibra",
                                 nombre="Correctivo", labor="correctivo")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})


def test_a_cubierta_con_su_gente(org_a, norte, cuadrilla, admin_profile):
    _jornada(org_a, cuadrilla, norte, "correctivo", lider_profile=admin_profile)
    c = reparto.cobertura(org_a, "cacaramoa", HOY, "correctivo")
    assert c["motivo"] == "cubierta"
    assert c["zona"]["nombre"] == "Norte"
    j = c["jornadas"][0]
    assert j["cuadrilla"] == "Cuadrilla 1" and j["coincide_labor"]
    assert [p["profile"] for p in j["con_cuenta"]] == [str(admin_profile.id)]
    assert j["sin_cuenta"] == 1                     # el ayudante va, pero no recibe


def test_b_otra_labor_o_nadie_lo_dice(org_a, norte, cuadrilla, admin_profile):
    assert reparto.cobertura(org_a, "CACARAMOA", HOY, "correctivo")["motivo"] == "sin_jornada"
    c = reparto.cobertura(org_a, "CACARAMOA", HOY, "correctivo")
    assert [h["cuadrilla"] for h in c["habituales"]] == ["Cuadrilla 1"]

    _jornada(org_a, cuadrilla, norte, "instalacion", lider_profile=admin_profile)
    assert reparto.cobertura(org_a, "CACARAMOA", HOY, "correctivo")["motivo"] == "otra_labor"


def test_c_fuera_de_toda_zona_trae_parecidos(org_a, norte):
    c = reparto.cobertura(org_a, "CACARMOA", HOY, "correctivo")
    assert c["motivo"] == "sin_zona"
    assert c["parecidas"][0]["localidad"] == "CACARAMOA"


def test_c2_el_endpoint(admin_client, org_a, norte, cuadrilla, admin_profile):
    _jornada(org_a, cuadrilla, norte, "correctivo", lider_profile=admin_profile)
    r = admin_client.get(f"{COBERTURA}?barrio=CACARAMOA&fecha={HOY}&labor=correctivo")
    assert r.status_code == 200, r.content
    assert r.json()["motivo"] == "cubierta"
    assert r.json()["fecha"] == HOY.isoformat()


def test_d_crear_con_la_cuadrilla_la_asigna_a_su_gente_y_el_reparto_la_respeta(
        admin_client, org_a, norte, cuadrilla, admin_profile, version):
    j = _jornada(org_a, cuadrilla, norte, "correctivo", lider_profile=admin_profile)
    r = admin_client.post(CREAR, {"work_type_version_id": str(version.id),
                                  "zona": "CACARAMOA", "jornada_id": str(j.id)},
                          format="json")
    assert r.status_code == 201, r.content
    orden = OrdenTrabajo.objects.get(org=org_a)
    asignados = list(orden.asignaciones.values_list("profile_id", "es_principal"))
    assert asignados == [(admin_profile.id, True)]   # el ayudante sin cuenta, no
    assert orden in reparto.proponer(org_a, HOY)["a_mano"]


def test_e_cuadrilla_sin_lider_se_rechaza_antes_de_crear(
        admin_client, org_a, norte, cuadrilla, version):
    cuadrilla.lider = None
    cuadrilla.save(update_fields=["lider"])
    j = _jornada(org_a, cuadrilla, norte, "correctivo")       # solo el ayudante
    r = admin_client.post(CREAR, {"work_type_version_id": str(version.id),
                                  "zona": "CACARAMOA", "jornada_id": str(j.id)},
                          format="json")
    assert r.status_code == 400, r.content
    assert "no tiene líder" in r.json()["detalle"]
    assert not OrdenTrabajo.objects.filter(org=org_a).exists()


def test_f_el_lider_del_dia_recibe_aunque_solo_el_auxiliar_este_anotado(
        admin_client, org_a, norte, cuadrilla, admin_profile, version):
    """La cuadrilla real (15/10/2026): el lider con celular, elegido en «Lider
    del dia», y el auxiliar sin cuenta como unico integrante. Antes: «no tiene
    a nadie con cuenta» y la orden no se creaba."""
    j = _jornada(org_a, cuadrilla, norte, "correctivo")       # solo el ayudante
    j.lider = admin_profile
    j.save(update_fields=["lider"])

    c = reparto.cobertura(org_a, "CACARAMOA", HOY, "correctivo")
    cj = c["jornadas"][0]
    assert [p["profile"] for p in cj["con_cuenta"]] == [str(admin_profile.id)]
    assert cj["con_cuenta"][0]["lider"] is True
    assert cj["van_con_el"] == ["Pedro Ayudante"] and cj["aviso"] is None

    r = admin_client.post(CREAR, {"work_type_version_id": str(version.id),
                                  "zona": "CACARAMOA", "jornada_id": str(j.id)},
                          format="json")
    assert r.status_code == 201, r.content
    orden = OrdenTrabajo.objects.get(org=org_a)
    assert list(orden.asignaciones.values_list("profile_id", "es_principal", "rol"))         == [(admin_profile.id, True, "tecnico_lider")]


def test_f2_sin_lider_del_dia_vale_el_de_la_cuadrilla(
        admin_client, org_a, norte, cuadrilla, admin_profile, version):
    j = _jornada(org_a, cuadrilla, norte, "correctivo")       # jornada.lider vacio
    assert j.lider_id is None and cuadrilla.lider_id == admin_profile.id
    r = admin_client.post(CREAR, {"work_type_version_id": str(version.id),
                                  "zona": "CACARAMOA", "jornada_id": str(j.id)},
                          format="json")
    assert r.status_code == 201, r.content
    assert list(OrdenTrabajo.objects.get(org=org_a).asignaciones
                .values_list("profile_id", flat=True)) == [admin_profile.id]


def test_f3_un_lider_con_la_cuenta_de_baja_no_recibe_y_se_dice(
        admin_client, org_a, norte, cuadrilla, user_profile, version):
    user_profile.is_active = False
    user_profile.save(update_fields=["is_active"])
    j = _jornada(org_a, cuadrilla, norte, "correctivo")
    j.lider = user_profile
    j.save(update_fields=["lider"])

    cj = reparto.cobertura(org_a, "CACARAMOA", HOY, "correctivo")["jornadas"][0]
    assert cj["con_cuenta"] == [] and "dada de baja" in cj["aviso"]
    r = admin_client.post(CREAR, {"work_type_version_id": str(version.id),
                                  "zona": "CACARAMOA", "jornada_id": str(j.id)},
                          format="json")
    assert r.status_code == 400 and "dada de baja" in r.json()["detalle"]
    assert not OrdenTrabajo.objects.filter(org=org_a).exists()


def test_e2_un_tecnico_que_no_existe_tampoco_deja_la_orden_creada(
        admin_client, org_a, version):
    r = admin_client.post(CREAR, {"work_type_version_id": str(version.id),
                                  "zona": "CACARAMOA",
                                  "tecnico_profile_id": "00000000-0000-0000-0000-000000000000"},
                          format="json")
    assert r.status_code == 404
    assert not OrdenTrabajo.objects.filter(org=org_a).exists()
