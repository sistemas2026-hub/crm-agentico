# -*- coding: utf-8 -*-
"""Que material toco esta orden de trabajo.

LA REGLA DE ESTE ARCHIVO, Y ES LA UNICA
---------------------------------------
Esto NO calcula una segunda contabilidad. Presenta movimientos que ya existen,
agrupados por lo que significan. Ni un saldo, ni una suma que compita con
`existencia(ubicacion, material)`, que sigue siendo la unica verdad del libro.

Si alguna vez hace falta un total acá, sale de sumar las filas que ya se estan
mostrando -- nunca de una columna guardada ni de un contador aparte.

POR QUE "ENTREGADO AL TECNICO" NO ES UN BLOQUE DE ESTA ORDEN
------------------------------------------------------------
`EntregaDeKit` no tiene FK a la orden, y esta bien que no la tenga: el despacho
de la mañana es a la CUSTODIA del tecnico, no a un trabajo. Con los mismos 150 m
de drop hace cinco instalaciones.

Entonces un bloque titulado "Entregado al tecnico" dentro de una orden se lee
como "entregado para ESTE trabajo", y eso seria falso. Lo unico que de verdad
esta asignado a un trabajo es una RESERVA (`ReservaDeMaterial.orden`), porque
alguien la hizo a proposito y contra esa orden.

El kit del dia se puede mostrar como contexto, pero se pide aparte y con su
propio nombre: `custodia_del_tecnico`, no `entregado`. Ver la ficha
`SPEC/objetivos/seguimiento-campo-por-ticket.md`.

QUE QUEDA FUERA, Y POR QUE
--------------------------
`IncidenciaDeMaterial` no tiene FK a la orden. Llegar a ella cruzando material y
tecnico seria inventar un vinculo que nadie registro: dos incidencias del mismo
material en el mismo dia se le colgarian a la orden equivocada.
"""

from __future__ import annotations

from campo.models import EntregaDeKit, MovimientoDeMaterial
from campo.inventario_operacion import ReservaDeMaterial


#: Los tipos que, vistos desde una orden, tienen un significado propio. El resto
#: (`ajuste`, `traslado`, `baja`, `entrada`, `despacho`) cae en "otros": son
#: correcciones de bodega que alguien ato a esta orden, y esconderlas seria peor
#: que mostrarlas sin titulo especial.
CONSUMO = MovimientoDeMaterial.CONSUMO
DEVOLUCION = MovimientoDeMaterial.DEVOLUCION


def _persona(profile) -> dict | None:
    """Quien lo hizo, sin datos que no hagan falta para leer la ficha."""
    if profile is None:
        return None
    user = getattr(profile, "user", None)
    return {
        "id": str(profile.id),
        "nombre": (getattr(user, "name", "") or getattr(user, "email", "") or "").strip(),
    }


def _linea_de_movimiento(m) -> dict:
    return {
        "id": str(m.id),
        "material": {
            "id": str(m.material_id),
            "codigo": m.material.codigo,
            "nombre": m.material.nombre,
            "unidad": m.material.unidad,
        },
        "cantidad": str(m.cantidad),
        "serie": m.serie or "",
        "tipo": m.tipo,
        # `descuadre` y `conflicto` no se ocultan: son justamente lo que alguien
        # tiene que mirar, y una pantalla que solo muestra lo que cuadra no sirve
        # para averiguar por que no cuadra.
        "estado": m.estado,
        "motivo": m.motivo or "",
        "quien": _persona(m.profile),
        "ocurrido_en": m.ocurrido_en.isoformat() if m.ocurrido_en else None,
        "registrado_en": m.created_at.isoformat() if m.created_at else None,
    }


def _linea_de_reserva(r) -> dict:
    return {
        "id": str(r.id),
        "material": {
            "id": str(r.material_id),
            "codigo": r.material.codigo,
            "nombre": r.material.nombre,
            "unidad": r.material.unidad,
        },
        "cantidad": str(r.cantidad),
        "serie": r.serie or "",
        "ubicacion": {
            "id": str(r.ubicacion_id),
            "nombre": getattr(r.ubicacion, "nombre", "") or "",
        },
        # Una reserva no se borra al consumirse: se marca. Asi la ficha puede
        # decir "se reservo y se uso" en vez de no decir nada.
        "pendiente": r.resuelta_en is None,
        "desenlace": r.desenlace or "",
        "vence_en": r.vence_en.isoformat() if r.vence_en else None,
        "resuelta_en": r.resuelta_en.isoformat() if r.resuelta_en else None,
        "quien": _persona(r.reservada_por),
    }


def materiales_de_orden(orden, *, incluir_custodia: bool = False) -> dict:
    """Los bloques de material de UNA orden.

    El aislamiento por empresa no se repite acá: la orden llega ya filtrada por
    `_obtener_orden_o_404`, y todo lo que se busca cuelga de ella. Aun asi cada
    consulta lleva `org=orden.org`, porque una FK mal escrita es mas facil de
    cometer que de notar -- y la prueba lo afirma con 0 filas.
    """
    movimientos = list(
        MovimientoDeMaterial.objects.filter(org=orden.org, orden=orden)
        .select_related("material", "profile__user")
        .order_by("ocurrido_en", "created_at")
    )

    consumido = [_linea_de_movimiento(m) for m in movimientos if m.tipo == CONSUMO]
    devuelto = [_linea_de_movimiento(m) for m in movimientos if m.tipo == DEVOLUCION]
    otros = [
        _linea_de_movimiento(m)
        for m in movimientos
        if m.tipo not in (CONSUMO, DEVOLUCION)
    ]

    reservas = list(
        ReservaDeMaterial.objects.filter(org=orden.org, orden=orden)
        .select_related("material", "ubicacion", "reservada_por__user")
        .order_by("created_at")
    )

    datos = {
        "orden_id": str(orden.id),
        "comprometido": [_linea_de_reserva(r) for r in reservas],
        "consumido": consumido,
        "devuelto": devuelto,
        "otros": otros,
        # Lo que la pantalla necesita para no dibujar cuatro bloques vacios.
        "hay_algo": bool(reservas or movimientos),
        # Un descuadre o un conflicto en esta orden merece un aviso arriba, no
        # que alguien lo encuentre leyendo fila por fila.
        "con_novedad": sum(
            1 for m in movimientos if m.estado != MovimientoDeMaterial.ACEPTADO
        ),
    }

    if incluir_custodia:
        datos["custodia_del_tecnico"] = _custodia_del_tecnico(orden)

    return datos


def _custodia_del_tecnico(orden) -> dict:
    """El kit vigente del tecnico principal. CONTEXTO, no material de la orden.

    Se devuelve bajo su propio nombre y con `es_de_esta_orden: False` escrito en
    la respuesta, para que ninguna pantalla lo presente como despachado para este
    trabajo. La aclaracion viaja en el dato y no solo en la interfaz a proposito:
    la interfaz la puede cambiar cualquiera; esto llega a quien lea la API.
    """
    asignacion = (
        orden.asignaciones.select_related("profile__user")
        .filter(es_principal=True)
        .first()
    )
    if asignacion is None:
        return {"tecnico": None, "items": [], "es_de_esta_orden": False}

    entrega = (
        EntregaDeKit.objects.filter(org=orden.org, profile=asignacion.profile)
        .prefetch_related("items__material")
        .order_by("-entregado_en")
        .first()
    )
    items = []
    if entrega is not None:
        items = [
            {
                "material": {
                    "id": str(i.material_id),
                    "codigo": i.material.codigo,
                    "nombre": i.material.nombre,
                    "unidad": i.material.unidad,
                },
                "cantidad": str(i.cantidad),
                "serie": i.serie or "",
            }
            for i in entrega.items.all()
        ]

    return {
        "tecnico": _persona(asignacion.profile),
        "acta": getattr(entrega, "acta", "") or "",
        "entregado_en": (
            entrega.entregado_en.isoformat()
            if entrega is not None and entrega.entregado_en
            else None
        ),
        "items": items,
        #: Lo dice el dato, no solo la pantalla.
        "es_de_esta_orden": False,
    }
