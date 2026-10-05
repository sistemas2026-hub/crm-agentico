# -*- coding: utf-8 -*-
"""Pedir material a bodega desde la calle.

EL PROBLEMA
-----------
El tecnico se queda sin conectores en la tercera instalacion y la aplicacion no
tiene nada que ofrecerle: saca el otro telefono y escribe al grupo. La pantalla
de Materiales le dice lo que tiene, y ahi se corta.

POR QUE UN PEDIDO NO ES UN MOVIMIENTO
--------------------------------------
Este modulo existe aparte por la decision que ya esta escrita en `models.py` y
que ordena todo el inventario:

    «Un movimiento de material ES UN HECHO QUE YA OCURRIO EN LA CALLE, no una
    solicitud que el servidor pueda aprobar.»

De ahi salen el `append-only`, el saldo calculado y el descuadre que se acepta.
Un pedido es exactamente lo contrario: todavia no paso nada, alguien lo tiene
que atender, y puede decir que no. Meterlo en la misma tabla romperia la unica
afirmacion que sostiene a esa tabla.

COMO SE CIERRA EL CICLO, SIN UNA PANTALLA NUEVA
------------------------------------------------
El pedido **avisa por los canales que la empresa ya configuro** --el chat, el
correo-- con la misma maquinaria de `services/avisos.py`. Bodega se entera por
donde ya recibe todo lo demas, y no hay que construirle una bandeja que nadie
mira. Y cuando lo atiende, lo hace con el despacho que ya existe: esto no
inventa una segunda forma de entregar material.

LO QUE NO RESUELVE, Y HAY QUE DECIRLO
--------------------------------------
No hay pantalla en el CRM para marcar un pedido como atendido: eso se hace
despachando, y el pedido queda `pendiente` hasta que alguien lo cierre a mano o
se construya esa pantalla. Es deuda declarada, no un olvido.
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


class PedidoDeMaterial(BaseModel):
    """Lo que un tecnico le pide a bodega desde el terreno."""

    PENDIENTE = "pendiente"
    ATENDIDO = "atendido"
    RECHAZADO = "rechazado"
    ESTADOS = (
        (PENDIENTE, "Pendiente"),
        (ATENDIDO, "Atendido"),
        (RECHAZADO, "Rechazado"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="pedidos_material"
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="pedidos_material"
    )
    material = models.ForeignKey(
        "campo.MaterialCatalogo",
        on_delete=models.PROTECT,
        related_name="pedidos",
    )
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)

    #: Por que lo pide. Opcional: parado en una escalera, escribir un motivo es
    #: lo primero que se saltea, y exigirlo haria que el pedido no se haga.
    motivo = models.CharField(max_length=255, blank=True, default="")

    #: En que orden le hace falta, si es por una en particular. Vacio cuando se
    #: esta quedando sin stock en general, que es el caso mas comun.
    orden = models.ForeignKey(
        "campo.OrdenTrabajo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedidos_material",
    )

    estado = models.CharField(max_length=16, choices=ESTADOS, default=PENDIENTE)

    #: LA MISMA GARANTIA QUE EL RESTO DE LA COLA.
    #:
    #: El telefono reenvia sin señal, y dos pedidos iguales le harian pensar a
    #: bodega que hacen falta cuarenta conectores cuando hacen falta veinte.
    #: Por clave primaria, nunca por un `select` previo: ahi vive la carrera.
    idempotency_key = models.CharField(max_length=128, db_index=True)

    class Meta:
        db_table = "campo_pedido_de_material"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "idempotency_key"],
                name="unique_pedido_idempotente_por_org",
            ),
        ]

    def __str__(self) -> str:
        return f"Pedido {self.cantidad} de {self.material_id} ({self.estado})"
