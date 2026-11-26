# -*- coding: utf-8 -*-
"""
================================================================================
 LOS PUNTOS DE TV DE UN TIPO DE TRABAJO
================================================================================
El usuario, el 26/11/2026: «para saber cuanto gastaron en material para TV, se
pueden poner unos botones, primero preguntando cuantos puntos de TV, y cada uno
ya tendria el material utilizado: conectores, spliter y cable». La regla que
eligio:

    1 punto            2 conectores coaxiales, sin spliter
    n puntos (n >= 2)  2 por punto + 2 de entrada (2 = 6, 3 = 8, 4 = 10, 5 = 12)
                       y un spliter: el mas chico que alcance ENTRE LOS QUE TIENE
                       ASIGNADOS EL TECNICO
    cable              se pregunta si uso el de la empresa, y cuantos metros
    maximo             5 puntos

EL CODIGO CALCULA, LA EMPRESA CONFIGURA. Aca se guardan los numeros y los
materiales de cada empresa; la cuenta la hace la app, sin señal, con el kit del
tecnico delante (`lib/features/ejecucion/puntos_de_tv.dart`). Lo que el tecnico
registra son consumos comunes: el servidor no sabe que salieron de aca.
================================================================================
"""
from __future__ import annotations

MAXIMO_DE_SPLITERS = 10
TOPE_DE_PUNTOS = 10


class PuntosDeTvInvalido(ValueError):
    """Lo que mando quien edita no se puede guardar. El texto es para el."""


def de_tipo(org, work_type) -> dict | None:
    """La configuracion que viaja a la app, o `None` si el tipo no tiene."""
    from campo.models import MaterialCatalogo, PuntosDeTv

    if work_type is None:
        return None
    c = PuntosDeTv.objects.filter(org=org, work_type=work_type, activo=True).first()
    if c is None or not c.conector:
        return None
    nombres = dict(MaterialCatalogo.objects.filter(org=org).values_list("codigo", "nombre"))
    return {
        "conector": {"codigo": c.conector, "nombre": nombres.get(c.conector, c.conector)},
        "conectores_por_punto": c.conectores_por_punto,
        "conectores_de_entrada": c.conectores_de_entrada,
        "maximo_de_puntos": c.maximo_de_puntos,
        "cable": ({"codigo": c.cable, "nombre": nombres.get(c.cable, c.cable)}
                  if c.cable else None),
        "spliters": [{"codigo": s["codigo"], "nombre": nombres.get(s["codigo"], s["codigo"]),
                      "salidas": s["salidas"]}
                     for s in sorted(c.spliters or [], key=lambda s: s["salidas"])],
    }


def para_el_editor(org, work_type) -> dict:
    """Lo que ve el editor de la plantilla, este activo o no."""
    from campo.models import PuntosDeTv

    c = PuntosDeTv.objects.filter(org=org, work_type=work_type).first()
    if c is None:
        return {"activo": False, "conector": "", "conectores_por_punto": 2,
                "conectores_de_entrada": 2, "maximo_de_puntos": 5, "cable": "",
                "spliters": []}
    return {"activo": c.activo, "conector": c.conector,
            "conectores_por_punto": c.conectores_por_punto,
            "conectores_de_entrada": c.conectores_de_entrada,
            "maximo_de_puntos": c.maximo_de_puntos, "cable": c.cable,
            "spliters": list(c.spliters or [])}


def _entero(valor, nombre, minimo, maximo):
    if isinstance(valor, bool):
        raise PuntosDeTvInvalido(f"{nombre} no se entiende.")
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        raise PuntosDeTvInvalido(f"{nombre} tiene que ser un número entero.")
    if not minimo <= n <= maximo:
        raise PuntosDeTvInvalido(f"{nombre} va de {minimo} a {maximo}.")
    return n


def guardar(org, work_type, datos) -> dict:
    """Guarda la configuracion de ese tipo de trabajo. Devuelve la del editor."""
    from campo.models import MaterialCatalogo, PuntosDeTv

    if not isinstance(datos, dict):
        raise PuntosDeTvInvalido("La configuración de TV no se entiende.")
    activo = bool(datos.get("activo"))
    conector = str(datos.get("conector") or "").strip()
    cable = str(datos.get("cable") or "").strip()
    por_punto = _entero(datos.get("conectores_por_punto", 2), "Los conectores por punto", 0, 10)
    entrada = _entero(datos.get("conectores_de_entrada", 2), "Los conectores de entrada", 0, 10)
    maximo = _entero(datos.get("maximo_de_puntos", 5), "El máximo de puntos", 1, TOPE_DE_PUNTOS)

    spliters_in = datos.get("spliters") or []
    if not isinstance(spliters_in, list) or len(spliters_in) > MAXIMO_DE_SPLITERS:
        raise PuntosDeTvInvalido(f"Los spliters van en una lista de hasta {MAXIMO_DE_SPLITERS}.")
    spliters, vistos = [], set()
    for i, s in enumerate(spliters_in, 1):
        if not isinstance(s, dict):
            raise PuntosDeTvInvalido(f"El spliter {i} no se entiende.")
        codigo = str(s.get("codigo") or "").strip()
        if not codigo:
            continue        # la fila que se agrego y no se lleno
        if codigo.lower() in vistos:
            raise PuntosDeTvInvalido(f"El spliter {codigo} está dos veces.")
        vistos.add(codigo.lower())
        spliters.append({"codigo": codigo,
                         "salidas": _entero(s.get("salidas"), f"Las salidas de {codigo}", 2, 32)})

    if activo and not conector:
        raise PuntosDeTvInvalido("Falta el conector coaxial.")
    catalogo = {c.lower(): c for c in
                MaterialCatalogo.objects.filter(org=org).values_list("codigo", flat=True)}
    faltan = [c for c in [conector, cable, *[s["codigo"] for s in spliters]]
              if c and c.lower() not in catalogo]
    if faltan:
        raise PuntosDeTvInvalido(
            "Estos materiales no están en el catálogo de la empresa: " + ", ".join(faltan) + ".")

    def real(c):
        return catalogo[c.lower()] if c else ""

    PuntosDeTv.objects.update_or_create(org=org, work_type=work_type, defaults={
        "activo": activo, "conector": real(conector), "cable": real(cable),
        "conectores_por_punto": por_punto, "conectores_de_entrada": entrada,
        "maximo_de_puntos": maximo,
        "spliters": [{"codigo": real(s["codigo"]), "salidas": s["salidas"]} for s in spliters],
    })
    return para_el_editor(org, work_type)
