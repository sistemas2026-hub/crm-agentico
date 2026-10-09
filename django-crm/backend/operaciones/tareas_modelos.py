# -*- coding: utf-8 -*-
"""
===============================================================================
 LA TABLA DE LO DELEGADO  --  una fila por tarea y empresa
===============================================================================

NO ES APPEND-ONLY, y es distinto de 'EstiloSupervisor' o 'RazonamientoSupervisor'
a proposito. Aquellas guardan una secuencia de hechos --que se dijo, que se
razono-- y ahi cada cambio es una fila nueva. Esta guarda un ESTADO: si la
tarea esta delegada o no. Una fila por empresa y clave, que se enciende y se
apaga.

Lo que SI se conserva es quien y cuando, de las dos puntas: quien la delego y
quien la quito. Quitar no borra la fila -- 'activa' pasa a False y los campos
de quitada se llenan. Borrarla haria imposible contestar "¿esto estuvo delegado
alguna vez?", que es justo la pregunta que alguien va a hacer el dia que un
caso aparezca cerrado y nadie recuerde por que.
"""
from common.base import BaseModel
from common.models import Org, Profile
from django.db import models


class TareaDelegada(BaseModel):
    """Una tarea del catalogo, delegada por una persona a una empresa."""

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="tareas_delegadas")

    #  La clave del catalogo ('operaciones/tareas_delegadas.py::CATALOGO').
    #  NO es un 'choices' del modelo y eso es deliberado: el catalogo vive en
    #  codigo y crece ahi; un 'choices' obligaria a una migracion por cada
    #  tarea nueva, y una fila con una clave vieja seguiria siendo legible en
    #  vez de romper la lectura. 'esta_delegada' ignora las claves que ya no
    #  estan en el catalogo, asi que una clave huerfana no habilita nada.
    clave = models.CharField(max_length=64)

    activa = models.BooleanField(default=True)

    #  LA FRASE CON LA QUE SE PIDIO, tal cual. No decide nada -- lo que se
    #  ejecuta es la tarea del catalogo-- pero permite ver, meses despues, que
    #  creia estar pidiendo quien la delego. Si la tarea hace algo distinto de
    #  lo que esa frase dice, el problema es del catalogo y hay que poder
    #  notarlo.
    pedido_textual = models.CharField(max_length=500, blank=True, default="")

    #  DONDE SE PIDIO, para poder contestar ahi mismo. Se guarda el id y no
    #  una relacion: una conversacion se puede borrar --la retencion las vence
    #  al año-- y eso no puede arrastrar la tarea delegada ni ponerla en
    #  cascada. Si la conversacion ya no esta, el aviso no sale y la tarea
    #  sigue andando, que es el orden correcto de prioridades.
    #
    #  VACIO cuando se delego por otro camino que no sea el chat. No es un
    #  error: significa "no hay donde avisar", y el ciclo lo trata asi en vez
    #  de buscarse una conversacion cualquiera para escribir.
    conversacion_id = models.UUIDField(null=True, blank=True)

    delegada_por = models.ForeignKey(
        Profile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tareas_que_delego")
    delegada_en = models.DateTimeField(null=True, blank=True)

    quitada_por = models.ForeignKey(
        Profile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tareas_que_quito")
    quitada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "operaciones_tarea_delegada"
        ordering = ["-delegada_en", "-created_at"]
        indexes = [
            #  Declarado a mano: 'BaseModel' no trae indice por org, y una Meta
            #  propia reemplazaria la del padre si lo trajera. Mismo motivo que
            #  en 'estilo_modelos' y 'razonamiento_modelos'.
            models.Index(fields=["org", "activa"]),
        ]
        constraints = [
            #  UNA fila por empresa y tarea. Dos filas de la misma clave
            #  dejarian el estado ambiguo: una activa y otra no, y la respuesta
            #  a "¿esta delegada?" dependeria del orden de lectura.
            models.UniqueConstraint(fields=["org", "clave"],
                                    name="tarea_delegada_unica_por_org"),
            #  Una tarea ACTIVA tiene que decir quien la delego y cuando. Sin
            #  eso no se puede repreguntar, que es justo lo que hace falta
            #  cuando algo se cerro solo y nadie recuerda haberlo pedido.
            models.CheckConstraint(
                condition=(models.Q(activa=False)
                           | (models.Q(delegada_por__isnull=False)
                              & models.Q(delegada_en__isnull=False))),
                name="tarea_activa_con_quien_y_cuando"),
        ]

    def __str__(self):
        return f"{self.clave} {'activa' if self.activa else 'quitada'}"
