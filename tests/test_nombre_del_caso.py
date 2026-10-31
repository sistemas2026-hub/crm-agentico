# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL NOMBRE DEL CASO: 64 CARACTERES, NI UNO MAS
================================================================================

Por que existe
--------------
El 28/08/2026 un cliente pidio un cambio de clave de WiFi. El ticket de la
operacion se creo bien, pero el caso del CRM se rechazo con:

    400 {"name": ["Ensure this field has no more than 64 characters."]}

El nombre medía 68. Y el detalle que lo hace peligroso: entraba de sobra
mientras el cliente NO estaba identificado -- ahi el nombre llevaba su numero
de telefono, que es corto. Arreglar la verificacion de identidad puso el
nombre real en su lugar y destapo el limite meses despues, en produccion, en
un caso que ademas fallaba en silencio (al cliente se le decia que su pedido
habia quedado registrado).

Lo que se guarda aca no es "que no pase de 64": es QUE se recorta cuando no
cabe. El identificador tiene que sobrevivir entero -- es lo unico que hace
unico al nombre (uno repetido tambien da 400) y lo que liga el caso con su
conversacion. El asunto tambien: es lo que decide a quien le toca. Lo que se
recorta es el nombre del cliente, que esta completo adentro del caso.

Uso
---
    py -3.13 tests/test_nombre_del_caso.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.seguimiento.nombres import (                        # noqa: E402
    LARGO_NOMBRE_CASO, nombre_del_caso)

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


print(__doc__.split("Uso")[0])
print("=" * 70)
print(" NOMBRE DEL CASO")
print("=" * 70)

# --- el caso real que fallo --------------------------------------------
ID = "3071c437fe8f4d1a"
real = nombre_del_caso("Cambio De Contraseña En Router Wifi",
                        "MARIO SABANAGRANDE", ID)
print()
print("el caso que rompio produccion el 28/08/2026")
print(f"      -> {real}")
comprobar(len(real) <= LARGO_NOMBRE_CASO,
          f"entra en {LARGO_NOMBRE_CASO} caracteres (medía 68)")
comprobar(real.endswith("#3071c437"),
          "el identificador queda ENTERO al final: es lo que lo hace unico")
comprobar(real.startswith("Cambio De Contraseña En Router Wifi"),
          "el asunto queda entero: es lo que decide a quien le toca")
comprobar("MARIO" in real,
          "del cliente queda lo que se pueda, no se borra de una")

# --- que se recorta el cliente, y solo el ------------------------------
print()
print("cuando no cabe, se recorta el cliente")
largo = nombre_del_caso("Internet Lento",
                         "MARIA FERNANDA DE LOS SANTOS RODRIGUEZ", ID)
comprobar(len(largo) <= LARGO_NOMBRE_CASO, "un nombre larguisimo tambien entra")
comprobar(largo.endswith("#3071c437") and largo.startswith("Internet Lento"),
          "sigue teniendo asunto e identificador completos")
comprobar("…" in largo, "el recorte se ve: no parece un apellido de verdad")

corto = nombre_del_caso("Internet Lento", "JOSE PEREZ", ID)
comprobar(corto == "Internet Lento · JOSE PEREZ · #3071c437",
          "lo que ya cabe no se toca")

# --- los bordes ---------------------------------------------------------
print()
print("los bordes")
sin_cliente = nombre_del_caso("Internet Lento", "", ID)
comprobar(sin_cliente == "Internet Lento · #3071c437",
          "sin cliente identificado no queda un separador colgando")

asunto_gigante = nombre_del_caso("A" * 200, "JOSE PEREZ", ID)
comprobar(len(asunto_gigante) <= LARGO_NOMBRE_CASO,
          "un asunto absurdo se recorta el tambien: un nombre feo es mejor "
          "que un caso que no se crea")

vacio = nombre_del_caso("", "", ID)
comprobar(vacio == "Consulta · #3071c437",
          "sin asunto ni cliente igual dice algo")

# Nadie sabe cuanto mide el nombre de un cliente antes de leerlo, asi que la
# unica garantia util es que ningun largo lo rompa.
print()
print("ningun largo de nombre lo pasa de 64")
paso = True
for n in range(0, 120):
    for asunto in ("Internet Lento", "Cambio De Contraseña En Router Wifi"):
        nombre = nombre_del_caso(asunto, "X" * n, ID)
        if len(nombre) > LARGO_NOMBRE_CASO or not nombre.endswith("#3071c437"):
            paso = False
            print(f"      con {n} caracteres de nombre: {len(nombre)} -> {nombre}")
comprobar(paso, "240 combinaciones de asunto y largo de cliente, todas entran")

print()
print("=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S) -- un caso asi no se crea y nadie lo ve")
    for f in fallos:
        print(f"   - {f}")
    print("=" * 70)
    sys.exit(1)
print(" Todo en orden: el nombre entra y no pierde lo que lo identifica.")
print("=" * 70)
