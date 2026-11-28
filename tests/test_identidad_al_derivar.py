# -*- coding: utf-8 -*-
"""
================================================================================
 AL DERIVAR NO SE AFIRMA UNA IDENTIDAD QUE NO SE VERIFICO
================================================================================

Por que existe
--------------
Cuando el router deriva, el motor le inyecta al area destino un mensaje de
sistema que le dice como seguir. El parentesis sobre la identidad era una
CONSTANTE: "ya esta verificado, no le pidas la identidad de nuevo", pasara lo
que pasara.

Pero el router NO verifica a nadie -- es una decision explicita
(Rol.deriva_verificacion): cada especialista pide la cedula en su propio
contexto, porque cuando la verificacion vivia en el router, alguien que se
equivocaba tipeando terminaba con una pregunta de ventas que no tenia nada
que ver con lo que habia pedido. Asi que derivar SIN verificar no es un borde
raro: es el camino normal.

Lo que producia, medido el 12/09/2026 en el simulador con una conversacion
sin verificar:

    cliente : hola para cancelar mi servicio
    router  : (deriva a facturacion) ...me pasas tu numero de cedula?
    cliente : 000021
    agente  : "No necesito ese numero, ya tengo tu cuenta ubicada."

Las dos mitades falsas: ni la tenia ubicada ni podia tenerla. El dato no se
filtro -- la guarda de identidad sigue frenando las herramientas-- pero el
especialista se saltea la verificacion y el cliente escucha una mentira sobre
lo que el sistema sabe de el.

Es la misma familia que "el sistema me confirma que sos el titular"
(15/08/2026), y se arreglo igual: diciendole al modelo lo que pasa, en vez de
esperar que lo deduzca de una ausencia.

IMPORTANTE -- POR QUE NO ALCANZABA UNA INSTRUCCION EN EL PROMPT. Se probo
primero: se agrego al prompt del tenant que no dijera tener la cuenta
ubicada, y el modelo siguio diciendolo. Tenia razon en ignorarlo -- el
mensaje del handoff es POSTERIOR y mas especifico, y afirmaba lo contrario.
Dos instrucciones que se contradicen no se resuelven pidiendo mas fuerte.
PRD 7.4: el prompt guia, el codigo garantiza.

Lo que se fija
--------------
1. VERIFICADO Y SIN VERIFICAR DICEN COSAS DISTINTAS. Es lo unico que importa:
   la version rota tenia un solo texto para los dos estados, asi que
   cualquier prueba que solo comprobara "el mensaje existe" la habria dado
   por buena.

2. SIN VERIFICAR NUNCA AFIRMA QUE SI. Ni con las palabras exactas de la
   version rota ni diciendo que no hace falta el documento.

3. FAIL-CLOSED SIN SESION. Sin sesion se asume no verificado: afirmar de mas
   una identidad es el error caro, afirmar de menos cuesta una pregunta.

4. NO SE AFIRMA SOBRE LA REDACCION, se afirma sobre lo que la redaccion
   HABILITA: que el texto no le diga al especialista que puede saltearse la
   identidad.

Corre SIN BASE DE DATOS y sin red: la funcion es pura.

Uso
---
    py -3.13 tests/test_identidad_al_derivar.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.modelo.motor import nota_de_identidad_al_derivar     # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    if not condicion:
        fallos.append(que)


def comprobar(seccion: str) -> None:
    print(f"\n--- {seccion} ---")


class SesionFalsa:
    def __init__(self, verificado: bool):
        self.verificado = verificado


# ---------------------------------------------------------------------------
comprobar("1. los dos estados no pueden decir lo mismo")

con = nota_de_identidad_al_derivar(SesionFalsa(True))
sin = nota_de_identidad_al_derivar(SesionFalsa(False))

afirmar(con != sin,
        "verificado y sin verificar producen EL MISMO texto -- es exactamente "
        "la version rota, que tenia una constante para los dos estados")
afirmar(bool(con.strip()) and bool(sin.strip()),
        "alguno de los dos textos vino vacio")

print(f"  verificado    : {con[:70]}")
print(f"  sin verificar : {sin[:70]}")

# ---------------------------------------------------------------------------
comprobar("2. sin verificar no afirma una identidad que no existe")

# El texto exacto de la version rota. Si vuelve a aparecer en el camino sin
# verificar, la regresion es literal.
afirmar("ya esta verificado" not in sin.lower(),
        "sin verificar sigue diciendo 'ya esta verificado' -- es el texto "
        "exacto que causo 'ya tengo tu cuenta ubicada' el 12/09/2026")

# Lo que el modelo dedujo de ese texto, no solo el texto.
#
# OJO CON LA FORMA DE ESTA COMPROBACION. La primera version buscaba el
# substring "cuenta ubicada" y fallaba contra el texto CORRECTO, que dice
# "no tienes su cuenta ubicada" -- la misma frase, negada, que es
# precisamente lo que queremos que diga. Buscar la frase suelta no distingue
# afirmarla de desmentirla. Se comprueba la forma AFIRMATIVA.
for frase in ("no le pidas la identidad", "ya tienes su cuenta ubicada",
              "no necesito", "no hace falta"):
    afirmar(frase not in sin.lower(),
            f"sin verificar insinua que la identidad esta resuelta: '{frase}'")

# Y que lo desmienta explicitamente, que es el punto del arreglo.
afirmar("no tienes su cuenta ubicada" in sin.lower()
        or "no tenes su cuenta ubicada" in sin.lower(),
        "sin verificar no desmiente tener la cuenta ubicada -- esa fue la "
        "frase exacta que el modelo fabrico")

# Y tiene que decir explicitamente que NO lo esta: el bug nacio de que el
# modelo tuviera que inferirlo de una ausencia.
afirmar("no esta verificado" in sin.lower(),
        "sin verificar no dice EXPLICITAMENTE que no lo esta -- dejarselo "
        "inferir de una ausencia es lo que fallo")

# ---------------------------------------------------------------------------
comprobar("3. verificado sigue sirviendo para lo que fue escrito")

afirmar("ya esta verificado" in con.lower(),
        "verificado dejo de decir que lo esta: el router volveria a pedirle "
        "la cedula a alguien ya verificado, que es el bug de agosto 2026")

# ---------------------------------------------------------------------------
comprobar("4. fail-closed: sin sesion se asume no verificado")

afirmar(nota_de_identidad_al_derivar(None) == sin,
        "sin sesion no da el mismo texto que sin verificar -- tiene que ser "
        "fail-closed")

# Una sesion a la que le falta el atributo tampoco puede dar por verificado.
class SesionSinAtributo:
    pass

afirmar(nota_de_identidad_al_derivar(SesionSinAtributo()) == sin,
        "una sesion sin el atributo 'verificado' no se trata como no "
        "verificada")

# ---------------------------------------------------------------------------
print()
if fallos:
    print(f"[FALLA] {len(fallos)} problema(s):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)

print("[OK] Al derivar, la nota de identidad dice la verdad en los dos estados.")
