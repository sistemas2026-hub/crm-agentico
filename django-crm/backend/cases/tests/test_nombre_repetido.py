# -*- coding: utf-8 -*-
"""Dos casos pueden llamarse igual, y uno repetido se puede editar.

EL DEFECTO, MEDIDO EN PRODUCCION EL 07/10/2026
-----------------------------------------------
Cambiarle el responsable a un ticket importado contestaba::

    name: Case already exists with this name

por un campo que el formulario ni habia tocado. 'CaseSerializer.validate_name'
rechazaba cualquier nombre ya usado en la organizacion -- la regla de
'accounts', donde una cuenta SI es unica por nombre, copiada a un caso, que es
un INCIDENTE.

Los tickets importados usan el asunto de WispHub como nombre, asi que los
repetidos son la norma: 153 "No Tiene Internet", 36 "Internet
Intermitente/Niveles Altos", 24 "Recolección De Equipos". En total **308 casos
imposibles de editar** desde la interfaz, y justo los que el sistema mismo
habia creado.

QUE SE AFIRMA
-------------
Sobre el EFECTO: que la edicion PASE. Comprobar que el validador ya no existe
no probaria nada -- la regla podria volver desde otro serializer, que es
exactamente como llego aca.
"""

from types import SimpleNamespace

import pytest
from rest_framework import status

from cases.models import Case
from cases.serializer import CaseCreateSerializer

pytestmark = pytest.mark.django_db

REPETIDO = "No Tiene Internet"


def _caso(org, creador, nombre=REPETIDO, estado="New"):
    return Case.objects.create(
        name=nombre, status=estado, priority="Low", case_type="Question",
        description="x", created_by=creador, org=org,
    )


def test_se_puede_editar_un_caso_cuyo_nombre_se_repite(
        admin_client, admin_user, admin_profile, org_a):
    """LA REPRODUCCION: dos casos con el mismo nombre, y se edita uno."""
    _caso(org_a, admin_user)
    caso = _caso(org_a, admin_user)

    #  El formulario manda TODOS sus campos, incluido 'name' sin tocar -- es
    #  lo que se ve en la pantalla de editar. Mandar solo 'assigned_to' no
    #  reproduce nada: sin 'name' en el cuerpo, 'validate_name' ni corre, y la
    #  prueba pasaria igual con el defecto puesto.
    r = admin_client.patch(
        f"/api/cases/{caso.id}/",
        {"name": REPETIDO, "status": "Assigned", "priority": "Normal",
         "assigned_to": [str(admin_profile.id)]},
        content_type="application/json")

    assert r.status_code == status.HTTP_200_OK, (
        f"la edicion se rechazo: {r.json()}")
    caso.refresh_from_db()
    assert list(caso.assigned_to.all()) == [admin_profile], (
        "respondio 200 pero no guardo el responsable")


def test_el_nombre_se_puede_dejar_igual_al_editar(
        admin_client, admin_user, org_a):
    """Mandar el mismo nombre que ya tiene no es 'un nombre repetido'."""
    _caso(org_a, admin_user)
    caso = _caso(org_a, admin_user)

    r = admin_client.patch(
        f"/api/cases/{caso.id}/", {"name": REPETIDO, "priority": "High"},
        content_type="application/json")

    assert r.status_code == status.HTTP_200_OK, r.json()
    caso.refresh_from_db()
    assert caso.priority == "High"


def test_el_serializer_acepta_un_nombre_ya_usado(org_a, admin_user):
    """El importador ya crea repetidos; la interfaz no tiene por que ser mas
    estricta. Una restriccion que el sistema se saltea a si mismo no es una
    regla: es una traba para quien edita a mano.

    Se afirma contra el SERIALIZER y no contra POST /api/cases/ a proposito:
    ese endpoint dispara una tarea de Celery y sin Redis falla por un motivo
    que no tiene nada que ver con lo que se quiere medir. Aqui vivia la regla
    y aqui se comprueba que ya no esta.
    """
    _caso(org_a, admin_user)

    #  El serializer toma la org de 'request_obj.profile.org'; se le pasa lo
    #  minimo que necesita en vez de montar una peticion entera.
    peticion = SimpleNamespace(profile=SimpleNamespace(org=org_a))
    s = CaseCreateSerializer(
        data={"name": REPETIDO, "status": "New", "priority": "Low",
              "case_type": "Question",
              "description": "otro cliente, mismo problema"},
        request_obj=peticion)
    assert s.is_valid(), s.errors
    assert "name" not in s.errors


def test_el_aislamiento_por_organizacion_no_cambia(
        admin_client, admin_user, org_a, org_b, user_b):
    """Quitar la unicidad no abre la puerta a editar lo de otra empresa."""
    ajeno = _caso(org_b, user_b)

    r = admin_client.patch(
        f"/api/cases/{ajeno.id}/", {"priority": "High"},
        content_type="application/json")

    assert r.status_code == status.HTTP_404_NOT_FOUND
    ajeno.refresh_from_db()
    assert ajeno.priority == "Low"
