# -*- coding: utf-8 -*-
"""
================================================================================
 LA AUTORIZACION GRANULAR  --  la tabla tenia lector y no tenia escritor
================================================================================

    DBHOST=... DBPORT=... DBNAME=... DBUSER=... DBPASSWORD=... \
        py -3.13 tests/test_autorizacion_herramienta.py

EL DEFECTO, MEDIDO EN PRODUCCION EL 06/10/2026
-----------------------------------------------
'asistente.autorizacion_herramienta' se creo el 22/09/2026 con su lector y su
compuerta. Lo que nunca se escribio fue la forma de CONCEDER: ninguna linea
del repositorio insertaba una fila, y todas las pruebas sustituian el lector.

Con la tabla en 0 filas, la frontera negaba todo lo autonomo. Ese dia el reloj
intento 2 importaciones, 177 reconciliaciones y 146 sincronizaciones de hilo:
las 325 murieron con HERRAMIENTA_SIN_AUTORIZACION. No era un permiso mal
puesto -- era una puerta sin picaporte.

CONTRA POSTGRES REAL, Y POR UN MOTIVO CONCRETO
-----------------------------------------------
Lo que se prueba es que la fila quede escrita con el ROL correcto y que el
lector la vea. La segregacion de privilegios --'app_backend' con SELECT y
nada mas-- solo se puede comprobar contra una base que la tenga: en memoria,
cualquier insercion "funciona".

NO SE AFLOJA NINGUNA COMPUERTA
-------------------------------
Autorizar una herramienta no la ejecuta. Antes siguen el kill switch, el techo
y la etapa de autonomia, en ese orden, y hay una comprobacion de que una
autorizacion generosa no alcanza si el interruptor esta tirado.
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
from nucleo.seguridad import autorizacion     # noqa: E402

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


def crudo():
    return psycopg.connect(db.dsn(), row_factory=dict_row)


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


def sembrar(slug: str) -> str:
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
        #  El TECHO de la empresa. Sin el, 'autorizacion.veredicto' corta antes
        #  con TECHO_AUTONOMIA_AUSENTE y nunca llega a mirar la autorizacion --
        #  que es justo lo que esta prueba quiere medir. Produccion lo tiene
        #  en 2 (medido el 06/10/2026); aqui se siembra igual.
        cur.execute(
            """insert into asistente.nivel_autonomia
                 (organization_id, nivel, nivel_anterior, actor, motivo)
               values (%s, 2, null, 'prueba', 'sembrado por la prueba')""",
            (org,))
        con.commit()
    return org


SLUG_A = f"autoriz-a-{uuid.uuid4().hex[:8]}"
SLUG_B = f"autoriz-b-{uuid.uuid4().hex[:8]}"
ORG_A = sembrar(SLUG_A)
ORG_B = sembrar(SLUG_B)
H = "importar_caso_externo"

try:
    print("=" * 70)
    print(" AUTORIZACION GRANULAR  (PostgreSQL real)")
    print("=" * 70)

    print("\n-- 1. sin fila, la compuerta niega --")
    v = autorizacion.veredicto(SLUG_A, H, nivel_requerido=2)
    comprobar("una herramienta nunca autorizada no pasa",
              not v.permitido, f"{v.codigo}")
    comprobar("...con el codigo que se vio en produccion",
              v.codigo == autorizacion.SIN_AUTORIZACION, v.codigo)

    print("\n-- 2. se concede, y entonces pasa --")
    fila = db.registrar_autorizacion_herramienta(
        SLUG_A, H, "autorizada", 2, autorizado_por="cli:prueba",
        motivo="sincronizacion interna")
    comprobar("la fila queda escrita", fila and fila["estado"] == "autorizada")
    comprobar("...sin estado anterior, porque no habia", fila["estado_anterior"] is None)
    comprobar("...con quien y por que", fila["autorizado_por"] == "cli:prueba"
              and fila["motivo"] == "sincronizacion interna")

    v = autorizacion.veredicto(SLUG_A, H, nivel_requerido=2)
    comprobar("EL EFECTO: con la fila, la compuerta la deja pasar",
              v.permitido, f"{v.codigo}: {v.motivo}")

    print("\n-- 3. revocar no borra: agrega --")
    antes = len(db.autorizaciones_vigentes(SLUG_A))
    rev = db.registrar_autorizacion_herramienta(
        SLUG_A, H, "revocada", 0, autorizado_por="cli:prueba",
        motivo="se revisa el procedimiento")
    comprobar("la revocacion recuerda el estado anterior",
              rev["estado_anterior"] == "autorizada", str(rev["estado_anterior"]))
    v = autorizacion.veredicto(SLUG_A, H, nivel_requerido=2)
    comprobar("y la compuerta vuelve a negar", not v.permitido, v.codigo)
    with crudo() as con, con.cursor() as cur:
        cur.execute("""select count(*) n from asistente.autorizacion_herramienta
                        where organization_id=%s and herramienta=%s""", (ORG_A, H))
        n = cur.fetchone()["n"]
    comprobar("las DOS filas siguen en la base (solo se agrega)", n == 2, str(n))
    comprobar("y 'vigentes' muestra una sola por herramienta",
              len(db.autorizaciones_vigentes(SLUG_A)) == antes, "")

    print("\n-- 4. una empresa no autoriza a la otra --")
    db.registrar_autorizacion_herramienta(
        SLUG_B, H, "autorizada", 2, autorizado_por="cli:prueba", motivo="x")
    vb = autorizacion.veredicto(SLUG_B, H, nivel_requerido=2)
    va = autorizacion.veredicto(SLUG_A, H, nivel_requerido=2)
    comprobar("B autorizada no autoriza a A",
              not va.permitido, f"A: {va.codigo}")
    comprobar("...y B no se ve afectada por la revocacion de A",
              vb.codigo != autorizacion.SIN_AUTORIZACION, vb.codigo)

    print("\n-- 5. lo que NO se acepta --")
    for estado, nivel, actor, etiqueta in (
            ("inventado", 2, "x", "un estado que no existe"),
            ("autorizada", 9, "x", "un nivel fuera de 0..4"),
            ("autorizada", 2, "  ", "una autorizacion sin autor")):
        try:
            db.registrar_autorizacion_herramienta(
                SLUG_A, "otra", estado, nivel, autorizado_por=actor, motivo="m")
            ok = False
        except ValueError:
            ok = True
        comprobar(f"se rechaza {etiqueta}", ok)

    print("\n-- 6. el runtime NO puede autorizarse a si mismo --")
    #  LA SEGREGACION, AFIRMADA SOBRE EL EFECTO.
    #
    #  Si el motor pudiera insertar aqui, podria concederse la herramienta que
    #  la frontera acaba de negarle, y la frontera dejaria de serlo. La base lo
    #  impide: 'app_backend' tiene SELECT y nada mas. Se comprueba
    #  INTENTANDOLO con el rol del runtime, no leyendo los grants: un grant
    #  correcto y el codigo pidiendo otro rol se ven igual de bien hasta que
    #  alguien lo prueba.
    import psycopg.errors as _err
    try:
        with db.sesion(SLUG_A) as (cur, org):      # rol por omision: app_backend
            cur.execute(
                """insert into asistente.autorizacion_herramienta
                     (organization_id, herramienta, estado, nivel_maximo,
                      autorizado_por)
                   values (%s,'colada','autorizada',4,'el motor')""", (org,))
        negado = False
    except _err.InsufficientPrivilege:
        negado = True
    comprobar("el rol del runtime NO puede insertar una autorizacion", negado,
              "si esto pasara, el motor podria autorizarse solo")

    print("\n-- 7. autorizar NO es ejecutar --")
    #  La compuerta de autorizacion es la ULTIMA. Si el interruptor esta
    #  tirado, la frontera corta antes y esta fila no sirve de nada.
    from nucleo.seguridad import frontera
    orig = frontera.interruptor.veredicto
    frontera.interruptor.veredicto = lambda t: type(
        "V", (), {"permitido": False, "estado": "detenido",
                  "motivo": "prueba", "codigo": "detenido"})()
    try:
        db.registrar_autorizacion_herramienta(
            SLUG_A, H, "autorizada", 2, autorizado_por="cli:prueba", motivo="m")
        try:
            with frontera.autonoma(SLUG_A, H, origen="prueba",
                                   efecto_externo=False):
                paso = True
        except frontera.AccionExternaNoAutorizada:
            paso = False
        comprobar("con el kill switch tirado, la autorizacion no alcanza",
                  not paso)
    finally:
        frontera.interruptor.veredicto = orig

finally:
    try:
        with crudo() as con, con.cursor() as cur:
            for org in (ORG_A, ORG_B):
                cur.execute("delete from asistente.autorizacion_herramienta where organization_id=%s", (org,))
                cur.execute("delete from asistente.nivel_autonomia where organization_id=%s", (org,))
                cur.execute("delete from asistente.ejecucion_autonoma where organization_id=%s", (org,))
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
