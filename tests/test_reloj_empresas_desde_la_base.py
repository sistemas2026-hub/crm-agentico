# -*- coding: utf-8 -*-
"""
El reloj sabe que empresas atender por la BASE, no por la carpeta tenants/.

    py -3.13 tests/test_reloj_empresas_desde_la_base.py

POR QUE EXISTE
--------------
Hasta el 31/10/2026 'reloj.tenants_conocidos' listaba 'tenants/*.config.yaml'
de la IMAGEN del contenedor. Dar de alta un ISP es una fila en
'asistente.tenant_config' (CLAUDE.md 3.1): con el listado por archivo, una
empresa dada de alta desde la plataforma no recibia NINGUN trabajo del reloj
-- ni cierres, ni importacion, ni reconciliacion -- hasta que alguien
commiteara su YAML y redesplegara. Y una empresa dada de baja seguia
recibiendolos mientras su archivo siguiera en el repositorio.

Lo que se prueba:

  1. El listado sale de 'db.tenants_activos', aunque la carpeta diga otra cosa.
  2. Sin base, el ciclo no atiende a NADIE. No cae al YAML: cargar la config
     del archivo cuando la base no contesta seria servir una configuracion
     que nadie puede editar, para trabajos autonomos.
  3. El reconciliador usa el mismo listado.
  4. Contra PostgreSQL REAL (si se le da RELOJ_PG_ADMIN): solo las activas, en
     orden, y una dada de baja no aparece.

La parte 4 se niega a correr contra otro host que el Postgres descartable
'pg-reloj', y sin la variable se reporta OMITIDA, no en verde:

    docker run --rm --network red-reloj -v <repo>:/repo:ro -v <vacio>:/repo/.env:ro \
      -w /repo -e PYTHONPATH=/repo \
      -e RELOJ_PG_ADMIN=postgres://postgres:prueba@pg-reloj:5432/postgres \
      dexter-motor:latest python tests/test_reloj_empresas_desde_la_base.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo import reloj  # noqa: E402
from nucleo.persistencia import db  # noqa: E402

fallos: list[str] = []


def revisar(cond: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if cond else "  [FALLA] ") + que)
    if not cond:
        fallos.append(que)
        if detalle:
            print(f"          {detalle}")


class Sustituir:
    """Cambia atributos de modulos y los deja como estaban al salir."""

    def __init__(self, *cambios):
        self.cambios = cambios
        self.previos = []

    def __enter__(self):
        for mod, nombre, valor in self.cambios:
            self.previos.append((mod, nombre, getattr(mod, nombre)))
            setattr(mod, nombre, valor)
        return self

    def __exit__(self, *_):
        for mod, nombre, valor in reversed(self.previos):
            setattr(mod, nombre, valor)
        return False


def _caida():
    raise SystemExit("faltan los datos de conexion")


print("\n--- 1. el listado sale de la base, no de la carpeta ---")
en_carpeta = sorted(p.name for p in (RAIZ / "tenants").glob("*.config.yaml"))
revisar(bool(en_carpeta), "la carpeta tenants/ tiene semillas (si no, la prueba no prueba nada)",
        f"encontradas: {en_carpeta}")
with Sustituir((db, "tenants_activos", lambda: ["dada-de-alta-desde-la-plataforma"])):
    listado = reloj.tenants_conocidos()
revisar(listado == ["dada-de-alta-desde-la-plataforma"],
        "una empresa que solo esta en la base recibe trabajos, y una semilla sin fila no",
        f"listado: {listado}")


with Sustituir((db, "tenants_activos", lambda: [])):
    listado = reloj.tenants_conocidos()
revisar(listado == [],
        "una base sin empresas activas es 'nadie', no un motivo para mirar la carpeta",
        f"listado: {listado}")


print("\n--- 2. sin base, nadie: no cae al YAML ---")
avisos: list[tuple] = []
with Sustituir((db, "tenants_activos", _caida),
               (reloj, "registrar", lambda *a, **k: avisos.append((a, k)))):
    listado = reloj.tenants_conocidos()
revisar(listado == [], "con la base caida el listado queda vacio", f"listado: {listado}")
revisar(any("no se pudo listar las empresas" in " ".join(map(str, a)) for a, _ in avisos),
        "y lo dice en el log, con texto fijo",
        f"avisos: {avisos}")

cargadas: list[str] = []
with Sustituir((db, "tenants_activos", _caida),
               (reloj, "registrar", lambda *a, **k: None),
               (reloj.fuente, "cargar", lambda t, r=None: cargadas.append(t))):
    salida = reloj.una_pasada(seco=True)
revisar(cargadas == [] and not salida,
        "una pasada con la base caida no carga la config de ninguna empresa",
        f"cargadas: {cargadas}, salida: {salida}")


print("\n--- 3. el reconciliador usa el mismo listado ---")
from nucleo.relevo import worker_reconciliador  # noqa: E402

with Sustituir((db, "tenants_activos", lambda: ["solo-en-la-base"])):
    del_reconciliador = worker_reconciliador._tenants()
revisar(del_reconciliador == ["solo-en-la-base"],
        "el reconciliador atiende a las empresas de la base",
        f"listado: {del_reconciliador}")


print("\n--- 4. contra PostgreSQL real ---")
ADMIN = os.environ.get("RELOJ_PG_ADMIN", "")
if not ADMIN:
    print("  OMITIDA: falta RELOJ_PG_ADMIN (ver el encabezado). Ninguna comprobacion "
          "de esta parte se ejecuto.")
elif urlparse(ADMIN).hostname != "pg-reloj":
    print(f"  me niego: el host {urlparse(ADMIN).hostname!r} no es el Postgres "
          f"descartable 'pg-reloj'.")
    raise SystemExit(2)
else:
    import psycopg

    base = f"reloj_{uuid.uuid4().hex[:8]}"
    url = urlparse(ADMIN)
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f"create database {base}")
    try:
        with psycopg.connect(ADMIN.rsplit("/", 1)[0] + f"/{base}", autocommit=True) as c:
            #  Las columnas que importan, como las declara
            #  supabase/202608042055_schema.sql.
            c.execute("""
                create table public.organization (id uuid primary key);
                create schema asistente;
                create table asistente.tenant_config (
                  organization_id uuid primary key references public.organization(id),
                  slug text not null unique,
                  config jsonb not null default '{}'::jsonb,
                  config_version integer not null default 1,
                  activo boolean not null default true);
            """)
            for slug, activo in (("zeta", True), ("alfa", True), ("dada-de-baja", False)):
                org = str(uuid.uuid4())
                c.execute("insert into public.organization values (%s)", (org,))
                c.execute("insert into asistente.tenant_config (organization_id, slug, activo) "
                          "values (%s, %s, %s)", (org, slug, activo))
        previo = {k: os.environ.get(k) for k in
                  ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD", "DATABASE_URL")}
        os.environ.update({"DBHOST": url.hostname, "DBPORT": str(url.port or 5432),
                           "DBNAME": base, "DBUSER": url.username,
                           "DBPASSWORD": url.password})
        try:
            del_motor = db.tenants_activos()
            del_reloj = reloj.tenants_conocidos()
        finally:
            for k, v in previo.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        revisar(del_motor == ["alfa", "zeta"],
                "la base devuelve las activas, ordenadas, y no la dada de baja",
                f"devolvio: {del_motor}")
        revisar(del_reloj == del_motor, "el reloj lista exactamente eso",
                f"reloj: {del_reloj}")
    finally:
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(f"drop database if exists {base} with (force)")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] El reloj sabe que empresas atender por la base, y sin base no atiende a nadie.")
