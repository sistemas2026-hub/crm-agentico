# -*- coding: utf-8 -*-
"""
================================================================================
 QUÉ FALLA SIEMPRE Y QUÉ TIEMBLA  --  separa la deuda del ruido
================================================================================

    py -3.13 cli/casos_inestables.py informe1.json informe2.json informe3.json

POR QUÉ EXISTE
--------------
§6 dice que *«la misma corrida sobre lo desplegado, en el mismo entorno, es el
único control que separa una regresión del ruido»*, y da el ejemplo de 70/88
contra 69/88. Lo que no dice es **cómo** separarlas cuando ya tenés varias
corridas: hay que mirar caso por caso, no el total.

Medido el 21/10/2026 sobre cuatro corridas del set dorado: los totales iban
4, 7, 6, 4 fallos de conducta — y eso se lee como «el sistema empeoró y
mejoró». No. Mirando caso por caso aparecen **dos clases distintas**:

    falla en TODAS      deuda real. El total la esconde dentro del ruido.
    falla en ALGUNAS    el instrumento temblando. Perseguirla es perder el día.

Ese día, de 11 casos que fallaron alguna vez, **solo 2 fallaban siempre**. Los
otros 9 eran el piso de ruido, concentrado —no repartido— en un puñado de
afirmaciones frágiles.

CÓMO SE USA
-----------
Se le pasan los `--json` de dos o más corridas de `cli/evaluar.py`. Cuantas
más, mejor separa: con dos, un caso que falla en una sola es ambiguo; con
cuatro, 1/4 ya es claramente ruido.

Los fallos de infraestructura (timeouts, conexión) se descartan: el corredor
ya los clasifica aparte y mezclarlos inventaría inestabilidad que no es del
modelo.
================================================================================
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

#:  Lo que no es una decisión del modelo. Mezclarlo contaría como «inestable»
#:  algo que solo dice que la red falló.
INFRA = ("Timeout", "ConnectionError", "ErrorSecreto")


def _conducta(caso: dict) -> bool:
    """¿Es un fallo de conducta, o se cayó la red?"""
    return not any(m in f for f in (caso.get("fallas") or []) for m in INFRA)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("informes", nargs="+", help="los --json de cada corrida")
    args = ap.parse_args()

    corridas = 0
    fallo_en: Counter = Counter()
    presente: Counter = Counter()
    motivos: dict[str, set] = {}

    for ruta in args.informes:
        p = Path(ruta)
        if not p.exists():
            print(f"  (no existe, se saltea: {ruta})")
            continue
        casos = json.loads(p.read_text(encoding="utf-8"))
        corridas += 1
        for c in casos:
            presente[c["nombre"]] += 1
            if not c.get("ok") and _conducta(c):
                fallo_en[c["nombre"]] += 1
                motivos.setdefault(c["nombre"], set()).add(
                    (c.get("fallas") or [""])[0][:80])

    if corridas < 2:
        raise SystemExit("hacen falta al menos dos corridas para separar nada")

    print("=" * 74)
    print(f"  QUÉ FALLA SIEMPRE Y QUÉ TIEMBLA  --  {corridas} corridas")
    print("=" * 74)

    #  SOLO SE JUZGA LO QUE ESTUVO EN TODAS. Un caso agregado a mitad de
    #  camino aparecería como «inestable» por haber corrido menos veces, y eso
    #  es exactamente la clase de falso hallazgo que esto existe para evitar.
    siempre = [n for n, k in fallo_en.items()
               if k == corridas and presente[n] == corridas]
    tiembla = [(n, k) for n, k in fallo_en.items()
               if 0 < k < corridas and presente[n] == corridas]
    parciales = [n for n in fallo_en if presente[n] != corridas]

    print()
    print(f"  DEUDA REAL  ({len(siempre)})  -- falla en todas")
    for n in sorted(siempre):
        print(f"     {n}")
        for m in sorted(motivos.get(n, [])):
            print(f"        {m}")
    if not siempre:
        print("     (ninguno)")

    print()
    print(f"  INESTABLES  ({len(tiembla)})  -- acá vive el piso de ruido")
    for n, k in sorted(tiembla, key=lambda x: -x[1]):
        print(f"     {k}/{corridas}  {n}")
    if not tiembla:
        print("     (ninguno)")

    if parciales:
        print()
        print(f"  NO SE JUZGAN  ({len(parciales)})  -- no estuvieron en todas "
              "las corridas")
        for n in sorted(parciales):
            print(f"     {n}")

    print()
    print(f"  El piso de ruido de este set es de hasta {len(tiembla)} casos.")
    print("  Un cambio que mueva menos que eso NO se puede distinguir del")
    print("  temblor, por más corridas que se hagan de una sola versión.")
    print("=" * 74)


if __name__ == "__main__":
    main()
