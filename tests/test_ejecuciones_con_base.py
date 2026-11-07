# -*- coding: utf-8 -*-
"""
================================================================================
 EJECUCIONES  --  las dos escrituras llegan en cualquier orden, y da igual
================================================================================

Que fija, y por que cada cosa
------------------------------
B1  UNA APERTURA TARDIA NO REVIVE UNA EJECUCION CERRADA. Es la afirmacion
    central de esta fase. La apertura va en un hilo --porque un viaje a la base
    cuesta 1.054 ms y cobrarselo al cliente para animar una pantalla es lo que
    ya se decidio no hacer-- y el cierre se pliega en el viaje de la traza. Son
    dos escrituras concurrentes sobre la misma fila SIN orden garantizado.

    Si el orden importara, el caso malo seria silencioso: la fila quedaria
    'iniciada' para siempre y la oficina mostraria a alguien tecleando desde
    hace horas. Por eso las dos son idempotentes sobre la clave primaria.

B2  UN CIERRE TEMPRANO CREA LA FILA YA CERRADA. El simetrico: si el UPDATE no
    encontrara nada, la ejecucion no existiria nunca y el turno no quedaria
    registrado.

B3  'iniciada_en' NO SE PISA AL CERRAR. Pisarlo haria que toda ejecucion
    durara cero, y la edad es justo lo que decide si todavia es creible.

B4  'desconocida' SE DERIVA, NO SE GUARDA. Una ejecucion mas vieja que el
    umbral deja de ser creible la mire quien la mire, sin que nadie haya
    corrido un barrido. En este repositorio ya se pago el precio de lo
    contrario: el reloj de tareas colgaba de un bloque __main__ que gunicorn
    nunca ejecuta, y nadie se entero.

B5  DOS EMPRESAS NO SE VEN. El aislamiento no es un filtro de la consulta: lo
    pone el contexto de sesion, y una lectura sin empresa fijada devuelve CERO
    filas, no todas.

B6  LA ESCRITURA NO RETIENE EL CURSOR DE E1. Es el riesgo marcado como grave en
    la ficha: una transaccion abierta mientras se espera algo externo congela
    la frontera de entrega del flujo incremental. Se comprueba midiendo que la
    frontera AVANZA despues de escribir.

Como se corre
-------------
Necesita un PostgreSQL 17 de laboratorio. Se salta solo si no hay, con exit 0
y diciendolo -- nunca en silencio.

    docker run -d --rm --name pgej -e POSTGRES_PASSWORD=p -e POSTGRES_DB=lab \\
        -p 15433:5432 postgres:17

    set DBHOST=localhost & set DBPORT=15433 & set DBUSER=postgres
    set DBPASSWORD=p & set DBNAME=lab
    py -3.13 tests/test_ejecuciones_con_base.py

Crea su propio esquema y sus propios datos. No toca produccion.
"""
import os
import sys
import time
import uuid
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

#  Las dos sentencias REALES de db.py, copiadas aqui. Se copian en vez de
#  importar el modulo porque ese abre su propia sesion contra la base de
#  verdad; lo que se prueba es la GARANTIA de las sentencias.
ABRIR = """
  insert into asistente.ejecuciones
    (id, organization_id, agente, conversation_id, estado)
  values (%s, %s, %s, %s, 'iniciada')
  on conflict (id) do nothing
"""

CERRAR = """
  insert into asistente.ejecuciones
    (id, organization_id, agente, conversation_id, estado,
     n_llamadas, hubo_fallo, terminada_en)
  values (%s, %s, %s, %s, %s, %s, %s, now())
  on conflict (id) do update
    set estado = case
                   when asistente.ejecuciones.estado = 'iniciada'
                     then excluded.estado
                   else asistente.ejecuciones.estado
                 end,
        cierre_en_conflicto = asistente.ejecuciones.cierre_en_conflicto
          or (asistente.ejecuciones.estado <> 'iniciada'
              and asistente.ejecuciones.estado <> excluded.estado),
        n_llamadas   = greatest(asistente.ejecuciones.n_llamadas,
                                excluded.n_llamadas),
        hubo_fallo   = asistente.ejecuciones.hubo_fallo or excluded.hubo_fallo,
        terminada_en = coalesce(asistente.ejecuciones.terminada_en,
                                excluded.terminada_en),
        conversation_id = coalesce(excluded.conversation_id,
                                   asistente.ejecuciones.conversation_id)
  returning cierre_en_conflicto
"""

ACTIVAS = """
  select id::text, agente,
         extract(epoch from (now() - iniciada_en))::float as edad_s
    from asistente.ejecuciones
   where organization_id = %s and estado = 'iniciada'
   order by iniciada_en desc
"""


def preparar():
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("create schema if not exists asistente")
        c.execute("""create table if not exists public.organization (
                       id uuid primary key default gen_random_uuid(),
                       name text)""")
        #  Lo minimo que la migracion necesita del esquema: el rol y la funcion
        #  de contexto. En produccion ya existen.
        c.execute("""do $$ begin
                       if not exists (select 1 from pg_roles
                                       where rolname = 'app_backend') then
                         create role app_backend nologin;
                       end if;
                     end $$""")
        #  En produccion el rol ya tiene el esquema concedido; en el
        #  laboratorio hay que darselo o la comprobacion de aislamiento falla
        #  por falta de permiso y no por la politica, que es lo que se mide.
        c.execute("grant usage on schema asistente to app_backend")
        c.execute("""create or replace function asistente.org_actual()
                     returns uuid language sql stable as $$
                       select nullif(current_setting('app.current_tenant', true), '')::uuid;
                     $$""")
        c.execute("drop table if exists asistente.ejecuciones")
        #  La migracion que se esta probando, tal cual.
        sql = (RAIZ / "supabase" / "202610302200_ejecuciones.sql").read_text(
            encoding="utf-8")
        c.execute(sql)
        c.execute("delete from public.organization")
        a = c.execute(
            "insert into public.organization (name) values ('ISP A') returning id"
        ).fetchone()[0]
        b = c.execute(
            "insert into public.organization (name) values ('ISP B') returning id"
        ).fetchone()[0]
        return a, b


def abrir(con, ident, org, agente="supervisor_noc", conv=None):
    con.execute(ABRIR, (ident, org, agente, conv))


def cerrar(con, ident, org, agente="supervisor_noc", conv=None,
           estado="terminada", n=0, fallo=False):
    return con.execute(
        CERRAR, (ident, org, agente, conv, estado, n, fallo)).fetchone()[0]


def fila(con, ident):
    return con.execute(
        "select estado, n_llamadas, hubo_fallo, iniciada_en, terminada_en, "
        "       conversation_id::text, tx::text, cierre_en_conflicto "
        "  from asistente.ejecuciones where id = %s", (ident,)).fetchone()


def main() -> int:
    org_a, org_b = preparar()
    con = psycopg.connect(DSN, autocommit=True)

    print("\n[B1] una apertura TARDIA no revive una ejecucion cerrada")
    ident = str(uuid.uuid4())
    cerrar(con, ident, org_a, n=3)              # el cierre llega primero
    abrir(con, ident, org_a)                    # y la apertura despues
    f = fila(con, ident)
    comprobar(f[0] == "terminada",
              f"sigue terminada despues de la apertura tardia (es '{f[0]}')")
    comprobar(f[1] == 3, "conserva el numero de llamadas del cierre")
    comprobar(f[4] is not None, "conserva el instante en que termino")

    print("\n[B2] un cierre TEMPRANO crea la fila ya cerrada")
    comprobar(f is not None, "la fila existe aunque el cierre llegara primero")

    print("\n[B3] 'iniciada_en' no se pisa al cerrar")
    ident = str(uuid.uuid4())
    abrir(con, ident, org_a)
    nacio = fila(con, ident)[3]
    time.sleep(1.1)
    cerrar(con, ident, org_a, n=5, fallo=True)
    f = fila(con, ident)
    comprobar(f[3] == nacio, "conserva el instante real de apertura")
    duracion = (f[4] - f[3]).total_seconds()
    comprobar(duracion >= 1.0,
              f"la ejecucion dura lo que duro ({duracion:.2f}s), no cero")
    comprobar(f[2] is True, "el fallo de una llamada viaja al cierre")

    print("\n[B3b] la conversacion la completa el cierre, y no la puede borrar")
    ident = str(uuid.uuid4())
    conv = str(uuid.uuid4())
    abrir(con, ident, org_a, conv=None)          # la apertura no la conoce
    cerrar(con, ident, org_a, conv=conv)         # el cierre si
    comprobar(fila(con, ident)[5] == conv, "el cierre la completa")
    cerrar(con, ident, org_a, conv=None)         # un cierre posterior sin ella
    comprobar(fila(con, ident)[5] == conv, "un cierre sin conversacion NO la borra")

    print("\n[B4] 'desconocida' se deriva de la edad, sin barrido")
    ident_viejo = str(uuid.uuid4())
    abrir(con, ident_viejo, org_a)
    con.execute("update asistente.ejecuciones set iniciada_en = now() - interval '20 minutes' "
                "where id = %s", (ident_viejo,))
    ident_nuevo = str(uuid.uuid4())
    abrir(con, ident_nuevo, org_a)
    activas = con.execute(ACTIVAS, (org_a,)).fetchall()
    por_id = {a[0]: a[2] for a in activas}
    umbral = 600
    comprobar(por_id.get(ident_viejo, 0) > umbral,
              "la vieja supera el umbral y deja de ser creible")
    comprobar(por_id.get(ident_nuevo, 99999) <= umbral,
              "la recien abierta sigue siendo creible")
    comprobar(all(a[0] != ident for a in activas),
              "una ejecucion cerrada ya no aparece entre las activas")

    print("\n[B7] el PRIMER estado terminal manda, y la contradiccion se anota")
    #  No es alcanzable hoy --hay un solo cerrador y siempre escribe
    #  'terminada'-- pero el esquema admite los otros dos. Sin guarda ganaria
    #  el ultimo en llegar, que es lo contrario de lo que vale.
    ident = str(uuid.uuid4())
    abrir(con, ident, org_a)
    choque1 = cerrar(con, ident, org_a, estado="terminada", n=4)
    comprobar(choque1 is False, "el primer cierre no es un conflicto")
    choque2 = cerrar(con, ident, org_a, estado="fallida", n=1)
    f = fila(con, ident)
    comprobar(f[0] == "terminada",
              f"el primer terminal se conserva (quedo '{f[0]}')")
    comprobar(choque2 is True, "el segundo se REPORTA como contradictorio")
    comprobar(f[7] is True, "y queda anotado en la fila")
    comprobar(f[1] == 4, "no pierde el recuento de llamadas del primero")

    print("\n[B7b] un cierre repetido IGUAL no es un conflicto")
    ident = str(uuid.uuid4())
    abrir(con, ident, org_a)
    cerrar(con, ident, org_a, estado="terminada", n=2)
    repetido = cerrar(con, ident, org_a, estado="terminada", n=2)
    comprobar(repetido is False, "reintentar el mismo cierre no levanta la bandera")
    comprobar(fila(con, ident)[7] is False, "y la fila sigue limpia")

    print("\n[B7c] un fallo visto una vez no se borra despues")
    ident = str(uuid.uuid4())
    abrir(con, ident, org_a)
    cerrar(con, ident, org_a, estado="terminada", n=3, fallo=True)
    cerrar(con, ident, org_a, estado="terminada", n=3, fallo=False)
    comprobar(fila(con, ident)[2] is True,
              "un cierre posterior que no lo vio NO borra el fallo")

    print("\n[B5] dos empresas no se ven")
    ident_b = str(uuid.uuid4())
    abrir(con, ident_b, org_b, agente="supervisor_noc")
    de_a = con.execute(ACTIVAS, (org_a,)).fetchall()
    comprobar(all(x[0] != ident_b for x in de_a),
              "la ejecucion de la otra empresa no sale en la consulta de A")

    #  Y el caso que de verdad importa: olvidarse de la empresa. Con la
    #  politica puesta, un rol sin privilegio y sin contexto ve CERO, no todo.
    with psycopg.connect(DSN) as c2:
        with c2.cursor() as cur:
            cur.execute("set local role app_backend")
            cur.execute("select count(*) from asistente.ejecuciones")
            sin_contexto = cur.fetchone()[0]
    comprobar(sin_contexto == 0,
              f"sin empresa fijada se ven CERO filas, no todas (vio {sin_contexto})")

    print("\n[B6] escribir una ejecucion no retiene el cursor de E1")
    #  La frontera de entrega es la transaccion mas antigua AUN ACTIVA. Si la
    #  escritura dejara una transaccion abierta, la frontera se quedaria quieta
    #  y el flujo incremental dejaria de entregar.
    antes = con.execute(
        "select pg_snapshot_xmin(pg_current_snapshot())::text").fetchone()[0]
    for _ in range(5):
        abrir(con, str(uuid.uuid4()), org_a)
    despues = con.execute(
        "select pg_snapshot_xmin(pg_current_snapshot())::text").fetchone()[0]
    comprobar(int(despues) > int(antes),
              f"la frontera avanzo ({antes} -> {despues}): nada quedo abierto")

    #  Y el sello de transaccion existe: es lo que hace que estas filas se
    #  puedan entregar con el mismo cursor que los eventos.
    f = fila(con, ident_nuevo)
    comprobar(f[6] is not None and f[6].isdigit(),
              "cada ejecucion lleva su sello de transaccion")

    con.close()
    print("\n" + "=" * 70)
    if fallos:
        print(f"[FALLA] {len(fallos)} comprobacion(es):")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("[OK] Las dos escrituras son idempotentes y el orden no importa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
