# -*- coding: utf-8 -*-
"""
================================================================================
 SUPERVISOR -- revisa conversaciones cerradas y propone aportes al manual
================================================================================

Hasta ahora, encontrar un buen ejemplo para /manual dependia de que un
humano fuera conversacion por conversacion marcando burbujas a mano. Este
modulo automatiza esa CAZA: cuando una conversacion se marca 'resuelta'
(ver nucleo/canales/api.py:chat()), se le pide a un modelo que la revise
completa y decida si fue un buen ejemplo, de que caso, y que aporta.

Para juzgar con algo mas que su propia opinion, la revision recupera del
corpus (nucleo/recuperacion/busqueda.py) los fragmentos del manual
relacionados con el tema de la conversacion -- mismo mecanismo de RAG que
usa el agente en vivo -- y se los da como referencia: puede decir "esto
CONTRADICE el manual" en vez de "esto me suena raro". Pero sigue sin poder
verificar nada que el manual no cubra todavia (ej. que la sintonizacion
real es "Antena" y no "Cable", que el maximo de TV son 4 antes de que
alguien lo documentara) -- eso lo sabe alguien con conocimiento real del
negocio, no un modelo leyendo la conversacion. Por eso toda revision
arranca en 'pendiente' (asistente.revisiones_supervisor) y un humano la
aprueba o descarta desde /manual antes de que cuente para algo.

Mismo criterio que nucleo/seguimiento/escalamiento.py: generico, no sabe
que tenant es, y nunca rompe el turno si algo falla.
================================================================================
"""

from __future__ import annotations

from nucleo.modelo import cliente
from nucleo.persistencia import db as persistencia
from nucleo.recuperacion import busqueda


def _esquema_revision(config) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "revisar_conversacion",
            "description": (
                "Evalua si esta conversacion, ya cerrada, es un buen "
                "ejemplo para el manual de procedimientos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "es_buen_ejemplo": {
                        "type": "boolean",
                        "description": "true si el agente siguio un "
                            "proceso correcto, sin inventar datos ni "
                            "contradecir el manual, y el caso se resolvio "
                            "bien. false si hubo algo dudoso (invento un "
                            "dato, se salto un paso, dio informacion que "
                            "no tenia como confirmar).",
                    },
                    "caso": {
                        "type": "string",
                        "enum": list(config.manual.casos),
                        "description": "De que caso/proceso se trata. "
                            "Requerido si es_buen_ejemplo=true; omitilo "
                            "si es false.",
                    },
                    "justificacion": {
                        "type": "string",
                        "description": "Por que decidiste esto -- en 1-2 "
                            "frases. Sirve tanto para que una persona "
                            "confirme un buen ejemplo como para entender "
                            "que salio mal en uno malo.",
                    },
                    "aporte_sugerido": {
                        "type": "string",
                        "description": "Que aprender de este caso puntual "
                            "para el manual, EN RELACION a la documentacion "
                            "que se te dio como referencia: si el manual ya "
                            "cubre el tema, que se puede precisar o mejorar "
                            "de lo ya escrito; si no lo cubre, que aporte "
                            "nuevo se puede agregar. No un checklist "
                            "completo, solo lo puntual de este caso. "
                            "Ignoralo si es_buen_ejemplo=false.",
                    },
                },
                "required": ["es_buen_ejemplo", "justificacion"],
            },
        },
    }


def _bloque_manual(fragmentos: list) -> str:
    """
    Lo que distingue a este supervisor de "un modelo opinando": sin esto,
    "fue buena la atencion" se juzga contra el conocimiento general del
    modelo, que es exactamente lo que el prompt de cliente_final tiene
    prohibido hacer (PRD -- no inventar). Con el manual real como
    referencia, el supervisor puede decir "esto CONTRADICE lo documentado"
    en vez de "esto me suena raro".
    """
    if not fragmentos:
        return (
            "No se encontro documentacion del manual relacionada con el tema "
            "de esta conversacion (o el manual todavia no cubre nada de "
            "esto). Evalua con criterio general: si el agente afirmo un "
            "dato que no tenia como confirmar, o se salteo un paso obvio, "
            "sigue siendo mal ejemplo aunque no haya guia escrita que lo diga.")
    cuerpo = "\n\n".join(f.citar() for f in fragmentos)
    return (
        "MANUAL DE PROCEDIMIENTOS -- fragmentos relacionados con el tema de "
        "esta conversacion (recuperados por similitud; pueden no cubrir "
        "todo el intercambio):\n\n"
        f"{cuerpo}\n\n"
        "Usalo como referencia de lo YA documentado. Si el agente dijo algo "
        "que CONTRADICE esto, es mal ejemplo aunque el cliente haya quedado "
        "conforme. Si dijo algo correcto que el manual no cubre o cubre "
        "distinto, es una oportunidad real de aporte -- decilo en "
        "'aporte_sugerido' apuntando a precisar o corregir lo ya escrito, "
        "no a repetirlo.")


def revisar(config, rol: str, tenant: str, conversation_id: str,
           historial: list[dict]) -> None:
    """
    Le pide al modelo que audite una conversacion ya cerrada y persiste el
    veredicto. Nunca rompe el turno: si falla, se loguea y listo -- la
    conversacion ya quedo cerrada de todas formas, esto es una capa aparte.

    'rol:supervisor' en llm.overrides (nucleo/config/schema.py) es una
    clave VIRTUAL, no un rol real del tenant: no aparece en config.roles.
    Reusa el mismo mecanismo que ya eligen los roles reales para poder
    apuntar la revision a un modelo distinto (tipicamente uno que razone
    mas, ya que esto no tiene la urgencia de latencia de responderle a un
    cliente en vivo) sin tocar codigo ni el esquema.

    Si no hay override dedicado, el respaldo es el modelo que YA esta
    usando 'rol' (no modelo_por_defecto): ese campo es el respaldo local
    (qwen3, pesado) que ningun rol usa en la practica porque estan
    redirigidos a DeepSeek -- caer ahi directo fallaria con
    'model not found' en cualquier instalacion sin ese modelo bajado
    (visto en vivo, agosto 2026). Ver el mismo aviso en escalamiento.evaluar().
    """
    if not config.manual.casos:
        return

    # Se busca con lo que dijo el CLIENTE (su problema/pregunta), no con la
    # conversacion completa -- mismo criterio que la busqueda en vivo
    # (nucleo/canales/api.py:chat()), pero aca se junta todo lo que escribio
    # en vez de un solo mensaje, porque el supervisor evalua el intercambio
    # entero y no un turno puntual.
    pregunta = " ".join(
        m.get("content", "") for m in historial
        if m.get("role") == "user" and m.get("content"))[:2000]
    try:
        fragmentos, _ = busqueda.recuperar(config, tenant, rol, pregunta) \
            if pregunta.strip() else ([], None)
    except Exception as e:
        print(f"[supervisor] no se pudo consultar el manual para "
              f"{conversation_id}: {type(e).__name__}: {e}")
        fragmentos = []

    referencia_modelo = config.llm.overrides.get(
        "rol:supervisor",
        config.llm.overrides.get(f"rol:{rol}", config.llm.modelo_por_defecto))
    mensajes = historial + [{
        "role": "user",
        "content": (
            "(Instruccion del sistema, no del cliente) Esta conversacion "
            "ya termino. Revisala completa comparandola contra el manual de "
            "abajo y evaluala llamando a revisar_conversacion. No "
            "respondas con texto.\n\n" + _bloque_manual(fragmentos)
        ),
    }]
    try:
        respuesta = cliente.chat(
            referencia_modelo, mensajes,
            tools=[_esquema_revision(config)])
    except Exception as e:
        print(f"[supervisor] fallo al revisar la conversacion "
              f"{conversation_id}: {type(e).__name__}: {e}")
        return

    for llamada in respuesta.llamadas:
        if llamada.nombre != "revisar_conversacion":
            continue
        args = llamada.argumentos
        try:
            persistencia.guardar_revision_supervisor(
                tenant, conversation_id,
                es_buen_ejemplo=bool(args.get("es_buen_ejemplo")),
                caso=args.get("caso"),
                justificacion=args.get("justificacion", ""),
                aporte_sugerido=args.get("aporte_sugerido"))
        except Exception as e:
            print(f"[supervisor] no se pudo guardar la revision de "
                  f"{conversation_id}: {type(e).__name__}: {e}")
        return
