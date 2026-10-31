# -*- coding: utf-8 -*-
"""
================================================================================
 ENCUESTAS POR WHATSAPP  -  la tabla y sus cuatro movimientos  (28/10/2026)
================================================================================

  reservar   la fila nace ANTES de mandar la plantilla; si el caso ya tenia
             una, no nace otra (unicidad por caso, sin select previo)
  enviada    queda el wamid de Meta, que es con lo que se reconoce la respuesta
  fallida    Meta no la acepto: queda dicho, y el caso no recibe otra
  responder  el boton que toco el cliente, una sola vez y dentro del plazo

Y 'resumen': lo que muestra "Calidad de la atencion". Se calcula aca, en SQL y
Python -- nunca se le pide a un modelo que sume o promedie (PRD §12.5).

Sin datos del cliente: ver supabase/202610281600_encuestas_whatsapp.sql.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nucleo.persistencia.db import sesion


def destino_del_caso(tenant: str, caso_id: str) -> dict | None:
    """
    A quien mandarle la encuesta de un caso: la conversacion mas reciente del
    caso, con su canal, el numero y el nombre del perfil. None si el caso no
    vino de un chat. El numero se usa para ENVIAR y no se guarda en la tabla
    de encuestas.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, canal, usuario_externo, nombre_cliente
                 from asistente.conversations
                where organization_id = %s and caso_id = %s
                order by actualizado_en desc limit 1""",
            (org, str(caso_id)))
        fila = cur.fetchone()
        return dict(fila) if fila else None


def reservar(tenant: str, caso_id: str, conversation_id: str | None, plantilla: str,
             vigencia_horas: int, responsable_id: str | None = None,
             responsable_nombre: str | None = None, area: str | None = None) -> str | None:
    """El id de la encuesta nueva, o None si el caso ya tenia una."""
    vence = datetime.now(timezone.utc) + timedelta(hours=vigencia_horas)
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.encuestas_whatsapp
                 (organization_id, caso_id, conversation_id, plantilla, vence_en,
                  responsable_id, responsable_nombre, area)
               values (%s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (organization_id, caso_id) do nothing
               returning id""",
            (org, str(caso_id), conversation_id, plantilla, vence,
             responsable_id or None, responsable_nombre or None, area or None))
        fila = cur.fetchone()
        return str(fila["id"]) if fila else None


def marcar_enviada(tenant: str, encuesta_id: str, wamid: str | None) -> None:
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.encuestas_whatsapp
                  set estado = 'enviada', wamid = %s, enviada_en = now()
                where organization_id = %s and id = %s and estado = 'reservada'""",
            (wamid, org, encuesta_id))


def marcar_fallida(tenant: str, encuesta_id: str) -> None:
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.encuestas_whatsapp set estado = 'fallida'
                where organization_id = %s and id = %s and estado = 'reservada'""",
            (org, encuesta_id))


def responder(tenant: str, wamid: str, opcion: str, puntaje: int | None) -> dict:
    """
    El boton que toco el cliente, para la encuesta cuyo mensaje es 'wamid'.

    {'encuesta': bool, 'registrada': bool, 'motivo': str|None, 'caso_id'}:
      encuesta=False   ese mensaje no es una encuesta (el boton es de otra cosa)
      registrada=True  primera respuesta valida, guardada
      motivo           'ya_respondida' | 'vencida' | 'opcion_desconocida'

    El UPDATE lleva las condiciones adentro (no un select y despues un update):
    dos toques casi simultaneos no guardan dos respuestas, gana el primero.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.encuestas_whatsapp
                  set estado = 'respondida', opcion = %s, puntaje = %s, respondida_en = now()
                where organization_id = %s and wamid = %s and estado = 'enviada'
                  and vence_en > now() and %s::smallint is not null
               returning caso_id""",
            (opcion, puntaje, org, wamid, puntaje))
        fila = cur.fetchone()
        if fila:
            return {"encuesta": True, "registrada": True, "motivo": None,
                    "caso_id": fila["caso_id"]}
        cur.execute(
            """select caso_id, estado, vence_en from asistente.encuestas_whatsapp
                where organization_id = %s and wamid = %s""",
            (org, wamid))
        fila = cur.fetchone()
    if not fila:
        return {"encuesta": False, "registrada": False, "motivo": None, "caso_id": None}
    if fila["estado"] == "respondida":
        motivo = "ya_respondida"
    elif puntaje is None:
        motivo = "opcion_desconocida"
    else:
        motivo = "vencida"
    return {"encuesta": True, "registrada": False, "motivo": motivo, "caso_id": fila["caso_id"]}


def filas(tenant: str, desde: datetime, hasta: datetime) -> list[dict]:
    """Las encuestas ENVIADAS en el periodo (respondidas o no), sin datos del cliente."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select caso_id, estado, opcion, puntaje, responsable_id, responsable_nombre,
                      area, enviada_en, respondida_en
                 from asistente.encuestas_whatsapp
                where organization_id = %s and enviada_en >= %s and enviada_en < %s
                  and estado in ('enviada', 'respondida')
                order by enviada_en desc""",
            (org, desde, hasta))
        return list(cur.fetchall())


def resumir(filas_: list[dict], satisfecho_desde: int = 4) -> dict:
    """
    Los numeros de "Calidad de la atencion", calculados en codigo.

    'satisfaccion' es el porcentaje de respuestas con puntaje >= satisfecho_desde
    (la forma habitual de contar CSAT); 'promedio', el puntaje medio. Una
    persona o un area sin respuestas va con None, no con cero: cero seria una
    nota pesima que nadie puso.
    """
    def agregado(grupo: list[dict]) -> dict:
        enviadas = len(grupo)
        notas = [f["puntaje"] for f in grupo if f.get("puntaje") is not None]
        respondidas = len(notas)
        return {
            "enviadas": enviadas,
            "respondidas": respondidas,
            "tasa_respuesta": round(100 * respondidas / enviadas, 1) if enviadas else None,
            "promedio": round(sum(notas) / respondidas, 2) if respondidas else None,
            "satisfaccion": (round(100 * sum(1 for n in notas if n >= satisfecho_desde) / respondidas, 1)
                             if respondidas else None),
        }

    def por(clave: str, rotulo) -> list[dict]:
        grupos: dict = {}
        for f in filas_:
            grupos.setdefault(f.get(clave) or "", []).append(f)
        salida = [{"clave": k, "nombre": rotulo(k, g), **agregado(g)} for k, g in grupos.items()]
        # Primero los que tienen respuestas, de peor a mejor: es lo que hay que mirar.
        return sorted(salida, key=lambda x: (x["promedio"] is None, x["promedio"] or 0, x["nombre"]))

    opciones: dict[str, dict] = {}
    for f in filas_:
        if f.get("opcion"):
            o = opciones.setdefault(f["opcion"], {"opcion": f["opcion"], "puntaje": f.get("puntaje"),
                                                 "cantidad": 0})
            o["cantidad"] += 1

    semanas: dict[str, list] = {}
    for f in filas_:
        if f.get("enviada_en"):
            lunes = (f["enviada_en"] - timedelta(days=f["enviada_en"].weekday())).date().isoformat()
            semanas.setdefault(lunes, []).append(f)

    respondidas = sorted((f for f in filas_ if f.get("respondida_en")),
                         key=lambda f: f["respondida_en"], reverse=True)
    return {
        "total": agregado(filas_),
        "opciones": sorted(opciones.values(), key=lambda o: -(o["puntaje"] or 0)),
        "por_semana": [{"semana": s, **agregado(g)} for s, g in sorted(semanas.items())],
        "por_responsable": por("responsable_id",
                               lambda k, g: (g[0].get("responsable_nombre") or "Sin responsable") if k
                               else "Sin responsable"),
        "por_area": por("area", lambda k, g: k or "Sin área"),
        "recientes": [{"caso_id": f["caso_id"], "opcion": f["opcion"], "puntaje": f["puntaje"],
                       "responsable": f.get("responsable_nombre"), "area": f.get("area"),
                       "respondida_en": f["respondida_en"].isoformat()}
                      for f in respondidas[:30]],
    }
