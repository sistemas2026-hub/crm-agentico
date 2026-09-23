# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE LA PANTALLA NECESITA SABER DE CADA HALLAZGO  --  solo lectura
================================================================================

La tabla del Supervisor tiene diez columnas y la propuesta solo trae cuatro:
tipo, accion, prioridad y estado. Las otras seis --caso/ticket, origen, tecnico,
zona, SLA y cuando se detecto-- viven en la entidad SOBRE LA QUE se emitio el
hallazgo, y hasta ahora no habia forma de leerlas desde la propuesta.

ESTO NO ES UNA SEGUNDA FUENTE DE VERDAD
---------------------------------------
No se copia ni un dato. Cada campo se lee de su dueño en el momento de
responder: el ticket externo de 'Case.external_ticket_id', la zona de
'OrdenTrabajo.zona', el tecnico de la asignacion vigente. Si mañana cambian
alli, la pantalla lo ve sin tocar nada.

LO QUE NO SE SABE SE DICE
-------------------------
Cada campo puede venir en None, y eso NO es un error: un hallazgo sobre un caso
no tiene tecnico de campo, y uno sobre una programacion no tiene ticket. La
pantalla pinta "—" y nadie tiene que adivinar si falta el dato o no aplica.
Ninguna funcion de aqui inventa un valor por defecto.

PII
---
Del cliente no sale nada: ni nombre, ni telefono, ni direccion, ni coordenadas.
Solo identificadores operativos y el nombre del COLABORADOR asignado, que es
quien trabaja el caso. Es el mismo criterio de lista blanca que rige en
'nucleo/seguridad/listas_blancas.py' para lo que viene de WispHub.
================================================================================
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

#  Como se nombra el origen en la pantalla.
WISPHUB = "wisphub"
DEXTER = "dexter"
DEXTER_Y_WISPHUB = "dexter+wisphub"


def _tecnico_de_orden(orden) -> dict | None:
    perfil = getattr(orden, "tecnico_principal", None)
    if perfil is None or getattr(perfil, "user", None) is None:
        return None
    return {"id": str(perfil.id),
            "nombre": perfil.user.name or perfil.user.email}


def _sla_de_orden(orden, ahora) -> dict:
    """
    El plazo de la orden. NO se calcula aqui: lo calcula 'operaciones/sla.py'.

    Es el mismo modulo que alimenta los detectores 'orden_sla_vencido' y
    'orden_sla_por_vencer', asi que la columna de la tabla y el hallazgo que la
    origino no pueden contradecirse. Si mañana cambia la ventana de aviso,
    cambia para los dos a la vez.
    """
    from operaciones import sla

    plazo = sla.plazo_de(orden, ahora=ahora)
    return {
        "estado": plazo.get("estado") or sla.DATOS_INSUFICIENTES,
        "vence_en": plazo.get("limite"),
        "minutos_restantes": plazo.get("minutos_restantes"),
        "minutos_atraso": plazo.get("minutos_atraso"),
        "datos_faltantes": plazo.get("datos_faltantes") or [],
        "fuente": "operaciones.sla",
    }


def _sla_de_caso(caso, ahora) -> dict:
    """
    El plazo del caso, dicho con LOS MISMOS SEIS ESTADOS que 'operaciones/sla.py'.

    POR QUE AQUI NO SE LLAMA A 'plazo_de'
    -------------------------------------
    'plazo_de' mide ORDENES DE TRABAJO: saca la duracion objetivo del tipo de
    trabajo congelado en la orden. Un caso no tiene tipo de trabajo -- tiene
    'sla_resolution_hours' y 'resolution_sla_deadline', que 'cases' ya calcula.

    Lo que NO se hace es inventar un segundo criterio: el veredicto sale de
    'is_sla_resolution_breached', que es del propio modelo, y el umbral de
    "esta por vencer" es 'sla.ventana_de_aviso' -- la MISMA funcion que usan
    los detectores de ordenes, con el mismo 20% con tope de 24 h. Un 48 fijo
    escrito aqui habria sido exactamente la logica paralela que este modulo
    existe para no crear.

    Los estados son los de 'operaciones/sla.py' y no unos propios, para que la
    columna signifique lo mismo venga de donde venga el hallazgo.
    """
    from operaciones import sla

    #  Un caso resuelto ya no tiene plazo corriendo: decir "vencido" de algo
    #  cerrado hace tres semanas describe el pasado como si fuera un pendiente.
    if getattr(caso, "resolved_at", None) is not None:
        return {"estado": sla.NO_APLICA, "vence_en": None,
                "minutos_restantes": None, "minutos_atraso": None,
                "datos_faltantes": [], "fuente": "cases.Case"}

    horas_objetivo = getattr(caso, "sla_resolution_hours", None)
    limite = getattr(caso, "resolution_sla_deadline", None)

    if limite is None:
        #  Sin fecha objetivo no hay plazo que medir. Se distingue de "no se
        #  pudo leer": aqui el dato se leyo y dice que no hay compromiso.
        return {"estado": sla.SIN_PLAZO, "vence_en": None,
                "minutos_restantes": None, "minutos_atraso": None,
                "datos_faltantes": ([] if horas_objetivo is not None else
                                    [{"campo": "sla_resolution_hours",
                                      "por_que": "el caso no declara plazo de resolución"}]),
                "fuente": "cases.Case"}

    minutos = (limite - ahora).total_seconds() / 60
    if getattr(caso, "is_sla_resolution_breached", False) or minutos < 0:
        return {"estado": sla.VENCIDA, "vence_en": limite.isoformat(),
                "minutos_restantes": None, "minutos_atraso": round(-minutos),
                "datos_faltantes": [], "fuente": "cases.Case"}

    #  La MISMA ventana que las ordenes: 20% del plazo, con tope de 24 h.
    ventana = sla.ventana_de_aviso(int((horas_objetivo or 0) * 60)) if horas_objetivo else 0
    estado = sla.VENCE_PRONTO if minutos <= ventana * 60 else sla.A_TIEMPO
    return {"estado": estado, "vence_en": limite.isoformat(),
            "minutos_restantes": round(minutos), "minutos_atraso": None,
            "datos_faltantes": [], "fuente": "cases.Case"}


def _zona_de_orden(orden, org):
    """
    La zona vive en la LINEA DEL PLAN, no en la orden.

    'OrdenTrabajo' no tiene columna 'zona': la escribe 'programar_orden' sobre
    'ProgramacionOrden'. Una orden sin programar no tiene zona todavia, y eso
    es un None honesto -- no un vacio que haya que rellenar.
    """
    from operaciones.models import ProgramacionOrden

    linea = (ProgramacionOrden.objects
             .filter(org=org, orden=orden,
                     estado__in=(ProgramacionOrden.PLANIFICADA,
                                 ProgramacionOrden.CONFIRMADA))
             .only("zona").first())
    return (linea.zona or None) if linea else None


def _origen_de_caso(caso) -> str:
    """
    De que sistema viene el caso.

    'provider' poblado = llego del proveedor. Que ADEMAS lo haya tocado el
    asistente se reconoce por tener responsable interno asignado: es lo unico
    observable hoy. Cuando exista una marca explicita de autoria del asistente,
    se cambia aca y la pantalla no se entera.
    """
    proveedor = (getattr(caso, "provider", "") or "").strip().lower()
    if not proveedor:
        return DEXTER
    tiene_responsable = caso.assigned_to.exists()
    return DEXTER_Y_WISPHUB if tiene_responsable else WISPHUB


def _de_caso(origen_id, org, ahora) -> dict:
    from cases.models import Case

    caso = (Case.objects.filter(id=origen_id, org=org)
            .prefetch_related("assigned_to__user").first())
    if caso is None:
        return {}
    asignado = caso.assigned_to.first()
    return {
        "caso": {
            "id": str(caso.id),
            "id_corto": str(caso.id)[:8],
            "nombre": caso.name,
            "estado": caso.status,
            "ticket_externo": caso.external_ticket_id or None,
            "proveedor": caso.provider or None,
            "estado_externo": caso.external_status or None,
            "estado_externo_leido_en": (caso.external_fetched_at.isoformat()
                                        if caso.external_fetched_at else None),
        },
        "estado_operativo": caso.status,
        "origen": _origen_de_caso(caso),
        "tecnico": ({"id": str(asignado.id),
                     "nombre": (asignado.user.name or asignado.user.email)}
                    if asignado and asignado.user else None),
        #  El caso no tiene zona en el CRM: la localidad vive en el proveedor y
        #  no se importa. Se declara None en vez de poner la ciudad de la
        #  cuenta, que es otra cosa.
        "zona": None,
        "sla": _sla_de_caso(caso, ahora),
    }


def _de_orden(origen_id, org, ahora) -> dict:
    from campo.models import OrdenTrabajo

    orden = (OrdenTrabajo.objects.filter(id=origen_id, org=org)
             .select_related("tipo_trabajo_version__work_type").first())
    if orden is None:
        return {}
    return {
        "orden": {
            "id": str(orden.id),
            "numero": orden.numero,
            "estado": orden.estado_operativo,
            "estado_validacion": orden.estado_validacion,
            "origen_sistema": orden.origen_sistema or None,
            "origen_ref": orden.origen_ref or None,
        },
        "estado_operativo": orden.estado_operativo,
        "origen": (orden.origen_sistema or None),
        "tecnico": _tecnico_de_orden(orden),
        "zona": _zona_de_orden(orden, org),
        "sla": _sla_de_orden(orden, ahora),
    }


def _de_actividad(origen_id, org, ahora) -> dict:
    from operaciones.models import ActividadOperativa

    #  'responsable' y nada mas: ActividadOperativa NO tiene 'orden' --lo
    #  descubrio la suite de M09-M, que revienta con FieldError si se pide.
    act = (ActividadOperativa.objects.filter(id=origen_id, org=org)
           .select_related("responsable__user").first())
    if act is None:
        return {}
    responsable = act.responsable
    return {
        "actividad": {"id": str(act.id), "titulo": act.titulo,
                      "estado": act.estado_operativo},
        "estado_operativo": act.estado_operativo,
        "origen": None,
        "tecnico": ({"id": str(responsable.id),
                     "nombre": (responsable.user.name or responsable.user.email)}
                    if responsable and responsable.user else None),
        "zona": None,
        "sla": None,
    }


#  Que resolver segun sobre que se emitio el hallazgo. Un tipo que no este aqui
#  devuelve el contexto vacio: la tabla pinta "—" y no se cae.
RESOLUTORES = {
    "case": _de_caso,
    "orden_trabajo": _de_orden,
    "actividad": _de_actividad,
}

VACIO = {"caso": None, "orden": None, "actividad": None, "tecnico": None,
         "zona": None, "origen": None, "sla": None, "estado_operativo": None}


def contexto_de(propuesta, ahora=None) -> dict:
    """
    Las seis columnas que la propuesta no tiene, leidas de su entidad de origen.

    Nunca levanta: si la entidad ya no existe --un caso borrado, una orden de
    otra organizacion-- devuelve el contexto vacio. Una propuesta historica
    tiene que poder leerse aunque su origen haya desaparecido.
    """
    ahora = ahora or timezone.now()
    resolutor = RESOLUTORES.get(propuesta.origen_tipo)
    if resolutor is None:
        return dict(VACIO, tipo=propuesta.origen_tipo)
    try:
        datos = resolutor(propuesta.origen_id, propuesta.org, ahora)
    except (ValueError, TypeError, ValidationError):
        #  'origen_id' es un CharField: guarda cualquier texto. Filtrar por un
        #  UUIDField con un valor que no lo es levanta ValidationError --no
        #  ValueError-- y sin esta rama una sola fila mal formada tumbaba la
        #  tabla entera. Lo encontro la prueba, no produccion.
        datos = {}
    return dict(VACIO, tipo=propuesta.origen_tipo, **datos)
