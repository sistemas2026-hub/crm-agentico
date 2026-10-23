# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR LEE SOLO LOS TICKETS DE SU AREA
================================================================================

DE DONDE SALE
-------------
"Revise la lista de soporte tecnico en los ticket y no salen los ticket de
descuentos programados, esos son de cartera. ¿Por que si el supervisor deberia
ver solo soporte tecnico?" -- 14/10/2026.

Medido ese dia sobre los tickets abiertos con tecnico:

    563  de una persona, de los cuales 509 eran de cartera
     76  de la persona de soporte, cero de cartera
         (y 76 es exactamente lo que la pantalla de Tickets muestra para
          "Soporte Tecnico")

El detector traia los 771. El propio Supervisor se daba cuenta --proponia
"derivar el ticket al area comercial"-- pero ya habia pagado la consulta al
modelo para leer un ticket que no le tocaba.

EL CAMINO CORTO LO ENCONTRO EL CLIENTE
---------------------------------------
Se habia empezado a construir un campo nuevo en el caso, con su migracion y un
relleno para los ~1.300 ya importados. Entonces pregunto lo obvio: "los tickets
en Dexter si estan divididos bien... ¿no puede el supervisor extraer de esa
area los ticket sin tanto rodeo?".

Si podia: la pantalla de Tickets ya lo hace preguntandole al motor que personas
son de cada area y filtrando por 'assigned_to'. Sin campo nuevo, sin migracion,
sin relleno, y funcionando con los 1.300 de hoy.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from operaciones import areas_del_tenant as areas
from operaciones import supervisor as sup

pytestmark = pytest.mark.django_db


def _perfil(org, nombre):
    from common.models import Profile, User

    u = User.objects.create(email=f"{uuid.uuid4().hex[:8]}@isp.test",
                            name=nombre, is_active=True)
    return Profile.objects.create(user=u, org=org, role="USER", is_active=True)


def _ticket(org, asunto, de_quien):
    from cases.models import Case

    ahora = timezone.now()
    c = Case.objects.create(
        org=org, name=asunto, status="Assigned", priority="Normal",
        provider="wisphub", external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614", external_status="Nuevo",
        external_fetched_at=ahora, description="Texto del reclamo.")
    Case.objects.filter(pk=c.pk).update(
        created_at=ahora - timezone.timedelta(days=6))
    c.assigned_to.add(de_quien)
    c.refresh_from_db()
    return c


# =============================================================================
#  §1  LA TRADUCCION DE AREA A PERSONAS
# =============================================================================

def test_el_area_se_traduce_a_sus_responsables():
    mapa = {"p-soporte": "soporte_tecnico", "p-cartera": "cartera",
            "p-otro": "ventas"}
    assert areas.responsables_de("soporte_tecnico", mapa) == ["p-soporte"]


def test_no_importan_mayusculas_ni_espacios():
    #  El nombre del area lo escribe una persona en la interfaz.
    mapa = {"p1": " Soporte_Tecnico "}
    assert areas.responsables_de("soporte_tecnico", mapa) == ["p1"]


def test_un_area_sin_gente_devuelve_vacio():
    assert areas.responsables_de("soporte_tecnico", {"p1": "cartera"}) == []


def test_OPERATIVO_tambien_es_del_Supervisor():
    """
    SON DOS AREAS Y NO UNA, y la primera version lo tuvo mal.

    Se razono que 'importacion_tickets.destinos' manda el departamento
    "Operativo" a 'soporte_tecnico', y es cierto -- pero eso dice a donde va el
    TICKET, no a que area pertenece una PERSONA, que es lo que se consulta.

    Medido el 14/10/2026 contra 'asistente.area_colaborador': 'operativo' es un
    area propia con CUATRO personas. Con un solo nombre, los tickets de esas
    cuatro quedaban afuera -- y se habian pedido las dos.
    """
    assert "operativo" in areas.AREAS_DEL_SUPERVISOR
    mapa = {"p-sop": "soporte_tecnico", "p-ope": "operativo",
            "p-car": "cartera", "p-ven": "ventas"}
    assert sorted(areas.responsables_de(areas.AREAS_DEL_SUPERVISOR, mapa)) ==         ["p-ope", "p-sop"]


def test_un_solo_nombre_sigue_funcionando():
    #  Acepta texto o lista: quien pase un nombre suelto no tiene que saberlo.
    assert areas.responsables_de("cartera", {"p1": "cartera"}) == ["p1"]


# =============================================================================
#  §2  EL EFECTO SOBRE LO QUE EL SUPERVISOR LEE
# =============================================================================

def test_los_tickets_de_cartera_NO_entran(org_a, monkeypatch):
    """
    EL CASO EXACTO DE PRODUCCION, en chico: un ticket de soporte y uno de
    cartera, cada uno con la persona de su area.
    """
    soporte = _perfil(org_a, "Mario Vasquez")
    cartera = _perfil(org_a, "Alejandra Castro")
    monkeypatch.setattr(areas, "area_por_persona",
                        lambda: {str(soporte.id): "soporte_tecnico",
                                 str(cartera.id): "cartera"})

    tecnico = _ticket(org_a, "No Tiene Internet", soporte)
    comercial = _ticket(org_a, "Desc Programado/ Sexto Mes Gratis.- CAMBIO DE PLAN",
                        cartera)

    vistos = {s.origen_id for s in
              sup._tickets_abiertos_con_tecnico(org_a, timezone.now())}

    assert str(tecnico.id) in vistos, "no entro un ticket de soporte"
    assert str(comercial.id) not in vistos, (
        "entro un ticket de cartera: el Supervisor paga una consulta al modelo "
        "para leer algo que no le toca")


def test_si_no_se_puede_saber_el_area_NO_se_lee_nada(org_a, monkeypatch):
    """
    FAIL-CLOSED, y no es simetrico: filtrar por una lista vacia no filtra nada
    y traeria la cola ENTERA -- los 771, incluidos los 509 de cartera. Quedarse
    sin leer una vuelta es barato y se ve en el log; leer setecientos ajenos
    cuesta setecientas consultas al modelo.
    """
    quien_sea = _perfil(org_a, "Alguien")
    _ticket(org_a, "No Tiene Internet", quien_sea)
    monkeypatch.setattr(areas, "area_por_persona", lambda: {})

    assert sup._tickets_abiertos_con_tecnico(org_a, timezone.now()) == []


def test_un_ticket_sin_nadie_asignado_sigue_afuera(org_a, monkeypatch):
    #  Ya estaba asi antes: sin tecnico es otra señal, no esta.
    from cases.models import Case

    soporte = _perfil(org_a, "Mario Vasquez")
    monkeypatch.setattr(areas, "area_por_persona",
                        lambda: {str(soporte.id): "soporte_tecnico"})
    ahora = timezone.now()
    huerfano = Case.objects.create(
        org=org_a, name="No Tiene Internet", status="New", priority="Normal",
        provider="wisphub", external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614", external_status="Nuevo",
        external_fetched_at=ahora, description="Texto.")

    vistos = {s.origen_id for s in
              sup._tickets_abiertos_con_tecnico(org_a, ahora)}
    assert str(huerfano.id) not in vistos
