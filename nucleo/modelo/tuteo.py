# -*- coding: utf-8 -*-
"""
Normaliza el tratamiento del texto que sale hacia el cliente.

POR QUE ESTO EXISTE EN CODIGO Y NO EN EL PROMPT
-----------------------------------------------
Se intento cuatro veces por prompt. La regla llego a estar escrita de la
forma mas explicita posible en la config del tenant -- con la lista de
formas prohibidas, los ejemplos en tuteo, y hasta la advertencia de que
"vale incluso cuando estas dando instrucciones paso a paso, que es donde
mas se escapa" -- y el modelo la desobedecio igual.

El 15/08/2026 se midio el resto de las fuentes posibles, una por una:
prompts de los tres roles de cara al cliente (0 formas), descripciones de
las 27 herramientas (0, despues de limpiarlas ese mismo dia), los 220
fragmentos de la base de conocimiento (0), ejemplos validados y
revisiones del supervisor (0). Con TODO el contexto limpio, la misma
conversacion seguia saliendo con "sos", "tenes", "revisa" con acento
final y "contame". No es una fuga de datos: es el modelo. Y no es
consistente -- la misma configuracion produce tuteo perfecto en una
corrida y voseo en la siguiente, que es la peor forma de fallar, porque
una prueba manual lo da por resuelto.

Es el mismo criterio de PRD 7.4 que ya rige para PII y para las acciones
sensibles: el prompt es guia, el codigo es la garantia.

POR QUE ES CONFIGURABLE Y NO SIEMPRE TUTEO
------------------------------------------
Un ISP argentino o uruguayo va a querer exactamente lo contrario. El
tratamiento es un dato que varia por empresa, asi que se declara en
'persona.normalizar_tratamiento' del tenant y nucleo/ solo aplica lo que
le pidan -- sin conocer a ninguna empresa en particular.

EL ACENTO ES EL QUE DECIDE, Y NO ES UN DETALLE
----------------------------------------------
Casi todo el voseo se distingue del castellano neutro UNICAMENTE por la
tilde final: 'hace' (el equipo hace ruido) vs 'hacé' (imperativo),
'marca' (la marca del router) vs 'marcá', 'pasas' (tuteo, ya correcto)
vs 'pasás'. Por eso la busqueda es sensible a la tilde: comparar sin
tildes convertiria "el equipo hace ruido" en "el equipo haz ruido".

La contra es que una forma de voseo escrita sin su tilde no se detecta.
Es un falso negativo -- se lee raro y ya. El falso positivo, en cambio,
corrompe una palabra correcta en un mensaje a un cliente. Se elige el
error barato.

POR QUE UNA TABLA Y NO UNA REGLA GENERAL
----------------------------------------
La regla general ("toda palabra terminada en -ás/-és/-ís es voseo") es
corta de escribir y rompe 'ademas', 'quizas', 'despues', 'interes',
'ingles', 'pais', 'raiz'. Ademas los verbos que cambian la raiz no la
cumplen ('podés' -> 'puedes', no 'podes').
"""
import re

# Formas que SOLO existen en voseo por llevar tilde final. La clave incluye
# la tilde a proposito -- ver la nota de arriba.
_CON_TILDE: dict[str, str] = {
    # presente, con cambio de raiz
    "podés": "puedes", "tenés": "tienes", "querés": "quieres",
    "venís": "vienes", "decís": "dices", "seguís": "sigues",
    "elegís": "eliges", "preferís": "prefieres", "sentís": "sientes",
    "entendés": "entiendes", "volvés": "vuelves", "dormís": "duermes",
    "pedís": "pides", "contás": "cuentas", "probás": "pruebas",
    "encontrás": "encuentras", "recordás": "recuerdas", "empezás": "empiezas",
    "cerrás": "cierras", "mostrás": "muestras", "perdés": "pierdes",
    # presente regular: solo pierde la tilde
    "necesitás": "necesitas", "sabés": "sabes", "usás": "usas",
    "hacés": "haces", "revisás": "revisas", "mirás": "miras",
    "buscás": "buscas", "esperás": "esperas", "llamás": "llamas",
    "mandás": "mandas", "pasás": "pasas", "tomás": "tomas",
    "dejás": "dejas", "marcás": "marcas", "apagás": "apagas",
    "prendés": "prendes", "conectás": "conectas", "desconectás": "desconectas",
    "reiniciás": "reinicias", "cambiás": "cambias", "verificás": "verificas",
    "confirmás": "confirmas", "intentás": "intentas", "notás": "notas",
    "escuchás": "escuchas", "respondés": "respondes", "conocés": "conoces",
    "creés": "crees", "debés": "debes", "leés": "lees", "comés": "comes",
    "vivís": "vives", "salís": "sales", "escribís": "escribes",
    "abrís": "abres", "recibís": "recibes", "permitís": "permites",
    "estás": "estas",
    # imperativo -- donde mas se escapa, porque un soporte tecnico es casi
    # todo instrucciones ("hacé esto", "revisá aquello")
    "hacé": "haz", "andá": "ve", "mirá": "mira", "probá": "prueba",
    "buscá": "busca", "entrá": "entra", "elegí": "elige", "revisá": "revisa",
    "esperá": "espera", "tomá": "toma", "dejá": "deja", "poné": "pon",
    "sacá": "saca", "apagá": "apaga", "prendé": "prende", "conectá": "conecta",
    "desconectá": "desconecta", "reiniciá": "reinicia", "marcá": "marca",
    "escribí": "escribe", "vení": "ven", "salí": "sal", "abrí": "abre",
    "cerrá": "cierra", "llamá": "llama", "cambiá": "cambia",
    "verificá": "verifica", "confirmá": "confirma", "intentá": "intenta",
    "volvé": "vuelve", "seguí": "sigue", "decí": "di", "anotá": "anota",
    "fijáte": "fijate", "mandá": "manda", "contá": "cuenta",
}

# Formas que no necesitan tilde para ser inequivocas: o no existen fuera del
# voseo ('sos', 'contame'), o son la version sin acentuar de un imperativo
# tuteo ('dejala' -> 'dejala' con tilde), y en ese caso corregirlas tambien
# mejora la ortografia de salida.
_SIN_TILDE: dict[str, str] = {
    "sos": "eres",
    "contame": "cuentame", "decime": "dime", "mostrame": "muestrame",
    "mandame": "mandame", "pasame": "pasame", "avisame": "avisame",
    "decile": "dile", "deciles": "diles", "pedile": "pidele",
    "avisale": "avisale", "fijate": "fijate", "quedate": "quedate",
    "acordate": "acuerdate", "olvidate": "olvidate", "sentate": "sientate",
    "calmate": "calmate", "esperame": "esperame",
    "hacelo": "hazlo", "hacela": "hazla", "ponelo": "ponlo", "ponela": "ponla",
    "dejalo": "dejalo", "dejala": "dejala", "llamalo": "llamalo",
    "llamala": "llamala", "usalo": "usalo", "usala": "usala",
    "sacalo": "sacalo", "sacala": "sacala", "probalo": "pruebalo",
    "probala": "pruebala", "revisalo": "revisalo", "revisala": "revisala",
}

# 'dale' NO entra: en Colombia se usa igual, y ademas es la forma normal de
# 'dar' + 'le' ("dale la clave al cliente"). Cambiarlo romperia frases
# correctas -- justo el falso positivo que esta tabla evita a proposito.

# El pronombre, con preposicion. Va antes que la palabra suelta: 'con vos'
# tiene que volverse 'contigo', no 'con tu'.
_PRONOMBRE_COMPUESTO: list[tuple[str, str]] = [
    ("con vos", "contigo"), ("a vos", "a ti"), ("para vos", "para ti"),
    ("de vos", "de ti"), ("en vos", "en ti"), ("por vos", "por ti"),
    ("sin vos", "sin ti"), ("hacia vos", "hacia ti"),
    ("vos mismo", "tú mismo"), ("vos misma", "tú misma"),
]

# El pronombre lleva tilde: 'tú' (pronombre) no es 'tu' (posesivo).
_TABLA = {**_CON_TILDE, **_SIN_TILDE, "vos": "tú"}
_RE_PALABRA = re.compile(r"\b[a-záéíóúñA-ZÁÉÍÓÚÑ]+\b")


def _con_forma_de(original: str, reemplazo: str) -> str:
    """Conserva mayusculas: 'Sos' -> 'Eres', 'SOS' -> 'ERES'."""
    if len(original) > 1 and original.isupper():
        return reemplazo.upper()
    if original[:1].isupper():
        return reemplazo[:1].upper() + reemplazo[1:]
    return reemplazo


def a_tuteo(texto: str) -> str:
    """
    Devuelve 'texto' en tuteo colombiano. Idempotente: aplicarlo dos veces
    da el mismo resultado (ninguna salida de la tabla es a su vez una clave).
    """
    if not texto:
        return texto

    for voseo, tut in _PRONOMBRE_COMPUESTO:
        texto = re.sub(rf"\b{voseo}\b", tut, texto, flags=re.I)

    def _reemplazar(m: re.Match) -> str:
        palabra = m.group(0)
        destino = _TABLA.get(palabra.lower())
        return palabra if destino is None else _con_forma_de(palabra, destino)

    return _RE_PALABRA.sub(_reemplazar, texto)


# Tratamiento declarado en la config -> funcion que lo aplica. Hoy solo 'tu':
# es el unico que se necesito y el unico que esta probado. Agregar 'usted' o
# 'vos' es escribir su tabla y sumarlo aca. El validador de la config rechaza
# cualquier valor que no este en este diccionario, asi que ningun tenant puede
# declarar un tratamiento que en realidad no se aplicaria.
NORMALIZADORES = {"tu": a_tuteo}
