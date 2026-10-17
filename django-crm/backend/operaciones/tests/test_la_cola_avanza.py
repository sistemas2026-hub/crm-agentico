# -*- coding: utf-8 -*-
"""
================================================================================
 LA COLA DE TICKETS TIENE QUE AVANZAR, NO MIRAR SIEMPRE LOS MISMOS
================================================================================

DE DONDE SALE
-------------
Medido en produccion el 13/10/2026, unas horas despues de poner el tope:

    771   tickets abiertos con tecnico que podian leerse
     40   los que el detector miraba por vuelta (los mas VIEJOS)
     38   de esos 40, ya leidos
    731   los que no iban a mirarse NUNCA

El comentario que acompañaba al tope decia: "no se pierde ninguno, el que no
entro hoy entra cuando los de adelante dejen de estar abiertos". Es falso: los
de adelante son justamente los que llevan mas tiempo abiertos, y no se cierran.

EL SINTOMA NO SE PARECIA A LA CAUSA, que es por lo que esta guarda vale la pena:
lo que se veia era "el Supervisor no registra ninguna lectura", que se lee como
un registro roto. Lo que estaba roto era A QUIEN miraba.

LO QUE AFIRMA
-------------
Que una segunda vuelta trae tickets DISTINTOS de la primera. No afirma cuantos,
ni en que orden: afirma que avanza, que es la propiedad que se perdio.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db


def _caso(org, dias_de_antiguedad, *, tecnico):
    """Un ticket abierto en el proveedor, con tecnico, listo para leerse."""
    from cases.models import Case

    ahora = timezone.now()
    c = Case.objects.create(
        org=org, name=f"Reclamo {uuid.uuid4().hex[:6]}", status="Assigned",
        priority="Normal", provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id=str(1000 + dias_de_antiguedad),
        external_status="Nuevo",
        external_fetched_at=ahora,
        description="Reporta intermitencia del servicio.")
    #  'created_at' es auto_now_add: se fuerza despues para controlar el orden,
    #  que es justo la variable de esta prueba.
    Case.objects.filter(pk=c.pk).update(
        created_at=ahora - timezone.timedelta(days=dias_de_antiguedad))
    c.assigned_to.add(tecnico)
    c.refresh_from_db()
    return c


def _perfil(org, correo="tec@isp.test"):
    from common.models import Profile, User

    u = User.objects.create(email=correo, name="Tecnico", is_active=True)
    return Profile.objects.create(user=u, org=org, role="USER", is_active=True)


@pytest.fixture(autouse=True)
def _tecnicos_de_soporte(monkeypatch):
    """
    Todo perfil de estas pruebas es de SOPORTE TECNICO.

    Desde el 14/10/2026 el detector solo mira los tickets del area del
    Supervisor, y el area sale de la persona asignada. Sin esto, estas pruebas
    --que hablan de la COLA, no de las areas-- quedarian en cero por una razon
    que no es la suya, y el mensaje de error apuntaria al lugar equivocado.
    """
    from operaciones import areas_del_tenant as areas
    from common.models import Profile

    monkeypatch.setattr(
        areas, "area_por_persona",
        lambda: {str(p.id): areas.AREA_DEL_SUPERVISOR
                 for p in Profile.objects.all()})


def _propuesta_leida(org, caso):
    """Una propuesta que YA tiene su lectura, como las de produccion."""
    from operaciones.diagnostico_de_ticket import ETIQUETA_LECTURA, FUENTE

    ahora = timezone.now()
    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        accion_propuesta="Decidir que se hace", motivo="Ya se leyo.",
        evidencia=[
            {"fuente": "cases.Case", "id": str(caso.id), "dato": "abierto",
             "observado_en": ahora.isoformat()},
            {"fuente": FUENTE, "id": str(caso.id),
             "dato": f"{ETIQUETA_LECTURA}algo (confianza media)",
             "observado_en": ahora.isoformat()},
        ],
        prioridad=40, impacto="x",
        huella_condicion="h-" + uuid.uuid4().hex[:8],
        expira_en=ahora + timezone.timedelta(days=7))


def test_los_ya_leidos_dejan_lugar_a_los_que_faltan(org_a, monkeypatch):
    """
    EL CASO EXACTO DE PRODUCCION, en chico.

    Tope de 3. Cinco tickets, los 3 mas viejos ya leidos. Antes del arreglo el
    detector devolvia esos 3 y la vuelta no hacia nada; los 2 nuevos no entraban
    nunca.
    """
    monkeypatch.setattr(sup, "TOPE_TICKETS_DETECTADOS", 3)
    tecnico = _perfil(org_a)

    viejos = [_caso(org_a, 30 - i, tecnico=tecnico) for i in range(3)]
    for c in viejos:
        _propuesta_leida(org_a, c)
    nuevos = [_caso(org_a, 5 - i, tecnico=tecnico) for i in range(2)]

    senales = sup._tickets_abiertos_con_tecnico(org_a, timezone.now())
    vistos = {s.origen_id for s in senales}

    assert vistos, (
        "el detector no devolvio nada: con tres leidos y dos sin leer, la cola "
        "quedo atascada igual que en produccion")
    for c in viejos:
        assert str(c.id) not in vistos, (
            "un ticket YA LEIDO sigue ocupando lugar en la cola: eso es lo que "
            "hacia que se miraran siempre los mismos 40")
    for c in nuevos:
        assert str(c.id) in vistos, (
            "un ticket sin leer quedo afuera habiendo lugar")


def test_dos_vueltas_seguidas_no_traen_lo_mismo(org_a, monkeypatch):
    """
    LA PROPIEDAD QUE SE PERDIO: que la cola avance.

    Se afirma sobre el EFECTO --la segunda vuelta trae otros tickets-- y no
    sobre que la consulta tenga tal filtro. Un filtro escrito al reves pasaria
    una prueba que mirara el mecanismo.
    """
    monkeypatch.setattr(sup, "TOPE_TICKETS_DETECTADOS", 2)
    tecnico = _perfil(org_a, "otro@isp.test")
    casos = [_caso(org_a, 20 - i, tecnico=tecnico) for i in range(5)]

    primera = {s.origen_id for s in
               sup._tickets_abiertos_con_tecnico(org_a, timezone.now())}
    assert len(primera) == 2

    #  Se leen los de la primera vuelta, como haria el ciclo.
    for c in casos:
        if str(c.id) in primera:
            _propuesta_leida(org_a, c)

    segunda = {s.origen_id for s in
               sup._tickets_abiertos_con_tecnico(org_a, timezone.now())}

    assert segunda, "la segunda vuelta no trajo nada habiendo tres sin leer"
    assert not (primera & segunda), (
        f"la segunda vuelta repite lo de la primera: {primera & segunda}. "
        f"Asi, con 771 tickets y tope de 40, 731 no se miran nunca")


def test_una_propuesta_ACEPTADA_tampoco_vuelve_a_la_cola(org_a, monkeypatch):
    """
    Una aceptada tambien esta leida. Volver a leerla gastaria la vuelta en algo
    que una persona YA decidio, y encima desplazaria a uno sin mirar.
    """
    monkeypatch.setattr(sup, "TOPE_TICKETS_DETECTADOS", 5)
    tecnico = _perfil(org_a, "tres@isp.test")
    caso = _caso(org_a, 10, tecnico=tecnico)
    p = _propuesta_leida(org_a, caso)
    p.estado = PropuestaSupervisor.ACEPTADA
    p.save(update_fields=["estado"])

    vistos = {s.origen_id for s in
              sup._tickets_abiertos_con_tecnico(org_a, timezone.now())}
    assert str(caso.id) not in vistos


def test_un_ticket_sin_leer_si_entra(org_a, monkeypatch):
    """
    La contraparte: el arreglo NO puede vaciar la cola. Si vaciara, el sintoma
    seria identico al del atasco --el ciclo no lee nada-- y esta prueba lo
    separa.
    """
    monkeypatch.setattr(sup, "TOPE_TICKETS_DETECTADOS", 5)
    tecnico = _perfil(org_a, "cuatro@isp.test")
    caso = _caso(org_a, 8, tecnico=tecnico)

    vistos = {s.origen_id for s in
              sup._tickets_abiertos_con_tecnico(org_a, timezone.now())}
    assert str(caso.id) in vistos
