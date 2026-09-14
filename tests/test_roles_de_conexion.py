# -*- coding: utf-8 -*-
"""
================================================================================
 LOS USUARIOS QUE SE CONECTAN  --  no los roles que se prueban con SET ROLE
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=test_p2 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_roles_de_conexion.py

Por que existe
--------------
La matriz de roles se midio conectando como 'motor' y haciendo 'set role'. Eso
prueba las ACL de los roles de ACCESO, y no prueba lo que va a pasar en
produccion: ahi cada proceso se conecta con SU usuario, y lo que puede o no
puede hacer depende de ese usuario de login, no de un 'set role' hecho desde
un superusuario.

Aca se conecta de verdad --autenticando con scram-sha-256-- como
'scheduler_login', 'executor_login' y 'monitor_login', y se consulta
session_user, current_user, membresias y ACL desde adentro de esa sesion.

Y se deja medido por que el scheduler NUNCA puede conectarse como 'motor'.

Las contraseñas son aleatorias por corrida y no salen de este proceso.
================================================================================
"""

from __future__ import annotations

import os
import secrets
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

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
BASE = os.environ["DBNAME"]
ADMIN_USR, ADMIN_PWD = os.environ["DBUSER"], os.environ["DBPASSWORD"]

PARES = {
    "scheduler_login": "scheduler_coordinator",
    "executor_login": "job_executor",
    "monitor_login": "monitor_ro",
}
ACCESO = ("scheduler_coordinator", "job_executor", "monitor_ro")
PELIGROSOS = ("asistente_owner", "app_backend", ADMIN_USR)
CLAVES = {login: secrets.token_urlsafe(24) for login in PARES}


def conectar(usuario, clave):
    return psycopg.connect(
        host=HOST, port=PUERTO, dbname=BASE, user=usuario, password=clave,
        sslmode="disable", autocommit=True, row_factory=dict_row,
        connect_timeout=10)


def intenta(con, sql, params=None):
    """(True, filas) o (False, nombre del error). Autocommit: un error no
    envenena la sesion para el intento siguiente."""
    try:
        cur = con.execute(sql, params)
        try:
            return True, cur.fetchall()
        except psycopg.ProgrammingError:
            return True, None
    except psycopg.errors.Error as e:
        return False, type(e).__name__


admin = conectar(ADMIN_USR, ADMIN_PWD)
try:
    # =========================================================================
    titulo("0. aplicar el archivo declarativo, dos veces")
    # =========================================================================
    sql = (RAIZ / "supabase" / "roles" / "conexiones_scheduler.sql").read_text(
        encoding="utf-8")
    for vuelta in (1, 2):
        ok, err = intenta(admin, sql)
        revisar(ok, f"pasada {vuelta} del archivo de roles sin error", err)

    # Una membresia ajena agregada a mano tiene que desaparecer al reaplicar:
    # declarativo es converger, no sumar.
    admin.execute("grant job_executor to scheduler_login")
    admin.execute(sql)
    extra = admin.execute(
        "select count(*) as n from pg_auth_members a "
        "join pg_roles m on m.oid=a.member join pg_roles g on g.oid=a.roleid "
        "where m.rolname='scheduler_login' and g.rolname='job_executor'"
    ).fetchone()["n"]
    revisar(extra == 0,
            "una membresia de mas agregada a mano se revoca al reaplicar",
            f"quedo {extra}")

    # =========================================================================
    titulo("1. sin contraseña no entra nadie")
    # =========================================================================
    for login in PARES:
        admin.execute(f"alter role {login} password null")
        try:
            conectar(login, "cualquier-cosa").close()
            revisar(False, f"'{login}' sin contraseña no autentica", "ENTRO")
        except psycopg.OperationalError:
            revisar(True, f"'{login}' sin contraseña no autentica "
                          f"(el archivo solo no abre ninguna puerta)")
        admin.execute(f"alter role {login} password %s".replace("%s", "'" +
                      CLAVES[login].replace("'", "''") + "'"))

    # =========================================================================
    titulo("2. atributos y membresias, desde el catalogo")
    # =========================================================================
    for login, rol in PARES.items():
        a = admin.execute(
            "select rolsuper, rolbypassrls, rolinherit, rolcanlogin, "
            "rolcreatedb, rolcreaterole, rolreplication from pg_roles "
            "where rolname=%s", (login,)).fetchone()
        print(f"    {login:<16} {dict(a)}")
        revisar(a["rolcanlogin"] and not a["rolsuper"] and not a["rolbypassrls"]
                and not a["rolinherit"] and not a["rolcreatedb"]
                and not a["rolcreaterole"] and not a["rolreplication"],
                f"'{login}': LOGIN, sin superuser, bypassrls, inherit, "
                f"createdb, createrole ni replication")
        mem = admin.execute(
            "select g.rolname as rol, a.admin_option, a.inherit_option, "
            "a.set_option from pg_auth_members a "
            "join pg_roles m on m.oid=a.member "
            "join pg_roles g on g.oid=a.roleid where m.rolname=%s",
            (login,)).fetchall()
        print(f"      membresias: {[dict(m) for m in mem]}")
        revisar([dict(m) for m in mem] == [{"rol": rol, "admin_option": False,
                                            "inherit_option": False,
                                            "set_option": True}],
                f"'{login}' tiene UNA membresia: {rol} (set, sin inherit ni admin)")

    # =========================================================================
    titulo("3. desde adentro de cada sesion")
    # =========================================================================
    funciones = {
        "scheduler_coordinator": [
            ("select * from asistente.jobs_vencidos(now(), 1)", None, True),
            ("select * from asistente.job_claim('prueba_inexistente',%s,now(),'w')",
             (uuid.uuid4(),), True),
            ("select asistente.job_finalize(%s,'x','succeeded')", (uuid.uuid4(),), False),
            ("select asistente.job_heartbeat(%s,'x')", (uuid.uuid4(),), False),
            ("select * from asistente.job_contexto(%s,'x')", (uuid.uuid4(),), False),
            ("select * from asistente.job_salud(now())", None, False),
        ],
        "job_executor": [
            ("select * from asistente.job_contexto(%s,'x')", (uuid.uuid4(),), True),
            ("select asistente.job_heartbeat(%s,'x')", (uuid.uuid4(),), True),
            ("select asistente.job_finalize(%s,'x','succeeded')", (uuid.uuid4(),), True),
            ("select * from asistente.job_claim('x',%s,now(),'w')", (uuid.uuid4(),), False),
            ("select * from asistente.jobs_vencidos(now(), 1)", None, False),
            ("select * from asistente.job_salud(now())", None, False),
        ],
        "monitor_ro": [
            ("select * from asistente.job_salud(now())", None, True),
            ("select * from asistente.jobs_vencidos(now(), 1)", None, False),
            ("select * from asistente.job_claim('x',%s,now(),'w')", (uuid.uuid4(),), False),
            ("select asistente.job_heartbeat(%s,'x')", (uuid.uuid4(),), False),
        ],
    }

    for login, rol in PARES.items():
        print(f"\n  --- {login} ---")
        con = conectar(login, CLAVES[login])
        try:
            quien = con.execute("select session_user as s, current_user as c"
                                ).fetchone()
            revisar(quien["s"] == login and quien["c"] == login,
                    f"recien conectado: session_user = current_user = {login}",
                    f"{dict(quien)}")

            ok, _ = intenta(con, funciones[rol][0][0], funciones[rol][0][1])
            revisar(not ok,
                    "sin 'set role' no puede ni lo suyo: la membresia es "
                    "NOINHERIT", "pudo")

            for otro in [r for r in ACCESO if r != rol] + list(PELIGROSOS):
                ok, err = intenta(con, f'set role "{otro}"')
                revisar(not ok, f"no puede SET ROLE {otro}", err or "PUDO")
                intenta(con, "reset role")

            ok, err = intenta(con, f"set role {rol}")
            revisar(ok, f"SI puede SET ROLE {rol}", err)
            quien = con.execute("select session_user as s, current_user as c"
                                ).fetchone()
            revisar(quien["s"] == login and quien["c"] == rol,
                    f"y queda session_user={login}, current_user={rol}",
                    f"{dict(quien)}")

            for sql_f, params, debe in funciones[rol]:
                ok, err = intenta(con, sql_f, params)
                corto = sql_f.split("asistente.")[1].split("(")[0]
                revisar(ok == debe,
                        f"como {rol}: {'puede' if debe else 'NO puede'} {corto}",
                        err or "pudo")

            for tabla in ("job_run", "job_attempt", "job_schedule_state",
                          "job_run_event", "job_catalogo"):
                ok, err = intenta(con, f"select 1 from asistente.{tabla} limit 1")
                revisar(not ok, f"no lee asistente.{tabla}", err or "LEYO")

            for crear in ("create table asistente.intruso (x int)",
                          "create table public.intruso (x int)",
                          "create function asistente.intrusa() returns int "
                          "language sql as 'select 1'"):
                ok, err = intenta(con, crear)
                revisar(not ok, f"no crea objetos: {crear.split('(')[0][:40]}",
                        err or "CREO")
        finally:
            con.close()

    # =========================================================================
    titulo("4. por que NUNCA como motor")
    # =========================================================================
    con = conectar(ADMIN_USR, ADMIN_PWD)
    try:
        a = con.execute("select rolsuper, rolbypassrls from pg_roles "
                        "where rolname = session_user").fetchone()
        print(f"    {ADMIN_USR}: rolsuper={a['rolsuper']} "
              f"rolbypassrls={a['rolbypassrls']}")
        con.execute("set role scheduler_coordinator")
        ok_puesto, _ = intenta(con, "select 1 from asistente.job_run limit 1")
        con.execute("reset role")
        ok_escape, _ = intenta(con, "select count(*) from asistente.job_run")
        revisar(not ok_puesto,
                "con 'set role scheduler_coordinator' puesto, ni motor lee job_run")
        revisar(ok_escape and (a["rolsuper"] or a["rolbypassrls"]),
                "pero basta 'reset role' para leerla: conectado como motor, "
                "las ACL no protegen nada -- el proceso puede salir del rol "
                "cuando quiera",
                "no pudo escapar: entonces el usuario de esta base no es "
                "superusuario y la demostracion no aplica")
    finally:
        con.close()

    # =========================================================================
    titulo("5. HALLAZGO para P5: el tick en-proceso necesita DOS membresias")
    # =========================================================================
    # 'coordinador.un_tick' reclama con puerta.sesion(COORDINADOR) y, en el MISMO
    # proceso y con el MISMO DSN, llama a ejecutor.ejecutar, que abre
    # puerta.sesion(EJECUTOR). Con un login de UNA sola membresia --que es lo
    # que P5 exige-- la fase de ejecucion no puede asumir su rol. Se mide que
    # consecuencia tiene hoy.
    admin.execute("delete from asistente.job_run_event")
    admin.execute("delete from asistente.job_attempt")
    admin.execute("delete from asistente.job_schedule_state")
    admin.execute("delete from asistente.job_run")
    admin.execute("update asistente.job_catalogo set habilitado=true "
                  "where code='prueba_p2'")
    admin.execute("insert into asistente.job_schedule_state (job_code, "
                  "organization_id, next_run_at) values ('prueba_p2', "
                  "'00000000-0000-4000-8000-00000000000a', "
                  "date_trunc('hour', now()) - interval '1 hour')")

    from nucleo.programador import coordinador, metricas, registro  # noqa: E402

    registro.olvidar_pruebas()
    registro.registrar_para_prueba("prueba_p2", lambda t: {"ok": True})
    viejo = {k: os.environ.get(k) for k in ("DBUSER", "DBPASSWORD")}
    os.environ["DBUSER"] = "scheduler_login"
    os.environ["DBPASSWORD"] = CLAVES["scheduler_login"]
    try:
        informe = coordinador.un_tick(metricas.Registro())
    finally:
        for k, v in viejo.items():
            os.environ[k] = v
        registro.olvidar_pruebas()

    turno = (informe.get("turnos") or [{}])[0]
    print(f"    informe: alcanzados={informe.get('alcanzados')} "
          f"turno={ {k: turno.get(k) for k in ('registrado', 'error', 'nota')} }")
    revisar(informe.get("alcanzados") == 1,
            "con scheduler_login el claim SI funciona")
    revisar(turno.get("registrado") is None
            and "InsufficientPrivilege" in str(turno.get("error", "")),
            "pero la fase de ejecucion NO puede asumir job_executor: el turno "
            "no se ejecuta -- el modo en-proceso de 'un_tick' es incompatible "
            "con logins de una sola membresia",
            f"{turno}")
    est = admin.execute(
        "select current_run_id is not null as vivo, lease_until > now() as lease "
        "from asistente.job_schedule_state where job_code='prueba_p2'").fetchone()
    revisar(est["vivo"] and est["lease"],
            "y el turno queda reclamado con lease vivo hasta que venza: no se "
            "pierde, pero se atrasa un lease entero",
            f"{dict(est)}")
finally:
    admin.close()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Cada login puede solo lo suyo, y motor no es opcion.")
print("=" * 74)
