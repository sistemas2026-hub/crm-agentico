# -*- coding: utf-8 -*-
"""
================================================================================
 ASIGNAR A MANO, Y QUE EL REPARTO LO RESPETE
================================================================================

Pedido del usuario (13/10/2026): poder elegir el tecnico al despachar, y que una
orden sin nadie no diga «Asignada».

  A  crear la orden con un tecnico la deja asignada a el (por el endpoint real)
  B  el REPARTO no la toca: queda afuera de todas sus listas y se nombra en
     `a_mano`. Antes la reasignaba en la siguiente publicacion.
  C  una orden SIN asignar sigue entrando al reparto como siempre
  D  si despues el reparto la movio, vuelve a ser libre
  E  Despacho dice a quien la tiene la orden viva del caso, o que no la tiene
     nadie

    pytest campo/tests/test_asignar_a_mano.py
================================================================================
"""

import datetime as dt

import pytest

from campo import reparto
from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)

pytestmark = pytest.mark.django_db

CREAR = "/api/campo/trabajos/crear/"
CASOS = "/api/campo/casos-despachables/"
HOY = dt.date(2026, 10, 13)


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="correctivo_fibra",
                                 nombre="Correctivo", labor="correctivo")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})


def _crear(cliente, version, **extra):
    return cliente.post(CREAR, {"work_type_version_id": str(version.id),
                                "zona": "BARRIO SIN MAPEAR", **extra},
                        format="json")


def _en_alguna_lista(propuesta, orden):
    listas = [o for a in propuesta["asignaciones"] for o in a["ordenes"]]
    for clave in ("sin_zona", "sin_cuadrilla", "sobrantes", "sin_clasificar"):
        listas += list(propuesta.get(clave) or [])
    return orden in listas


def test_a_b_asignada_a_mano_no_la_toca_el_reparto(
        admin_client, org_a, version, user_profile):
    r = _crear(admin_client, version, tecnico_profile_id=str(user_profile.id))
    assert r.status_code == 201, r.content
    assert r.json()["orden"]["tecnico_principal"]["id"] == str(user_profile.id)

    orden = OrdenTrabajo.objects.get(org=org_a)
    propuesta = reparto.proponer(org_a, HOY)
    assert orden in propuesta["a_mano"]
    assert not _en_alguna_lista(propuesta, orden)


def test_c_sin_asignar_sigue_entrando_al_reparto(admin_client, org_a, version):
    _crear(admin_client, version)
    orden = OrdenTrabajo.objects.get(org=org_a)
    assert not orden.asignaciones.exists()
    propuesta = reparto.proponer(org_a, HOY)
    assert orden not in propuesta["a_mano"]
    assert _en_alguna_lista(propuesta, orden)       # sin_zona: el barrio no se mapeo


def test_d_si_despues_la_movio_el_reparto_vuelve_a_ser_libre(
        admin_client, org_a, version, user_profile):
    _crear(admin_client, version, tecnico_profile_id=str(user_profile.id))
    orden = OrdenTrabajo.objects.get(org=org_a)
    EventoTrabajo.objects.create(org=org_a, orden=orden,
                                 tipo="reasignada_por_reparto", datos={})
    propuesta = reparto.proponer(org_a, HOY)
    assert orden not in propuesta["a_mano"]
    assert _en_alguna_lista(propuesta, orden)


def test_d2_manual_pero_hoy_sin_nadie_no_se_respeta(
        admin_client, org_a, version, user_profile):
    """Una manual que despues quedo sin nadie no tiene a quien respetar."""
    _crear(admin_client, version, tecnico_profile_id=str(user_profile.id))
    orden = OrdenTrabajo.objects.get(org=org_a)
    AsignacionTrabajo.objects.filter(orden=orden).delete()
    assert orden not in reparto.proponer(org_a, HOY)["a_mano"]


def _aprobado(org):
    from cases.models import Case
    from operaciones.models import PropuestaSupervisor

    caso = Case.objects.create(org=org, name="Sin internet", status="New",
                               priority="Normal", is_active=True)
    PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.CASO_REQUIERE_VISITA,
        origen_tipo="case", origen_id=str(caso.id),
        estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[{"fuente": "equipo", "dato": "caido por fibra",
                    "momento": "2026-10-13T03:00:00Z"}])
    return caso


def test_e_despacho_dice_si_la_orden_viva_no_la_tiene_nadie(
        admin_client, org_a, version, user_profile, monkeypatch):
    monkeypatch.setattr("campo.despacho_views.contexto_del_caso", lambda c: {})
    caso = _aprobado(org_a)
    _crear(admin_client, version, case_id=str(caso.id))
    fila = admin_client.get(CASOS).json()["casos"][0]
    assert fila["orden_activa"] is not None
    assert fila["orden_activa_tecnico"] is None           # SIN ASIGNAR

    orden = OrdenTrabajo.objects.get(org=org_a)
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    #  Con tecnico sale de la lista por defecto: esta en Programacion
    #  (28/10/2026). Se cuenta, y pidiendolo se ve con su nombre.
    d = admin_client.get(CASOS).json()
    assert d["casos"] == [] and d["con_tecnico"] == 1
    fila = admin_client.get(CASOS, {"con_tecnico": "1"}).json()["casos"][0]
    assert fila["orden_activa_tecnico"]                    # su nombre
