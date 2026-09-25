# -*- coding: utf-8 -*-
"""
================================================================================
 LOS TICKETS DE UNA EMPRESA NO SE CUENTAN COMO DE LA OTRA
================================================================================

    ALLOW_EPHEMERAL_TEST_DB_SETUP=1 DBHOST=localhost DBPORT=55435 \\
      DBNAME=test_motor DBUSER=motor DBPASSWORD=motor \\
      py -3.13 tests/test_aislamiento_tickets_conocidos.py

Por que existe
--------------
'importacion_io.tickets_conocidos()' abria una conexion CRUDA y leia:

    select trim(ticket_operativo) from asistente.conversations
    where coalesce(trim(ticket_operativo),'') <> ''

Sin filtro de organizacion. 'motor_user' tiene BYPASSRLS --lo necesita para UNA
consulta, la que averigua a que organizacion pertenece el tenant-- y una
conexion cruda se queda con ese privilegio puesto.

LO QUE ESO PRODUCE NO ES SOLO UNA LECTURA CRUZADA. Ese conjunto decide la
AUTORIA de un ticket: si el numero esta ahi, el importador concluye "lo abrio
Dexter". Con dos ISP en la misma base, el ticket 92100 de la empresa B haria
que el 92100 de la empresa A se clasificara como abierto por Dexter cuando lo
abrio una persona. Y esa clasificacion se PERSISTE en
'Case.external_created_by_type'.

Lo que se fija
--------------
 1. Con el tenant A fijado, solo se ven los tickets de A.
 2. Con B, solo los de B.
 3. El mismo numero de ticket en las dos empresas no se confunde.
 4. Sin contexto no se ve NADA -- fail-closed, no fail-open.
 5. La politica actua aunque el rol que conecta tenga BYPASSRLS, porque
    'SET ROLE app_backend' la vuelve a activar. Es la pieza de la que depende
    todo el diseno.
================================================================================
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


def _dsn():
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        print(f"  [saltado] faltan {faltan}: esta prueba necesita una base "
              f"efimera con el esquema del motor. Ver cli/esquema_de_pruebas.py")
        raise SystemExit(0)
    return (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
            f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
            f"password={os.environ['DBPASSWORD']} sslmode=disable")


import psycopg                                                    # noqa: E402

ORG_A = uuid.UUID("00000000-0000-4000-8000-0000000000aa")
ORG_B = uuid.UUID("00000000-0000-4000-8000-0000000000bb")
TICKET_COMPARTIDO = "92100"


def sembrar(con):
    """Dos empresas, cada una con su conversacion. Una comparte el numero."""
    with con.cursor() as cur:
        cur.execute("select column_name, data_type from information_schema.columns "
                    "where table_schema='public' and table_name='organization' "
                    "and is_nullable='NO' and column_default is null")
        obligatorias = cur.fetchall()

        for org, nombre in ((ORG_A, "Empresa A"), (ORG_B, "Empresa B")):
            valores = {"id": str(org), "name": nombre,
                       "api_key": f"clave-{org}", "company_name": nombre}
            for campo, tipo in obligatorias:
                if campo in valores:
                    continue
                if "timestamp" in tipo or tipo == "date":
                    valores[campo] = "now()"
                elif tipo == "boolean":
                    valores[campo] = True
                elif tipo in ("integer", "bigint", "smallint", "numeric",
                              "double precision", "real"):
                    valores[campo] = 0
                elif tipo in ("json", "jsonb", "ARRAY"):
                    valores[campo] = "{}"
                else:
                    valores[campo] = ""
            cols = ", ".join(f'"{k}"' for k in valores)
            marcas, params = [], []
            for k, v in valores.items():
                if v == "now()":
                    marcas.append("now()")
                else:
                    marcas.append("%s")
                    params.append(v)
            cur.execute(f"insert into public.organization ({cols}) "
                        f"values ({', '.join(marcas)}) "
                        f"on conflict (id) do nothing", params)

        cur.execute("delete from asistente.conversations where organization_id in (%s, %s)",
                    (str(ORG_A), str(ORG_B)))
        # A: dos tickets, uno de ellos el compartido.
        for org, tickets in ((ORG_A, [TICKET_COMPARTIDO, "70001"]),
                             (ORG_B, [TICKET_COMPARTIDO, "80002"])):
            for t in tickets:
                cur.execute(
                    "insert into asistente.conversations "
                    "(organization_id, canal, usuario_externo, ticket_operativo) "
                    "values (%s, 'whatsapp', %s, %s)",
                    (str(org), f"user-{org}-{t}", t))
    con.commit()


def leer_como(con, org):
    """Lo que ve el codigo del importador con ese tenant fijado."""
    with con.cursor() as cur:
        cur.execute("set local role app_backend")
        cur.execute("select set_config('app.current_tenant', %s, true)",
                    (str(org) if org else "",))
        cur.execute("select trim(ticket_operativo) from asistente.conversations "
                    "where coalesce(trim(ticket_operativo),'') <> ''")
        visto = {str(f[0]).strip() for f in cur.fetchall()}
        cur.execute("reset role")
    con.rollback()
    return visto


print("=" * 74)
print("  la consulta de tickets conocidos, bajo app_backend")
print("=" * 74)

con = psycopg.connect(_dsn())
try:
    sembrar(con)

    # --- 5: la pieza de la que depende todo ---------------------------------
    with con.cursor() as cur:
        cur.execute("select rolsuper, rolbypassrls from pg_roles "
                    "where rolname = current_user")
        superusuario, evade = cur.fetchone()
    con.rollback()
    print(f"\n  el rol que CONECTA: rolsuper={superusuario}, "
          f"rolbypassrls={evade}")
    print("  (si evade RLS y aun asi el aislamiento funciona, es porque")
    print("   'SET ROLE app_backend' lo vuelve a activar -- que es la pieza")
    print("   de la que depende el diseno entero)\n")

    ve_a = leer_como(con, ORG_A)
    ve_b = leer_como(con, ORG_B)
    ve_sin = leer_como(con, None)

    revisar(ve_a == {TICKET_COMPARTIDO, "70001"},
            "con el tenant A fijado se ven SOLO los tickets de A",
            f"vio {sorted(ve_a)}")
    revisar(ve_b == {TICKET_COMPARTIDO, "80002"},
            "con el tenant B fijado se ven SOLO los de B",
            f"vio {sorted(ve_b)}")
    revisar("80002" not in ve_a,
            "el ticket exclusivo de B no aparece para A",
            f"A vio {sorted(ve_a)} -- eso clasificaria un ticket de A como "
            f"abierto por Dexter usando evidencia de otra empresa")
    revisar("70001" not in ve_b,
            "y el de A no aparece para B",
            f"B vio {sorted(ve_b)}")

    # --- 4: fail-closed -----------------------------------------------------
    revisar(ve_sin == set(),
            "SIN contexto no se ve NADA (fail-closed, no fail-open)",
            f"vio {sorted(ve_sin)} -- 'org_actual()' devuelve NULL sin "
            f"contexto y 'organization_id = NULL' nunca es cierto; si esto "
            f"trae filas, la politica no esta haciendo su trabajo")

    # --- 3: el numero compartido, que es el caso que importa ---------------
    print()
    print("=" * 74)
    print("  el mismo numero de ticket en las dos empresas")
    print("=" * 74)
    revisar(TICKET_COMPARTIDO in ve_a and TICKET_COMPARTIDO in ve_b,
            f"el ticket {TICKET_COMPARTIDO} existe en las dos y cada una ve el suyo")
    revisar(len(ve_a) == 2 and len(ve_b) == 2,
            "cada empresa ve exactamente dos, no cuatro",
            f"A={sorted(ve_a)} B={sorted(ve_b)} -- si alguna ve cuatro, la "
            f"consulta volvio a leer sin filtro")

    # --- lo que pasaba ANTES, para que quede medido ------------------------
    print()
    print("=" * 74)
    print("  lo que veia la conexion cruda (sin bajar de rol)")
    print("=" * 74)
    with con.cursor() as cur:
        cur.execute("select trim(ticket_operativo) from asistente.conversations "
                    "where coalesce(trim(ticket_operativo),'') <> ''")
        crudo = {str(f[0]).strip() for f in cur.fetchall()}
    con.rollback()

    if superusuario or evade:
        revisar(crudo >= {TICKET_COMPARTIDO, "70001", "80002"},
                "la conexion cruda SI ve las dos empresas (el defecto, medido)",
                f"vio {sorted(crudo)}")
        print(f"       la cruda vio {len(crudo)} ticket(s); cada tenant ve 2")
    else:
        print("  [i] el rol que conecta no evade RLS en esta base, asi que el "
              "defecto no se puede reproducir aca")
    # --- las DOS capas, por separado --------------------------------------------
    print()
    print("=" * 74)
    print("  el filtro explicito, sin depender de RLS")
    print("=" * 74)

    # La consulta lleva un WHERE por organizacion ADEMAS de la politica. Se
    # comprueba aca sin bajar de rol: si algun dia alguien desactiva la politica, o
    # si esta consulta termina corriendo bajo un rol que la evade, el filtro sigue.
    with con.cursor() as cur:
        cur.execute("select trim(ticket_operativo) from asistente.conversations "
                    "where organization_id = %s "
                    "  and coalesce(trim(ticket_operativo),'') <> ''", (str(ORG_A),))
        solo_filtro = {str(f[0]).strip() for f in cur.fetchall()}
    con.rollback()

    revisar(solo_filtro == {TICKET_COMPARTIDO, "70001"},
            "con el WHERE explicito y SIN bajar de rol, A ve solo lo suyo",
            f"vio {sorted(solo_filtro)} -- el filtro es la segunda capa: RLS es la "
            f"defensa de fondo, no el unico filtro")

    fuente = (RAIZ / "nucleo" / "seguimiento"
              / "importacion_io.py").read_text(encoding="utf-8")
    i = fuente.find("asistente.conversations")
    tramo = fuente[max(0, i - 400):i + 300]
    revisar("with sesion(tenant)" in tramo,
            "el codigo usa sesion(tenant) -- primera capa")
    revisar("organization_id = %s" in tramo,
            "y ademas lleva el filtro explicito parametrizado -- segunda capa",
            "un filtro interpolado seria inyeccion; uno ausente deja la consulta "
            "dependiendo solo de que la politica siga existiendo")
    revisar("psycopg.connect" not in tramo,
            "y no queda ninguna conexion cruda")
finally:
    con.close()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Los tickets de una empresa no se cuentan como de la otra.")
print("=" * 74)
