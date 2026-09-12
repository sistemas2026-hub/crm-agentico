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
# El tenant sintetico. No se parece a ninguna empresa real a proposito: la
# suite generica tiene que poder correr sin que exista ningun cliente.
TENANT_PRUEBAS = os.environ.get("TENANT_PRUEBAS", "test_tenant")
ORG_PRUEBAS = uuid.UUID("00000000-0000-4000-8000-000000000001")

# La configuracion sintetica MINIMA que el esquema acepta: identidad, persona,
# un rol, rag y llm. Nada mas, y nada de ningun cliente -- ni prompts, ni
# herramientas, ni corpus, ni numeros de telefono. Comprobada contra el
# validador real en 'tests/test_tenant_sintetico.py'.
CONFIG_MINIMA = {
    "identidad": {
        "slug": "test-tenant",
        "nombre_legal": "Tenant Sintetico De Pruebas",
        "nombre_comercial": "Pruebas",
        "sector": "isp",
        "zona_horaria": "America/Bogota",
        "idioma": "es",
    },
    "persona": {"nombre_asistente": "Asistente De Pruebas"},
    "roles": {"pruebas": {}},
    "rag": {
        "modelo_embeddings": "text-embedding-3-large",
        "mensaje_sin_resultados": "No hay informacion sobre eso.",
    },
    "llm": {"modelo_por_defecto": "deepseek-v4-flash"},
    "herramientas": [],
}


# --- las defensas ------------------------------------------------------------
#
# El hostname NO alcanza. 'localhost' puede ser la punta de un tunel SSH contra
# la base de produccion, y esta herramienta CREA Y ESCRIBE ESQUEMA. Que el
# destino parezca local es la clase de suposicion que este proyecto ya pago una
# vez confundiendo bases.
#
# Son cinco condiciones simultaneas. Y no hay bandera de escape: una opcion
# para saltarlas convierte cinco defensas en cero el dia que alguien tiene
# prisa, que es el dia en que hacen falta.
# 'tests/test_esquema_de_pruebas_se_niega.py' lo fija.

BANDERA = "ALLOW_EPHEMERAL_TEST_DB_SETUP"

# La base tiene que llamarse como una base de pruebas. Es la condicion que un
# tunel no puede satisfacer sin que alguien lo haya hecho a proposito.
PREFIJOS_PERMITIDOS = ("test", "prueba", "pruebas", "ci_", "motor_test",
                       "efimera")

# Y nunca, pase lo que pase, contra una de estas.
NOMBRES_PROHIBIDOS = {"postgres", "supabase", "produccion", "production",
                      "prod", "crm_db", "rapilink", "main", "master"}

# El marcador que esta herramienta deja al preparar una base. Si el esquema ya
# tiene datos y NO tiene el marcador, no es una base de pruebas de esta
# herramienta y no se toca.
TABLA_MARCADOR = "public._base_de_pruebas_efimera"


def _dsn() -> str:
    """El destino, comprobado cinco veces antes de escribir una sola linea."""
    if os.environ.get(BANDERA) != "1":
        raise SystemExit(
            f"Falta {BANDERA}=1.\n"
            f"Esta herramienta CREA Y ESCRIBE ESQUEMA. Exigir una bandera "
            f"explicita evita que corra por accidente desde un script o un "
            f"historial de shell.")

    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        raise SystemExit(
            f"Faltan {faltan}. Este comando NO lee el .env a proposito: el .env "
            f"apunta a la base real, y tomarlo de ahi es exactamente el "
            f"accidente que se quiere evitar.\n"
            f"Ejemplo:\n"
            f"  {BANDERA}=1 DBHOST=localhost DBPORT=55435 DBNAME=motor_test "
            f"DBUSER=motor DBPASSWORD=motor py -3.13 cli/esquema_de_pruebas.py")

    base = os.environ["DBNAME"]
    if base.lower() in NOMBRES_PROHIBIDOS:
        raise SystemExit(
            f"DBNAME='{base}' esta en la lista de nombres prohibidos. "
            f"Esta herramienta no corre contra una base con nombre de base real.")
    if not any(base.lower().startswith(p) for p in PREFIJOS_PERMITIDOS):
        raise SystemExit(
            f"DBNAME='{base}' no empieza por ninguno de {list(PREFIJOS_PERMITIDOS)}.\n"
            f"El nombre es la unica condicion que un tunel SSH contra produccion "
            f"no puede satisfacer por accidente: 'localhost' si puede.")

    return (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
            f"dbname={base} user={os.environ['DBUSER']} "
            f"password={os.environ['DBPASSWORD']} sslmode=disable")


def confirmar_destino(conn) -> None:
    """
    Lo que la base dice DE SI MISMA, que es lo unico que no se puede fingir
    desde el entorno.

    Se pregunta despues de conectar y antes de escribir: el nombre de la base,
    el usuario efectivo y la direccion del servidor salen del servidor, no de
    las variables con las que uno creia estar conectandose.
    """
    with conn.cursor() as cur:
        cur.execute("select current_database(), current_user, "
                    "inet_server_addr(), version()")
        base, usuario, servidor, version = cur.fetchone()

    print(f"  destino : {base} @ {servidor or 'socket local'}")
    print(f"  usuario : {usuario}")
    print(f"  servidor: {str(version).split(',')[0]}")
    print()

    if base.lower() in NOMBRES_PROHIBIDOS:
        raise SystemExit(
            f"La base dice llamarse '{base}', que esta prohibida. Las variables "
            f"decian otra cosa: eso es exactamente un tunel o un alias.")
    if not any(base.lower().startswith(p) for p in PREFIJOS_PERMITIDOS):
        raise SystemExit(
            f"La base dice llamarse '{base}', que no tiene prefijo de pruebas.")


def comprobar_marcador(conn) -> None:
    """
    Una base ya poblada y sin marcador no se toca.

    El marcador lo deja esta misma herramienta. Si el esquema 'asistente' ya
    existe con tablas pero nadie dejo el marcador, esa base la preparo otra
    cosa -- y "otra cosa" incluye "produccion".
    """
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s) is not null", (TABLA_MARCADOR,))
        tiene_marcador = cur.fetchone()[0]

        cur.execute("select count(*) from information_schema.tables "
                    "where table_schema = 'asistente'")
        poblada = cur.fetchone()[0] > 0

    if poblada and not tiene_marcador:
        raise SystemExit(
            f"El esquema 'asistente' ya tiene tablas y esta base NO tiene el "
            f"marcador {TABLA_MARCADOR}.\n"
            f"Esta base la preparo otra cosa. Esta herramienta solo escribe "
            f"sobre bases vacias o sobre las que ella misma preparo.")

    with conn.cursor() as cur:
        cur.execute(f"create table if not exists {TABLA_MARCADOR} "
                    f"(creada_en timestamptz default now(), "
                    f" por text default 'cli/esquema_de_pruebas.py')")
    conn.commit()


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
        # La semilla de un tenant REAL solo se usa si alguien la pide por
        # nombre. Por defecto ('test_tenant') no existe ninguna, y la config
        # sintetica de arriba es la que entra: la suite generica no puede
        # depender de que exista un cliente.
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
        confirmar_destino(conn)
        comprobar_marcador(conn)
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
