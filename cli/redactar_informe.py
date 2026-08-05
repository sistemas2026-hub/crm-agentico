# -*- coding: utf-8 -*-
"""
================================================================================
 REDACCION DEL INFORME  -  aqui SI entra el modelo, pero solo a escribir
================================================================================

Division del trabajo
--------------------
    informe_materiales.py  ->  CALCULA   (Python, determinista)
    redactar_informe.py    ->  REDACTA   (el modelo, sobre numeros ya resueltos)

El modelo recibe ~14 totales y una tabla de cobertura. NUNCA los 2.736 tickets.
No suma, no promedia, no saca porcentajes: todo eso viene calculado en la
entrada. Su trabajo es convertir una tabla en algo que una persona lea.

El guardarrail
--------------
Se extrae CADA numero del texto que devuelve el modelo y se comprueba que
exista en la entrada. Si aparece uno que nadie le dio, se marca y el informe
no se da por bueno. El modelo redacta libre; el codigo audita las cifras.

Es la unica forma de dejarlo escribir con soltura sin arriesgar que invente un
dato — y es barata: una expresion regular y una comparacion de conjuntos.

Datos y suposiciones, separados
-------------------------------
Se le pide que etiquete sus interpretaciones como HIPOTESIS. Un modelo mirando
una tabla puede sugerir por que una categoria va baja, pero no tiene forma de
saberlo. Si eso se mezcla con los datos, en dos semanas alguien cita la
suposicion como si fuera una medicion.

Uso
---
    py -3.13 redactar_informe.py informe_materiales_2026-07-01_2026-07-31.json
================================================================================
"""

import os
import re
import sys
import json

import ollama

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Para informes no hay prisa: corren de noche o bajo demanda, y nadie espera
# mirando la pantalla. Conviene el modelo mas capaz disponible, no el mas
# rapido. Por eso NO se reutiliza MODELO_REDACCION, que esta afinado para el
# chat en vivo.
MODELO = os.environ.get("MODELO_INFORME", "qwen3:30b-a3b-q4_K_M")

MIN_TICKETS_CATEGORIA = 10      # categorias con menos no dicen nada util


def _candidatos(token):
    """
    Lecturas posibles de un numero escrito, como VALORES y no como texto.

    En espanol '9.913' puede ser nueve mil novecientos trece o nueve coma
    novecientos trece. Se prueban las dos y basta con que una cuadre.

    Comparar como cadenas era el error de la primera version: el modelo
    escribia '50%' donde el dato decia '50.0' y se marcaba como inventado.
    Un guardarrail que da falsos positivos termina ignorandose, que es peor
    que no tenerlo.
    """
    t = token.strip().rstrip(".,")
    out = set()
    for lectura in (t, t.replace(".", "").replace(",", ""), t.replace(",", ".")):
        try:
            out.add(round(float(lectura), 3))
        except ValueError:
            pass
    return out


def _valores(texto):
    """Conjunto de valores numericos presentes en un texto."""
    out = set()
    for token in re.findall(r"\d[\d.,]*", str(texto)):
        out |= _candidatos(token)
    return out


def preparar_entrada(inf):
    """
    Arma lo que ve el modelo: numeros ya calculados y nada mas.

    Los derivados (porcentajes, promedios) se calculan AQUI. Si no se los
    damos hechos, el modelo va a intentar dividir — y esa es exactamente la
    operacion que no debe hacer.
    """
    cerrados = inf["tickets_cerrados"]
    con_reg = inf["con_registro_de_material"]

    categorias = {c: v for c, v in inf["cobertura_por_categoria"].items()
                  if v["tickets"] >= MIN_TICKETS_CATEGORIA}
    con_trabajo = {c: v for c, v in categorias.items() if v["pct"] >= 50}
    sin_trabajo = {c: v for c, v in categorias.items() if v["pct"] == 0}

    trabajos = con_reg - inf["registros_en_cero"]
    promedios = {m: round(v / trabajos, 1) for m, v in inf["totales"].items()} \
        if trabajos else {}

    return {
        "periodo": inf["periodo"],
        "consumo_total": inf["totales"],
        "promedio_por_trabajo_con_consumo": promedios,
        "tickets_cerrados": cerrados,
        "con_registro_de_material": con_reg,
        "porcentaje_con_registro": round(100 * con_reg / cerrados, 1) if cerrados else 0,
        "registros_en_cero": inf["registros_en_cero"],
        "trabajos_con_consumo": trabajos,
        "cobertura_categorias_con_visita": con_trabajo,
        "cobertura_categorias_sin_visita": sin_trabajo,
        "registros_a_revisar": len(inf["sin_normalizar"]),
        "advertencia_oficial": inf["advertencia"],
    }


INSTRUCCIONES = """Eres analista de operaciones de un proveedor de internet (ISP).
Redacta un informe breve en espanol a partir de los datos que se te entregan.

REGLAS ESTRICTAS:
1. NO CALCULES NADA. No sumes, no restes, no dividas, no saques porcentajes.
   Todos los numeros que necesitas ya estan en los datos. Usa solo esos, tal cual.
2. Si un numero no esta en los datos, no lo escribas.
3. Separa los hechos de tus interpretaciones. Las interpretaciones van en una
   seccion aparte y cada una empieza con "HIPOTESIS:".
4. Las categorias sin visita (acuerdos de pago, no contesta, encuestas) tienen
   0% de registro y eso es CORRECTO: ahi no se gasta material porque nadie va a
   terreno. No lo presentes como incumplimiento.
5. Incluye al final, textual, la advertencia oficial que viene en los datos.

ESTRUCTURA:
  RESUMEN          2 o 3 frases: que se consumio y en cuantos trabajos.
  CONSUMO          Los materiales principales.
  COBERTURA        Que tan completo es el registro, por tipo de trabajo.
  A REVISAR        Lo que quedo pendiente de verificacion.
  HIPOTESIS        Tus interpretaciones, cada una marcada. Maximo 3.
  ADVERTENCIA      La advertencia oficial, textual.

Se concreto y sobrio. Sin adjetivos de relleno."""


def redactar(datos):
    resp = ollama.chat(model=MODELO, messages=[
        {"role": "system", "content": INSTRUCCIONES},
        {"role": "user", "content": json.dumps(datos, ensure_ascii=False, indent=2)},
    ])
    return (resp["message"].get("content") or "").strip()


def auditar(texto, datos):
    """
    Devuelve los numeros del texto que NO estan en los datos de entrada.

    Se toleran los que provienen del propio periodo (anios, meses, dias): son
    parte de la fecha y no cifras de negocio.
    """
    permitidos = _valores(json.dumps(datos, ensure_ascii=False))
    permitidos |= _valores(datos["periodo"])
    # El modelo puede enumerar ("1.", "2.", "3.") o citar el ano suelto.
    permitidos |= {1.0, 2.0, 3.0, 2026.0}

    sospechosos = []
    for token in re.findall(r"\d[\d.,]*", texto):
        if not (_candidatos(token) & permitidos):
            sospechosos.append(token.rstrip(".,"))
    return sorted(set(sospechosos))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: py -3.13 redactar_informe.py <informe_materiales_*.json>")

    with open(sys.argv[1], encoding="utf-8") as f:
        informe = json.load(f)

    datos = preparar_entrada(informe)
    print(f"Redactando con {MODELO}...")
    print(f"  El modelo recibe {len(json.dumps(datos))} caracteres de numeros "
          f"ya calculados (ningun ticket).\n")

    texto = redactar(datos)
    print("=" * 72)
    print(texto)
    print("=" * 72)

    raros = auditar(texto, datos)
    if raros:
        print(f"\n  [!] AUDITORIA: {len(raros)} numero(s) del texto NO estan en "
              f"la entrada: {', '.join(raros[:12])}")
        print("      Revisar antes de publicar: pueden ser calculos del modelo.")
    else:
        print("\n  [OK] AUDITORIA: todos los numeros del texto vienen de los datos.")

    salida = sys.argv[1].replace(".json", "_redactado.txt")
    with open(salida, "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    print(f"  Guardado en: {salida}\n")
