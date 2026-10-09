# -*- coding: utf-8 -*-
"""
================================================================================
 PRESENCIA DE OBJETOS  --  informativo. Puede probar que algo FALTA; nunca que
                           algo este aplicado.
================================================================================

    py -3.13 cli/migraciones.py               # que falta y que no se puede verificar
    py -3.13 cli/migraciones.py --detalle     # ademas, objeto por objeto
    py -3.13 cli/migraciones.py --aplicar     # SE NIEGA: ver cli/migrar_asistente.py

Historia, y por que cambio
--------------------------
Esto nacio el 25/08/2026, cuando se descubrio que dos migraciones nunca se
habian aplicado en produccion (conversations.caso_manual y
conversations.resumen) y las funciones que las usaban venian fallando en
silencio. La idea era buena: no confiar en una lista, ir a mirar si los objetos
estan. Y rechazaba una tabla de registro por una razon cierta: marcar las 27
como aplicadas habria tapado las dos que faltaban.

Ese razonamiento sigue valiendo, y es el que respeta el ledger nuevo: la
adopcion de una base existente NO marca nada por lista, verifica cada migracion
contra el catalogo con un manifiesto semantico y deja sin anotar lo que no
puede demostrar (cli/manifiesto_adopcion.py).

Lo que ya no se sostiene de esta herramienta:

  * '--aplicar' ejecutaba archivos enteros por fuera de cualquier registro, sin
    checksum, sin lock y sin respetar huecos. Era una segunda via de escritura.
    Ahora se niega y remite al migrador.
  * Afirmaba "las N migraciones estan aplicadas" cuando existian las tablas,
    columnas, funciones e indices que cada archivo declaraba. Eso no prueba que
    esten aplicadas: no mira constraints, predicados, politicas, grants,
    comentarios, cuerpos de funciones ni datos. Y los tipos de objeto que no
    reconocia devolvian 'existe = True'. Medido: sobre
    202609070900_bandeja_sin_inflar.sql no ve ningun objeto, asi que lo daba
    siempre por aplicado y '--aplicar' nunca lo habria ejecutado.

Asi que ahora:

  FALTA            algun objeto que el archivo declara NO existe. Esto si es una
                   prueba: la migracion no esta (entera) aplicada.
  NO VERIFICABLE   todo lo demas. Que existan sus objetos no demuestra nada, y
                   las sentencias que no son creacion de objetos -- comment,
                   grant, policy, update, do, alter column... -- no se pueden
                   verificar por existencia.

No hay estado "ok". El resumen global nunca dice "aplicadas". Si se quiere saber
que esta aplicado en una base, eso lo responde 'cli/migrar_asistente.py --estado'.

Codigos de salida
-----------------
  0  no se usa (esta herramienta no puede afirmar que todo este bien)
  1  al menos un archivo con objetos FALTANTES
  2  uso invalido (incluido --aplicar)
  3  ningun faltante, y al menos un archivo NO VERIFICABLE (el caso normal)

Como se nombra una migracion nueva
----------------------------------
    supabase/AAAAMMDDHHMM_lo_que_hace.sql     (hora de Colombia, no del servidor)
================================================================================
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SALIDA_FALTA, SALIDA_USO, SALIDA_NO_VERIFICABLE = 1, 2, 3

_ID = r'[a-z_][a-z0-9_]*'
_TABLA = re.compile(rf"^create (?:unlogged )?table (?:if not exists )?({_ID}\.{_ID})\b")
_INDICE = re.compile(rf"^create (?:unique )?index (?:concurrently )?(?:if not exists )?({_ID})\b")
_FUNCION = re.compile(rf"^create (?:or replace )?function ({_ID}\.{_ID})\s*\(")
_ALTER = re.compile(rf"^alter table (?:if exists )?(?:only )?({_ID}\.{_ID}) (.*)$")
_ADD_COLUMN = re.compile(rf"^add column (?:if not exists )?({_ID})\b")


def _plano(s: str) -> str:
    return " ".join(s.split()).lower()


def _clausulas(texto: str) -> list[str]:
    """Parte por comas de nivel superior (fuera de parentesis y comillas)."""
    partes, buf, prof, comilla = [], [], 0, False
    for c in texto:
        if c == "'":
            comilla = not comilla
        elif not comilla and c == "(":
            prof += 1
        elif not comilla and c == ")":
            prof -= 1
        elif not comilla and prof == 0 and c == ",":
            partes.append("".join(buf).strip())
            buf = []
            continue
        buf.append(c)
    partes.append("".join(buf).strip())
    return [p for p in partes if p]


def analizar(sql: str):
    """
    (objetos, sentencias_no_verificables)

    objetos: [(tipo, identificador)] que el archivo dice crear.
    sentencias_no_verificables: todas las que no son creacion de objetos. Una
    creacion reconocida tampoco se da por verificada: solo se puede comprobar
    que su objeto EXISTA, y eso sirve para encontrar faltantes, no para afirmar.
    """
    from cli.manifiesto_adopcion import dividir

    objetos: list[tuple[str, str]] = []
    no_verificables: list[str] = []
    for sentencia in dividir(sql):
        s = _plano(sentencia)
        if m := _TABLA.match(s):
            objetos.append(("tabla", m.group(1)))
            continue
        if m := _INDICE.match(s):
            objetos.append(("indice", m.group(1)))
            continue
        if m := _FUNCION.match(s):
            objetos.append(("funcion", m.group(1)))
            continue
        if m := _ALTER.match(s):
            clausulas = _clausulas(m.group(2))
            columnas = [_ADD_COLUMN.match(c) for c in clausulas]
            if clausulas and all(columnas):
                objetos.extend(("columna", f"{m.group(1)}.{c.group(1)}") for c in columnas)
                continue
        no_verificables.append(s[:90])
    vistos, unicos = set(), []
    for o in objetos:
        if o not in vistos:
            vistos.add(o)
            unicos.append(o)
    return unicos, no_verificables


def existe(cur, tipo: str, ident: str) -> bool | None:
    """True/False si se sabe; None si el tipo no es uno que se sepa comprobar."""
    if tipo == "tabla":
        cur.execute("select to_regclass(%s)", (ident,))
        return cur.fetchone()[0] is not None
    if tipo == "funcion":
        esquema, nombre = ident.split(".", 1)
        cur.execute("select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where n.nspname = %s and p.proname = %s limit 1", (esquema, nombre))
        return cur.fetchone() is not None
    if tipo == "indice":
        cur.execute("select 1 from pg_indexes where indexname = %s limit 1", (ident,))
        return cur.fetchone() is not None
    if tipo == "columna":
        esquema, tabla, columna = ident.split(".", 2)
        cur.execute("select 1 from information_schema.columns where table_schema = %s "
                    "and table_name = %s and column_name = %s limit 1",
                    (esquema, tabla, columna))
        return cur.fetchone() is not None
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Presencia de objetos de las migraciones (informativo)")
    p.add_argument("--detalle", action="store_true")
    p.add_argument("--aplicar", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    if args.aplicar:
        # Antes de conectarse: esta via no puede escribir ni por error.
        print("[migraciones] --aplicar ya no existe en esta herramienta.\n"
              "  Ejecutaba archivos de supabase/ por fuera del ledger: sin checksum,\n"
              "  sin lock y sin respetar huecos. El unico camino que escribe es:\n\n"
              "      py -3.13 cli/migrar_asistente.py --estado\n"
              "      py -3.13 cli/migrar_asistente.py --aplicar\n\n"
              "  Y una base que ya tiene el esquema se adopta, no se aplica:\n"
              "      py -3.13 cli/migrar_asistente.py --adoptar")
        return SALIDA_USO

    import psycopg

    from cli import migrar_asistente as mig
    from nucleo.persistencia.conexion import dsn

    falta_alguno = False
    no_verificables = 0
    archivos = mig.archivos()
    with psycopg.connect(dsn()) as con, con.cursor() as cur:
        for ruta in archivos:
            try:
                sql, _sha = mig.leer_migracion(ruta)
            except mig.ContenidoNoCanonico as e:
                no_verificables += 1
                print(f"  [NO VERIFICABLE] {ruta.name}: {e}")
                continue
            objetos, sin_verificar = analizar(sql)
            faltan, desconocidos = [], []
            for tipo, ident in objetos:
                r = existe(cur, tipo, ident)
                if r is None:
                    desconocidos.append((tipo, ident))
                elif r is False:
                    faltan.append((tipo, ident))
            if faltan:
                falta_alguno = True
                print(f"  [FALTA] {ruta.name}")
                for tipo, ident in faltan:
                    print(f"            no existe {tipo} {ident}")
            else:
                no_verificables += 1
                motivo = []
                if not objetos:
                    motivo.append("no declara objetos comprobables")
                if sin_verificar:
                    motivo.append(f"{len(sin_verificar)} sentencia(s) que no se "
                                  f"verifican por existencia")
                if desconocidos:
                    motivo.append(f"{len(desconocidos)} objeto(s) de tipo desconocido")
                if not motivo:
                    motivo.append("sus objetos existen, y eso no prueba que este aplicada")
                print(f"  [NO VERIFICABLE] {ruta.name}  ({'; '.join(motivo)})")
            if args.detalle:
                for tipo, ident in objetos:
                    print(f"            objeto {tipo} {ident}")
                for s in sin_verificar:
                    print(f"            sin verificar: {s}")

    print()
    if falta_alguno:
        print("Hay migraciones con objetos FALTANTES (ver arriba).")
        return SALIDA_FALTA
    print(f"Ningun objeto faltante, y {no_verificables} de {len(archivos)} archivos "
          f"NO VERIFICABLES por esta via.\nEsto no significa que esten aplicadas: "
          f"para eso, py -3.13 cli/migrar_asistente.py --estado")
    return SALIDA_NO_VERIFICABLE


if __name__ == "__main__":
    raise SystemExit(main())
