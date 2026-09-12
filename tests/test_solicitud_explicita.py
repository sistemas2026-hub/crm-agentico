# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA -- "pidio una persona" lo dice el cliente, no el asistente
================================================================================

    py -3.13 tests/test_solicitud_explicita.py

POR QUE EXISTE
--------------
El 02/09/2026 un cliente escribio:

    "hola, cual es mi plan? cedula 000021"

El asistente derivo la charla a otro agente INTERNO y se lo narro como "te
paso con un compañero del equipo". El evaluador leyo la conversacion entera
--incluida esa frase, que era del asistente-- y la clasifico como
'solicitud_explicita'. Se abrio un caso que nadie pidio.

DOS CAUSAS, Y NINGUNA ES QUE EL MODELO SEA TONTO
------------------------------------------------
1. El evaluador elige el motivo de una lista de nombres pelados, sin ninguna
   definicion. Y en español "solicitud explicita" se lee como "pidio algo
   explicitamente" -- que es lo que hace cualquiera al escribir.
2. Lee la transcripcion completa, donde estan sus propias frases y las
   herramientas que corrio. Una derivacion interna se le parece a un traspaso.

LOS TRES NIVELES
----------------
Arreglar solo el falso positivo dejaba el problema del otro lado: entre
"pasame con un asesor" y "cual es mi plan" hay una franja enorme que no es
ninguna de las dos.

  1. Lo pide claro          -> escala, y no se le pregunta nada mas.
  2. Se le nota, no lo pide -> se le PREGUNTA (una vez, y el limite lo pone
                               el codigo: sin el, un "bueno..." trae la misma
                               pregunta en cada turno hasta que el cliente se
                               va).
  3. Contesta               -> "si" escala; "no" sigue el asistente; cualquier
                               otra cosa NO se lee como un si.

Lo que este archivo guarda es la parte que NO depende del prompt: que la
evidencia salga siempre de un mensaje del cliente, y que las tres decisiones
se puedan comprobar sin levantar nada.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import cargar_config                   # noqa: E402
from nucleo.seguimiento.forzado import (                         # noqa: E402
    pidio_hablar_con_humano, decidir_pedido_humano, respondio_que_si,
    intencion_ambigua, veces_que_se_pregunto, motivos_por_hecho,
    motivos_que_no_elige_el_modelo,
    PIDE_HUMANO, PREGUNTAR, CONFIRMA, RECHAZA)

_fallas = []


def afirmar(condicion, que):
    print(("  [ok]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        _fallas.append(que)


CONFIG = cargar_config("tenants/rapilink.config.yaml")
ESC = CONFIG.escalamiento
FRASES = ESC.frases_pide_humano
PREGUNTA = ESC.pregunta_pide_humano


def pidio(*turnos):
    """turnos: ('user'|'assistant'|'tool'|'system', texto)"""
    historial = [{"role": rol, "content": texto} for rol, texto in turnos]
    return pidio_hablar_con_humano(historial, FRASES)


def decidir(*turnos, maximo=None):
    historial = [{"role": rol, "content": texto} for rol, texto in turnos]
    return decidir_pedido_humano(
        historial, PREGUNTA, frases=FRASES,
        ambiguas=ESC.frases_intencion_ambigua,
        afirmativas=ESC.frases_afirmativas,
        negativas=ESC.frases_negativas,
        maximo_preguntas=(ESC.maximo_preguntas_pide_humano
                          if maximo is None else maximo))[0]


print(__doc__.split("POR QUE EXISTE")[0])
print("=" * 70)
print(" NIVEL 1 -- ¿EL CLIENTE PIDIO HABLAR CON UNA PERSONA?")
print("=" * 70)

print()
print("A -- pregunta por su plan")
afirmar(pidio(("user", "hola, cual es mi plan? cedula 000021")) is None,
        "'¿cual es mi plan?' NO es pedir una persona")

print()
print("B -- pide una persona")
afirmar(pidio(("user", "Quiero hablar con una persona.")) is not None,
        "'quiero hablar con una persona' SI lo es")

print()
print("C -- pide ayuda tecnica")
afirmar(pidio(("user", "No tengo internet, ayudame.")) is None,
        "pedir ayuda no es pedir una persona")

print()
print("D -- el ASISTENTE ofrece un humano y el cliente nunca lo pidio")
# El caso exacto del 02/09.
afirmar(pidio(("user", "hola, cual es mi plan? cedula 000021"),
              ("assistant", "Claro, te paso con un compañero del equipo. "
                            "Ya tiene el contexto de lo que venimos hablando.")) is None,
        "lo que ofrece el asistente NO cuenta como pedido del cliente")

print()
print("E -- derivacion interna en la traza")
afirmar(pidio(("user", "no me anda el internet"),
              ("tool", '{"ok": true, "area": "soporte_tecnico_cliente", '
                       '"instruccion_interna": "Listo, la atiende soporte"}'),
              ("system", "(Nota del sistema) Ya estas atendiendo esta area.")) is None,
        "derivar_a_area en la traza NO es evidencia de nada")

print()
print("F -- primero pregunta y despues SI lo pide")
afirmar(pidio(("user", "cuanto debo este mes?"),
              ("assistant", "Tu saldo es 0. ¿Algo mas?"),
              ("user", "Mejor pasame con una persona.")) is not None,
        "se detecta aunque llegue varios turnos despues")

print()
print("G -- cliente frustrado, sin pedir una persona")
afirmar(pidio(("user", "Esto no sirve, llevo todo el dia con problemas.")) is None,
        "la frustracion no es un pedido -- para eso esta el nivel 2")

print()
print("H -- conversacion normal que resuelve el asistente")
afirmar(pidio(("user", "hola"),
              ("assistant", "¡Hola! ¿En que te ayudo?"),
              ("user", "queria saber mi fecha de corte"),
              ("assistant", "Tu fecha de corte es el 6.")) is None,
        "una conversacion resuelta no deja evidencia de pedido")

print()
print("I -- pide un tecnico")
afirmar(pidio(("user", "Necesito hablar con un técnico.")) is not None,
        "'hablar con un técnico' SI lo es, con tilde incluida")

print()
print("J -- pide ayuda para revisar su internet")
afirmar(pidio(("user", "¿Me puedes ayudar a revisar mi internet?")) is None,
        "pedir que lo ayuden a revisar NO es pedir una persona")

print()
print("los otros ejemplos negativos del pedido")
for texto in ("Ayúdame", "¿Cuánto debo?", "Necesito cambiar mi clave",
              "No entiendo", "Estoy molesto", "Quiero solucionar mi problema"):
    afirmar(pidio(("user", texto)) is None, f"{texto!r} no lo es")

print()
print("y los otros positivos")
for texto in ("Pásame con un asesor", "Necesito que me atienda un humano",
              "Comunícame con alguien del equipo",
              "no quiero hablar con un bot, quiero una persona de verdad"):
    afirmar(pidio(("user", texto)) is not None, f"{texto!r} si lo es")

print()
print("negado o en pasado NO es pedirlo")
# Los cuatro falsos positivos que dejaba la comparacion por frases sueltas.
for texto in ("no quiero hablar con una persona, prefiero que lo resuelvas vos",
              "ayer hablé con un asesor y me dijo que ya estaba arreglado",
              "mi vecino habló con un técnico y le cambiaron el equipo",
              "prefiero no hablar con un asesor todavía"):
    afirmar(pidio(("user", texto)) is None, f"{texto!r} no lo es")

print()
print("=" * 70)
print(" NIVEL 2 -- SE LE NOTA Y NO LO PIDE: SE PREGUNTA")
print("=" * 70)

print()
print("K -- 'esto no me lo estas solucionando'")
afirmar(decidir(("user", "Esto no me lo estás solucionando")) == PREGUNTAR,
        "no escala: se le pregunta")
afirmar(pidio(("user", "Esto no me lo estás solucionando")) is None,
        "y sigue sin ser una solicitud explicita")

print()
print("L -- 'ya estoy cansado'")
afirmar(decidir(("user", "Ya estoy cansado")) == PREGUNTAR,
        "el cansancio abre la pregunta, no el caso")

print()
print("M -- 'no me ayudas'")
afirmar(decidir(("user", "No me ayudas")) == PREGUNTAR, "se le pregunta")

print()
print("N -- 'esto no sirve'")
afirmar(decidir(("user", "Esto no sirve")) == PREGUNTAR, "se le pregunta")

print()
print("O -- 'necesito que alguien me ayude'")
afirmar(decidir(("user", "Necesito que alguien me ayude")) == PREGUNTAR,
        "pide ayuda humana sin nombrarla: se le pregunta, no se decide por el")

print()
print("P -- una consulta normal NO abre la pregunta")
for texto in ("¿cuál es mi plan?", "no tengo internet",
              "no entiendo", "¿cuándo me vencen las facturas?",
              "quiero cambiar la clave del wifi"):
    afirmar(decidir(("user", texto)) is None,
            f"{texto!r} se atiende, no se le ofrece una persona")

print()
print("y un pedido claro NO pasa por la pregunta")
afirmar(decidir(("user", "esto no sirve, pásame con un asesor")) == PIDE_HUMANO,
        "si ya lo pidio, preguntarselo seria hacerlo repetir")

print()
print("=" * 70)
print(" NIVEL 3 -- CONTESTA LA PREGUNTA")
print("=" * 70)


def respondio(texto):
    """La conversacion donde se le pregunto y el cliente contesta 'texto'."""
    return decidir(("user", "Esto no sirve"),
                   ("assistant", f"Déjame revisarlo.\n\n{PREGUNTA}"),
                   ("user", texto))


print()
print("Q -- dice que si")
afirmar(respondio("Sí") == CONFIRMA, "'Sí' escala")

print()
print("R -- las otras formas del si")
for texto in ("Sí por favor", "Claro", "sí, hágalo", "dale", "listo pues"):
    afirmar(respondio(texto) == CONFIRMA, f"{texto!r} escala")

print()
print("S -- dice que no")
for texto in ("No", "No gracias", "no hace falta", "así está bien",
              "dejalo así", "No, prefiero seguir contigo"):
    afirmar(respondio(texto) == RECHAZA, f"{texto!r} NO escala")

print()
print("T -- contesta algo que no es ni si ni no")
# El corazon del nivel 3: "no se sabe" no es "si". Asumirlo abre un caso a
# nombre de un cliente que no lo pidio -- el mismo error del 02/09, por otra
# puerta.
for texto in ("Bueno...", "Pues no sé", "Como quieras", "mmm", "ok pero no ya"):
    afirmar(respondio(texto) is None, f"{texto!r} no se lee como un si")

print()
print("U -- no se pregunta dos veces (el bucle)")
ya_pregunto = (("user", "Esto no sirve"),
               ("assistant", f"Déjame revisarlo.\n\n{PREGUNTA}"),
               ("user", "Bueno..."),
               ("assistant", "Reviso tu equipo y te cuento."),
               ("user", "Ya estoy cansado de esto"))
afirmar(decidir(*ya_pregunto) is None,
        "con la pregunta ya hecha, la misma intencion no la repite")
afirmar(veces_que_se_pregunto(
    [{"role": r, "content": t} for r, t in ya_pregunto], PREGUNTA) == 1,
    "y el limite se cuenta sobre el historial, no sobre una bandera")
afirmar(decidir(*ya_pregunto, maximo=2) == PREGUNTAR,
        "un tenant que quiera dos preguntas las tiene: el limite es config")
afirmar(decidir(("user", "Esto no sirve"), maximo=0) is None,
        "y con el limite en 0 no se pregunta nunca")

print()
print("V -- solo el cliente es evidencia, tambien en la respuesta")
afirmar(decidir(("user", "Esto no sirve"),
                ("assistant", f"Déjame revisarlo.\n\n{PREGUNTA}"),
                ("assistant", "Sí, claro, ya te comunico.")) is None,
        "un 'si' del propio asistente no confirma nada")
afirmar(decidir(("user", "Esto no sirve"),
                ("assistant", f"Déjame revisarlo.\n\n{PREGUNTA}"),
                ("tool", '{"ok": true, "respuesta": "si"}')) is None,
        "ni el resultado de una herramienta")
afirmar(decidir(("user", "hola"),
                ("assistant", "¡Hola! ¿En qué te ayudo?"),
                ("user", "Sí")) is None,
        "un 'si' suelto sin la pregunta delante no escala nada")
# Se le pregunto hace rato y estuvo hablando de otra cosa: su "si" de ahora
# le contesta a la ultima pregunta que le hicieron, no a esta.
afirmar(decidir(("user", "Esto no sirve"),
                ("assistant", f"Déjame revisarlo.\n\n{PREGUNTA}"),
                ("user", "no, deja así"),
                ("assistant", "Listo. ¿Te ayudo con algo más?"),
                ("user", "Sí")) is None,
        "un 'si' cuatro turnos despues no reabre la pregunta vieja")

print()
print("las piezas sueltas")
afirmar(respondio_que_si("sí") is True, "respondio_que_si distingue el si")
afirmar(respondio_que_si("no") is False, "y el no")
afirmar(respondio_que_si("como quieras") is None,
        "y devuelve None --no False-- cuando no se sabe: son cosas distintas")
afirmar(respondio_que_si("") is None, "un texto vacio no explota")
afirmar(intencion_ambigua("cual es mi plan") is None,
        "una consulta no tiene intencion ambigua")
afirmar(intencion_ambigua("ya estoy harto de esto") is not None,
        "una queja si")
afirmar(decidir_pedido_humano([], PREGUNTA)[0] is None,
        "un historial vacio no explota")
afirmar(decidir_pedido_humano(None, PREGUNTA)[0] is None, "ni uno None")
afirmar(decidir_pedido_humano(
    [{"role": "user", "content": "esto no sirve"}], "")[0] is None,
    "sin pregunta declarada no se pregunta: nadie lo estrena sin pedirlo")

print()
print("=" * 70)
print(" LA MEDICION -- 22 formas legitimas, 15 que no deben disparar")
print("=" * 70)

LEGITIMAS = [
    "Quiero hablar con una persona",
    "Pásame con un asesor",
    "Necesito hablar con un técnico",
    "Comunícame con alguien del equipo",
    "¿Me pueden comunicar con un agente?",
    "quiero hablar con un humano",
    "Ponme con una persona por favor",
    "Necesito que me atienda un humano",
    "Que me atienda una persona real",
    "Pásenme con el supervisor",
    "Quiero un asesor",
    "Necesito una persona que me ayude",
    "Transfiéranme a soporte humano",
    "no quiero hablar con un bot, quiero una persona de verdad",
    "¿Me puedes pasar con alguien?",
    "Quisiera hablar con un representante",
    "Necesito comunicarme con un operador",
    "Que me llame un técnico",
    "Deme un asesor",
    "Quiero atención humana",
    "prefiero hablar con una persona",
    "Quiero que me atienda un asesor",
]

NO_DEBEN = [
    "hola, cual es mi plan? cedula 000021",
    "No tengo internet, ayudame",
    "Esto no sirve, llevo todo el día con problemas",
    "¿Cuánto debo?",
    "Necesito cambiar mi clave",
    "No entiendo",
    "Estoy molesto",
    "Quiero solucionar mi problema",
    "¿Me puedes ayudar a revisar mi internet?",
    "Ayúdame",
    "no quiero hablar con una persona, prefiero que lo resuelvas vos",
    "ayer hablé con un asesor y me dijo que ya estaba arreglado",
    "mi vecino habló con un técnico y le cambiaron el equipo",
    "prefiero no hablar con un asesor todavía",
    "quiero saber cuándo viene el técnico a instalar",
]

# La franja del medio: ni una cosa ni la otra. Que no se cuelen como pedido es
# lo que separa el nivel 2 del nivel 1 -- si se colaran, la pregunta no
# existiria y volveriamos a abrir casos que nadie pidio.
AMBIGUAS = [
    "Esto no me lo estás solucionando",
    "Ya estoy cansado",
    "No me ayudas",
    "Esto no sirve",
    "Necesito que alguien me ayude",
]

detectadas = [t for t in LEGITIMAS if pidio(("user", t))]
falsos = [(t, pidio(("user", t))) for t in NO_DEBEN if pidio(("user", t))]
colados = [(t, pidio(("user", t))) for t in AMBIGUAS if pidio(("user", t))]

print()
print(f"  legitimas detectadas   : {len(detectadas)}/{len(LEGITIMAS)}   (minimo 18)")
print(f"  falsos positivos       : {len(falsos)}/{len(NO_DEBEN)}   (tienen que ser 0)")
print(f"  ambiguas que se cuelan : {len(colados)}/{len(AMBIGUAS)}   (tienen que ser 0)")
print()
for texto in LEGITIMAS:
    if not pidio(("user", texto)):
        print(f"      no detectada  : {texto}")
for texto, frase in falsos + colados:
    print(f"      FALSO POSITIVO: {texto}  ->  {frase!r}")

afirmar(len(detectadas) >= 18, "18 de 22 formas legitimas como minimo")
afirmar(not falsos, "ni un falso positivo en las 15 que no deben disparar")
afirmar(not colados, "y ninguna intencion ambigua se cuela como pedido")
# Los patrones son del idioma y viven en el motor; la lista del tenant es
# vocabulario de la empresa. Si el motor solo ya no alcanzara, el proximo ISP
# tendria que escribir en su YAML como se pide una persona en español.
solo_motor = [t for t in LEGITIMAS
              if pidio_hablar_con_humano([{"role": "user", "content": t}], [])]
print()
print(f"  sin la lista del tenant: {len(solo_motor)}/{len(LEGITIMAS)}")
afirmar(len(solo_motor) >= 18,
        "el motor solo ya reconoce el idioma: la lista del tenant es "
        "vocabulario propio, no la base")

print()
print("=" * 70)
print(" LO QUE DECLARA EL TENANT")
print("=" * 70)
print()
afirmar(ESC.motivo_pide_humano == "solicitud_explicita",
        "el motivo que exige evidencia esta declarado")
afirmar(ESC.motivo_pide_humano in ESC.activar_si,
        "y existe en activar_si, o se exigiria evidencia para algo inalcanzable")
# El motivo lo decide el codigo, asi que el evaluador no lo elige. Aca se fija
# la parte que no necesita levantar nada; el menu que de verdad viaja al
# modelo lo comprueba tests/test_motivos_por_rol.py.
afirmar(ESC.motivo_pide_humano in motivos_que_no_elige_el_modelo(CONFIG),
        "y esta entre los que el evaluador no puede elegir")
afirmar(ESC.motivo_pide_humano not in motivos_por_hecho(CONFIG),
        "pero no entre los de hecho: de ahi sale el resumen del caso, y pedir "
        "una persona no deja traza de ninguna herramienta")
afirmar(bool(PREGUNTA), "la pregunta del nivel 2 esta escrita")
afirmar(ESC.maximo_preguntas_pide_humano >= 1,
        "y tiene un limite de veces, que es el freno del bucle")
afirmar(pidio_hablar_con_humano([{"role": "user", "content": "pasame con alguien"}], [])
        is not None,
        "el motor reconoce el pedido sin depender de la lista del tenant")
afirmar(pidio_hablar_con_humano(None, FRASES) is None, "un historial None no explota")

print()
print("=" * 70)
if _fallas:
    print(f" {len(_fallas)} falla(s):")
    for f in _fallas:
        print("   - " + f)
    sys.exit(1)
print(" Todo en orden: lo pide el cliente, o se le pregunta y contesta el.")
print("=" * 70)
