# -*- coding: utf-8 -*-
"""
================================================================================
 LA JORNADA DEL DIA, ARMADA SOLA  --  copiando la del ultimo dia trabajado
================================================================================

POR QUE HACE FALTA
------------------
`reparto.proponer()` reparte entre las cuadrillas que YA tienen jornada armada
ese dia:

    JornadaDeCuadrilla.objects.filter(org=org, fecha=fecha)

La composicion es del dia a proposito --es lo que permite decir quien estuvo el
miercoles pasado-- pero eso tiene un costo: a las 3 de la mañana del martes, la
jornada del martes todavia no existe. Sin este modulo el reparto automatico
devolveria vacio todas las noches, y el sintoma seria "no se asigno nada", que
no señala a la causa.

DE DONDE SALE LA JORNADA DE HOY
-------------------------------
    1. la del ultimo dia que esa cuadrilla trabajo    <- el caso normal
    2. lo HABITUAL de la cuadrilla                    <- el arranque en frio
    3. nada, y se dice cual y por que                 <- ni una ni otra

El 2 existe porque sin el, una empresa que acaba de dar de alta sus cuadrillas
tendria que armar un dia entero a mano antes de que esto sirviera para algo.

LO QUE NO PISA
--------------
Una jornada que YA existe para esa fecha no se toca. Si alguien la armo --o la
corrigio-- esa decision gana: la tomo una persona mirando el caso, y este
proceso corre a las tres de la mañana sin mirar nada.

Eso hace la operacion IDEMPOTENTE: correrla dos veces deja lo mismo que
correrla una, que es la condicion para poder reintentarla sin pensar.

QUE NO SE COPIA
---------------
Las personas dadas de BAJA. Copiar a alguien que ya no trabaja ahi lo pondria
a recibir trabajo, y el dia que se note ya habria un cliente esperando. Se
cuenta cuantas quedaron afuera y se informa -- un silencio ahi se leeria como
que la cuadrilla esta completa.
"""

from __future__ import annotations

from django.db import transaction

from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                              JornadaDeCuadrilla)


def _ultima_jornada(cuadrilla, antes_de):
    """La jornada mas reciente de esa cuadrilla ANTERIOR a la fecha pedida.

    `antes_de` y no `<=`: si ya hay una del mismo dia, no hay nada que armar
    -- de eso se encarga quien llama, y copiarse a si misma seria un no-op
    disfrazado de trabajo.
    """
    return (
        JornadaDeCuadrilla.objects
        .filter(cuadrilla=cuadrilla, fecha__lt=antes_de)
        .prefetch_related("zonas", "integrantes__persona")
        .order_by("-fecha")
        .first()
    )


def _crear_desde(cuadrilla, fecha, anterior):
    """Copia la jornada anterior. Devuelve (jornada, cuantos_de_baja)."""
    jornada = JornadaDeCuadrilla.objects.create(
        org=cuadrilla.org,
        cuadrilla=cuadrilla,
        fecha=fecha,
        labor=anterior.labor,
        # El lider del DIA, no el de la cuadrilla: si el martes la llevo otro,
        # el miercoles arranca con ese y alguien lo corrige si hace falta.
        lider=anterior.lider or cuadrilla.lider,
    )
    jornada.zonas.set(anterior.zonas.all())

    de_baja = 0
    for viejo in anterior.integrantes.all():
        if not viejo.persona.activa:
            de_baja += 1
            continue
        IntegranteDeJornada.objects.create(
            org=cuadrilla.org, jornada=jornada,
            persona=viejo.persona, rol=viejo.rol,
        )
    return jornada, de_baja


def _crear_desde_lo_habitual(cuadrilla, fecha):
    """El arranque en frio: la cuadrilla nunca trabajo todavia.

    Se arma con lo que la cuadrilla declara como habitual. Los integrantes no
    salen de ahi --quien trabaja cada dia es del dia-- asi que la jornada nace
    con el lider solo, si lo tiene. Alguien le agrega la gente; lo que esto
    evita es que no exista NADA que corregir.
    """
    jornada = JornadaDeCuadrilla.objects.create(
        org=cuadrilla.org,
        cuadrilla=cuadrilla,
        fecha=fecha,
        labor=cuadrilla.labor_habitual,
        lider=cuadrilla.lider,
    )
    jornada.zonas.set(cuadrilla.zonas_habituales.all())
    return jornada


def asegurar_jornadas(org, fecha) -> dict:
    """Deja armada la jornada de cada cuadrilla activa para esa fecha.

    No pisa lo que ya existe. Devuelve que paso con cada una, nombrandolas:
    un conteo sin nombres obliga a salir a buscar cual fue.

        {
          "copiadas":   [{"cuadrilla": ..., "desde": fecha, "sin_gente": n}],
          "estrenadas": [...],   # armadas con lo habitual, nunca trabajaron
          "ya_estaban": [...],   # alguien las armo a mano; no se tocaron
          "sin_base":   [...],   # ni jornada anterior ni habitual utilizable
          "sin_zona":   [...],   # quedaron armadas pero NO reciben trabajo
        }
    """
    salida = {"copiadas": [], "estrenadas": [], "ya_estaban": [],
              "sin_base": [], "sin_zona": []}

    cuadrillas = list(
        Cuadrilla.objects.filter(org=org, activa=True)
        .prefetch_related("zonas_habituales")
        .order_by("nombre")
    )
    ya = set(
        JornadaDeCuadrilla.objects
        .filter(org=org, fecha=fecha)
        .values_list("cuadrilla_id", flat=True)
    )

    for cuadrilla in cuadrillas:
        if cuadrilla.id in ya:
            salida["ya_estaban"].append(cuadrilla.nombre)
            continue

        anterior = _ultima_jornada(cuadrilla, fecha)
        with transaction.atomic():
            if anterior is not None:
                jornada, de_baja = _crear_desde(cuadrilla, fecha, anterior)
                salida["copiadas"].append({
                    "cuadrilla": cuadrilla.nombre,
                    "desde": anterior.fecha.isoformat(),
                    "sin_gente": de_baja,
                })
            elif cuadrilla.zonas_habituales.exists() or cuadrilla.lider_id:
                jornada = _crear_desde_lo_habitual(cuadrilla, fecha)
                salida["estrenadas"].append(cuadrilla.nombre)
            else:
                # Ni historia ni habitual: armarla seria crear una jornada que
                # no puede recibir nada. Se dice en vez de dejar una fila
                # vacia que parece trabajo hecho.
                salida["sin_base"].append(cuadrilla.nombre)
                continue

        # VACIO NO ES "CUBRE TODAS". Una cuadrilla sin zona no recibe trabajo
        # por zona, asi que queda armada y aun asi no va a aparecer en el
        # reparto -- eso tiene que notarse ahora, no a las siete.
        if not jornada.zonas.exists():
            salida["sin_zona"].append(cuadrilla.nombre)

    return salida
