# -*- coding: utf-8 -*-
"""
El inventario: de donde sale el material y a donde vuelve.

QUE PROBLEMA RESUELVE
---------------------
El modulo de materiales estaba construido desde la mitad hacia adelante: todo lo
que pasa DESPUES de que el tecnico ya tiene el material en la camioneta
--consumo, descuadre, conflicto de serie, devolucion, incidencia, transferencia,
acta de jornada--. Lo que faltaba era el otro extremo: la bodega. Medido el
25/09/2026, antes de escribir esto:

    entidades de bodega / existencia / stock                           0
    endpoints para CREAR una EntregaDeKit (KitView solo tenia `get`)   0
    lugares del backend que instanciaran EntregaDeKit fuera de tests   0
    rol de bodeguero                                                   0

O sea: nadie podia entregarle un kit a un tecnico, y el material devuelto no
volvia a ninguna parte -- `saldo_de` se lo restaba al tecnico y ahi terminaba el
rastro.

UN SOLO LIBRO, CON ORIGEN Y DESTINO
-----------------------------------
Se evaluo una capa paralela --un libro de bodega junto al libro del tecnico, con
el despacho como puente-- y se descarto: son dos verdades, y el dia que una
escritura entre y la otra no, bodega dice 10 y el tecnico dice 9. Con el
agravante de que el puente es el punto mas concurrido del sistema.

En su lugar `MovimientoDeMaterial` gana origen y destino, y la existencia de
CUALQUIER ubicacion sale de la misma resta:

    existencia(ubicacion, material) = SUM(movimientos con destino = ubicacion)
                                    - SUM(movimientos con origen  = ubicacion)

`saldo_de(tecnico)` pasa a ser un caso particular de esa funcion, no otro
calculo. Un solo lugar donde puede estar mal.

LAS DOS FRONTERAS SON NULLS LEGITIMOS
-------------------------------------
No hay ubicacion `PROVEEDOR` ni `CLIENTE`, y no es un olvido:

  * una ENTRADA no tiene origen interno -- el material entra al sistema.
    Inventar un "proveedor" como ubicacion seria crear una entidad para esquivar
    una frontera real, y los proveedores son otro trabajo (Fase 3).
  * un CONSUMO no tiene destino interno -- el material sale. Y el cliente no es
    una ubicacion: si lo fuera, alguien preguntaria "que hay en el cliente 1001"
    y esa es una pregunta de WispHub, que es el dueño del equipo instalado.
    `MovimientoDeMaterial.orden` ya dice en que trabajo se uso, con mas
    informacion que una ubicacion.

El retiro de un equipo en un cliente que cancelo es el caso simetrico: una
ENTRADA sin origen, con su orden como justificacion. No una salida del cliente.
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


class UbicacionInventario(BaseModel):
    """Donde puede estar el material DENTRO del sistema.

    POR QUE ENTRA DESDE EL PRIMER DIA, con una sola bodega
    ------------------------------------------------------
    Una empresa con tres municipios tiene tres bodegas y traslada material entre
    ellas. Hoy hay una sola, y modelarlo despues seria una migracion de datos
    sobre un libro append-only; modelarlo ahora es un campo. La dimension entra
    ya; los traslados entre bodegas son Fase 2.

    El vehiculo existe por el mismo motivo: en una cuadrilla el material vive en
    la camioneta y no en la mochila de una persona, y esa distincion cambia a
    quien se le pide cuenta.
    """

    BODEGA = "bodega"
    VEHICULO = "vehiculo"
    TECNICO = "tecnico"
    TIPOS = (
        (BODEGA, "Bodega"),
        (VEHICULO, "Vehiculo"),
        (TECNICO, "Tecnico"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="ubicaciones_inventario"
    )
    tipo = models.CharField(max_length=20, choices=TIPOS, default=BODEGA)
    nombre = models.CharField(max_length=120)
    #: Solo para tipo `tecnico`: de quien es la custodia. Es lo que permite que
    #: `existencia()` sirva igual para una bodega y para una persona.
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ubicaciones_inventario",
    )
    activa = models.BooleanField(default=True)
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_ubicacion_inventario"
        ordering = ["tipo", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "nombre"], name="unique_ubicacion_nombre_por_org"
            ),
            # La custodia de una persona es UNA. Dos ubicaciones para el mismo
            # tecnico partirian su saldo en dos y ninguna de las dos seria
            # cierta.
            models.UniqueConstraint(
                fields=["org", "profile"],
                condition=models.Q(tipo="tecnico"),
                name="unique_ubicacion_por_tecnico",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()}: {self.nombre}"


class ActivoSerializado(BaseModel):
    """La identidad de UN aparato fisico. Nada mas.

    POR QUE NO GUARDA ESTADO NI UBICACION
    -------------------------------------
    Los dos son funcion del ultimo movimiento de esa serie, y guardarlos repite
    el error que este modulo ya descarto para el saldo: un contador y un
    movimiento que llega ocho horas tarde --el caso normal de una cuadrilla sin
    señal-- se desincronizan en cuanto alguien reintenta, y a partir de ahi nadie
    sabe cual de los dos numeros es el bueno.

    Donde esta se responde con `UbicacionDeActivo`, que es un PUNTERO al presente
    y no un acumulado, y que se reconcilia contra el libro (ver su docstring).
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="activos_serializados"
    )
    material = models.ForeignKey(
        "campo.MaterialCatalogo",
        on_delete=models.PROTECT,
        related_name="activos",
    )
    serie = models.CharField(max_length=128)
    fecha_alta = models.DateField(null=True, blank=True)
    garantia_hasta = models.DateField(null=True, blank=True)
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_activo_serializado"
        ordering = ["material", "serie"]
        constraints = [
            # Un aparato fisico, una fila. El mismo serial de dos fabricantes
            # distintos es posible, y por eso la clave lleva el material.
            models.UniqueConstraint(
                fields=["org", "material", "serie"],
                name="unique_activo_serie_por_material",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.material_id}:{self.serie}"


class UbicacionDeActivo(BaseModel):
    """Donde esta este aparato AHORA. Un indice, no la verdad.

    LA DISTINCION QUE HACE LEGITIMO ESTE MODELO
    -------------------------------------------
    Este proyecto prohibe guardar un derivado --el saldo se calcula, nunca se
    guarda-- y esta tabla guarda uno. No es una excepcion conveniente: es que un
    PUNTERO al presente no es un CONTADOR acumulado.

        contador guardado    acumula N operaciones. Un error viejo es invisible y
          (prohibido)        no hay forma de saber cual de los dos numeros es el
                             bueno.
        puntero al presente  guarda UNA referencia: donde esta este activo hoy.
          (aceptable)        Es reconstruible desde el libro, y por lo tanto
                             VERIFICABLE.

    Y la reconciliacion NO es opcional: sin la prueba que recalcula la custodia
    de cada activo desde sus movimientos y la compara con esta tabla, esto es un
    contador guardado con otro nombre.

    POR QUE EXISTE, si se puede calcular
    ------------------------------------
    Porque hay una garantia que Postgres no puede dar de otra forma: **una serie
    no puede estar en dos custodias a la vez**. Esa propiedad es temporal --una
    serie no puede tener dos salidas consecutivas sin una entrada en medio-- y
    una invariante sobre una secuencia no se expresa con un UniqueConstraint.
    Con esta tabla si: un activo, una fila.

    El constraint viejo intentaba lo mismo y fallaba en la direccion contraria:
    `ItemDeKit` tenia `unique(material, serie)` absoluto, asi que una ONT
    devuelta no se podia volver a entregar NUNCA. Su propio comentario decia
    "una serie no se entrega dos veces SIN HABER VUELTO" y la condicion no
    modelaba el haber vuelto.
    """

    activo = models.OneToOneField(
        ActivoSerializado,
        on_delete=models.CASCADE,
        related_name="posicion",
    )
    #: `null` = fuera de custodia: se consumio, se instalo o se dio de baja. Es
    #: un estado legitimo y no un dato faltante -- el material salio del sistema
    #: y el movimiento dice hacia donde.
    ubicacion = models.ForeignKey(
        UbicacionInventario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activos_presentes",
    )
    #: El hecho que justifica esta posicion. Es lo que la vuelve auditable: una
    #: fila sin movimiento detras es un defecto detectable, no un misterio.
    movimiento = models.ForeignKey(
        "campo.MovimientoDeMaterial",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="posiciones_que_justifica",
    )
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campo_ubicacion_de_activo"

    def __str__(self) -> str:
        donde = self.ubicacion.nombre if self.ubicacion else "fuera de custodia"
        return f"{self.activo_id} -> {donde}"
