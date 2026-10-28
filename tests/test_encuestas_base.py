# -*- coding: utf-8 -*-
"""
================================================================================
 ENCUESTAS POR WHATSAPP, CONTRA POSTGRESQL DE VERDAD  --  28/10/2026
================================================================================
    DBHOST=... DBNAME=... DBUSER=... DBPASSWORD=... py -3.13 tests/test_encuestas_base.py

Sin las variables de conexion se SALTEA y lo dice (exit 0): no es un verde.
Necesita una base con el esquema 'asistente' y la migracion
202610281600_encuestas_whatsapp.sql aplicada, y crea sus propios tenants de
prueba ('prueba_encuestas' y 'prueba_encuestas_otra').

Lo que se afirma, sobre el EFECTO en la base:
  1. una encuesta por caso: la segunda reserva no crea nada;
  2. la respuesta se guarda UNA vez, con dos toques simultaneos gana uno;
  3. vencida, boton desconocido o mensaje que no es encuesta: no se guarda;
  4. 'fallida' solo desde 'reservada';
  5. otra empresa no ve ni responde las encuestas de esta (RLS);
  6. el destino sale de la conversacion del caso; la tabla no guarda el numero;
  7. el resumen que muestra "Calidad de la atencion" cuadra con las filas.
================================================================================
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}: esta prueba NO corrio")
    sys.exit(0)

import psycopg                                             # noqa: E402

from nucleo.persistencia import encuestas                  # noqa: E402
from nucleo.persistencia.conexion import dsn               # noqa: E402

fallos: list[str] = []
T1, T2 = "prueba_encuestas", "prueba_encuestas_otra"
ORG1, ORG2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def sql(texto, args=()):
    with psycopg.connect(dsn()) as con:
        filas = con.execute(texto, args)
        try:
            return filas.fetchall()
        except psycopg.ProgrammingError:
            return []


# --- los dos tenants de prueba, y un caso con su conversacion
for org, slug in ((ORG1, T1), (ORG2, T2)):
    sql("""insert into public.organization (created_at, updated_at, id, name, api_key, is_active,
             default_currency, address_line, city, company_name, country, email, phone, postcode,
             state, tax_id, website, csat_enabled, auto_close_children_on_parent_close,
             terminology, vertical, timezone)
           values (now(), now(), %s, %s, %s, true, 'COP', '', '', 'Prueba', 'CO', '', '', '', '',
                   '', '', false, false, '{}', 'isp', 'America/Bogota')
           on conflict (id) do nothing""", (org, slug, f"k-{slug}"))
    sql("""insert into asistente.tenant_config (organization_id, slug) values (%s, %s)
           on conflict do nothing""", (org, slug))
sql("delete from asistente.encuestas_whatsapp where organization_id in (%s, %s)", (ORG1, ORG2))

corrida = uuid.uuid4().hex[:8]
CASO = str(uuid.uuid4())
conv = sql("""insert into asistente.conversations (organization_id, canal, usuario_externo,
                nombre_cliente, caso_id, estado)
              values (%s, 'whatsapp', '573001112233', 'Juana Perez', %s, 'cerrada') returning id""",
           (ORG1, CASO))[0][0]

print("\n== 1. Una por caso")
d = encuestas.destino_del_caso(T1, CASO)
revisar(d and d["usuario_externo"] == "573001112233" and d["nombre_cliente"] == "Juana Perez"
        and str(d["id"]) == str(conv), "el destino sale de la conversacion del caso", f"{d}")
revisar(encuestas.destino_del_caso(T1, str(uuid.uuid4())) is None, "un caso sin chat no tiene destino")
e1 = encuestas.reservar(T1, CASO, str(conv), "encuesta_satisfaccion", 72,
                        responsable_id="p-1", responsable_nombre="Ana", area="soporte_tecnico")
e2 = encuestas.reservar(T1, CASO, str(conv), "encuesta_satisfaccion", 72)
revisar(e1 and e2 is None, "la segunda reserva del mismo caso no crea nada", f"{e1} {e2}")
cols = [r[0] for r in sql("""select column_name from information_schema.columns
                              where table_schema='asistente' and table_name='encuestas_whatsapp'""")]
revisar(not any(c in cols for c in ("usuario_externo", "telefono", "nombre_cliente")),
        "la tabla no tiene columna para el numero ni el nombre del cliente", f"{cols}")

print("\n== 2. La respuesta, una vez")
WAMID = f"wamid.{corrida}"
r = encuestas.responder(T1, WAMID, "Excelente", 5)
revisar(r == {"encuesta": False, "registrada": False, "motivo": None, "caso_id": None},
        "antes de marcarla enviada, el wamid no es de ninguna encuesta", f"{r}")
encuestas.marcar_enviada(T1, e1, WAMID)
resultados: list = []
hilos = [threading.Thread(target=lambda o=o, p=p: resultados.append(encuestas.responder(T1, WAMID, o, p)))
         for o, p in (("Excelente", 5), ("Mala", 1))]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
registradas = [x for x in resultados if x["registrada"]]
otras = [x for x in resultados if not x["registrada"]]
revisar(len(registradas) == 1 and otras and otras[0]["motivo"] == "ya_respondida",
        "dos toques casi simultaneos: se guarda UNO, el otro 'ya_respondida'", f"{resultados}")
fila = sql("select estado, opcion, puntaje from asistente.encuestas_whatsapp where id = %s", (e1,))[0]
revisar(fila[0] == "respondida" and (fila[1], fila[2]) in (("Excelente", 5), ("Mala", 1)),
        "queda la opcion y el puntaje del que gano", f"{fila}")

print("\n== 3. Lo que no se guarda")
CASO_V = str(uuid.uuid4())
ev = encuestas.reservar(T1, CASO_V, None, "encuesta_satisfaccion", 72)
encuestas.marcar_enviada(T1, ev, f"wamid.v.{corrida}")
sql("update asistente.encuestas_whatsapp set vence_en = now() - interval '1 minute' where id = %s", (ev,))
r = encuestas.responder(T1, f"wamid.v.{corrida}", "Buena", 4)
revisar(r["encuesta"] and not r["registrada"] and r["motivo"] == "vencida",
        "vencida: es una encuesta, pero no cuenta", f"{r}")
CASO_D = str(uuid.uuid4())
ed = encuestas.reservar(T1, CASO_D, None, "encuesta_satisfaccion", 72)
encuestas.marcar_enviada(T1, ed, f"wamid.d.{corrida}")
r = encuestas.responder(T1, f"wamid.d.{corrida}", "Otra cosa", None)
estado = sql("select estado from asistente.encuestas_whatsapp where id = %s", (ed,))[0][0]
revisar(r["motivo"] == "opcion_desconocida" and estado == "enviada",
        "un boton sin puntaje no la marca respondida: sigue esperando", f"{r} {estado}")
r = encuestas.responder(T1, "wamid.que-no-es-encuesta", "Si", 5)
revisar(r["encuesta"] is False, "un boton de otra plantilla no es una encuesta")

print("\n== 4. Fallida")
CASO_F = str(uuid.uuid4())
ef = encuestas.reservar(T1, CASO_F, None, "encuesta_satisfaccion", 72)
encuestas.marcar_fallida(T1, ef)
encuestas.marcar_enviada(T1, ef, "wamid.tarde")
fila = sql("select estado, wamid from asistente.encuestas_whatsapp where id = %s", (ef,))[0]
revisar(fila == ("fallida", None), "fallida no vuelve a enviada", f"{fila}")
revisar(encuestas.reservar(T1, CASO_F, None, "encuesta_satisfaccion", 72) is None,
        "y el caso no recibe otra")

print("\n== 5. Otra empresa no la ve")
r = encuestas.responder(T2, WAMID, "Mala", 1)
revisar(r["encuesta"] is False, "la otra empresa no responde la encuesta de esta (RLS)", f"{r}")
revisar(encuestas.destino_del_caso(T2, CASO) is None, "ni ve el destino del caso")
otra = encuestas.reservar(T2, CASO, None, "encuesta_satisfaccion", 72)
revisar(otra is not None, "el mismo id de caso en otra empresa es otra encuesta (la unicidad es por empresa)")

print("\n== 6. El resumen")
ahora = datetime.now(timezone.utc)
f = encuestas.filas(T1, ahora - timedelta(days=1), ahora + timedelta(days=1))
casos = {x["caso_id"] for x in f}
revisar(CASO in casos and CASO_D in casos and CASO_F not in casos,
        "entran las enviadas y respondidas; no la fallida", f"{sorted(casos)}")
revisar(all("usuario_externo" not in x and "nombre_cliente" not in x for x in f),
        "las filas no traen datos del cliente")
res = encuestas.resumir(f)
revisar(res["total"]["enviadas"] == len(f) and res["total"]["respondidas"] == 1,
        "el total cuenta enviadas y respondidas", f"{res['total']}")
ana = next((x for x in res["por_responsable"] if x["clave"] == "p-1"), None)
revisar(ana and ana["nombre"] == "Ana" and ana["respondidas"] == 1,
        "por responsable, con el nombre que mando el CRM", f"{res['por_responsable']}")

sql("delete from asistente.encuestas_whatsapp where organization_id in (%s, %s)", (ORG1, ORG2))
sql("delete from asistente.conversations where id = %s", (conv,))
print(f"\n{'=' * 76}\n  {'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}\n{'=' * 76}")
sys.exit(1 if fallos else 0)
