# -*- coding: utf-8 -*-
"""
================================================================================
 EL POOL DE CONEXIONES NO AFLOJA EL AISLAMIENTO  --  11/11/2026
================================================================================
    DBHOST=... DBPORT=... DBUSER=... DBPASSWORD=...  py -3.13 tests/test_pool_conexiones_base.py

Desde hoy sesion() reutiliza conexiones (nucleo/persistencia/db.py, EL POOL DE
CONEXIONES). Lo que esta prueba afirma, contra PostgreSQL real:

  1. EL EFECTO: dos sesiones seguidas usan la MISMA conexion (mismo backend),
     y la segunda es mas barata que abrir una conexion nueva.
  2. LA GARANTIA: la conexion que vuelve al pool esta en el rol con el que se
     conecto y SIN tenant fijado. Una sesion con el tenant A no le deja nada a
     la siguiente, aunque sea del tenant B -- la misma conexion, 0 filas ajenas.
  3. Una sesion que falla (rollback) tampoco deja rastro.
  4. El camino del interruptor (timeout corto) sigue abriendo conexion propia.

Construye una base efimera y la borra al final. Se saltea sin credenciales.
================================================================================
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker")
    raise SystemExit(0)

import psycopg                                                      # noqa: E402

from base_local import exigir_base_local                           # noqa: E402
exigir_base_local(__file__)

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
BASE = "pool_" + uuid.uuid4().hex[:6]
TENANT_A, TENANT_B = "empresa_a", "empresa_b"
fallos: list[str] = []


def comprobar(condicion, que, detalle=""):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def dsn(base):
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


def q(sentencia, params=None):
    with psycopg.connect(dsn(BASE), autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


def fila_minima(tabla, fijos):
    cols = q("""select column_name, data_type, character_maximum_length from information_schema.columns
                where table_schema = 'public' and table_name = %s
                  and is_nullable = 'NO' and column_default is null""", (tabla,))
    valores = dict(fijos)
    por_tipo = {"uuid": lambda: str(uuid.uuid4()), "boolean": lambda: False,
                "integer": lambda: 0, "bigint": lambda: 0, "smallint": lambda: 0,
                "jsonb": lambda: "{}", "json": lambda: "{}",
                "timestamp with time zone": lambda: "now", "date": lambda: "2026-01-01"}
    for nombre, tipo, largo in cols:
        if nombre not in valores:
            valor = por_tipo.get(tipo, lambda: "x" + uuid.uuid4().hex[:8])()
            valores[nombre] = valor[:largo] if largo and isinstance(valor, str) else valor
    nombres = list(valores)
    q(f"insert into public.{tabla} ({', '.join(nombres)}) values ({', '.join(['%s'] * len(nombres))})",
      [valores[n] for n in nombres])


print("=" * 74)
print(" EL POOL DE CONEXIONES NO AFLOJA EL AISLAMIENTO")
print("=" * 74)
try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO,
                            "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    orgs = {}
    for t in (TENANT_A, TENANT_B):
        orgs[t] = str(uuid.uuid4())
        fila_minima("organization", {"id": orgs[t], "name": f"Org {t}"})
        q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (orgs[t], t))
    for t in (TENANT_A, TENANT_B):
        q("""insert into asistente.conversations (organization_id, canal, usuario_externo, estado)
             values (%s, 'whatsapp', %s, 'abierta')""", (orgs[t], "5730000" + t[-1]))
    os.environ["DBNAME"] = BASE
    from nucleo.persistencia import db                              # noqa: E402

    comprobar(db._pool() is not None, "hay pool (psycopg_pool instalado)")

    print("\n1. EL EFECTO: la conexion se reutiliza")
    pids = []
    for _ in range(8):
        t0 = time.perf_counter()
        with db.sesion(TENANT_A) as (cur, _):
            pids.append(cur.execute("select pg_backend_pid() as pid").fetchone()["pid"])
        reusada_ms = (time.perf_counter() - t0) * 1000
    pid_1 = pids[-1]
    t0 = time.perf_counter()
    psycopg.connect(db.dsn()).close()
    nueva_ms = (time.perf_counter() - t0) * 1000
    # El pool puede abrir una segunda conexion en el arranque; lo que no puede
    # es abrir una por sesion, que es lo que hacia hasta hoy.
    comprobar(len(set(pids)) <= 2,
              f"ocho sesiones seguidas usan {len(set(pids))} backend(s), no ocho", str(pids))
    comprobar(reusada_ms < nueva_ms,
              f"la sesion reutilizada ({reusada_ms:.1f} ms) cuesta menos que una conexion nueva ({nueva_ms:.1f} ms)")

    print("\n2. LA GARANTIA: lo que vuelve al pool esta limpio")
    pool = db._pool()
    with db.sesion(TENANT_A) as (cur, org_a):
        dentro = cur.execute("""select current_user as rol,
                                       current_setting('app.current_tenant', true) as tenant,
                                       (select count(*) from asistente.conversations) as filas""").fetchone()
    comprobar(dentro["rol"] == db.ROL_RUNTIME and dentro["tenant"] == org_a and dentro["filas"] == 1,
              "DENTRO de la sesion: rol app_backend, tenant A fijado, 1 fila (la suya)",
              str(dentro))
    con = pool.getconn()
    try:
        fuera = con.execute("""select current_user as rol,
                                      coalesce(current_setting('app.current_tenant', true), '') as tenant""").fetchone()
        con.rollback()
    finally:
        pool.putconn(con)
    comprobar(fuera["rol"] != db.ROL_RUNTIME and fuera["tenant"] == "",
              "AL VOLVER al pool: rol de conexion y SIN tenant fijado", str(fuera))

    with db.sesion(TENANT_B) as (cur, org_b):
        de_b = cur.execute("""select current_setting('app.current_tenant', true) as tenant,
                                     (select count(*) from asistente.conversations) as filas,
                                     (select count(*) from asistente.conversations
                                       where organization_id = %s) as ajenas""", (org_a,)).fetchone()
    comprobar(de_b["tenant"] == org_b and de_b["filas"] == 1 and de_b["ajenas"] == 0,
              "la siguiente sesion (tenant B) sobre la misma conexion ve SOLO lo de B", str(de_b))

    print("\n3. Una sesion que falla tampoco deja rastro")
    try:
        with db.sesion(TENANT_A) as (cur, _):
            cur.execute("select 1/0")
    except Exception:
        pass
    con = pool.getconn()
    try:
        tras = con.execute("""select current_user as rol,
                                     coalesce(current_setting('app.current_tenant', true), '') as tenant,
                                     txid_current_if_assigned() as tx""").fetchone()
        con.rollback()
    finally:
        pool.putconn(con)
    comprobar(tras["rol"] != db.ROL_RUNTIME and tras["tenant"] == "" and tras["tx"] is None,
              "tras el rollback: sin rol elevado, sin tenant, sin transaccion abierta", str(tras))

    print("\n4. El interruptor sigue con conexion propia")
    with db.sesion(TENANT_A, connect_timeout=db.SEGUNDOS_CONEXION_GATE) as (cur, _):
        pid_gate = cur.execute("select pg_backend_pid() as pid").fetchone()["pid"]
        st = cur.execute("show statement_timeout").fetchone()["statement_timeout"]
    comprobar(pid_gate != pid_1 and st == f"{db.SEGUNDOS_CONEXION_GATE}s",
              f"el camino del gate abre otra conexion y acota statement_timeout ({st})",
              f"pid gate {pid_gate} vs pool {pid_1}")

    print("\n5. Sin pool (DB_POOL=0) se vuelve a una conexion por sesion")
    os.environ["DB_POOL"] = "0"
    try:
        with db.sesion(TENANT_A) as (cur, _):
            pid_sin = cur.execute("select pg_backend_pid() as pid").fetchone()["pid"]
        comprobar(pid_sin != pid_1, "con DB_POOL=0 la sesion no pasa por el pool")
    finally:
        del os.environ["DB_POOL"]

    db.cerrar_pools()
finally:
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute(f'drop database if exists "{BASE}" with (force)')
    except Exception as e:
        print(f"  (no se pudo borrar {BASE}: {type(e).__name__})")

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("Todo en orden.")
