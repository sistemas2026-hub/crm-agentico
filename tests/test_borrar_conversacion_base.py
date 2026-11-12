# -*- coding: utf-8 -*-
"""
================================================================================
 BORRAR UNA CONVERSACION: SOLO DE PRUEBA  --  contra PostgreSQL, por la ruta real
================================================================================

    DBHOST=127.0.0.1 DBPORT=55520 DBUSER=postgres DBPASSWORD=... \\
        py -3.13 tests/test_borrar_conversacion_base.py

12/11/2026 (auditoria del menu §2 «Conversaciones»). DELETE /conversaciones/<id>
borraba cualquier conversacion de la empresa con solo el tenant como guarda:
tambien las de WhatsApp real, aunque estuvieran en 'conservar' por un reclamo.
Borrar datos de un cliente es CRITICO (PRD §2). La guarda va dentro del delete
(db.borrar_conversacion, `canal = any(permitidos)`), asi que se prueba contra
la base y por la ruta Flask, no con un doble:

  A. Una conversacion de canal REAL: 403 'canal_real', y la fila y sus
     mensajes siguen en la base.
  B. Una del simulador y una de la API: 204, y se van con sus mensajes.
  C. Un canal que el motor no conoce (o nulo) no se borra: falla cerrado.
  D. Otra empresa: 404, y la fila ajena sigue ahi.

Y de paso, con la misma base (construirla cuesta minutos):
  E. La apertura de una conversacion trae 'ticket_operativo', que la Bandeja
     usa para enlazar el ticket (lib/conversaciones/enlaces.js) y que hasta el
     12/11/2026 solo viajaba en la cola.
================================================================================
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}: NO se comprobo nada contra la base.")
    raise SystemExit(0)
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker (cli/base_desde_cero.py corre las migraciones de Django)")
    raise SystemExit(0)

from base_local import exigir_base_local                           # noqa: E402
exigir_base_local(__file__)

import psycopg                                                      # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
BASE = "borrar_" + uuid.uuid4().hex[:6]
TENANT = "rapilink"
fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def dsn(base: str) -> str:
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


def q(sentencia, params=None):
    with psycopg.connect(dsn(BASE), autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


def fila_minima(tabla: str, fijos: dict) -> None:
    cols = q("""select column_name, data_type, character_maximum_length from information_schema.columns
                where table_schema = 'public' and table_name = %s
                  and is_nullable = 'NO' and column_default is null""", (tabla,))
    valores = dict(fijos)
    por_tipo = {"uuid": lambda: str(uuid.uuid4()), "boolean": lambda: False,
                "integer": lambda: 0, "bigint": lambda: 0, "smallint": lambda: 0,
                "jsonb": lambda: "{}", "json": lambda: "{}",
                "timestamp with time zone": lambda: "now", "date": lambda: "2026-01-01"}
    for nombre, tipo, largo in cols:
        if nombre not in valores:
            valor = por_tipo.get(tipo, lambda: "x" + uuid.uuid4().hex[:8])()
            valores[nombre] = valor[:largo] if largo and isinstance(valor, str) else valor
    nombres = list(valores)
    q(f"insert into public.{tabla} ({', '.join(nombres)}) values ({', '.join(['%s'] * len(nombres))})",
      [valores[n] for n in nombres])


def conv(org, canal, numero="573100000001", conservar=False):
    cid = str(q("""insert into asistente.conversations (organization_id, canal, usuario_externo, conservar)
                   values (%s, %s, %s, %s) returning id""", (org, canal, numero, conservar))[0][0])
    q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen)
         values (%s, %s, 'user', 'hola', 'cliente')""", (org, cid))
    return cid


def existe(cid) -> bool:
    return bool(q("select 1 from asistente.conversations where id = %s", (cid,)))


def mensajes(cid) -> int:
    return q("select count(*) from asistente.messages where conversation_id = %s", (cid,))[0][0]


print("=" * 74)
print(" BORRAR UNA CONVERSACION: SOLO DE PRUEBA  --  contra PostgreSQL")
print("=" * 74)
try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO,
                            "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    org, otra = str(uuid.uuid4()), str(uuid.uuid4())
    fila_minima("organization", {"id": org, "name": "Org borrar"})
    fila_minima("organization", {"id": otra, "name": "Otra empresa"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (otra, "otra_empresa"))
    os.environ["DBNAME"] = BASE
    from nucleo.canales import api                                 # noqa: E402

    http = api.app.test_client()

    def borrar(cid):
        return http.delete(f"/conversaciones/{cid}?tenant={TENANT}")

    # ======================================================================
    print("\n== A. canal real: no se borra ==")
    real = conv(org, "whatsapp", conservar=True)
    resp = borrar(real)
    comprobar(resp.status_code == 403 and (resp.get_json() or {}).get("codigo") == "canal_real",
              f"una conversacion de WhatsApp real responde 403 canal_real ({resp.status_code})")
    comprobar(existe(real) and mensajes(real) == 1,
              "la conversacion real y su mensaje siguen en la base")

    # ======================================================================
    print("\n== B. canales de prueba: se borran con sus mensajes ==")
    for canal in ("whatsapp-simulado", "api"):
        cid = conv(org, canal, numero="5731000000" + canal[:2])
        resp = borrar(cid)
        comprobar(resp.status_code == 204, f"'{canal}' responde 204 ({resp.status_code})")
        comprobar(not existe(cid) and mensajes(cid) == 0,
                  f"'{canal}': la conversacion y sus mensajes ya no estan")

    # ======================================================================
    print("\n== C. canal desconocido: falla cerrado ==")
    rara = conv(org, "telegram")
    resp = borrar(rara)
    comprobar(resp.status_code == 403 and existe(rara),
              f"un canal que el motor no conoce no se borra ({resp.status_code})")

    # ======================================================================
    print("\n== D. otra empresa ==")
    ajena = conv(otra, "whatsapp-simulado")
    resp = borrar(ajena)
    comprobar(resp.status_code == 404 and existe(ajena),
              f"una conversacion de otra empresa responde 404 y sigue ahi ({resp.status_code})")
    resp = borrar(str(uuid.uuid4()))
    comprobar(resp.status_code == 404, f"un id que no existe responde 404 ({resp.status_code})")

    # ======================================================================
    print("\n== E. la apertura trae el ticket operativo ==")
    con_ticket = conv(org, "whatsapp", numero="573100000077")
    q("update asistente.conversations set ticket_operativo = '94553' where id = %s", (con_ticket,))
    resp = http.get(f"/conversaciones/{con_ticket}/mensajes?tenant={TENANT}")
    c = (resp.get_json() or {}).get("conversacion") or {}
    comprobar(resp.status_code == 200 and c.get("ticket_operativo") == "94553",
              f"/mensajes (la misma definicion que /apertura) trae ticket_operativo "
              f"({resp.status_code}, {c.get('ticket_operativo')!r})")
    sin_ticket = conv(org, "whatsapp", numero="573100000078")
    c = (http.get(f"/conversaciones/{sin_ticket}/mensajes?tenant={TENANT}").get_json() or {}).get("conversacion") or {}
    comprobar("ticket_operativo" in c and c["ticket_operativo"] is None,
              "sin ticket, la clave viene en null: la pantalla no dibuja el enlace")
finally:
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute(f'drop database if exists "{BASE}" with (force)')
    except Exception as e:                                           # noqa: BLE001
        print(f"  (no se pudo borrar {BASE}: {type(e).__name__})")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Borrar una conversacion solo alcanza a las de prueba; las de un cliente real quedan.")
