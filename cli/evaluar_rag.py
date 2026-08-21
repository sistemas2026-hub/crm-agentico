# -*- coding: utf-8 -*-
"""
================================================================================
 EVALUAR LA RECUPERACION (RAG)  --  por etapas, no por promedio de similitud
================================================================================

Por que existe
--------------
Hasta ahora la unica forma de saber si el RAG andaba era abrir el simulador y
leer la respuesta. Eso no distingue las tres cosas que fallan distinto y se
arreglan en lugares opuestos:

  - el rol no tiene NINGUN documento asignado   -> permisos (/manual)
  - el documento correcto nunca entra al top-k  -> consulta o busqueda
  - entra pero queda abajo                      -> orden (ahi si, reranker)

Y una cuarta que no se ve nunca leyendo respuestas: que el umbral deje pasar
material que NO responde la pregunta.

Que mide
--------
  Recall@1/@3/@8   si el documento esperado aparece, y que tan arriba
  MRR              lo anterior en un solo numero (1/posicion del primer acierto)
  gate FN          habia respuesta documentada y nada supero el umbral
  gate FP          NO habia respuesta y algo la supero igual
  elegibles        cuantos fragmentos podia ver el rol (0 = problema de
                   permisos, ver supabase/21_diagnostico_recuperacion.sql)

Lo que NO mide
--------------
Si la RESPUESTA final fue buena. Eso es cli/evaluar.py (casos dorados contra
el motor real). Esto mide solo el paso de recuperacion, que es anterior: si el
fragmento correcto no llega, no hay prompt que lo arregle.

Ojo con el umbral y el grounding
--------------------------------
Superar 'umbral_similitud' significa PARECIDO SEMANTICO, no "aca esta la
respuesta". Un fragmento sobre el procedimiento de instalacion puede sacar
0.55 para "cuanto vale instalarlo" y no traer un solo precio. Por eso el gate
es un filtro probabilistico de relevancia y no una garantia de respaldo -- los
casos 'sin_respuesta' de este set existen para medir exactamente ese error.

Uso
---
    py -3.13 cli/evaluar_rag.py rapilink
    py -3.13 cli/evaluar_rag.py rapilink --detalle    # que recupero en cada fallo
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml                                                    # noqa: E402
from dotenv import load_dotenv                                 # noqa: E402

load_dotenv(RAIZ / ".env", override=True)

from nucleo.config import fuente                               # noqa: E402
from nucleo.recuperacion.busqueda import (                     # noqa: E402
    contar_elegibles, recuperar)


def _mismo_documento(codigo: str, esperado: str) -> bool:
    """
    Si dos codigos nombran el mismo documento, tolerando el TRUNCAMIENTO.

    Un documento que no declara codigo en su tabla de metadatos recibe como
    codigo el nombre del archivo cortado a 40 caracteres
    (nucleo/ingesta/docx.py: ruta.stem[:40]), y uno de los de Rapilink queda
    incluso terminado en espacio. Exigir la cadena exacta en el set de
    evaluacion obligaria a escribir esos recortes a mano -- ilegible, y un
    espacio final invisible convierte una etiqueta correcta en un fallo
    fantasma. Paso al escribir este set: 3 de 5 'fallos' eran eso.

    Se comparan los primeros min(len) caracteres, que es exactamente lo que
    el truncamiento conserva. 'G-GO-04' y 'G-GO-05' siguen siendo distintos.
    """
    a = (codigo or "").strip().lower()
    b = (esperado or "").strip().lower()
    if not a or not b:
        return False
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def _posicion(fragmentos, esperados: list[str]) -> int | None:
    """1-based de la primera coincidencia, o None. Compara por codigo de
    documento, no por fragmento: cualquier parte del documento correcto
    cuenta como acierto."""
    for i, f in enumerate(fragmentos, start=1):
        if any(_mismo_documento(f.codigo, e) for e in esperados):
            return i
    return None


def main(slug: str, detalle: bool) -> None:
    casos = yaml.safe_load(
        (RAIZ / "evaluacion" / f"{slug}.rag.yaml").read_text(encoding="utf-8"))["casos"]
    config = fuente.cargar(slug, raiz=RAIZ)
    umbral = config.rag.umbral_similitud
    top_k = config.rag.top_k

    print("=" * 74)
    print(f"  Recuperacion de {slug} -- {len(casos)} caso(s)")
    print(f"  umbral={umbral}  top_k={top_k}  modelo={config.rag.modelo_embeddings}")
    print("=" * 74)

    # Un rol sin documentos hace fallar TODO lo suyo por un motivo que no es
    # de recuperacion. Se cuenta una vez y se reporta aparte.
    elegibles: dict[str, int] = {}
    for c in casos:
        rol = c["rol"]
        if rol not in elegibles:
            elegibles[rol] = contar_elegibles(slug, rol)

    positivos = [c for c in casos if not c.get("sin_respuesta")]
    negativos = [c for c in casos if c.get("sin_respuesta")]

    aciertos = {1: 0, 3: 0, 8: 0}
    suma_rr = 0.0
    gate_fn: list[dict] = []
    brechas: list[dict] = []
    medidos = 0

    print("\n--- positivos (deberia recuperar el documento esperado) ---")
    for c in positivos:
        rol, pregunta = c["rol"], c["pregunta"]
        fragmentos, mejor = recuperar(config, slug, rol, pregunta)
        pos = _posicion(fragmentos, c["espera"])
        recuperados = [f.codigo for f in fragmentos]

        es_brecha = bool(c.get("brecha_conocida"))
        marca = "ok " if pos == 1 else (f"@{pos}" if pos else "NO ")
        if es_brecha:
            marca = "brecha"
            brechas.append({**c, "pos": pos, "recuperados": recuperados})
        else:
            medidos += 1
            if pos:
                suma_rr += 1.0 / pos
                for k in (1, 3, 8):
                    if pos <= k:
                        aciertos[k] += 1
            else:
                gate_fn.append({**c, "mejor": mejor, "recuperados": recuperados,
                                "elegibles": elegibles[rol]})

        sim = f"{mejor:.3f}" if mejor is not None else "  -  "
        print(f"  [{marca:>6}] {sim}  ({rol}) {pregunta[:52]}")
        if detalle and pos != 1:
            print(f"           recupero: {recuperados or '(nada)'}")
            print(f"           esperaba: {c['espera']}")

    print("\n--- negativos (NO deberia pasar el umbral) ---")
    gate_fp: list[dict] = []
    for c in negativos:
        rol, pregunta = c["rol"], c["pregunta"]
        fragmentos, mejor = recuperar(config, slug, rol, pregunta)
        paso = bool(fragmentos)
        if paso:
            gate_fp.append({**c, "mejor": mejor,
                            "recuperados": [f.codigo for f in fragmentos]})
        sim = f"{mejor:.3f}" if mejor is not None else "  -  "
        print(f"  [{'FP ' if paso else 'ok ':>6}] {sim}  ({rol}) {pregunta[:52]}")
        if detalle and paso:
            print(f"           dejo pasar: {[f.codigo for f in fragmentos]}")

    # --- resumen -------------------------------------------------------------
    print("\n" + "=" * 74)
    print("  FRAGMENTOS VISIBLES POR ROL")
    for rol, n in sorted(elegibles.items()):
        aviso = "  <-- CERO: es un problema de permisos, no de recuperacion" if n == 0 else ""
        print(f"    {rol:26} {n:5}{aviso}")

    if medidos:
        print(f"\n  RECUPERACION  (sobre {medidos} positivos medibles)")
        for k in (1, 3, 8):
            pct = 100.0 * aciertos[k] / medidos
            print(f"    Recall@{k:<2}  {aciertos[k]:3}/{medidos}  {pct:5.1f}%")
        print(f"    MRR       {suma_rr / medidos:.3f}")

    print(f"\n  GATE  (umbral {umbral})")
    print(f"    falsos negativos  {len(gate_fn):3}  (habia respuesta y no paso nada)")
    print(f"    falsos positivos  {len(gate_fp):3}  (no habia respuesta y paso algo)")

    if gate_fn:
        print("\n  Falsos negativos -- revisar si la etiqueta esta bien antes de")
        print("  concluir que es el umbral:")
        for c in gate_fn:
            m = f"{c['mejor']:.3f}" if c["mejor"] is not None else "sin candidatos"
            print(f"    ({c['rol']}) {c['pregunta'][:46]:46} mejor={m}")

    if gate_fp:
        print("\n  Falsos positivos -- el umbral dejo pasar material que no responde:")
        for c in gate_fp:
            print(f"    ({c['rol']}) {c['pregunta'][:46]:46} "
                  f"mejor={c['mejor']:.3f} -> {c['recuperados'][:3]}")

    if brechas:
        print(f"\n  BRECHAS CONOCIDAS ({len(brechas)}) -- no cuentan como error;")
        print("  estan para que se note el dia que se arreglen:")
        for c in brechas:
            estado = f"recupero @{c['pos']}" if c["pos"] else "no recupero"
            print(f"    ({c['rol']}) {c['pregunta'][:40]:40} {estado}")

    print("=" * 74)
    if not detalle:
        print("  Con --detalle se ve que recupero en cada fallo.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("Uso: py -3.13 cli/evaluar_rag.py <slug> [--detalle]")
    main(args[0], "--detalle" in sys.argv)
