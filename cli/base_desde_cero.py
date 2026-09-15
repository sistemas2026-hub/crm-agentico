# -*- coding: utf-8 -*-
"""
================================================================================
 UNA BASE DESDE CERO  --  el orden canonico, ejecutable
================================================================================

    DBPASSWORD=... py -3.13 cli/base_desde_cero.py --base p2_cero
    DBPASSWORD=... py -3.13 cli/base_desde_cero.py --base p2_cero --sin-recrear
    DBPASSWORD=... py -3.13 cli/base_desde_cero.py --base p2_cero --verificar-solo

    1. La extension pgcrypto en el schema 'extensions' (una vez; como Supabase)
    2. Las migraciones de Django                     (crea public.organization)
    3. Los archivos de supabase/, POR EL LEDGER      (cli/migrar_asistente.py)
    4. Comprobacion: tablas, constraints, funciones, RLS, grants y ledger

El paso 2 va ANTES del 3: 'supabase/202608042055_schema.sql' referencia
'public.organization(id)', que la crea Django. El paso 3 va por el ledger: lo
anotado no se reejecuta, asi que la segunda pasada termina con 0 pendientes.

Seguridad de la propia herramienta
----------------------------------
Crea y BORRA bases, asi que:

  * solo acepta hosts locales;
  * el nombre de la base se valida contra ^[a-z_][a-z0-9_]{0,62}$ ANTES de
    conectarse, y en el SQL va como identificador de psycopg, nunca interpolado.
    La version anterior hacia f'drop database if exists "{base}"': un nombre con
    comillas cortaba el identificador;
  * la contraseña sale SOLO del entorno (DBPASSWORD). No hay '--clave': un
    argumento de linea de comandos se ve en 'ps' y queda en el historial de la
    shell;
  * al contenedor de Django se le pasa '-e DBPASSWORD' SIN valor: docker lo toma
    del entorno del proceso. La version anterior armaba '-e DBPASSWORD=<valor>',
    que queda visible en los argumentos del proceso docker, y ademas imprimia el
    comando completo.
================================================================================
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import psycopg                                                    # noqa: E402
from psycopg import sql                                           # noqa: E402

HOSTS_LOCALES = {"localhost", "127.0.0.1", "db", "host.docker.internal"}
IMAGEN_DJANGO = os.environ.get("IMAGEN_DJANGO", "dexter-backend:latest")
NOMBRE_VALIDO = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def conectar(base: str, host: str, puerto: str, usuario: str) -> psycopg.Connection:
    return psycopg.connect(host=host, port=puerto, dbname=base, user=usuario,
                           password=os.environ["DBPASSWORD"], sslmode="disable",
                           autocommit=True)


def paso(n: int, que: str) -> None:
    print(f"\n{'=' * 74}\n  PASO {n}: {que}\n{'=' * 74}", flush=True)


def crear_base(base, host, puerto, usuario) -> None:
    with conectar("postgres", host, puerto, usuario) as con:
        con.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(base)))
        con.execute(sql.SQL("create database {}").format(sql.Identifier(base)))
    print(f"  base '{base}' creada, vacia")


def pgcrypto(base, host, puerto, usuario) -> None:
    with conectar(base, host, puerto, usuario) as con:
        # 'extensions', como en Supabase y en produccion. Si pgcrypto ya estuviera
        # en otro schema, 'if not exists' no la mueve y la comprobacion de abajo
        # lo detiene.
        con.execute("create schema if not exists extensions")
        con.execute("create extension if not exists pgcrypto with schema extensions")
        for f in ("extensions.digest(text,text)", "extensions.gen_random_bytes(integer)"):
            hay = con.execute("select to_regprocedure(%s) is not null", (f,)).fetchone()[0]
            print(f"  {f}: {'presente' if hay else 'FALTA'}")
            if not hay:
                raise SystemExit(f"pgcrypto incompleto: falta {f}")


def comando_django(base, host, puerto, usuario) -> list[str]:
    """
    El comando de docker. NO contiene la contraseña: '-e DBPASSWORD' sin valor
    hace que docker la tome del entorno del proceso que lo lanza.
    """
    host_cont = "host.docker.internal" if host in ("localhost", "127.0.0.1") else host
    backend = (RAIZ / "django-crm" / "backend").as_posix()
    return [
        "docker", "run", "--rm",
        "-v", f"{backend}:/app",
        "-e", f"DBHOST={host_cont}", "-e", f"DBPORT={puerto}",
        "-e", f"DBNAME={base}", "-e", f"DBUSER={usuario}",
        "-e", "DBPASSWORD",
        "-e", "DJANGO_SETTINGS_MODULE=crm.settings",
        "-e", "SECRET_KEY=solo-para-migrar-una-base-local",
        "-e", "DEBUG=0", "-e", "ALLOWED_HOSTS=*",
        IMAGEN_DJANGO,
        "python3", "manage.py", "migrate", "--noinput",
    ]


def django(base, host, puerto, usuario) -> int:
    cmd = comando_django(base, host, puerto, usuario)
    print("  " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ))
    for linea in (r.stdout or "").strip().splitlines()[-25:]:
        print(f"    {linea}")
    if r.returncode != 0:
        print(f"    [stderr] {(r.stderr or '').strip()[-2000:]}")
    print(f"  exit={r.returncode}")
    return r.returncode


def asistente(base, host, puerto, usuario) -> int:
    """Los archivos de supabase/, a traves del ledger. Devuelve su codigo de salida."""
    os.environ.update({"DBHOST": host, "DBPORT": str(puerto), "DBNAME": base,
                       "DBUSER": usuario})
    from cli import migrar_asistente as mig                       # noqa: E402

    con = mig.conectar()
    try:
        return mig.aplicar(con, 60.0)
    finally:
        con.close()


TABLAS = ("job_catalogo", "job_schedule_state", "job_run", "job_attempt",
          "job_run_event")
FUNCIONES = ("job_slot", "jobs_vencidos", "job_claim", "job_cerrar_turno",
             "job_intento_vigente", "job_intento_vigente_por_capability",
             "job_heartbeat", "job_finalize", "job_contexto", "job_salud")
ROLES = ("asistente_owner", "scheduler_coordinator", "job_executor", "monitor_ro")


def verificar(base, host, puerto, usuario) -> list[str]:
    malas: list[str] = []

    def mal(q):
        malas.append(q)
        print(f"  [FALLA] {q}")

    def ok(q):
        print(f"  [ok] {q}")

    with conectar(base, host, puerto, usuario) as con:
        hay = {f[0] for f in con.execute(
            "select tablename from pg_tables where schemaname='asistente'")}
        faltan = [t for t in TABLAS if t not in hay]
        ok(f"las {len(TABLAS)} tablas job_* existen") if not faltan else \
            mal(f"faltan tablas: {faltan}")

        props = con.execute(
            "select c.relname, r.rolname, c.relrowsecurity from pg_class c "
            "join pg_roles r on r.oid=c.relowner join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='asistente' and c.relname = any(%s)", (list(TABLAS),)).fetchall()
        malos = [p for p in props if p[1] != "asistente_owner" or not p[2]]
        ok("las cinco son de asistente_owner y tienen RLS") if not malos else \
            mal(f"propiedad/RLS mal: {malos}")

        hayf = {f[0] for f in con.execute(
            "select proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
            "where n.nspname='asistente' and proname like 'job%'")}
        faltanf = [f for f in FUNCIONES if f not in hayf]
        sobran = sorted(hayf - set(FUNCIONES))
        ok(f"las {len(FUNCIONES)} funciones existen") if not faltanf else \
            mal(f"faltan funciones: {faltanf}")
        ok("y no quedo ninguna funcion huerfana") if not sobran else \
            mal(f"funciones que la migracion ya no declara: {sobran}")

        hayr = {f[0] for f in con.execute(
            "select rolname from pg_roles where rolname = any(%s)", (list(ROLES),))}
        faltanr = [r for r in ROLES if r not in hayr]
        ok(f"los {len(ROLES)} roles existen") if not faltanr else mal(f"faltan roles: {faltanr}")

        conlogin = con.execute("select rolname from pg_roles where rolname = any(%s) "
                               "and rolcanlogin", (list(ROLES),)).fetchall()
        ok("ninguno de los cuatro puede hacer login") if not conlogin else \
            mal(f"roles con login: {conlogin}")

        n = con.execute(
            "select count(*) from pg_constraint c join pg_class t on t.oid=c.conrelid "
            "join pg_namespace n on n.oid=t.relnamespace "
            "where n.nspname='asistente' and t.relname = any(%s)", (list(TABLAS),)).fetchone()[0]
        ok(f"{n} constraints sobre las cinco tablas") if n >= 40 else \
            mal(f"solo {n} constraints, se esperaban 40 o mas")

        pol = con.execute("select count(*) from pg_policies where schemaname='asistente' "
                          "and tablename = any(%s)", (list(TABLAS),)).fetchone()[0]
        ok(f"{pol} politicas RLS sobre las cinco") if pol >= 5 else mal(f"solo {pol} politicas RLS")

        publico = con.execute(
            "select p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
            "where n.nspname='asistente' and p.proname like 'job%' "
            "and has_function_privilege('public', p.oid, 'execute')").fetchall()
        ok("PUBLIC no puede ejecutar ninguna funcion job_*") if not publico \
            else mal(f"PUBLIC puede ejecutar: {[p[0] for p in publico]}")

        explicitos = {f[0] for f in con.execute(
            "select 'schema' from pg_namespace n cross join lateral aclexplode(n.nspacl) a "
            " where n.nspname = 'extensions' and a.privilege_type = 'USAGE' "
            "   and a.grantee = 'asistente_owner'::regrole "
            "union all "
            "select p.oid::regprocedure::text from pg_proc p cross join lateral aclexplode(p.proacl) a "
            " where p.oid in ('extensions.digest(text,text)'::regprocedure, "
            "                 'extensions.gen_random_bytes(integer)'::regprocedure) "
            "   and a.privilege_type = 'EXECUTE' and a.grantee = 'asistente_owner'::regrole")}
        ok("asistente_owner: USAGE en extensions y EXECUTE explicito sobre digest y "
           "gen_random_bytes") if len(explicitos) == 3 else \
            mal(f"grants explicitos de asistente_owner incompletos: {sorted(explicitos)}")

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
    p.add_argument("--verificar-solo", action="store_true")
    p.add_argument("--sin-recrear", action="store_true",
                   help="no borra la base: para la SEGUNDA pasada")
    a = p.parse_args(argv)

    if not NOMBRE_VALIDO.match(a.base):
        print(f"[cero] nombre de base invalido: tiene que cumplir "
              f"{NOMBRE_VALIDO.pattern}. No se hizo nada.")
        return 2
    if a.host not in HOSTS_LOCALES:
        print(f"[cero] '{a.host}' no es un host local. Este script crea y "
              f"BORRA bases; no se lo apunta a un servidor remoto.")
        return 2
    if not os.environ.get("DBPASSWORD"):
        print("[cero] falta DBPASSWORD en el entorno. La contraseña no se acepta "
              "por argumento.")
        return 2

    if a.verificar_solo:
        paso(4, "comprobacion")
        return 1 if verificar(a.base, a.host, a.puerto, a.usuario) else 0

    if not a.sin_recrear:
        paso(0, f"crear la base '{a.base}' vacia")
        crear_base(a.base, a.host, a.puerto, a.usuario)

    paso(1, "pgcrypto en el schema 'extensions'")
    pgcrypto(a.base, a.host, a.puerto, a.usuario)

    paso(2, "migraciones de Django (crean public.organization)")
    if django(a.base, a.host, a.puerto, a.usuario) != 0:
        print("\n[cero] Django fallo. La cadena no continua: los archivos de "
              "supabase/ dependen de public.organization.")
        return 1

    paso(3, "migraciones de asistente, por el ledger")
    codigo = asistente(a.base, a.host, a.puerto, a.usuario)
    if codigo != 0:
        print(f"\n[cero] el migrador termino en {codigo}; la cadena no continua.")
        return 1

    paso(4, "comprobacion de tablas, constraints, funciones, RLS, grants y ledger")
    malas = verificar(a.base, a.host, a.puerto, a.usuario)
    print()
    if malas:
        print(f"[cero] {len(malas)} comprobacion(es) fallaron.")
        return 1
    print("[cero] base construida desde cero y verificada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
