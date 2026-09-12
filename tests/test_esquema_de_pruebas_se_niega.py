# -*- coding: utf-8 -*-
"""
================================================================================
 EL PREPARADOR DE BASES SE NIEGA  --  cinco defensas, ninguna saltable
================================================================================

    py -3.13 tests/test_esquema_de_pruebas_se_niega.py

Por que existe
--------------
'cli/esquema_de_pruebas.py' CREA Y ESCRIBE ESQUEMA. Su primera version confiaba
en que DBHOST fuera 'localhost', y eso no es una defensa: 'localhost' puede ser
la punta de un tunel SSH contra la base de produccion. Tambien puede ser una
base local que a alguien le importa.

Las cinco condiciones son simultaneas y no hay '--force'. Un '--force'
convierte cinco defensas en cero el dia que alguien tiene prisa, que es
justamente el dia en que hacen falta.

  1. bandera explicita        ALLOW_EPHEMERAL_TEST_DB_SETUP=1
  2. DSN dado a mano          no se lee el .env, nunca
  3. nombre con prefijo       la unica condicion que un tunel no satisface solo
  4. lo que dice la base      current_database() y current_user, no el entorno
  5. marcador de la propia    una base poblada y ajena no se toca
     herramienta

La tercera es la que carga el peso: las variables se pueden equivocar, el
hostname se puede tunelizar, pero el nombre de la base sale del servidor.
================================================================================
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cli.esquema_de_pruebas as prep                            # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


def con_entorno(**valores):
    """Un entorno controlado: lo que no se pasa, se borra."""
    previo = {}
    claves = {"ALLOW_EPHEMERAL_TEST_DB_SETUP", "DBHOST", "DBPORT", "DBNAME",
              "DBUSER", "DBPASSWORD"}
    for k in claves:
        previo[k] = os.environ.pop(k, None)
    for k, v in valores.items():
        if v is not None:
            os.environ[k] = v
    return previo


def restaurar(previo):
    for k, v in previo.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v


def rechaza(motivo_esperado: str, **entorno) -> tuple[bool, str]:
    """True si '_dsn()' se niega. Devuelve tambien el mensaje."""
    previo = con_entorno(**entorno)
    try:
        prep._dsn()
        return False, "NO se nego"
    except SystemExit as e:
        texto = str(e)
        return (motivo_esperado.lower() in texto.lower()), texto.splitlines()[0]
    finally:
        restaurar(previo)


COMPLETO = dict(ALLOW_EPHEMERAL_TEST_DB_SETUP="1", DBHOST="localhost",
                DBPORT="55435", DBNAME="test_motor", DBUSER="u",
                DBPASSWORD="p")

print("=" * 74)
print("  lo que el preparador RECHAZA")
print("=" * 74)

# --- 1: sin la bandera ------------------------------------------------------
ok, msg = rechaza("ALLOW_EPHEMERAL_TEST_DB_SETUP",
                  **{**COMPLETO, "ALLOW_EPHEMERAL_TEST_DB_SETUP": None})
revisar(ok, "sin la bandera explicita no corre", msg)

# --- 2: DSN incompleto ------------------------------------------------------
ok, msg = rechaza("Faltan", **{**COMPLETO, "DBPASSWORD": None})
revisar(ok, "con el DSN incompleto no corre", msg)

# --- 3: no toma credenciales del .env ---------------------------------------
previo = con_entorno(ALLOW_EPHEMERAL_TEST_DB_SETUP="1")
try:
    hubo_negativa = False
    try:
        prep._dsn()
    except SystemExit:
        hubo_negativa = True
    revisar(hubo_negativa,
            "con el entorno vacio NO cae al .env: se niega",
            "si leyera el .env apuntaria a la base real")
finally:
    restaurar(previo)

fuente = (RAIZ / "cli" / "esquema_de_pruebas.py").read_text(encoding="utf-8")
revisar("load_dotenv" not in fuente and '".env"' not in fuente,
        "y ni siquiera importa dotenv",
        "cualquier camino que lea el .env es un camino a produccion")

# --- 4: nombres de base reales ----------------------------------------------
for prohibido in ("postgres", "crm_db", "rapilink", "production", "prod"):
    ok, msg = rechaza("prohibid", **{**COMPLETO, "DBNAME": prohibido})
    revisar(ok, f"rechaza DBNAME='{prohibido}'", msg)

# --- 5: localhost con nombre no permitido (el tunel simulado) ---------------
ok, msg = rechaza("no empieza por", **{**COMPLETO, "DBHOST": "localhost",
                                "DBNAME": "supabase_main"})
revisar(ok,
        "localhost con un nombre de base ajeno se rechaza (tunel simulado)",
        msg)

ok, msg = rechaza("no empieza por", **{**COMPLETO, "DBHOST": "127.0.0.1",
                                "DBNAME": "clientes"})
revisar(ok, "y 127.0.0.1 tampoco basta por si solo", msg)

# --- 6: un host remoto con nombre de pruebas --------------------------------
# El host remoto YA NO es la defensa: lo es el nombre. Se deja escrito que un
# remoto con nombre de pruebas pasa la comprobacion de variables, y que lo que
# lo detiene despues es 'confirmar_destino', que pregunta a la base.
previo = con_entorno(**{**COMPLETO, "DBHOST": "db.ejemplo.com"})
try:
    paso = True
    try:
        prep._dsn()
    except SystemExit:
        paso = False
    revisar(paso,
            "un host remoto con nombre de pruebas pasa la comprobacion de "
            "variables -- a proposito",
            "lo detiene 'confirmar_destino', que pregunta a la BASE y no al "
            "entorno")
finally:
    restaurar(previo)

# --- 7: el que si tiene que pasar -------------------------------------------
previo = con_entorno(**COMPLETO)
try:
    dsn = prep._dsn()
    revisar("dbname=test_motor" in dsn, "un destino valido si arma el DSN", dsn)
    revisar("password=p" in dsn, "y lleva la credencial que se le dio")
finally:
    restaurar(previo)

# --- 8: no existe una puerta trasera ----------------------------------------
print()
print("=" * 74)
print("  no hay forma de saltarse las defensas")
print("=" * 74)

# 'force' aparece UNA vez, en el comentario que explica por que no existe la
# opcion. Lo que se prohibe es que el programa la LEA, no que la nombre.
lee_force = any(p in fuente for p in ('"--force"', "'--force'",
                                      'argv and "--force"', 'FORCE ='))
revisar(not lee_force,
        "el programa no lee ninguna opcion --force",
        "cinco defensas con un escape son cero defensas")
revisar("force" not in fuente.lower(),
        "y la palabra no aparece en el archivo ni como opcion ni como texto",
        f"aparece {fuente.lower().count('force')} vez/veces")

for pieza in ("BANDERA", "PREFIJOS_PERMITIDOS", "NOMBRES_PROHIBIDOS",
              "TABLA_MARCADOR", "confirmar_destino", "comprobar_marcador"):
    revisar(pieza in fuente, f"la defensa '{pieza}' sigue en el archivo")

revisar("confirmar_destino(conn)" in fuente and "comprobar_marcador(conn)" in fuente,
        "y las dos que preguntan a la base se llaman antes de escribir",
        "declararlas y no llamarlas es el error que este proyecto ya cometio "
        "con la reconciliacion")

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] El preparador se niega a todo lo que no sea una base de pruebas.")
print("=" * 74)
