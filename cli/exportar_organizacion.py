# -*- coding: utf-8 -*-
"""
Escribe el fixture de la estructura por defecto que usa la pantalla.

POR QUE HACE FALTA UN GENERADOR
-------------------------------
La prueba de la oficina virtual corre en vitest, que no puede importar Python.
Asi que necesita el documento de la organizacion como JSON, y copiarlo a mano
es justo el error que dejo a E1 sin probar durante semanas: su prueba COPIABA la
consulta en vez de importar el modulo, y la funcion no funcionaba con la prueba
en verde.

Entonces: el fixture se GENERA desde el motor con este comando, y
'tests/test_organizacion_config.py' comprueba que siga coincidiendo. Si alguien
cambia la estructura por defecto y no regenera, esa prueba se pone roja y dice
este comando.

    py -3.13 cli/exportar_organizacion.py

No toca la base, no toca la red y no lee ningun secreto.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config.organizacion import ORGANIZACION_POR_DEFECTO     # noqa: E402

DESTINO = (RAIZ / "django-crm" / "frontend" / "src" / "lib" / "centro-mando" /
           "__fixtures__" / "organizacion-por-defecto.json")


def main() -> int:
    doc = {"origen": "por_defecto",
           **ORGANIZACION_POR_DEFECTO.model_dump(mode="json")}
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    #  Salto de linea LF y sin BOM: el archivo lo lee vitest y lo compara una
    #  prueba de Python. Dejar que Windows escriba CRLF haria que las dos
    #  lecturas no coincidieran por un motivo que no tiene nada que ver con la
    #  estructura.
    with open(DESTINO, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print(f"escrito  {DESTINO.relative_to(RAIZ)}")
    print(f"         {len(doc['departamentos'])} departamentos · "
          f"{len(doc['espacios'])} espacios · {len(doc['pisos'])} pisos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
