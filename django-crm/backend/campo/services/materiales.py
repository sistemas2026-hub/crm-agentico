# -*- coding: utf-8 -*-
"""
La custodia de materiales de un técnico: qué tiene, qué gastó, qué debe.

LA REGLA QUE ORDENA TODO
------------------------
Un movimiento de material **es un hecho que ya ocurrió en la calle**, no una
solicitud que el servidor pueda aprobar o negar. Cuando el teléfono lo manda,
el conector ya está ponchado y los metros de fibra ya no están en la bobina.

Por eso este módulo no valida para rechazar: valida para **clasificar**. Un
consumo que deja el saldo en negativo entra igual y queda marcado como
descuadre, porque rechazarlo no devolvería el material a la camioneta — solo
borraría el único registro de que se usó, y dejaría al técnico explicando de
memoria a fin de mes.

La única excepción es una serie que otro ya consumió: dos técnicos no pueden
haber instalado la misma ONT. Ahí sí hay un error de hecho, y el segundo
movimiento entra como conflicto para que alguien lo mire.

EL SALDO SE CALCULA, NO SE GUARDA
---------------------------------
No hay columna de "disponible". El saldo sale de sumar las entregas y restar
los movimientos, siempre. Un contador guardado y un movimiento que llega ocho
horas tarde —que es el caso normal de una cuadrilla sin señal— se desincronizan
en cuanto alguien reintenta, y a partir de ahí nadie sabe cuál de los dos
números es el bueno. Sumar es barato; explicar un contador que miente, no.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum

from campo.models import (
    EntregaDeKit,
    ItemDeKit,
    MaterialCatalogo,
    MovimientoDeMaterial,
)

CERO = Decimal("0")


def a_decimal(valor) -> Decimal:
    """Lo que venga del teléfono, como número. Nunca lanza."""
    if valor is None or valor == "":
        return CERO
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return CERO


def entregado_a(profile, material) -> Decimal:
    """Cuánto de este material se le entregó a esta persona, en total."""
    total = ItemDeKit.objects.filter(
        entrega__profile=profile, material=material
    ).aggregate(total=Sum("cantidad"))["total"]
    return a_decimal(total)


def movido_por(profile, material, tipo) -> Decimal:
    """Cuánto movió esta persona de este material, por tipo de movimiento.

    Los movimientos en conflicto NO suman: por definición no ocurrieron —
    alguien más ya había consumido esa serie— y contarlos descuadraría el
    saldo de quien no hizo nada malo.
    """
    total = (
        MovimientoDeMaterial.objects.filter(
            profile=profile, material=material, tipo=tipo
        )
        .exclude(estado=MovimientoDeMaterial.CONFLICTO)
        .aggregate(total=Sum("cantidad"))["total"]
    )
    return a_decimal(total)


def saldo_de(profile, material) -> Decimal:
    """Lo que esta persona debería tener encima de este material.

    Puede dar negativo, y que pueda es el punto: un negativo es justamente lo
    que hay que poder ver. Taparlo con un `max(0, ...)` haría que el descuadre
    desapareciera de la pantalla sin haberse resuelto.
    """
    entregado = entregado_a(profile, material)
    consumido = movido_por(profile, material, MovimientoDeMaterial.CONSUMO)
    devuelto = movido_por(profile, material, MovimientoDeMaterial.DEVOLUCION)
    ajustado = movido_por(profile, material, MovimientoDeMaterial.AJUSTE)
    return entregado - consumido - devuelto + ajustado


def _serie_ya_consumida(org, material, serie) -> bool:
    if not serie:
        return False
    return MovimientoDeMaterial.objects.filter(
        org=org,
        material=material,
        serie=serie,
        tipo=MovimientoDeMaterial.CONSUMO,
        estado=MovimientoDeMaterial.ACEPTADO,
    ).exists()


def clasificar(*, org, profile, material, tipo, cantidad, serie="") -> tuple[str, str]:
    """Con qué estado entra este movimiento, y por qué. No escribe nada.

    Devuelve ``(estado, motivo)``. El motivo va en palabras porque alguien en
    la oficina lo va a leer para decidir qué hacer, y "estado=2" no le dice
    nada a esa persona.
    """
    if serie and tipo == MovimientoDeMaterial.CONSUMO:
        if _serie_ya_consumida(org, material, serie):
            return (
                MovimientoDeMaterial.CONFLICTO,
                f"La serie {serie} ya figura instalada por otro movimiento. "
                f"Dos equipos no pueden tener el mismo número: hay que revisar "
                f"cuál de los dos trabajos la lleva de verdad.",
            )

    if tipo == MovimientoDeMaterial.CONSUMO:
        disponible = saldo_de(profile, material)
        if cantidad > disponible:
            faltante = cantidad - disponible
            return (
                MovimientoDeMaterial.DESCUADRE,
                f"Se registraron {cantidad} {material.unidad} y según el kit "
                f"había {disponible}. Faltan {faltante}. El consumo se guarda "
                f"igual —ya ocurrió— pero el kit no cuadra: puede ser material "
                f"que se entregó sin acta.",
            )

    return (MovimientoDeMaterial.ACEPTADO, "")


@transaction.atomic
def registrar_movimiento(
    *,
    org,
    profile,
    material,
    tipo,
    cantidad,
    idempotency_key,
    serie="",
    orden=None,
    ocurrido_en=None,
    datos=None,
) -> tuple[MovimientoDeMaterial, bool]:
    """Guarda un movimiento. Devuelve ``(movimiento, era_nuevo)``.

    Idempotente por ``idempotency_key``: una cola offline reintenta, y el
    segundo intento tiene que devolver el mismo movimiento en vez de descontar
    dos veces. Esa es la diferencia entre un reintento y un consumo nuevo, y
    solo el teléfono sabe cuál de los dos es — por eso la clave la pone él.
    """
    ya = MovimientoDeMaterial.objects.filter(
        org=org, idempotency_key=idempotency_key
    ).first()
    if ya is not None:
        return ya, False

    cantidad = a_decimal(cantidad)
    if not material.admite_fraccion:
        # Un conector y medio no existe. Se trunca hacia abajo en vez de
        # redondear: inventar media unidad de más es peor que perderla.
        cantidad = cantidad.to_integral_value(rounding="ROUND_DOWN")

    estado, motivo = clasificar(
        org=org,
        profile=profile,
        material=material,
        tipo=tipo,
        cantidad=cantidad,
        serie=serie,
    )

    campos = dict(
        org=org,
        profile=profile,
        material=material,
        orden=orden,
        tipo=tipo,
        cantidad=cantidad,
        serie=serie or "",
        estado=estado,
        motivo=motivo,
        idempotency_key=idempotency_key,
        datos=datos or {},
    )
    # Solo se manda si el telefono dijo cuando fue. Pasar None explicito
    # anularia el default del modelo y dejaria la columna en nulo.
    if ocurrido_en is not None:
        campos["ocurrido_en"] = ocurrido_en

    movimiento = MovimientoDeMaterial.objects.create(**campos)
    return movimiento, True


def kit_de(profile, org):
    """Lo que esta persona tiene a cargo, listo para la pantalla.

    Una fila por material entregado, con su saldo y lo que se movió. Se arma
    acá y no en el serializador porque la misma cuenta la necesitan la app, el
    cierre de jornada y la vista de la oficina: tres lugares que no pueden
    llegar a tres números distintos.
    """
    entregas = EntregaDeKit.objects.filter(profile=profile, org=org)
    items = (
        ItemDeKit.objects.filter(entrega__in=entregas)
        .select_related("material", "entrega")
        .order_by("material__categoria", "material__nombre")
    )

    por_material: dict[int, dict] = {}
    for item in items:
        fila = por_material.setdefault(
            item.material_id,
            {
                "material": item.material,
                "recibido": CERO,
                "series": [],
                "acta": item.entrega.acta,
                "entregado_en": item.entrega.entregado_en,
            },
        )
        fila["recibido"] += a_decimal(item.cantidad)
        if item.serie:
            fila["series"].append(item.serie)

    filas = []
    for datos in por_material.values():
        material = datos["material"]
        consumido = movido_por(profile, material, MovimientoDeMaterial.CONSUMO)
        devuelto = movido_por(profile, material, MovimientoDeMaterial.DEVOLUCION)
        filas.append(
            {
                **datos,
                "consumido": consumido,
                "devuelto": devuelto,
                "disponible": saldo_de(profile, material),
            }
        )
    return filas


def materiales_sin_cuadrar(profile, org):
    """Los movimientos que alguien tiene que mirar antes de cerrar la jornada.

    Existe para que el descuadre no se quede escondido en una tabla: si se
    acepta un consumo que no cuadra, hay que poder listarlo después. Aceptar
    sin dejar rastro sería peor que rechazar.
    """
    return (
        MovimientoDeMaterial.objects.filter(org=org, profile=profile)
        .exclude(estado=MovimientoDeMaterial.ACEPTADO)
        .select_related("material", "orden")
        .order_by("-ocurrido_en")
    )
