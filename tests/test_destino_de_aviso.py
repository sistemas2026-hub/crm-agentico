# -*- coding: utf-8 -*-
"""
================================================================================
 A QUIEN SE LE ESCRIBE UN AVISO  --  nucleo/seguimiento/destino.py (30/10/2026)
================================================================================

Un aviso proactivo le escribe a un cliente que no esta chateando. Su numero
sale del sistema del ISP CRUDO: sin indicativo, y con varios numeros en uno
solo en el 55% de los casos ("3001234567, 3109876543"). Lo que se protege:

  - se extraen los moviles con el patron que ya declara la empresa
    (autenticacion.patron_extraccion) y se les pone SU indicativo;
  - sin indicativo declarado no se inventa uno: no hay destino;
  - la conversacion del caso gana sobre el campo crudo (es el numero que el
    cliente usa de verdad con la empresa);
  - con varios numeros, gana el que ya le escribio a la empresa por WhatsApp;
    si ninguno, el primero (el principal en el ISP);
  - el numero que sale tiene la MISMA forma que 'usuario_externo', que es lo
    que compara la baja (Ley 1581): una forma distinta la saltaria.

Sin base: las consultas se inyectan.

    py -3.13 tests/test_destino_de_aviso.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.seguimiento import destino                     # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


def config(indicativo="57", patron=r"(?<!\d)3\d{9}(?!\d)"):
    return SimpleNamespace(autenticacion=SimpleNamespace(patron_extraccion=patron,
                                                         indicativo_pais=indicativo))


print("\nextraer y normalizar")
comprobar(destino.numeros_whatsapp(config(), "3001234567, 3109876543") == ["573001234567", "573109876543"],
          "dos moviles en un campo, cada uno con el indicativo")
comprobar(destino.numeros_whatsapp(config(), "Tel: 300 123 4567") == ["573001234567"],
          "un movil escrito con espacios es el mismo movil")
comprobar(destino.numeros_whatsapp(config(), "+57 312 455 8901") == ["573124558901"],
          "con el indicativo ya puesto, no se le pone dos veces")
comprobar(destino.numeros_whatsapp(config(), "312-455-8901") == ["573124558901"],
          "con guiones, igual")
comprobar(destino.numeros_whatsapp(config(), "3001234567 3109876543") == ["573001234567", "573109876543"],
          "dos moviles separados solo por un espacio siguen siendo dos")
comprobar(destino.numeros_whatsapp(config(), "57 6052345678") == [],
          "un fijo con indicativo no se vuelve movil")
comprobar(destino.numeros_whatsapp(config(), "3001234567 / 3001234567") == ["573001234567"],
          "el mismo numero dos veces cuenta una")
comprobar(destino.numeros_whatsapp(config(indicativo=None), "3001234567") == [],
          "sin indicativo declarado no se inventa uno")
comprobar(destino.numeros_whatsapp(config(), "") == [] and destino.numeros_whatsapp(config(), None) == [],
          "vacio o None, ninguno")

print("\nelegir a quien")
conocidos = {"573109876543"}
r = destino.elegir(config(), conversacion=None, telefono_crudo="3001234567, 3109876543",
                   ya_escribio=lambda n: n in conocidos)
comprobar(r == ("573109876543", "conocido"), "gana el numero que ya le escribio a la empresa", str(r))
r = destino.elegir(config(), conversacion=None, telefono_crudo="3001234567, 3109876543",
                   ya_escribio=lambda n: False)
comprobar(r == ("573001234567", "primero_del_isp"), "si ninguno, el primero del ISP", str(r))
r = destino.elegir(config(), conversacion="573155550000", telefono_crudo="3001234567",
                   ya_escribio=lambda n: False)
comprobar(r == ("573155550000", "conversacion"), "la conversacion del caso gana sobre el campo crudo", str(r))
r = destino.elegir(config(indicativo=None), conversacion=None, telefono_crudo="3001234567",
                   ya_escribio=lambda n: False)
comprobar(r == (None, "sin_indicativo"), "sin indicativo y sin conversacion: sin destino, con su motivo", str(r))
r = destino.elegir(config(), conversacion=None, telefono_crudo="fijo 6052345678",
                   ya_escribio=lambda n: False)
comprobar(r == (None, "sin_movil"), "sin un movil reconocible: sin destino", str(r))

print("\nun identificador que no es un numero")
r = destino.elegir(config(), conversacion="CO.1360399936298471", telefono_crudo="3001234567",
                   ya_escribio=lambda n: False)
comprobar(r == ("573001234567", "primero_del_isp"),
          "un BSUID del chat NO se vuelve numero quitandole las letras: se usa el del ISP", str(r))
r = destino.elegir(config(), conversacion="+573155550000", telefono_crudo=None, ya_escribio=lambda n: False)
comprobar(r == ("573155550000", "conversacion"), "un '+' delante si es un numero", str(r))

print("\nla forma es la que compara la baja")
comprobar(all(n.isdigit() for n in destino.numeros_whatsapp(config(), "+57 3001234567 ;3109876543")),
          "solo digitos, sin '+' ni espacios, como usuario_externo")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Un aviso sabe a quien escribirle, y cuando no lo sabe no adivina.")
