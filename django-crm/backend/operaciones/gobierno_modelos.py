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
    #  P8.2 (05/10/2026). Ni si ni no: la recomendacion no venia al caso.
    #  Se distingue de RECHAZO a proposito -- rechazar es decir 'no hagas
    #  esto', y 'no aplicable' es decir 'esto no era una pregunta'. Medir
    #  los dos juntos haria que una propuesta fuera de contexto contara
    #  como un error de criterio del Supervisor, que es otra cosa.
    NO_APLICABLE = "no_aplicable"
    #  08/10/2026. La ejecuto el SISTEMA porque se cumplieron las condiciones
    #  que una persona autorizo de antemano -- hoy, cerrar un caso que el
    #  proveedor ya cerro y cuyo equipo el diagnostico optico encontro sano.
    #
    #  TIPO PROPIO Y NO 'ACEPTO', por el mismo motivo por el que 'EXPIRO' es
    #  tipo propio: nadie la miro. Contarla como una aceptacion humana inflaria
    #  la tasa de aceptacion del Supervisor con decisiones que el Supervisor se
    #  tomo solo, y esa tasa existe justamente para medir si acierta cuando una
    #  persona lo juzga.
    CERRO_SOLO = "cerro_solo"

    TODOS = (ACEPTO, RECHAZO, MODIFICO, POSPUSO, EXPIRO,
             NO_APLICABLE, CERRO_SOLO)
    #  'no_aplicable' SI es humano --lo dice una persona-- pero NO entra en
    #  la tasa de aceptacion: no es ni aceptar ni rechazar.
    HUMANOS = (ACEPTO, RECHAZO, MODIFICO, POSPUSO, NO_APLICABLE)
    #  Sobre estos se mide si el Supervisor acerto. 'pospuso' y
    #  'no_aplicable' no son un veredicto sobre su criterio.
    VEREDICTO = (ACEPTO, RECHAZO, MODIFICO)
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
    #  PROTECT. Esta fila es HISTORIA y no se puede perder por un borrado.
    #
    #  COMO SE LLEGO AQUI, en tres pasos y con la medicion de cada uno:
    #
    #  1. Era SET_NULL. Borrar una propuesta revisada dejaba esta fila con las
    #     dos referencias nulas y 'decision_con_objeto' reventaba el borrado con
    #     CheckViolation. Latente hasta P8.2, porque nadie escribia decisiones.
    #
    #  2. Se intento aflojar la restriccion para aceptar la 'recomendacion'
    #     copiada. 'test_28_una_decision_sin_objeto_se_rechaza' lo rechazo: P4
    #     ya habia decidido que una recomendacion suelta no alcanza.
    #
    #  3. Se puso CASCADE --si sin objeto la fila no debe existir, que se vaya
    #     con el objeto-- y eso resolvia la excepcion PERDIENDO la decision.
    #     Para una tabla de auditoria y aprendizaje operacional, perder la fila
    #     es peor que no poder borrar la propuesta.
    #
    #  PROTECT dice lo correcto: una propuesta con decision registrada NO se
    #  borra. Y no estorba, porque en produccion las propuestas no se borran --
    #  se aceptan, rechazan, modifican, expiran o cancelan, que son cambios de
    #  estado. Medido: el UNICO lugar del repositorio que las borra es la
    #  limpieza de una prueba con 'transaction=True'.
    propuesta = models.ForeignKey(
        "operaciones.PropuestaSupervisor", on_delete=models.PROTECT,
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
            #  La decision apunta a una situacion O a una propuesta. Las dos
            #  nulas, no.
            #
            #  P8.2 intento aflojarla --aceptar tambien una 'recomendacion'
            #  copiada-- y 'test_28_una_decision_sin_objeto_se_rechaza' la
            #  defendio: ese test crea una fila con recomendacion='x' y las
            #  dos referencias nulas, y exige IntegrityError. P4 ya habia
            #  decidido que una recomendacion suelta NO alcanza, asi que se
            #  revirtio y el problema real se arreglo donde estaba: el
            #  'on_delete' de 'propuesta', que dejaba la fila huerfana.
            models.CheckConstraint(
                condition=(models.Q(situacion__isnull=False)
                           | models.Q(propuesta__isnull=False)),
                name="decision_con_objeto"),
            #  Una decision HUMANA necesita su persona. Sin esto, cualquier
            #  camino podria registrar decisiones sin dueño y las metricas de
            #  aceptacion dejarian de significar algo.
            models.CheckConstraint(
                #  'expiro' y 'cerro_solo' son las dos decisiones del SISTEMA:
                #  una por vencimiento y la otra por cumplirse condiciones que
                #  una persona autorizo antes. Ninguna tiene actor, y las dos
                #  quedan fuera de 'HUMANOS' para que no contaminen la tasa de
                #  aceptacion. Cualquier otro tipo sin actor sigue prohibido.
                condition=(models.Q(tipo__in=["expiro", "cerro_solo"])
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


# =============================================================================
#  EL APRENDIZAJE  --  lo que se supo DESPUES, y quien lo supo
# =============================================================================

class TipoAprendizaje:
    """
    Que clase de leccion deja un caso. Lista cerrada.

    Son las ocho que el bloque nombra, y cada una existe porque mide algo que
    las otras no:

      * RECOMENDACION_CONFIRMADA  se acepto Y despues se comprobo que servia.
      * RECHAZO_ERRADO            se rechazo y el problema se confirmo igual.
                                  Es la mas valiosa del conjunto: la unica que
                                  dice que el Supervisor tenia razon y no se le
                                  creyo.
      * FALSO_POSITIVO            detecto una situacion y no habia problema.
      * OMISION                   habia problema y NO habia situacion. El falso
                                  negativo.
      * CORRELACION_CORRECTA      agrupo bien.
      * CORRELACION_INCORRECTA    agrupo cosas que no iban juntas.
      * REINCIDENCIA              volvio a pasar en el mismo sitio.
      * CORRECCION_HUMANA         una persona cambio la recomendacion.
    """

    RECOMENDACION_CONFIRMADA = "recomendacion_confirmada"
    RECHAZO_ERRADO = "rechazo_errado"
    FALSO_POSITIVO = "falso_positivo"
    OMISION = "omision"
    CORRELACION_CORRECTA = "correlacion_correcta"
    CORRELACION_INCORRECTA = "correlacion_incorrecta"
    REINCIDENCIA = "reincidencia"
    CORRECCION_HUMANA = "correccion_humana"

    TODOS = (RECOMENDACION_CONFIRMADA, RECHAZO_ERRADO, FALSO_POSITIVO,
             OMISION, CORRELACION_CORRECTA, CORRELACION_INCORRECTA,
             REINCIDENCIA, CORRECCION_HUMANA)
    ETIQUETAS = tuple((t, t.replace("_", " ").capitalize()) for t in TODOS)

    #  Los que cuentan CONTRA el Supervisor al medir precision.
    EN_CONTRA = (FALSO_POSITIVO, OMISION, CORRELACION_INCORRECTA)
    #  Los que cuentan A FAVOR.
    A_FAVOR = (RECOMENDACION_CONFIRMADA, RECHAZO_ERRADO, CORRELACION_CORRECTA)


class OrigenAprendizaje:
    """
    QUIEN concluyo. Y el Supervisor NO esta en la lista, a proposito.

    Es la regla del bloque: no permitir que el Supervisor escriba su propio
    resultado para declararse correcto. Si 'supervisor' fuera un origen valido,
    esta seria una tabla donde el evaluado se pone la nota, y toda metrica
    construida encima mediria su opinion de si mismo.

    Los tres que si valen:

      PERSONA              alguien lo dijo, y queda su nombre.
      VERIFICACION         salio de una verificacion registrada de la situacion.
      EVIDENCIA_OPERATIVA  salio de un hecho operativo comprobable: una ONT que
                           volvio, un caso que se cerro con causa.
    """

    PERSONA = "persona"
    VERIFICACION = "verificacion"
    EVIDENCIA_OPERATIVA = "evidencia_operativa"

    TODOS = (PERSONA, VERIFICACION, EVIDENCIA_OPERATIVA)
    ETIQUETAS = tuple((o, o.replace("_", " ").capitalize()) for o in TODOS)


class AprendizajeSupervisor(BaseModel):
    """
    Una leccion con su evidencia, su fecha y quien la saco. APPEND-ONLY.

    POR QUE UNA TABLA Y NO CAMPOS EN LAS QUE YA HAY
    -----------------------------------------------
    Porque un aprendizaje no pertenece a una propuesta ni a una situacion: puede
    nacer de las dos, de ninguna, o de una tercera cosa -- un ticket que
    aparecio despues y mostro que no habia ninguna situacion abierta. Y porque
    son MUCHOS por objeto: la misma situacion puede dejar una leccion de
    correlacion, otra de reincidencia y otra de correccion humana. Como campos
    serian columnas casi siempre vacias, y una sola por tipo.

    No reemplaza nada. 'PropuestaSupervisor' sigue siendo la propuesta,
    'DecisionSupervisor' sigue siendo la decision con su desenlace, y
    'SituacionOperativa' sigue siendo la situacion. Esto apunta a ellas.

    POR QUE APPEND-ONLY
    -------------------
    Mismo motivo que 'SituacionEvento': una leccion que se puede reescribir no
    es historia, es una opinion actual. Si la conclusion cambia, se agrega otra
    fila que lo diga -- y entonces se puede ver que alguien cambio de opinion,
    que es justo el dato que se perderia.

    LO QUE ESTA TABLA NO AFIRMA
    ---------------------------
    Que la conclusion sea verdad. Afirma que ALGUIEN concluyo eso, con esa
    evidencia, ese dia. 'confianza' viaja para que una conclusion floja no se
    lea igual que una firme: es lo que permite no presentar una conclusion
    inferida como un hecho.
    """

    class NoSeReescribe(Exception):
        """Un aprendizaje no se edita ni se borra. Se agrega otro."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="aprendizajes_supervisor")
    tipo = models.CharField(max_length=32, choices=TipoAprendizaje.ETIQUETAS)
    origen = models.CharField(max_length=24,
                              choices=OrigenAprendizaje.ETIQUETAS)

    #  A QUE se refiere. Los tres son opcionales por separado y obligatorios en
    #  conjunto: una leccion que no apunta a nada no se puede volver a leer.
    situacion = models.ForeignKey(
        "operaciones.SituacionOperativa", on_delete=models.CASCADE,
        null=True, blank=True, related_name="aprendizajes")
    #  PROTECT las dos, por el mismo motivo que en 'DecisionSupervisor': una
    #  leccion es historia. Si se pudiera borrar la propuesta o la decision que
    #  la originaron, el aprendizaje se iria con ellas -- y una tabla de
    #  aprendizaje que se puede vaciar borrando otra cosa no mide nada.
    #
    #  La OMISION no se ve afectada: nace sin objeto a proposito y por eso esta
    #  exenta en 'aprendizaje_con_objeto'. A esa no la arrastra ningun borrado.
    propuesta = models.ForeignKey(
        "operaciones.PropuestaSupervisor", on_delete=models.PROTECT,
        null=True, blank=True, related_name="aprendizajes")
    decision = models.ForeignKey(
        "operaciones.DecisionSupervisor", on_delete=models.PROTECT,
        null=True, blank=True, related_name="aprendizajes")

    conclusion = models.TextField(
        help_text="Que se aprendio, en una frase que se entienda sola.")
    #  Obligatoria por restriccion de base. Sin evidencia, "aprendimos que..."
    #  es una afirmacion sin respaldo y la tabla entera perderia sentido.
    evidencia = models.TextField(
        help_text="En que se basa. Sin esto la conclusion es una opinion.")
    confianza = models.CharField(max_length=16, default="media")

    #  Quien. Obligatorio cuando el origen es una persona: una leccion humana
    #  sin autor no se puede repreguntar.
    actor = models.ForeignKey(Profile, on_delete=models.PROTECT,
                              null=True, blank=True,
                              related_name="aprendizajes_registrados")
    registrado_en = models.DateTimeField()

    #  Los numeros que P8.3 va a necesitar y que no tienen columna propia:
    #  {'afectados_propuestos': 12, 'afectados_confirmados': 10} para la calidad
    #  de correlacion; {'situacion_anterior': '<uuid>'} para la reincidencia.
    #  Van en JSON y no en columnas porque cada tipo necesita otros, y columnas
    #  por tipo serian siete columnas vacias en cada fila.
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "operaciones_aprendizaje_supervisor"
        ordering = ["-registrado_en"]
        indexes = [
            models.Index(fields=["org", "tipo", "registrado_en"]),
            models.Index(fields=["org", "situacion"]),
        ]
        constraints = [
            #  Apunta a algo... SALVO una omision.
            #
            #  Esto lo corrigio una prueba: la primera version exigia
            #  situacion, propuesta o decision SIEMPRE, y con eso el caso
            #  principal de un falso negativo era imposible de registrar --
            #  una omision existe JUSTAMENTE porque no habia situacion a la
            #  que apuntar. Lo que la sostiene es su evidencia (obligatoria
            #  por la restriccion de abajo) y lo que diga 'datos': el
            #  ticket, el PON, la hora.
            models.CheckConstraint(
                condition=(models.Q(situacion__isnull=False)
                           | models.Q(propuesta__isnull=False)
                           | models.Q(decision__isnull=False)
                           | models.Q(tipo="omision")),
                name="aprendizaje_con_objeto"),
            #  Evidencia obligatoria, en la BASE y no solo en el servicio: el
            #  otro camino se puede saltear llamando al ORM directo.
            models.CheckConstraint(
                condition=~models.Q(evidencia=""),
                name="aprendizaje_exige_evidencia"),
            #  Una leccion de una persona lleva su nombre.
            models.CheckConstraint(
                condition=(~models.Q(origen="persona")
                           | models.Q(actor__isnull=False)),
                name="aprendizaje_humano_con_actor"),
        ]

    def __str__(self):
        return f"[{self.tipo}] {self.conclusion[:60]}"

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise self.NoSeReescribe(
                "un aprendizaje no se edita: si la conclusion cambio, se "
                "agrega otro que lo diga, y asi queda el cambio de opinion")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise self.NoSeReescribe(
            "un aprendizaje no se borra: lo que se aprendio, se aprendio")
