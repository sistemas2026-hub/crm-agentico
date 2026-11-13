# -*- coding: utf-8 -*-
"""
Ninguna prueba que siembra empresas corre contra una base remota.

POR QUE EXISTE (01/11/2026)
---------------------------
Despues del deploy de la tesis de capacidad, el reloj de produccion listo
cuatro "empresas" que no lo eran: prueba-b4-beef6c79, prueba-b4-f27ce15d,
prueba-entrega-732c97c5 y prueba-entrega-a28bafe8. Las habian dejado
tests/test_b4_sincronizaciones.py y tests/test_entrega_registrada.py, corridas
alguna vez con las credenciales de produccion y cortadas antes de limpiar. Eran
invisibles mientras el reloj miraba la carpeta tenants/; desde que mira la base
(Ola 4) aparecen en cada vuelta, y en el CRM como organizaciones activas.

33 pruebas insertan en asistente.tenant_config y ninguna miraba a que base
apuntaba. Ahora todas pasan por tests/base_local.py antes de conectarse.

Uso:  py -3.13 tests/test_base_local.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PRUEBAS = Path(__file__).resolve().parent
sys.path.insert(0, str(PRUEBAS))

from base_local import es_local, host_de                         # noqa: E402

fallos: list[str] = []


def revisar(cond, que, porque=""):
    print(f"  [{'ok' if cond else 'FALLA'}] {que}", flush=True)
    if not cond:
        if porque:
            print(f"         {porque}", flush=True)
        fallos.append(que)


print("\n1. que host cuenta como local")
for host in ("", "localhost", "127.0.0.1", "::1", "host.docker.internal",
             "db", "pg-b7", "pg-deploy-311"):
    revisar(es_local(host), f"{host!r} es local")
for host in ("crm.example.co", "10.0.0.5", "db.interna.empresa", "192.168.1.20"):
    revisar(not es_local(host), f"{host!r} NO es local")

print("\n2. el host de un DSN propio")
revisar(host_de("postgres://u:p@pg-b7:5432/x") == "pg-b7", "forma URL")
revisar(host_de("host=crm.example.co port=5432 dbname=x") == "crm.example.co",
        "forma clave=valor")
revisar(host_de("") == "", "sin DSN, sin host (la prueba se saltea sola)")

print("\n3. toda prueba que siembra empresas llama a la guarda antes de conectar")
SIEMBRA = re.compile(r"insert into asistente\.tenant_config", re.I)
CONECTA = re.compile(r"psycopg\.connect\(")
#  Un DSN propio en una variable de entorno (RELOJ_PG_ADMIN, M06B_PG_ADMIN...):
#  la prueba fija DBHOST desde ahi DESPUES de conectarse, asi que la guarda
#  tiene que mirar ese DSN.
DSN_PROPIO = re.compile(r"^ADMIN\s*=\s*os\.environ\.get\(", re.M)
sin_guarda, sin_dsn = [], []
for p in sorted(PRUEBAS.glob("test_*.py")):
    if p.name == Path(__file__).name:
        continue
    texto = p.read_text(encoding="utf-8")
    conexion = CONECTA.search(texto)
    if not SIEMBRA.search(texto) or conexion is None:
        #  Sin psycopg.connect, la sentencia vive en un cursor falso
        #  (test_alta_tenant_autonomia, test_guarda_alineacion_git).
        continue
    guarda = texto.find("exigir_base_local(")
    if guarda < 0 or guarda > conexion.start():
        sin_guarda.append(p.name)
    elif DSN_PROPIO.search(texto) and "exigir_base_local(__file__, dsn=" not in texto:
        sin_dsn.append(p.name)
revisar(not sin_guarda, "ninguna siembra empresas sin pasar antes por exigir_base_local",
        f"sin guarda: {sin_guarda}")
revisar(not sin_dsn, "las que usan un DSN propio le pasan ese DSN a la guarda",
        f"miran DBHOST en vez de su DSN: {sin_dsn}")

print("\n4. contra una base remota, la prueba se niega SIN conectarse")
#  Una de las dos que dejaron restos, con un host remoto que no resuelve: si la
#  guarda no corta antes, el error es de conexion y no el aviso.
entorno = dict(os.environ, DBHOST="base-remota.invalid", DBPORT="5432",
               DBNAME="x", DBUSER="x", DBPASSWORD="x")
r = subprocess.run([sys.executable, str(PRUEBAS / "test_b4_sincronizaciones.py")],
                   env=entorno, capture_output=True, text=True, timeout=120,
                   encoding="utf-8", errors="replace")
salida = r.stdout + r.stderr
revisar("no es local" in salida and "OMITIDA" in salida,
        "test_b4_sincronizaciones se niega con el aviso", salida[-400:])
revisar("OperationalError" not in salida and "Traceback" not in salida,
        "y no llega a intentar la conexion", salida[-400:])

print()
if fallos:
    print(f"FALLARON {len(fallos)}")
    sys.exit(1)
print("todo ok")
