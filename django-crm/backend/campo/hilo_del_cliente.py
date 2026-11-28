# -*- coding: utf-8 -*-
"""
================================================================================
 EL HILO DEL CLIENTE NO SE CORTA  --  12/11/2026
================================================================================
Auditoria del menu (SPEC/AUDITORIA_MENU_2026-11-12.md §1 puntos 1-2, §4 items 5
y 6): las pantallas del ISP eran islas. Desde un ticket no se podia contestar
«¿hay tecnico asignado?», una orden no tenia pagina propia, y no habia un lugar
donde ver a UN cliente entero (sus chats, sus tickets, sus visitas).

Este modulo es la UNA definicion de esas uniones, para que el ticket, la pagina
de la orden y la ficha del cliente no las armen cada uno a su manera:

  * `caso_de_origen`      de que ticket nacio una orden (y si es de la misma
                          empresa). Lo usan `crear_orden` y la migracion 0049.
  * `ordenes_visibles`    que ordenes puede VER en resumen quien pregunta.
  * `resumen_de_orden`    lo que se muestra de una orden fuera de su pagina:
                          estado, tecnico, cuadrilla, fecha. Sin datos del
                          cliente: quien lo lee ya esta mirando al cliente.

QUIEN ES EL CLIENTE, Y POR QUE SOLO POR SU SERVICIO
---------------------------------------------------
El identificador del servicio en el sistema del ISP (`id_servicio`). Es el
mismo criterio que `services/historial_del_servicio.id_de_servicio` y que el
motor (`identidad_del_contexto`): nunca por nombre, telefono ni direccion --
agrupar por eso mostraria las visitas del vecino con cara de dato correcto.
================================================================================
"""
from __future__ import annotations

import re
import uuid

from django.db.models import Q

#: El unico `origen_tipo` que nombra un ticket del CRM.
ORIGEN_CASO = "case"

#: Lo que se acepta como identificador de servicio en una URL. El del ISP es
#: numerico hoy; se admite alfanumerico corto para el proximo proveedor, y nada
#: mas: ni barras ni espacios, que es como un parametro se vuelve otra ruta.
SERVICIO_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def caso_de_origen(org, origen_tipo, origen_ref):
    """El `Case` del que nacio una orden, o None.

    Solo si `origen_tipo` es «case», `origen_ref` es un id bien formado y el
    caso es de LA MISMA empresa. Cualquier otra cosa devuelve None y no une:
    un texto de otra empresa no puede volverse una union con su ticket.
    """
    if str(origen_tipo or "").strip() != ORIGEN_CASO:
        return None
    try:
        pk = uuid.UUID(str(origen_ref or "").strip())
    except (ValueError, AttributeError):
        return None
    from cases.models import Case

    org_id = getattr(org, "pk", org)
    return Case.objects.filter(pk=pk, org_id=org_id).first()


# =============================================================================
#  QUIEN VE QUE
# =============================================================================

def es_gestion(profile, user) -> bool:
    """La misma regla que `views._debe_estar_asignado` y `PuedeAccederOrden`:
    la gestion ve toda orden de su empresa; el resto, solo las suyas."""
    from campo.permissions import ROLES_GESTION

    rol = (getattr(profile, "role", "") or "").upper()
    return rol in ROLES_GESTION or bool(getattr(user, "is_superuser", False))


def ordenes_visibles(org, profile, user):
    """Las ordenes de las que `profile` puede ver el RESUMEN.

    La gestion, todas las de su empresa. Cualquier otro, las que tiene
    asignadas y las que nacieron de un ticket que puede abrir: quien atiende un
    ticket necesita saber si hay tecnico, sin que eso le abra la orden entera
    (la pagina de la orden sigue con su propio permiso: `puede_abrir`).
    Fail-closed: sin perfil, ninguna.
    """
    from campo.models import OrdenTrabajo

    qs = OrdenTrabajo.objects.filter(org=org)
    if profile is None:
        return qs.none()
    if es_gestion(profile, user):
        return qs
    from cases.access import visible_cases_qs

    return qs.filter(Q(asignaciones__profile=profile)
                     | Q(caso__in=visible_cases_qs(profile).values("pk"))).distinct()


def puede_abrir(orden, profile, user) -> bool:
    """Si la pagina de la orden le va a responder. Misma regla que
    `views._obtener_orden_o_404`, dicha antes para no dibujar un enlace a un
    404."""
    if profile is None:
        return False
    if es_gestion(profile, user):
        return True
    return any(a.profile_id == profile.id for a in orden.asignaciones.all())


# =============================================================================
#  LO QUE SE MUESTRA DE UNA ORDEN FUERA DE SU PAGINA
# =============================================================================

def _zona_de(org):
    from campo.reparto import _zona_de as zona

    return zona(org)


def _fecha_de(orden, zona) -> str | None:
    """El dia de la visita: el que le armo el Supervisor, o el programado en la
    hora de la empresa (no la del servidor, que es UTC)."""
    if orden.orden_del_dia_fecha:
        return orden.orden_del_dia_fecha.isoformat()
    if orden.programada_para:
        return orden.programada_para.astimezone(zona).date().isoformat()
    return None


def _cuadrilla_del_dia(orden, principal, fecha_iso):
    """La cuadrilla con que sale el responsable ese dia, o None. La regla de
    quien RECIBE sus ordenes (`dia_publicado.jornada_de_la_persona`)."""
    if principal is None or not fecha_iso:
        return None
    import datetime as dt

    from campo.dia_publicado import jornada_de_la_persona

    j = jornada_de_la_persona(orden.org, principal, dt.date.fromisoformat(fecha_iso))
    return j.cuadrilla.nombre if j is not None else None


def _iso(valor):
    return valor.isoformat() if valor else None


def resumen_de_orden(orden, *, abrir: bool, zona=None) -> dict:
    """Estado, tecnico, cuadrilla y fecha de una orden. SIN datos del cliente:
    quien lo lee ya esta mirando al cliente (en su ticket o en su ficha), y el
    telefono y el GPS solo los necesita quien va a la casa."""
    from campo.services.inventario import nombre_de

    zona = zona or _zona_de(orden.org)
    asignaciones = list(orden.asignaciones.all())
    principal = next((a.profile for a in asignaciones if a.es_principal), None)
    fecha = _fecha_de(orden, zona)
    return {
        "id": str(orden.id),
        "numero": orden.numero,
        "tipo": orden.tipo_trabajo_version.work_type.nombre,
        "estado_operativo": orden.estado_operativo,
        "estado_etiqueta": orden.get_estado_operativo_display(),
        "estado_validacion": orden.estado_validacion,
        "prioridad": orden.prioridad,
        "tecnico": nombre_de(principal) if principal is not None else None,
        "integrantes": len(asignaciones),
        "cuadrilla": _cuadrilla_del_dia(orden, principal, fecha),
        "fecha": fecha,
        "programada_para": _iso(orden.programada_para),
        "completada_campo_en": _iso(orden.completada_campo_en),
        "cerrada_en": _iso(orden.cerrada_en),
        "caso_id": str(orden.caso_id) if orden.caso_id else None,
        "puede_abrir": abrir,
    }


def resumenes(qs, profile, user) -> list[dict]:
    filas = list(qs.select_related("tipo_trabajo_version__work_type", "org")
                   .prefetch_related("asignaciones__profile__user")
                   .order_by("-created_at")[:50])
    if not filas:
        return []
    zona = _zona_de(filas[0].org)
    return [resumen_de_orden(o, abrir=puede_abrir(o, profile, user), zona=zona)
            for o in filas]


# =============================================================================
#  LAS PREGUNTAS: el ticket, el servicio, la orden
# =============================================================================

def ordenes_del_caso(caso, profile, user) -> list[dict]:
    """Las visitas de un ticket, por el FK (campo/0049)."""
    return resumenes(ordenes_visibles(caso.org, profile, user).filter(caso=caso),
                     profile, user)


def ordenes_del_servicio(org, servicio, profile, user) -> list[dict]:
    """Las visitas a un servicio: por el abonado copiado en la orden (el
    criterio de `historial_del_servicio`) o por el servicio de su ticket."""
    qs = ordenes_visibles(org, profile, user).filter(
        Q(cliente_id_abonado=servicio) | Q(contexto__servicio=servicio)
        | Q(caso__external_service_id=servicio))
    return resumenes(qs, profile, user)


def tickets_del_servicio(profile, servicio, limite: int = 50) -> list[dict]:
    """Los tickets del servicio que `profile` puede abrir (la regla de la cola,
    `cases.access.visible_cases_qs`). Solo el titulo, que es lo que la cola ya
    muestra: ni descripcion ni hilo."""
    from cases.access import visible_cases_qs

    casos = (visible_cases_qs(profile).filter(external_service_id=servicio)
             .order_by("-created_at")[:limite])
    return [{
        "id": str(c.id),
        "nombre": c.name,
        "estado": c.status,
        "prioridad": c.priority,
        "external_ticket_id": c.external_ticket_id or None,
        "external_status": c.external_status or None,
        "creado_en": _iso(c.created_at),
    } for c in casos]


def solicitudes_de_los_tickets(org, profile, user, tickets_isp) -> list[dict] | None:
    """Las solicitudes de instalacion cuyo ticket del ISP es uno de los del
    servicio. None (no «ninguna») para quien no es de gestion: la bandeja de
    Instalaciones decide su propio rol (agente D) y aca no se abre antes.

    Solo estado, tipo, plan y fechas: la solicitud trae documento, foto de
    cedula y GPS, y nada de eso hace falta para saber en que quedo.
    """
    if not es_gestion(profile, user):
        return None
    ids = [t for t in tickets_isp if t]
    if not ids:
        return []
    from solicitudes.models import SolicitudServicio

    return [{
        "id": str(s.id),
        "estado": s.estado,
        "estado_etiqueta": s.get_estado_display(),
        "tipo_solicitud": s.tipo_solicitud,
        "plan_interesado": s.plan_interesado,
        "ticket_wisphub": s.ticket_wisphub,
        "enviada_en": _iso(s.enviada_en),
        "revisada_en": _iso(s.revisada_en),
    } for s in SolicitudServicio.objects.filter(org=org, ticket_wisphub__in=ids)
                                        .order_by("-created_at")[:50]]


def ficha_del_cliente(org, servicio, profile, user) -> dict:
    """Lo que el CRM sabe de un servicio, en una respuesta. Las conversaciones
    y el estado del equipo los da el motor (la capa servidor del frontend los
    junta): Django no habla con el ISP a proposito."""
    tickets = tickets_del_servicio(profile, servicio)
    return {
        "servicio": servicio,
        "tickets": tickets,
        "ordenes": ordenes_del_servicio(org, servicio, profile, user),
        "solicitudes": solicitudes_de_los_tickets(
            org, profile, user, [t["external_ticket_id"] for t in tickets]),
    }


def servicio_de_la_orden(orden) -> str:
    """El servicio de una orden: el de `historial_del_servicio` y, si la orden
    no lo copio, el de su ticket."""
    from campo.services.historial_del_servicio import id_de_servicio

    servicio = id_de_servicio(orden)
    if not servicio and orden.caso_id:
        servicio = (orden.caso.external_service_id or "").strip()
    return servicio


def hilo_de_la_orden(orden) -> dict:
    """Lo que la pagina de la orden necesita ademas de su bitacora y su
    material: de que ticket y de que servicio es, para enlazarlos, y quien va.
    Sin telefono ni GPS: el mismo recorte que `programacion-noc.js::leerOrden`,
    hecho aca para que no viajen."""
    from campo.serializers import _cuadrilla

    caso = orden.caso
    return {
        **resumen_de_orden(orden, abrir=True),
        "resumen": orden.resumen,
        "zona": orden.zona,
        "cliente": {"nombre": orden.cliente_nombre or None,
                    "direccion": orden.cliente_direccion or None},
        "servicio": servicio_de_la_orden(orden) or None,
        "ventana_inicio": _iso(orden.ventana_inicio),
        "ventana_fin": _iso(orden.ventana_fin),
        "sla_vence_en": _iso(orden.sla_vence_en),
        "iniciada_en": _iso(orden.iniciada_en),
        "vuelta": orden.vuelta,
        "cuadrilla_integrantes": [
            {"nombre": c["nombre"], "rol": c["rol_display"],
             "es_principal": c["es_principal"]} for c in _cuadrilla(orden)],
        "caso": ({"id": str(caso.id), "nombre": caso.name, "estado": caso.status,
                  "external_ticket_id": caso.external_ticket_id or None}
                 if caso is not None else None),
        "evidencias": [{
            "id": str(e.id),
            "requisito_id": e.requisito_id,
            "nombre": e.nombre_original,
            "mime_type": e.mime_type,
            "estado": e.estado_archivo,
            "de_un_reporte": bool(e.evento_id),
            "vuelta": e.vuelta,
        } for e in orden.evidencias.order_by("recibida_en_servidor")],
    }
