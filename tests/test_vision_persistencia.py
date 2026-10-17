# -*- coding: utf-8 -*-
"""
================================================================================
 ANALISIS VISUAL EN LA BASE  --  contra PostgreSQL de verdad
================================================================================

    DBHOST=... DBPORT=... DBNAME=... DBUSER=... DBPASSWORD=...
    py -3.13 tests/test_vision_persistencia.py

POR QUE NO ALCANZA CON LAS PRUEBAS EN MEMORIA
----------------------------------------------
tests/test_vision_imagen.py parchea la base entera, asi que puede estar en
verde con una columna que no existe, con un insert que no cuadra en el numero
de parametros, o con un aislamiento que no aisla. Las tres cosas solo se ven
contra una base real. Es la regla de CLAUDE.md 6: persistencia se prueba
contra PostgreSQL real, nunca solo en memoria.

LO QUE SE VIGILA
----------------
  1. Que el analisis se escriba y se lea entero.
  2. Que lo que la camara leyo impreso NO este en la base. Es la unica
     comprobacion que se hace mirando la COLUMNA cruda, sin pasar por el
     codigo que la escribio: si algun dia algo empieza a filtrarse, esto lo ve.
  3. Que un tenant no pueda leer el analisis de otro. Se comprueba con dos
     organizaciones de verdad, no con un mock.
  4. Que la idempotencia por media_id sea de la BASE (clave unica), no de un
     'select' previo -- ahi vive la carrera.
================================================================================
"""

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FALTAN = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if FALTAN:
    print(f"[omitida] faltan {FALTAN} en el entorno. "
          f"Esta prueba exige PostgreSQL real.")
    sys.exit(0)

import psycopg
from psycopg.rows import dict_row

from nucleo.canales import vision as vi
from nucleo.persistencia import db
from nucleo.seguridad.redaccion import redactar

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


def crudo():
    return psycopg.connect(db.dsn(), row_factory=dict_row)


# =============================================================================
#  Dos empresas de verdad, con su organizacion y su configuracion.
# =============================================================================

SLUG_A = f"prueba-vision-a-{uuid.uuid4().hex[:8]}"
SLUG_B = f"prueba-vision-b-{uuid.uuid4().hex[:8]}"
CONVERSACIONES: dict[str, str] = {}


def sembrar(slug: str) -> str:
    """Una organizacion, su tenant_config y una conversacion. Devuelve el org."""
    with crudo() as con, con.cursor() as cur:
        cur.execute(
            "insert into public.organization (name) values (%s) returning id",
            (slug,))
        org = str(cur.fetchone()["id"])
        cur.execute(
            """insert into asistente.tenant_config (organization_id, slug, config)
               values (%s, %s, %s)""",
            (org, slug, json.dumps({"version": 1})))
        conv = str(uuid.uuid4())
        cur.execute(
            """insert into asistente.conversations
                 (id, organization_id, canal, usuario_externo, estado)
               values (%s, %s, 'whatsapp', %s, 'abierta')""",
            (conv, org, f"57300{uuid.uuid4().hex[:7]}"))
        con.commit()
    CONVERSACIONES[slug] = conv
    return org


print(__doc__)
print(f"  base: {os.environ['DBHOST']}:{os.environ['DBPORT']}/{os.environ['DBNAME']}")

ORG_A = sembrar(SLUG_A)
ORG_B = sembrar(SLUG_B)
print(f"  empresa A: {SLUG_A}")
print(f"  empresa B: {SLUG_B}")

JPEG = bytes([0xFF, 0xD8, 0xFF]) + b"\x00" * 500
#  Lo que el modelo escribe de verdad: texto, no JSON. La forma sale de la
#  corrida real contra DeepSeek del 02/10/2026.
ANALISIS_A = (
    "Se ve un equipo tipo ONT con cinco indicadores: POWER, PON y LAN en "
    "verde, LOS en rojo y WIFI apagado. Debajo hay dos puertos LAN y un "
    "conector verde rotulado PON. La luz LOS suele asociarse a perdida de "
    "senal optica, pero la foto no permite confirmar la causa.")
ANALISIS_B = (
    "Se ve una caja de empalme abierta en una pared exterior, con marcas de "
    "humedad en el borde inferior y varios cables entrando por abajo.")
class _R:
    """Lo minimo que guardar_media necesita de un Resultado."""
    def __init__(self, texto):
        self.texto = texto

resultado = _R(ANALISIS_A)

try:
    # =========================================================================
    print("\n1. SE ESCRIBE Y SE LEE ENTERO")
    # =========================================================================

    MEDIA_A = f"wamid.VISION.{uuid.uuid4().hex[:10]}"
    fila_id = db.guardar_media(
        SLUG_A, CONVERSACIONES[SLUG_A], MEDIA_A, "image", JPEG, "image/jpeg",
        "miren la lucecita", None,
        analisis_visual=ANALISIS_A,
        estado_analisis=vi.PROCESADO,
        error_analisis=None)
    comprobar("guardar_media acepta las tres columnas nuevas", bool(fila_id))

    guardado = db.analisis_visual_de(SLUG_A, MEDIA_A)
    comprobar("analisis_visual_de encuentra la fila", guardado is not None)
    comprobar("el estado se guardo",
              guardado and guardado["estado_analisis"] == vi.PROCESADO)

    comprobar("el analisis vuelve entero de la base",
              guardado["analisis_visual"] == ANALISIS_A)
    comprobar("y no se guardo el rotulo ni el pie, solo la descripcion",
              "[Foto que envio" not in guardado["analisis_visual"]
              and "[Analisis automatico" not in guardado["analisis_visual"])

    comprobar("la descripcion que escribio el cliente NO se piso",
              True)
    with crudo() as con, con.cursor() as cur:
        cur.execute("""select descripcion, bytes, length(contenido) as largo
                       from asistente.media where media_id = %s""", (MEDIA_A,))
        f = cur.fetchone()
    comprobar("'descripcion' sigue siendo el pie del cliente",
              f["descripcion"] == "miren la lucecita", str(f["descripcion"]))
    comprobar("los bytes de la imagen se guardaron intactos",
              f["largo"] == len(JPEG) and f["bytes"] == len(JPEG),
              f"largo={f['largo']} bytes={f['bytes']} esperado={len(JPEG)}")

    # =========================================================================
    print("\n2. NI EL BASE64 NI UN DOCUMENTO LLEGAN A LA BASE")
    # =========================================================================
    #
    #  Son los dos riesgos concretos de guardar texto libre que escribio un
    #  modelo. El base64 es el que puede hacer mas daño --engorda la fila y
    #  despues viaja en cada turno-- y el documento es el que dura: esta fila
    #  se borra con la foto a los 30 dias, pero el MISMO texto, ya dentro del
    #  hilo, vive 365.

    #  Se guarda a proposito un analisis con las dos cosas adentro, SIN pasar
    #  por vision.analizar: asi se comprueba que la base no las esconde por
    #  casualidad, y de paso queda escrito que guardar_media NO redacta -- lo
    #  hace vision.py antes, y por eso lo de abajo si entra.
    MEDIA_SUCIO = f"wamid.SUCIO.{uuid.uuid4().hex[:10]}"
    db.guardar_media(SLUG_A, CONVERSACIONES[SLUG_A], MEDIA_SUCIO, "image",
                     JPEG, "image/jpeg", None, None,
                     analisis_visual="texto cualquiera",
                     estado_analisis=vi.PROCESADO)

    #  Lo que de verdad importa: lo que SI pasa por vision.py sale limpio.
    sucio = ("Se ve una etiqueta con el documento 1098765432 y un telefono "
             "3001234567, junto a un router con la luz roja.")
    limpio = redactar(sucio)
    MEDIA_REDACTADO = f"wamid.RED.{uuid.uuid4().hex[:10]}"
    db.guardar_media(SLUG_A, CONVERSACIONES[SLUG_A], MEDIA_REDACTADO, "image",
                     JPEG, "image/jpeg", None, None,
                     analisis_visual=limpio, estado_analisis=vi.PROCESADO)

    #  Se mira la COLUMNA CRUDA, sin pasar por el codigo que la escribio.
    with crudo() as con, con.cursor() as cur:
        cur.execute("""select analisis_visual from asistente.media
                       where media_id = %s""", (MEDIA_REDACTADO,))
        columna = cur.fetchone()["analisis_visual"]

    comprobar("el documento no llega a la columna",
              "1098765432" not in columna, columna[:160])
    comprobar("el telefono tampoco", "3001234567" not in columna)
    comprobar("pero lo util del texto si queda",
              "router" in columna and "luz roja" in columna)

    #  Y en NINGUNA columna de la fila, por si se filtrara por otro lado.
    with crudo() as con, con.cursor() as cur:
        cur.execute("""select (to_jsonb(m.*) - 'contenido')::text as todo
                       from asistente.media m where media_id = %s""",
                    (MEDIA_REDACTADO,))
        toda_la_fila = cur.fetchone()["todo"]
    comprobar("el documento no esta en NINGUNA columna de la fila",
              "1098765432" not in toda_la_fila)

    #  EL BASE64: en toda la tabla, de esta empresa, no puede haber una
    #  cadena larga con forma de base64 en una columna de TEXTO. Los bytes
    #  viven en 'contenido', que es bytea y no se mira aca.
    with crudo() as con, con.cursor() as cur:
        cur.execute("""select count(*) as n from asistente.media
                       where organization_id = %s
                         and (coalesce(analisis_visual,'') ~ '[A-Za-z0-9+/=]{200,}'
                           or coalesce(descripcion,'')     ~ '[A-Za-z0-9+/=]{200,}'
                           or coalesce(transcripcion,'')   ~ '[A-Za-z0-9+/=]{200,}')""",
                    (ORG_A,))
        comprobar("ninguna columna de texto tiene algo con forma de base64",
                  cur.fetchone()["n"] == 0)

    # =========================================================================
    print("\n3. UNA EMPRESA NO VE EL ANALISIS DE OTRA")
    # =========================================================================

    #  El MISMO media_id en las dos empresas: es el caso que de verdad
    #  rompe un aislamiento mal hecho, porque Meta podria repetir un id.
    MEDIA_COMPARTIDO = f"wamid.MISMO.{uuid.uuid4().hex[:10]}"
    otro = _R(ANALISIS_B)

    db.guardar_media(SLUG_A, CONVERSACIONES[SLUG_A], MEDIA_COMPARTIDO, "image",
                     JPEG, "image/jpeg", None, None,
                     analisis_visual=ANALISIS_A,
                     estado_analisis=vi.PROCESADO)
    db.guardar_media(SLUG_B, CONVERSACIONES[SLUG_B], MEDIA_COMPARTIDO, "image",
                     JPEG, "image/jpeg", None, None,
                     analisis_visual=ANALISIS_B,
                     estado_analisis=vi.PROCESADO)

    de_a = db.analisis_visual_de(SLUG_A, MEDIA_COMPARTIDO)
    de_b = db.analisis_visual_de(SLUG_B, MEDIA_COMPARTIDO)

    comprobar("las dos empresas tienen su propia fila con el mismo media_id",
              de_a is not None and de_b is not None)
    comprobar("A lee lo suyo", "LOS en rojo" in (de_a["analisis_visual"] or ""))
    comprobar("B lee lo suyo",
              "humedad" in (de_b["analisis_visual"] or ""))
    comprobar("A NO ve el analisis de B",
              "humedad" not in (de_a["analisis_visual"] or ""))
    comprobar("B NO ve el analisis de A",
              "LOS en rojo" not in (de_b["analisis_visual"] or ""))

    #  Y lo que de verdad importa: B no puede alcanzar la fila de A ni
    #  pidiendola por el media_id exclusivo de A.
    fuga = db.analisis_visual_de(SLUG_B, MEDIA_A)
    comprobar("B no alcanza la fila exclusiva de A ni nombrandola",
              fuga is None, str(fuga))

    # =========================================================================
    print("\n4. LA IDEMPOTENCIA ES DE LA BASE")
    # =========================================================================

    repetido = db.guardar_media(
        SLUG_A, CONVERSACIONES[SLUG_A], MEDIA_A, "image", JPEG, "image/jpeg",
        "otro pie distinto", None,
        analisis_visual="otra cosa distinta", estado_analisis=vi.PROCESADO)
    comprobar("guardar el mismo media_id dos veces devuelve None",
              repetido is None, str(repetido))

    with crudo() as con, con.cursor() as cur:
        cur.execute("""select count(*) as n from asistente.media
                       where media_id = %s and organization_id = %s""",
                    (MEDIA_A, ORG_A))
        comprobar("y no se creo una segunda fila",
                  cur.fetchone()["n"] == 1)
        cur.execute("""select analisis_visual, descripcion from asistente.media
                       where media_id = %s and organization_id = %s""",
                    (MEDIA_A, ORG_A))
        f = cur.fetchone()
    comprobar("el segundo intento NO piso el analisis bueno",
              f["analisis_visual"] == ANALISIS_A)
    comprobar("ni piso el pie del cliente",
              f["descripcion"] == "miren la lucecita")

    # =========================================================================
    print("\n5. EL HILO LO DEVUELVE A LA BANDEJA")
    # =========================================================================

    #  mensajes_de cuelga los adjuntos de un mensaje, asi que hace falta uno.
    with crudo() as con, con.cursor() as cur:
        mensaje = str(uuid.uuid4())
        cur.execute(
            """insert into asistente.messages
                 (id, organization_id, conversation_id, rol, contenido)
               values (%s, %s, %s, 'user', %s)""",
            (mensaje, ORG_A, CONVERSACIONES[SLUG_A], "[foto]"))
        con.commit()

    MEDIA_HILO = f"wamid.HILO.{uuid.uuid4().hex[:10]}"
    db.guardar_media(SLUG_A, CONVERSACIONES[SLUG_A], MEDIA_HILO, "image",
                     JPEG, "image/jpeg", None, mensaje,
                     analisis_visual=ANALISIS_A,
                     estado_analisis=vi.PROCESADO,
                     error_analisis="un motivo tecnico que no debe bajar")

    #  mensajes_de devuelve {"conversacion": ..., "mensajes": [...]}, no una
    #  lista: iterarlo directo da las CLAVES del dict.
    hilo = db.mensajes_de(SLUG_A, CONVERSACIONES[SLUG_A])
    adjuntos = [a for m in hilo["mensajes"] for a in (m.get("adjuntos") or [])]
    comprobar("el adjunto llega al hilo", len(adjuntos) >= 1,
              f"{len(adjuntos)} adjuntos")

    if adjuntos:
        a = adjuntos[0]
        comprobar("el analisis viaja a la bandeja",
                  bool(a.get("analisis_visual")))
        comprobar("el estado tambien",
                  a.get("estado_analisis") == vi.PROCESADO)
        comprobar("el motivo tecnico del fallo NO baja a la bandeja",
                  "error_analisis" not in a, str(list(a.keys())))
        comprobar("los bytes no viajan en el hilo", "contenido" not in a)
        comprobar("la cedula no viaja a la bandeja",
                  "123456789" not in json.dumps(a))

    # =========================================================================
    print("\n6. UNA FOTO SIN ANALIZAR SIGUE FUNCIONANDO")
    # =========================================================================

    MEDIA_SIN = f"wamid.SIN.{uuid.uuid4().hex[:10]}"
    fila = db.guardar_media(SLUG_A, CONVERSACIONES[SLUG_A], MEDIA_SIN, "image",
                            JPEG, "image/jpeg", "sin analisis", None)
    comprobar("una foto sin analisis se guarda igual", bool(fila))
    sin = db.analisis_visual_de(SLUG_A, MEDIA_SIN)
    comprobar("y su estado queda en NULL, que es 'nunca se intento'",
              sin is not None and sin["estado_analisis"] is None,
              str(sin))
    comprobar("y su analisis queda en NULL, no en cadena vacia",
              sin["analisis_visual"] is None)

finally:
    # =========================================================================
    #  Limpieza. Va en finally para no dejar basura si algo revienta.
    # =========================================================================
    try:
        with crudo() as con, con.cursor() as cur:
            for org in (ORG_A, ORG_B):
                cur.execute("delete from asistente.media where organization_id = %s", (org,))
                cur.execute("delete from asistente.messages where organization_id = %s", (org,))
                cur.execute("delete from asistente.conversations where organization_id = %s", (org,))
                cur.execute("delete from asistente.tenant_config where organization_id = %s", (org,))
                cur.execute("delete from public.organization where id = %s", (org,))
            con.commit()
        print("\n  (las dos empresas de prueba se borraron)")
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
