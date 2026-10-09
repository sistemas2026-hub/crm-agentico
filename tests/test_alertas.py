# -*- coding: utf-8 -*-
"""
================================================================================
 ALERTAS OPERATIVAS  --  que avise cuando pasa, y SOLO cuando pasa
================================================================================

    py -3.13 tests/test_alertas.py                 solo las reglas
    DBHOST=... DBPORT=... DBNAME=... DBUSER=... DBPASSWORD=... \
        py -3.13 tests/test_alertas.py             reglas + estado real

DOS MITADES, Y LA SEPARACION ES EL PUNTO
-----------------------------------------
  A. LAS REGLAS. Funciones puras: reciben una cifra y dicen que corresponde.
     Corren sin base, sin red y sin modelo, asi que corren siempre -- tambien
     en CI, donde las 52 pruebas que piden Postgres todavia no corren (D1).
     Son las que deciden, y una decision que necesita PostgreSQL para
     probarse se prueba poco.

  B. EL ESTADO. Contra PostgreSQL REAL, porque lo que se prueba aca es que la
     antirrepeticion exista en la BASE y no en el proceso: un indice unico
     parcial que falta solo se ve cuando la base acepta lo que no debia. En
     memoria, la segunda insercion "funciona" y la prueba pasa en verde con
     el defecto vivo.

LO QUE NO SE PRUEBA ACA
-----------------------
No se llama a DeepSeek, no se consulta el saldo por HTTP y no se llama a
ningun modelo. El saldo sale de la foto que ya esta en 'usage_daily', que es
justamente el diseño: una alerta que gasta credito para avisar que se acaba
el credito seria una forma elegante de empeorarlo.
================================================================================
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.observabilidad import alertas

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


# =============================================================================
#  A.  LAS REGLAS
# =============================================================================

print("=" * 70)
print(" A. LAS REGLAS  (sin base, sin red, sin modelo)")
print("=" * 70)

print("\n-- saldo --")

l = alertas.evaluar_saldo(42.00)
comprobar("1. saldo normal -> ninguna alerta",
          l.estado == alertas.LIMPIO and l.condicion is None, str(l))

l = alertas.evaluar_saldo(4.99)
comprobar("2. saldo bajo 5 -> WARNING",
          l.estado == alertas.ALERTA and l.condicion.gravedad == alertas.WARNING,
          str(l))
comprobar("   ...y dice contra que umbral",
          l.condicion.umbral == 5.00 and l.condicion.metrica == alertas.SALDO_USD,
          str(l.condicion))
comprobar("   ...y el tipo es saldo_bajo", l.condicion.tipo == alertas.SALDO_BAJO)

l = alertas.evaluar_saldo(1.99)
comprobar("3. saldo bajo 2 -> CRITICAL",
          l.estado == alertas.ALERTA and l.condicion.gravedad == alertas.CRITICAL,
          str(l))
comprobar("   ...con el umbral critico, no el de aviso",
          l.condicion.umbral == 2.00, str(l.condicion))

l = alertas.evaluar_saldo(5.00)
comprobar("4. saldo EXACTAMENTE 5 -> no hay WARNING (la comparacion es '<')",
          l.estado == alertas.LIMPIO, str(l))

l = alertas.evaluar_saldo(2.00)
comprobar("5. saldo EXACTAMENTE 2 -> no hay CRITICAL",
          l.estado == alertas.ALERTA and l.condicion.gravedad == alertas.WARNING,
          "2.00 no cruza el critico, pero si el de aviso: " + str(l))

l = alertas.evaluar_saldo(None)
comprobar("15. saldo NULL -> SIN_DATO, no una alerta",
          l.estado == alertas.SIN_DATO and l.condicion is None, str(l))

#  El caso real del 05/10/2026.
l = alertas.evaluar_saldo(0.72, dia_foto=date(2026, 10, 5), hoy=date(2026, 10, 5))
comprobar("el 0.72 USD medido el 05/10/2026 habria sido CRITICAL",
          l.estado == alertas.ALERTA and l.condicion.gravedad == alertas.CRITICAL,
          str(l))
comprobar("...y la alerta dice de cuando es la foto",
          l.condicion.metadatos.get("edad_dias") == 0
          and l.condicion.metadatos.get("dia_foto") == "2026-10-05",
          str(l.condicion.metadatos))

l = alertas.evaluar_saldo(0.72, dia_foto=date(2026, 10, 1), hoy=date(2026, 10, 5))
comprobar("una foto vieja se marca con su edad, no se descarta",
          l.estado == alertas.ALERTA
          and l.condicion.metadatos["edad_dias"] == 4, str(l.condicion.metadatos))

comprobar("los umbrales se pueden pasar por parametro (el dia que sean config)",
          alertas.evaluar_saldo(50.0, warning=100.0, critical=60.0
                                ).condicion.gravedad == alertas.CRITICAL)

print("\n-- divergencia --")


def ver(ratio=None, diferencia=0.0, comparables=10, calculado=1.0, real=1.0):
    return {"comparables": comparables, "ratio": ratio,
            "diferencia": diferencia, "calculado": calculado, "real": real}


l = alertas.evaluar_divergencia(ver(ratio=1.5, diferencia=0.5))
comprobar("9. ratio exactamente 1.5 -> ninguna alerta",
          l.estado == alertas.LIMPIO, str(l))

l = alertas.evaluar_divergencia(ver(ratio=1.2, diferencia=0.2))
comprobar("9b. ratio por debajo -> ninguna alerta", l.estado == alertas.LIMPIO,
          str(l))

l = alertas.evaluar_divergencia(ver(ratio=1.51, diferencia=0.5))
comprobar("10. ratio > 1.5 -> WARNING",
          l.estado == alertas.ALERTA and l.condicion.gravedad == alertas.WARNING,
          str(l))
comprobar("    ...la metrica es el ratio y el umbral es 1.5",
          l.condicion.metrica == alertas.RATIO and l.condicion.umbral == 1.5,
          str(l.condicion))

l = alertas.evaluar_divergencia(ver(ratio=3.01, diferencia=0.5))
comprobar("11. ratio > 3 -> CRITICAL",
          l.estado == alertas.ALERTA and l.condicion.gravedad == alertas.CRITICAL,
          str(l))

l = alertas.evaluar_divergencia(ver(ratio=1.1, diferencia=5.01))
comprobar("12. diferencia > 5 USD -> CRITICAL aunque el ratio no cruce",
          l.estado == alertas.ALERTA
          and l.condicion.gravedad == alertas.CRITICAL
          and l.condicion.metrica == alertas.DIFERENCIA_USD, str(l))
comprobar("    ...y deja escrito que regla disparo",
          l.condicion.metadatos.get("regla") == "diferencia",
          str(l.condicion.metadatos))

l = alertas.evaluar_divergencia(ver(ratio=1.1, diferencia=5.00))
comprobar("12b. diferencia EXACTAMENTE 5 -> no dispara",
          l.estado == alertas.LIMPIO, str(l))

l = alertas.evaluar_divergencia(ver(ratio=0.3, diferencia=-8.0))
comprobar("contar de mas tambien se avisa, por la diferencia en dolares",
          l.estado == alertas.ALERTA
          and l.condicion.metrica == alertas.DIFERENCIA_USD, str(l))
comprobar("...y la direccion queda anotada",
          l.condicion.metadatos.get("direccion") == "contamos_de_mas",
          str(l.condicion.metadatos))

l = alertas.evaluar_divergencia(ver(ratio=0.3, diferencia=-0.4))
comprobar("pero un ratio BAJO con centavos de diferencia no alerta: la razon "
          "solo se mira hacia arriba", l.estado == alertas.LIMPIO, str(l))

l = alertas.evaluar_divergencia(ver(ratio=5.0, diferencia=9.0))
comprobar("si cumple las dos reglas criticas, gana el ratio (se evalua primero)",
          l.condicion.metadatos.get("regla") == "ratio", str(l.condicion))

l = alertas.evaluar_divergencia(ver(ratio=4.0, diferencia=6.0, comparables=2))
comprobar("13. comparables < 3 -> SIN_DATO, aunque la cifra sea escandalosa",
          l.estado == alertas.SIN_DATO, str(l))
comprobar("    ...y dice por que", "comparables" in l.motivo, l.motivo)

l = alertas.evaluar_divergencia(ver(ratio=4.0, diferencia=6.0, comparables=3))
comprobar("13b. con exactamente 3 comparables si se concluye",
          l.estado == alertas.ALERTA, str(l))

l = alertas.evaluar_divergencia({"comparables": 0, "estado": "sin_datos"})
comprobar("sin dias comparables -> SIN_DATO", l.estado == alertas.SIN_DATO, str(l))

l = alertas.evaluar_divergencia(None)
comprobar("14a. conciliacion que no devolvio nada -> SIN_DATO, no explota",
          l.estado == alertas.SIN_DATO, str(l))

l = alertas.evaluar_divergencia(ver(ratio=None, diferencia=0.1))
comprobar("ratio None (no se pudo calcular) y diferencia chica -> limpio",
          l.estado == alertas.LIMPIO, str(l))

#  El caso real del 05/10/2026: 2.86x sostenido 23 dias.
l = alertas.evaluar_divergencia(ver(ratio=2.86, diferencia=4.41, comparables=23,
                                    calculado=2.37, real=6.78))
comprobar("el 2.86x medido el 05/10/2026 habria sido WARNING",
          l.estado == alertas.ALERTA and l.condicion.gravedad == alertas.WARNING,
          str(l))

print("\n-- la ventana: por que 14 dias y no 3 --")
comprobar("la ventana es de 14 dias", alertas.DIAS_VENTANA == 14)
comprobar("y el minimo de comparables es 3", alertas.MINIMO_COMPARABLES == 3)
comprobar("con una ventana de 3 dias el minimo seria INALCANZABLE "
          "(3 filas - 1 sin par previo = 2 < 3)",
          3 - 1 < alertas.MINIMO_COMPARABLES)

comprobar("el umbral de aviso del ratio es el mismo que usa el panel",
          alertas.RATIO_WARNING == __import__(
              "nucleo.observabilidad.consumo", fromlist=["x"]).RATIO_DIVERGENCIA)


# =============================================================================
#  B.  EL ESTADO  --  contra PostgreSQL real
# =============================================================================

import os       # noqa: E402

FALTAN = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if FALTAN:
    print("\n" + "=" * 70)
    print(f" B. OMITIDA: faltan {FALTAN}. Exige PostgreSQL real.")
    print("=" * 70)
    if fallos:
        print(f"\nFALLARON {len(fallos)}:")
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)
    print("\nLas reglas, en verde. El estado no se midio.")
    sys.exit(0)

import json      # noqa: E402
import uuid      # noqa: E402

import psycopg                           # noqa: E402
from psycopg.rows import dict_row        # noqa: E402

from nucleo.persistencia import db       # noqa: E402

print("\n" + "=" * 70)
print(" B. EL ESTADO  (PostgreSQL real)")
print("=" * 70)


def crudo():
    return psycopg.connect(db.dsn(), row_factory=dict_row)


class _Saldo:
    url = "https://ejemplo.invalido/balance"
    campo = "saldo"
    auth_ref = ""
    auth_header = "Authorization"
    auth_esquema = "Bearer"
    tolerancia = 0.15


class _SinSaldo:
    url = ""
    campo = ""
    auth_ref = ""
    auth_header = "Authorization"
    auth_esquema = "Bearer"
    tolerancia = 0.15


class _LLM:
    def __init__(self, saldo):
        self.modelo_por_defecto = "deepseek:deepseek-v4-flash"
        self.saldo = saldo
        self.tarifas = {}


class _Identidad:
    def __init__(self, slug):
        self.slug = slug


class _Config:
    """Lo minimo que 'alertas.evaluar' mira. Nada de red: la URL es invalida
    a proposito y nunca se llama -- el saldo sale de la foto en la base."""
    def __init__(self, slug, con_saldo=True):
        self.identidad = _Identidad(slug)
        self.llm = _LLM(_Saldo() if con_saldo else _SinSaldo())


SLUG_A = f"alertas-a-{uuid.uuid4().hex[:8]}"
SLUG_B = f"alertas-b-{uuid.uuid4().hex[:8]}"


#  'public.organization' la maneja Django, que rellena en Python varias
#  columnas NOT NULL sin default en la base. Insertar desde aca a mano exige
#  completarlas, y escribir la lista fija acoplaria esta prueba al esquema del
#  CRM: el dia que agreguen una columna, falla una prueba de alertas por un
#  motivo que no tiene nada que ver. Se derivan del catalogo.
#
#  El relleno de texto es un UUID recortado al largo de la columna, no una
#  cadena vacia: 'api_key' tiene restriccion UNIQUE, asi que dos empresas de
#  prueba con '' chocarian entre si.
_RELLENO = {"timestamp with time zone": "now()", "boolean": "false",
            "uuid": "gen_random_uuid()", "jsonb": "'{}'::jsonb",
            "integer": "0", "bigint": "0", "numeric": "0"}


def _columnas_obligatorias() -> list[tuple[str, str]]:
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
            n = min(int(f["largo"] or 36), 36)
            relleno = f"left(gen_random_uuid()::text, {n})"
        salida.append((f["column_name"], relleno))
    return salida


OBLIGATORIAS = _columnas_obligatorias()


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
        con.commit()
    return org


def foto(org: str, dia: date, saldo, costo=0.0) -> None:
    """Deja una fila de usage_daily con su foto de saldo."""
    with crudo() as con, con.cursor() as cur:
        cur.execute(
            """insert into asistente.usage_daily
                 (organization_id, dia, costo_usd, saldo_proveedor_usd)
               values (%s,%s,%s,%s)
               on conflict (organization_id, dia) do update
                 set costo_usd = excluded.costo_usd,
                     saldo_proveedor_usd = excluded.saldo_proveedor_usd""",
            (org, dia, costo, saldo))
        con.commit()


def filas(org: str, tipo=None) -> list[dict]:
    with crudo() as con, con.cursor() as cur:
        cur.execute(
            """select tipo, gravedad, proveedor, metrica, valor, umbral,
                      resuelta_en, creado_en, metadatos
                 from asistente.alertas_operativas
                where organization_id = %s
                  and (%s::text is null or tipo = %s)
                order by creado_en, id""", (org, tipo, tipo))
        return [dict(f) for f in cur.fetchall()]


ORG_A = sembrar(SLUG_A)
ORG_B = sembrar(SLUG_B)
CFG_A = _Config(SLUG_A)
CFG_B = _Config(SLUG_B)
HOY = date.today()

try:
    # -------------------------------------------------------------------------
    print("\n-- 6 y 19: no duplicar, ni entre barridos ni entre reinicios --")
    # -------------------------------------------------------------------------
    foto(ORG_A, HOY, 1.10)

    r1 = alertas.evaluar(CFG_A, SLUG_A)
    abiertas = [f for f in filas(ORG_A, "saldo_bajo") if f["resuelta_en"] is None]
    comprobar("primer barrido: se abre la alerta de saldo",
              r1["creadas"] == 1 and len(abiertas) == 1, str(r1))
    comprobar("...y es CRITICAL, con el valor que la disparo",
              abiertas[0]["gravedad"] == "critical"
              and float(abiertas[0]["valor"]) == 1.10, str(abiertas[0]))
    comprobar("18. el proveedor queda registrado, derivado de la config",
              abiertas[0]["proveedor"] == "deepseek", str(abiertas[0]))

    r2 = alertas.evaluar(CFG_A, SLUG_A)
    r3 = alertas.evaluar(CFG_A, SLUG_A)
    total = len(filas(ORG_A, "saldo_bajo"))
    comprobar("6. tres barridos seguidos -> UNA sola fila",
              total == 1 and r2["creadas"] == 0 and r3["creadas"] == 0,
              f"{total} filas; {r2['creadas']}/{r3['creadas']} creadas")

    #  El reinicio: 'alertas' no guarda nada en memoria, asi que recargar el
    #  modulo equivale a arrancar el proceso de cero. Si la antirrepeticion
    #  viviera en un dict de proceso, esto crearia la segunda fila.
    import importlib                                            # noqa: E402
    importlib.reload(alertas)
    r4 = alertas.evaluar(CFG_A, SLUG_A)
    comprobar("19. despues de 'reiniciar' el proceso, sigue sin duplicar",
              len(filas(ORG_A, "saldo_bajo")) == 1 and r4["creadas"] == 0,
              str(r4))

    #  Y la garantia de verdad: la base lo IMPIDE, no el codigo que la llama.
    choco = False
    try:
        with crudo() as con, con.cursor() as cur:
            cur.execute(
                """insert into asistente.alertas_operativas
                     (organization_id, tipo, gravedad, proveedor, metrica,
                      valor, umbral)
                   values (%s,'saldo_bajo','warning','deepseek','saldo_usd',1,2)""",
                (ORG_A,))
            con.commit()
    except psycopg.errors.UniqueViolation:
        choco = True
    comprobar("la antirrepeticion esta en la BASE: un insert directo rebota",
              choco, "la base acepto una segunda alerta activa del mismo asunto")

    # -------------------------------------------------------------------------
    print("\n-- la gravedad sube en el lugar, no abre una segunda --")
    # -------------------------------------------------------------------------
    #  Primero se resuelve y se reabre como warning, para despues empeorarla.
    with crudo() as con, con.cursor() as cur:
        cur.execute("delete from asistente.alertas_operativas where organization_id=%s",
                    (ORG_A,))
        con.commit()
    foto(ORG_A, HOY, 4.50)
    alertas.evaluar(CFG_A, SLUG_A)
    foto(ORG_A, HOY, 1.20)
    r = alertas.evaluar(CFG_A, SLUG_A)
    abiertas = [f for f in filas(ORG_A, "saldo_bajo") if f["resuelta_en"] is None]
    comprobar("de warning a critical: se actualiza, no se duplica",
              r["actualizadas"] == 1 and len(filas(ORG_A, "saldo_bajo")) == 1
              and abiertas[0]["gravedad"] == "critical", str(r))
    comprobar("...y el valor refleja la cifra de ahora",
              float(abiertas[0]["valor"]) == 1.20, str(abiertas[0]))

    r = alertas.evaluar(CFG_A, SLUG_A)
    comprobar("y el barrido siguiente, con la misma gravedad, no escribe nada",
              r["actualizadas"] == 0 and r["creadas"] == 0, str(r))

    # -------------------------------------------------------------------------
    print("\n-- 7 y 8: se recupera, se resuelve; recae, se abre una nueva --")
    # -------------------------------------------------------------------------
    foto(ORG_A, HOY, 50.00)
    r = alertas.evaluar(CFG_A, SLUG_A)
    todas = filas(ORG_A, "saldo_bajo")
    comprobar("7. saldo recuperado -> la alerta se resuelve",
              r["resueltas"] == 1 and len(todas) == 1
              and todas[0]["resuelta_en"] is not None, str(r))

    r = alertas.evaluar(CFG_A, SLUG_A)
    comprobar("...y no se vuelve a resolver en el barrido siguiente",
              r["resueltas"] == 0, str(r))

    foto(ORG_A, HOY, 0.80)
    r = alertas.evaluar(CFG_A, SLUG_A)
    todas = filas(ORG_A, "saldo_bajo")
    comprobar("8. recae -> se abre una alerta NUEVA, no se reabre la vieja",
              r["creadas"] == 1 and len(todas) == 2
              and sum(1 for f in todas if f["resuelta_en"] is None) == 1,
              f"{len(todas)} filas; {r}")
    comprobar("...y queda el historico de las dos veces que paso",
              sum(1 for f in todas if f["resuelta_en"] is not None) == 1)

    # -------------------------------------------------------------------------
    print("\n-- 15 y 14: sin dato no se inventa ni la alarma ni el alta --")
    # -------------------------------------------------------------------------
    SLUG_C = f"alertas-c-{uuid.uuid4().hex[:8]}"
    ORG_C = sembrar(SLUG_C)
    CFG_C = _Config(SLUG_C)
    r = alertas.evaluar(CFG_C, SLUG_C)
    comprobar("15b. sin ninguna foto de saldo -> no se crea nada",
              r["creadas"] == 0 and len(filas(ORG_C)) == 0, str(r))
    comprobar("...y se reporta como sin_dato, no como 'todo bien'",
              r["sin_dato"] == 2, str(r["pasos"]))

    #  Una alerta abierta + el dato que desaparece: NO se resuelve.
    foto(ORG_C, HOY, 0.50)
    alertas.evaluar(CFG_C, SLUG_C)
    with crudo() as con, con.cursor() as cur:
        cur.execute("""update asistente.usage_daily set saldo_proveedor_usd = null
                        where organization_id = %s""", (ORG_C,))
        con.commit()
    r = alertas.evaluar(CFG_C, SLUG_C)
    abiertas = [f for f in filas(ORG_C, "saldo_bajo") if f["resuelta_en"] is None]
    comprobar("si el dato desaparece, la alerta abierta NO se resuelve sola",
              r["resueltas"] == 0 and len(abiertas) == 1,
              "resolver por falta de datos seria un alta medica inventada")

    #  Conciliacion rota: no puede impedir que se mire el saldo.
    import nucleo.observabilidad.consumo as _consumo             # noqa: E402
    original = _consumo.veredicto_conciliacion
    _consumo.veredicto_conciliacion = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("la base de conciliacion no contesta"))
    try:
        foto(ORG_C, HOY, 0.40)
        r = alertas.evaluar(CFG_C, SLUG_C)
        comprobar("14. la conciliacion revienta y el saldo igual se evalua",
                  r["vigilado"] and any(p["tipo"] == "saldo_bajo"
                                        and p["estado"] == alertas.ALERTA
                                        for p in r["pasos"]), str(r["pasos"]))
        comprobar("...y el paso de divergencia queda en sin_dato, sin alerta falsa",
                  any(p["tipo"] == "divergencia_consumo"
                      and p["estado"] == alertas.SIN_DATO for p in r["pasos"]),
                  str(r["pasos"]))
    finally:
        _consumo.veredicto_conciliacion = original

    # -------------------------------------------------------------------------
    print("\n-- 16: modo seco, cero escrituras --")
    # -------------------------------------------------------------------------
    SLUG_D = f"alertas-d-{uuid.uuid4().hex[:8]}"
    ORG_D = sembrar(SLUG_D)
    CFG_D = _Config(SLUG_D)
    foto(ORG_D, HOY, 0.90)

    seco = alertas.evaluar(CFG_D, SLUG_D, seco=True)
    comprobar("16. el seco DICE que crearia la alerta",
              any(p["accion"] == "crear" for p in seco["pasos"]), str(seco["pasos"]))
    comprobar("    ...y no escribio ni una fila",
              len(filas(ORG_D)) == 0, f"{len(filas(ORG_D))} filas")

    #  Y el seco de una resolucion: tiene que decir que resolveria.
    alertas.evaluar(CFG_D, SLUG_D)          # ahora si, de verdad
    foto(ORG_D, HOY, 99.00)
    antes = filas(ORG_D)
    seco = alertas.evaluar(CFG_D, SLUG_D, seco=True)
    despues = filas(ORG_D)
    comprobar("    el seco DICE que resolveria",
              any(p["accion"] == "resolver" for p in seco["pasos"]),
              str(seco["pasos"]))
    comprobar("    ...y la alerta sigue abierta",
              [f["resuelta_en"] for f in antes] == [f["resuelta_en"] for f in despues]
              and despues[0]["resuelta_en"] is None)

    # -------------------------------------------------------------------------
    print("\n-- 17 y 20: una empresa no afecta a la otra --")
    # -------------------------------------------------------------------------
    foto(ORG_B, HOY, 100.00)
    alertas.evaluar(CFG_B, SLUG_B)
    comprobar("17. B con saldo sano no tiene alertas, aunque A si",
              len(filas(ORG_B)) == 0
              and any(f["resuelta_en"] is None for f in filas(ORG_A)),
              f"B={len(filas(ORG_B))}  A={len(filas(ORG_A))}")

    comprobar("17b. A no ve las alertas de B ni al reves",
              all(k[0] in alertas.TIPOS for k in alertas.activas(SLUG_A))
              and alertas.activas(SLUG_B) == {},
              f"{alertas.activas(SLUG_A)} / {alertas.activas(SLUG_B)}")

    #  El aislamiento del reloj: una empresa rota no frena a las demas. Se
    #  mide sobre 'una_pasada', que es donde vive el try/except -- no sobre
    #  una funcion parecida escrita para la prueba.
    import nucleo.reloj as reloj                                 # noqa: E402

    orden: list[str] = []

    def explota_en_el_primero(config, tenant, seco):
        orden.append(tenant)
        if len(orden) == 1:
            raise RuntimeError("esta empresa tiene la config a medias")
        return {"vigilado": True, "creadas": 0, "resueltas": 0}

    original_al = reloj._alertas
    original_tenants = reloj.tenants_conocidos
    reloj._alertas = explota_en_el_primero
    reloj.tenants_conocidos = lambda: ["uno", "dos", "tres"]
    original_cargar = reloj.fuente.cargar
    reloj.fuente.cargar = lambda t, raiz: _Config(t)
    original_ver = reloj.interruptor.veredicto
    reloj.interruptor.veredicto = lambda t: type(
        "V", (), {"estado": "detenido", "motivo": "prueba", "permitido": False})()
    try:
        salida = reloj.una_pasada(seco=True)
        comprobar("20. la alerta rota de una empresa no impide procesar las demas",
                  len(orden) == 3 and len(salida) == 3, f"{orden} / {len(salida)}")
        comprobar("    ...y el error de esa empresa queda reportado",
                  "error" in salida[0]["alertas"]
                  and "error" not in salida[1]["alertas"], str(salida[0]))

        #  Y AHORA EN SERIO, SIN --dry-run. En seco el reloj NO corta por el
        #  interruptor (lo dice su propio comentario: la gracia del seco es
        #  ver que haria). Afirmar sobre esa pasada no probaria nada del
        #  camino real -- es la trampa de 6: la prueba recorreria la rama que
        #  no es. Esta pasada si entra en la rama 'autonomia detenida'.
        #
        #  LO QUE SE AFIRMA ACA ES LO CONTRARIO DE LO QUE AFIRMABA LA PRIMERA
        #  VERSION, y la inversion es el arreglo del 05/10/2026: las alertas
        #  corrian antes de la compuerta con el argumento de que observar no es
        #  actuar, y el contrato del interruptor nombra el trabajo del
        #  scheduler. Se afirma sobre el EFECTO --que la funcion no se llamo--
        #  y no solo sobre lo que el informe dice de si mismo.
        orden.clear()
        import contextlib                                       # noqa: E402
        import io                                               # noqa: E402
        tubo = io.StringIO()
        with contextlib.redirect_stdout(tubo):
            salida = reloj.una_pasada(seco=False)
        log = tubo.getvalue()
        comprobar("    con la autonomia DETENIDA, los otros dos se omiten",
                  salida[1]["vencimientos"].get("omitido") == "autonomia detenida"
                  and salida[1]["importacion"].get("omitido") == "autonomia detenida",
                  str(salida[1]))
        comprobar("    ...y las alertas TAMBIEN se omiten, con el mismo motivo",
                  salida[1]["alertas"].get("omitido") == "autonomia detenida",
                  str(salida[1].get("alertas")))
        comprobar("    ...y '_alertas' NO se ejecuto ni una vez: el efecto, no "
                  "el informe", orden == [],
                  f"se llamo para {orden} con el interruptor tirado")
        comprobar("    ...en las tres empresas, no solo en una",
                  all(t["alertas"].get("omitido") == "autonomia detenida"
                      for t in salida), str([t["alertas"] for t in salida]))
        comprobar("    ...y el informe no se contradice: nada que diga "
                  "'vigilado' junto a 'omitido'",
                  not any("vigilado" in t["alertas"] for t in salida),
                  str([t["alertas"] for t in salida]))

        #  EL LOG MISMO, no el informe. Es donde estaba el sintoma: la linea
        #  "no se ejecuta ningun trabajo" seguida de otra que reportaba las
        #  alertas corridas. Se afirma sobre el TEXTO que sale, porque es lo
        #  que lee una persona a las tres de la tarde con la palanca tirada.
        comprobar("    el log dice que no se ejecuta ningun trabajo",
                  "no se ejecuta ningun trabajo" in log, log[:300])
        comprobar("    ...y NO se desmiente: ninguna linea reporta alertas "
                  "corridas en el mismo ciclo",
                  "vigilado" not in log and "alertas=" not in log,
                  [l for l in log.splitlines() if "alerta" in l or "vigilado" in l])
    finally:
        reloj._alertas = original_al
        reloj.tenants_conocidos = original_tenants
        reloj.fuente.cargar = original_cargar
        reloj.interruptor.veredicto = original_ver

    # -------------------------------------------------------------------------
    print("\n-- un tenant sin endpoint de saldo no se vigila --")
    # -------------------------------------------------------------------------
    SLUG_E = f"alertas-e-{uuid.uuid4().hex[:8]}"
    ORG_E = sembrar(SLUG_E)
    foto(ORG_E, HOY, 0.01)
    r = alertas.evaluar(_Config(SLUG_E, con_saldo=False), SLUG_E)
    comprobar("sin 'llm.saldo' declarado no se mira nada, ni con saldo en 0.01",
              r["vigilado"] is False and len(filas(ORG_E)) == 0, str(r))

    # -------------------------------------------------------------------------
    print("\n-- la divergencia, extremo a extremo contra la base --")
    # -------------------------------------------------------------------------
    SLUG_F = f"alertas-f-{uuid.uuid4().hex[:8]}"
    ORG_F = sembrar(SLUG_F)
    CFG_F = _Config(SLUG_F)
    #  5 dias: el saldo baja 2.00/dia y el sistema cree que gasta 0.50/dia.
    #  Son 4 comparables (el primero no tiene con que compararse) y ratio 4x.
    #  El saldo arranca alto a proposito para que NO dispare saldo_bajo y lo
    #  unico que se mida aca sea la divergencia.
    for i, saldo in enumerate([100.0, 98.0, 96.0, 94.0, 92.0]):
        foto(ORG_F, HOY - timedelta(days=4 - i), saldo, costo=0.50)
    r = alertas.evaluar(CFG_F, SLUG_F)
    div = [f for f in filas(ORG_F, "divergencia_consumo")]
    comprobar("divergencia real (4 comparables, 2.00 vs 0.50 por dia) -> CRITICAL",
              len(div) == 1 and div[0]["gravedad"] == "critical", str(r["pasos"]))
    comprobar("...y no se abrio una alerta de saldo (92 USD esta sano)",
              len(filas(ORG_F, "saldo_bajo")) == 0)
    comprobar("...y el metadato explica la cifra",
              div[0]["metadatos"].get("comparables") == 4
              and div[0]["metadatos"].get("dias_ventana") == 14,
              str(div[0]["metadatos"]))

finally:
    try:
        with crudo() as con, con.cursor() as cur:
            cur.execute(
                """select id from public.organization
                    where name like 'alertas-a-%' or name like 'alertas-b-%'
                       or name like 'alertas-c-%' or name like 'alertas-d-%'
                       or name like 'alertas-e-%' or name like 'alertas-f-%'""")
            for f in cur.fetchall():
                org = f["id"]
                cur.execute("delete from asistente.alertas_operativas where organization_id=%s", (org,))
                cur.execute("delete from asistente.usage_daily where organization_id=%s", (org,))
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
print("TODO EN VERDE  --  reglas + estado contra PostgreSQL real")
print("=" * 70)
