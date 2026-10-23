# -*- coding: utf-8 -*-
"""
================================================================================
 EL CIRCUITO COMPLETO  --  el coordinador REAL despierta al Supervisor
================================================================================

    DBHOST=... DBPORT=... DBNAME=<base del ledger> DBUSER=... DBPASSWORD=... \\
        py -3.13 tests/test_latido_extremo_a_extremo.py

    (sin esas variables se saltea, igual que las demas suites del scheduler)

QUE MIDE ESTO QUE NINGUNA OTRA PRUEBA MIDE
------------------------------------------
Las otras tres cubren mitades:

  * 'tests/test_supervisor_latido.py' prueba el TRABAJO con la red sustituida.
  * 'operaciones/tests/test_p1_latido_supervisor.py' prueba la VISTA de Django.
  * 'tests/test_p2_compuertas.py' y 'test_scheduler_multiproceso.py' prueban el
    SCHEDULER con un handler hermetico de prueba.

Ninguna junta las tres cosas. Esta corre 'coordinador.un_tick()' --el real, el
mismo que correria en produccion-- sobre una fila de verdad de
'asistente.job_catalogo', y comprueba que:

  1. el coordinador RESUELVE 'supervisor_latido' desde el registro congelado y
     lo ejecuta (no lo cuenta como job desconocido);
  2. sale UNA peticion HTTP, con el tenant del turno y su credencial;
  3. el turno queda REGISTRADO en la base -- 'job_run', 'job_attempt' y los
     eventos del turno -- como ejecutado y exitoso;
  4. y lo que SI se persiste no lleva datos de cliente.

LO QUE SE MIDIO Y SALIO DISTINTO DE LO ESPERADO (02/10/2026)
------------------------------------------------------------
La primera version de esta prueba buscaba los conteos en 'job_run.output'. ESA
COLUMNA NO EXISTE, y no es un descuido del scheduler: 'puerta.finalizar' llama a
'asistente.job_finalize(attempt, capability, outcome, error_code)' y nada mas, y
los eventos del turno ('CLAIMED', 'STARTED', 'SUCCEEDED') guardan solo metadatos
del scheduler -- intento, fencing, worker. El valor que devuelve un trabajo
viaja en el informe EN MEMORIA del tick ('resultado["trabajo"]', ver
nucleo/programador/ejecutor.py) y a la linea de log del propio trabajo.

Consecuencia, dicha sin adornos: hoy la base prueba QUE el latido corrio y que
salio bien; CUANTAS senales vio queda en el log del motor, no en una tabla. Esta
prueba lo afirma en las dos direcciones -- lo que si queda y lo que no -- para
que nadie vuelva a suponer que hay un 'output' donde no lo hay. Si esos conteos
deben ser durables, es una decision de diseno (una columna, o un evento del
turno), no un arreglo de este archivo.

ES "CODIGO CONSTRUIDO NO ES CODIGO QUE CORRE", APLICADO A ESTE BLOQUE. El reloj
de tareas de este proyecto ya colgo una vez de un bloque '__main__' que gunicorn
nunca ejecutaba, y la reconciliacion estuvo probada y sin llamador. Las dos veces
el sintoma fue el mismo: silencio.

LO QUE SE SUSTITUYE, Y POR QUE ESE SEAM Y NO OTRO
-------------------------------------------------
Lo unico sustituido es la RESPUESTA de Django: un servidor HTTP de verdad, en un
puerto local, que contesta el mismo sobre que devuelve 'LatidoSupervisorView'.
No se sustituye el coordinador, ni el ejecutor, ni la base, ni 'requests'.

El seam esta ahi porque del otro lado ya hay 16 pruebas contra la vista REAL
--incluidas las que afirman que no escribe y que no cruza organizaciones-- y
levantar Django aqui mediria Django otra vez en vez de medir el circuito.

LA FILA DEL CATALOGO SE PONE Y SE QUITA
---------------------------------------
Esta prueba inserta 'supervisor_latido' en 'asistente.job_catalogo' porque es la
unica forma de que el coordinador lo reclame -- y es justo el interruptor que en
produccion sigue apagado. Lo borra en el 'finally': dejarlo seria convertir una
prueba en un encendido.
================================================================================
"""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"{chr(10)}         {porque}" if porque else ""))


faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] el circuito completo necesita {faltan}")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from nucleo.programador import coordinador, metricas, registro     # noqa: E402
from nucleo.programador import trabajos                            # noqa: E402

JOB = "supervisor_latido"
A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
TOKEN = "pat-de-prueba-local"

DSN = (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
       f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
       f"password={os.environ['DBPASSWORD']} sslmode=disable")

#  El sobre EXACTO que devuelve 'LatidoSupervisorView'. Copiarlo a mano seria
#  inventar un contrato; estas claves son las que afirma
#  'test_las_claves_de_la_respuesta_son_exactamente_estas'.
RESPUESTA = {
    "organizacion": str(A),
    "leido_en": "2026-10-02T12:00:00+00:00",
    "senales_vigentes": 4,
    "senales_por_tipo": {"caso_abierto_antiguo": 3, "orden_sin_programar": 1},
    "escrituras": 0,
    "fuente": "operaciones.supervisor.detectar",
}

pedidos: list[dict] = []


class Supervisor(BaseHTTPRequestHandler):
    """Un Django minimo: contesta el sobre del latido y anota que le pidieron."""

    def do_GET(self):                                             # noqa: N802
        u = urlparse(self.path)
        pedidos.append({
            "ruta": u.path,
            "params": {k: v[0] for k, v in parse_qs(u.query).items()},
            "auth": self.headers.get("Authorization", ""),
        })
        cuerpo = json.dumps(RESPUESTA).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *a):                                    # silencio
        pass


servidor = HTTPServer(("127.0.0.1", 0), Supervisor)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
URL = (f"http://127.0.0.1:{servidor.server_address[1]}"
       f"/api/operaciones/supervisor/latido/")

con = psycopg.connect(DSN, autocommit=True, row_factory=dict_row)

print()
print("=" * 74)
print("  el coordinador real, la base real, el trabajo real")
print("=" * 74)

try:
    os.environ[trabajos.VARIABLE_URL] = URL
    os.environ[trabajos.VARIABLE_TOKEN] = TOKEN

    con.execute("delete from asistente.job_run_event")
    con.execute("delete from asistente.job_attempt")
    con.execute("delete from asistente.job_schedule_state where job_code=%s",
                (JOB,))
    con.execute("delete from asistente.job_run where job_code=%s", (JOB,))
    con.execute("delete from asistente.job_catalogo where code=%s", (JOB,))
    #  La fila que en produccion NO existe. Es el interruptor de operacion.
    con.execute(
        "insert into asistente.job_catalogo (code, descripcion, anchor, "
        "intervalo) values (%s, 'latido del Supervisor (prueba)', "
        "date_trunc('hour', now()) - interval '1 day', interval '1 hour')",
        (JOB,))
    con.execute("insert into asistente.job_schedule_state "
                "(job_code, organization_id, next_run_at) values "
                "(%s,%s, date_trunc('hour', now()) - interval '1 hour')",
                (JOB, A))

    informe = coordinador.un_tick(metricas.Registro())

    # -----------------------------------------------------------------------
    #  1. el coordinador lo resolvio y lo ejecuto
    # -----------------------------------------------------------------------
    revisar(informe["recibidos"] == 1 and informe["alcanzados"] == 1,
            "el coordinador reclama el turno y lo trabaja",
            f"{ {k: v for k, v in informe.items() if k != 'turnos'} }")
    revisar(informe["cuadra"], "y el embudo cuadra")
    turno = (informe["turnos"] or [{}])[0]
    revisar(turno.get("registrado") == "succeeded",
            "el turno cierra como exito -- no como 'job desconocido'",
            f"{turno}")

    # -----------------------------------------------------------------------
    #  2. salio UNA peticion, con el tenant y la credencial
    # -----------------------------------------------------------------------
    revisar(len(pedidos) == 1,
            f"salio UNA sola peticion al Supervisor (fueron {len(pedidos)})")
    p = pedidos[0] if pedidos else {}
    revisar(p.get("ruta") == "/api/operaciones/supervisor/latido/",
            "a la ruta del latido, no a la del ciclo", f"{p.get('ruta')}")
    revisar(p.get("params", {}).get("organization_id") == str(A),
            "con la organizacion del TURNO, derivada de la base",
            f"{p.get('params')}")
    revisar(p.get("auth", "").startswith("Bearer "),
            "y con la credencial que el motor ya tiene para el CRM")

    # -----------------------------------------------------------------------
    #  3. quedo REGISTRADO en la base  --  la parte que nada mas mide
    # -----------------------------------------------------------------------
    fila = con.execute(
        "select estado, organization_id, job_code, completed_at from "
        "asistente.job_run where job_code=%s order by creado_en desc limit 1",
        (JOB,)).fetchone()
    revisar(fila is not None, "quedo una fila en 'asistente.job_run'")
    if fila:
        revisar(fila["estado"] == "succeeded",
                "con estado 'succeeded'", f"{fila['estado']}")
        revisar(str(fila["organization_id"]) == str(A),
                "y atada a la organizacion del turno")
        revisar(fila["completed_at"] is not None,
                "y con el turno cerrado, no en curso")

    att = con.execute(
        "select a.outcome, a.error_code, a.attempt_number from "
        "asistente.job_attempt a join asistente.job_run r on r.id=a.run_id "
        "where r.job_code=%s order by a.started_at desc limit 1",
        (JOB,)).fetchone()
    revisar(att is not None and att["outcome"] == "succeeded",
            "y un intento registrado como 'succeeded'", f"{att}")
    revisar(att is not None and att["error_code"] is None,
            "sin codigo de error")

    eventos = [e["tipo"] for e in con.execute(
        "select e.tipo from asistente.job_run_event e join asistente.job_run r "
        "on r.id=e.run_id where r.job_code=%s order by e.ocurrido_en", (JOB,))]
    revisar(eventos == ["CLAIMED", "STARTED", "SUCCEEDED"],
            "y la traza del turno, en orden", f"{eventos}")

    # -----------------------------------------------------------------------
    #  4. LOS CONTEOS NO LLEGAN A LA BASE  --  medido, no supuesto
    # -----------------------------------------------------------------------
    #  No hay 'output' donde guardarlos. Se afirma en las dos direcciones para
    #  que el limite sea visible: el dia que alguien agregue una columna o un
    #  evento con la salida del trabajo, ESTA prueba se pone en rojo y obliga a
    #  revisar que se esta persistiendo y si lleva datos de cliente.
    columnas = {c["column_name"] for c in con.execute(
        "select column_name from information_schema.columns where "
        "table_schema='asistente' and table_name='job_run'")}
    revisar("output" not in columnas,
            "'job_run' NO tiene columna de salida: los conteos del latido no "
            "quedan en la base, solo en el log del motor",
            f"{sorted(columnas)}")
    datos = json.dumps([e["datos"] for e in con.execute(
        "select e.datos from asistente.job_run_event e join asistente.job_run r "
        "on r.id=e.run_id where r.job_code=%s", (JOB,))])
    revisar("senales" not in datos,
            "y los eventos del turno tampoco los traen", f"{datos}")

    #  Lo que SI viaja, viaja en el informe en memoria del tick. Ahi tambien
    #  tiene que estar limpio: ese informe se imprime y se registra.
    trabajo = turno.get("trabajo") or {}
    revisar(trabajo.get("senales_vigentes") == 4,
            "los conteos si llegan al informe del tick, que es donde hoy viven",
            f"{trabajo}")
    plano = json.dumps(trabajo)
    for prohibido in ("evidencia", "origen_id", "cliente", "telefono",
                      "cedula", "direccion", "coordenadas"):
        revisar(prohibido not in plano,
                f"y el informe del tick no trae '{prohibido}'")

    # -----------------------------------------------------------------------
    #  5. el tick siguiente no lo repite
    # -----------------------------------------------------------------------
    pedidos.clear()
    informe2 = coordinador.un_tick(metricas.Registro())
    revisar(informe2["alcanzados"] == 0 and not pedidos,
            "el tick siguiente no vuelve a preguntar: un slot ya trabajado no "
            "se repite",
            f"{ {k: v for k, v in informe2.items() if k != 'turnos'} }")

finally:
    #  Se quita la fila del catalogo. Dejarla puesta seria dejar el latido
    #  ENCENDIDO en esta base, que es exactamente lo que el bloque promete no
    #  hacer.
    #  El orden importa: 'job_attempt' y los eventos referencian a 'job_run'.
    con.execute("delete from asistente.job_run_event e using asistente.job_run r "
                "where e.run_id = r.id and r.job_code = %s", (JOB,))
    con.execute("delete from asistente.job_attempt a using asistente.job_run r "
                "where a.run_id = r.id and r.job_code = %s", (JOB,))
    con.execute("delete from asistente.job_schedule_state where job_code=%s",
                (JOB,))
    con.execute("delete from asistente.job_run where job_code=%s", (JOB,))
    con.execute("delete from asistente.job_catalogo where code=%s", (JOB,))
    quedan = con.execute(
        "select count(*) as n from asistente.job_catalogo where code=%s",
        (JOB,)).fetchone()["n"]
    revisar(quedan == 0,
            "y la prueba deja el catalogo como lo encontro: sin el latido",
            f"quedan {quedan} fila(s)")
    con.close()
    servidor.shutdown()
    registro.olvidar_pruebas()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] El scheduler despierta al Supervisor y la respuesta queda trazable.")
print("=" * 74)
