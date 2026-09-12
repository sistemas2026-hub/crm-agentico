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


def hace_cuanto(horas: float) -> str:
    """
    'hace 20 minutos', 'ayer', 'hace 26 dias'. En palabras y no en una fecha
    porque es lo que el modelo va a REPETIR: "el 12 de agosto" lo obliga a
    calcular cuanto hace de eso; "hace 26 dias" ya es la respuesta.

    Los tramos son gruesos a proposito. La diferencia que importa no es entre
    18 y 22 horas, es entre "recien" y "hace semanas" -- que es lo que decide
    si corresponde retomar el tema o preguntar de cero.
    """
    if horas < 1:
        minutos = max(1, int(horas * 60))
        return f"hace {minutos} minuto{'s' if minutos != 1 else ''}"
    if horas < 24:
        h = int(horas)
        return f"hace {h} hora{'s' if h != 1 else ''}"
    dias = int(horas / 24)
    if dias == 1:
        return "ayer"
    if dias < 31:
        return f"hace {dias} dias"
    meses = int(dias / 30)
    return f"hace {meses} {'mes' if meses == 1 else 'meses'}"


def como_contexto(resumen: str, horas: float | None = None) -> dict:
    """
    El resumen, con la forma en que entra al historial del turno nuevo.

    'horas' es cuanto hace que esa conversacion se cerro, y no sobra: sin
    ella, una de hace dos horas y una de hace un mes le llegan al modelo
    IDENTICAS. Paso en produccion el 07/09/2026 -- ante un "Hola", el
    asistente contesto "veo que estuvimos hablando HACE UN MOMENTO sobre un
    problema de internet", y esa conversacion era de veintiseis dias antes.
    El resumen que se le dio era correcto; lo unico falso fue el cuando, que
    era justo lo unico que no se le habia dicho.

    Queda con valor por defecto para no romper a quien la llame sin el dato,
    pero ahi se dice que no consta en vez de callarlo: un modelo sin fecha
    rellena el hueco, y rellena con "recien".
    """
    cuando = hace_cuanto(horas) if horas is not None else "en una fecha que no consta"
    return {"role": "system", "content":
            "Contexto de una conversacion ANTERIOR con este mismo cliente, "
            f"cerrada por inactividad {cuando.upper()}. Sirve para que no le "
            "hagas repetir lo que ya conto:\n\n"
            f"{resumen}\n\n"
            "OJO CON DOS COSAS.\n"
            f"1) Esa conversacion fue {cuando}. Si mencionas que ya habian "
            "hablado, di cuando fue DE VERDAD -- nunca 'hace un momento' ni "
            "'recien' si no lo fue. Y si paso mucho tiempo, no des por hecho "
            "que escribe por lo mismo: preguntaselo.\n"
            "2) Esto es lo que PASO, no el estado actual de nada. Si "
            "necesitas saber como esta su servicio ahora, vuelve a medirlo con "
            "tus herramientas -- nunca repitas una lectura de aca como si "
            "siguiera vigente."}
