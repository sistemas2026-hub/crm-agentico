# -*- coding: utf-8 -*-
"""
El CLI del importador ARRANCA de verdad, y el reloj encuentra lo que llama.

    py -3.13 tests/test_cli_importacion_arranca.py

POR QUE EXISTE
--------------
El 09/09/2026 el dry-run en produccion murio antes de hacer nada:

    ImportError: cannot import name 'aplicar'
    from 'nucleo.seguimiento.importacion_io'

Un script de parche mio corto un rango de lineas que se llevo puestas
'aplicar' y 'aplicar_reconciliacion'. El CLI las importaba y el reloj llamaba
a la primera desde 'barrido'.

Y la suite entera siguio en verde: 80 comprobaciones del importador, 53 del
writer, 814 de cases. Ninguna importaba 'importacion_io' -- las del motor
prueban 'importacion.py', que es puro, y la guarda de arquitectura lee el
archivo como TEXTO, no lo importa. O sea que existia cobertura sobre lo que el
modulo dice y ninguna sobre si se puede cargar.

Esta prueba cierra ese hueco por los dos lados: importa los modulos de verdad
y arranca el entrypoint como proceso.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


# --- 1. los nombres que el CLI consume existen de verdad ------------------

print("\nlos modulos se pueden importar")

# Se importan los nombres UNO POR UNO, igual que hace el CLI. Un
# 'import importacion_io' a secas pasaria aunque faltara media docena de
# funciones.
try:
    from nucleo.seguimiento.importacion_io import (  # noqa: F401
        aplicar, aplicar_reconciliacion, barrido, casos_de_este_proveedor,
        leer_ticket, listar_tickets, resolver_servicios, tickets_conocidos)
    revisar(True, "importacion_io exporta las ocho funciones que se le piden")
except ImportError as e:
    revisar(False, "importacion_io exporta las ocho funciones que se le piden",
            f"{e}")


# --- 2. lo que el CLI declara importar es lo que existe --------------------

fuente_cli = (RAIZ / "cli" / "importar_tickets.py").read_text(encoding="utf-8")
bloque = fuente_cli.split("from nucleo.seguimiento.importacion_io import")[1]
bloque = bloque[:bloque.index(")")]
pedidos = {x.strip().rstrip(",") for x in bloque.replace("(", "").replace(
    "# noqa: E402", "").split(",") if x.strip()}
pedidos = {p for p in pedidos if p and p.isidentifier()}

import nucleo.seguimiento.importacion_io as io_mod  # noqa: E402

faltan = sorted(p for p in pedidos if not hasattr(io_mod, p))
revisar(not faltan,
        f"el CLI pide {len(pedidos)} nombres y todos existen",
        f"faltan: {faltan}")


# --- 3. el reloj tambien --------------------------------------------------

# El reloj se mudo a su propio modulo el 10/09/2026 (servicio 'motor-reloj'):
# dentro de api.py nunca corrio bajo gunicorn. Esta comprobacion tiene que
# seguirlo, o pasa por vacio -- que es peor que fallar.
fuente_reloj = (RAIZ / "nucleo" / "reloj.py").read_text(encoding="utf-8")
# Con expresion regular y no partiendo cadenas: el troceo ingenuo levantaba
# tambien las menciones en prosa ("...lo hace 'importacion_io.barrido'.") y
# pedia que existiera un atributo llamado "barrido'.".
import re  # noqa: E402

usados = set(re.findall(r"importacion_io\.([A-Za-z_][A-Za-z0-9_]*)", fuente_reloj))
faltan_reloj = sorted(u for u in usados if not hasattr(io_mod, u))
revisar(not faltan_reloj,
        f"el reloj usa {sorted(usados)} y existen",
        f"faltan: {faltan_reloj}")

# 'barrido' llama a 'aplicar' por dentro: el reloj se habria roto igual aunque
# solo importara 'barrido'.
revisar("aplicar(" in (RAIZ / "nucleo" / "seguimiento"
                       / "importacion_io.py").read_text(encoding="utf-8"),
        "y 'barrido' encuentra el 'aplicar' que llama por dentro")


# --- 4. el entrypoint arranca como PROCESO --------------------------------

print("\nel entrypoint arranca")

r = subprocess.run([sys.executable, str(RAIZ / "cli" / "importar_tickets.py"), "--help"],
                   capture_output=True, text=True, timeout=120, cwd=str(RAIZ))
revisar(r.returncode == 0,
        "'importar_tickets.py --help' termina en 0",
        (r.stderr or r.stdout)[-400:])
revisar("--aplicar" in r.stdout and "--piloto" in r.stdout,
        "y la ayuda muestra las banderas reales",
        "si no las muestra, argparse no llego a construirse")

# Sin red y sin base: '--help' sale antes de conectarse a nada. Lo que esto
# prueba es que TODOS los imports del archivo se resolvieron.
revisar("ImportError" not in r.stderr and "ModuleNotFoundError" not in r.stderr,
        "sin ImportError ni ModuleNotFoundError al cargar el CLI")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] El CLI carga, el reloj encuentra lo que llama, y el entrypoint arranca.")
