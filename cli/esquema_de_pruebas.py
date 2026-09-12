# -*- coding: utf-8 -*-
"""
================================================================================
 EL ESQUEMA DEL MOTOR, EN UNA BASE EFIMERA  --  para poder probar sin produccion
================================================================================

    py -3.13 cli/esquema_de_pruebas.py                 # aplica las migraciones
    py -3.13 cli/esquema_de_pruebas.py --con-tenant    # y siembra un tenant falso

POR QUE EXISTE
--------------
Tres pruebas del motor exigen el esquema 'asistente' --tenant_config,
documentos, la funcion 'match_chunks' de pgvector-- y hasta ahora la unica base
que lo tenia era la de PRODUCCION. La consecuencia practica es que esas pruebas
o se corrian contra produccion o no se corrian, y lo segundo es lo que venia
pasando: quedaban fuera de todo reporte con un "no ejecutable".

Ninguna de las dos es aceptable. Las migraciones de 'supabase/' son la
definicion del esquema y estan versionadas: aplicarlas a un PostgreSQL efimero
da exactamente la misma forma, sin copiar un solo dato de nadie.

LOS DATOS SON SINTETICOS, Y TIENEN QUE SERLO
--------------------------------------------
El tenant que siembra '--con-tenant' se llama 'pruebas' y su configuracion es
minima: lo justo para que 'nucleo.persistencia.db.sesion' resuelva una
organizacion. No hay clientes, ni telefonos, ni credenciales. Si algun dia
alguien necesita mas, que lo invente aca -- no que lo traiga.

USO
---
    DBHOST=localhost DBPORT=55435 DBNAME=motor DBUSER=motor DBPASSWORD=motor \\
        py -3.13 cli/esquema_de_pruebas.py --con-tenant

    DBHOST=... py -3.13 tests/test_aprobacion_documentos.py
================================================================================
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

MIGRACIONES = RAIZ / "supabase"

# El tenant sintetico. El slug no se parece a ninguna empresa real a proposito.
TENANT_PRUEBAS = os.environ.get("TENANT_PRUEBAS", "pruebas")
ORG_PRUEBAS = uuid.UUID("00000000-0000-4000-8000-000000000001")

CONFIG_MINIMA = {
    "identidad": {
        "slug": TENANT_PRUEBAS,
        "nombre_legal": "Empresa De Pruebas SAS",
        "nombre_comercial": "Pruebas",
        "sector": "isp",
        "zona_horaria": "America/Bogota",
        "idioma": "es",
    },
    "roles": {},
    "herramientas": [],
}


def _dsn() -> str:
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        raise SystemExit(
            f"Faltan {faltan}. Este comando NO lee el .env a proposito: apuntar "
            f"sin querer a produccion es exactamente lo que viene a evitar.\n"
            f"Ejemplo:\n"
            f"  DBHOST=localhost DBPORT=55435 DBNAME=motor DBUSER=motor "
            f"DBPASSWORD=motor py -3.13 cli/esquema_de_pruebas.py")

    host = os.environ["DBHOST"]
    if host not in ("localhost", "127.0.0.1", "db", "pg-motor", "::1"):
        raise SystemExit(
            f"DBHOST='{host}' no parece una base local o de contenedor. Este "
            f"comando CREA Y BORRA esquemas: no corre contra nada remoto.")
    return (f"host={host} port={os.environ['DBPORT']} "
            f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
            f"password={os.environ['DBPASSWORD']} sslmode=disable")


def aplicar(conn) -> int:
    """Las migraciones de supabase/, en orden de nombre, que es su orden."""
    archivos = sorted(MIGRACIONES.glob("*.sql"))
    if not archivos:
        raise SystemExit(f"No hay migraciones en {MIGRACIONES}")

    aplicadas = 0
    for ruta in archivos:
        sql = ruta.read_text(encoding="utf-8")
        with conn.cursor() as cur:
            try:
                cur.execute(sql)
                conn.commit()
                aplicadas += 1
                print(f"  [ok] {ruta.name}")
            except Exception as e:                            # noqa: BLE001
                conn.rollback()
                # Una migracion que no aplica no siempre es un problema: varias
                # son idempotentes y otras dependen de extensiones que esta
                # imagen puede no traer. Se dice cual y se sigue, porque lo que
                # importa es si al final existe lo que las pruebas necesitan --
                # y eso se comprueba abajo, no aca.
                print(f"  [--] {ruta.name}: {type(e).__name__}: "
                      f"{str(e).splitlines()[0][:90]}")
    return aplicadas


def sembrar_tenant(conn) -> None:
    """
    Un tenant sintetico, lo minimo para que 'sesion()' resuelva una org.

    La organizacion va PRIMERO: 'asistente.tenant_config.organization_id' es
    una FK contra 'public.organization', que la crea el CRM. Es la misma
    dependencia que hace que las migraciones de 'supabase/' tengan que correr
    DESPUES de las de Django.
    """
    import json

    with conn.cursor() as cur:
        # Las columnas obligatorias se leen del ESQUEMA y no se enumeran a mano:
        # 'organization' tiene una veintena de NOT NULL sin default y la lista
        # cambia con cada migracion del CRM. Escribirla aca la dejaria vieja al
        # primer campo nuevo, y el sintoma seria un NotNullViolation que no
        # explica nada.
        cur.execute("""
            select column_name, data_type
            from information_schema.columns
            where table_schema = 'public' and table_name = 'organization'
              and is_nullable = 'NO' and column_default is null
        """)
        obligatorias = cur.fetchall()

        valores = {"id": str(ORG_PRUEBAS), "name": "Empresa De Pruebas",
                   "api_key": f"clave-sintetica-{ORG_PRUEBAS}"}
        for nombre, tipo in obligatorias:
            if nombre in valores:
                continue
            if "timestamp" in tipo or tipo == "date":
                valores[nombre] = "now()"
            elif tipo == "boolean":
                valores[nombre] = True
            elif tipo in ("integer", "bigint", "smallint", "numeric",
                          "double precision", "real"):
                valores[nombre] = 0
            elif tipo in ("json", "jsonb"):
                valores[nombre] = "{}"
            elif tipo == "ARRAY":
                valores[nombre] = "{}"
            else:
                valores[nombre] = ""
        valores.setdefault("company_name", "Empresa De Pruebas")

        columnas = ", ".join(f'"{k}"' for k in valores)
        marcas, params = [], []
        for k, v in valores.items():
            if v == "now()":
                marcas.append("now()")
            else:
                marcas.append("%s")
                params.append(v)
        cur.execute(
            f"insert into public.organization ({columnas}) "
            f"values ({', '.join(marcas)}) on conflict (id) do nothing", params)

        # Si el repo trae una semilla YAML para este slug, se usa esa: tiene
        # roles y la seccion 'rag' que las pruebas necesitan. Es una SEMILLA
        # versionada en el repositorio, no un volcado de produccion -- los
        # secretos viven en 'tenant_secrets' y no estan ahi.
        semilla = RAIZ / "tenants" / f"{TENANT_PRUEBAS}.config.yaml"
        if semilla.exists():
            import yaml

            config = yaml.safe_load(semilla.read_text(encoding="utf-8"))
            config.setdefault("identidad", {})["slug"] = TENANT_PRUEBAS
            print(f"  [i] config desde la semilla {semilla.name}")
        else:
            config = CONFIG_MINIMA
            print(f"  [i] config minima (no hay {semilla.name})")

        cur.execute("""
            insert into asistente.tenant_config (organization_id, slug, config,
                                                 config_version)
            values (%s, %s, %s, 1)
            on conflict (organization_id) do update
              set slug = excluded.slug, config = excluded.config
        """, (str(ORG_PRUEBAS), TENANT_PRUEBAS, json.dumps(config, default=str)))
    conn.commit()
    print(f"  [ok] tenant sintetico '{TENANT_PRUEBAS}' (org {ORG_PRUEBAS})")


def comprobar(conn) -> list[str]:
    """Lo que las pruebas necesitan de verdad. Si falta algo, se dice cual."""
    faltan = []
    with conn.cursor() as cur:
        cur.execute("select 1 from information_schema.schemata "
                    "where schema_name = 'asistente'")
        if not cur.fetchone():
            faltan.append("el esquema 'asistente'")

        for tabla in ("tenant_config", "documents", "document_chunks"):
            cur.execute("select 1 from information_schema.tables "
                        "where table_schema='asistente' and table_name=%s",
                        (tabla,))
            if not cur.fetchone():
                faltan.append(f"asistente.{tabla}")

        cur.execute("select 1 from pg_proc p join pg_namespace n "
                    "on n.oid = p.pronamespace where p.proname = 'match_chunks'")
        if not cur.fetchone():
            faltan.append("la funcion match_chunks")
    return faltan


def main() -> int:
    import psycopg

    print("=" * 74)
    print("  ESQUEMA DEL MOTOR EN UNA BASE EFIMERA")
    print("=" * 74)
    print(f"  migraciones: {MIGRACIONES}")
    print()

    with psycopg.connect(_dsn()) as conn:
        n = aplicar(conn)
        print(f"\n  {n} migracion(es) aplicadas")

        if "--con-tenant" in sys.argv:
            sembrar_tenant(conn)

        faltan = comprobar(conn)

    print()
    print("=" * 74)
    if faltan:
        print("  FALTA lo que las pruebas necesitan:")
        for f in faltan:
            print(f"    - {f}")
        print("=" * 74)
        return 1
    print("  [OK] El esquema tiene lo que las pruebas del motor necesitan.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
