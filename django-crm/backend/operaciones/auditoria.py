# -*- coding: utf-8 -*-
"""
================================================================================
 AUDITORIA  --  se escribe en la que ya existe, no se inventa otra
================================================================================

POR QUE common.Activity Y NO UNA TABLA PROPIA
---------------------------------------------
Porque ya es el registro de auditoria del CRM y esta vivo: 516 filas, 241 de
ellas en los ultimos 7 dias (medido el 15/09/2026). Tiene lo que hace falta --
'user' (quien), 'action' (que), 'created_at' (cuando), 'org' (organizacion),
'metadata' (estado anterior, estado nuevo, motivo) y 'description'-- y su
registro de verbos ya incluye APPROVED, REJECTED y STATUS_CHANGED, que es
exactamente el flujo de revision.

Crear una tabla de auditoria para este modulo seria el tercer sistema: ya estan
'common.Activity' (el CRM) y 'asistente.audit_log' (el motor, que Fase 1
estreno). Cada uno cubre su dominio; un tercero solo agregaria un lugar mas
donde buscar.

LO QUE ESTO NO ES
-----------------
No convierte Activity en una agenda. Se ESCRIBE en ella un hecho en pasado --
"el Jefe de Operaciones acepto la propuesta X"-- que es exactamente para lo que
esta hecha. Lo que falta hacer vive en ActividadOperativa, que es otra tabla.

QUE PASA SI FALLA
-----------------
Nada se traga. Si no se puede anotar una transicion, la transicion no ocurre:
esto corre dentro de la misma transaccion que el cambio. Es lo contrario del
criterio del motor (donde perder una fila de auditoria no puede tumbar la
atencion a un cliente) y la diferencia es deliberada -- aca no hay ningun
cliente esperando, y una decision humana sin rastro no sirve para nada.
================================================================================
"""

from __future__ import annotations

from common.models import Activity

# Los dos tipos de entidad que este modulo audita. Se declaran en
# common.models.Activity.ENTITY_TYPE_CHOICES: un valor no declarado se guarda
# igual (Django valida 'choices' en formularios, no al guardar) pero queda
# divergiendo en silencio -- que es como 'AsignacionTrabajo.rol' termino con un
# 'tecnico_lider' que su propio modelo no documenta.
ENTIDAD_ACTIVIDAD = "ActividadOperativa"
ENTIDAD_PROPUESTA = "PropuestaSupervisor"
ENTIDAD_NOVEDAD = "NovedadOperativa"


def registrar(*, org, actor, accion: str, entidad: str, entidad_id,
              nombre: str = "", descripcion: str = "",
              estado_anterior: str = "", estado_nuevo: str = "",
              motivo: str = "", extra: dict | None = None) -> Activity:
    """
    Una fila de auditoría. Devuelve la fila escrita.

    'actor' es el Profile que decidió, o None cuando el autor es el Supervisor
    -- y esa distinción importa: una propuesta creada por la IA tiene
    'user=None' y se reconoce por eso, no por un usuario de sistema inventado
    que despues se confunda con una persona.
    """
    metadata = {k: v for k, v in {
        "estado_anterior": estado_anterior,
        "estado_nuevo": estado_nuevo,
        "motivo": motivo,
    }.items() if v}
    if extra:
        metadata.update(extra)

    return Activity.objects.create(
        org=org,
        user=actor,
        action=accion,
        entity_type=entidad,
        entity_id=entidad_id,
        entity_name=(nombre or "")[:255],
        description=descripcion or "",
        metadata=metadata,
    )


def historial(org, entidad: str, entidad_id):
    """Todo lo que le pasó a una entidad, lo más reciente primero."""
    return Activity.objects.filter(
        org=org, entity_type=entidad, entity_id=entidad_id
    ).order_by("-created_at")


def recientes(org, limite: int = 20):
    """
    Los últimos hechos registrados por este módulo, lo más reciente primero.

    Es el feed del tablero, y es lo único de esa pantalla que no existía en
    ninguna forma: 'historial' responde "qué le pasó a ESTA propuesta", y no
    hay manera de preguntar "qué pasó, en general, en la última hora".

    Se acota a las tres entidades de este módulo a propósito. 'common.Activity'
    es la auditoría del CRM entero -- sin el filtro, el feed del Supervisor se
    llenaría de contactos editados y correos enviados, que es cierto pero no es
    lo que esta pantalla pregunta.
    """
    return Activity.objects.filter(
        org=org,
        entity_type__in=[ENTIDAD_PROPUESTA, ENTIDAD_ACTIVIDAD, ENTIDAD_NOVEDAD],
    ).select_related("user", "user__user").order_by("-created_at")[:limite]
