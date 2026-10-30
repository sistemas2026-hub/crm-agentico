# -*- coding: utf-8 -*-
"""
================================================================================
 REINCIDENCIA, CONTRA POSTGRES REAL
================================================================================

    DBHOST=... DBPORT=... DBUSER=... DBPASSWORD=... \\
        py -3.13 tests/test_reincidencia_base.py

Construye una base efimera desde cero (cli/base_desde_cero.py, el mismo ledger
que produccion) y corre la transicion de verdad. Sin las variables se saltea
con exit 0 -- y eso ya escondio regresiones: correrla con base.

POR QUE EXISTE  (29/10/2026)
----------------------------
"Este cliente escribio 3 veces en 15 dias por internet lento" cambia la
conversacion. Lo cuenta db.reincidencia_de, por numero Y canal, dentro de la
ventana de dias de la empresa. Lo que se protege: la ventana, el agrupado por
caso, y que otro numero u otro canal no se mezclen.
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
BASE = "reinc_" + uuid.uuid4().hex[:6]
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
print(" REINCIDENCIA: CUANTAS VECES ESCRIBIO ESTE NUMERO")
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
    fila_minima("organization", {"id": org, "name": "Org reincidencia"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))
    os.environ["DBNAME"] = BASE
    from nucleo.persistencia import db                              # noqa: E402

    def conv(tel, hace_dias, caso=None, canal="whatsapp"):
        return str(q("""insert into asistente.conversations
                          (organization_id, canal, usuario_externo, caso_manual, creado_en)
                        values (%s, %s, %s, %s, now() - make_interval(days => %s)) returning id""",
                     (org, canal, tel, caso, hace_dias))[0][0])

    hoy = conv("573001", 0, "internet_lento")
    conv("573001", 5, "internet_lento")
    conv("573001", 12, "consulta_saldo")
    conv("573001", 40, "internet_lento")          # fuera de la ventana de 30
    conv("573002", 1, "internet_lento")          # otro numero
    conv("573001", 2, "internet_lento", canal="whatsapp-simulado")  # otro canal

    r30 = db.reincidencia_de(TENANT, hoy, 30)
    comprobar(r30 and r30["total"] == 3,
              f"cuenta las 3 del mismo numero y canal dentro de 30 dias ({r30})")
    comprobar(r30 and r30["por_caso"][0] == {"caso": "internet_lento", "n": 2},
              "y la mas repetida primero: internet_lento x2")
    r60 = db.reincidencia_de(TENANT, hoy, 60)
    comprobar(r60 and r60["total"] == 4, f"con 60 dias entra la de hace 40 ({r60 and r60['total']})")
    comprobar(db.reincidencia_de(TENANT, hoy, 0) is None, "0 dias = apagado")
    comprobar(db.reincidencia_de(TENANT, str(uuid.uuid4()), 30) is None,
              "una conversacion que no existe no inventa nada")
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
