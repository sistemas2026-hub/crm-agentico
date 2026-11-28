# -*- coding: utf-8 -*-
"""
================================================================================
 EL MATERIAL QUE SE PRECARGA EN UN TIPO DE TRABAJO
================================================================================
El usuario, el 26/11/2026, probando una instalación: «como sale el material en
esta orden debería ir material utilizado, que sea precargado. Por ejemplo,
cuando se hace una instalación se utilizan 2 conectores APC, una ONU, dos
tensores, un precinto, dos chazos y dos tornillos para anclar la ONU; las
grapas y la fibra son variadas». Y decidió: vienen puestas y el técnico las
ajusta.

NO ES UNA TABLA NUEVA. «Cuánto se suele usar de un material en un tipo de
trabajo» ya existía: `ReglaDeConsumo.cantidad_habitual`, y con ella la app ya
avisa cuando se pasa. Precargar es la misma cifra puesta de entrada. Lo único
que faltaba es decir CUÁLES de esas reglas van en la lista (`precargar`): una
regla puede existir solo para avisar, sin que el material tenga que aparecer
en cada orden.

Una línea sin cantidad (las grapas, la fibra) va en la lista vacía: el técnico
escribe cuánto usó.

Una línea puede decir de qué CAMPO de la plantilla sale (`campo`): en un
material comun, su cantidad (los metros de fibra de «Metros de fibra usados»);
en un equipo con serie, su SERIE (la ONU, de «Serial de la ONU»: el usuario,
26/11/2026, «debe llenarse solo al momento que el técnico escanea, para no
volver a escribir»).

Es de cada empresa, como todo lo que varía de una a otra (CLAUDE.md §3.3): se
carga desde la plataforma, en el editor de la plantilla.
================================================================================
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

#: Una lista para revisar en la casa, no un inventario.
MAXIMO_DE_LINEAS = 30


class MaterialHabitualInvalido(ValueError):
    """Lo que mandó quien edita no se puede guardar. El texto es para él."""


def _numero(valor):
    if valor is None:
        return None
    v = Decimal(valor)
    return int(v) if v == v.to_integral_value() else float(v)


def de_tipo(org, work_type) -> list[dict]:
    """La lista que se precarga en las órdenes de ese tipo de trabajo, en el
    orden en que se cargó. Vacía si el tipo no tiene ninguna."""
    from campo.models import ReglaDeConsumo

    if work_type is None:
        return []
    reglas = (ReglaDeConsumo.objects
              .filter(org=org, work_type=work_type, precargar=True,
                      material__activo=True)
              .select_related("material")
              .order_by("orden_en_la_lista", "created_at"))
    return [{
        "codigo": r.material.codigo,
        "nombre": r.material.nombre,
        "unidad": r.material.unidad,
        "clase": r.material.clase,
        "cantidad": _numero(r.cantidad_habitual),
        #  El campo de la plantilla de donde sale la cantidad, si sale de uno.
        "campo": r.cantidad_de_campo,
    } for r in reglas]


def _cantidad(valor, codigo):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, bool):
        raise MaterialHabitualInvalido(f"La cantidad de {codigo} no se entiende.")
    try:
        d = Decimal(str(valor))
    except InvalidOperation:
        raise MaterialHabitualInvalido(f"La cantidad de {codigo} no es un número.")
    if not d.is_finite() or d <= 0 or d > 100000:
        raise MaterialHabitualInvalido(
            f"La cantidad de {codigo} tiene que ser mayor que cero (o vacía: la escribe el técnico).")
    return d.quantize(Decimal("0.001"))


def guardar(org, work_type, lineas) -> list[dict]:
    """Reemplaza la lista del tipo de trabajo. Devuelve la que quedó.

    `lineas`: `[{"codigo": "SCAPC", "cantidad": 2}, {"codigo": "GRAPA", "cantidad": null},
    {"codigo": "DROP", "campo": "Metros de fibra usados"}]`. Con `campo`, la app
    toma la cantidad de lo que el tecnico escribio en ese campo.

    Las reglas que salen de la lista NO se borran: se les quita la marca de
    precargar. Pueden tener un máximo o una exigencia de motivo que alguien
    configuró, y eso no se pierde por sacar el material de la lista.
    """
    from campo.models import MaterialCatalogo, ReglaDeConsumo

    if not isinstance(lineas, list):
        raise MaterialHabitualInvalido("La lista de material no se entiende.")
    if len(lineas) > MAXIMO_DE_LINEAS:
        raise MaterialHabitualInvalido(f"Son más de {MAXIMO_DE_LINEAS} materiales.")

    limpias, vistos = [], set()
    for i, linea in enumerate(lineas, 1):
        if not isinstance(linea, dict):
            raise MaterialHabitualInvalido(f"La línea {i} no se entiende.")
        codigo = str(linea.get("codigo") or "").strip()
        if not codigo:
            raise MaterialHabitualInvalido(f"A la línea {i} le falta el material.")
        if codigo.lower() in vistos:
            raise MaterialHabitualInvalido(f"{codigo} está dos veces en la lista.")
        vistos.add(codigo.lower())
        campo = str(linea.get("campo") or "").strip()
        if len(campo) > 120:
            raise MaterialHabitualInvalido(f"El campo de {codigo} es demasiado largo.")
        limpias.append((codigo, _cantidad(linea.get("cantidad"), codigo), campo))

    materiales = {m.codigo.lower(): m for m in MaterialCatalogo.objects.filter(org=org)}
    faltan = [c for c, _, _ in limpias if c.lower() not in materiales]
    if faltan:
        raise MaterialHabitualInvalido(
            "Estos materiales no están en el catálogo de la empresa: " + ", ".join(faltan) + ".")

    with transaction.atomic():
        quedan = []
        for posicion, (codigo, cantidad, campo) in enumerate(limpias):
            material = materiales[codigo.lower()]
            regla, _ = ReglaDeConsumo.objects.get_or_create(
                org=org, material=material, work_type=work_type)
            regla.cantidad_habitual = cantidad
            regla.precargar = True
            regla.orden_en_la_lista = posicion
            regla.cantidad_de_campo = campo
            regla.save(update_fields=["cantidad_habitual", "precargar",
                                      "orden_en_la_lista", "cantidad_de_campo",
                                      "updated_at"])
            quedan.append(regla.id)
        (ReglaDeConsumo.objects
         .filter(org=org, work_type=work_type, precargar=True)
         .exclude(id__in=quedan)
         .update(precargar=False))
    return de_tipo(org, work_type)
