# -*- coding: utf-8 -*-
"""
================================================================================
 GET /chat/historial  --  que la conversacion vuelva, y que vuelva SOLO la tuya
================================================================================

    DBHOST=... DBPORT=... DBNAME=... DBUSER=... DBPASSWORD=... \
        py -3.13 tests/test_chat_historial.py

CONTRA POSTGRES REAL, y no es una preferencia. Lo que se prueba es el
aislamiento: que la conversacion de una empresa no salga por la puerta de
otra, y que la de una persona no salga por la de su companero. Un aislamiento
simulado en memoria esta garantizado por el diccionario que lo simula -- el de
verdad lo da 'organization_id' y la clave (canal, usuario_externo), y eso solo
se ve contra la base.

QUE SE VIGILA
-------------
  1. Sin conversacion, lista vacia y 200. No es un error: es alguien que
     todavia no escribio.
  2. El hilo vuelve completo y EN ORDEN.
  3. La burbuja del Supervisor y el asistente general NO comparten hilo --
     es lo que justifica el prefijo 'snoc:'.
  4. Una empresa no ve la conversacion de otra.
  5. Un usuario no ve la de otro.
  6. Por aca NO se lee el hilo de WhatsApp de un cliente.

NO SE LLAMA AL MODELO. Los mensajes se siembran con 'registrar_mensaje', que
es el mismo camino que usa el turno real -- sembrar con un INSERT a mano
probaria una tabla, no el camino.
================================================================================
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os       # noqa: E402

FALTAN = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if FALTAN:
    print(f"[omitida] faltan {FALTAN}. Esta prueba exige PostgreSQL real.")
    sys.exit(0)

import json                                   # noqa: E402

import psycopg                                # noqa: E402
from psycopg.rows import dict_row             # noqa: E402

from nucleo.persistencia import db            # noqa: E402

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


def crudo():
    return psycopg.connect(db.dsn(), row_factory=dict_row)


#  'public.organization' la maneja Django, que rellena en Python varias
#  columnas NOT NULL sin default. Se derivan del catalogo para no acoplar
#  esta prueba al esquema del CRM.
_RELLENO = {"timestamp with time zone": "now()", "boolean": "false",
            "uuid": "gen_random_uuid()", "jsonb": "'{}'::jsonb",
            "integer": "0", "bigint": "0", "numeric": "0"}


def _obligatorias():
    with crudo() as con, con.cursor() as cur:
        cur.execute(
            """select column_name, data_type, character_maximum_length largo
                 from information_schema.columns
                where table_schema='public' and table_name='organization'
                  and is_nullable='NO' and column_default is null
                  and column_name not in ('id','name')""")
        filas = [dict(f) for f in cur.fetchall()]
    salida = []
    for f in filas:
        relleno = _RELLENO.get(f["data_type"])
        if relleno is None:
            relleno = f"left(gen_random_uuid()::text, {min(int(f['largo'] or 36), 36)})"
        salida.append((f["column_name"], relleno))
    return salida


OBLIGATORIAS = _obligatorias()


def sembrar_empresa(slug: str) -> str:
    extra = "".join(f", {c}" for c, _ in OBLIGATORIAS)
    valores = "".join(f", {v}" for _, v in OBLIGATORIAS)
    with crudo() as con, con.cursor() as cur:
        cur.execute(
            f"""insert into public.organization (id, name{extra})
                values (gen_random_uuid(), %s{valores}) returning id""", (slug,))
        org = str(cur.fetchone()["id"])
        cur.execute(
            """insert into asistente.tenant_config (organization_id, slug, config)
               values (%s,%s,%s)""", (org, slug, json.dumps({"version": 1})))
        con.commit()
    return org


SLUG_A = f"snocchat-a-{uuid.uuid4().hex[:8]}"
SLUG_B = f"snocchat-b-{uuid.uuid4().hex[:8]}"
ORG_A = sembrar_empresa(SLUG_A)
ORG_B = sembrar_empresa(SLUG_B)

#  Las claves tal como las arma el proxy ('lib/supervisor/chat-sesion.js').
SESION_SNOC = "snoc:usuario-1"
SESION_GENERAL = "usuario-1"          # la que usa /api/asistente
SESION_OTRO = "snoc:usuario-2"

#  El motor se importa DESPUES de sembrar: al importarlo levanta la app Flask.
from nucleo.canales import api as motor_api   # noqa: E402

#  '_config_de' lee la config del tenant, y la semilla de arriba es minima a
#  proposito -- lo que se prueba es el historial, no la validacion del
#  esquema. Se reemplaza por algo que solo tiene que existir.
motor_api._config_de = lambda tenant: object()

CLIENTE = motor_api.app.test_client()


#  'origen' lo exige 'db.validar_origen' y no es libre: 'user' solo admite
#  'cliente' y 'assistant' admite 'ia'. En este canal "cliente" quiere decir
#  "el lado que escribio", no un abonado -- es el mismo par que escribe el
#  turno real, y por eso se usa igual aca.
_ORIGEN = {"user": "cliente", "assistant": "ia"}


def decir(tenant, sesion, rol_msg, texto, canal="api"):
    db.registrar_mensaje(tenant, canal, sesion, "soporte", rol_msg, texto,
                         origen=_ORIGEN[rol_msg])


def pedir(tenant, sesion, canal=None):
    url = f"/chat/historial?tenant={tenant}&identificador_sesion={sesion}"
    if canal:
        url += f"&canal={canal}"
    r = CLIENTE.get(url)
    return r.status_code, r.get_json()


try:
    print("=" * 70)
    print(" GET /chat/historial  (PostgreSQL real)")
    print("=" * 70)

    print("\n-- 1. sin conversacion --")
    codigo, datos = pedir(SLUG_A, SESION_SNOC)
    comprobar("sin conversacion responde 200, no 404", codigo == 200, str(codigo))
    comprobar("...con una lista vacia y sin id",
              datos == {"conversacion_id": None, "mensajes": []}, str(datos))

    print("\n-- 2. el hilo vuelve, completo y en orden --")
    decir(SLUG_A, SESION_SNOC, "user", "¿Que deberia revisar primero?")
    decir(SLUG_A, SESION_SNOC, "assistant", "Hay 3 casos sin movimiento hace 9 dias.")
    decir(SLUG_A, SESION_SNOC, "user", "¿Y por que los consideras criticos?")

    codigo, datos = pedir(SLUG_A, SESION_SNOC)
    textos = [m["contenido"] for m in datos["mensajes"]]
    comprobar("vuelven los tres mensajes", len(textos) == 3, str(len(textos)))
    comprobar("...en el orden en que se escribieron",
              textos[0].startswith("¿Que deberia") and textos[2].startswith("¿Y por que"),
              str(textos))
    comprobar("...con el rol de cada uno",
              [m["rol"] for m in datos["mensajes"]] == ["user", "assistant", "user"],
              str([m["rol"] for m in datos["mensajes"]]))
    comprobar("...y el id de la conversacion", bool(datos["conversacion_id"]))

    #  EL CRITERIO DE ACEPTACION, medido donde ocurre: una peticion HTTP
    #  nueva, sin nada en memoria del navegador, devuelve el hilo anterior.
    #  Es exactamente lo que pasa al recargar la pagina.
    comprobar("CRITERIO: una peticion nueva ve la conversacion previa "
              "(= recargar la pagina)",
              "¿Y por que los consideras criticos?" in textos)

    print("\n-- 3. el Supervisor y el asistente general NO comparten hilo --")
    decir(SLUG_A, SESION_GENERAL, "user", "¿Cuanto debe la factura 881?")
    codigo, snoc = pedir(SLUG_A, SESION_SNOC)
    codigo, general = pedir(SLUG_A, SESION_GENERAL)
    comprobar("el hilo del Supervisor sigue con 3 mensajes",
              len(snoc["mensajes"]) == 3, str(len(snoc["mensajes"])))
    comprobar("...y no contiene la pregunta del asistente general",
              all("factura 881" not in m["contenido"] for m in snoc["mensajes"]))
    comprobar("son dos conversaciones distintas",
              snoc["conversacion_id"] != general["conversacion_id"],
              "el prefijo 'snoc:' es lo unico que las separa")

    print("\n-- 4. una empresa no ve la de otra --")
    decir(SLUG_B, SESION_SNOC, "user", "secreto de la empresa B")
    codigo, deA = pedir(SLUG_A, SESION_SNOC)
    codigo, deB = pedir(SLUG_B, SESION_SNOC)
    comprobar("MISMA clave de sesion, empresas distintas -> hilos distintos",
              deA["conversacion_id"] != deB["conversacion_id"])
    comprobar("A no ve el mensaje de B",
              all("secreto" not in m["contenido"] for m in deA["mensajes"]),
              str(deA["mensajes"]))
    comprobar("B solo ve el suyo", len(deB["mensajes"]) == 1, str(deB["mensajes"]))

    print("\n-- 5. un usuario no ve la de otro --")
    decir(SLUG_A, SESION_OTRO, "user", "lo que escribio el otro supervisor")
    codigo, mio = pedir(SLUG_A, SESION_SNOC)
    comprobar("no se filtra el hilo del companero",
              all("el otro supervisor" not in m["contenido"] for m in mio["mensajes"]),
              str(mio["mensajes"]))

    print("\n-- 6. por aca no se lee el WhatsApp de un cliente --")
    codigo, datos = pedir(SLUG_A, SESION_SNOC, canal="whatsapp")
    comprobar("un canal real se rechaza con 403", codigo == 403, str(codigo))
    comprobar("...y no devuelve ningun mensaje", "mensajes" not in (datos or {}),
              str(datos))

    codigo, _ = pedir(SLUG_A, SESION_SNOC, canal="inventado")
    comprobar("un canal desconocido tampoco cae al default: 400", codigo == 400,
              str(codigo))

    print("\n-- 7. parametros --")
    comprobar("sin tenant -> 400", CLIENTE.get(
        f"/chat/historial?identificador_sesion={SESION_SNOC}").status_code == 400)
    comprobar("sin identificador_sesion -> 400", CLIENTE.get(
        f"/chat/historial?tenant={SLUG_A}").status_code == 400)
    comprobar("un limite no numerico -> 400", CLIENTE.get(
        f"/chat/historial?tenant={SLUG_A}&identificador_sesion={SESION_SNOC}"
        f"&limite=muchos").status_code == 400)

    codigo, datos = pedir(SLUG_A, SESION_SNOC)
    r = CLIENTE.get(f"/chat/historial?tenant={SLUG_A}"
                    f"&identificador_sesion={SESION_SNOC}&limite=2")
    comprobar("el limite recorta, y deja los MAS RECIENTES",
              len(r.get_json()["mensajes"]) == 2
              and r.get_json()["mensajes"][-1]["contenido"].startswith("¿Y por que"),
              str(r.get_json()["mensajes"]))

    print("\n-- 8. no se filtra nada de la bandeja --")
    codigo, datos = pedir(SLUG_A, SESION_SNOC)
    claves = set(datos["mensajes"][0].keys())
    comprobar("cada mensaje trae solo id, rol, contenido y creado_en",
              claves == {"id", "rol", "contenido", "creado_en"}, str(claves))

finally:
    try:
        with crudo() as con, con.cursor() as cur:
            for org in (ORG_A, ORG_B):
                cur.execute("""delete from asistente.messages where conversation_id in
                                 (select id from asistente.conversations
                                   where organization_id=%s)""", (org,))
                cur.execute("delete from asistente.conversations where organization_id=%s", (org,))
                cur.execute("delete from asistente.tenant_config where organization_id=%s", (org,))
                cur.execute("delete from public.organization where id=%s", (org,))
            con.commit()
        print("\n  (las empresas de prueba se borraron)")
    except Exception as e:
        print(f"\n  [aviso] no se pudo limpiar: {type(e).__name__}")

print("\n" + "=" * 70)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("TODO EN VERDE  --  contra PostgreSQL real")
print("=" * 70)
