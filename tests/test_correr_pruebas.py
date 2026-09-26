# -*- coding: utf-8 -*-
"""
================================================================================
 EL CORREDOR DE PRUEBAS TIENE QUE SABER QUE ESTA MIRANDO
================================================================================

Por que existe
--------------
`cli/correr_pruebas.py` es el que dice si el repositorio esta en verde, y
existe para hacer UNA distincion que D1 nombra explicitamente: **FALLO no es lo
mismo que NO SE PUDO CORRER**. Si esa distincion se rompe, el numero que reporta
deja de significar algo -- y nadie lo nota, porque el corredor es justamente lo
que se mira en vez de abrir los logs.

El 26/09/2026 se rompia de las dos maneras, medido sobre una corrida real de las
150 pruebas:

  1. Cinco pruebas decian "Conexion incompleta: falta DBNAME" --o sea, no se
     pudieron medir-- y el corredor las contaba como FALLO. Su patron conocia
     un mensaje de la capa de conexion y no el otro.
  2. El motivo que imprimia era, en nueve de catorce fallos, **una linea de
     OK**: estas pruebas van imprimiendo cada comprobacion y cierran con la
     ultima que paso, asi que "las 31 escrituras estan clasificadas, sin sobras
     ni faltas" se reportaba como la razon de un rojo. Un motivo que describe
     algo que salio BIEN es peor que ninguno: manda a buscar donde no esta.

Lo que se prueba aca son las dos funciones puras que deciden eso, invocadas de
verdad -- no una copia. Sin base, sin subprocesos y en milisegundos.

Uso
---
    py -3.13 tests/test_correr_pruebas.py
================================================================================
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

#: Se carga por ruta y no con 'import': el modulo es un CLI y al importarlo por
#: nombre ejecutaria su bloque de arranque.
_spec = importlib.util.spec_from_file_location(
    "correr_pruebas_bajo_prueba", RAIZ / "cli" / "correr_pruebas.py")
corredor = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(corredor)
except SystemExit:          # el CLI decide salir cuando nadie le pasa argumentos
    pass

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


print("=" * 74)
print(" EL CORREDOR DISTINGUE UN FALLO DE UN 'NO SE PUDO CORRER'")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n1. los dos mensajes de la capa de conexion son falta de entorno")

for mensaje in ("No hay datos de conexion en el entorno. Definir DBHOST, DBPORT...",
                "Conexion incompleta: falta DBNAME en el entorno. Se necesitan las cinco: "
                "DBHOST, DBPORT, DBNAME, DBUSER, DBPASSWORD.",
                "could not connect to server: Connection refused",
                'connection to server at "localhost" failed'):
    comprobar(bool(corredor._FALTA_ENTORNO.search(mensaje)),
              f"se reconoce: {mensaje[:52]}...")

# Y no cualquier cosa: un fallo de verdad NO puede leerse como falta de entorno,
# porque entonces se contaria como salteado y el rojo desapareceria del informe.
for mensaje in ("  [FALLA] la cifra de escaladas viaja igual",
                "AssertionError: esperaba 3 y dio 10",
                "  [FALLA] el umbral efectivo se acota al del cierre"):
    comprobar(not corredor._FALTA_ENTORNO.search(mensaje),
              f"NO se confunde con entorno: {mensaje.strip()[:48]}...")

# ---------------------------------------------------------------------------
print("\n2. el motivo es el fallo, no la ultima linea que quedo impresa")

salida_tipica = [
    "  [ok]   las 31 escrituras estan clasificadas, sin sobras ni faltas",
    "  [FALLA] la cifra de escaladas viaja igual",
    "  [ok]   ninguna herramienta de escritura quedo sin clase de riesgo",
    "======================================================================",
    "  - las otras 24 escrituras NO son irreversibles",
]
motivo = corredor._primer_motivo_legible(salida_tipica)
comprobar("[FALLA]" in motivo and "escaladas" in motivo,
          "con un [FALLA] en el medio, el motivo es ESE y no la ultima linea",
          f"dio {motivo!r}")

comprobar("31 escrituras" not in motivo and "24 escrituras" not in motivo,
          "y nunca una comprobacion que PASO: eso manda a buscar donde no esta")

# Un traceback: el encabezado no explica nada, la excepcion si.
traza = ["Traceback (most recent call last):",
         '  File "x.py", line 3, in <module>',
         "TypeError: '>' not supported between instances of 'NoneType' and 'int'"]
comprobar("TypeError" in corredor._primer_motivo_legible(traza),
          "en un traceback el motivo es la excepcion, no el encabezado",
          f"dio {corredor._primer_motivo_legible(traza)!r}")

# Solo lineas de OK: mejor vacio que un motivo falso. Quien llama pone el codigo
# de salida, que no explica pero tampoco miente.
comprobar(corredor._primer_motivo_legible(
              ["  [ok]   algo bien", "  - otra cosa bien", "===="]) == "",
          "si no hay ninguna linea de fallo, el motivo queda VACIO")

comprobar(corredor._primer_motivo_legible([]) == "",
          "y una salida vacia no revienta")

# El timeout tambien es un motivo legible, y no un fallo de la prueba.
comprobar("colgo" in corredor._primer_motivo_legible(["se colgo: mas de 180s"]),
          "un cuelgue se reporta como lo que es")

print("\n" + "=" * 74)
if fallos:
    print(f"[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("[OK] El corredor separa lo que fallo de lo que no se pudo medir, y dice por que.")
