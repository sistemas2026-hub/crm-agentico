# -*- coding: utf-8 -*-
"""
================================================================================
 BANCO DE PRUEBAS  -  comparar modelos con TU prompt y TUS herramientas
================================================================================

Para que sirve
--------------
Responder con datos, y no con opiniones, tres preguntas:

  1. ¿Elige bien la herramienta y sus argumentos?
  2. ¿RESPETA el dato que le entrega la herramienta, o lo inventa?
  3. ¿Cuanto tarda, y cuanto de ese tiempo es razonamiento que se descarta?

La 2 es la importante. La leccion de gemma3 esta en el PRD: un modelo que no
maneja el rol 'tool' no falla con un error, responde con datos inventados y
tono seguro. Ningun benchmark publico avisa de eso; esta prueba si.

Por que importa medir el 'thinking'
-----------------------------------
El PRD mide 2.500-5.400 caracteres de razonamiento por turno, que se generan
y se DESCARTAN. Si el grueso de la latencia esta ahi, es tiempo recuperable
sin comprar hardware: ninguna GPU arregla tokens que sobran.

Importante
----------
NO llama a la API de WispHub. Los resultados de herramienta son fijos e
inventados a proposito, para poder comprobar si el modelo los repite tal cual.

Uso
---
    py -3.13 banco_pruebas.py                      (todos los instalados)
    py -3.13 banco_pruebas.py qwen3:4b qwen3:30b-a3b-q4_K_M
================================================================================
"""

import sys
import json
import time

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import soporte_wisphub as sw
from nucleo.modelo import cliente as mc


# ==============================================================================
#  CASOS
# ==============================================================================
# Cada caso declara que herramienta se espera y que argumentos son
# imprescindibles. Se comprueban SOLO esos: si el modelo agrega otros, no se
# le penaliza; lo que importa es que no se equivoque en los que definen la
# consulta.

CASOS_HERRAMIENTA = [
    {"area": "soporte", "pregunta": "necesito los datos del cliente 4821",
     "espera": "consultar_cliente", "args": {"id_cliente": "4821"}},

    {"area": "soporte", "pregunta": "busca al cliente con cedula 1082345678",
     "espera": "consultar_cliente_por_cedula", "args": {"cedula": "1082345678"}},

    {"area": "soporte", "pregunta": "que paso con el ticket 89266?",
     "espera": "consultar_ticket", "args": {"id_ticket": "89266"}},

    {"area": "soporte", "pregunta": "que tickets tiene el cliente 4821",
     "espera": "consultar_tickets_de_cliente", "args": {"id_cliente": "4821"}},

    {"area": "soporte", "pregunta": "cuantos clientes suspendidos hay?",
     "espera": "consultar_agregado",
     "args": {"entidad": "clientes"}},

    {"area": "facturacion",
     "pregunta": "cuantas facturas pendientes hay en cada zona?",
     "espera": "consultar_agregado",
     "args": {"entidad": "facturas", "agrupar_por": "zona"}},

    {"area": "facturacion", "pregunta": "muestrame las facturas del cliente 4821",
     "espera": "consultar_facturas", "args": {"id_cliente": "4821"}},

    # Sin herramienta posible: lo correcto es NO llamar a ninguna.
    {"area": "soporte",
     "pregunta": "dame la clave del wifi del cliente 4821",
     "espera": None, "args": {}},
]

# --- Respeto al dato: la prueba de gemma3 ---
# El resultado lleva numeros deliberadamente raros. Si el modelo los repite,
# esta usando el dato. Si contesta otra cosa, lo esta inventando.
CASOS_DATO = [
    {
        "area": "facturacion",
        "pregunta": "cuanto debe el cliente 4821?",
        "herramienta": "consultar_facturas",
        "resultado": {"count": 1, "results": [
            {"id_factura": 778931, "estado": "pendiente",
             "total": 127543, "saldo": 127543,
             "fecha_vencimiento": "2026-07-19"}]},
        "debe_contener": ["127543"],
        "no_debe": ["130000", "127.000", "aproximadamente"],
    },
    {
        "area": "soporte",
        "pregunta": "cuantos clientes suspendidos hay?",
        "herramienta": "consultar_agregado",
        "resultado": {
            "total": 8093,
            "interpretacion": "Clientes con estado 'suspendido'.",
        },
        "debe_contener": ["8093", "suspendid"],
        "no_debe": [],
    },
    {
        # RF-15: la interpretacion y la advertencia SOLO sirven si el modelo
        # las repite. Es la unica regla del sistema que depende del prompt y
        # no del codigo; por eso hay que medirla.
        "area": "facturacion",
        "pregunta": "cuantas facturas pendientes hay?",
        "herramienta": "consultar_agregado",
        "resultado": {
            "total": 3427,
            "interpretacion": ("Facturas con estado 'pendiente', periodo por "
                               "defecto del API (~2 ultimos meses de emision)."),
            "advertencia": ("Cuenta FACTURAS pendientes, no clientes morosos: "
                            "un cliente con varias facturas vencidas cuenta "
                            "varias veces."),
        },
        "debe_contener": ["3427"],
        # Se busca la RAIZ, no la frase exacta: el modelo puede escribir
        # "cliente moroso" en singular y estaria transmitiendo el aviso igual.
        # Comparar prosa libre contra frases literales falla por una 's' y
        # convierte un acierto en un falso negativo.
        "rf15": ["pendiente", "moros"],
        "no_debe": [],
    },
]


# ==============================================================================
#  MEDICION
# ==============================================================================

# Precios por millon de tokens, agosto 2026. INDICATIVOS: este mercado se
# mueve semanalmente, hay que verificarlos con el proveedor antes de
# presupuestar. Local = 0: no hay costo por token.
PRECIOS = {
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro":   (0.28, 0.87),
}


def _costo(resp) -> float:
    """USD de esta llamada. 0 si el modelo corre local."""
    p = PRECIOS.get(resp.modelo)
    if not p:
        return 0.0
    return resp.tokens_entrada / 1e6 * p[0] + resp.tokens_salida / 1e6 * p[1]


def probar_herramientas(modelo):
    aciertos = herramienta_ok = args_ok = 0
    tiempos, tokens, pensados, velocidades, costos = [], [], [], [], []

    for caso in CASOS_HERRAMIENTA:
        mensajes = [{"role": "system", "content": sw.construir_system(caso["area"])},
                    {"role": "user", "content": caso["pregunta"]}]
        try:
            r = mc.chat(modelo, mensajes, tools=sw.herramientas_de(caso["area"]))
        except Exception as e:                      # modelo caido, OOM, red
            print(f"    ! {caso['pregunta'][:40]}: {str(e)[:70]}")
            continue
        tiempos.append(r.segundos); tokens.append(r.tokens_salida)
        pensados.append(r.razonamiento_chars); costos.append(_costo(r))
        if r.tok_s:
            velocidades.append(r.tok_s)

        nombre = r.llamadas[0].nombre if r.llamadas else None

        if nombre == caso["espera"]:
            herramienta_ok += 1
            if nombre is None:
                args_ok += 1
                aciertos += 1
            else:
                crudos = r.llamadas[0].argumentos
                bien = all(str(crudos.get(k, "")).strip().lower() == str(v).lower()
                           for k, v in caso["args"].items())
                args_ok += bien
                aciertos += bien

    n = len(CASOS_HERRAMIENTA)
    return {
        "casos": n,
        "herramienta_pct": round(100 * herramienta_ok / n, 1),
        "args_pct": round(100 * args_ok / n, 1),
        "s_medio": round(sum(tiempos) / len(tiempos), 2) if tiempos else 0,
        "tok_s": round(sum(velocidades) / len(velocidades), 1) if velocidades else 0,
        "think_medio": int(sum(pensados) / len(pensados)) if pensados else 0,
        "costo": sum(costos),
    }


def probar_respeto(modelo):
    """Segunda llamada: ya tiene el dato, solo debe redactarlo."""
    respeta = rf15 = invento = 0
    tiempos, pensados, costos = [], [], []
    total_rf15 = sum(1 for c in CASOS_DATO if c.get("rf15"))

    for caso in CASOS_DATO:
        mensajes = [
            {"role": "system", "content": sw.construir_system(caso["area"])},
            {"role": "user", "content": caso["pregunta"]},
            # Formato canonico (el de OpenAI). nucleo/modelo/cliente.py lo
            # adapta a lo que exija cada proveedor: Ollama quiere 'arguments'
            # como diccionario, la API como cadena, y los modelos de
            # razonamiento exigen ademas 'reasoning_content'.
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "call_1", "type": "function",
                             "function": {"name": caso["herramienta"],
                                          "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call_1",
             "name": caso["herramienta"],
             "content": json.dumps(caso["resultado"], ensure_ascii=False)},
        ]
        try:
            r = mc.chat(modelo, mensajes)
        except Exception as e:
            print(f"    ! {caso['pregunta'][:40]}: {str(e)[:70]}")
            continue
        tiempos.append(r.segundos); pensados.append(r.razonamiento_chars)
        costos.append(_costo(r))

        texto = (r.contenido or "").lower()
        # Se quitan separadores de miles: '127.543' y '127,543' son el dato.
        plano = texto.replace(".", "").replace(",", "").replace(" ", "")

        if all(d.lower().replace(".", "") in plano or d.lower() in texto
               for d in caso["debe_contener"]):
            respeta += 1
        if any(d.lower() in texto for d in caso["no_debe"]):
            invento += 1
        if caso.get("rf15") and all(x.lower() in texto for x in caso["rf15"]):
            rf15 += 1

    n = len(CASOS_DATO)
    return {
        "respeta_pct": round(100 * respeta / n, 1),
        "invento": invento,
        "rf15_pct": round(100 * rf15 / total_rf15, 1) if total_rf15 else 0,
        "s_medio": round(sum(tiempos) / len(tiempos), 2) if tiempos else 0,
        "think_medio": int(sum(pensados) / len(pensados)) if pensados else 0,
        "costo": sum(costos),
    }


def modelos_instalados():
    try:
        datos = ollama.list()
    except Exception as e:
        raise SystemExit(f"No responde Ollama: {e}")
    out = []
    for m in datos.get("models", []):
        nombre = m.get("model") or m.get("name")
        if nombre:
            out.append(nombre)
    return out


if __name__ == "__main__":
    modelos = sys.argv[1:] or modelos_instalados()
    print(f"\nProbando {len(modelos)} modelo(s). Sin tocar la API de WispHub.\n")

    filas = []
    for modelo in modelos:
        print(f"  {modelo} ...", flush=True)
        h = probar_herramientas(modelo)
        r = probar_respeto(modelo)
        filas.append((modelo, h, r))
        print(f"     herramienta {h['herramienta_pct']}%  args {h['args_pct']}%  "
              f"respeta {r['respeta_pct']}%  {h['tok_s']} tok/s")

    print("\n" + "=" * 96)
    print(f"  {'modelo':<26} {'herram':>7} {'args':>6} {'respeta':>8} {'inv':>4} "
          f"{'RF-15':>6} {'tok/s':>7} {'s/turno':>8} {'think':>7} {'US$/1k':>8}")
    print("=" * 96)
    for modelo, h, r in filas:
        # Costo extrapolado a 1.000 consultas, para que sea comparable con el
        # volumen real (~300/dia) y no con los 11 casos de la prueba.
        n_casos = h["casos"] + 3
        por_mil = (h["costo"] + r["costo"]) / n_casos * 1000
        print(f"  {modelo:<26} {h['herramienta_pct']:>6.1f}% {h['args_pct']:>5.1f}% "
              f"{r['respeta_pct']:>7.1f}% {r['invento']:>4} {r['rf15_pct']:>5.1f}% "
              f"{h['tok_s']:>7.1f} {h['s_medio'] + r['s_medio']:>8.2f} "
              f"{h['think_medio']:>7} {por_mil:>8.2f}")
    print("=" * 96)
    print("""
  herram  : eligio la herramienta correcta (o ninguna, cuando corresponde)
  args    : ademas acerto los argumentos que definen la consulta
  respeta : repitio el dato que le dio la herramienta, sin alterarlo
  inv     : veces que INVENTO un dato. Tiene que ser 0. No hay margen aqui
  RF-15   : transmitio la interpretacion y la advertencia al colaborador
  think   : caracteres de razonamiento por turno, que se generan y se tiran
  US$/1k  : costo extrapolado a 1.000 consultas. 0 = corre local
""")
