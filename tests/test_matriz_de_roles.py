# -*- coding: utf-8 -*-
"""
================================================================================
 LA MATRIZ DE ROLES  --  observada en la base, no declarada en un comentario
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=test_p2 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_matriz_de_roles.py

Por que existe
--------------
Un diseño de permisos escrito en un docstring no es un diseño de permisos. Ya
paso una vez en este repo, y salio caro: 'manage_rls --status' informaba que el
aislamiento estaba bien porque miraba 'usesuper', que NO expone 'rolbypassrls'.
El rol de pruebas tenia los dos atributos y las pruebas de RLS pasaban en verde
sobre un motor que no estaba aplicando ninguna politica.

Asi que esto CONSULTA el catalogo de PostgreSQL y ademas PRUEBA cada rol
haciendo lo que no deberia poder hacer. Las dos cosas: el catalogo dice como
quedo configurado, la prueba dice que efectivamente no puede.

Imprime la matriz completa aunque todo pase: es la evidencia que se entrega.
================================================================================
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

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


faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

DSN = (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
       f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
       f"password={os.environ['DBPASSWORD']} sslmode=disable")

TABLAS = ("job_catalogo", "job_schedule_state", "job_run", "job_attempt",
          "job_run_event")
RUNTIME = ("scheduler_coordinator", "job_executor", "monitor_ro", "app_backend")
TODOS = ("asistente_owner",) + RUNTIME

con = psycopg.connect(DSN, autocommit=True, row_factory=dict_row)
try:
    # =========================================================================
    titulo("1. atributos de rol")
    # =========================================================================
    print(f"    {'rol':<24} {'super':>6} {'bypassrls':>10} {'inherit':>8} "
          f"{'login':>6}")
    atributos = {}
    for r in con.execute(
            "select rolname, rolsuper, rolbypassrls, rolinherit, rolcanlogin "
            "from pg_roles where rolname = any(%s) order by rolname",
            (list(TODOS) + [os.environ["DBUSER"]],)).fetchall():
        atributos[r["rolname"]] = r
        print(f"    {r['rolname']:<24} {str(r['rolsuper']):>6} "
              f"{str(r['rolbypassrls']):>10} {str(r['rolinherit']):>8} "
              f"{str(r['rolcanlogin']):>6}")

    for rol in TODOS:
        a = atributos.get(rol)
        revisar(a is not None, f"el rol '{rol}' existe")
        if not a:
            continue
        revisar(not a["rolsuper"], f"'{rol}' no es superusuario")
        revisar(not a["rolbypassrls"], f"'{rol}' no evade RLS")
        revisar(not a["rolcanlogin"], f"'{rol}' es NOLOGIN")

    # =========================================================================
    titulo("2. membresias")
    # =========================================================================
    filas = con.execute(
        "select m.rolname as miembro, g.rolname as grupo, a.admin_option, "
        "       a.inherit_option, a.set_option "
        "  from pg_auth_members a "
        "  join pg_roles m on m.oid = a.member "
        "  join pg_roles g on g.oid = a.roleid "
        " where g.rolname = any(%s) order by 2, 1", (list(TODOS),)).fetchall()
    for f in filas:
        print(f"    {f['miembro']} -> {f['grupo']}  admin={f['admin_option']} "
              f"inherit={f['inherit_option']} set={f['set_option']}")
    cruces = [f for f in filas if f["miembro"] in TODOS]
    revisar(not cruces,
            "ningun rol de runtime es miembro de otro",
            f"{[(c['miembro'], c['grupo']) for c in cruces]} -- "
            f"'grant app_backend to job_executor' anularia la separacion")

    # =========================================================================
    titulo("3. propiedad de schemas, tablas y funciones")
    # =========================================================================
    for f in con.execute(
            "select n.nspname as schema, r.rolname as dueño from pg_namespace n "
            "join pg_roles r on r.oid=n.nspowner where n.nspname "
            "in ('asistente','extensions','public')").fetchall():
        print(f"    schema {f['schema']:<12} -> {f['dueño']}")

    props = con.execute(
        "select c.relname, r.rolname as dueño, c.relrowsecurity as rls, "
        "       c.relforcerowsecurity as force "
        "  from pg_class c join pg_roles r on r.oid=c.relowner "
        "  join pg_namespace n on n.oid=c.relnamespace "
        " where n.nspname='asistente' and c.relname = any(%s) order by 1",
        (list(TABLAS),)).fetchall()
    for f in props:
        print(f"    tabla  {f['relname']:<22} -> {f['dueño']}  "
              f"rls={f['rls']} force={f['force']}")
    revisar(all(f["dueño"] == "asistente_owner" for f in props),
            "las cinco tablas son de asistente_owner")
    revisar(all(f["rls"] for f in props), "las cinco tienen RLS habilitado")
    revisar(not any(f["force"] for f in props),
            "y ninguna tiene FORCE: el dueño ve todas las filas desde las "
            "funciones SECURITY DEFINER, que es el unico camino")

    funcs = con.execute(
        "select p.oid, p.proname, "
        "       pg_get_function_identity_arguments(p.oid) as args, "
        "       r.rolname as dueño, p.prosecdef, p.proconfig, p.proacl::text as acl "
        "  from pg_proc p join pg_roles r on r.oid=p.proowner "
        "  join pg_namespace n on n.oid=p.pronamespace "
        " where n.nspname='asistente' and p.proname like 'job%' order by 2"
    ).fetchall()
    print()
    for f in funcs:
        print(f"    {f['proname']}({f['args']})")
        print(f"        dueño={f['dueño']} secdef={f['prosecdef']} "
              f"config={f['proconfig']}")
    revisar(all(f["dueño"] == "asistente_owner" for f in funcs),
            f"las {len(funcs)} funciones son de asistente_owner")
    revisar(all(f["proconfig"] == ["search_path=pg_catalog"] for f in funcs),
            "todas fijan search_path=pg_catalog",
            f"{[(f['proname'], f['proconfig']) for f in funcs if f['proconfig'] != ['search_path=pg_catalog']]}")
    sin_secdef = [f["proname"] for f in funcs if not f["prosecdef"]]
    revisar(sin_secdef == ["job_slot"],
            "la unica sin SECURITY DEFINER es 'job_slot', que es aritmetica pura",
            f"{sin_secdef}")

    # =========================================================================
    titulo("4. ACL de schemas, tablas y funciones")
    # =========================================================================
    for f in con.execute(
            "select nspname, nspacl::text from pg_namespace "
            "where nspname in ('asistente','extensions')").fetchall():
        print(f"    schema {f['nspname']}: {f['nspacl']}")

    print()
    for f in con.execute(
            "select c.relname, c.relacl::text from pg_class c "
            "join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='asistente' and c.relname = any(%s) order by 1",
            (list(TABLAS),)).fetchall():
        print(f"    tabla {f['relname']:<22}: {f['relacl']}")
    for rol in RUNTIME:
        malas = [t for t in TABLAS
                 if any(con.execute(
                     "select has_table_privilege(%s, %s, %s) as p",
                     (rol, f"asistente.{t}", priv)).fetchone()["p"]
                     for priv in ("select", "insert", "update", "delete"))]
        revisar(not malas,
                f"'{rol}' no tiene ningun privilegio sobre las tablas job_*",
                f"lo tiene sobre {malas}")

    print()
    for f in funcs:
        print(f"    {f['proname']:<34}: {f['acl']}")

    esperado = {
        "jobs_vencidos": {"scheduler_coordinator"},
        "job_claim": {"scheduler_coordinator"},
        "job_heartbeat": {"job_executor"},
        "job_finalize": {"job_executor"},
        "job_contexto": {"job_executor"},
        "job_salud": {"monitor_ro"},
        "job_slot": set(),
        "job_cerrar_turno": set(),
        "job_intento_vigente": set(),
        "job_intento_vigente_por_capability": set(),
    }
    for f in funcs:
        # por OID, no por firma: 'pg_get_function_identity_arguments' incluye
        # los NOMBRES de los parametros y has_function_privilege no los acepta
        puede = {r for r in RUNTIME
                 if con.execute(
                     "select has_function_privilege(%s, %s::oid, 'execute') as p",
                     (r, f["oid"])).fetchone()["p"]}
        revisar(puede == esperado.get(f["proname"], set()),
                f"solo {sorted(esperado.get(f['proname'], set())) or 'nadie'} "
                f"puede ejecutar {f['proname']}",
                f"pueden: {sorted(puede)}")
        pub = con.execute(
            "select has_function_privilege('public', %s::oid, 'execute') as p",
            (f["oid"],)).fetchone()["p"]
        revisar(not pub, f"PUBLIC no puede ejecutar {f['proname']}")

    # =========================================================================
    titulo("5. politicas RLS")
    # =========================================================================
    for f in con.execute(
            "select tablename, policyname, roles::text, cmd, qual "
            "from pg_policies where schemaname='asistente' "
            "and tablename = any(%s) order by 1",
            (list(TABLAS),)).fetchall():
        print(f"    {f['tablename']:<22} {f['policyname']:<18} "
              f"roles={f['roles']} cmd={f['cmd']}")
        print(f"        using: {f['qual']}")

    # =========================================================================
    titulo("6. lo que cada rol NO puede hacer, probado")
    # =========================================================================
    for rol in ("scheduler_coordinator", "job_executor", "monitor_ro"):
        try:
            con.execute(f"grant {rol} to current_user")
        except psycopg.errors.Error:
            pass

    def como(rol, sql, params=None):
        with con.cursor() as cur:
            cur.execute("begin")
            cur.execute(f"set local role {rol}")
            try:
                cur.execute(sql, params)
                try:
                    cur.fetchall()
                except psycopg.ProgrammingError:
                    pass
                cur.execute("rollback")
                return True, ""
            except psycopg.errors.Error as e:
                cur.execute("rollback")
                return False, type(e).__name__

    pruebas = [
        ("scheduler_coordinator", "select 1 from asistente.job_run limit 1", False),
        ("scheduler_coordinator", "select 1 from asistente.job_attempt limit 1", False),
        ("scheduler_coordinator", "select 1 from cases_case limit 1", False),
        ("scheduler_coordinator", "select asistente.job_finalize(%s,'x','succeeded')", False),
        ("scheduler_coordinator", "select asistente.job_heartbeat(%s,'x')", False),
        ("job_executor", "select * from asistente.job_claim('x',%s,now(),'w')", False),
        ("job_executor", "select * from asistente.jobs_vencidos(now(),1)", False),
        ("job_executor", "select 1 from asistente.job_run limit 1", False),
        ("job_executor", "select 1 from asistente.job_schedule_state limit 1", False),
        ("monitor_ro", "select 1 from asistente.job_schedule_state limit 1", False),
        ("monitor_ro", "select * from asistente.jobs_vencidos(now(),1)", False),
        ("monitor_ro", "select * from asistente.job_claim('x',%s,now(),'w')", False),
        ("app_backend", "select 1 from asistente.job_run limit 1", False),
        ("app_backend", "select * from asistente.jobs_vencidos(now(),1)", False),
        ("app_backend", "insert into asistente.job_catalogo(code,descripcion,"
                        "anchor,intervalo) values ('x','x',now(),interval '1h')", False),
        ("scheduler_coordinator", "create table asistente.intruso(x int)", False),
        ("job_executor", "create table asistente.intruso(x int)", False),
        ("monitor_ro", "create table asistente.intruso(x int)", False),
    ]
    for rol, sql, debe_poder in pruebas:
        params = (uuid.uuid4(),) if "%s" in sql else None
        pudo, err = como(rol, sql, params)
        corto = sql[:58].replace("\n", " ")
        revisar(pudo == debe_poder,
                f"'{rol}' {'puede' if debe_poder else 'NO puede'}: {corto}",
                err or "lo hizo")

    # y lo que si tiene que poder
    for rol, sql in (("scheduler_coordinator",
                      "select * from asistente.jobs_vencidos(now(),1)"),
                     ("job_executor", "select asistente.job_heartbeat(%s,'x')"),
                     ("monitor_ro", "select * from asistente.job_salud(now())")):
        params = (uuid.uuid4(),) if "%s" in sql else None
        pudo, err = como(rol, sql, params)
        revisar(pudo, f"'{rol}' SI puede lo suyo: {sql[:50]}", err)

    # Nadie puede asumir al dueño.
    #
    # NO se mide con 'set role asistente_owner' desde una sesion con el rol
    # puesto: PostgreSQL verifica SET ROLE contra el usuario de SESION, no
    # contra el rol actual. Como el usuario de login de esta suite es miembro
    # de asistente_owner --lo necesita para correr las migraciones-- ese sondeo
    # daria verde siempre y no mediria nada. Lo que hay que preguntar es si el
    # rol tiene la membresia, que es 'pg_has_role'.
    for rol in RUNTIME:
        r = con.execute(
            "select pg_has_role(%s,'asistente_owner','USAGE') as usa, "
            "       pg_has_role(%s,'asistente_owner','MEMBER') as miembro",
            (rol, rol)).fetchone()
        revisar(not r["usa"] and not r["miembro"],
                f"'{rol}' no es miembro de asistente_owner ni hereda de el",
                f"usage={r['usa']} member={r['miembro']}")
finally:
    con.close()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] La matriz de roles observada coincide con la diseñada.")
print("=" * 74)
