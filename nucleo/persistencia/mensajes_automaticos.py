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


def ya_escribio(tenant: str, numero: str) -> bool:
    """Si este numero tiene alguna conversacion de WhatsApp con la empresa.
    Desempata a quien escribirle cuando el ISP guarda varios moviles."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select 1 from asistente.conversations
                where organization_id = %s and canal = 'whatsapp' and usuario_externo = %s
                limit 1""", (org, numero))
        return cur.fetchone() is not None


def caidas_avisadas(tenant: str, servicios: list[str], dias: int) -> dict[str, str]:
    """
    {servicio: hora en que cayo} de los servicios a los que el aviso de caida
    SALIO de verdad (estado 'enviado') en los ultimos 'dias' -- la ultima
    caida avisada de cada uno. Lo lee de la clave 'caida:<servicio>:<hora>'
    (nucleo/seguimiento/aviso_de_caida.clave): el "ya volvio" se le manda a
    quien recibio el "se cayo", no a una lista que alguien mande (30/10/2026).
    """
    if not servicios:
        return {}
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select clave from asistente.mensajes_automaticos
                where organization_id = %s and evento = 'caida_masiva' and estado = 'enviado'
                  and creado_en >= now() - make_interval(days => %s::int)
                  and split_part(clave, ':', 2) = any(%s::text[])
                order by creado_en""", (org, int(dias), list(servicios)))
        salida: dict[str, str] = {}
        for fila in cur.fetchall():
            _, servicio, cayo = str(fila["clave"]).split(":", 2)
            salida[servicio] = cayo
        return salida
