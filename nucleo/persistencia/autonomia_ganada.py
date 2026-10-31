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
================================================================================
"""

from __future__ import annotations

from nucleo.persistencia.db import sesion

DECIDIDAS = ("aprobada", "ejecutada_ok", "ejecutada_fallo", "desconocida", "rechazada")


def medir(tenant: str, herramienta: str, desde, hasta) -> dict:
    """Los conteos de una herramienta en [desde, hasta)."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select count(*) filter (where estado = any(%(decididas)s::text[])) as revisadas,
                      count(*) filter (where estado = 'rechazada') as rechazadas,
                      count(*) filter (where estado in ('ejecutada_fallo', 'desconocida')) as fallidas
                 from asistente.acciones_propuestas
                where organization_id = %(org)s and herramienta = %(h)s
                  and coalesce(revisado_en, creado_en) >= %(desde)s
                  and coalesce(revisado_en, creado_en) < %(hasta)s""",
            {"org": org, "h": herramienta, "desde": desde, "hasta": hasta,
             "decididas": list(DECIDIDAS)})
        a = cur.fetchone()
        cur.execute(
            """select count(*) filter (where estado = 'ACCION_CONFIRMADA') as confirmadas,
                      count(*) filter (where estado = 'ACCION_NO_CONFIRMADA') as no_confirmadas,
                      count(*) filter (where estado = 'NO_VERIFICABLE') as no_verificables,
                      count(*) filter (where estado = 'VERIFICACION_PENDIENTE') as pendientes
                 from asistente.verificaciones_accion
                where organization_id = %(org)s and herramienta = %(h)s
                  and ejecutada_en >= %(desde)s and ejecutada_en < %(hasta)s""",
            {"org": org, "h": herramienta, "desde": desde, "hasta": hasta})
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


def degradar(tenant: str, herramienta: str, motivo: str, evidencia: dict | None = None) -> dict | None:
    """El codigo la baja (condicion 4). None si no estaba activa. Por la
    funcion de la base: el runtime no puede escribir otro estado."""
    import json

    with sesion(tenant) as (cur, org):
        cur.execute("select * from asistente.autonomia_ganada_degradar(%s, %s, %s, %s::jsonb)",
                    (org, herramienta, motivo, json.dumps(evidencia or {})))
        fila = cur.fetchone()
    return dict(fila) if fila and fila.get("id") else None
