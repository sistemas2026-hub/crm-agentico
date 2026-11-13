"""Configuracion no hace una consulta por caso ni por persona (29/10/2026).

"Demora mucho al mostrar la pantalla", dijo el usuario. Medido: de las
quince lecturas del CRM que Configuracion espera, dos crecian con los datos.

- El resumen de escalamiento cuenta los incumplimientos de los ultimos 30 dias
  caso por caso, y add_business_hours pedia los feriados con values_list, que
  se salta el prefetch: 2 consultas por caso (408 con 200 casos).
- El listado de equipos serializa cada integrante con su usuario: una
  consulta por persona (131 con 3 equipos de 40).

Lo que se afirma es que la cantidad de consultas NO depende del volumen:
con pocos datos y con ocho veces mas, la misma.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from business_hours.models import BusinessHoliday
from business_hours.calendar import get_default_calendar
from cases.models import Case
from common.models import Profile, Teams, User


def _consultas(client, url):
    client.get(url)  # la primera crea lo que falte (el calendario por defecto)
    with CaptureQueriesContext(connection) as q:
        r = client.get(url)
    assert r.status_code == 200, r.content[:300]
    return len(q.captured_queries)


def _casos(org, n, desde=0):
    for i in range(desde, desde + n):
        Case.objects.create(name=f"c{i}", status="New", priority="Low", org=org)


def _personas(org, n, desde=0):
    out = []
    for i in range(desde, desde + n):
        u = User.objects.create_user(email=f"p{i}@t.com", password="x")
        out.append(Profile.objects.create(user=u, org=org, role="USER", is_active=True))
    return out


def test_escalamiento_no_consulta_por_caso(admin_client, org_a):
    url = "/api/cases/escalation-policies/"
    admin_client.get("/api/business-hours/calendar/")
    cal = get_default_calendar(org_a.id)
    assert cal is not None, "sin calendario el camino de los feriados no se recorre"
    BusinessHoliday.objects.create(calendar=cal, date="2026-12-25", name="Navidad", org=org_a)

    _casos(org_a, 5)
    pocos = _consultas(admin_client, url)
    _casos(org_a, 40, desde=5)
    muchos = _consultas(admin_client, url)
    assert muchos == pocos, f"5 casos: {pocos} consultas; 45 casos: {muchos}"


def test_equipos_no_consulta_por_integrante(admin_client, org_a):
    url = "/api/teams/"
    gente = _personas(org_a, 3)
    eq = Teams.objects.create(name="eq", org=org_a)
    eq.users.add(*gente)
    pocos = _consultas(admin_client, url)

    mas = _personas(org_a, 24, desde=3)
    eq.users.add(*mas)
    Teams.objects.create(name="eq2", org=org_a).users.add(*mas)
    muchos = _consultas(admin_client, url)
    assert muchos == pocos, f"3 integrantes: {pocos} consultas; 51 en dos equipos: {muchos}"
