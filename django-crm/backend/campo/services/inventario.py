# -*- coding: utf-8 -*-
"""
El inventario: existencias, despacho y recepcion.

UNA SOLA FUNCION CALCULA EXISTENCIA, Y ES LA REGLA QUE ORDENA TODO
------------------------------------------------------------------
No hay columna de stock. La existencia de CUALQUIER ubicacion --una bodega, una
camioneta, la mochila de un tecnico-- sale de la misma resta:

    existencia(ubicacion, material) = SUM(destino = ubicacion)
                                    - SUM(origen  = ubicacion)

`saldo_de(tecnico)` de services/materiales.py es un caso particular de esto, no
otro calculo. Que sean dos codigos distintos es exactamente el defecto que se
evito al descartar los dos libros: el dia que difieran, nadie sabe cual de los
dos numeros es el bueno.

LO QUE SE VALIDA ANTES Y LO QUE NO
---------------------------------
`services/materiales.py` no valida para rechazar: valida para clasificar, porque
un consumo YA PASO en la calle y rechazarlo solo borraria el registro de que
paso. Este modulo tiene una excepcion y conviene entender por que no la
contradice:

    un consumo   ya paso: el conector esta ponchado  -> se clasifica
    un despacho  NO paso todavia: el material esta sobre el mostrador
                 -> es el UNICO acto del ciclo que se puede impedir a tiempo

Rechazar un despacho imposible no borra ningun hecho: evita que nazca uno falso.
Nada de lo ya ocurrido se bloquea jamas.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from campo.inventario import ActivoSerializado, UbicacionDeActivo, UbicacionInventario
from campo.models import EntregaDeKit, ItemDeKit, MaterialCatalogo, MovimientoDeMaterial

CERO = Decimal("0")

#: La precision del DecimalField de `cantidad` (3 decimales). Se cuantiza al
#: presentar porque un `Sum` devuelve el Decimal que le sale --"40" o
#: "40.000" segun los operandos-- y un formato que varia obliga a cada
#: consumidor a normalizar. Un solo formato, predecible; como mostrarlo lo
#: decide la pantalla, que ya recibe `clase` y `unidad`.
PRECISION = Decimal("0.001")

#: Los movimientos que NO cuentan para una existencia. Un conflicto por
#: definicion no ocurrio --alguien mas ya habia consumido esa serie-- y contarlo
#: descuadraria la existencia de quien no hizo nada malo. Mismo criterio que
#: `movido_por` en services/materiales.py.
_NO_CUENTAN = (MovimientoDeMaterial.CONFLICTO,)


class DespachoInvalido(Exception):
    """Lo que se niega ANTES de que el material salga de la bodega.

    Lista corta a proposito: solo lo que todavia no paso y que, si pasara,
    dejaria el inventario afirmando algo falso sobre un objeto fisico.
    """


# ---------------------------------------------------------------------------
# Existencias
# ---------------------------------------------------------------------------

def _suma(campo: str, ubicacion, material) -> Decimal:
    total = (
        MovimientoDeMaterial.objects.filter(
            **{campo: ubicacion}, material=material
        )
        .exclude(estado__in=_NO_CUENTAN)
        .aggregate(total=Sum("cantidad"))["total"]
    )
    return Decimal(total) if total is not None else CERO


def existencia(ubicacion, material) -> Decimal:
    """Cuanto de este material hay en esta ubicacion, ahora.

    Puede dar negativo, y que pueda es el punto: un negativo es justo lo que hay
    que poder ver. Taparlo con un `max(0, ...)` haria que el descuadre
    desapareciera de la pantalla sin haberse resuelto.
    """
    return _suma("ubicacion_destino", ubicacion, material) - _suma(
        "ubicacion_origen", ubicacion, material
    )


def existencias_de(ubicacion) -> list[dict]:
    """Una fila por material que haya pasado por esta ubicacion.

    Incluye los que quedaron en cero: que un material haya estado y ya no este
    es informacion, y esconderlo obliga a adivinar si nunca hubo o si se acabo.
    """
    ids = set(
        MovimientoDeMaterial.objects.filter(ubicacion_destino=ubicacion)
        .values_list("material_id", flat=True)
    ) | set(
        MovimientoDeMaterial.objects.filter(ubicacion_origen=ubicacion)
        .values_list("material_id", flat=True)
    )
    filas = []
    for material in MaterialCatalogo.objects.filter(id__in=ids):
        filas.append({
            "material_id": str(material.id),
            "codigo": material.codigo,
            "nombre": material.nombre,
            "categoria": material.categoria,
            "clase": material.clase,
            "unidad": material.unidad,
            # STRING y no Decimal: DRF serializa un Decimal como float, y un
            # float pierde precision justo donde este modulo la cuida --una
            # bobina se consume en metros con tres decimales--. Medido: 40.000
            # llegaba como 40.0 al JSON.
            "existencia": str(existencia(ubicacion, material).quantize(PRECISION)),
        })
    return sorted(filas, key=lambda f: (f["categoria"], f["nombre"]))


def ubicacion_de_tecnico(profile, org, *, crear: bool = True):
    """La custodia de una persona, que es una sola.

    Se crea al vuelo la primera vez que se le despacha algo: pedirle a alguien
    que cree la ubicacion antes de poder entregarle material seria un paso que
    no aporta y que se olvida.
    """
    existente = UbicacionInventario.objects.filter(
        org=org, tipo=UbicacionInventario.TECNICO, profile=profile
    ).first()
    if existente or not crear:
        return existente
    nombre = getattr(profile, "name", None) or getattr(profile, "id", "tecnico")
    return UbicacionInventario.objects.create(
        org=org,
        tipo=UbicacionInventario.TECNICO,
        profile=profile,
        nombre=f"Custodia de {nombre}",
    )


# ---------------------------------------------------------------------------
# Activos serializados: donde esta cada aparato
# ---------------------------------------------------------------------------

def activo_de(org, material, serie: str, *, crear: bool = True):
    """La identidad de un aparato. Se da de alta al verlo por primera vez."""
    serie = (serie or "").strip()
    if not serie:
        return None
    existente = ActivoSerializado.objects.filter(
        org=org, material=material, serie=serie
    ).first()
    if existente or not crear:
        return existente
    return ActivoSerializado.objects.create(
        org=org, material=material, serie=serie
    )


def posicion_de(activo):
    """Donde esta este activo segun el indice. Puede no tener fila todavia."""
    return UbicacionDeActivo.objects.filter(activo=activo).first()


def posicion_recalculada(activo):
    """Donde deberia estar, reconstruido DESDE EL LIBRO.

    Es la contraparte de `posicion_de`, y existe para que las dos se puedan
    comparar. Sin esta funcion, `UbicacionDeActivo` seria un contador guardado
    con otro nombre: un dato que nadie puede verificar.
    """
    ultimo = (
        MovimientoDeMaterial.objects.filter(
            org=activo.org, material=activo.material, serie=activo.serie
        )
        .exclude(estado__in=_NO_CUENTAN)
        .order_by("-ocurrido_en", "-created_at")
        .first()
    )
    if ultimo is None:
        return None, None
    # El destino del ultimo movimiento ES la posicion. `None` es una posicion
    # legitima: se consumio, se instalo o se dio de baja.
    return ultimo.ubicacion_destino, ultimo


def _mover_activo(activo, ubicacion, movimiento) -> None:
    """Actualiza el indice en la MISMA transaccion que el movimiento.

    Si esto se hiciera aparte, entre las dos escrituras existiria una ventana
    donde el libro dice una cosa y el indice otra -- y es justo la ventana que
    el indice existe para cerrar.
    """
    UbicacionDeActivo.objects.update_or_create(
        activo=activo,
        defaults={"ubicacion": ubicacion, "movimiento": movimiento},
    )


# ---------------------------------------------------------------------------
# Las tres operaciones del ciclo
# ---------------------------------------------------------------------------

def _clave(*partes) -> str:
    """Clave idempotente ESTABLE, derivada de algo durable.

    Un uuid nuevo por intento es un identificador unico, no una clave
    idempotente -- es un invariante congelado del proyecto. Por eso la clave sale
    del acta y la linea, nunca de la hora ni de un random.
    """
    return ":".join(str(p) for p in partes if p is not None)


@transaction.atomic
def registrar_entrada(*, org, material, cantidad, ubicacion_destino,
                      serie="", origen_ref="", profile=None, orden=None,
                      ocurrido_en=None):
    """Material que ENTRA al sistema: una compra, o un equipo retirado.

    Es el unico movimiento sin origen, y ese null es la frontera del sistema.
    No se inventa una ubicacion PROVEEDOR para evitarlo: ver campo/inventario.py.
    """
    if ubicacion_destino is None:
        raise DespachoInvalido("Una entrada necesita decir a que ubicacion entra.")

    serie = (serie or "").strip()
    activo = activo_de(org, material, serie) if serie else None

    datos = {"origen_ref": origen_ref} if origen_ref else {}
    extra = {"ocurrido_en": ocurrido_en} if ocurrido_en else {}
    mov = MovimientoDeMaterial.objects.create(
        org=org,
        profile=profile,
        material=material,
        orden=orden,
        tipo=MovimientoDeMaterial.ENTRADA,
        cantidad=Decimal("1") if serie else Decimal(str(cantidad)),
        serie=serie,
        ubicacion_origen=None,
        ubicacion_destino=ubicacion_destino,
        idempotency_key=_clave("entrada", org.id, material.id,
                               serie or cantidad, origen_ref or "sin-ref"),
        datos=datos,
        **extra,
    )
    if activo is not None:
        _mover_activo(activo, ubicacion_destino, mov)
    return mov


def _comprobar_serie_libre(org, material, serie, ubicacion_origen) -> None:
    """A4: una serie no puede estar en dos custodias a la vez.

    Se comprueba ANTES de escribir porque el despacho todavia no ocurrio. Y con
    `select_for_update` sobre el indice, no con un select suelto: dos despachos
    concurrentes de la misma serie llegarian los dos a la misma conclusion y los
    dos escribirian. Ahi vive la carrera.
    """
    activo = activo_de(org, material, serie, crear=False)
    if activo is None:
        # Nunca se vio esta serie. Puede entrar: alguien la esta dando de alta al
        # despacharla, que es como llega el material que nadie registro antes.
        return
    pos = UbicacionDeActivo.objects.select_for_update().filter(activo=activo).first()
    if pos is None or pos.ubicacion is None:
        return
    if ubicacion_origen is not None and pos.ubicacion_id == ubicacion_origen.id:
        return
    raise DespachoInvalido(
        "La serie " + serie + " figura en '" + pos.ubicacion.nombre + "' y no en "
        "el origen de este despacho. Un aparato no puede estar en dos manos a la "
        "vez: primero hay que registrar su devolucion."
    )


@transaction.atomic
def despachar(*, org, ubicacion_origen, profile_destino, lineas,
              despachado_por=None, acta="", notas=""):
    """Bodega -> tecnico. Deja el ACTA y los MOVIMIENTOS.

    El acta (EntregaDeKit + ItemDeKit) es el documento que dos personas firman;
    los movimientos son la verdad de la que sale la existencia. Los dos se
    escriben en la misma transaccion: un acta sin movimientos seria un papel que
    nadie puede cuadrar, y movimientos sin acta seria material sin responsable.

    `lineas`: [{material, cantidad, serie}]. Una serie, una unidad.
    """
    if ubicacion_origen is None:
        raise DespachoInvalido("Un despacho necesita decir de que bodega sale.")
    if not lineas:
        raise DespachoInvalido("Un despacho sin lineas no es un despacho.")

    destino = ubicacion_de_tecnico(profile_destino, org)
    entrega = EntregaDeKit.objects.create(
        org=org,
        profile=profile_destino,
        despachado_por=despachado_por,
        acta=acta,
        notas=notas,
    )

    movimientos = []
    for i, linea in enumerate(lineas):
        material = linea["material"]
        serie = (linea.get("serie") or "").strip()
        cantidad = Decimal("1") if serie else Decimal(str(linea.get("cantidad") or 0))
        if cantidad <= CERO:
            raise DespachoInvalido(
                "La linea " + str(i + 1) + " (" + material.codigo + ") no dice "
                "cuanto se entrega."
            )
        if material.es_serializado and not serie:
            raise DespachoInvalido(
                material.codigo + " es serializado: sin el numero de serie no se "
                "puede saber que aparato se entrego."
            )

        # LA GARANTIA, antes de escribir nada de esta linea.
        if serie:
            _comprobar_serie_libre(org, material, serie, ubicacion_origen)

        ItemDeKit.objects.create(
            entrega=entrega, material=material, cantidad=cantidad, serie=serie
        )
        mov = MovimientoDeMaterial.objects.create(
            org=org,
            profile=profile_destino,
            material=material,
            tipo=MovimientoDeMaterial.DESPACHO,
            cantidad=cantidad,
            serie=serie,
            ubicacion_origen=ubicacion_origen,
            ubicacion_destino=destino,
            idempotency_key=_clave("despacho", org.id, entrega.id, i,
                                   material.id, serie or cantidad),
            datos={"acta": acta} if acta else {},
        )
        movimientos.append(mov)
        if serie:
            _mover_activo(activo_de(org, material, serie), destino, mov)

    return entrega, movimientos


@transaction.atomic
def recibir_devolucion(*, org, profile_origen, ubicacion_destino, lineas,
                       recibida_por=None, notas=""):
    """Tecnico -> bodega. El material vuelve a existir en la bodega.

    Es lo que faltaba del ciclo: antes `saldo_de` le restaba la devolucion al
    tecnico y ahi terminaba el rastro, porque no habia bodega donde sumarla.
    """
    if ubicacion_destino is None:
        raise DespachoInvalido("Una devolucion necesita decir a que bodega vuelve.")

    origen = ubicacion_de_tecnico(profile_origen, org, crear=False)
    if origen is None:
        raise DespachoInvalido(
            "Esta persona no tiene custodia abierta: no hay nada que devolver."
        )

    movimientos = []
    for i, linea in enumerate(lineas):
        material = linea["material"]
        serie = (linea.get("serie") or "").strip()
        cantidad = Decimal("1") if serie else Decimal(str(linea.get("cantidad") or 0))
        mov = MovimientoDeMaterial.objects.create(
            org=org,
            profile=profile_origen,
            material=material,
            tipo=MovimientoDeMaterial.DEVOLUCION,
            cantidad=cantidad,
            serie=serie,
            ubicacion_origen=origen,
            ubicacion_destino=ubicacion_destino,
            idempotency_key=_clave("devolucion", org.id, origen.id, i,
                                   material.id, serie or cantidad),
            motivo=notas,
        )
        movimientos.append(mov)
        if serie:
            _mover_activo(activo_de(org, material, serie), ubicacion_destino, mov)
    return movimientos


def historia_de(org, material, serie) -> list:
    """Por donde paso este aparato, en orden. La pregunta que justifica todo.

    "Esta ONT con esta serie, quien la tuvo, donde esta, cuando salio y por que"
    -- con un solo libro es una consulta ordenada por ocurrido_en, y es la
    diferencia entre esto y un contador de conectores.
    """
    movs = (
        MovimientoDeMaterial.objects.filter(org=org, material=material, serie=serie)
        .select_related("ubicacion_origen", "ubicacion_destino")
        .order_by("ocurrido_en", "created_at")
    )
    salida = []
    for m in movs:
        salida.append({
            "en": m.ocurrido_en.isoformat() if m.ocurrido_en else None,
            "tipo": m.tipo,
            "estado": m.estado,
            "desde": m.ubicacion_origen.nombre if m.ubicacion_origen else None,
            "hacia": m.ubicacion_destino.nombre if m.ubicacion_destino else None,
            "orden": str(m.orden_id) if m.orden_id else None,
            "motivo": m.motivo or "",
        })
    return salida
