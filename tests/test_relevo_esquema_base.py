# -*- coding: utf-8 -*-
"""
================================================================================
 EL ESQUEMA DEL RELEVO  --  control, asignacion y eventos, sin cambiar conducta
================================================================================

    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_relevo_esquema_base.py

B3.1 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md. Base efimera por cli/base_desde_cero.py
(la cadena entera por el ledger, incluida 202609161800_relevo_control_y_eventos.sql).

  1. SIN CAMBIO DE CONDUCTA: una conversacion creada como hoy (INSERT sin las
     columnas nuevas, o por db.registrar_mensaje) queda con control 'ia',
     version 0 y el resto vacio; una fila con las banderas de legado de
     escalada NO se reclasifica.
  2. Los CHECK rechazan los estados que el contrato declara imposibles
     (I1, I2) y aceptan los validos.
  3. relevo_eventos, como app_backend y con RLS (igual que el motor): inserta,
     NO puede actualizar ni borrar, no ve eventos de otra empresa; tipo,
     actor, datos y clave validados en la base.

Se salta si faltan DBHOST/DBPORT/DBUSER/DBPASSWORD o Docker. Borra su base.
================================================================================
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker")
    raise SystemExit(0)

import psycopg                                                      # noqa: E402
from psycopg.types.json import Jsonb                                # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
BASE = "b3_esquema_" + uuid.uuid4().hex[:6]
TENANT, OTRO = "b3prueba", "b3otra"
OPERADOR = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def dsn(base: str) -> str:
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


def q(sentencia, params=None):
    with psycopg.connect(dsn(BASE), autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


def rechaza(sentencia, params, excepcion) -> tuple[bool, str]:
    try:
        q(sentencia, params)
        return False, "se acepto"
    except excepcion:
        return True, ""
    except Exception as e:                                          # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def fila_minima(tabla: str, fijos: dict) -> None:
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


def borrar_base():
    with psycopg.connect(dsn("postgres"), autocommit=True) as con:
        con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname = %s and pid <> pg_backend_pid()", (BASE,))
        con.execute(f'drop database if exists "{BASE}"')


print("=" * 74)
print(" EL ESQUEMA DEL RELEVO")
print("=" * 74)

try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    comprobar(bool(q("select 1 from asistente.migraciones_aplicadas "
                     "where archivo = '202609161800_relevo_control_y_eventos.sql'")),
              "la migracion del relevo quedo aplicada por el ledger")

    org, otra = str(uuid.uuid4()), str(uuid.uuid4())
    fila_minima("organization", {"id": org, "name": "Org B3"})
    fila_minima("organization", {"id": otra, "name": "Otra B3"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s), (%s, %s)",
      (org, TENANT, otra, OTRO))
    os.environ["DBNAME"] = BASE
    from nucleo.persistencia import db                              # noqa: E402

    # -----------------------------------------------------------------------
    print("\n== 1. sin cambio de conducta ==")
    conv = q("""insert into asistente.conversations (organization_id, canal, usuario_externo)
                values (%s, 'whatsapp', '573000000001') returning id""", (org,))[0][0]
    fila = q("""select control, control_motivo, asignada_a_usuario_id, asignada_a_nombre, asignada_en,
                       pendiente_interno_desde, aviso_relevo, relevo_version
                from asistente.conversations where id = %s""", (conv,))[0]
    comprobar(fila == ("ia", None, None, None, None, None, None, 0),
              f"INSERT como hoy: control 'ia', version 0, resto vacio ({fila})")
    conv2, _ = db.registrar_mensaje(TENANT, "api", "u1", "cliente_final", "user", "hola", origen="cliente")
    comprobar(q("select control, relevo_version from asistente.conversations where id = %s", (conv2,))[0] == ("ia", 0),
              "una conversacion creada por db.registrar_mensaje queda con control 'ia'")
    legado = q("""insert into asistente.conversations
                    (organization_id, canal, usuario_externo, escalada_a_humano, necesita_atencion_humana, tomada_por)
                  values (%s, 'whatsapp', '573000000002', true, true, 'ana@x.co') returning id""", (org,))[0][0]
    comprobar(q("select control, control_motivo, asignada_a_nombre, escalada_a_humano, tomada_por "
                "from asistente.conversations where id = %s", (legado,))[0]
              == ("ia", None, None, True, "ana@x.co"),
              "una fila con banderas de legado de escalada NO se reclasifica (sin backfill hasta G8)")

    # -----------------------------------------------------------------------
    print("\n== 2. los CHECK del contrato ==")
    upd = "update asistente.conversations set {} where id = %s"
    for que, set_sql in (
            ("control fuera de ia|humano", "control = 'robot'"),
            ("control humano sin motivo (I1)", "control = 'humano'"),
            ("motivo con control de la IA (I1)", "control_motivo = 'escalada'"),
            ("motivo desconocido", "control = 'humano', control_motivo = 'capricho'"),
            ("asignada con control de la IA (I2)", "asignada_a_nombre = 'Ana', asignada_a_usuario_id = '" + OPERADOR + "'"),
            ("asignada con id y sin nombre", "control = 'humano', control_motivo = 'escalada', asignada_a_usuario_id = '" + OPERADOR + "'"),
            ("aviso desconocido", "aviso_relevo = 'otra_cosa'")):
        ok, detalle = rechaza(upd.format(set_sql), (conv,), psycopg.errors.CheckViolation)
        comprobar(ok, f"rechaza: {que}", detalle)
    q(upd.format("control = 'humano', control_motivo = 'escalada', asignada_a_nombre = 'Ana', "
                 "asignada_a_usuario_id = %s, asignada_en = now(), relevo_version = relevo_version + 1"),
      (OPERADOR, conv))
    comprobar(q("select control, asignada_a_nombre, relevo_version from asistente.conversations where id = %s",
                (conv,))[0] == ("humano", "Ana", 1),
              "acepta: control humano por escalada, asignada a Ana, version 1")
    q(upd.format("asignada_a_usuario_id = null, asignada_a_nombre = 'tomada_por legado'"), (conv,))
    comprobar(True, "acepta: asignacion de legado con nombre y sin id")
    ok, detalle = rechaza(upd.format("control = 'ia', control_motivo = null"), (conv,), psycopg.errors.CheckViolation)
    comprobar(ok, "rechaza: devolver a la IA sin soltar la asignacion (I2)", detalle)
    q(upd.format("control = 'ia', control_motivo = null, asignada_a_nombre = null, asignada_a_usuario_id = null, "
                 "asignada_en = null"), (conv,))
    comprobar(True, "acepta: devolver a la IA soltando la asignacion")

    # -----------------------------------------------------------------------
    print("\n== 3. relevo_eventos como app_backend ==")
    with db.sesion(TENANT) as (cur, o):
        cur.execute("""insert into asistente.relevo_eventos
                         (organization_id, conversation_id, tipo, actor_tipo, actor_usuario_id, actor_nombre,
                          datos, clave_idempotencia)
                       values (%s, %s, 'tomada', 'operador', %s, 'Ana', %s, 'ev-1') returning id""",
                    (o, conv, OPERADOR, Jsonb({"anterior": None})))
        ev = cur.fetchone()["id"]
    comprobar(bool(ev), "app_backend inserta un evento de su empresa")

    for que, sql in (("actualizar", "update asistente.relevo_eventos set tipo = 'soltada' where id = %s"),
                     ("borrar", "delete from asistente.relevo_eventos where id = %s")):
        try:
            with db.sesion(TENANT) as (cur, o):
                cur.execute(sql, (ev,))
            comprobar(False, f"app_backend NO puede {que} un evento", "se permitio")
        except psycopg.errors.InsufficientPrivilege:
            comprobar(True, f"app_backend NO puede {que} un evento (solo se agrega)")
    comprobar(q("select tipo from asistente.relevo_eventos where id = %s", (ev,)) == [("tomada",)],
              "el evento sigue intacto")

    with db.sesion(OTRO) as (cur, o):
        cur.execute("select count(*) as n from asistente.relevo_eventos")
        visibles = cur.fetchone()["n"]
    comprobar(visibles == 0, f"otra empresa no ve el evento (RLS) ({visibles})")
    try:
        with db.sesion(OTRO) as (cur, o):
            cur.execute("""insert into asistente.relevo_eventos (organization_id, conversation_id, tipo, actor_tipo)
                           values (%s, %s, 'soltada', 'sistema')""", (org, conv))
        comprobar(False, "otra empresa no puede escribir eventos de esta", "se permitio")
    except psycopg.errors.InsufficientPrivilege:
        comprobar(True, "otra empresa no puede escribir eventos de esta (RLS with check)")

    base_ev = ("insert into asistente.relevo_eventos (organization_id, conversation_id, tipo, actor_tipo, "
               "actor_nombre, datos, clave_idempotencia) values (%s, %s, %s, %s, %s, %s, %s)")
    for que, params, exc in (
            ("tipo desconocido", (org, conv, "inventado", "sistema", None, Jsonb({}), None), psycopg.errors.CheckViolation),
            ("actor desconocido", (org, conv, "tomada", "robot", None, Jsonb({}), None), psycopg.errors.CheckViolation),
            ("operador sin nombre", (org, conv, "tomada", "operador", None, Jsonb({}), None), psycopg.errors.CheckViolation),
            ("datos que no son un objeto", (org, conv, "tomada", "sistema", None, Jsonb([1, 2]), None), psycopg.errors.CheckViolation),
            ("clave repetida en la conversacion", (org, conv, "soltada", "operador", "Ana", Jsonb({}), "ev-1"), psycopg.errors.UniqueViolation)):
        ok, detalle = rechaza(base_ev, params, exc)
        comprobar(ok, f"rechaza evento: {que}", detalle)
    q("delete from asistente.conversations where id = %s", (conv,))
    comprobar(q("select count(*) from asistente.relevo_eventos where id = %s", (ev,))[0][0] == 0,
              "borrar la conversacion (purga) arrastra sus eventos")
finally:
    try:
        borrar_base()
        print(f"\n       -> {BASE} borrada")
    except Exception as e:
        print(f"\n  [aviso] no se pudo borrar {BASE}: {type(e).__name__}: {e}")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] El esquema del relevo no cambia nada de hoy y rechaza lo que el contrato prohibe.")
