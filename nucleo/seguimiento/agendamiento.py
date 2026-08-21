# -*- coding: utf-8 -*-
"""
================================================================================
 AGENDAMIENTO AUTOMATICO -- agenda una visita tecnica sin pasar por un humano
================================================================================

Hoy, cuando un especialista tecnico (ej. soporte_tecnico_cliente) decide
escalar una falla de TV, siempre pasa por un humano en BottleCRM -- aunque
el checklist del manual ya haya quedado completo y lo unico que haria esa
persona sea releer la conversacion y llamar a 'agendar_visita_tecnica' con
los mismos datos que el chat ya reunio.

Este modulo hace esa misma relectura, con el manual real como referencia
(mismo patron que nucleo/seguimiento/supervisor.py: RAG-grounded, para
juzgar contra el procedimiento documentado, no contra la opinion general
del modelo). Solo corre para los casos que el tenant declaro
explicitamente en 'escalamiento.agendamiento_automatico' -- ver
nucleo/config/schema.py:Escalamiento. Apagado por defecto.

FALLA CERRADA, siempre: cualquier duda, dato faltante o error tecnico cae
al camino de hoy (escalar a un humano). Nunca se resuelve una duda a favor
de agendar -- despachar un tecnico es mas costoso que abrir un ticket.

SEGUNDA CAPA (PRD 7.4): el modelo decide SI corresponde agendar y compone
una descripcion legible; el CODIGO valida que los datos minimos esten
presentes y ejecuta la escritura real contra WispHub -- nunca via
tool-calling del modelo. Mismo principio que ya aplica
escalamiento.escalar() al crear el ticket de BottleCRM en codigo.
================================================================================
"""

from __future__ import annotations

import json

from nucleo.modelo import cliente
from nucleo.modelo.motor import _buscar_campo, _ejecutar_tool
from nucleo.recuperacion import busqueda


def _esquema_verificacion(config) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "verificar_agendamiento",
            "description": (
                "Revisa si el checklist del manual para este caso quedo "
                "completo en la conversacion, y si corresponde agendar una "
                "visita tecnica sin pasar por un humano."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "checklist_completo": {
                        "type": "boolean",
                        "description": "true si cada punto del "
                            "procedimiento (ver el manual mas abajo) fue "
                            "preguntado Y recibio una respuesta suficiente "
                            "en la conversacion. false si falta alguno.",
                    },
                    "corresponde_agendar": {
                        "type": "boolean",
                        "description": "Solo tiene sentido si "
                            "checklist_completo=true. true si, con todo "
                            "dentro de lo recomendado, la falla persiste "
                            "(posible falla real del servicio). false si el "
                            "procedimiento explica el problema por una "
                            "causa del lado del cliente -- en ese caso NO "
                            "corresponde agendar nada, se sigue orientando "
                            "al cliente.",
                    },
                    "pregunta_faltante": {
                        "type": "string",
                        "description": "Solo si checklist_completo=false: "
                            "la UNICA pregunta puntual que falta para "
                            "completarlo (no un resumen de todo lo que "
                            "falta, un solo punto concreto).",
                    },
                    "descripcion_visita": {
                        "type": "string",
                        "description": "Solo si corresponde_agendar=true: "
                            "2-3 frases describiendo el caso para el "
                            "tecnico que va a la visita -- que se "
                            "confirmo, que no se explica por causas del "
                            "cliente. Solo lo que la conversacion confirmo "
                            "de verdad, nunca inventado.",
                    },
                },
                "required": ["checklist_completo"],
            },
        },
    }


def verificar(config, tenant: str, rol: str, historial: list[dict]) -> dict | None:
    """
    Le pide al modelo que revise, contra el manual real, si el checklist de
    este caso quedo completo y si corresponde agendar. Nunca rompe el turno:
    un fallo (RAG caido, el modelo no respondio con la funcion) devuelve
    None, y quien llama cae al camino de escalar a un humano -- ver el
    docstring del modulo, "falla cerrada, siempre".

    Usa la transcripcion COMPLETA, no un resumen corto: un resumen de 2-3
    frases (como el que ya arma escalamiento.evaluar()) puede omitir justo
    el campo que falto, y es exactamente lo que hay que poder detectar.
    """
    pregunta = " ".join(
        m.get("content", "") for m in historial
        if m.get("role") == "user" and m.get("content"))[:2000]
    try:
        fragmentos, _ = busqueda.recuperar(config, tenant, rol, pregunta) \
            if pregunta.strip() else ([], None)
    except Exception as e:
        print(f"[agendamiento] no se pudo consultar el manual: "
              f"{type(e).__name__}: {e}")
        fragmentos = []

    if not fragmentos:
        # Sin el procedimiento real no hay contra que verificar el
        # checklist -- no se inventa un criterio general aca (a diferencia
        # del supervisor, que si puede opinar sin manual). Cae al camino de
        # siempre.
        print("[agendamiento] no se encontro el procedimiento del manual "
              "para este caso, se cae al camino humano")
        return None

    cuerpo_manual = "\n\n".join(f.citar() for f in fragmentos)
    referencia_modelo = config.llm.overrides.get(f"rol:{rol}", config.llm.modelo_por_defecto)
    mensajes = historial + [{
        "role": "user",
        "content": (
            "(Instruccion del sistema, no del cliente) Revisa la "
            "conversacion de arriba contra el procedimiento real de abajo "
            "y evaluala llamando a verificar_agendamiento. No respondas "
            "con texto.\n\n"
            "PROCEDIMIENTO DEL MANUAL para este caso:\n\n"
            f"{cuerpo_manual}"
        ),
    }]
    try:
        respuesta = cliente.chat(
            referencia_modelo, mensajes, tools=[_esquema_verificacion(config)])
    except Exception as e:
        print(f"[agendamiento] fallo al verificar: {type(e).__name__}: {e}")
        return None

    for llamada in respuesta.llamadas:
        if llamada.nombre == "verificar_agendamiento":
            return llamada.argumentos
    return None


def evidencia_ya_alcanza(config, caso: str, historial: list[dict]) -> str | None:
    """
    Si la traza ya prueba, por si sola, que corresponde una visita.

    Devuelve el motivo legible (para el log) o None si hay que pasar por el
    verificador del manual, que es el camino normal.

    Por que existe: el verificador contrasta la conversacion contra el
    procedimiento que el RAG recupere, y ese procedimiento esta escrito para
    una persona que atiende -- no para un agente que ya midio la OLT. Visto
    el 21/08/2026, una falla sin señal optica no llegaba a agendar nunca
    porque el checklist recuperado exigia "¿que mensaje aparece en el
    dispositivo?", una pregunta que no tiene respuesta cuando no hay ninguna
    conexion de la cual leer un mensaje.

    Solo se salta el verificador donde la evidencia viene de la RED y no del
    relato del cliente. Cada condicion la declara el tenant
    ('escalamiento.evidencia_suficiente') con la misma forma que
    'Herramienta.exige_previas'; sin declararlas, todo sigue pasando por el
    verificador.
    """
    condiciones = (config.escalamiento.evidencia_suficiente or {}).get(caso) or []
    if not condiciones:
        return None
    for cond in condiciones:
        for msg in historial:
            if msg.get("role") != "tool" or msg.get("name") != cond.herramienta:
                continue
            try:
                dato = json.loads(msg.get("content") or "null")
            except (TypeError, ValueError):
                continue
            if isinstance(dato, dict) and dato.get("error"):
                continue
            if cond.acepta(_buscar_campo(dato, cond.campo)):
                return f"{cond.herramienta}.{cond.campo}"
    return None


def agendar(config, tenant: str, sesion, nombre_herramienta: str,
           descripcion: str) -> str | None:
    """
    Ejecuta la herramienta de agendamiento DIRECTO, en codigo -- nunca via
    tool-calling del modelo (el especialista que atiende al cliente ni
    siquiera tiene esta herramienta en su catalogo). El modelo ya opino (en
    verificar()) que corresponde; esto es la segunda capa que arma los
    argumentos reales y confirma que no falta nada antes de escribir contra
    WispHub.

    Devuelve el id del ticket creado, o None si no se pudo -- nunca lanza:
    un fallo aca tiene que caer al camino humano, no romper el turno.
    """
    herramienta = next((h for h in config.herramientas if h.nombre == nombre_herramienta), None)
    if herramienta is None:
        print(f"[agendamiento] '{nombre_herramienta}' no esta configurada "
              f"para '{tenant}', no se agenda.")
        return None

    servicio = getattr(sesion, "id_cliente", None) if sesion is not None else None
    descripcion = (descripcion or "").strip()
    if not servicio or not descripcion:
        print(f"[agendamiento] faltan datos minimos (servicio={bool(servicio)}, "
              f"descripcion={bool(descripcion)}), no se agenda.")
        return None

    try:
        respuesta = _ejecutar_tool(
            herramienta, sesion, {"servicio": servicio, "descripcion": descripcion}, tenant)
        # 'id_ticket', no 'id' -- _ejecutar_tool devuelve la respuesta CRUDA
        # de WispHub (sin pasar por listas_blancas.filtrar_campos, que no
        # renombra nada), y el campo real del ticket es 'id_ticket' (ver
        # campos_permitidos.agendar_visita_tecnica en el config del tenant).
        return respuesta.get("id_ticket") if isinstance(respuesta, dict) else None
    except Exception as e:
        print(f"[agendamiento] fallo al ejecutar '{nombre_herramienta}': "
              f"{type(e).__name__}: {e}")
        return None
