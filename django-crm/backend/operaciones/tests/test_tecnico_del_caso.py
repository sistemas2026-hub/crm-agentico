# -*- coding: utf-8 -*-
"""
================================================================================
 EL TECNICO EN LA BANDEJA, CUANDO LA PROPUESTA SALE DE UN CASO
================================================================================

DE DONDE SALE
-------------
Medido en produccion el 13/10/2026, mirando la bandeja: las seis propuestas de
tickets leidos decian «Sin tecnico asignado», las seis.

Y no podia ser. El detector que las pone ahi exige justamente lo contrario
--'assigned_to__isnull=False', que fue lo que el cliente pidio con esas
palabras: "solo los que tienen un tecnico asignado"-- asi que la pantalla
estaba contradiciendo a la condicion que las habia traido.

La causa: 'contexto_propuesta' llenaba 'tecnico' SOLO para las propuestas que
salen de una ORDEN de trabajo. Para las que salen de un CASO la clave quedaba
vacia, y la celda vacia se dibuja como «Sin tecnico asignado» -- que no es un
hueco, es una afirmacion, y era falsa.

LO QUE SE AFIRMA
----------------
El VALOR que sale del contexto, no que el codigo consulte tal campo. Una
prueba que mirara la consulta pasaria igual con el nombre equivocado adentro.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from operaciones import contexto_propuesta
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db


def _caso(org, **extra):
    from cases.models import Case

    datos = dict(
        org=org,
        name="Internet intermitente",
        status="Assigned",
        priority="Normal",
        provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="6580",
    )
    datos.update(extra)
    return Case.objects.create(**datos)


def _propuesta_de(org, caso):
    return PropuestaSupervisor.objects.create(
        org=org,
        tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case",
        origen_id=str(caso.id),
        accion_propuesta="Decidir que se hace con este ticket",
        motivo="Sigue abierto en el proveedor.",
        #  La base EXIGE evidencia ('propuesta_exige_evidencia'): una propuesta
        #  sin con que respaldarse no se puede guardar, y esta bien que asi sea.
        evidencia=[{
            "fuente": "cases.Case",
            "id": str(caso.id),
            "dato": f"ticket {caso.external_ticket_id} sigue abierto",
            "observado_en": timezone.now().isoformat(),
        }],
        prioridad=40,
        impacto="Tiempo que corre sin decision",
        huella_condicion="huella-" + uuid.uuid4().hex[:8],
        expira_en=timezone.now() + timezone.timedelta(days=7),
    )


def _tecnico_de(org, caso):
    p = _propuesta_de(org, caso)
    return contexto_propuesta.contexto_de(org, [p])[str(p.id)]["tecnico"]


def _perfil(org, correo, nombre=""):
    """Alguien que puede tener un caso asignado."""
    from common.models import Profile, User

    #  'name' en un solo campo: este User no es el de Django por defecto.
    u = User.objects.create(email=correo, name=nombre, is_active=True)
    return Profile.objects.create(user=u, org=org, role="USER", is_active=True)


def test_el_tecnico_del_caso_llega_a_la_bandeja(org_a):
    caso = _caso(org_a)
    caso.assigned_to.add(_perfil(org_a, "tecnico1@isp.test", "Hector Ruiz"))

    assert _tecnico_de(org_a, caso) == "Hector Ruiz", (
        "el caso tiene tecnico y la bandeja lo dibuja como «Sin tecnico "
        "asignado»: contradice a la condicion que puso la propuesta ahi")


def test_sin_nombre_se_lo_nombra_por_lo_que_el_sistema_ya_guarda(org_a):
    """
    MEDIDO, no supuesto: 'common.User.save' rellena 'name' con la parte
    anterior a la arroba la primera vez que se guarda, asi que un usuario sin
    nombre NUNCA llega aqui con 'name' vacio.

    La primera version de esta prueba esperaba el correo entero y el rojo
    mostro el comportamiento real -- que ademas es el que conviene: la celda
    dice «tecnico2» y no publica la direccion completa de alguien.

    La rama del correo sigue en el codigo como respaldo y no sobra: nada
    impide que alguien deje 'name' en blanco despues de creado.
    """
    caso = _caso(org_a)
    caso.assigned_to.add(_perfil(org_a, "tecnico2@isp.test"))

    assert _tecnico_de(org_a, caso) == "tecnico2"


def test_con_dos_asignados_se_ve_que_hay_mas(org_a):
    #  Elegir uno en silencio esconderia que hay mas gente en el caso.
    caso = _caso(org_a)
    caso.assigned_to.add(_perfil(org_a, "a@isp.test", "Ana Diaz"))
    caso.assigned_to.add(_perfil(org_a, "b@isp.test", "Beto Paz"))

    valor = _tecnico_de(org_a, caso)
    assert valor.endswith("+1"), f"no se ve que hay otro asignado: {valor!r}"


def test_sin_asignar_sigue_diciendo_que_no_hay(org_a):
    #  La ausencia tiene que seguir siendo distinguible: el arreglo NO puede
    #  inventar un nombre para rellenar la celda.
    assert _tecnico_de(org_a, _caso(org_a)) == ""
