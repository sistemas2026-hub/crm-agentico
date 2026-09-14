# -*- coding: utf-8 -*-
"""
================================================================================
 LAS CONSTRAINTS DEL SCHEDULER MUERDEN  --  no la logica de Python
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=test_p2 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_scheduler_constraints.py

Por que existe
--------------
Guardar 'organization_id' en las cuatro tablas no aisla nada por si solo: nada
impediria un intento de la empresa A colgando de un turno de la B, o un evento
que mezcle el run de una con el intento de la otra. Una politica RLS sobre una
columna incoherente es una politica que se aplica sobre el dato equivocado.

Lo que aisla son las FK compuestas. Y la unica forma de saber que funcionan es
intentar meter la combinacion cruzada y ver que PostgreSQL la rechaza.

Cada prueba de abajo INTENTA escribir algo invalido. Si entra, falla.
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

A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
B = uuid.UUID("00000000-0000-4000-8000-00000000000b")
JOB = "importacion_tickets"
SLOT_A = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
SLOT_B = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
def cap() -> bytes:
    """32 bytes distintos cada vez.

    El largo lo exige 'ja_cap_len'; que sean DISTINTOS lo exige 'ja_cap_unica'.
    Con una constante compartida, la segunda comprobacion de cada bloque se
    rechazaba por el hash repetido y enmascaraba lo que se queria medir.
    """
    return uuid.uuid4().bytes + uuid.uuid4().bytes

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


def dsn():
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        print(f"  [saltado] faltan {faltan}")
        raise SystemExit(0)
    return (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
            f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
            f"password={os.environ['DBPASSWORD']} sslmode=disable")


def rechaza(con, sql, params, que, esperado=""):
    """Intenta escribir algo invalido. Tiene que fallar por CONSTRAINT."""
    try:
        with con.cursor() as cur:
            cur.execute(sql, params)
        con.rollback()
        revisar(False, que, "ENTRO -- la constraint no existe o no cubre este caso")
    except psycopg.errors.Error as e:
        con.rollback()
        nombre = getattr(getattr(e, "diag", None), "constraint_name", "") or ""
        clase = type(e).__name__
        ok = esperado in nombre if esperado else True
        revisar(ok, que, f"rechazado por {clase}/{nombre or 'sin nombre'}"
                         f" (se esperaba {esperado})" if not ok else "")
        if ok:
            print(f"         ({clase} · {nombre or 'check'})")


def crear_run(con, org, slot, estado="running"):
    rid = uuid.uuid4()
    with con.cursor() as cur:
        cur.execute("""insert into asistente.job_run
            (id, job_code, organization_id, scheduled_slot, idempotency_key,
             config_version, config_hash, inputs, inputs_hash, estado, started_at)
            values (%s,%s,%s,%s,%s,1,'h','{}','ih',%s, now())""",
            (rid, JOB, org, slot, f"{JOB}|{org}|{slot.isoformat()}", estado))
    con.commit()
    return rid


def crear_intento(con, rid, org, n=1):
    aid = uuid.uuid4()
    with con.cursor() as cur:
        cur.execute("""insert into asistente.job_attempt
            (id, run_id, organization_id, attempt_number, lease_token,
             fencing_version, capability_hash, worker_id)
            values (%s,%s,%s,%s,%s,1,%s,'w1')""",
            (aid, rid, org, n, uuid.uuid4(), cap()))
    con.commit()
    return aid


con = psycopg.connect(dsn())
try:
    # limpieza de corridas anteriores
    with con.cursor() as cur:
        cur.execute("delete from asistente.job_run_event")
        cur.execute("delete from asistente.job_attempt")
        cur.execute("update asistente.job_schedule_state set current_run_id=null, "
                    "current_slot=null, retry_due_at=null, lease_token=null, "
                    "lease_until=null")
        cur.execute("delete from asistente.job_run")
    con.commit()

    run_a = crear_run(con, A, SLOT_A)
    run_b = crear_run(con, B, SLOT_B)
    att_a = crear_intento(con, run_a, A)

    print("=" * 74)
    print("  la organizacion no se puede cruzar")
    print("=" * 74)

    rechaza(con,
            """insert into asistente.job_attempt
               (run_id, organization_id, attempt_number, lease_token,
                fencing_version, capability_hash, worker_id)
               values (%s,%s,5,%s,1,%s,'w')""",
            (run_b, A, uuid.uuid4(), cap()),
            "un intento de la org A sobre un turno de la org B",
            "ja_run_misma_org")

    rechaza(con,
            """insert into asistente.job_run_event
               (run_id, organization_id, tipo) values (%s,%s,'STARTED')""",
            (run_a, B),
            "un evento de la org B sobre un turno de la org A",
            "jre_run_misma_org")

    rechaza(con,
            """insert into asistente.job_run_event
               (run_id, attempt_id, organization_id, tipo)
               values (%s,%s,%s,'STARTED')""",
            (run_b, att_a, B),
            "un evento que mezcla el turno de B con el intento de A",
            "jre_attempt_del_mismo_run")

    # El turno de A no puede colgar del historial de B. Se usa una version que
    # SOLO existe para B: la FK es (organization_id, config_version), asi que
    # con organization_id de A no la encuentra.
    with con.cursor() as cur:
        cur.execute("""insert into asistente.tenant_config_historial
                       (organization_id, config_version, config)
                       values (%s, 77, '{}') on conflict do nothing""", (str(B),))
    con.commit()
    rechaza(con,
            """insert into asistente.job_run
               (job_code, organization_id, scheduled_slot, idempotency_key,
                config_version, config_hash, inputs_hash, estado, completed_at)
               values (%s,%s,%s,'k-cruzada',77,'h','ih','succeeded', now())""",
            (JOB, A, datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)),
            "un turno de A que referencia una config que solo existe para B",
            "jr_config_historica")

    print()
    print("=" * 74)
    print("  la config historica")
    print("=" * 74)

    rechaza(con,
            """insert into asistente.job_run
               (job_code, organization_id, scheduled_slot, idempotency_key,
                config_version, config_hash, inputs_hash, estado, completed_at)
               values (%s,%s,%s,'k-inexistente',99,'h','ih','succeeded',now())""",
            (JOB, B, datetime(2026, 9, 14, 13, 0, tzinfo=timezone.utc)),
            "una version de config que no existe",
            "jr_config_historica")

    rechaza(con,
            "delete from asistente.tenant_config_historial "
            "where organization_id=%s and config_version=1",
            (A,),
            "borrar una version de config referenciada por un turno",
            "jr_config_historica")

    print()
    print("=" * 74)
    print("  estado y desenlace no se contradicen")
    print("=" * 74)

    rechaza(con,
            "update asistente.job_run set estado='succeeded' where id=%s",
            (run_a,),
            "un turno terminal sin completed_at",
            "jr_terminal_completo")

    rechaza(con,
            """insert into asistente.job_attempt
               (run_id, organization_id, attempt_number, lease_token,
                fencing_version, capability_hash, worker_id, outcome)
               values (%s,%s,9,%s,1,%s,'w','succeeded')""",
            (run_a, A, uuid.uuid4(), cap()),
            "un intento terminado sin completed_at",
            "ja_completo")

    rechaza(con,
            """insert into asistente.job_attempt
               (run_id, organization_id, attempt_number, lease_token,
                fencing_version, capability_hash, worker_id, error_code)
               values (%s,%s,8,%s,1,%s,'w','algo')""",
            (run_b, B, uuid.uuid4(), cap()),
            "un error_code sin fallo",
            "ja_error")

    rechaza(con,
            """insert into asistente.job_attempt
               (run_id, organization_id, attempt_number, lease_token,
                fencing_version, capability_hash, worker_id)
               values (%s,%s,7,%s,1,%s,'w')""",
            (run_a, A, uuid.uuid4(), b"\x01" * 16),
            "un capability_hash que no mide 32 bytes",
            "ja_cap_len")

    print()
    print("=" * 74)
    print("  un solo intento activo, un solo turno vivo")
    print("=" * 74)

    rechaza(con,
            """insert into asistente.job_attempt
               (run_id, organization_id, attempt_number, lease_token,
                fencing_version, capability_hash, worker_id)
               values (%s,%s,2,%s,2,%s,'w2')""",
            (run_a, A, uuid.uuid4(), cap()),
            "un segundo intento activo sobre el mismo turno",
            "ja_uno_activo")

    rechaza(con,
            """insert into asistente.job_run
               (job_code, organization_id, scheduled_slot, idempotency_key,
                config_version, config_hash, inputs_hash, estado)
               values (%s,%s,%s,'k-segundo',1,'h','ih','pending')""",
            (JOB, A, datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc)),
            "un segundo turno vivo para el mismo job y organizacion",
            "jr_uno_activo")

    print()
    print("=" * 74)
    print("  un solo desenlace")
    print("=" * 74)

    with con.cursor() as cur:
        cur.execute("""insert into asistente.job_run_event
                       (run_id, attempt_id, organization_id, tipo)
                       values (%s,%s,%s,'SUCCEEDED')""", (run_a, att_a, A))
    con.commit()

    rechaza(con,
            """insert into asistente.job_run_event
               (run_id, attempt_id, organization_id, tipo)
               values (%s,%s,%s,'FAILED_TERMINAL')""",
            (run_a, att_a, A),
            "un segundo desenlace para el MISMO intento, de otro tipo",
            "jre_un_terminal_por_intento")

    print()
    print("=" * 74)
    print("  coherencia del estado")
    print("=" * 74)

    with con.cursor() as cur:
        cur.execute("""insert into asistente.job_schedule_state
                       (job_code, organization_id, next_run_at)
                       values (%s,%s,%s) on conflict do nothing""",
                    (JOB, A, SLOT_A))
    con.commit()

    rechaza(con,
            "update asistente.job_schedule_state set current_slot=%s where "
            "job_code=%s and organization_id=%s",
            (SLOT_A, JOB, A),
            "un current_slot sin current_run_id",
            "js_slot_run")

    rechaza(con,
            "update asistente.job_schedule_state set retry_due_at=now() where "
            "job_code=%s and organization_id=%s",
            (JOB, A),
            "un retry_due_at sin turno en curso",
            "js_retry")

    rechaza(con,
            "update asistente.job_schedule_state set lease_token=%s where "
            "job_code=%s and organization_id=%s",
            (uuid.uuid4(), JOB, A),
            "un lease_token sin lease_until",
            "js_lease_par")

    rechaza(con,
            "update asistente.job_schedule_state set current_run_id=%s, "
            "current_slot=%s where job_code=%s and organization_id=%s",
            (run_b, SLOT_B, JOB, A),
            "apuntar a un turno de OTRA organizacion",
            "js_run_coherente")

    rechaza(con,
            "update asistente.job_schedule_state set current_run_id=%s, "
            "current_slot=%s where job_code=%s and organization_id=%s",
            (run_a, SLOT_B, JOB, A),
            "apuntar al turno propio pero con el slot equivocado",
            "js_run_coherente")

    # el caso que SI tiene que entrar
    try:
        with con.cursor() as cur:
            cur.execute("update asistente.job_schedule_state set current_run_id=%s, "
                        "current_slot=%s where job_code=%s and organization_id=%s",
                        (run_a, SLOT_A, JOB, A))
        con.commit()
        revisar(True, "apuntar al turno propio con el slot correcto SI entra")
    except psycopg.errors.Error as e:
        con.rollback()
        revisar(False, "apuntar al turno propio con el slot correcto SI entra", str(e)[:120])

finally:
    con.rollback()
    con.close()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Las combinaciones cruzadas las rechaza PostgreSQL, no Python.")
print("=" * 74)
