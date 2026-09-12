# -*- coding: utf-8 -*-
"""
================================================================================
 LA VENTANA DE BYPASSRLS DEL MOTOR  --  una consulta, no todo el proceso
================================================================================

    py -3.13 tests/test_motor_no_se_queda_con_bypassrls.py

Por que existe
--------------
'motor_user' tiene BYPASSRLS, y hay un motivo: 'nucleo/persistencia/db.py::
_organizacion()' averigua a que organizacion pertenece un tenant ANTES de poder
fijar cual, asi que esa consulta no puede depender de que ya este fijado.

Pero "una consulta necesita bypass" no puede convertirse en "todo el proceso
corre con bypass". 'sesion()' baja a 'app_backend' en la linea siguiente, y a
partir de ahi RLS acota todo. Lo que lo rompe es abrir una conexion por fuera:
esa se queda arriba.

Y pasaba. 'importacion_io.py' abria una conexion cruda y leia:

    select trim(ticket_operativo) from asistente.conversations
    where coalesce(trim(ticket_operativo),'') <> ''

Sin filtro de organizacion, con BYPASSRLS puesto: los numeros de ticket de
TODAS las empresas. Con un solo tenant no se nota; con dos, clasificaria como
"lo abrio Dexter" un ticket que abrio el Dexter de otra empresa.

La tabla tenia RLS habilitado Y forzado todo el tiempo. La politica estaba: lo
que faltaba era bajar de rol.

Lo que se fija
--------------
1. Hay UNA sola 'psycopg.connect' en todo 'nucleo/', y es la de 'sesion()'.
2. 'sesion()' baja de rol y fija el tenant, en ese orden, antes de entregar
   el cursor.
3. La consulta que necesita el bypass es una sola, parametrizada.
4. No hay SQL dinamico en el motor.
================================================================================
"""

from __future__ import annotations

import re
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


def fuentes_del_motor():
    for ruta in sorted((RAIZ / "nucleo").rglob("*.py")):
        if "__pycache__" in str(ruta):
            continue
        yield ruta, ruta.read_text(encoding="utf-8", errors="replace")


print("=" * 74)
print("  una sola conexion, y baja de rol enseguida")
print("=" * 74)

# --- 1: una sola puerta -----------------------------------------------------
conexiones = []
for ruta, texto in fuentes_del_motor():
    for n, linea in enumerate(texto.splitlines(), 1):
        if "psycopg.connect" in linea and not linea.strip().startswith("#"):
            rel = ruta.relative_to(RAIZ).as_posix()   # Windows usa "\\"
            conexiones.append(f"{rel}:{n}")

revisar(len(conexiones) == 1
        and conexiones[0].startswith("nucleo/persistencia/db.py"),
        "hay UNA sola psycopg.connect en nucleo/, y esta en db.py",
        f"encontradas: {conexiones}\n         Una conexion abierta por fuera de "
        f"'sesion()' se queda con BYPASSRLS puesto y lee todas las empresas.")

# --- 2: sesion() baja de rol ANTES de entregar el cursor --------------------
db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
cuerpo = db[db.index("def sesion("):]
cuerpo = cuerpo[:cuerpo.index("\ndef ", 10)]

pos_org = cuerpo.find("_organizacion(")
pos_rol = cuerpo.find("set local role app_backend")
pos_tenant = cuerpo.find("app.current_tenant")
pos_yield = cuerpo.find("yield")

revisar(pos_rol > 0, "sesion() baja el rol a app_backend")
revisar(pos_tenant > 0, "y fija el tenant en la sesion")
revisar(0 < pos_org < pos_rol,
        "la consulta que necesita el bypass corre ANTES de bajar de rol",
        "si corriera despues, app_backend no podria resolver el tenant y "
        "nada funcionaria -- el orden es la razon de todo el diseno")
revisar(pos_rol < pos_yield and pos_tenant < pos_yield,
        "y las dos cosas pasan ANTES de entregar el cursor",
        f"rol en {pos_rol}, tenant en {pos_tenant}, yield en {pos_yield}: "
        f"si el yield fuera antes, el llamante recibiria una conexion con "
        f"BYPASSRLS puesto")

# --- 3: la consulta del bypass es una sola, y parametrizada -----------------
org_fn = db[db.index("def _organizacion("):]
org_fn = org_fn[:org_fn.index("\n@contextmanager")]
ejecuta = re.findall(r"cur\.execute\(", org_fn)
revisar(len(ejecuta) == 1,
        "la ventana de bypass es UNA sola consulta",
        f"encontradas {len(ejecuta)}: cada una mas es una lectura sin RLS")
revisar("%s" in org_fn and "(tenant,)" in org_fn,
        "y esta parametrizada",
        "un slug concatenado ahi seria inyeccion con BYPASSRLS puesto")

# --- 4: nada de SQL dinamico en el motor ------------------------------------
print()
print("=" * 74)
print("  ningun SQL armado con texto")
print("=" * 74)

sospechosas = []
patron = re.compile(r"execute\(\s*f[\"']|execute\([^)]*\+\s*[a-z_]")
for ruta, texto in fuentes_del_motor():
    for n, linea in enumerate(texto.splitlines(), 1):
        if patron.search(linea) and not linea.strip().startswith("#"):
            sospechosas.append(
                f"{ruta.relative_to(RAIZ).as_posix()}:{n}: {linea.strip()[:70]}")

revisar(not sospechosas,
        "ninguna consulta se arma concatenando o con f-string",
        "\n         ".join(sospechosas))

# --- 5: la consulta que estaba suelta -------------------------------------
print()
print("=" * 74)
print("  la consulta que leia las conversaciones de todas las empresas")
print("=" * 74)

imp = (RAIZ / "nucleo" / "seguimiento"
       / "importacion_io.py").read_text(encoding="utf-8")
revisar("asistente.conversations" in imp,
        "la consulta sigue existiendo (no se resolvio borrandola)")
revisar("with sesion(tenant)" in imp,
        "y ahora corre dentro de sesion(tenant), o sea como app_backend",
        "con una conexion cruda leia los numeros de ticket de TODAS las "
        "empresas: no es solo una lectura cruzada, es una clasificacion de "
        "autoria equivocada entre empresas")

i = imp.find("asistente.conversations")
tramo = imp[max(0, i - 900):i]
revisar("psycopg.connect" not in tramo,
        "y no queda una conexion cruda al lado")

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] El bypass del motor dura una consulta, no todo el proceso.")
print("=" * 74)
