# -*- coding: utf-8 -*-
"""
================================================================================
 GOBIERNO  --  que decidio un humano, y hasta donde puede llegar el Supervisor
================================================================================

DOS TABLAS, Y NINGUNA DUPLICA LO QUE YA HAY
-------------------------------------------
    DecisionSupervisor   lo que un humano decidio sobre una recomendacion, y
                         QUE RESULTADO tuvo. 'PropuestaSupervisor' ya guarda el
                         estado de la revision (aceptada/rechazada) y quien la
                         reviso; lo que no existe en ninguna parte es el
                         DESENLACE: si lo decidido funciono, y si hubo que
                         corregirlo despues.

    NivelAutonomia       el nivel 0-4 vigente POR EMPRESA, con el historial de
                         quien lo cambio y por que. Los cinco niveles ya estan
                         declarados en 'PropuestaSupervisor.NIVELES' y NO se
                         redefinen aqui -- se importan. Lo que falta es que el
                         nivel sea un DATO por empresa en vez de la constante
                         'NIVEL_MAXIMO_ETAPA' del codigo, y que cambiarlo deje
                         rastro.

POR QUE LA MEMORIA DE DECISIONES NO ES UN LUJO
----------------------------------------------
Sin ella no se puede contestar la pregunta que decide si el Supervisor sirve:
cuando recomendo algo y un humano lo acepto, ¿funciono? Las metricas de
"recomendaciones aceptadas" sin el resultado miden obediencia, no acierto.

Y hay una regla que esta tabla existe para hacer posible SIN romperla: una
decision humana NO se convierte en una regla automatica. Se guarda, se cuenta, y
alguien decide despues si eso justifica cambiar una regla -- con su evidencia.
Nada en este modulo lee estas filas para cambiar un umbral.

EL SUPERVISOR NO PUEDE SUBIRSE EL NIVEL
---------------------------------------
'NivelAutonomia' exige un actor humano en la fila, y la base lo obliga. Un cambio
de nivel sin persona no se puede escribir, asi que no hay camino por el que el
propio Supervisor se amplie el alcance -- ni por descuido de un llamador nuevo.
================================================================================
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


class TipoDecision:
    """
    Que decidio la persona. Lista cerrada.

    'MODIFICO' existe aparte de aceptar y rechazar porque es la mas informativa
    de las tres: significa que la recomendacion iba en la direccion correcta y el
    detalle estaba mal. Juntarla con "aceptada" perderia exactamente la señal que
    sirve para mejorar, y con "rechazada" diria que la idea no servia.
    """

    ACEPTO = "acepto"
    RECHAZO = "rechazo"
    MODIFICO = "modifico"
    #  Ni si ni no: la dejo para despues. Es un desenlace real y frecuente, y
    #  contarla como rechazo inflaria los rechazos con cosas que nadie rechazo.
    POSPUSO = "pospuso"
    #  La decidio el sistema por vencimiento, sin que nadie la mirara. NO es una
    #  decision humana, y se distingue para que no contamine las metricas de
    #  aceptacion.
    EXPIRO = "expiro"

    TODOS = (ACEPTO, RECHAZO, MODIFICO, POSPUSO, EXPIRO)
    HUMANOS = (ACEPTO, RECHAZO, MODIFICO, POSPUSO)
    ETIQUETAS = tuple((t, t.capitalize()) for t in TODOS)


class ResultadoDecision:
    """
    Como salio lo que se decidio. 'PENDIENTE' es el estado normal al principio.

    'NO_SE_PUEDE_SABER' no es pereza: es el caso en que ningun endpoint puede
    confirmar el efecto. El proyecto ya tiene esa cicatriz escrita -- que un
    equipo reinicie y vuelva no prueba que la casa tenga internet, y eso lo sabe
    el cliente, no un sistema. Marcarlo asi evita contar como exito algo que
    nadie comprobo.
    """

    PENDIENTE = "pendiente"
    FUNCIONO = "funciono"
    NO_FUNCIONO = "no_funciono"
    PARCIAL = "parcial"
    NO_SE_PUEDE_SABER = "no_se_puede_saber"

    TODOS = (PENDIENTE, FUNCIONO, NO_FUNCIONO, PARCIAL, NO_SE_PUEDE_SABER)
    #  Los que ya tienen desenlace: sobre estos se puede medir acierto.
    CERRADOS = (FUNCIONO, NO_FUNCIONO, PARCIAL)
    ETIQUETAS = tuple((t, t.replace("_", " ").capitalize()) for t in TODOS)


class DecisionSupervisor(BaseModel):
    """
    Una decision humana sobre una recomendacion, y su desenlace.

    QUE NO ES
    ---------
    No es la propuesta (eso es 'PropuestaSupervisor', y se referencia) ni el
    timeline de la situacion (eso es 'SituacionEvento'). Es la union de las tres
    cosas que hoy viven separadas y que juntas contestan "¿sirvio?": que se
    recomendo, que decidio quien podia decidir, y que paso despues.

    LA PROPUESTA ES OPCIONAL, Y LA SITUACION TAMBIEN
    ------------------------------------------------
    Una decision puede colgar de una propuesta, de una situacion, o de las dos.
    Lo que no puede es colgar de ninguna: una decision sin objeto no se puede
    interpretar, y la base lo impide.
    """

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="decisiones_supervisor")
    #  Las dos referencias son opcionales por separado y obligatorias en
    #  conjunto: lo exige la restriccion de abajo.
    situacion = models.ForeignKey(
        "operaciones.SituacionOperativa", on_delete=models.CASCADE,
        null=True, blank=True, related_name="decisiones")
    propuesta = models.ForeignKey(
        "operaciones.PropuestaSupervisor", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="decisiones_registradas")

    #  Que se habia recomendado, copiado en el momento de decidir. Se copia a
    #  proposito: la propuesta puede cambiar de estado despues, y esta fila tiene
    #  que seguir diciendo sobre QUE se decidio.
    recomendacion = models.CharField(max_length=255)

    tipo = models.CharField(max_length=16, choices=TipoDecision.ETIQUETAS)
    #  Quien decidio. NULO solo cuando el tipo es 'expiro' -- que no es una
    #  decision de nadie-- y la base lo obliga.
    actor = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name="decisiones_de_supervisor")
    decidida_en = models.DateTimeField()
    motivo = models.TextField(blank=True, default="")

    resultado = models.CharField(max_length=24,
                                 choices=ResultadoDecision.ETIQUETAS,
                                 default=ResultadoDecision.PENDIENTE)
    resultado_en = models.DateTimeField(null=True, blank=True)
    #  Como se supo el resultado. Sin esto, 'funciono' es una opinion.
    resultado_evidencia = models.TextField(blank=True, default="")
    #  Si hubo que corregir lo decidido. Es la señal mas valiosa que produce esta
    #  tabla, y la que mas se pierde si no se guarda en el momento.
    correccion = models.TextField(blank=True, default="")

    class Meta:
        db_table = "operaciones_decision_supervisor"
        ordering = ["-decidida_en"]
        indexes = [
            models.Index(fields=["org", "-decidida_en"]),
            models.Index(fields=["org", "tipo", "resultado"]),
            models.Index(fields=["situacion", "-decidida_en"]),
        ]
        constraints = [
            #  Una decision tiene que ser SOBRE algo.
            models.CheckConstraint(
                condition=(models.Q(situacion__isnull=False)
                           | models.Q(propuesta__isnull=False)),
                name="decision_con_objeto"),
            #  Una decision HUMANA necesita su persona. Sin esto, cualquier
            #  camino podria registrar decisiones sin dueño y las metricas de
            #  aceptacion dejarian de significar algo.
            models.CheckConstraint(
                condition=(models.Q(tipo="expiro")
                           | models.Q(actor__isnull=False)),
                name="decision_humana_con_actor"),
            #  Un resultado cerrado necesita decir COMO se supo.
            models.CheckConstraint(
                condition=(~models.Q(resultado__in=["funciono", "no_funciono",
                                                    "parcial"])
                           | ~models.Q(resultado_evidencia="")),
                name="decision_resultado_con_evidencia"),
        ]

    def __str__(self):
        return f"{self.tipo} {self.recomendacion[:40]} -> {self.resultado}"


class NivelAutonomia(BaseModel):
    """
    El nivel 0-4 del Supervisor para UNA empresa. Historial append-only.

    EL VIGENTE ES LA FILA MAS RECIENTE, y no hay columna 'vigente'
    -------------------------------------------------------------
    Una bandera 'vigente' obliga a dos escrituras por cambio --apagar la vieja y
    encender la nueva-- y dos escrituras son una carrera. Con el historial puro,
    el vigente se lee ordenando por fecha y el cambio es UN insert.

    SIN FILA, NIVEL 0. FAIL-CLOSED
    ------------------------------
    Una empresa sin ninguna fila esta en OBSERVAR. No se hereda un default
    permisivo desde el codigo: desplegar no puede conceder alcance.

    LOS CINCO NIVELES NO SE REDEFINEN AQUI
    --------------------------------------
    Son los de 'PropuestaSupervisor.NIVELES', que ya estaban declarados y en uso.
    Copiarlos crearia dos vocabularios que se desincronizan -- el mismo error que
    el proyecto ya cometio con la regla de admin escrita nueve veces.

    Y EL SUPERVISOR NO PUEDE SUBIRSELO
    ----------------------------------
    'actor' es obligatorio por restriccion de la base. Un cambio de nivel sin
    persona no se puede escribir, asi que no existe camino --ni un llamador nuevo
    por descuido-- para que la IA se amplie el alcance.
    """

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="niveles_autonomia_supervisor")
    #  El rango lo fija la restriccion de abajo contra los niveles declarados en
    #  'PropuestaSupervisor'. No se repite la lista de etiquetas.
    nivel = models.PositiveSmallIntegerField()
    nivel_anterior = models.PositiveSmallIntegerField(null=True, blank=True)

    actor = models.ForeignKey(Profile, on_delete=models.PROTECT,
                              related_name="cambios_de_autonomia")
    cambiado_en = models.DateTimeField()
    #  Por que se cambio, y con que evidencia. Los dos obligatorios: subir el
    #  alcance de un sistema que actua sobre la red de clientes sin decir por que
    #  es exactamente lo que no debe poder hacerse en silencio.
    motivo = models.TextField()
    criterios = models.TextField()

    class Meta:
        db_table = "operaciones_nivel_autonomia"
        ordering = ["-cambiado_en"]
        indexes = [
            models.Index(fields=["org", "-cambiado_en"]),
        ]
        constraints = [
            #  0 a 4, los niveles que existen. Un 7 seria un alcance que nadie
            #  definio.
            models.CheckConstraint(condition=models.Q(nivel__lte=4),
                                   name="autonomia_nivel_en_rango"),
            models.CheckConstraint(
                condition=models.Q(nivel_anterior__isnull=True)
                | models.Q(nivel_anterior__lte=4),
                name="autonomia_nivel_anterior_en_rango"),
            models.CheckConstraint(condition=~models.Q(motivo=""),
                                   name="autonomia_con_motivo"),
            models.CheckConstraint(condition=~models.Q(criterios=""),
                                   name="autonomia_con_criterios"),
        ]

    def __str__(self):
        return f"nivel {self.nivel} ({self.org_id})"
