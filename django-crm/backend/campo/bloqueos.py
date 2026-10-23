# -*- coding: utf-8 -*-
"""El bloqueo de un trabajo: un HECHO con apertura y cierre.

POR QUE ES UNA TABLA Y NO UN CAMPO EN LA ORDEN
----------------------------------------------
Mismo motivo que `ReservaDeMaterial`: un bloqueo es un hecho con fecha, no una
bandera. Un booleano `esta_bloqueada` en la orden contesta "¿ahora?" y pierde
todo lo demas -- cuantas veces se bloqueo, por que, cuanto duro cada vez, quien
lo resolvio. Y esa es justo la pregunta que alguien hace el martes siguiente:
"¿por que esta instalacion tardo tres dias?".

Asi que la fila no se borra ni se edita al resolverse: se le pone `resuelto_en`.

LAS DOS COSAS QUE NO SON LO MISMO
---------------------------------
    estado_operativo = "bloqueada"   ->  el trabajo esta detenido
    requiere_noc = True              ->  hace falta que ALGUIEN DEL NOC haga algo

Un trabajo puede estar detenido esperando al cliente, esperando material, o
porque llueve. Nada de eso lo resuelve el NOC. Si los dos conceptos fueran uno,
la bandeja del NOC mostraria trabajos que nadie de esa mesa puede destrabar, y a
la semana la dejarian de mirar.

Por eso `requiere_noc` es un campo ESTRUCTURAL de plataforma y no se deduce
leyendo un campo dinamico del esquema del ISP: otra empresa lo llamaria
"Requerimiento a NOC", "pedido a mesa" o cualquier otra cosa, y un filtro que
depende del nombre que eligio un cliente deja de funcionar con el segundo.

POR QUE SE GUARDA EL ESTADO ANTERIOR
------------------------------------
Al resolver un bloqueo hay que volver a algun lado, y ese lado NO se adivina.
Puede haber un bloqueo antes de llegar al sitio --no hay acceso a la calle-- y
otro con el tecnico ya arriba del poste: volver siempre a `en_sitio` seria
inventar que el tecnico llego cuando no habia llegado.

Se persiste al abrir, no se deduce despues mirando "el ultimo evento".
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from common.base import BaseModel
from common.models import Org, Profile


class BloqueoDeTrabajo(BaseModel):
    """Un trabajo que no puede seguir, con su motivo y su salida."""

    #: Quien lo destrabó. Es de plataforma --no del esquema de un ISP-- porque de
    #: esto sale la respuesta a "¿quién nos está deteniendo los trabajos?".
    NOC = "noc"
    COORDINACION = "coordinacion"
    BODEGA = "bodega"
    TECNICO = "tecnico"
    CLIENTE = "cliente"
    TERCERO = "tercero"
    OTRO = "otro"
    QUIENES = (
        (NOC, "NOC"),
        (COORDINACION, "Coordinación"),
        (BODEGA, "Bodega"),
        (TECNICO, "El técnico"),
        (CLIENTE, "El cliente"),
        (TERCERO, "Un tercero"),
        (OTRO, "Otro"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="bloqueos_de_trabajo"
    )
    orden = models.ForeignKey(
        "campo.OrdenTrabajo", on_delete=models.CASCADE, related_name="bloqueos"
    )

    #: El reporte del que nació. Puede faltar si el bloqueo lo abrió la oficina.
    evento_reporte = models.ForeignKey(
        "campo.EventoTrabajo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bloqueo_abierto",
    )

    abierto_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bloqueos_abiertos",
    )
    abierto_en = models.DateTimeField(default=timezone.now)

    #: Adónde vuelve la orden al resolverse. Se guarda acá, al abrir.
    estado_operativo_anterior = models.CharField(max_length=32, blank=True, default="")

    #: Si además de reportarlo se detuvo el trabajo. Un bloqueo puede quedar
    #: anotado sin mover el estado: el técnico avisa que algo lo demora y sigue
    #: haciendo lo que puede.
    detuvo_el_trabajo = models.BooleanField(default=False)

    #: EL DATO QUE CONSTRUYE LA BANDEJA. Ver el encabezado.
    requiere_noc = models.BooleanField(default=False)

    #: Lo que el tenant eligió en su formulario, copiado como texto para poder
    #: agrupar. No es una lista cerrada de plataforma: cada empresa tiene las
    #: suyas. Vacío es válido.
    categoria = models.CharField(max_length=64, blank=True, default="")

    #: En palabras, para quien lo lea sin abrir el evento.
    motivo = models.TextField(blank=True, default="")
    necesita = models.TextField(
        blank=True,
        default="",
        help_text="Qué hace falta para poder seguir.",
    )

    # --- La salida -----------------------------------------------------------
    resuelto_en = models.DateTimeField(null=True, blank=True)
    resuelto_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bloqueos_resueltos",
    )
    resuelto_por_rol = models.CharField(
        max_length=32, choices=QUIENES, blank=True, default=""
    )
    que_se_hizo = models.TextField(blank=True, default="")
    volvio_a = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        db_table = "campo_bloqueo_trabajo"
        ordering = ["-abierto_en"]
        constraints = [
            # UN solo bloqueo abierto por orden. Dos bloqueos vivos a la vez
            # dejarían sin respuesta la pregunta "¿a qué estado vuelvo?", que es
            # justamente lo que esta tabla existe para contestar.
            models.UniqueConstraint(
                fields=["orden"],
                condition=models.Q(resuelto_en__isnull=True),
                name="un_solo_bloqueo_abierto_por_orden",
            ),
        ]
        indexes = [
            # La bandeja del NOC: los abiertos que le tocan a esa mesa.
            models.Index(
                fields=["org", "requiere_noc", "resuelto_en"],
                name="idx_bloqueo_noc_abierto",
            ),
        ]

    def __str__(self) -> str:
        estado = "abierto" if self.resuelto_en is None else "resuelto"
        return f"OT #{self.orden.numero}: bloqueo {estado}"

    @property
    def esta_abierto(self) -> bool:
        return self.resuelto_en is None

    @property
    def minutos_detenido(self) -> int:
        """Cuánto llevó (o lleva) detenido.

        Es el dato que después explica por qué una intervención tardó, sin que
        esos minutos se cuenten como «el técnico no reportó».
        """
        fin = self.resuelto_en or timezone.now()
        return int((fin - self.abierto_en).total_seconds() // 60)
