# -*- coding: utf-8 -*-
"""
================================================================================
 PREFLIGHT G6  --  se puede aplicar el DDL ahora mismo, o no
================================================================================

    DBHOST=... DBPORT=... DBNAME=... DBUSER=... DBPASSWORD=... \\
      py -3.13 cli/preflight_g6.py                    (solo lectura)
    ... py -3.13 cli/preflight_g6.py --medir --filas 200000   (base de PRUEBA)

DOS COSAS DISTINTAS, Y CONVIENE NO CONFUNDIRLAS
-----------------------------------------------
  sin --medir   SOLO LECTURA. Mira si la base esta en condiciones de recibir el
                DDL: sesiones 'idle in transaction', locks retenidos sobre las
                tres tablas del contrato, y el volumen real. Es lo que G6 exige
                correr INMEDIATAMENTE ANTES de aplicar, tambien en produccion.

  con --medir   ESCRIBE. Deshace el DDL de mensajes, puebla la tabla y lo vuelve
                a aplicar cronometrando. Solo contra una base de prueba: se
                niega si la base se llama como la de produccion o si encuentra
                datos que no sembro.

POR QUE EL PREFLIGHT NO ES UNA FORMALIDAD
-----------------------------------------
'ALTER TABLE ADD COLUMN' nullable y sin default no reescribe la tabla desde
PostgreSQL 11 -- es un cambio de catalogo-- pero igual pide un ACCESS EXCLUSIVE
por un instante. Si hay UNA transaccion abierta sobre esa tabla, el ALTER se
queda esperando ese lock, y mientras espera BLOQUEA A TODOS LOS DEMAS detras de
el. Una transaccion olvidada convierte un cambio de milisegundos en una caida.

Ese es exactamente el problema que ya se midio en este despliegue (sesiones
'idle in transaction' detras del pooler), y por eso G6 dice que con sesiones
retenidas NO SE APLICA, y que subir 'lock_timeout' no es la primera respuesta:
subirlo hace que el ALTER espere MAS, no menos.

'CREATE UNIQUE INDEX' sin CONCURRENTLY toma un SHARE lock: no bloquea lecturas
pero SI bloquea escrituras mientras construye. Cuanto tarda depende de cuantas
filas entran en el indice -- y el de mensajes es PARCIAL
('where clave_idempotencia is not null'), asi que sobre datos de legado, donde
esa columna es toda NULL, el indice nace vacio.
================================================================================
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

#: Las tres que el contrato nombra (§16, G6).
TABLAS = ("asistente.conversations", "asistente.messages",
          "asistente.acciones_propuestas")

#: Nombres que NO se tocan con --medir, pase lo que pase. La lista es corta a
#: proposito: es mas facil agregar un nombre que explicar por que se borro una
#: columna de produccion.
PROHIBIDAS = ("postgres", "prod", "produccion", "production", "supabase")

#: Lo que la migracion de mensajes agrega. Deshacerlo y rehacerlo es lo que se
#: cronometra. Sale de supabase/202609161600_origen_de_mensajes.sql: si ese
#: archivo cambia, esto tiene que cambiar con el.
COLUMNAS = ("origen", "autor_usuario_id", "autor_nombre", "clave_idempotencia")
INDICE = "messages_clave_idempotencia_uq"

DDL_COLUMNAS = """
alter table asistente.messages
  add column if not exists origen text
    constraint messages_origen_check
    check (origen in ('cliente', 'ia', 'humano', 'sistema')),
  add column if not exists autor_usuario_id uuid,
  add column if not exists autor_nombre text,
  add column if not exists clave_idempotencia text
"""

DDL_INDICE = f"""
create unique index if not exists {INDICE}
  on asistente.messages (organization_id, conversation_id, clave_idempotencia)
  where clave_idempotencia is not null
"""


def conectar(autocommit=True):
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        print(f"[g6] faltan variables de conexion: {faltan}")
        raise SystemExit(2)
    return psycopg.connect(
        host=os.environ["DBHOST"], port=os.environ["DBPORT"],
        dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
        password=os.environ["DBPASSWORD"],
        autocommit=autocommit, row_factory=dict_row)


# =============================================================================
#  SOLO LECTURA -- lo que hay que mirar antes de aplicar
# =============================================================================

def preflight(cn) -> bool:
    """True si se puede aplicar. Imprime por que si no."""
    print(f"\n{'=' * 72}\n  PREFLIGHT  ({os.environ['DBNAME']})\n{'=' * 72}")
    limpio = True

    fila = cn.execute("select version() as v").fetchone()
    print(f"  servidor : {fila['v'].split(',')[0]}")

    print("\n  -- volumen --")
    for tabla in TABLAS:
        try:
            n = cn.execute(f"select count(*) as n from {tabla}").fetchone()["n"]
            t = cn.execute("select pg_size_pretty(pg_total_relation_size(%s)) as s",
                           (tabla,)).fetchone()["s"]
            print(f"     {tabla:<38} {n:>9} filas   {t}")
        except Exception as e:
            print(f"     {tabla:<38} no se pudo leer: {type(e).__name__}")

    # Sesiones que retienen una transaccion abierta. El ALTER espera DETRAS de
    # ellas, y todo lo demas espera detras del ALTER.
    print("\n  -- sesiones con transaccion abierta --")
    retenidas = cn.execute("""
        select pid, state, usename,
               extract(epoch from (now() - state_change))::int as segundos
        from pg_stat_activity
        where state in ('idle in transaction', 'idle in transaction (aborted)')
          and datname = current_database() and pid <> pg_backend_pid()
        order by segundos desc""").fetchall()
    if retenidas:
        limpio = False
        for s in retenidas:
            print(f"     [BLOQUEA] pid {s['pid']} {s['state']} "
                  f"hace {s['segundos']}s ({s['usename']})")
        print("     Con sesiones retenidas NO se aplica. Subir lock_timeout no es"
              "\n     la respuesta: haria que el ALTER espere mas, no menos.")
    else:
        print("     ninguna  [ok]")

    print("\n  -- locks sobre las tres tablas --")
    locks = cn.execute("""
        select l.pid, l.mode, c.relname, a.state,
               extract(epoch from (now() - a.state_change))::int as segundos
        from pg_locks l
        join pg_class c on c.oid = l.relation
        join pg_namespace n on n.oid = c.relnamespace
        left join pg_stat_activity a on a.pid = l.pid
        where n.nspname = 'asistente'
          and c.relname in ('conversations', 'messages', 'acciones_propuestas')
          and l.pid <> pg_backend_pid()
        order by c.relname""").fetchall()
    problematicos = [x for x in locks
                     if "Exclusive" in (x["mode"] or "") or "ShareLock" == x["mode"]]
    for x in locks:
        marca = "[BLOQUEA]" if x in problematicos else "         "
        print(f"     {marca} pid {x['pid']:>7} {x['mode']:<22} {x['relname']}")
    if not locks:
        print("     ninguno  [ok]")
    if problematicos:
        limpio = False

    print(f"\n  => {'SE PUEDE APLICAR' if limpio else 'NO SE APLICA TODAVIA'}")
    return limpio


# =============================================================================
#  MEDICION -- solo contra una base de prueba
# =============================================================================

def _exigir_base_de_prueba(cn):
    nombre = os.environ["DBNAME"].lower()
    for prohibida in PROHIBIDAS:
        if prohibida in nombre:
            print(f"[g6] '{os.environ['DBNAME']}' parece una base real "
                  f"(contiene '{prohibida}'). --medir ESCRIBE: no se hace.")
            raise SystemExit(2)


def _sembrar(cn, filas: int) -> str:
    """Una organizacion propia con 'filas' mensajes repartidos en conversaciones.

    La distribucion imita la medida en produccion (A8): 2584 mensajes en 298
    conversaciones, o sea ~8,7 por conversacion. Un reparto plano daria un
    indice con otra forma.
    """
    org = uuid.uuid4()
    oblig = cn.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema='public' and table_name='organization' "
        "and is_nullable='NO' and column_default is null").fetchall()
    valores = {"id": str(org), "name": f"g6-{org.hex[:8]}",
               "api_key": f"k-{org}", "company_name": "g6"}
    for f in oblig:
        campo, tipo = f["column_name"], f["data_type"]
        if campo in valores:
            continue
        valores[campo] = ("now()" if "timestamp" in tipo or tipo == "date"
                          else True if tipo == "boolean"
                          else 0 if tipo in ("integer", "bigint", "smallint", "numeric")
                          else "{}" if tipo in ("json", "jsonb", "ARRAY") else "")
    cols = ", ".join('"' + k + '"' for k in valores)
    marcas = ", ".join("now()" if v == "now()" else "%s" for v in valores.values())
    cn.execute(f"insert into public.organization ({cols}) values ({marcas})",
               [v for v in valores.values() if v != "now()"])

    por_conversacion = 9
    conversaciones = max(1, filas // por_conversacion)
    print(f"  sembrando {filas} mensajes en {conversaciones} conversaciones...")
    t0 = time.perf_counter()
    cn.execute("""
        insert into asistente.conversations
            (organization_id, canal, usuario_externo, estado)
        select %s, 'whatsapp', '57300' || lpad(g::text, 7, '0'), 'abierta'
        from generate_series(1, %s) g""", (str(org), conversaciones))
    cn.execute("""
        insert into asistente.messages
            (organization_id, conversation_id, rol, contenido, creado_en)
        select c.organization_id, c.id,
               case when g %% 2 = 0 then 'user' else 'assistant' end,
               repeat('texto de prueba ', 1 + (g %% 20)),
               now() - (g || ' minutes')::interval
        from asistente.conversations c
        cross join generate_series(1, %s) g
        where c.organization_id = %s""", (por_conversacion, str(org)))
    print(f"  sembrado en {time.perf_counter() - t0:.1f} s")
    return str(org)


def _deshacer(cn):
    cn.execute(f"drop index if exists asistente.{INDICE}")
    for col in COLUMNAS:
        cn.execute(f"alter table asistente.messages drop column if exists {col}")


def _cronometrar(cn, etiqueta, sql, lock_timeout="3s"):
    """Una sentencia, con lock_timeout puesto: si no consigue el lock en ese
    plazo falla en vez de bloquear a todos detras. Es lo que hay que hacer en
    produccion, no confiar en que estara libre."""
    with cn.cursor() as cur:
        cur.execute(f"set lock_timeout = '{lock_timeout}'")
        t0 = time.perf_counter()
        try:
            cur.execute(sql)
            ms = (time.perf_counter() - t0) * 1000
            print(f"     {etiqueta:<34} {ms:>9.1f} ms")
            return ms, None
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            print(f"     {etiqueta:<34} {ms:>9.1f} ms  FALLO: {type(e).__name__}")
            return ms, e
        finally:
            cur.execute("set lock_timeout = 0")


def medir(cn, filas: int, repeticiones: int = 2):
    _exigir_base_de_prueba(cn)
    print(f"\n{'=' * 72}\n  MEDICION  ({filas} filas, {repeticiones} corridas)"
          f"\n{'=' * 72}")

    org = _sembrar(cn, filas)
    try:
        n = cn.execute("select count(*) as n from asistente.messages "
                       "where organization_id = %s", (org,)).fetchone()["n"]
        antes = cn.execute("select pg_size_pretty(pg_total_relation_size("
                           "'asistente.messages')) as s").fetchone()["s"]
        print(f"  messages: {n} filas propias, tabla {antes}")

        for corrida in range(1, repeticiones + 1):
            print(f"\n  -- corrida {corrida} --")
            _deshacer(cn)
            t_col, e1 = _cronometrar(cn, "alter table add column x4", DDL_COLUMNAS)
            t_idx, e2 = _cronometrar(cn, "create unique index (parcial)", DDL_INDICE)
            print(f"     {'TOTAL':<34} {t_col + t_idx:>9.1f} ms")
            if e1 or e2:
                print("     [FALLA] el DDL no se pudo aplicar")

        despues = cn.execute("select pg_size_pretty(pg_total_relation_size("
                             "'asistente.messages')) as s").fetchone()["s"]
        idx = cn.execute("select pg_size_pretty(pg_relation_size(%s)) as s",
                         (f"asistente.{INDICE}",)).fetchone()["s"]
        print(f"\n  tabla antes {antes} -> despues {despues}   indice {idx}")
        print("  El indice es PARCIAL sobre clave_idempotencia: en datos de"
              "\n  legado esa columna es toda NULL, asi que nace vacio.")

        # Escrituras concurrentes DURANTE el create index.
        print("\n  -- una escritura concurrente mientras corre el CREATE INDEX --")
        _deshacer(cn)
        cn.execute(DDL_COLUMNAS)
        otra = conectar()
        try:
            conv = cn.execute("select id from asistente.conversations "
                              "where organization_id = %s limit 1",
                              (org,)).fetchone()["id"]
            t0 = time.perf_counter()
            cn.execute(DDL_INDICE)
            t_idx = (time.perf_counter() - t0) * 1000
            t1 = time.perf_counter()
            otra.execute("""insert into asistente.messages
                              (organization_id, conversation_id, rol, contenido)
                            values (%s, %s, 'user', 'durante el ddl')""",
                         (org, conv))
            t_ins = (time.perf_counter() - t1) * 1000
            print(f"     create index                   {t_idx:>9.1f} ms")
            print(f"     insert inmediatamente despues  {t_ins:>9.1f} ms")
            print("     El CREATE INDEX toma SHARE: bloquea escrituras mientras"
                  "\n     construye. Con este volumen la ventana es la de arriba.")
        finally:
            otra.close()
    finally:
        cn.execute("delete from public.organization where id = %s", (org,))
        print(f"\n  [limpieza] organizacion de prueba borrada")


def main():
    p = argparse.ArgumentParser(description="Preflight G6")
    p.add_argument("--medir", action="store_true",
                   help="ESCRIBE: puebla y cronometra. Solo base de prueba.")
    p.add_argument("--filas", type=int, default=2584,
                   help="cuantos mensajes sembrar (por defecto, el volumen "
                        "medido en produccion: A8)")
    p.add_argument("--corridas", type=int, default=2)
    args = p.parse_args()

    cn = conectar()
    try:
        limpio = preflight(cn)
        if args.medir:
            medir(cn, args.filas, args.corridas)
        return 0 if limpio else 1
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
