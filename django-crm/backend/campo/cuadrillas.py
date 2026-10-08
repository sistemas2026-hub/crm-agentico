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

#  Los roles de cuadrilla se IMPORTAN de `AsignacionTrabajo`, no se copian --
#  ver el docstring de `IntegranteDeJornada`. El import de arriba hacia abajo
#  funciona porque `campo/models.py` importa ESTE modulo al final, ya con
#  `AsignacionTrabajo` definido; al reves seria un ciclo. Si alguna vez se
#  mueve ese import al principio de models.py, esto se rompe al arrancar --
#  ruidoso, no en silencio, que es lo que importa.
from campo.models import AsignacionTrabajo


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

    #: QUE ZONAS CUBRE ESE DIA, y por eso vive en la jornada y no en la
    #: cuadrilla: igual que la labor, hay dias que una cuadrilla se sale de su
    #: territorio de siempre, y el martes nadie podria decir donde estuvo el
    #: miercoles pasado si esto se pisara cada mañana.
    #:
    #: Son VARIAS porque una cuadrilla cubre mas de una zona en un dia flojo, y
    #: obligar a una sola llevaria a inventar zonas combinadas ("Norte y
    #: Centro") que despues nadie sabe mantener.
    #:
    #: Vacio significa "sin zona asignada", que NO es "cubre todas": con zona
    #: dura, una cuadrilla sin zona no recibe trabajo por zona, y eso tiene que
    #: notarse en vez de repartirle cualquier cosa.
    zonas = models.ManyToManyField(
        "campo.ZonaOperativa",
        related_name="jornadas",
        blank=True,
    )

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


class PersonaDeCampo(BaseModel):
    """Alguien que trabaja en campo, tenga o no cuenta en el sistema.

    POR QUE NO ALCANZA `Profile`
    ----------------------------
    `Profile` exige un `User`, o sea un correo y credenciales: es quien ENTRA
    al sistema. Y los auxiliares no entran -- no tienen celular asignado, asi
    que no hay nada que les pedir una contraseña para. Mientras el integrante
    de una jornada fue un `Profile`, anotar a un auxiliar obligaba a inventarle
    una cuenta que nadie iba a usar, y el catalogo de roles quedaba mintiendo:
    ofrecia 'ayudante' y 'chofer' (ver `AsignacionTrabajo.ROLES_CUADRILLA`)
    para gente que el modelo no permitia registrar.

    Son dos preguntas distintas y ahora son dos tablas:

        Profile          quien puede ENTRAR al sistema
        PersonaDeCampo   quien TRABAJO, con cuenta o sin ella

    EL ENLACE A `profile` ES OPCIONAL, Y ESO ES EL PUNTO
    ---------------------------------------------------
    Lleno para el lider, que tiene celular y usa la aplicacion; vacio para el
    auxiliar. El dia que a un auxiliar le asignen un celular se le crea la
    cuenta y se le enlaza a ESTA MISMA fila: su historial no se parte en dos
    personas distintas, que es lo que pasaria si cada forma de identificarlo
    tuviera su propia tabla.

    POR QUE EL NOMBRE NO ES UNICO
    -----------------------------
    Dos personas se pueden llamar igual de verdad, y bloquear la segunda
    obligaria a deformarle el nombre para poder cargarla. Quien crea una
    recibe un aviso si ya hay otra con ese nombre --ver
    `cuadrillas_views.PersonasDeCampoView`-- y decide; el modelo no decide por
    el. Lo que si se impide es que dos filas apunten al MISMO `profile`: ahi no
    hay ambiguedad posible, seria la misma persona dos veces.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="personas_de_campo"
    )
    nombre = models.CharField(max_length=120)

    #: La cuenta de esta persona, si tiene. Ver el docstring: vacio es el caso
    #: normal de un auxiliar, no un dato faltante.
    profile = models.ForeignKey(
        Profile,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="persona_de_campo",
    )

    #: Con que rol entra normalmente a una cuadrilla. Es un valor por defecto
    #: para no retipearlo cada mañana, NO una restriccion: el rol que vale es
    #: el de la jornada, porque un ayudante puede manejar un dia.
    rol_habitual = models.CharField(
        max_length=64,
        choices=AsignacionTrabajo.ROLES_CUADRILLA,
        default=AsignacionTrabajo.AYUDANTE,
    )

    #: Una persona NO se borra: se da de baja. Sus jornadas la referencian y
    #: son las que explican quien estuvo cada dia.
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "campo_persona_de_campo"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "profile"],
                condition=models.Q(profile__isnull=False),
                name="unique_persona_de_campo_por_cuenta",
            )
        ]

    def __str__(self) -> str:
        return self.nombre

    @property
    def tiene_cuenta(self) -> bool:
        """Si puede recibir trabajo en la aplicacion de campo.

        No es cosmetico: una orden asignada a quien no entra al sistema no la
        ve nadie en un telefono. Ver `cuadrillas_views.RepartoView`.
        """
        return self.profile_id is not None


class IntegranteDeJornada(BaseModel):
    """Quien trabajo en esa cuadrilla ese dia, y con que rol.

    LOS ROLES SON LOS DE `AsignacionTrabajo`, y no se duplican: una persona que
    es ayudante en la cuadrilla tiene que poder quedar como ayudante en la
    orden sin traducir nada. Importarlos de alla evita que los dos catalogos
    se separen en silencio, que es exactamente lo que ya le paso una vez a ese
    campo (ver el comentario de ROLES_CUADRILLA).

    APUNTA A `PersonaDeCampo`, NO A `Profile` -- ver el docstring de aquella:
    un auxiliar sin celular tambien integra la cuadrilla, y antes no podia.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="integrantes_de_jornada"
    )
    jornada = models.ForeignKey(
        JornadaDeCuadrilla, on_delete=models.CASCADE, related_name="integrantes"
    )
    persona = models.ForeignKey(
        PersonaDeCampo, on_delete=models.PROTECT,
        related_name="jornadas_de_cuadrilla",
    )
    rol = models.CharField(max_length=64)

    class Meta:
        db_table = "campo_integrante_jornada"
        ordering = ["rol", "persona__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["jornada", "persona"],
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

        Desde que el integrante es una `PersonaDeCampo`, esto tambien alcanza a
        los auxiliares. Antes no: un auxiliar no podia estar anotado en ningun
        lado, asi que doblarlo entre dos cuadrillas no lo veia nadie.
        """
        if not self.jornada_id or not self.persona_id:
            return
        choque = (
            IntegranteDeJornada.objects.filter(
                jornada__fecha=self.jornada.fecha,
                jornada__org=self.jornada.org,
                persona_id=self.persona_id,
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
        return f"{self.persona_id} · {self.rol}"
