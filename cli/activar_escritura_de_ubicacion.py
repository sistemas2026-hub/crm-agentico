# -*- coding: utf-8 -*-
"""Agrega al tenant las dos herramientas que escriben la ubicacion del cliente.

    python cli/activar_escritura_de_ubicacion.py rapilink              # simulacro
    python cli/activar_escritura_de_ubicacion.py rapilink --aplicar

POR QUE UN CAMBIO QUIRURGICO Y NO `cargar_config.py`. Cargar la config
sobrescribe la fila entera con el YAML del repo, y la fuente de verdad es la
BASE: lo que alguien haya creado o ajustado desde `/agentes` desaparece sin
aviso. Esto agrega DOS herramientas y no toca nada mas -- si alguna de las dos
ya esta, no hace nada.

DE DONDE SALEN LAS DEFINICIONES. Del YAML del repo, leidas tal cual: retipearlas
aca seria una segunda copia que se desactualiza sola, y la diferencia entre las
dos no la notaria nadie hasta que el proveedor conteste 400.

LO QUE ESTO HABILITA. Hasta que corra, el motor no encuentra ninguna
herramienta marcada y el boton de la app contesta «esta empresa todavia no
tiene configurado donde guardar la ubicacion» -- que es lo correcto, no un
error. Despues de esto, el boton escribe de verdad.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import yaml                                                      # noqa: E402

MARCAS = ("escribe_coordenada_equipo", "escribe_coordenada_servicio")


def _del_yaml(slug: str) -> list[dict]:
    """Las dos definiciones, leidas del YAML del repo."""
    ruta = RAIZ / "tenants" / f"{slug}.config.yaml"
    if not ruta.exists():
        raise SystemExit(f"no esta {ruta}")
    crudo = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    return [h for h in (crudo.get("herramientas") or [])
            if any(h.get(m) for m in MARCAS)]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    slug = sys.argv[1]
    aplicar = "--aplicar" in sys.argv

    nuevas = _del_yaml(slug)
    if len(nuevas) != 2:
        print(f"el YAML trae {len(nuevas)} herramienta(s) marcada(s), se "
              f"esperaban 2. No se toca nada.")
        return 1
    print("del YAML del repo:")
    for h in nuevas:
        print(f"    {h['nombre']:<38} {h.get('metodo')}  "
              f"multipart={h.get('multipart', False)}")

    from nucleo.config import editor
    from nucleo.config.fuente import cargar

    vigente = cargar(slug)
    ya = {h.nombre for h in vigente.herramientas}
    print(f"\nla BASE tiene {len(ya)} herramientas")
    faltan = [h for h in nuevas if h["nombre"] not in ya]
    if not faltan:
        print("las dos YA estan en la base: no hay nada que hacer.")
        return 0
    print("faltan:", ", ".join(h["nombre"] for h in faltan))

    if not aplicar:
        print("\nSIMULACRO: no se escribio nada. Agregá --aplicar.")
        return 0

    def mutar(cfg: dict) -> None:
        #  Se agregan al final. El orden de la lista no significa nada: el
        #  motor las busca por su marca, nunca por posicion.
        presentes = {h.get("nombre") for h in cfg.get("herramientas") or []}
        for h in faltan:
            if h["nombre"] not in presentes:
                cfg.setdefault("herramientas", []).append(h)

    #  `_editar` valida el resultado DENTRO de la transaccion: si el esquema
    #  rechaza algo --por ejemplo una marca sin sus `parametros_de_coordenada`--
    #  no se escribe nada y la base queda como estaba.
    despues = editor._editar(slug, mutar)
    ahora = {h.nombre for h in despues.herramientas}
    puestas = [h["nombre"] for h in faltan if h["nombre"] in ahora]
    print(f"\nESCRITO. La base pasa de {len(ya)} a {len(ahora)} herramientas.")
    for n in puestas:
        print(f"    + {n}")
    if len(puestas) != len(faltan):
        print("   *** alguna no quedo: revisar antes de usar el boton")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
