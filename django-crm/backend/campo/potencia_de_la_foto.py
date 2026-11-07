# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE DICE LA FOTO CONTRA LO QUE ESCRIBIO EL TECNICO  --  07/11/2026
================================================================================
El usuario, mirando la inspeccion de «Medicion al llegar» en la OT #187:

    «vamos desde aqui de medicion al llegar mira lo que respondio»

El modelo habia leido bien: «la pantalla se lee: 1310 nm, "Lo" y -70.00 dBm».
Ese numero es el dato mas importante de esa foto -- «Lo» es perdida de senal
-- y quedaba escrito en un parrafo y ahi moria.

Mientras tanto el tecnico escribe A MANO «Potencia al llegar: X dBm» en su
reporte. Nadie comparaba los dos. En la OT #186 escribio -21.0 dBm al llegar
Y al salir, identicos, que es justo el patron que conviene poder contrastar
contra lo que la foto muestra.

EL CODIGO CALCULA, EL MODELO SOLO DESCRIBE (CLAUDE.md §4). El modelo no juzga
si dos lecturas coinciden ni resta: escribe lo que ve, y de ese texto el
codigo saca el numero con una expresion regular y compara. Un juicio que
dependa de que el modelo reste no se puede auditar.

POR QUE NO SE REUSA `paso_a_despacho.niveles_reportados`
--------------------------------------------------------
Hace casi esto y se lo evaluo primero. Descarta todo lo que caiga fuera de
-45..-5 dBm, y con razon: lee tickets, donde el numero sale de una ONU y uno
de -70 seria un error de tipeo o un dato de otra cosa.

Aca la fuente es la pantalla de un medidor de mano, que SI baja de -45: la
foto que origino esto dice -70.00 dBm con el indicador «Lo». Reusar ese rango
habria descartado justo la lectura que importa.

LO QUE NO HACE
--------------
**No decide si el trabajo se cierra.** Devuelve un punto de la revision, como
los demas; quien decide es `revision_del_cierre`.

**No afirma cuando no puede.** Sin numero en la foto, o sin numero escrito
por el tecnico, el punto queda en «no se sabe» -- nunca en «no cumple». Una
foto que el modelo no supo leer no es un tecnico que mintio.
================================================================================
"""
from __future__ import annotations

import re

#:  UN NIVEL, tal como aparece escrito: "-70.00 dBm", "-21,0dBm", "-7 dBm".
#:  El signo es obligatorio -- una potencia optica recibida es negativa, y sin
#:  exigirlo "1310 nm" y "2 KHz" entrarian como lecturas.
_UN_NIVEL = r"-\s?\d{1,2}(?:[.,]\d{1,3})?"
_DBM = re.compile(_UN_NIVEL + r"\s*dbm", re.IGNORECASE)

#:  EL RANGO QUE UN MEDIDOR DE MANO PUEDE DAR. Mas ancho que el de
#:  `paso_a_despacho` (-45..-5) por el motivo de la cabecera: la foto que
#:  origino esto marca -70.00. El tope de abajo corta en -80 porque por
#:  debajo de eso ningun medidor del mercado lee: lo que venga mas abajo es
#:  un numero de otra cosa que quedo en la frase.
MINIMO = -80.0
MAXIMO = -1.0

#:  Cuanto pueden diferir las dos lecturas y seguir siendo "la misma".
#:
#:  POR QUE 3 dBm. Dos instrumentos distintos en el mismo punto no dan el
#:  mismo numero: el medidor de mano del tecnico y lo que el escribe redondean
#:  distinto, y la foto se saca en un momento y el dato se anota en otro. Tres
#:  dBm es media escala de las que la guia usa para clasificar un enlace, asi
#:  que una diferencia mayor ya no es ruido de medicion: o la foto es de otro
#:  punto, o el numero escrito no salio de esa pantalla.
TOLERANCIA_DBM = 3.0


def niveles(texto: str) -> list[float]:
    """Los dBm que trae un texto, en orden y sin repetir el mismo dos veces.

    Del texto del analisis de la foto, o del que escribio el tecnico: los dos
    son texto libre y se leen igual.
    """
    salida = []
    for bruto in _DBM.findall(texto or ""):
        crudo = bruto.replace(" ", "").replace(",", ".")
        crudo = crudo[:-3] if crudo.lower().endswith("dbm") else crudo
        try:
            valor = float(crudo)
        except ValueError:
            continue
        if not (MINIMO <= valor <= MAXIMO):
            continue
        if valor not in salida:
            salida.append(valor)
    return salida


def uno_solo(texto: str) -> float | None:
    """El unico nivel del texto, o `None` si no hay o hay mas de uno.

    CON DOS NUMEROS NO SE COMPARA. Una foto donde el modelo leyo dos lecturas
    --la de la ONU y la de la OLT, o una pantalla con historial-- no dice cual
    es la que el tecnico anoto, y elegir una seria inventar la mitad del
    juicio. Se prefiere «no se sabe» a una coincidencia sacada a la suerte.
    """
    v = niveles(texto)
    return v[0] if len(v) == 1 else None


def comparar(de_la_foto: float | None,
             del_tecnico: float | None) -> tuple[bool | None, str]:
    """`(coinciden, por_que)`. `None` cuando falta alguno de los dos.

    `coinciden=False` es una afirmacion fuerte --el numero escrito no salio de
    esa pantalla-- y por eso solo se da con los dos numeros en la mano.
    """
    if de_la_foto is None or del_tecnico is None:
        return None, "no se pudo leer la potencia en los dos lados"
    diferencia = abs(de_la_foto - del_tecnico)
    if diferencia <= TOLERANCIA_DBM:
        return True, (f"la foto marca {de_la_foto:.1f} dBm y el reporte dice "
                      f"{del_tecnico:.1f} dBm")
    return False, (f"la foto marca {de_la_foto:.1f} dBm y el reporte dice "
                   f"{del_tecnico:.1f} dBm: {diferencia:.1f} dBm de "
                   f"diferencia")
