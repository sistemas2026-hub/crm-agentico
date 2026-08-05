# -*- coding: utf-8 -*-
"""
================================================================================
 INGESTA DEL CORPUS  -  del .docx a los fragmentos, con el perfil del tenant
================================================================================

Lee los documentos de corpus/<slug>/, los fragmenta segun el PERFIL DOCUMENTAL
declarado en la configuracion de esa empresa, y reporta que salio.

El perfil es lo que evita que los criterios de una empresa se apliquen a los
documentos de otra: donde empieza una seccion, que recuadro es un aviso y que
bloque es pie de pagina cambia de una organizacion a otra.

Por defecto NO escribe en la base: primero se mira el resultado. La carga real
va con --cargar.

Uso
---
    py -3.13 cli/ingerir.py rapilink              # analiza y reporta
    py -3.13 cli/ingerir.py rapilink --detalle    # ademas lista los fragmentos
    py -3.13 cli/ingerir.py rapilink --defectos   # solo el informe de defectos
================================================================================
"""

from __future__ import annotations

import sys
from collections import Counter
from fnmatch import fnmatch
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                      # noqa: E402
from nucleo.ingesta.docx import PerfilDocumento, procesar     # noqa: E402


def clasificar(ruta: Path, cfg) -> str:
    """vigente | obsoleto | excluido, segun lo declarado por el tenant."""
    if any(fnmatch(ruta.name, patron) for patron in cfg.corpus.excluir):
        return "excluido"
    if any(fnmatch(ruta.name, patron) for patron in cfg.corpus.obsoletos):
        return "obsoleto"
    return "vigente"


def perfil_de(slug: str) -> tuple[PerfilDocumento, int]:
    """Traduce el perfil declarado en el YAML del tenant al que usa el motor."""
    cfg = cargar_config(RAIZ / "tenants" / f"{slug}.config.yaml")
    p = cfg.corpus.perfil_documento
    tokens = (cfg.corpus.tipos_documento[0].tamano_objetivo_tokens
              if cfg.corpus.tipos_documento else 500)
    return PerfilDocumento(
        marcas_callout=tuple(p.marcas_callout),
        encabezados_pie=tuple(p.encabezados_pie),
        campos_metadatos=tuple(p.campos_metadatos),
        titulo_un_nivel_en_tabla=p.titulo_un_nivel_en_tabla,
        exigir_multinivel_sin_estilo=p.exigir_multinivel_sin_estilo,
        max_largo_titulo=p.max_largo_titulo,
        defectos_a_reportar=tuple(p.defectos_a_reportar),
        anotar_imagenes=p.anotar_imagenes,
    ), tokens


def main(slug: str, detalle: bool, solo_defectos: bool) -> None:
    carpeta = RAIZ / "corpus" / slug
    if not carpeta.is_dir():
        raise SystemExit(f"No existe {carpeta}. Deja ahi los .docx del tenant.")

    cfg = cargar_config(RAIZ / "tenants" / f"{slug}.config.yaml")
    perfil, tokens = perfil_de(slug)
    archivos = sorted(carpeta.glob("*.docx"))
    if not archivos:
        raise SystemExit(f"{carpeta} no tiene ningun .docx")

    print(f"Tenant: {slug}   documentos: {len(archivos)}   "
          f"objetivo: {tokens} tokens por fragmento\n")

    docs, defectos, estados = [], Counter(), Counter()
    if not solo_defectos:
        print(f"{'documento':<44} {'estado':<9} {'codigo':<9} {'v':<3} "
              f"{'frag':>5} {'tabla':>6} {'img':>4} {'def':>4}")
        print("-" * 92)

    for ruta in archivos:
        estado = clasificar(ruta, cfg)
        estados[estado] += 1

        # Un excluido NI SIQUIERA se lee. No es solo que no se vectorice: su
        # texto no debe pasar por el proceso ni quedar en un log.
        if estado == "excluido":
            if not solo_defectos:
                print(f"{ruta.name[:42]:<44} {'EXCLUIDO':<9} "
                      f"{'—':<9} {'—':<3} {'—':>5} {'—':>6} {'—':>4} {'—':>4}")
            continue

        try:
            d = procesar(ruta, perfil=perfil, max_tokens=tokens)
        except Exception as e:                        # documento corrupto
            print(f"{ruta.name[:42]:<44} ERROR: {str(e)[:34]}")
            continue
        d.estado = estado
        docs.append(d)
        # Los defectos de un obsoleto no se reportan: nadie los va a arreglar.
        if estado == "vigente":
            for x in d.defectos:
                defectos[x["tipo"]] += 1
        if not solo_defectos:
            n_tab = sum(1 for f in d.fragmentos if f.tipo == "tabla")
            n_img = sum(1 for f in d.fragmentos
                        if "[imagen en el documento original]" in f.contenido)
            print(f"{ruta.name[:42]:<44} {estado:<9} {d.codigo[:8]:<9} "
                  f"{d.version[:2]:<3} {len(d.fragmentos):>5} {n_tab:>6} "
                  f"{n_img:>4} {len(d.defectos):>4}")

    total = sum(len(d.fragmentos) for d in docs)
    tablas = sum(1 for d in docs for f in d.fragmentos if f.tipo == "tabla")

    if not solo_defectos:
        print("-" * 86)
        print(f"{'TOTAL':<46} {'':<9} {'':<3} {total:>5} {tablas:>6}\n")

    # --- defectos: la lista de arreglos concretos para el corpus del cliente ---
    print("=" * 74)
    print("  DEFECTOS DEL CORPUS")
    print("=" * 74)
    if not defectos:
        print("  (ninguno)")
    else:
        for tipo, n in defectos.most_common():
            print(f"  {tipo:<24} {n}")
        print()
        for d in docs:
            if d.defectos:
                print(f"  {d.ruta.name[:60]}")
                for x in d.defectos:
                    print(f"      {x['detalle']}")

    if detalle:
        print()
        print("=" * 74)
        print("  FRAGMENTOS")
        print("=" * 74)
        for d in docs:
            print(f"\n  {d.codigo} v{d.version} — {d.titulo[:48]}")
            for f in d.fragmentos:
                marca = "TABLA" if f.tipo == "tabla" else "texto"
                print(f"    [{marca}] {f.numero:<6} {f.titulo[:36]:<38} "
                      f"{len(f.contenido):>5}c")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("Uso: py -3.13 cli/ingerir.py <slug> [--detalle] "
                         "[--defectos]")
    main(args[0], "--detalle" in sys.argv, "--defectos" in sys.argv)
