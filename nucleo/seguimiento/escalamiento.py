# -*- coding: utf-8 -*-
"""
================================================================================
 ESCALAMIENTO -- pasar una conversacion a un humano
================================================================================

'escalamiento.activar_si' (nucleo/config/schema.py) existia en la
configuracion desde antes de este modulo, pero nada lo ejecutaba: ninguna
conversacion se marcaba escalada_a_humano. Sus valores por defecto
(frustracion_detectada, tres_fallos_seguidos, solicitud_explicita,
duda_de_identidad) son condiciones SEMANTICAS, no palabras clave -- por eso
quien las evalua es el modelo, no una comparacion de texto por codigo.

Una sola llamada al modelo por turno hace las cuatro cosas (evaluar() abajo):
si corresponde escalar, que etiqueta de conversaciones.etiquetas describe el
tema, si la conversacion ya llego a su fin (el cliente se despidio o
confirmo que su problema se resolvio) -- api.py usa esto ultimo para cerrar
la conversacion en la bandeja -- y un resumen corto del caso para cuando
escala. Se combinan para no duplicar el costo de una llamada aparte por
cada una.

El resumen va PRIMERO en la descripcion del ticket, antes de la
transcripcion completa (ver escalar()): quien toma el caso en BottleCRM lo
lee de entrada, sin tener que leer toda la conversacion para entender de
que se trata -- eso es lo que hacia perder tiempo antes.

Al escalar (escalar()), se crea el ticket real en BottleCRM via su API REST
(nucleo/herramientas/http.py:ejecutar(), el mismo ejecutor generico que ya
usan las herramientas de WispHub -- sin cliente HTTP nuevo) y se guarda el
resultado en asistente.conversations (nucleo/persistencia/db.py).

Generico a proposito: no sabe que tenant es, ni que "rapilink" existe --
todo lo que necesita (condiciones, taxonomia, credenciales del CRM) viene
de la config que le pasan.
================================================================================
"""

from __future__ import annotations

from nucleo.herramientas import http as herramientas_http
from nucleo.modelo import cliente
from nucleo.persistencia import db as persistencia

NOMBRE_HERRAMIENTA_TAGS_LISTAR = "listar_tags_crm"
NOMBRE_HERRAMIENTA_TAGS_CREAR = "crear_tag_crm"
NOMBRE_HERRAMIENTA_CASO_CREAR = "crear_caso_soporte"


def _herramienta(config, nombre: str):
    return next((h for h in config.herramientas if h.nombre == nombre), None)


def _esquema_evaluacion(config) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "evaluar_conversacion",
            "description": (
                "Evalua si esta conversacion necesita pasar a un humano AHORA, "
                "y que tema la describe mejor."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "escalar": {
                        "type": "boolean",
                        "description": "true si corresponde escalar a un humano ahora mismo.",
                    },
                    "motivo": {
                        "type": "string",
                        "enum": list(config.escalamiento.activar_si),
                        "description": "Por que escala. Ignoralo si escalar=false.",
                    },
                    "etiqueta": {
                        "type": "string",
                        "enum": list(config.conversaciones.etiquetas),
                        "description": "De que trata la conversacion, de esta lista.",
                    },
                    "resuelta": {
                        "type": "boolean",
                        "description": "true si el cliente confirmo que su "
                            "problema ya se resolvio o se esta despidiendo "
                            "(gracias, listo, ya quedo, chau) y la "
                            "conversacion no necesita seguir abierta. false "
                            "en cualquier otro caso, incluido mientras el "
                            "problema sigue sin resolver.",
                    },
                    "resumen": {
                        "type": "string",
                        "description": "2-3 frases resumiendo el caso para "
                            "quien lo va a atender: que reporto el cliente, "
                            "que ya se probo/descarto, y en que quedo "
                            "pendiente. Ignoralo si escalar=false. Va antes "
                            "de la transcripcion completa en el ticket, asi "
                            "que tiene que alcanzar por si solo, sin tener "
                            "que leer el resto para entenderlo.",
                    },
                },
                "required": ["escalar", "etiqueta", "resuelta"],
            },
        },
    }


def evaluar(config, rol: str, historial: list[dict]) -> dict | None:
    """
    Le pregunta al modelo si esta conversacion necesita un humano ahora, que
    etiqueta le corresponde, si ya llego a su fin, y (si escala) un resumen
    corto del caso. Nunca elige algo fuera de escalamiento.activar_si /
    conversaciones.etiquetas -- el esquema se lo impide (enum).

    Usa el mismo modelo que ya esta respondiendole a este rol
    (llm.overrides['rol:<rol>'], igual que motor.py) en vez de
    modelo_por_defecto: ese campo es el respaldo local (qwen3, ~18GB) que
    ningun rol usa en la practica porque los 5 estan redirigidos a DeepSeek
    -- usarlo aca habria fallado con 'model not found' en cualquier
    instalacion que no tenga ese modelo bajado.

    Devuelve None si no hay nada configurado para evaluar contra, o si el
    modelo no llamo la funcion en este turno (se reintenta en el proximo,
    no es un fallo: el modelo puede simplemente no haber tenido motivo).
    """
    if not config.escalamiento.activar_si or not config.conversaciones.etiquetas:
        return None

    referencia_modelo = config.llm.overrides.get(f"rol:{rol}", config.llm.modelo_por_defecto)
    mensajes = historial + [{
        "role": "user",
        "content": (
            "(Instruccion del sistema, no del cliente) Evalua la conversacion "
            "de arriba llamando a evaluar_conversacion. No respondas con texto."
        ),
    }]
    try:
        respuesta = cliente.chat(
            referencia_modelo, mensajes,
            tools=[_esquema_evaluacion(config)])
    except Exception as e:
        print(f"[escalamiento] fallo al evaluar: {type(e).__name__}: {e}")
        return None

    for llamada in respuesta.llamadas:
        if llamada.nombre == "evaluar_conversacion":
            return llamada.argumentos
    return None


def _resolver_tag(config, nombre_tag: str) -> str | None:
    """
    id de la etiqueta en BottleCRM, creandola si hace falta.

    Verificado en vivo (agosto 2026): a diferencia de otras pantallas del
    CRM (que resuelven una etiqueta por nombre solas via get_or_create_tags),
    POST /api/cases/ exige uuid en 'tags' y rechaza un nombre con
    'is not a valid UUID'. POST /api/tags/ si crea por nombre, pero rechaza
    un nombre duplicado con 400 -- por eso primero se busca en la lista
    existente y solo se crea si de verdad no esta.
    """
    listar = _herramienta(config, NOMBRE_HERRAMIENTA_TAGS_LISTAR)
    if not listar:
        return None
    existentes = herramientas_http.ejecutar(listar, {})
    for t in existentes:
        if isinstance(t, dict) and t.get("slug") == nombre_tag:
            return t.get("id")

    crear = _herramienta(config, NOMBRE_HERRAMIENTA_TAGS_CREAR)
    if not crear:
        return None
    creado = herramientas_http.ejecutar(crear, {"name": nombre_tag})
    return creado.get("id") if isinstance(creado, dict) else None


_ROL_LEGIBLE = {"user": "Cliente", "assistant": "Asistente"}


def _transcripcion_legible(historial: list[dict]) -> str:
    """
    Solo lo que de verdad se dijeron cliente y asistente -- para la
    descripcion del ticket que lee un humano. 'historial' trae mucho mas
    que eso (el prompt del sistema, el bloque de contexto del RAG con el
    manual completo, las respuestas crudas de las herramientas): pasarlo
    entero convertia la descripcion del caso en un volcado de la ingenieria
    de prompt en vez de un resumen legible del caso.
    """
    lineas = [
        f"{_ROL_LEGIBLE[m['role']]}: {m['content']}"
        for m in historial
        if m.get("role") in _ROL_LEGIBLE and m.get("content")
    ]
    return "\n".join(lineas)


def escalar(config, tenant: str, usuario_externo: str, conversation_id: str,
           historial: list[dict], motivo: str, etiqueta: str,
           resumen: str = "") -> None:
    """
    Crea el ticket en BottleCRM y marca la conversacion como escalada.

    Nunca rompe el turno: un fallo (CRM caido, token vencido, lo que sea) se
    loguea y listo -- mismo criterio que ya usa registrar_mensaje. El
    proximo turno vuelve a intentar evaluar() porque la conversacion sigue
    sin caso_id.
    """
    herramienta_caso = _herramienta(config, NOMBRE_HERRAMIENTA_CASO_CREAR)
    if not herramienta_caso:
        print(f"[escalamiento] '{NOMBRE_HERRAMIENTA_CASO_CREAR}' no esta "
              f"configurada para '{tenant}', no se crea el ticket.")
        return

    try:
        tag_id = _resolver_tag(config, etiqueta)
        transcripcion = _transcripcion_legible(historial)

        # El resumen va PRIMERO y nunca se recorta (es corto por diseno,
        # 2-3 frases via el esquema de evaluar_conversacion). El limite de
        # 4000 caracteres de BottleCRM se le aplica a la TRANSCRIPCION, no
        # al conjunto -- si se cortara desde el final del texto combinado
        # (como se hacia antes), un resumen largo o una transcripcion corta
        # podian dejar el resumen mismo afuera.
        encabezado = f"RESUMEN: {resumen.strip()}\n\n{'-' * 40}\n\n" if resumen.strip() else ""
        espacio_transcripcion = max(4000 - len(encabezado), 0)
        cuerpo = encabezado + transcripcion[-espacio_transcripcion:]

        payload = {
            # Unico por org (verificado en vivo: un nombre repetido da 400)
            # -- el id de conversacion de sobra lo garantiza.
            "name": f"WhatsApp {usuario_externo} - {conversation_id[:8]}",
            "description": cuerpo,
            "status": "New",
            "case_type": "Question",
            "priority": "Normal",
        }
        if tag_id:
            payload["tags"] = [tag_id]

        respuesta = herramientas_http.ejecutar(herramienta_caso, payload)
        caso_id = respuesta.get("id") if isinstance(respuesta, dict) else None

        persistencia.marcar_escalada(tenant, conversation_id, motivo, caso_id, etiqueta)
    except Exception as e:
        print(f"[escalamiento] fallo al escalar la conversacion "
              f"{conversation_id}: {type(e).__name__}: {e}")


# Estados en los que BottleCRM considera un caso terminado. 'Closed' es el
# unico que cases/signals.py trata como resuelto (RESOLVED_STATUSES); los
# demas siguen siendo trabajo abierto.
ESTADOS_CERRADOS = ("Closed", "Rejected", "Duplicate")


def caso_sigue_abierto(config, caso_id: str) -> bool:
    """
    Un GET al caso del CRM para saber si el humano ya lo resolvio.

    Existe para que el bot pueda PAUSARSE de verdad: sin esto, despues de
    escalar el asistente le sigue contestando al cliente al que se le acaba de
    decir que lo iba a atender una persona. El prompt puede pedirle que no lo
    haga, pero eso es guia y no garantia (PRD 7.4) -- la misma razon por la
    que el filtro de campos y la confirmacion de acciones sensibles viven en
    codigo.

    FAIL-SAFE: cualquier error de red, credencial o forma de la respuesta se
    interpreta como "sigue abierto". Nunca se asume resuelto sin confirmarlo:
    equivocarse hacia el lado de la pausa deja a un cliente esperando a una
    persona que ya viene; hacia el otro, lo deja hablando con un bot que le
    dijeron que no lo iba a atender.
    """
    if not caso_id:
        return False

    herramienta = _herramienta(config, NOMBRE_HERRAMIENTA_CASO_CREAR)
    if herramienta is None:
        return True

    try:
        import requests

        url = f"{herramienta.base_url.rstrip('/')}{herramienta.endpoint}{caso_id}/"
        r = requests.get(url, headers=herramientas_http.headers_de(herramienta), timeout=10)
        r.raise_for_status()
        cuerpo = r.json()
        caso = cuerpo.get("cases_obj", cuerpo) if isinstance(cuerpo, dict) else {}
        return caso.get("status") not in ESTADOS_CERRADOS
    except Exception as e:
        print(f"[escalamiento] no se pudo verificar el caso {caso_id}, "
              f"se mantiene pausado: {type(e).__name__}: {e}")
        return True
