# -*- coding: utf-8 -*-
"""
================================================================================
 CANAL WHATSAPP  -  traduccion con la Cloud API de Meta
================================================================================

Que es y que NO es
------------------
Es la capa de traduccion entre el formato de Meta y lo que el motor ya
entiende. Todo lo especifico de WhatsApp vive aca: la forma del webhook, la
firma, el sobre de envio, la ventana de 24 horas. Nada de eso se filtra al
resto del nucleo.

NO tiene logica de conversacion. No decide que contestar, no verifica
identidad, no escala: eso ya esta resuelto en nucleo/modelo/motor.py y lo
orquesta nucleo/canales/api.py. Un canal traduce y entrega.

Por que no es una "herramienta"
-------------------------------
Una Herramienta (nucleo/herramientas/) es algo que el MODELO decide invocar
para responder una pregunta. El canal es por donde entra y sale la
conversacion: existe antes de que haya modelo, y sigue existiendo cuando el
que contesta es una persona desde la bandeja. Son capas distintas.

Sobre la constante del host
---------------------------
'graph.facebook.com' es el mismo para toda empresa que use WhatsApp Business
-- lo que cambia por empresa es la CUENTA (phone_number_id, token), que vive
en la configuracion y en los secretos. Por eso esta en la lista blanca de
tests/test_nucleo_sin_tenants.py junto a los proveedores de modelo, y no en el
YAML de cada tenant. 'canales.whatsapp.api_base' lo sobreescribe para quien
entre por un BSP.

LA VENTANA DE 24 HORAS  (no es un detalle de implementacion)
------------------------------------------------------------
Meta solo acepta texto libre dentro de las 24 h desde el ULTIMO mensaje del
cliente. Fuera de esa ventana solo pasan plantillas aprobadas. Es la causa mas
comun de "le escribi y no le llego": la API responde error, no silencio, y por
eso enviar() devuelve el motivo en vez de tragarselo -- un agente que cree que
su respuesta salio cuando no salio esta peor que uno que ve el error.
================================================================================
"""

from __future__ import annotations

import hashlib
import hmac

import requests

from nucleo.seguridad import secretos

API_BASE_POR_DEFECTO = "https://graph.facebook.com"
TIMEOUT_SEGUNDOS = 20

# Meta devuelve este codigo cuando el texto libre cae fuera de la ventana de
# 24 h. Se distingue del resto de errores porque tiene una salida concreta
# (mandar una plantilla), no es un fallo a reintentar.
CODIGO_FUERA_DE_VENTANA = 131047

# Tipos de mensaje que traen un archivo aparte, todos con la misma forma
# {id, mime_type, caption} dentro de la clave que se llama igual que el tipo.
TIPOS_CON_ARCHIVO = ("image", "audio", "video", "document", "sticker", "voice")


class ErrorWhatsApp(Exception):
    """Fallo al hablar con la Cloud API, o configuracion incompleta."""


# =============================================================================
#  CONFIGURACION Y CREDENCIALES
# =============================================================================

def _cfg(config):
    """El bloque canales.whatsapp, ya validado. Levanta si el canal no esta
    activo: es preferible a mandar mensajes desde un canal que la empresa
    todavia no habilito."""
    cfg = getattr(config.canales, "whatsapp", None)
    if cfg is None or not cfg.activo:
        raise ErrorWhatsApp(
            "El canal de WhatsApp no esta activo para esta empresa "
            "(canales.whatsapp.activo).")
    return cfg


def _secreto(tenant: str, ref: str | None, para_que: str) -> str:
    if not ref:
        raise ErrorWhatsApp(
            f"canales.whatsapp no declara el nombre del secreto {para_que}.")
    valor = secretos.obtener(tenant, ref)
    if not valor:
        raise ErrorWhatsApp(
            f"Falta la credencial '{ref}' ({para_que}). Cargala en los ajustes "
            f"de la empresa o en el entorno del motor.")
    return valor


def activo(config) -> bool:
    """Sin levantar -- para preguntar antes de intentar."""
    cfg = getattr(config.canales, "whatsapp", None)
    return bool(cfg and cfg.activo)


# =============================================================================
#  ENTRADA  -  verificar la firma y traducir el webhook
# =============================================================================

def firma_valida(config, tenant: str, cuerpo_crudo: bytes,
                 cabecera: str | None) -> bool:
    """
    HMAC-SHA256 del cuerpo CRUDO contra el App Secret, comparado con la
    cabecera 'X-Hub-Signature-256' que manda Meta.

    Falla cerrado: sin cabecera, con formato raro, o sin poder resolver el
    secreto, devuelve False. Nunca True 'por las dudas' -- el webhook es una
    URL publica, y sin esto cualquiera puede inyectar conversaciones a nombre
    de un cliente.

    Sobre el cuerpo CRUDO: se firma el byte a byte que llego, no el JSON
    reserializado. Volver a serializar cambia espacios y orden de claves, y la
    firma deja de coincidir aunque el contenido sea el mismo.
    """
    if not cabecera or not cabecera.startswith("sha256="):
        return False
    try:
        secreto = _secreto(tenant, _cfg(config).app_secret_ref,
                           "que firma los webhooks (app_secret_ref)")
    except Exception as e:
        # Se atrapa TODO, no solo ErrorWhatsApp: si la base esta caida,
        # secretos.obtener() levanta ErrorSecreto, y dejarlo propagar
        # convertiria un webhook no verificable en un 500. No verificar es no
        # procesar, y eso se dice con un 401 -- pero se registra, porque desde
        # afuera es indistinguible de un atacante y desde adentro es una caida.
        print(f"[whatsapp] no se pudo verificar la firma de '{tenant}': "
              f"{type(e).__name__}: {e}")
        return False
    esperado = hmac.new(secreto.encode(), cuerpo_crudo, hashlib.sha256).hexdigest()
    # compare_digest y no '==': comparar en tiempo constante evita filtrar la
    # firma correcta midiendo cuanto tarda en fallar.
    return hmac.compare_digest(esperado, cabecera.split("=", 1)[1])


def token_de_verificacion_valido(config, tenant: str, recibido: str | None) -> bool:
    """El handshake de alta: Meta llama una vez con GET y espera que le
    devuelvan 'hub.challenge' solo si 'hub.verify_token' coincide."""
    if not recibido:
        return False
    try:
        esperado = _secreto(tenant, _cfg(config).verify_token_ref,
                            "del handshake (verify_token_ref)")
    except Exception as e:
        print(f"[whatsapp] no se pudo verificar el handshake de '{tenant}': "
              f"{type(e).__name__}: {e}")
        return False
    return hmac.compare_digest(esperado, recibido)


def mensajes_entrantes(cuerpo: dict) -> list[dict]:
    """
    Aplana el sobre de Meta a una lista de mensajes simples.

    El sobre viene anidado y en plural en los tres niveles
    (entry[] -> changes[] -> value.messages[]) porque Meta puede agrupar varios
    eventos en una sola entrega. En la practica casi siempre trae uno, pero
    asumirlo perderia mensajes en silencio bajo carga.

    Devuelve, por mensaje:
        wamid    id unico de Meta -- la clave para no contestar dos veces
        de       telefono del cliente, en formato internacional sin '+'
        nombre   como se llama en su perfil de WhatsApp, si vino
        tipo     text | image | audio | ...
        texto    el contenido si es texto; '' en los demas tipos
        crudo    el mensaje entero, para lo que todavia no se traduce

    DE DONDE SALE EL TELEFONO  (no es una sola clave)
    -------------------------------------------------
    La referencia de Meta dice que el remitente viene en 'messages[].from', y
    que 'contacts[].wa_id' trae el mismo numero. En la practica llego una
    tercera forma: 'from_user_id' con un valor OPACO ('CO.13603999...'), que
    no es un telefono y no sirve para cruzar contra la base del ISP.

    Por eso se prefiere 'wa_id' de 'contacts': es el unico que la
    documentacion define como el numero, y es el que necesita la verificacion
    por posesion del canal (nucleo/seguridad/verificacion.py). Las otras dos
    quedan como respaldo, en orden de confiabilidad -- sin ninguna de las
    tres no hay a quien contestarle.
    """
    salida = []
    for entrada in (cuerpo or {}).get("entry", []) or []:
        for cambio in entrada.get("changes", []) or []:
            valor = cambio.get("value") or {}

            # Los contactos vienen al lado de los mensajes, en la misma
            # entrega. Casi siempre es uno; se indexa por si Meta agrupa
            # varios remitentes en un mismo envio.
            contactos = valor.get("contacts") or []
            wa_id = None
            nombre = None
            if contactos:
                # 'wa_id' es lo que documenta Meta. 'user_id' es lo que llego
                # en vivo (agosto 2026) en su lugar: un identificador opaco,
                # no un telefono. Se toma igual porque es la unica forma de
                # direccionar a esa persona -- y se prefiere al
                # 'from_user_id' del mensaje porque ESE viene con prefijo de
                # pais ('CO.136...') y los acuses de entrega de Meta nombran
                # al destinatario SIN el ('136...').
                wa_id = contactos[0].get("wa_id") or contactos[0].get("user_id")
                nombre = ((contactos[0].get("profile") or {}).get("name"))

            for m in valor.get("messages", []) or []:
                tipo = m.get("type", "")
                # Los tipos con archivo comparten la forma {id, mime_type,
                # caption}: se lee igual para todos en vez de una rama por tipo.
                adjunto = m.get(tipo) or {} if tipo in TIPOS_CON_ARCHIVO else {}
                salida.append({
                    "wamid": m.get("id"),
                    # 'from' es lo que documenta la Cloud API, pero Meta
                    # tambien entrega 'from_user_id' -- verificado en vivo
                    # (agosto 2026) sobre un mensaje real: las claves que
                    # llegaron fueron ['from_user_id','id','text','timestamp',
                    # 'type'], sin 'from'. Leer solo una de las dos descarta
                    # mensajes legitimos, y el descarte es silencioso porque
                    # sin remitente no hay a quien contestarle.
                    "de": wa_id or m.get("from") or m.get("from_user_id"),
                    "nombre": nombre,
                    "tipo": tipo,
                    "texto": (m.get("text") or {}).get("body", "") if tipo == "text" else "",
                    # El pie de foto es texto del cliente: "mira como quedo"
                    # dice tanto como la foto misma.
                    "descripcion": adjunto.get("caption", ""),
                    "media_id": adjunto.get("id"),
                    "mime": adjunto.get("mime_type"),
                    "crudo": m,
                })
    return salida


def estados_entrantes(cuerpo: dict) -> list[dict]:
    """
    Acuses de entrega (sent/delivered/read/failed), que llegan por el mismo
    webhook que los mensajes pero en 'value.statuses'.

    Se separan a proposito: un webhook de estado NO es una conversacion y no
    debe despertar al modelo. Confundirlos hace que el bot conteste a su propio
    acuse de recibo.
    """
    salida = []
    for entrada in (cuerpo or {}).get("entry", []) or []:
        for cambio in entrada.get("changes", []) or []:
            for s in (cambio.get("value") or {}).get("statuses", []) or []:
                salida.append({
                    "wamid": s.get("id"),
                    "estado": s.get("status"),
                    "de": s.get("recipient_id"),
                    "error": (s.get("errors") or [{}])[0].get("message"),
                })
    return salida


# =============================================================================
#  SALIDA  -  enviar
# =============================================================================

def _url(config, recurso: str) -> str:
    cfg = _cfg(config)
    base = (cfg.api_base or API_BASE_POR_DEFECTO).rstrip("/")
    return f"{base}/{cfg.version_api}/{recurso}"


def _post(config, tenant: str, recurso: str, payload: dict) -> dict:
    token = _secreto(tenant, _cfg(config).token_ref,
                     "de envio (token_ref)")
    r = requests.post(
        _url(config, recurso),
        headers={"Authorization": f"Bearer {token}"},
        json=payload, timeout=TIMEOUT_SEGUNDOS)

    if r.status_code >= 400:
        try:
            err = (r.json() or {}).get("error") or {}
        except ValueError:
            err = {}
        codigo = err.get("code")
        detalle = err.get("message") or r.text[:200]
        if codigo == CODIGO_FUERA_DE_VENTANA:
            raise ErrorWhatsApp(
                "Pasaron mas de 24 horas desde el ultimo mensaje del cliente, "
                "asi que WhatsApp ya no acepta texto libre: hay que usar una "
                "plantilla aprobada.")
        raise ErrorWhatsApp(f"WhatsApp rechazo el envio ({codigo}): {detalle}")

    return r.json()


def enviar_texto(config, tenant: str, para: str, texto: str) -> str | None:
    """
    Un mensaje de texto al cliente. Devuelve el wamid del mensaje enviado, que
    es con lo que despues se casan los acuses de entrega.

    Levanta ErrorWhatsApp con el motivo legible -- ver la nota sobre la ventana
    de 24 h en el encabezado. Quien llama decide si eso se le muestra a un
    agente (si, en la bandeja) o solo se registra (en el turno del bot, donde
    no hay nadie mirando).
    """
    if not texto or not texto.strip():
        raise ErrorWhatsApp("No se envia un mensaje vacio.")

    cfg = _cfg(config)
    emisor = _secreto(tenant, cfg.phone_number_id_ref,
                      "del numero emisor (phone_number_id_ref)")
    respuesta = _post(config, tenant, f"{emisor}/messages", {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": para,
        "type": "text",
        # preview_url en False a proposito: una vista previa de enlace la
        # genera Meta trayendo la pagina, y no hace falta para lo que responde
        # el asistente.
        "text": {"preview_url": False, "body": texto},
    })
    mensajes = respuesta.get("messages") or []
    return mensajes[0].get("id") if mensajes else None


def enviar_plantilla(config, tenant: str, para: str, plantilla: str,
                     variables: list[str] | None = None,
                     idioma: str = "es") -> str | None:
    """
    Un mensaje de PLANTILLA, que es la unica forma de escribirle primero a
    alguien o de contestar pasadas las 24 h.

    'plantilla' es la clave declarada en canales.whatsapp.plantillas del
    tenant, no el nombre que tiene en Meta: asi el codigo que avisa de una mora
    dice 'aviso_mora' y cada empresa mapea eso al nombre que registro.

    'variables' llena los {{1}}, {{2}}... del cuerpo, EN ORDEN. Meta rechaza el
    envio si la cantidad no coincide con la plantilla aprobada, y ese error
    llega como un rechazo generico -- por eso se valida antes lo que se puede.

    ⚠️ El texto de una plantilla lo aprueba Meta, no nosotros. Cambiarlo exige
    volver a pasar por su revision (dias). Lo que se puede cambiar sin tramite
    son las variables.
    """
    cfg = _cfg(config)
    nombre_real = cfg.plantillas.get(plantilla)
    if not nombre_real:
        raise ErrorWhatsApp(
            f"La plantilla '{plantilla}' no esta declarada en "
            f"canales.whatsapp.plantillas. Declaradas: "
            f"{', '.join(sorted(cfg.plantillas)) or 'ninguna'}.")

    componentes = []
    if variables:
        componentes.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)} for v in variables],
        })

    emisor = _secreto(tenant, cfg.phone_number_id_ref,
                      "del numero emisor (phone_number_id_ref)")
    respuesta = _post(config, tenant, f"{emisor}/messages", {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": para,
        "type": "template",
        "template": {
            "name": nombre_real,
            "language": {"code": idioma},
            **({"components": componentes} if componentes else {}),
        },
    })
    mensajes = respuesta.get("messages") or []
    return mensajes[0].get("id") if mensajes else None


def plantillas_aprobadas(config, tenant: str) -> list[dict]:
    """
    Que plantillas tiene aprobadas la empresa en Meta, con su estado.

    Sirve para dos cosas que hoy se hacen a ciegas: ver si lo declarado en el
    YAML existe de verdad del otro lado, y saber si una que se mando a aprobar
    ya paso. Necesita el waba_id (el phone_number_id NO sirve aca).
    """
    cfg = _cfg(config)
    waba = _secreto(tenant, cfg.waba_id_ref, "de la cuenta (waba_id_ref)")
    token = _secreto(tenant, cfg.token_ref, "de envio (token_ref)")

    r = requests.get(_url(config, f"{waba}/message_templates"),
                     headers={"Authorization": f"Bearer {token}"},
                     params={"limit": 100}, timeout=TIMEOUT_SEGUNDOS)
    if r.status_code >= 400:
        raise ErrorWhatsApp(
            f"No se pudieron leer las plantillas: {r.status_code} {r.text[:200]}")

    return [{"nombre": p.get("name"), "estado": p.get("status"),
             "idioma": p.get("language"), "categoria": p.get("category")}
            for p in (r.json().get("data") or [])]


# =============================================================================
#  MULTIMEDIA  -  bajar lo que mando el cliente
# =============================================================================
#  Para un ISP la foto de las luces del router es EL caso de soporte: dice en un
#  segundo lo que al cliente le cuesta tres mensajes explicar.
#
#  Son DOS pasos, no uno: Meta no entrega el archivo en el webhook, solo un id.
#  Con ese id se pide la ficha (que trae una URL firmada y temporal) y recien
#  ahi se descarga -- y esa segunda descarga TAMBIEN necesita el token, aunque
#  la URL ya venga firmada. Es el error mas facil de cometer aca.

# Un telefono moderno manda fotos de varios MB. Se rechaza antes de bajar lo que
# no vamos a poder guardar, en vez de descargarlo para descartarlo despues.
MAX_BYTES_DESCARGA = 16 * 1024 * 1024


def descargar_media(config, tenant: str, media_id: str) -> tuple[bytes, str]:
    """
    Devuelve (bytes, mime) del archivo que mando el cliente.

    Levanta ErrorWhatsApp si no se puede: quien llama decide si eso corta el
    turno (no, nunca) o solo deja al mensaje sin adjunto.
    """
    token = _secreto(tenant, _cfg(config).token_ref, "de envio (token_ref)")
    cabeceras = {"Authorization": f"Bearer {token}"}

    ficha = requests.get(_url(config, media_id), headers=cabeceras,
                         timeout=TIMEOUT_SEGUNDOS)
    if ficha.status_code >= 400:
        raise ErrorWhatsApp(
            f"No se pudo consultar el archivo {media_id}: {ficha.status_code}")
    datos = ficha.json()
    url = datos.get("url")
    if not url:
        raise ErrorWhatsApp(f"La ficha del archivo {media_id} no trae 'url'.")

    tamano = int(datos.get("file_size") or 0)
    if tamano > MAX_BYTES_DESCARGA:
        raise ErrorWhatsApp(
            f"El archivo pesa {tamano // 1024} KB, mas del maximo aceptado.")

    # La URL viene firmada y aun asi exige el token. Sin esta cabecera Meta
    # devuelve 401 y parece que la URL estuviera vencida.
    archivo = requests.get(url, headers=cabeceras, timeout=TIMEOUT_SEGUNDOS,
                           stream=True)
    if archivo.status_code >= 400:
        raise ErrorWhatsApp(
            f"No se pudo descargar el archivo {media_id}: {archivo.status_code}")

    contenido = archivo.content
    if len(contenido) > MAX_BYTES_DESCARGA:
        raise ErrorWhatsApp("El archivo descargado supera el maximo aceptado.")

    return contenido, datos.get("mime_type") or archivo.headers.get("Content-Type", "")


def marcar_leido(config, tenant: str, wamid: str) -> None:
    """
    El doble tilde azul. Es cosmetico pero no gratuito en percepcion: sin esto
    el cliente no tiene ninguna señal de que su mensaje llego mientras el
    modelo piensa.

    Nunca levanta: que falle el acuse no puede impedir que se conteste.
    """
    try:
        cfg = _cfg(config)
        emisor = _secreto(tenant, cfg.phone_number_id_ref,
                          "del numero emisor (phone_number_id_ref)")
        _post(config, tenant, f"{emisor}/messages", {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wamid,
        })
    except Exception as e:
        print(f"[whatsapp] no se pudo marcar leido {wamid}: {type(e).__name__}: {e}")
