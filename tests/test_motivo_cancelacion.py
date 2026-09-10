# -*- coding: utf-8 -*-
"""
================================================================================
 EL MOTIVO DE UNA CANCELACION LO DICE EL CLIENTE, NO EL MODELO
================================================================================

Por que existe
--------------
Medido el 10/09/2026 en una conversacion real, numero 312 000 004:

    [CLIENTE] para cancelar mi instalacion
    [AGENTE ] ¿me pasas la cedula con la que registraste la solicitud?
    [CLIENTE] 1023456789
    [AGENTE ] ¿me dices el nombre completo con el que la registraste?
    [CLIENTE] rafael moreno
    [AGENTE ] Listo, tu solicitud quedo cancelada.

Salto del paso 3 al 5 del protocolo y mando de motivo la frase 'El cliente no
dio motivo'. El paso 4 -- "pedile el MOTIVO, y dejalo hablar"-- estaba escrito
en el prompt, intacto, y se ignoro.

La cancelacion quedo guardada con un motivo que nadie dijo. Eso vacia de
sentido a la funcion entera: el motivo existe para que, leidos en conjunto,
digan si las ventas se caen por precio, por demora o por la competencia. Un
relleno contamina esa lectura y encima parece un dato.

La comprobacion de "campo no vacio" ya existia y NO alcanzo, porque el modelo
lo lleno. Es el mismo patron de todo este proyecto: PRD 7.4, el prompt es
guia, el codigo es la garantia.

Corre SIN DJANGO y sin base: por eso la regla vive en solicitudes/motivos.py y
no dentro de la vista. Una regla que no se puede correr es una regla que nadie
comprueba.

Uso
---
    py -3.13 tests/test_motivo_cancelacion.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "django-crm" / "backend"))

from solicitudes.motivos import es_de_relleno, plano                 # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


print("== 1. la frase EXACTA que se midio ==")
afirmar(es_de_relleno("El cliente no dio motivo"),
        "'El cliente no dio motivo' se rechaza -- es la que mando el modelo "
        "el 10/09/2026")


print("\n== 2. y la FAMILIA, no solo esa frase ==")
# Se compara por contencion sobre el texto normalizado, no por igualdad: la
# frase exacta cambia en cada corrida, y perseguir cadenas literales seria
# perseguir al modelo para siempre.
for texto in ("no dio motivo",
              "El cliente no dio un motivo especifico",
              "No quiso decir el motivo",
              "Cancelacion sin motivo",
              "El cliente no especifico razones",
              "no menciono el motivo",
              "El cliente no informo la razon",
              "NO DIO MOTIVO",
              "El cliente no indicó motivo"):
    afirmar(es_de_relleno(texto), f"se rechaza {texto!r}")


print("\n== 3. un motivo demasiado corto tampoco es un motivo ==")
# Sin esto, el relleno se disfraza de brevedad: 'ok', 'x', 'ya'.
for texto in ("ok", "x", "ya", "  ", "", "-"):
    afirmar(es_de_relleno(texto), f"se rechaza {texto!r}")


print("\n== 4. los motivos REALES pasan ==")
# Son los que hay guardados en produccion, tal cual los escribieron los
# clientes. Si alguno de estos se rechazara, la guarda seria peor que el bug:
# bloquearia cancelaciones legitimas y el cliente quedaria atrapado.
for texto in ("se murio el gato",
              "me separe y me toco irme de la casa y yo no iba dejar internet "
              "a mi exmujer",
              "prueba agendar instalacion",
              "consegui mas barato en otro lado",
              "ya no me voy a mudar",
              "me demoraron mucho",
              "no me alcanza el presupuesto"):
    afirmar(not es_de_relleno(texto), f"pasa {texto[:46]!r}")


print("\n== 5. la normalizacion no cambia lo que se guarda ==")
# 'plano' es solo para COMPARAR. El motivo se guarda literal -- lo pidio el
# negocio y tiene razon: un resumen perderia justo lo que sirve.
afirmar(plano("  El   Cliente  NO Dió  Motivo ") == "el cliente no dio motivo",
        "compara sin tildes, sin mayusculas y sin espacios de mas")

fuente = (RAIZ / "django-crm/backend/solicitudes/gestion.py").read_text(encoding="utf-8")
afirmar("s.motivo_cancelacion = motivo" in fuente,
        "y lo que se guarda sigue siendo el texto ORIGINAL, no el normalizado")
bloque = fuente[fuente.index("if es_de_relleno(motivo):"):][:3000]
afirmar("instruccion_interna" in bloque and "Preguntale al cliente" in bloque,
        "al rechazar se le dice al modelo que PREGUNTE, no solo que fallo -- "
        "un error sin salida lo deja intentando lo mismo")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] Un motivo que el cliente no dijo no puede cancelar nada.")
