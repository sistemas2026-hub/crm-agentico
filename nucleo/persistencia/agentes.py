# -*- coding: utf-8 -*-
"""
LO QUE HIZO CADA AGENTE  --  13/11/2026.

Hasta hoy la pantalla de Agentes tenia una sola medicion, la tasa de escalada
de TODA la empresa ('db.tasa_escalamiento', que en su propio docstring dice
"no filtra por rol"). Al lado de un agente decia algo que no era de ese agente.
Aca se cuenta POR AGENTE, con lo que la base ya guarda desde agosto:

  · asistente.conversations.rol_efectivo   -- con que agente se atendio
  · asistente.tool_calls.rol_solicitante   -- que herramienta pidio cada uno,
                                              si salio bien y si escribia
  · asistente.acciones_propuestas          -- lo que espero aprobacion, y que
                                              decidio la persona
  · asistente.tenant_config_historial      -- cada version de la config

TRES REGLAS, las mismas del resto del proyecto:

  · Solo canales REALES (nucleo/canales/canal.py). El simulador y el asistente
    interno no son clientes: contarlos diluye la tasa con conversaciones de
    prueba -- mismo criterio que 'tasa_escalamiento' desde el 30/10/2026.
  · Conteos agregados en SQL, no filas traidas para contarlas en Python.
  · Ningun dato del cliente sale entero. La bitacora muestra los ULTIMOS
    CUATRO digitos del contacto, como la Bandeja con un tercero (11/11/2026):
    alcanza para reconocer un caso sin exponer el telefono. Los parametros de
    las herramientas NO se leen: pueden traer cedulas y direcciones.

Solo LEE. Nada de aca decide ni autoriza nada.
"""
from __future__ import annotations

import re

from nucleo.persistencia.db import sesion


def _canales_reales() -> list[str]:
    from nucleo.canales.canal import REALES
    return sorted(REALES)


def ultimos_digitos(contacto: str | None) -> str:
    """'•••• 4821' a partir de cualquier identificador; '—' si no hay digitos."""
    digitos = re.sub(r"\D", "", contacto or "")
    return f"•••• {digitos[-4:]}" if len(digitos) >= 4 else "—"


def desempeno(tenant: str, dias: int) -> dict:
    """
    Por agente: conversaciones, cuantas pasaron a una persona y por que, y como
    le fue a cada herramienta que uso. Un agente sin conversaciones en el
    periodo NO aparece: "0 conversaciones" diria que anda bien, y lo que pasa
    es que no hay datos (sin dato != 0).
    """
    canales = _canales_reales()
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select rol_efectivo as rol, escalada_a_humano, motivo_escalamiento,
                      count(*) as n
                 from asistente.conversations
                where organization_id = %s
                  and canal = any(%s::text[])
                  and rol_efectivo is not null
                  and creado_en >= now() - (%s || ' days')::interval
                group by rol_efectivo, escalada_a_humano, motivo_escalamiento""",
            (org, canales, dias))
        conversaciones = [dict(f) for f in cur.fetchall()]

        cur.execute(
            """select t.rol_solicitante as rol, t.herramienta, t.es_escritura,
                      count(*) as usos,
                      count(*) filter (where not t.exito) as fallos,
                      mode() within group (order by t.codigo_error)
                          filter (where not t.exito) as error_mas_comun
                 from asistente.tool_calls t
                 join asistente.conversations c
                   on c.id = t.conversation_id and c.organization_id = t.organization_id
                where t.organization_id = %s
                  and c.canal = any(%s::text[])
                  and t.rol_solicitante is not null
                  and t.creado_en >= now() - (%s || ' days')::interval
                group by t.rol_solicitante, t.herramienta, t.es_escritura""",
            (org, canales, dias))
        herramientas = [dict(f) for f in cur.fetchall()]

    salida: dict[str, dict] = {}
    for f in conversaciones:
        a = salida.setdefault(f["rol"], {"conversaciones": 0, "escaladas": 0,
                                         "por_motivo": {}, "herramientas": {}})
        a["conversaciones"] += f["n"]
        if f["escalada_a_humano"]:
            a["escaladas"] += f["n"]
            motivo = f["motivo_escalamiento"] or "(sin motivo registrado)"
            a["por_motivo"][motivo] = a["por_motivo"].get(motivo, 0) + f["n"]
    for f in herramientas:
        a = salida.setdefault(f["rol"], {"conversaciones": 0, "escaladas": 0,
                                         "por_motivo": {}, "herramientas": {}})
        a["herramientas"][f["herramienta"]] = {
            "usos": f["usos"], "fallos": f["fallos"],
            "error_mas_comun": f["error_mas_comun"], "escribe": bool(f["es_escritura"])}
    for a in salida.values():
        total = a["conversaciones"]
        a["resueltas_sin_persona"] = total - a["escaladas"]
        a["tasa_sin_persona"] = (a["resueltas_sin_persona"] / total) if total else None
    return {"dias": dias, "agentes": salida}


def bitacora(tenant: str, rol: str, dias: int, limite: int = 100) -> list[dict]:
    """
    Lo que este agente CAMBIO en el mundo real, lo mas nuevo primero.

    Dos fuentes, porque son dos caminos distintos en el motor:

      · tool_calls con es_escritura: lo que se EJECUTO (solo, o despues de que
        una persona lo aprobara -- 'confirmado_por').
      · acciones_propuestas: lo que espero aprobacion. Las pendientes y las
        rechazadas no tienen fila en tool_calls -- no se ejecutaron -- y sin
        esta segunda fuente la bitacora callaria justo lo que una persona freno.

    Una aprobada aparece UNA vez: la de acciones_propuestas, que ya trae quien
    la aprobo y el resultado de ejecutarla.
    """
    canales = _canales_reales()
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select t.creado_en as cuando, t.herramienta, t.exito, t.codigo_error,
                      t.confirmado_por, c.usuario_externo
                 from asistente.tool_calls t
                 join asistente.conversations c
                   on c.id = t.conversation_id and c.organization_id = t.organization_id
                where t.organization_id = %s
                  and c.canal = any(%s::text[])
                  and t.rol_solicitante = %s
                  and t.es_escritura
                  and t.creado_en >= now() - (%s || ' days')::interval
                order by t.creado_en desc
                limit %s""",
            (org, canales, rol, dias, limite))
        ejecutadas = [dict(f) for f in cur.fetchall()]

        cur.execute(
            """select creado_en as cuando, herramienta, estado, revisado_por,
                      revisado_en, codigo_error, propuesto_por,
                      (resultado_ejecucion is not null) as se_ejecuto
                 from asistente.acciones_propuestas
                where organization_id = %s
                  and rol_solicitante = %s
                  and creado_en >= now() - (%s || ' days')::interval
                order by creado_en desc
                limit %s""",
            (org, rol, dias, limite))
        propuestas = [dict(f) for f in cur.fetchall()]

    filas = []
    for f in ejecutadas:
        #  Una ejecucion que vino de una propuesta aprobada ya esta abajo, con
        #  quien la aprobo: no se cuenta dos veces.
        if f["confirmado_por"]:
            continue
        filas.append({
            "cuando": f["cuando"].isoformat(), "herramienta": f["herramienta"],
            "cliente": ultimos_digitos(f["usuario_externo"]),
            "decidio": "solo", "quien": None,
            "resultado": "ok" if f["exito"] else "fallo",
            "error": None if f["exito"] else (f["codigo_error"] or "error sin codigo")})
    for f in propuestas:
        estado = f["estado"]
        if estado == "aprobada":
            resultado = "fallo" if f["codigo_error"] else ("ok" if f["se_ejecuto"] else "pendiente")
        elif estado == "rechazada":
            resultado = "no_se_ejecuto"
        else:
            resultado = "pendiente"
        filas.append({
            "cuando": f["cuando"].isoformat(), "herramienta": f["herramienta"],
            "cliente": ultimos_digitos(f["propuesto_por"]),
            "decidio": {"aprobada": "aprobo", "rechazada": "rechazo"}.get(estado, "espera"),
            "quien": f["revisado_por"],
            "resultado": resultado, "error": f["codigo_error"]})
    filas.sort(key=lambda f: f["cuando"], reverse=True)
    return filas[:limite]


def versiones_del_rol(tenant: str, rol: str, limite: int = 200) -> list[dict]:
    """
    Cada version de la config con la seccion de ESTE rol, la mas nueva
    primero. Solo la seccion del rol viaja (config->'roles'->rol), no la
    config entera: una config de Rapilink pesa cientos de KB y aca hacen falta
    dos campos. Una version en que el rol no existia trae 'rol': None.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select config_version as version, creado_en,
                      config->'roles'->(%s::text) as rol
                 from asistente.tenant_config_historial
                where organization_id = %s
                order by config_version desc
                limit %s""",
            (rol, org, limite))
        return [dict(f) for f in cur.fetchall()]


def rol_en_version(tenant: str, rol: str, version: int) -> dict | None:
    """La seccion del rol tal como estaba en UNA version. None si no estaba."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select config->'roles'->(%s::text) as rol
                 from asistente.tenant_config_historial
                where organization_id = %s and config_version = %s""",
            (rol, org, version))
        fila = cur.fetchone()
    return (dict(fila).get("rol") if fila else None) or None
