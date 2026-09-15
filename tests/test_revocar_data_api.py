# -*- coding: utf-8 -*-
"""
================================================================================
 REVOCAR LA DATA API  --  anon y authenticated sin acceso a public
================================================================================

    py -3.13 tests/test_revocar_data_api.py

Por que existe
--------------
El 15/09/2026 produccion tenia a anon y authenticated con CRUD sobre las 129
tablas de public (por los default privileges de la plantilla de Supabase) y
PostgREST publicado. La ruta se cerro en Kong; supabase/seguridad/ tiene los
dos SQL que cierran el permiso. Esta prueba los corre sobre la IMAGEN EXACTA
de produccion (fijada por digest), con el 'postgres' sin superusuario, Django
migrado y la cadena del ledger aplicada, y afirma sobre el EFECTO:

  1. antes: el problema existe (anon lee public.organization) -- sin esto la
     prueba no podria ver nada
  2. falla cerrado: parte 1 con otro rol, parte 2 antes que la 1, y una tabla
     que postgres no puede revocar -> abortan y NO queda nada aplicado
  3. despues de las dos partes: ningun privilegio efectivo de anon/authenticated
     sobre relaciones de public; sin EXECUTE directo; defaults limpios;
     SET ROLE anon / authenticated da 42501 en SELECT, INSERT y nextval
  4. lo que NO debia cambiar no cambio: service_role, crm_user, motor_user,
     app_backend, PUBLIC y los demas schemas, comparados ACL por ACL
  5. objetos NUEVOS creados por postgres y por supabase_admin en public no le
     dan nada a anon; crm_user sigue recibiendo lo suyo
  6. idempotente, y Django + el ledger siguen funcionando despues

Y deja escrito lo que NO cierra: anon conserva USAGE sobre public y EXECUTE
sobre las funciones de extension, a traves de PUBLIC.
================================================================================
"""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

IMG = "supabase/postgres@sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00"
PARTE1 = RAIZ / "supabase" / "seguridad" / "revocar_data_api_postgres.sql"
PARTE2 = RAIZ / "supabase" / "seguridad" / "revocar_data_api_supabase_admin.sql"

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


if not shutil.which("docker"):
    print("  [saltado] hace falta Docker")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402

from cli import base_desde_cero as cero                           # noqa: E402


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


NOMBRE = f"dexter-revocar-data-api-{secrets.token_hex(3)}"
PUERTO = str(puerto_libre())
CLAVE = secrets.token_urlsafe(24)


def dsn(usuario="supabase_admin"):
    return (f"host=127.0.0.1 port={PUERTO} dbname=postgres user={usuario} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


def q(sql, params=None, usuario="supabase_admin"):
    with psycopg.connect(dsn(usuario), autocommit=True) as con:
        cur = con.execute(sql, params)
        return cur.fetchall() if cur.description else []


def correr_archivo(ruta: Path, usuario: str):
    """Ejecuta el archivo entero en una conexion nueva. Devuelve (ok, error, avisos)."""
    avisos: list[str] = []
    con = psycopg.connect(dsn(usuario), autocommit=True)
    con.add_notice_handler(lambda d: avisos.append(f"{d.severity}: {d.message_primary}"))
    try:
        con.execute(ruta.read_text(encoding="utf-8"))
        return True, "", avisos
    except psycopg.Error as e:
        return False, f"{e.sqlstate}: {str(e).splitlines()[0]}", avisos
    finally:
        con.close()


def como_rol(rol: str, sentencia: str):
    """SET ROLE desde postgres (miembro de anon/authenticated) y devuelve el SQLSTATE, o 'ok'."""
    with psycopg.connect(dsn("postgres"), autocommit=True) as con:
        try:
            con.execute(f"set role {rol}")
            con.execute(sentencia)
            return "ok"
        except psycopg.Error as e:
            return e.sqlstate


# (tipo, schema, objeto, grantor, grantee, privilegio, grantable). El schema va aparte porque
# regclass/regprocedure omiten el prefijo cuando el schema esta en el search_path.
ACL_TODO = """
select 'relacion', n.nspname, c.relname, pg_get_userbyid(a.grantor), pg_get_userbyid(a.grantee), a.privilege_type, a.is_grantable
from pg_class c join pg_namespace n on n.oid = c.relnamespace
cross join lateral aclexplode(coalesce(c.relacl, acldefault((case when c.relkind = 'S' then 's' else 'r' end)::"char", c.relowner))) a
where c.relkind in ('r','v','m','p','f','S') and n.nspname not like 'pg\\_%' and n.nspname <> 'information_schema'
union all
select 'funcion', n.nspname, p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',
       pg_get_userbyid(a.grantor), pg_get_userbyid(a.grantee), a.privilege_type, a.is_grantable
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
where n.nspname not like 'pg\\_%' and n.nspname <> 'information_schema'
union all
select 'schema', n.nspname, n.nspname, pg_get_userbyid(a.grantor), pg_get_userbyid(a.grantee), a.privilege_type, a.is_grantable
from pg_namespace n cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
where n.nspname not like 'pg\\_temp\\_%' and n.nspname not like 'pg\\_toast\\_temp\\_%'
union all
select 'default:' || pg_get_userbyid(d.defaclrole) || ':' || d.defaclobjtype::text, coalesce(n.nspname, '(global)'), '',
       pg_get_userbyid(a.grantor), pg_get_userbyid(a.grantee), a.privilege_type, a.is_grantable
from pg_default_acl d left join pg_namespace n on n.oid = d.defaclnamespace
cross join lateral aclexplode(d.defaclacl) a
"""


def acl():
    return {tuple(f) for f in q(ACL_TODO)}


def de_anon_en_public(filas):
    """Las entradas que los SQL SI deben quitar: anon/authenticated en public (objetos, schema y defaults)."""
    return {f for f in filas if f[4] in ("anon", "authenticated") and f[1] == "public"}


def privilegios_efectivos_anon():
    return q("""
        select r.rol, count(*)
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        cross join (values ('anon'), ('authenticated')) r(rol)
        where n.nspname = 'public'
          and ((c.relkind in ('r','v','m','p','f')
                and has_table_privilege(r.rol, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN'))
            or (c.relkind = 'S' and has_sequence_privilege(r.rol, c.oid, 'USAGE,SELECT,UPDATE')))
        group by 1 order by 1""")


def arrancar():
    subprocess.run(["docker", "rm", "-f", NOMBRE], capture_output=True)
    r = subprocess.run(["docker", "run", "-d", "--name", NOMBRE, "-e", "POSTGRES_PASSWORD",
                        "-p", f"127.0.0.1:{PUERTO}:5432", IMG],
                       capture_output=True, text=True, env={**os.environ, "POSTGRES_PASSWORD": CLAVE})
    if r.returncode != 0:
        raise RuntimeError(f"docker run: {r.stderr[-500:]}")
    limite = time.monotonic() + 900
    while True:
        try:
            if q("select rolsuper from pg_roles where rolname = 'postgres'") == [(False,)]:
                time.sleep(3)
                q("select 1")
                return
        except psycopg.Error:
            pass
        if time.monotonic() > limite:
            raise RuntimeError("la instancia no quedo lista")
        time.sleep(2)


def env_db(usuario):
    e = {k: v for k, v in os.environ.items() if not k.startswith("MIGRAR_PRUEBA_")}
    e.pop("PGOPTIONS", None)
    e.update({"DBHOST": "127.0.0.1", "DBPORT": PUERTO, "DBNAME": "postgres", "DBUSER": usuario,
              "DBPASSWORD": CLAVE, "PYTHONUNBUFFERED": "1"})
    return e


try:
    titulo("instancia: imagen exacta de produccion, Django, ledger, roles de produccion")
    arrancar()
    img = subprocess.run(["docker", "inspect", "-f", "{{.Config.Image}}", NOMBRE], capture_output=True, text=True).stdout.strip()
    revisar(img == IMG, "el contenedor corre la imagen fijada por digest", img)
    revisar(q("select current_setting('server_version_num')::int")[0][0] == 170006, "PostgreSQL 17.6")
    revisar(q("select rolsuper, rolbypassrls from pg_roles where rolname='postgres'")[0] == (False, True),
            "postgres sin superusuario y con BYPASSRLS, como produccion")
    for ext in ("pg_trgm", "vector"):
        q(f"create extension if not exists {ext} with schema public", usuario="postgres")

    r = subprocess.run(cero.comando_django("postgres", "127.0.0.1", PUERTO, "postgres"), capture_output=True,
                       text=True, env=env_db("postgres"), timeout=1500)
    if not revisar(r.returncode == 0, "Django migra como postgres", (r.stderr or "")[-800:].replace(CLAVE, "<clave>")):
        raise SystemExit(1)
    # crm_user y motor_user son prerrequisitos de despliegue: existen ANTES del ledger.
    # Sus permisos sobre public los da la cadena (202609141110_roles_operativos_public.sql).
    with psycopg.connect(dsn("supabase_admin"), autocommit=True) as con:
        cero.preparar_roles_de_despliegue(con)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migrar_asistente.py"), "--aplicar"],
                       capture_output=True, text=True, env=env_db("postgres"), timeout=1500)
    if not revisar(r.returncode == 0, "el ledger aplica la cadena como postgres",
                   ((r.stdout or "") + (r.stderr or ""))[-800:].replace(CLAVE, "<clave>")):
        raise SystemExit(1)

    # La membresia de motor_user en app_backend tambien es del despliegue, no de la cadena.
    q("grant app_backend to motor_user", usuario="postgres")
    tablas, sin_rls = q("select count(*), count(*) filter (where not c.relrowsecurity) from pg_class c "
                        "join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r'")[0]
    print(f"       public: {tablas} tablas, {sin_rls} sin RLS")

    titulo("1. antes: el problema existe")
    antes = acl()
    efectivos = dict(privilegios_efectivos_anon())
    revisar(efectivos.get("anon", 0) >= tablas and efectivos.get("authenticated", 0) >= tablas,
            f"anon y authenticated tienen privilegios efectivos sobre todas las relaciones de public ({efectivos})")
    revisar(como_rol("anon", "select 1 from public.organization limit 1") == "ok",
            "control: SET ROLE anon lee public.organization (la prueba puede ver el acceso)")
    quitar = de_anon_en_public(antes)
    print(f"       entradas de ACL que los SQL deben quitar: {len(quitar)}")

    titulo("2. falla cerrado, sin dejar nada aplicado")
    ok, err, _ = correr_archivo(PARTE1, "supabase_admin")
    revisar(not ok and "debe correr como postgres" in err, "parte 1 con supabase_admin: aborta por el rol", err)
    ok, err, _ = correr_archivo(PARTE2, "postgres")
    revisar(not ok and "debe correr como supabase_admin" in err, "parte 2 con postgres: aborta por el rol", err)
    revisar(acl() == antes, "y no cambio ninguna ACL")

    ok, err, _ = correr_archivo(PARTE2, "supabase_admin")
    revisar(not ok and "default privileges de postgres o supabase_admin" in err,
            "parte 2 antes que la 1: aborta porque los defaults de postgres siguen concediendo", err)
    revisar(acl() == antes, "y el rollback no dejo ni uno de sus REVOKE")

    q("create table public.ajena_de_admin (id int)", usuario="supabase_admin")
    antes_ajena = acl()
    revisar(como_rol("anon", "select 1 from public.ajena_de_admin") == "ok",
            "control: una tabla de supabase_admin en public nace legible por anon (sus default privileges)")
    ok, err, avisos = correr_archivo(PARTE1, "postgres")
    revisar(not ok and ("privilegios efectivos" in err or err.startswith("42501")),
            "parte 1 con una tabla que postgres no puede revocar: aborta", err)
    revisar(acl() == antes_ajena, "y no quedo aplicado nada: anon conserva todo, tambien sobre las tablas de postgres")
    print(f"       avisos del servidor en ese intento: {sorted(set(avisos))[:4]}")
    q("drop table public.ajena_de_admin", usuario="supabase_admin")
    revisar(acl() == antes, "la base vuelve exactamente al estado inicial")

    # La postcondicion "nada mas cambio" tiene que DISPARAR, no solo existir: una copia de la
    # parte 1 que ademas le quita algo a crm_user debe abortar entera.
    import tempfile
    texto = PARTE1.read_text(encoding="utf-8")
    marca = "-- POSTCONDICIONES."
    revisar(texto.count(marca) == 1, "la parte 1 tiene un unico bloque de postcondiciones donde inyectar el control")
    with tempfile.TemporaryDirectory() as tmp:
        alterada = Path(tmp) / "parte1_que_toca_crm_user.sql"
        alterada.write_text(texto.replace(marca, "revoke select on public.organization from crm_user;\n\n" + marca),
                            encoding="utf-8")
        ok, err, _ = correr_archivo(alterada, "postgres")
    revisar(not ok and "cambio un privilegio que no era de anon/authenticated" in err and "crm_user" in err,
            "control: si el SQL tocara a crm_user, la postcondicion lo detecta y aborta", err[:300])
    revisar(acl() == antes, "y ese intento tampoco dejo nada aplicado")

    titulo("3. parte 1 (postgres) y parte 2 (supabase_admin)")
    ok, err, avisos = correr_archivo(PARTE1, "postgres")
    revisar(ok, "parte 1 aplica como postgres", err)
    print(f"       avisos: {sorted(set(avisos)) or 'ninguno'}")
    if not ok:
        raise SystemExit(1)
    tras1 = acl()
    ok, err, avisos = correr_archivo(PARTE2, "supabase_admin")
    revisar(ok, "parte 2 aplica como supabase_admin", err)
    print(f"       avisos: {sorted(set(avisos)) or 'ninguno'}")
    despues = acl()

    revisar(privilegios_efectivos_anon() == [], "ningun privilegio efectivo de anon/authenticated sobre relaciones de public",
            f"{privilegios_efectivos_anon()}")
    revisar(de_anon_en_public(despues) == set(), "ninguna entrada de anon/authenticated en ACL de public (objetos, schema, defaults)",
            f"{sorted(de_anon_en_public(despues))[:5]}")
    revisar(antes - despues == quitar, "lo unico que desaparecio es exactamente lo de anon/authenticated en public",
            f"de mas: {sorted((antes - despues) - quitar)[:5]}  faltan: {sorted(quitar - (antes - despues))[:5]}")
    revisar(despues - antes == set(), "y no aparecio ningun privilegio nuevo", f"{sorted(despues - antes)[:5]}")

    seq = q("select c.oid::regclass::text from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relkind='S' order by 1 limit 1")[0][0]
    for rol in ("anon", "authenticated"):
        revisar(como_rol(rol, "select 1 from public.organization limit 1") == "42501", f"SET ROLE {rol}: SELECT -> 42501")
        revisar(como_rol(rol, "insert into public.organization default values") == "42501", f"SET ROLE {rol}: INSERT -> 42501")
        revisar(como_rol(rol, f"select nextval('{seq}')") == "42501", f"SET ROLE {rol}: nextval -> 42501")
        revisar(como_rol(rol, "truncate public.organization") == "42501", f"SET ROLE {rol}: TRUNCATE -> 42501")

    titulo("4. lo que no debia cambiar")
    otros = lambda filas: {f for f in filas if f[4] not in ("anon", "authenticated")}  # noqa: E731
    revisar(otros(antes) == otros(despues), "ACL de todos los demas roles (PUBLIC incluido) identicas en TODOS los schemas")
    fuera_de_public = lambda filas: {f for f in filas if f[4] in ("anon", "authenticated")} - de_anon_en_public(filas)  # noqa: E731
    revisar(fuera_de_public(antes) == fuera_de_public(despues),
            "anon/authenticated conservan lo suyo en storage, graphql, graphql_public, auth y extensions")
    for rol, priv in (("service_role", "SELECT,INSERT,UPDATE,DELETE"), ("crm_user", "SELECT,INSERT,UPDATE,DELETE"),
                      ("motor_user", "SELECT")):
        revisar(q("select has_table_privilege(%s, 'public.organization', %s)", (rol, priv))[0][0],
                f"{rol} sigue con {priv} sobre public.organization")
    revisar(q("select pg_has_role('authenticator', 'anon', 'MEMBER') and pg_has_role('authenticator', 'authenticated', 'MEMBER')")[0][0],
            "authenticator sigue pudiendo cambiar a anon/authenticated (membresias intactas)")

    usage = q("select has_schema_privilege('anon', 'public', 'USAGE')")[0][0]
    fn = q("select p.oid::regprocedure::text from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
           "join pg_depend d on d.classid='pg_proc'::regclass and d.objid=p.oid and d.deptype='e' "
           "where n.nspname='public' order by 1 limit 1")[0][0]
    ejecuta = q("select has_function_privilege('anon', %s, 'EXECUTE')", (fn,))[0][0]
    revisar(usage and ejecuta, "LIMITE documentado: anon conserva USAGE sobre public y EXECUTE en funciones de extension "
            f"a traves de PUBLIC (usage={usage}, execute {fn}={ejecuta})")

    titulo("5. objetos nuevos")
    q("create table public.nueva_de_postgres (id serial primary key)", usuario="postgres")
    q("create table public.nueva_de_admin (id serial primary key)", usuario="supabase_admin")
    q("create function public.nueva_fn_postgres() returns int language sql as 'select 1'", usuario="postgres")
    for t in ("public.nueva_de_postgres", "public.nueva_de_postgres_id_seq", "public.nueva_de_admin", "public.nueva_de_admin_id_seq"):
        tiene = q("select exists (select 1 from aclexplode(coalesce(relacl, acldefault('r', relowner))) a "
                  "where a.grantee in ('anon'::regrole, 'authenticated'::regrole)) from pg_class where oid = %s::regclass", (t,))[0][0]
        revisar(not tiene, f"{t}: nace sin nada para anon/authenticated")
    revisar(not q("select exists (select 1 from aclexplode(proacl) a where a.grantee in ('anon'::regrole,'authenticated'::regrole)) "
                  "from pg_proc where oid = 'public.nueva_fn_postgres()'::regprocedure")[0][0],
            "public.nueva_fn_postgres(): nace sin EXECUTE directo para anon/authenticated")
    revisar(q("select has_table_privilege('crm_user', 'public.nueva_de_postgres', 'SELECT,INSERT,UPDATE,DELETE')")[0][0],
            "crm_user sigue recibiendo sus privilegios en lo que crea postgres")
    revisar(q("select has_table_privilege('service_role', 'public.nueva_de_admin', 'SELECT')")[0][0],
            "service_role sigue recibiendo sus privilegios en lo que crea supabase_admin")
    q("drop table public.nueva_de_postgres; drop function public.nueva_fn_postgres()", usuario="postgres")
    q("drop table public.nueva_de_admin", usuario="supabase_admin")

    titulo("6. idempotente, y la aplicacion sigue funcionando")
    ok1, err1, _ = correr_archivo(PARTE1, "postgres")
    ok2, err2, _ = correr_archivo(PARTE2, "supabase_admin")
    revisar(ok1 and ok2 and acl() == despues, "correr las dos partes otra vez deja exactamente lo mismo", f"{err1} {err2}")
    r = subprocess.run(cero.comando_django("postgres", "127.0.0.1", PUERTO, "postgres"), capture_output=True,
                       text=True, env=env_db("postgres"), timeout=1500)
    revisar(r.returncode == 0, "Django migrate sigue corriendo como postgres", (r.stderr or "")[-500:].replace(CLAVE, "<clave>"))
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migrar_asistente.py"), "--estado"],
                       capture_output=True, text=True, env=env_db("postgres"), timeout=300)
    revisar(r.returncode == 0, "el ledger sigue leyendo su estado", ((r.stdout or "") + (r.stderr or ""))[-500:].replace(CLAVE, "<clave>"))
finally:
    subprocess.run(["docker", "rm", "-f", NOMBRE], capture_output=True)

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("OK: revocar la Data API cierra anon/authenticated sobre public sin tocar nada mas")
