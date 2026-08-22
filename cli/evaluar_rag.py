# -*- coding: utf-8 -*-
"""
================================================================================
 EVALUAR LA RECUPERACION (RAG)  --  cada fallo con su causa, no un promedio
================================================================================

Por que existe
--------------
Hasta ahora la unica forma de saber si el RAG andaba era abrir el simulador y
leer la respuesta. Eso no distingue cosas que fallan distinto y se arreglan en
lugares opuestos -- y peor: un promedio de similitud alto puede convivir con
un sistema que contesta mal.

Este comando corre un set etiquetado y clasifica CADA fallo en una de seis
causas. La clase no se infiere a ojo: sale de condiciones estrictas.

  permissions    hay documento correcto, pero el rol no puede verlo.
                 Se arregla asignando roles en /manual. Ni el umbral ni el
                 modelo de embeddings tienen nada que ver.
  retrieval      el documento es elegible y NO entro al top_k.
                 Problema de busqueda o de como se arma la consulta.
  ranking        entro al top_k pero no quedo primero.
                 Es la unica clase que un reranker podria arreglar -- si esta
                 en cero, un reranker no tiene nada que rescatar.
  threshold      esta entre los candidatos pero el gate lo rechazo por score.
                 Aca si tiene sentido discutir calibracion.
  answerability  paso el gate material que NO responde la pregunta.
                 Parecido semantico confundido con evidencia.
  tool-routing   la pregunta la resuelve una herramienta y se le inyecto
                 documentacion igual.

La diferencia entre 'retrieval' y 'threshold' exige ver lo que quedo DEBAJO
del umbral, por eso se usa recuperar_candidatos() (top_k sin filtrar) ademas
de recuperar() (lo que de verdad recibe el motor).

Lo que NO mide
--------------
Si la RESPUESTA final fue buena, ni si el modelo llamo a la herramienta
correcta. Eso es cli/evaluar.py, contra el motor real. Esto mide el paso
anterior: si el fragmento correcto no llega, no hay prompt que lo arregle.

'docs_inyectados' es la excepcion util: replica exactamente la condicion de
nucleo/modelo/motor.py ("if fragmentos:"), asi que dice si el motor le habria
metido documentacion al modelo en ese turno -- que es como se detecta el
fallo de tool-routing sin correr el motor entero.

Comparar dos corridas
---------------------
    py -3.13 cli/evaluar_rag.py rapilink --guardar baseline_v1
    ...se cambia una sola cosa...
    py -3.13 cli/evaluar_rag.py rapilink --comparar baseline_v1

Un cambio por corrida. Si se tocan dos cosas a la vez se sabe que mejoro pero
no por que.

Uso
---
    py -3.13 cli/evaluar_rag.py rapilink
    py -3.13 cli/evaluar_rag.py rapilink --detalle
    py -3.13 cli/evaluar_rag.py rapilink --guardar <nombre>
    py -3.13 cli/evaluar_rag.py rapilink --comparar <nombre>
    py -3.13 cli/evaluar_rag.py rapilink --csv fichas.csv
================================================================================
"""

from __future__ import annotations

import csv
import json
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
    contar_elegibles, documentos_visibles, recuperar_candidatos)

CLASES = ["permissions", "retrieval", "ranking", "threshold",
          "answerability", "tool-routing"]

INSTANTANEAS = RAIZ / "evaluacion" / "instantaneas"


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


def _rango(candidatos, esperados: list[str]) -> int | None:
    """Posicion 1-based del primer candidato del documento esperado."""
    for i, f in enumerate(candidatos, start=1):
        if any(_mismo_documento(f.codigo, e) for e in esperados):
            return i
    return None


def _clasificar(caso: dict, candidatos, umbral: float,
                visibles: set[str], elegibles: int) -> tuple[str | None, dict]:
    """
    (clase_de_fallo | None si estuvo OK, ficha del caso).

    El orden de las condiciones importa: se pregunta primero por la causa mas
    de fondo. Un rol que no puede ver el documento tambien va a fallar el
    ranking, pero llamarlo 'ranking' mandaria a optimizar el orden de una
    lista donde el documento correcto nunca podia estar.
    """
    pasados = [f for f in candidatos if f.similitud >= umbral]
    ficha = {
        "pregunta": caso["pregunta"],
        "rol": caso["rol"],
        "ruta_esperada": caso.get("ruta", "documental"),
        "espera": ",".join(caso.get("espera", [])),
        "fragmentos_elegibles": elegibles,
        "top1_doc": candidatos[0].codigo if candidatos else "",
        "top1_score": round(candidatos[0].similitud, 4) if candidatos else None,
        "rango_esperado": None,
        "gate_paso": bool(pasados),
        "docs_inyectados": bool(pasados),   # misma condicion que motor.py
        "brecha_conocida": bool(caso.get("brecha_conocida")),
    }

    # --- negativos: no deberia pasar NADA el gate -------------------------
    if caso.get("sin_respuesta"):
        if not pasados:
            return None, ficha
        # Paso algo. Que clase de error es depende de donde deberia haber
        # salido la respuesta.
        clase = ("tool-routing" if caso.get("ruta") == "herramienta"
                 else "answerability")
        return clase, ficha

    # --- positivos --------------------------------------------------------
    esperados = caso["espera"]
    ficha["rango_esperado"] = _rango(candidatos, esperados)

    # 1. permisos: el rol ni siquiera puede ver el documento correcto.
    if elegibles == 0 or not any(
            any(_mismo_documento(v, e) for e in esperados) for v in visibles):
        return "permissions", ficha

    # 2. no entro al top_k.
    if ficha["rango_esperado"] is None:
        return "retrieval", ficha

    # 3. entro, pero por debajo del umbral -> lo rechaza el gate.
    gold = candidatos[ficha["rango_esperado"] - 1]
    if gold.similitud < umbral:
        return "threshold", ficha

    # 4. paso el gate pero no quedo primero.
    if ficha["rango_esperado"] > 1:
        return "ranking", ficha

    return None, ficha


def main(slug: str, detalle: bool, guardar: str | None,
         comparar: str | None, csv_salida: str | None) -> None:
    casos = yaml.safe_load(
        (RAIZ / "evaluacion" / f"{slug}.rag.yaml").read_text(encoding="utf-8"))["casos"]
    config = fuente.cargar(slug, raiz=RAIZ)
    umbral = config.rag.umbral_similitud

    print("=" * 76)
    print(f"  Recuperacion de {slug} -- {len(casos)} caso(s)")
    print(f"  umbral={umbral}  top_k={config.rag.top_k}  "
          f"modelo={config.rag.modelo_embeddings}")
    print("=" * 76)

    # Una consulta por rol, no por caso.
    roles = {c["rol"] for c in casos}
    elegibles = {r: contar_elegibles(slug, r) for r in roles}
    visibles = {r: documentos_visibles(slug, r) for r in roles}

    conteo = {c: 0 for c in CLASES}
    # Las brechas conocidas se cuentan APARTE y por clase. Contarlas dentro
    # de 'conteo' escondería regresiones nuevas detrás de un número que ya
    # se sabía alto; no mostrarlas por clase produce un reporte que se lee
    # como contradictorio ("permissions 0" arriba y un fallo de permissions
    # listado abajo). Se cuentan las dos cosas y se dice cuál es cuál.
    conteo_brechas = {c: 0 for c in CLASES}
    fichas: list[dict] = []
    ok = 0
    brechas = 0

    # Recall/MRR se calculan solo sobre positivos que NO son brecha conocida:
    # mezclar un fallo ya documentado con los demas esconde las regresiones
    # nuevas detras de un numero que nunca se mueve.
    medibles = 0
    aciertos = {1: 0, 3: 0, 8: 0}
    suma_rr = 0.0

    for caso in casos:
        rol = caso["rol"]
        candidatos = recuperar_candidatos(config, slug, rol, caso["pregunta"])
        clase, ficha = _clasificar(caso, candidatos, umbral,
                                   visibles[rol], elegibles[rol])
        ficha["clase_fallo"] = clase or "ok"
        fichas.append(ficha)

        if caso.get("brecha_conocida"):
            brechas += 1
            if clase:
                conteo_brechas[clase] += 1
        elif clase:
            conteo[clase] += 1
        else:
            ok += 1

        if (not caso.get("sin_respuesta") and not caso.get("brecha_conocida")):
            medibles += 1
            r = ficha["rango_esperado"]
            gold_pasa = (r is not None
                         and candidatos[r - 1].similitud >= umbral)
            if r and gold_pasa:
                suma_rr += 1.0 / r
                for k in (1, 3, 8):
                    if r <= k:
                        aciertos[k] += 1

        etiqueta = "ok" if not clase else clase
        if caso.get("brecha_conocida"):
            etiqueta = f"brecha/{clase}" if clase else "brecha"
        s = f"{ficha['top1_score']:.3f}" if ficha["top1_score"] is not None else "  -  "
        print(f"  [{etiqueta:>14}] {s}  ({rol}) {caso['pregunta'][:44]}")
        if detalle and clase:
            print(f"       esperaba {caso.get('espera') or '(nada)'}  "
                  f"top1={ficha['top1_doc']!r}  rango={ficha['rango_esperado']}")

    # --- resumen -----------------------------------------------------------
    print("\n" + "=" * 76)
    print("  FRAGMENTOS VISIBLES POR ROL")
    for rol in sorted(elegibles):
        aviso = "   <-- CERO: es permisos, no recuperacion" if elegibles[rol] == 0 else ""
        print(f"    {rol:26} {elegibles[rol]:5}{aviso}")

    medidos = len(casos) - brechas
    print(f"\n  CLASIFICACION  ({medidos} consultas medidas"
          f"{f' + {brechas} brechas conocidas aparte' if brechas else ''})")
    print(f"    {'ok':16} {ok:4}")
    for c in sorted(CLASES, key=lambda x: -conteo[x]):
        extra = f"   (+{conteo_brechas[c]} en brechas)" if conteo_brechas[c] else ""
        print(f"    {c:16} {conteo[c]:4}{extra}")
    if brechas:
        detalle_b = ", ".join(f"{c}={conteo_brechas[c]}"
                              for c in CLASES if conteo_brechas[c])
        print(f"\n    brechas conocidas {brechas:4}  ({detalle_b or 'sin clase'})")
        print("    ^ EXCLUIDAS de los contadores de arriba y de Recall/MRR: son")
        print("      fallos ya documentados. Estan para que se note cuando se")
        print("      arreglen, no para inflar el error de cada corrida.")

    if medibles:
        print(f"\n  RECUPERACION  (sobre {medibles} positivos medibles)")
        for k in (1, 3, 8):
            print(f"    Recall@{k:<2}  {aciertos[k]:3}/{medibles}  "
                  f"{100.0 * aciertos[k] / medibles:5.1f}%")
        print(f"    MRR       {suma_rr / medibles:.3f}")

    if conteo["ranking"] == 0:
        print("\n  Nota: 'ranking' en cero -- un reranker no tendria nada que")
        print("  rescatar hoy. Es la medicion que decide si vale su latencia.")

    resumen = {"consultas": len(casos), "medidas": medidos,
               "ok": ok, **conteo, "brechas": brechas,
               "brechas_por_clase": {c: n for c, n in conteo_brechas.items() if n},
               "recall@1": aciertos[1], "recall@3": aciertos[3],
               "recall@8": aciertos[8], "medibles": medibles,
               "mrr": round(suma_rr / medibles, 4) if medibles else 0.0}

    # --- instantanea / comparacion ----------------------------------------
    if comparar:
        ruta = INSTANTANEAS / f"{slug}.{comparar}.json"
        if not ruta.exists():
            print(f"\n  No existe la instantanea '{comparar}' ({ruta}).")
        else:
            previo = json.loads(ruta.read_text(encoding="utf-8"))
            print(f"\n  CONTRA '{comparar}'")
            for clave in ("ok", *CLASES, "recall@1", "recall@3", "mrr"):
                antes, ahora = previo["resumen"].get(clave, 0), resumen.get(clave, 0)
                if antes != ahora:
                    signo = "+" if ahora > antes else ""
                    print(f"    {clave:16} {antes} -> {ahora}  ({signo}{ahora - antes:g})")
            if previo["resumen"] == resumen:
                print("    (sin cambios)")

    if guardar:
        INSTANTANEAS.mkdir(parents=True, exist_ok=True)
        ruta = INSTANTANEAS / f"{slug}.{guardar}.json"
        ruta.write_text(json.dumps(
            {"umbral": umbral, "top_k": config.rag.top_k,
             "modelo": config.rag.modelo_embeddings,
             "resumen": resumen, "fichas": fichas},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Instantanea guardada: {ruta.relative_to(RAIZ)}")

    if csv_salida:
        ruta = Path(csv_salida)
        with ruta.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(fichas[0]))
            w.writeheader()
            w.writerows(fichas)
        print(f"  Fichas por caso: {ruta}")

    print("=" * 76)


def _valor(bandera: str) -> str | None:
    if bandera in sys.argv:
        i = sys.argv.index(bandera)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


if __name__ == "__main__":
    posicionales = [a for a in sys.argv[1:] if not a.startswith("--")]
    banderas = {"--guardar", "--comparar", "--csv"}
    valores = {b: _valor(b) for b in banderas}
    slug = next((p for p in posicionales if p not in valores.values()), None)
    if not slug:
        raise SystemExit(
            "Uso: py -3.13 cli/evaluar_rag.py <slug> [--detalle] "
            "[--guardar <nombre>] [--comparar <nombre>] [--csv <archivo>]")
    main(slug, "--detalle" in sys.argv, valores["--guardar"],
         valores["--comparar"], valores["--csv"])
