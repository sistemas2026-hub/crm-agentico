# -*- coding: utf-8 -*-
"""
La separacion de credenciales, medida contra PostgreSQL de verdad  --  Etapa B.4.

test_credenciales.py cubre la logica de entorno, que es aritmetica de cadenas.
Lo de aqui es lo que NO se puede afirmar sin una base: quien puede alterar que,
de quien queda una tabla recien creada, y si crm_user conserva su trabajo
despues de quitarle CREATE.

Como en common/tests/test_pool_rls_isolation.py, los parametros de conexion
salen de las MISMAS variables que lee crm/settings.py, y todo se salta si no
hay un PostgreSQL configurado. Se necesita ademas un rol que pueda crear roles
-- en un contenedor desechable, 'postgres' lo es.

TODO ocurre dentro de un esquema propio que se crea y se destruye en cada
prueba. No toca 'public', ni las 11 tablas pendientes de RLS, ni nada de
produccion.
"""

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from common import credenciales as cr  # noqa: E402

pytestmark = pytest.mark.postgres_only

ORG_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORG_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

# Roles del banco. Llevan sufijo para no chocar con los de verdad si alguien
# corre esto contra una base que ya los tenga.
SUF = "_b4"
OWNER = cr.ROL_DUENO + SUF
MIGRATOR = cr.ROL_MIGRACIONES + SUF
TRAFICO = cr.ROL_TRAFICO + SUF


def _params():
    return {
        "dbname": os.environ.get("DBNAME", "crm_db"),
        "user": os.environ.get("DBUSER", "postgres"),
        "password": os.environ.get("DBPASSWORD", "postgres"),
        "host": os.environ.get("DBHOST", "localhost"),
        "port": os.environ.get("DBPORT", "5432"),
    }


def _admin():
    try:
        c = psycopg.connect(**_params(), connect_timeout=5, autocommit=True)
    except Exception as e:
        pytest.skip(f"sin PostgreSQL alcanzable: {type(e).__name__}: {e}")
    con_permiso = c.execute(
        "select rolsuper or rolcreaterole from pg_roles where rolname = current_user"
    ).fetchone()[0]
    if not con_permiso:
        c.close()
        pytest.skip("el rol de la prueba no puede crear roles")
    return c


@pytest.fixture()
def banco():
    """
    Un esquema desechable con los tres roles y una tabla con RLS.

    Se llama distinto en cada prueba para que dos corridas simultaneas no se
    pisen, y se borra en el 'finally' pase lo que pase.
    """
    admin = _admin()
    esquema = "b4_" + uuid.uuid4().hex[:10]
    try:
        # Sin bloque DO: anidar comillas dentro de un execute() de plpgsql es
        # justo donde esto se rompio la primera vez, y el try/except dice lo
        # mismo sin el laberinto de comillas.
        for rol, extra in ((OWNER, "nologin"),
                           (MIGRATOR, "login password 'b4'"),
                           (TRAFICO, "login password 'b4'")):
            try:
                admin.execute(
                    f'create role "{rol}" {extra} nosuperuser nobypassrls')
            except psycopg.errors.DuplicateObject:
                pass
        admin.execute(f'grant "{OWNER}" to "{MIGRATOR}"')
        admin.execute(f'grant "{OWNER}" to current_user')

        admin.execute(f"create schema {esquema}")
        admin.execute(f'alter schema {esquema} owner to "{OWNER}"')
        admin.execute(f'grant usage on schema {esquema} to "{TRAFICO}", "{MIGRATOR}"')

        # La pieza de B.3 que impide que la propiedad derive: crm_migrator
        # arranca actuando como el dueno.
        base = _params()["dbname"]
        admin.execute(f'alter role "{MIGRATOR}" in database "{base}" set role = "{OWNER}"')

        # DEFAULT PRIVILEGES para el dueno -- el hueco 2 de B.3.
        admin.execute(f'alter default privileges for role "{OWNER}" in schema {esquema} '
                      f'grant select, insert, update, delete on tables to "{TRAFICO}"')
        admin.execute(f'alter default privileges for role "{OWNER}" in schema {esquema} '
                      f'grant usage, select on sequences to "{TRAFICO}"')

        yield admin, esquema
    finally:
        try:
            admin.execute(f"drop schema if exists {esquema} cascade")
            base = _params()["dbname"]
            admin.execute(f'alter role "{MIGRATOR}" in database "{base}" reset role')
            for rol in (MIGRATOR, TRAFICO, OWNER):
                admin.execute(f'drop owned by "{rol}" cascade')
                admin.execute(f'drop role if exists "{rol}"')
        except Exception:
            pass
        admin.close()


def _como(rol, sentencias, esquema=None):
    """Ejecuta como 'rol' en una transaccion que SIEMPRE se revierte."""
    c = psycopg.connect(**{**_params(), "user": rol, "password": "b4"},
                        connect_timeout=5, autocommit=False)
    try:
        cur = c.cursor()
        if esquema:
            cur.execute(f"set local search_path to {esquema}")
        salida = None
        for s in sentencias:
            cur.execute(s)
            if cur.description:
                salida = cur.fetchall()
        c.rollback()
        return ("ok", salida)
    except Exception as e:
        c.rollback()
        return ("error", f"{type(e).__name__}: {str(e).splitlines()[0][:110]}")
    finally:
        c.close()


def _dueno(admin, esquema, tabla):
    f = admin.execute("""
        select pg_get_userbyid(c.relowner) from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = %s and c.relname = %s""", (esquema, tabla)).fetchone()
    return f[0] if f else None


# =============================================================================
#  Puntos 6.11 y 6.12  --  el reparto DDL / DML
# =============================================================================

def test_el_trafico_no_puede_alterar_la_estructura(banco):
    admin, esq = banco
    admin.execute(f"create table {esq}.t (id int)")
    admin.execute(f'alter table {esq}.t owner to "{OWNER}"')
    admin.execute(f'grant select, insert, update, delete on {esq}.t to "{TRAFICO}"')

    estado, det = _como(TRAFICO, [f"alter table {esq}.t add column x int"])
    assert estado == "error", "crm_user no puede hacer DDL"
    assert "owner" in det.lower() or "denied" in det.lower(), det


def test_la_credencial_de_migraciones_si_puede_alterar(banco):
    admin, esq = banco
    admin.execute(f"create table {esq}.t (id int)")
    admin.execute(f'alter table {esq}.t owner to "{OWNER}"')

    estado, det = _como(MIGRATOR, [f"alter table {esq}.t add column x int"])
    assert estado == "ok", det


# =============================================================================
#  Puntos 6.3, 6.4 y 8  --  de quien queda lo que crea una migracion
# =============================================================================

def test_lo_que_crea_la_migracion_queda_del_rol_dueno(banco):
    """
    El hueco 1 de B.3. Sin 'set role', la tabla quedaria de crm_migrator -- un
    rol CON login-- y la separacion se deshace sola, migracion a migracion.
    """
    admin, esq = banco
    c = psycopg.connect(**{**_params(), "user": MIGRATOR, "password": "b4"},
                        autocommit=True)
    try:
        c.execute(f"create table {esq}.nueva (id bigint generated by default as identity, "
                  f"org_id uuid)")
    finally:
        c.close()

    assert _dueno(admin, esq, "nueva") == OWNER


def test_el_trafico_recibe_permiso_sobre_la_tabla_nueva_sin_grant_manual(banco):
    """
    El hueco 2 de B.3: si los DEFAULT PRIVILEGES apuntan al rol equivocado, la
    migracion pasa en verde y deja la aplicacion sin poder leer lo que acaba de
    crear. Es la peor forma de fallar.
    """
    admin, esq = banco
    c = psycopg.connect(**{**_params(), "user": MIGRATOR, "password": "b4"},
                        autocommit=True)
    try:
        c.execute(f"create table {esq}.nueva (id bigint generated by default as identity, "
                  f"org_id uuid, dato text)")
    finally:
        c.close()

    for permiso in ("select", "insert", "update", "delete"):
        tiene = admin.execute(
            "select has_table_privilege(%s, %s, %s)",
            (TRAFICO, f"{esq}.nueva", permiso)).fetchone()[0]
        assert tiene, f"crm_user deberia tener {permiso.upper()} automaticamente"

    # Sin USAGE sobre la secuencia de identidad, el primer INSERT falla al
    # pedir el siguiente id -- y el error no menciona la secuencia.
    usa = admin.execute(
        "select has_sequence_privilege(%s, %s, 'usage')",
        (TRAFICO, f"{esq}.nueva_id_seq")).fetchone()[0]
    assert usa, "falta USAGE sobre la secuencia de identidad"

    estado, _ = _como(TRAFICO, [f"insert into {esq}.nueva (org_id, dato) "
                                f"values ('{ORG_A}', 'x')"], esquema=esq)
    assert estado == "ok", "el INSERT real tiene que funcionar, no solo el permiso"


# =============================================================================
#  Puntos 6.6, 6.7  --  RLS y FORCE RLS siguen valiendo
# =============================================================================

def test_rls_y_force_siguen_aislando_con_el_dueno_separado(banco):
    admin, esq = banco
    admin.execute(f"create table {esq}.t (id serial primary key, org_id uuid, dato text)")
    admin.execute(f'alter table {esq}.t owner to "{OWNER}"')
    admin.execute(f'grant select, insert, update, delete on {esq}.t to "{TRAFICO}"')
    admin.execute(f"insert into {esq}.t (org_id, dato) values "
                  f"('{ORG_A}','de A'), ('{ORG_B}','de B')")
    admin.execute(f"alter table {esq}.t enable row level security")
    admin.execute(f"alter table {esq}.t force row level security")
    admin.execute(f"create policy p on {esq}.t using "
                  f"(org_id::text = nullif(current_setting('app.current_org', true),''))")

    estado, filas = _como(TRAFICO, [
        f"select set_config('app.current_org', '{ORG_A}', true)",
        f"select dato from {esq}.t"], esquema=esq)
    assert estado == "ok" and len(filas) == 1 and filas[0][0] == "de A"

    estado, filas = _como(TRAFICO, [f"select dato from {esq}.t"], esquema=esq)
    assert estado == "ok" and filas is None or filas == [], (
        "sin contexto de organizacion tiene que ver CERO filas")


def test_el_dueno_sin_login_no_puede_conectarse(banco):
    """crm_owner no es una credencial, y eso es lo que lo hace seguro."""
    admin, _ = banco
    puede = admin.execute(
        "select rolcanlogin from pg_roles where rolname = %s", (OWNER,)).fetchone()[0]
    assert puede is False


# =============================================================================
#  Punto 9  --  quitarle CREATE al trafico no le quita su trabajo
# =============================================================================

def test_sin_create_el_trafico_sigue_funcionando_igual(banco):
    admin, esq = banco
    admin.execute(f"create table {esq}.t (id serial primary key, org_id uuid, dato text)")
    admin.execute(f'alter table {esq}.t owner to "{OWNER}"')
    admin.execute(f'grant select, insert, update, delete on {esq}.t to "{TRAFICO}"')
    admin.execute(f'grant usage, select on all sequences in schema {esq} to "{TRAFICO}"')
    admin.execute(f'revoke create on schema {esq} from "{TRAFICO}"')

    estado, _ = _como(TRAFICO, [f"create table {esq}.intrusa (id int)"], esquema=esq)
    assert estado == "error", "sin CREATE no puede crear tablas"

    for sentencia in (
            f"insert into {esq}.t (org_id, dato) values ('{ORG_A}', 'x')",
            f"select count(*) from {esq}.t",
            f"update {esq}.t set dato = 'y'",
            f"delete from {esq}.t"):
        estado, det = _como(TRAFICO, [sentencia], esquema=esq)
        assert estado == "ok", f"el trafico normal se rompio: {sentencia} -> {det}"


# =============================================================================
#  revisar_base()  --  la guarda contra la base
# =============================================================================

def test_la_guarda_detecta_que_el_rol_no_puede_alterar_lo_que_hay(banco):
    """
    La comprobacion que reemplazo a decidir por el nombre del rol: contar las
    tablas cuyo dueno el rol efectivo NO puede ejercer.
    """
    admin, esq = banco
    c = psycopg.connect(**{**_params(), "user": TRAFICO, "password": "b4"},
                        autocommit=True)
    try:
        problemas = cr.revisar_base(c.cursor(), cr.PROPOSITO_MIGRACIONES)
    finally:
        c.close()
    # En 'public' hay tablas que el rol de trafico no posee: la guarda las cuenta.
    assert any(p.codigo == "A" for p in problemas), (
        f"deberia detectar tablas ajenas; devolvio {problemas}")
    assert cr.hay_que_abortar(problemas)


def test_la_guarda_no_se_queja_de_un_rol_que_si_puede(banco):
    admin, _ = banco
    problemas = cr.revisar_base(admin.cursor(), cr.PROPOSITO_MIGRACIONES)
    # El rol de la prueba es dueno (o superusuario) de todo 'public'.
    assert not any(p.codigo == "A" for p in problemas), problemas


def test_la_guarda_exige_que_el_migrador_actue_como_el_dueno(banco):
    """
    Con 'set role' puesto, el rol efectivo es el dueno y no hay queja. Es la
    unica forma de comprobar esa pieza: la variable de entorno no la muestra.
    """
    admin, esq = banco
    c = psycopg.connect(**{**_params(), "user": MIGRATOR, "password": "b4"},
                        autocommit=True)
    try:
        efectivo, sesion = c.execute("select current_user, session_user").fetchone()
    finally:
        c.close()
    assert sesion == MIGRATOR
    assert efectivo == OWNER, (
        "sin 'set role', cada tabla que cree una migracion queda del rol con login")
