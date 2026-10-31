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
