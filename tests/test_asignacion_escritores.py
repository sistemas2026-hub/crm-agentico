# -*- coding: utf-8 -*-
"""
================================================================================
 B3.4 (D4)  --  una sola puerta para cambiar QUIEN tiene una conversacion
================================================================================

    py -3.13 tests/test_asignacion_escritores.py          (sin base)

La exclusion de D4 (dos operadores nunca creen que ambos la tienen) vive en
nucleo/relevo/transiciones.py: fila bloqueada con FOR UPDATE, precondicion,
escritura y evento en una transaccion. Sirve solo si NADIE MAS escribe la
asignacion por otro lado. Esta suite lo vigila sobre el codigo fuente:

  1. Fuera de transiciones.py, ningun archivo del motor, del CLI, del backend
     Django ni del frontend escribe asignada_a_usuario_id, asignada_a_nombre,
     asignada_en, tomada_por ni tomada_en. Las migraciones historicas que ya
     corrieron estan listadas por nombre: una nueva que escriba, falla.
  2. Dentro de transiciones.py, cada funcion que escribe esas columnas lo hace
     desde un 'cuerpo' que corre por _ejecutar(), y _fila() bloquea la fila.

Las carreras reales (dos operadores, tomar contra reasignar) estan en
tests/test_relevo_transiciones_base.py, seccion 13.
================================================================================
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


COLUMNAS = r"(asignada_a_usuario_id|asignada_a_nombre|asignada_en|tomada_por|tomada_en)"
# Una escritura: 'columna = valor' en un SET, o la columna en la lista de un
# INSERT ... (cols). Un 'where tomada_por = %s' tambien entra: se prefiere un
# falso positivo que revisar a un escritor que se escapa.
ESCRITURA = re.compile(COLUMNAS + r"\s*=(?!=)", re.IGNORECASE)
PERMITIDO = RAIZ / "nucleo" / "relevo" / "transiciones.py"
# Migraciones que ya corrieron en produccion. No se editan: se listan.
MIGRACIONES_HISTORICAS = {"202609071900_tomar_caso.sql"}

print("=" * 74)
print(" B3.4: una sola puerta para la asignacion")
print("=" * 74)

print("\n== 1. nadie mas escribe la asignacion ==")
carpetas = [RAIZ / "nucleo", RAIZ / "cli", RAIZ / "supabase",
            RAIZ / "django-crm" / "backend", RAIZ / "django-crm" / "frontend" / "src"]
extensiones = {".py", ".sql", ".js", ".ts", ".svelte"}
hallados = []
revisados = 0
for carpeta in carpetas:
    for archivo in carpeta.rglob("*"):
        if (archivo.suffix not in extensiones or not archivo.is_file()
                or "node_modules" in archivo.parts or "__pycache__" in archivo.parts
                or ".svelte-kit" in archivo.parts or archivo == PERMITIDO
                or archivo.name in MIGRACIONES_HISTORICAS):
            continue
        revisados += 1
        texto = archivo.read_text(encoding="utf-8", errors="replace")
        for n, linea in enumerate(texto.splitlines(), 1):
            sin_comentario = linea.split("--")[0] if archivo.suffix == ".sql" else linea
            if ESCRITURA.search(sin_comentario) and not sin_comentario.lstrip().startswith(("#", "//", "*")):
                hallados.append(f"{archivo.relative_to(RAIZ)}:{n}: {linea.strip()[:90]}")
comprobar(revisados > 300, f"se revisaron los archivos del proyecto ({revisados})")
comprobar(not hallados, "ningun escritor de la asignacion fuera de transiciones.py"
          + ("".join(f"\n          {h}" for h in hallados) if hallados else ""))

print("\n== 2. dentro de transiciones.py, todo pasa por la fila bloqueada ==")
fuente = PERMITIDO.read_text(encoding="utf-8")
arbol = ast.parse(fuente)
funciones = {n.name: n for n in arbol.body if isinstance(n, ast.FunctionDef)}
fila = ast.get_source_segment(fuente, funciones["_fila"])
comprobar("for update" in fila.lower(), "_fila() bloquea la fila (FOR UPDATE)")
escritoras = []
for nombre, nodo in funciones.items():
    segmento = ast.get_source_segment(fuente, nodo)
    if nombre.startswith("_") or not ESCRITURA.search(segmento):
        continue
    escritoras.append(nombre)
    anidadas = [n for n in nodo.body if isinstance(n, ast.FunctionDef) and n.name == "cuerpo"]
    retorno = [n for n in nodo.body if isinstance(n, ast.Return) and isinstance(n.value, ast.Call)
               and getattr(n.value.func, "id", "") == "_ejecutar"]
    fuera_del_cuerpo = [n for n in nodo.body if not isinstance(n, ast.FunctionDef)
                        and ESCRITURA.search(ast.get_source_segment(fuente, n) or "")]
    comprobar(bool(anidadas) and bool(retorno) and not fuera_del_cuerpo,
              f"{nombre}: escribe solo dentro de cuerpo(), que corre por _ejecutar()")
comprobar({"intervenir", "tomar", "soltar", "reasignar", "resolver", "devolver_a_ia"} <= set(escritoras),
          f"se reconocen las transiciones que escriben la asignacion ({sorted(escritoras)})")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] La asignacion se escribe por una sola puerta.")
