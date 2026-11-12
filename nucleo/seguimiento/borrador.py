# -*- coding: utf-8 -*-
"""
================================================================================
 BORRADOR DE RESPUESTA -- la IA propone, una persona decide (30/10/2026)
================================================================================

En una conversacion escalada, quien atiende escribe todo a mano aunque el
asistente ya haya leido el hilo y consultado los sistemas. Esto le pide al
modelo una propuesta de respuesta que la persona EDITA y ENVIA ella.

CRECER EN ALCANCE, NO EN AUTONOMIA (CLAUDE.md §4): este modulo no envia nada,
no escribe en la base y no llama herramientas. Devuelve texto. Entre el
borrador y el cliente siempre esta una persona apretando Enviar.

A PEDIDO, nunca automatico: decision del usuario del 29/10/2026 (ficha
SPEC/objetivos/conversaciones-que-se-atienden-solas.md). Solo gasta modelo
cuando alguien lo pide.

Lo que ve el modelo es lo que ya esta en la conversacion: los mensajes del
cliente, lo que se le contesto y las notas internas del equipo. Nada nuevo
sale del sistema; el proveedor es el mismo que ya atiende a ese rol (PRD
RNF-01). Las notas van marcadas como contexto, no como algo que decir.

La redaccion pasa por la guardia de salida (nucleo/seguridad/salida.py), la
misma que corre antes de que el asistente le hable a un cliente: si detecta
una fuga, NO se devuelve el texto.
================================================================================
"""

from __future__ import annotations

from nucleo.modelo import cliente
from nucleo.modelo.tuteo import NORMALIZADORES
from nucleo.observabilidad import consumo
from nucleo.observabilidad.registro import registrar
from nucleo.seguridad import salida as guardia_salida

MAX_MENSAJES = 30
MAX_CARACTERES_MENSAJE = 1500
TIMEOUT_BORRADOR = 30.0

_TONO = {
    "formal": "formal y respetuoso (usted)",
    "cercano": "cercano y amable (tú)",
    "tecnico": "claro y técnico, sin rodeos",
}


class BorradorNoDisponible(Exception):
    """El borrador no se pudo producir o no se puede mostrar (fuga, vacio).

    `http` dice que codigo le corresponde a la respuesta, y existe para que
    quien la arma NO TENGA QUE LEER EL MENSAJE  --  12/11/2026.

    `api.py` decidia con `502 if "no respondio" in str(e) else 422`: una
    comparacion contra una cadena en español que vive en otro archivo. Cambiar
    esa frase --una tilde, una palabra-- convertia silenciosamente todos los
    fallos del modelo en 422, y nada lo habria dicho. El codigo es un dato de
    la excepcion, no algo que se deduzca de como se redacto.
    """

    #: 422 por omision: el pedido estaba bien y no hay nada que sugerir.
    http = 422

    def __init__(self, mensaje: str, http: int = 422):
        super().__init__(mensaje)
        self.http = http


def _instruccion(config) -> str:
    persona = config.persona
    empresa = config.identidad.nombre_comercial or config.identidad.nombre_legal
    tono = _TONO.get(persona.tono, _TONO["cercano"])
    return (
        f"Sos parte del equipo de atención de {empresa}. Redactá la PRÓXIMA respuesta al "
        f"cliente para que la envíe una persona del equipo, que la va a revisar antes. "
        f"Tono {tono}. En español.\n"
        "Reglas:\n"
        "- Solo el texto del mensaje, sin comillas, sin firma y sin explicar lo que hiciste.\n"
        "- Breve: dos o tres frases.\n"
        "- No prometas nada que la conversación no muestre confirmado: ni una visita, ni un "
        "plazo, ni una acción hecha.\n"
        "- No inventes datos (montos, fechas, horarios, nombres). Si falta un dato, pedíselo "
        "al cliente.\n"
        "- Las NOTAS INTERNAS son contexto del equipo: nunca las cites ni las repitas al "
        "cliente."
    )


def _historial(mensajes: list[dict]) -> list[dict]:
    """
    Los mensajes del hilo en el formato del modelo. El cliente es 'user'; lo
    que se le contesto -- la IA o una persona -- es 'assistant'. Las notas
    internas van como 'user' marcadas como contexto del equipo: el rol
    'system' a mitad de un historial no lo respetan todos los proveedores.
    """
    salida = []
    for m in mensajes[-MAX_MENSAJES:]:
        texto = str(m.get("contenido") or "").strip()[:MAX_CARACTERES_MENSAJE]
        if not texto:
            continue
        rol = m.get("rol")
        if rol == "user":
            salida.append({"role": "user", "content": texto})
        elif rol in ("assistant", "humano"):
            salida.append({"role": "assistant", "content": texto})
        elif rol == "nota":
            salida.append({"role": "user",
                           "content": f"[NOTA INTERNA DEL EQUIPO, no es del cliente] {texto}"})
    return salida


def redactar(config, *, rol: str | None, mensajes: list[dict]) -> str:
    """
    El borrador, o BorradorNoDisponible. 'mensajes' son los del hilo tal como
    los devuelve persistencia.mensajes_de; 'rol' es el de la conversacion,
    para usar el mismo modelo que ya la atiende (igual que escalamiento).
    """
    historial = _historial(mensajes)
    if not any(h["role"] == "user" and not h["content"].startswith("[NOTA") for h in historial):
        raise BorradorNoDisponible("el cliente todavía no escribió nada que responder")
    referencia = config.llm.overrides.get(f"rol:{rol}", config.llm.modelo_por_defecto) \
        if rol else config.llm.modelo_por_defecto
    mensajes_modelo = ([{"role": "system", "content": _instruccion(config)}] + historial
                       + [{"role": "user", "content": "(Instrucción del sistema, no del cliente) "
                           "Redactá ahora la próxima respuesta al cliente."}])
    try:
        respuesta = cliente.chat(referencia, mensajes_modelo, temperatura=0.3,
                                 timeout=TIMEOUT_BORRADOR,
                                 razonamiento=config.llm.razonamiento)
        consumo.anotar(referencia, respuesta)
    except Exception as e:
        registrar("borrador", "fallo al pedir el borrador", error=e)
        raise BorradorNoDisponible("el modelo no respondió", http=502) from None
    texto = (respuesta.contenido or "").strip().strip('"').strip()
    if not texto:
        raise BorradorNoDisponible("el modelo no propuso nada")
    # El TRATAMIENTO lo garantiza el codigo, no el prompt: el mismo
    # normalizador que el motor aplica a sus respuestas (nucleo/modelo/
    # tuteo.py). Medido el 30/10/2026: con el modelo real el borrador salio
    # «¿podés confirmarme…?» para una empresa que le habla de tú al cliente.
    normalizar = NORMALIZADORES.get(config.persona.normalizar_tratamiento or "")
    if normalizar:
        texto = normalizar(texto)
    limpio, fuga = guardia_salida.verificar(texto)
    if fuga:
        registrar("borrador", "borrador bloqueado por la guardia de salida")
        raise BorradorNoDisponible("la sugerencia mencionaba datos internos")
    return limpio
