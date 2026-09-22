# -*- coding: utf-8 -*-
"""
================================================================================
 OPERACIONES  --  M02 (lo que falta hacer), M03 (cuando y quien), M09 (que
                  recomienda el Supervisor)
================================================================================

POR QUE UN MODULO NUEVO Y NO UNO PARALELO
-----------------------------------------
Esto es el CRM de Rapilink, no otro CRM. El modulo sigue exactamente el patron
con el que ya se sumaron 'campo' y 'solicitudes': comparte Org, Profile, Case y
OrdenTrabajo, no los duplica, y no tiene su propia nocion de cliente ni de
caso. Se agrupa aparte para que la superficie nueva se pueda revisar --y
revertir-- de una pieza.

LO QUE SE REUTILIZA, Y NO SE VUELVE A CREAR
-------------------------------------------
    campo.OrdenTrabajo        el desplazamiento fisico. No se crea otra OT.
    campo.AsignacionTrabajo   la cuadrilla. Ya soporta N personas con rol.
    campo.OrdenTrabajo.programada_para   el "cuando" vigente de una orden.
    cases.Case                el problema del cliente.
    common.Activity           la bitacora. Aqui se ESCRIBE, no se reemplaza.
    business_hours.BusinessCalendar      la jornada de la empresa.

LO QUE SE AGREGA, Y POR QUE NO EXISTIA
--------------------------------------
    ActividadOperativa     lo que FALTA hacer. 'Activity' registra lo que ya
                           paso y no tiene estado, responsable ni vencimiento;
                           'tasks.Task' esta vacia y es codigo vendorizado de
                           terceros. Medido el 15/09/2026: Activity 516 filas
                           vivas, Task/Board 0.
    DisponibilidadTecnico  quien puede trabajar y cuando. No habia NADA:
                           BusinessCalendar da el horario de la EMPRESA, no el
                           de cada persona.
    ProgramacionSemanal    el plan. Sin un objeto "plan" no hay contra que
                           comparar lo que pasa en el dia.
    ProgramacionOrden      una linea del plan. NO reemplaza a
                           'programada_para': el plan dice lo que se penso, el
                           campo de la orden dice lo que rige hoy.
    NovedadOperativa       lo que obligo a cambiar el plan. Es lo que hace que
                           reprogramar deje rastro en vez de pisar una fecha.
    PropuestaSupervisor    lo que la IA recomienda. Ver su docstring sobre por
                           que no es asistente.acciones_propuestas.

LOS DOS EJES DE ESTADO  --  ejecutado != validado != cerrado
------------------------------------------------------------
No se inventan: se copian de campo.OrdenTrabajo, que ya los tiene y ya los usa
en produccion. 'estado_operativo' contesta que se hizo; 'estado_validacion',
si alguien con criterio lo dio por bueno; 'vuelta', cuantas veces se presento.
Un solo eje obligaria a elegir entre "completada" y "pendiente de validar", y
la realidad es que son las dos cosas a la vez.
================================================================================
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


# =============================================================================
#  EJE DE VALIDACION  --  compartido, y literal al de campo.OrdenTrabajo
# =============================================================================
#  Los mismos seis valores, con las mismas etiquetas. Que las dos mitades del
#  sistema se lean igual vale mas que cualquier mejora de nombres: quien mira
#  una orden y una actividad el mismo dia no tiene que traducir.

SIN_EVALUAR = "sin_evaluar"
VALIDACION_PENDIENTE = "pendiente"
APROBABLE = "aprobable"
REQUIERE_CORRECCION = "requiere_correccion"
REQUIERE_REVISION = "requiere_revision"
APROBADO = "aprobado"

ESTADOS_VALIDACION = (
    (SIN_EVALUAR, "Sin evaluar"),
    (VALIDACION_PENDIENTE, "Pendiente de validación"),
    (APROBABLE, "Aprobable"),
    (REQUIERE_CORRECCION, "Requiere corrección"),
    (REQUIERE_REVISION, "Requiere revisión humana"),
    (APROBADO, "Aprobado"),
)


# =============================================================================
#  M02  --  ACTIVIDAD OPERATIVA
# =============================================================================


class ActividadOperativa(BaseModel):
    """
    Lo que FALTA hacer: una tarea, un pendiente, un compromiso, un handoff.

    QUE NO ES, Y LA DISTINCION IMPORTA
    ----------------------------------
      Case          el problema del cliente. Una actividad puede colgar de un
                    caso, pero cerrar la actividad no cierra el caso.
      Ticket        el espejo del problema en el sistema del ISP. Es externo.
      OrdenTrabajo  un desplazamiento fisico. Un caso puede necesitar cero,
                    una o tres; una actividad no mueve a nadie de lugar.
      Activity      lo que YA paso, en pasado, sin estado ni vencimiento.
      Incidencia    una falla de red que afecta a varios. La detecta el motor.
      Bloqueo       no es una entidad: es un ESTADO de esta, con su motivo.
      Alerta        una señal derivada, que se calcula y no se escribe.
      Escalamiento  pasar a otro nivel. Aqui es un estado, no un objeto.

    NUEVE TIPOS, UNA SOLA TABLA
    ---------------------------
    Un compromiso y una solicitud de informacion son el mismo objeto con
    distinto 'tipo': responsable, fecha objetivo, estado, dependencia. Crear
    nueve entidades seria el error simetrico al de meter todo en Activity.
    """

    TAREA = "tarea"
    PENDIENTE_T = "pendiente"
    COMPROMISO = "compromiso"
    SEGUIMIENTO = "seguimiento"
    SOLICITUD_INFORMACION = "solicitud_informacion"
    DEPENDENCIA = "dependencia"
    HANDOFF = "handoff"
    SOPORTE = "soporte"
    CORRECCION = "correccion"
    TIPOS = (
        (TAREA, "Tarea"),
        (PENDIENTE_T, "Pendiente"),
        (COMPROMISO, "Compromiso"),
        (SEGUIMIENTO, "Seguimiento"),
        (SOLICITUD_INFORMACION, "Solicitud de información"),
        (DEPENDENCIA, "Dependencia"),
        (HANDOFF, "Handoff"),
        (SOPORTE, "Soporte"),
        (CORRECCION, "Corrección"),
    )

    PENDIENTE = "pendiente"
    EN_GESTION = "en_gestion"
    EN_ESPERA = "en_espera"
    BLOQUEADA = "bloqueada"
    ESCALADA = "escalada"
    COMPLETADA = "completada"
    CANCELADA = "cancelada"
    # 'validacion_pendiente' NO esta aca a proposito. "Completada" y "falta
    # validarla" son dos ejes a la vez, no dos valores del mismo: con un solo
    # eje hay que elegir, y se pierde poder decir "completada + requiere
    # correccion", que es el caso real que la devolucion produce.
    ESTADOS_OPERATIVOS = (
        (PENDIENTE, "Pendiente"),
        (EN_GESTION, "En gestión"),
        (EN_ESPERA, "En espera"),
        (BLOQUEADA, "Bloqueada"),
        (ESCALADA, "Escalada"),
        (COMPLETADA, "Completada"),
        (CANCELADA, "Cancelada"),
    )

    # Estados en los que la actividad ya no avanza sola. Los usa el Supervisor
    # para no proponer sobre algo que nadie va a mover.
    ESTADOS_FINALES = (COMPLETADA, CANCELADA)

    # =========================================================================
    #  ESCALAMIENTO  --  paso M05-B
    # =========================================================================
    #  'escalada' ya era un estado. Lo que faltaba es a QUIEN, CUANDO y CON QUE
    #  NIVEL: sin eso, "escalada" dice que alguien pidio ayuda y no dice a
    #  quien, asi que nadie sabe si la pidio bien.
    #
    #  EL NIVEL NO ES GRAVEDAD. Describe la RUTA de gestion -- a que instancia
    #  se llevo. La gravedad operacional vive en 'NovedadOperativa.impacto', y
    #  son cosas distintas a proposito: una incidencia de impacto bajo puede
    #  necesitar nivel 3 porque solo esa instancia puede autorizarla, y una
    #  critica puede resolverse en nivel 1 si quien esta ahi puede hacerlo.
    #  Tampoco es culpa, ni sancion, ni desempeño de nadie.
    #
    #  Tres niveles y no mas: es la escala minima que distingue "mi supervisor
    #  directo" de "la instancia que decide" de "fuera de operaciones". Agregar
    #  un cuarto sin una ruta real detras seria inventar organigrama.
    NIVEL_1 = "nivel_1"
    NIVEL_2 = "nivel_2"
    NIVEL_3 = "nivel_3"
    NIVELES_ESCALAMIENTO = (
        (NIVEL_1, "Nivel 1"),
        (NIVEL_2, "Nivel 2"),
        (NIVEL_3, "Nivel 3"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="actividades_operativas"
    )
    tipo = models.CharField(max_length=32, choices=TIPOS, default=TAREA)
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, default="")

    estado_operativo = models.CharField(
        max_length=32, choices=ESTADOS_OPERATIVOS, default=PENDIENTE
    )
    estado_validacion = models.CharField(
        max_length=32, choices=ESTADOS_VALIDACION, default=SIN_EVALUAR
    )
    vuelta = models.PositiveIntegerField(
        default=1,
        help_text="Presentación a validación. Sube con cada devolución.",
    )

    responsable = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actividades_operativas",
        help_text="Puede estar vacío: una actividad sin responsable es una señal, no un error.",
    )

    # Origen desacoplado, sin GenericForeignKey -- mismo patron que
    # campo.OrdenTrabajo. Evita una FK por cada cosa de la que puede colgar y
    # no ata el borrado de un caso al de sus actividades.
    origen_tipo = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="case, orden_trabajo, conversacion, solicitud, manual",
    )
    origen_id = models.CharField(
        max_length=128, blank=True, default="", help_text="Id o número del origen"
    )

    vence_en = models.DateTimeField(null=True, blank=True)

    depende_de = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dependientes",
        help_text="Esta actividad no puede avanzar hasta que la otra termine.",
    )

    motivo_bloqueo = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Obligatorio cuando el estado es 'bloqueada'. Un bloqueo sin causa no sirve.",
    )

    #  --- M05-B: a quien, cuando y con que nivel se escalo ---
    #  Los tres son NULL/vacio mientras no haya escalamiento, y las actividades
    #  que ya existan se quedan asi: no se inventa un destinatario, una fecha
    #  ni un nivel retroactivos para una actividad que se escalo cuando el
    #  sistema todavia no los registraba.
    escalado_a = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalamientos_recibidos",
        help_text="A quién se escaló. Obligatorio al escalar: un escalamiento "
                  "sin destinatario no llega a nadie.",
    )
    escalado_en = models.DateTimeField(
        null=True, blank=True,
        help_text="Cuándo se escaló. Null si nunca se escaló.",
    )
    nivel_escalamiento = models.CharField(
        max_length=16, choices=NIVELES_ESCALAMIENTO, blank=True, default="",
        help_text="Ruta de gestión a la que se llevó. NO es gravedad ni culpa: "
                  "la gravedad operacional vive en NovedadOperativa.impacto.",
    )

    #  LAS DOS FECHAS QUE SON HECHOS, NO DERIVACIONES  --  M02
    #  -------------------------------------------------------
    #  'created_at' y 'updated_at' ya vienen de BaseModel, pero "cuando se
    #  termino" y "cuando se valido" no se pueden leer de ahi: 'updated_at' se
    #  mueve con cualquier cambio posterior. Reconstruirlas desde la auditoria
    #  obligaria a recorrer common.Activity para responder algo tan basico como
    #  "que se completo esta semana".
    #
    #  Nulas mientras no ocurra el hecho. Nunca se rellenan con la fecha de
    #  otra cosa: una actividad sin completar no tiene fecha de completada.
    completado_en = models.DateTimeField(
        null=True, blank=True,
        help_text="Cuando se marco completada. Null = todavia no.",
    )
    validado_en = models.DateTimeField(
        null=True, blank=True,
        help_text="Cuando se resolvio su validacion. Null = sin resolver.",
    )

    class Meta:
        db_table = "operaciones_actividad"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["org", "estado_operativo", "vence_en"]),
            models.Index(fields=["org", "responsable", "estado_operativo"]),
            models.Index(fields=["org", "origen_tipo", "origen_id"]),
        ]
        constraints = [
            # Un bloqueo sin motivo es exactamente lo que impide que el
            # Supervisor distinga "falta material" de "no sabemos". La base lo
            # exige para que no dependa de que alguien se acuerde.
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado_operativo="bloqueada")
                    | ~models.Q(motivo_bloqueo="")
                ),
                name="actividad_bloqueada_exige_motivo",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.get_tipo_display()}] {self.titulo}"

    def clean(self):
        # Una actividad que depende de si misma nunca avanza, y el ciclo mas
        # corto es el mas facil de crear por error desde un formulario.
        if self.depende_de_id and self.depende_de_id == self.id:
            raise ValidationError({"depende_de": "Una actividad no puede depender de sí misma."})
        if self.estado_operativo == self.BLOQUEADA and not self.motivo_bloqueo.strip():
            raise ValidationError({"motivo_bloqueo": "Un bloqueo necesita su causa."})

    @property
    def esta_vencida(self) -> bool:
        """Pasó su fecha objetivo y todavía no terminó."""
        from django.utils import timezone

        if not self.vence_en or self.estado_operativo in self.ESTADOS_FINALES:
            return False
        return self.vence_en < timezone.now()

    @property
    def bloqueada_por_dependencia(self) -> bool:
        """Espera a otra actividad que todavía no terminó."""
        if not self.depende_de_id:
            return False
        return self.depende_de.estado_operativo not in self.ESTADOS_FINALES


# =============================================================================
#  M03  --  DISPONIBILIDAD, PROGRAMACION Y NOVEDADES
# =============================================================================


class DisponibilidadTecnico(BaseModel):
    """
    Una franja en la que una persona puede (o no puede) trabajar.

    POR QUE HACIA FALTA ALGO NUEVO
    ------------------------------
    business_hours.BusinessCalendar define el horario de la EMPRESA, y el SLA
    ya lo respeta. No dice nada de una persona concreta: quien esta de
    vacaciones, quien entra al mediodia, quien cubre otra zona el jueves.
    Medido el 15/09/2026: no existia ninguna estructura de disponibilidad.

    LA CAPACIDAD NO SE GUARDA ACA, NI EN NINGUN LADO
    ------------------------------------------------
    Un numero de "capacidad" depende de la disponibilidad, de la carga ya
    asignada, de la duracion estimada del tipo de trabajo, de la zona y de los
    bloqueos. Guardarlo es garantizar que quede viejo la proxima vez que
    cualquiera de esos cinco cambie. Se calcula cuando se necesita, a partir
    de estas franjas y de las ordenes ya programadas -- ver
    operaciones/supervisor/senales.py.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="disponibilidades"
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="disponibilidades"
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    # False = la franja es una AUSENCIA declarada, no un turno. Se guarda en la
    # misma tabla porque la pregunta que se le hace es la misma ("¿esta esta
    # persona disponible el jueves a las 10?") y separarlas obligaria a
    # consultar dos tablas para contestarla una vez.
    disponible = models.BooleanField(default=True)
    motivo = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Obligatorio cuando disponible=False: vacaciones, permiso, incapacidad.",
    )
    zona = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Zona que cubre en esa franja. Vacío = cualquiera.",
    )

    class Meta:
        db_table = "operaciones_disponibilidad"
        ordering = ["fecha", "hora_inicio"]
        indexes = [
            models.Index(fields=["org", "fecha", "profile"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hora_fin__gt=models.F("hora_inicio")),
                name="disponibilidad_franja_valida",
            ),
            models.CheckConstraint(
                condition=models.Q(disponible=True) | ~models.Q(motivo=""),
                name="ausencia_exige_motivo",
            ),
        ]

    def __str__(self) -> str:
        que = "disponible" if self.disponible else f"ausente ({self.motivo})"
        return f"{self.profile_id} {self.fecha} {self.hora_inicio}-{self.hora_fin}: {que}"


class ProgramacionSemanal(BaseModel):
    """
    El plan de una semana. Es la base; la programación diaria lo modifica.

    POR QUE EXISTE UN OBJETO "PLAN"
    -------------------------------
    La regla operativa es que la semanal es la base y la diaria NO se
    reconstruye desde cero: se modifica por novedades. Sin un objeto plan no
    hay contra que comparar lo que pasa el martes, y "se modifico" deja de ser
    una afirmacion verificable.
    """

    BORRADOR = "borrador"
    PUBLICADA = "publicada"
    CERRADA = "cerrada"
    ESTADOS = (
        (BORRADOR, "Borrador"),
        (PUBLICADA, "Publicada"),
        (CERRADA, "Cerrada"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="programaciones_semanales"
    )
    semana_inicio = models.DateField(help_text="Lunes de la semana que planifica")
    estado = models.CharField(max_length=16, choices=ESTADOS, default=BORRADOR)
    publicada_en = models.DateTimeField(null=True, blank=True)
    publicada_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="programaciones_publicadas",
    )
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "operaciones_programacion_semanal"
        ordering = ["-semana_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "semana_inicio"],
                name="unique_programacion_semana_por_org",
            ),
        ]

    def __str__(self) -> str:
        return f"Semana del {self.semana_inicio} ({self.get_estado_display()})"


class ProgramacionOrden(BaseModel):
    """
    Una línea del plan semanal: esta orden, este día, a esta hora.

    NO REEMPLAZA A OrdenTrabajo.programada_para  --  y la diferencia es el
    punto entero
    ----------------------------------------------------------------------
        ProgramacionOrden   lo que se PLANIFICO el viernes anterior.
        OT.programada_para  lo que RIGE ahora mismo.

    Cuando una novedad mueve una orden, lo que cambia es 'programada_para' de
    la orden; esta linea queda como estaba, y la NovedadOperativa guarda el
    antes y el despues. Asi "se reprogramo" se puede demostrar en vez de
    deducir, y el plan original no se pisa en silencio.

    Medido el 15/09/2026: 'programada_para' esta en 0 de 3 ordenes -- el campo
    existe y nunca se uso, asi que aca no se esta reemplazando nada vivo.
    """

    PLANIFICADA = "planificada"
    CONFIRMADA = "confirmada"
    REPROGRAMADA = "reprogramada"
    CANCELADA = "cancelada"
    ESTADOS = (
        (PLANIFICADA, "Planificada"),
        (CONFIRMADA, "Confirmada"),
        (REPROGRAMADA, "Reprogramada"),
        (CANCELADA, "Cancelada"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="lineas_programacion"
    )
    programacion = models.ForeignKey(
        ProgramacionSemanal, on_delete=models.CASCADE, related_name="lineas"
    )
    # La orden es la de campo. No se crea otra: se la referencia.
    orden = models.ForeignKey(
        "campo.OrdenTrabajo", on_delete=models.CASCADE, related_name="lineas_programacion"
    )
    dia = models.DateField()
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)
    zona = models.CharField(max_length=128, blank=True, default="")
    prioridad = models.PositiveSmallIntegerField(
        default=50, help_text="Menor corre antes. 0 = lo más urgente."
    )
    secuencia = models.PositiveSmallIntegerField(
        default=0,
        help_text="Orden dentro de la jornada. NO es una ruta optimizada: es el orden propuesto.",
    )
    estado = models.CharField(max_length=16, choices=ESTADOS, default=PLANIFICADA)

    # El tipo de trabajo NO se copia: sale de orden.tipo_trabajo_version. Un
    # dato duplicado es un dato que se desincroniza.

    class Meta:
        db_table = "operaciones_programacion_orden"
        ordering = ["dia", "secuencia"]
        indexes = [
            models.Index(fields=["org", "dia"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["programacion", "orden"],
                name="unique_orden_por_programacion",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.dia} #{self.secuencia} -> OT {self.orden_id}"


class NovedadOperativa(BaseModel):
    """
    Lo que obligó a cambiar el plan. Es lo que hace auditable una reprogramación.

    LA LISTA DE CAUSAS ES CERRADA, Y HAY UNA QUE NO ESTA
    ----------------------------------------------------
    No existe 'incumplimiento_de_persona', y su ausencia es deliberada. Una
    demora puede ser un bloqueo, un material que no llego, una dependencia, una
    ausencia, un cambio de prioridad o un dato mal cargado. Con los datos de
    hoy no hay forma de distinguir ninguna de esas de un incumplimiento -- y el
    costo de equivocarse lo paga una persona real.

    'demora_sin_causa_registrada' es lo que se usa cuando solo hay fechas. Su
    nombre dice exactamente lo que se sabe y nada mas.
    """

    AUSENCIA = "ausencia"
    BLOQUEO = "bloqueo"
    FALTA_MATERIAL = "falta_material"
    DEPENDENCIA = "dependencia"
    REPROGRAMACION = "reprogramacion"
    CAMBIO_PRIORIDAD = "cambio_de_prioridad"
    DATO_INCOMPLETO = "dato_incompleto"
    DEMORA_SIN_CAUSA = "demora_sin_causa_registrada"
    TIPOS = (
        (AUSENCIA, "Ausencia"),
        (BLOQUEO, "Bloqueo"),
        (FALTA_MATERIAL, "Falta de material"),
        (DEPENDENCIA, "Dependencia pendiente"),
        (REPROGRAMACION, "Reprogramación"),
        (CAMBIO_PRIORIDAD, "Cambio de prioridad"),
        (DATO_INCOMPLETO, "Dato incompleto"),
        (DEMORA_SIN_CAUSA, "Demora sin causa registrada"),
    )

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="novedades")
    tipo = models.CharField(max_length=40, choices=TIPOS)
    descripcion = models.TextField(blank=True, default="")

    orden = models.ForeignKey(
        "campo.OrdenTrabajo",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="novedades",
    )
    actividad = models.ForeignKey(
        ActividadOperativa,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="novedades",
    )
    profile = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="novedades",
        help_text="A quién afecta, cuando aplica (una ausencia, por ejemplo).",
    )

    # El antes y el despues de una reprogramacion. Es lo que impide pisar la
    # fecha en silencio: la orden cambia, y aca queda de que a que.
    programada_anterior = models.DateTimeField(null=True, blank=True)
    programada_nueva = models.DateTimeField(null=True, blank=True)

    registrada_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="novedades_registradas",
    )

    # =========================================================================
    #  CICLO DE VIDA  --  paso M05-A
    # =========================================================================
    #  Una novedad registra QUE obligo a cambiar el plan. El ciclo de vida
    #  contesta otra cosa: si esa causa ya se atendio.
    #
    #  SON DOS PREGUNTAS DISTINTAS, Y ESA ES LA RAZON DE QUE ESTO SE PERSISTA.
    #  Desbloquear una actividad significa "ya no esta bloqueada"; NO significa
    #  "la causa se resolvio". Un tecnico puede desbloquear para seguir
    #  trabajando mientras el material sigue sin llegar. Si el estado se
    #  dedujera del estado de la actividad, el sistema daria por cerrada una
    #  causa que nadie atendio -- y despues mediria, escalaria y reportaria
    #  sobre esa mentira.
    #
    #  Por eso una incidencia solo se resuelve con la operacion explicita de
    #  'novedades.resolver()', que exige decir COMO se resolvio.
    ABIERTA = "abierta"
    EN_GESTION = "en_gestion"
    RESUELTA = "resuelta"
    ESTADOS = (
        (ABIERTA, "Abierta"),
        (EN_GESTION, "En gestión"),
        (RESUELTA, "Resuelta"),
    )
    #  Transiciones permitidas. No hay reapertura: no existe hoy en el
    #  proyecto y no se inventa aca.
    TRANSICIONES = {
        ABIERTA: (EN_GESTION, RESUELTA),
        EN_GESTION: (RESUELTA,),
        RESUELTA: (),
    }

    #  Afectacion OPERACIONAL. No es culpa, ni incumplimiento, ni desempeño de
    #  nadie: describe cuanto estorba esto para operar.
    #
    #  Escala propia y no la de PropuestaSupervisor porque alli 'impacto' es
    #  texto libre ("que se ve afectado si no se atiende"), no una escala.
    #  Reutilizarlo obligaria a convertir un CharField de 255 en un catalogo y
    #  cambiaria el significado de un campo que M09 ya usa.
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"
    IMPACTOS = (
        (BAJO, "Bajo"),
        (MEDIO, "Medio"),
        (ALTO, "Alto"),
        (CRITICO, "Crítico"),
    )

    estado = models.CharField(
        max_length=16, choices=ESTADOS, default=ABIERTA,
        help_text="Ciclo de vida de la incidencia. Solo cambia con una "
                  "operación explícita de operaciones/novedades.py.",
    )
    #  Vacio = nadie lo declaro. NO es 'bajo': no se inventa una afectacion
    #  que nadie midio, ni para las filas que ya existan.
    impacto = models.CharField(
        max_length=16, choices=IMPACTOS, blank=True, default="",
        help_text="Afectación operacional declarada. Vacío = sin declarar.",
    )
    resuelta_en = models.DateTimeField(
        null=True, blank=True,
        help_text="Cuándo se resolvió. Null mientras no lo esté.",
    )
    resolucion = models.TextField(
        blank=True, default="",
        help_text="Cómo se resolvió. Obligatoria al resolver: sin explicación "
                  "no se puede distinguir una causa atendida de una olvidada.",
    )
    #  Quien la resolvio. Se reutiliza Profile, que es la relacion que el
    #  modelo ya usa para 'registrada_por' -- no se inventa una entidad de
    #  responsable.
    resuelta_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="novedades_resueltas",
        help_text="Quién la resolvió. Null si se resolvió sin actor "
                  "identificado (una tarea de sistema, por ejemplo).",
    )

    class Meta:
        db_table = "operaciones_novedad"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["org", "tipo", "created_at"]),
            models.Index(fields=["org", "orden"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} ({self.created_at:%Y-%m-%d})"


# =============================================================================
#  M09  --  LA PROPUESTA DEL SUPERVISOR
# =============================================================================


class PropuestaSupervisor(BaseModel):
    """
    Lo que el Supervisor NOC IA RECOMIENDA. Nunca lo que hace.

    POR QUE NO ES asistente.acciones_propuestas
    -------------------------------------------
    Aquella tabla existe, funciona y esta en produccion (40 filas medidas el
    15/09/2026), pero su unidad es OTRA: una llamada a herramienta con su
    payload listo para ejecutar -- 'herramienta' y 'argumentos' son
    obligatorios ahi, y por eso una fila suya siempre es ejecutable.

    Una recomendacion del Supervisor puede no ser una llamada a nada:
    "priorizar el caso #123", "reprogramar la OT-125 a las 14:00". No tiene
    herramienta ni argumentos que poner. Forzar las dos cosas en una tabla
    obligaria a volver opcionales esos dos campos, y ahi se pierde la garantia
    que hoy hace confiable a la otra.

    Se relacionan en vez de fundirse: el dia que una propuesta aceptada deba
    ejecutarse, creara su fila alla y la referenciara desde aca. En esta etapa
    ese campo queda siempre nulo.

    Y las 40 filas de aquella tabla siguen siendo su BACKLOG HISTORICO: no se
    tocan, no se migran, no se reinterpretan como propuestas nuevas.

    SHADOW MODE: 'ejecutada' NO ES UN ESTADO POSIBLE
    ------------------------------------------------
    Aceptar una propuesta significa "el Jefe de Operaciones esta de acuerdo",
    no "se hizo". En esta etapa no hay ningun camino de ejecucion, y la
    ausencia del estado es lo que lo vuelve comprobable en vez de prometido.
    """

    # --- señales que el Supervisor sabe emitir hoy -------------------------
    # Solo las que los datos actuales sostienen. Deliberadamente NO hay una
    # señal de "incumplimiento de primera respuesta": 'first_response_at' esta
    # poblado en 4 de 165 casos (medido el 15/09/2026), asi que su ausencia no
    # prueba nada.
    CASO_ANTIGUO = "caso_abierto_antiguo"
    ACTIVIDAD_VENCIDA = "actividad_vencida"
    ACTIVIDAD_SIN_RESPONSABLE = "actividad_sin_responsable"
    ACTIVIDAD_BLOQUEADA = "actividad_bloqueada"
    COMPROMISO_POR_VENCER = "compromiso_por_vencer"
    DEPENDENCIA_PENDIENTE = "dependencia_pendiente"
    ORDEN_SIN_PROGRAMAR = "orden_sin_programar"
    ORDEN_EN_RIESGO = "orden_con_riesgo_operacional"
    #  Paso M09-D. Las dos quedaron definidas en M09-C.1 y entran ahora porque
    #  los datos que las sostienen ya existen:
    #    - 'programacion_sin_publicar' se demuestra con ProgramacionSemanal:
    #      estado, publicada_en y publicada_por. No se infiere nada.
    #    - 'dato_incompleto' es NIVEL 0, informativa, y NO es un comodin: solo
    #      se emite cuando hay un objeto concreto con un campo concreto que
    #      falta y se puede nombrar. Ver supervisor._ordenes_desincronizadas.
    PROGRAMACION_SIN_PUBLICAR = "programacion_sin_publicar"
    DATO_INCOMPLETO = "dato_incompleto"
    #  Paso M04-A. Riesgo TEMPORAL de una orden de trabajo, derivado del plazo
    #  que declara su tipo de trabajo (ver operaciones/sla.py).
    #
    #  El prefijo 'orden_' no es cosmetico: el SLA de 'cases.Case' es otro
    #  sistema, con sus propios campos, su pausa y su politica de escalamiento.
    #  Estas dos senales NO hablan de casos y no deben confundirse con
    #  'is_sla_resolution_breached'. Nombrarlas 'sla_vencido' a secas habria
    #  dejado dos cosas distintas con el mismo nombre.
    ORDEN_SLA_VENCIDO = "orden_sla_vencido"
    ORDEN_SLA_POR_VENCER = "orden_sla_por_vencer"
    #  Paso M05-A. Una incidencia que sigue ABIERTA o EN_GESTION. El estado
    #  sale de la columna, no de observar la actividad: desbloquear no
    #  resuelve nada.
    INCIDENCIA_SIN_RESOLVER = "incidencia_sin_resolver"
    #  Paso M05-B. Una actividad quedo en 'escalada' sin destinatario: es un
    #  dato FALTANTE, no una recomendacion de a quien escalarla. El Supervisor
    #  no elige destinatario -- no existe politica que se lo permita.
    ESCALAMIENTO_SIN_DESTINATARIO = "escalamiento_sin_destinatario"
    #  M09-N (22/09/2026). El caso figura CERRADO en el sistema del proveedor y
    #  sigue abierto en el CRM. Es una inconsistencia de SINCRONIZACION, y por
    #  eso es un tipo propio y no un 'caso_abierto_antiguo': medido en
    #  produccion, 78 de los 96 casos antiguos estaban asi, y tratarlos como
    #  casos desatendidos habria mandado a revisar clientes ya atendidos. No
    #  afirma incumplimiento de nadie, ni que el problema del cliente este
    #  resuelto: solo que los dos sistemas no dicen lo mismo.
    CASO_DESINCRONIZADO = "caso_desincronizado"
    TIPOS_SENAL = (
        (CASO_ANTIGUO, "Caso abierto antiguo"),
        (ACTIVIDAD_VENCIDA, "Actividad vencida"),
        (ACTIVIDAD_SIN_RESPONSABLE, "Actividad sin responsable"),
        (ACTIVIDAD_BLOQUEADA, "Actividad bloqueada"),
        (COMPROMISO_POR_VENCER, "Compromiso próximo a vencer"),
        (DEPENDENCIA_PENDIENTE, "Dependencia pendiente"),
        (ORDEN_SIN_PROGRAMAR, "Orden sin programación"),
        (ORDEN_EN_RIESGO, "Orden con riesgo operacional"),
        (PROGRAMACION_SIN_PUBLICAR, "Programación semanal sin publicar"),
        (DATO_INCOMPLETO, "Dato incompleto"),
        (ORDEN_SLA_VENCIDO, "Orden con plazo operativo vencido"),
        (ORDEN_SLA_POR_VENCER, "Orden con plazo operativo por vencer"),
        (INCIDENCIA_SIN_RESOLVER, "Incidencia operativa sin resolver"),
        (ESCALAMIENTO_SIN_DESTINATARIO, "Escalamiento sin destinatario registrado"),
        (CASO_DESINCRONIZADO, "Caso cerrado en el proveedor y abierto en el CRM"),
    )

    PROPUESTA = "propuesta"
    ACEPTADA = "aceptada"
    MODIFICADA = "modificada"
    RECHAZADA = "rechazada"
    EXPIRADA = "expirada"
    CANCELADA = "cancelada"
    ESTADOS = (
        (PROPUESTA, "Propuesta"),
        (ACEPTADA, "Aceptada"),
        (MODIFICADA, "Modificada"),
        (RECHAZADA, "Rechazada"),
        (EXPIRADA, "Expirada"),
        (CANCELADA, "Cancelada"),
    )
    ESTADOS_REVISADOS = (ACEPTADA, MODIFICADA, RECHAZADA)

    #  LOS QUE IMPIDEN VOLVER A PROPONER LO MISMO  --  paso M09-D
    #  ---------------------------------------------------------
    #  Hasta este paso la deduplicacion miraba solo 'propuesta', y el efecto
    #  era el que se reporto en M09-C.1: el Jefe rechazaba una recomendacion y
    #  al ciclo siguiente volvia identica. Rechazar es una decision; repetir la
    #  pregunta la ignora -- y es el mismo mecanismo que dejo la cola de
    #  'acciones_propuestas' con 36 pendientes sin revisar.
    #
    #  'expirada' y 'cancelada' NO estan aca a proposito: expirar significa que
    #  nadie la miro, y entonces volver a preguntar es lo correcto.
    ESTADOS_QUE_BLOQUEAN = (PROPUESTA, ACEPTADA, MODIFICADA, RECHAZADA)

    # Niveles de autonomia, tal como quedaron definidos. En esta etapa el
    # Supervisor opera en 0/1: registra propuestas de cualquier nivel --para
    # poder medir cuantas habria-- pero nada se ejecuta.
    NIVEL_OBSERVAR = 0
    NIVEL_RECOMENDAR = 1
    NIVEL_COORDINAR = 2
    NIVEL_EJECUTAR_REVERSIBLE = 3
    NIVEL_CRITICO = 4
    NIVELES = (
        (NIVEL_OBSERVAR, "0 · Observar"),
        (NIVEL_RECOMENDAR, "1 · Recomendar"),
        (NIVEL_COORDINAR, "2 · Coordinar"),
        (NIVEL_EJECUTAR_REVERSIBLE, "3 · Ejecutar acciones reversibles"),
        (NIVEL_CRITICO, "4 · Acción crítica, siempre humano"),
    )
    # El techo de esta etapa. Una propuesta por encima se registra igual, pero
    # queda marcada como fuera del alcance vigente.
    NIVEL_MAXIMO_ETAPA = NIVEL_RECOMENDAR

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="propuestas_ia")

    tipo_senal = models.CharField(max_length=48, choices=TIPOS_SENAL)
    origen_tipo = models.CharField(
        max_length=64, help_text="case, actividad, orden_trabajo"
    )
    origen_id = models.CharField(max_length=128)

    accion_propuesta = models.CharField(
        max_length=255, help_text="Qué recomienda, en una línea legible."
    )
    motivo = models.TextField(help_text="Por qué lo recomienda.")

    # La evidencia es una LISTA de observaciones, cada una con fuente, dato y
    # hora de lectura. Sin ella la propuesta no se crea: lo garantiza la
    # restriccion de abajo, no la buena voluntad de quien llame.
    evidencia = models.JSONField(default=list)

    prioridad = models.PositiveSmallIntegerField(
        default=50, help_text="Menor es más urgente."
    )
    impacto = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Qué se ve afectado si no se atiende.",
    )
    nivel_autonomia_requerido = models.PositiveSmallIntegerField(
        choices=NIVELES,
        default=NIVEL_RECOMENDAR,
        help_text="Qué nivel HABRIA hecho falta para ejecutarla sola.",
    )

    #  LA IDENTIDAD DE LA CONDICION, NO SU MAGNITUD  --  paso M09-D
    #  -----------------------------------------------------------
    #  Es lo que distingue "el mismo hecho otra vez" de "un hecho nuevo". La
    #  distincion importa porque casi toda señal tiene una magnitud que cambia
    #  sola: un caso abierto suma un dia cada dia. Si la huella incluyera los
    #  dias, una propuesta rechazada volveria mañana con otra huella -- que es
    #  justo el defecto que este campo viene a cerrar.
    #
    #  Asi que la huella lleva SOLO lo que, si cambia, convierte la situacion
    #  en otra: el motivo de un bloqueo, la fecha comprometida, la dependencia
    #  concreta. La magnitud viaja en la evidencia, que si se actualiza.
    #
    #  Vacia en las propuestas anteriores a este paso: el default lo deja
    #  explicito en vez de nulo, para que una huella ausente no se confunda
    #  con una huella calculada.
    huella_condicion = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Identidad estable de la condición detectada. Ver supervisor.py.",
    )

    estado = models.CharField(max_length=16, choices=ESTADOS, default=PROPUESTA)
    conocimiento_version = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Regla o documento que se usó, cuando aplica.",
    )
    expira_en = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Una recomendación vieja sobre un caso ya cerrado es ruido.",
    )

    # --- revision humana ---------------------------------------------------
    revisado_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas_revisadas",
    )
    revisado_en = models.DateTimeField(null=True, blank=True)
    resultado = models.TextField(
        blank=True,
        default="",
        help_text="Qué decidió el Jefe de Operaciones, y con qué comentario.",
    )

    #  LO QUE EL REVISOR AGREGA, Y QUE LA IA NO PUEDE ESCRIBIR  --  paso M09-F
    #  -----------------------------------------------------------------------
    #  M09-C cerro la lista de causas y prohibio 'incumplimiento_de_persona':
    #  el Supervisor describe condiciones, no señala personas. Por eso este
    #  campo NO esta en supervisor.CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR -- lo llena
    #  un humano al MODIFICAR, o no lo llena nadie. Que exista la columna no
    #  habilita a la IA a usarla; lo que la habilita seria escribirla, y no hay
    #  ninguna ruta que lo haga.
    responsable_sugerido = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas_sugeridas",
        help_text="A quién propone el REVISOR. La IA nunca escribe aquí.",
    )
    observaciones = models.TextField(
        blank=True,
        default="",
        help_text="Contexto que agrega el revisor y que el sistema no podía saber.",
    )

    #  EL HECHO HISTORICO, INTACTO  --  paso M09-F
    #  -------------------------------------------
    #  Cuando el revisor MODIFICA, lo que la IA habia recomendado se copia aqui
    #  ANTES de tocar nada, una sola vez, y no se vuelve a escribir nunca.
    #
    #  No es redundante con la auditoria: la auditoria registra la transicion
    #  --util para saber quien cambio que y cuando-- pero reconstruir desde ella
    #  la recomendacion original exige encadenar renglones hacia atras y confiar
    #  en que ninguno falte. Y el Shadow Mode existe justamente para comparar lo
    #  que la IA propuso contra lo que el humano decidio: si esa comparacion
    #  depende de una reconstruccion, no se puede medir.
    #
    #  Vacio ({}) mientras nadie haya modificado. La EVIDENCIA nunca entra aca
    #  porque la evidencia nunca se modifica: no hace falta respaldar lo que no
    #  cambia.
    propuesta_original = models.JSONField(
        default=dict,
        blank=True,
        help_text="Copia literal de lo que recomendó la IA, antes de la primera "
                  "modificación humana. Se escribe una vez.",
    )

    # Puente a la capa de ejecucion. NULO EN TODA ESTA ETAPA: existe para que
    # la relacion este declarada, no para usarse.
    accion_propuesta_ref = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Id en asistente.acciones_propuestas. Vacío en Shadow Mode.",
    )

    class Meta:
        db_table = "operaciones_propuesta_supervisor"
        ordering = ["prioridad", "-created_at"]
        indexes = [
            models.Index(fields=["org", "estado", "prioridad"]),
            models.Index(fields=["org", "tipo_senal", "origen_id"]),
            #  El que resuelve la deduplicacion de cada ciclo. NO es unique:
            #  una propuesta expirada o cancelada PUEDE repetirse mas adelante
            #  con la misma huella, y eso es correcto -- expirar significa que
            #  nadie la miro. La unicidad la decide el estado, no la base.
            models.Index(
                fields=["org", "tipo_senal", "origen_tipo", "origen_id",
                        "huella_condicion"],
                name="idx_propuesta_dedup",
            ),
        ]
        constraints = [
            # SIN EVIDENCIA NO HAY PROPUESTA. La lista vacia se serializa como
            # '[]' y el objeto vacio como '{}': se rechazan los dos. Es la
            # regla que impide que el Supervisor afirme algo porque si.
            models.CheckConstraint(
                condition=(
                    ~models.Q(evidencia__in=[[], {}, None])
                ),
                name="propuesta_exige_evidencia",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.get_tipo_senal_display()}] {self.accion_propuesta}"

    def clean(self):
        if not self.evidencia:
            raise ValidationError(
                {"evidencia": "Una propuesta sin evidencia no se registra."}
            )
        if isinstance(self.evidencia, list):
            faltan = [
                i for i, e in enumerate(self.evidencia)
                if not isinstance(e, dict)
                or not {"fuente", "dato", "observado_en"} <= set(e)
            ]
            if faltan:
                raise ValidationError({
                    "evidencia": (
                        "Cada observación necesita 'fuente', 'dato' y "
                        f"'observado_en'. Faltan en: {faltan}"
                    )
                })

    @property
    def dentro_del_alcance(self) -> bool:
        """Si su nivel cabe en lo que esta etapa permite (observar/recomendar)."""
        return self.nivel_autonomia_requerido <= self.NIVEL_MAXIMO_ETAPA
