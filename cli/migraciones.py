# -*- coding: utf-8 -*-
"""
================================================================================
 ESTADO DE LAS MIGRACIONES  --  contra el esquema real, sin registro que mentir
================================================================================

Por que existe
--------------
Las migraciones de supabase/ se aplican A MANO y no habia forma de saber cuales
estaban puestas. El 25/08/2026 se descubrio que DOS nunca se habian aplicado en
produccion:

  18_caso_conversacion.sql   -> conversations.caso_manual
  20_resumen_conversacion.sql -> conversations.resumen

Las dos funciones que dependian de esas columnas venian fallando desde el dia
que se desplegaron. No se noto porque las dos escrituras estan envueltas en
try/except a proposito -- 'marcar_caso' y 'guardar_resumen' no deben romper el
turno de un cliente por no poder guardar una etiqueta. Correcto como decision,
y justamente por eso el fallo era invisible: cada turno clasificaba la
conversacion, intentaba guardarla, fallaba y seguia como si nada.

Por que NO lleva una tabla de registro
--------------------------------------
Lo primero que uno hace es crear 'migraciones_aplicadas' y marcar las 27 como
puestas. Eso habria tapado el problema en vez de encontrarlo: las dos que
faltaban se habrian marcado igual que el resto, y el registro diria que todo
esta bien mientras dos columnas siguen sin existir.

Un registro es una AFIRMACION sobre la base; el esquema es la base. Asi que
esto lee cada .sql, saca que objetos dice crear, y va a ver si estan. No hay
nada que se pueda desincronizar, ni que rellenar a mano, ni en lo que confiar.

Tampoco sirve re-correr todas por las dudas: 13 de las 27 traen sentencias que
no son idempotentes (politicas RLS, sobre todo), asi que aplicar a ciegas
revienta.

Uso
---
    py -3.13 cli/migraciones.py              # que falta
    py -3.13 cli/migraciones.py --detalle    # ademas, objeto por objeto
    py -3.13 cli/migraciones.py --aplicar    # corre SOLO las que les falta algo
================================================================================
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# override=False por el mismo motivo que en cli/cargar_config.py: un .env viejo
# no debe ganarle a lo que el entorno del despliegue declara.
load_dotenv(RAIZ / ".env", override=False)

from nucleo.persistencia.conexion import dsn        # noqa: E402

MIGRACIONES = RAIZ / "supabase"

# Los comentarios de SQL se sacan antes de buscar nada: varias migraciones
# explican en prosa que crean, y esas frases matchean los mismos patrones.
_COMENTARIO = re.compile(r"--[^\n]*")
_TABLA = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?([a-z_]+\.[a-z_]+)", re.I)
_INDICE = re.compile(r"create\s+(?:unique\s+)?index\s+(?:if\s+not\s+exists\s+)?([a-z_]+)", re.I)
_FUNCION = re.compile(r"create\s+(?:or\s+replace\s+)?function\s+([a-z_]+\.[a-z_]+)", re.I)
_ALTER = re.compile(r"alter\s+table\s+(?:if\s+exists\s+)?([a-z_]+\.[a-z_]+)", re.I)
_COLUMNA = re.compile(r"add\s+column\s+(?:if\s+not\s+exists\s+)?([a-z_]+)", re.I)


def objetos_de(sql: str) -> list[tuple[str, str]]:
    """
    Que dice crear esta migracion, como [(tipo, identificador), ...].

    Las columnas necesitan saber a que tabla pertenecen, y eso solo se sabe
    leyendo en orden: cada 'add column' cuelga del ultimo 'alter table' que se
    vio. Por eso se recorre el texto posicionalmente y no con findall suelto.
    """
    limpio = _COMENTARIO.sub("", sql)
    hallazgos: list[tuple[str, str]] = []

    for m in _TABLA.finditer(limpio):
        hallazgos.append(("tabla", m.group(1).lower()))
    for m in _FUNCION.finditer(limpio):
        hallazgos.append(("funcion", m.group(1).lower()))
    for m in _INDICE.finditer(limpio):
        hallazgos.append(("indice", m.group(1).lower()))

    tabla_actual = None
    for m in re.finditer(r"alter\s+table[^;]*?;|add\s+column\s+(?:if\s+not\s+exists\s+)?[a-z_]+",
                         limpio, re.I | re.S):
        texto = m.group(0)
        alter = _ALTER.search(texto)
        if alter:
            tabla_actual = alter.group(1).lower()
        for col in _COLUMNA.finditer(texto):
            if tabla_actual:
                hallazgos.append(("columna", f"{tabla_actual}.{col.group(1).lower()}"))

    # Sin duplicar, conservando el orden en que aparecen.
    vistos, salida = set(), []
    for par in hallazgos:
        if par not in vistos:
            vistos.add(par)
            salida.append(par)
    return salida


def existe(cur, tipo: str, ident: str) -> bool:
    if tipo == "tabla":
        cur.execute("select to_regclass(%s)", (ident,))
        return cur.fetchone()[0] is not None
    if tipo == "funcion":
        esquema, nombre = ident.split(".", 1)
        cur.execute("""select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                       where n.nspname = %s and p.proname = %s limit 1""", (esquema, nombre))
        return cur.fetchone() is not None
    if tipo == "indice":
        cur.execute("select 1 from pg_indexes where indexname = %s limit 1", (ident,))
        return cur.fetchone() is not None
    if tipo == "columna":
        esquema, resto = ident.split(".", 1)
        tabla, columna = resto.split(".", 1)
        cur.execute("""select 1 from information_schema.columns
                       where table_schema = %s and table_name = %s
                         and column_name = %s limit 1""", (esquema, tabla, columna))
        return cur.fetchone() is not None
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Estado real de las migraciones")
    p.add_argument("--detalle", action="store_true", help="lista objeto por objeto")
    p.add_argument("--aplicar", action="store_true",
                   help="corre las migraciones a las que les falta algun objeto")
    args = p.parse_args()

    import psycopg
    archivos = sorted(MIGRACIONES.glob("*.sql"))
    if not archivos:
        print(f"No hay migraciones en {MIGRACIONES}")
        return 1

    incompletas: list[tuple[Path, list[tuple[str, str]]]] = []

    with psycopg.connect(dsn(), connect_timeout=60) as con:
        for ruta in archivos:
            objetos = objetos_de(ruta.read_text(encoding="utf-8"))
            faltan = []
            with con.cursor() as cur:
                for tipo, ident in objetos:
                    if not existe(cur, tipo, ident):
                        faltan.append((tipo, ident))

            if not objetos:
                # Una migracion que solo hace 'update' o 'comment on' no declara
                # ningun objeto: no se puede verificar y se dice, en vez de
                # darla por buena en silencio.
                print(f"  [?]  {ruta.name}  -- no declara objetos, no verificable")
                continue

            if faltan:
                incompletas.append((ruta, faltan))
                print(f"  [FALTA] {ruta.name}")
                for tipo, ident in faltan:
                    print(f"            no existe {tipo} {ident}")
            elif args.detalle:
                print(f"  [ok] {ruta.name}")
                for tipo, ident in objetos:
                    print(f"            {tipo} {ident}")
            else:
                print(f"  [ok] {ruta.name}  ({len(objetos)} objetos)")

        print()
        if not incompletas:
            print(f"Las {len(archivos)} migraciones estan aplicadas.")
            return 0

        print(f"{len(incompletas)} migracion(es) con objetos faltantes.")
        if not args.aplicar:
            print("Para aplicarlas:  py -3.13 cli/migraciones.py --aplicar")
            return 1

        for ruta, _ in incompletas:
            sql = ruta.read_text(encoding="utf-8")
            try:
                with con.cursor() as cur:
                    cur.execute(sql)
                con.commit()
                print(f"  aplicada  {ruta.name}")
            except Exception as e:
                con.rollback()
                # No se sigue con las siguientes: las migraciones tienen orden
                # y la que sigue puede depender de esta.
                print(f"  FALLO     {ruta.name}: {str(e).splitlines()[0]}")
                return 1

    print("\nListo. Volver a correr sin --aplicar para confirmar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
