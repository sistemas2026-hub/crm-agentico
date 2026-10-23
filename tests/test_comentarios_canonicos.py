# -*- coding: utf-8 -*-
"""
================================================================================
 COMENTARIOS CANONICOS  --  el texto que produccion ya tiene, declarado en git
================================================================================

    py -3.13 tests/test_comentarios_canonicos.py
    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_comentarios_canonicos.py

Por que existe
--------------
La comparacion de solo lectura contra produccion del 15/09/2026 dejo cinco
divergencias de comentarios: el texto que hay en produccion llego fuera de git
(borradores aplicados y no commiteados) y no coincide con el que declaran sus
migraciones historicas. Para la adopcion se decidio que el estado canonico es
EXACTAMENTE el de produccion, y eso lo declara
'supabase/202609141120_comentarios_catalogo_canonicos.sql'.

Los md5 de abajo son los que devolvio produccion en esa lectura (columna 'hay'
de la comparacion). Esta prueba aplica el archivo sobre una base temporal y
exige que el catalogo quede con EXACTAMENTE esos md5, medidos con la misma foto
que usa el manifiesto. Si alguien reescribe un texto "para que se lea mejor",
esto falla.

  1. el archivo: cinco COMMENT ON, nada mas, verificable automaticamente
  2. aplicado: los cinco md5 de produccion, con su whitespace y su salto de
     linea real (ticket_operativo)
  3. control: si se cambia un solo caracter, la foto lo detecta
  4. idempotente

Lo que NO prueba: la cadena completa ni la adopcion (ver
tests/test_ledger_migraciones.py).
================================================================================
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cli import migrar_asistente as mig                           # noqa: E402
from cli.manifiesto_adopcion import AUTOMATICA, _normal, clasificar, dividir, estado_de, foto  # noqa: E402

ARCHIVO = RAIZ / "supabase" / "202609141120_comentarios_catalogo_canonicos.sql"

# md5 medidos en PRODUCCION el 15/09/2026 (lectura de solo lectura por la ruta directa).
CANONICOS = {
    ("comentario_columna", "asistente", "conversations", "ticket_operativo"): "f553093b634c406f881effc91b2238b1",
    ("comentario_tabla", "asistente", "verificaciones_accion"): "0d61f178d1a95cdfa1be9f4760afe024",
    ("comentario_columna", "asistente", "conversations", "estado_escalada"): "20647bcacffd2bebee45a99a8df0c463",
    ("comentario_columna", "asistente", "conversations", "escalada_detalle"): "d0525ba3c1580c69d6493ba619aaad0f",
    ("comentario_columna", "asistente", "messages", "llamadas_modelo"): "c50757c7294f633209f8efed0a37a030",
}

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def titulo(t):
    print(f"\n{'=' * 74}\n  {t}\n{'=' * 74}", flush=True)


# =============================================================================
titulo("1. el archivo")
# =============================================================================
crudo = ARCHIVO.read_bytes()
texto, sha = mig.leer_migracion(ARCHIVO)
sentencias = dividir(texto)
claves = [c for s in sentencias for c in clasificar(s)]
revisar(b"\r" not in crudo, "sin CR: LF puro")
revisar(len(sentencias) == 5, f"cinco sentencias ({len(sentencias)})")
revisar(all(s.lower().startswith("comment on ") for s in sentencias), "todas son COMMENT ON")
revisar(set(claves) == set(CANONICOS) and len(claves) == 5,
        "las cinco claves son las de los objetos canonicos", f"{claves}")
revisar(estado_de(claves)[0] == AUTOMATICA, "verificable automaticamente", f"{estado_de(claves)}")
revisar(all(c[0] in ("comentario_tabla", "comentario_columna") for c in claves),
        "solo comentario_tabla / comentario_columna")
print(f"       sha256 canonico: {sha}")

# =============================================================================
titulo("2. aplicado sobre una base temporal: los md5 de produccion")
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] la parte con base necesita {faltan}")
else:
    import psycopg
    from psycopg import sql

    BASE = f"test_comentarios_{secrets.token_hex(3)}"

    def dsn(base):
        return (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} dbname={base} "
                f"user={os.environ['DBUSER']} password={os.environ['DBPASSWORD']} sslmode=disable connect_timeout=15")

    with psycopg.connect(dsn("postgres"), autocommit=True) as adm:
        adm.execute(sql.SQL("create database {}").format(sql.Identifier(BASE)))
    try:
        with psycopg.connect(dsn(BASE), autocommit=True) as con:
            # Lo minimo que los COMMENT ON necesitan: los objetos, no su contenido.
            con.execute("create schema asistente;"
                        "create table asistente.conversations (id int, ticket_operativo text, "
                        "  estado_escalada text, escalada_detalle text);"
                        "create table asistente.messages (id int, llamadas_modelo int);"
                        "create table asistente.verificaciones_accion (id int)")
            vacias = {c: _normal(foto(con, c)) for c in CANONICOS}
            revisar(all(v.get("comentario") is None for v in vacias.values()),
                    "antes de aplicar, los cinco objetos existen y no tienen comentario", f"{vacias}")

            with con.transaction():
                con.execute(texto)
            reales = {c: _normal(foto(con, c)) for c in CANONICOS}
            malos = {c: (reales[c].get("comentario"), esperado) for c, esperado in CANONICOS.items()
                     if reales[c].get("comentario") != esperado}
            revisar(not malos, "los cinco comentarios quedan con el md5 EXACTO de produccion", f"{malos}")

            largos = con.execute(
                "select col_description('asistente.conversations'::regclass, a.attnum), "
                "       length(col_description('asistente.conversations'::regclass, a.attnum)), "
                "       position(chr(10) in col_description('asistente.conversations'::regclass, a.attnum)) "
                "from pg_attribute a where a.attrelid = 'asistente.conversations'::regclass "
                "and a.attname = 'ticket_operativo'").fetchone()
            revisar(largos[1] == 168 and largos[2] == 79,
                    "ticket_operativo conserva su salto de linea real (168 caracteres, el LF en la posicion 79)",
                    f"largo={largos[1]} salto en={largos[2]}")
            revisar("         despliegue" in largos[0],
                    "y la sangria de nueve espacios de la linea siguiente")

            # 3. control: un caracter distinto y la foto lo ve
            con.execute("comment on table asistente.verificaciones_accion is "
                        "'Comprobacion posterior de que una accion produjo su efecto tecnico.'")
            revisar(_normal(foto(con, ("comentario_tabla", "asistente", "verificaciones_accion")))["comentario"]
                    != CANONICOS[("comentario_tabla", "asistente", "verificaciones_accion")],
                    "control: con otro texto, la foto deja de coincidir")

            # 4. idempotente: volver a aplicarlo restaura y no cambia nada mas
            with con.transaction():
                con.execute(texto)
            otra_vez = {c: _normal(foto(con, c)) for c in CANONICOS}
            revisar(otra_vez == reales, "aplicarlo de nuevo deja exactamente lo mismo")
    finally:
        with psycopg.connect(dsn("postgres"), autocommit=True) as adm:
            adm.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(BASE)))

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("OK: los cinco comentarios canonicos son exactamente los que produccion ya tiene")
