# -*- coding: utf-8 -*-
"""
================================================================================
 LA AUTONOMIA SE GANA CON EVIDENCIA  --  31/10/2026 (PRD §2, §8.17 Ola 3)
================================================================================

Una accion pasa de "una persona aprueba" a "la IA ejecuta" SOLO si cumple las
cuatro condiciones del PRD §2. Este modulo calcula las tres primeras, por
empresa y por accion, y lo dice con sus numeros. NO ejecuta nada ni cambia
ningun permiso: subir lo decide una persona viendo esto; bajar, el codigo.

  1. EFECTO VERIFICABLE EN CODIGO: la herramienta declara 'verificacion' con
     comprobaciones (reiniciar_ont mide 'last_status_change'). Sin eso, nunca:
     'registrar_pago' no tiene como medirse y queda afuera POR CONSTRUCCION,
     no por estar en una lista con su nombre (el nucleo no conoce nombres).
  2. PRECONDICIONES EN CODIGO: declara 'exige_previas', sobre datos medidos.
  3. EVIDENCIA EN ESTA EMPRESA, en la ventana: un minimo de propuestas que
     una persona reviso, una tasa de aprobacion por encima del umbral, CERO
     verificaciones no confirmadas y CERO ejecuciones fallidas.

  4. (DEGRADACION SOLA) vive donde se ejecuta: es la Fase B.

EL PISO
-------
Cada empresa elige sus umbrales ('autonomia_ganada' en su config), pero nunca
por debajo del piso del nucleo: ninguna empresa puede ganar autonomia con
cinco casos revisados o con una de cada cinco rechazada. Cero no confirmadas
y cero fallidas no se configuran: un solo reinicio que no reinicio es razon
suficiente para que una persona siga mirando.

El modelo no cuenta nada (PRD §12.5): los numeros salen de SQL y la regla de
aca.
================================================================================
"""

from __future__ import annotations

from datetime import timedelta

#: El piso del nucleo: lo menos que puede pedir una empresa.
PISO = {"minimo_revisadas": 20, "ventana_dias": 14, "tasa_minima_aprobacion": 0.90}
#: Lo que se pide si la empresa no dijo nada: mas que el piso.
POR_DEFECTO = {"minimo_revisadas": 30, "ventana_dias": 30, "tasa_minima_aprobacion": 0.95}


def por_que_no_es_candidata(herramienta) -> list[str]:
    """Las condiciones 1 y 2 que la herramienta no cumple, por su config.
    Vacio = es candidata."""
    faltan = []
    verificacion = getattr(herramienta, "verificacion", None)
    if verificacion is None or not getattr(verificacion, "comprobaciones", None):
        faltan.append("efecto_no_verificable")
    if not getattr(herramienta, "exige_previas", None):
        faltan.append("sin_previas_en_codigo")
    return faltan


def umbrales(config, accion: str) -> dict:
    """Los de la empresa para esa accion, o los por defecto. Nunca bajo el piso
    (el schema ya lo valida; esto lo repite por si llega una config vieja)."""
    propios = {}
    ag = getattr(config, "autonomia_ganada", None)
    if ag is not None and accion in (ag.acciones or {}):
        u = ag.acciones[accion]
        propios = {"minimo_revisadas": u.minimo_revisadas, "ventana_dias": u.ventana_dias,
                   "tasa_minima_aprobacion": u.tasa_minima_aprobacion}
    u = {**POR_DEFECTO, **propios}
    return {"minimo_revisadas": max(u["minimo_revisadas"], PISO["minimo_revisadas"]),
            "ventana_dias": max(u["ventana_dias"], PISO["ventana_dias"]),
            "tasa_minima_aprobacion": max(u["tasa_minima_aprobacion"], PISO["tasa_minima_aprobacion"])}


def veredicto(medicion: dict, u: dict) -> dict:
    """
    {'elegible', 'tasa_aprobacion', 'faltan': [{condicion, tiene, necesita}]}.
    'tasa_aprobacion' es None sin revisadas: 0 de 0 no es 0%.
    """
    revisadas = medicion["revisadas"]
    tasa = (revisadas - medicion["rechazadas"]) / revisadas if revisadas else None
    faltan = []
    if revisadas < u["minimo_revisadas"]:
        faltan.append({"condicion": "minimo_revisadas", "tiene": revisadas,
                       "necesita": u["minimo_revisadas"]})
    if tasa is None or tasa < u["tasa_minima_aprobacion"]:
        faltan.append({"condicion": "tasa_minima_aprobacion",
                       "tiene": None if tasa is None else round(tasa, 4),
                       "necesita": u["tasa_minima_aprobacion"]})
    if medicion["no_confirmadas"] > 0:
        faltan.append({"condicion": "cero_no_confirmadas", "tiene": medicion["no_confirmadas"],
                       "necesita": 0})
    if medicion["fallidas"] > 0:
        faltan.append({"condicion": "cero_fallidas", "tiene": medicion["fallidas"], "necesita": 0})
    return {"elegible": not faltan, "tasa_aprobacion": None if tasa is None else round(tasa, 4),
            "faltan": faltan}


def evaluar(config, tenant: str, ahora, *, medir) -> list[dict]:
    """
    Cada herramienta que hoy pide aprobacion humana, con si es candidata, su
    evidencia en la ventana de la empresa y si es elegible. medir(tenant,
    herramienta, desde, hasta) -> conteos (nucleo/persistencia/autonomia_ganada).
    """
    salida = []
    for h in config.herramientas:
        if not getattr(h, "aprobacion_humana", False):
            continue
        no_candidata = por_que_no_es_candidata(h)
        fila = {"accion": h.nombre, "candidata": not no_candidata, "no_candidata": no_candidata}
        if not no_candidata:
            u = umbrales(config, h.nombre)
            desde = ahora - timedelta(days=u["ventana_dias"])
            m = medir(tenant, h.nombre, desde, ahora)
            fila.update({"umbrales": u, "evidencia": m, "desde": desde.isoformat(),
                         **veredicto(m, u)})
        else:
            fila["elegible"] = False
        salida.append(fila)
    return salida
