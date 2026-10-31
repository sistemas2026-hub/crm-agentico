# -*- coding: utf-8 -*-
"""
================================================================================
 M06-B  --  el techo de autonomia contra PostgreSQL DE VERDAD (descartable)
================================================================================

Lo que la prueba sin base no puede ver: la RLS entre empresas, los permisos del
runtime, el tope de politica en la tabla, y dos operadores moviendo el techo a
la vez. Corre el CODIGO REAL (techo.py, persistencia.db) contra una base que
esta prueba CREA y BORRA.

    SOLO CONTRA UN POSTGRES LOCAL Y DESCARTABLE. Se niega a correr si:
      - M06B_PG_ADMIN no apunta al host 'pg-b7' (el contenedor local), o
      - la base a crear no empieza con 'm06b_'.
    No hay forma de apuntarla a produccion sin editar estas dos lineas.

Como se corre (desde el host, en la red local de pruebas; el .env real se tapa
con uno vacio para que nada lo lea):

    docker run --rm --network net-b7 \
      -v <repo>:/repo:ro -v <vacio>:/repo/.env:ro -w /repo -e PYTHONPATH=/repo \
      -e M06B_PG_ADMIN=postgres://admin:...@pg-b7:5432/crmdb \
      crm-agentico-motor:latest python tests/test_m06b_techo_postgres.py
================================================================================
"""

from __future__ import annotations

import os
import pathlib
import sys
import threading
import uuid
from urllib.parse import urlparse

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ADMIN = os.environ.get("M06B_PG_ADMIN", "")
_url = urlparse(ADMIN)
BASE = f"m06b_techo_{uuid.uuid4().hex[:8]}"
if not ADMIN:
    #  Corrida suelta en el host (la suite de tests/): no hay Postgres
    #  descartable al alcance. Se dice que se omitio -- no se finge un verde.
    print("[m06b-pg] OMITIDA: falta M06B_PG_ADMIN. Esta prueba corre dentro de "
          "la red local de pruebas (ver el encabezado); ninguna comprobacion se "
          "ejecuto.")
    raise SystemExit(0)
if _url.hostname != "pg-b7" or not BASE.startswith("m06b_"):
    print(f"[m06b-pg] me niego: host {_url.hostname!r} no es el Postgres local "
          f"descartable 'pg-b7'.")
    raise SystemExit(2)

import psycopg                                                    # noqa: E402

FALLOS: list[str] = []
ORG = {"tenant_a": str(uuid.uuid4()), "tenant_b": str(uuid.uuid4()),
       "tenant_c": str(uuid.uuid4())}


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if condicion else "  [FALLA] ") + que)
    if not condicion:
        FALLOS.append(que)
        if detalle:
            print(f"          {detalle}")


def seccion(t: str) -> None:
    print(f"\n--- {t} ---")


def admin(base: str = "crmdb"):
    return psycopg.connect(ADMIN.rsplit("/", 1)[0] + f"/{base}", autocommit=True)


def sql(base: str, texto: str, params=None):
    with admin(base) as c:
        return c.execute(texto, params).fetchall() if texto.strip().lower().startswith(
            ("select", "with")) else c.execute(texto, params)


def preparar() -> bool:
    """La base descartable, con lo minimo que las dos migraciones necesitan.
    Devuelve si esta prueba creo el rol del operador (para borrarlo al final)."""
    with admin() as c:
        c.execute(f'create database "{BASE}"')
        creo_rol = not c.execute(
            "select 1 from pg_roles where rolname='autonomia_operador'").fetchone()
        if creo_rol:
            c.execute("create role autonomia_operador nologin")
        if not c.execute("select 1 from pg_roles where rolname='app_backend'").fetchone():
            c.execute("create role app_backend nologin")
    sql(BASE, """
        create extension if not exists pgcrypto;
        create schema if not exists asistente;
        create table public.organization (id uuid primary key);
        create table asistente.tenant_config (slug text primary key,
                                              organization_id uuid not null);
        create or replace function asistente.org_actual() returns uuid
          language sql stable as
          $$ select nullif(current_setting('app.current_tenant', true), '')::uuid $$;
        grant usage on schema asistente to app_backend, autonomia_operador;
    """)
    for slug, org in ORG.items():
        sql(BASE, "insert into public.organization values (%s)", (org,))
        sql(BASE, "insert into asistente.tenant_config values (%s, %s)", (slug, org))
    sql(BASE, (RAIZ / "supabase" / "202609221000_autonomia2_autorizacion.sql")
        .read_text(encoding="utf-8"))
    #  Una fila VIEJA con techo 4 (la escala de M09-J lo permitia), escrita
    #  ANTES de la migracion de M06-B: tiene que poder aplicarse igual y el
    #  codigo tiene que leerla como invalida.
    sql(BASE, """insert into asistente.nivel_autonomia (organization_id, nivel, actor, motivo)
                 values (%s, 4, 'legado', 'fila anterior a M06-B')""", (ORG["tenant_c"],))
    return creo_rol


def migrar() -> None:
    sql(BASE, (RAIZ / "supabase" / "202609221010_techo_autonomia.sql")
        .read_text(encoding="utf-8"))


def main() -> int:
    print("=" * 78)
    print(f"  M06-B contra PostgreSQL descartable ({_url.hostname}/{BASE})")
    print("=" * 78)
    creo_rol = False
    try:
        creo_rol = preparar()

        seccion("Migracion")
        migrar()
        afirmar(True, "aplica con una fila vieja de techo 4 presente (NOT VALID)")
        migrar()
        afirmar(True, "y es idempotente: aplicarla dos veces no falla")
        sql(BASE, "grant insert on asistente.nivel_autonomia to app_backend")
        try:
            migrar()
            detecta = False
        except Exception as e:                                   # noqa: BLE001
            detecta = "subirse el techo" in str(e)
        sql(BASE, "revoke insert on asistente.nivel_autonomia from app_backend")
        afirmar(detecta, "la comprobacion de la migracion FALLA si el runtime "
                         "tuviera INSERT sobre el techo")

        #  El codigo real, apuntado a la base descartable.
        partes = urlparse(ADMIN)
        os.environ.update(DBHOST=partes.hostname, DBPORT=str(partes.port or 5432),
                          DBNAME=BASE, DBUSER=partes.username,
                          DBPASSWORD=partes.password)
        from nucleo.persistencia import db as persistencia
        from nucleo.seguridad import techo as techos

        seccion("11. Sin fila -> falla cerrado")
        _, fallo = techos.leer("tenant_a")
        afirmar(fallo is not None and fallo.codigo == techos.AUSENTE,
                f"tenant_a sin techo -> {fallo and fallo.codigo}")

        seccion("10/17. Fila vieja fuera de politica -> invalida")
        _, fallo = techos.leer("tenant_c")
        afirmar(fallo is not None and fallo.codigo == techos.INVALIDO,
                f"tenant_c con techo 4 heredado -> {fallo and fallo.codigo}")

        seccion("13. El runtime no puede escribir el techo")
        try:
            with persistencia.sesion("tenant_a") as (cur, org):
                cur.execute("""insert into asistente.nivel_autonomia
                               (organization_id, nivel, actor) values (%s, 3, 'runtime')""",
                            (org,))
            escribio = True
        except Exception as e:                                   # noqa: BLE001
            escribio = False
            motivo = type(e).__name__
        afirmar(not escribio, f"app_backend -> INSERT rechazado ({motivo})")

        seccion("16. Un cambio de operador, auditado con todos los campos")
        fila = techos.cambiar("tenant_a", 2, actor="Operador Prueba",
                              motivo="habilitar coordinacion", origen="cli:p16",
                              anterior_esperado=None)
        afirmar(fila["resultado"] == "aplicado", f"None -> 2: {fila['resultado']}")
        nivel, _ = techos.leer("tenant_a")
        afirmar(nivel == 2, f"el techo leido ahora es {nivel}")
        h = persistencia.historial_techo("tenant_a")[0]
        afirmar(all(h.get(k) not in (None, "") for k in
                    ("nivel_solicitado", "actor", "motivo", "origen", "resultado",
                     "creado_en")) and h["nivel_anterior"] is None,
                f"intento con nivel anterior, nuevo, quien, cuando, motivo, origen y "
                f"resultado: {dict(h)}")

        seccion("12. Aislamiento entre empresas (RLS)")
        _, fallo = techos.leer("tenant_b")
        afirmar(fallo is not None and fallo.codigo == techos.AUSENTE,
                f"tenant_b no ve el techo de tenant_a -> {fallo and fallo.codigo}")
        with persistencia.sesion("tenant_b") as (cur, _org):
            cur.execute("select count(*) as n from asistente.nivel_autonomia")
            todas = cur.fetchone()["n"]
            cur.execute("select count(*) as n from asistente.nivel_autonomia "
                        "where organization_id = %s", (ORG["tenant_a"],))
            de_a = cur.fetchone()["n"]
            cur.execute("select count(*) as n from asistente.techo_autonomia_intentos")
            intentos = cur.fetchone()["n"]
        afirmar(todas == 0 and de_a == 0 and intentos == 0,
                f"como app_backend de tenant_b: 0 filas de techo (sin filtro: {todas}, "
                f"pidiendo las de A: {de_a}) y 0 intentos ({intentos})")
        try:
            with persistencia.sesion("tenant_a",
                                     rol=persistencia.ROL_OPERADOR_AUTONOMIA) as (cur, _):
                cur.execute("""insert into asistente.nivel_autonomia
                               (organization_id, nivel, actor, origen)
                               values (%s, 3, 'Operador Prueba', 'cli:x')""",
                            (ORG["tenant_b"],))
            cruzo = True
        except Exception as e:                                   # noqa: BLE001
            cruzo = False
            motivo = type(e).__name__
        afirmar(not cruzo, f"el operador en la sesion de A no escribe el techo de B ({motivo})")

        seccion("17. El tope de politica en la tabla")
        try:
            with persistencia.sesion("tenant_a",
                                     rol=persistencia.ROL_OPERADOR_AUTONOMIA) as (cur, org):
                cur.execute("""insert into asistente.nivel_autonomia
                               (organization_id, nivel, actor, origen)
                               values (%s, 4, 'Operador Prueba', 'cli:x')""", (org,))
            paso = True
        except Exception as e:                                   # noqa: BLE001
            paso = False
            motivo = type(e).__name__
        afirmar(not paso, f"techo 4 escrito directo en la tabla -> rechazado ({motivo})")

        seccion("Intentos: el runtime solo anota rechazos")
        try:
            with persistencia.sesion("tenant_a") as (cur, org):
                cur.execute("""insert into asistente.techo_autonomia_intentos
                               (organization_id, nivel_solicitado, actor, origen, resultado)
                               values (%s, 3, 'runtime', 'cli:x', 'aplicado')""", (org,))
            fabrico = True
        except Exception as e:                                   # noqa: BLE001
            fabrico = False
            motivo = type(e).__name__
        afirmar(not fabrico, f"app_backend no puede fabricar un 'aplicado' ({motivo})")
        try:
            techos.cambiar("tenant_a", 3, actor="motor", motivo="me subo",
                           origen="cli:agente", anterior_esperado=2)
            rechazado = False
        except techos.CambioRechazado as e:
            rechazado = e.codigo == techos.CAMBIO_ACTOR_DEL_SISTEMA
        ultimo = persistencia.historial_techo("tenant_a")[0]
        afirmar(rechazado and ultimo["resultado"] == "rechazado"
                and ultimo["codigo"] == techos.CAMBIO_ACTOR_DEL_SISTEMA,
                f"un agente que intenta subirlo: rechazado Y auditado ({dict(ultimo)})")
        nivel, _ = techos.leer("tenant_a")
        afirmar(nivel == 2, f"y el techo sigue en {nivel}")

        seccion("18. Concurrencia: diez operadores mueven el techo a la vez")
        barrera = threading.Barrier(10)
        resultados: list[str] = []
        candado = threading.Lock()

        def operador(i: int):
            barrera.wait()
            try:
                f = techos.cambiar("tenant_a", 3, actor=f"Operador {i}",
                                   motivo="concurrencia", origen=f"cli:conc-{i}",
                                   anterior_esperado=2)
                r = f["resultado"]
            except techos.CambioRechazado as e:
                r = e.codigo
            with candado:
                resultados.append(r)

        hilos = [threading.Thread(target=operador, args=(i,)) for i in range(10)]
        for t in hilos:
            t.start()
        for t in hilos:
            t.join()
        aplicados = resultados.count("aplicado")
        conflictos = resultados.count(techos.CAMBIO_CONFLICTO)
        afirmar(aplicados == 1 and conflictos == 9,
                f"exactamente 1 aplicado y 9 en conflicto ({resultados})")
        filas = sql(BASE, "select nivel, nivel_anterior from asistente.nivel_autonomia "
                          "where organization_id = %s order by creado_en, id",
                    (ORG["tenant_a"],))
        afirmar(filas == [(2, None), (3, 2)],
                f"historial del techo coherente: {filas}")

        seccion("18. Replay: el mismo pedido otra vez no deja otra transicion")
        ganador = sql(BASE, "select origen from asistente.nivel_autonomia where "
                            "organization_id = %s order by creado_en desc limit 1",
                      (ORG["tenant_a"],))[0][0]
        r = persistencia.registrar_cambio_techo("tenant_a", 3, 2, "Operador X",
                                                "concurrencia", ganador)
        n = sql(BASE, "select count(*) from asistente.nivel_autonomia "
                      "where organization_id = %s", (ORG["tenant_a"],))[0][0]
        afirmar(r["resultado"] == "repetido" and n == 2,
                f"reenvio del pedido ganador -> {r['resultado']}, sigue habiendo {n} filas")

        seccion("Con el techo real, el paso de la frontera")
        afirmar(techos.veredicto("tenant_a", 3).permitido
                and not techos.veredicto("tenant_b", 1).permitido
                and techos.veredicto("tenant_c", 1).codigo == techos.INVALIDO,
                "A (techo 3) pasa una nivel 3; B (sin techo) no pasa ni una nivel 1; "
                "C (techo 4 heredado) queda invalido")
    finally:
        try:
            with admin() as c:
                c.execute(f'drop database if exists "{BASE}" with (force)')
                if creo_rol:
                    c.execute("drop role if exists autonomia_operador")
            quedan = sql("crmdb", "select count(*) from pg_database where datname = %s",
                         (BASE,))[0][0]
            print(f"\n  base descartable {BASE} borrada (quedan: {quedan})")
        except Exception as e:                                   # noqa: BLE001
            print(f"\n  [!] no se pudo borrar {BASE}: {e}")
            FALLOS.append("limpieza")

    print()
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s): {FALLOS}")
        return 1
    print("  [OK] RLS, permisos, tope y concurrencia se comportan en PostgreSQL real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
