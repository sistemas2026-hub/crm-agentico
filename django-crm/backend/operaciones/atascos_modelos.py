# -*- coding: utf-8 -*-
"""
===============================================================================
 LOS ATASCOS DEL SUPERVISOR  --  una fila por dia, fase, tipo y sujeto
===============================================================================

Pedido del usuario (29/10/2026), antes de decidir si un agente de IA resuelve
lo que las reglas no saben: «medir primero». Cada vez que el ciclo no puede
decidir algo --un kit que ninguna regla elige, una orden sin cuadrilla, una
lectura que el modelo no contesto--, queda aca con su tipo. En una o dos
semanas dice cuantos atascos hay de cada clase, y cuales podria destrabar mas
contexto.

UNA FILA POR DIA, NO POR VUELTA. El ciclo corre cada hora y el mismo atasco se
ve doce veces en un dia: contar filas inflaria el numero. `veces` dice cuantas
vueltas lo vieron; lo que se mide son los DIAS y los SUJETOS distintos.

SIN DATOS DEL CLIENTE. `sujeto` es un identificador (una orden, una cuadrilla,
una labor, una propuesta) y `motivo` un texto fijo del codigo: el mismo que va
al log. Nunca la descripcion de un ticket ni un nombre.

SIN RLS, con el filtro por empresa explicito: el mismo patron que
'TareaDelegada' y las tablas de campo. Quien lee esto es el comando del informe,
que fija la empresa a mano.
"""
from django.db import models

from common.base import BaseModel
from common.models import Org


class AtascoDelSupervisor(BaseModel):
    """Algo que el ciclo no pudo decidir, un dia, con cuantas vueltas lo vieron."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="atascos_del_supervisor")

    #  El dia en la zona de la empresa: un atasco de las 23:30 en Bogota es de
    #  ese dia, no del siguiente en UTC.
    dia = models.DateField()

    #  La fase del ciclo y el tipo del catalogo ('operaciones/atascos.py').
    #  NO son 'choices': el catalogo crece en codigo, como el de las tareas
    #  delegadas, y una fila con un tipo viejo sigue siendo legible.
    fase = models.CharField(max_length=48)
    tipo = models.CharField(max_length=48)

    #  QUE se trabo: el id de la orden, la cuadrilla, la labor o la propuesta.
    sujeto = models.CharField(max_length=100)

    #  Texto fijo, el de la ultima vuelta que lo vio.
    motivo = models.CharField(max_length=200, blank=True, default="")

    veces = models.PositiveIntegerField(default=1)
    primera_vez = models.DateTimeField()
    ultima_vez = models.DateTimeField()

    class Meta:
        db_table = "operaciones_atasco_supervisor"
        ordering = ["-dia", "fase", "tipo"]
        indexes = [
            #  Declarado a mano, como en 'tareas_modelos': 'BaseModel' no trae
            #  indice por org. El informe lee por empresa y rango de dias.
            models.Index(fields=["org", "dia"]),
        ]
        constraints = [
            #  UNA fila por dia y atasco: es lo que hace que la segunda vuelta
            #  sume en vez de contar dos veces.
            models.UniqueConstraint(fields=["org", "dia", "fase", "tipo", "sujeto"],
                                    name="atasco_uno_por_dia"),
        ]

    def __str__(self):
        return f"{self.dia} {self.fase} · {self.tipo} · {self.sujeto}"
