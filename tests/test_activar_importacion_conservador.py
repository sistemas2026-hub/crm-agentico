# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE LA ACTIVACION DE IMPORTACION  --  cli/activar_importacion.py
================================================================================

Por que existe
--------------
Esta guarda nace de un defecto REAL, encontrado el 12/09/2026 al ir a aplicar
configuracion a produccion.

`cli/activar_importacion.py` parecia la herramienta correcta para agregar una
herramienta nueva al catalogo del tenant. Hacia esto:

    doc["importacion_tickets"] = nueva

Una asignacion, no una fusion. En produccion la base tenia `cada_horas: 1`
--el importador ENCENDIDO, en una edicion deliberada y aparte-- y once ajustes
mas que la semilla del YAML no conoce. Esa linea los habria borrado todos y
habria dejado `cada_horas` en 0: el importador apagado, en silencio, como
efecto secundario de agregar una herramienta.

No lo detecto ninguna prueba. Lo detecto leer el archivo antes de correrlo.

Lo que se fija aca
------------------
1. Ninguna clave existente se pierde.
2. Ningun valor existente cambia -- en particular `cada_horas`, que es el
   interruptor del importador.
3. Lo que falta si se agrega, porque para eso existe el comando.
4. Si la seccion no existia, nace entera y APAGADA.

El punto 2 es el que importa: es el unico que falla si alguien vuelve a poner
una asignacion donde va una fusion.

Uso
---
    py -3.13 tests/test_activar_importacion_conservador.py
================================================================================
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cli.activar_importacion import (completar_importacion_tickets,   # noqa: E402
                                     _importacion_tickets)

fallos: list[str] = []


def revisar(condicion: bool, que: str, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok] {que}")
    else:
        print(f"  [FALLA] {que}")
        if detalle:
            print(f"         {detalle}")
        fallos.append(que)


# Como se ve la base de PRODUCCION: encendida, y con ajustes que el YAML no
# trae. Los valores son los que tenia rapilink el 12/09/2026.
BASE_VIVA = {
    "importacion_tickets": {
        "cada_horas": 1,                       # ENCENDIDO. El dato que importa.
        "proveedor": "wisphub",
        "ventana_dias": 30,
        "solapamiento_horas": 6,
        "ajuste_que_solo_existe_en_la_base": "no lo borres",
        "otro_ajuste_de_la_interfaz": [1, 2, 3],
    },
    "herramientas": [],
}


print("=" * 74)
print("  la activacion COMPLETA la configuracion, no la reemplaza")
print("=" * 74)

doc = copy.deepcopy(BASE_VIVA)
antes = copy.deepcopy(doc["importacion_tickets"])
nueva = _importacion_tickets()

completar_importacion_tickets(doc, nueva)
despues = doc["importacion_tickets"]

# --- 1: nada se pierde -------------------------------------------------------
perdidas = sorted(set(antes) - set(despues))
revisar(not perdidas,
        "ninguna clave que ya estaba en la base desaparece",
        f"se perdieron: {perdidas}")

# --- 2: nada se pisa ---------------------------------------------------------
pisadas = {k: (antes[k], despues.get(k)) for k in antes if despues.get(k) != antes[k]}
revisar(not pisadas,
        "ningun valor que ya estaba en la base cambia",
        f"cambiaron: {pisadas}")

# --- 3: EL caso que costo el susto -------------------------------------------
revisar(despues.get("cada_horas") == 1,
        "cada_horas=1 sobrevive: agregar una herramienta NO apaga el importador",
        f"cada_horas quedo en {despues.get('cada_horas')!r}. Si esto dice 0, "
        f"alguien volvio a poner una asignacion donde va una fusion.")

revisar(despues.get("ajuste_que_solo_existe_en_la_base") == "no lo borres",
        "los ajustes que solo viven en la base sobreviven",
        f"{despues.get('ajuste_que_solo_existe_en_la_base')!r}")

# --- 4: lo que falta, se agrega ----------------------------------------------
agregadas = sorted(set(despues) - set(antes))
revisar(agregadas,
        "las claves que faltaban si se agregan (para eso existe el comando)",
        "no agrego ninguna: dejaria de cumplir su proposito")
revisar(set(nueva) <= set(despues),
        "y al terminar estan TODAS las que la importacion necesita",
        f"faltan: {sorted(set(nueva) - set(despues))}")

# --- 5: si no existia, nace apagada ------------------------------------------
print()
print("=" * 74)
print("  si la seccion no existia, nace entera y APAGADA")
print("=" * 74)

vacio: dict = {"herramientas": []}
completar_importacion_tickets(vacio, _importacion_tickets())
revisar(vacio["importacion_tickets"]["cada_horas"] == 0,
        "un tenant sin seccion la estrena en 0: se agrega la capacidad, no la importacion",
        f"nacio en {vacio['importacion_tickets'].get('cada_horas')!r}")
revisar(set(vacio["importacion_tickets"]) == set(_importacion_tickets()),
        "y la estrena completa",
        f"{sorted(vacio['importacion_tickets'])}")

# Una seccion presente pero rota (None, o una lista) no es un dict: se trata
# como ausente en vez de reventar con AttributeError a mitad de la mutacion.
for basura in (None, [], "nada"):
    roto = {"importacion_tickets": basura}
    completar_importacion_tickets(roto, _importacion_tickets())
    revisar(isinstance(roto["importacion_tickets"], dict)
            and roto["importacion_tickets"]["cada_horas"] == 0,
            f"una seccion invalida ({basura!r}) se reemplaza por una apagada",
            f"quedo {roto['importacion_tickets']!r}")

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] La activacion completa la configuracion sin pisar lo decidido.")
print("=" * 74)
