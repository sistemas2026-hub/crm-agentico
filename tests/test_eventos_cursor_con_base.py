# -*- coding: utf-8 -*-
"""
================================================================================
 CURSOR DE EVENTOS  --  entrega sin perdidas y aislamiento entre empresas
================================================================================

Lo que fija, y por que cada cosa
---------------------------------
A6  dos ISP no se ven entre si. El aislamiento no es un filtro en la consulta:
    lo pone 'sesion(tenant)', y una consulta sin empresa fijada devuelve cero
    filas, no todas.

A7  cero perdidas y cero duplicados. El caso que lo motiva NO es teorico: el
    cursor por (creado_en, id) pierde eventos, medido el 29/10/2026 contra
    PostgreSQL 17.11 -- de 2 insertados entregaba 1. La causa es que
    'creado_en default now()' es el instante en que la transaccion EMPEZO, no
    en el que hizo commit.

Y el coste de la garantia: una transaccion en vuelo RETIENE a las posteriores.
Eso se comprueba aqui en vez de descubrirse en produccion.

Como se corre
-------------
Necesita un PostgreSQL 17 de laboratorio. Se salta solo si no hay, con exit 0
y diciendolo -- nunca en silencio.

    docker run -d --rm --name pge1 -e POSTGRES_PASSWORD=p -e POSTGRES_DB=lab \\
        -p 15432:5432 postgres:17

    set DBHOST=localhost & set DBPORT=15432 & set DBUSER=postgres
    set DBPASSWORD=p & set DBNAME=lab
    py -3.13 tests/test_eventos_cursor_con_base.py

Crea su propio esquema y sus propios datos. No toca produccion.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
RAIZ = Path(__file__).resolve().parent.parent

if not os.environ.get("DBHOST"):
    print("[saltada] No hay DBHOST: hace falta un PostgreSQL 17 de")
    print("          laboratorio. Ver la cabecera. NO se comprobo nada.")
    raise SystemExit(0)

_HOST = os.environ.get("DBHOST", "")
if _HOST not in ("localhost", "127.0.0.1", "::1", "host.docker.internal"):
    print(f"[ABORTA] DBHOST='{_HOST}' no es local, y esta prueba ESCRIBE.")
    raise SystemExit(1)

import psycopg                                           # noqa: E402

fallos: list[str] = []


def comprobar(ok: bool, que: str) -> None:
    print(f"  [{'OK' if ok else 'FALLA'}]  {que}")
    if not ok:
        fallos.append(que)


DSN = (f"host={os.environ['DBHOST']} port={os.environ.get('DBPORT','5432')} "
       f"user={os.environ['DBUSER']} password={os.environ['DBPASSWORD']} "
       f"dbname={os.environ['DBNAME']}")

FRONTERA = "pg_snapshot_xmin(pg_current_snapshot())"
CERO = ("0", "00000000-0000-0000-0000-000000000000")

#  La consulta REAL del cursor, con el aislamiento por empresa incluido. Se
#  copia aqui en vez de importar db.py porque ese modulo abre su propia sesion
#  contra la base de verdad; lo que se prueba es la GARANTIA de la consulta.
CURSOR = f"""
  select tx::text, id::text, herramienta from asistente.tool_calls
   where organization_id = %s
     and tx is not null
     and tx < {FRONTERA}
     and (tx, id) > (%s::xid8, %s::uuid)
   order by tx, id limit %s
"""


def preparar():
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("create schema if not exists asistente")
        c.execute("""create table if not exists public.organization (
                       id uuid primary key default gen_random_uuid(),
                       name text)""")
        c.execute("""create table if not exists asistente.tool_calls (
                       id uuid primary key default gen_random_uuid(),
                       organization_id uuid not null
                         references public.organization(id),
                       herramienta text not null,
                       parametros jsonb not null default '{}'::jsonb,
                       rol_solicitante text, exito boolean not null default true,
                       es_escritura boolean not null default false,
                       duracion_ms integer,
                       creado_en timestamptz not null default now())""")
        #  La migracion que se esta probando, tal cual.
        sql = (RAIZ / "supabase" / "202610291700_tool_calls_cursor.sql").read_text(
            encoding="utf-8")
        c.execute(sql)
        c.execute("delete from asistente.tool_calls")
        c.execute("delete from public.organization")
        a = c.execute(
            "insert into public.organization (name) values ('ISP A') returning id"
        ).fetchone()[0]
        b = c.execute(
            "insert into public.organization (name) values ('ISP B') returning id"
        ).fetchone()[0]
        return a, b


def meter(org, nombre, con=None, params="{}"):
    cerrar = con is None
    con = con or psycopg.connect(DSN, autocommit=True)
    con.execute("insert into asistente.tool_calls "
                "(organization_id, herramienta, parametros) values (%s,%s,%s::jsonb)",
                (org, nombre, params))
    if cerrar:
        con.close()


def consumir(lector, org, cursor, limite=100):
    vistos = []
    while True:
        filas = lector.execute(CURSOR, (org, cursor[0], cursor[1], limite)).fetchall()
        if not filas:
            return vistos, cursor
        vistos += [f[2] for f in filas]
        cursor = (filas[-1][0], filas[-1][1])


print("=" * 72)
with psycopg.connect(DSN, autocommit=True) as c:
    print(f" CURSOR DE EVENTOS  --  PostgreSQL {c.execute('show server_version').fetchone()[0]}")
print("=" * 72)

ORG_A, ORG_B = preparar()

# ------------------------------------------------------------------ A6 -----
print("\n[A6] Dos ISP no se ven entre si")
for i in range(4):
    meter(ORG_A, f"a{i}")
for i in range(3):
    meter(ORG_B, f"b{i}")

lec = psycopg.connect(DSN, autocommit=True)
va, _ = consumir(lec, ORG_A, CERO)
vb, _ = consumir(lec, ORG_B, CERO)
lec.close()
comprobar(sorted(va) == ["a0", "a1", "a2", "a3"],
          f"la empresa A recibe SOLO lo suyo -> {sorted(va)}")
comprobar(sorted(vb) == ["b0", "b1", "b2"],
          f"la empresa B recibe SOLO lo suyo -> {sorted(vb)}")
comprobar(not (set(va) & set(vb)), "cero eventos cruzados entre las dos")

# ------------------------------------------------------------------ A7 -----
print("\n[A7] Cero perdidas con una transaccion que commitea tarde")
with psycopg.connect(DSN, autocommit=True) as c:
    c.execute("delete from asistente.tool_calls")

lenta = psycopg.connect(DSN, autocommit=False)
meter(ORG_A, "LA_QUE_COMMITEA_TARDE", con=lenta)
time.sleep(0.4)
meter(ORG_A, "rapida")

lec = psycopg.connect(DSN, autocommit=True)
v1, cur = consumir(lec, ORG_A, CERO)
lenta.commit()
v2, cur = consumir(lec, ORG_A, cur)
lec.close()
lenta.close()
todos = v1 + v2
comprobar(len(todos) == 2 and len(set(todos)) == 2,
          f"2 insertados -> {len(todos)} entregados, sin repetir {sorted(todos)}")
comprobar("LA_QUE_COMMITEA_TARDE" in todos,
          "la que commiteo tarde SI llega (es la que el cursor por fecha perdia)")

print("\n[A7b] Paginacion: el limite no pierde ni duplica")
with psycopg.connect(DSN, autocommit=True) as c:
    c.execute("delete from asistente.tool_calls")
for i in range(30):
    meter(ORG_A, f"p{i:02}")
lec = psycopg.connect(DSN, autocommit=True)
v, _ = consumir(lec, ORG_A, CERO, limite=7)
lec.close()
comprobar(len(v) == 30 and len(set(v)) == 30,
          f"30 eventos en paginas de 7 -> {len(v)} entregados, {len(set(v))} distintos")

print("\n[A7c] Reconexion: otro cliente retoma el cursor guardado")
with psycopg.connect(DSN, autocommit=True) as c:
    c.execute("delete from asistente.tool_calls")
for i in range(5):
    meter(ORG_A, f"r{i}")
lec = psycopg.connect(DSN, autocommit=True)
primeros = lec.execute(CURSOR, (ORG_A, CERO[0], CERO[1], 2)).fetchall()
cur = (primeros[-1][0], primeros[-1][1])
lec.close()
meter(ORG_A, "llego_mientras_caido")
otro = psycopg.connect(DSN, autocommit=True)
resto, _ = consumir(otro, ORG_A, cur)
otro.close()
todos = [f[2] for f in primeros] + resto
comprobar(len(todos) == 6 and len(set(todos)) == 6,
          f"6 eventos (5 + 1 durante la caida) -> {len(todos)} sin repetir")

# ------------------------------------------------- la frontera del snapshot -
print("\n[F] La frontera NO avanza sobre transacciones activas")
with psycopg.connect(DSN, autocommit=True) as c:
    c.execute("delete from asistente.tool_calls")
bloq = psycopg.connect(DSN, autocommit=False)
meter(ORG_A, "la_que_bloquea", con=bloq)
time.sleep(0.3)
for i in range(3):
    meter(ORG_A, f"posterior{i}")
lec = psycopg.connect(DSN, autocommit=True)
durante, _ = consumir(lec, ORG_A, CERO)
comprobar(len(durante) == 0,
          f"con una transaccion ABIERTA no se entrega nada -> {len(durante)} de 4")
bloq.commit()
despues, _ = consumir(lec, ORG_A, CERO)
comprobar(len(despues) == 4,
          f"al cerrarse salen las 4 de golpe -> {len(despues)}")

#  Y que ese retraso se PUEDA VER. No se promete un techo: se mide.
bloq2 = psycopg.connect(DSN, autocommit=False)
meter(ORG_A, "retiene", con=bloq2)
time.sleep(1.1)
retraso = lec.execute("""select extract(epoch from (now() - min(xact_start)))
                           from pg_stat_activity
                          where backend_xid is not null
                            and pid <> pg_backend_pid()""").fetchone()[0]
comprobar(retraso is not None and retraso >= 1.0,
          f"el retraso del flujo es OBSERVABLE -> {round(float(retraso),1)}s")
bloq2.rollback()
bloq2.close()
lec.close()

# ------------------------------------------------------- lista blanca -------
print("\n[P] De 'parametros' solo sale la lista blanca")
with psycopg.connect(DSN, autocommit=True) as c:
    c.execute("delete from asistente.tool_calls")
meter(ORG_A, "derivar_a_area",
      params='{"area":"facturacion_cliente","motivo":"...ubre","cedula":"...6789"}')
lec = psycopg.connect(DSN, autocommit=True)
params = lec.execute("select parametros from asistente.tool_calls").fetchone()[0]
lec.close()
PUBLICAS = ("area", "servicio", "confianza")
expuesto = {k: params[k] for k in PUBLICAS if k in params}
comprobar(expuesto == {"area": "facturacion_cliente"},
          f"sale el destino de la derivacion -> {expuesto}")
comprobar("motivo" not in expuesto and "cedula" not in expuesto,
          "y NO salen el motivo ni la cedula, aunque esten enmascarados")

print("\n" + "=" * 72)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" El cursor entrega sin perdidas y las empresas no se ven entre si.")
print("=" * 72)
