# -*- coding: utf-8 -*-
"""
Verificacion de una restauracion: estructura Y funcion.

    py -3.13 despliegue/respaldo/verificar_restauracion.py --puerto 15460 \
        [--host localhost] [--base postgres] [--usuario postgres] \
        [--clave test] [--sin-comparar]

POR QUE EXISTE
--------------
Un 'pg_restore' que termina en 0 no dice nada sobre si la base restaurada
sirve. Medido en el paso 10.2: con pgcrypto en el esquema equivocado, el
restore termina en 0, las 129 tablas estan, las 10 funciones del scheduler
estan, 'job_salud()' y 'jobs_vencidos()' responden -- y 'job_claim()' falla con
'schema "extensions" does not exist'.

Por eso la prueba principal es el FLUJO: reclamar un turno, leer su contexto,
latir y finalizar. job_salud y jobs_vencidos quedan como controles
secundarios, nunca como prueba del scheduler: no llaman a digest.

Los datos de prueba se crean SOLO en la replica.
"""
import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import psycopg
from psycopg.rows import dict_row

fallos = []


def afirmar(cond, que, detalle=""):
    print(("  [ok]    " if cond else "  [FALLA] ") + que
          + ("\n           -> " + detalle if detalle else ""))
    if not cond:
        fallos.append(que)


def q(con, s, p=None):
    cur = con.cursor()
    cur.execute(s, p)
    r = cur.fetchall()
    con.rollback()
    return r


# Cada comprobacion estructural: (etiqueta, sql que devuelve una sola columna 'v')
CLS = ("select count(*)::text as v from pg_class c "
       "join pg_namespace ns on ns.oid=c.relnamespace where ns.nspname='public' ")
ESTRUCTURA = [
    ("tablas en public",              CLS + "and c.relkind='r'"),
    ("secuencias en public",          CLS + "and c.relkind='S'"),
    ("indices en public",             CLS + "and c.relkind='i'"),
    ("indices invalidos",             "select count(*)::text as v from pg_index i "
                                      "join pg_class c on c.oid=i.indexrelid "
                                      "join pg_namespace n on n.oid=c.relnamespace "
                                      "where n.nspname='public' and not i.indisvalid"),
    ("constraints en public",         "select count(*)::text as v from pg_constraint co "
                                      "join pg_class c on c.oid=co.conrelid "
                                      "join pg_namespace n on n.oid=c.relnamespace "
                                      "where n.nspname='public'"),
    ("politicas en public",           "select count(*)::text as v from pg_policies "
                                      "where schemaname='public'"),
    ("tablas con RLS",                CLS + "and c.relkind='r' and c.relrowsecurity"),
    ("tablas con FORCE RLS",          CLS + "and c.relkind='r' and c.relforcerowsecurity"),
    ("dueños de las tablas",          "select string_agg(distinct pg_get_userbyid(c.relowner), ',') as v "
                                      "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                                      "where n.nspname='public' and c.relkind='r'"),
    ("tablas en asistente",           "select count(*)::text as v from pg_class c "
                                      "join pg_namespace n on n.oid=c.relnamespace "
                                      "where n.nspname='asistente' and c.relkind='r'"),
    ("politicas en asistente",        "select count(*)::text as v from pg_policies "
                                      "where schemaname='asistente'"),
    ("funciones job* del scheduler",  "select count(*)::text as v from pg_proc p "
                                      "join pg_namespace n on n.oid=p.pronamespace "
                                      "where n.nspname='asistente' and p.proname like 'job%'"),
    ("job* con search_path=pg_catalog", "select count(*)::text as v from pg_proc p "
                                      "join pg_namespace n on n.oid=p.pronamespace "
                                      "where n.nspname='asistente' and p.proname like 'job%' "
                                      "and p.proconfig::text like '%pg_catalog%'"),
    ("md5 de los 10 cuerpos job*",    "select md5(string_agg(p.prosrc,'' order by p.proname)) as v "
                                      "from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                                      "where n.nspname='asistente' and p.proname like 'job%'"),
    ("GRANT a crm_user en public",    "select count(*)::text as v from information_schema.role_table_grants "
                                      "where grantee='crm_user' and table_schema='public'"),
    ("ACL de job_claim",              "select coalesce(p.proacl::text,'(nulo)') as v from pg_proc p "
                                      "join pg_namespace n on n.oid=p.pronamespace "
                                      "where n.nspname='asistente' and p.proname='job_claim'"),
    ("roles del proyecto presentes",  "select count(*)::text as v from pg_roles where rolname = any("
                                      "array['crm_user','crm_owner','crm_migrator','motor_user',"
                                      "'app_backend','asistente_owner','job_executor',"
                                      "'scheduler_coordinator','monitor_ro'])"),
    ("membresia crm_migrator->crm_owner", "select count(*)::text as v from pg_auth_members m "
                                      "join pg_roles r on r.oid=m.member join pg_roles g on g.oid=m.roleid "
                                      "where r.rolname='crm_migrator' and g.rolname='crm_owner'"),
    ("crm_migrator con SET role",     "select count(*)::text as v from pg_db_role_setting s "
                                      "join pg_roles r on r.oid=s.setrole "
                                      "where r.rolname='crm_migrator' and s.setconfig::text like '%role=crm_owner%'"),
    ("esquema de pgcrypto",           "select ns.nspname as v from pg_extension e "
                                      "join pg_namespace ns on ns.oid=e.extnamespace "
                                      "where e.extname='pgcrypto'"),
    ("existe el esquema extensions",  "select (to_regnamespace('extensions') is not null)::text as v"),
    ("extensions.digest resuelve",    "select (to_regprocedure('extensions.digest(text,text)') "
                                      "is not null)::text as v"),
    ("extensions.gen_random_bytes",   "select (to_regprocedure('extensions.gen_random_bytes(integer)') "
                                      "is not null)::text as v"),
    ("asistente_owner USAGE en extensions",
                                      "select has_schema_privilege('asistente_owner','extensions','usage')::text as v"),
    ("pg_trgm y vector en public",    "select string_agg(e.extname||'@'||ns.nspname, ',' order by e.extname) as v "
                                      "from pg_extension e join pg_namespace ns on ns.oid=e.extnamespace "
                                      "where e.extname in ('pg_trgm','vector')"),
]


def estructural(repl, prod):
    print("\n" + "=" * 78)
    print("  VALIDACION ESTRUCTURAL" + ("  (replica vs produccion)" if prod else "  (solo replica)"))
    print("=" * 78)
    iguales = 0
    for etiqueta, sql in ESTRUCTURA:
        b = q(repl, sql)[0]["v"]
        if prod is None:
            print(f"    [dato]  {etiqueta:38} {str(b)[:52]}")
            continue
        a = q(prod, sql)[0]["v"]
        ok = (a == b)
        iguales += ok
        if ok:
            print(f"    [=]     {etiqueta:38} {str(a)[:52]}")
        else:
            afirmar(False, etiqueta, f"produccion={a}   replica={b}")
    if prod is not None:
        print(f"\n    {iguales} de {len(ESTRUCTURA)} identicos")


def funcional(repl):
    print("\n" + "=" * 78)
    print("  VALIDACION FUNCIONAL DEL SCHEDULER  (la prueba que de verdad decide)")
    print("=" * 78)
    repl.autocommit = True
    cur = repl.cursor()

    f = q(repl, """select t.organization_id::text as org, t.config_version as v
                     from asistente.tenant_config t
                     join asistente.tenant_config_historial h
                       on h.organization_id=t.organization_id
                      and h.config_version=t.config_version
                     join public.organization o on o.id=t.organization_id
                    limit 1""")
    if not f:
        afirmar(False, "hay una organizacion con config en el historial")
        return
    org, ver = f[0]["org"], f[0]["v"]
    print(f"    organizacion de prueba: {org}  (config_version {ver})")

    cur.execute("""insert into asistente.job_catalogo
                     (code, descripcion, anchor, intervalo, lease_duracion,
                      max_intentos, backoffs, max_claims_por_tick,
                      presupuesto_tick, habilitado)
                   values ('verif_restore','Verificacion de restauracion',
                           date_trunc('second', now()), '00:05:00','00:05:00',
                           4, array['00:01:00','00:05:00','00:15:00']::interval[],
                           500,'00:00:45', true)
                   on conflict (code) do nothing""")
    cur.execute("""insert into asistente.job_schedule_state
                     (job_code, organization_id, next_run_at)
                   values ('verif_restore', %s,
                           date_trunc('second', now() - interval '1 minute'))
                   on conflict (job_code, organization_id) do update
                     set next_run_at = excluded.next_run_at,
                         current_run_id=null, current_slot=null,
                         lease_token=null, lease_until=null
                   returning next_run_at""", (org,))
    slot = cur.fetchone()["next_run_at"]
    print(f"    datos de prueba sembrados (solo en la replica). slot={slot}")

    turno = None
    try:
        cur.execute("select * from asistente.job_claim(%s,%s,%s,%s,%s)",
                    ("verif_restore", org, slot, "verificador",
                     json.dumps({"verificacion": True})))
        filas = cur.fetchall()
        turno = filas[0] if filas else None
        afirmar(turno is not None, "job_claim() reclama un turno",
                "devolvio 0 filas" if turno is None else "")
    except Exception as e:
        afirmar(False, "job_claim() reclama un turno",
                f"{type(e).__name__}: {str(e).splitlines()[0][:120]}")

    if turno:
        cap, chash = turno["capability"], turno["config_hash"]
        print(f"           run_id={turno['run_id']}  intento #{turno['attempt_number']}")
        afirmar(len(cap) == 64 and all(x in "0123456789abcdef" for x in cap),
                "capability de 64 hex (gen_random_bytes(32) resolvio)", f"largo={len(cap)}")
        afirmar(len(chash) == 64, "config_hash de 64 hex (digest sha256 resolvio)")

        ctx = None
        try:
            cur.execute("select * from asistente.job_contexto(%s,%s)", (turno["run_id"], cap))
            fl = cur.fetchall()
            ctx = dict(fl[0]) if fl else None
            afirmar(ctx is not None, "job_contexto() devuelve el turno completo")
        except Exception as e:
            afirmar(False, "job_contexto() devuelve el turno completo",
                    f"{type(e).__name__}: {str(e).splitlines()[0][:120]}")
        if ctx:
            afirmar(ctx["config_hash"] == chash,
                    "el config_hash del contexto coincide con el del claim",
                    f"claim={chash[:16]} contexto={str(ctx['config_hash'])[:16]}")

        try:
            cur.execute("select asistente.job_heartbeat(%s,%s) as h", (turno["attempt_id"], cap))
            afirmar(cur.fetchone()["h"] is not None, "job_heartbeat() renueva el lease")
        except Exception as e:
            afirmar(False, "job_heartbeat() renueva el lease",
                    f"{type(e).__name__}: {str(e).splitlines()[0][:120]}")

        try:
            cur.execute("select asistente.job_finalize(%s,%s,%s,%s) as f",
                        (turno["attempt_id"], cap, "succeeded", None))
            fin = cur.fetchone()["f"]
            afirmar(fin == "succeeded", "job_finalize() cierra el intento", f"desenlace={fin}")
        except Exception as e:
            afirmar(False, "job_finalize() cierra el intento",
                    f"{type(e).__name__}: {str(e).splitlines()[0][:120]}")

        r = q(repl, "select estado from asistente.job_run where id=%s", (turno["run_id"],))
        afirmar(bool(r) and r[0]["estado"] == "succeeded",
                "estado final de job_run = 'succeeded'", str(r[0]["estado"]) if r else "no existe")
        r = q(repl, "select outcome, completed_at is not null as c "
                    "from asistente.job_attempt where id=%s", (turno["attempt_id"],))
        afirmar(bool(r) and r[0]["outcome"] == "succeeded" and r[0]["c"],
                "job_attempt con outcome 'succeeded' y completed_at")
        r = q(repl, "select count(*) as n from asistente.job_run_event where run_id=%s",
              (turno["run_id"],))
        afirmar(r[0]["n"] >= 3, f"job_run_event registro el recorrido ({r[0]['n']} eventos)")

    print("\n    --- controles secundarios (NO prueban el scheduler: no llaman a digest) ---")
    for f_ in ("job_salud()", "jobs_vencidos()"):
        try:
            cur.execute(f"select * from asistente.{f_}")
            print(f"    [ok]    {f_} responde ({len(cur.fetchall())} fila(s))")
        except Exception as e:
            afirmar(False, f"{f_} responde", f"{type(e).__name__}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--puerto", type=int, required=True)
    ap.add_argument("--base", default="postgres")
    ap.add_argument("--usuario", default="postgres")
    ap.add_argument("--clave", default="test")
    ap.add_argument("--sin-comparar", action="store_true",
                    help="no compara contra produccion (no se conecta a ella)")
    a = ap.parse_args()

    repl = psycopg.connect(host=a.host, port=a.puerto, dbname=a.base,
                           user=a.usuario, password=a.clave, sslmode="disable",
                           connect_timeout=20, row_factory=dict_row)
    prod = None
    if not a.sin_comparar:
        from dotenv import load_dotenv
        load_dotenv(str(RAIZ / ".env"), override=False)
        from nucleo.persistencia.conexion import dsn
        prod = psycopg.connect(dsn(), connect_timeout=30, row_factory=dict_row)
        prod.read_only = True

    try:
        estructural(repl, prod)
        funcional(repl)
    finally:
        repl.close()
        if prod:
            prod.close()

    print("\n" + "=" * 78)
    print(f"  {len(fallos)} falla(s)")
    for f_ in fallos:
        print("    - " + f_)
    print("=" * 78)
    raise SystemExit(1 if fallos else 0)


if __name__ == "__main__":
    main()
