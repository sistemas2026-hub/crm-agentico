# -*- coding: utf-8 -*-
"""
================================================================================
 CORRER LAS PRUEBAS  --  las 145, o el subconjunto que este entorno permite
================================================================================

    py -3.13 cli/correr_pruebas.py                 todo lo que se pueda aca
    py -3.13 cli/correr_pruebas.py --sin-base      salta las que piden Postgres
    py -3.13 cli/correr_pruebas.py --solo relevo   las que tengan eso en el nombre
    py -3.13 cli/correr_pruebas.py --listar        que hay y como se clasifica

POR QUE EXISTE
--------------
`tests/` son 145 archivos sueltos: no hay pytest, no hay runner, y cada uno se
corre a mano. Eso significa que en la practica **no se corren**: cinco de las
diecinueve regresiones del 08-09/09/2026 las habria cazado un caso que ya
existia, verde, y que nadie miro.

Tampoco los corre nadie automaticamente. `.github/` tenia solo CODEOWNERS, y los
workflows que viven en `django-crm/.github/` no los lee GitHub Actions: solo mira
la raiz. Ese es el hueco D1 de CLAUDE.md.

COMO CORRE UNA PRUEBA
---------------------
Como subproceso, mirando el codigo de salida. No se importan: la mayoria no
tiene bloque `__main__` y hace su trabajo al importarse, asi que importarlas
desde un corredor las ejecutaria en un orden y un estado compartidos que nadie
diseno. Un proceso por archivo tambien evita que una que ensucie el entorno
global se lleve puestas a las siguientes.

LO QUE NO PUEDE CORRER, LO DICE
-------------------------------
48 archivos piden Postgres y 3 salen a la red. Saltarlos en silencio seria peor
que no correr nada: un verde que en realidad son 94 de 145 miente sobre la
cobertura. Se saltan nombrados, contados aparte, y el resumen distingue
**FALLO** de **NO SE PUDO CORRER** -- que es la misma regla que el contrato
congelado llama NO_VERIFICABLE.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PRUEBAS = RAIZ / "tests"

#: Pide una base de datos de verdad.
_PIDE_BASE = re.compile(r"psycopg|DATABASE_URL|\bDBHOST\b|dsn\(|conexion\.dsn")
#: Sale a internet o a un modelo.
_PIDE_RED = re.compile(r"requests\.(get|post|put|delete)|openai\.|anthropic\.")

#: No son pruebas aunque vivan en tests/.
_NO_SON_PRUEBAS = {"manifiesto_de_laboratorio.py"}


def clasificar(archivo: Path) -> str:
    """base | red | aislada. Se decide leyendo, no ejecutando."""
    texto = archivo.read_text(encoding="utf-8", errors="replace")
    if _PIDE_BASE.search(texto):
        return "base"
    if _PIDE_RED.search(texto):
        return "red"
    return "aislada"


def descubrir() -> list[tuple[Path, str]]:
    archivos = sorted(
        p for p in PRUEBAS.glob("test_*.py") if p.name not in _NO_SON_PRUEBAS
    )
    return [(p, clasificar(p)) for p in archivos]


#: Lo que dice una prueba cuando le falta el entorno, no cuando falla.
#:
#: La clasificacion por lectura tiene falsos negativos: `test_autor_y_reintento`
#: y `test_guardas_control` piden Postgres sin nombrar `psycopg` ni `DBHOST`, asi
#: que entraban como aisladas y su queja salia listada entre las fallas. Un
#: «no se pudo medir» contado como «se midio y fallo» es justo lo que el
#: contrato congelado llama NO_VERIFICABLE, y arruina el unico numero que este
#: corredor produce.
_FALTA_ENTORNO = re.compile(
    r"No hay datos de conexion|"
    r"Definir DBHOST|"
    r"could not connect to server|"
    r"connection to server .* failed",
    re.IGNORECASE,
)


def _primer_motivo_legible(lineas: list[str]) -> str:
    """La linea que de verdad explica el fallo, recorriendo desde el final.

    Se descarta lo que no dice nada por si solo: las barras de separacion que
    estas pruebas imprimen al cerrar, y los encabezados de traceback. Si no
    queda ninguna, se devuelve vacio y quien llama pone el codigo de salida --
    antes que una linea de iguales, que parece un motivo y no lo es.
    """
    for linea in reversed(lineas):
        limpia = linea.strip()
        if not limpia.strip("=-_ "):          # solo barras: no explica nada
            continue
        if limpia.startswith("Traceback ("):   # el encabezado, no la causa
            continue
        return limpia[:160]
    return ""


def correr(archivo: Path, segundos: int) -> tuple[bool, str, float]:
    arranque = time.monotonic()
    try:
        r = subprocess.run(
            [sys.executable, str(archivo)],
            cwd=str(RAIZ),
            capture_output=True,
            text=True,
            timeout=segundos,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return False, f"se colgo: mas de {segundos}s", time.monotonic() - arranque
    tardo = time.monotonic() - arranque
    if r.returncode == 0:
        return True, "", tardo
    # La ultima linea util del error dice mas que el traceback entero.
    #
    # "util" hay que definirlo: la primera version tomaba la ultima linea no
    # vacia y el 24/09/2026 la primera corrida en CI reporto un fallo cuyo
    # motivo era "=========". Estas pruebas cierran con una barra de
    # separacion, asi que la ultima linea casi nunca es la que explica nada.
    # Un motivo ilegible no es cosmetico: manda a abrir el log entero, que es
    # justo el trabajo que este corredor existe para ahorrar.
    salida = (r.stdout or "") + (r.stderr or "")
    lineas = [l for l in salida.strip().splitlines() if l.strip()]
    motivo = _primer_motivo_legible(lineas) or f"codigo {r.returncode}"
    if _FALTA_ENTORNO.search(salida):
        # No fallo: no se pudo medir. Se devuelve como salteada.
        return None, "pide Postgres (lo dijo al correr, no se leia en el codigo)", tardo
    return False, motivo, tardo


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sin-base", action="store_true",
                   help="salta las que piden Postgres")
    p.add_argument("--sin-red", action="store_true",
                   help="salta las que salen a la red")
    p.add_argument("--solo", default="",
                   help="solo las que tengan este texto en el nombre")
    p.add_argument("--listar", action="store_true",
                   help="muestra la clasificacion y no corre nada")
    p.add_argument("--timeout", type=int, default=180,
                   help="segundos por prueba (por defecto 180)")
    args = p.parse_args()

    todas = descubrir()
    if args.solo:
        todas = [(a, c) for a, c in todas if args.solo in a.name]

    if args.listar:
        for clase in ("aislada", "base", "red"):
            grupo = [a.name for a, c in todas if c == clase]
            print(f"\n{clase.upper()}  ({len(grupo)})")
            for n in grupo:
                print(f"  {n}")
        return 0

    saltadas: list[tuple[str, str]] = []
    a_correr: list[Path] = []
    for archivo, clase in todas:
        if clase == "base" and args.sin_base:
            saltadas.append((archivo.name, "pide Postgres"))
        elif clase == "red" and args.sin_red:
            saltadas.append((archivo.name, "sale a la red"))
        else:
            a_correr.append(archivo)

    print(f"corriendo {len(a_correr)} prueba(s)"
          f"{f', saltando {len(saltadas)}' if saltadas else ''}\n")

    fallaron: list[tuple[str, str]] = []
    arranque = time.monotonic()
    for i, archivo in enumerate(a_correr, 1):
        ok, motivo, tardo = correr(archivo, args.timeout)
        marca = {True: "ok  ", False: "FALLA", None: "sin "}[ok]
        print(f"  [{i:3}/{len(a_correr)}] {marca} {archivo.name:52} {tardo:5.1f}s")
        if ok is None:
            saltadas.append((archivo.name, motivo))
        elif not ok:
            print(f"            -> {motivo}")
            fallaron.append((archivo.name, motivo))

    total = time.monotonic() - arranque
    print(f"\n{'=' * 78}")
    verdes = len(a_correr) - len(fallaron) - sum(
        1 for n, _ in saltadas if any(n == a.name for a in a_correr))
    print(f"  {verdes} en verde · {len(fallaron)} en rojo"
          f" · {len(saltadas)} sin correr · {total:.0f}s")

    if saltadas:
        # Nombradas, no escondidas: un verde sobre 94 de 145 miente si no se
        # dice cuantas quedaron afuera y por que.
        print(f"\n  NO SE PUDIERON CORRER ({len(saltadas)}) -- no es lo mismo que pasar:")
        for nombre, motivo in saltadas[:6]:
            print(f"    {nombre:54} {motivo}")
        if len(saltadas) > 6:
            print(f"    ... y {len(saltadas) - 6} mas (--listar para verlas)")

    if fallaron:
        print(f"\n  EN ROJO ({len(fallaron)}):")
        for nombre, motivo in fallaron:
            print(f"    {nombre}")
            print(f"      {motivo}")
    print(f"{'=' * 78}")
    return 1 if fallaron else 0


if __name__ == "__main__":
    sys.exit(main())
