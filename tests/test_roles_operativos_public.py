# -*- coding: utf-8 -*-
"""
================================================================================
 ROLES OPERATIVOS SOBRE PUBLIC  --  tres prerrequisitos del entorno, fail-closed
================================================================================

    py -3.13 tests/test_roles_operativos_public.py

Por que existe
--------------
'supabase/202609141110_roles_operativos_public.sql' declara en git los permisos
que crm_user (Django) y motor_user (el motor) ya tienen en produccion. Necesita
TRES roles que no crea, porque no son del ledger:

  postgres     rol de plataforma de PostgreSQL/Supabase: es quien crea las
               tablas en produccion, y sus default privileges son los que se
               declaran ('alter default privileges for role postgres ...')
  crm_user     roles operativos de Dexter: existencia, LOGIN y contraseñas
  motor_user   son del despliegue; la migracion solo declara sus grants

Si falta uno, PostgreSQL rechaza la sentencia que lo nombra (42704) y el
migrador revierte el archivo entero. Sin DO, para que el manifiesto lo
verifique automaticamente.

Corre sobre TRES servidores efimeros propios (los roles son de cluster; hacen
falta clusters donde NO existan):

  PG16           pgvector/pgvector:pg16, superusuario 'postgres'; ALL = arwdDxt
  PG16-motor     la misma imagen con superusuario 'motor' y SIN rol 'postgres',
                 como el pg-motor de las suites locales
  PG17           la imagen exacta de produccion (por digest), aplicando como su
                 'postgres' sin superusuario; ALL = arwdDxtm

El archivo se aplica con el MIGRADOR REAL (cli/migrar_asistente.py::aplicar)
sobre una carpeta que solo lo contiene, asi que se prueba tambien el ledger:

  1. falta crm_user   -> exit 1, 42704, ninguna ACL cambia, ninguna fila en el ledger
  2. falta motor_user -> falla en el ULTIMO grant y revierte tambien los seis
                         anteriores a crm_user
  3. falta postgres   -> (PG16-motor) falla al llegar a los default privileges y
                         revierte los grants previos
  4. con los prerrequisitos del harness (cli/base_desde_cero.py) -> aplica y
     queda EXACTAMENTE lo declarado; el 'postgres' artificial nace NOLOGIN, sin
     atributos, sin contraseña, sin membresias; crearlo no cambia ningun dueño;
     el migrador sigue siendo el mismo usuario
  5. idempotente
  6. el manifiesto lo clasifica verificable automaticamente y la foto
     default_acl de postgres/public ve lo declarado

La comparacion contra la foto de produccion y el hardening van en la
referencia PG17 completa, no aca.
================================================================================
"""

from __future__ import annotations

import contextlib
import io
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ARCHIVO = RAIZ / "supabase" / "202609141110_roles_operativos_public.sql"
IMG_PG17 = "supabase/postgres@sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00"
IMG_PG16 = os.environ.get("IMAGEN_PG_EFIMERA", "pgvector/pgvector:pg16")

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
from cli import migrar_asistente as mig                           # noqa: E402
from cli.manifiesto_adopcion import AUTOMATICA, _normal, clasificar, dividir, estado_de, foto  # noqa: E402

ACL = r"""
select 'relacion', n.nspname, c.relname, pg_get_userbyid(a.grantor), pg_get_userbyid(a.grantee), a.privilege_type, a.is_grantable
from pg_class c join pg_namespace n on n.oid = c.relnamespace
cross join lateral aclexplode(coalesce(c.relacl, acldefault((case when c.relkind = 'S' then 's' else 'r' end)::"char", c.relowner))) a
where c.relkind in ('r','v','m','p','f','S') and n.nspname = 'public'
union all
select 'schema', n.nspname, n.nspname, pg_get_userbyid(a.grantor), pg_get_userbyid(a.grantee), a.privilege_type, a.is_grantable
from pg_namespace n cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
where n.nspname = 'public'
union all
select 'default:' || pg_get_userbyid(d.defaclrole) || ':' || d.defaclobjtype::text, coalesce(n.nspname, '(global)'), '',
       pg_get_userbyid(a.grantor), pg_get_userbyid(a.grantee), a.privilege_type, a.is_grantable
from pg_default_acl d left join pg_namespace n on n.oid = d.defaclnamespace
cross join lateral aclexplode(d.defaclacl) a
"""
DUENOS = r"""
select 'relacion:' || n.nspname || '.' || c.relname, pg_get_userbyid(c.relowner) from pg_class c
join pg_namespace n on n.oid = c.relnamespace where n.nspname not like 'pg\_%' and n.nspname <> 'information_schema'
union all select 'schema:' || nspname, pg_get_userbyid(nspowner) from pg_namespace
union all select 'base:' || datname, pg_get_userbyid(datdba) from pg_database
"""
LETRA = {"INSERT": "a", "SELECT": "r", "UPDATE": "w", "DELETE": "d", "TRUNCATE": "D", "REFERENCES": "x",
         "TRIGGER": "t", "MAINTAIN": "m", "EXECUTE": "X", "USAGE": "U", "CREATE": "C"}


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servidor:
    def __init__(self, etiqueta, imagen, admin, aplicador, env_extra=None):
        self.etiqueta, self.imagen, self.admin, self.aplicador = etiqueta, imagen, admin, aplicador
        self.env_extra = env_extra or {}
        self.nombre = f"dexter-roles-op-{etiqueta.lower()}-{secrets.token_hex(3)}"
        self.puerto, self.clave = str(puerto_libre()), secrets.token_urlsafe(24)

    def dsn(self, usuario, base="postgres"):
        return (f"host=127.0.0.1 port={self.puerto} dbname={base} user={usuario} password={self.clave} "
                f"sslmode=disable connect_timeout=15")

    def q(self, sentencia, params=None, usuario=None, base="postgres"):
        with psycopg.connect(self.dsn(usuario or self.admin, base), autocommit=True) as con:
            cur = con.execute(sentencia, params)
            return cur.fetchall() if cur.description else []

    def arrancar(self):
        subprocess.run(["docker", "rm", "-f", self.nombre], capture_output=True)
        envs = []
        for k in self.env_extra:
            envs += ["-e", k]
        r = subprocess.run(["docker", "run", "-d", "--name", self.nombre, "-e", "POSTGRES_PASSWORD", *envs,
                            "-p", f"127.0.0.1:{self.puerto}:5432", self.imagen],
                           capture_output=True, text=True,
                           env={**os.environ, "POSTGRES_PASSWORD": self.clave, **self.env_extra})
        if r.returncode != 0:
            raise RuntimeError(f"docker run: {r.stderr[-400:]}")
        limite = time.monotonic() + 900
        while time.monotonic() < limite:
            try:
                if self.etiqueta == "PG17":
                    if self.q("select rolsuper from pg_roles where rolname = 'postgres'") == [(False,)]:
                        time.sleep(3)
                        self.q("select 1")
                        return
                else:
                    self.q("select 1")
                    time.sleep(2)
                    self.q("select 1")
                    return
            except psycopg.Error:
                pass
            time.sleep(2)
        raise RuntimeError(f"{self.etiqueta}: el servidor no quedo listo")

    def borrar(self):
        subprocess.run(["docker", "rm", "-f", self.nombre], capture_output=True)


def acl(srv, base):
    return {tuple(f) for f in srv.q(ACL, base=base)}


def aplicar_con_el_migrador(srv, base):
    """cli/migrar_asistente.py::aplicar, el mismo camino que produccion, sobre una carpeta con SOLO este archivo."""
    carpeta = Path(tempfile.mkdtemp(prefix="roles-op-"))
    shutil.copy2(ARCHIVO, carpeta / ARCHIVO.name)
    salida = io.StringIO()
    try:
        with psycopg.connect(srv.dsn(srv.aplicador, base), autocommit=True) as con, contextlib.redirect_stdout(salida):
            codigo = mig.aplicar(con, 30.0, carpeta)
        filas = srv.q("select origen from asistente.migraciones_aplicadas where archivo = %s", (ARCHIVO.name,),
                      base=base) if srv.q("select to_regclass('asistente.migraciones_aplicadas') is not null",
                                          base=base)[0][0] else []
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    return codigo, [f[0] for f in filas], salida.getvalue()


def preparar_base(srv, base):
    # Dueño = el rol que aplica: miembro de pg_database_owner, como en produccion.
    srv.q(f'create database "{base}" owner {srv.aplicador}')
    srv.q("create table public.organization (id serial primary key, nombre text); "
          "create table public.otra_tabla (id bigserial primary key); "
          "create sequence public.suelta", usuario=srv.aplicador, base=base)


def letras(filas, predicado, grantee):
    por = {}
    for t, sch, obj, grantor, ge, priv, gr in filas:
        if ge == grantee and predicado(t, sch, obj):
            por.setdefault((t, sch, obj), set()).add(LETRA.get(priv, "?"))
    return {k: "".join(sorted(v, key="arwdDxtmXUC".index)) for k, v in por.items()}


def negativo(srv, base, falta, antes_de_aplicar=None):
    preparar_base(srv, base)
    if antes_de_aplicar:
        antes_de_aplicar()
    antes = acl(srv, base)
    codigo, filas, texto = aplicar_con_el_migrador(srv, base)
    revisar(codigo == mig.SALIDA_FALLO and f'role "{falta}" does not exist' in texto,
            f"falta {falta}: el migrador termina en {mig.SALIDA_FALLO} con 42704 nombrando {falta}",
            f"exit {codigo}: {texto[-300:]}")
    despues = acl(srv, base)
    revisar(despues == antes, f"falta {falta}: rollback completo, ACL de public y default privileges identicas")
    revisar(not [f for f in despues if f[4] in ("crm_user", "motor_user")],
            f"falta {falta}: ningun grant previo quedo aplicado a crm_user ni a motor_user")
    revisar(filas == [], f"falta {falta}: ninguna fila del ledger para el archivo", f"{filas}")


def correr(srv):
    titulo(f"{srv.etiqueta}: {srv.imagen.split('@')[0]} (superusuario {srv.admin}, aplica {srv.aplicador})")
    srv.arrancar()
    try:
        version = int(srv.q("select current_setting('server_version_num')")[0][0])
        tabla_todo = "arwdDxtm" if version >= 170000 else "arwdDxt"
        hay_postgres = bool(srv.q("select 1 from pg_roles where rolname = 'postgres'"))
        print(f"       server_version_num={version}; ALL sobre tablas debe dar {tabla_todo}; rol postgres presente: {hay_postgres}")
        revisar(not srv.q("select rolname from pg_roles where rolname in ('crm_user','motor_user')"),
                "el cluster efimero arranca sin crm_user ni motor_user")

        if hay_postgres:
            negativo(srv, "falta_crm", "crm_user")
            negativo(srv, "falta_motor", "motor_user",
                     antes_de_aplicar=lambda: srv.q("create role crm_user nologin"))
            srv.q("drop role crm_user")
        else:
            # PG16-motor: los dos roles operativos existen y falta SOLO postgres.
            def solo_operativos():
                srv.q("create role crm_user nologin; create role motor_user nologin")
            negativo(srv, "falta_postgres", "postgres", antes_de_aplicar=solo_operativos)
            srv.q("drop role crm_user; drop role motor_user")

        preparar_base(srv, "con_roles")
        duenos_antes = {tuple(f) for f in srv.q(DUENOS, base="con_roles")}
        with psycopg.connect(srv.dsn(srv.admin), autocommit=True) as con:
            creados = cero.preparar_roles_de_despliegue(con)
        esperados_creados = ["crm_user", "motor_user"] + ([] if hay_postgres else ["postgres"])
        revisar(sorted(creados) == sorted(esperados_creados), f"el harness creo los que faltaban: {sorted(creados)}")
        revisar({tuple(f) for f in srv.q(DUENOS, base="con_roles")} == duenos_antes,
                "crear los prerrequisitos no cambio ningun dueño (relaciones, schemas, bases)")
        if not hay_postgres:
            attrs = srv.q("select rolsuper, rolcanlogin, rolcreatedb, rolcreaterole, rolbypassrls, rolreplication, "
                          "rolpassword is null from pg_authid where rolname = 'postgres'")
            revisar(attrs == [(False, False, False, False, False, False, True)],
                    "el 'postgres' artificial: NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS, sin contraseña",
                    f"{attrs}")
            revisar(not srv.q("select 1 from pg_auth_members m join pg_roles r on r.oid in (m.roleid, m.member) "
                              "where r.rolname = 'postgres'"), "y sin ninguna membresia")
            revisar(srv.q("select pg_get_userbyid(relowner) from pg_class where oid = 'public.organization'::regclass",
                          base="con_roles") == [(srv.aplicador,)], f"las tablas siguen siendo de {srv.aplicador}, no de postgres")
        else:
            with psycopg.connect(srv.dsn(srv.admin), autocommit=True) as con:
                antes_attrs = con.execute("select rolsuper, rolcanlogin, rolbypassrls from pg_roles where rolname='postgres'").fetchone()
                cero.preparar_roles_de_despliegue(con)
                despues_attrs = con.execute("select rolsuper, rolcanlogin, rolbypassrls from pg_roles where rolname='postgres'").fetchone()
            revisar(antes_attrs == despues_attrs, f"si postgres ya existe, el harness no toca sus atributos ({despues_attrs})")

        antes = acl(srv, "con_roles")
        codigo, filas, texto = aplicar_con_el_migrador(srv, "con_roles")
        revisar(codigo == mig.SALIDA_OK and filas == ["aplicada"], "con los prerrequisitos: aplica y el ledger lo anota 'aplicada'",
                f"exit {codigo} filas {filas}: {texto[-300:]}")
        sesion = srv.q("select session_user, current_user", usuario=srv.aplicador, base="con_roles")
        revisar(sesion == [(srv.aplicador, srv.aplicador)], f"el migrador siguio siendo {srv.aplicador} (sin SET ROLE)")
        despues = acl(srv, "con_roles")
        revisar(not (antes - despues), "no quito ningun privilegio", f"{sorted(antes - despues)[:5]}")
        revisar({f[4] for f in despues - antes} <= {"crm_user", "motor_user"},
                "solo agrego privilegios a crm_user y motor_user", f"{sorted({f[4] for f in despues - antes})}")

        rel = letras(despues, lambda t, s, o: t == "relacion", "crm_user")
        tablas = {k: v for k, v in rel.items() if k[2] in ("organization", "otra_tabla")}
        secuencias = {k: v for k, v in rel.items() if k[2] not in ("organization", "otra_tabla")}
        revisar(tablas and set(tablas.values()) == {tabla_todo}, f"crm_user sobre las tablas de public: {tabla_todo}", f"{tablas}")
        revisar(len(secuencias) == 3 and set(secuencias.values()) == {"rwU"}, "crm_user sobre las 3 secuencias de public: rwU",
                f"{secuencias}")
        revisar(set(letras(despues, lambda t, s, o: t == "schema", "crm_user").values()) == {"UC"},
                "crm_user sobre el schema public: UC")
        defaults = letras(despues, lambda t, s, o: t.startswith("default:postgres:") and s == "public", "crm_user")
        revisar(defaults == {("default:postgres:r", "public", ""): tabla_todo, ("default:postgres:S", "public", ""): "rwU",
                             ("default:postgres:f", "public", ""): "X"},
                f"default privileges de postgres en public hacia crm_user: tablas {tabla_todo}, secuencias rwU, funciones X",
                f"{defaults}")
        motor = [f for f in despues if f[4] == "motor_user"]
        revisar([(f[0], f[2], f[5]) for f in motor] == [("relacion", "organization", "SELECT")],
                "motor_user: SELECT sobre public.organization y nada mas", f"{motor}")
        revisar(not [f for f in despues - antes if f[6] in (True, "t", "true")], "ningun privilegio con grant option")

        with psycopg.connect(srv.dsn(srv.aplicador, "con_roles"), autocommit=True) as con:
            fd = _normal(foto(con, ("default_acl", "postgres", "public")))
        tipos = {x["tipo"]: [a for a in x["acl"] if a.startswith("crm_user=")] for x in fd}
        revisar(tipos.get("r") == [f"crm_user={tabla_todo}/postgres"] and tipos.get("S") == ["crm_user=rwU/postgres"]
                and tipos.get("f") == ["crm_user=X/postgres"],
                "la foto default_acl postgres/public del manifiesto ve lo declarado", f"{fd}")

        codigo, filas, texto = aplicar_con_el_migrador(srv, "con_roles")
        revisar(codigo == mig.SALIDA_OK and acl(srv, "con_roles") == despues and filas == ["aplicada"],
                "otra pasada del migrador: 0 pendientes y nada cambia", f"exit {codigo}: {texto[-200:]}")
        estado, msg = None, ""
        with psycopg.connect(srv.dsn(srv.aplicador, "con_roles"), autocommit=True) as con:
            try:
                with con.transaction():
                    con.execute(mig.leer_migracion(ARCHIVO)[0])
            except psycopg.Error as e:
                estado, msg = e.sqlstate, str(e)
        revisar(estado is None and acl(srv, "con_roles") == despues, "ejecutarla de nuevo a mano es idempotente", msg)
    finally:
        srv.borrar()


titulo("clasificacion del archivo por el manifiesto")
texto, sha = mig.leer_migracion(ARCHIVO)
claves = []
for s in dividir(texto):
    for c in clasificar(s):
        if c not in claves:
            claves.append(c)
esperadas = [("schema", "public"), ("acl_tablas", "public"), ("acl_secuencias", "public"),
             ("default_acl", "postgres", "public"), ("acl_tabla", "public", "organization")]
revisar(claves == esperadas, f"claves: {esperadas}", f"{claves}")
revisar(estado_de(claves)[0] == AUTOMATICA, "verificable automaticamente (sin DO, sin sentencias desconocidas)",
        f"{estado_de(claves)}")
cuerpo = [s.lower() for s in dividir(texto)]
revisar(not any(s.startswith(("do ", "create role", "alter role", "set role")) or "password" in s or "current_user" in s
                for s in cuerpo),
        "no crea ni altera roles, no tiene DO, no hace SET ROLE, no usa current_user ni contraseñas")

for srv in (Servidor("PG16", IMG_PG16, admin="postgres", aplicador="postgres"),
            Servidor("PG16-motor", IMG_PG16, admin="motor", aplicador="motor", env_extra={"POSTGRES_USER": "motor"}),
            Servidor("PG17", IMG_PG17, admin="supabase_admin", aplicador="postgres")):
    try:
        correr(srv)
    except Exception as e:                                          # noqa: BLE001
        revisar(False, f"{srv.etiqueta}: la corrida termino", f"{type(e).__name__}: {e}")
        srv.borrar()

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("OK: roles_operativos_public exige postgres, crm_user y motor_user, y declara exactamente los permisos de produccion")
