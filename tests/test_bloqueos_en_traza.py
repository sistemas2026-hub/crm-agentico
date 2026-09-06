# -*- coding: utf-8 -*-
"""
Un bloqueo del propio codigo NO es un fallo de un sistema externo.

    py -3.13 tests/test_bloqueos_en_traza.py

POR QUE EXISTE
--------------
Son dos cosas opuestas y hasta el 06/09/2026 se veian iguales en la traza:

    la API del ISP devolvio 400   -> algo se rompio, hay que reportarlo
    el codigo freno la accion     -> la proteccion funciono como debia

Quien atiende tiene que hacer cosas contrarias en cada caso. Verlos con la
misma X lleva justo a la reaccion equivocada.

Peor todavia: IDENTIDAD_NO_VERIFICADA se excluia del registro A PROPOSITO,
con un razonamiento que era correcto mientras la traza fuera una lista de
exitos y fallos, y dejo de serlo en cuanto la pantalla cuenta los bloqueos.
Medido antes del cambio: 570 llamadas registradas, CERO bloqueos. No porque
no ocurrieran.

Este test corre SIN RED y SIN BASE: no llama al modelo ni a WispHub. Lo que
fija es que los seis codigos de gate esten clasificados como bloqueo, y que
ningun mensaje de excepcion de un tercero se cuele en esa lista.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nucleo.modelo.motor import CODIGOS_DE_BLOQUEO  # noqa: E402

fallos: list[str] = []


def revisar(condicion: bool, descripcion: str, detalle: str = "") -> None:
    if condicion:
        print(f"  ok     {descripcion}")
    else:
        fallos.append(f"{descripcion}{(' -- ' + detalle) if detalle else ''}")
        print(f"  FALLA  {descripcion}" + (f"\n         {detalle}" if detalle else ""))


# --- 1. los seis gates que produce el motor estan todos clasificados -------
# Si alguien agrega un gate nuevo en motor.py y no lo suma a la lista, su
# bloqueo se va a contar como "error en herramienta" y el panel va a decir
# que fallo un sistema externo cuando no fallo nada.
ESPERADOS = {
    "IDENTIDAD_NO_VERIFICADA",
    "IDENTIDAD_NO_RESUELTA",
    "PRECONDICION_NO_CUMPLIDA",
    "FALTA_HABLAR_CON_EL_CLIENTE",
    "HERRAMIENTA_DESCONOCIDA",
    "LIMITE_DE_CONVERSACION",
}
faltan = ESPERADOS - CODIGOS_DE_BLOQUEO
revisar(not faltan, "los seis codigos de gate cuentan como bloqueo",
        f"sin clasificar: {sorted(faltan)}" if faltan else "")


# --- 2. la lista se lee del CODIGO FUENTE, no de la memoria de nadie ------
# Un codigo que motor.py asigna a 'codigo_error' y que no esta en la lista es
# exactamente el agujero que este test tiene que ver. Se busca la forma
# literal 'codigo_error = "ALGO_ASI"' en el fuente y se compara.
import re  # noqa: E402

fuente = (RAIZ / "nucleo" / "modelo" / "motor.py").read_text(encoding="utf-8")
asignados = set(re.findall(r'codigo_error\s*=\s*"([A-Z_]{6,})"', fuente))
huerfanos = asignados - CODIGOS_DE_BLOQUEO
revisar(
    not huerfanos,
    "ningun codigo de gate quedo fuera de CODIGOS_DE_BLOQUEO",
    f"motor.py asigna {sorted(huerfanos)} y no estan clasificados. "
    "Si son bloqueos, sumarlos a la lista Y a MOTIVO_BLOQUEO en la pantalla "
    "de conversaciones; si son errores de verdad, decirlo aca."
    if huerfanos else "")


# --- 3. un error de un tercero NUNCA es un bloqueo -------------------------
# 'codigo_error' es texto libre y ahi conviven los codigos de gate con
# mensajes de excepcion enteros. Estos son los que hay de verdad en la base.
DE_TERCEROS = [
    "ErrorHerramientaHttp: 400 Client Error",
    "HTTPError: 500 Server Error for url",
    "ConnectionError",
    "ReadTimeout",
]
coladas = [e for e in DE_TERCEROS if e in CODIGOS_DE_BLOQUEO]
revisar(not coladas, "un fallo de un sistema externo no se cuenta como bloqueo",
        f"clasificados mal: {coladas}" if coladas else "")


# --- 4. la pantalla sabe explicar los seis, no solo contarlos --------------
# Un contador que dice "1 accion bloqueada" sin decir cual sirve de poco:
# lo que cambia lo que hace quien atiende es el motivo. Si se agrega un gate
# y nadie escribe su frase, la pantalla cae a un texto generico -- esto lo
# avisa antes de que pase.
pantalla = (RAIZ / "django-crm" / "frontend" / "src" / "routes" / "(app)"
            / "conversaciones" / "[id]" / "+page.svelte").read_text(encoding="utf-8")
sin_frase = sorted(c for c in CODIGOS_DE_BLOQUEO if f"{c}:" not in pantalla)
revisar(not sin_frase, "cada bloqueo tiene su motivo en palabras en la pantalla",
        f"sin traducir en MOTIVO_BLOQUEO: {sin_frase}" if sin_frase else "")


# --- 5. la base guarda la marca ---------------------------------------------
# Sin la columna no hay nada que contar. Se comprueba contra el archivo de
# migracion, no contra la base: este test corre sin conexion.
sql = (RAIZ / "supabase" / "202609061400_bloqueos_en_traza.sql")
revisar(sql.exists() and "es_bloqueo" in sql.read_text(encoding="utf-8"),
        "existe la migracion que agrega la columna es_bloqueo")

escritura = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
revisar("es_bloqueo" in escritura,
        "la escritura de la traza persiste es_bloqueo",
        "db.py no menciona la columna: el motor la calcularia y se perderia")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Los bloqueos del codigo no se confunden con fallos de terceros.")
