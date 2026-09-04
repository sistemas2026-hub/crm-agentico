# -*- coding: utf-8 -*-
"""
================================================================================
 RESUMEN DE CONVERSACION  -  lo que el asistente recuerda cuando el cliente vuelve
================================================================================

Por que existe
--------------
Una conversacion se cerraba solo si el evaluador la marcaba resuelta o si la
cerraba una persona. Si el cliente volvia dias despues con OTRO problema, se
pegaba al mismo hilo. Medido el 18/08/2026 sobre una conversacion real: 67
mensajes a lo largo de 180 horas -- internet lento, un caso escalado y despues
television, todo junto.

Con ese contexto el modelo se pierde de dos formas, y las dos se vieron en esa
misma conversacion:

  - Volvio a preguntar cuantos equipos tenia el cliente, DOS TURNOS despues de
    que se lo contestara.
  - Dijo "ya mire el estado de tu servicio: la fibra llega bien y el equipo
    esta en linea" sin haber ejecutado NINGUNA herramienta en ese tramo: los
    datos eran de cuatro horas antes, de otro problema. Eso es peor que la
    pregunta repetida -- es decirle a alguien que su equipo esta sano sin
    haberlo mirado.

La conversacion ahora se cierra sola por inactividad. Pero cerrar a secas
perderia lo que ya se sabe, y el cliente tendria que contar todo otra vez.

Que hace este modulo
--------------------
Al cerrar, guarda en pocas frases que paso. Cuando el mismo usuario_externo
vuelve a escribir, ese texto se le entrega al modelo ANTES del primer turno:
sabe con quien habla y que quedo pendiente, sin arrastrar el historial entero.

Por que el resumen NO reemplaza a las herramientas
--------------------------------------------------
Dice que se hizo y como quedo, no el estado ACTUAL de nada. Un resumen que
dijera "su equipo estaba en linea" invita al modelo a repetirlo como si
siguiera siendo cierto, que es exactamente el error que este modulo existe
para evitar. Por eso el prompt de abajo pide hechos de la conversacion
(que reporto, que se probo, en que quedo) y no lecturas de sistemas.
================================================================================
"""
from __future__ import annotations

from nucleo.modelo import cliente

# Corto a proposito: viaja delante de cada primer turno, y un resumen largo
# compite por atencion con el problema que el cliente esta contando AHORA.
MAX_CARACTERES = 600

_INSTRUCCION = (
    "Resumi en 3 frases como maximo que paso en esta conversacion, para que "
    "quien la retome sepa en que quedo. Incluye: que reporto el cliente, que "
    "se probo o se hizo, y que quedo pendiente.\n\n"
    "NO incluyas lecturas de sistemas como si fueran actuales (que el equipo "
    "estaba en linea, que la señal llegaba bien, saldos): eso cambia y quien "
    "retome tiene que volver a medirlo. Escribe hechos de la conversacion, no "
    "el estado de la red.\n\n"
    "Sin saludos, sin adornos, sin opinar sobre el cliente."
)


def redactar(config, historial: list[dict]) -> str | None:
    """
    Devuelve el resumen, o None si no hay nada que resumir o si fallo.

    Nunca lanza: esto corre al cerrar una conversacion, y que falle un resumen
    no puede impedir el cierre ni romper el turno de nadie.
    """
    turnos = [m for m in historial
             if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    # Menos de dos turnos no es una conversacion: es un saludo suelto o un
    # mensaje sin respuesta. Resumir eso cuesta una llamada al modelo para
    # producir una frase que no le sirve a nadie.
    if len(turnos) < 4:
        return None
    try:
        conversacion = "\n".join(
            f"{'CLIENTE' if m['role'] == 'user' else 'ASISTENTE'}: {m['content']}"
            for m in turnos[-40:])
        resp = cliente.chat(
            config.llm.modelo_por_defecto,
            [{"role": "system", "content": _INSTRUCCION},
             {"role": "user", "content": conversacion}],
            tools=None, temperatura=0.0)
        texto = (resp.contenido or "").strip()
        return texto[:MAX_CARACTERES] or None
    except Exception as e:
        print(f"[resumen] no se pudo redactar: {type(e).__name__}: {e}")
        return None


def como_contexto(resumen: str) -> dict:
    """El resumen, con la forma en que entra al historial del turno nuevo."""
    return {"role": "system", "content":
            "Contexto de una conversacion ANTERIOR con este mismo cliente, "
            "que se cerro por inactividad. Sirve para que no le hagas repetir "
            "lo que ya conto:\n\n"
            f"{resumen}\n\n"
            "OJO: esto es lo que PASO, no el estado actual de nada. Si "
            "necesitas saber como esta su servicio ahora, vuelve a medirlo con "
            "tus herramientas -- nunca repitas una lectura de aca como si "
            "siguiera vigente."}
