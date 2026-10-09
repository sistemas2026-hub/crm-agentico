# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL ASISTENTE DE CONFIGURACION GUIADA
================================================================================

Por que existe
--------------
nucleo/config/editor.py deja escrito que crear una herramienta nueva
"sigue siendo trabajo de codigo... esa superficie es sensible en
seguridad". El asistente de configuracion guiada (CLAUDE.md: "la proxima
empresa que se conecte no deberia necesitar una sesion de codigo") le abre
una puerta -- y esta guarda prueba que la puerta sigue teniendo la
cerradura: un borrador mal armado (tipo invalido, sin roles_permitidos, un
nombre que ya existe) tiene que RECHAZARSE, no colarse al catalogo real.

Verificado en vivo (17/08/2026) el primer intento de esto: el modelo
propuso 'tipo: catalogo' (no existe) y sin 'roles_permitidos' -- este test
deja ese caso real como regresion, no uno inventado.

Uso
---
    py -3.13 tests/test_configuracion_guiada.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv                      # noqa: E402
load_dotenv(RAIZ / ".env", override=True)             # noqa: E402

from nucleo.config import editor                     # noqa: E402
from nucleo.config import cargar_config               # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def _rechaza(herramienta_propuesta: dict) -> bool:
    try:
        editor.aprobar_herramienta_propuesta("rapilink", herramienta_propuesta)
        return False
    except editor.ErrorEdicion:
        return True


print("borrador sin 'nombre' -- se rechaza antes de tocar la base")
comprobar(_rechaza({"tipo": "http"}), "sin nombre, ErrorEdicion inmediato")

print("\nborrador con 'tipo' invalido -- caso real visto en produccion (17/08/2026)")
comprobar(_rechaza({
    "nombre": "prueba_tipo_invalido_test_configuracion_guiada",
    "tipo": "catalogo",  # no existe -- el modelo lo invento la primera vez
    "auth_ref": "X", "endpoint": "https://x.com/y", "campos_disponibles": ["id"],
}), "'tipo: catalogo' se rechaza -- no es http/agregado/sql/webhook/batch/interno")

print("\nborrador sin 'roles_permitidos' -- tambien visto en el mismo caso real")
comprobar(_rechaza({
    "nombre": "prueba_sin_roles_test_configuracion_guiada",
    "tipo": "http", "solo_lectura": True,
    "base_url": "https://x.com", "endpoint": "/y",
}), "sin roles_permitidos (Field required), se rechaza")

print("\nborrador con nombre que ya existe en el catalogo real -- no debe pisarlo")
cfg = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
nombre_real = cfg.herramientas[0].nombre
comprobar(_rechaza({
    "nombre": nombre_real, "tipo": "http", "solo_lectura": True,
    "roles_permitidos": ["administracion"], "base_url": "https://x.com", "endpoint": "/y",
}), f"'{nombre_real}' ya existe -- el borrador con ese nombre se rechaza, no pisa el original")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Un borrador mal armado no llega al catalogo real -- la cerradura sigue puesta.")
