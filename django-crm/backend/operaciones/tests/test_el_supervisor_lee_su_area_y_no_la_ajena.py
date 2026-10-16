# -*- coding: utf-8 -*-
"""
================================================================================
 EL AREA ES DEL CASO, NO DE QUIEN LO TIENE ASIGNADO
================================================================================

EL DEFECTO, REPORTADO Y MEDIDO EN PRODUCCION  --  16/10/2026
-------------------------------------------------------------
El Supervisor NOC estaba leyendo, analizando y proponiendo sobre tickets de
cartera y de ventas. No es un area suya: es un supervisor de operaciones.

LA CAUSA, y estaba escrita en el propio codigo. El docstring de
'DestinoTicket' (nucleo/config/schema.py) lo decia textual:

    "el area viaja de la config a la pantalla dando la vuelta por el
     responsable, y en ningun punto queda escrita en la fila"

O sea: el area de un caso se DEDUCIA del area de la persona asignada. Un
ticket de ventas asignado a un tecnico heredaba area de soporte, y entraba.

EL DATO SIEMPRE EXISTIO: 'importacion_tickets.destinos' mapea
'departamento|asunto' a un area y el motor la usa para elegir responsable. Lo
unico que faltaba era persistirla y filtrar por ella.

LOS VIEJOS, Y POR QUE EL FILTRO TIENE DOS MITADES
--------------------------------------------------
Los ~1.300 casos importados antes del campo tienen 'area' vacia. Para esos
sigue valiendo el filtro por persona, igual que ayer -- si no, el Supervisor
se quedaria sin cola de un dia para el otro. La reconciliacion los va
completando a medida que relee cada ticket.

La asimetria importa y estas pruebas la fijan: un caso CON area ajena NO entra
aunque tenga un tecnico encima; un caso SIN area entra con el criterio viejo.
================================================================================
"""
import uuid

import pytest
from django.utils import timezone

from cases.models import Case
from common.models import Profile, User
from operaciones import supervisor as sup

pytestmark = pytest.mark.django_db


def _persona(org, correo, area_del_motor, areas):
    """Alguien del equipo, con su area segun el motor."""
    u = User.objects.create(email=correo, name=correo.split("@")[0])
    p = Profile.objects.create(org=org, user=u, role="USER", is_active=True)
    areas[str(p.id)] = area_del_motor
    return p


def _caso(org, *, area, responsable, nombre="No tiene internet"):
    c = Case.objects.create(
        org=org, name=nombre, status="New", priority="Normal", is_active=True,
        provider="wisphub", external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614", area=area,
        description="El cliente dice que no tiene internet.",
        external_status="Nuevo",
        external_fetched_at=timezone.now())
    c.assigned_to.add(responsable)
    return c


@pytest.fixture
def equipo(org_a, monkeypatch):
    """Un tecnico de soporte y una persona de cartera, segun el motor."""
    from operaciones import areas_del_tenant as areas

    por_persona = {}
    tecnico = _persona(org_a, "tecnico@x.test", "soporte_tecnico", por_persona)
    cartera = _persona(org_a, "cartera@x.test", "cartera", por_persona)

    def _responsables(areas_pedidas):
        pedidas = set(areas_pedidas)
        return [pid for pid, a in por_persona.items() if a in pedidas]

    monkeypatch.setattr(areas, "responsables_de", _responsables)
    return tecnico, cartera


def _leidos(org):
    """Los ids de caso que la deteccion trae para leer."""
    return {str(s.origen_id) for s in sup._tickets_abiertos_con_tecnico(
        org, timezone.now())}


# =============================================================================
#  §1  EL CASO CON AREA AJENA NO ENTRA, AUNQUE LO TENGA UN TECNICO
# =============================================================================

def test_un_caso_de_VENTAS_asignado_a_un_tecnico_NO_entra(org_a, equipo):
    """El defecto exacto que se reporto."""
    tecnico, _ = equipo
    ajeno = _caso(org_a, area="ventas", responsable=tecnico,
                  nombre="Cotización de plan nuevo")

    assert str(ajeno.id) not in _leidos(org_a), (
        "un ticket de ventas no deja de serlo porque se lo hayan asignado a "
        "un técnico: el Supervisor NOC no tiene nada que proponer sobre él")


def test_un_caso_de_CARTERA_asignado_a_un_tecnico_tampoco(org_a, equipo):
    tecnico, _ = equipo
    ajeno = _caso(org_a, area="cartera", responsable=tecnico,
                  nombre="Reconexión por pago")

    assert str(ajeno.id) not in _leidos(org_a)


def test_el_caso_de_SU_area_si_entra(org_a, equipo):
    tecnico, _ = equipo
    propio = _caso(org_a, area="soporte_tecnico", responsable=tecnico)

    assert str(propio.id) in _leidos(org_a)


def test_operativo_TAMBIEN_es_suyo(org_a, equipo):
    """Son dos áreas y no una: lo pidió el cliente y está medido en 14/10."""
    tecnico, _ = equipo
    propio = _caso(org_a, area="operativo", responsable=tecnico)

    assert str(propio.id) in _leidos(org_a)


# =============================================================================
#  §2  LOS VIEJOS, SIN AREA, SIGUEN CON EL CRITERIO DE AYER
# =============================================================================

def test_un_caso_SIN_area_con_tecnico_sigue_entrando(org_a, equipo):
    """
    Los ~1.300 importados antes del campo. Si dejaran de entrar, el Supervisor
    se quedaría sin cola de un día para el otro.
    """
    tecnico, _ = equipo
    viejo = _caso(org_a, area="", responsable=tecnico)

    assert str(viejo.id) in _leidos(org_a)


def test_un_caso_SIN_area_de_alguien_de_otra_area_NO_entra(org_a, equipo):
    """La mitad vieja del filtro sigue siendo la de siempre."""
    _, cartera = equipo
    viejo = _caso(org_a, area="", responsable=cartera)

    assert str(viejo.id) not in _leidos(org_a)


def test_el_area_del_caso_MANDA_sobre_la_de_la_persona(org_a, equipo):
    """
    El caso que fija la decisión: área propia, persona de otra área.

    Con el criterio viejo no entraba; con el nuevo sí, porque el trabajo es de
    soporte aunque hoy lo tenga alguien de cartera.
    """
    _, cartera = equipo
    propio = _caso(org_a, area="soporte_tecnico", responsable=cartera)

    assert str(propio.id) in _leidos(org_a)


# =============================================================================
#  §3  EL CONTRATO DE IMPORTACION LO ACEPTA
# =============================================================================

def test_la_importacion_puede_escribir_el_area():
    from cases import importacion_views as iv

    assert "area" in iv.CAMPOS_DESCUBRIMIENTO


def test_la_reconciliacion_TAMBIEN_puede(org_a):
    """
    Es lo que rellena los viejos sin una migración que adivine: cada vez que
    se relee el ticket, el área llega.
    """
    from cases import importacion_views as iv

    assert "area" in iv.CAMPOS_RECONCILIACION
    #  Y lo que esa fase NO puede seguir tocando, que es el invariante.
    for prohibido in ("status", "assigned_to", "priority"):
        assert prohibido not in iv.CAMPOS_RECONCILIACION
