# -*- coding: utf-8 -*-
"""
Cerrar la jornada: qué se devuelve, qué falta y por qué.

LA CUENTA QUE ORDENA TODO
-------------------------
Lo que un técnico debería devolver no es un número guardado en ningún lado:

    entregado
    − consumido confirmado
    − transferido y aceptado por otro
    = esperado devolver

Se calcula igual que el saldo, y por la misma razón: un contador guardado y
una cola offline que reintenta se desincronizan en cuanto algo se reenvía, y
a partir de ahí nadie sabe cuál de los dos números es el bueno.

LA DIFERENCIA NO SE ABSORBE: SE NOMBRA
--------------------------------------
Cuando lo que vuelve no coincide con lo esperado, no hay un ajuste silencioso
que cuadre la cuenta. Hay una incidencia con su motivo, porque "faltan 3
conectores" y "se dañaron 3 al retirarlos" son hechos distintos y la empresa
necesita saber cuál de los dos tiene.

QUÉ BLOQUEA Y QUÉ NO
--------------------
Registrar hechos nunca se bloquea: eso no cambió. Lo que sí puede negarse es
**afirmar que la jornada está cerrada**, que es otra cosa — es una declaración
sobre el estado del mundo, y no puede hacerse mientras haya cosas sin resolver
que la contradicen.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from campo.models import (
    ActaDeDevolucion,
    AsignacionTrabajo,
    EntregaDeKit,
    IncidenciaDeMaterial,
    ItemDeKit,
    MovimientoDeMaterial,
    OrdenTrabajo,
    TransferenciaDeMaterial,
)
from campo.services.materiales import a_decimal, a_texto, entregado_a

CERO = Decimal("0")


class CierreBloqueado(Exception):
    """Faltan cosas por resolver antes de poder afirmar que la jornada cerró."""


def transferido_por(profile, material) -> Decimal:
    """Lo que esta persona le pasó a otra y el otro aceptó.

    Solo lo aceptado. Una transferencia pendiente no mueve nada: entre que uno
    entrega y el otro acepta hay un rato, y en ese rato el material sigue
    siendo de quien lo entregó. Descontarlo antes haría desaparecer inventario
    sin que nadie responda por él.
    """
    total = TransferenciaDeMaterial.objects.filter(
        entrega=profile,
        material=material,
        estado=TransferenciaDeMaterial.ACEPTADA,
    ).aggregate(total=Sum("cantidad"))["total"]
    return a_decimal(total)


def recibido_por_transferencia(profile, material) -> Decimal:
    """Lo que otro le pasó a esta persona y esta persona aceptó."""
    total = TransferenciaDeMaterial.objects.filter(
        recibe=profile,
        material=material,
        estado=TransferenciaDeMaterial.ACEPTADA,
    ).aggregate(total=Sum("cantidad"))["total"]
    return a_decimal(total)


def _movido(profile, material, tipo) -> Decimal:
    total = (
        MovimientoDeMaterial.objects.filter(
            profile=profile, material=material, tipo=tipo
        )
        .exclude(estado=MovimientoDeMaterial.CONFLICTO)
        .aggregate(total=Sum("cantidad"))["total"]
    )
    return a_decimal(total)


def esperado_devolver(profile, material) -> Decimal:
    """Cuánto de este material debería volver a bodega."""
    return (
        entregado_a(profile, material)
        + recibido_por_transferencia(profile, material)
        - _movido(profile, material, MovimientoDeMaterial.CONSUMO)
        - transferido_por(profile, material)
    )


def _materiales_de(profile, org):
    """Todo material que esta persona tocó: recibido, o movido sin recibir."""
    de_kit = ItemDeKit.objects.filter(
        entrega__profile=profile, entrega__org=org
    ).values_list("material_id", flat=True)
    de_movimientos = MovimientoDeMaterial.objects.filter(
        profile=profile, org=org
    ).values_list("material_id", flat=True)
    de_transferencias = TransferenciaDeMaterial.objects.filter(
        Q(entrega=profile) | Q(recibe=profile), org=org
    ).values_list("material_id", flat=True)

    ids = set(de_kit) | set(de_movimientos) | set(de_transferencias)
    from campo.models import MaterialCatalogo

    return MaterialCatalogo.objects.filter(id__in=ids).order_by("categoria", "nombre")


def conciliacion_de(profile, org):
    """Una fila por material, con la cuenta completa de la jornada."""
    filas = []
    for material in _materiales_de(profile, org):
        entregado = entregado_a(profile, material)
        recibido_transf = recibido_por_transferencia(profile, material)
        consumido = _movido(profile, material, MovimientoDeMaterial.CONSUMO)
        devuelto = _movido(profile, material, MovimientoDeMaterial.DEVOLUCION)
        transferido = transferido_por(profile, material)
        esperado = entregado + recibido_transf - consumido - transferido

        incidencias = a_decimal(
            IncidenciaDeMaterial.objects.filter(
                profile=profile, org=org, material=material
            ).aggregate(total=Sum("cantidad"))["total"]
        )

        filas.append({
            "material": material,
            "entregado": entregado,
            "recibido_por_transferencia": recibido_transf,
            "consumido": consumido,
            "transferido": transferido,
            "esperado_devolver": esperado,
            "devuelto": devuelto,
            # Lo que falta después de contar todo, incidencias incluidas. Cero
            # es lo normal; distinto de cero es lo que hay que explicar.
            "diferencia": esperado - devuelto - incidencias,
            "incidencias": incidencias,
        })
    return filas


def resumen_de_jornada(profile, org, jornada=None) -> dict:
    """Los números del día, calculados siempre igual.

    Determinista a propósito: dos llamadas seguidas sin que nada cambie tienen
    que dar lo mismo, porque este resumen es lo que alguien firma.
    """
    jornada = jornada or timezone.localdate()

    ordenes = OrdenTrabajo.objects.filter(
        org=org,
        id__in=AsignacionTrabajo.objects.filter(profile=profile).values_list(
            "orden_id", flat=True
        ),
    )
    completadas = ordenes.filter(
        estado_operativo__in=[
            OrdenTrabajo.COMPLETADA_CAMPO,
            OrdenTrabajo.CERRADA,
        ]
    ).count()
    total_ordenes = ordenes.count()

    filas = conciliacion_de(profile, org)
    con_diferencia = [f for f in filas if f["diferencia"] != CERO]

    return {
        "jornada": jornada.isoformat(),
        "ordenes": {
            "asignadas": total_ordenes,
            "completadas": completadas,
            "pendientes": total_ordenes - completadas,
        },
        "material": {
            "recibido": a_texto(sum((f["entregado"] for f in filas), CERO)),
            "consumido": a_texto(sum((f["consumido"] for f in filas), CERO)),
            "a_devolver": a_texto(sum((f["esperado_devolver"] for f in filas), CERO)),
            "devuelto": a_texto(sum((f["devuelto"] for f in filas), CERO)),
            "diferencias": len(con_diferencia),
        },
        "detalle": [
            {
                "codigo": f["material"].codigo,
                "nombre": f["material"].nombre,
                "unidad": f["material"].unidad,
                "clase": f["material"].clase,
                "entregado": a_texto(f["entregado"]),
                "consumido": a_texto(f["consumido"]),
                "transferido": a_texto(f["transferido"]),
                "esperado_devolver": a_texto(f["esperado_devolver"]),
                "devuelto": a_texto(f["devuelto"]),
                "diferencia": a_texto(f["diferencia"]),
            }
            for f in filas
        ],
    }


def series_sin_devolver(profile, org):
    """Equipos serializados que se entregaron y no volvieron ni se instalaron.

    Un equipo con número no puede quedar "en algún lado": o está instalado en
    una casa, o volvió a bodega, o alguien tiene que decir qué pasó. Por eso
    se listan uno por uno y no como una cantidad.
    """
    entregadas = set(
        ItemDeKit.objects.filter(
            entrega__profile=profile,
            entrega__org=org,
            material__clase="serializado",
        )
        .exclude(serie="")
        .values_list("serie", flat=True)
    )
    if not entregadas:
        return []

    resueltas = set(
        MovimientoDeMaterial.objects.filter(
            profile=profile, org=org, serie__in=entregadas
        )
        .exclude(estado=MovimientoDeMaterial.CONFLICTO)
        .values_list("serie", flat=True)
    )
    justificadas = set(
        IncidenciaDeMaterial.objects.filter(
            profile=profile, org=org, serie__in=entregadas
        ).values_list("serie", flat=True)
    )
    transferidas = set(
        TransferenciaDeMaterial.objects.filter(
            entrega=profile,
            org=org,
            serie__in=entregadas,
            estado=TransferenciaDeMaterial.ACEPTADA,
        ).values_list("serie", flat=True)
    )
    return sorted(entregadas - resueltas - justificadas - transferidas)


def transferencias_abiertas(profile, org):
    """Material que esta persona le pasó a otra y el otro todavía no aceptó.

    Se lista aparte de la conciliación porque no es un faltante: el material
    sigue siendo de quien lo entregó, y contarlo como devuelto sería hacerlo
    desaparecer antes de que nadie se haga cargo. Lo que hace falta es que se
    vea, para que quien cierra la jornada sepa por qué su saldo no baja.
    """
    return (
        TransferenciaDeMaterial.objects.filter(
            org=org, entrega=profile, estado=TransferenciaDeMaterial.PENDIENTE
        )
        .select_related("material", "recibe", "recibe__user")
        .order_by("-created_at")
    )


def motivos_para_no_cerrar(profile, org) -> list[str]:
    """Por qué no se puede afirmar todavía que esta jornada cerró.

    Devuelve frases, no códigos: lo que las hace útiles es que alguien las lea
    y sepa qué le falta hacer. Una lista vacía significa que se puede cerrar.
    """
    motivos = []

    pendientes_de_subir = MovimientoDeMaterial.objects.filter(
        org=org, profile=profile
    ).count()
    # Los movimientos ya están en el servidor por definición: lo que puede
    # faltar vive en el teléfono, y de eso avisa la app. Acá se mira lo que el
    # servidor sí puede saber.

    for fila in conciliacion_de(profile, org):
        if fila["diferencia"] != CERO:
            motivos.append(
                f"{fila['material'].nombre}: faltan "
                f"{a_texto(fila['diferencia'])} {fila['material'].unidad} "
                f"sin explicar."
            )

    for serie in series_sin_devolver(profile, org):
        motivos.append(
            f"El equipo con serie {serie} no se instaló ni volvió a bodega: "
            f"hay que decir dónde está."
        )

    sin_motivo = IncidenciaDeMaterial.objects.filter(
        org=org, profile=profile, motivo=""
    ).count()
    if sin_motivo:
        motivos.append(
            f"Hay {sin_motivo} diferencia(s) registradas sin explicar por qué."
        )

    sin_resolver = MovimientoDeMaterial.objects.filter(
        org=org, profile=profile, estado=MovimientoDeMaterial.CONFLICTO
    ).count()
    if sin_resolver:
        motivos.append(
            f"Hay {sin_resolver} movimiento(s) en conflicto: dos trabajos "
            f"dicen haber usado el mismo equipo."
        )

    del pendientes_de_subir
    return motivos


@transaction.atomic
def confirmar_acta(*, org, profile, jornada=None, recibida_por=None, notas=""):
    """Cierra la jornada y congela los números.

    Al confirmar, el resumen deja de calcularse y pasa a guardarse: un acta es
    lo que dos personas acordaron ese día. Si el mes que viene alguien corrige
    un movimiento viejo, el acta no puede cambiar sola y contar otra historia.
    """
    jornada = jornada or timezone.localdate()

    motivos = motivos_para_no_cerrar(profile, org)
    if motivos:
        raise CierreBloqueado(" ".join(motivos))

    acta, _ = ActaDeDevolucion.objects.get_or_create(
        org=org, profile=profile, jornada=jornada
    )
    if acta.estado == ActaDeDevolucion.CONFIRMADA:
        # Confirmar dos veces devuelve la misma acta: la de la primera vez,
        # con sus números. Recalcularla la haría cambiar después de firmada.
        return acta, False

    acta.resumen = resumen_de_jornada(profile, org, jornada)
    acta.estado = ActaDeDevolucion.CONFIRMADA
    acta.confirmada_en = timezone.now()
    acta.recibida_por = recibida_por
    acta.notas = notas
    acta.save()

    IncidenciaDeMaterial.objects.filter(
        org=org, profile=profile, acta__isnull=True
    ).update(acta=acta)

    return acta, True


@transaction.atomic
def registrar_incidencia(
    *, org, profile, material, tipo, cantidad, motivo,
    idempotency_key, serie="", evidencia=None, ocurrido_en=None,
):
    """Deja escrito por qué falta material. Idempotente, como todo lo demás.

    Exige el motivo: una diferencia sin explicación es exactamente lo que
    después nadie puede reconstruir. Es lo único que se rechaza acá, y no por
    rigor administrativo — sin esa frase, el faltante aparece en un conteo
    físico dentro de tres meses y ya no hay a quién preguntarle.
    """
    ya = IncidenciaDeMaterial.objects.filter(
        org=org, idempotency_key=idempotency_key
    ).first()
    if ya is not None:
        return ya, False

    if not (motivo or "").strip():
        raise CierreBloqueado(
            "Hay que decir qué pasó con ese material. Sin motivo, el faltante "
            "aparece en el conteo del mes que viene y ya nadie se acuerda."
        )

    campos = dict(
        org=org, profile=profile, material=material, tipo=tipo,
        cantidad=a_decimal(cantidad), serie=serie or "", motivo=motivo,
        evidencia=evidencia, idempotency_key=idempotency_key,
    )
    if ocurrido_en is not None:
        campos["ocurrido_en"] = ocurrido_en
    return IncidenciaDeMaterial.objects.create(**campos), True


@transaction.atomic
def registrar_transferencia(
    *, org, entrega, recibe, material, cantidad, idempotency_key,
    serie="", motivo="",
):
    """Propone pasarle material a otro técnico. Queda pendiente hasta que acepte."""
    ya = TransferenciaDeMaterial.objects.filter(
        org=org, idempotency_key=idempotency_key
    ).first()
    if ya is not None:
        return ya, False

    return TransferenciaDeMaterial.objects.create(
        org=org, entrega=entrega, recibe=recibe, material=material,
        cantidad=a_decimal(cantidad), serie=serie or "", motivo=motivo,
        idempotency_key=idempotency_key,
    ), True


@transaction.atomic
def resolver_transferencia(*, transferencia, acepta: bool):
    """Quien recibe dice sí o no. Recién ahí se mueve el saldo.

    Una transferencia ya resuelta no cambia de opinión: aceptar dos veces
    movería el inventario dos veces, que es justo lo que la idempotencia de
    todo este módulo existe para impedir.
    """
    if transferencia.estado != TransferenciaDeMaterial.PENDIENTE:
        return transferencia, False

    transferencia.estado = (
        TransferenciaDeMaterial.ACEPTADA if acepta
        else TransferenciaDeMaterial.RECHAZADA
    )
    transferencia.resuelta_en = timezone.now()
    transferencia.save(update_fields=["estado", "resuelta_en", "updated_at"])
    return transferencia, True
