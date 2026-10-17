# -*- coding: utf-8 -*-
"""
================================================================================
 LA CAPA DE FUENTES  --  que se consulto, cuando, y que tan viejo es el dato
================================================================================

POR QUE EXISTE
--------------
El Supervisor ya LEE seis fuentes (SmartOLT, WispHub, Dexter/CRM, SLA, M02,
M03): los 15 detectores de 'supervisor.py' las recorren en cada ciclo. Lo que no
existe es el ESTADO de esas lecturas. Hoy, si una fuente no contesta, el
detector devuelve una lista vacia y el ciclo sigue como si no hubiera nada que
ver. "No pude preguntar" y "no hay nada" terminan en la misma lista.

Eso ya se midio y no es teorico: de los 15 detectores, SOLO 2 habian disparado
alguna vez en produccion. Los otros 13 leen tablas vacias (0 actividades, 0
programaciones, 0 novedades) y devuelven [] -- indistinguible de "todo en
orden". Un tablero construido sobre eso afirma que no hay problemas porque no
tiene con que verlos.

Estas dos tablas son la respuesta: una guarda el ESTADO de cada fuente, la otra
el DATO con el que se puede comparar un ciclo contra el anterior.

LO QUE NO DUPLICAN DEL SCHEDULER
--------------------------------
El scheduler ya tiene 'job_run', 'job_attempt' y 'job_run_event', y ahi vive
todo lo que es del TURNO: quien reclamo, cuantos intentos, el lease, el
desenlace. Nada de eso se repite aqui.

Lo que SI vive aqui es lo que el scheduler no sabe ni tiene por que saber: que
una fuente se llama SmartOLT, que su dato tiene 3 minutos de antiguedad, que la
agregacion del proveedor tarda 2 a 5 minutos, y que la consulta anterior trajo
8 ONUs caidas y esta trae 19. El scheduler mide TURNOS; esto mide FUENTES.

El puente entre los dos es 'ejecucion_id', que es el 'job_run.id' del turno que
produjo la lectura. Con eso, desde una fila de aqui se llega al turno completo
sin copiar una sola columna suya.

UNA COSA QUE ESTA CAPA NO HACE, Y ES DELIBERADO
-----------------------------------------------
No decide nada. No crea situaciones, no crea propuestas, no escala y no corre el
ciclo del Supervisor. Deja el dato y su frescura escritos, y ahi termina. La
deteccion y la correlacion son el bloque siguiente, y mezclarlas aqui haria
imposible saber si un problema es de la lectura o de la interpretacion.
================================================================================
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org


# =============================================================================
#  EL VOCABULARIO  --  compartido por las dos tablas y por 'fuentes.py'
# =============================================================================

class Fuente:
    """
    Las seis fuentes, como constantes y no como texto libre.

    No es un modelo: es un catalogo cerrado. Agregar una fuente es un cambio de
    codigo revisado, igual que agregar un trabajo al registro del scheduler --
    y por el mismo motivo: si el nombre viniera de una fila, cualquiera podria
    inventar una fuente que nadie implemento.
    """

    SMARTOLT = "smartolt"
    WISPHUB = "wisphub"
    DEXTER = "dexter"
    SLA = "sla"
    M02 = "m02"
    M03 = "m03"

    TODAS = (SMARTOLT, WISPHUB, DEXTER, SLA, M02, M03)

    ETIQUETAS = (
        (SMARTOLT, "SmartOLT (red optica)"),
        (WISPHUB, "WispHub (clientes y tickets del ISP)"),
        (DEXTER, "Dexter / CRM (casos)"),
        (SLA, "SLA (riesgo temporal)"),
        (M02, "M02 (actividades y compromisos)"),
        (M03, "M03 (programacion y ordenes)"),
    )


class EstadoLectura:
    """
    Como salio la consulta. SEIS estados, y los seis hacen falta.

    La distincion que justifica la tabla entera esta entre los tres primeros:

      CON_DATOS       se consulto y trajo registros.
      SIN_REGISTROS   se consulto, contesto bien, y no hay nada. M02 y M03 en
                      produccion estan asi: vacias de verdad.
      NO_CONSULTADA   no le toco el turno todavia, o la fuente esta inactiva.
                      NO es "no hay nada": es "no se sabe".

    Y los otros tres son las formas de no saber:

      ERROR           contesto mal, o no contesto. Jamas se lee como cero.
      NO_DISPONIBLE   la fuente esta bloqueada por una barrera del sistema --
                      WispHub hoy, por Autonomia 2. No es un fallo: es un NO
                      deliberado, y confundirlo con un error manda a depurar
                      algo que funciona.
      INCONCLUSA      se consulto, contesto vacio, PERO dentro de una ventana
                      en la que el vacio no significa nada.

    INCONCLUSA no la pidio nadie: la exige la evidencia. Los desarrolladores de
    SmartOLT informaron que 'get_outage_pons' agrupa con 2 a 5 minutos de
    retraso (ver .claude/skills/smartolt-api). Una respuesta vacia en esa
    ventana NO prueba que no haya una caida de red -- prueba que el proveedor
    todavia no la agrupo. Tratarla como SIN_REGISTROS seria exactamente la
    afirmacion falsa que esta capa existe para evitar.
    """

    CON_DATOS = "con_datos"
    SIN_REGISTROS = "sin_registros"
    NO_CONSULTADA = "no_consultada"
    ERROR = "error"
    NO_DISPONIBLE = "no_disponible"
    INCONCLUSA = "inconclusa"

    TODOS = (CON_DATOS, SIN_REGISTROS, NO_CONSULTADA, ERROR, NO_DISPONIBLE,
             INCONCLUSA)

    #  Los que NO autorizan a concluir "no hay problema". Se usa como lista
    #  BLANCA invertida a proposito: un estado nuevo cae aqui por defecto, no
    #  en el lado que permite afirmar.
    NO_CONCLUYENTES = (NO_CONSULTADA, ERROR, NO_DISPONIBLE, INCONCLUSA)

    ETIQUETAS = (
        (CON_DATOS, "Consultada, con registros"),
        (SIN_REGISTROS, "Consultada, sin registros"),
        (NO_CONSULTADA, "No consultada"),
        (ERROR, "Error de consulta"),
        (NO_DISPONIBLE, "Fuente no disponible"),
        (INCONCLUSA, "Inconclusa (dentro de la ventana de la fuente)"),
    )


class Frescura:
    """
    Que tan viejo es el dato. Es un eje DISTINTO del estado de la lectura.

    Una consulta puede salir bien (CON_DATOS) y traer un dato de hace una hora:
    la lectura fue un exito y el dato esta VIEJO. Mezclar los dos ejes en una
    sola columna es como se presenta un dato antiguo como estado actual, que es
    justo lo que no puede pasar.

    DESCONOCIDA es el valor por defecto y no un caso raro: si la fuente no dice
    de cuando es su dato, la antiguedad no se puede calcular. Se dice que no se
    sabe en vez de suponer que es de ahora.
    """

    FRESCA = "fresca"
    VIEJA = "vieja"
    DESCONOCIDA = "desconocida"
    SIN_DATO = "sin_dato"

    TODAS = (FRESCA, VIEJA, DESCONOCIDA, SIN_DATO)

    ETIQUETAS = (
        (FRESCA, "Fresca"),
        (VIEJA, "Vieja (pasa la antiguedad maxima de la fuente)"),
        (DESCONOCIDA, "Desconocida (la fuente no fecha su dato)"),
        (SIN_DATO, "Sin dato que fechar"),
    )


# =============================================================================
#  EL ESTADO DE CADA FUENTE  --  una fila por organizacion y fuente
# =============================================================================

class FuenteEstado(BaseModel):
    """
    Lo que se sabe de una fuente AHORA. Una sola fila por organizacion+fuente.

    Es el registro que contesta, sin recorrer historial: esta activa? cada
    cuanto se consulta? cuando fue la ultima vez? cuando toca de nuevo? como
    salio? cuantos registros trajo? de cuando es el dato?

    POR QUE 'proxima_consulta_en' VIVE AQUI Y NO EN EL SCHEDULER
    -----------------------------------------------------------
    Porque el scheduler mide el tiempo del PROCESO y esta columna mide el de
    una FUENTE, y son dos relojes con dueños distintos.

    El scheduler despierta al Supervisor cada tanto -- una fila en
    'asistente.job_catalogo' con su intervalo, que es el unico temporizador del
    sistema y no se duplica. Cuando lo despierta, el Supervisor mira ESTAS filas
    y consulta solo las fuentes que ya vencieron. Asi SmartOLT puede ir cada 5
    minutos y M03 cada hora sin que haya dos procesos corriendo, y sin que la
    frecuencia quede escrita en el codigo.

    Se eligio asi y no con un trabajo por fuente porque un trabajo por fuente
    obligaria a que el motor --que es generico y no conoce ningun sistema
    concreto-- tuviera 'smartolt' escrito en su registro de trabajos. La
    frecuencia es un dato de operacion de una empresa; su lugar es una fila
    editable, no un literal en 'nucleo/'.

    FALLA CERRADO: 'activa' arranca en False
    ---------------------------------------
    Una fuente recien creada NO se consulta. Encenderla es una decision de
    operacion, igual que la fila del catalogo del scheduler. El default
    contrario convertiria desplegar el codigo en encender seis consultas
    periodicas contra sistemas de un cliente.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="fuentes_supervisor")
    fuente = models.CharField(max_length=32, choices=Fuente.ETIQUETAS)

    # --- configuracion (editable por operacion, nunca en codigo) -----------
    #  Arranca APAGADA. Ver el docstring: desplegar no es encender.
    activa = models.BooleanField(default=False)
    #  Cada cuanto se consulta. El bloque pide 5 minutos para SmartOLT como
    #  objetivo inicial; el default es ese y se cambia por fila, no por deploy.
    frecuencia_segundos = models.PositiveIntegerField(default=300)
    #  A partir de cuanta antiguedad el dato deja de poder presentarse como
    #  estado actual. Por fuente, porque no se parecen: una caida optica de
    #  hace 10 minutos sigue siendo noticia, un plan semanal de hace 10 minutos
    #  esta igual de vigente que hace un dia.
    antiguedad_maxima_segundos = models.PositiveIntegerField(default=900)
    #  La ventana en la que un vacio es INCONCLUSA y no SIN_REGISTROS. 0 = no
    #  aplica. Para SmartOLT son los 2 a 5 minutos de agregacion que informo el
    #  proveedor; se deja configurable porque es un dato de un tercero y puede
    #  cambiar sin avisarnos.
    ventana_inconclusa_segundos = models.PositiveIntegerField(default=0)

    # --- ultima consulta ---------------------------------------------------
    ultima_consulta_inicio = models.DateTimeField(null=True, blank=True)
    ultima_consulta_fin = models.DateTimeField(null=True, blank=True)
    proxima_consulta_en = models.DateTimeField(null=True, blank=True)

    estado = models.CharField(
        max_length=32, choices=EstadoLectura.ETIQUETAS,
        default=EstadoLectura.NO_CONSULTADA)
    frescura = models.CharField(
        max_length=16, choices=Frescura.ETIQUETAS, default=Frescura.SIN_DATO)

    #  Cuantos registros trajo. NULL no es 0: 0 es "consultada y vacia", NULL
    #  es "no se sabe cuantos porque no se pudo consultar". La diferencia es la
    #  razon de ser de esta tabla.
    registros = models.IntegerField(null=True, blank=True)
    #  De cuando es el DATO segun la fuente, no cuando lo leimos nosotros.
    dato_en = models.DateTimeField(null=True, blank=True)

    #  El mensaje tecnico del error. Es para quien depura, y por eso NO se
    #  muestra a un cliente ni viaja a un prompt.
    error_tecnico = models.TextField(blank=True, default="")
    #  Por que esta fuente no esta disponible, cuando el estado es
    #  NO_DISPONIBLE. Es distinto de un error: aqui va la barrera que lo
    #  impide, no una falla.
    motivo_no_disponible = models.TextField(blank=True, default="")

    #  El puente al scheduler: 'asistente.job_run.id' del turno que produjo
    #  esta lectura. No es una FK -- esa tabla vive en otra base logica, la del
    #  motor-- y por eso se guarda el identificador y nada mas.
    ejecucion_id = models.UUIDField(null=True, blank=True)
    #  Que consulta se hizo. Para SmartOLT distingue 'outage_pons' de lo que
    #  venga despues; sirve para no comparar manzanas con naranjas cuando la
    #  consulta cambie de forma.
    tipo_consulta = models.CharField(max_length=64, blank=True, default="")
    esquema = models.CharField(max_length=32, blank=True, default="")

    #  Contadores que sirven para ver una fuente que falla SIEMPRE, que es
    #  distinto de una que fallo una vez.
    fallos_consecutivos = models.PositiveIntegerField(default=0)
    ultimo_exito_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "operaciones_fuente_estado"
        ordering = ["fuente"]
        constraints = [
            #  Una sola fila por organizacion y fuente. Es lo que permite
            #  leerla sin ordenar por fecha y sin preguntarse cual es la
            #  vigente.
            models.UniqueConstraint(
                fields=["org", "fuente"], name="fuente_unica_por_org"),
            #  Una frecuencia de 0 seria una consulta en bucle contra el
            #  sistema de un tercero. La base lo impide para que no dependa de
            #  que la pantalla valide.
            models.CheckConstraint(
                condition=models.Q(frecuencia_segundos__gte=30),
                name="fuente_frecuencia_minima"),
            #  Un error sin mensaje es exactamente lo que deja a alguien
            #  mirando "error" sin poder hacer nada. Y al reves: un mensaje de
            #  error en un estado que no es error es ruido que se lee como
            #  problema.
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado="error")
                    | ~models.Q(error_tecnico="")),
                name="fuente_error_con_motivo"),
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado="no_disponible")
                    | ~models.Q(motivo_no_disponible="")),
                name="fuente_no_disponible_con_motivo"),
        ]
        indexes = [
            #  El indice que usa el sondeo: cuales vencieron.
            models.Index(fields=["org", "activa", "proxima_consulta_en"]),
        ]

    def __str__(self):
        return f"{self.fuente} [{self.estado}/{self.frescura}]"

    @property
    def concluyente(self) -> bool:
        """
        Si de esta lectura se puede concluir algo sobre el mundo.

        Es la propiedad que impide el error que motiva toda la capa: leer un
        ERROR o una fuente NO_CONSULTADA como "no hay problemas". Tambien dice
        no cuando el dato es VIEJO -- una foto de hace una hora no describe el
        estado de ahora, aunque la consulta que la trajo haya salido bien.
        """
        if self.estado in EstadoLectura.NO_CONCLUYENTES:
            return False
        return self.frescura != Frescura.VIEJA


# =============================================================================
#  EL DATO  --  para poder comparar un ciclo con el anterior
# =============================================================================

class FuenteSnapshot(BaseModel):
    """
    El estado relevante que trajo UNA consulta. Acotado, no una copia de nada.

    POR QUE NO SE GUARDA LA FUENTE ENTERA
    -------------------------------------
    Porque no hace falta y porque costaria caro en el unico lugar donde duele.
    SmartOLT tiene 5.061 ONUs en Rapilink; guardar su estado completo cada 5
    minutos son ~1,5 millones de filas por dia para contestar una pregunta que
    se responde con 4: 'get_outage_pons' ya devuelve el resumen agrupado por
    PON, con los afectados y desde cuando.

    Asi que lo que se guarda es lo que el Supervisor necesita para notar un
    CAMBIO: por PON, cuantos afectados y de que tipo. El ejemplo del bloque
    --PON-04 paso de 1 ONT caida a 12-- se contesta con eso, y no requiere
    haber guardado las 5.061.

    Y LO QUE ESTO NO ES
    -------------------
    No es una bitacora de auditoria (esa es 'common.Activity') ni el registro
    del turno (ese es 'job_run'). Es memoria de trabajo con un solo proposito:
    tener contra que comparar la proxima lectura.

    SIN PII, Y MEDIDO CONTRA EL CAMPO QUE LA TRAE
    ---------------------------------------------
    'get_onu_details' de SmartOLT devuelve 'name' con el nombre completo del
    cliente, 'address', y lat/long del domicilio (ver la skill). Nada de eso
    entra aqui: el resumen por PON no nombra a nadie. Lo afirma la suite
    comparando el JSON serializado, no las claves del primer nivel.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="snapshots_supervisor")
    fuente = models.CharField(max_length=32, choices=Fuente.ETIQUETAS)

    #  Cuando lo capturamos nosotros.
    capturado_en = models.DateTimeField()
    #  De cuando es el dato segun la fuente. NULL cuando la fuente no lo dice
    #  -- y entonces la frescura es DESCONOCIDA, nunca FRESCA por omision.
    dato_en = models.DateTimeField(null=True, blank=True)

    estado = models.CharField(max_length=32, choices=EstadoLectura.ETIQUETAS)
    frescura = models.CharField(max_length=16, choices=Frescura.ETIQUETAS,
                                default=Frescura.SIN_DATO)

    #  El resumen acotado. Su forma la fija el adaptador de cada fuente y la
    #  declara 'esquema': sin eso, comparar dos capturas de formas distintas
    #  daria una diferencia que no significa nada.
    datos = models.JSONField(default=dict, blank=True)
    esquema = models.CharField(max_length=32)
    tipo_consulta = models.CharField(max_length=64, blank=True, default="")

    registros = models.IntegerField(null=True, blank=True)
    error_tecnico = models.TextField(blank=True, default="")

    #  El turno que lo produjo, para llegar a 'job_run' sin copiarlo.
    ejecucion_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "operaciones_fuente_snapshot"
        ordering = ["-capturado_en"]
        indexes = [
            #  El unico acceso que importa: el ultimo de esta fuente para esta
            #  organizacion. Lleva 'org' primero para que el filtro de tenant
            #  no quede fuera del indice.
            models.Index(fields=["org", "fuente", "-capturado_en"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado="error")
                    | ~models.Q(error_tecnico="")),
                name="snapshot_error_con_motivo"),
        ]

    def __str__(self):
        return f"{self.fuente} @ {self.capturado_en:%Y-%m-%d %H:%M}"
