# -*- coding: utf-8 -*-
"""
Cada aviso por plantilla, una sola vez por (evento, motivo)  --  28/10/2026.
Ver supabase/202610290900_mensajes_automaticos.sql.
"""

from __future__ import annotations

from nucleo.persistencia.db import sesion


def reservar(tenant: str, evento: str, clave: str, plantilla: str) -> str | None:
    """El id de la reserva, o None si ese motivo ya disparo este aviso."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.mensajes_automaticos (organization_id, evento, clave, plantilla)
               values (%s, %s, %s, %s)
               on conflict (organization_id, evento, clave) do nothing
               returning id""",
            (org, evento, clave, plantilla))
        fila = cur.fetchone()
        return str(fila["id"]) if fila else None


def marcar(tenant: str, reserva_id: str, estado: str, wamid: str | None = None) -> None:
    """'enviado' (con el wamid) o 'fallido'. Solo desde 'reservado'."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.mensajes_automaticos
                  set estado = %s, wamid = %s,
                      enviado_en = case when %s::text = 'enviado' then now() else enviado_en end
                where organization_id = %s and id = %s and estado = 'reservado'""",
            (estado, wamid, estado, org, reserva_id))
