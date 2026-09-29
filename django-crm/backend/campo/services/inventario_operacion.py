# -*- coding: utf-8 -*-
"""
Fase 2 y 3: reservas, conteo fisico, traslados, compras y valorizacion.

LAS TRES CUENTAS NUEVAS, Y NINGUNA ES UNA COLUMNA
-------------------------------------------------
    reservado(ubicacion, material)   SUM de reservas sin resolver
    libre(ubicacion, material)       existencia - reservado
    valorizacion(ubicacion)          SUM(cantidad x costo) de lo que entro

`libre` es la unica de las tres que la operacion mira todos los dias, y es la que
mas facil se convertiria en un contador guardado: "para no recalcular en cada
pantalla". No se guarda, y la guarda de test_inventario_una_sola_verdad.py lo
impide.

EL CONTEO NO CORRIGE: PRODUCE UN AJUSTE
---------------------------------------
"El sistema dice 50 y tengo 48" no es un error del sistema: es un hecho nuevo que
alguien tiene que explicar. Cerrar un conteo escribe un AJUSTE por cada diferencia
--con su motivo y su responsable-- y deja la diferencia visible. Un conteo que
sobreescribiera el saldo perderia lo unico interesante que tiene.

EL COSTO NO SE PROPAGA A LAS SALIDAS
------------------------------------
Entra con la compra y se queda en el movimiento de entrada. El costo de lo que
sale se calcula por promedio ponderado sobre lo que entro; copiarlo a cada consumo
seria guardar un derivado. Y el promedio se declara: no es FIFO ni LIFO, y decirlo
importa porque los tres dan numeros distintos sobre los mismos datos.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from campo.inventario_operacion import (
    Compra,
    ConteoFisico,
    LineaDeConteo,
    ReservaDeMaterial,
)
from campo.models import MaterialCatalogo, MovimientoDeMaterial
from campo.services.inventario import (
    CERO,
    PRECISION,
    DespachoInvalido,
    _clave,
    _mover_activo,
    activo_de,
    existencia,
)


class ReservaInvalida(Exception):
    """Lo que se niega antes de comprometer material que no hay."""


class ConteoInvalido(Exception):
    """Lo que se niega antes de escribir ajustes."""


# ---------------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------------

def reservado(ubicacion, material) -> Decimal:
    """Cuanto de este material esta comprometido y todavia no salio."""
    total = (
        ReservaDeMaterial.objects.filter(
            ubicacion=ubicacion, material=material, resuelta_en__isnull=True
        ).aggregate(total=Sum("cantidad"))["total"]
    )
    return Decimal(total) if total is not None else CERO


def libre(ubicacion, material) -> Decimal:
    """Lo que se puede prometer hoy: lo que hay menos lo comprometido.

    Es la pregunta que la operacion hace de verdad. "Hay cien ONT" no sirve para
    decidir si se puede aceptar la instalacion de manana; "quedan setenta libres",
    si.

    Puede dar negativo si alguien reservo mas de lo que hay --y que pueda es el
    punto, igual que con la existencia: un negativo aca significa que se prometio
    material que no existe, y eso hay que verlo antes de que un tecnico viaje.
    """
    return existencia(ubicacion, material) - reservado(ubicacion, material)


@transaction.atomic
def reservar(*, org, ubicacion, material, cantidad=None, serie="", orden=None,
             reservada_por=None, vence_en=None, motivo=""):
    """Compromete material para un trabajo que todavia no salio.

    SE VALIDA ANTES, y por el mismo motivo que el despacho: reservar no es un
    hecho que ya ocurrio en la calle. Es una promesa, y una promesa que no se
    puede cumplir es peor que no hacerla -- el tecnico se entera en la bodega.
    """
    serie = (serie or "").strip()
    cant = Decimal("1") if serie else Decimal(str(cantidad or 0))
    if cant <= CERO:
        raise ReservaInvalida("Una reserva sin cantidad no reserva nada.")

    if serie:
        # Una serie reservada esta reservada una vez. El constraint lo garantiza;
        # esto da el mensaje util antes de que Postgres tire IntegrityError.
        ya = ReservaDeMaterial.objects.filter(
            org=org, material=material, serie=serie, resuelta_en__isnull=True
        ).first()
        if ya is not None:
            raise ReservaInvalida(
                f"La serie {serie} ya esta reservada"
                + (f" para la orden {ya.orden_id}." if ya.orden_id else ".")
            )

    disponible = libre(ubicacion, material)
    if cant > disponible:
        raise ReservaInvalida(
            f"No alcanza: en '{ubicacion.nombre}' quedan {disponible} libres de "
            f"{material.codigo} y se piden {cant}. Hay "
            f"{existencia(ubicacion, material)} en total, "
            f"{reservado(ubicacion, material)} ya comprometidos."
        )

    return ReservaDeMaterial.objects.create(
        org=org, ubicacion=ubicacion, material=material, cantidad=cant,
        serie=serie, orden=orden, reservada_por=reservada_por,
        vence_en=vence_en, motivo=motivo,
    )


@transaction.atomic
def liberar(reserva, *, motivo="", desenlace=ReservaDeMaterial.LIBERADA,
            movimiento=None):
    """Una reserva deja de estar activa. La fila NO se borra.

    Marcar en vez de borrar es lo que permite contestar "por que faltaron ONT el
    martes": las reservas liberadas de ese dia siguen ahi, con quien las hizo y
    por que se cayeron.
    """
    if reserva.resuelta_en is not None:
        return reserva
    reserva.resuelta_en = timezone.now()
    reserva.desenlace = desenlace
    reserva.movimiento = movimiento
    if motivo:
        reserva.motivo = (reserva.motivo + "\n" + motivo).strip()
    reserva.save(update_fields=["resuelta_en", "desenlace", "movimiento",
                                "motivo", "updated_at"])
    return reserva


def vencer_reservas(org) -> list:
    """Las reservas pasadas de plazo dejan de bloquear material.

    Sin esto una orden que se cayo deja material comprometido para siempre, y el
    que la reservo ya se fue a su casa. Es el mismo criterio que T20 del proyecto
    aplica a las acciones pendientes: un plazo vencido es un desenlace, no un
    limbo.

    NO libera las que no tienen plazo: una reserva sin `vence_en` es una decision
    de quien la hizo, y vencerla por una regla que nadie declaro seria romper una
    promesa por cuenta propia.
    """
    ahora = timezone.now()
    vencidas = []
    for r in ReservaDeMaterial.objects.filter(
        org=org, resuelta_en__isnull=True, vence_en__lt=ahora
    ):
        vencidas.append(liberar(
            r, desenlace=ReservaDeMaterial.VENCIDA,
            motivo=f"Vencio el plazo ({r.vence_en.isoformat()}) sin despacharse.",
        ))
    return vencidas


def reservas_de(ubicacion, *, solo_activas: bool = True) -> list[dict]:
    """Que hay comprometido en esta ubicacion, y para que."""
    qs = ReservaDeMaterial.objects.filter(ubicacion=ubicacion).select_related(
        "material", "orden"
    )
    if solo_activas:
        qs = qs.filter(resuelta_en__isnull=True)
    return [{
        "id": str(r.id),
        "material": r.material.codigo,
        "nombre": r.material.nombre,
        "cantidad": str(r.cantidad.quantize(PRECISION)),
        "serie": r.serie,
        "orden": str(r.orden_id) if r.orden_id else None,
        "vence_en": r.vence_en.isoformat() if r.vence_en else None,
        "activa": r.activa,
        "desenlace": r.desenlace,
    } for r in qs]


# ---------------------------------------------------------------------------
# Traslados entre ubicaciones internas
# ---------------------------------------------------------------------------

@transaction.atomic
def trasladar(*, org, ubicacion_origen, ubicacion_destino, lineas,
              profile=None, motivo=""):
    """Bodega -> bodega, o bodega -> vehiculo. El material cambia de sitio.

    Es el movimiento mas simple de todos y el que hace util tener mas de una
    bodega: sin traslado, dos bodegas son dos sistemas separados.

    Se valida igual que un despacho --una serie no puede salir de donde no
    esta-- porque tampoco ocurrio todavia.
    """
    if ubicacion_origen is None or ubicacion_destino is None:
        raise DespachoInvalido("Un traslado necesita origen y destino.")
    if ubicacion_origen.id == ubicacion_destino.id:
        raise DespachoInvalido(
            "El origen y el destino son la misma ubicacion: eso no es un "
            "traslado."
        )

    movimientos = []
    for i, linea in enumerate(lineas):
        material = linea["material"]
        serie = (linea.get("serie") or "").strip()
        cant = Decimal("1") if serie else Decimal(str(linea.get("cantidad") or 0))
        if cant <= CERO:
            raise DespachoInvalido(
                f"La linea {i + 1} ({material.codigo}) no dice cuanto se traslada."
            )
        if serie:
            from campo.services.inventario import _comprobar_serie_libre
            _comprobar_serie_libre(org, material, serie, ubicacion_origen)

        mov = MovimientoDeMaterial.objects.create(
            org=org, profile=profile, material=material,
            tipo=MovimientoDeMaterial.TRASLADO,
            cantidad=cant, serie=serie,
            ubicacion_origen=ubicacion_origen,
            ubicacion_destino=ubicacion_destino,
            idempotency_key=_clave("traslado", org.id, ubicacion_origen.id,
                                   ubicacion_destino.id, i, material.id,
                                   serie or cant),
            motivo=motivo,
        )
        movimientos.append(mov)
        if serie:
            _mover_activo(activo_de(org, material, serie), ubicacion_destino, mov)
    return movimientos


# ---------------------------------------------------------------------------
# Conteo fisico
# ---------------------------------------------------------------------------

@transaction.atomic
def abrir_conteo(*, org, ubicacion, contado_por=None, notas=""):
    """Empieza un conteo. Uno por ubicacion a la vez."""
    ya = ConteoFisico.objects.filter(
        org=org, ubicacion=ubicacion, estado=ConteoFisico.BORRADOR
    ).first()
    if ya is not None:
        raise ConteoInvalido(
            f"Ya hay un conteo abierto de '{ubicacion.nombre}' desde "
            f"{ya.iniciado_en.date()}. Cerralo o descartalo antes de abrir otro: "
            f"dos conteos abiertos producen dos verdades sobre lo mismo."
        )
    return ConteoFisico.objects.create(
        org=org, ubicacion=ubicacion, contado_por=contado_por, notas=notas
    )


def anotar_conteo(conteo, *, material, cantidad, motivo=""):
    """Lo que se conto de un material. Se puede corregir mientras es borrador."""
    if conteo.estado != ConteoFisico.BORRADOR:
        raise ConteoInvalido(
            "Este conteo esta cerrado: sus numeros ya produjeron ajustes y "
            "cambiarlos ahora reescribiria la historia. Abri uno nuevo."
        )
    linea, _ = LineaDeConteo.objects.update_or_create(
        conteo=conteo, material=material,
        defaults={"cantidad_contada": Decimal(str(cantidad)), "motivo": motivo},
    )
    return linea


@transaction.atomic
def cerrar_conteo(conteo, *, profile=None):
    """Congela las diferencias y escribe un AJUSTE por cada una.

    Devuelve `(lineas, ajustes)`. Una linea que cuadra no genera movimiento, y eso
    se ve en que su `ajuste` queda vacio: el conteo dice tambien lo que estaba
    bien, que es informacion.
    """
    if conteo.estado != ConteoFisico.BORRADOR:
        raise ConteoInvalido("Este conteo ya estaba cerrado.")

    lineas = list(conteo.lineas.select_related("material"))
    if not lineas:
        raise ConteoInvalido(
            "Un conteo sin lineas no se puede cerrar: no dice nada sobre la "
            "bodega, y cerrarlo dejaria constancia de que se conto cuando no."
        )

    ajustes = []
    for linea in lineas:
        material = linea.material
        # Se congela lo que el sistema decia AHORA, no lo que dira despues. Si se
        # recalculara al leer, la diferencia cambiaria sola con cada movimiento
        # posterior y el conteo dejaria de ser un hecho.
        segun_sistema = existencia(conteo.ubicacion, material)
        linea.existencia_sistema = segun_sistema
        diferencia = linea.cantidad_contada - segun_sistema

        if diferencia != CERO:
            # El ajuste entra al libro como cualquier movimiento, con direccion.
            # Sobra material -> entra a la ubicacion; falta -> sale de ella.
            entra = diferencia > CERO
            ajuste = MovimientoDeMaterial.objects.create(
                org=conteo.org,
                profile=profile or conteo.contado_por,
                material=material,
                tipo=MovimientoDeMaterial.AJUSTE,
                cantidad=abs(diferencia),
                ubicacion_origen=None if entra else conteo.ubicacion,
                ubicacion_destino=conteo.ubicacion if entra else None,
                idempotency_key=_clave("conteo", conteo.org_id, conteo.id,
                                       material.id),
                motivo=(
                    f"Conteo fisico del {conteo.iniciado_en.date()}: contado "
                    f"{linea.cantidad_contada}, el sistema decia {segun_sistema}. "
                    f"Diferencia {diferencia}."
                    + (f" Motivo de quien conto: {linea.motivo}"
                       if linea.motivo else
                       " SIN MOTIVO DECLARADO: la diferencia quedo sin explicar.")
                ),
            )
            linea.ajuste = ajuste
            ajustes.append(ajuste)

        linea.save(update_fields=["existencia_sistema", "ajuste", "updated_at"])

    conteo.estado = ConteoFisico.CERRADO
    conteo.cerrado_en = timezone.now()
    conteo.save(update_fields=["estado", "cerrado_en", "updated_at"])
    return lineas, ajustes


# ---------------------------------------------------------------------------
# FASE 3 -- compras y costo
# ---------------------------------------------------------------------------

@transaction.atomic
def registrar_compra(*, org, ubicacion_destino, lineas, proveedor=None,
                     referencia="", moneda="COP", recibida_por=None, notas=""):
    """Un lote que llego: crea la compra y una ENTRADA por linea, con su costo.

    `lineas`: [{material, cantidad, serie, costo_unitario}]

    Es la unica via por la que entra un costo al sistema. Y es una `entrada` del
    libro comun, no un movimiento de otra clase: la existencia sigue saliendo de
    la misma resta.
    """
    if ubicacion_destino is None:
        raise DespachoInvalido("Una compra necesita decir a que bodega entra.")
    if not lineas:
        raise DespachoInvalido("Una compra sin lineas no es una compra.")

    compra = Compra.objects.create(
        org=org, proveedor=proveedor, referencia=referencia, moneda=moneda,
        recibida_por=recibida_por, notas=notas,
    )

    movimientos = []
    for i, linea in enumerate(lineas):
        material = linea["material"]
        serie = (linea.get("serie") or "").strip()
        cant = Decimal("1") if serie else Decimal(str(linea.get("cantidad") or 0))
        if cant <= CERO:
            raise DespachoInvalido(
                f"La linea {i + 1} ({material.codigo}) no dice cuanto llego."
            )
        costo = linea.get("costo_unitario")
        mov = MovimientoDeMaterial.objects.create(
            org=org, profile=recibida_por, material=material,
            tipo=MovimientoDeMaterial.ENTRADA,
            cantidad=cant, serie=serie,
            ubicacion_origen=None,
            ubicacion_destino=ubicacion_destino,
            costo_unitario=Decimal(str(costo)) if costo is not None else None,
            compra=compra,
            idempotency_key=_clave("compra", org.id, compra.id, i, material.id,
                                   serie or cant),
            motivo=f"Compra {referencia}" if referencia else "Compra",
        )
        movimientos.append(mov)
        if serie:
            _mover_activo(activo_de(org, material, serie), ubicacion_destino, mov)
    return compra, movimientos


def costo_promedio(org, material) -> Decimal | None:
    """Promedio PONDERADO de lo que costo este material al entrar.

    Se declara el metodo a proposito: no es FIFO ni LIFO, y los tres dan numeros
    distintos sobre los mismos datos. Elegir uno sin decirlo es la forma mas
    facil de que dos informes no cuadren y nadie sepa por que.

    Devuelve `None` cuando ninguna entrada trae costo -- que es distinto de cero.
    Cero diria que es gratis.
    """
    filas = MovimientoDeMaterial.objects.filter(
        org=org, material=material, tipo=MovimientoDeMaterial.ENTRADA,
        costo_unitario__isnull=False,
    ).values_list("cantidad", "costo_unitario")
    total_cant = CERO
    total_valor = CERO
    for cant, costo in filas:
        total_cant += cant
        total_valor += cant * costo
    if total_cant == CERO:
        return None
    return (total_valor / total_cant).quantize(Decimal("0.0001"))


def valorizacion(ubicacion) -> dict:
    """Cuanto vale lo que hay en esta ubicacion, y de que no se sabe.

    LO QUE NO SE PUEDE VALORIZAR SE NOMBRA. Un material sin costo conocido no se
    cuenta como cero: se lista aparte, con su cantidad. Un total que se come en
    silencio lo que no sabe valorizar es la forma mas rapida de que alguien tome
    una decision con un numero que parece completo y no lo es.
    """
    from campo.services.inventario import existencias_de

    total = CERO
    con_costo = []
    sin_costo = []
    for fila in existencias_de(ubicacion):
        material = MaterialCatalogo.objects.get(id=fila["material_id"])
        cant = Decimal(fila["existencia"])
        costo = costo_promedio(ubicacion.org, material)
        if costo is None:
            sin_costo.append({**fila, "costo_unitario": None, "valor": None})
            continue
        valor = (cant * costo).quantize(Decimal("0.01"))
        total += valor
        con_costo.append({**fila, "costo_unitario": str(costo), "valor": str(valor)})

    return {
        "ubicacion": {"id": str(ubicacion.id), "nombre": ubicacion.nombre},
        "total": str(total.quantize(Decimal("0.01"))),
        "materiales": con_costo,
        # Nombrado, no absorbido.
        "sin_costo_conocido": sin_costo,
        "advertencia": (
            f"{len(sin_costo)} material(es) sin costo conocido no entran en el "
            f"total." if sin_costo else ""
        ),
    }


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------

def consumo_por_material(org, *, desde=None, hasta=None) -> list[dict]:
    """En que se fue el material. Ordenado por lo que mas se consumio.

    Cuenta por `ocurrido_en` y no por `created_at`: lo que importa es cuando paso
    en la calle, no cuando llego el dato. Un movimiento sin señal puede llegar
    horas despues y agruparlo por el dia en que sincronizo pondria el consumo del
    martes en el miercoles.
    """
    qs = MovimientoDeMaterial.objects.filter(
        org=org, tipo=MovimientoDeMaterial.CONSUMO
    ).exclude(estado=MovimientoDeMaterial.CONFLICTO)
    if desde:
        qs = qs.filter(ocurrido_en__gte=desde)
    if hasta:
        qs = qs.filter(ocurrido_en__lte=hasta)

    filas = (
        qs.values("material__codigo", "material__nombre", "material__unidad")
        .annotate(total=Sum("cantidad"))
        .order_by("-total")
    )
    salida = []
    for f in filas:
        salida.append({
            "codigo": f["material__codigo"],
            "nombre": f["material__nombre"],
            "unidad": f["material__unidad"],
            "consumido": str(Decimal(f["total"]).quantize(PRECISION)),
        })
    return salida


def consumo_por_tecnico(org, *, desde=None, hasta=None) -> list[dict]:
    """Quien consumio cuanto. Para una conversacion, no para un ranking.

    Se devuelve tal cual y sin "eficiencia" calculada: dos tecnicos con distinto
    tipo de trabajo no son comparables por metros de fibra, y un numero que
    parece comparable se usa como si lo fuera.
    """
    from campo.services.inventario import nombre_de

    qs = MovimientoDeMaterial.objects.filter(
        org=org, tipo=MovimientoDeMaterial.CONSUMO, profile__isnull=False
    ).exclude(estado=MovimientoDeMaterial.CONFLICTO)
    if desde:
        qs = qs.filter(ocurrido_en__gte=desde)
    if hasta:
        qs = qs.filter(ocurrido_en__lte=hasta)

    por_persona = {}
    for mov in qs.select_related("profile__user", "material"):
        clave = str(mov.profile_id)
        entrada = por_persona.setdefault(clave, {
            "profile": clave,
            "nombre": nombre_de(mov.profile),
            "materiales": {},
        })
        m = entrada["materiales"].setdefault(mov.material.codigo, CERO)
        entrada["materiales"][mov.material.codigo] = m + mov.cantidad

    salida = []
    for entrada in por_persona.values():
        salida.append({
            "profile": entrada["profile"],
            "nombre": entrada["nombre"],
            "materiales": [
                {"codigo": c, "consumido": str(v.quantize(PRECISION))}
                for c, v in sorted(entrada["materiales"].items())
            ],
        })
    return sorted(salida, key=lambda e: e["nombre"])


def descuadres_abiertos(org) -> list[dict]:
    """Los movimientos que quedaron en descuadre o conflicto.

    Es la lista que alguien tiene que mirar, y por eso existe como consulta y no
    como un numero en un tablero: un contador de descuadres se mira una vez y se
    ignora; una lista con el material, la persona y el motivo se puede resolver.
    """
    qs = MovimientoDeMaterial.objects.filter(
        org=org,
        estado__in=(MovimientoDeMaterial.DESCUADRE, MovimientoDeMaterial.CONFLICTO),
    ).select_related("material", "profile__user").order_by("-ocurrido_en")

    from campo.services.inventario import nombre_de
    return [{
        "id": str(m.id),
        "en": m.ocurrido_en.isoformat() if m.ocurrido_en else None,
        "estado": m.estado,
        "tipo": m.tipo,
        "material": m.material.codigo,
        "cantidad": str(m.cantidad.quantize(PRECISION)),
        "serie": m.serie,
        "persona": nombre_de(m.profile) if m.profile_id else None,
        "motivo": m.motivo,
        "motivo_tecnico": m.motivo_tecnico,
    } for m in qs]
