# -*- coding: utf-8 -*-
"""El desglose de la cola se cuenta sobre TODO, no sobre la página.

EL DEFECTO, MEDIDO EN PRODUCCIÓN EL 06/10/2026
-----------------------------------------------
La pantalla de tickets mostraba::

    Tickets: 47 · Cartera: 0 · Soporte Técnico: 25 · Administración: 0

y parecía que 22 tickets no tenían área. No era eso. El total salía del
servidor (``cases_count``, sobre los 47 abiertos) y el desglose por área se
calculaba en el navegador sobre ``results``, que es una página de 25. Los 22
que "faltaban" eran los que no habían llegado.

Medido ese día: los 47 abiertos tenían exactamente un responsable, la misma
persona, de área ``soporte_tecnico``. El desglose correcto era 47, no 25.

QUÉ SE AFIRMA, Y POR QUÉ ASÍ
-----------------------------
Sobre el EFECTO: que con MÁS casos que el tamaño de página, el desglose siga
dando el total. Por eso cada prueba crea más casos que ``limit`` -- mirar el
``annotate`` no probaría nada el día que alguien cambie la paginación.

Se agrupa por RESPONSABLE y no por área a propósito: el mapa persona -> área
no vive en este CRM sino en ``asistente.area_colaborador``, que sirve el
motor. Aquí se cuenta lo que hay; la traducción a áreas la hace el frontend
(``lib/v2/tickets-resumen.js``), que sí conoce ese mapa.
"""

import pytest

from cases.models import Case
from cases.views import OPEN_STATUSES

pytestmark = pytest.mark.django_db

RUTA = "/api/cases/?limit=25&slim=true"
LIMITE = 25


def _caso(org, creador, *, estado="New", prioridad="Low", asignado=None,
          primera_respuesta=None):
    caso = Case.objects.create(
        name="ticket de prueba", status=estado, priority=prioridad,
        case_type="Question", description="x", created_by=creador, org=org,
        first_response_at=primera_respuesta,
    )
    if asignado is not None:
        caso.assigned_to.add(asignado)
    return caso


def _por_responsable(cuerpo):
    """{id_responsable|None: fila} para leer el desglose sin orden."""
    return {f["assigned_to"]: f for f in cuerpo["open_by_assignee"]}


def test_el_desglose_cuenta_todo_aunque_la_pagina_corte(
        admin_client, admin_user, admin_profile, org_a):
    """LA REPRODUCCIÓN: más abiertos que el límite, un solo responsable."""
    for _ in range(47):
        _caso(org_a, admin_user, asignado=admin_profile)

    cuerpo = admin_client.get(RUTA).json()

    assert cuerpo["open_count"] == 47
    assert len(cuerpo["cases"]) == LIMITE, "la paginación no se tocó"

    filas = _por_responsable(cuerpo)
    assert filas[str(admin_profile.id)]["total"] == 47, (
        "el desglose volvió a contar sobre la página")


def test_varios_responsables_y_varias_paginas(
        admin_client, admin_user, admin_profile, org_a, user_profile):
    """Dos responsables repartidos en más de dos páginas: cada uno con su total."""
    for _ in range(30):
        _caso(org_a, admin_user, asignado=admin_profile)
    for _ in range(25):
        _caso(org_a, admin_user, asignado=user_profile)

    cuerpo = admin_client.get(RUTA).json()
    filas = _por_responsable(cuerpo)

    assert cuerpo["open_count"] == 55
    assert len(cuerpo["cases"]) == LIMITE
    assert filas[str(admin_profile.id)]["total"] == 30
    assert filas[str(user_profile.id)]["total"] == 25
    #  Y la suma del desglose es el total: ningún caso se perdió ni se contó
    #  dos veces (cada uno tiene un solo responsable).
    assert sum(f["total"] for f in cuerpo["open_by_assignee"]) == 55


def test_los_sin_responsable_son_su_propia_fila(
        admin_client, admin_user, admin_profile, org_a):
    """La cola sin asignar se cuenta, no se pierde."""
    for _ in range(30):
        _caso(org_a, admin_user, asignado=admin_profile)
    for _ in range(8):
        _caso(org_a, admin_user, asignado=None)

    filas = _por_responsable(admin_client.get(RUTA).json())
    assert filas[None]["total"] == 8
    assert filas[str(admin_profile.id)]["total"] == 30


def test_las_metricas_del_desglose_tambien_son_del_total(
        admin_client, admin_user, admin_profile, org_a):
    """Urgentes, sin respuesta y en progreso: las tres sobre el conjunto."""
    from django.utils import timezone

    for _ in range(26):
        _caso(org_a, admin_user, asignado=admin_profile, prioridad="Urgent")
    for _ in range(5):
        _caso(org_a, admin_user, asignado=admin_profile, prioridad="Low",
              estado="Assigned", primera_respuesta=timezone.now())

    fila = _por_responsable(admin_client.get(RUTA).json())[str(admin_profile.id)]
    assert fila["total"] == 31
    assert fila["urgentes"] == 26
    assert fila["sin_respuesta"] == 26      # los 5 ya respondidos no cuentan
    assert fila["en_progreso"] == 5


def test_lo_cerrado_no_entra_en_el_desglose(
        admin_client, admin_user, admin_profile, org_a):
    """El desglose es de la cola ABIERTA, con el mismo filtro de siempre."""
    for _ in range(30):
        _caso(org_a, admin_user, asignado=admin_profile)
    for _ in range(10):
        _caso(org_a, admin_user, asignado=admin_profile, estado="Closed")

    cuerpo = admin_client.get(RUTA).json()
    filas = _por_responsable(cuerpo)
    assert cuerpo["open_count"] == 30
    assert filas[str(admin_profile.id)]["total"] == 30, (
        f"el desglose tiene que usar {OPEN_STATUSES}, igual que open_count")


def test_una_organizacion_no_ve_el_desglose_de_otra(
        admin_client, admin_user, admin_profile, org_a, org_b, user_b):
    """El aislamiento no cambia por agregar un agregado."""
    for _ in range(30):
        _caso(org_a, admin_user, asignado=admin_profile)
    for _ in range(12):
        _caso(org_b, user_b, asignado=None)

    cuerpo = admin_client.get(RUTA).json()
    assert cuerpo["open_count"] == 30
    assert sum(f["total"] for f in cuerpo["open_by_assignee"]) == 30
