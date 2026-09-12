# -*- coding: utf-8 -*-
"""
================================================================================
 NINGUN ARCHIVO DE tests/ PUEDE IMPRIMIR [FALLA] Y SALIR CON CODIGO 0
================================================================================

    py -3.13 tests/test_runners_no_ocultan_fallos.py

Por que existe
--------------
'tests/test_importacion_tickets.py' tenia 890 lineas y su ultima compuerta de
salida en la 759. Las 131 de abajo -- todas las del hilo de respuestas --
corrian sin que nada las hiciera fallar: el archivo imprimia '[FALLA]' en
pantalla y terminaba con codigo 0.

Eso es peor que no tener la prueba. Una prueba ausente se nota; una que figura
en verde mientras el sintoma esta vivo hace creer que algo esta cubierto. Y el
archivo aparecio en un reporte de auditoria como "exit 0 = pasa", que era falso.

Estos archivos no usan pytest: son guiones que acumulan fallos en una lista y
deciden al final. El patron falla siempre igual -- alguien agrega pruebas al
final del archivo, despues de la ultima compuerta, y nadie lo nota porque la
salida sigue diciendo 0.

Que se comprueba
----------------
Para cada guion manual de tests/: que NINGUNA llamada a la funcion que acumula
fallos quede DESPUES de la ultima compuerta de salida. Es analisis estatico
sobre la posicion en el archivo, que es exactamente donde vive el defecto.

Los archivos de pytest se saltan: alli el corredor decide el codigo de salida y
no hay forma de que una prueba fallida pase inadvertida.
================================================================================
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "tests"

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


# Como se llama la funcion que acumula un fallo, en los guiones de este repo.
ACUMULA = re.compile(r"^\s*(revisar|comprobar|verificar)\s*\(", re.M)

# Como se cierra: cualquier salida distinta de cero.
COMPUERTA = re.compile(r"^\s*(raise SystemExit\(1\)|sys\.exit\(1\))", re.M)

# Un archivo que importa pytest lo decide pytest.
USA_PYTEST = re.compile(r"^\s*import pytest|^\s*from pytest", re.M)


def linea_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


print("=" * 74)
print("  guiones manuales de tests/: la ultima comprobacion antes de la salida")
print("=" * 74)

archivos = sorted(CARPETA.glob("test_*.py"))
manuales, saltados = [], 0

for ruta in archivos:
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    if USA_PYTEST.search(texto):
        saltados += 1
        continue
    if not ACUMULA.search(texto):
        saltados += 1
        continue
    manuales.append((ruta, texto))

print(f"\n  archivos en tests/            : {len(archivos)}")
print(f"  guiones manuales a auditar   : {len(manuales)}")
print(f"  saltados (pytest o sin checks): {saltados}\n")

sin_compuerta, destapados = [], []

for ruta, texto in manuales:
    acumulaciones = list(ACUMULA.finditer(texto))
    compuertas = list(COMPUERTA.finditer(texto))

    if not compuertas:
        sin_compuerta.append(ruta.name)
        print(f"  [FALLA] {ruta.name}: no tiene NINGUNA salida distinta de cero")
        continue

    ultima_check = linea_de(texto, acumulaciones[-1].start())
    ultima_puerta = linea_de(texto, compuertas[-1].start())

    if ultima_check > ultima_puerta:
        destapados.append((ruta.name, ultima_puerta, ultima_check))
        print(f"  [FALLA] {ruta.name}: la ultima compuerta esta en la linea "
              f"{ultima_puerta} y hay comprobaciones hasta la {ultima_check}")
    else:
        print(f"  [ok] {ruta.name:<46} compuerta {ultima_puerta:>4} "
              f">= ultimo check {ultima_check:>4}")

revisar(not sin_compuerta,
        "todos los guiones manuales tienen una salida distinta de cero",
        f"sin compuerta: {sin_compuerta}")

revisar(not destapados,
        "ninguno deja comprobaciones DESPUES de su ultima compuerta",
        "\n         ".join(
            f"{n}: compuerta en {p}, comprobaciones hasta {c}"
            for n, p, c in destapados))

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print(" Un guion que imprime [FALLA] y sale con 0 aparece en verde en")
    print(" cualquier reporte. Agregar la compuerta al FINAL del archivo.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Ningun guion de tests/ puede ocultar un fallo tras su salida.")
print("=" * 74)
