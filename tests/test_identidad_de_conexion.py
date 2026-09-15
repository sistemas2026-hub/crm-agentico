# -*- coding: utf-8 -*-
"""
================================================================================
 IDENTIDAD DE CONEXION  --  quien abrio esta sesion, y que no quede abierta
================================================================================

    py -3.13 tests/test_identidad_de_conexion.py                  (estatico)
    DBHOST=localhost DBPORT=55435 DBNAME=postgres DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_identidad_de_conexion.py              (ademas, la base)

Por que existe
--------------
El 15/09/2026 tres sesiones quedaron 'idle in transaction' contra produccion
-una casi ocho dias-, retuvieron AccessShareLock sobre asistente.tenant_config y
cancelaron una migracion de P2 por lock_timeout. Ademas congelaron el horizonte
de vacuum: el xmin mas viejo tenia 797.012 transacciones de edad.

No se pudo saber QUE PROCESO las abrio. Todas las conexiones de la plataforma
llegan a PostgreSQL a traves de Supavisor y se ven con
application_name = 'Supavisor', asi que el motor, el reloj y cualquier CLI
corrida desde una maquina de desarrollo son indistinguibles en
pg_stat_activity. Eso costo una investigacion entera.

  1. dsn() firma la conexion, y el nombre sale del entorno
  2. quien ya declaro el suyo en DATABASE_URL lo conserva
  3. contra la base: el nombre LLEGA a pg_stat_activity
  4. sesion() no deja transaccion abierta: ni al salir bien, ni por excepcion
  5. el apagado da mas margen del que gunicorn necesita

Lo que NO prueba: que Supavisor preserve application_name. Eso solo se ve con un
pooler en el medio, y aqui la conexion es directa -- queda medido en produccion
despues del despliegue.
================================================================================
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.persistencia import conexion                          # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def titulo(t):
    print(f"\n{'=' * 74}\n  {t}\n{'=' * 74}", flush=True)


def con_entorno(**vars):
    """Contexto que pone variables y las devuelve a como estaban."""
    class _Ctx:
        def __enter__(self):
            self.antes = {k: os.environ.get(k) for k in vars}
            for k, v in vars.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        def __exit__(self, *_):
            for k, v in self.antes.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return _Ctx()


PARTES = {"DBHOST": "ejemplo", "DBPORT": "5432", "DBNAME": "b",
          "DBUSER": "u", "DBPASSWORD": "c"}

# =============================================================================
titulo("1. dsn() firma la conexion")
# =============================================================================
with con_entorno(**PARTES, DB_APPLICATION_NAME="dexter-motor"):
    url = conexion.dsn()
revisar("application_name=dexter-motor" in url,
        "el nombre del entorno viaja en la cadena", url.replace("c", "<clave>"))

with con_entorno(**PARTES, DB_APPLICATION_NAME=None):
    por_defecto = conexion.dsn()
revisar("application_name=dexter" in por_defecto,
        "sin la variable, firma 'dexter' y no queda sin firmar")

with con_entorno(**PARTES, DB_APPLICATION_NAME="  "):
    vacio = conexion.dsn()
revisar("application_name=dexter" in vacio,
        "una variable vacia o en blanco tambien cae al valor por defecto")

with con_entorno(**PARTES, DB_APPLICATION_NAME="dexter cli raro/1"):
    escapado = conexion.dsn()
revisar(" " not in escapado.split("application_name=")[1],
        "un nombre con espacios o barras se codifica y no rompe la URL",
        escapado)

# =============================================================================
titulo("2. quien ya lo declaro, lo conserva")
# =============================================================================
with con_entorno(**{k: None for k in PARTES},
                 DATABASE_URL="postgresql://u:c@h:5432/b?application_name=el-mio",
                 DB_APPLICATION_NAME="dexter-motor"):
    ajena = conexion.dsn()
revisar(ajena.count("application_name=") == 1 and "el-mio" in ajena,
        "no se pisa el application_name que ya traia DATABASE_URL", ajena)

with con_entorno(**{k: None for k in PARTES},
                 DATABASE_URL="postgresql://u:c@h:5432/b?sslmode=require",
                 DB_APPLICATION_NAME="dexter-reloj"):
    con_query = conexion.dsn()
revisar("sslmode=require" in con_query and "application_name=dexter-reloj" in con_query,
        "si ya habia parametros, se agrega con '&' y no se pierde ninguno", con_query)

# =============================================================================
titulo("3. el apagado le da mas margen a gunicorn del que se toma")
# =============================================================================
compose = (RAIZ / "docker-compose.prod.yml").read_text(encoding="utf-8")


def segundos(texto: str) -> int | None:
    m = re.match(r"^(\d+)\s*s?$", texto.strip())
    return int(m.group(1)) if m else None


gracia = [segundos(m) for m in re.findall(r"stop_grace_period:\s*(\S+)", compose)]
graceful = [int(m) for m in re.findall(r"--graceful-timeout\s+(\d+)", compose)]
revisar(len(gracia) >= 2, f"los dos servicios declaran stop_grace_period ({len(gracia)})")
revisar(graceful and all(g is not None for g in gracia) and min(gracia) > max(graceful),
        "Docker espera MAS de lo que gunicorn tarda en cerrar "
        f"(stop_grace_period={gracia}, graceful-timeout={graceful})",
        "si Docker mata antes, el 'finally' de sesion() no corre y la "
        "transaccion queda abierta del lado del pooler")
revisar("DB_APPLICATION_NAME: dexter-motor" in compose
        and "DB_APPLICATION_NAME: dexter-reloj" in compose,
        "motor y reloj se firman distinto: es lo unico que los separa")

# =============================================================================
titulo("4. contra la base: el nombre llega, y la transaccion no queda abierta")
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] la parte con base necesita {faltan}")
else:
    import psycopg                                                # noqa: E402

    os.environ.setdefault("DBNAME", "postgres")
    marca = "dexter-prueba-identidad"
    with con_entorno(DB_APPLICATION_NAME=marca):
        url = conexion.dsn()

    observador = psycopg.connect(conexion.dsn().replace(
        f"application_name={marca}", "application_name=dexter-prueba-observador"),
        autocommit=True)
    try:
        with psycopg.connect(url) as con:          # autocommit=False, como sesion()
            cur = con.cursor()
            cur.execute("select pg_backend_pid()")
            pid = cur.fetchone()[0]
            visto = observador.execute(
                "select application_name, state from pg_stat_activity where pid = %s",
                (pid,)).fetchone()
            revisar(visto is not None and visto[0] == marca,
                    f"pg_stat_activity ve el nombre declarado ({visto[0] if visto else None!r})")
            revisar(visto is not None and visto[1] == "idle in transaction",
                    "y la sesion esta, en efecto, dentro de una transaccion abierta",
                    "si no lo estuviera, la prueba siguiente no probaria nada")

        # fuera del 'with': psycopg cierra la conexion, como hace sesion()
        quedo = observador.execute(
            "select state from pg_stat_activity where pid = %s", (pid,)).fetchone()
        revisar(quedo is None,
                "al salir del bloque no queda ninguna sesion viva",
                f"quedo en estado {quedo[0]!r}" if quedo else "")

        # y lo mismo cuando el bloque termina por excepcion
        pid2 = None
        try:
            with psycopg.connect(url) as con:
                cur = con.cursor()
                cur.execute("select pg_backend_pid()")
                pid2 = cur.fetchone()[0]
                raise RuntimeError("fallo a proposito")
        except RuntimeError:
            pass
        quedo2 = observador.execute(
            "select state from pg_stat_activity where pid = %s", (pid2,)).fetchone()
        revisar(quedo2 is None,
                "tampoco queda abierta cuando el bloque termina por excepcion",
                f"quedo en estado {quedo2[0]!r}" if quedo2 else "")
    finally:
        observador.close()

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("OK: la conexion dice quien la abrio, y no deja transacciones abiertas")
