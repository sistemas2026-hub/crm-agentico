# -*- coding: utf-8 -*-
"""
================================================================================
 PRUEBA DE VELOCIDAD PERCIBIDA  -  streaming, local vs DeepSeek
================================================================================

Mide lo que el ojo humano nota, no solo el total:

  - tiempo al PRIMER token   -> cuanto se espera antes de ver algo
  - tok/s DURANTE la generacion -> que tan rapido sigue apareciendo el texto
  - tiempo total

Un modelo puede tener el mismo tiempo total que otro y sentirse muy distinto
si uno empieza a responder en 0.3s y el otro en 8s callado.

Usa la MISMA pregunta real (redactar sobre datos ya calculados, sin PII: la
ruta ya aprobada para DeepSeek) contra los dos modelos, con streaming real.

Uso
---
    py -3.13 cli/prueba_velocidad.py
================================================================================
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(override=True)

SISTEMA = (
    "Eres analista de operaciones de un ISP. Redacta un informe breve en "
    "espanol a partir de los datos que se te entregan. No calcules nada: "
    "todos los numeros que necesitas ya estan en los datos. Se concreto.")

# La misma tarea real que ya corre en produccion: redactar sobre el informe de
# materiales de julio, con los totales ya calculados por Python.
DATOS = """
{
  "periodo": "2026-07-01 a 2026-07-31",
  "consumo_total": {"CABLE DROP": 9913.0, "CONECTOR APC": 358.0,
                     "CONECTOR COAXIAL": 280.0, "ONU CATV": 177.0,
                     "TORNILLO": 132.0, "CHAZO": 123.0},
  "tickets_cerrados": 2736, "con_registro_de_material": 460,
  "cobertura_categorias_con_visita": {
    "Instalacion Nueva Realizada": {"tickets": 80, "con_registro": 69, "pct": 86.2},
    "Cambio De Router Wifi": {"tickets": 76, "con_registro": 75, "pct": 98.7},
    "Problema De Conexion": {"tickets": 48, "con_registro": 24, "pct": 50.0}
  }
}
"""
PREGUNTA = f"Redacta el resumen ejecutivo de este informe:\n{DATOS}"


def probar_ollama(modelo: str):
    import ollama
    t0 = time.monotonic()
    primero = None
    n_chars_primer_bloque = 0
    texto = ""
    n_bloques = 0

    for parte in ollama.chat(
            model=modelo,
            messages=[{"role": "system", "content": SISTEMA},
                      {"role": "user", "content": PREGUNTA}],
            stream=True):
        frag = (parte.get("message", {}) or {}).get("content") or ""
        pensando = (parte.get("message", {}) or {}).get("thinking") or ""
        if frag:
            if primero is None:
                primero = time.monotonic() - t0
            texto += frag
            n_bloques += 1
        if pensando and primero is None:
            pass  # el pensamiento no cuenta como "texto visible"

    total = time.monotonic() - t0
    return {"ttft": primero or total, "total": total, "chars": len(texto),
            "bloques": n_bloques, "texto": texto}


def probar_deepseek(modelo: str):
    from openai import OpenAI
    clave = os.environ.get("DEEPSEEK_API_KEY")
    if not clave:
        raise SystemExit("Falta DEEPSEEK_API_KEY en el .env")
    cli = OpenAI(api_key=clave, base_url="https://api.deepseek.com")

    t0 = time.monotonic()
    primero = None
    texto = ""
    n_bloques = 0

    stream = cli.chat.completions.create(
        model=modelo,
        messages=[{"role": "system", "content": SISTEMA},
                  {"role": "user", "content": PREGUNTA}],
        stream=True)
    for chunk in stream:
        delta = chunk.choices[0].delta
        frag = getattr(delta, "content", None) or ""
        if frag:
            if primero is None:
                primero = time.monotonic() - t0
            texto += frag
            n_bloques += 1

    total = time.monotonic() - t0
    return {"ttft": primero or total, "total": total, "chars": len(texto),
            "bloques": n_bloques, "texto": texto}


def mostrar(nombre: str, r: dict):
    tok_aprox = r["chars"] / 4                      # ~4 caracteres/token en espanol
    t_generando = max(r["total"] - r["ttft"], 0.001)
    print(f"\n{'='*72}")
    print(f"  {nombre}")
    print(f"{'='*72}")
    print(f"  Tiempo hasta la PRIMERA palabra visible : {r['ttft']:.2f} s")
    print(f"  Tiempo total                            : {r['total']:.2f} s")
    print(f"  Caracteres generados                    : {r['chars']}")
    print(f"  Velocidad DURANTE la generacion          : "
          f"{tok_aprox / t_generando:.1f} tok/s (aprox.)")
    print(f"  Fragmentos recibidos (eventos de red)    : {r['bloques']}")
    print(f"\n  --- primeras 280 caracteres del texto ---")
    print(f"  {r['texto'][:280].strip()}...")


if __name__ == "__main__":
    print("Misma pregunta, streaming real, a los dos modelos.")
    print("(sin datos de cliente: es la ruta ya aprobada para DeepSeek)\n")

    print("Corriendo local (qwen3:30b-a3b-q4_K_M)...")
    local = probar_ollama("qwen3:30b-a3b-q4_K_M")
    mostrar("LOCAL  -  qwen3:30b-a3b-q4_K_M", local)

    print("\nCorriendo DeepSeek (deepseek-v4-flash)...")
    api = probar_deepseek("deepseek-v4-flash")
    mostrar("API  -  deepseek-v4-flash", api)

    print(f"\n{'='*72}")
    print("  COMPARACION DIRECTA")
    print(f"{'='*72}")
    print(f"  Espera antes de ver algo   : local {local['ttft']:.2f}s "
          f"  vs   deepseek {api['ttft']:.2f}s "
          f"  ({local['ttft']/max(api['ttft'],0.01):.1f}x mas rapido deepseek)")
    print(f"  Tiempo total               : local {local['total']:.2f}s "
          f"  vs   deepseek {api['total']:.2f}s "
          f"  ({local['total']/max(api['total'],0.01):.1f}x mas rapido deepseek)")
