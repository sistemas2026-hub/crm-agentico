# -*- coding: utf-8 -*-
"""
================================================================================
 ESTILO DEL SUPERVISOR  --  lo que SI se edita desde la interfaz
================================================================================

QUE PROBLEMA RESUELVE
---------------------
El prompt del Supervisor estaba entero en codigo. Afinar el tono, el largo o que
se muestra son cosas que se hacen veinte veces hasta que quedan bien, y veinte
commits con despliegue para eso es desproporcionado. Ademas choca con §3.3 de
CLAUDE.md: lo que varia por empresa es configuracion editable y persistida por
tenant, nunca un valor fijo en codigo. El segundo ISP va a querer su propio tono.

LA LINEA DEL CORTE, Y POR QUE NO ES TODO EDITABLE
-------------------------------------------------
Se midio algo que obliga a partirlo: EL CHAT NO PASA POR 'cerebro.validar()'.
Usa 'razonar', no 'concluir', asi que las cinco garantias --un hecho sin fuente
se descarta, una recomendacion sin hechos se cae-- NO corren en el chat. Ahi lo
que sostiene el "jamas inventas" es el prompt mismo.

Consecuencia: el prompt se parte en dos, y solo una mitad se edita.

    NUCLEO   en codigo, NO editable. La identidad, los limites, el "nunca
             presentas una hipotesis como un hecho", el "jamas inventas", como
             usa las herramientas. Son GARANTIAS: en el camino del chat estan
             haciendo trabajo real, no decorando.

    ESTILO   en esta tabla, editable por empresa. Como habla, cuanto escribe,
             que muestra y que no. Son decisiones de PRESENTACION: cambiarlas no
             puede hacer que el Supervisor afirme algo que no sabe.

El nivel de autonomia NO esta en ninguna de las dos: se consulta en vivo en cada
turno. Un estilo que dijera "tu nivel es 3" no cambiaria nada, porque el nivel
sale de la base.

APPEND-ONLY, CON EL MISMO MOLDE QUE 'NivelAutonomia'
----------------------------------------------------
Cada cambio es una fila nueva; el vigente es el mas reciente. Sin filas, manda
el texto por defecto del codigo -- asi el despliegue llega inerte y el
comportamiento es identico al de antes hasta que alguien edite.

Se guarda 'texto_anterior' por el mismo motivo que 'NivelAutonomia' guarda
'nivel_anterior': un prompt que empeoro la respuesta se revierte mirando el
cambio, no reconstruyendolo de memoria.
"""

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


class AmbitoEstilo:
    """
    Los dos lugares donde el Supervisor usa un prompt, y son distintos.

    En el CHAT hay una persona preguntando: el estilo gobierna la conversacion.
    En el CICLO hay una señal ya detectada y nadie leyendo en ese momento: lo
    que se le pide es interpretar, no conversar. Un solo texto para los dos
    haria que afinar la conversacion degradara el analisis automatico.
    """

    CHAT = "chat"
    CICLO = "ciclo"
    TODOS = (CHAT, CICLO)
    ETIQUETAS = (
        (CHAT, "Chat del Supervisor"),
        (CICLO, "Ciclo automatico"),
    )


class EstiloSupervisor(BaseModel):
    """
    Un cambio de estilo. La fila mas reciente por ambito es la que rige.

    NO GUARDA EL NUCLEO. Si alguien quisiera borrar "jamas inventas" tendria que
    tocar codigo y pasar por revision, que es exactamente la intencion:
    'test_estilo' afirma que el nucleo aparece en el prompt compuesto por
    cualquier estilo, incluido uno vacio o uno que intente contradecirlo.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="estilos_supervisor"
    )
    ambito = models.CharField(max_length=12, choices=AmbitoEstilo.ETIQUETAS)

    texto = models.TextField(
        help_text="El bloque de estilo que se agrega al nucleo. Tono, largo, "
                  "que mostrar y que no."
    )
    texto_anterior = models.TextField(
        blank=True, default="",
        help_text="Lo que regia antes de este cambio. Vacio en el primero.",
    )

    actor = models.ForeignKey(
        Profile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="estilos_cambiados",
        help_text="Quien lo cambio. 'estilo.cambiar' lo exige.",
    )
    cambiado_en = models.DateTimeField()
    motivo = models.TextField(
        help_text="Por que se cambio. Un prompt sin motivo no se puede "
                  "discutir despues de que empeore una respuesta."
    )

    class Meta:
        db_table = "operaciones_estilo_supervisor"
        ordering = ["-cambiado_en", "-created_at"]
        indexes = [
            #  Declarado a mano: 'BaseModel' no trae indice por org, y una Meta
            #  propia reemplazaria la del padre si lo trajera. Mismo motivo que
            #  en 'razonamiento_modelos'.
            models.Index(fields=["org", "-cambiado_en"]),
            models.Index(fields=["org", "ambito", "-cambiado_en"]),
        ]
        constraints = [
            #  Un estilo vacio no es "sin estilo": es un prompt al que le falta
            #  la mitad. Para volver al texto por defecto esta
            #  'estilo.restablecer', que deja su propia fila con su motivo --
            #  no se borra la fila, porque el historial no se edita.
            models.CheckConstraint(
                condition=~models.Q(texto=""),
                name="estilo_no_vacio",
            ),
            models.CheckConstraint(
                condition=~models.Q(motivo=""),
                name="estilo_con_motivo",
            ),
        ]
        verbose_name = "estilo del Supervisor"
        verbose_name_plural = "estilos del Supervisor"

    def __str__(self):
        return f"{self.ambito} · {self.cambiado_en:%d/%m/%Y %H:%M}"
