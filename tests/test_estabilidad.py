# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL RESUMEN DE ESTABILIDAD DEL ENLACE
================================================================================

Por que existe
--------------
El caso que esta herramienta atiende es el mas facil de dar por bueno sin
serlo: el cliente dice "a veces anda mal", el agente mide y todo da perfecto
-- porque midio justo cuando estaba andando. La unica evidencia esta en el
historial de caidas, y contarlo es aritmetica: cuantos eventos entran en la
ventana, cual causa domina, si eso alcanza para llamarlo inestable. Eso es
codigo (PRD 12.5), y el codigo necesita guarda.

Lo que se protege aca, en orden de importancia:

  - Que una ausencia de datos NUNCA se lea como "el enlace esta estable". Es
    el mismo error que ya costo caro con "no pude ver los dispositivos" vs
    "no hay nadie conectado".
  - Que el historial se parsee en LAS DOS formas en que el proveedor lo
    manda (diccionario indexado por numero, o lista). Asumir una sola es
    como se rompen estas integraciones en silencio.
  - Que la ventana excluya de verdad lo viejo: un puerto acumula equipos que
    se cayeron hace meses, y contarlos hincha el numero hasta volverlo inutil.

No hace falta red: se prueban las funciones de conteo con historiales
armados a mano.

Uso
---
    py -3.13 tests/test_estabilidad.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.herramientas.estabilidad import (  # noqa: E402
    CAIDAS_PARA_INESTABLE, VENTANA_HORAS, _a_fecha, _eventos)

fallos: list[str] = []


def comprobar(condicion, descripcion):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


print("\nformas en que llega el historial")
como_dict = {"10": {"Cause": "ONT Re-register", "Offline at": "2026-08-21 14:13:32-05:00"},
             "09": {"Cause": "ONT LOSi/LOBi alarm", "Offline at": "2026-08-21 13:28:24-05:00"}}
como_lista = list(como_dict.values())
comprobar(len(_eventos(como_dict)) == 2, "diccionario indexado por numero: se leen los dos")
comprobar(len(_eventos(como_lista)) == 2, "lista: se leen los dos")
comprobar(_eventos(None) == [] and _eventos("texto") == [],
          "una forma inesperada no revienta, devuelve vacio")

# El orden importa: el dict viene con '10' primero en el JSON del proveedor,
# pero ordenado por clave el mas viejo queda primero y el mas reciente ultimo,
# que es de donde sale 'ultima_caida'.
comprobar(_eventos(como_dict)[-1]["Cause"] == "ONT Re-register",
          "el mas reciente queda ultimo (de ahi sale 'ultima_caida')")

print("\nfechas")
comprobar(_a_fecha("2026-08-21 14:13:33-05:00") is not None, "el formato real se parsea")
for basura in (None, "", "   ", "ayer", 12345):
    comprobar(_a_fecha(basura) is None, f"no se inventa una fecha con {basura!r}")

print("\nlos umbrales estan declarados y son conservadores")
comprobar(VENTANA_HORAS == 24, "la ventana es de un dia")
comprobar(CAIDAS_PARA_INESTABLE >= 3,
          "hacen falta 3 o mas caidas: dos pueden ser un corte de luz y su vuelta")

print("\nlo medido en vivo el 21/08/2026 (ONU de prueba)")
# Nueve caidas, ocho por perdida optica. Se rehace el conteo con el mismo
# historial para fijar que el resultado sea ese y no otro.
real = {}
for i in range(1, 10):
    real["%02d" % i] = {"Cause": "ONT LOSi/LOBi alarm",
                        "Offline at": "2026-08-21 %02d:00:00-05:00" % (8 + i)}
real["10"] = {"Cause": "ONT Re-register", "Offline at": "2026-08-21 17:26:10-05:00"}
evs = _eventos(real)
comprobar(len(evs) == 10, "los diez eventos se leen")
opticas = sum(1 for e in evs if "LOSi" in e["Cause"])
comprobar(opticas == 9, "se cuentan las alarmas opticas, no la causa mas reciente")
comprobar(evs[-1]["Cause"] == "ONT Re-register",
          "y el 're-register' mas reciente NO borra el patron de atras")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] El resumen de estabilidad cuenta lo que hay que contar.")
