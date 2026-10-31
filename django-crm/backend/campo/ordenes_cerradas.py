# -*- coding: utf-8 -*-
"""
================================================================================
 LAS ORDENES CERRADAS  --  30/10/2026
================================================================================

El usuario: «¿en Dexter a donde van los tickets cuando ya se cierran?», y la
pestaña Cerradas de Programacion que aprobo sobre el boceto: cada orden
cerrada con quien la cerro, como quedo el ticket del ISP, sus tiempos, que
hizo el tecnico, lo que reviso el Supervisor y SU historial.

EL HISTORIAL ES DE ESA ORDEN, Y NADA MAS
----------------------------------------
Pedido del usuario sobre el boceto: «esto de supervisor cargo material
tampoco debe ir ahi». El material y las novedades son del DIA de la
cuadrilla: viven en su log, en la pestaña Hoy. Aca entra solo lo que le paso
a esta orden: quien la asigno, salio, llego, sus reportes, termino, la
devolucion, quien la aprobo y el ticket del ISP.

LO QUE REVISO EL SUPERVISOR se lee de la foto que se guarda al aprobar
(`revision_del_cierre.guardar_foto`): una orden cerrada ya no se revisa, y
recalcularla diria otra cosa. Las cerradas antes de que existiera la foto no
la tienen, y se dice asi.

Sin datos que no hagan falta: el nombre y la direccion del cliente salen como
en la pestaña Hoy (la decision del 30/10, solo lo asignado); el telefono no.
================================================================================
"""
from __future__ import annotations

import datetime as dt

ASIGNACIONES = ("asignada_por_el_supervisor", "publicada_por_una_persona",
                "asignacion", "reasignacion")
REPORTES = {"inicio_campo": "inicio", "avance_campo": "avance",
            "bloqueo_campo": "bloqueo", "cierre_campo": "cierre"}
#: Lo que cierra el CRM con el ticket del ISP (`services/cierre_en_isp.py`).
TICKET_CERRADO = "ticket_isp_cerrado"
TICKET_NO_CERRADO = "ticket_isp_no_cerrado"
FOTO = "revision_al_aprobar"


def _nombre(profile) -> str:
    try:
        return (profile.user.name or "").strip() or "Una persona"
    except AttributeError:
        return "Una persona"


def del_rango(org, desde: dt.date, hasta: dt.date) -> dict:
    """Las cerradas entre `desde` y `hasta` (incluidos), en el dia de la
    empresa, de la mas reciente a la mas vieja."""
    from campo import reparto as R
    from campo.cuadrillas import JornadaDeCuadrilla
    from campo.models import EventoTrabajo, OrdenTrabajo
    from campo.niveles import asuntos_de_las_ordenes

    zona = R._zona_de(org)
    inicio = dt.datetime.combine(desde, dt.time(0, 0), tzinfo=zona)
    fin = dt.datetime.combine(hasta + dt.timedelta(days=1), dt.time(0, 0), tzinfo=zona)
    ordenes = list(OrdenTrabajo.objects
                   .filter(org=org, estado_operativo=OrdenTrabajo.CERRADA,
                           cerrada_en__gte=inicio, cerrada_en__lt=fin)
                   .select_related("tipo_trabajo_version__work_type")
                   .prefetch_related("asignaciones__profile__user")
                   .order_by("-cerrada_en"))
    asunto_de = asuntos_de_las_ordenes(org, ordenes)
    eventos = {}
    for ev in (EventoTrabajo.objects.filter(org=org, orden_id__in=[o.id for o in ordenes])
               .select_related("profile__user").order_by("created_at", "id")):
        eventos.setdefault(ev.orden_id, []).append(ev)

    filas = []
    for o in ordenes:
        evs = eventos.get(o.id, [])
        perfiles = [a.profile_id for a in o.asignaciones.all()]
        dia = (o.completada_campo_en or o.cerrada_en).astimezone(zona).date()
        jornada = (JornadaDeCuadrilla.objects
                   .filter(org=org, fecha=dia, integrantes__persona__profile_id__in=perfiles)
                   .select_related("cuadrilla").first())
        filas.append(_fila(o, evs, zona, asunto_de.get(o.id, ""),
                           jornada.cuadrilla.nombre if jornada else ""))
    return {
        "desde": desde.isoformat(), "hasta": hasta.isoformat(),
        "cuentas": {
            "cerradas": len(filas),
            "por_una_persona": sum(1 for f in filas if f["quien"]["de"] == "persona"),
            "por_el_supervisor": sum(1 for f in filas if f["quien"]["de"] == "supervisor"),
            "ticket_sin_cerrar": sum(1 for f in filas if f["ticket"]["estado"] == "no_cerrado"),
        },
        "ordenes": filas,
    }


def _fila(o, evs, zona, asunto, cuadrilla) -> dict:
    from campo import reparto as R
    from campo import tiempos_del_dia as TD

    cerrada = o.cerrada_en.astimezone(zona)
    tiempos = TD.tiempos_de([o], zona=zona, fecha=cerrada.date()).get(o.id) or {}
    version = o.tipo_trabajo_version
    return {
        "id": str(o.id),
        "numero": o.numero,
        "tipo": getattr(getattr(version, "work_type", None), "nombre", "") or "",
        "asunto": asunto,
        "barrio": R._localidad_de(o) or "",
        "cliente": o.cliente_nombre or "",
        "direccion": o.cliente_direccion or "",
        "cuadrilla": cuadrilla,
        "tecnicos": [_nombre(a.profile) for a in o.asignaciones.all()],
        "cerrada_en": cerrada.isoformat(),
        "quien": _quien(evs),
        "ticket": _ticket(o, evs),
        "tiempos": tiempos,
        "solucion": _solucion(evs),
        "revision": next((dict(ev.datos or {}) for ev in reversed(evs) if ev.tipo == FOTO), None),
        "historial": historial_de(o, evs, zona, tiempos),
    }


def _quien(evs) -> dict:
    aprobada = next((ev for ev in reversed(evs) if ev.tipo == "validacion_aprobada"), None)
    if aprobada is not None and aprobada.profile_id:
        return {"de": "persona", "nombre": _nombre(aprobada.profile)}
    if aprobada is not None or any(ev.tipo == "cerrada_por_el_supervisor" for ev in evs):
        return {"de": "supervisor", "nombre": "El Supervisor"}
    #  Cerrada sin aprobacion: la conciliacion de ordenes viejas.
    return {"de": "sin_registro", "nombre": ""}


def _ticket(o, evs) -> dict:
    if not str((o.contexto or {}).get("ticket") or "").strip():
        return {"estado": "sin_ticket", "detalle": ""}
    ultimo = next((ev for ev in reversed(evs)
                   if ev.tipo in (TICKET_CERRADO, TICKET_NO_CERRADO)), None)
    if ultimo is None:
        return {"estado": "sin_registro", "detalle": ""}
    if ultimo.tipo == TICKET_CERRADO:
        return {"estado": "cerrado", "detalle": ""}
    return {"estado": "no_cerrado", "detalle": str((ultimo.datos or {}).get("codigo") or "")}


def _solucion(evs) -> str:
    cierre = next((ev for ev in reversed(evs) if ev.tipo == "cierre_campo"), None)
    return str(((cierre.datos or {}).get("respuestas") or {}).get("solucion") or "") if cierre else ""


def historial_de(o, evs, zona, tiempos) -> list:
    """Lo que le paso a ESTA orden, en orden de hora: `[{cuando, texto, de}]`,
    `cuando` = «DD/MM HH:MM» en la hora de la empresa."""
    from campo.tiempos_del_dia import TERMINADAS

    salida = []
    termino = False

    def poner(ev, texto, de):
        salida.append({"cuando": ev.created_at.astimezone(zona).strftime("%d/%m %H:%M"),
                       "texto": texto, "de": de})

    for ev in evs:
        nuevo = (ev.datos or {}).get("nuevo_estado")
        if ev.tipo in ASIGNACIONES:
            if ev.tipo == "asignada_por_el_supervisor":
                poner(ev, "El Supervisor la asignó", "supervisor")
            else:
                poner(ev, f"{_nombre(ev.profile)} la asignó", "persona")
        elif nuevo == "en_camino":
            poner(ev, "Salió hacia la orden", "tecnico")
        elif nuevo == "en_sitio":
            extra = (f" ({tiempos['traslado_min']} min de camino)"
                     if tiempos.get("traslado_min") is not None else "")
            poner(ev, f"Llegó{extra}", "tecnico")
        elif nuevo == "cerrada":
            poner(ev, "Quedó cerrada", "persona" if ev.profile_id else "supervisor")
        elif nuevo in TERMINADAS and not termino:
            termino = True
            extra = (f" ({tiempos['en_sitio_min']} min en sitio)"
                     if tiempos.get("en_sitio_min") is not None
                     else f" (había llegado el {tiempos['llego']})"
                     if "/" in str(tiempos.get("llego") or "") else "")
            poner(ev, f"Terminó en campo{extra}", "tecnico")
        elif ev.tipo in REPORTES:
            poner(ev, f"Reportó {REPORTES[ev.tipo]}",
                  "alerta" if ev.tipo == "bloqueo_campo" else "tecnico")
        elif ev.tipo == "correccion_requerida":
            quien = _nombre(ev.profile) if ev.profile_id else "El Supervisor"
            poner(ev, f"{quien} la devolvió al técnico", "alerta")
        elif ev.tipo == "validacion_aprobada":
            if ev.profile_id:
                poner(ev, f"{_nombre(ev.profile)} la aprobó", "persona")
            else:
                poner(ev, "El Supervisor la aprobó", "supervisor")
        elif ev.tipo == TICKET_CERRADO:
            poner(ev, "Ticket cerrado en el sistema del ISP", "supervisor" if not ev.profile_id else "persona")
        elif ev.tipo == TICKET_NO_CERRADO:
            poner(ev, "No se pudo cerrar el ticket en el sistema del ISP", "alerta")
        elif ev.tipo == "ticket_cerrado_con_la_orden_cambiada":
            poner(ev, "El Supervisor cerró el ticket y la orden cambió en el medio", "alerta")
    return salida
