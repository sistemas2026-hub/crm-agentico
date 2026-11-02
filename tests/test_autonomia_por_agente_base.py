# -*- coding: utf-8 -*-
"""
================================================================================
 LA AUTONOMIA POR AGENTE, CONTRA POSTGRESQL REAL  --  02/11/2026
================================================================================

supabase/202611021200_autonomia_por_agente.sql. Lo que se protege:

  - la fila propia de un agente MANDA sobre la general: una retirada para
    'soporte' frena a 'soporte' aunque la general este activa; un agente sin
    fila propia sigue la general;
  - la consulta que decide es la de nucleo/persistencia/autonomia_ganada.vigente
    (se importa su texto, no se copia);
  - promover dos veces el mismo alcance falla; la funcion vieja (sin agente)
    sigue respetando lo general, asi el orden entre migracion y despliegue no
    rompe nada;
  - degradar baja TODO lo activo de la herramienta y no repite ruido;
  - otra empresa no;
  - la migracion es idempotente.

Contra un Postgres de descarte, nunca uno real:

    docker run -d --name pg-agente -e POSTGRES_PASSWORD=prueba -p 55491:5432 postgres:16
    AUTONOMIA_PG_ADMIN=postgres://postgres:prueba@127.0.0.1:55491/postgres \\
        py -3.13 tests/test_autonomia_por_agente_base.py

Sin la variable se reporta OMITIDA, no en verde.
================================================================================
"""

from __future__ import annotations

import inspect
import os
import re
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

ADMIN = os.environ.get("AUTONOMIA_PG_ADMIN", "")
if not ADMIN:
    print("  OMITIDA: falta AUTONOMIA_PG_ADMIN (ver el encabezado). Ninguna comprobacion corrio.")
    raise SystemExit(0)

from base_local import exigir_base_local                       # noqa: E402
exigir_base_local(__file__, dsn=ADMIN)

import psycopg                                                  # noqa: E402

from nucleo.persistencia import autonomia_ganada as persistencia  # noqa: E402

fallos: list[str] = []
ORG = "00000000-0000-0000-0000-000000000001"


def revisar(cond: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if cond else '[FALLA]'} {que}" + (f" ({detalle})" if not cond else ""))
    if not cond:
        fallos.append(que)


def consulta_de_vigente() -> str:
    """El SQL de persistencia.vigente, sacado de su codigo: si cambia alla, la
    prueba mide el nuevo."""
    fuente = inspect.getsource(persistencia.vigente)
    return re.search(r'"""(select .*?)"""', fuente, re.S).group(1)


base = f"agente_{uuid.uuid4().hex[:10]}"
with psycopg.connect(ADMIN, autocommit=True) as c:
    c.execute(f"create database {base}")
try:
    with psycopg.connect(ADMIN.rsplit("/", 1)[0] + f"/{base}", autocommit=True) as c:
        c.execute("""
            do $$ begin
              if not exists (select 1 from pg_roles where rolname = 'app_backend') then
                create role app_backend nologin; end if;
              if not exists (select 1 from pg_roles where rolname = 'autonomia_operador') then
                create role autonomia_operador nologin; end if;
            end $$;
            create schema asistente;
            create table public.organization (id uuid primary key);
            insert into public.organization values ('00000000-0000-0000-0000-000000000001');
            create function asistente.org_actual() returns uuid language sql stable as $f$
              select nullif(current_setting('app.current_tenant', true), '')::uuid $f$;""")
        c.execute((RAIZ / "supabase" / "202610310200_autonomia_ganada.sql").read_text(encoding="utf-8"))
        c.execute(f"set app.current_tenant = '{ORG}'")
        c.execute("select estado from asistente.autonomia_ganada_promover(%s, 'reiniciar_ont', 'ana', 'antes', '{}')",
                  (ORG,))
        nueva = (RAIZ / "supabase" / "202611021200_autonomia_por_agente.sql").read_text(encoding="utf-8")
        c.execute(nueva)
        c.execute(nueva)
        revisar(True, "la migracion corre sobre una fila general previa, y una segunda vez")

        uno = lambda sql, *p: c.execute(sql, p).fetchone()             # noqa: E731
        revisar(uno("select count(*) from asistente.autonomia_ganada where rol is null and estado = 'activa'")[0] == 1,
                "la fila de antes queda como general")
        uno("select 1 from asistente.autonomia_ganada_retirar_agente(%s, 'reiniciar_ont', 'soporte', 'ana', 'no')", ORG)
        uno("select 1 from asistente.autonomia_ganada_promover_agente(%s, 'reiniciar_ont', 'cliente_final', 'ana', 'si', '{}')", ORG)

        sql_vigente = consulta_de_vigente()

        def vigente(rol):
            fila = c.execute(sql_vigente, (ORG, "reiniciar_ont", rol)).fetchone()
            return fila and (fila[6] or "*", fila[1])

        revisar(vigente("soporte") == ("soporte", "retirada"),
                "la retirada propia de 'soporte' manda sobre la general activa", str(vigente("soporte")))
        revisar(vigente("cliente_final") == ("cliente_final", "activa"),
                "la promocion propia de 'cliente_final' decide", str(vigente("cliente_final")))
        revisar(vigente("ventas") == ("*", "activa"),
                "un agente sin fila propia sigue la general", str(vigente("ventas")))
        revisar(vigente(None) == ("*", "activa"), "sin agente: la general", str(vigente(None)))

        for sql, que in (
            ("select asistente.autonomia_ganada_promover_agente(%s, 'reiniciar_ont', 'cliente_final', 'ana', 'x', '{}')",
             "promover dos veces el mismo alcance falla"),
            ("select asistente.autonomia_ganada_promover(%s, 'reiniciar_ont', 'ana', 'x', '{}')",
             "la funcion vieja (sin agente) respeta lo general activo"),
        ):
            try:
                c.execute(sql, (ORG,))
                revisar(False, que)
            except psycopg.errors.RaiseException:
                revisar(True, que)

        degradada = uno("select estado from asistente.autonomia_ganada_degradar(%s, 'reiniciar_ont', 'no confirmo', '{}')", ORG)
        alcances = dict(c.execute("""select distinct on (rol) coalesce(rol, '*'), estado
                                       from asistente.autonomia_ganada where herramienta = 'reiniciar_ont'
                                      order by rol, creado_en desc, id desc""").fetchall())
        revisar(degradada[0] == "degradada" and alcances == {"*": "degradada", "cliente_final": "degradada",
                                                            "soporte": "retirada"},
                "degradar baja TODO lo activo, general y por agente", str(alcances))
        otra = uno("select estado from asistente.autonomia_ganada_degradar(%s, 'reiniciar_ont', 'otra', '{}')", ORG)
        revisar(otra[0] is None, "una segunda degradacion no agrega nada")
        #  LA PROPIA MANDA AUNQUE LA GENERAL SEA MAS NUEVA: se vuelve a promover
        #  la general DESPUES de la retirada de 'soporte'. Una consulta que solo
        #  ordenara por fecha devolveria la general activa.
        uno("select 1 from asistente.autonomia_ganada_promover_agente(%s, 'reiniciar_ont', null, 'ana', 'otra vez', '{}')", ORG)
        revisar(vigente("soporte") == ("soporte", "retirada"),
                "la propia manda aunque la general sea mas nueva", str(vigente("soporte")))
        revisar(vigente("ventas") == ("*", "activa"), "y quien no tiene propia toma la general nueva",
                str(vigente("ventas")))
        try:
            c.execute("select asistente.autonomia_ganada_promover_agente('00000000-0000-0000-0000-000000000009', "
                      "'reiniciar_ont', 'soporte', 'ana', 'x', '{}')")
            revisar(False, "otra empresa no promueve")
        except psycopg.errors.RaiseException:
            revisar(True, "otra empresa no promueve")
finally:
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f"drop database if exists {base} with (force)")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] La autonomia se decide por agente, la propia manda, y degradar baja todo.")
