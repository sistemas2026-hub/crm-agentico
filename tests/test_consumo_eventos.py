# -*- coding: utf-8 -*-
"""
================================================================================
 EVENTOS DE CONSUMO  --  que se cuente todo, y que cada cosa cuente donde va
================================================================================

    DBHOST=... DBPORT=... DBNAME=... DBUSER=... DBPASSWORD=...
    py -3.13 tests/test_consumo_eventos.py

CONTRA POSTGRES REAL, no en memoria. Lo que se prueba aca es que una fila
quede escrita con el aislamiento y los checks puestos, y eso no se puede
simular: un 'check' que falta solo se ve cuando la base rechaza --o acepta--
lo que no debia.

QUE SE VIGILA, Y POR QUE EN ESTE ORDEN
---------------------------------------
  1. Que el gasto de produccion cuente para el tope, y que el de pruebas NO.
     Es la razon de ser de toda esta tabla. Hasta el 05/10/2026 habia que
     elegir entre contar las pruebas --y que el tope saltara por trabajo que
     nadie facturo-- o no contarlas y no saber cuanto costaron. Medido ese
     dia: el saldo del proveedor bajo $6.78 mientras el sistema calculaba
     $2.37.
  2. Que un gasto sin tarifa quede VISIBLE. 'costo 0' y 'no sabemos cuanto
     costo' son dos cosas distintas y antes se veian igual.
  3. Que una empresa no vea el consumo de otra.
  4. Que un fallo del contador no tumbe la atencion de un cliente.

NO SE PRUEBA ACA que Vision o la transcripcion produzcan el evento end-to-end
con el proveedor real: eso cuesta plata y vive en sus propias pruebas. Lo que
si se prueba es que el camino que las registra funcione.
================================================================================
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FALTAN = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not __import__("os").environ.get(v)]
if FALTAN:
    print(f"[omitida] faltan {FALTAN}. Esta prueba exige PostgreSQL real.")
    sys.exit(0)

import json
import os

import psycopg
from psycopg.rows import dict_row

from nucleo.observabilidad import consumo
from nucleo.observabilidad import eventos_consumo as ev
from nucleo.persistencia import db

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
#  Dos empresas de verdad.
# =============================================================================

SLUG_A = f"consumo-a-{uuid.uuid4().hex[:8]}"
SLUG_B = f"consumo-b-{uuid.uuid4().hex[:8]}"


def sembrar(slug: str) -> str:
    with crudo() as con, con.cursor() as cur:
        cur.execute("insert into public.organization (name) values (%s) returning id",
                    (slug,))
        org = str(cur.fetchone()["id"])
        cur.execute(
            """insert into asistente.tenant_config (organization_id, slug, config)
               values (%s,%s,%s)""", (org, slug, json.dumps({"version": 1})))
        con.commit()
    return org


class _Tarifa:
    """Lo minimo que _costo necesita: USD por millon, ya resueltas."""
    def __init__(self, nueva, cache, salida):
        self._v = (nueva, cache, salida)

    def por_millon(self, _momento):
        return self._v


class _LLM:
    def __init__(self, tarifas):
        self.tarifas = tarifas


class _Limites:
    def __init__(self, tope):
        self.max_costo_usd_mes = tope


class _Identidad:
    def __init__(self, slug):
        self.slug = slug


class _Config:
    def __init__(self, slug, tope=None, tarifas=None):
        self.identidad = _Identidad(slug)
        self.limites = _Limites(tope)
        self.llm = _LLM(tarifas if tarifas is not None else {
            #  Numeros redondos a proposito: lo que se comprueba es la
            #  aritmetica, no una tarifa real.
            "deepseek:deepseek-v4-flash": _Tarifa(10.0, 1.0, 100.0)})


class _Respuesta:
    def __init__(self, entrada=0, salida=0, cache=0, razonamiento_chars=0):
        self.tokens_entrada = entrada
        self.tokens_salida = salida
        self.tokens_entrada_cache = cache
        self.razonamiento_chars = razonamiento_chars
        self.segundos = 1.5


def eventos_de(slug, **filtros):
    cond = " and ".join(f"{k} = %s" for k in filtros)
    with crudo() as con, con.cursor() as cur:
        cur.execute("select organization_id from asistente.tenant_config where slug=%s",
                    (slug,))
        org = cur.fetchone()["organization_id"]
        sql = ("select * from asistente.consumo_eventos where organization_id = %s"
               + (f" and {cond}" if cond else "") + " order by creado_en")
        cur.execute(sql, (org, *filtros.values()))
        return [dict(f) for f in cur.fetchall()]


print(__doc__)
ORG_A = sembrar(SLUG_A)
ORG_B = sembrar(SLUG_B)
print(f"  empresa A: {SLUG_A}\n  empresa B: {SLUG_B}\n")

try:
    # =========================================================================
    print("1. UNA LLAMADA DE CONVERSACION = UN EVENTO")
    # =========================================================================
    cfg = _Config(SLUG_A, tope=100.0)
    with consumo.abrir(cfg) as ficha:
        consumo.anotar("deepseek:deepseek-v4-flash",
                       _Respuesta(entrada=1000, salida=200, cache=400,
                                  razonamiento_chars=80))

    e = eventos_de(SLUG_A, servicio="conversation")
    comprobar("se escribio exactamente UN evento", len(e) == 1, str(len(e)))
    if e:
        x = e[0]
        comprobar("servicio = conversation", x["servicio"] == "conversation")
        comprobar("proveedor y modelo salen de la referencia",
                  x["proveedor"] == "deepseek"
                  and x["modelo"] == "deepseek-v4-flash")
        comprobar("origen = production por defecto en abrir()",
                  x["origen"] == "production")
        comprobar("entrada", x["input_tokens"] == 1000)
        comprobar("cacheados (subconjunto de la entrada)",
                  x["cached_input_tokens"] == 400)
        comprobar("salida", x["output_tokens"] == 200)
        comprobar("razonamiento: de caracteres a tokens (~4 por token)",
                  x["reasoning_tokens"] == 20, str(x["reasoning_tokens"]))
        comprobar("hay_tarifa", x["hay_tarifa"] is True)
        #  600 nuevos x 10 + 400 cacheados x 1 + 200 salida x 100 = 26.400
        #  sobre un millon = 0.0264
        comprobar("el costo usa cache y salida por separado",
                  abs(float(x["costo_usd"]) - 0.0264) < 1e-9,
                  str(x["costo_usd"]))

    # =========================================================================
    print("\n2. CADA LLAMADA ES UN EVENTO  (los reintentos TAMBIEN)")
    # =========================================================================
    cfg2 = _Config(SLUG_B, tope=100.0)
    with consumo.abrir(cfg2):
        for _ in range(3):
            consumo.anotar("deepseek:deepseek-v4-flash",
                           _Respuesta(entrada=100, salida=10))
    e = eventos_de(SLUG_B, servicio="conversation")
    comprobar("tres llamadas -> tres eventos", len(e) == 3, str(len(e)))
    comprobar("y ninguno duplicado",
              len({str(x["id"]) for x in e}) == 3)

    # =========================================================================
    print("\n3. EL ORIGEN DECIDE QUIEN PAGA  (lo central)")
    # =========================================================================
    cfg3 = _Config(SLUG_A, tope=100.0)
    for origen in (ev.EVALUACION, ev.PRUEBA):
        with consumo.abrir(cfg3, origen=origen):
            consumo.anotar("deepseek:deepseek-v4-flash",
                           _Respuesta(entrada=1_000_000, salida=0))

    comprobar("una evaluacion deja su evento",
              len(eventos_de(SLUG_A, origen="evaluation")) == 1)
    comprobar("una prueba tambien",
              len(eventos_de(SLUG_A, origen="test")) == 1)

    with crudo() as con, con.cursor() as cur:
        cur.execute("select asistente.gasto_produccion_del_mes(%s) g", (ORG_A,))
        gasto_prod = float(cur.fetchone()["g"])
        cur.execute("""select coalesce(sum(costo_usd),0) t
                         from asistente.consumo_eventos where organization_id=%s""",
                    (ORG_A,))
        gasto_todo = float(cur.fetchone()["t"])

    comprobar("el gasto TOTAL incluye evaluacion y prueba",
              gasto_todo > gasto_prod, f"total={gasto_todo} prod={gasto_prod}")
    comprobar("pero el que cuenta para el tope NO las incluye",
              abs(gasto_prod - 0.0264) < 1e-6, str(gasto_prod))

    #  Y la otra mitad: una evaluacion no escribe en usage_daily.
    with crudo() as con, con.cursor() as cur:
        cur.execute("""select coalesce(sum(costo_usd),0) c, coalesce(sum(n_mensajes),0) m
                         from asistente.usage_daily where organization_id=%s""", (ORG_A,))
        ud = cur.fetchone()
    comprobar("usage_daily solo tiene el turno de produccion",
              int(ud["m"]) == 1, f"{ud['m']} turnos")
    comprobar("y su costo coincide con el de produccion",
              abs(float(ud["c"]) - 0.0264) < 1e-6, str(ud["c"]))

    # =========================================================================
    print("\n4. EL TOPE, CON EVENTOS REALES")
    # =========================================================================
    cfg_tope = _Config(SLUG_A, tope=0.02)       # ya gastamos 0.0264
    estado = consumo.estado_del_gasto(cfg_tope, SLUG_A)
    comprobar("con el gasto de produccion por encima del tope: frenar",
              estado["accion"] == "frenar", str(estado))

    cfg_alto = _Config(SLUG_A, tope=100.0)
    comprobar("con margen de sobra: seguir",
              consumo.estado_del_gasto(cfg_alto, SLUG_A)["accion"] == "seguir")

    #  La prueba que de verdad importa: si las evaluaciones contaran, este
    #  tope habria saltado. El gasto de evaluacion fue 10 USD.
    cfg_medio = _Config(SLUG_A, tope=1.0)
    comprobar("una evaluacion cara NO dispara el tope del tenant",
              consumo.estado_del_gasto(cfg_medio, SLUG_A)["accion"] == "seguir",
              "si esto falla, las pruebas estan facturando")

    # =========================================================================
    print("\n5. SIN TARIFA: SE VE QUE HUBO GASTO Y NO CUANTO")
    # =========================================================================
    sin = _Config(SLUG_B, tope=100.0, tarifas={})
    with consumo.abrir(sin):
        consumo.anotar("anthropic:claude-sonnet-5",
                       _Respuesta(entrada=5000, salida=500))
    e = eventos_de(SLUG_B, modelo="claude-sonnet-5")
    comprobar("el evento se escribe igual", len(e) == 1)
    if e:
        comprobar("hay_tarifa = false", e[0]["hay_tarifa"] is False)
        comprobar("costo = 0 (no un estimado)", float(e[0]["costo_usd"]) == 0.0)
        comprobar("los TOKENS si quedan: el gasto no se esconde",
                  e[0]["input_tokens"] == 5000 and e[0]["output_tokens"] == 500)
        comprobar("proveedor anthropic", e[0]["proveedor"] == "anthropic")

    res = ev.resumen(SLUG_B, dias=1)
    comprobar("el resumen lo marca como sin tarifa",
              any(f["modelo"] == "claude-sonnet-5" for f in res["sin_tarifa"]),
              str(res["sin_tarifa"]))

    # =========================================================================
    print("\n6. VISION Y TRANSCRIPCION  (eventos sueltos, sin turno abierto)")
    # =========================================================================
    #  Sin 'abrir': es exactamente como corren en api.py, antes del turno.
    with ev.origen(ev.PRODUCCION):
        ok_v = ev.anotar_evento(SLUG_A, ev.VISION, "deepseek", "deepseek-v4-flash",
                                entrada=2399, costo_usd=0.024, hay_tarifa=True,
                                metadatos={"segundos": 8.0})
        ok_t = ev.anotar_evento(SLUG_A, ev.TRANSCRIPCION, "openai",
                                "gpt-4o-transcribe", entrada=36,
                                hay_tarifa=False)
    comprobar("vision deja su evento SIN turno abierto", ok_v)
    comprobar("la transcripcion tambien", ok_t)
    v = eventos_de(SLUG_A, servicio="vision")
    t = eventos_de(SLUG_A, servicio="transcription")
    comprobar("vision: servicio y proveedor correctos",
              len(v) == 1 and v[0]["proveedor"] == "deepseek")
    comprobar("vision entra como produccion", v and v[0]["origen"] == "production")
    comprobar("transcripcion: sin tarifa, pero con sus tokens",
              len(t) == 1 and t[0]["hay_tarifa"] is False
              and t[0]["input_tokens"] == 36)

    # =========================================================================
    print("\n7. AISLAMIENTO ENTRE EMPRESAS")
    # =========================================================================
    de_a = eventos_de(SLUG_A)
    de_b = eventos_de(SLUG_B)
    comprobar("A tiene sus eventos", len(de_a) >= 5)
    comprobar("B tiene los suyos", len(de_b) >= 4)
    comprobar("ningun evento de A pertenece a B",
              all(str(x["organization_id"]) == ORG_A for x in de_a))
    comprobar("ni al reves",
              all(str(x["organization_id"]) == ORG_B for x in de_b))

    res_a = ev.resumen(SLUG_A, dias=1)
    comprobar("el resumen de A no trae el modelo que solo uso B",
              not any(f["modelo"] == "claude-sonnet-5" for f in res_a["por_modelo"]),
              str(res_a["por_modelo"]))

    # =========================================================================
    print("\n8. LOS CHECKS DE LA TABLA")
    # =========================================================================
    with crudo() as con, con.cursor() as cur:
        for etiqueta, sql, args in (
            ("un servicio inventado se rechaza",
             "insert into asistente.consumo_eventos (organization_id, servicio, proveedor, modelo) values (%s,'astrologia','x','y')", (ORG_A,)),
            ("un origen inventado se rechaza",
             "insert into asistente.consumo_eventos (organization_id, servicio, proveedor, modelo, origen) values (%s,'vision','x','y','produccion_real')", (ORG_A,)),
            ("cache mayor que la entrada se rechaza",
             "insert into asistente.consumo_eventos (organization_id, servicio, proveedor, modelo, input_tokens, cached_input_tokens) values (%s,'vision','x','y',10,20)", (ORG_A,)),
            ("costo sin tarifa se rechaza",
             "insert into asistente.consumo_eventos (organization_id, servicio, proveedor, modelo, costo_usd, hay_tarifa) values (%s,'vision','x','y',1.5,false)", (ORG_A,)),
        ):
            try:
                cur.execute(sql, args)
                con.rollback()
                comprobar(etiqueta, False, "la base lo ACEPTO")
            except Exception:
                con.rollback()
                comprobar(etiqueta, True)

    # =========================================================================
    print("\n9. UN FALLO DEL CONTADOR NO TUMBA LA ATENCION")
    # =========================================================================
    ok = ev.anotar_evento("tenant-que-no-existe", ev.VISION, "x", "y", entrada=1)
    comprobar("un tenant inexistente devuelve False, no levanta", ok is False)
    ok = ev.anotar_evento(SLUG_A, "servicio_raro", "x", "y")
    comprobar("un servicio invalido devuelve False, no levanta", ok is False)
    comprobar("el resumen de un tenant inexistente devuelve vacio, no levanta",
              ev.resumen("tenant-que-no-existe")["por_origen"] == [])

    #  Y lo que de verdad importa: que anotar() no reviente el turno aunque la
    #  base este caida. Se simula rompiendo la sesion.
    import nucleo.observabilidad.eventos_consumo as modulo_ev

    def _sesion_rota(*a, **k):
        raise RuntimeError("la base no responde")

    original = modulo_ev.sesion
    modulo_ev.sesion = _sesion_rota
    try:
        with consumo.abrir(_Config(SLUG_A, tope=100.0)):
            consumo.anotar("deepseek:deepseek-v4-flash",
                           _Respuesta(entrada=10, salida=1))
        comprobar("con la base de eventos caida, el turno termina igual", True)
    except Exception as e:
        comprobar("con la base de eventos caida, el turno termina igual",
                  False, f"{type(e).__name__}")
    finally:
        modulo_ev.sesion = original

    # =========================================================================
    print("\n10. EL RESUMEN QUE VE EL PANEL")
    # =========================================================================
    res = ev.resumen(SLUG_A, dias=1)
    origenes = {f["origen"] for f in res["por_origen"]}
    comprobar("separa produccion de evaluacion y prueba",
              {"production", "evaluation", "test"} <= origenes, str(origenes))
    servicios = {f["servicio"] for f in res["por_servicio"]}
    comprobar("distingue los tres servicios que hoy gastan",
              {"conversation", "vision", "transcription"} <= servicios,
              str(servicios))
    comprobar("y dice que modelos se usaron sin tarifa",
              isinstance(res["sin_tarifa"], list))

finally:
    try:
        with crudo() as con, con.cursor() as cur:
            for org in (ORG_A, ORG_B):
                cur.execute("delete from asistente.consumo_eventos where organization_id=%s", (org,))
                cur.execute("delete from asistente.usage_daily where organization_id=%s", (org,))
                cur.execute("delete from asistente.tenant_config where organization_id=%s", (org,))
                cur.execute("delete from public.organization where id=%s", (org,))
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
