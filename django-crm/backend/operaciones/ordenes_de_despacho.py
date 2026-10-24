# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CREA LAS ORDENES DE DESPACHO  --  Fase 2.3 (23/10/2026)
================================================================================

Lo que hoy hace una persona con el boton «Despachar» --elegir la plantilla, la
fecha y la prioridad, y crear la orden con los datos del cliente-- lo va a
hacer el Supervisor solo, para cada caso de la cola de Despacho (decision del
usuario del 21/10: «si ya pasaron a despacho, estan aprobados para campo»).
Ficha: SPEC/objetivos/supervisor-arma-la-jornada.md, fase 2.3.

ENTREGA 1 (este archivo, por ahora): LA REGLA Y LA VISTA PREVIA. Decide, caso
por caso, que crearia y por que no crearia, SIN escribir nada y SIN
preguntarle al motor: todo sale de lo que ya esta guardado (la lectura del
Supervisor, el barrio de la propuesta, el asunto y la creacion del ticket). La
creacion de verdad es la entrega 2, y va a usar ESTA misma regla.

LO QUE NO SE CREA, Y SE DICE POR QUE (decisiones del 21/10)
---------------------------------------------------------
    ya tiene una orden viva         la tiene alguien, o espera el reparto
    ya tuvo una orden               cerrada o cancelada: una segunda visita la
                                    decide una persona, no el Supervisor
    sin barrio                      no se sabe a donde va; el barrio llega en
                                    las vueltas que siguen o el ISP no lo tiene
    barrio sin zona                 se carga en Zonas operativas
    sin plantilla                   el motivo de `plantilla_del_caso`

LA INSTALACION NUEVA SI SE CREA aunque no tenga barrio: su ficha es la del
cliente de instalaciones del ISP, que no dice donde es la casa. Sale marcada
«llamar al cliente para ubicarlo» (decision del usuario del 21/10).

UN CORTE DE RED ES UNA SOLA ORDEN POR PUERTO: el primer caso del puerto que se
puede crear lleva la orden; los demas quedan ATADOS a ella y no generan visita.

LA PRIORIDAD LA CALCULA EL CODIGO (decision del usuario del 23/10, CLAUDE.md
§4): con plazo en la plantilla, vencida o vence hoy = alta, vence mañana =
media, despues = baja; sin plazo, por la espera: dos dias o mas = alta, uno =
media, de hoy = baja.

EL DIA LO DECIDE LA HORA DE CORTE de la empresa (Cuadrillas -> Horario): lo que
entro a Despacho antes del corte sale hoy; lo que entro despues, mañana. Sin
hora de corte, el Supervisor no crea nada.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

CREAR = "crear"
NO_SE_CREA = "no_se_crea"
ATADA = "atada"

YA_TIENE_ORDEN = "ya_tiene_orden"
YA_TUVO_ORDEN = "ya_tuvo_orden"
SIN_BARRIO_TODAVIA = "sin_barrio_todavia"
SIN_BARRIO = "sin_barrio"
BARRIO_SIN_ZONA = "barrio_sin_zona"
SIN_PLANTILLA = "sin_plantilla"

_POR_QUE_NO = {
    YA_TIENE_ORDEN: "Ya tiene una orden viva.",
    YA_TUVO_ORDEN: ("Ya tuvo una orden, cerrada o cancelada: una segunda "
                    "visita la decide una persona."),
    SIN_BARRIO_TODAVIA: ("Todavía no se sabe su barrio: el Supervisor lo pide "
                         "en las vueltas que siguen."),
    SIN_BARRIO: "El ISP no tiene el barrio del cliente.",
    BARRIO_SIN_ZONA: ("Su barrio no está en ninguna zona: se carga en Zonas "
                      "operativas."),
}

#: La prioridad de la orden, con los valores de `OrdenTrabajo.prioridad`.
ALTA, MEDIA, BAJA = "alta", "media", "baja"


def prioridad_de(creado, plazo_dias, hoy: dt.date, zona) -> str:
    """Alta, media o baja: por el plazo de la plantilla, y si no tiene, por
    la espera. Regla del usuario del 23/10/2026.

    Se cuenta en DIAS de calendario de la empresa (`zona`), desde el dia en
    que se creo el ticket. Sin fecha de creacion no hay nada que medir: media.
    """
    if creado is None:
        return MEDIA
    dia_creado = creado.astimezone(zona).date()
    if plazo_dias is not None:
        restantes = (dia_creado + dt.timedelta(days=plazo_dias) - hoy).days
        if restantes <= 0:
            return ALTA
        return MEDIA if restantes == 1 else BAJA
    espera = (hoy - dia_creado).days
    if espera >= 2:
        return ALTA
    return MEDIA if espera == 1 else BAJA


def dia_de_la_orden(entro_en, hora_de_corte, ahora, zona):
    """Para que dia sale la orden, o None si no hay hora de corte.

    Lo que entro a Despacho antes del corte de HOY sale hoy, y lo que entro
    despues, mañana. Lo que entro un dia anterior sale hoy: ya espero. Sin la
    hora en que entro (una aceptada sin `revisado_en`), hoy: es el lado que no
    la deja esperando de mas.
    """
    if hora_de_corte is None:
        return None
    hoy = ahora.astimezone(zona).date()
    if entro_en is None:
        return hoy
    entro = entro_en.astimezone(zona)
    if entro.date() < hoy or entro.time() < hora_de_corte:
        return hoy
    return hoy + dt.timedelta(days=1)


def _ordenes_por_caso(org, casos: list) -> tuple[set, set]:
    """(los casos con una orden viva, los que tuvieron una cerrada o
    cancelada). Viva = la misma regla de `ordenes_vivas_del_caso`."""
    from campo.models import OrdenTrabajo

    if not casos:
        return set(), set()
    terminadas = (OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA)
    vivas, tuvieron = set(), set()
    for ref, estado in (OrdenTrabajo.objects
                        .filter(org=org, origen_sistema="crm",
                                origen_ref__in=casos)
                        .values_list("origen_ref", "estado_operativo")):
        (tuvieron if estado in terminadas else vivas).add(str(ref))
    return vivas, tuvieron


def decidir(org, ahora=None) -> dict:
    """Que crearia el Supervisor ahora, caso por caso. No escribe nada.

        {"hoy", "hora_de_corte", "porque",   # porque: por que no correria
         "crear":      [{caso, ticket, asunto, plantilla, version, por,
                         labor, prioridad, para, barrio, zona,
                         llamar_al_cliente, corte_de_red}],
         "no_se_crea": [{caso, ticket, asunto, motivo, detalle}],
         "atadas":     [{caso, ticket, asunto, a_caso, a_ticket}]}

    En el orden en que se crearon los tickets: el corte de red lo lleva el
    caso mas viejo del puerto que se puede crear.
    """
    from campo import plantillas as P
    from campo.cuadrillas import (
        configuracion_de_reparto,
        labor_de_cada_grupo,
        onus_para_corte_de_red,
    )
    from campo.labores import nombres_de_labor
    from campo.reparto import _zona_de
    from campo.zonas import AliasDeZona, normalizar_localidad
    from cases.models import Case
    from operaciones import armado_de_jornadas as adj
    from operaciones import paso_a_despacho as pad

    ahora = ahora or timezone.now()
    zona_horaria = _zona_de(org)
    hoy = ahora.astimezone(zona_horaria).date()
    corte = configuracion_de_reparto(org).hora_de_corte
    salida = {"hoy": hoy.isoformat(),
              "hora_de_corte": corte.strftime("%H:%M") if corte else "",
              "porque": ("" if corte else
                         "Falta la hora de corte (Cuadrillas → Horario de "
                         "las cuadrillas): sin ella, el Supervisor no crea "
                         "órdenes."),
              "crear": [], "no_se_crea": [], "atadas": []}

    propuestas = adj.propuestas_en_despacho(org)
    if not propuestas:
        return salida
    casos = {str(c.id): c for c in Case.objects.filter(
        org=org, id__in=list(propuestas))}
    vivas, tuvieron = _ordenes_por_caso(org, list(propuestas))
    labores = labor_de_cada_grupo(org)
    nombres = nombres_de_labor(org)
    ofrecidas = P.plantillas_que_se_ofrecen(org)
    zona_de_barrio = {
        a.localidad: a.zona.nombre
        for a in AliasDeZona.objects.filter(org=org, zona__activa=True)
        .select_related("zona")
    }
    umbral = onus_para_corte_de_red(org.id)
    #  El puerto de cada caso que es parte de un corte de red, y el caso que
    #  lleva la orden de cada puerto. Los que ya tienen orden viva van primero:
    #  si el caso con la orden viene despues en la cola, los otros se atan a el.
    puerto_de = {}
    for caso_id, p in propuestas.items():
        medicion = pad.ultima_medicion(p)
        if pad.es_corte_de_red(medicion, umbral):
            puerto_de[caso_id] = medicion["puerto"]
    con_orden = {puerto_de[c]: c for c in puerto_de if c in vivas}

    def _fila(caso_id, caso):
        return {"caso": caso_id,
                "ticket": (getattr(caso, "external_ticket_id", "") or "").strip(),
                "asunto": getattr(caso, "name", "") or ""}

    #  POR ANTIGUEDAD: el corte lo lleva el mas viejo, y la pantalla lee la
    #  cola en el orden en que llego.
    nunca = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    orden = sorted(propuestas, key=lambda c: (
        getattr(casos.get(c), "created_at", None) or nunca, c))
    for caso_id in orden:
        p, caso = propuestas[caso_id], casos.get(caso_id)
        if caso is None:
            continue
        fila = _fila(caso_id, caso)

        def no(motivo, detalle=""):
            salida["no_se_crea"].append({
                **fila, "motivo": motivo,
                "detalle": detalle or _POR_QUE_NO.get(motivo, "")})

        if caso_id in vivas:
            no(YA_TIENE_ORDEN)
            continue
        if caso_id in tuvieron:
            no(YA_TUVO_ORDEN)
            continue
        puerto = puerto_de.get(caso_id)
        if puerto and puerto in con_orden:
            lleva = con_orden[puerto]
            salida["atadas"].append({
                **fila, "a_caso": lleva,
                "a_ticket": (getattr(casos.get(lleva), "external_ticket_id", "")
                             or "").strip()})
            continue

        pieza = adj.localidad_guardada(p)
        lectura = pad._ultima_lectura_con_grupo(p) or {}
        nuevo = adj._es_de_un_cliente_nuevo(pieza or {}, lectura)
        barrio = normalizar_localidad((pieza or {}).get("localidad") or "")
        zona = zona_de_barrio.get(barrio) if barrio else None
        if not barrio and not nuevo:
            no(SIN_BARRIO_TODAVIA if pieza is None else SIN_BARRIO)
            continue
        if barrio and zona is None:
            no(BARRIO_SIN_ZONA,
               f"Su barrio ({barrio}) no está en ninguna zona: se carga en "
               "Zonas operativas.")
            continue

        labor = adj.labor_del_caso(p, labores, es_corte=bool(puerto))
        elegida = P.plantilla_del_caso(
            org, labor=labor or "", asunto=caso.name or "",
            #  Medida = la decidio una medicion del equipo, no la lectura.
            labor_medida=bool(adj.labor_de_la_visita(p)),
            ofrecidas=ofrecidas)
        version = elegida["version"]
        if version is None:
            no(SIN_PLANTILLA, elegida["detalle"])
            continue

        if puerto:
            con_orden[puerto] = caso_id
        tipo = version.work_type
        para = dia_de_la_orden(p.revisado_en, corte, ahora, zona_horaria)
        salida["crear"].append({
            **fila,
            "plantilla": tipo.nombre,
            "version": str(version.id),
            "por": elegida["por"],
            "labor": nombres.get(tipo.labor, tipo.labor),
            "prioridad": prioridad_de(caso.created_at, tipo.plazo_dias, hoy,
                                      zona_horaria),
            "para": para.isoformat() if para else "",
            "barrio": barrio,
            "zona": zona or "",
            "llamar_al_cliente": not barrio,
            "corte_de_red": bool(puerto),
        })
    return salida
