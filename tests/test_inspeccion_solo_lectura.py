# -*- coding: utf-8 -*-
"""
================================================================================
 EL SCRIPT DE INSPECCION NO ESCRIBE  --  leido, y corrido contra copias locales
================================================================================

    py -3.13 tests/test_inspeccion_solo_lectura.py                       (estatico)
    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
      DBNAME=<base construida por el ledger> py -3.13 tests/test_inspeccion_solo_lectura.py

'supabase/ledger/analisis/inspeccion_solo_lectura.sql' es lo que se va a correr
contra la base objetivo para decidir una adopcion. Esta prueba sostiene lo que
promete su cabecera:

  1. leido: cada sentencia es un SELECT o uno de los tres SET permitidos, sin
     una palabra de escritura, y toda consulta a una tabla de 'asistente' es un
     conteo. Con controles: un UPDATE, una lectura de filas, un SET READ WRITE y
     un advisory lock metidos a proposito tienen que detectarse;
  2. contra una COPIA de DBNAME (nunca la base original, nunca un host remoto):
     corre entero sin un error y el catalogo queda identico;
  3. contra una base sin 'asistente': cada falta falla sola y llega al final;
  4. control: en una sesion como la del script, un CREATE TABLE falla.

psql corre en un contenedor (IMAGEN_PSQL, por defecto postgres:16): no hace
falta tenerlo instalado.
================================================================================
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cli.manifiesto_adopcion import dividir                       # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


def titulo(t):
    print()
    print("=" * 74)
    print(f"  {t}")
    print("=" * 74)


SCRIPT = RAIZ / "supabase" / "ledger" / "analisis" / "inspeccion_solo_lectura.sql"

PERMITIDAS = [re.compile(p) for p in (
    r"select\b",
    r"set session characteristics as transaction read only$",
    r"set statement_timeout = '\d+s'$",
    r"set lock_timeout = '\d+s'$",
)]
PROHIBIDAS = re.compile(
    r"\b(insert|update|delete|merge|create|alter|drop|grant|revoke|truncate|copy|call|do|"
    r"vacuum|analyze|cluster|reindex|refresh|lock|comment|listen|notify|prepare|execute|"
    r"nextval|setval|set_config|pg_advisory_\w+|pg_terminate_backend|pg_cancel_backend|"
    r"pg_read_file|pg_read_binary_file|lo_\w+|dblink\w*|read\s+write)\b")


def sentencias(texto: str) -> list[str]:
    """Las sentencias SQL, sin metacomandos de psql; '\\gset' cierra la suya."""
    lineas = [re.sub(r"\\gset\s*$", ";", l) for l in texto.splitlines()
              if not l.lstrip().startswith("\\")]
    return [" ".join(s.split()).lower() for s in dividir("\n".join(lineas))]


def sin_literales(s: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", s)


def problemas(texto: str) -> list[str]:
    malas = []
    for s in sentencias(texto):
        limpia = sin_literales(s)
        if not any(p.match(s) for p in PERMITIDAS):
            malas.append(f"no es SELECT ni un SET permitido: {s[:80]}")
        m = PROHIBIDAS.search(limpia)
        if m:
            malas.append(f"'{m.group(1)}': {s[:80]}")
        if re.search(r"\b(?:from|join)\s+asistente\.\w+", limpia) and "count(" not in limpia:
            malas.append(f"lee filas de 'asistente' sin agregarlas: {s[:80]}")
    return malas


# =============================================================================
titulo("1. el script, leido")
# =============================================================================
texto = SCRIPT.read_bytes().decode("utf-8")
revisar("ESTE SCRIPT NO ADOPTA NI MODIFICA NADA." in texto[:300],
        "la cabecera dice que no adopta ni modifica nada")
n = len(sentencias(texto))
malas = problemas(texto)
revisar(n >= 20 and not malas,
        f"sus {n} sentencias son SELECT o SET de solo lectura, sin escritura, y agregadas",
        f"{malas}")
for mutacion, que in (("update asistente.conversations set estado = 'x';", "un UPDATE"),
                      ("select tomada_por from asistente.conversations;", "una lectura de filas sin agregar"),
                      ("set transaction read write;", "un SET que vuelve a lectura-escritura"),
                      ("select pg_advisory_lock(1);", "un advisory lock")):
    revisar(bool(problemas(texto + "\n" + mutacion + "\n")),
            f"control: la lectura detecta {que} agregado al final")

# =============================================================================
#  con base
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan or not shutil.which("docker"):
    print(f"\n  [saltado] la parte con base necesita {faltan or 'Docker'}")
elif os.environ["DBHOST"] not in ("localhost", "127.0.0.1"):
    print("\n  [saltado] la parte con base solo corre contra un servidor LOCAL")
else:
    import psycopg                                                # noqa: E402

    HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
    USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
    ORIGEN = os.environ["DBNAME"]
    COPIA, VACIA = ORIGEN + "_inspeccion", ORIGEN + "_inspeccion_vacia"
    IMAGEN_PSQL = os.environ.get("IMAGEN_PSQL", "postgres:16")
    SOLO_LECTURA = "-c default_transaction_read_only=on"

    def conectar(base, **kw):
        return psycopg.connect(host=HOST, port=PUERTO, dbname=base, user=USUARIO,
                               password=CLAVE, sslmode="disable", **kw)

    def consultar(base, sql):
        with conectar(base, autocommit=True) as con:
            return con.execute(sql).fetchall()

    def recrear(base, plantilla=None):
        with conectar("postgres", autocommit=True) as con:
            for _ in range(40):
                con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                            "where datname = any(%s) and pid <> pg_backend_pid()",
                            ([base, plantilla or base],))
                try:
                    con.execute(f'drop database if exists "{base}"')
                    if plantilla is not None:
                        con.execute(f'create database "{base}" template "{plantilla}"')
                    return
                except (psycopg.errors.ObjectInUse, psycopg.errors.DuplicateDatabase):
                    time.sleep(0.5)
            raise RuntimeError(f"no se pudo recrear {base}")

    def psql(base, entrada, pgoptions=True):
        env = {**os.environ, "PGPASSWORD": CLAVE}
        env.pop("PGOPTIONS", None)
        if pgoptions:
            env["PGOPTIONS"] = SOLO_LECTURA
        cmd = ["docker", "run", "--rm", "-i", "--add-host=host.docker.internal:host-gateway",
               "-e", "PGPASSWORD", *(["-e", "PGOPTIONS"] if pgoptions else []),
               IMAGEN_PSQL, "psql", "-X", "-h", "host.docker.internal", "-p", PUERTO,
               "-U", USUARIO, "-d", base, "-f", "-"]
        r = subprocess.run(cmd, input=entrada, capture_output=True, text=True,
                           encoding="utf-8", env=env, timeout=300)
        return r.returncode, (r.stdout or "") + (r.stderr or "")

    FOTO = """
        select md5(string_agg(x, '|' order by x)) from (
          select 'rel:' || n.nspname::text || '.' || c.relname::text || ':' || c.relkind::text
                 || ':' || coalesce(c.relacl::text, '') as x
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
          union all
          select 'fun:' || p.oid::regprocedure::text || ':' || coalesce(p.proacl::text, '')
            from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname not in ('pg_catalog', 'information_schema')
          union all
          select 'rol:' || rolname::text from pg_roles
          union all
          select 'ajuste:' || coalesce(array_to_string(setconfig, ','), '') from pg_db_role_setting
        ) t"""

    try:
        # =====================================================================
        titulo("2. contra una copia de la base construida por el ledger")
        # =====================================================================
        recrear(COPIA, ORIGEN)
        antes = consultar(COPIA, FOTO)
        codigo, salida = psql(COPIA, texto)
        errores = [l for l in salida.splitlines() if "ERROR" in l]
        revisar(codigo == 0 and not errores, "corre entero: exit 0 y ni un ERROR",
                f"exit {codigo}: {errores[:3]}")
        secciones = [f"== {i}." for i in range(11)] + ["== fin"]
        revisar(all(h in salida for h in secciones), "pasa por las once secciones y llega al final",
                f"faltan {[h for h in secciones if h not in salida]}")
        revisar("server_version_num" in salida and "extversion" in salida and "execute_para" in salida,
                "trae la huella y los EXECUTE por funcion")
        revisar(consultar(COPIA, FOTO) == antes,
                "el catalogo de la copia quedo identico (relaciones, funciones, grants, roles, ajustes)")

        # =====================================================================
        titulo("3. contra una base sin 'asistente'")
        # =====================================================================
        recrear(VACIA)
        with conectar("postgres", autocommit=True) as con:
            con.execute(f'create database "{VACIA}"')
        codigo, salida = psql(VACIA, texto)
        errores = [l for l in salida.splitlines() if "ERROR:" in l]
        revisar(codigo == 0 and "== fin" in salida, "tambien llega al final (exit 0)", salida[-300:])
        revisar(bool(errores) and all("does not exist" in e for e in errores),
                f"sus {len(errores)} errores son todos de objetos que faltan", f"{errores}")
        revisar("tablas_en_asistente" in salida and "tenant_aislado" in salida
                and "execute_para" in salida and "server_version_num" in salida,
                "y las consultas de catalogo corrieron igual: una falta no aborta las demas")

        # =====================================================================
        titulo("4. control: en una sesion como la del script, escribir falla")
        # =====================================================================
        rechazo = "cannot execute CREATE TABLE in a read-only transaction"
        codigo, salida = psql(COPIA, "create table public.control_escritura (x int);\n")
        revisar(rechazo in salida, "con PGOPTIONS: CREATE TABLE rechazado", salida[-200:])
        codigo, salida = psql(COPIA, "set session characteristics as transaction read only;\n"
                                     "create table public.control_escritura (x int);\n",
                              pgoptions=False)
        revisar(rechazo in salida, "sin PGOPTIONS, el SET del propio script alcanza para rechazarlo",
                salida[-200:])
        revisar(not consultar(COPIA, "select to_regclass('public.control_escritura') is not null")[0][0],
                "y la tabla no existe")
    finally:
        with conectar("postgres", autocommit=True) as con:
            for base in (COPIA, VACIA):
                con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                            "where datname = %s and pid <> pg_backend_pid()", (base,))
                con.execute(f'drop database if exists "{base}"')

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] El script de inspeccion solo lee.")
print("=" * 74)
