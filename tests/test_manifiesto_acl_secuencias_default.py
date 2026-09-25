# -*- coding: utf-8 -*-
"""
================================================================================
 MANIFIESTO: ACL DE SECUENCIAS Y DEFAULT PRIVILEGES  --  lo que antes no se veia
================================================================================

    py -3.13 tests/test_manifiesto_acl_secuencias_default.py
    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_manifiesto_acl_secuencias_default.py

Por que existe
--------------
La adopcion certifica el estado de una base comparando fotos de catalogo. Hasta
el 15/09/2026 el manifiesto no sabia fotografiar dos partes reales de ese estado:
los privilegios de las SECUENCIAS y 'pg_default_acl'. Una migracion que las
declara ('grant ... on all sequences in schema', 'alter default privileges')
caia como 'desconocido' y terminaba en revision humana solo porque al
verificador le faltaba la capacidad de mirar.

Se agregaron exactamente dos tipos de comprobacion:

  acl_secuencias <schema>     relkind='S' del schema: nombre, dueño, ACL ordenada
  default_acl <rol> <schema>  pg_default_acl de ese par, TODOS sus tipos juntos

  1. clasificacion: los patrones nuevos (grant y revoke) y los que tienen que
     SEGUIR siendo 'desconocido' (sin FOR ROLE, sin IN SCHEMA, listas, TYPES)
  2. REGRESION: los 40 historicos del manifiesto versionado conservan su estado
     (automatica / datos / humana) con el clasificador nuevo
  3. con base: fotos deterministas -- schema vacio = [], orden estable por
     nombre, ACL normalizada sin importar el orden de los GRANT, varios tipos
     de default ACL en una sola clave, grant y revoke se reflejan

Lo que NO prueba: la cadena de migraciones ni la adopcion (ver
tests/test_ledger_migraciones.py).
================================================================================
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cli import migrar_asistente as mig                           # noqa: E402
from cli.manifiesto_adopcion import (AUTOMATICA, _normal, clasificar,  # noqa: E402
                                     diferencias, dividir, estado_de, foto)

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
titulo("1. clasificacion")
# =============================================================================
CASOS = [
    ("grant usage, select, update on all sequences in schema public to crm_user", [("acl_secuencias", "public")]),
    ("REVOKE ALL ON ALL SEQUENCES IN SCHEMA asistente FROM anon", [("acl_secuencias", "asistente")]),
    ("alter default privileges for role postgres in schema public\n  grant select, insert, update, delete, "
     "truncate, references, trigger, maintain on tables to crm_user", [("default_acl", "postgres", "public")]),
    ("alter default privileges for role postgres in schema public grant usage, select, update on sequences to crm_user",
     [("default_acl", "postgres", "public")]),
    ("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO crm_user",
     [("default_acl", "postgres", "public")]),
    ("alter default privileges for role supabase_admin in schema public revoke all on tables from anon, authenticated",
     [("default_acl", "supabase_admin", "public")]),
    ("alter default privileges for user postgres in schema public revoke grant option for select on tables from x",
     [("default_acl", "postgres", "public")]),
    # los que ya existian no cambian
    ("grant select on all tables in schema public to crm_user", [("acl_tablas", "public")]),
    ("grant execute on all functions in schema asistente to app_backend", [("acl_funciones", "asistente")]),
    ("grant select on public.organization to motor_user", [("acl_tabla", "public", "organization")]),
    ("grant usage, create on schema public to crm_user", [("schema", "public")]),
]
for sentencia, esperado in CASOS:
    obtenido = clasificar(sentencia)
    revisar(obtenido == esperado, f"{' '.join(sentencia.split())[:78]} -> {esperado}", f"{obtenido}")

SIGUEN_DESCONOCIDAS = [
    "alter default privileges in schema public grant all on tables to crm_user",          # sin FOR ROLE
    "alter default privileges for role postgres grant all on tables to crm_user",         # sin IN SCHEMA
    "alter default privileges for role postgres, otro in schema public grant all on tables to x",  # lista de roles
    "alter default privileges for role postgres in schema public, asistente grant all on tables to x",  # lista de schemas
    "alter default privileges for role postgres in schema public grant usage on types to x",
    "alter default privileges for role postgres grant usage on schemas to x",
    "grant usage on all sequences in schema public, asistente to x",                      # lista de schemas
]
for sentencia in SIGUEN_DESCONOCIDAS:
    obtenido = clasificar(sentencia)
    revisar(len(obtenido) == 1 and obtenido[0][0] == "desconocido",
            f"sigue desconocida: {sentencia[:70]}", f"{obtenido}")

claves = []
for s in dividir("grant usage on all sequences in schema public to crm_user;\n"
                 "alter default privileges for role postgres in schema public grant execute on functions to crm_user;"):
    claves += clasificar(s)
revisar(estado_de(claves)[0] == AUTOMATICA, "un archivo solo con esas sentencias es verificable automaticamente",
        f"{estado_de(claves)}")

# =============================================================================
titulo("2. REGRESION: los 40 historicos conservan su estado")
# =============================================================================
versionado = json.loads((RAIZ / "supabase" / "ledger" / "manifiesto_adopcion.json").read_bytes().decode("utf-8"))
cambios, nuevas = [], {}
for archivo, entrada in sorted(versionado["migraciones"].items()):
    texto, _sha = mig.leer_migracion(RAIZ / "supabase" / archivo)
    cl = []
    for s in dividir(texto):
        for c in clasificar(s):
            if c not in cl:
                cl.append(c)
    estado, _motivo = estado_de(cl)
    if estado != entrada["estado"]:
        cambios.append((archivo, entrada["estado"], estado))
    tipos_nuevos = sorted({c[0] for c in cl} & {"acl_secuencias", "default_acl"})
    if tipos_nuevos:
        nuevas[archivo] = tipos_nuevos
import manifiesto_de_laboratorio as lab                            # noqa: E402
revisar(set(versionado["migraciones"]) == lab.archivos_de_adopcion(RAIZ),
        f"el manifiesto versionado lista los {len(versionado['migraciones'])} archivos de adopcion (P2 fuera)",
        f"{set(versionado['migraciones']) ^ lab.archivos_de_adopcion(RAIZ)}")
revisar(not cambios, "ningun historico cambia de categoria con el clasificador nuevo", f"{cambios}")
print(f"       historicos que ganan claves nuevas (pueden ganar verificaciones, no categoria): {nuevas or 'ninguno'}")

# =============================================================================
titulo("3. fotos deterministas, con base")
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] la parte con base necesita {faltan}")
else:
    import psycopg
    from psycopg import sql

    sufijo = secrets.token_hex(3)
    BASE, R1, R2 = f"test_manifiesto_acl_{sufijo}", f"mf_r1_{sufijo}", f"mf_r2_{sufijo}"

    def dsn(base):
        return (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} dbname={base} "
                f"user={os.environ['DBUSER']} password={os.environ['DBPASSWORD']} sslmode=disable connect_timeout=15")

    with psycopg.connect(dsn("postgres"), autocommit=True) as adm:
        adm.execute(sql.SQL("create database {}").format(sql.Identifier(BASE)))
        adm.execute(sql.SQL("create role {} nologin").format(sql.Identifier(R1)))
        adm.execute(sql.SQL("create role {} nologin").format(sql.Identifier(R2)))
    try:
        with psycopg.connect(dsn(BASE), autocommit=True) as con:
            yo = con.execute("select current_user").fetchone()[0]
            con.execute("create schema sch_vacio; create schema sch_s; create schema sch_t")
            for sch in ("sch_s", "sch_t"):
                con.execute(f"create sequence {sch}.zeta; create sequence {sch}.alfa; create sequence {sch}.medio; "
                            f"create table {sch}.una_tabla (id int)")

            revisar(_normal(foto(con, ("acl_secuencias", "sch_vacio"))) == [], "acl_secuencias de un schema vacio = []")
            revisar(_normal(foto(con, ("acl_secuencias", "no_existe_el_schema"))) == [], "acl_secuencias de un schema inexistente = []")
            f0 = _normal(foto(con, ("acl_secuencias", "sch_s")))
            revisar([x["nombre"] for x in f0] == ["alfa", "medio", "zeta"],
                    "orden estable por nombre, no por orden de creacion; la tabla no aparece", f"{f0}")
            revisar(all(x["schema"] == "sch_s" and x["dueño"] == yo and x["acl"] is None for x in f0),
                    "cada secuencia trae schema, dueño y ACL (None = sin grants explicitos)", f"{f0}")

            con.execute(f'grant usage, select on all sequences in schema sch_s to "{R1}"')
            con.execute(f'grant update on all sequences in schema sch_s to "{R2}"')
            con.execute(f'grant update on all sequences in schema sch_t to "{R2}"')
            con.execute(f'grant usage, select on all sequences in schema sch_t to "{R1}"')
            fs, ft = _normal(foto(con, ("acl_secuencias", "sch_s"))), _normal(foto(con, ("acl_secuencias", "sch_t")))
            revisar(all(x["acl"] == sorted(x["acl"]) for x in fs), "la ACL sale ordenada")
            revisar([x["acl"] for x in fs] == [x["acl"] for x in ft],
                    "misma ACL aunque los GRANT se hicieran en otro orden (normalizada)", f"{fs[0]['acl']} / {ft[0]['acl']}")
            revisar(fs == _normal(foto(con, ("acl_secuencias", "sch_s"))), "dos fotos seguidas son identicas")
            revisar(any(a.startswith(f"{R1}=rU/") for a in fs[0]["acl"]) and any(a.startswith(f"{R2}=w/") for a in fs[0]["acl"]),
                    "el GRANT se refleja con los privilegios exactos", f"{fs[0]['acl']}")
            con.execute(f'revoke all on all sequences in schema sch_s from "{R1}"')
            fr = _normal(foto(con, ("acl_secuencias", "sch_s")))
            revisar(not any(a.startswith(f"{R1}=") for x in fr for a in x["acl"]), "el REVOKE se refleja")
            revisar(bool(diferencias(fs, fr)), "diferencias() detecta el cambio")
            revisar(not diferencias(fr, _normal(foto(con, ("acl_secuencias", "sch_s")))), "y no reporta nada cuando no cambio")

            revisar(_normal(foto(con, ("default_acl", yo, "sch_vacio"))) == [], "default_acl sin filas = []")
            revisar(_normal(foto(con, ("default_acl", "rol_que_no_existe", "sch_s"))) == [], "default_acl de un rol inexistente = []")
            con.execute(f'alter default privileges for role "{yo}" in schema sch_s grant execute on functions to "{R2}"')
            con.execute(f'alter default privileges for role "{yo}" in schema sch_s grant usage, select on sequences to "{R1}"')
            con.execute(f'alter default privileges for role "{yo}" in schema sch_s grant select, insert on tables to "{R2}", "{R1}"')
            fd = _normal(foto(con, ("default_acl", yo, "sch_s")))
            revisar([x["tipo"] for x in fd] == ["S", "f", "r"],
                    "una sola clave trae los tres tipos (secuencias, funciones, tablas), en orden estable", f"{fd}")
            revisar(all(x["rol"] == yo and x["schema"] == "sch_s" and x["acl"] == sorted(x["acl"]) for x in fd),
                    "cada fila trae rol, schema, tipo y ACL ordenada")
            tablas = next(x for x in fd if x["tipo"] == "r")["acl"]
            revisar(any(a.startswith(f"{R1}=ar/") for a in tablas) and any(a.startswith(f"{R2}=ar/") for a in tablas),
                    "los privilegios por defecto de tablas son los otorgados", f"{tablas}")
            con.execute(f'alter default privileges for role "{yo}" in schema sch_s revoke all on tables from "{R1}", "{R2}"')
            fd2 = _normal(foto(con, ("default_acl", yo, "sch_s")))
            revisar([x["tipo"] for x in fd2] == ["S", "f"], "el REVOKE de tablas saca esa fila y deja las otras", f"{fd2}")
            revisar(bool(diferencias(fd, fd2)), "diferencias() detecta el cambio de default ACL")
            revisar(json.dumps(fd2, sort_keys=True) == json.dumps(_normal(foto(con, ("default_acl", yo, "sch_s"))), sort_keys=True),
                    "la foto serializa igual dos veces")
    finally:
        with psycopg.connect(dsn("postgres"), autocommit=True) as adm:
            adm.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(BASE)))
            for r in (R1, R2):
                adm.execute(sql.SQL("drop role if exists {}").format(sql.Identifier(r)))

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("OK: el manifiesto ve la ACL de secuencias y los default privileges, y ningun historico cambia de categoria")
