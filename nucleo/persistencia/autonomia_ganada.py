# -*- coding: utf-8 -*-
"""
================================================================================
 LA EVIDENCIA DE UNA ACCION, POR EMPRESA  --  31/10/2026 (PRD §2, §8.17 Ola 3)
================================================================================

Cuenta en SQL lo que una persona hizo con las propuestas de UNA herramienta en
una ventana, y como salieron sus verificaciones. Solo CONTEOS: ni argumentos,
ni conversaciones, ni quien. Lo decide nucleo/seguridad/autonomia_ganada.py.

  revisadas       una persona decidio: la aprobo (y se ejecuto, bien, mal o sin
                  saberse) o la rechazo. 'vencida' y 'cancelada' NO cuentan:
                  nadie la miro, y contarla inflaria la tasa sin evidencia.
  rechazadas      una persona dijo que no.
  fallidas        se aprobo y la ejecucion fallo o quedo incierta.
  verificaciones  lo que midio verificacion_accion despues del efecto.

Una propuesta cuenta en la ventana por cuando se DECIDIO (revisado_en), no
cuando nacio: la evidencia es la decision.

QUE NO ES EVIDENCIA  (auditor de frontera, 31/10/2026)
  - el boton de reinicio de la Bandeja (rol 'bandeja'): lo propone y lo
    aprueba la misma persona en el mismo pedido -- 100% por construccion;
  - una conversacion que no es de un canal real (el simulador);
  - lo que firmo la propia autonomia: una accion no se gana la autonomia con
    las ejecuciones que hizo sola.
Sin estas exclusiones, 30 reinicios desde la Bandeja y 3 propuestas del
modelo rechazadas daban 90,9% y la accion quedaba elegible.
================================================================================
"""

from __future__ import annotations

from nucleo.persistencia.db import sesion

DECIDIDAS = ("aprobada", "ejecutada_ok", "ejecutada_fallo", "desconocida", "rechazada")
#: El aprobador con que firma la autonomia (nucleo/seguridad/aprobacion.py).
PREFIJO = "autonomia_ganada:"


def medir(tenant: str, herramienta: str, desde, hasta, *, canales) -> dict:
    """Los conteos de una herramienta en [desde, hasta). 'canales' son los
    reales (nucleo/canales/canal.REALES)."""
    p = {"org": None, "h": herramienta, "desde": desde, "hasta": hasta,
         "decididas": list(DECIDIDAS), "canales": list(canales), "autonoma": f"{PREFIJO}%"}
    with sesion(tenant) as (cur, org):
        p["org"] = org
        cur.execute(
            """select count(*) filter (where a.estado = any(%(decididas)s::text[])) as revisadas,
                      count(*) filter (where a.estado = 'rechazada') as rechazadas,
                      count(*) filter (where a.estado in ('ejecutada_fallo', 'desconocida')) as fallidas
                 from asistente.acciones_propuestas a
                 join asistente.conversations c
                   on c.organization_id = a.organization_id and c.id = a.conversation_id
                where a.organization_id = %(org)s and a.herramienta = %(h)s
                  and coalesce(a.rol_solicitante, '') <> 'bandeja'
                  and coalesce(a.revisado_por, '') not like %(autonoma)s
                  and c.canal = any(%(canales)s::text[])
                  and coalesce(a.revisado_en, a.creado_en) >= %(desde)s
                  and coalesce(a.revisado_en, a.creado_en) < %(hasta)s""", p)
        a = cur.fetchone()
        cur.execute(
            """select count(*) filter (where v.estado = 'ACCION_CONFIRMADA') as confirmadas,
                      count(*) filter (where v.estado = 'ACCION_NO_CONFIRMADA') as no_confirmadas,
                      count(*) filter (where v.estado = 'NO_VERIFICABLE') as no_verificables,
                      count(*) filter (where v.estado = 'VERIFICACION_PENDIENTE') as pendientes
                 from asistente.verificaciones_accion v
                 join asistente.conversations c
                   on c.organization_id = v.organization_id and c.id = v.conversation_id
                where v.organization_id = %(org)s and v.herramienta = %(h)s
                  and c.canal = any(%(canales)s::text[])
                  and v.ejecutada_en >= %(desde)s and v.ejecutada_en < %(hasta)s""", p)
        v = cur.fetchone()
    return {k: int(fila[k]) for fila, claves in ((a, ("revisadas", "rechazadas", "fallidas")),
                                                 (v, ("confirmadas", "no_confirmadas",
                                                      "no_verificables", "pendientes")))
            for k in claves}


# =============================================================================
#  LA PROMOCION, EL RETIRO Y LA DEGRADACION  --  Fase B (31/10/2026)
# =============================================================================
#  Tabla de solo agregar: el estado vigente de (empresa, herramienta) es la
#  ULTIMA fila (supabase/202610310200_autonomia_ganada.sql). Estas funciones
#  NO deciden si se puede promover: eso lo decide nucleo/seguridad/
#  autonomia_ganada.py con la evidencia del momento.

def vigente(tenant: str, herramienta: str) -> dict | None:
    """La ultima fila de esa herramienta, o None si nunca hubo. LANZA si la
    base no contesta: quien llama decide que eso es "no autonoma"."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, estado, actor, motivo, evidencia, creado_en
                 from asistente.autonomia_ganada
                where organization_id = %s and herramienta = %s
                order by creado_en desc, id desc limit 1""", (org, herramienta))
        fila = cur.fetchone()
    return dict(fila) if fila else None


def promover(tenant: str, herramienta: str, actor: str, motivo: str, evidencia: dict) -> dict:
    """Una persona le da autonomia a la herramienta. Baja a 'autonomia_operador':
    es administracion, no runtime. No atrapa: si falla, quien promovio tiene
    que enterarse de que NO quedo."""
    return _agregar(tenant, herramienta, "activa", actor, motivo, evidencia)


def retirar(tenant: str, herramienta: str, actor: str, motivo: str) -> dict:
    """Una persona se la quita. Mismo rol que promover."""
    return _agregar(tenant, herramienta, "retirada", actor, motivo, {})


def _agregar(tenant, herramienta, estado, actor, motivo, evidencia) -> dict:
    import json

    from nucleo.persistencia.db import ROL_OPERADOR_AUTONOMIA

    with sesion(tenant, rol=ROL_OPERADOR_AUTONOMIA) as (cur, org):
        cur.execute(
            """insert into asistente.autonomia_ganada
                 (organization_id, herramienta, estado, actor, motivo, evidencia)
               values (%s, %s, %s, %s, %s, %s::jsonb)
               returning id, estado, actor, motivo, evidencia, creado_en""",
            (org, herramienta, estado, actor, motivo, json.dumps(evidencia or {})))
        return dict(cur.fetchone())


def verificaciones_sin_resolver(tenant: str, herramienta: str, horas: int) -> int:
    """Cuantas verificaciones de la herramienta siguen pendientes con mas de
    'horas' de antiguedad. Una verificacion se resuelve recien cuando el
    cliente vuelve a escribir: si no vuelve, queda pendiente para siempre, y
    una autonomia que se mide asi no se degradaria nunca."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select count(*) as n from asistente.verificaciones_accion
                where organization_id = %s and herramienta = %s
                  and estado = 'VERIFICACION_PENDIENTE'
                  and ejecutada_en < now() - make_interval(hours => %s::int)""",
            (org, herramienta, int(horas)))
        return int(cur.fetchone()["n"])


def ejecuciones_autonomas(tenant: str, herramienta: str, *, horas: int,
                          hash_argumentos: str | None = None) -> int:
    """Cuantas veces la ejecuto la autonomia en las ultimas 'horas' (de esa
    accion EXACTA si se pasa su huella). El tope de volumen vive en la base, no
    en el historial en memoria de un proceso (CLAUDE.md §13, D4)."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select count(*) as n from asistente.acciones_propuestas
                where organization_id = %s and herramienta = %s
                  and revisado_por like %s
                  and revisado_en >= now() - make_interval(hours => %s::int)
                  and (%s::text is null or hash_argumentos = %s::text)""",
            (org, herramienta, f"{PREFIJO}%", int(horas), hash_argumentos, hash_argumentos))
        return int(cur.fetchone()["n"])


def degradar(tenant: str, herramienta: str, motivo: str, evidencia: dict | None = None) -> dict | None:
    """El codigo la baja (condicion 4). None si no estaba activa. Por la
    funcion de la base: el runtime no puede escribir otro estado."""
    import json

    with sesion(tenant) as (cur, org):
        cur.execute("select * from asistente.autonomia_ganada_degradar(%s, %s, %s, %s::jsonb)",
                    (org, herramienta, motivo, json.dumps(evidencia or {})))
        fila = cur.fetchone()
    return dict(fila) if fila and fila.get("id") else None
