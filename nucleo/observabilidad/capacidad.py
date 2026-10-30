# -*- coding: utf-8 -*-
"""
================================================================================
 EL TABLERO DE CAPACIDAD  --  lo que se le muestra a la empresa (30/10/2026)
================================================================================

Toma los conteos de nucleo/persistencia/capacidad.py y los vuelve las seis
metricas de PRD §2. Todo numero sale de aca o de SQL, nunca del modelo (§12.5).

Dos reglas que no se negocian:

  - NO SE INVENTA UN NUMERO. Sin cerradas, la tasa es null y no 0; sin
    personas que atendieron, no hay "casos por persona"; sin minutos
    declarados por la empresa, no hay minutos ahorrados. Cada null viaja con
    su motivo, porque un 0 se lee como un resultado.
  - LOS CONTRAPESOS VAN JUNTO A LA PALANCA. La resolucion sin persona nunca
    se entrega sin el recontacto y la satisfaccion al lado: subir la primera
    cerrando casos sin resolverlos es la trampa que el tablero tiene que dejar
    a la vista, no esconder (PRD §2, "Regla").

CORTE: 'messages.origen' existe desde el 16/09/2026. Antes de esa fecha no se
puede saber si una persona escribio, asi que un periodo anterior se recorta y
la respuesta lo dice.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timezone

#: 16/09/2026 00:00 en Bogota: desde aca cada mensaje dice quien lo escribio.
CORTE = datetime(2026, 9, 16, 5, 0, tzinfo=timezone.utc)


def _tasa(parte, todo):
    return round(parte / todo, 4) if todo else None


def componer(m: dict, minutos_por_conversacion: int | None,
             minutos_por_visita: int | None) -> dict:
    cerradas = m["cerradas"]
    resueltas = m["resueltas_sin_persona"]
    personas = m["personas_que_atendieron"]
    evitadas = m.get("visitas_evitadas")

    por_persona = {"valor": round(cerradas / personas, 2) if personas else None,
                   "casos": cerradas, "personas": personas}
    if not personas:
        por_persona["motivo"] = "ninguna persona atendio una conversacion en el periodo"

    visitas = {"valor": evitadas, "reinicios_confirmados": m.get("reinicios_confirmados"),
               "dias_sin_visita": m.get("dias_sin_visita"),
               "definicion": "accion remota confirmada sin visita al mismo cliente "
                             "en los dias siguientes; es una estimacion"}
    if evitadas is None:
        visitas["motivo"] = ("la empresa no declaro que acciones evitan una visita "
                             "ni que herramientas la agendan")

    por_conversaciones = resueltas * minutos_por_conversacion if minutos_por_conversacion else None
    por_visitas = (evitadas * minutos_por_visita
                   if minutos_por_visita and evitadas is not None else None)
    partes = [x for x in (por_conversaciones, por_visitas) if x is not None]
    minutos = {"total": sum(partes) if partes else None,
               "por_conversaciones": por_conversaciones, "por_visitas": por_visitas}
    faltan = []
    if not minutos_por_conversacion:
        faltan.append("minutos por conversacion")
    if not minutos_por_visita:
        faltan.append("minutos por visita")
    if faltan:
        minutos["motivo"] = "la empresa no declaro: " + ", ".join(faltan)

    return {
        "casos_por_persona": por_persona,
        "resolucion_sin_persona": {"tasa": _tasa(resueltas, cerradas),
                                   "resueltas": resueltas, "cerradas": cerradas},
        "recontacto": {"ventana_horas": m.get("ventana_recontacto_horas"),
                       "tasa": _tasa(m["recontactos"], cerradas),
                       "tasa_sin_persona": _tasa(m["recontactos_sin_persona"], resueltas),
                       "recontactos": m["recontactos"],
                       "recontactos_sin_persona": m["recontactos_sin_persona"]},
        "satisfaccion": {"promedio": (round(m["satisfaccion_promedio"], 2)
                                      if m["satisfaccion_promedio"] is not None else None),
                         "respondidas": m["encuestas_respondidas"],
                         "enviadas": m["encuestas_enviadas"]},
        "visitas_evitadas": visitas,
        "minutos_ahorrados": minutos,
        "tiempo_hasta_resolucion": {
            "mediana_minutos": (round(m["minutos_hasta_resolucion"], 1)
                                if m["minutos_hasta_resolucion"] is not None else None)},
    }
