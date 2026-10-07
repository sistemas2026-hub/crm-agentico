# -*- coding: utf-8 -*-
"""
================================================================================
 LA CUADRILLA  --  el equipo que existe entre el lunes y el martes
================================================================================

POR QUE HACIA FALTA ALGO NUEVO
------------------------------
`AsignacionTrabajo` ata personas a UNA orden con un rol (lider, ayudante,
chofer). Es correcto y sigue siendo la verdad de quien ejecuto cada trabajo,
pero no alcanza para despachar: no existe ningun objeto al que decirle "mañana
haces instalaciones". La cuadrilla se armaba orden por orden y desaparecia con
ella, asi que no se podia preguntar "cuanto hizo la cuadrilla 1 este mes" ni
"a quien le asigno las 12 instalaciones de mañana".

LA COMPOSICION ES DEL DIA, NO DE LA CUADRILLA
---------------------------------------------
La cuadrilla tiene identidad estable --un nombre, un lider-- y una composicion
que cambia: hay dias que pasa de instalacion a correctivo, y hay dias que el
auxiliar es otro. Guardar la labor y los auxiliares EN la cuadrilla obligaria a
pisarlos cada mañana, y el martes nadie podria decir quien fue el miercoles
pasado.

Por eso son dos tablas:

    Cuadrilla          quien es, y sigue siendo la misma mañana
    JornadaDeCuadrilla que hizo ESE dia: su labor y quienes la integraron

Es la misma forma que `ProgramacionSemanal` / `ProgramacionOrden` ya usa en
operaciones, y por el mismo motivo: sin una fila por dia, "se cambio de labor"
deja de ser una afirmacion verificable.

LO QUE ESTO NO HACE
-------------------
No reemplaza a `AsignacionTrabajo` y no se mezcla con ella. Una orden sigue
diciendo quien la ejecuto, persona por persona; la cuadrilla dice a quien se le
reparte el trabajo. Cuando una orden se asigna a una cuadrilla, lo que se
escribe son las asignaciones de sus integrantes de ESE dia -- la orden no
guarda un puntero a la cuadrilla, porque la composicion de mañana no puede
cambiar quien hizo el trabajo de ayer.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


class Cuadrilla(BaseModel):
    """Un equipo de campo con identidad estable.

    El nombre es lo que la gente usa para hablar de ella ("la 1", "la de
    Soledad"), asi que es unico por empresa: dos cuadrillas con el mismo nombre
    vuelven ambiguo cualquier reporte.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="cuadrillas"
    )
    nombre = models.CharField(max_length=120)

    #: Quien responde por la cuadrilla. Puede faltar --una cuadrilla en armado
    #: todavia no tiene lider-- pero sin lider no se le puede despachar, y eso
    #: lo valida quien despacha, no este modelo.
    lider = models.ForeignKey(
        Profile,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cuadrillas_que_lidera",
    )

    #: El vehiculo en el que se mueve, si lo tiene fijo.
    #:
    #: Es la ubicacion de inventario de tipo `vehiculo`: en una cuadrilla el
    #: material vive en la camioneta y no en la mochila de una persona, y esa
    #: distincion ya existe en el inventario. Se referencia en vez de repetirse.
    vehiculo = models.ForeignKey(
        "campo.UbicacionInventario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cuadrillas",
        help_text="Ubicacion de inventario de tipo vehiculo.",
    )

    #: Una cuadrilla NO se borra: se da de baja. Sus jornadas la referencian y
    #: son las que explican quien hizo que.
    activa = models.BooleanField(default=True)
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_cuadrilla"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "nombre"], name="unique_cuadrilla_nombre_por_org"
            )
        ]

    def __str__(self) -> str:
        return self.nombre


class JornadaDeCuadrilla(BaseModel):
    """Que hizo una cuadrilla un dia: su labor y quienes la integraron.

    UNA FILA POR CUADRILLA Y POR DIA, y ahi esta todo el punto. La labor del
    martes no pisa la del lunes, asi que "el miercoles pasaron a correctivo" se
    demuestra en vez de deducirse -- y cuando alguien pregunte por que esa
    semana se hicieron pocas instalaciones, la respuesta esta escrita.
    """

    INSTALACION = "instalacion"
    CORRECTIVO = "correctivo"
    TRABAJOS = "trabajos"
    LABORES = (
        (INSTALACION, "Instalacion"),
        (CORRECTIVO, "Correctivo"),
        (TRABAJOS, "Trabajos"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="jornadas_de_cuadrilla"
    )
    cuadrilla = models.ForeignKey(
        Cuadrilla, on_delete=models.CASCADE, related_name="jornadas"
    )
    fecha = models.DateField()
    labor = models.CharField(max_length=20, choices=LABORES, default=INSTALACION)

    #: El lider de ESE dia. Normalmente el de la cuadrilla, pero no siempre:
    #: si el lider esta de vacaciones, alguien la lleva igual. Se guarda aparte
    #: por el mismo motivo que la labor -- quien respondia ese martes no puede
    #: depender de quien la lidera hoy.
    lider = models.ForeignKey(
        Profile,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="jornadas_que_lidero",
    )
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_jornada_cuadrilla"
        ordering = ["-fecha", "cuadrilla__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["cuadrilla", "fecha"],
                name="unique_jornada_por_cuadrilla_y_dia",
            )
        ]

    def __str__(self) -> str:
        return f"{self.cuadrilla.nombre} · {self.fecha} · {self.get_labor_display()}"


class IntegranteDeJornada(BaseModel):
    """Quien trabajo en esa cuadrilla ese dia, y con que rol.

    LOS ROLES SON LOS DE `AsignacionTrabajo`, y no se duplican: una persona que
    es ayudante en la cuadrilla tiene que poder quedar como ayudante en la
    orden sin traducir nada. Importarlos de alla evita que los dos catalogos
    se separen en silencio, que es exactamente lo que ya le paso una vez a ese
    campo (ver el comentario de ROLES_CUADRILLA).
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="integrantes_de_jornada"
    )
    jornada = models.ForeignKey(
        JornadaDeCuadrilla, on_delete=models.CASCADE, related_name="integrantes"
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.PROTECT, related_name="jornadas_de_cuadrilla"
    )
    rol = models.CharField(max_length=64)

    class Meta:
        db_table = "campo_integrante_jornada"
        ordering = ["rol", "profile_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["jornada", "profile"],
                name="unique_persona_por_jornada",
            )
        ]

    def clean(self):
        """Una persona no puede estar en dos cuadrillas el mismo dia.

        La unicidad de arriba cubre la misma jornada; esto cubre el caso que de
        verdad pasa: alguien anotado en la cuadrilla 1 y en la 2 el martes. No
        es un error de tipeo inofensivo -- las dos cuadrillas contarian con esa
        persona al repartir el trabajo, y una de las dos se quedaria corta sin
        que nadie lo note hasta la mañana.
        """
        if not self.jornada_id or not self.profile_id:
            return
        choque = (
            IntegranteDeJornada.objects.filter(
                jornada__fecha=self.jornada.fecha,
                jornada__org=self.jornada.org,
                profile_id=self.profile_id,
            )
            .exclude(jornada_id=self.jornada_id)
            .select_related("jornada__cuadrilla")
            .first()
        )
        if choque:
            raise ValidationError(
                f"Esa persona ya esta en la cuadrilla "
                f"'{choque.jornada.cuadrilla.nombre}' el {self.jornada.fecha}."
            )

    def __str__(self) -> str:
        return f"{self.profile_id} · {self.rol}"
