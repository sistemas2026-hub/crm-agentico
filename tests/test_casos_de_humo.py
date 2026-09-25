# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUBCONJUNTO DE HUMO SIGUE SIENDO CORRIBLE
================================================================================

Por que existe
--------------
'--humo' existe por una razon medible: los 56 casos dorados tardan ~23 minutos
y por eso no se corren. Entre el 08 y el 09/09/2026 se hicieron diecinueve
arreglos sin correrlos enteros ni una vez, y cinco de esos diecinueve eran
regresiones que un caso de ese mismo archivo habria cazado.

Un subconjunto de humo solo sirve mientras siga siendo BARATO y SEGURO. Las
dos formas de perderlo son silenciosas:

  1. Alguien marca un caso mas, y otro, y la corrida vuelve a durar veinte
     minutos. Entonces deja de correrse, igual que la completa, y el problema
     original vuelve intacto con una bandera nueva encima.

  2. Alguien marca un caso que llega al diagnostico completo. Ese REINICIA la
     ONU de laboratorio de verdad: 'sesion_por_defecto' trae su serial, la
     recuperacion medida es de ~6 minutos (15/08/2026), y el caso siguiente
     corre contra un equipo que se esta levantando. El sintoma es una bateria
     que falla en varios casos a la vez y parece una regresion del prompt --
     ya se persiguio dos veces asi antes de mirar el equipo.

Esto guarda las dos cosas. No prueba que los casos PASEN --eso lo hace
cli/evaluar.py contra el motor real-- sino que el subconjunto siga siendo
la clase de cosa que uno corre sin pensarlo.

Corre SIN BASE DE DATOS, sin red y sin modelo: solo lee el YAML.

Uso
---
    py -3.13 tests/test_casos_de_humo.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import importlib.util                                                # noqa: E402
import yaml                                                          # noqa: E402

# La lista de herramientas que escriben vive en el corredor, no aca: si
# estuviera en los dos lados, la copia del test se quedaria vieja justo
# cuando importa. cli/ no es un paquete, asi que se carga por ruta.
_spec = importlib.util.spec_from_file_location(
    "evaluar", RAIZ / "cli" / "evaluar.py")
_evaluar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_evaluar)

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


# LO QUE ESTA GUARDA NO PUEDE VER, Y HAY QUE SABERLO
#
# Solo mira lo que el caso AFIRMA ('espera.usa'). El 09/09/2026 eso no
# alcanzo: 'falla de internet va a soporte tecnico' afirma unicamente
# 'derivar_a_area' y en la corrida real encadeno hasta 'reiniciar_ont',
# reiniciando la ONU de laboratorio. Un caso no declara los efectos que no
# espera -- por eso justamente son los peligrosos.
#
# La comprobacion que si ve la verdad esta en cli/evaluar.py y corre sobre la
# traza despues de la corrida. Esta de aca sigue valiendo por barata (sin red,
# sin modelo) y porque atrapa el error obvio: marcar de humo un caso que ya
# declaraba que iba a escribir.
TOCAN_EL_EQUIPO = _evaluar.ESCRIBEN_EN_SISTEMAS

# Ocho casos a ~20-25s cada uno son ~3 minutos. Diez ya son cuatro y medio, y
# a partir de ahi la corrida deja de caber "despues de cada cambio", que es lo
# unico que este subconjunto tenia a favor.
TOPE = 10


for ruta in sorted(RAIZ.glob("evaluacion/*.casos.yaml")):
    tenant = ruta.name.replace(".casos.yaml", "")
    print(f"== {tenant} ==")

    doc = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    casos = doc.get("casos") or []
    humo = [c for c in casos if c.get("humo")]

    afirmar(bool(humo),
            f"hay casos marcados 'humo: true' ({len(humo)} de {len(casos)})")

    afirmar(len(humo) <= TOPE,
            f"el subconjunto sigue cabiendo en una corrida corta "
            f"({len(humo)} <= {TOPE}) -- si hace falta agregar uno, se saca "
            f"otro, no se estira")

    for caso in humo:
        usa = caso.get("espera", {}).get("usa") or []
        peligrosas = [h for h in usa
                      if any(m in h for m in TOCAN_EL_EQUIPO)]
        afirmar(not peligrosas,
                f"'{caso['nombre']}' no escribe en ningun sistema "
                f"{'-- ' + str(peligrosas) if peligrosas else ''}")

    # Un caso de humo que no afirma nada no protege nada, y da una corrida
    # verde que no significa nada. Es la unica forma de tener ocho casos
    # pasando y cero cobertura.
    for caso in humo:
        espera = caso.get("espera") or {}
        afirmar(bool(espera),
                f"'{caso['nombre']}' afirma algo sobre la traza")

    # Los nombres tienen que seguir existiendo tal cual: '--humo' filtra por
    # la bandera, pero quien lo diagnostica despues busca por nombre.
    afirmar(len({c["nombre"] for c in humo}) == len(humo),
            "ningun nombre repetido entre los casos de humo")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El subconjunto de humo sigue siendo corto y no toca ningun equipo.")
