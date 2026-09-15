# -*- coding: utf-8 -*-
"""
================================================================================
 A1 Y P2 EN extensions  --  la firma de 5 ya no esta, y P2 usa lo que hay en produccion
================================================================================

    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_a1_p2_extensions.py

Por que existe
--------------
La inspeccion de solo lectura de produccion (14/09/2026) encontro dos cosas que
el repositorio no reproducia: match_chunks con una sola firma (la de 6) y
pgcrypto en el schema 'extensions', no en 'ext'. A1 declara lo primero; P2 se
adapto a lo segundo antes de aplicarse en ningun entorno real.

  1. base desde cero por cli/base_desde_cero.py: la cadena entera, sin hueco
  2. A1: solo queda la firma de 6; el SQL LITERAL de busqueda.py recupera por
     rol; sin p_rol no hay filas; y el control: con la firma de 5 de vuelta, la
     llamada corta es ambigua
  3. P2: pgcrypto en extensions y sin 'ext'; grants EXPLICITOS; asistente_owner
     usa digest y gen_random_bytes aunque PUBLIC no pueda; la comprobacion de
     P2 aborta si el grant explicito no quedo; las guardas rechazan 'ext'
  4. una base con los bytes VIEJOS de P2 falla cerrado por checksum
  5. P2 aplicado por un rol como el 'postgres' de Supabase --sin superusuario,
     con CREATEROLE, dueño de 'extensions', EXECUTE con grant option-- en un
     PostgreSQL efimero propio: la cadena entera en el ledger, roles, los 15
     dueños, sin CREATE residual, grants de pgcrypto; y el control negativo:
     sin el CREATE temporal, ese rol no puede pasarle una tabla a asistente_owner

  En 3 ademas: los 15 dueños, sin CREATE, y las postcondiciones de P2 abortando
  cuando se les rompe una tabla, una funcion o se deja CREATE puesto.

Lo que NO prueba: supautils ni PostgreSQL 17. Eso es la referencia con la
imagen exacta de produccion.
================================================================================
"""

from __future__ import annotations

import ast
import io
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from datetime import date, datetime, timezone
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


faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)
if not shutil.which("docker") or not shutil.which("git"):
    print("  [saltado] hacen falta Docker y git")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402
from psycopg import sql                                           # noqa: E402
from psycopg.types.json import Jsonb                              # noqa: E402

from cli import base_desde_cero as cero                           # noqa: E402
from cli.manifiesto_adopcion import dividir                       # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
PREFIJO = os.environ.get("DBNAME", "a1p2")
BASE, VACIA, VIEJA = PREFIJO + "_cero", PREFIJO + "_guardas", PREFIJO + "_p2_viejo"
IMAGEN_PG = os.environ.get("IMAGEN_PG_EFIMERA", "pgvector/pgvector:pg16")
PUERTO_EFIMERO = os.environ.get("PUERTO_EFIMERO", "55441")
COMMIT_P2_VIEJO = "fc9e897522b13c943d7f4dfb4df155f866a45a4c"

A1 = "202609141100_match_chunks_firma_5_obsoleta.sql"
P2 = ("202609141200_scheduler_persistente.sql", "202609141300_scheduler_funciones.sql")
FIRMA_6 = ("p_org uuid, p_query_embedding vector, p_match_count integer, "
           "p_umbral real, p_filtros jsonb, p_rol text")
FUNCIONES_PGCRYPTO = {"extensions.digest(text,text)", "extensions.gen_random_bytes(integer)"}
TABLAS_P2 = ("job_catalogo", "job_schedule_state", "job_run", "job_attempt", "job_run_event")
FUNCIONES_P2 = ("asistente.job_slot(timestamptz, interval, timestamptz)",
                "asistente.jobs_vencidos(timestamptz, int)",
                "asistente.job_claim(text, uuid, timestamptz, text, jsonb)",
                "asistente.job_cerrar_turno(uuid, text, timestamptz)",
                "asistente.job_intento_vigente(uuid, text)",
                "asistente.job_heartbeat(uuid, text)",
                "asistente.job_finalize(uuid, text, text, text)",
                "asistente.job_contexto(uuid, text)",
                "asistente.job_intento_vigente_por_capability(text)",
                "asistente.job_salud(timestamptz)")
REVOCA_PUBLIC = ("revoke execute on function extensions.digest(text,text), "
                 "extensions.gen_random_bytes(integer) from public")
USA_PGCRYPTO = ("select length(extensions.digest('x', 'sha256')), "
                "length(extensions.gen_random_bytes(4))")


def dsn(base, puerto=PUERTO, usuario=USUARIO, clave=CLAVE, host=HOST):
    # connect_timeout: una conexion que no llega tiene que fallar, no colgar la prueba.
    return (f"host={host} port={puerto} dbname={base} user={usuario} password={clave} "
            f"sslmode=disable connect_timeout=15")


def paso(texto):
    print(f"       -> {texto}", flush=True)


def consultar(base, q, params=None, **kw):
    with psycopg.connect(dsn(base, **kw), autocommit=True) as con:
        cur = con.execute(q, params)
        return cur.fetchall() if cur.description else []


def error_en(base, *sentencias, **kw):
    """(sqlstate, primera linea) del primer error, en una transaccion que se deshace siempre."""
    with psycopg.connect(dsn(base, **kw)) as con:
        try:
            for s in sentencias:
                con.execute(s)
        except psycopg.Error as e:
            con.rollback()
            return e.sqlstate, (str(e).splitlines() or [""])[0]
        con.rollback()
        return None, ""


def recrear(base, plantilla=None):
    with psycopg.connect(dsn("postgres"), autocommit=True) as con:
        for _ in range(40):
            con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                        "where datname = any(%s) and pid <> pg_backend_pid()",
                        ([base, plantilla or base],))
            try:
                con.execute(f'drop database if exists "{base}"')
                con.execute(f'create database "{base}"' + (f' template "{plantilla}"' if plantilla else ""))
                return
            except (psycopg.errors.ObjectInUse, psycopg.errors.DuplicateDatabase):
                time.sleep(0.5)
        raise RuntimeError(f"no se pudo crear {base}")


def borrar(base):
    with psycopg.connect(dsn("postgres"), autocommit=True) as con:
        con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname = %s and pid <> pg_backend_pid()", (base,))
        con.execute(f'drop database if exists "{base}"')


def sentencia(archivo, *contiene):
    """La primera sentencia del archivo que contiene todos los fragmentos."""
    texto = (RAIZ / "supabase" / archivo).read_bytes().decode("utf-8")
    for s in dividir(texto):
        if all(c in s for c in contiene):
            return s
    raise RuntimeError(f"{archivo}: no hay sentencia con {contiene}")


def explicitos(base, **kw) -> dict:
    """Entradas EXPLICITAS de asistente_owner en las ACL (sin contar PUBLIC) -> quien las otorgo."""
    return dict(consultar(base, """
        select 'schema extensions', pg_get_userbyid(a.grantor)
          from pg_namespace n cross join lateral aclexplode(n.nspacl) a
         where n.nspname = 'extensions' and a.privilege_type = 'USAGE'
           and a.grantee = (select oid from pg_roles where rolname = 'asistente_owner')
        union all
        select p.oid::regprocedure::text, pg_get_userbyid(a.grantor)
          from pg_proc p cross join lateral aclexplode(p.proacl) a
         where p.oid in ('extensions.digest(text,text)'::regprocedure,
                         'extensions.gen_random_bytes(integer)'::regprocedure)
           and a.privilege_type = 'EXECUTE'
           and a.grantee = (select oid from pg_roles where rolname = 'asistente_owner')""", **kw))


def duenos_15(base, **kw):
    """(objeto, dueño) de las 5 tablas y las 10 funciones de P2, por nombre y firma exactos."""
    return consultar(base, """
        select 'asistente.' || t,
               (select pg_get_userbyid(relowner) from pg_class where oid = to_regclass('asistente.' || t))
          from unnest(%s::text[]) t
        union all
        select f, (select pg_get_userbyid(proowner) from pg_proc where oid = to_regprocedure(f))
          from unnest(%s::text[]) f""", (list(TABLAS_P2), list(FUNCIONES_P2)), **kw)


def fila_minima(cur, esquema, tabla, fijos):
    """Inserta una fila con los valores dados y relleno para cada NOT NULL sin default."""
    cols = cur.execute(
        "select column_name, data_type, udt_name, character_maximum_length "
        "from information_schema.columns "
        "where table_schema=%s and table_name=%s and is_nullable='NO' and column_default is null "
        "and is_identity='NO' and is_generated='NEVER'", (esquema, tabla)).fetchall()
    valores = dict(fijos)
    for nombre, tipo, udt, largo in cols:
        if nombre in valores:
            continue
        if udt == "uuid":
            valores[nombre] = uuid.uuid4()
        elif tipo in ("text", "character varying", "character"):
            valores[nombre] = f"a1{secrets.token_hex(8)}"[:largo] if largo else f"prueba-a1-{secrets.token_hex(4)}"
        elif udt == "bool":
            valores[nombre] = False
        elif udt in ("int2", "int4", "int8", "numeric", "float4", "float8"):
            valores[nombre] = 0
        elif udt in ("timestamptz", "timestamp"):
            valores[nombre] = datetime.now(timezone.utc)
        elif udt == "date":
            valores[nombre] = date.today()
        elif udt in ("jsonb", "json"):
            valores[nombre] = Jsonb({})
        elif tipo == "ARRAY":
            valores[nombre] = []
        else:
            raise RuntimeError(f"{esquema}.{tabla}.{nombre}: tipo {tipo}/{udt} sin valor de prueba")
    q = sql.SQL("insert into {}.{} ({}) values ({}) returning id").format(
        sql.Identifier(esquema), sql.Identifier(tabla),
        sql.SQL(", ").join(map(sql.Identifier, valores)),
        sql.SQL(", ").join(sql.Placeholder() * len(valores)))
    return cur.execute(q, list(valores.values())).fetchone()[0]


TMP = Path(tempfile.mkdtemp(prefix="a1p2-"))
CONTENEDOR = None

try:
    # =========================================================================
    titulo("1. base desde cero: la cadena entera por el ledger")
    # =========================================================================
    env_local = {**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO, "DBPASSWORD": CLAVE}
    env_local.pop("PGOPTIONS", None)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, env=env_local, timeout=1800)
    revisar(r.returncode == 0 and "base construida desde cero y verificada" in r.stdout,
            "cli/base_desde_cero.py construye y verifica la base", (r.stdout + r.stderr)[-1200:])
    archivos = sorted(p.name for p in (RAIZ / "supabase").glob("*.sql"))
    led = consultar(BASE, "select archivo, origen from asistente.migraciones_aplicadas order by 1")
    revisar([f[0] for f in led] == archivos and {f[1] for f in led} == {"aplicada"},
            f"el ledger anota los {len(archivos)} archivos, todos 'aplicada'")
    i = archivos.index(A1)
    revisar(archivos[i - 1] == "202609101200_marcas_tv_desconocidas.sql" and archivos[i + 1] == P2[0],
            "A1 ordena despues del ultimo archivo del manifiesto y antes de P2",
            f"{archivos[i - 1:i + 2]}")
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migrar_asistente.py"), "--estado"],
                       capture_output=True, text=True, env={**env_local, "DBNAME": BASE})
    revisar(r.returncode == 0 and "pendientes            : 0" in r.stdout and "HUECO" not in r.stdout
            and "con checksum distinto : 0" in r.stdout,
            "--estado: 0 pendientes, 0 checksums distintos, sin hueco", r.stdout[-400:])

    # =========================================================================
    titulo("2. A1: la firma de 5 no esta, y la recuperacion sigue igual")
    # =========================================================================
    firmas = [f[0] for f in consultar(
        BASE, "select pg_get_function_identity_arguments(p.oid) from pg_proc p "
              "join pg_namespace n on n.oid = p.pronamespace "
              "where n.nspname = 'asistente' and p.proname = 'match_chunks' order by 1")]
    revisar(firmas == [FIRMA_6], "match_chunks: solo queda la firma de 6, con p_rol", f"{firmas}")
    revisar(consultar(BASE, "select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                            "where n.nspname = 'asistente' and p.proname = 'match_chunks_hibrido'")[0][0] == 1,
            "match_chunks_hibrido sigue ahi, sin tocar")

    arbol = ast.parse((RAIZ / "nucleo" / "recuperacion" / "busqueda.py").read_text(encoding="utf-8"))
    consultas = [n.args[0].value for n in ast.walk(arbol)
                 if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute" and n.args
                 and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
                 and "match_chunks" in n.args[0].value]
    revisar(len(consultas) == 1 and "p_rol =>" in consultas[0],
            "busqueda.py tiene UNA consulta a match_chunks, con p_rol por nombre", f"{consultas}")

    ROL, CODIGO = "rol_prueba_a1", f"ZZ-A1-{secrets.token_hex(3)}"
    vec = "[" + ",".join(["0.01"] * 1024) + "]"
    firma_5 = sentencia("202608042055_schema.sql", "function asistente.match_chunks(")
    with psycopg.connect(dsn(BASE)) as con:
        cur = con.cursor()
        org = fila_minima(cur, "public", "organization", {})
        doc = fila_minima(cur, "asistente", "documents",
                          {"organization_id": org, "codigo": CODIGO, "titulo": "prueba A1",
                           "version": "01", "estado": "vigente", "roles_permitidos": [ROL]})
        fila_minima(cur, "asistente", "document_chunks",
                    {"organization_id": org, "document_id": doc, "orden": 1,
                     "contenido": "fragmento de prueba A1", "embedding": vec,
                     "vigente": True, "metadata": Jsonb({})})

        cur.execute(consultas[0], (org, vec, 8, ROL))
        filas = cur.fetchall()
        revisar(len(filas) == 1 and filas[0][0] == CODIGO,
                "el SQL literal de busqueda.py recupera el fragmento para su rol", f"{filas}")
        cur.execute(consultas[0], (org, vec, 8, "rol_sin_permiso"))
        revisar(cur.fetchall() == [], "y para un rol sin permiso, nada")
        cur.execute("select count(*) from asistente.match_chunks(%s, %s::vector)", (org, vec))
        revisar(cur.fetchone()[0] == 0,
                "sin p_rol (2 argumentos): 0 filas y sin error; resuelve a la de 6 con p_rol nulo")
        cur.execute("select count(*) from asistente.match_chunks(%s, %s::vector, 8, 0.0, '{}'::jsonb)",
                    (org, vec))
        revisar(cur.fetchone()[0] == 0, "con los 5 argumentos viejos: 0 filas y sin error")

        cur.execute("savepoint control")
        cur.execute(firma_5)
        try:
            cur.execute("select count(*) from asistente.match_chunks(%s, %s::vector)", (org, vec))
            estado = None
        except psycopg.Error as e:
            estado = e.sqlstate
        cur.execute("rollback to savepoint control")
        revisar(estado == "42725",
                "control: con la firma de 5 de vuelta, la misma llamada es ambigua (42725)", f"{estado}")
        con.rollback()

    # =========================================================================
    titulo("3. P2 en extensions, con grants explicitos")
    # =========================================================================
    revisar(consultar(BASE, "select n.nspname from pg_extension e join pg_namespace n "
                            "on n.oid = e.extnamespace where e.extname = 'pgcrypto'") == [("extensions",)],
            "pgcrypto esta en 'extensions'")
    revisar(consultar(BASE, "select to_regnamespace('ext') is null")[0][0],
            "no existe el schema 'ext': P2 no lo requiere")
    roles = consultar(BASE, "select rolname, rolcanlogin from pg_roles where rolname = any(%s) order by 1",
                      (list(cero.ROLES),))
    revisar(len(roles) == 4 and not any(r[1] for r in roles), "los cuatro roles de P2 existen, sin login",
            f"{roles}")
    exp = explicitos(BASE)
    revisar(set(exp) == {"schema extensions"} | FUNCIONES_PGCRYPTO,
            "asistente_owner: USAGE en extensions y EXECUTE EXPLICITO sobre digest(text,text) y "
            "gen_random_bytes(integer)", f"{exp}")

    estado, msg = error_en(BASE, REVOCA_PUBLIC, "set local role asistente_owner", USA_PGCRYPTO)
    revisar(estado is None,
            "sin el EXECUTE de PUBLIC, asistente_owner usa digest y gen_random_bytes: le alcanza su grant",
            f"{estado}: {msg}")
    estado, msg = error_en(BASE, REVOCA_PUBLIC,
                           "revoke execute on function extensions.digest(text,text), "
                           "extensions.gen_random_bytes(integer) from asistente_owner",
                           "set local role asistente_owner", USA_PGCRYPTO)
    revisar(estado == "42501", "control: sin PUBLIC y sin su grant, falla por permiso (42501)",
            f"{estado}: {msg}")

    verifica = sentencia(P2[1], "has_function_privilege", "asistente_owner")
    estado, msg = error_en(BASE, verifica)
    revisar(estado is None, "la comprobacion fail-closed de P2 pasa con los grants puestos", f"{estado}: {msg}")
    estado, msg = error_en(BASE, "revoke execute on function extensions.digest(text,text) from asistente_owner",
                           verifica)
    revisar(estado is not None and "extensions.digest(text,text)" in msg,
            "si el EXECUTE explicito no quedo, ABORTA aunque PUBLIC todavia pueda ejecutarla",
            f"{estado}: {msg}")
    estado, msg = error_en(BASE, "revoke usage on schema extensions from asistente_owner", verifica)
    revisar(estado is not None and "USAGE en el schema extensions" in msg,
            "si falta el USAGE en extensions, tambien aborta", f"{estado}: {msg}")

    d15 = duenos_15(BASE)
    revisar(len(d15) == 15 and all(d == "asistente_owner" for _o, d in d15),
            "los 15 objetos de P2 (5 tablas, 10 funciones) son de asistente_owner", f"{d15}")
    revisar(consultar(BASE, "select has_schema_privilege('asistente_owner', 'asistente', 'CREATE')")[0][0] is False,
            "asistente_owner NO conserva CREATE en el schema asistente")
    postcond = sentencia(P2[1], "conserva CREATE")
    estado, msg = error_en(BASE, postcond)
    revisar(estado is None, "las postcondiciones de dueños y CREATE pasan", f"{estado}: {msg}")
    estado, msg = error_en(BASE, "grant create on schema asistente to asistente_owner", postcond)
    revisar(estado is not None and "conserva CREATE" in msg,
            "si asistente_owner conservara CREATE, la postcondicion ABORTA", f"{estado}: {msg}")
    estado, msg = error_en(BASE, "alter table asistente.job_run owner to current_user", postcond)
    revisar(estado is not None and "asistente.job_run" in msg,
            "si una tabla no quedara de asistente_owner, ABORTA nombrandola", f"{estado}: {msg}")
    estado, msg = error_en(BASE, "alter function asistente.job_claim(text, uuid, timestamptz, text, jsonb) "
                                 "owner to current_user", postcond)
    revisar(estado is not None and "job_claim" in msg,
            "si una funcion no quedara de asistente_owner, ABORTA nombrandola", f"{estado}: {msg}")

    recrear(VACIA)
    guardas = {a: sentencia(a, "to_regprocedure") for a in P2}
    for a, g in guardas.items():
        estado, msg = error_en(VACIA, g)
        revisar(estado is not None and "extensions" in msg,
                f"{a[:12]}: sin pgcrypto, la guarda falla nombrando 'extensions'", f"{estado}: {msg}")
    consultar(VACIA, "create schema ext")
    consultar(VACIA, "create extension pgcrypto with schema ext")
    for a, g in guardas.items():
        estado, msg = error_en(VACIA, g)
        revisar(estado is not None, f"{a[:12]}: con pgcrypto en 'ext' (la disposicion vieja), falla",
                f"{estado}: {msg}")
    consultar(VACIA, "drop extension pgcrypto")
    consultar(VACIA, "create schema extensions")
    consultar(VACIA, "create extension pgcrypto with schema extensions")
    for a, g in guardas.items():
        estado, msg = error_en(VACIA, g)
        revisar(estado is None, f"{a[:12]}: con pgcrypto en 'extensions', la guarda pasa", f"{estado}: {msg}")

    # =========================================================================
    titulo("4. una base con los bytes VIEJOS de P2 falla cerrado")
    # =========================================================================
    viejo = TMP / "viejo"
    arch = subprocess.run(["git", "archive", "--format=tar", COMMIT_P2_VIEJO, "cli", "supabase"],
                          capture_output=True, cwd=str(RAIZ))
    if arch.returncode != 0:
        raise RuntimeError(f"git archive {COMMIT_P2_VIEJO[:7]}: {arch.stderr[-200:]!r}")
    with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as t:
        t.extractall(viejo, filter="data")
    recrear(VIEJA)
    consultar(VIEJA, "create schema ext")
    consultar(VIEJA, "create extension pgcrypto with schema ext")
    r = subprocess.run(cero.comando_django(VIEJA, HOST, PUERTO, USUARIO), capture_output=True, text=True,
                       env=env_local)
    revisar(r.returncode == 0, "Django migra la base", (r.stderr or "")[-300:])
    r = subprocess.run([sys.executable, str(viejo / "cli" / "migrar_asistente.py"), "--aplicar"],
                       capture_output=True, text=True, env={**env_local, "DBNAME": VIEJA})
    revisar(r.returncode == 0, f"el repo de {COMMIT_P2_VIEJO[:7]} aplica su cadena (P2 con 'ext')",
            r.stdout[-300:])
    antes = consultar(VIEJA, "select archivo, sha256 from asistente.migraciones_aplicadas order by 1")
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migrar_asistente.py"), "--aplicar"],
                       capture_output=True, text=True, env={**env_local, "DBNAME": VIEJA})
    revisar(r.returncode == 2 and all(a in r.stdout for a in P2) and "CAMBIARON" in r.stdout,
            "el migrador actual: exit 2, nombra los dos archivos de P2 como cambiados", r.stdout[-500:])
    revisar(consultar(VIEJA, "select archivo, sha256 from asistente.migraciones_aplicadas order by 1") == antes
            and A1 not in {f[0] for f in antes},
            "y no aplico nada: ni A1 ni ningun otro archivo")

    # =========================================================================
    titulo("5. P2 aplicado por un rol como el 'postgres' de Supabase")
    # =========================================================================
    clave_super, clave_rol = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
    CONTENEDOR = f"a1p2-supa-{secrets.token_hex(3)}"
    r = subprocess.run(["docker", "run", "-d", "--rm", "--name", CONTENEDOR,
                        "-e", "POSTGRES_USER=supabase_admin", "-e", "POSTGRES_PASSWORD",
                        "-p", f"127.0.0.1:{PUERTO_EFIMERO}:5432", IMAGEN_PG],
                       capture_output=True, text=True, env={**os.environ, "POSTGRES_PASSWORD": clave_super})
    revisar(r.returncode == 0, f"PostgreSQL efimero propio ({IMAGEN_PG}) en 127.0.0.1:{PUERTO_EFIMERO}",
            (r.stderr or "")[-300:])
    # 127.0.0.1 y no 'localhost': el puerto se publica solo en IPv4, y en Windows
    # 'localhost' puede intentar ::1 primero.
    super_kw = {"puerto": PUERTO_EFIMERO, "usuario": "supabase_admin", "clave": clave_super, "host": "127.0.0.1"}
    rol_kw = {"puerto": PUERTO_EFIMERO, "usuario": "postgres", "clave": clave_rol, "host": "127.0.0.1"}
    paso("esperando que el PostgreSQL efimero acepte conexiones")
    limite = time.monotonic() + 90
    while True:
        try:
            consultar("postgres", "select 1", **super_kw)
            time.sleep(2)
            consultar("postgres", "select 1", **super_kw)
            break
        except psycopg.OperationalError:
            if time.monotonic() > limite:
                raise
            time.sleep(1)

    paso("creando el rol 'postgres' sin superusuario y la base 'dexter'")
    with psycopg.connect(dsn("postgres", **super_kw), autocommit=True) as con:
        con.execute(sql.SQL("alter role postgres login nosuperuser createrole createdb bypassrls "
                            "password {}").format(sql.Literal(clave_rol))
                    if con.execute("select count(*) from pg_roles where rolname='postgres'").fetchone()[0]
                    else sql.SQL("create role postgres login nosuperuser createrole createdb bypassrls "
                                 "password {}").format(sql.Literal(clave_rol)))
        con.execute("create database dexter owner postgres")
    paso("preparando 'extensions', pgcrypto, vector y pg_trgm como en produccion")
    with psycopg.connect(dsn("dexter", **super_kw), autocommit=True) as con:
        # La disposicion medida en produccion: 'extensions' de postgres, pgcrypto
        # del superusuario con EXECUTE para PUBLIC y para postgres con grant option.
        con.execute("create schema extensions authorization postgres")
        con.execute("create extension pgcrypto with schema extensions")
        con.execute("grant execute on function extensions.digest(text,text), extensions.digest(bytea,text), "
                    "extensions.gen_random_bytes(integer) to postgres with grant option")
        con.execute("create extension vector with schema public")
        con.execute("create extension pg_trgm with schema public")
    atributos = consultar("postgres", "select rolsuper, rolcreaterole, rolbypassrls from pg_roles "
                                      "where rolname = 'postgres'", **super_kw)
    revisar(atributos == [(False, True, True)], "el rol 'postgres': sin superusuario, con CREATEROLE y BYPASSRLS",
            f"{atributos}")

    env_rol = {**env_local, "DBHOST": "127.0.0.1", "DBPORT": PUERTO_EFIMERO, "DBNAME": "dexter",
               "DBUSER": "postgres", "DBPASSWORD": clave_rol}
    paso("migraciones de Django como 'postgres'")
    r = subprocess.run(cero.comando_django("dexter", "127.0.0.1", PUERTO_EFIMERO, "postgres"),
                       capture_output=True, text=True, env=env_rol, timeout=900)
    revisar(r.returncode == 0, "Django migra como 'postgres' sin superusuario", (r.stderr or "")[-600:])
    paso("ledger --aplicar como 'postgres'")
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migrar_asistente.py"), "--aplicar"],
                       capture_output=True, text=True, env=env_rol, timeout=900)
    salida = (r.stdout or "") + (r.stderr or "")
    revisar(r.returncode == 0 and f"{len(archivos)} aplicada(s)" in salida,
            f"el ledger aplica los {len(archivos)} archivos como 'postgres', P2 incluido", salida[-900:])
    revisar(clave_rol not in salida and clave_super not in salida, "sin claves en la salida")

    os.environ["DBPASSWORD_ANTERIOR_A1P2"] = os.environ["DBPASSWORD"]
    os.environ["DBPASSWORD"] = clave_rol
    try:
        malas = cero.verificar("dexter", "127.0.0.1", PUERTO_EFIMERO, "postgres")
    finally:
        os.environ["DBPASSWORD"] = os.environ.pop("DBPASSWORD_ANTERIOR_A1P2")
    revisar(not malas, "la verificacion de base_desde_cero pasa entera sobre esa base", f"{malas}")

    exp = explicitos("dexter", **super_kw)
    revisar(set(exp) == {"schema extensions"} | FUNCIONES_PGCRYPTO and set(exp.values()) == {"postgres"},
            "grants explicitos de asistente_owner, otorgados por 'postgres' sin superusuario", f"{exp}")
    miembros = consultar("dexter", "select m.rolname, a.set_option from pg_auth_members a "
                                   "join pg_roles g on g.oid = a.roleid join pg_roles m on m.oid = a.member "
                                   "where g.rolname = 'asistente_owner'", **super_kw)
    revisar(("postgres", True) in miembros, "'postgres' es miembro de asistente_owner (lo que exige 'owner to')",
            f"{miembros}")
    duenos = consultar("dexter", "select distinct pg_get_userbyid(p.proowner) from pg_proc p "
                                 "join pg_namespace n on n.oid = p.pronamespace "
                                 "where n.nspname = 'asistente' and p.proname like 'job%'", **super_kw)
    revisar(duenos == [("asistente_owner",)], "las funciones job_* son de asistente_owner", f"{duenos}")

    ledger5 = consultar("dexter", "select archivo, origen from asistente.migraciones_aplicadas order by 1",
                        **super_kw)
    revisar([f[0] for f in ledger5] == archivos and {f[1] for f in ledger5} == {"aplicada"},
            f"{len(ledger5)}/{len(archivos)} en el ledger como 'postgres', {P2[1][:12]} incluido, todos 'aplicada'",
            f"faltan {sorted(set(archivos) - {f[0] for f in ledger5})}")
    d15 = duenos_15("dexter", **super_kw)
    revisar(len(d15) == 15 and all(d == "asistente_owner" for _o, d in d15),
            "15/15: las 5 tablas y las 10 funciones de P2 son de asistente_owner", f"{d15}")
    revisar(consultar("dexter", "select has_schema_privilege('asistente_owner', 'asistente', 'CREATE')",
                      **super_kw)[0][0] is False,
            "al terminar, asistente_owner NO conserva CREATE en asistente")

    # Control negativo con los roles reales y 'postgres' sin superusuario: el
    # CREATE temporal es lo que hace pasar el cambio de dueño.
    estado, msg = error_en("dexter", "create table asistente.zz_prueba_owner (x int)",
                           "alter table asistente.zz_prueba_owner owner to asistente_owner", **rol_kw)
    revisar(estado == "42501" and "schema asistente" in msg,
            "control: sin CREATE temporal, 'postgres' no puede darle una tabla a asistente_owner (42501)",
            f"{estado}: {msg}")
    estado, msg = error_en("dexter", "grant create on schema asistente to asistente_owner",
                           "create table asistente.zz_prueba_owner (x int)",
                           "alter table asistente.zz_prueba_owner owner to asistente_owner", **rol_kw)
    revisar(estado is None, "y con el CREATE temporal si puede (deshecho)", f"{estado}: {msg}")
    estado, msg = error_en("dexter", REVOCA_PUBLIC, "set local role asistente_owner", USA_PGCRYPTO, **super_kw)
    revisar(estado is None, "y ahi tambien usa pgcrypto sin depender de PUBLIC", f"{estado}: {msg}")
finally:
    if CONTENEDOR:
        subprocess.run(["docker", "stop", CONTENEDOR], capture_output=True, text=True)
    for b in (VACIA, VIEJA):
        try:
            borrar(b)
        except psycopg.Error:
            pass
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Sin la firma de 5, y P2 sobre extensions con sus grants propios.")
print("=" * 74)
