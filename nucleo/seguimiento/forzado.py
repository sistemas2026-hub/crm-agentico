# -*- coding: utf-8 -*-
"""
================================================================================
 ESCALADA POR HECHO  --  la que no decide el modelo
================================================================================

Modulo propio y sin dependencias a proposito: 'api.py' arrastra la base y el
motor entero, y esto tiene que poder comprobarse sin levantar nada. Es la
unica forma de que este camino tenga guarda -- el corredor de casos dorados
llama a motor.responder() y nunca pasa por la escalada (cero menciones de
escalamiento en cli/evaluar.py), asi que un fallo aca no lo ve nadie.

Ver tests/test_escalada_forzada.py y el bug que lo motivo.
"""

from __future__ import annotations


def _plano(texto: str) -> str:
    """
    Minusculas, sin tildes, sin puntuacion y con un solo espacio entre
    palabras.

    La puntuacion se saca porque parte las frases donde nadie lo espera:
    "pasame, con una persona" no contenia "pasame con" y se escapaba.
    """
    import re
    import unicodedata
    plano = unicodedata.normalize("NFD", (texto or "").lower())
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", plano).split())


# Como se pide una persona en español, y no en Rapilink: la ESTRUCTURA es del
# idioma --un verbo de contacto y un sustantivo de persona-- y por eso vive en
# el motor. El vocabulario propio de cada empresa ('ejecutivo', 'call center')
# se agrega aparte, en 'escalamiento.frases_pide_humano'.
#
# Medido el 02/09/2026 sobre 22 formas legitimas y 15 que no deben disparar:
# con la lista de frases sola se detectaban 11 de 22 y se colaban 4 falsos
# positivos; con estos patrones, 18 de 22 y ninguno.
_PERSONA = (r"(persona|humano|asesor|tecnico|agente|operador|supervisor|"
            r"ejecutivo|representante|encargado)")
_CONTACTO = (r"(hablar|comunicar|comunicarme|comunicame|comuniqueme|comunican|"
             r"comuniquen|comunique|pasar|pasarme|pasame|pasenme|paseme|pasas|"
             r"transferir|transferirme|transfieran|poner|ponerme|ponme|poneme|"
             r"derivar|derivarme|deriveme)")
_ARTICULO = r"(un|una|el|la|algun|alguna|otro|otra|algien)?"

_PATRONES_PIDE_HUMANO = (
    # "pasame con una persona", "hablar con alguien", "comunicame con un asesor"
    rf"\b{_CONTACTO}\b(?:\s+\w+){{0,3}}?\s+con\s+{_ARTICULO}\s*({_PERSONA}|alguien)\b",
    # "que me atienda un humano", "atiendame una persona"
    rf"\batien(da|dan|dame|derme|der)\b(?:\s+\w+){{0,2}}?\s*{_ARTICULO}\s*({_PERSONA}|alguien)\b",
    # "quiero un asesor", "necesito una persona" -- con articulo a proposito:
    # "necesito que alguien me ayude" NO es esto, es una intencion ambigua.
    rf"\b(quiero|necesito|requiero|deme|dame|quisiera)\s+(un|una)\s+{_PERSONA}\b",
    # "que me llame un tecnico"
    rf"\b(llame|llamen|llamarme|llamar)\b(?:\s+\w+){{0,2}}?\s*{_ARTICULO}\s*{_PERSONA}\b",
    # formas hechas
    r"\b(soporte|atencion|servicio)\s+(humano|humana|de\s+verdad|real)\b",
    r"\b(persona|humano)\s+(real|de\s+verdad)\b",
    r"\bser\s+humano\b",
)

# "no quiero hablar con un bot" SI es pedir una persona, aunque empiece con un
# "no": lo negado es el bot, no la persona. Se mira antes que la guarda de
# negacion, que si no lo descartaria.
_ANTI_BOT = r"\b(bot|robot|chatbot|maquina|grabacion|contestadora)\b"

# Negar el pedido no es hacerlo: "no quiero hablar con una persona" y
# "prefiero no hablar con un asesor" decian lo contrario y disparaban igual.
_NIEGA = r"\b(no|nunca|sin|tampoco|prefiero\s+no)\b"

# Pero un "no" cerca NO alcanza para descartar: en "esto no sirve, pasame con
# un asesor" el "no" niega otra cosa, y el pedido es real. Se buscaba dentro
# de los 22 caracteres anteriores y se perdia justo el cliente mas molesto,
# que es el que menos conviene perder.
#
# Lo que cuenta es que la negacion GOBIERNE al verbo del pedido: entre el "no"
# y el verbo solo pueden quedar pronombres y verbos de querer. "no quiero" y
# "no me interesa" niegan lo que sigue; "no sirve" cierra su propia frase.
_NIEGA_ANTES = (r"\b(no|nunca|tampoco|jamas)\s+"
                r"((me|te|le|se|nos|les|lo|la)\s+)*"
                r"((quiero|queria|quisiera|deseo|deseaba|necesito|necesitaba|"
                r"pienso|pretendo|interesa|gustaria|gusta|apetece|voy\s+a|"
                r"hace\s+falta|es\s+necesario|hay\s+que|quisieramos)\s+)*$")

# Contarlo en pasado tampoco es pedirlo: "ayer hable con un asesor", "el mes
# pasado vino un tecnico".
_PASADO = (rf"\b(hable|hablo|hablamos|vino|vinieron|atendio|atendieron|llamo|"
           rf"llamaron|converse|converso)\b(?:\s+\w+){{0,2}}?\s*(con\s+)?"
           rf"{_ARTICULO}\s*{_PERSONA}\b")


def _sin_tildes(texto: str) -> str:
    """Compatibilidad: se conserva el nombre viejo, que usa otro modulo."""
    return _plano(texto)


def pidio_hablar_con_humano(historial: list[dict], frases: list[str] | None) -> str | None:
    """
    La frase con la que EL CLIENTE pidio hablar con una persona, o None.

    Mira SOLO los mensajes del cliente ('role' == 'user'). Es la mitad que
    faltaba: el evaluador lee la conversacion entera, donde tambien estan lo
    que dijo el asistente y las herramientas que corrio, y eso lo confunde.

    Paso el 02/09/2026 con "hola, cual es mi plan? cedula 000021". El
    asistente derivo a otro agente interno y se lo narro al cliente como "te
    paso con un compañero del equipo"; el evaluador leyo ESA frase --suya, no
    del cliente-- y clasifico la conversacion como una solicitud explicita de
    hablar con una persona. Se abrio un caso que nadie pidio.

    Un traspaso anunciado por el asistente, o una herramienta de derivacion
    interna en la traza, NO son evidencia de que el cliente haya pedido nada.
    Por eso esto vive aca, junto a lo demas que se decide mirando hechos de la
    conversacion y no interpretandola.

    Sin frases declaradas devuelve None: el llamador decide que hacer con eso
    (hoy, no exigir evidencia -- ver api.py).
    """
    for mensaje in historial or []:
        if mensaje.get("role") != "user":
            continue
        encontrado = _pide_humano_en(mensaje.get("content", ""), frases)
        if encontrado:
            return encontrado
    return None


def _pide_humano_en(texto: str, frases: list[str] | None) -> str | None:
    """Lo mismo, sobre UN mensaje. Patrones del idioma + frases del tenant."""
    import re

    dicho = _plano(texto)
    if not dicho:
        return None

    # Primero el anti-bot: "no quiero hablar con un bot" pide una persona
    # aunque empiece con un "no", y la guarda de negacion lo descartaria.
    if re.search(_ANTI_BOT, dicho) and re.search(_NIEGA, dicho):
        return "rechaza el bot"

    if re.search(_PASADO, dicho):
        return None

    for patron in _PATRONES_PIDE_HUMANO:
        m = re.search(patron, dicho)
        if not m:
            continue
        # Lo que hay JUSTO antes decide si lo esta pidiendo o negando.
        if re.search(_NIEGA_ANTES, dicho[:m.start()]):
            continue
        return m.group(0)

    # Y el vocabulario que agrego la empresa, que el motor no puede adivinar.
    for frase in frases or []:
        limpia = _plano(str(frase))
        if limpia and limpia in dicho:
            if re.search(_NIEGA_ANTES, dicho[:dicho.index(limpia)]):
                continue
            return frase
    return None


# ============================================================================
#  Los tres niveles de "quiero una persona"
# ============================================================================
#
# Entre "pasame con un asesor" y "cual es mi plan" hay una franja enorme que
# no es ninguna de las dos: "esto no me lo estas solucionando", "ya estoy
# cansado". Tratarla como un pedido abre casos que nadie pidio; tratarla como
# una consulta cualquiera deja al cliente golpeando una pared.
#
# Ni una cosa ni la otra: se PREGUNTA. Y lo que decide es la respuesta del
# cliente, no la lectura que el modelo haga de su enojo.
#
#   PIDE_HUMANO  lo dijo claro                    -> escala, no se pregunta
#   PREGUNTAR    hay intencion, no pedido         -> se le pregunta (una vez)
#   CONFIRMA     se le pregunto y dijo que si     -> escala
#   RECHAZA      se le pregunto y dijo que no     -> sigue el asistente
#   (None)       ni lo pidio ni lo insinuo, o contesto algo que no es ni si
#                ni no ("bueno...", "como quieras") -> no se asume nada
PIDE_HUMANO = "PIDE_HUMANO"
PREGUNTAR = "PREGUNTAR"
CONFIRMA = "CONFIRMA"
RECHAZA = "RECHAZA"

# Intencion ambigua: el cliente expresa que esto no esta funcionando, sin
# nombrar a nadie. NO entra aca una consulta normal ("cual es mi plan") ni el
# reporte de una falla ("no tengo internet"): ahi el asistente todavia tiene
# trabajo que hacer, y preguntarle si quiere una persona lo empuja a una cola
# que no necesita.
_AMBIGUA = (
    # "no me lo estas solucionando", "no me han resuelto", "no me ayudas"
    r"\bno\s+me\s+(?:\w+\s+){0,3}?(solucion|resuelv|resolv|arregl|ayud|"
    r"sirv|atien|responden|contestan|cumpl)\w*",
    # "esto no sirve", "asi no funciona", "nada me funciona", "nadie me ayuda"
    r"\b(esto|eso|asi|nada|nadie|ustedes|el\s+servicio)\s+no\s+"
    r"(?:\w+\s+){0,2}?(sirv|funcion|ayud|solucion|resuelv|responde)\w*",
    r"\bnadie\s+(me\s+)?(ayuda|responde|contesta|soluciona)\w*",
    # "ya estoy cansado", "estoy harto de esto"
    r"\b(ya\s+)?estoy\s+(cansad|hart|aburrid|molest|fastidiad|desesperad|"
    r"indignad|verrac)\w*",
    # "llevo tres dias asi", "llevo todo el dia sin internet"
    r"\bllevo\s+(?:\w+\s+){0,3}?(dia|dias|semana|semanas|mes|meses|hora|horas)\b",
    # "necesito que alguien me ayude" -- pide ayuda humana sin nombrarla, que
    # es exactamente la franja del medio.
    r"\b(necesito|quiero|quisiera|requiero)\s+que\s+alguien\s+me\s+\w+",
)

# Un "si" solo cuenta si ABRE la respuesta: "si, por favor" es un si; "si no
# funciona, avisame" empieza igual y no lo es. Por eso van anclados al
# principio, y cualquier negacion en el mensaje los descarta.
#
# 'bueno' NO esta a proposito: "bueno..." es la duda tipica, no un si.
_AFIRMA = (r"^(si+|sip|claro|dale|obvio|listo|correcto|exacto|afirmativo|"
           r"de\s+una|por\s+favor|porfa|porfavor|hagalo|hazlo|hagale|"
           r"me\s+gustaria|esta\s+bien|ok|oka|okey|vale)\b")

# Y un no explicito. 'como quieras', 'pues no se' no estan: no son un no, son
# una duda -- y una duda no autoriza a abrir un caso ni a cerrar el tema.
_RECHAZA = (r"^(no|nop|nel|negativo|mejor\s+no|todavia\s+no|aun\s+no|"
            r"por\s+ahora\s+no|asi\s+esta\s+bien|asi\s+estoy\s+bien|"
            r"no\s+hace\s+falta|no\s+es\s+necesario)\b")


def intencion_ambigua(texto: str, frases: list[str] | None = None) -> str | None:
    """
    Lo que hace sospechar que el cliente querria una persona, sin haberlo
    pedido. Devuelve el fragmento que lo delata, o None.

    No es lo mismo que 'pidio_hablar_con_humano': esto NO alcanza para
    escalar. Solo alcanza para preguntar.
    """
    import re

    dicho = _plano(texto)
    if not dicho:
        return None
    for patron in _AMBIGUA:
        m = re.search(patron, dicho)
        if m:
            return m.group(0)
    for frase in frases or []:
        limpia = _plano(str(frase))
        if limpia and limpia in dicho:
            return frase
    return None


def respondio_que_si(texto: str, afirmativas: list[str] | None = None,
                     negativas: list[str] | None = None) -> bool | None:
    """
    True si el cliente dijo que si, False si dijo que no, None si contesto
    otra cosa.

    None NO es "no": es "no se sabe". Y la unica lectura segura de "no se
    sabe" es no escalar y no dar el tema por cerrado -- un "bueno..." o un
    "como quieras" no autorizan a abrir un caso a nombre del cliente.
    """
    import re

    dicho = _plano(texto)
    if not dicho:
        return None

    def empieza_con(frases):
        return any(dicho.startswith(_plano(str(f))) for f in frases or [])

    if re.search(_RECHAZA, dicho) or empieza_con(negativas):
        return False
    if re.search(_AFIRMA, dicho) or empieza_con(afirmativas):
        # "si, pero no me sirve" empieza con un si y no lo es. Ante la duda,
        # no se asume que dijo que si.
        return None if re.search(_NIEGA, dicho) else True
    return None


def _ultimo_del_cliente(historial: list[dict]) -> tuple[str, int]:
    """El ultimo mensaje del cliente y su posicion, o ('', -1)."""
    for i in range(len(historial or []) - 1, -1, -1):
        if historial[i].get("role") == "user":
            return (historial[i].get("content") or ""), i
    return "", -1


def _se_lo_pregunto_recien(historial: list[dict], pregunta: str, corte: int) -> bool:
    """
    True si la pregunta esta en el ULTIMO mensaje del asistente anterior al
    mensaje del cliente que se esta leyendo.

    Importa que sea el ultimo: si se le pregunto hace cinco turnos y el
    cliente estuvo hablando de otra cosa, su "si" de ahora contesta a otra
    pregunta -- probablemente a la de cierre.
    """
    for i in range(corte - 1, -1, -1):
        if historial[i].get("role") != "assistant":
            continue
        return pregunta in _plano(historial[i].get("content") or "")
    return False


def veces_que_se_pregunto(historial: list[dict], pregunta: str) -> int:
    """Cuantas veces el asistente ya hizo esa pregunta en la conversacion."""
    plana = _plano(pregunta or "")
    if not plana:
        return 0
    return sum(1 for m in (historial or [])
               if m.get("role") == "assistant"
               and plana in _plano(m.get("content") or ""))


def decidir_pedido_humano(historial: list[dict], pregunta: str = "",
                          frases: list[str] | None = None,
                          ambiguas: list[str] | None = None,
                          afirmativas: list[str] | None = None,
                          negativas: list[str] | None = None,
                          maximo_preguntas: int = 1) -> tuple[str | None, str]:
    """
    (decision, evidencia) sobre si el cliente quiere hablar con una persona.

    Todo lo que mira son mensajes con 'role' == 'user'. Lo que dijo el
    asistente solo se usa para saber si YA se hizo la pregunta -- nunca como
    evidencia de un pedido: ese fue exactamente el bug del 02/09/2026.

    El limite de preguntas es lo que evita el bucle. Sin el, un cliente
    molesto que contesta "bueno..." recibe la misma pregunta en cada turno
    hasta que se va. Se cuenta sobre el historial, no sobre una bandera: es
    un hecho verificable de la conversacion, y asi la decision se puede
    comprobar sin levantar nada.
    """
    historial = historial or []

    # Nivel 1. Lo pidio claro: se escala y no se pregunta nada mas. Mira la
    # conversacion entera -- un pedido de hace tres turnos que nadie atendio
    # sigue siendo un pedido.
    pedido = pidio_hablar_con_humano(historial, frases)
    if pedido:
        return PIDE_HUMANO, pedido

    ultimo, donde = _ultimo_del_cliente(historial)
    if donde < 0:
        return None, ""

    plana = _plano(pregunta or "")
    if not plana:
        return None, ""

    # Nivel 3. Se le pregunto en el turno anterior y esto de ahora es la
    # respuesta.
    if _se_lo_pregunto_recien(historial, plana, donde):
        dijo = respondio_que_si(ultimo, afirmativas, negativas)
        if dijo is True:
            return CONFIRMA, ultimo.strip()
        if dijo is False:
            return RECHAZA, ultimo.strip()
        return None, ""

    # Nivel 2. Ni lo pidio ni se le pregunto: si hay intencion, se pregunta.
    if veces_que_se_pregunto(historial, pregunta) >= max(0, maximo_preguntas):
        return None, ""
    ambigua = intencion_ambigua(ultimo, ambiguas)
    if ambigua:
        return PREGUNTAR, ambigua
    return None, ""


def con_las_manos_vacias(historial: list[dict]) -> bool:
    """
    True si el asistente todavia no ejecuto NINGUNA herramienta en toda la
    conversacion.

    Es un hecho de la traza, no una opinion: los resultados de herramientas
    viajan en el historial como mensajes de rol 'tool'.

    Sirve para frenar una escalada decidida por el modelo cuando no hay nada
    que entregar. Un caso que llega a la bandeja con la traza vacia le pide a
    una persona que empiece de cero -- y el asistente ni siquiera intento lo
    que sabe hacer.

    Hizo falta porque pedirselo al modelo NO alcanzo. El 28/08/2026 se le
    agrego la instruccion de no confundir un tramite con un pedido de hablar
    con alguien; funciono en la prueba y volvio a fallar en produccion tres
    horas despues, con el mismo mensaje y otra conversacion. El prompt es
    guia, la garantia es codigo (PRD 7.4).
    """
    return not any(m.get("role") == "tool" for m in (historial or []))


def motivos_por_hecho(config) -> set[str]:
    """
    Los motivos que NO puede elegir el modelo: los que declara una herramienta
    en 'escalar_al_completar'.

    Un motivo asi significa "una herramienta ya registro el pedido", y eso es
    un hecho de la traza -- mirando el texto no se puede saber. El evaluador
    corre igual en cada turno y ve la misma lista de motivos, asi que si el
    motivo esta en su menu lo va a elegir en cuanto la conversacion SUENE a
    un pedido, que es antes de que el pedido exista.

    Paso el 28/08/2026 con un cambio de clave de WiFi: el asistente le habia
    preguntado al cliente si confirmaba la clave, el evaluador escalo en ese
    mismo turno con 'pedido_para_ejecutar', y la escalada REEMPLAZA la
    respuesta (ver api.py) -- asi que la pregunta nunca le llego. El cliente
    leyo "tu pedido quedo registrado" sin haber confirmado nada, la
    herramienta que valida el pedido nunca corrio, y el caso le decia a quien
    lo tomara que faltaba la confirmacion del cliente.
    """
    motivos = {h.escalar_al_completar for h in (config.herramientas or [])
               if h.escalar_al_completar}
    # Lo mismo vale para el que sale de una comprobacion posterior: "la accion
    # no produjo su efecto" es una medicion, no algo que se pueda juzgar
    # leyendo la conversacion. Si estuviera en el menu, el evaluador lo
    # elegiria en cuanto el cliente dijera que sigue igual -- antes de que
    # nadie haya medido nada.
    motivos |= {h.verificacion.escalar_si_no_confirma
                for h in (config.herramientas or [])
                if getattr(h, "verificacion", None)
                and h.verificacion.escalar_si_no_confirma}
    return motivos


def motivos_que_no_elige_el_modelo(config) -> set[str]:
    """
    Todo lo que el evaluador NO puede elegir: los motivos que decide un hecho
    de la traza (arriba) mas el de "el cliente pidio una persona".

    Ese ultimo se separa a proposito y no se mete dentro de
    'motivos_por_hecho': ese conjunto significa "una herramienta ya registro
    un pedido", y api.py lo usa ademas para sacar el resumen del caso de la
    traza de herramientas. Pedir una persona no deja ninguna traza de
    herramienta -- meterlo ahi le pondria al caso, de resumen, el pedido de
    cualquier otra cosa que hubiera corrido en el mismo turno.

    Por que sale del menu: desde que el codigo lo decide leyendo los mensajes
    del cliente (ver decidir_pedido_humano), dejarselo tambien al evaluador es
    pedir dos veredictos para la misma pregunta. Y el segundo tiene un costo:
    si el evaluador lo elige mal, el candado de api.py cancela la escalada
    entera -- y si en el fondo queria escalar por OTRA razon, esa razon se
    pierde. Sin el motivo en el menu, tiene que nombrar la razon de verdad.
    """
    motivos = motivos_por_hecho(config)
    if config.escalamiento.motivo_pide_humano:
        motivos = motivos | {config.escalamiento.motivo_pide_humano}
    return motivos


# Codigos que 'motor.py' pone en 'codigo_error' cuando el MOTOR impidio la
# llamada -- no cuando la herramienta la intento y no pudo. 'escalar_si_falla'
# solo tiene sentido para lo segundo: una guardia interna funcionando como
# debe no es una herramienta fallada, y no puede forzar una escalada.
#
# Encontrado en la auditoria de Fase #2 (02/09/2026), sobre un caso real y no
# hipotetico: 'reiniciar_ont' declara 'escalar_si_falla' Y 'exige_previas', y
# el propio codigo documenta que el modelo SI intenta llamarla antes de que
# 'consultar_senal_ont'/'ping_cliente' hayan corrido en la conversacion ("un
# texto en el prompt no alcanzo -- probado en vivo, agosto 2026"). Ese intento
# prematuro cae en la misma traza que un reintento exitoso, en el MISMO turno
# (motor.py corre varias iteraciones del bucle de herramientas por turno) --
# sin este filtro, el primer intento (rechazado a proposito, correctamente)
# forzaba la escalada aunque el segundo, dos entradas mas abajo en la misma
# traza, hubiera reiniciado el equipo de verdad.
#
# 'IDENTIDAD_NO_VERIFICADA' NO esta en esta lista porque no hace falta: motor.py
# ya la excluye de 'registro' antes de que exista la fila de traza (es el gate
# de seguridad frenando ANTES de llamar a nada), asi que escalada_forzada()
# nunca llega a verla.
CODIGOS_MOTOR_GUARD = frozenset({
    "PRECONDICION_NO_CUMPLIDA",
    "LIMITE_DE_CONVERSACION",
    "FALTA_HABLAR_CON_EL_CLIENTE",
    "IDENTIDAD_NO_RESUELTA",
    "HERRAMIENTA_DESCONOCIDA",
})

# Distinto de CODIGOS_MOTOR_GUARD a proposito, aunque a los ojos de
# escalada_forzada() se traten igual (se saltan, ni fallo ni exito): un
# MOTOR_GUARD es el motor IMPIDIENDO la llamada; esto es la herramienta
# CORRIENDO BIEN y devolviendo una condicion de NEGOCIO que no esta lista
# para que una persona la ejecute todavia. Separarlos evita mezclar dos
# cosas distintas bajo el mismo nombre, y evita que este codigo nuevo
# altere la cuenta de 5 que ya afirma un test existente sobre
# CODIGOS_MOTOR_GUARD.
#
# 'PEDIDO_INVALIDO': lo pone motor.py (ver _codigo_error_de_pedido_wifi)
# cuando 'registrar_pedido_wifi' (Herramienta.valida_pedido_wifi, ver
# nucleo/herramientas/wifi.py) marca un SSID/clave que no cumple las
# reglas del estandar. Sin este codigo, 'escalar_al_completar' disparaba
# igual -- el motor solo mira si hubo excepcion, nunca si el DATO en si es
# valido -- y el cliente escuchaba "tu pedido quedo registrado" sobre algo
# que nadie puede aplicar. Encontrado y reproducido en la auditoria de
# Fase #6/#6.1 (03/09/2026).
CODIGOS_CONDICION_DE_NEGOCIO = frozenset({
    "PEDIDO_INVALIDO",
})


def _superado_mas_adelante(registro: list[dict], indice: int, nombre_herramienta: str) -> bool:
    """
    True si, mas ADELANTE en la MISMA traza (mismo turno), la MISMA
    herramienta volvio a ejecutarse y esta vez salio bien (sin codigo_error).

    Encontrado en la auditoria de Fase #5 (03/09/2026): 'reiniciar_ont' puede
    fallar con un error real (ConnectionError, timeout, HTTP 500) sin gastar
    su 'limite_por_conversacion' -- motor.py::_veces_ejecutada() no cuenta un
    intento que termino en error, justamente para no gastarle al cliente su
    unica oportunidad por un fallo que no le paso nada. Eso deja abierta la
    puerta a un reintento real, en el MISMO turno, que esta vez SI funciona.
    Sin este chequeo, escalada_forzada() encontraba el primer fallo de la
    traza y escalaba, ignorando que la misma herramienta, mas abajo en esa
    misma lista, ya habia reiniciado el equipo de verdad y lo habia dejado en
    VERIFICACION_PENDIENTE.

    Solo mira hacia ADELANTE (indices > 'indice'): un exito ANTERIOR no
    'perdona' un fallo real que viene DESPUES -- ese fallo posterior es el
    estado mas reciente de la accion, y sigue siendo motivo real de escalar.
    Ver el caso inverso en tests/test_escalada_forzada.py.

    Una guardia del motor (CODIGOS_MOTOR_GUARD) en una entrada posterior no
    cuenta como el exito que supera al fallo: esa entrada SI trae
    codigo_error (aunque sea uno que el motor ya filtra en el bucle de
    arriba), asi que 'not codigo_error' da False y no la toma como superacion
    -- una guardia no es un reintento exitoso, es el motor sin llamar a nada.
    """
    return any(siguiente.get("herramienta") == nombre_herramienta
              and not siguiente.get("codigo_error")
              for siguiente in registro[indice + 1:])


def escalada_forzada(config, registro_herramientas: list[dict]) -> tuple[str | None, str]:
    """
    (motivo, por_que) cuando una herramienta OBLIGA a escalar, o (None, "").

    Escalamiento POR HECHO, no por juicio: no le pregunta al modelo. Vive
    aparte de chat() para poder comprobarlo sin levantar nada -- la unica
    forma de que este camino tenga guarda, porque el corredor de casos
    dorados llama a motor.responder() y nunca pasa por aca (cero menciones de
    escalamiento en cli/evaluar.py). Ese hueco dejo pasar un bug real: el
    flujo de WiFi recogia el pedido y no se lo entregaba a nadie, con los 5
    casos dorados en verde.

    Gana la primera herramienta de la traza que lo pida, y un fallo tiene
    prioridad sobre un exito dentro de la misma llamada -- salvo que ese
    'fallo' sea en realidad una guardia del motor (CODIGOS_MOTOR_GUARD) o una
    condicion de negocio (CODIGOS_CONDICION_DE_NEGOCIO): esa entrada se
    salta entera, ni cuenta como fallo para 'escalar_si_falla' ni como exito
    para 'escalar_al_completar', porque no es ninguna de las dos cosas -- es
    el motor decidiendo no llamar a nada, o la herramienta devolviendo un
    dato que todavia no esta listo para que una persona lo ejecute. Y salvo
    tambien que esa MISMA herramienta, mas adelante en la MISMA traza, haya
    vuelto a ejecutarse y esta vez salido bien de verdad -- ver
    '_superado_mas_adelante': un fallo real no pesa mas que el resultado
    definitivo de la accion en este turno (Fase #5.1, 03/09/2026).

    La razon nombra a la herramienta porque termina siendo el RESUMEN del
    caso cuando el evaluador no dejo uno (ver api.py): sin el nombre, quien
    abre el caso lee una frase que podria ser de cualquier conversacion.
    """
    por_nombre = {h.nombre: h for h in config.herramientas}
    registro = registro_herramientas or []
    for i, llamada in enumerate(registro):
        herr = por_nombre.get(llamada.get("herramienta"))
        if herr is None:
            continue
        codigo = llamada.get("codigo_error")
        if codigo and (codigo in CODIGOS_MOTOR_GUARD
                       or codigo in CODIGOS_CONDICION_DE_NEGOCIO):
            continue
        if codigo:
            if herr.escalar_si_falla and not _superado_mas_adelante(
                    registro, i, llamada.get("herramienta")):
                return (herr.escalar_si_falla,
                        f"'{herr.nombre}' no pudo ejecutarse")
        # El espejo: la herramienta SALIO BIEN y su exito es, justamente, un
        # pedido que tiene que ejecutar una persona. Ver schema.py.
        elif herr.escalar_al_completar:
            return (herr.escalar_al_completar,
                    f"'{herr.nombre}' se completo y lo que registro tiene "
                    f"que aplicarlo una persona")
    return None, ""
