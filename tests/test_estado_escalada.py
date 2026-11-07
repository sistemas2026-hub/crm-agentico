# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA -- no se promete un traspaso que no ocurrio
================================================================================

    py -3.13 tests/test_estado_escalada.py

POR QUE EXISTE
--------------
El 02/09/2026, en una conversacion real, el evaluador se cayo por timeout. Como
devolvia None igual que cuando decide "no escalar", el turno siguio como si
nada: sin caso, sin ticket y sin escalada. Y el modelo le dijo al cliente:

    "Tu caso ya quedo en manos de un colaborador humano."

No habia nadie. El texto del tenant solo reemplaza al del modelo DENTRO de la
rama de escalada, asi que cuando esa rama no corre, el modelo promete libre.

LO QUE ESTE ARCHIVO CUIDA
-------------------------
Que las tres situaciones sigan siendo tres, y no una sola vista desde afuera:

  CONFIRMADO      hay caso o ticket persistido
  NO_CONFIRMADO   se intento y no quedo nada
  NO_DETERMINADO  el evaluador fallo -- no sabemos si correspondia

Sobre todo, que NO_DETERMINADO nunca se deslice a CONFIRMADO. Ese deslizamiento
es el que le miente al cliente.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import cargar_config                   # noqa: E402
from nucleo.seguimiento import estado_escalada as ee             # noqa: E402

_fallas = []


def afirmar(condicion, que):
    print(("  [ok]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        _fallas.append(que)


print(__doc__.split("POR QUE EXISTE")[0])
print("=" * 70)
print(" ESTADO DEL TRASPASO")
print("=" * 70)

print()
print("CASO A -- el evaluador decidio y quedo registrado")
estado, por_que = ee.calcular(evaluador_fallo=False, se_intento_escalar=True,
                              caso_creado=True, ticket_creado=True)
print(f"      -> {estado}: {por_que}")
afirmar(estado == ee.CONFIRMADO, "caso y ticket creados = ESCALAMIENTO_CONFIRMADO")

estado, _ = ee.calcular(False, True, caso_creado=False, ticket_creado=True)
afirmar(estado == ee.CONFIRMADO,
        "alcanza con UNO de los dos: el ticket de la operacion tambien es una persona")
estado, _ = ee.calcular(False, True, caso_creado=True, ticket_creado=False)
afirmar(estado == ee.CONFIRMADO, "o solo el caso del CRM")

print()
print("CASO B -- se intento y no quedo registrado en ningun lado")
estado, por_que = ee.calcular(False, True, caso_creado=False, ticket_creado=False)
print(f"      -> {estado}: {por_que}")
afirmar(estado == ee.NO_CONFIRMADO, "sin caso ni ticket = ESCALAMIENTO_NO_CONFIRMADO")
afirmar(estado != ee.CONFIRMADO, "y nunca se cuenta como confirmado")

# El CRM caido con el evaluador funcionando da lo mismo: al cliente no le
# cambia nada de donde vino la falla.
estado, _ = ee.calcular(evaluador_fallo=True, se_intento_escalar=True,
                        caso_creado=False, ticket_creado=False)
afirmar(estado == ee.NO_CONFIRMADO,
        "lo que manda es si quedo registrado, no si el evaluador contesto")

print()
print("CASO E -- el evaluador fallo y nadie llego a intentar nada")
estado, por_que = ee.calcular(evaluador_fallo=True, se_intento_escalar=False,
                              caso_creado=False, ticket_creado=False)
print(f"      -> {estado}: {por_que}")
afirmar(estado == ee.NO_DETERMINADO, "el timeout da NO_DETERMINADO")
afirmar(estado != ee.CONFIRMADO,
        "NO_DETERMINADO no es 'se escalo' -- esa confusion es la que miente")
afirmar(estado != ee.NO_CONFIRMADO,
        "y tampoco es 'fallo el registro': nadie llego a intentarlo")

print()
print("CASO F -- un turno normal no queda con estado ninguno")
estado, _ = ee.calcular(False, False, False, False)
afirmar(estado is None,
        "sin escalada en juego no hay nada que anotar ni que sustituir")

print()
print("CASO D -- la promesa se reconoce en el texto que de verdad salio")
config = cargar_config("tenants/rapilink.config.yaml")
frases = config.escalamiento.frases_de_traspaso
afirmar(bool(frases), "el tenant declara sus frases de traspaso")

# Textual, de la conversacion del 02/09/2026.
real = ("Tu caso ya quedó en manos de un colaborador humano para que lo revise "
        "a fondo: tu equipo quedó reiniciado y sigue sin responder el servicio.")
afirmar(ee.promete_traspaso(real, frases) is not None,
        "reconoce la promesa exacta que salio en produccion")

otra = "Un compañero  del   equipo\nlo va a aplicar y te confirma."
afirmar(ee.promete_traspaso(otra, frases) is not None,
        "no se escapa por mayusculas, saltos de linea ni espacios de mas")

sanas = [
    "Ya reinicié tu equipo. Espera uno o dos minutos y prueba de nuevo.",
    "Tu plan es PLAN FIBRA OPTICA 100MB. ¿Necesitas algo más?",
    "¿Te volvió el internet?",
    "No, la clave vieja ya no sirve. Reconecta con la nueva.",
]
afirmar(all(ee.promete_traspaso(t, frases) is None for t in sanas),
        "y no marca respuestas normales: 4 de 4 pasan limpias")

afirmar(ee.promete_traspaso(real, []) is None,
        "sin frases declaradas no se revisa nada: nadie estrena esto sin pedirlo")
afirmar(ee.promete_traspaso("", frases) is None, "un texto vacio no explota")

print()
print("=" * 70)
if _fallas:
    print(f" {len(_fallas)} falla(s):")
    for f in _fallas:
        print("   - " + f)
    sys.exit(1)
print(" Todo en orden: lo que no quedo registrado no se puede prometer.")
print("=" * 70)
