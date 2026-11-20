# -*- coding: utf-8 -*-
"""
================================================================================
 LA CARGA HISTORICA  --  que el troceado no deje huecos ni repita
================================================================================

    py -3.13 tests/test_importar_historico.py

Corre SIN RED y SIN BASE.

QUE SE PRUEBA, Y QUE NO
-----------------------
Lo UNICO que este comando agrega es partir un rango largo en tramos que el
proveedor acepte. Todo lo demas --que filtro aplicar, a que area va cada
ticket, como se escribe-- es el mismo codigo que corre el reloj, y ya tiene
sus pruebas en test_importacion_tickets.py. Duplicarlas aqui daria una falsa
sensacion de cobertura.

POR QUE EL TROCEADO MERECE PRUEBA PROPIA
-----------------------------------------
Porque un error ahi no se ve: deja un HUECO de dias que nadie nota hasta que
alguien busca un ticket que deberia estar. Un tramo de mas solo cuesta una
llamada; un dia que ningun tramo cubre cuesta tickets perdidos, y el sintoma
aparece meses despues.

El tope de 55 dias no es prudencia: el proveedor responde HTTP 400 a cualquier
rango mayor a dos meses, medido el 07/10/2026 pidiendo '2026-01-01 -> hoy'.
================================================================================
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

sys.path.insert(0, str(RAIZ / "cli"))
from importar_historico import DIAS_POR_TRAMO, tramos  # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))
    fallos.append(que)


def dias_cubiertos(lista):
    """Todos los dias que los tramos tocan, para buscar huecos y solapes."""
    vistos = []
    for d, h in lista:
        a, b = date.fromisoformat(d), date.fromisoformat(h)
        while a <= b:
            vistos.append(a)
            a += timedelta(days=1)
    return vistos


print("el rango se parte sin dejar huecos ni repetir dias")

#  EL CASO REAL: el ticket abierto mas viejo es del 29/04/2025.
DESDE, HASTA = date(2025, 4, 29), date(2026, 10, 7)
lista = list(tramos(DESDE, HASTA))
cubiertos = dias_cubiertos(lista)
esperados = (HASTA - DESDE).days + 1

revisar(len(cubiertos) == esperados,
        f"los {esperados} dias del rango quedan cubiertos",
        f"cubiertos {len(cubiertos)}")
revisar(len(set(cubiertos)) == len(cubiertos),
        "y ninguno se pide dos veces",
        "un dia repetido no rompe nada --la unicidad lo corta-- pero cuesta "
        "llamadas y delata que el calculo esta mal")
revisar(cubiertos[0] == DESDE and cubiertos[-1] == HASTA,
        "el primer dia y el ultimo son los pedidos")
revisar(all(
    (date.fromisoformat(h) - date.fromisoformat(d)).days + 1 <= DIAS_POR_TRAMO
    for d, h in lista),
    f"ningun tramo pasa de {DIAS_POR_TRAMO} dias",
    "el proveedor responde 400 a mas de dos meses")

#  --- los bordes, que es donde un troceado se rompe -----------------------
print("\nlos bordes")

uno = list(tramos(date(2026, 1, 10), date(2026, 1, 10)))
revisar(uno == [("2026-01-10", "2026-01-10")],
        "un rango de UN dia da un tramo de ese dia",
        "con un '<' en vez de '<=' esto daria una lista vacia y la corrida "
        "diria 'no hay tickets' sin haber preguntado")

justo = list(tramos(date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=DIAS_POR_TRAMO - 1)))
revisar(len(justo) == 1,
        f"un rango de exactamente {DIAS_POR_TRAMO} dias da UN tramo, no dos")

uno_mas = list(tramos(date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=DIAS_POR_TRAMO)))
revisar(len(uno_mas) == 2 and uno_mas[1][0] == uno_mas[1][1],
        "y uno mas da dos, el segundo de un solo dia")

revisar(list(tramos(date(2026, 5, 2), date(2026, 5, 1))) == [],
        "un rango invertido no devuelve tramos",
        "el CLI ademas lo rechaza antes, pero la funcion no puede confiar en eso")

#  Que los tramos sean CONSECUTIVOS: el siguiente arranca justo al dia
#  siguiente del anterior. Es la forma directa de afirmar 'sin huecos'.
consecutivos = all(
    date.fromisoformat(lista[i + 1][0]) - date.fromisoformat(lista[i][1]) == timedelta(days=1)
    for i in range(len(lista) - 1))
revisar(consecutivos,
        "cada tramo arranca el dia siguiente al que termino el anterior")

print(f"\n  ({len(lista)} tramos para el rango real del 29/04/2025 a hoy)")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] El rango se cubre entero, sin huecos ni dias repetidos.")
