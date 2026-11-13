# -*- coding: utf-8 -*-
"""
Un turno de las 7 de la tarde no puede aparecer en el dia siguiente.

    py -3.13 tests/test_frontera_de_dia.py

La primera mitad corre SIN RED Y SIN BASE. La segunda evalua la expresion
real en Postgres -- sin tocar ninguna tabla, es aritmetica de fechas -- y se
salta con aviso si no hay base a mano.

QUE PASO
--------
El 07/09/2026 se agrego al informe de turnos la agrupacion por dia en hora de
Colombia, precisamente para que la tarde de un ISP colombiano no quedara
mezclada con la manana del dia siguiente. Se escribio asi:

    (creado_en at time zone 'UTC' at time zone 'America/Bogota')::date

y hace lo contrario de lo que dice. 'creado_en' ya es timestamptz: el primer
'at time zone' le QUITA la zona, y el segundo lee ese valor sin zona COMO SI
fuera hora de Bogota y lo convierte de vuelta. Resultado: suma cinco horas en
vez de restarlas. Los turnos de las 6 de la tarde del 07 salieron fechados el
08.

POR QUE MERECE UN TEST Y NO UN COMENTARIO
-----------------------------------------
No lanza ningun error. No deja ninguna fila mal. El informe se ve
perfectamente bien, con totales que suman, y cuenta una historia falsa. Es la
peor clase de bug que puede tener un instrumento de medicion: el unico
sintoma es que las conclusiones son equivocadas, y eso se descubre --si se
descubre-- semanas despues.

Y va a volver: 'at time zone UTC at time zone X' se lee como "de UTC a X",
que es exactamente lo que uno quiere decir. Suena bien y esta mal.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fallos: list[str] = []


def revisar(ok: bool, que: str, detalle: str = "") -> None:
    if ok:
        print(f"  ok     {que}")
    else:
        fallos.append(que)
        print(f"  FALLA  {que}" + (f"\n         {detalle}" if detalle else ""))


# =============================================================================
#  1. Sin base: la forma de doble conversion no puede reaparecer
# =============================================================================

INFORME = RAIZ / "cli" / "medir_turnos.py"
fuente = INFORME.read_text(encoding="utf-8")

# Se busca sobre el SQL, no sobre el archivo entero: el comentario que explica
# el bug CONTIENE la forma mala a proposito, y sin esto el test fallaria por
# la explicacion de lo que esta bien hecho. Ya paso una vez, en
# test_tomar_no_es_resolver.py, por el mismo motivo.
sql = "\n".join(l for l in fuente.splitlines() if not l.lstrip().startswith("#"))

dobles = re.findall(r"at time zone\s+\S+\s+at time zone", sql)
revisar(not dobles,
        "el informe no convierte la zona dos veces seguidas",
        f"{dobles}: sobre una columna timestamptz eso SUMA el desfase en vez "
        f"de restarlo. Basta un 'at time zone' con la zona destino.")

conversiones = len(re.findall(r"at time zone", sql))
revisar(conversiones >= 3,
        f"las {conversiones} agrupaciones por dia siguen convirtiendo la zona",
        "Si bajo a 0, alguna consulta volvio a agrupar en UTC -- que es el "
        "problema original, no el arreglo.")

revisar('ZONA = "America/Bogota"' in fuente and "Dias en" in fuente,
        "el informe dice en que zona agrupa",
        "Dentro de un mes nadie va a recordar con que frontera de dia se "
        "agruparon estos numeros.")


# =============================================================================
#  2. Contra Postgres: la expresion real, en los dos bordes
# =============================================================================
#  Es aritmetica de fechas: no lee ninguna tabla ni escribe nada.

CASOS = [
    # (instante UTC,           dia esperado en Bogota,  por que)
    ("2026-09-08 00:30+00", "2026-09-07", "7:30 PM del 07 en Bogota: es el 07"),
    ("2026-09-08 04:59+00", "2026-09-07", "11:59 PM del 07: todavia es el 07"),
    ("2026-09-08 05:00+00", "2026-09-08", "medianoche del 08: ya es el 08"),
    ("2026-09-07 23:59+00", "2026-09-07", "6:59 PM del 07, el caso que fallo"),
]

try:
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env", override=False)
    from nucleo.persistencia.db import sesion
    with sesion("rapilink") as (cur, _org):
        for instante, esperado, porque in CASOS:
            cur.execute(
                "select (%s::timestamptz at time zone 'America/Bogota')::date d",
                (instante,))
            dio = str(cur.fetchone()["d"])
            revisar(dio == esperado,
                    f"{instante} agrupa en {esperado}  ({porque})",
                    f"agrupo en {dio}")

        # Y que el test DISCRIMINE: la forma vieja tiene que dar mal. Sin
        # esto, un test que pasa no prueba nada -- podria estar comprobando
        # una expresion que da bien de las dos maneras.
        cur.execute(
            "select (%s::timestamptz at time zone 'UTC' "
            "        at time zone 'America/Bogota')::date d",
            ("2026-09-08 00:30+00",))
        malo = str(cur.fetchone()["d"])
        revisar(malo == "2026-09-08",
                "la forma vieja sigue dando mal (el test distingue las dos)",
                f"la doble conversion dio {malo}, y se esperaba que diera el "
                f"dia equivocado (2026-09-08). Si ahora da bien, este test "
                f"dejo de proteger de nada y hay que revisarlo.")
except Exception as e:
    print(f"\n  [sin base] no se pudo comprobar contra Postgres "
          f"({type(e).__name__}: {str(e)[:70]}).")
    print("  Las comprobaciones estaticas de arriba SI corrieron, pero la "
          "expresion\n  real no se evaluo. Correrlo con base antes de "
          "confiar en el informe.")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] La tarde del 7 se cuenta en el 7.")
