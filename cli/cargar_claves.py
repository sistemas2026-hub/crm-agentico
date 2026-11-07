# -*- coding: utf-8 -*-
"""
================================================================================
 CARGAR SOLO ESTAS CLAVES DEL YAML A LA BASE  --  30/10/2026
================================================================================

'cli/cargar_config.py' sube el YAML ENTERO, y eso a veces no se puede: la base
tiene cosas que el archivo no trae (un agente creado desde la interfaz, la
encuesta de Rapilink en modo prueba con 'solo_a') y cargarlo las pisaria. Hasta
hoy la salida era no cargar nada, y lo nuevo del repo quedaba sin llegar.

Esto copia del YAML a la base SOLO las claves que se nombran, por el mismo
camino que el editor de la interfaz (nucleo/config/editor.py::_editar): lee la
config vigente de la base, reemplaza esas claves, VALIDA el resultado entero
contra TenantConfig y guarda en una transaccion. Lo demas no se toma del YAML
(ojo: el editor reescribe los valores por defecto del esquema, CLAUDE.md D7).

    py -3.13 cli/cargar_claves.py tenants/rapilink.config.yaml \\
        --clave capacidad \\
        --clave "herramientas[reiniciar_ont].exige_previas"

Sin --aplicar solo muestra que cambiaria. Formas de clave:

    capacidad                                   una clave de primer nivel
    autenticacion.indicativo_pais               un campo de un bloque, sin tocar
                                                los demas campos del bloque
    herramientas[reiniciar_ont].exige_previas   un campo de un elemento de una
                                                lista, ubicado por su 'nombre'

Una clave que no existe en el YAML no se inventa ni se borra en la base: es un
error. Despues de aplicar, lo de siempre (CLAUDE.md §6):
    py -3.13 cli/diferencias_config.py <slug>
    py -3.13 cli/evaluar.py <slug> --humo --base
================================================================================
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

_EN_LISTA = re.compile(r"^(?P<lista>[a-z_]+)\[(?P<nombre>[^\]]+)\]\.(?P<campo>[a-z_]+)$")
_SIMPLE = re.compile(r"^[a-z_]+$")
_EN_BLOQUE = re.compile(r"^(?P<bloque>[a-z_]+)\.(?P<campo>[a-z_]+)$")


class ClaveInvalida(ValueError):
    pass


def _ubicar(doc: dict, clave: str, crear: bool = False):
    """(contenedor, campo) donde vive 'clave' en 'doc', o ClaveInvalida. Con
    'crear', un bloque que no existe se crea vacio (en la base: el campo nuevo
    de un bloque que todavia no tenia ninguno)."""
    if _SIMPLE.match(clave):
        return doc, clave
    b = _EN_BLOQUE.match(clave)
    if b:
        bloque = doc.get(b["bloque"])
        if bloque is None and crear:
            bloque = doc[b["bloque"]] = {}
        if not isinstance(bloque, dict):
            raise ClaveInvalida(f"'{b['bloque']}' no es un bloque en este documento")
        return bloque, b["campo"]
    m = _EN_LISTA.match(clave)
    if not m:
        raise ClaveInvalida(f"'{clave}' no tiene una forma conocida (ver --help)")
    elementos = [e for e in (doc.get(m["lista"]) or [])
                 if isinstance(e, dict) and e.get("nombre") == m["nombre"]]
    if len(elementos) != 1:
        raise ClaveInvalida(f"'{m['lista']}' tiene {len(elementos)} elementos con "
                            f"nombre '{m['nombre']}', se esperaba uno")
    return elementos[0], m["campo"]


def copiar_claves(base: dict, semilla: dict, claves: list[str]) -> tuple[dict, list[dict]]:
    """
    'base' con las 'claves' tomadas de 'semilla'. No toca 'base'.

    Devuelve (documento nuevo, cambios), donde cada cambio es
    {clave, antes, despues}. Una clave ausente en la semilla es un error: no se
    borra nada de la base por omision.
    """
    nuevo = copy.deepcopy(base)
    cambios = []
    for clave in claves:
        origen, campo = _ubicar(semilla, clave)
        if campo not in origen:
            raise ClaveInvalida(f"'{clave}' no esta en el YAML: no se borra de la base por omision")
        destino, campo_d = _ubicar(nuevo, clave, crear=True)
        antes = copy.deepcopy(destino.get(campo_d))
        despues = copy.deepcopy(origen[campo])
        if antes != despues:
            destino[campo_d] = despues
            cambios.append({"clave": clave, "antes": antes, "despues": despues})
    return nuevo, cambios


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("archivo", help="tenants/<slug>.config.yaml")
    p.add_argument("--clave", action="append", required=True)
    p.add_argument("--aplicar", action="store_true", help="sin esto, solo muestra")
    a = p.parse_args(argv)

    import yaml

    from nucleo.config import editor

    ruta = Path(a.archivo)
    slug = ruta.name.split(".")[0]
    semilla = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    vistos: list[dict] = []

    def mutar(doc: dict) -> None:
        nuevo, cambios = copiar_claves(doc, semilla, a.clave)
        vistos.extend(cambios)
        if not a.aplicar:
            raise _SoloMostrar()
        doc.clear()
        doc.update(nuevo)

    try:
        editor._editar(slug, mutar)
    except _SoloMostrar:
        pass
    except ClaveInvalida as e:
        print(f"[cargar_claves] {e}")
        return 2

    if not vistos:
        print(f"[cargar_claves] {slug}: la base ya tiene esas claves igual que el YAML.")
        return 0
    for c in vistos:
        print(f"\n--- {c['clave']}")
        print("  base hoy :", json.dumps(c["antes"], ensure_ascii=False)[:600])
        print("  del YAML :", json.dumps(c["despues"], ensure_ascii=False)[:600])
    print("\n[cargar_claves] " + ("APLICADO, validado contra el esquema." if a.aplicar
                                  else "Solo mostrado. Agrega --aplicar para escribir."))
    return 0


class _SoloMostrar(Exception):
    """Corta _editar antes de guardar: sale de la transaccion sin escribir."""


if __name__ == "__main__":
    raise SystemExit(main())
