# -*- coding: utf-8 -*-
"""
================================================================================
 CARGAR SOLO ESTAS CLAVES  --  cli/cargar_claves.py::copiar_claves (30/10/2026)
================================================================================

Lo que se protege: que subir UNA clave del YAML a la base no toque nada mas.
Es el motivo de existir de la herramienta -- la base de Rapilink tiene la
encuesta en modo prueba ('solo_a') que el YAML no trae, y cargar el archivo
entero la pisaria.

Sin base: 'copiar_claves' es una funcion pura sobre dos diccionarios. El camino
de escritura es nucleo/config/editor.py::_editar, que ya tiene sus guardas.

    py -3.13 tests/test_cargar_claves.py
================================================================================
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cli.cargar_claves import ClaveInvalida, copiar_claves   # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def lanza(fn) -> bool:
    try:
        fn()
    except ClaveInvalida:
        return True
    return False


BASE = {
    "encuesta_whatsapp": {"solo_a": ["573000000000"]},
    "capacidad": {"acciones_que_evitan_visita": []},
    "herramientas": [
        {"nombre": "reiniciar_ont", "exige_previas": [{"herramienta": "ping"}], "descripcion": "BASE"},
        {"nombre": "ping_cliente", "descripcion": "BASE"},
    ],
}
SEMILLA = {
    "encuesta_whatsapp": {},
    "capacidad": {"acciones_que_evitan_visita": ["reiniciar_ont"]},
    "herramientas": [
        {"nombre": "reiniciar_ont", "exige_previas": [{"herramienta": "ping"},
                                                     {"herramienta": "incidente"}],
         "descripcion": "YAML"},
        {"nombre": "ping_cliente", "descripcion": "YAML"},
    ],
}
intacta = copy.deepcopy(BASE)

print("\nuna clave de primer nivel")
nuevo, cambios = copiar_claves(BASE, SEMILLA, ["capacidad"])
comprobar(nuevo["capacidad"] == SEMILLA["capacidad"], "la clave pedida queda como en el YAML")
comprobar(nuevo["encuesta_whatsapp"] == {"solo_a": ["573000000000"]},
          "la encuesta en modo prueba de la base NO se pisa")
comprobar(nuevo["herramientas"] == BASE["herramientas"], "el catalogo no se toca")
comprobar([c["clave"] for c in cambios] == ["capacidad"], "el cambio se informa con su clave")
comprobar(BASE == intacta, "el documento de la base no se modifica en el lugar")

print("\nun campo de un elemento de una lista, por su nombre")
nuevo, cambios = copiar_claves(BASE, SEMILLA, ["herramientas[reiniciar_ont].exige_previas"])
reinicio = next(h for h in nuevo["herramientas"] if h["nombre"] == "reiniciar_ont")
comprobar(len(reinicio["exige_previas"]) == 2, "la previa nueva llega")
comprobar(reinicio["descripcion"] == "BASE", "el resto de esa herramienta queda como en la base")
comprobar(next(h for h in nuevo["herramientas"] if h["nombre"] == "ping_cliente")["descripcion"] == "BASE",
          "y las otras herramientas tambien")

print("\nlo que no se hace")
_, sin_cambio = copiar_claves(SEMILLA, SEMILLA, ["capacidad"])
comprobar(sin_cambio == [], "si ya esta igual, no informa cambios")
comprobar(lanza(lambda: copiar_claves(BASE, {"herramientas": []}, ["capacidad"])),
          "una clave ausente en el YAML es un error: no se borra de la base por omision")
comprobar(lanza(lambda: copiar_claves(BASE, SEMILLA, ["herramientas[no_existe].exige_previas"])),
          "un elemento que no esta, error")
comprobar(lanza(lambda: copiar_claves(BASE, SEMILLA, ["herramientas.0.nombre"])),
          "una forma de clave desconocida, error")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Cargar una clave no toca nada mas.")
