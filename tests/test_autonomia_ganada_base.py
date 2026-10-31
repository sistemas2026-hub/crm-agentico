# -*- coding: utf-8 -*-
"""
================================================================================
 LA EVIDENCIA DE UNA ACCION  --  contra PostgreSQL (31/10/2026)
================================================================================

    DBHOST=127.0.0.1 DBPORT=55471 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_autonomia_ganada_base.py

Base efimera del ledger (cli/base_desde_cero.py), nunca la local ni la de
produccion. nucleo/persistencia/autonomia_ganada.medir cuenta lo que decide si
una accion gana autonomia (PRD §2). Afirma el NUMERO EXACTO:

  - revisada es lo que una persona decidio; vencida y cancelada NO cuentan
    (nadie la miro, e inflarian la tasa sin evidencia);
  - la ventana se mide por cuando se DECIDIO, no por cuando nacio;
  - otra herramienta y otra empresa no mueven nada;
  - cada estado de verificacion en su conteo.
================================================================================
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
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
BASE = "autonomia_" + uuid.uuid4().hex[:6]
AHORA = datetime.now(timezone.utc)
fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def q(sentencia, params=None):
    with psycopg.connect(f"host={HOST} port={PUERTO} dbname={BASE} user={USUARIO} password={CLAVE} "
                         f"sslmode=disable connect_timeout=15", autocommit=True) as con:
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


def hace(dias: float) -> datetime:
    return AHORA - timedelta(days=dias)


def conversacion(org) -> str:
    return str(q("""insert into asistente.conversations (organization_id, canal, usuario_externo)
                    values (%s, 'whatsapp', %s) returning id""", (org, "57300" + uuid.uuid4().hex[:7]))[0][0])


def propuesta(org, estado, *, herramienta="reiniciar_ont", nacio=None, decidida=None):
    q("""insert into asistente.acciones_propuestas
           (organization_id, conversation_id, herramienta, resumen, propuesto_por, estado,
            creado_en, revisado_en, motivo_rechazo)
         values (%s, %s, %s, 'Reiniciar', 'ia', %s, %s, %s, %s)""",
      (org, conversacion(org), herramienta, estado, nacio or hace(3), decidida,
       "x" if estado in ("cancelada", "rechazada") else None))


def verificacion(org, estado, *, herramienta="reiniciar_ont", cuando=None):
    q("""insert into asistente.verificaciones_accion
           (organization_id, conversation_id, herramienta, ejecutada_en, espera_segundos, max_intentos, estado)
         values (%s, %s, %s, %s, 120, 3, %s)""", (org, conversacion(org), herramienta, cuando or hace(3), estado))


print("=" * 74)
print(" LA EVIDENCIA DE UNA ACCION")
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
    fila_minima("organization", {"id": org, "name": "Org autonomia"})
    fila_minima("organization", {"id": otra, "name": "Otra empresa"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, "rapilink"))
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (otra, "otra_empresa"))
    os.environ["DBNAME"] = BASE

    from nucleo.persistencia import autonomia_ganada as medicion   # noqa: E402

    # Dentro de la ventana (decididas hace 3 dias):
    for estado in ("ejecutada_ok", "ejecutada_ok", "ejecutada_ok", "aprobada"):
        propuesta(org, estado, decidida=hace(3))
    propuesta(org, "rechazada", decidida=hace(2))
    propuesta(org, "ejecutada_fallo", decidida=hace(2))
    propuesta(org, "desconocida", decidida=hace(2))
    # Nadie las miro: no son evidencia.
    propuesta(org, "vencida", decidida=hace(2))
    propuesta(org, "cancelada", decidida=hace(2))
    propuesta(org, "pendiente")
    # Nacio hace 40 dias pero se DECIDIO hace 5: cuenta.
    propuesta(org, "ejecutada_ok", nacio=hace(40), decidida=hace(5))
    # Nacio hace 5 pero se decidio hace 35 (imposible en la vida real, pero
    # prueba que manda 'revisado_en'): NO cuenta.
    propuesta(org, "ejecutada_ok", nacio=hace(5), decidida=hace(35))
    # Fuera de la ventana, otra herramienta, otra empresa:
    propuesta(org, "rechazada", decidida=hace(45))
    propuesta(org, "rechazada", herramienta="cambiar_tipo_onu", decidida=hace(2))
    propuesta(otra, "rechazada", decidida=hace(2))

    for estado in ("ACCION_CONFIRMADA", "ACCION_CONFIRMADA", "ACCION_NO_CONFIRMADA",
                   "NO_VERIFICABLE", "VERIFICACION_PENDIENTE"):
        verificacion(org, estado)
    verificacion(org, "ACCION_NO_CONFIRMADA", cuando=hace(45))
    verificacion(org, "ACCION_NO_CONFIRMADA", herramienta="cambiar_tipo_onu")
    verificacion(otra, "ACCION_NO_CONFIRMADA")

    m = medicion.medir("rapilink", "reiniciar_ont", hace(30), AHORA)
    print()
    comprobar(m["revisadas"] == 8, "revisadas: 4 aprobadas + rechazada + fallo + incierta + la que nacio "
              "antes y se decidio adentro = 8 (sin vencida, cancelada ni pendiente)", str(m))
    comprobar(m["rechazadas"] == 1, "rechazadas: 1 (la de afuera, la de otra herramienta y la de otra "
              "empresa no)", str(m))
    comprobar(m["fallidas"] == 2, "fallidas: ejecutada_fallo + desconocida", str(m))
    comprobar((m["confirmadas"], m["no_confirmadas"], m["no_verificables"], m["pendientes"]) == (2, 1, 1, 1),
              "verificaciones: 2 confirmadas, 1 no confirmada, 1 no verificable, 1 pendiente", str(m))
    vacia = medicion.medir("otra_empresa", "reiniciar_ont", hace(30), AHORA)
    comprobar(vacia["revisadas"] == 1 and vacia["no_confirmadas"] == 1,
              "la otra empresa ve solo lo suyo", str(vacia))
finally:
    try:
        with psycopg.connect(f"host={HOST} port={PUERTO} dbname=postgres user={USUARIO} password={CLAVE} "
                             f"sslmode=disable", autocommit=True) as con:
            con.execute(f'drop database if exists "{BASE}" with (force)')
    except Exception:                                                  # noqa: BLE001
        pass

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] La evidencia de una accion se cuenta exacta, por empresa y por cuando se decidio.")
