# -*- coding: utf-8 -*-
"""
================================================================================
 REPORTE DE HUECOS EN LA DOCUMENTACION  --  que pregunto la gente y no supimos
================================================================================

Nace de una idea que quedo dando vueltas sin construirse: cada vez que el
asistente no encuentra en el corpus un fragmento suficientemente parecido a
lo que preguntaron (RAG por debajo de 'umbral_similitud'), no llama al
modelo -- responde el mensaje configurado y guarda la pregunta en
asistente.unanswered_queries. Esa tabla existe desde el esquema original
(01_schema.sql, seccion 6) y se llena sola en cada turno
(nucleo/recuperacion/busqueda.py) desde hace meses. Nadie la habia leido.

Es la diferencia entre un asistente que solo contesta y uno que mejora con
el uso: agrupa las preguntas repetidas -- la que mas veces aparece es la que
mas vale la pena escribir en el manual primero, y una vez escrita el
proximo que pregunte lo mismo si recibe respuesta.

Uso
---
    py -3.13 cli/reporte_huecos_documentacion.py --tenant rapilink --dias 30
    py -3.13 cli/reporte_huecos_documentacion.py --tenant rapilink --dias 30 --todas
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

from nucleo.persistencia import db as persistencia


def main(tenant: str, dias: int, incluir_revisadas: bool) -> None:
    filas = persistencia.preguntas_sin_respuesta(tenant, dias, incluir_revisadas)

    print(f"Tenant: {tenant}  |  Ultimos {dias} dia(s)"
         f"{'  |  incluye ya revisadas' if incluir_revisadas else ''}")

    if not filas:
        print("\n  (sin preguntas sin respuesta en el periodo -- o ya estan "
             "todas revisadas, probar con --todas)")
        return

    total_ocurrencias = sum(f["n"] for f in filas)
    print(f"Preguntas distintas: {len(filas)}  |  Ocurrencias totales: "
         f"{total_ocurrencias}\n")

    for f in filas:
        rol = f["rol_ejemplo"] or "(sin rol)"
        similitud = f"{f['peor_similitud']:.2f}" if f["peor_similitud"] is not None else "?"
        print(f"  {f['n']:>3}x  [{similitud} similitud]  "
             f"({rol})  {f['pregunta_ejemplo']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--dias", type=int, default=30)
    parser.add_argument("--todas", action="store_true",
                        help="Incluye las que ya se marcaron como revisadas")
    args = parser.parse_args()
    main(args.tenant, args.dias, args.todas)
