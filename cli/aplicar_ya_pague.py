# -*- coding: utf-8 -*-
"""
Aplica a la BASE solo el parrafo "SI EL CLIENTE DICE QUE YA PAGO" (11/11/2026).

    py -3.13 cli/aplicar_ya_pague.py rapilink              dice que haria, no escribe
    py -3.13 cli/aplicar_ya_pague.py rapilink --aplicar    escribe

Es un cambio de prompt, sin campos nuevos del esquema: no depende de que el motor haya
desplegado primero, pero igual va DESPUES del push para que repo y base digan lo mismo.
NO cargar el YAML entero (pisaria lo que la base tiene y el repo no).

El texto sale del propio YAML del repo (una sola fuente). Si el prompt de
'facturacion_cliente' ya no tiene la frase de la que cuelga (alguien lo edito desde
/agentes), NO escribe nada y lo dice.

Despues: py -3.13 cli/diferencias_config.py rapilink  y  cli/evaluar.py rapilink --humo --base
"""
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ROL = "facturacion_cliente"
MARCA = "SI EL CLIENTE DICE QUE YA PAGO"
ANCLA = "fecha con la de hoy antes de decir que el servicio esta en riesgo.\n"


def parrafo(tenant):
    """El parrafo tal como lo declara el repo: desde la marca hasta el final del bloque."""
    doc = yaml.safe_load((RAIZ / "tenants" / f"{tenant}.config.yaml").read_text(encoding="utf-8"))
    texto = doc["roles"][ROL]["descripcion"]
    i = texto.index(MARCA)
    fin = texto.index("\n\n", i) if "\n\n" in texto[i:] else len(texto)
    return texto[i:fin].rstrip("\n") + "\n"


def mutar(doc, nuevo, avisos):
    rol = doc["roles"][ROL]
    texto = rol.get("descripcion") or ""
    if MARCA in texto:
        avisos.append("prompt: ya estaba")
        return
    if texto.count(ANCLA) != 1:
        raise SystemExit(
            f"NO SE ESCRIBIO NADA: el prompt de '{ROL}' ya no tiene (una sola vez) la frase de la "
            f"que cuelga este agregado:\n  {ANCLA.strip()}\nAlguien lo edito desde /agentes. "
            "Agregarlo a mano.")
    rol["descripcion"] = texto.replace(ANCLA, ANCLA + "\n" + nuevo, 1)
    avisos.append("prompt: agregado")


def main():
    tenant = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    if not tenant:
        raise SystemExit(__doc__)
    nuevo = parrafo(tenant)
    if "--aplicar" not in sys.argv:
        print(f"[solo lectura] agregaria a '{ROL}' de '{tenant}' ({len(nuevo)} caracteres):\n\n{nuevo}")
        return
    from nucleo.config import editor
    avisos = []
    editor._editar(tenant, lambda doc: mutar(doc, nuevo, avisos))
    print("aplicado:", "; ".join(avisos))


if __name__ == "__main__":
    main()
