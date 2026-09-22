# -*- coding: utf-8 -*-
"""
================================================================================
 M06-C  --  RLS de autorizacion/bitacora y el sello, contra PostgreSQL REAL
================================================================================

Pruebas 1-5 de RLS (y la F: que se ve con BYPASSRLS), mas el sello de la
aprobacion escrito POR LA BASE y protegido por el trigger. Codigo real
(persistencia.db, autorizacion, aprobacion) contra una base que esta prueba
CREA y BORRA en el Postgres local descartable 'pg-b7'.

Se niega a correr contra otro host (devuelve 2). Sin M06C_PG_ADMIN se reporta
OMITIDA -- no en verde. Se corre igual que tests/test_m06b_techo_postgres.py:

    docker run --rm --network net-b7 -v <repo>:/repo:ro -v <vacio>:/repo/.env:ro \
      -w /repo -e PYTHONPATH=/repo -e M06C_PG_ADMIN=postgres://admin:...@pg-b7:5432/crmdb \
      crm-agentico-motor:latest python tests/test_m06c_postgres.py
================================================================================
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import uuid
from urllib.parse import urlparse

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ADMIN = os.environ.get("M06C_PG_ADMIN", "")
_url = urlparse(ADMIN)
BASE = f"m06c_{uuid.uuid4().hex[:8]}"
if not ADMIN:
    print("[m06c-pg] OMITIDA: falta M06C_PG_ADMIN. Corre dentro de la red local de "
          "pruebas (ver el encabezado); ninguna comprobacion se ejecuto.")
    raise SystemExit(0)
if _url.hostname != "pg-b7" or not BASE.startswith("m06c_"):
    print(f"[m06c-pg] me niego: host {_url.hostname!r} no es el Postgres local "
          f"descartable 'pg-b7'.")
    raise SystemExit(2)

import psycopg                                                    # noqa: E402

FALLOS: list[str] = []
ORG = {"tenant_a": str(uuid.uuid4()), "tenant_b": str(uuid.uuid4())}


def afirmar(c: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if c else "  [FALLA] ") + que)
    if not c:
        FALLOS.append(que)
        if detalle:
            print(f"          {detalle}")


def seccion(t: str) -> None:
    print(f"\n--- {t} ---")


def admin(base="crmdb"):
    return psycopg.connect(ADMIN.rsplit("/", 1)[0] + f"/{base}", autocommit=True)


def sql(texto, params=None, base=None):
    with admin(base or BASE) as c:
        cur = c.execute(texto, params)
        return cur.fetchall() if cur.description else None


def como(rol: str, org: str | None, texto: str, params=None):
    """Una sentencia como 'rol', con la organizacion activa 'org'. Devuelve
    (filas, None) o (None, nombre_del_error)."""
    try:
        with admin(BASE) as c:
            with c.transaction():
                c.execute(f"set local role {rol}")
                if org:
                    c.execute("select set_config('app.current_tenant', %s, true)", (org,))
                cur = c.execute(texto, params)
                return (cur.fetchall() if cur.description else cur.rowcount), None
    except Exception as e:                                       # noqa: BLE001
        return None, type(e).__name__


def aplicar(nombre: str) -> None:
    sql((RAIZ / "supabase" / nombre).read_text(encoding="utf-8"))


def preparar() -> list[str]:
    creados = []
    with admin() as c:
        c.execute(f'create database "{BASE}"')
        for rol in ("app_backend", "autonomia_operador", "m06c_intruso"):
            if not c.execute("select 1 from pg_roles where rolname=%s", (rol,)).fetchone():
                c.execute(f"create role {rol} nologin")
                creados.append(rol)
    sql("""
        create extension if not exists pgcrypto;
        create schema if not exists asistente;
        create table public.organization (id uuid primary key);
        create table asistente.tenant_config (slug text primary key,
                                              organization_id uuid not null);
        create table asistente.conversations (id uuid primary key);
        create or replace function asistente.org_actual() returns uuid
          language sql stable as
          $$ select nullif(current_setting('app.current_tenant', true), '')::uuid $$;
        grant usage on schema asistente to app_backend, autonomia_operador;
    """)
    for slug, org in ORG.items():
        sql("insert into public.organization values (%s)", (org,))
        sql("insert into asistente.tenant_config values (%s, %s)", (slug, org))
    for m in ("202608190922_acciones_propuestas.sql", "202609191430_autonomia2_autorizacion.sql",
              "202609211800_aprobacion_vinculante.sql", "202609211900_techo_autonomia.sql",
              "202609212000_m06c_aislamiento_y_sello.sql"):
        aplicar(m)
    #  Una autorizacion y una fila de bitacora por empresa, escritas como
    #  administrador (con BYPASSRLS), para tener que aislar.
    for slug, org in ORG.items():
        sql("""insert into asistente.autorizacion_herramienta
               (organization_id, herramienta, estado, nivel_maximo, autorizado_por)
               values (%s, 'crear_tag_crm', 'autorizada', 2, 'jefe.prueba')""", (org,))
        sql("""insert into asistente.ejecucion_autonoma
               (organization_id, herramienta, decision, actor)
               values (%s, 'crear_tag_crm', 'bloqueada', %s)""", (org, f"prueba-{slug}"))
    return creados


def main() -> int:
    print("=" * 78)
    print(f"  M06-C contra PostgreSQL descartable ({_url.hostname}/{BASE})")
    print("=" * 78)
    creados: list[str] = []
    A, B = ORG["tenant_a"], ORG["tenant_b"]
    try:
        creados = preparar()
        seccion("Migracion")
        aplicar("202609212000_m06c_aislamiento_y_sello.sql")
        afirmar(True, "aplica sobre M06-A y M06-B, y es idempotente (segunda vez sin error)")
        forzada = sql("""select c.relname, c.relrowsecurity, c.relforcerowsecurity
                         from pg_class c join pg_namespace n on n.oid = c.relnamespace
                         where n.nspname = 'asistente'
                           and c.relname in ('autorizacion_herramienta', 'ejecucion_autonoma')
                         order by 1""")
        afirmar(forzada == [("autorizacion_herramienta", True, True),
                            ("ejecucion_autonoma", True, True)],
                f"las dos tablas con RLS habilitada y forzada: {forzada}")
        sql("grant update on asistente.ejecucion_autonoma to app_backend")
        try:
            aplicar("202609212000_m06c_aislamiento_y_sello.sql")
            detecta = False
        except Exception as e:                                   # noqa: BLE001
            detecta = "reescribir la bitacora" in str(e)
        sql("revoke update on asistente.ejecucion_autonoma from app_backend")
        afirmar(detecta, "la comprobacion de la migracion FALLA si el runtime pudiera "
                         "reescribir la bitacora")

        seccion("1. Lectura cross-tenant -> bloqueada")
        for tabla in ("autorizacion_herramienta", "ejecucion_autonoma"):
            todas, _ = como("app_backend", A, f"select organization_id::text from asistente.{tabla}")
            de_b, _ = como("app_backend", A,
                           f"select 1 from asistente.{tabla} where organization_id = %s", (B,))
            afirmar(todas == [(A,)] and de_b == [],
                    f"{tabla}: app_backend de A ve solo lo suyo ({len(todas or [])} fila) y "
                    f"pidiendo las de B ve {len(de_b or [])}")
            sin_org, _ = como("app_backend", None, f"select 1 from asistente.{tabla}")
            afirmar(sin_org == [], f"{tabla}: sin empresa activa, 0 filas ({sin_org})")

        seccion("2. Escritura cross-tenant -> bloqueada")
        _, err = como("app_backend", A, """insert into asistente.ejecucion_autonoma
                      (organization_id, herramienta, decision) values (%s, 'x', 'bloqueada')""", (B,))
        afirmar(err is not None, f"app_backend de A escribe bitacora de B -> {err}")
        _, err = como("autonomia_operador", A, """insert into asistente.autorizacion_herramienta
                      (organization_id, herramienta, estado, nivel_maximo, autorizado_por)
                      values (%s, 'crear_tag_crm', 'autorizada', 3, 'intruso')""", (B,))
        afirmar(err is not None, f"el operador en la sesion de A autoriza en B -> {err}")
        n, err = como("app_backend", A, "update asistente.ejecucion_autonoma set motivo = 'x'")
        afirmar(err is not None, f"app_backend reescribe la bitacora -> {err}")
        n, err = como("app_backend", A, "delete from asistente.ejecucion_autonoma")
        afirmar(err is not None, f"app_backend borra la bitacora -> {err}")
        afirmar(sql("select count(*) from asistente.ejecucion_autonoma")[0][0] == 2
                and sql("select count(*) from asistente.autorizacion_herramienta")[0][0] == 2,
                "y las filas siguen intactas (2 y 2)")

        seccion("3. El runtime legitimo funciona, con el codigo real")
        partes = urlparse(ADMIN)
        os.environ.update(DBHOST=partes.hostname, DBPORT=str(partes.port or 5432),
                          DBNAME=BASE, DBUSER=partes.username, DBPASSWORD=partes.password)
        from nucleo.persistencia import db as persistencia
        from nucleo.seguridad import aprobacion as aprobaciones
        from nucleo.seguridad import autorizacion
        from nucleo.seguridad import techo as techos
        fila = persistencia.autorizacion_herramienta("tenant_a", "crear_tag_crm")
        afirmar(fila is not None and fila["autorizado_por"] == "jefe.prueba",
                "el gate lee la autorizacion de SU empresa")
        persistencia.registrar_ejecucion_autonoma(
            "tenant_a", herramienta="crear_tag_crm", decision="permitida",
            codigo="autorizada", actor="motor", evidencia="evento:m06c")
        afirmar(sql("select count(*) from asistente.ejecucion_autonoma where organization_id = %s",
                    (A,))[0][0] == 2, "la bitacora del runtime se escribe en SU empresa")
        techos.cambiar("tenant_a", 2, actor="Operador Prueba", motivo="m06c",
                       origen="cli:m06c", anterior_esperado=None)
        v = autorizacion.veredicto("tenant_a", "crear_tag_crm")
        afirmar(v.permitido, f"la autorizacion granular de punta a punta (techo 2 + "
                             f"autorizacion 2) -> {v.codigo}")
        v = autorizacion.veredicto("tenant_b", "crear_tag_crm")
        afirmar(not v.permitido, f"B, con su propia autorizacion pero sin techo -> {v.codigo}")

        seccion("4. El operador autorizado funciona")
        n, err = como("autonomia_operador", A, """insert into asistente.autorizacion_herramienta
                      (organization_id, herramienta, estado, estado_anterior, nivel_maximo,
                       autorizado_por, motivo)
                      values (%s, 'crear_tag_crm', 'revocada', 'autorizada', 2,
                              'jefe.prueba', 'fin del piloto')""", (A,))
        afirmar(err is None and n == 1, f"el operador revoca en SU empresa ({err or 'ok'})")
        v = autorizacion.veredicto("tenant_a", "crear_tag_crm")
        afirmar(v.codigo == autorizacion.REVOCADA, f"y el gate lo ve al instante -> {v.codigo}")
        filas, err = como("autonomia_operador", A,
                          "select organization_id::text from asistente.ejecucion_autonoma")
        de_b = sum(1 for f in (filas or []) if f[0] != A)
        afirmar(err is None and filas and de_b == 0,
                f"el operador lee la bitacora de SU empresa ({len(filas or [])} filas, "
                f"{de_b} de otra empresa)")

        seccion("5. Identidad no autorizada -> bloqueada")
        for tabla in ("autorizacion_herramienta", "ejecucion_autonoma"):
            _, err = como("m06c_intruso", A, f"select 1 from asistente.{tabla}")
            afirmar(err is not None, f"un rol sin permisos lee {tabla} -> {err}")
        _, err = como("app_backend", A, """insert into asistente.autorizacion_herramienta
                      (organization_id, herramienta, estado, nivel_maximo, autorizado_por)
                      values (%s, 'crear_tag_crm', 'autorizada', 4, 'runtime')""", (A,))
        afirmar(err is not None, f"el runtime se autoriza a si mismo -> {err}")

        seccion("F. BYPASSRLS: existe, y no reemplaza el aislamiento")
        sup = sql("select rolsuper or rolbypassrls from pg_roles where rolname = current_user")[0][0]
        todas = sql("select count(distinct organization_id) from asistente.autorizacion_herramienta")[0][0]
        rb = sql("select rolbypassrls from pg_roles where rolname = 'app_backend'")[0][0]
        afirmar(sup and todas == 2 and not rb,
                f"el usuario que conecta TIENE bypass y ve las {todas} empresas; app_backend "
                f"(bypassrls={rb}) no -- por eso el motor baja de rol antes de leer o escribir")

        seccion("El sello de la aprobacion, escrito por la base")
        args = {"id_factura": 999001, "fecha_limite": "2026-10-15", "accion": 0}
        huella = aprobaciones.hash_de(args)
        pid = persistencia.guardar_accion_propuesta(
            "tenant_a", "agregar_promesa_pago", args, "Promesa de prueba", "facturacion",
            "colaborador", hash_argumentos=huella, origen="evento:wamid-m06c", contexto={})
        afirmar(persistencia.aprobar_accion_propuesta("tenant_a", pid, "supervisor.prueba"),
                "se aprueba (compare-and-set) y se escribe el sello")
        f = persistencia.accion_propuesta_de("tenant_a", pid)
        esperado = aprobaciones.sello_de(tenant="tenant_a", organization_id=A,
                                         herramienta="agregar_promesa_pago",
                                         origen="evento:wamid-m06c", huella=huella,
                                         aprobador="supervisor.prueba")
        afirmar(f["sello_aprobacion"] == esperado, "el sello guardado es el que ata la accion")
        a = aprobaciones.desde_fila(f, "tenant_a")
        v = aprobaciones.veredicto(a, tenant="tenant_a", herramienta="agregar_promesa_pago",
                                   argumentos=f["argumentos"])
        afirmar(v.permitido, f"leida de la base, la aprobacion vale para ESA promesa ({v.codigo})")
        v = aprobaciones.veredicto(a, tenant="tenant_a", herramienta="registrar_pago",
                                   argumentos=f["argumentos"])
        afirmar(not v.permitido, f"...y no para registrar_pago ({v.codigo})")
        afirmar(not persistencia.aprobar_accion_propuesta("tenant_a", pid, "otra.persona"),
                "una segunda aprobacion de la misma fila no pasa (0 filas)")
        for campo, valor in (("origen", "evento:otro"), ("sello_aprobacion", "0" * 64),
                             ("revisado_por", "otra.persona"),
                             ("argumentos", json.dumps({"id_factura": 999002}))):
            try:
                sql(f"update asistente.acciones_propuestas set {campo} = %s where id = %s",
                    (valor, pid))
                paso = True
            except Exception as e:                               # noqa: BLE001
                paso = False
                tipo = type(e).__name__
            afirmar(not paso, f"reescribir '{campo}' de una aprobacion, incluso como "
                              f"administrador -> {tipo}")
        pid2 = persistencia.guardar_accion_propuesta(
            "tenant_a", "agregar_promesa_pago", args, "Otra", "facturacion", "colaborador",
            hash_argumentos=huella, origen="evento:wamid-2", contexto={})
        try:
            sql("update asistente.acciones_propuestas set sello_aprobacion = 'x' where id = %s",
                (pid2,))
            paso = True
        except Exception:                                        # noqa: BLE001
            paso = False
        afirmar(not paso, "una propuesta PENDIENTE no puede traer un sello puesto de antemano")
        otra, err = como("app_backend", B, "select 1 from asistente.acciones_propuestas "
                                           "where id = %s", (pid,))
        afirmar(otra == [], "la propuesta de A no es visible desde B")
    finally:
        try:
            with admin() as c:
                c.execute(f'drop database if exists "{BASE}" with (force)')
                for rol in creados:
                    c.execute(f"drop role if exists {rol}")
            quedan = sql("select count(*) from pg_database where datname = %s", (BASE,),
                         base="crmdb")[0][0]
            print(f"\n  base descartable {BASE} borrada (quedan: {quedan}); roles creados y "
                  f"borrados: {creados}")
        except Exception as e:                                   # noqa: BLE001
            print(f"\n  [!] no se pudo limpiar: {e}")
            FALLOS.append("limpieza")

    print()
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s): {FALLOS}")
        return 1
    print("  [OK] Aislamiento y sello verificados en PostgreSQL real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
