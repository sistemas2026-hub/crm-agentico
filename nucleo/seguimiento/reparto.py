# -*- coding: utf-8 -*-
"""
================================================================================
 REPARTO DE TRABAJO  --  a quien le toca cuando un area tiene varias personas
================================================================================

Por que existe
--------------
Con una sola persona por area no hay nada que decidir. Con dos o mas si, y
hasta ahora el codigo se plantaba: dejaba el caso sin asignar antes que
elegir a dedo. Eso era correcto como piso -- un reparto arbitrario parece
razonable y no lo es -- pero deja trabajo sin dueño, que es justo lo que hay
que evitar.

Como reparte
------------
Al que MENOS tiene abierto. No por turnos.

Un turno rotativo reparte parejo en el papel y desparejo en la practica: si a
una persona le tocaron tres casos que se estancaron y a otra tres que cerro,
el turno les sigue dando la misma cantidad. Mirar lo que cada uno tiene
ABIERTO equilibra solo, y sigue la disponibilidad sin llevar ningun contador
aparte: quien se desocupa vuelve a ser el que menos tiene, y le toca.

Dos cosas que NO hace, a proposito
-----------------------------------
No desempata al azar. Ante la misma carga gana un orden estable, para que la
pregunta "¿por que le toco a esta persona?" tenga respuesta seis meses
despues. Un reparto que no se puede explicar es uno que nadie va a confiar.

No mide "que tan ocupado esta alguien", mide cuanto tiene abierto. Son cosas
distintas -- dos casos dificiles pueden pesar mas que ocho triviales -- y el
conteo es la mejor aproximacion disponible sin pedirle a nadie que cargue su
propia disponibilidad a mano.
================================================================================
"""

from __future__ import annotations


def elegir_menos_cargado(candidatos: list[str],
                         carga: dict[str, int] | None = None) -> str | None:
    """
    De 'candidatos', el que menos trabajo abierto tiene.

    'carga' puede venir incompleta: quien no aparece se cuenta como 0. Es lo
    correcto -- si de alguien no hay registro es porque no tiene nada -- y
    ademas hace que un fallo al consultar la carga degrade a un reparto por
    orden estable en vez de romper la asignacion.

    Devuelve None solo si no hay candidatos.
    """
    if not candidatos:
        return None
    carga = carga or {}
    # El orden alfabetico del identificador es el desempate: arbitrario, si,
    # pero IGUAL siempre. Eso es lo que lo vuelve explicable.
    return min(sorted(candidatos), key=lambda c: carga.get(c, 0))


def contar_por_responsable(filas, campo: str) -> dict[str, int]:
    """
    Cuantos elementos abiertos tiene cada responsable, a partir de una lista de
    registros ya filtrada a lo que cuenta como abierto.

    'campo' es donde vive el responsable en cada fila. Se aceptan las dos
    formas en que las APIs lo devuelven -- un id suelto o un objeto con 'id' --
    porque asumir una sola es como se rompen estas integraciones.
    """
    salida: dict[str, int] = {}
    for f in filas or []:
        if not isinstance(f, dict):
            continue
        valor = f.get(campo)
        if isinstance(valor, dict):
            valor = valor.get("id")
        elif isinstance(valor, list):
            # Algunos CRM permiten varios responsables: cuenta para todos, que
            # es lo honesto -- el caso ocupa a los dos.
            for v in valor:
                clave = v.get("id") if isinstance(v, dict) else v
                if clave:
                    salida[str(clave)] = salida.get(str(clave), 0) + 1
            continue
        if valor:
            salida[str(valor)] = salida.get(str(valor), 0) + 1
    return salida
