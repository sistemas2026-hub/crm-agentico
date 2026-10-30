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
  con persona  una persona escribio (messages.origen = 'humano'), tomo el caso,
               intervino, recibio la escalada, la atendio a mano, o hubo una
               accion que necesitaba aprobacion. Cualquiera de esas basta: el
               tablero mide lo que la IA resolvio SOLA, y una sola senal de
               persona desmiente "sola".
  fin          el ultimo mensaje de la conversacion. NO el evento 'cerrada':
               los cierres de legado y los de T18 no lo dejan (db.py lo
               documenta en el hilo de la bandeja), y medir desde ahi perderia
               justo esas conversaciones.
  recontacto   el MISMO numero, por el mismo canal, abre otra conversacion
               dentro de la ventana despues del fin.
  visita       una accion de 'acciones_que_evitan_visita' CONFIRMADA, sin una
  evitada      herramienta de visita exitosa para el mismo cliente en los dias
               siguientes. Es una estimacion, no una certeza: no se sabe que
               habria pasado sin el reinicio.
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
                        coalesce((select max(m.creado_en) from asistente.messages m
                                   where m.organization_id = c.organization_id
                                     and m.conversation_id = c.id), c.creado_en) as fin
                   from asistente.conversations c
                  where c.organization_id = %(org)s
                    and c.canal = any(%(canales)s::text[])
                    and c.creado_en >= %(desde)s and c.creado_en < %(hasta)s
               ), cerradas as (
                 select u.*,
                        (u.escalada_a_humano or u.atendida_manual or u.tomada_por is not null
                         or exists (select 1 from asistente.relevo_eventos e
                                     where e.organization_id = %(org)s and e.conversation_id = u.id
                                       and e.tipo in ('escalada', 'intervencion', 'tomada'))
                         or exists (select 1 from asistente.messages m
                                     where m.organization_id = %(org)s and m.conversation_id = u.id
                                       and m.origen = 'humano')
                         or exists (select 1 from asistente.acciones_propuestas a
                                     where a.organization_id = %(org)s and a.conversation_id = u.id)
                        ) as con_persona,
                        (coalesce(u.usuario_externo, '') <> '' and exists (
                           select 1 from asistente.conversations c2
                            where c2.organization_id = %(org)s and c2.id <> u.id
                              and c2.canal = u.canal and c2.usuario_externo = u.usuario_externo
                              and c2.creado_en > u.fin
                              and c2.creado_en <= u.fin + make_interval(hours => %(ventana)s::int))
                        ) as volvio
                   from u where u.estado = 'cerrada'
               )
               select count(*) as cerradas,
                      count(*) filter (where not con_persona) as resueltas_sin_persona,
                      count(*) filter (where volvio) as recontactos,
                      count(*) filter (where volvio and not con_persona) as recontactos_sin_persona,
                      percentile_cont(0.5) within group (
                          order by extract(epoch from (fin - creado_en)) / 60.0
                      ) as minutos_hasta_resolucion
                 from cerradas""", p)
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

        reinicios = evitadas = None
        if acciones and visitas:
            cur.execute(
                """select count(*) as confirmadas,
                          count(*) filter (where not exists (
                             select 1 from asistente.tool_calls t
                               join asistente.conversations c2 on c2.id = t.conversation_id
                              where t.organization_id = %(org)s and c2.organization_id = %(org)s
                                and t.herramienta = any(%(visitas)s::text[]) and t.exito
                                and t.creado_en >= v.ejecutada_en
                                and t.creado_en < v.ejecutada_en + make_interval(days => %(dias)s::int)
                                and (t.conversation_id = v.conversation_id
                                     or (coalesce(c.usuario_externo, '') <> ''
                                         and c2.canal = c.canal
                                         and c2.usuario_externo = c.usuario_externo))
                          )) as evitadas
                     from asistente.verificaciones_accion v
                     join asistente.conversations c on c.id = v.conversation_id
                    where v.organization_id = %(org)s and c.organization_id = %(org)s
                      and c.canal = any(%(canales)s::text[])
                      and v.herramienta = any(%(acciones)s::text[])
                      and v.estado = 'ACCION_CONFIRMADA'
                      and v.ejecutada_en >= %(desde)s and v.ejecutada_en < %(hasta)s""", p)
            f = cur.fetchone()
            reinicios, evitadas = f["confirmadas"], f["evitadas"]

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
        "recontactos": fila["recontactos"],
        "recontactos_sin_persona": fila["recontactos_sin_persona"],
        "minutos_hasta_resolucion": float(mediana) if mediana is not None else None,
        "personas_que_atendieron": personas,
        "reinicios_confirmados": reinicios,
        "visitas_evitadas": evitadas,
        "encuestas_enviadas": enc["enviadas"],
        "encuestas_respondidas": enc["respondidas"],
        "satisfaccion_promedio": float(enc["promedio"]) if enc["promedio"] is not None else None,
        "ventana_recontacto_horas": int(ventana_recontacto_horas),
        "dias_sin_visita": int(dias_sin_visita),
    }
