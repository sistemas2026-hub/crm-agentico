# -*- coding: utf-8 -*-
"""
================================================================================
 LOS TIEMPOS DEL DIA  --  30/10/2026
================================================================================

El usuario: «¿cómo le lleva el Supervisor el seguimiento a los técnicos, de
cuánto han demorado?», y que se vea en Programación («dale»).

QUE SE CALCULA, por orden, con la bitacora (`EventoTrabajo`): a que hora salio
(en camino), a que hora llego (en sitio) y a que hora termino (completada en
campo); de ahi el TRASLADO y el TIEMPO EN SITIO. Por cuadrilla: a que hora
salio a la primera y cuantas lleva hechas. Lo calcula el codigo (CLAUDE.md §4:
el modelo no suma).

LA HORA ES LA DEL SERVIDOR: la del evento que dejo el cambio de estado. Con la
app sin señal, el cambio sube despues y la hora es la de cuando subio --un
traslado puede salir mas largo de lo que fue--. Se dice en la pantalla, no se
corrige adivinando.

LO DE OTRO DIA LLEVA SU FECHA (30/10/2026). Una OT quedo «en sitio» el 15/10 a
las 18:43 y nadie la cerro: el cuadro de su cuadrilla decia «21159 min» y
«salió 18:43», como si hubiera salido hoy. Ahora: una hora de otro dia va con
su fecha («15/10 18:43»); los minutos solo se cuentan si empezo HOY; y «salió»
es la primera salida DEL DIA, no la primera de la historia de sus ordenes.
================================================================================
"""

from __future__ import annotations

from django.utils import timezone

EN_CAMINO = "en_camino"
EN_SITIO = "en_sitio"
TERMINADAS = ("completada_campo", "cerrada")


def _minutos(desde, hasta):
    if desde is None or hasta is None or hasta < desde:
        return None
    return int((hasta - desde).total_seconds() // 60)


def _hm(d, zona, dia):
    """«HH:MM» si es del dia; «DD/MM HH:MM» si no. None sin hora."""
    if d is None:
        return None
    local = d.astimezone(zona)
    return local.strftime("%H:%M") if local.date() == dia else local.strftime("%d/%m %H:%M")


def _es_de_hoy(d, zona, ahora):
    return d is not None and d.astimezone(zona).date() == ahora.astimezone(zona).date()


def _mismo_dia(a, b, zona):
    """Un traslado o un tiempo en sitio se cuenta en minutos solo si empezo y
    termino el mismo dia: la OT que llego el 15/10 y se cerro el 30/10 no
    estuvo «21188 min en sitio»."""
    return (a is not None and b is not None
            and a.astimezone(zona).date() == b.astimezone(zona).date())


def _con_fecha(hora: str | None) -> bool:
    """Si una hora de `_hm` es de otro dia (lleva «DD/MM»)."""
    return bool(hora) and "/" in hora


def tiempos_de(ordenes, *, zona, ahora=None, fecha=None) -> dict:
    """{orden.id: {"salio", "llego", "termino", "traslado_min", "en_sitio_min",
    "en_sitio_hace_min", "en_sitio_desde"}}. Las horas, «HH:MM» en la zona de
    la empresa, con su fecha si no son de `fecha` (por defecto, hoy); lo que no
    paso, None. Esta en sitio AHORA: `en_sitio_hace_min` si llego hoy, y si
    llego otro dia, `en_sitio_desde` con la fecha. UNA consulta para todas."""
    from campo.models import EventoTrabajo

    ahora = ahora or timezone.now()
    dia = fecha or ahora.astimezone(zona).date()
    ids = [o.id for o in ordenes]
    primero = {}
    for orden_id, datos, cuando in (
            EventoTrabajo.objects.filter(orden_id__in=ids)
            .filter(datos__nuevo_estado__in=[EN_CAMINO, EN_SITIO, *TERMINADAS])
            .order_by("created_at").values_list("orden_id", "datos", "created_at")):
        estado = (datos or {}).get("nuevo_estado")
        clave = "termino" if estado in TERMINADAS else estado
        primero.setdefault((orden_id, clave), cuando)

    def hm(d):
        return _hm(d, zona, dia)

    salida = {}
    for o in ordenes:
        salio = primero.get((o.id, EN_CAMINO))
        llego = primero.get((o.id, EN_SITIO))
        termino = primero.get((o.id, "termino")) or getattr(o, "completada_campo_en", None)
        ahi = o.estado_operativo == EN_SITIO and termino is None and llego is not None
        salida[o.id] = {
            "salio": hm(salio),
            "llego": hm(llego),
            "termino": hm(termino),
            "traslado_min": _minutos(salio, llego) if _mismo_dia(salio, llego, zona) else None,
            "en_sitio_min": _minutos(llego, termino) if _mismo_dia(llego, termino, zona) else None,
            #  Esta en sitio AHORA: cuanto lleva, si llego hoy; si llego otro
            #  dia, desde cuando, con la fecha (no «21159 min»).
            "en_sitio_hace_min": (_minutos(llego, ahora)
                                  if ahi and _es_de_hoy(llego, zona, ahora) else None),
            "en_sitio_desde": (llego.astimezone(zona).strftime("%d/%m %H:%M")
                               if ahi and not _es_de_hoy(llego, zona, ahora) else None),
        }
    return salida


def resumen_de_la_cuadrilla(ordenes, tiempos: dict, *, asuntos=None,
                            ahora=None, zona=None, fecha=None) -> dict:
    """A que hora salio HOY a la primera, cuantas lleva hechas de cuantas, y en
    cual esta ahora (en camino o en sitio): su asunto y desde cuando. Desde que
    ENTRO a ese estado la ultima vez; los minutos, solo si fue hoy --si fue
    otro dia, `desde` lleva la fecha y `minutos` es None--."""
    import datetime as dt

    from campo.models import EventoTrabajo

    ahora = ahora or timezone.now()
    zona = zona or dt.timezone.utc
    dia = fecha or ahora.astimezone(zona).date()
    inicio = dt.datetime.combine(dia, dt.time(0, 0), tzinfo=zona)
    primera = (EventoTrabajo.objects
               .filter(orden_id__in=[o.id for o in ordenes], datos__nuevo_estado=EN_CAMINO,
                       created_at__gte=inicio, created_at__lt=inicio + dt.timedelta(days=1))
               .order_by("created_at").values_list("created_at", flat=True).first())
    en_curso = next((o for o in ordenes if o.estado_operativo in (EN_CAMINO, EN_SITIO)), None)
    curso = None
    if en_curso is not None:
        desde = (EventoTrabajo.objects
                 .filter(orden_id=en_curso.id, datos__nuevo_estado=en_curso.estado_operativo)
                 .order_by("-created_at").values_list("created_at", flat=True).first())
        de_hoy = _es_de_hoy(desde, zona, ahora)
        curso = {"numero": en_curso.numero, "estado": en_curso.estado_operativo,
                 "desde": (None if desde is None
                           else desde.astimezone(zona).strftime("%H:%M" if de_hoy
                                                                else "%d/%m %H:%M")),
                 "asunto": (asuntos or {}).get(en_curso.id, ""),
                 "minutos": _minutos(desde, ahora) if de_hoy else None}
    return {
        "salio": _hm(primera, zona, dia),
        "hechas": sum(1 for o in ordenes if o.estado_operativo in TERMINADAS),
        "total": len(ordenes),
        "en_curso": curso,
    }


#: Lo que reporta el tecnico (`services/seguimiento_campo.TIPOS`), como se dice.
REPORTES = {"inicio_campo": "inicio", "avance_campo": "avance",
            "bloqueo_campo": "bloqueo", "cierre_campo": "cierre"}
ASIGNACIONES = ("asignada_por_el_supervisor", "publicada_por_una_persona",
                "asignacion", "reasignacion")


def log_del_dia(ordenes, *, fecha, zona, tiempos, novedades=(), material=None,
                sin_reporte=None, ahora=None) -> list:
    """El log del dia de una cuadrilla (30/10/2026, el usuario: «un log
    contraible de los seguimientos que le ha hecho el Supervisor al tecnico»):
    lo que hizo el Supervisor y lo que reporto el tecnico, en orden de hora.

        [{"hora": "HH:MM", "texto": str, "de": supervisor|persona|tecnico|alerta}]

    Sin datos del cliente: numeros de orden, nada mas. Las asignaciones del
    mismo minuto y de la misma mano van en una linea («OT #12, #15, #19»).
    `material` = (kit, cuando se cargo) o None; `sin_reporte` = {numero,
    minutos} o None, y va al final: es AHORA.
    """
    from collections import defaultdict

    from campo.models import EventoTrabajo

    ahora = ahora or timezone.now()
    numero = {o.id: o.numero for o in ordenes}
    entradas = []
    asignadas = defaultdict(list)
    for ev in (EventoTrabajo.objects.filter(orden_id__in=list(numero))
               .select_related("profile__user").order_by("created_at")):
        if ev.created_at.astimezone(zona).date() != fecha:
            continue
        n = numero[ev.orden_id]
        nuevo = (ev.datos or {}).get("nuevo_estado")
        t = tiempos.get(ev.orden_id) or {}
        if ev.tipo in ASIGNACIONES:
            quien = ("El Supervisor" if ev.tipo == "asignada_por_el_supervisor"
                     else (getattr(getattr(ev.profile, "user", None), "name", "")
                           or "Una persona"))
            asignadas[(ev.created_at.replace(second=0, microsecond=0), quien)].append(n)
        elif nuevo == EN_CAMINO:
            entradas.append((ev.created_at, f"Salió hacia OT #{n}", "tecnico"))
        elif nuevo == EN_SITIO:
            extra = (f" ({t['traslado_min']} min de camino)"
                     if t.get("traslado_min") is not None else "")
            entradas.append((ev.created_at, f"Llegó a OT #{n}{extra}", "tecnico"))
        elif nuevo in TERMINADAS:
            extra = (f" ({t['en_sitio_min']} min en sitio)"
                     if t.get("en_sitio_min") is not None
                     else f" (había llegado el {t['llego']})"
                     if _con_fecha(t.get("llego")) else "")
            entradas.append((ev.created_at, f"Terminó OT #{n}{extra}", "tecnico"))
        elif ev.tipo in REPORTES:
            entradas.append((ev.created_at, f"Reportó {REPORTES[ev.tipo]} en OT #{n}",
                             "alerta" if ev.tipo == "bloqueo_campo" else "tecnico"))
        elif ev.tipo == "bloqueo_detuvo_el_trabajo":
            entradas.append((ev.created_at, f"OT #{n} quedó detenida por un bloqueo", "alerta"))
        elif ev.tipo == "bloqueo_libero_el_trabajo":
            entradas.append((ev.created_at, f"OT #{n} se destrabó", "tecnico"))
    for (minuto, quien), nums in asignadas.items():
        entradas.append((minuto, f"{quien} le asignó OT "
                                 + ", ".join(f"#{x}" for x in sorted(set(nums))),
                         "supervisor" if quien == "El Supervisor" else "persona"))
    if material is not None and material[1] is not None:
        kit, cuando = material
        entradas.append((cuando, f"El Supervisor cargó el material{f' ({kit})' if kit else ''}",
                         "supervisor"))
    #  Los recordatorios que el Supervisor le mando al telefono (30/10/2026,
    #  `recordatorio_de_reporte.py`), con si llegaron.
    from campo.avisos import AvisoEnviado
    from campo.services.avisos import CLAVE_SIN_REPORTE

    import datetime as dt

    por_id = {str(i): n for i, n in numero.items()}
    inicio = dt.datetime.combine(fecha, dt.time(0, 0), tzinfo=zona)
    for clave, canales, cuando in (
            AvisoEnviado.objects
            .filter(clave__startswith=f"{CLAVE_SIN_REPORTE}|", created_at__gte=inicio,
                    created_at__lt=inicio + dt.timedelta(days=1))
            .values_list("clave", "canales", "created_at")):
        partes = clave.split("|")
        n = por_id.get(partes[1]) if len(partes) > 2 else None
        if n is None:
            continue
        llego = "" if "push" in (canales or []) else " (no llegó al teléfono)"
        entradas.append((cuando, f"El Supervisor le recordó reportar en OT #{n}{llego}",
                         "supervisor"))
    for nov in novedades:
        entradas.append((nov.avisada_en, f"Avisó novedad: {nov.get_tipo_display().lower()} "
                                         f"({nov.get_afecta_display().lower()})", "alerta"))
        if nov.resuelta_en is not None:
            entradas.append((nov.resuelta_en, "Siguió después de la novedad", "tecnico"))

    entradas.sort(key=lambda e: e[0])
    salida = [{"hora": d.astimezone(zona).strftime("%H:%M"), "texto": texto, "de": de}
              for d, texto, de in entradas]
    if sin_reporte:
        salida.append({"hora": ahora.astimezone(zona).strftime("%H:%M"),
                       "texto": f"Sin reporte hace {sin_reporte['minutos']} min en "
                                f"OT #{sin_reporte['numero']}",
                       "de": "alerta"})
    return salida
