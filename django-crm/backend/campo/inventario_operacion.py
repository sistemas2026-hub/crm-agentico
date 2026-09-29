# -*- coding: utf-8 -*-
"""
Fase 2 y 3 del inventario: operacion y gestion.

QUE ENTRA ACA Y POR QUE ESTA SEPARADO DE inventario.py
------------------------------------------------------
`inventario.py` tiene el nucleo de la custodia: donde puede estar el material, la
identidad de un aparato y donde esta ahora. Eso es lo que hace falta para que el
ciclo fisico cierre, y no depende de nada de este archivo.

Aca viven las dos capas que se apoyan encima:

    Fase 2, operacion    reservas · conteo fisico · traslados
    Fase 3, gestion      proveedores · compras · costos

Estan juntas en un modulo y separadas del nucleo a proposito: si alguna vez hay
que apagar la gestion --un ISP chico que no quiere llevar costos-- se apaga esto
sin tocar la custodia. Al reves no: la gestion no sirve sin saber donde esta el
material.

LA ADVERTENCIA QUE ESTE ARCHIVO NO PUEDE BORRAR
-----------------------------------------------
El brief de diseno dejo la Fase 3 explicitamente FUERA, con este motivo: "es el
modo de fallar de este trabajo. Volverse un ERP y perder la filosofia que ya esta
bien resuelta". Se construye por decision explicita del usuario el 28/09/2026, y
la advertencia queda escrita porque sigue siendo cierta: cada cosa que se agregue
aca tiene que respetar las mismas reglas que el nucleo --nada que se pueda
calcular se guarda, nada se edita, lo que falta se nombra-- o el modulo se
convierte en lo que el brief temia.

NINGUN CONTADOR, TAMPOCO ACA
----------------------------
  reservado(ubicacion, material)   = SUM de reservas sin resolver
  contado vs existencia            = la diferencia PRODUCE un ajuste, no la tapa
  valorizacion(ubicacion)          = SUM(cantidad x costo) sobre los movimientos

Ninguna de las tres es una columna. Una reserva no se borra al consumirse: se
marca CUANDO dejo de estar activa y con que movimiento, asi que la historia queda
y el numero sigue saliendo de una suma.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from common.base import BaseModel
from common.models import Org, Profile


# =============================================================================
# FASE 2 -- RESERVAS
# =============================================================================

class ReservaDeMaterial(BaseModel):
    """Material comprometido para un trabajo que todavia no salio.

    PARA QUE SIRVE, en una frase de la operacion
    -------------------------------------------
    Manana hay veinte instalaciones y hay cien ONT en bodega. La pregunta no es
    cuantas hay: es cuantas quedan LIBRES despues de lo ya comprometido. Sin esto,
    dos despachadores prometen el mismo equipo y el segundo tecnico llega a la
    bodega y no esta.

    POR QUE NO ES UN MOVIMIENTO
    ---------------------------
    Porque el material NO se movio: sigue en la bodega y alguien puede verlo ahi.
    Meterlo al libro de movimientos como si hubiera salido haria que la existencia
    mintiera sobre lo que hay fisicamente, que es justo lo que ese libro promete.

    POR QUE NO ES UN CONTADOR, aunque sea una tabla
    ----------------------------------------------
    Una reserva es un HECHO con fecha: se comprometio tanto, para tal orden. No se
    edita ni se borra al consumirse -- se marca `resuelta_en` y se guarda el
    movimiento que la consumio. Asi `reservado()` sigue siendo una suma sobre las
    que no tienen esa marca, y la historia queda entera:

        reservado(ubicacion, material) = SUM(cantidad) WHERE resuelta_en IS NULL

    Borrar la fila al despachar seria mas simple y perderia la pregunta que la
    operacion hace despues: "por que faltaron ONT el martes".
    """

    CONSUMIDA = "consumida"
    LIBERADA = "liberada"
    VENCIDA = "vencida"
    DESENLACES = (
        (CONSUMIDA, "Consumida"),
        (LIBERADA, "Liberada"),
        (VENCIDA, "Vencida"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="reservas_material"
    )
    ubicacion = models.ForeignKey(
        "campo.UbicacionInventario",
        on_delete=models.PROTECT,
        related_name="reservas",
        help_text="De donde va a salir. Una reserva es contra UNA bodega.",
    )
    material = models.ForeignKey(
        "campo.MaterialCatalogo", on_delete=models.PROTECT, related_name="reservas"
    )
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    serie = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Reservar UN aparato concreto. Vacio = reservar cantidad.",
    )
    #: Para que trabajo. Es lo que hace la reserva explicable: una reserva sin
    #: orden no se le puede reclamar a nadie.
    orden = models.ForeignKey(
        "campo.OrdenTrabajo",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reservas_material",
    )
    reservada_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservas_hechas",
    )
    #: Hasta cuando vale. Una reserva sin plazo bloquea material para siempre
    #: cuando la orden se cae y nadie la libera -- y el que la hizo ya se fue a
    #: su casa. El plazo lo pone quien reserva; T20 del proyecto hace lo mismo
    #: con las acciones pendientes.
    vence_en = models.DateTimeField(null=True, blank=True)

    #: `null` = sigue activa. Cuando deja de estarlo se marca ACA, no se borra la
    #: fila: la pregunta "por que faltaron ONT el martes" se contesta con esto.
    resuelta_en = models.DateTimeField(null=True, blank=True)
    desenlace = models.CharField(
        max_length=20, choices=DESENLACES, blank=True, default=""
    )
    #: El movimiento que la consumio, cuando el desenlace es `consumida`. Es lo
    #: que permite comprobar que una reserva resuelta tiene un despacho detras.
    movimiento = models.ForeignKey(
        "campo.MovimientoDeMaterial",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservas_que_consumio",
    )
    motivo = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_reserva_material"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["ubicacion", "material"],
                condition=models.Q(resuelta_en__isnull=True),
                name="idx_reserva_activa",
            ),
        ]
        constraints = [
            # Una serie reservada esta reservada UNA vez. Dos reservas activas de
            # la misma ONT son dos promesas del mismo aparato, que es el problema
            # que esta tabla existe para evitar.
            models.UniqueConstraint(
                fields=["org", "material", "serie"],
                condition=models.Q(serie__gt="", resuelta_en__isnull=True),
                name="unique_serie_reservada_activa",
            ),
        ]

    def __str__(self) -> str:
        estado = self.desenlace or "activa"
        return f"Reserva {self.material_id} x{self.cantidad} ({estado})"

    @property
    def activa(self) -> bool:
        return self.resuelta_en is None


# =============================================================================
# FASE 2 -- CONTEO FISICO
# =============================================================================

class ConteoFisico(BaseModel):
    """Alguien fue, conto lo que hay, y lo comparo con lo que el sistema dice.

    POR QUE EL CONTEO NO CORRIGE SOLO
    ---------------------------------
    "El sistema dice 50 y tengo 48" no es un error del sistema: es un hecho nuevo
    que hay que explicar. El conteo NO reescribe la existencia -- produce un
    AJUSTE identificado, con su motivo y su responsable, que entra al libro como
    cualquier otro movimiento.

    Un conteo que sobreescribiera el saldo seria un contador guardado con pasos
    extra: perderia la diferencia, que es lo unico interesante del conteo.

    LOS DOS ESTADOS, y por que el borrador importa
    ---------------------------------------------
    Contar una bodega lleva horas y se hace con el telefono en la mano. Un conteo
    en `borrador` se puede ir llenando; al CERRARLO se congelan las diferencias y
    se escriben los ajustes. Sin el borrador, cada linea contada tendria que
    ajustar al instante y el inventario se movería mientras se cuenta.
    """

    BORRADOR = "borrador"
    CERRADO = "cerrado"
    ESTADOS = ((BORRADOR, "Borrador"), (CERRADO, "Cerrado"))

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="conteos_inventario"
    )
    ubicacion = models.ForeignKey(
        "campo.UbicacionInventario", on_delete=models.PROTECT, related_name="conteos"
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default=BORRADOR)
    contado_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conteos_hechos",
    )
    iniciado_en = models.DateTimeField(default=timezone.now)
    cerrado_en = models.DateTimeField(null=True, blank=True)
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_conteo_fisico"
        ordering = ["-iniciado_en"]
        constraints = [
            # Dos conteos abiertos de la misma bodega producirian dos verdades
            # sobre lo mismo, y los ajustes del segundo taparian los del primero.
            models.UniqueConstraint(
                fields=["org", "ubicacion"],
                condition=models.Q(estado="borrador"),
                name="unique_conteo_abierto_por_ubicacion",
            ),
        ]

    def __str__(self) -> str:
        return f"Conteo {self.ubicacion_id} ({self.estado})"


class LineaDeConteo(BaseModel):
    """Lo que se conto de un material, y lo que el sistema decia en ese momento.

    `existencia_sistema` se guarda al CERRAR y no se recalcula despues: es lo que
    el sistema afirmaba cuando alguien estaba parado frente al estante. Si se
    recalculara, la diferencia cambiaria sola con cada movimiento posterior y el
    conteo dejaria de ser un hecho -- pasaria a ser una opinion sobre el presente.

    Es la misma razon por la que `ActaDeDevolucion` congela sus totales.
    """

    conteo = models.ForeignKey(
        ConteoFisico, on_delete=models.CASCADE, related_name="lineas"
    )
    material = models.ForeignKey(
        "campo.MaterialCatalogo", on_delete=models.PROTECT, related_name="conteos"
    )
    cantidad_contada = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    #: Congelado al cerrar. Vacio mientras el conteo esta en borrador.
    existencia_sistema = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True
    )
    #: El ajuste que produjo esta linea, si produjo alguno. Una linea que cuadra
    #: no genera movimiento, y eso se ve en que este campo queda vacio.
    ajuste = models.ForeignKey(
        "campo.MovimientoDeMaterial",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lineas_de_conteo",
    )
    motivo = models.TextField(
        blank=True,
        default="",
        help_text="Por que hay diferencia, en palabras de quien conto.",
    )

    class Meta:
        db_table = "campo_linea_conteo"
        constraints = [
            models.UniqueConstraint(
                fields=["conteo", "material"], name="unique_material_por_conteo"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.material_id}: contado {self.cantidad_contada}"


# =============================================================================
# FASE 3 -- PROVEEDORES Y COMPRAS
# =============================================================================

class Proveedor(BaseModel):
    """A quien se le compra.

    LO MINIMO, y el motivo de que sea minimo
    ----------------------------------------
    Nombre, identificacion tributaria y contacto. Nada de condiciones de pago,
    calificaciones ni historial comercial: eso es un modulo de compras y el brief
    advirtio que convertir esto en un ERP es el modo de fallar del trabajo.

    Lo que un inventario necesita de un proveedor es poder responder "de donde
    vino este lote". Todo lo demas es otra cosa.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="proveedores"
    )
    nombre = models.CharField(max_length=200)
    identificacion = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="NIT, RUT o el que use el pais. Opcional a proposito: hay "
                  "proveedores chicos sin factura formal.",
    )
    contacto = models.CharField(max_length=200, blank=True, default="")
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_proveedor"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "nombre"], name="unique_proveedor_por_org"
            ),
        ]

    def __str__(self) -> str:
        return self.nombre


class Compra(BaseModel):
    """Un lote que entro, con su referencia y su costo.

    NO ES UNA ORDEN DE COMPRA
    -------------------------
    No hay aprobacion, ni pedido pendiente, ni recepcion parcial contra un
    pedido. Esto registra lo que YA llego: es el origen de una entrada, no un
    flujo de aprovisionamiento. La diferencia importa porque una orden de compra
    arrastra estados, aprobadores y presupuesto, y ahi empieza el ERP.

    Cuando una empresa necesite el pedido pendiente, sera su propio trabajo y
    tendra su propia ficha.
    """

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="compras")
    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="compras",
        help_text="Opcional: hay material que entra sin proveedor identificado "
                  "--una donacion, un traslado entre empresas del grupo--.",
    )
    referencia = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Numero de factura o remision.",
    )
    recibida_en = models.DateTimeField(default=timezone.now)
    recibida_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compras_recibidas",
    )
    moneda = models.CharField(
        max_length=8,
        default="COP",
        help_text="Una compra tiene UNA moneda. Mezclarlas en un total es el "
                  "error clasico de una valorizacion.",
    )
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_compra"
        ordering = ["-recibida_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "proveedor", "referencia"],
                condition=models.Q(referencia__gt=""),
                name="unique_factura_por_proveedor",
            ),
        ]

    def __str__(self) -> str:
        return f"Compra {self.referencia or self.pk}"
