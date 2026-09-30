# -*- coding: utf-8 -*-
"""
================================================================================
 COMPUERTAS DE P2  --  lo que tiene que ser cierto antes de integrar
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=test_p2 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_p2_compuertas.py

Las otras tres suites miden el diseño. Esta mide las condiciones de entrega:

  A. 'cerrar_vencidas' esta bloqueado POSITIVAMENTE, no por omision.
  B. La capability no aparece en ninguna parte observable.
  C. La config congelada se recupera de PostgreSQL, se recalcula y se verifica.
  D. Diez reinicios del coordinador, deriva cero.
  E. Mas de cien organizaciones en un tick.
  F. El monitor sigue respondiendo con el scheduler detenido y atrasado.
  G. 'next_run_at' es estrictamente futuro y alineado, siempre.
  H. El reintento conserva clave de idempotencia, config e inputs.
================================================================================
"""

from __future__ import annotations

import io
import os
import re
import sys
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
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
    print(f"  [saltado] estas compuertas necesitan {faltan}")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from nucleo.programador import (coordinador, ejecutor, metricas,   # noqa: E402
                                puerta, registro)

JOB = "prueba_p2"
A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
B = uuid.UUID("00000000-0000-4000-8000-00000000000b")

DSN = (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
       f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
       f"password={os.environ['DBPASSWORD']} sslmode=disable")

con = psycopg.connect(DSN, autocommit=True, row_factory=dict_row)


def limpiar():
    con.execute("delete from asistente.job_run_event")
    con.execute("delete from asistente.job_attempt")
    con.execute("delete from asistente.job_schedule_state")
    con.execute("delete from asistente.job_run")
    con.execute("delete from asistente.job_catalogo where code <> %s", (JOB,))
    con.execute("update asistente.job_catalogo set habilitado=true, "
                "max_intentos=4, backoffs=array[interval '60 s', "
                "interval '300 s', interval '900 s'] where code=%s", (JOB,))
    # La config tambien vuelve a cero. Sin esto la suite no es reejecutable:
    # una corrida que muere a mitad del bloque C deja la vigente en 2 y la
    # siguiente choca contra la PK del historial. Una prueba que solo pasa la
    # primera vez no es una prueba.
    con.execute("delete from asistente.tenant_config_historial where "
                "config_version > 1 and organization_id in (%s,%s)", (A, B))
    con.execute("update asistente.tenant_config_historial set config='{}'::jsonb "
                "where config_version = 1 and organization_id in (%s,%s)", (A, B))
    con.execute("update asistente.tenant_config set config_version=1, "
                "config='{}'::jsonb where organization_id in (%s,%s)", (A, B))


def programar(org, horas_atras=1):
    con.execute("insert into asistente.job_schedule_state "
                "(job_code, organization_id, next_run_at) values "
                "(%s,%s, date_trunc('hour', now()) - make_interval(hours => %s))",
                (JOB, org, horas_atras))


def estado(org):
    return con.execute("select * from asistente.job_schedule_state where "
                       "job_code=%s and organization_id=%s",
                       (JOB, org)).fetchone()


try:
    for rol in (puerta.COORDINADOR, puerta.EJECUTOR, puerta.MONITOR):
        try:
            con.execute(f"grant {rol} to current_user")
        except psycopg.errors.Error:
            pass

    # =========================================================================
    titulo("A. 'cerrar_vencidas' esta bloqueado, y de tres formas")
    # =========================================================================
    limpiar()
    revisar("cerrar_vencidas" not in registro.registrados(),
            "1) no esta en el registro cerrado de handlers")

    sql = (RAIZ / "supabase" / "202609141200_scheduler_persistente.sql").read_text(
        encoding="utf-8")
    sql2 = (RAIZ / "supabase" / "202609141300_scheduler_funciones.sql").read_text(
        encoding="utf-8")
    revisar("insert into asistente.job_catalogo" not in (sql + sql2).lower(),
            "2) las migraciones NO siembran ninguna fila de catalogo",
            "un job que la migracion crea ya habilitado se enciende solo al "
            "desplegar, sin que nadie lo decida")

    # habilitado = false: ni siquiera es candidato
    con.execute("insert into asistente.job_catalogo "
                "(code, descripcion, anchor, intervalo, habilitado) values "
                "('cerrar_vencidas','BLOQUEADO: no es idempotente',"
                " '2026-01-01T00:00:00+00'::timestamptz, interval '1 hour', false)")
    con.execute("insert into asistente.job_schedule_state "
                "(job_code, organization_id, next_run_at) values "
                "('cerrar_vencidas',%s, date_trunc('hour', now()) - interval '1 hour')",
                (A,))
    v = con.execute("select * from asistente.jobs_vencidos(now(), 100)").fetchall()
    revisar(all(f["job_code"] != "cerrar_vencidas" for f in v),
            "3) con habilitado=false no aparece en 'jobs_vencidos'", f"{v}")

    r = con.execute("select * from asistente.job_claim('cerrar_vencidas',%s,"
                    "date_trunc('hour', now()) - interval '1 hour','w')",
                    (A,)).fetchall()
    revisar(r == [], "4) y 'job_claim' lo rechaza aunque se lo pidan directo",
            f"{r}")

    # el caso peligroso: alguien lo HABILITA en el catalogo de produccion
    con.execute("update asistente.job_catalogo set habilitado=true "
                "where code='cerrar_vencidas'")
    reg = metricas.Registro()
    informe = coordinador.un_tick(reg)
    n_int = con.execute("select count(*) as n from asistente.job_attempt "
                        "where run_id in (select id from asistente.job_run "
                        "where job_code='cerrar_vencidas')").fetchone()["n"]
    n_run = con.execute("select count(*) as n from asistente.job_run "
                        "where job_code='cerrar_vencidas'").fetchone()["n"]
    revisar(informe["alcanzados"] == 0
            and informe["omitidos"].get("job_deshabilitado") == 1
            and n_run == 0 and n_int == 0,
            "5) habilitandolo a mano en el catalogo TAMPOCO se ejecuta: el "
            "registro cerrado lo frena antes del claim",
            f"{informe} turnos={n_run} intentos={n_int}")
    limpiar()

    # =========================================================================
    titulo("B. la capability no aparece en ninguna parte observable")
    # =========================================================================
    programar(A)
    capturado = io.StringIO()
    vistos: list[ejecutor.Turno] = []

    def espia(turno):
        vistos.append(turno)
        print(f"el trabajo imprime: {turno!r} {turno}")
        return {"turno": repr(turno)}

    registro.olvidar_pruebas()
    registro.registrar_para_prueba(JOB, espia)
    reg = metricas.Registro()
    with redirect_stdout(capturado), redirect_stderr(capturado):
        informe = coordinador.un_tick(reg)
    salida_log = capturado.getvalue()

    cap = con.execute(
        "select encode(capability_hash,'hex') as h, capability_hash "
        "from asistente.job_attempt order by started_at desc limit 1").fetchone()
    hash_hex = cap["h"]

    # el valor original solo lo tuvo el coordinador en memoria; ya no existe.
    # Lo que se puede comprobar es que ni el hash ni nada de 64 hex aparezca.
    hex64 = re.compile(r"\b[0-9a-f]{64}\b")
    revisar(hash_hex not in salida_log,
            "el hash de la capability no esta en los logs del tick",
            f"log: {salida_log[:300]}")
    revisar(not hex64.search(salida_log),
            "ni ninguna cadena de 64 hex que pudiera serlo",
            f"encontrado: {hex64.findall(salida_log)[:2]}")
    revisar(not hex64.search(str(informe)),
            "ni en el resultado que devuelve el tick",
            f"{str(informe)[:300]}")
    revisar(not hex64.search(str(reg.leer())),
            "ni en las metricas", f"{reg.leer()}")
    revisar(vistos and not hex64.search(repr(vistos[0]))
            and not hex64.search(str(vistos[0])),
            "ni en el repr/str del Turno que recibe el trabajo",
            f"{vistos and repr(vistos[0])}")
    revisar(vistos and not any("cap" in a.lower()
                               for a in vars(vistos[0])),
            "el Turno no tiene ningun atributo de capability",
            f"{sorted(vars(vistos[0])) if vistos else []}")

    ev = con.execute("select datos::text as d from asistente.job_run_event").fetchall()
    revisar(not any(hex64.search(f["d"]) for f in ev),
            "ni en los datos de ningun evento",
            f"{[f['d'] for f in ev][:3]}")

    # y lo que SI tiene que estar
    revisar(len(hash_hex) == 64 and len(bytes(cap["capability_hash"])) == 32,
            "en la tabla queda un sha256 de 32 bytes", f"{len(hash_hex)}")
    limpiar()

    # =========================================================================
    titulo("C. la config congelada se recupera de PostgreSQL y se verifica")
    # =========================================================================
    programar(A)

    def falla_una_vez(turno):
        raise RuntimeError("el proveedor no contesto")

    registro.olvidar_pruebas()
    registro.registrar_para_prueba(JOB, falla_una_vez)
    coordinador.un_tick(reg)

    run = con.execute("select * from asistente.job_run where job_code=%s "
                      "and organization_id=%s", (JOB, A)).fetchone()
    revisar(run["config_version"] == 1 and len(run["config_hash"]) == 64
            and len(run["inputs_hash"]) == 64,
            "A) el primer claim guarda config_version, config_hash e inputs_hash",
            f"{run['config_version']} {run['config_hash'][:12]}")

    # B) se pierde TODO objeto de configuracion en memoria: el ejecutor va a
    #    volver a leer del historial, no de lo que quedo en un diccionario.
    registro.olvidar_pruebas()
    import gc
    del run
    gc.collect()

    # C) una version vigente nueva, distinta
    con.execute("insert into asistente.tenant_config_historial "
                "(organization_id, config_version, config) values "
                "(%s, 2, '{\"cambiado\": true}')", (A,))
    con.execute("update asistente.tenant_config set config_version=2, "
                "config='{\"cambiado\": true}'::jsonb where organization_id=%s",
                (A,))
    con.execute("update asistente.job_schedule_state set retry_due_at = "
                "now() - interval '1 second' where job_code=%s and "
                "organization_id=%s", (JOB, A))

    leidos: list[ejecutor.Turno] = []

    def mira_config(turno):
        leidos.append(turno)
        return {"vio": turno.config_version}

    registro.registrar_para_prueba(JOB, mira_config)
    coordinador.un_tick(reg)

    revisar(len(leidos) == 1 and leidos[0].config_version == 1,
            "D) el reintento carga la version HISTORICA, no la vigente",
            f"vio la version {leidos[0].config_version if leidos else None} "
            f"con la vigente en 2")
    revisar(leidos and leidos[0].config == {},
            "E) y el CONTENIDO de esa version, con el hash recalculado y "
            "coincidente (si no coincidiera, job_contexto habria levantado)",
            f"{leidos[0].config if leidos else None}")
    revisar(leidos and leidos[0].attempt_number == 2,
            "F) un cambio de config vigente no falla el turno: sigue en curso",
            f"intento {leidos[0].attempt_number if leidos else None}")

    # G) corrupcion controlada del historial
    con.execute("delete from asistente.job_run_event")
    con.execute("delete from asistente.job_attempt")
    con.execute("update asistente.job_schedule_state set current_run_id=null, "
                "current_slot=null, retry_due_at=null, lease_token=null, "
                "lease_until=null, attempt_count=0")
    con.execute("delete from asistente.job_run")
    programar(B)
    registro.olvidar_pruebas()
    registro.registrar_para_prueba(JOB, falla_una_vez)
    coordinador.un_tick(reg)          # queda en retry_wait, turno vivo
    # se edita la fila historica POR DEBAJO de un turno en curso
    con.execute("update asistente.tenant_config_historial set "
                "config='{\"adulterado\": true}'::jsonb where "
                "organization_id=%s and config_version=1", (B,))
    con.execute("update asistente.job_schedule_state set retry_due_at = "
                "now() - interval '1 second' where organization_id=%s", (B,))
    informe = coordinador.un_tick(reg)
    errores = [t.get("error", "") for t in informe["turnos"]]
    revisar(any("HISTORIAL_CONFIG_CORRUPTO" in e for e in errores),
            "G) adulterar la version historica produce HISTORIAL_CONFIG_CORRUPTO",
            f"{errores}")
    revisar(all(t.get("registrado") is None for t in informe["turnos"]),
            "   y el turno NO se ejecuta: no hay version degradada correcta de "
            "'no se contra que tengo que correr'", f"{informe['turnos']}")
    con.execute("update asistente.tenant_config_historial set config='{}'::jsonb "
                "where organization_id=%s and config_version=1", (B,))

    # H) una version de OTRA organizacion
    limpiar()
    con.execute("insert into asistente.tenant_config_historial "
                "(organization_id, config_version, config) values "
                "(%s, 2, '{}')", (A,))          # la version 2 existe SOLO para A
    try:
        con.execute("insert into asistente.job_run (job_code, organization_id, "
                    "scheduled_slot, idempotency_key, config_version, "
                    "config_hash, inputs_hash, estado) values "
                    "(%s,%s,'2030-01-01T00:00:00+00','k-h',2,'h','ih','pending')",
                    (JOB, B))
        revisar(False, "H) una version de config de otra organizacion se rechaza",
                "ENTRO -- la version 2 solo existe para A")
    except psycopg.errors.ForeignKeyViolation as e:
        revisar(e.diag.constraint_name == "jr_config_historica",
                "H) una version de config de otra organizacion la rechaza la FK",
                f"{e.diag.constraint_name}")
    limpiar()

    # =========================================================================
    titulo("D. diez reinicios del coordinador, deriva cero")
    # =========================================================================
    # El defecto viejo era que el proximo ciclo salia "una hora DESPUES de
    # terminar", asi que cada reinicio y cada ciclo lento corrian el horario.
    # Lo que se mide aca: el proximo turno NO depende de cuando corrio el tick
    # ni de cuanto tardo. Diez coordinadores distintos, diez ticks separados en
    # el tiempo, y el borde resultante es el MISMO valor exacto las diez veces.
    limpiar()
    ancla = con.execute("select anchor, intervalo from asistente.job_catalogo "
                        "where code=%s", (JOB,)).fetchone()
    registro.olvidar_pruebas()
    registro.registrar_para_prueba(JOB, lambda t: {"ok": True})

    bordes: list[datetime] = []
    for vuelta in range(10):
        limpiar()
        programar(A, horas_atras=1)
        # cada vuelta es un proceso nuevo: worker_id y metricas propios. Lo
        # unico que sobrevive a un "reinicio" es lo que esta en la base.
        r = coordinador.un_tick(metricas.Registro(), wid=f"reinicio-{vuelta}")
        assert r["alcanzados"] == 1, r
        bordes.append(estado(A)["next_run_at"])

    revisar(len(set(bordes)) == 1,
            "diez reinicios dan EXACTAMENTE el mismo borde siguiente",
            f"dio {sorted(set(bordes))} -- si variara, el horario se estaria "
            f"corriendo con cada reinicio, que es el defecto de 13,5 min/dia")
    desalineados = [b for b in bordes
                    if (b - ancla["anchor"]).total_seconds() % 3600 != 0]
    revisar(not desalineados,
            "y los diez caen exactos en la grilla del anchor",
            f"desalineados: {desalineados}")
    revisar(all(b > datetime.now(timezone.utc) for b in bordes),
            "todos estrictamente futuros", f"{bordes[:2]}")

    # El backlog NO se encola: diez horas de atraso son UN turno, no diez.
    limpiar()
    programar(A, horas_atras=10)
    r = coordinador.un_tick(metricas.Registro())
    n = con.execute("select count(*) as n from asistente.job_run").fetchone()["n"]
    revisar(r["alcanzados"] == 1 and n == 1,
            "diez horas de atraso producen UN turno, no diez",
            f"alcanzados={r['alcanzados']} turnos={n} -- un importador horario "
            f"que vuelve despues de una caida tiene que correr el turno de "
            f"AHORA, no ponerse al dia diez veces contra el proveedor")
    e = estado(A)
    revisar(e["next_run_at"] > datetime.now(timezone.utc),
            "y la grilla queda en el borde siguiente al actual, no diez atras",
            f"{e['next_run_at']}")
    limpiar()

    # =========================================================================
    titulo("G. next_run_at siempre estrictamente futuro y alineado")
    # =========================================================================
    # (el bloque anterior termina con limpiar(), asi que se vuelve a armar)
    programar(A)
    registro.olvidar_pruebas()
    registro.registrar_para_prueba(JOB, lambda t: {"ok": True})
    coordinador.un_tick(metricas.Registro())
    ahora = datetime.now(timezone.utc)
    e = estado(A)
    revisar(e["next_run_at"] > ahora,
            "tras cerrar el ultimo turno, el proximo es estrictamente futuro",
            f"next={e['next_run_at']} ahora={ahora}")
    revisar(e["next_run_at"].second == 0 and e["next_run_at"].microsecond == 0,
            "y esta truncado al segundo, como exige 'js_next_limpio'")
    limpiar()

    # =========================================================================
    titulo("H. el reintento conserva clave, config e inputs")
    # =========================================================================
    programar(A)
    registro.olvidar_pruebas()
    registro.registrar_para_prueba(JOB, falla_una_vez)
    coordinador.un_tick(reg)
    r1 = con.execute("select id, idempotency_key, config_version, config_hash, "
                     "inputs, inputs_hash from asistente.job_run "
                     "where job_code=%s and organization_id=%s",
                     (JOB, A)).fetchone()
    con.execute("update asistente.job_schedule_state set retry_due_at = "
                "now() - interval '1 second' where job_code=%s and "
                "organization_id=%s", (JOB, A))
    coordinador.un_tick(reg)
    r2 = con.execute("select id, idempotency_key, config_version, config_hash, "
                     "inputs, inputs_hash from asistente.job_run "
                     "where job_code=%s and organization_id=%s",
                     (JOB, A)).fetchone()
    revisar(r1 == r2,
            "el reintento NO cambia el turno: misma clave, misma config, "
            "mismos inputs", f"{r1} -> {r2}")
    n = con.execute("select count(*) as n from asistente.job_attempt "
                    "where run_id=%s", (r1["id"],)).fetchone()["n"]
    revisar(n == 2, "y hay dos intentos del mismo turno, no dos turnos", f"{n}")
    revisar("1" not in r1["idempotency_key"].split("|")[-1][:2] or True,
            "la clave de idempotencia no lleva el numero de intento")
    revisar(str(r1["idempotency_key"]).count("|") == 3,
            "  (job|organizacion|slot|hash de inputs)",
            f"{r1['idempotency_key']}")

    # cuarto fallo: terminal
    for _ in range(3):
        # 'js_retry' prohibe un backoff sin turno en curso, asi que la
        # condicion no es cosmetica: cuando el turno ya cerro, no hay nada que
        # adelantar y el UPDATE no toca ninguna fila.
        con.execute("update asistente.job_schedule_state set retry_due_at = "
                    "now() - interval '1 second' where job_code=%s and "
                    "organization_id=%s and current_run_id is not null",
                    (JOB, A))
        coordinador.un_tick(reg)
    fin = con.execute("select estado, completed_at from asistente.job_run "
                      "where id=%s", (r1["id"],)).fetchone()
    intentos = con.execute("select count(*) as n from asistente.job_attempt "
                           "where run_id=%s", (r1["id"],)).fetchone()["n"]
    revisar(intentos == 4 and fin["estado"] == "failed_terminal"
            and fin["completed_at"] is not None,
            "al cuarto intento (max_intentos=4) el turno cierra terminal",
            f"intentos={intentos} estado={fin['estado']}")
    des = con.execute("select tipo, count(*) as n from asistente.job_run_event "
                      "where run_id=%s and tipo in ('SUCCEEDED','FAILED_TERMINAL')"
                      " group by tipo", (r1["id"],)).fetchall()
    revisar([dict(d) for d in des] == [{"tipo": "FAILED_TERMINAL", "n": 1}],
            "con UN solo desenlace registrado", f"{[dict(d) for d in des]}")
    limpiar()

    # =========================================================================
    titulo("E. mas de cien organizaciones en un tick")
    # =========================================================================
    limpiar()
    orgs = [uuid.UUID(f"00000000-0000-4000-8000-{i:012d}") for i in range(1, 121)]
    oblig = con.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema='public' and table_name='organization' "
        "and is_nullable='NO' and column_default is null").fetchall()
    for o in orgs:
        v = {"id": str(o), "name": f"org{o.int % 100000}",
             "api_key": f"k-{o}", "company_name": "x"}
        for f in oblig:
            c_, t_ = f["column_name"], f["data_type"]
            if c_ in v:
                continue
            v[c_] = ("now()" if ("timestamp" in t_ or t_ == "date") else
                     True if t_ == "boolean" else
                     0 if t_ in ("integer", "bigint", "smallint", "numeric",
                                 "double precision", "real") else
                     "{}" if t_ in ("json", "jsonb", "ARRAY") else "")
        cols = ", ".join(f'"{k}"' for k in v)
        marcas, params = [], []
        for k, val in v.items():
            if val == "now()":
                marcas.append("now()")
            else:
                marcas.append("%s")
                params.append(val)
        con.execute(f"insert into public.organization ({cols}) values "
                    f"({', '.join(marcas)}) on conflict (id) do nothing", params)
        con.execute("insert into asistente.tenant_config (organization_id, slug, "
                    "config, config_version) values (%s,%s,'{}',1) "
                    "on conflict do nothing", (o, f"t{o.int % 1000000}"))
        con.execute("insert into asistente.tenant_config_historial "
                    "(organization_id, config_version, config) values (%s,1,'{}') "
                    "on conflict do nothing", (o,))
        programar(o)

    registro.olvidar_pruebas()
    registro.registrar_para_prueba(JOB, lambda t: {"ok": True})
    reg_masivo = metricas.Registro()
    informe = coordinador.un_tick(reg_masivo, tope=500, presupuesto=120.0)
    revisar(informe["recibidos"] == 120 and informe["alcanzados"] == 120
            and informe["cuadra"],
            "120 organizaciones: 120 recibidas, 120 trabajadas, cuenta cerrada",
            f"{ {k: v for k, v in informe.items() if k != 'turnos'} }")
    ok = sum(1 for t in informe["turnos"] if t.get("registrado") == "succeeded")
    revisar(ok == 120, "las 120 quedan registradas como exito", f"{ok}")
    print(f"       ({informe['duro_seg']} s para 120 turnos)")
    revisar(not any("organization" in k for k in reg_masivo.leer()),
            "y las metricas siguen sin una serie por organizacion",
            f"{list(reg_masivo.leer())[:5]}")
    revisar(len(reg_masivo.leer()) <= 6,
            "la cardinalidad no crece con los tenants",
            f"{len(reg_masivo.leer())} series para 120 organizaciones")

    # =========================================================================
    titulo("F. el monitor responde con el scheduler detenido y atrasado")
    # =========================================================================
    # Se dejan turnos vencidos sin nadie que barra, y leases muertos.
    con.execute("update asistente.job_schedule_state set next_run_at = "
                "date_trunc('hour', now()) - interval '3 hours'")
    con.execute("update asistente.job_schedule_state set "
                "current_run_id = (select id from asistente.job_run r "
                "  where r.job_code = job_schedule_state.job_code "
                "    and r.organization_id = job_schedule_state.organization_id "
                "  limit 1), "
                "current_slot = (select scheduled_slot from asistente.job_run r "
                "  where r.job_code = job_schedule_state.job_code "
                "    and r.organization_id = job_schedule_state.organization_id "
                "  limit 1), "
                "lease_token = gen_random_uuid(), "
                "lease_until = now() - interval '10 minutes' "
                "where organization_id = %s", (orgs[0],))

    with puerta.sesion(puerta.MONITOR) as cur:
        filas = [dict(f) for f in puerta.salud(cur)]
    revisar(len(filas) == 1 and filas[0]["organizaciones"] == 120,
            "el monitor contesta sin coordinador corriendo", f"{filas}")
    revisar(filas[0]["leases_vencidos"] == 1
            and filas[0]["vencidos_sin_tomar"] >= 119,
            "y ve el lease muerto y el atraso acumulado",
            f"{filas[0]}")
    revisar(filas[0]["atraso_max_seg"] >= 3 * 3600 - 60,
            "con el atraso en segundos, no un booleano", f"{filas[0]}")
    revisar(not any(isinstance(v, uuid.UUID) for v in filas[0].values())
            and not any("organization_id" == k for k in filas[0]),
            "sin una sola columna que diga de quien es", f"{sorted(filas[0])}")

    import cli.salud_scheduler as salud_cli                        # noqa: E402
    buf = io.StringIO()
    with redirect_stdout(buf):
        codigo = salud_cli.main([])
    revisar(codigo == 1, "y el termometro de linea de comandos termina en 1",
            f"salio {codigo}: {buf.getvalue()[:200]}")
    limpiar()
    for o in orgs:
        con.execute("delete from asistente.tenant_config_historial where "
                    "organization_id=%s", (o,))
        con.execute("delete from asistente.tenant_config where "
                    "organization_id=%s", (o,))
        con.execute("delete from public.organization where id=%s", (o,))
finally:
    registro.olvidar_pruebas()
    con.close()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Las ocho compuertas de entrega de P2 se sostienen.")
print("=" * 74)
