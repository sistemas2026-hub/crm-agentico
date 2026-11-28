# -*- coding: utf-8 -*-
"""
================================================================================
 MENSAJES AUTOMATICOS, CONTRA POSTGRESQL DE VERDAD  --  28/10/2026
================================================================================
    DBHOST=... DBNAME=... DBUSER=... DBPASSWORD=... py -3.13 tests/test_mensajes_automaticos_base.py

Sin las variables de conexion se SALTEA y lo dice (exit 0): no es un verde.
Necesita el esquema 'asistente' con 202610290900_mensajes_automaticos.sql y
los tenants de prueba de tests/test_encuestas_base.py.

  1. el mismo (evento, motivo) se reserva UNA vez, aun con diez a la vez;
  2. otro evento o otro motivo si se reserva;
  3. marcar solo mueve desde 'reservado';
  4. otra empresa no choca con esta (la unicidad es por empresa) ni la ve.
================================================================================
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}: esta prueba NO corrio")
    sys.exit(0)

import psycopg                                             # noqa: E402

from nucleo.persistencia import mensajes_automaticos as reg  # noqa: E402
from nucleo.persistencia.conexion import dsn               # noqa: E402

fallos: list[str] = []
T1, T2 = "prueba_encuestas", "prueba_encuestas_otra"


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def sql(texto, args=()):
    with psycopg.connect(dsn()) as con:
        filas = con.execute(texto, args)
        try:
            return filas.fetchall()
        except psycopg.ProgrammingError:
            return []


clave = f"caso:{uuid.uuid4()}"
resultados: list = []
hilos = [threading.Thread(target=lambda: resultados.append(
    reg.reservar(T1, "ticket_cerrado_cliente", clave, "ticket_cerrado"))) for _ in range(10)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
ids = [r for r in resultados if r]
revisar(len(ids) == 1 and resultados.count(None) == 9,
        "diez disparos a la vez del mismo motivo: UNA reserva", f"{resultados}")
revisar(reg.reservar(T1, "ticket_creado_cliente", clave, "x") is not None,
        "el mismo motivo en otro evento si se reserva")
revisar(reg.reservar(T1, "ticket_cerrado_cliente", f"caso:{uuid.uuid4()}", "x") is not None,
        "otro motivo del mismo evento tambien")

reg.marcar(T1, ids[0], "enviado", "wamid.Z")
reg.marcar(T1, ids[0], "fallido")
fila = sql("select estado, wamid, enviado_en is not null from asistente.mensajes_automaticos where id = %s",
           (ids[0],))[0]
revisar(fila == ("enviado", "wamid.Z", True), "enviado queda enviado: un 'fallido' despues no lo pisa", f"{fila}")

otra = reg.reservar(T2, "ticket_cerrado_cliente", clave, "ticket_cerrado")
revisar(otra is not None, "otra empresa con el mismo motivo es otro aviso (unicidad por empresa)")
reg.marcar(T2, ids[0], "fallido")
fila = sql("select estado from asistente.mensajes_automaticos where id = %s", (ids[0],))[0][0]
revisar(fila == "enviado", "otra empresa no puede marcar el aviso de esta (RLS)", f"{fila}")

cols = [r[0] for r in sql("""select column_name from information_schema.columns
                              where table_schema='asistente' and table_name='mensajes_automaticos'""")]
revisar(not any(c in cols for c in ("usuario_externo", "telefono", "para", "texto", "contenido")),
        "la tabla no guarda el numero ni el texto", f"{cols}")

sql("delete from asistente.mensajes_automaticos where clave like 'caso:%%'")
print(f"\n{'=' * 76}\n  {'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}\n{'=' * 76}")
sys.exit(1 if fallos else 0)
