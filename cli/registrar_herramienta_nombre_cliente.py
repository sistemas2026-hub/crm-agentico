# -*- coding: utf-8 -*-
"""
================================================================================
 REGISTRAR 'fijar_nombre_cliente_externo' EN LA CONFIG DESPLEGADA
================================================================================

QUE HACE
--------
Agrega UNA herramienta al catalogo del tenant en 'asistente.tenant_config', y
nada mas. La entrada sale del YAML del repo, que es la semilla, validada por el
mismo esquema que valida todo lo demas.

POR QUE UN SCRIPT Y NO 'cli/cargar_config.py'
---------------------------------------------
Porque el YAML NO es un superconjunto de lo que hay en la base: hay campos que
se pueblan en caliente y que el archivo no tiene. Medido -- 'localidades' (128
entradas), 'parrilla_canales' (100) y 'ping_cliente.argumentos_sobrescribibles'
existen solo en la base. Una carga completa los vaciaria sin decir nada.

Asi que se usa 'editor._editar', que lee la config vigente, le aplica una
mutacion quirurgica, valida el resultado entero y lo guarda -- todo en una
transaccion con la fila bloqueada. Si la validacion falla, no se escribe nada.

Uso:
    py -3.13 cli/registrar_herramienta_nombre_cliente.py rapilink            # solo mira
    py -3.13 cli/registrar_herramienta_nombre_cliente.py rapilink --aplicar  # escribe
================================================================================
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv                              # noqa: E402

load_dotenv(RAIZ / ".env", override=False)

import yaml                                                 # noqa: E402

from nucleo.config import editor, fuente                    # noqa: E402

HERRAMIENTA = "fijar_nombre_cliente_externo"


def entrada_del_yaml(tenant: str) -> dict:
    """
    La entrada tal como la declara el repo.

    Se lee del YAML crudo y NO del modelo validado: 'model_dump()' agrega cada
    campo con su default -- decenas por herramienta-- y guardar eso convertiria
    una edicion de una herramienta en una entrada que no se parece a sus 76
    vecinas. Lo que se escribe es lo que dice el archivo; el validador de
    '_editar' comprueba despues que sea una herramienta valida.
    """
    ruta = RAIZ / "tenants" / f"{tenant}.config.yaml"
    doc = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    for h in doc.get("herramientas") or []:
        if h.get("nombre") == HERRAMIENTA:
            return h
    raise SystemExit(f"'{HERRAMIENTA}' no esta en {ruta.name}: nada que registrar.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tenant")
    p.add_argument("--aplicar", action="store_true",
                   help="escribe en asistente.tenant_config")
    args = p.parse_args()

    # --- 1. la configuracion vigente, desde la BASE -----------------------
    cargada = fuente.cargar(args.tenant)
    config = cargada[0] if isinstance(cargada, tuple) else cargada
    version = cargada[1] if isinstance(cargada, tuple) and len(cargada) > 1 else "?"
    if config is None:
        print(f"No se pudo cargar la config de '{args.tenant}'.")
        return 1

    nombres = [h.nombre for h in config.herramientas]
    print(f"config vigente            v{version}, {len(nombres)} herramientas")

    # --- 2. confirmar que NO existe ---------------------------------------
    if HERRAMIENTA in nombres:
        print(f"'{HERRAMIENTA}' YA ESTA registrada. No hay nada que hacer.")
        return 0
    print(f"'{HERRAMIENTA}'  ->  NO existe en la base")

    # --- 3. mostrar exactamente que se va a agregar -----------------------
    entrada = entrada_del_yaml(args.tenant)
    print()
    print("ENTRADA QUE SE AGREGARIA (del YAML del repo, literal):")
    print(json.dumps(entrada, indent=2, ensure_ascii=False))
    print()

    if not args.aplicar:
        print("Solo se miro. Nada se escribio. Para escribir: --aplicar")
        return 0

    # --- la mutacion, quirurgica ------------------------------------------
    esperadas = len(nombres) + 1

    def mutar(doc: dict) -> None:
        """
        Agrega la herramienta al final de la lista. No toca nada mas.

        Se comprueba DENTRO de la mutacion que siga sin estar: '_editar' relee
        la fila con 'for update' dentro de su transaccion, asi que este es el
        unico punto donde se ve el estado real contra el que se va a escribir.
        Entre el paso 2 de arriba y este instante pudo entrar otra edicion.
        """
        herramientas = doc.setdefault("herramientas", [])
        ya = [h.get("nombre") for h in herramientas]
        if HERRAMIENTA in ya:
            raise editor.ErrorEdicion(
                f"'{HERRAMIENTA}' aparecio en la config entre la lectura y la "
                f"escritura: otra edicion gano la carrera. No se escribe nada.")
        herramientas.append(copy.deepcopy(entrada))

    resultado = editor._editar(args.tenant, mutar)

    # --- comprobar el EFECTO, sobre lo que devolvio el editor -------------
    finales = [h.nombre for h in resultado.herramientas]
    if HERRAMIENTA not in finales:
        print(f"[!] '{HERRAMIENTA}' NO quedo en la config. Revisar.")
        return 1
    if len(finales) != esperadas:
        print(f"[!] la cuenta no cuadra: {len(finales)} herramientas, se "
              f"esperaban {esperadas}. Revisar que no se haya tocado otra.")
        return 1

    print(f"OK: '{HERRAMIENTA}' registrada. {len(finales)} herramientas "
          f"({esperadas - 1} + 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
