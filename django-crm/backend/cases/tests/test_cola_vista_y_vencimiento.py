# -*- coding: utf-8 -*-
"""Las pestanas "Mios" / "Sin asignar" y el orden "vence primero", en el SERVIDOR.

EL DEFECTO (24/10/2026)
-----------------------
La pantalla de Tickets filtraba las pestanas "Mios" y "Sin asignar" sobre
``cases``, que es UNA PAGINA de 25: la pestana mostraba los mios de esas 25,
y su numero y la paginacion no coincidian. Desde hoy la lista acepta
``vista=mios|sin_asignar`` y devuelve, en la RAIZ de la respuesta,
``mios_count`` y ``sin_asignar_count`` calculados sobre los abiertos de la cola
filtrada ANTES de la vista, para que cada pestana muestre su numero aunque este
activa otra.

QUE SE AFIRMA
-------------
Sobre el EFECTO, leyendo la respuesta del endpoint real:

* "mios" sale de la SESION: el mismo pedido con dos usuarios distintos da dos
  listas distintas, y un ``assigned_to`` ajeno en la URL no cambia quien soy.
* "sin asignar" no trae ningun caso con responsable, ni duplica filas.
* Los dos conteos son los mismos con cualquier vista, y coinciden con la
  cantidad real.
* ``ordering=vence``: el vencido hace mas va antes que el por vencer, los
  respondidos al final; y sin ``ordering`` el orden sigue siendo -created_at.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from cases.models import Case

pytestmark = pytest.mark.django_db

RUTA = "/api/cases/"
ABIERTOS = "status=New&status=Assigned&status=Pending"


def _set_rls(org):
    """Set the RLS session var so a direct ORM insert satisfies the org policy.

    No-op on SQLite; required when the suite runs against PostgreSQL.
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as c:
        c.execute("SELECT set_config('app.current_org', %s, false)", [str(org.id)])


def _caso(org, creador, nombre, *, estado="New", asignados=(),
          hace_horas=None, sla_horas=None, respondido=False):
    _set_rls(org)
    caso = Case.objects.create(
        name=nombre, status=estado, priority="Low", case_type="Question",
        description="x", created_by=creador, org=org,
    )
    for persona in asignados:
        caso.assigned_to.add(persona)
    cambios = {}
    if hace_horas is not None:
        # created_at es auto_now_add: se corrige despues, con update().
        cambios["created_at"] = timezone.now() - timedelta(hours=hace_horas)
    if sla_horas is not None:
        cambios["sla_first_response_hours"] = sla_horas
        # La resolucion lejos, para que 'sla_breached' solo mire la primera
        # respuesta y la comparacion con el orden sea limpia.
        cambios["sla_resolution_hours"] = 10_000
    if respondido:
        cambios["first_response_at"] = timezone.now()
    if cambios:
        Case.objects.filter(pk=caso.pk).update(**cambios)
    return caso


def _nombres(cuerpo):
    return [c["name"] for c in cuerpo["cases"]]


@pytest.fixture
def cola(org_a, admin_user, admin_profile, user_profile):
    """Cuatro abiertos y dos cerrados, con responsables conocidos.

    abiertos:  M (solo admin) · U (solo user) · AMBOS (admin + user) · N (nadie)
    cerrados:  M_CERRADO (admin) · N_CERRADO (nadie) -- no cuentan en las pestanas
    """
    _caso(org_a, admin_user, "M", asignados=[admin_profile])
    _caso(org_a, admin_user, "U", asignados=[user_profile])
    _caso(org_a, admin_user, "AMBOS", asignados=[admin_profile, user_profile])
    _caso(org_a, admin_user, "N")
    _caso(org_a, admin_user, "M_CERRADO", estado="Closed",
          asignados=[admin_profile])
    _caso(org_a, admin_user, "N_CERRADO", estado="Closed")


# --------------------------------------------------------------------------
#  vista=mios
# --------------------------------------------------------------------------

def test_mios_devuelve_solo_los_del_que_pide(admin_client, user_client, cola):
    del_admin = admin_client.get(f"{RUTA}?slim=true&vista=mios").json()
    del_user = user_client.get(f"{RUTA}?slim=true&vista=mios").json()

    assert sorted(_nombres(del_admin)) == ["AMBOS", "M", "M_CERRADO"]
    assert del_admin["cases_count"] == 3
    assert sorted(_nombres(del_user)) == ["AMBOS", "U"], (
        "el mismo pedido con otra sesion tiene que dar los de esa persona")


def test_un_assigned_to_ajeno_no_cambia_quien_soy(
        admin_client, cola, user_profile):
    """El 'assigned_to' de la URL sigue siendo el filtro de la barra: se CRUZA
    con 'mios', no lo reemplaza. Si la identidad saliera de ahi, vendria U."""
    ajeno = str(user_profile.id)
    cuerpo = admin_client.get(
        f"{RUTA}?slim=true&vista=mios&assigned_to={ajeno}"
        f"&yo={ajeno}&profile={ajeno}"
    ).json()

    assert _nombres(cuerpo) == ["AMBOS"]
    assert "U" not in _nombres(cuerpo)


# --------------------------------------------------------------------------
#  vista=sin_asignar
# --------------------------------------------------------------------------

def test_sin_asignar_devuelve_solo_sin_responsable(admin_client, cola):
    cuerpo = admin_client.get(f"{RUTA}?slim=true&vista=sin_asignar").json()

    assert sorted(_nombres(cuerpo)) == ["N", "N_CERRADO"]
    assert cuerpo["cases_count"] == 2
    assert all(c["assigned_to"] == [] for c in cuerpo["cases"])


def test_la_vista_no_duplica_un_caso_con_dos_responsables(admin_client, cola):
    cuerpo = admin_client.get(f"{RUTA}?slim=true&vista=mios").json()

    assert _nombres(cuerpo).count("AMBOS") == 1
    assert cuerpo["cases_count"] == len(cuerpo["cases"])


def test_una_vista_desconocida_no_filtra(admin_client, cola):
    sin = admin_client.get(f"{RUTA}?slim=true").json()
    rara = admin_client.get(f"{RUTA}?slim=true&vista=cualquiera").json()

    assert rara["cases_count"] == sin["cases_count"] == 6
    assert sorted(_nombres(rara)) == sorted(_nombres(sin))


# --------------------------------------------------------------------------
#  Los conteos de las pestanas
# --------------------------------------------------------------------------

@pytest.mark.parametrize("vista", [None, "todos", "mios", "sin_asignar"])
def test_los_conteos_no_dependen_de_la_vista_activa(admin_client, cola, vista):
    url = f"{RUTA}?slim=true" + (f"&vista={vista}" if vista else "")
    cuerpo = admin_client.get(url).json()

    # mios abiertos del admin: M y AMBOS. Sin asignar abiertos: N.
    assert cuerpo["mios_count"] == 2
    assert cuerpo["sin_asignar_count"] == 1
    # Los de siempre, sin la vista: los cuatro abiertos.
    assert cuerpo["open_count"] == 4
    totales = sum(f["total"] for f in cuerpo["open_by_assignee"]
                  if f["assigned_to"] is None)
    assert totales == 1


def test_el_numero_de_la_pestana_coincide_con_su_lista(admin_client, cola):
    """El defecto original: el numero y la paginacion no coincidian."""
    for vista, clave in (("mios", "mios_count"),
                         ("sin_asignar", "sin_asignar_count")):
        cuerpo = admin_client.get(
            f"{RUTA}?slim=true&limit=1&{ABIERTOS}&vista={vista}").json()
        assert cuerpo["cases_count"] == cuerpo[clave], vista
        assert len(cuerpo["cases"]) == 1, "la paginacion sigue cortando"


def test_los_conteos_respetan_los_demas_filtros(admin_client, cola):
    cuerpo = admin_client.get(f"{RUTA}?slim=true&search=AMBOS").json()

    assert cuerpo["mios_count"] == 1
    assert cuerpo["sin_asignar_count"] == 0


# --------------------------------------------------------------------------
#  ordering=vence
# --------------------------------------------------------------------------

@pytest.fixture
def cola_con_vencimientos(org_a, admin_user):
    """Vencimiento de primera respuesta = creado + SLA (horas corridas).

    VENCIDO     creado hace 10 h, SLA 2 h   -> vencio hace 8 h
    POR_VENCER  creado hace 0,5 h, SLA 4 h  -> vence en 3,5 h
    MAS_TARDE   creado hace 20 h, SLA 24 h  -> vence en 4 h
    RESP_NUEVO  respondido, creado hace 1 h
    RESP_VIEJO  respondido, creado hace 48 h, SLA 1 h (seria el primero si
                no estuviera respondido)

    Los tres primeros en orden de creacion NO coinciden con su orden de
    vencimiento, asi que un -created_at o un created_at no pasan la prueba.
    """
    _caso(org_a, admin_user, "VENCIDO", hace_horas=10, sla_horas=2)
    _caso(org_a, admin_user, "POR_VENCER", hace_horas=0.5, sla_horas=4)
    _caso(org_a, admin_user, "MAS_TARDE", hace_horas=20, sla_horas=24)
    _caso(org_a, admin_user, "RESP_NUEVO", hace_horas=1, sla_horas=4,
          respondido=True)
    _caso(org_a, admin_user, "RESP_VIEJO", hace_horas=48, sla_horas=1,
          respondido=True)


def test_vence_primero(admin_client, cola_con_vencimientos):
    cuerpo = admin_client.get(f"{RUTA}?slim=true&ordering=vence").json()

    assert _nombres(cuerpo) == [
        "VENCIDO", "POR_VENCER", "MAS_TARDE", "RESP_NUEVO", "RESP_VIEJO"]


def test_sin_ordering_el_orden_es_el_de_siempre(
        admin_client, cola_con_vencimientos):
    cuerpo = admin_client.get(f"{RUTA}?slim=true").json()

    assert _nombres(cuerpo) == [
        "POR_VENCER", "RESP_NUEVO", "VENCIDO", "MAS_TARDE", "RESP_VIEJO"]


def test_vence_primero_y_el_filtro_de_vencidos_dicen_lo_mismo(
        admin_client, cola_con_vencimientos):
    """El orden usa el mismo calculo que 'sla_breached': lo que el filtro da
    por vencido es exactamente el principio de la lista ordenada."""
    ordenados = _nombres(
        admin_client.get(f"{RUTA}?slim=true&ordering=vence").json())
    vencidos = _nombres(
        admin_client.get(f"{RUTA}?slim=true&sla_breached=true").json())

    assert vencidos == ["VENCIDO"]
    assert ordenados[:len(vencidos)] == vencidos


def test_vence_primero_no_cambia_los_conteos(
        admin_client, cola_con_vencimientos):
    sin = admin_client.get(f"{RUTA}?slim=true").json()
    con = admin_client.get(f"{RUTA}?slim=true&ordering=vence").json()

    for clave in ("open_count", "urgent_count", "awaiting_first_reply",
                  "mios_count", "sin_asignar_count", "cases_count"):
        assert con[clave] == sin[clave], clave
    assert sorted(con["open_by_assignee"], key=str) == sorted(
        sin["open_by_assignee"], key=str)
