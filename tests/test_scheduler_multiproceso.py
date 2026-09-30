# -*- coding: utf-8 -*-
"""
================================================================================
 DOS PROCESOS DE VERDAD  --  no dos hilos del mismo interprete
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=test_p2 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_scheduler_multiproceso.py

Por que existe
--------------
'test_scheduler_funciones.py' mide la carrera de ocho coordinadores con hilos y
conexiones separadas. Eso prueba bien los locks de PostgreSQL y no prueba nada
de esto:

  * que cada proceso inicialice su propio registro cerrado de handlers;
  * que el registro NO se comparta por memoria entre replicas;
  * que dos pools de conexiones distintos no se estorben;
  * que la caida REAL de un proceso --SIGKILL, sin finally, sin cierre de
    conexion ordenado-- deje el turno recuperable;
  * que otra replica lo recupere;
  * que la finalizacion tardia del proceso muerto, si volviera, sea rechazada.

Un hilo que "muere" sigue teniendo el interprete vivo, los objetos en memoria y
las conexiones abiertas. Un proceso que recibe SIGKILL no. La diferencia es
justo la que importa para un scheduler.

Como se mide
------------
Se lanzan procesos Python de verdad con 'subprocess', cada uno con su propio
intérprete, su propio import de 'nucleo.programador' y sus propias conexiones.
El proceso que "muere" se mata con kill(), no se le pide que termine.

Lo que se conserva del turno rescatado se compara CAMPO A CAMPO: mismo run,
misma config congelada, mismos inputs, misma clave de idempotencia.
================================================================================
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
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
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

JOB = "prueba_p2"
A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
DSN = (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
       f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
       f"password={os.environ['DBPASSWORD']} sslmode=disable")

TMP = Path(tempfile.mkdtemp(prefix="p2-multiproceso-"))

# -----------------------------------------------------------------------------
#  Los programas que se lanzan. Cada uno es un proceso completo: importa
#  'nucleo.programador' por su cuenta, arma su propio registro y abre sus
#  propias conexiones.
# -----------------------------------------------------------------------------

PROGRAMA_CLAIM = r'''
import json, os, sys, time
sys.path.insert(0, os.environ["RAIZ"])
from nucleo.programador import puerta

JOB, ORG, SLOT = sys.argv[1], sys.argv[2], sys.argv[3]
señal = os.environ.get("SENAL_ARCHIVO")
with puerta.sesion(puerta.COORDINADOR) as cur:
    claim = puerta.reclamar(cur, JOB, ORG, SLOT, os.environ["WORKER"])
salida = {"pid": os.getpid(), "gano": claim is not None}
if claim:
    salida["run_id"] = str(claim["run_id"])
    salida["attempt_number"] = claim["attempt_number"]
    salida["fencing"] = claim["fencing_version"]
    # la capability se escribe en un archivo aparte, no en la salida del
    # proceso: la salida se imprime y se loguea
    open(os.environ["CAP_ARCHIVO"], "w").write(claim["capability"])
print(json.dumps(salida))
'''

PROGRAMA_TRABAJAR = r'''
import json, os, sys, time
sys.path.insert(0, os.environ["RAIZ"])
from nucleo.programador import ejecutor, registro

# Cada proceso arma SU registro. No hay nada compartido por memoria.
vistos = {}
def trabajo(turno):
    vistos.update({
        "job_code": turno.job_code,
        "organization_id": str(turno.organization_id),
        "config_version": turno.config_version,
        "config_hash": turno.config_hash,
        "inputs_hash": turno.inputs_hash,
        "attempt_number": turno.attempt_number,
    })
    open(os.environ["LISTO_ARCHIVO"], "w").write(json.dumps(vistos))
    # Se queda trabajando "mucho". Si lo matan, no llega a finalizar.
    time.sleep(float(os.environ.get("TARDA", "60")))
    return {"ok": True}

registro.registrar_para_prueba(os.environ["JOB"], trabajo)
run_id = sys.argv[1]
cap = open(os.environ["CAP_ARCHIVO"]).read().strip()
r = ejecutor.ejecutar(run_id, cap, lease_segundos=float(os.environ["LEASE"]))
print(json.dumps({"pid": os.getpid(), "registrado": r.get("registrado"),
                  "nota": r.get("nota"), "error": r.get("error")}))
'''


def escribir(nombre: str, contenido: str) -> Path:
    p = TMP / nombre
    p.write_text(contenido, encoding="utf-8")
    return p


def entorno(**extra) -> dict:
    e = dict(os.environ)
    e.update({"RAIZ": str(RAIZ), "JOB": JOB})
    e.update({k: str(v) for k, v in extra.items()})
    return e


con = psycopg.connect(DSN, autocommit=True, row_factory=dict_row)


def limpiar():
    con.execute("delete from asistente.job_run_event")
    con.execute("delete from asistente.job_attempt")
    con.execute("delete from asistente.job_schedule_state")
    con.execute("delete from asistente.job_run")
    con.execute("update asistente.job_catalogo set habilitado=true, "
                "max_intentos=4, lease_duracion=interval '6 seconds' "
                "where code=%s", (JOB,))


def programar(horas_atras=1):
    con.execute("insert into asistente.job_schedule_state "
                "(job_code, organization_id, next_run_at) values "
                "(%s,%s, date_trunc('hour', now()) - make_interval(hours => %s))",
                (JOB, A, horas_atras))
    return con.execute("select next_run_at from asistente.job_schedule_state "
                       "where job_code=%s and organization_id=%s",
                       (JOB, A)).fetchone()["next_run_at"]


try:
    for rol in ("scheduler_coordinator", "job_executor", "monitor_ro"):
        try:
            con.execute(f"grant {rol} to current_user")
        except psycopg.errors.Error:
            pass

    claim_py = escribir("claim.py", PROGRAMA_CLAIM)
    trabajar_py = escribir("trabajar.py", PROGRAMA_TRABAJAR)

    # =========================================================================
    titulo("1. claim simultaneo desde DOS PROCESOS distintos")
    # =========================================================================
    limpiar()
    slot = programar()
    caps = [TMP / "cap0.txt", TMP / "cap1.txt"]

    procesos = [
        subprocess.Popen(
            [sys.executable, str(claim_py), JOB, str(A), slot.isoformat()],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=entorno(WORKER=f"proceso-{i}", CAP_ARCHIVO=str(caps[i])))
        for i in range(2)]
    salidas = []
    for p in procesos:
        out, err = p.communicate(timeout=60)
        salidas.append((p.returncode, out.strip(), err.strip()))

    revisar(all(c == 0 for c, _, _ in salidas),
            "los dos procesos terminaron en 0",
            f"{[(c, e[-200:]) for c, _, e in salidas]}")
    datos = [json.loads(o) for _, o, _ in salidas if o]
    revisar(len(datos) == 2, "los dos imprimieron su resultado", f"{salidas}")
    pids = {d["pid"] for d in datos}
    revisar(len(pids) == 2 and os.getpid() not in pids,
            "y son PROCESOS distintos entre si y del que corre la prueba",
            f"pids={pids} prueba={os.getpid()}")
    ganadores = [d for d in datos if d["gano"]]
    revisar(len(ganadores) == 1,
            "exactamente UNO se quedo con el turno",
            f"ganaron {len(ganadores)}")
    n = con.execute("select count(*) as n from asistente.job_attempt"
                    ).fetchone()["n"]
    revisar(n == 1, "y hay un solo intento en la base", f"{n}")

    ganador = ganadores[0]
    cap_ganador = caps[[d["pid"] for d in datos].index(ganador["pid"])]

    # =========================================================================
    titulo("2. el proceso dueño se muere de verdad (kill, no return)")
    # =========================================================================
    listo = TMP / "listo.json"
    if listo.exists():
        listo.unlink()
    trabajador = subprocess.Popen(
        [sys.executable, str(trabajar_py), ganador["run_id"]],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=entorno(CAP_ARCHIVO=str(cap_ganador), LISTO_ARCHIVO=str(listo),
                    LEASE=6, TARDA=120))

    limite = time.monotonic() + 30
    while not listo.exists() and time.monotonic() < limite:
        time.sleep(0.2)
    revisar(listo.exists(),
            "el proceso ejecutor arranco el trabajo y derivo el turno",
            "no llego a escribir el archivo de señal")
    visto = json.loads(listo.read_text()) if listo.exists() else {}
    revisar(visto.get("job_code") == JOB
            and visto.get("organization_id") == str(A),
            "con el job y la organizacion derivados de la base, no recibidos",
            f"{visto}")
    revisar(visto.get("config_version") == 1 and len(visto.get("config_hash", "")) == 64,
            "y la config congelada", f"{visto}")

    fila_antes = con.execute(
        "select id, idempotency_key, config_version, config_hash, inputs, "
        "inputs_hash, scheduled_slot from asistente.job_run where id=%s",
        (ganador["run_id"],)).fetchone()

    trabajador.kill()                       # SIGKILL: sin finally, sin cierre
    trabajador.wait(timeout=20)
    revisar(trabajador.returncode != 0,
            "el proceso murio sin terminar su trabajo",
            f"salio {trabajador.returncode}")

    intento = con.execute(
        "select outcome, completed_at from asistente.job_attempt "
        "where run_id=%s", (ganador["run_id"],)).fetchone()
    revisar(intento["outcome"] is None,
            "el intento queda ABIERTO: nadie lo cerro",
            f"{intento}")
    estado = con.execute(
        "select lease_until, current_run_id from asistente.job_schedule_state "
        "where job_code=%s and organization_id=%s", (JOB, A)).fetchone()
    revisar(estado["current_run_id"] is not None,
            "y el estado sigue apuntando al turno", f"{estado}")

    # =========================================================================
    titulo("3. el lease vence y OTRO proceso lo recupera")
    # =========================================================================
    v = con.execute("select * from asistente.jobs_vencidos(now(), 10)").fetchall()
    revisar(v == [], "mientras el lease vive, el turno NO vence", f"{v}")

    espera = (estado["lease_until"] - con.execute("select now() as n"
                                                  ).fetchone()["n"])
    segundos = max(espera.total_seconds(), 0) + 1
    print(f"       (esperando {segundos:.1f}s a que venza el lease de 6s)")
    time.sleep(segundos)

    v = con.execute("select * from asistente.jobs_vencidos(now(), 10)").fetchall()
    revisar(len(v) == 1 and v[0]["motivo"] == "lease_vencido",
            "vencido el lease, el turno vuelve a estar disponible",
            f"{v}")

    cap_rescate = TMP / "cap_rescate.txt"
    r = subprocess.run(
        [sys.executable, str(claim_py), JOB, str(A), slot.isoformat()],
        capture_output=True, text=True,
        env=entorno(WORKER="proceso-rescate", CAP_ARCHIVO=str(cap_rescate)))
    rescate = json.loads(r.stdout.strip()) if r.stdout.strip() else {}
    revisar(r.returncode == 0 and rescate.get("gano"),
            "una replica nueva --otro proceso-- lo reclama",
            f"exit {r.returncode}: {r.stderr[-300:]}")
    revisar(rescate.get("run_id") == ganador["run_id"],
            "y es el MISMO turno, no uno nuevo",
            f"{rescate.get('run_id')} vs {ganador['run_id']}")
    revisar(rescate.get("attempt_number") == 2,
            "con el intento siguiente", f"{rescate.get('attempt_number')}")
    revisar(rescate.get("fencing", 0) > ganador["fencing"],
            "y el fencing avanzado",
            f"{rescate.get('fencing')} vs {ganador['fencing']}")

    viejo = con.execute(
        "select outcome from asistente.job_attempt where attempt_number=1 "
        "and run_id=%s", (ganador["run_id"],)).fetchone()
    revisar(viejo["outcome"] == "lease_lost",
            "el intento del proceso muerto queda cerrado como 'lease_lost'",
            f"{viejo}")

    fila_despues = con.execute(
        "select id, idempotency_key, config_version, config_hash, inputs, "
        "inputs_hash, scheduled_slot from asistente.job_run where id=%s",
        (ganador["run_id"],)).fetchone()
    revisar(dict(fila_antes) == dict(fila_despues),
            "el turno rescatado conserva run, clave de idempotencia, config e "
            "inputs, campo a campo",
            f"{dict(fila_antes)}\n         {dict(fila_despues)}")

    # =========================================================================
    titulo("4. si el proceso muerto volviera, su finalizacion se rechaza")
    # =========================================================================
    cap_muerta = cap_ganador.read_text().strip()
    with psycopg.connect(DSN, autocommit=True) as otra:
        fin = otra.execute("select asistente.job_finalize(%s,%s,'succeeded') as f",
                           (con.execute(
                               "select id from asistente.job_attempt where "
                               "attempt_number=1 and run_id=%s",
                               (ganador["run_id"],)).fetchone()["id"],
                            cap_muerta)).fetchone()[0]
    revisar(fin is None,
            "la capability del proceso muerto ya no sirve para finalizar",
            f"devolvio {fin}")
    lat = con.execute(
        "select asistente.job_heartbeat(%s,%s) as h",
        (con.execute("select id from asistente.job_attempt where "
                     "attempt_number=1 and run_id=%s",
                     (ganador["run_id"],)).fetchone()["id"],
         cap_muerta)).fetchone()["h"]
    revisar(lat is None, "ni para latir", f"devolvio {lat}")

    ctx = con.execute("select count(*) as n from asistente.job_contexto(%s,%s)",
                      (ganador["run_id"], cap_muerta)).fetchone()["n"]
    revisar(ctx == 0, "ni para volver a derivar el contexto", f"{ctx} filas")

    # =========================================================================
    titulo("5. la replica que rescato SI puede terminar")
    # =========================================================================
    listo2 = TMP / "listo2.json"
    r = subprocess.run(
        [sys.executable, str(trabajar_py), ganador["run_id"]],
        capture_output=True, text=True,
        env=entorno(CAP_ARCHIVO=str(cap_rescate), LISTO_ARCHIVO=str(listo2),
                    LEASE=30, TARDA=0.1))
    salida = json.loads(r.stdout.strip()) if r.stdout.strip() else {}
    revisar(r.returncode == 0 and salida.get("registrado") == "succeeded",
            "el proceso que rescato el turno lo termina con exito",
            f"exit {r.returncode}: {r.stdout[-300:]} {r.stderr[-300:]}")
    visto2 = json.loads(listo2.read_text()) if listo2.exists() else {}
    revisar(visto2.get("attempt_number") == 2
            and visto2.get("config_hash") == visto.get("config_hash")
            and visto2.get("inputs_hash") == visto.get("inputs_hash"),
            "y trabajo con la MISMA config e inputs que el intento muerto",
            f"{visto} vs {visto2}")

    final = con.execute("select estado, completed_at from asistente.job_run "
                        "where id=%s", (ganador["run_id"],)).fetchone()
    revisar(final["estado"] == "succeeded" and final["completed_at"] is not None,
            "el turno cierra bien", f"{final}")

    # =========================================================================
    titulo("6. el registro de handlers no se comparte entre procesos")
    # =========================================================================
    # Un proceso que NO registra el handler no puede ejecutar el job, aunque
    # otro proceso de la misma maquina lo haya registrado hace un segundo.
    limpiar()
    slot = programar()
    cap_solo = TMP / "cap_solo.txt"
    r = subprocess.run(
        [sys.executable, str(claim_py), JOB, str(A), slot.isoformat()],
        capture_output=True, text=True,
        env=entorno(WORKER="proceso-sin-handler", CAP_ARCHIVO=str(cap_solo)))
    d = json.loads(r.stdout.strip())
    sin_registro = escribir("sin_registro.py", r'''
import json, os, sys
sys.path.insert(0, os.environ["RAIZ"])
from nucleo.programador import ejecutor, registro
# NO se registra ningun handler: este proceso arranco limpio.
print(json.dumps({"registrados": sorted(registro.registrados()),
                  "r": ejecutor.ejecutar(sys.argv[1],
                                         open(os.environ["CAP_ARCHIVO"]).read().strip())}))
''')
    r2 = subprocess.run(
        [sys.executable, str(sin_registro), d["run_id"]],
        capture_output=True, text=True,
        env=entorno(CAP_ARCHIVO=str(cap_solo)))
    out = json.loads(r2.stdout.strip()) if r2.stdout.strip() else {}
    revisar(out.get("registrados") == [],
            "un proceso nuevo arranca con el registro VACIO: no hereda nada "
            "por memoria de otro proceso",
            f"{out.get('registrados')}")
    revisar(out.get("r", {}).get("registrado") == "failed_terminal",
            "y el turno se cierra terminal, no reintentable: que este "
            "despliegue no sepa hacer el job no se arregla reintentando",
            f"{out.get('r')}")
finally:
    con.close()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Dos procesos de verdad: uno reclama, uno muere, otro recupera.")
print("=" * 74)
