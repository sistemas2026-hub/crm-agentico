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
    ReglaDeConsumo,
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


class ConsumoInvalido(Exception):
    """Lo que se rechaza ANTES de registrar nada.

    Es una lista corta a proposito. Casi todo lo que llega ya paso en la calle
    y se guarda aunque no cuadre; esto es para lo que no se puede interpretar
    como un hecho: un consumo que no dice en que trabajo se uso, o un equipo
    serializado sin su numero. Guardarlos seria guardar una fila que despues
    nadie puede explicar.
    """


#: Los tipos que pueden existir sin una orden de trabajo.
#:
#: Un consumo SIEMPRE pertenece a un trabajo: es la unica forma de saber
#: despues en que se fue el material, y sin eso el inventario cuadra pero no
#: explica nada. Devolver a bodega y ajustar por conteo, en cambio, son actos
#: de jornada y no de trabajo.
#:
#: Si alguna empresa necesita registrar consumo sin orden -- material gastado
#: en el taller, por ejemplo -- la salida es agregar un tipo explicito a este
#: conjunto, no aflojar la regla del consumo.
TIPOS_SIN_ORDEN = frozenset({
    MovimientoDeMaterial.DEVOLUCION,
    MovimientoDeMaterial.AJUSTE,
})


def exigir_origen(*, tipo, orden, material, serie) -> None:
    """Se niega a registrar lo que despues no se podria explicar."""
    if tipo not in TIPOS_SIN_ORDEN and orden is None:
        raise ConsumoInvalido(
            "Un consumo tiene que decir en que trabajo se uso el material. "
            "Para devolver a bodega o ajustar por conteo existen los tipos "
            "'devolucion' y 'ajuste', que no necesitan orden."
        )

    if material.es_serializado and tipo == MovimientoDeMaterial.CONSUMO:
        if not (serie or "").strip():
            raise ConsumoInvalido(
                f"{material.nombre} es un equipo con numero de serie: sin el "
                f"numero no se puede saber cual se instalo, ni encontrarlo "
                f"despues si el cliente reclama."
            )


def regla_para(*, org, material, orden):
    """La regla que aplica, de la mas concreta a la mas general.

    Gana la del tipo de trabajo sobre la general: cambiar una ONT gasta
    distinto que instalar desde cero, y quien configuro la regla especifica lo
    hizo para que mandara.
    """
    work_type_id = None
    if orden is not None and orden.tipo_trabajo_version_id:
        work_type_id = orden.tipo_trabajo_version.work_type_id

    reglas = ReglaDeConsumo.objects.filter(org=org, material=material)
    if work_type_id:
        especifica = reglas.filter(work_type_id=work_type_id).first()
        if especifica is not None:
            return especifica
    return reglas.filter(work_type__isnull=True).first()


def evaluar_cantidad(*, org, material, orden, cantidad, motivo_tecnico=""):
    """Que tiene que saber quien registra este consumo.

    Devuelve ``(avisos, exige_motivo, bloquea)``. Nada de esto rechaza por su
    cuenta: lo habitual es una referencia, no un limite, y el material ya se
    gasto cuando el telefono lo informa. Bloquear de verdad solo ocurre si la
    empresa lo pidio con `bloquea_sobre_maximo`.
    """
    regla = regla_para(org=org, material=material, orden=orden)
    if regla is None:
        return [], False, False

    avisos = []
    exige_motivo = False
    bloquea = False

    habitual = regla.cantidad_habitual
    if habitual is not None and cantidad > habitual:
        avisos.append(
            f"Cantidad superior a lo habitual: se suelen usar {a_texto(habitual)} "
            f"{material.unidad} y se registraron {a_texto(cantidad)}."
        )
        if regla.exige_motivo_sobre_habitual and not (motivo_tecnico or "").strip():
            exige_motivo = True

    if regla.maximo is not None and cantidad > regla.maximo:
        avisos.append(
            f"Por encima del maximo configurado ({a_texto(regla.maximo)} "
            f"{material.unidad})."
        )
        bloquea = regla.bloquea_sobre_maximo

    return avisos, exige_motivo, bloquea


def a_texto(valor) -> str:
    """Un decimal sin ceros de mas, para escribirlo en un aviso."""
    if valor is None:
        return "0"
    return format(Decimal(str(valor)).normalize(), "f")


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
    motivo_tecnico="",
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

    # Lo que no se puede interpretar como un hecho no se guarda.
    exigir_origen(tipo=tipo, orden=orden, material=material, serie=serie)

    # Y lo que la empresa configuró sobre cantidades. Solo rechaza si alguien
    # encendió `bloquea_sobre_maximo`; el resto son avisos que viajan de vuelta.
    avisos, exige_motivo, bloquea = evaluar_cantidad(
        org=org,
        material=material,
        orden=orden,
        cantidad=cantidad,
        motivo_tecnico=motivo_tecnico,
    )
    if bloquea:
        raise ConsumoInvalido(
            "Esta empresa no permite registrar esta cantidad: "
            + " ".join(avisos)
        )
    if exige_motivo:
        raise ConsumoInvalido(
            "Hay que escribir por qué se usó más de lo habitual: "
            + " ".join(avisos)
        )

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
        motivo_tecnico=motivo_tecnico or "",
        datos={**(datos or {}), **({"avisos": avisos} if avisos else {})},
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
