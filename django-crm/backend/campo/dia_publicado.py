"""
================================================================================
 EL DIA PUBLICADO  --  28/10/2026
================================================================================
Lo que quedo publicado para un dia: por cuadrilla, cada orden con su barrio, su
prioridad y su estado, a quien se la dieron, QUIEN la asigno y a que hora --el
Supervisor o una persona--, y si a esa gente le llego el aviso. Mas lo que no
quedo con ninguna cuadrilla de ese dia: lo que tiene a alguien que hoy no sale,
y lo que espera sin nadie (lo que quedo afuera por el cupo).

Pedido del usuario el 28/10: «cuando el supervisor publique, salga en
Programacion lo que publico», con la pantalla de Programacion despues de
Despacho. Despacho es lo que FALTA; esto es lo que QUEDO.

SOLO LEE. Las reglas son las del reparto, no una copia: la orden es de la
cuadrilla cuya gente la tiene (`cuadrillas.destinatarios`), una orden
programada para otro dia no cuenta (`reparto._para_otro_dia`), y lo que espera
es lo que el reparto puede mover (`reparto.ESTADOS_QUE_ESPERAN`).

QUIEN LA ASIGNO sale de la bitacora de la orden (`EventoTrabajo`), el ultimo
de: `asignada_por_el_supervisor` (sin persona: el Supervisor),
`publicada_por_una_persona` (el boton «Publicar» de Cuadrillas, desde el
28/10/2026), `asignacion` y `reasignacion` (Despachar a mano). Lo publicado con
el boton ANTES de esa fecha no dejo quien: dice «sin registro», que es la
verdad, y no se adivina.

EL AVISO: si el aviso de la asignacion SALIO AL TELEFONO. No alcanza con que
exista la notificacion (`avisos.VERBO_ASIGNADO` con la orden, o
`avisos.VERBO_JORNADA` con su numero): se crea aunque nadie tenga telefono, y
entonces el envio ni se intenta. Lo que dice si salio es el registro del envio
(`AvisoEnviado`): «push» en sus canales = Google lo ACEPTO para un telefono
(aceptado, no leido). Medido en produccion el 28/10/2026: la pantalla decia
«Avisado» en dos ordenes de un tecnico y «Sin telefono registrado» en la
tercera --las tres del mismo tecnico, que no tiene telefono--.

Por eso, en este orden: enviado al telefono; si no, nadie de la orden tiene
telefono; si no, se aviso y no llego al telefono; si no, sin aviso.
================================================================================
"""

from __future__ import annotations

import datetime as dt

#: De la bitacora de la orden, los eventos que dicen quien se la dio a quien.
EVENTOS_DE_ASIGNACION = ("asignada_por_el_supervisor", "publicada_por_una_persona",
                         "asignacion", "reasignacion")

SUPERVISOR = "supervisor"
PERSONA = "persona"

AVISADO = "avisado"
NO_LLEGO = "no_llego"
SIN_AVISO = "sin_aviso"
SIN_TELEFONO = "sin_telefono"

#: Cuantos dias atras se buscan los avisos: una orden del dia puede haberse
#: asignado la vispera, y sin tope la consulta crece con la historia.
DIAS_DE_AVISOS = 7

_RANGO_PRIORIDAD = {"alta": 0, "media": 1, "baja": 2}


def _nombre(profile) -> str:
    """Un compañero, no un cliente: su nombre va."""
    try:
        return (profile.user.name or profile.user.email or "Alguien").strip()
    except AttributeError:
        return "Alguien"


def _activas():
    from campo.models import OrdenTrabajo
    return (OrdenTrabajo.ASIGNADA, OrdenTrabajo.CORRECCION_REQUERIDA,
            OrdenTrabajo.EN_CAMINO, OrdenTrabajo.EN_SITIO, OrdenTrabajo.BLOQUEADA)


def _terminadas():
    from campo.models import OrdenTrabajo
    return (OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.CERRADA)


def del_dia(org, fecha) -> dict:
    """Lo publicado para `fecha`. Ver el encabezado.

        {"fecha", "cuadrillas": [{jornada, cuadrilla, labor, zonas, tope,
                                  ordenes: [fila]}],
         "con_alguien_que_no_sale": [fila], "esperan": [orden],
         "cuentas": {publicadas, por_el_supervisor, por_personas,
                     sin_registro, avisadas, esperan}}
    """
    from django.db.models import Q

    from campo import reparto as R
    from campo.avisos import AvisoEnviado, DispositivoDeTecnico
    from campo.cuadrillas import (
        JornadaDeCuadrilla,
        configuracion_de_reparto,
        destinatarios,
    )
    from campo.labores import nombres_de_labor
    from campo.models import EventoTrabajo, OrdenTrabajo
    from campo.services import avisos
    from common.models import Notification

    zona = R._zona_de(org)
    jornadas = list(
        JornadaDeCuadrilla.objects.filter(org=org, fecha=fecha)
        .select_related("cuadrilla", "cuadrilla__lider", "lider")
        .prefetch_related("zonas").order_by("cuadrilla__nombre"))
    receptores = {j.id: {r["profile"].id for r in destinatarios(j)["reciben"]}
                  for j in jornadas}

    #  LAS ORDENES DEL DIA: las vivas con gente (salvo las programadas para
    #  otro dia) y las que se terminaron ESE dia.
    ordenes = []
    for o in (OrdenTrabajo.objects
              .filter(org=org, asignaciones__isnull=False)
              .filter(Q(estado_operativo__in=_activas())
                      | Q(estado_operativo__in=_terminadas(),
                          completada_campo_en__date__gte=fecha - dt.timedelta(days=1)))
              .distinct()
              .select_related("tipo_trabajo_version__work_type")
              .prefetch_related("asignaciones__profile__user")):
        if o.estado_operativo in _activas():
            if R._para_otro_dia(o, fecha, zona):
                continue
        elif (o.completada_campo_en is None
              or o.completada_campo_en.astimezone(zona).date() != fecha):
            continue
        ordenes.append(o)

    #  QUIEN LA ASIGNO: el ultimo evento de asignacion de cada orden.
    ultimo = {}
    for ev in (EventoTrabajo.objects
               .filter(org=org, orden_id__in=[o.id for o in ordenes],
                       tipo__in=EVENTOS_DE_ASIGNACION)
               .select_related("profile__user").order_by("created_at", "id")):
        ultimo[ev.orden_id] = ev

    #  EL AVISO: la notificacion de la asignacion, si salio al telefono, y si
    #  hay telefono. Ver el encabezado.
    perfiles = {a.profile_id for o in ordenes for a in o.asignaciones.all()}
    con_telefono = set(
        DispositivoDeTecnico.objects.filter(org=org, activo=True,
                                            profile_id__in=perfiles)
        .values_list("profile_id", flat=True))
    desde = dt.datetime.combine(fecha - dt.timedelta(days=DIAS_DE_AVISOS),
                                dt.time(0, 0), tzinfo=zona)
    #  Lo que Google acepto, con la clave que arma `services/avisos.py`:
    #  `asignacion|<orden>|<revision>` y `jornada|<perfil>|<fecha>|<huella>`.
    orden_al_telefono, jornada_al_telefono = set(), set()
    for clave, canales in (AvisoEnviado.objects
                           .filter(org=org, created_at__gte=desde)
                           .filter(Q(clave__startswith="asignacion|")
                                   | Q(clave__startswith="jornada|"))
                           .values_list("clave", "canales")):
        if "push" not in (canales or []):
            continue
        partes = clave.split("|")
        if partes[0] == "asignacion" and len(partes) >= 2:
            orden_al_telefono.add(partes[1])
        elif partes[0] == "jornada" and len(partes) >= 3:
            jornada_al_telefono.add((partes[1], partes[2]))
    notificado, al_telefono = set(), set()
    for n in (Notification.objects
              .filter(org=org, recipient_id__in=perfiles, created_at__gte=desde,
                      verb__in=(avisos.VERBO_ASIGNADO, avisos.VERBO_JORNADA))
              .values("recipient_id", "verb", "entity_id", "data")):
        datos = n["data"] or {}
        if n["verb"] == avisos.VERBO_ASIGNADO and n["entity_id"]:
            clave = (n["recipient_id"], str(n["entity_id"]))
            notificado.add(clave)
            if str(n["entity_id"]) in orden_al_telefono:
                al_telefono.add(clave)
        salio = (str(n["recipient_id"]), str(datos.get("fecha") or "")) in jornada_al_telefono
        for numero in datos.get("ordenes") or []:
            notificado.add((n["recipient_id"], numero))
            if salio:
                al_telefono.add((n["recipient_id"], numero))

    def fila(o) -> dict:
        quienes = sorted(o.asignaciones.all(),
                         key=lambda a: (not a.es_principal, _nombre(a.profile)))
        ids = [a.profile_id for a in quienes]
        ev = ultimo.get(o.id)
        if ev is None:
            por, por_nombre, cuando = "", "", None
        elif ev.tipo == "asignada_por_el_supervisor":
            por, por_nombre, cuando = SUPERVISOR, "Supervisor", ev.created_at
        else:
            por = PERSONA
            por_nombre = _nombre(ev.profile) if ev.profile_id else "Una persona"
            cuando = ev.created_at
        def hay(conjunto):
            return any((p, str(o.id)) in conjunto or (p, o.numero) in conjunto
                       for p in ids)

        if hay(al_telefono):
            aviso = AVISADO
        elif not set(ids) & con_telefono:
            aviso = SIN_TELEFONO
        elif hay(notificado):
            aviso = NO_LLEGO
        else:
            aviso = SIN_AVISO
        version = o.tipo_trabajo_version
        return {
            "id": str(o.id),
            "numero": o.numero,
            "tipo": getattr(getattr(version, "work_type", None), "nombre", "") or "",
            "barrio": R._localidad_de(o) or "",
            "prioridad": o.prioridad or "",
            "estado": o.estado_operativo,
            "estado_texto": o.get_estado_operativo_display(),
            "tecnicos": [_nombre(a.profile) for a in quienes],
            "asignada_por": por,
            "asignada_por_nombre": por_nombre,
            "asignada_en": cuando.astimezone(zona).isoformat() if cuando else None,
            "aviso": aviso,
        }

    def en_orden(lista):
        return sorted(lista, key=lambda o: (
            o.estado_operativo in _terminadas(),
            _RANGO_PRIORIDAD.get(o.prioridad or "", 3), o.numero))

    por_jornada = {j.id: [] for j in jornadas}
    sin_jornada = []
    for o in ordenes:
        quienes = {a.profile_id for a in o.asignaciones.all()}
        destino = next((j for j in jornadas if quienes & receptores[j.id]), None)
        (por_jornada[destino.id] if destino else sin_jornada).append(o)

    esperan = [
        o for o in (OrdenTrabajo.objects
                    .filter(org=org, estado_operativo__in=R.ESTADOS_QUE_ESPERAN,
                            asignaciones__isnull=True)
                    .select_related("tipo_trabajo_version__work_type"))
        if not R._para_otro_dia(o, fecha, zona)]

    labores = nombres_de_labor(org)
    tope = configuracion_de_reparto(org).tope_por_cuadrilla
    filas = [fila(o) for o in ordenes]
    return {
        "fecha": fecha.isoformat(),
        "cuadrillas": [{
            "jornada": str(j.id),
            "cuadrilla": j.cuadrilla.nombre,
            "labor": labores.get(j.labor, j.labor),
            "zonas": [z.nombre for z in j.zonas.all()],
            "tope": j.cuadrilla.tope_diario or tope,
            "ordenes": [fila(o) for o in en_orden(por_jornada[j.id])],
        } for j in jornadas],
        "con_alguien_que_no_sale": [fila(o) for o in en_orden(sin_jornada)],
        "esperan": [{
            "id": str(o.id), "numero": o.numero,
            "tipo": getattr(getattr(o.tipo_trabajo_version, "work_type", None),
                            "nombre", "") or "",
            "barrio": R._localidad_de(o) or "",
            "prioridad": o.prioridad or "",
        } for o in sorted(esperan, key=lambda o: (
            _RANGO_PRIORIDAD.get(o.prioridad or "", 3), o.numero))],
        "cuentas": {
            "publicadas": len(filas),
            "por_el_supervisor": sum(1 for f in filas if f["asignada_por"] == SUPERVISOR),
            "por_personas": sum(1 for f in filas if f["asignada_por"] == PERSONA),
            "sin_registro": sum(1 for f in filas if not f["asignada_por"]),
            "avisadas": sum(1 for f in filas if f["aviso"] == AVISADO),
            "esperan": len(esperan),
        },
    }
