# -*- coding: utf-8 -*-
"""
================================================================================
 LA CONVERSACION DEL SUPERVISOR  --  continuidad, no memoria infinita
================================================================================

POR QUE NO SE REUSA 'asistente.conversations'
---------------------------------------------
Esa tabla existe y funciona, pero es del MOTOR y de otra cosa: guarda las
conversaciones de WhatsApp con un CLIENTE FINAL, con su ventana de 24 horas, su
relevo IA-humano, sus acuses de entrega y su cierre por plazo. Meter aqui la
conversacion de un colaborador con el Supervisor haria que esas reglas --pensadas
para un abonado-- se aplicaran a un empleado mirando un tablero: la ventana de 24
h, el cierre automatico, el contador de mensajes sin respuesta.

Y hay una razon mas dura: el Supervisor vive en Django y el motor NO lee las
tablas del CRM. Una conversacion que referencia una 'SituacionOperativa' no puede
vivir del otro lado de esa frontera.

DOS TABLAS, Y NINGUNA GUARDA MAS DE LO QUE HACE FALTA
-----------------------------------------------------
    ConversacionSupervisor   el hilo, con su CONTEXTO actual (que situacion o que
                             caso se esta mirando). Es lo que hace que "¿cuantos
                             afectados?" se entienda sin repetir "de S-001".
    MensajeSupervisor        cada mensaje, con la traza de que herramientas se
                             consultaron para contestarlo.

LO QUE NO SE PERSISTE, A PROPOSITO
----------------------------------
El CONTEXTO OPERATIVO no se copia aqui. Las situaciones, los afectados, el SLA y
las fuentes se consultan EN VIVO cada turno: son datos que cambian entre ciclos, y
una copia en la conversacion quedaria vieja y se leeria como actual. Lo que se
guarda es lo que no se puede reconstruir -- que se pregunto, que se contesto, y de
que se estaba hablando.

Tampoco se guarda el prompt del sistema: vive en codigo, se arma en cada turno y
cambiar una regla no debe exigir migrar conversaciones viejas.
================================================================================
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


class RolMensaje:
    """
    Quien habla. Los cuatro roles que el bucle de herramientas necesita.

    'herramienta' es un rol y no un campo aparte porque en la conversacion que ve
    el modelo ES un turno: la pregunta, la llamada, el resultado y la respuesta
    van en orden. Guardarlo de otra forma obligaria a reconstruir ese orden
    despues, y el orden es justamente lo que hace que el modelo entienda.
    """

    HUMANO = "humano"
    SUPERVISOR = "supervisor"
    HERRAMIENTA = "herramienta"
    #  Un turno que fallo. Se guarda igual: una conversacion con un hueco sin
    #  explicacion es peor que una que dice "el modelo no contesto".
    ERROR = "error"

    TODOS = (HUMANO, SUPERVISOR, HERRAMIENTA, ERROR)
    ETIQUETAS = tuple((r, r.capitalize()) for r in TODOS)


class ConversacionSupervisor(BaseModel):
    """
    Un hilo entre una persona y el Supervisor, con el contexto de que se habla.

    EL CONTEXTO ES EL CORAZON DE ESTA TABLA
    ---------------------------------------
    'situacion' y 'caso' son el sujeto implicito de la conversacion. Si el humano
    abrio el chat desde S-001, o si menciono S-001 y el Supervisor contesto sobre
    ella, entonces "¿cuantos clientes afectados?" se refiere a S-001 sin que nadie
    lo repita.

    Son NULABLES porque una conversacion puede no tener sujeto: "¿que esta
    pasando?" no habla de ninguna situacion en particular. Forzar un contexto
    habria obligado a inventar uno.

    Y SE PUEDEN CAMBIAR. Un hilo que empezo en S-001 puede pasar a S-002; lo que
    no puede es cambiar sin que se note, y por eso cada cambio deja su mensaje en
    el hilo.
    """

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="conversaciones_supervisor")
    #  Quien conversa. Una conversacion SIEMPRE tiene dueño: no hay chat anonimo
    #  con el Supervisor, porque lo que muestra es panorama operativo interno.
    actor = models.ForeignKey(Profile, on_delete=models.CASCADE,
                             related_name="conversaciones_con_supervisor")

    titulo = models.CharField(max_length=160, blank=True, default="")

    # --- el contexto vigente -----------------------------------------------
    situacion = models.ForeignKey(
        "operaciones.SituacionOperativa", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="conversaciones")
    #  El caso se guarda por ID y no como FK: un caso puede cerrarse o
    #  archivarse, y la conversacion sobre el sigue teniendo sentido. Una FK con
    #  CASCADE se lo llevaria; con PROTECT impediria cerrar el caso.
    caso_id = models.CharField(max_length=64, blank=True, default="")

    abierta_en = models.DateTimeField()
    ultimo_mensaje_en = models.DateTimeField()
    #  Un hilo se archiva, no se borra: lo que se pregunto y lo que el Supervisor
    #  contesto es el unico registro de que sabia en ese momento.
    archivada = models.BooleanField(default=False)

    class Meta:
        db_table = "operaciones_conversacion_supervisor"
        ordering = ["-ultimo_mensaje_en"]
        indexes = [
            models.Index(fields=["org", "actor", "-ultimo_mensaje_en"]),
            models.Index(fields=["org", "situacion"]),
        ]

    def __str__(self):
        return f"{self.titulo or 'conversación'} ({self.actor_id})"


class MensajeSupervisor(BaseModel):
    """
    Un mensaje del hilo, con la traza de como se contesto.

    POR QUE LA TRAZA VA EN LA FILA DEL MENSAJE
    ------------------------------------------
    Porque la pregunta que importa despues es "¿de donde sacó eso?". Guardar las
    herramientas consultadas en una tabla aparte obligaria a cruzarla por tiempo
    para reconstruirlo, y el tiempo es el peor identificador: dos turnos del mismo
    minuto quedarian mezclados.

    'contexto_usado' guarda QUE se le mando al modelo en resumen --cuantas
    situaciones, que fuentes, que nivel de autonomia-- y no el contenido entero.
    Sirve para explicar una respuesta rara sin duplicar el estado del mundo en
    cada fila.
    """

    conversacion = models.ForeignKey(
        ConversacionSupervisor, on_delete=models.CASCADE,
        related_name="mensajes")
    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="mensajes_supervisor")

    rol = models.CharField(max_length=16, choices=RolMensaje.ETIQUETAS)
    contenido = models.TextField()
    escrito_en = models.DateTimeField()

    # --- trazabilidad ------------------------------------------------------
    #  Que herramientas se consultaron para armar ESTA respuesta, con sus
    #  argumentos. Nunca el resultado completo: puede traer datos de cliente.
    herramientas = models.JSONField(default=list, blank=True)
    #  Un resumen de lo que entro al prompt. No el prompt.
    contexto_usado = models.JSONField(default=dict, blank=True)
    #  El modelo y el proveedor que contestaron. No son secretos; la credencial
    #  nunca sale del motor.
    modelo = models.CharField(max_length=64, blank=True, default="")
    proveedor = models.CharField(max_length=32, blank=True, default="")
    #  Cuanto tardo, en milisegundos. Util y no sensible.
    duracion_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "operaciones_mensaje_supervisor"
        ordering = ["escrito_en", "created_at"]
        indexes = [
            models.Index(fields=["conversacion", "escrito_en"]),
            models.Index(fields=["org", "-escrito_en"]),
        ]
        constraints = [
            #  Un mensaje de ERROR tiene que decir que fallo. Sin esto, un hueco
            #  en la conversacion seria indistinguible de un turno que nadie
            #  mando.
            models.CheckConstraint(
                condition=(~models.Q(rol="error") | ~models.Q(error="")),
                name="mensaje_error_con_motivo"),
        ]

    def __str__(self):
        return f"{self.rol}: {self.contenido[:50]}"
