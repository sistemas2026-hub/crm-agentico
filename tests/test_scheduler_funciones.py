# -*- coding: utf-8 -*-
"""
================================================================================
 LAS SEIS FUNCIONES DEL SCHEDULER  --  el ciclo, el fencing y los permisos
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=test_p2 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_scheduler_funciones.py

Por que existe
--------------
Las constraints ya prueban que un estado invalido no se puede ESCRIBIR. Esto
prueba lo otro: que la maquina que lo recorre llega a los estados que tiene que
llegar, y que un worker zombi no puede volver a meter la mano.

Lo que se mide, en orden:

  1. El ciclo feliz: vence, se reclama, late, termina, y la grilla avanza.
  2. La capability no queda en claro en ninguna parte.
  3. Un worker que perdio el lease no puede latir ni finalizar, ni siquiera
     con su capability correcta -- y por separado, medido solo, que lo que lo
     frena tambien incluye el fencing y no unicamente el cierre del intento.
  4. El backoff existe: entre el fallo y el reintento el turno NO vence.
  5. La config se congela: cambiarla a mitad de un turno no afecta al turno.
  6. El ultimo fallo reintentable se registra como terminal, una sola vez.
  7. Los permisos: cada rol puede exactamente lo suyo y no puede leer ni una
     fila de las tablas.
  8. 'job_salud' no devuelve ninguna columna que identifique a una empresa.

El tiempo no se espera, se simula: se empuja 'lease_until' al pasado con un
UPDATE directo, y a 'jobs_vencidos' se le pasa 'p_ahora'. Un test que duerme
minutos no se corre.
================================================================================
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
B = uuid.UUID("00000000-0000-4000-8000-00000000000b")
JOB = "importacion_tickets"

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


def dsn():
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        print(f"  [saltado] faltan {faltan}")
        raise SystemExit(0)
    return (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
            f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
            f"password={os.environ['DBPASSWORD']} sslmode=disable")


# -----------------------------------------------------------------------------
#  utilidades
# -----------------------------------------------------------------------------

def limpiar(con):
    with con.cursor() as cur:
        cur.execute("delete from asistente.job_run_event")
        cur.execute("delete from asistente.job_attempt")
        cur.execute("delete from asistente.job_schedule_state")
        cur.execute("delete from asistente.job_run")
        cur.execute("update asistente.job_catalogo set habilitado = true, "
                    "max_intentos = 4, "
                    "backoffs = array[interval '60 s', interval '300 s', "
                    "                 interval '900 s'] "
                    "where code = %s", (JOB,))
        # config vigente en version 1 para las dos organizaciones
        cur.execute("delete from asistente.tenant_config_historial "
                    "where organization_id in (%s,%s) and config_version > 1",
                    (A, B))
        cur.execute("update asistente.tenant_config set config_version = 1, "
                    "config = '{}'::jsonb where organization_id in (%s,%s)",
                    (A, B))
    con.commit()


def programar(con, org, vence_hace=timedelta(minutes=5)):
    """Deja el job de esa organizacion vencido desde hace un rato."""
    slot = alinear(datetime.now(timezone.utc) - vence_hace)
    with con.cursor() as cur:
        cur.execute("insert into asistente.job_schedule_state "
                    "(job_code, organization_id, next_run_at) values (%s,%s,%s)",
                    (JOB, org, slot))
    con.commit()
    return slot


def alinear(momento):
    """El slot de la grilla horaria anclada en 2026-01-01T00:00:00Z."""
    return momento.replace(minute=0, second=0, microsecond=0)


def estado(con, org):
    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from asistente.job_schedule_state "
                    "where job_code=%s and organization_id=%s", (JOB, org))
        return cur.fetchone()


def turno(con, run_id):
    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from asistente.job_run where id=%s", (run_id,))
        return cur.fetchone()


def vencidos(con, ahora=None, limite=100):
    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from asistente.jobs_vencidos(coalesce(%s, now()), %s)",
                    (ahora, limite))
        return cur.fetchall()


def reclamar(con, org, slot, worker="w1"):
    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from asistente.job_claim(%s,%s,%s,%s)",
                    (JOB, org, slot, worker))
        f = cur.fetchall()
    con.commit()
    return f[0] if f else None


def matar_lease(con, org):
    """Simula un worker que se murio: el lease queda vencido."""
    with con.cursor() as cur:
        cur.execute("update asistente.job_schedule_state "
                    "set lease_until = now() - interval '1 minute' "
                    "where job_code=%s and organization_id=%s", (JOB, org))
    con.commit()


con = psycopg.connect(dsn())
try:
    # =========================================================================
    titulo("el ciclo feliz")
    # =========================================================================
    limpiar(con)
    slot = programar(con, A)

    v = vencidos(con)
    revisar(len(v) == 1 and v[0]["organization_id"] == A
            and v[0]["motivo"] == "nuevo" and v[0]["slot"] == slot,
            "un job programado y vencido aparece una vez, como 'nuevo'",
            f"devolvio {v}")

    c = reclamar(con, A, slot)
    revisar(c is not None and c["attempt_number"] == 1
            and c["fencing_version"] == 1,
            "el primer claim abre el intento 1 con fencing 1",
            f"devolvio {c}")
    revisar(c and c["config_version"] == 1 and len(c["config_hash"]) == 64,
            "el claim devuelve la version de config congelada y su sha256",
            f"version={c and c['config_version']} hash={c and c['config_hash']}")

    e = estado(con, A)
    revisar(e["current_run_id"] == c["run_id"] and e["current_slot"] == slot
            and e["lease_until"] is not None and e["retry_due_at"] is None,
            "el estado queda apuntando al turno, con lease y sin backoff",
            f"{e}")

    revisar(vencidos(con) == [],
            "con el lease vivo, el job ya NO aparece como vencido",
            "un lease vivo que no oculta el turno es un turno que se reclama dos veces")

    # ---- la capability no se guarda -----------------------------------------
    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select capability_hash from asistente.job_attempt "
                    "where id=%s", (c["attempt_id"],))
        guardado = cur.fetchone()["capability_hash"]
        cur.execute("select ext.digest(%s,'sha256') as h", (c["capability"],))
        esperado = cur.fetchone()["h"]
    con.rollback()
    revisar(bytes(guardado) == bytes(esperado) and len(bytes(guardado)) == 32,
            "en la tabla queda el sha256 de la capability, no la capability")
    revisar(c["capability"].encode() != bytes(guardado)
            and len(c["capability"]) == 64,
            "la capability viaja en claro UNA vez, en la respuesta del claim")

    # ---- heartbeat ----------------------------------------------------------
    with con.cursor() as cur:
        cur.execute("select asistente.job_heartbeat(%s,%s)",
                    (c["attempt_id"], c["capability"]))
        h1 = cur.fetchone()[0]
    con.commit()
    revisar(h1 is not None and h1 > e["lease_until"] - timedelta(seconds=1),
            "el heartbeat con la capability correcta extiende el lease",
            f"antes={e['lease_until']} despues={h1}")

    with con.cursor() as cur:
        cur.execute("select asistente.job_heartbeat(%s,%s)",
                    (c["attempt_id"], "no-es-la-capability"))
        h2 = cur.fetchone()[0]
    con.commit()
    revisar(h2 is None, "con una capability equivocada, el heartbeat devuelve NULL")

    # ---- contexto -----------------------------------------------------------
    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from asistente.job_contexto(%s,%s)",
                    (c["run_id"], c["capability"]))
        ctx = cur.fetchone()
        cur.execute("select current_setting('app.current_tenant', true)")
        guc = cur.fetchone()["current_setting"]
    con.rollback()
    revisar(ctx is not None and ctx["organization_id"] == A and guc == str(A),
            "el contexto deja app.current_tenant en la organizacion del turno",
            f"devolvio {ctx}, el GUC quedo en {guc}")
    revisar(ctx and ctx["job_code"] == JOB and ctx["config_version"] == 1
            and ctx["config"] == {} and ctx["inputs"] == {}
            and ctx["attempt_id"] == c["attempt_id"],
            "y devuelve el turno entero leido de la base, no del claim",
            f"{ctx}")

    with con.cursor() as cur:
        cur.execute("select count(*) from asistente.job_contexto(%s,%s)",
                    (uuid.uuid4(), c["capability"]))
        n = cur.fetchone()[0]
    con.rollback()
    revisar(n == 0,
            "con un run_id que no es el del intento, no devuelve nada",
            "un ejecutor confundido de turno no puede pedir el contexto de otro")

    # ---- finalizar ----------------------------------------------------------
    with con.cursor() as cur:
        cur.execute("select asistente.job_finalize(%s,%s,'succeeded')",
                    (c["attempt_id"], c["capability"]))
        fin = cur.fetchone()[0]
    con.commit()
    revisar(fin == "succeeded", "finalizar con exito devuelve 'succeeded'",
            f"devolvio {fin}")

    r = turno(con, c["run_id"])
    e = estado(con, A)
    revisar(r["estado"] == "succeeded" and r["completed_at"] is not None,
            "el turno queda 'succeeded' con su completed_at")
    revisar(e["current_run_id"] is None and e["current_slot"] is None
            and e["lease_token"] is None and e["attempt_count"] == 0,
            "el estado queda limpio para el proximo turno", f"{e}")
    revisar(e["next_run_at"] > slot and e["next_run_at"].minute == 0
            and e["next_run_at"].second == 0,
            "la grilla avanza a un slot alineado posterior",
            f"slot={slot} next={e['next_run_at']}")
    revisar(e["last_successful_at"] is not None, "queda sellado el ultimo exito")

    # =========================================================================
    titulo("el worker zombi: fencing")
    # =========================================================================
    limpiar(con)
    slot = programar(con, A)
    viejo = reclamar(con, A, slot, worker="w-zombi")
    matar_lease(con, A)

    v = vencidos(con)
    revisar(len(v) == 1 and v[0]["motivo"] == "lease_vencido",
            "con el lease vencido el turno vuelve a vencer, como 'lease_vencido'",
            f"devolvio {v}")

    nuevo = reclamar(con, A, slot, worker="w-vivo")
    revisar(nuevo is not None and nuevo["run_id"] == viejo["run_id"]
            and nuevo["attempt_number"] == 2
            and nuevo["fencing_version"] > viejo["fencing_version"],
            "el rescate reclama el MISMO turno con el intento siguiente y mas fencing",
            f"viejo={viejo and (viejo['attempt_number'], viejo['fencing_version'])} "
            f"nuevo={nuevo and (nuevo['attempt_number'], nuevo['fencing_version'])}")

    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select outcome, completed_at from asistente.job_attempt "
                    "where id=%s", (viejo["attempt_id"],))
        za = cur.fetchone()
    con.rollback()
    revisar(za["outcome"] == "lease_lost" and za["completed_at"] is not None,
            "el intento abandonado queda cerrado como 'lease_lost'", f"{za}")

    with con.cursor() as cur:
        cur.execute("select asistente.job_heartbeat(%s,%s)",
                    (viejo["attempt_id"], viejo["capability"]))
        zh = cur.fetchone()[0]
        cur.execute("select asistente.job_finalize(%s,%s,'succeeded')",
                    (viejo["attempt_id"], viejo["capability"]))
        zf = cur.fetchone()[0]
    con.commit()
    revisar(zh is None, "el zombi no puede latir, aunque su capability sea la buena")
    revisar(zf is None, "y tampoco puede declarar exito sobre el turno que perdio",
            "si pudiera, un worker congelado 10 minutos marcaria como hecho un "
            "turno que otro esta ejecutando")

    r = turno(con, viejo["run_id"])
    revisar(r["estado"] == "running",
            "el turno sigue corriendo: la llegada tarde no lo movio", f"{r['estado']}")

    # ---- que es lo que REALMENTE lo frena ------------------------------------
    # Medido con una mutacion: quitando la comparacion de fencing de
    # 'job_intento_vigente', las dos comprobaciones de arriba SIGUEN en verde.
    # No las frena el fencing: las frena que el rescate cerro su intento y
    # 'outcome is null' deja de cumplirse. El fencing es una segunda guarda, y
    # una guarda de la que no se puede afirmar nada si no se la mide sola.
    #
    # Sola no se alcanza por la API: un rescate SIEMPRE cierra el intento
    # previo. Asi que se fabrica el estado a mano -- fencing adelantado con el
    # intento todavia abierto-- que es la forma que tendria una escritura
    # entrelazada.
    limpiar(con)
    slot = programar(con, A)
    solo = reclamar(con, A, slot, worker="w-solo")

    with con.cursor() as cur:
        cur.execute("update asistente.job_schedule_state "
                    "set fencing_version = fencing_version + 1 "
                    "where job_code=%s and organization_id=%s", (JOB, A))
    con.commit()
    with con.cursor() as cur:
        cur.execute("select asistente.job_heartbeat(%s,%s)",
                    (solo["attempt_id"], solo["capability"]))
        fh = cur.fetchone()[0]
        cur.execute("select asistente.job_finalize(%s,%s,'succeeded')",
                    (solo["attempt_id"], solo["capability"]))
        ff = cur.fetchone()[0]
    con.commit()
    revisar(fh is None and ff is None,
            "con el intento ABIERTO pero el fencing adelantado, no puede escribir",
            f"heartbeat={fh} finalize={ff} -- esta es la comprobacion que mide "
            f"el fencing y ninguna otra")

    with con.cursor() as cur:
        cur.execute("update asistente.job_schedule_state "
                    "set fencing_version = fencing_version - 1, "
                    "    lease_token = gen_random_uuid() "
                    "where job_code=%s and organization_id=%s", (JOB, A))
    con.commit()
    with con.cursor() as cur:
        cur.execute("select asistente.job_finalize(%s,%s,'succeeded')",
                    (solo["attempt_id"], solo["capability"]))
        ft = cur.fetchone()[0]
    con.commit()
    revisar(ft is None,
            "y con el fencing igual pero OTRO lease_token, tampoco",
            f"devolvio {ft}")

    # =========================================================================
    titulo("el backoff, y que la config se congela")
    # =========================================================================
    limpiar(con)
    slot = programar(con, A)
    c1 = reclamar(con, A, slot)

    with con.cursor() as cur:
        cur.execute("select asistente.job_finalize(%s,%s,'failed_retryable','ETIMEDOUT')",
                    (c1["attempt_id"], c1["capability"]))
        f1 = cur.fetchone()[0]
    con.commit()
    revisar(f1 == "failed_retryable", "un fallo reintentable se registra como tal")

    e = estado(con, A)
    r = turno(con, c1["run_id"])
    revisar(r["estado"] == "retry_wait", "el turno queda esperando reintento")
    revisar(e["current_run_id"] == c1["run_id"] and e["current_slot"] == slot,
            "el turno y su slot NO se pierden entre intentos",
            "limpiarlos convierte el reintento en un turno nuevo: se pierde la "
            "config congelada, el contador de intentos y el backoff entero")
    revisar(e["retry_due_at"] is not None
            and 55 <= (e["retry_due_at"] - datetime.now(timezone.utc)).total_seconds() <= 65,
            "el primer backoff son 60 segundos",
            f"faltan {e['retry_due_at'] and (e['retry_due_at'] - datetime.now(timezone.utc)).total_seconds()} s")
    revisar(e["lease_token"] is None,
            "y el lease se suelta mientras espera: nadie lo esta ejecutando")

    revisar(vencidos(con) == [],
            "DURANTE el backoff el turno no vence",
            "si venciera, el backoff no existiria -- se reintentaria en el acto")

    despues = datetime.now(timezone.utc) + timedelta(seconds=90)
    v = vencidos(con, ahora=despues)
    revisar(len(v) == 1 and v[0]["motivo"] == "reintento" and v[0]["slot"] == slot,
            "pasado el backoff vence como 'reintento', sobre el mismo slot",
            f"devolvio {v}")

    # ---- la config cambia a mitad de camino ---------------------------------
    with con.cursor() as cur:
        cur.execute("insert into asistente.tenant_config_historial "
                    "(organization_id, config_version, config) values (%s,2,'{\"x\":1}')",
                    (A,))
        cur.execute("update asistente.tenant_config set config_version=2, "
                    "config='{\"x\":1}'::jsonb where organization_id=%s", (A,))
        cur.execute("update asistente.job_schedule_state "
                    "set retry_due_at = now() - interval '1 second' "
                    "where job_code=%s and organization_id=%s", (JOB, A))
    con.commit()

    c2 = reclamar(con, A, slot)
    revisar(c2 is not None and c2["config_version"] == 1,
            "el reintento corre contra la config CONGELADA, no la vigente",
            f"la vigente es la 2; el reintento trajo la "
            f"{c2 and c2['config_version']} -- un turno que cambia de reglas a "
            f"mitad de camino no es reintentable, es otro turno")
    revisar(c2 is not None and c2["run_id"] == c1["run_id"]
            and c2["attempt_number"] == 2,
            "y es el mismo turno, intento 2")

    # =========================================================================
    titulo("el ultimo fallo reintentable es terminal")
    # =========================================================================
    limpiar(con)
    slot = programar(con, A)
    with con.cursor() as cur:
        cur.execute("update asistente.job_catalogo set max_intentos=2, "
                    "backoffs=array[interval '0 s'] where code=%s", (JOB,))
    con.commit()

    ca = reclamar(con, A, slot)
    with con.cursor() as cur:
        cur.execute("select asistente.job_finalize(%s,%s,'failed_retryable','E1')",
                    (ca["attempt_id"], ca["capability"]))
        pa = cur.fetchone()[0]
    con.commit()
    cb = reclamar(con, A, slot)
    with con.cursor() as cur:
        cur.execute("select asistente.job_finalize(%s,%s,'failed_retryable','E2')",
                    (cb["attempt_id"], cb["capability"]))
        pb = cur.fetchone()[0]
    con.commit()

    revisar(pa == "failed_retryable" and pb == "failed_terminal",
            "el intento 1 se registra reintentable y el 2 --el ultimo-- terminal",
            f"intento1={pa} intento2={pb}")

    r = turno(con, ca["run_id"])
    e = estado(con, A)
    revisar(r["estado"] == "failed_terminal" and r["completed_at"] is not None,
            "el turno cierra mal, con su completed_at")
    revisar(e["current_run_id"] is None and e["next_run_at"] > slot,
            "la grilla avanza igual: un turno que fallo no bloquea el siguiente",
            f"{e}")
    revisar(e["last_successful_at"] is None,
            "y no se sella un exito que no hubo")

    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select tipo, count(*) as n from asistente.job_run_event "
                    "where run_id=%s and tipo in ('SUCCEEDED','FAILED_TERMINAL') "
                    "group by tipo", (ca["run_id"],))
        des = {f["tipo"]: f["n"] for f in cur.fetchall()}
    con.rollback()
    revisar(des == {"FAILED_TERMINAL": 1},
            "y el turno tiene UN solo desenlace registrado", f"{des}")

    with con.cursor() as cur:
        cur.execute("update asistente.job_catalogo set max_intentos=4, "
                    "backoffs=array[interval '60 s', interval '300 s', "
                    "interval '900 s'] where code=%s", (JOB,))
    con.commit()

    # =========================================================================
    titulo("dos organizaciones no se pisan")
    # =========================================================================
    limpiar(con)
    slot_a = programar(con, A)
    slot_b = programar(con, B)
    ca = reclamar(con, A, slot_a)
    v = vencidos(con)
    revisar(len(v) == 1 and v[0]["organization_id"] == B,
            "reclamar el de A deja el de B intacto y vencido", f"{v}")
    eb = estado(con, B)
    revisar(eb["current_run_id"] is None and eb["lease_token"] is None,
            "el estado de B no se toco", f"{eb}")

    # =========================================================================
    titulo("ocho coordinadores a la vez, un solo claim")
    # =========================================================================
    # 'for update skip locked' es la afirmacion; esto es la medicion. Ocho
    # conexiones distintas llaman a job_claim sobre el MISMO turno en el mismo
    # instante. Si salieran dos claims, dos workers estarian ejecutando el
    # mismo barrido contra el mismo proveedor.
    limpiar(con)
    slot = programar(con, A)

    import threading

    ganadores: list[dict] = []
    errores: list[str] = []
    arranquen = threading.Barrier(8)

    def competir(n):
        try:
            c = psycopg.connect(dsn(), row_factory=dict_row)
            try:
                arranquen.wait(timeout=10)
                with c.cursor() as cur:
                    cur.execute("select * from asistente.job_claim(%s,%s,%s,%s)",
                                (JOB, A, slot, f"w{n}"))
                    f = cur.fetchall()
                c.commit()
                if f:
                    ganadores.append(f[0])
            finally:
                c.close()
        except BaseException as exc:                             # noqa: BLE001
            errores.append(type(exc).__name__)

    hilos = [threading.Thread(target=competir, args=(n,)) for n in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    # Medido con una mutacion: quitando el 'for update skip locked', siete de
    # las ocho mueren con UniqueViolation contra el UNIQUE del slot. O sea que
    # la garantia de "un solo turno" la da la CONSTRAINT, no el candado; lo que
    # aporta el candado es que la carrera se pierda en silencio en vez de a los
    # gritos. Las dos cosas hacen falta y no son la misma.
    revisar(not errores,
            "ninguna de las ocho llamadas reventó: la carrera se pierde limpia",
            f"{sorted(set(errores))}")
    revisar(len(ganadores) == 1,
            "exactamente UNO de los ocho se queda con el turno",
            f"se lo quedaron {len(ganadores)} -- dos claims son dos workers "
            f"ejecutando el mismo barrido contra el mismo proveedor")

    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select count(*) as n from asistente.job_attempt "
                    "where run_id in (select id from asistente.job_run "
                    "where job_code=%s and organization_id=%s)", (JOB, A))
        n_intentos = cur.fetchone()["n"]
        cur.execute("select count(*) as n from asistente.job_run "
                    "where job_code=%s and organization_id=%s", (JOB, A))
        n_turnos = cur.fetchone()["n"]
    con.rollback()
    revisar(n_turnos == 1 and n_intentos == 1,
            "y en la base quedo un turno con un intento, no ocho",
            f"turnos={n_turnos} intentos={n_intentos}")

    # =========================================================================
    titulo("los permisos: cada rol hace lo suyo y no lee ni una fila")
    # =========================================================================
    limpiar(con)
    slot = programar(con, A)

    try:
        with con.cursor() as cur:
            for rol in ("scheduler_coordinator", "job_executor", "monitor_ro"):
                cur.execute(f"grant {rol} to current_user")
        con.commit()
        hay_roles = True
    except psycopg.errors.Error as exc:
        con.rollback()
        hay_roles = False
        print(f"  [saltado] no se pudo asumir los roles de runtime: "
              f"{type(exc).__name__}")

    def como(rol, sql, params=None):
        """Corre 'sql' con el rol puesto. Devuelve (ok, nombre_del_error)."""
        with con.cursor() as cur:
            cur.execute(f"set local role {rol}")
            try:
                cur.execute(sql, params)
                try:
                    cur.fetchall()
                except psycopg.ProgrammingError:
                    pass
                con.rollback()
                return True, ""
            except psycopg.errors.Error as exc:
                con.rollback()
                return False, type(exc).__name__

    if hay_roles:
        ok, _ = como("scheduler_coordinator",
                     "select * from asistente.jobs_vencidos(now(), 10)")
        revisar(ok, "el coordinador puede preguntar que vence")

        ok, err = como("scheduler_coordinator",
                       "select * from asistente.job_claim(%s,%s,%s,'w')",
                       (JOB, A, slot))
        revisar(ok, "el coordinador puede reclamar", err)

        ok, err = como("scheduler_coordinator",
                       "select asistente.job_finalize(%s,'x','succeeded')",
                       (uuid.uuid4(),))
        revisar(not ok and err == "InsufficientPrivilege",
                "pero NO puede finalizar: el resultado no es suyo", err or "entro")

        for tabla in ("job_schedule_state", "job_run", "job_attempt",
                      "job_run_event"):
            ok, err = como("scheduler_coordinator",
                           f"select 1 from asistente.{tabla} limit 1")
            revisar(not ok and err == "InsufficientPrivilege",
                    f"el coordinador no puede leer asistente.{tabla}",
                    err or "leyo la tabla directamente")

        ok, err = como("job_executor",
                       "select asistente.job_heartbeat(%s,'x')", (uuid.uuid4(),))
        revisar(ok, "el ejecutor puede latir", err)
        ok, err = como("job_executor",
                       "select asistente.job_finalize(%s,'x','succeeded')",
                       (uuid.uuid4(),))
        revisar(ok, "el ejecutor puede finalizar", err)
        ok, err = como("job_executor",
                       "select * from asistente.job_claim(%s,%s,%s,'w')",
                       (JOB, A, slot))
        revisar(not ok and err == "InsufficientPrivilege",
                "pero NO puede reclamar: no elige que le toca", err or "entro")
        ok, err = como("job_executor", "select 1 from asistente.job_run limit 1")
        revisar(not ok and err == "InsufficientPrivilege",
                "ni leer los turnos", err or "leyo")

        ok, err = como("monitor_ro", "select * from asistente.job_salud(now())")
        revisar(ok, "el monitor puede ver los agregados", err)
        ok, err = como("monitor_ro",
                       "select 1 from asistente.job_schedule_state limit 1")
        revisar(not ok and err == "InsufficientPrivilege",
                "y no puede leer el estado fila por fila", err or "leyo")
        ok, err = como("monitor_ro",
                       "select * from asistente.jobs_vencidos(now(), 1)")
        revisar(not ok and err == "InsufficientPrivilege",
                "ni preguntar que vence", err or "entro")

    # =========================================================================
    titulo("las metricas no dicen de quien son")
    # =========================================================================
    with con.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from asistente.job_salud(now())")
        filas = cur.fetchall()
        columnas = [d.name for d in cur.description]
    con.rollback()
    revisar(not any("organization" in c or "org" == c for c in columnas),
            "job_salud no devuelve ninguna columna de organizacion",
            f"columnas: {columnas}")
    revisar(all(not isinstance(v, uuid.UUID)
                for f in filas for v in f.values()),
            "ni un UUID suelto que permita reidentificar",
            f"{filas}")
finally:
    con.close()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] El ciclo, el fencing, el congelamiento y los permisos se sostienen.")
print("=" * 74)
