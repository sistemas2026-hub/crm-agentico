# -*- coding: utf-8 -*-
"""
Si el motivo de una cancelacion lo dijo el cliente, o lo relleno el modelo.

POR QUE EXISTE
--------------
Medido el 10/09/2026 en una conversacion real. El prompt de ventas dice, en su
paso 4, "pedile el MOTIVO, y dejalo hablar". El modelo salto del paso 3 al 5 --
confirmo el nombre y contesto "Listo, tu solicitud quedo cancelada"-- y mando
de motivo la frase 'El cliente no dio motivo'.

La cancelacion quedo guardada con un motivo que nadie dijo. Eso vacia de
sentido a la funcion entera: el motivo existe para que, leidos en conjunto,
digan si las ventas se caen por precio, por demora o por la competencia. Un
relleno contamina esa lectura y encima parece un dato.

La comprobacion de "campo no vacio" ya existia y no alcanzo, porque el modelo
lo lleno. PRD 7.4: el prompt es guia, el codigo es la garantia.

POR QUE VIVE EN SU PROPIO ARCHIVO
---------------------------------
Sin importar Django. Asi la regla se puede probar en una maquina que no tiene
el entorno del backend levantado -- que es exactamente la situacion en la que
se escribio, y una regla que no se puede correr es una regla que nadie
comprueba.

LO QUE ESTO NO HACE
-------------------
No detecta mentiras. Si el modelo inventa "el cliente se muda", pasa. Solo
tapa la familia de frases con las que un modelo rellena un campo obligatorio
cuando se salteo el paso de preguntar, que es el fallo que de verdad ocurrio.
"""

from __future__ import annotations

import unicodedata

# Lo que escribe un modelo cuando NO pregunto el motivo. Se compara por
# CONTENCION sobre el texto normalizado, no por igualdad: la frase exacta
# cambia en cada corrida ("no dio motivo", "el cliente no dio un motivo",
# "no quiso decir el motivo") y perseguir cadenas exactas seria perseguir al
# modelo para siempre.
#
# Lista en español a proposito: describe como falla ESTE producto, que atiende
# en español. Un tenant que atienda en otro idioma necesita la suya.
RELLENOS = (
    "no dio motivo", "no dijo motivo", "no indico motivo", "no especifico",
    "no quiso decir", "sin motivo", "no proporciono", "no menciono",
    "motivo no", "no se especifica", "no informo", "no dio razon",
    "no dio un motivo", "no brindo",
)

# Un motivo de verdad tiene palabras. "ok", "ya", "x" no son un motivo, y
# exigir dos evita que el relleno se disfrace de brevedad.
MINIMO_PALABRAS = 2


def plano(texto: str) -> str:
    """Sin tildes, sin mayusculas, sin espacios de mas."""
    t = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def es_de_relleno(motivo: str) -> bool:
    """Si esto lo escribio el modelo en vez del cliente."""
    llano = plano(motivo)
    if len(llano.split()) < MINIMO_PALABRAS:
        return True
    return any(p in llano for p in RELLENOS)
