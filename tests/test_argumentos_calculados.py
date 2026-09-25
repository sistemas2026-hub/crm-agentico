# -*- coding: utf-8 -*-
"""
================================================================================
 LAS FECHAS QUE SE CALCULAN AL LLAMAR
================================================================================

Por que existe
--------------
El ticket de instalacion tiene que decir cuando se estima empezar y cuando
terminar. La de inicio es el momento en que se crea; la de fin depende de
cuanto tarda ESA empresa en instalar -- un dato de operacion que cambia por
ISP y que, por la regla del proyecto, no puede quedar fijo en el YAML ni en
codigo: vive en 'variables_tenant' y se edita desde la pantalla.

'argumentos_calculados' es el mecanismo, y tiene tres cosas que probar:

1. LA GRAMATICA ES CERRADA. Solo 'ahora' y 'ahora+VARIABLE'. Esto viaja a una
   API de terceros con la credencial del tenant: un campo que aceptara una
   expresion libre convertiria la pantalla de configuracion en una via de
   ejecucion. Se valida al CARGAR, no al llamar -- una expresion mal escrita
   tiene que reventar cuando alguien guarda, no en medio de una instalacion.

2. EL FORMATO ES ISO 8601, y no es una preferencia. Verificado en vivo contra
   WispHub el 09/09/2026: ISO da 200, y 'DD/MM/AAAA HH:MM:SS' da 400 con el
   mensaje "Use uno de los siguientes formatos: YYYY-MM-DDThh:mm".

3. SIN LA VARIABLE NO SE INVENTA UN PLAZO. Si no esta cargada, o no es un
   numero, el argumento se OMITE. Un ticket sin fecha hace que alguien
   pregunte; un ticket con una fecha salida de un default escondido le promete
   al cliente algo que nadie decidio.

Corre SIN BASE DE DATOS y sin red.

Uso
---
    py -3.13 tests/test_argumentos_calculados.py
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config.schema import Herramienta                         # noqa: E402
from nucleo.modelo import motor                                      # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


BASE = dict(nombre="crear_ticket", tipo="http", endpoint="/api/tickets/",
            base_url="https://api.ejemplo.io", descripcion="x",
            roles_permitidos=["soporte"])


def herramienta(**extra):
    return Herramienta(**BASE, **extra)


print("== 1. la gramatica es cerrada ==")

for expresion in ("ahora", "ahora+DIAS_ESTIMADOS"):
    try:
        herramienta(argumentos_calculados={"f": expresion})
        ok = True
    except Exception:
        ok = False
    afirmar(ok, f"se acepta la forma valida {expresion!r}")

# Lo que NO se acepta. La ultima es la que explica por que la lista es blanca
# y no negra: cualquier cosa que no sea una de las dos formas se rechaza, sin
# intentar adivinar que quiso decir quien la escribio.
for expresion in ("ahora+", "manana", "ahora-1", "hoy+3",
                  "__import__('os').system('rm -rf /')", ""):
    try:
        herramienta(argumentos_calculados={"f": expresion})
        ok = False
    except Exception:
        ok = True
    afirmar(ok, f"se rechaza {expresion[:34]!r}")


print("\n== 2. 'ahora' es el momento de la llamada, en ISO 8601 ==")

h = herramienta(argumentos_calculados={"fecha_estimada_inicio": "ahora"})
args = motor._resolver_argumentos(h, None, {}, variables_tenant={})
valor = args.get("fecha_estimada_inicio")
afirmar(bool(valor), "el argumento sale con valor")

try:
    leido = datetime.fromisoformat(valor)
    formato_ok = True
except (TypeError, ValueError):
    leido, formato_ok = None, False
afirmar(formato_ok,
        "y se puede leer como ISO 8601 -- WispHub devuelve 400 con "
        "'DD/MM/AAAA', medido el 09/09/2026")
afirmar(formato_ok and abs((datetime.now() - leido).total_seconds()) < 120,
        "y es AHORA, no una fecha fija")


print("\n== 3. 'ahora+VARIABLE' suma los dias que diga el tenant ==")

h = herramienta(argumentos_calculados={"fecha_estimada_inicio": "ahora",
                                       "fecha_estimada_fin": "ahora+DIAS"})
args = motor._resolver_argumentos(h, None, {}, variables_tenant={"DIAS": "3"})
ini = datetime.fromisoformat(args["fecha_estimada_inicio"])
fin = datetime.fromisoformat(args["fecha_estimada_fin"])
dias = (fin - ini).total_seconds() / 86400
afirmar(2.99 < dias < 3.01, f"tres dias de diferencia (dieron {dias:.3f})")

# El valor sale de la variable, no de un numero escrito en el codigo: otra
# empresa que instale el mismo dia pone 1 y otra con lista de espera pone 15,
# sin que nadie toque el nucleo ni el YAML.
args = motor._resolver_argumentos(h, None, {}, variables_tenant={"DIAS": "15"})
ini = datetime.fromisoformat(args["fecha_estimada_inicio"])
fin = datetime.fromisoformat(args["fecha_estimada_fin"])
afirmar(14.99 < (fin - ini).total_seconds() / 86400 < 15.01,
        "con la variable en 15, quince -- el plazo lo decide la empresa")


print("\n== 4. sin la variable NO se inventa un plazo ==")
# Un ticket sin fecha hace que alguien pregunte. Un ticket con una fecha
# salida de un default escondido le promete al cliente algo que nadie decidio,
# y nadie se entera de que fue el codigo quien lo eligio.
for variables, caso in (({}, "la variable no esta cargada"),
                        ({"DIAS": ""}, "esta pero vacia"),
                        ({"DIAS": "pronto"}, "esta pero no es un numero")):
    args = motor._resolver_argumentos(h, None, {}, variables_tenant=variables)
    afirmar("fecha_estimada_fin" not in args,
            f"se omite la fecha de fin cuando {caso}")
    afirmar("fecha_estimada_inicio" in args,
            f"  y la de inicio SIGUE saliendo ({caso}) -- no depende de nadie")


print("\n== 5. no pisa a los otros argumentos ==")
# Convive con las tres formas que ya existian. Si se pisaran, un ticket saldria
# sin su servicio o sin su tecnico y nadie lo veria hasta mirarlo en WispHub.
h = herramienta(
    argumentos_fijos={"asunto": "Instalacion Nueva"},
    argumentos_desde_variables={"servicio": "ID_SERVICIO"},
    argumentos_calculados={"fecha_estimada_inicio": "ahora"})
args = motor._resolver_argumentos(h, None, {}, variables_tenant={"ID_SERVICIO": "3545"})
afirmar(args.get("asunto") == "Instalacion Nueva", "el fijo sigue estando")
afirmar(args.get("servicio") == "3545", "el que viene de una variable tambien")
afirmar("fecha_estimada_inicio" in args, "y la fecha calculada se suma")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] Las fechas se calculan al llamar, en ISO, y el plazo lo pone la empresa.")
