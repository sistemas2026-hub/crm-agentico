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

#  UNA PRUEBA PUEDE PEDIR MAS TIEMPO, Y TIENE QUE DECIR POR QUE.
#
#  Existe porque 'test_revocar_data_api.py' vive al borde del tope: 160s, 176s y
#  a la tercera se colgo (medido el 27/09/2026 en tres corridas seguidas).
#  Levanta la imagen EXACTA de produccion fijada por digest, corre las
#  migraciones de Django y aplica la cadena del ledger, asi que con el Docker
#  ocupado pasa de 180 sin que nada este roto.
#
#  Un rojo intermitente es peor que un rojo: ensena a ignorar los rojos. Y subir
#  el tope para TODAS esconderia un cuelgue de verdad en las otras 155. Asi que
#  el permiso es por prueba, con su motivo escrito al lado.
#
#  La marca la pone la prueba en su propio texto, no esta lista: se busca
#  'TOPE_DE_TIEMPO = <segundos>' en el archivo. Asi el motivo vive junto al
#  codigo que lo necesita y no se desincroniza.
_TOPE_PROPIO = re.compile(r"^TOPE_DE_TIEMPO\s*=\s*(\d+)\s*$", re.MULTILINE)

#  Techo absoluto: ni declarandolo una prueba puede tardar mas que esto. Sin el,
#  'TOPE_DE_TIEMPO = 99999' seria una forma de desactivar la deteccion de
#  cuelgues escribiendo una linea.
_TOPE_MAXIMO = 900


def tope_de(archivo: Path, por_defecto: int) -> int:
    """Los segundos que esta prueba puede tardar. Nunca mas que _TOPE_MAXIMO."""
    texto = archivo.read_text(encoding="utf-8", errors="replace")
    m = _TOPE_PROPIO.search(texto)
    if not m:
        return por_defecto
    return max(por_defecto, min(int(m.group(1)), _TOPE_MAXIMO))


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
    # 26/09/2026: la capa de conexion tiene DOS mensajes, y este faltaba. Con
    # cuatro de las cinco variables puestas, cinco pruebas decian "Conexion
    # incompleta: falta DBNAME" y el corredor las contaba como FALLO -- o sea
    # justo la distincion que existe para hacer (D1). Un rojo que en realidad
    # es "no se pudo medir" infla el numero y esconde los fallos de verdad
    # entre ruido de entorno.
    r"Conexion incompleta|"
    r"could not connect to server|"
    r"connection to server .* failed|"
    #  27/09/2026: una guarda puede necesitar algo que NO es la base -- la del
    #  entrypoint necesita un bash que funcione, y en Windows puede resolver al
    #  de WSL y fallar. Cuando una prueba DECLARA su dependencia con esta frase
    #  exacta, se cuenta como no medida en vez de como rojo. La frase es larga y
    #  literal a proposito: acortarla la volveria facil de disparar por
    #  accidente, y entonces esconderia fallos reales -- el error simetrico.
    r"NO SE PUDO CORRER: falta una dependencia del entorno",
    re.IGNORECASE,
)


#: Lo que una prueba de este repo imprime cuando algo NO paso. Se busca esto
#: antes que cualquier otra linea: es la diferencia entre un motivo que explica
#: y uno que describe lo ultimo que salio bien.
#  EL VEREDICTO QUE LA PRUEBA DA DE SI MISMA, y solo eso.
#
#  Existe porque '_FALTA_ENTORNO' se aplica sobre la salida ENTERA, asi que
#  cualquier prueba que MENCIONE una frase de entorno --por ejemplo porque su
#  fixture la imprime a proposito-- quedaba degradada a "no se pudo correr"
#  aunque hubiera corrido y fallado. Medido el 27/09/2026: rompiendo una
#  afirmacion de 'tests/test_correr_pruebas.py' la prueba sale con 1 y este
#  corredor la contaba como salteada y salia con 0. O sea que la guarda del
#  instrumento que dice si el repo esta en verde era justo la unica que el
#  instrumento no podia reportar en rojo, y el workflow de CI quedaba verde.
#
#  DELIBERADAMENTE ESTRECHO: no incluye 'Traceback' ni 'Exception', porque una
#  prueba que NO PUDO correr por falta de base tambien los imprime. Lo que
#  distingue las dos cosas no es que haya habido un error: es que la prueba
#  haya alcanzado a emitir SU PROPIO veredicto en rojo.
_VEREDICTO_PROPIO_EN_ROJO = re.compile(
    r"\[FALLA\]|\[falla\]|^\s*FALLAS?\s*\(|^\s*FALLA\b|"
    r"no pasaron|\bROJO\b",
    re.MULTILINE,
)

_MARCA_DE_FALLO = re.compile(
    r"\[FALLA\]|\[falla\]|^FALLA|AssertionError|Error:|"
    r"Exception|Traceback \(most recent|se colgo|no pasaron",
)


def _primer_motivo_legible(lineas: list[str]) -> str:
    """La linea que de verdad explica el fallo, recorriendo desde el final.

    Se descarta lo que no dice nada por si solo: las barras de separacion que
    estas pruebas imprimen al cerrar, y los encabezados de traceback. Si no
    queda ninguna, se devuelve vacio y quien llama pone el codigo de salida --
    antes que una linea de iguales, que parece un motivo y no lo es.
    """
    # PRIMERO lo que se declara como fallo, y solo despues la ultima linea
    # util. Sin esta pasada, el motivo que salia era casi siempre una linea de
    # OK -- estas pruebas imprimen sus comprobaciones y cierran con la ultima
    # que paso, asi que "las 31 escrituras estan clasificadas, sin sobras ni
    # faltas" se reportaba como el motivo de un rojo (medido el 26/09/2026 en
    # nueve de catorce fallos). Un motivo que describe algo que SALIO BIEN es
    # peor que ninguno: manda a buscar donde no esta.
    for linea in reversed(lineas):
        limpia = linea.strip()
        if _MARCA_DE_FALLO.search(limpia) and limpia.strip("=-_ "):
            return limpia[:160]
    for linea in reversed(lineas):
        limpia = linea.strip()
        if not limpia.strip("=-_ "):          # solo barras: no explica nada
            continue
        if limpia.startswith("Traceback ("):   # el encabezado, no la causa
            continue
        if limpia.startswith(("[ok]", "[OK]", "- ", "  - ")):
            continue                           # una comprobacion que paso
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
    #  El orden importa y antes estaba al reves: si la prueba alcanzo a dar su
    #  propio veredicto en rojo, FALLO -- mencionar una frase de entorno no la
    #  vuelve inmedible. Al reves si vale: sin veredicto propio y con la frase,
    #  no se pudo medir.
    coincide = _FALTA_ENTORNO.search(salida)
    if coincide and not _VEREDICTO_PROPIO_EN_ROJO.search(salida):
        #  No fallo: no se pudo medir. Se devuelve como salteada, y el motivo
        #  dice QUE falto -- no siempre es la base. Antes decia "pide Postgres"
        #  para todo, asi que una guarda que necesitaba bash mandaba a revisar
        #  credenciales de base. Un motivo que describe el problema equivocado
        #  es la version de "un motivo que describe algo que salio bien": manda
        #  a buscar donde no esta.
        if "dependencia del entorno" in coincide.group(0).lower():
            motivo_entorno = ("pide una dependencia del entorno que no es la "
                              "base (lo dijo al correr)")
        else:
            motivo_entorno = "pide Postgres (lo dijo al correr, no se leia en el codigo)"
        return None, motivo_entorno, tardo
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
        ok, motivo, tardo = correr(archivo, tope_de(archivo, args.timeout))
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
