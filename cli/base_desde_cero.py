# -*- coding: utf-8 -*-
"""
================================================================================
 UNA BASE DESDE CERO  --  el orden canonico, ejecutable
================================================================================

    py -3.13 cli/base_desde_cero.py --base p2_cero
    py -3.13 cli/base_desde_cero.py --base p2_cero --sin-recrear     (2a pasada)
    py -3.13 cli/base_desde_cero.py --base p2_cero --verificar-solo

Por que existe
--------------
"Aplicar las migraciones" no era un procedimiento: era una cosa que alguien
sabia hacer. Y no se podia hacer sobre una base vacia, porque la mitad del
esquema la crea Django y la otra mitad los archivos de 'supabase/', y el orden
entre las dos mitades no estaba escrito en ninguna parte.

    1. La extension pgcrypto en el schema 'ext'      (superusuario, una vez)
    2. Las migraciones de Django                     (crea public.organization)
    3. Los archivos de supabase/, POR EL LEDGER      (cli/migrar_asistente.py)
    4. Comprobacion: tablas, constraints, funciones, RLS, grants y ledger

El paso 2 va ANTES del 3 y no es negociable:
'supabase/202608042055_schema.sql' referencia 'public.organization(id)', que la
crea la app 'accounts' de Django. Con la base vacia y sin ese paso, los 42
archivos fallan en cascada -- medido: el primero con UndefinedTable y los otros
con InvalidSchemaName porque el schema 'asistente' nunca llego a existir.

El paso 3 va por el ledger, no ejecutando los archivos
------------------------------------------------------
La version anterior de este script ejecutaba los .sql uno por uno. La primera
pasada funcionaba; la SEGUNDA fallaba con DuplicateObject en cinco archivos
historicos que hacen 'create policy' sin guarda, y ademas volvia a correr un
'grant execute on all functions in schema asistente to app_backend' que
alcanzaba funciones nuevas. Con el ledger, lo anotado no se reejecuta: la
segunda pasada ('--sin-recrear') tiene que terminar con 0 pendientes.

Django corre en su imagen
-------------------------
'django-crm/backend' tiene sus dependencias en la imagen 'dexter-backend', no
en el Python del host. Este script monta el codigo actual sobre /app de esa
imagen, asi que migra la cadena del WORKTREE y no la que quedo congelada
cuando se construyo la imagen.

Que NO hace
-----------
No apunta a produccion y no puede: exige que el host sea local. No siembra
datos. No crea el catalogo de jobs -- un job que la migracion crea habilitado
se enciende solo al desplegar.
================================================================================
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import psycopg                                                    # noqa: E402

HOSTS_LOCALES = {"localhost", "127.0.0.1", "db", "host.docker.internal"}
IMAGEN_DJANGO = os.environ.get("IMAGEN_DJANGO", "dexter-backend:latest")


def dsn(base: str, host: str, puerto: str, usuario: str, clave: str) -> str:
    return (f"host={host} port={puerto} dbname={base} user={usuario} "
            f"password={clave} sslmode=disable")


def paso(n: int, que: str) -> None:
    print(f"\n{'=' * 74}\n  PASO {n}: {que}\n{'=' * 74}", flush=True)


def crear_base(base, host, puerto, usuario, clave) -> None:
    with psycopg.connect(dsn("postgres", host, puerto, usuario, clave),
                         autocommit=True) as con:
        con.execute(f'drop database if exists "{base}"')
        con.execute(f'create database "{base}"')
    print(f"  base '{base}' creada, vacia")


def pgcrypto(base, host, puerto, usuario, clave) -> None:
    with psycopg.connect(dsn(base, host, puerto, usuario, clave),
                         autocommit=True) as con:
        con.execute("create schema if not exists ext")
        con.execute("create extension if not exists pgcrypto with schema ext")
        for f in ("ext.digest(text,text)", "ext.gen_random_bytes(integer)"):
            hay = con.execute("select to_regprocedure(%s) is not null as hay",
                              (f,)).fetchone()[0]
            print(f"  {f}: {'presente' if hay else 'FALTA'}")
            if not hay:
                raise SystemExit(f"pgcrypto incompleto: falta {f}")


def django(base, host, puerto, usuario, clave) -> int:
    """Las migraciones de Django, en su propia imagen, con el codigo de aca."""
    # Desde el contenedor, el Postgres del host no es 'localhost'.
    host_cont = "host.docker.internal" if host in ("localhost", "127.0.0.1") else host
    backend = (RAIZ / "django-crm" / "backend").as_posix()
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{backend}:/app",
        "-e", f"DBHOST={host_cont}", "-e", f"DBPORT={puerto}",
        "-e", f"DBNAME={base}", "-e", f"DBUSER={usuario}",
        "-e", f"DBPASSWORD={clave}",
        "-e", "DJANGO_SETTINGS_MODULE=crm.settings",
        "-e", "SECRET_KEY=solo-para-migrar-una-base-local",
        "-e", "DEBUG=0", "-e", "ALLOWED_HOSTS=*",
        IMAGEN_DJANGO,
        "python3", "manage.py", "migrate", "--noinput",
    ]
    print("  " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    cola = (r.stdout or "").strip().splitlines()
    for linea in cola[-25:]:
        print(f"    {linea}")
    if r.returncode != 0:
        print(f"    [stderr] {(r.stderr or '').strip()[-2000:]}")
    print(f"  exit={r.returncode}")
    return r.returncode


def asistente(base, host, puerto, usuario, clave) -> int:
    """
    Los archivos de supabase/, a traves del ledger. Devuelve el codigo de salida
    del migrador: 0 aplico lo pendiente (o no habia nada), cualquier otro valor
    es un fallo que el migrador ya explico.
    """
    os.environ.update({"DBHOST": host, "DBPORT": str(puerto), "DBNAME": base,
                       "DBUSER": usuario, "DBPASSWORD": clave})
    from cli import migrar_asistente as mig                       # noqa: E402

    con = mig.conectar()
    try:
        mig.bootstrap(con)
        return mig.aplicar(con, 60.0)
    finally:
        con.close()


# -----------------------------------------------------------------------------
#  comprobacion
# -----------------------------------------------------------------------------

TABLAS = ("job_catalogo", "job_schedule_state", "job_run", "job_attempt",
          "job_run_event")
FUNCIONES = ("job_slot", "jobs_vencidos", "job_claim", "job_cerrar_turno",
             "job_intento_vigente", "job_intento_vigente_por_capability",
             "job_heartbeat", "job_finalize", "job_contexto", "job_salud")
ROLES = ("asistente_owner", "scheduler_coordinator", "job_executor",
         "monitor_ro")


def verificar(base, host, puerto, usuario, clave) -> list[str]:
    malas: list[str] = []

    def mal(q):
        malas.append(q)
        print(f"  [FALLA] {q}")

    def ok(q):
        print(f"  [ok] {q}")

    with psycopg.connect(dsn(base, host, puerto, usuario, clave)) as con:
        hay = {f[0] for f in con.execute(
            "select tablename from pg_tables where schemaname='asistente'")}
        faltan = [t for t in TABLAS if t not in hay]
        ok(f"las {len(TABLAS)} tablas job_* existen") if not faltan else \
            mal(f"faltan tablas: {faltan}")

        props = con.execute(
            "select c.relname, r.rolname, c.relrowsecurity "
            "from pg_class c join pg_roles r on r.oid=c.relowner "
            "join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='asistente' and c.relname = any(%s)",
            (list(TABLAS),)).fetchall()
        malos = [p for p in props if p[1] != "asistente_owner" or not p[2]]
        ok("las cinco son de asistente_owner y tienen RLS") if not malos else \
            mal(f"propiedad/RLS mal: {malos}")

        hayf = {f[0] for f in con.execute(
            "select proname from pg_proc p join pg_namespace n "
            "on n.oid=p.pronamespace where n.nspname='asistente' "
            "and proname like 'job%'")}
        faltanf = [f for f in FUNCIONES if f not in hayf]
        sobran = sorted(hayf - set(FUNCIONES))
        ok(f"las {len(FUNCIONES)} funciones existen") if not faltanf else \
            mal(f"faltan funciones: {faltanf}")
        ok("y no quedo ninguna funcion huerfana") if not sobran else \
            mal(f"funciones que la migracion ya no declara: {sobran}")

        hayr = {f[0] for f in con.execute(
            "select rolname from pg_roles where rolname = any(%s)",
            (list(ROLES),))}
        faltanr = [r for r in ROLES if r not in hayr]
        ok(f"los {len(ROLES)} roles existen") if not faltanr else \
            mal(f"faltan roles: {faltanr}")

        conlogin = con.execute(
            "select rolname from pg_roles where rolname = any(%s) and rolcanlogin",
            (list(ROLES),)).fetchall()
        ok("ninguno de los cuatro puede hacer login") if not conlogin else \
            mal(f"roles con login: {conlogin}")

        n = con.execute(
            "select count(*) from pg_constraint c join pg_class t "
            "on t.oid=c.conrelid join pg_namespace n on n.oid=t.relnamespace "
            "where n.nspname='asistente' and t.relname = any(%s)",
            (list(TABLAS),)).fetchone()[0]
        ok(f"{n} constraints sobre las cinco tablas") if n >= 40 else \
            mal(f"solo {n} constraints, se esperaban 40 o mas")

        pol = con.execute(
            "select count(*) from pg_policies where schemaname='asistente' "
            "and tablename = any(%s)", (list(TABLAS),)).fetchone()[0]
        ok(f"{pol} politicas RLS sobre las cinco") if pol >= 5 else \
            mal(f"solo {pol} politicas RLS")

        publico = con.execute(
            "select p.proname from pg_proc p join pg_namespace n "
            "on n.oid=p.pronamespace where n.nspname='asistente' "
            "and p.proname like 'job%' "
            "and has_function_privilege('public', p.oid, 'execute')").fetchall()
        ok("PUBLIC no puede ejecutar ninguna funcion job_*") if not publico \
            else mal(f"PUBLIC puede ejecutar: {[p[0] for p in publico]}")

        cat = con.execute("select count(*) from asistente.job_catalogo").fetchone()[0]
        ok("el catalogo de jobs queda VACIO") if cat == 0 else \
            mal(f"la migracion sembro {cat} job(s): se encenderian solos")

        archivos = {Path(f).name for f in glob.glob(str(RAIZ / "supabase" / "*.sql"))}
        led = {f[0]: f[1] for f in con.execute(
            "select archivo, origen from asistente.migraciones_aplicadas").fetchall()}
        ok(f"el ledger anota los {len(archivos)} archivos, todos 'aplicada'") \
            if set(led) == archivos and set(led.values()) == {"aplicada"} else \
            mal(f"ledger incompleto o con otro origen: faltan "
                f"{sorted(archivos - set(led))}, sobran {sorted(set(led) - archivos)}")
    return malas


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="p2_cero")
    p.add_argument("--host", default=os.environ.get("DBHOST", "localhost"))
    p.add_argument("--puerto", default=os.environ.get("DBPORT", "55435"))
    p.add_argument("--usuario", default=os.environ.get("DBUSER", "motor"))
    p.add_argument("--clave", default=os.environ.get("DBPASSWORD", "motor"))
    p.add_argument("--verificar-solo", action="store_true")
    p.add_argument("--sin-recrear", action="store_true",
                   help="no borra la base: para la SEGUNDA pasada")
    a = p.parse_args(argv)

    if a.host not in HOSTS_LOCALES:
        print(f"[cero] '{a.host}' no es un host local. Este script crea y "
              f"BORRA bases; no se lo apunta a un servidor remoto.")
        return 2

    if a.verificar_solo:
        paso(4, "comprobacion")
        return 1 if verificar(a.base, a.host, a.puerto, a.usuario, a.clave) else 0

    if not a.sin_recrear:
        paso(0, f"crear la base '{a.base}' vacia")
        crear_base(a.base, a.host, a.puerto, a.usuario, a.clave)

    paso(1, "pgcrypto en el schema 'ext'")
    pgcrypto(a.base, a.host, a.puerto, a.usuario, a.clave)

    paso(2, "migraciones de Django (crean public.organization)")
    if django(a.base, a.host, a.puerto, a.usuario, a.clave) != 0:
        print("\n[cero] Django fallo. La cadena no continua: los archivos de "
              "supabase/ dependen de public.organization.")
        return 1

    paso(3, "migraciones de asistente, por el ledger")
    codigo = asistente(a.base, a.host, a.puerto, a.usuario, a.clave)
    if codigo != 0:
        print(f"\n[cero] el migrador termino en {codigo}; la cadena no continua.")
        return 1

    paso(4, "comprobacion de tablas, constraints, funciones, RLS, grants y ledger")
    malas = verificar(a.base, a.host, a.puerto, a.usuario, a.clave)
    print()
    if malas:
        print(f"[cero] {len(malas)} comprobacion(es) fallaron.")
        return 1
    print("[cero] base construida desde cero y verificada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
