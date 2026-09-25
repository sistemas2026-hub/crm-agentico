# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE REDACCION DE TEXTO LIBRE
================================================================================

Por que existe
--------------
PRD.md 7.4 documenta el limite: la lista blanca decide que CAMPOS pasan, no
que CONTIENEN. Un ticket de instalacion real trajo nombre, telefono, email,
direccion, coordenadas GPS, numero de documento, plan con precio y un enlace
publico al PDF de la solicitud, todo en un solo campo de texto libre
('descripcion'). Este modulo (nucleo/seguridad/redaccion.py) es la
implementacion que el PRD dejaba pendiente.

El texto de abajo reconstruye ese caso (no es el original -- nunca se
guardo, ver PRD.md RNF-01) pero incluye los mismos TIPOS de dato que se
documentaron, para probar contra algo parecido a lo real en vez de un
ejemplo de laboratorio.

Uso
---
    py -3.13 tests/test_redaccion.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.seguridad import redaccion   # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


print("reconstruccion del caso real documentado en PRD.md 7.4")
TICKET_REAL = (
    "Instalacion para Juan Perez, cel 3012345678, correo juan.perez@gmail.com, "
    "vive en Calle 45 #12-30, coordenadas -4.123456, -73.654321. Cedula "
    "1044601347. Contrato PLAN HOGAR 100MB a $69900. Solicitud completa en "
    "https://wisphub.net/solicitudes/48213.pdf"
)
limpio = redaccion.redactar(TICKET_REAL)
print(f"  original: {TICKET_REAL[:70]}...")
print(f"  redactado: {limpio}")

comprobar("3012345678" not in limpio, "el telefono no sobrevive")
comprobar("juan.perez@gmail.com" not in limpio, "el email no sobrevive")
comprobar("-4.123456" not in limpio and "-73.654321" not in limpio,
         "las coordenadas GPS no sobreviven")
comprobar("1044601347" not in limpio, "la cedula no sobrevive")
comprobar("wisphub.net/solicitudes" not in limpio, "el enlace no sobrevive")

print("\nlo operativo -- lo que el colaborador SI necesita para atender el ticket -- se conserva")
comprobar("Instalacion" in limpio, "el motivo del ticket sigue legible")
comprobar("PLAN HOGAR" in limpio, "el plan contratado sigue legible (no es PII)")

print("\ncasos limite")
comprobar(redaccion.redactar("") == "", "texto vacio no revienta")
comprobar(redaccion.redactar(None) is None, "None no revienta")
comprobar(redaccion.redactar("el router esta en la sala") ==
         "el router esta en la sala",
         "texto sin PII queda intacto, letra por letra")

print("\nredactar_campos() -- mismo criterio que listas_blancas.py, dos formas de dato")
con_dict = redaccion.redactar_campos(
    {"descripcion": TICKET_REAL, "estado": "abierto"}, ["descripcion"])
comprobar("estado" in con_dict and con_dict["estado"] == "abierto",
         "un campo NO listado no se toca")
comprobar("3012345678" not in con_dict["descripcion"],
         "el campo listado si se redacta, en un dict suelto")

con_lista = redaccion.redactar_campos(
    {"total": 1, "resultados": [{"descripcion": TICKET_REAL, "id_ticket": 5}]},
    ["descripcion"])
comprobar("3012345678" not in con_lista["resultados"][0]["descripcion"],
         "tambien se redacta dentro de una lista de resultados paginada")
comprobar(con_lista["resultados"][0]["id_ticket"] == 5,
         "un campo numerico no listado no se toca ni se rompe")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] La redaccion saca la PII de un campo de texto libre sin volverlo inutil.")
