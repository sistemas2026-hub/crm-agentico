# -*- coding: utf-8 -*-
"""
================================================================================
 «QUEDA EN ESPERA»: EL PENDIENTE INTERNO DE T5, CONTRA POSTGRES REAL
================================================================================

    DBHOST=... DBPORT=... DBUSER=... DBPASSWORD=... \\
        py -3.13 tests/test_relevo_pendiente_interno_base.py

Construye una base efimera desde cero (cli/base_desde_cero.py, el mismo ledger
que produccion) y corre la transicion de verdad. Sin las variables se saltea
con exit 0 -- y eso ya escondio regresiones: correrla con base.

POR QUE EXISTE  (29/10/2026)
----------------------------
El contrato del relevo define desde septiembre el pendiente interno (opcion de
T5): columnas, banda 4 y los eventos 'pendiente_interno_abierto/cerrado'. Nada
lo escribia. Ahora lo escribe transiciones.marcar_pendiente_interno. Lo que se
protege: que con nota se abra con su evento, que sin nota se cierre (y que sin
nada abierto no deje un evento vacio), que con la IA atendiendo no se pueda, y
que la NOTA no termine en el evento (puede traer datos del cliente).
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

faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker")
    raise SystemExit(0)

import psycopg                                                      # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
BASE = "pend_int_" + uuid.uuid4().hex[:6]
TENANT = "rapilink"
ANA = ("7c9e6679-7425-40de-944b-e07fc1f90ae7", "Ana Perez")

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


def pendiente(conv):
    return q("""select pendiente_interno_desde is not null, pendiente_interno_nota, relevo_version
                from asistente.conversations where id = %s""", (conv,))[0]


def eventos(conv, tipo):
    return q("""select datos from asistente.relevo_eventos
                where conversation_id = %s and tipo = %s""", (conv, tipo))


print("=" * 74)
print(" «QUEDA EN ESPERA»: EL PENDIENTE INTERNO DE T5")
print("=" * 74)

try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO,
                            "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    org = str(uuid.uuid4())
    fila_minima("organization", {"id": org, "name": "Org pendiente"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))
    os.environ["DBNAME"] = BASE
    from nucleo.relevo import transiciones as T                     # noqa: E402

    c = str(q("""insert into asistente.conversations (organization_id, canal, usuario_externo)
                 values (%s, 'whatsapp-simulado', '573000000099') returning id""", (org,))[0][0])
    T.escalar(TENANT, c, motivo="solicitud_explicita")
    T.tomar(TENANT, c, operador_id=ANA[0], operador_nombre=ANA[1])

    print("\n== abrir ==")
    r1 = T.marcar_pendiente_interno(TENANT, c, nota="esperando que reinicie el equipo",
                                    operador_id=ANA[0], operador_nombre=ANA[1])
    p = pendiente(c)
    comprobar(r1.aplicada and p[0] and p[1] == "esperando que reinicie el equipo",
              f"con nota: queda en espera, con la nota en su columna ({p})")
    ev = eventos(c, "pendiente_interno_abierto")
    comprobar(len(ev) == 1 and "nota" not in (ev[0][0] or {}),
              f"un evento 'pendiente_interno_abierto' SIN la nota adentro ({ev})")

    print("\n== cerrar ==")
    r2 = T.marcar_pendiente_interno(TENANT, c, nota=None,
                                    operador_id=ANA[0], operador_nombre=ANA[1])
    p = pendiente(c)
    comprobar(r2.aplicada and not p[0] and p[1] is None,
              f"sin nota: se cierra y se borra la nota ({p})")
    comprobar(len(eventos(c, "pendiente_interno_cerrado")) == 1, "con su evento 'cerrado'")
    version = p[2]
    r3 = T.marcar_pendiente_interno(TENANT, c, nota="   ",
                                    operador_id=ANA[0], operador_nombre=ANA[1])
    comprobar(not r3.aplicada and r3.motivo == "sin_pendiente" and pendiente(c)[2] == version
              and len(eventos(c, "pendiente_interno_cerrado")) == 1,
              "sin nada abierto, responder sin marca no deja otro evento ni sube la version")

    print("\n== con la IA atendiendo no se puede ==")
    c2 = str(q("""insert into asistente.conversations (organization_id, canal, usuario_externo, relevo_version)
                  values (%s, 'whatsapp-simulado', '573000000098', 1) returning id""", (org,))[0][0])
    r4 = T.marcar_pendiente_interno(TENANT, c2, nota="algo",
                                    operador_id=ANA[0], operador_nombre=ANA[1])
    comprobar(not r4.aplicada and not pendiente(c2)[0],
              f"control IA: no se abre ({r4.motivo})")
finally:
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute(f'drop database if exists "{BASE}" with (force)')
    except Exception as e:
        print(f"  [aviso] no se pudo borrar {BASE}: {type(e).__name__}")

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
