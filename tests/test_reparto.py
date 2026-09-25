# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL REPARTO DE TRABAJO
================================================================================

Por que existe
--------------
Hasta el 23/08/2026, un area con dos o mas personas dejaba el caso SIN
asignar. Y un caso sin dueño no queda "para todos": el CRM le muestra a quien
no es administrador solo lo suyo, asi que queda invisible para el equipo
entero. Medido sobre la instancia real: 54 casos escalados, y las dos
personas del equipo veian cero.

El reparto arregla eso, pero introduce su propio riesgo: si reparte mal, el
sintoma es que una persona se satura y otra esta libre -- algo que nadie ve
hasta que alguien se queja. De ahi esta guarda.

Lo que se protege
-----------------
  - Que le toque al que MENOS tiene abierto, no por turnos. Un turno rotativo
    reparte parejo en el papel y desparejo en la practica: si a uno le tocaron
    casos que se estancaron y a otro casos que cerro, el turno les sigue dando
    lo mismo.
  - Que el desempate sea ESTABLE y no al azar. La pregunta "¿por que le toco a
    esta persona?" tiene que tener respuesta seis meses despues; un reparto
    que no se puede explicar es uno que nadie confia.
  - Que no saber la carga NO impida asignar. Degradar a un orden estable es
    peor que repartir parejo, pero mucho mejor que dejar el trabajo huerfano.

Uso
---
    py -3.13 tests/test_reparto.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.seguimiento.reparto import (  # noqa: E402
    contar_por_responsable, elegir_menos_cargado)

fallos: list[str] = []


def comprobar(condicion, descripcion):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


print("\nle toca al que menos tiene")
comprobar(elegir_menos_cargado(["ana", "beto"], {"ana": 5, "beto": 1}) == "beto",
          "con 5 contra 1, le toca al de 1")
comprobar(elegir_menos_cargado(["ana", "beto"], {"ana": 0, "beto": 9}) == "ana",
          "y al reves tambien -- no es un turno fijo")

print("\nquien se desocupa vuelve a recibir")
# Es la propiedad que pidio el cliente: sin contador aparte, solo mirando lo
# abierto. Beto cierra los suyos y vuelve a ser el que menos tiene.
antes = elegir_menos_cargado(["ana", "beto"], {"ana": 2, "beto": 7})
despues = elegir_menos_cargado(["ana", "beto"], {"ana": 3, "beto": 1})
comprobar(antes == "ana" and despues == "beto",
          "cuando el saturado se desocupa, el siguiente le toca a el")

print("\nel desempate es estable, no al azar")
mismos = {"zoe": 3, "ana": 3, "beto": 3}
elegidos = {elegir_menos_cargado(["zoe", "ana", "beto"], mismos) for _ in range(20)}
comprobar(len(elegidos) == 1,
          "veinte veces con la misma carga dan SIEMPRE la misma persona")
comprobar(elegir_menos_cargado(["zoe", "ana", "beto"], mismos) == "ana",
          "y es un orden explicable, no el que quedo primero en la lista")

print("\nno saber la carga no impide asignar")
comprobar(elegir_menos_cargado(["ana", "beto"], {}) is not None,
          "sin datos de carga igual asigna: dejar el trabajo huerfano es peor")
comprobar(elegir_menos_cargado(["ana", "beto"], None) is not None,
          "y con la carga en None tampoco falla")
comprobar(elegir_menos_cargado(["ana", "beto"], {"ana": 4}) == "beto",
          "quien no figura en la carga cuenta como cero, no como desconocido")

print("\nlo que ESPERA tambien ocupa")
# Contar solo lo ya empezado dejaba invisible la cola de alguien: quien tenia
# ocho casos sin abrir figuraba tan libre como quien no tenia ninguno, y se le
# seguian dando mas.
espera = contar_por_responsable(
    [{"assigned_to": "ana", "status": "New"},
     {"assigned_to": "ana", "status": "Assigned"},
     {"assigned_to": "beto", "status": "Pending"}], "assigned_to")
comprobar(espera == {"ana": 2, "beto": 1},
          "cuentan los nuevos y los asignados, no solo los que ya se abrieron")
comprobar(elegir_menos_cargado(["ana", "beto"], espera) == "beto",
          "y el reparto lo usa: le toca al que tiene menos esperando")

print("\nsin candidatos no se inventa uno")
comprobar(elegir_menos_cargado([], {"ana": 1}) is None, "lista vacia devuelve None")

print("\ncontar responsables, en las formas en que llegan de una API")
comprobar(contar_por_responsable(
    [{"assigned_to": "ana"}, {"assigned_to": "ana"}, {"assigned_to": "beto"}],
    "assigned_to") == {"ana": 2, "beto": 1}, "id suelto")
comprobar(contar_por_responsable(
    [{"assigned_to": {"id": "ana"}}], "assigned_to") == {"ana": 1},
    "objeto con 'id' -- asumir una sola forma es como se rompen estas cosas")
comprobar(contar_por_responsable(
    [{"assigned_to": [{"id": "ana"}, {"id": "beto"}]}], "assigned_to")
    == {"ana": 1, "beto": 1},
    "varios responsables: cuenta para los dos, porque a los dos los ocupa")
comprobar(contar_por_responsable([{"otra_cosa": "x"}, None, "texto"], "assigned_to") == {},
          "filas sin responsable o con forma rara no rompen el conteo")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] El trabajo se reparte parejo y de forma explicable.")
