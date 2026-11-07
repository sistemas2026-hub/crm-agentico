# -*- coding: utf-8 -*-
"""
================================================================================
 LA MEDICION DEL TABLERO DE CAPACIDAD  --  30/10/2026
================================================================================

Cuenta en SQL lo que el tablero muestra (PRD §2). Devuelve CONTEOS, nunca
filas ni datos de un cliente: las tasas y los minutos los compone
nucleo/observabilidad/capacidad.py, y el modelo no toca ningun numero (§12.5).

QUE ES CADA COSA
----------------
  universo     conversaciones de la empresa en canales reales, nacidas en
               [desde, hasta). El simulador y el asistente interno no son
               clientes: no entran.
  con persona  una persona escribio (messages.origen = 'humano', sin contar
               las notas internas: anotar no es hacerse cargo), tomo el caso,
               intervino, recibio la escalada, la atendio a mano, hubo una
               accion que necesitaba aprobacion, o termino en un ticket
               operativo (una visita o el ticket de una escalada). Cualquiera
               basta: el tablero mide lo que la IA resolvio SOLA.
  resuelta     cerrada, sin persona, y NO por inactividad. Una cerrada por
  sin persona  inactividad es un cliente que dejo de contestar: no confirma
               que este resuelto, y se informa aparte en vez de sumarse.
  fin          el ultimo mensaje que no es una nota. NO el evento 'cerrada':
               los cierres de legado y los de T18 no lo dejan (db.py lo
               documenta en el hilo de la bandeja).
  recontacto   un mensaje DEL CLIENTE en otra conversacion del mismo numero
               dentro de la ventana. Una conversacion que abre un operador
               (T21) no lo es. Solo se evaluan las conversaciones cuya ventana
               ya termino: a una cerrada hace una hora no le dio tiempo.
  visita       una accion de 'acciones_que_evitan_visita' CONFIRMADA cuya
  evitada      ventana de dias ya termino, sin visita para el mismo cliente en
               esos dias: ni una herramienta de visita exitosa, ni un ticket
               operativo (la visita que agenda el codigo no pasa por
               tool_calls; deja 'conversations.ticket_operativo'). Sigue siendo
               una estimacion: una visita cargada a mano en el sistema del ISP
               no se ve desde aca.

Las dos ventanas incompletas sesgarian a favor de Dexter --menos recontactos,
mas visitas evitadas--, que es justo el numero que se le muestra a quien compra.
================================================================================
"""

from __future__ import annotations

from nucleo.persistencia.db import sesion


def medir(tenant: str, desde, hasta, *, canales, acciones_que_evitan_visita,
          herramientas_de_visita, ventana_recontacto_horas: int,
          dias_sin_visita: int) -> dict:
    canales = sorted(canales)
    acciones = list(acciones_que_evitan_visita)
    visitas = list(herramientas_de_visita)
    with sesion(tenant) as (cur, org):
        p = {"org": org, "desde": desde, "hasta": hasta, "canales": canales,
             "ventana": int(ventana_recontacto_horas), "dias": int(dias_sin_visita),
             "acciones": acciones, "visitas": visitas}

        cur.execute(
            """with u as (
                 select c.id, c.canal, c.usuario_externo, c.creado_en, c.estado,
                        c.escalada_a_humano, c.atendida_manual, c.tomada_por,
                        c.ticket_operativo, c.cerrada_por_tipo,
                        coalesce((select max(m.creado_en) from asistente.messages m
                                   where m.organization_id = c.organization_id
                                     and m.conversation_id = c.id
                                     and m.rol <> 'nota'), c.creado_en) as fin
                   from asistente.conversations c
                  where c.organization_id = %(org)s
                    and c.canal = any(%(canales)s::text[])
                    and c.creado_en >= %(desde)s and c.creado_en < %(hasta)s
               ), cerradas as (
                 select u.*,
                        (u.escalada_a_humano or u.atendida_manual or u.tomada_por is not null
                         or u.ticket_operativo is not null
                         or exists (select 1 from asistente.relevo_eventos e
                                     where e.organization_id = %(org)s and e.conversation_id = u.id
                                       and e.tipo in ('escalada', 'intervencion', 'tomada'))
                         or exists (select 1 from asistente.messages m
                                     where m.organization_id = %(org)s and m.conversation_id = u.id
                                       and m.origen = 'humano' and m.rol <> 'nota')
                         or exists (select 1 from asistente.acciones_propuestas a
                                     where a.organization_id = %(org)s and a.conversation_id = u.id)
                        ) as con_persona,
                        coalesce(u.cerrada_por_tipo, '') = 'inactividad' as por_inactividad,
                        u.fin + make_interval(hours => %(ventana)s::int) <= %(hasta)s as evaluable,
                        (coalesce(u.usuario_externo, '') <> '' and exists (
                           select 1 from asistente.messages m
                             join asistente.conversations c2 on c2.id = m.conversation_id
                            where m.organization_id = %(org)s and c2.organization_id = %(org)s
                              and c2.id <> u.id and c2.canal = u.canal
                              and c2.usuario_externo = u.usuario_externo
                              and m.origen = 'cliente'
                              and m.creado_en > u.fin
                              and m.creado_en <= u.fin + make_interval(hours => %(ventana)s::int))
                        ) as volvio
                   from u where u.estado = 'cerrada'
               ), clasificadas as (
                 select *, (not con_persona and not por_inactividad) as resuelta from cerradas
               )
               select count(*) as cerradas,
                      count(*) filter (where resuelta) as resueltas_sin_persona,
                      count(*) filter (where not con_persona and por_inactividad) as por_inactividad,
                      count(*) filter (where evaluable) as evaluables_recontacto,
                      count(*) filter (where evaluable and resuelta) as evaluables_sin_persona,
                      count(*) filter (where evaluable and volvio) as recontactos,
                      count(*) filter (where evaluable and volvio and resuelta) as recontactos_sin_persona,
                      percentile_cont(0.5) within group (
                          order by extract(epoch from (fin - creado_en)) / 60.0
                      ) as minutos_hasta_resolucion
                 from clasificadas""", p)
        fila = dict(cur.fetchone())

        cur.execute(
            """select count(distinct e.actor_usuario_id) as personas
                 from asistente.relevo_eventos e
                 join asistente.conversations c on c.id = e.conversation_id
                where e.organization_id = %(org)s and c.organization_id = %(org)s
                  and e.actor_tipo = 'operador' and e.actor_usuario_id is not null
                  and c.canal = any(%(canales)s::text[])
                  and c.creado_en >= %(desde)s and c.creado_en < %(hasta)s""", p)
        personas = cur.fetchone()["personas"]

        reinicios = evitadas = en_ventana = None
        if acciones and visitas:
            cur.execute(
                """with confirmadas as (
                     select v.conversation_id, v.ejecutada_en, c.canal, c.usuario_externo,
                            v.ejecutada_en + make_interval(days => %(dias)s::int) as cierra_ventana
                       from asistente.verificaciones_accion v
                       join asistente.conversations c on c.id = v.conversation_id
                      where v.organization_id = %(org)s and c.organization_id = %(org)s
                        and c.canal = any(%(canales)s::text[])
                        and v.herramienta = any(%(acciones)s::text[])
                        and v.estado = 'ACCION_CONFIRMADA'
                        and v.ejecutada_en >= %(desde)s and v.ejecutada_en < %(hasta)s
                   )
                   select count(*) filter (where cierra_ventana > %(hasta)s) as en_ventana,
                          count(*) filter (where cierra_ventana <= %(hasta)s) as confirmadas,
                          count(*) filter (where cierra_ventana <= %(hasta)s
                            and not exists (
                              select 1 from asistente.tool_calls t
                                join asistente.conversations c2 on c2.id = t.conversation_id
                               where t.organization_id = %(org)s and c2.organization_id = %(org)s
                                 and t.herramienta = any(%(visitas)s::text[]) and t.exito
                                 and t.creado_en >= k.ejecutada_en and t.creado_en < k.cierra_ventana
                                 and (t.conversation_id = k.conversation_id
                                      or (coalesce(k.usuario_externo, '') <> ''
                                          and c2.canal = k.canal
                                          and c2.usuario_externo = k.usuario_externo)))
                            and not exists (
                              select 1 from asistente.conversations c3
                               where c3.organization_id = %(org)s
                                 and c3.ticket_operativo is not null
                                 and (c3.id = k.conversation_id
                                      or (coalesce(k.usuario_externo, '') <> ''
                                          and c3.canal = k.canal
                                          and c3.usuario_externo = k.usuario_externo
                                          and c3.creado_en >= k.ejecutada_en
                                          and c3.creado_en < k.cierra_ventana)))
                          ) as evitadas
                     from confirmadas k""", p)
            f = cur.fetchone()
            reinicios, evitadas, en_ventana = f["confirmadas"], f["evitadas"], f["en_ventana"]

        cur.execute(
            """select count(*) filter (where enviada_en >= %(desde)s and enviada_en < %(hasta)s) as enviadas,
                      count(*) filter (where puntaje is not null
                                         and respondida_en >= %(desde)s and respondida_en < %(hasta)s)
                          as respondidas,
                      avg(puntaje) filter (where puntaje is not null
                                             and respondida_en >= %(desde)s and respondida_en < %(hasta)s)
                          as promedio
                 from asistente.encuestas_whatsapp
                where organization_id = %(org)s""", p)
        enc = cur.fetchone()

    mediana = fila["minutos_hasta_resolucion"]
    return {
        "cerradas": fila["cerradas"],
        "resueltas_sin_persona": fila["resueltas_sin_persona"],
        "por_inactividad": fila["por_inactividad"],
        "evaluables_recontacto": fila["evaluables_recontacto"],
        "evaluables_sin_persona": fila["evaluables_sin_persona"],
        "recontactos": fila["recontactos"],
        "recontactos_sin_persona": fila["recontactos_sin_persona"],
        "minutos_hasta_resolucion": float(mediana) if mediana is not None else None,
        "personas_que_atendieron": personas,
        "reinicios_confirmados": reinicios,
        "reinicios_en_ventana": en_ventana,
        "visitas_evitadas": evitadas,
        "encuestas_enviadas": enc["enviadas"],
        "encuestas_respondidas": enc["respondidas"],
        "satisfaccion_promedio": float(enc["promedio"]) if enc["promedio"] is not None else None,
        "ventana_recontacto_horas": int(ventana_recontacto_horas),
        "dias_sin_visita": int(dias_sin_visita),
    }
