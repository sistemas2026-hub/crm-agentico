# -*- coding: utf-8 -*-
"""
================================================================================
 IMPORTAR CASOS DORADOS  --  lo que el equipo marco, al archivo de casos
================================================================================

Por que existe (12/11/2026)
---------------------------
El equipo marca respuestas como «☆ Buen ejemplo» y aprueba revisiones del
supervisor. Hasta hoy eso no llegaba a ningun lado (SPEC/AUDITORIA_MENU_
2026-11-12.md, grupo «Dexter»). nucleo/habilidades/casos_dorados.py arma, desde
la TRAZA guardada, el caso dorado de cada uno; produccion no puede escribir el
repositorio, asi que este CLI es el que los trae a evaluacion/<slug>.casos.yaml.

Que hace
--------
1. Lee de la base (la que configure el entorno: DBHOST/DBNAME/...) los ejemplos
   marcados y las revisiones APROBADAS de buen ejemplo.
2. Arma el caso de cada uno -- mensajes del cliente REDACTADOS por patron, y la
   traza: 'usa', 'deriva_a', 'sin_errores'.
3. Los AGREGA al final del archivo, sin tocar una sola linea de lo que ya esta
   (los comentarios de ese archivo son la mitad de su valor), y sin duplicar:
   cada caso lleva 'origen' (ejemplo:<id> o revision:<id>) y lo que ya esta en
   el archivo no se vuelve a agregar.
4. Comprueba que el archivo resultante se sigue cargando como lo carga
   cli/evaluar.py (yaml.safe_load + 'casos') y que tiene exactamente los casos
   de antes mas los nuevos. Si no, NO escribe nada.

Todos nacen 'manual: true': cli/evaluar.py los saltea en la corrida completa
hasta que una persona los lea (la redaccion por patron no tapa nombres ni
direcciones), les agregue lo que NO debe pasar y les saque la marca.

Lee la base y escribe un archivo del repositorio: no llama al modelo ni a
ninguna API externa, y no escribe en la base.

Uso
---
    py -3.13 cli/importar_casos_dorados.py rapilink --seco     # que agregaria
    py -3.13 cli/importar_casos_dorados.py rapilink
    py -3.13 cli/importar_casos_dorados.py rapilink --archivo otro.casos.yaml
    py -3.13 cli/importar_casos_dorados.py rapilink --yaml     # config del repo
================================================================================
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("DB_APPLICATION_NAME", "dexter-cli-importar-casos")

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml                                                         # noqa: E402
from dotenv import load_dotenv                                      # noqa: E402

# override=False por la misma razon que cli/evaluar.py: lo que el entorno
# declara gana; el archivo solo rellena lo que falta.
load_dotenv(RAIZ / ".env", override=False)

from nucleo.habilidades import casos_dorados                        # noqa: E402


def origenes_en(texto: str) -> set[str]:
    """Los 'origen' de los casos que ya estan en el archivo."""
    doc = yaml.safe_load(texto) or {}
    return {str(c.get("origen")) for c in (doc.get("casos") or [])
            if isinstance(c, dict) and c.get("origen")}


def agregar(texto: str, bloques: list[str]) -> str:
    """El archivo con los bloques al final. 'casos:' tiene que ser la ULTIMA
    clave del documento: agregar texto al final solo cae dentro de la lista si
    no hay otra clave despues. Si no lo es, se niega -- reescribir el YAML
    entero perderia los comentarios."""
    doc = yaml.safe_load(texto) or {}
    claves = list(doc.keys()) if isinstance(doc, dict) else []
    if not claves or claves[-1] != "casos":
        raise SystemExit("La lista 'casos:' no es la ultima clave del archivo: "
                         "agregar al final no caeria dentro de ella. No se "
                         "escribio nada.")
    base = texto if texto.endswith("\n") else texto + "\n"
    return base + "".join("\n" + b for b in bloques)


def comprobar(antes: str, despues: str, nuevos: list[dict]) -> None:
    """Fail-closed: el archivo nuevo se carga como lo carga cli/evaluar.py y
    tiene los casos de antes, en el mismo orden, mas los nuevos."""
    viejo = (yaml.safe_load(antes) or {}).get("casos") or []
    doc = yaml.safe_load(despues) or {}
    casos = doc.get("casos") or []
    if casos[:len(viejo)] != viejo or casos[len(viejo):] != nuevos:
        raise SystemExit("El archivo resultante no tiene exactamente los casos de "
                         "antes mas los nuevos. No se escribio nada.")
    for c in nuevos:
        if not (c.get("nombre") and c.get("rol") and c.get("mensajes")):
            raise SystemExit(f"Un caso salio sin nombre, rol o mensajes "
                             f"({c.get('origen')}). No se escribio nada.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tenant")
    ap.add_argument("--archivo", help="Archivo de casos (por defecto "
                                      "evaluacion/<tenant>.casos.yaml)")
    ap.add_argument("--seco", action="store_true",
                    help="Muestra lo que agregaria, sin escribir")
    ap.add_argument("--yaml", action="store_true",
                    help="Usa la config del repo en vez de la de la base")
    args = ap.parse_args(argv)

    ruta = Path(args.archivo) if args.archivo else RAIZ / "evaluacion" / f"{args.tenant}.casos.yaml"
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}")
    antes = ruta.read_text(encoding="utf-8")

    # La config decide dos cosas del caso: con que rol entra el cliente y que
    # herramienta deriva. La de la base es la que corrio esas conversaciones.
    if args.yaml:
        from nucleo.config import cargar_config
        config = cargar_config(RAIZ / "tenants" / f"{args.tenant}.config.yaml")
    else:
        from nucleo.config import fuente
        resultado = fuente.desde_base(args.tenant)
        if resultado is None:
            raise SystemExit(f"'{args.tenant}' no esta en asistente.tenant_config "
                             f"(usar --yaml para la config del repo).")
        config = resultado[0]

    ya = origenes_en(antes)
    nuevos, bloques, salteados = [], [], []
    for tipo, id_origen in casos_dorados.candidatos(args.tenant):
        if f"{tipo}:{id_origen}" in ya:
            continue
        armar = (casos_dorados.caso_de_ejemplo if tipo == "ejemplo"
                 else casos_dorados.caso_de_revision)
        try:
            caso, avisos = armar(config, args.tenant, id_origen)
        except casos_dorados.SinCaso as e:
            salteados.append((f"{tipo}:{id_origen}", str(e)))
            continue
        nuevos.append(caso)
        bloques.append(casos_dorados.a_yaml(caso, avisos))

    print(f"  {len(ya)} caso(s) del archivo ya venian de una conversacion marcada")
    print(f"  {len(nuevos)} caso(s) nuevo(s) para agregar")
    for origen, motivo in salteados:
        print(f"  [salteado] {origen}: {motivo}")
    if not nuevos:
        return 0

    despues = agregar(antes, bloques)
    comprobar(antes, despues, nuevos)
    if args.seco:
        print("\n" + "".join("\n" + b for b in bloques))
        print("  (--seco: no se escribio nada)")
        return 0
    ruta.write_text(despues, encoding="utf-8")
    print(f"  Escrito {ruta}. Leelos antes de commitear: la redaccion por patron "
          f"no tapa nombres ni direcciones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
