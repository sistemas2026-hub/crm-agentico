# -*- coding: utf-8 -*-
"""
================================================================================
 A QUIEN SE LE AVISO LA CAIDA  --  contra PostgreSQL (31/10/2026)
================================================================================

    DBHOST=127.0.0.1 DBPORT=55471 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_aviso_de_caida_base.py

Base efimera del ledger. mensajes_automaticos.caidas_avisadas decide a quien se
le manda "ya quedo restablecido": solo a quien el aviso de caida le SALIO.

  - un aviso reservado pero que no salio (fallido, o todavia reservado) no
    cuenta: no se le dice "ya volvio" a quien no se entero de la falla;
  - otro evento, otra empresa o un aviso mas viejo que la ventana tampoco;
  - de varias caidas del mismo servicio, la ultima.
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
BASE = "caida_" + uuid.uuid4().hex[:6]
fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


from base_local import exigir_base_local                           # noqa: E402
exigir_base_local(__file__)
def q(sentencia, params=None, base=None):
    with psycopg.connect(f"host={HOST} port={PUERTO} dbname={base or BASE} user={USUARIO} "
                         f"password={CLAVE} sslmode=disable connect_timeout=15", autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


def org_minima(nombre: str) -> str:
    oid = str(uuid.uuid4())
    cols = q("""select column_name, data_type, character_maximum_length from information_schema.columns
                where table_schema = 'public' and table_name = 'organization'
                  and is_nullable = 'NO' and column_default is null""")
    por_tipo = {"uuid": lambda: str(uuid.uuid4()), "boolean": lambda: False,
                "integer": lambda: 0, "bigint": lambda: 0, "smallint": lambda: 0,
                "jsonb": lambda: "{}", "json": lambda: "{}",
                "timestamp with time zone": lambda: "now", "date": lambda: "2026-01-01"}
    valores = {"id": oid, "name": nombre}
    for c, tipo, largo in cols:
        if c not in valores:
            v = por_tipo.get(tipo, lambda: "x" + uuid.uuid4().hex[:8])()
            valores[c] = v[:largo] if largo and isinstance(v, str) else v
    q(f"insert into public.organization ({', '.join(valores)}) values ({', '.join(['%s'] * len(valores))})",
      list(valores.values()))
    return oid


def aviso(org, evento, clave, estado, dias=1):
    q("""insert into asistente.mensajes_automaticos (organization_id, evento, clave, plantilla, estado, creado_en)
         values (%s, %s, %s, 'x', %s, now() - make_interval(days => %s))""", (org, evento, clave, estado, dias))


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
    org, otra = org_minima("Org caida"), org_minima("Otra")
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, 'rapilink')", (org,))
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, 'otra_empresa')", (otra,))
    os.environ["DBNAME"] = BASE
    from nucleo.persistencia import mensajes_automaticos as reg     # noqa: E402

    aviso(org, "caida_masiva", "caida:101:2026-10-01 07:00:00", "enviado", dias=5)
    aviso(org, "caida_masiva", "caida:101:2026-10-30 07:16:44", "enviado", dias=1)   # la ultima
    aviso(org, "caida_masiva", "caida:102:2026-10-30 07:16:44", "fallido")
    aviso(org, "caida_masiva", "caida:103:2026-10-30 07:16:44", "reservado")
    aviso(org, "caida_masiva", "caida:104:2026-09-01 07:00:00", "enviado", dias=30)  # vieja
    aviso(org, "caida_restablecida", "caida:105:2026-10-30 07:16:44", "enviado")     # otro evento
    aviso(otra, "caida_masiva", "caida:106:2026-10-30 07:16:44", "enviado")         # otra empresa
    aviso(org, "caida_masiva", "caida:1010:2026-10-30 07:16:44", "enviado")          # no es el 101

    r = reg.caidas_avisadas("rapilink", ["101", "102", "103", "104", "105", "106"], dias=7)
    print()
    comprobar(r == {"101": "2026-10-30 07:16:44"},
              "solo el 101, con su ultima caida: ni fallidos, ni reservados, ni viejos, ni otro evento, "
              "ni otra empresa, ni un servicio que empieza igual", str(r))
    comprobar(reg.caidas_avisadas("rapilink", [], dias=7) == {}, "sin servicios, nada")
finally:
    try:
        q(f'drop database if exists "{BASE}" with (force)', base="postgres")
    except Exception:                                                  # noqa: BLE001
        pass

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] El 'ya volvio' se le manda a quien recibio el 'se cayo'.")
