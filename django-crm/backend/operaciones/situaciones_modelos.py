# -*- coding: utf-8 -*-
"""
================================================================================
 SITUACION OPERATIVA  --  lo que el Supervisor cree que esta pasando
================================================================================

QUE ES, Y QUE NO ES
-------------------
Una situacion es UN problema que el Supervisor cree estar viendo, sostenido entre
ciclos. "12 ONT caidas en el PON 3/1/4 desde las 02:15" es una situacion: no es
un caso, no es un ticket, no es una orden y no es una propuesta.

    Case                 el problema de UN cliente. Una situacion puede tener
                         cero casos, o doce.
    Ticket               el espejo de un caso en el sistema del ISP. Externo.
    PropuestaSupervisor  una RECOMENDACION. Una situacion puede generar una
                         propuesta mas tarde; la propuesta no la reemplaza ni la
                         cierra. Son dos cosas y las dos siguen existiendo.
    OrdenTrabajo         un desplazamiento fisico.
    FuenteSnapshot       la foto cruda de una fuente. La situacion es la
                         INTERPRETACION sostenida de varias fotos.

POR QUE TIENE QUE PODER EXISTIR SIN TICKETS
-------------------------------------------
Porque es el punto entero del Supervisor: la red puede verse caida antes de que
el primer cliente escriba. Si una situacion exigiera un ticket, el sistema solo
podria reaccionar DESPUES de que alguien reclame -- que es exactamente lo que ya
pasa hoy y lo que esto viene a cambiar. Por eso 'tickets: 0' es un estado valido
y no un error, y hay una prueba que lo afirma.

LO QUE ESTAS TABLAS NO HACEN
----------------------------
No ejecutan nada. Crear o actualizar una situacion es una operacion INTERNA de
supervision: no reinicia un equipo, no cierra un caso, no reprograma, no manda un
mensaje y no eleva autonomia. El Supervisor sigue en observar y recomendar.

CUATRO TABLAS, Y POR QUE NO UNA
-------------------------------
    SituacionOperativa  la situacion: estado, riesgo, hipotesis, confianza.
    SituacionAfectado   QUE esta afectado, por tipo. Una fila por recurso, con
                        restriccion de unicidad -- es lo que hace que el mismo
                        PON contado dos veces siga siendo uno.
    SituacionEvento     el timeline, APPEND-ONLY. Nunca se reescribe.
    SituacionRelacion   una situacion con otra. Separada porque la relacion
                        tiene su propio tipo y su propia fuerza.

Meterlas en una sola obligaria a columnas que casi siempre estan vacias, y a que
"agregar un afectado" fuera una escritura sobre la fila de la situacion -- justo
donde dos ciclos concurrentes se pisan.
================================================================================
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


# =============================================================================
#  EL VOCABULARIO
# =============================================================================

class Riesgo:
    """
    Cuanto preocupa. Es una escala declarada, no un numero libre.

    Se mantiene corta a proposito: cinco niveles ya obligan a discutir la
    diferencia entre dos de ellos, y diez vuelven la eleccion arbitraria.
    """

    INFORMATIVO = "informativo"
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"

    TODOS = (INFORMATIVO, BAJO, MEDIO, ALTO, CRITICO)
    ETIQUETAS = tuple((r, r.capitalize()) for r in TODOS)

    #  Para poder decir "subio" o "bajo" sin comparar cadenas.
    ORDEN = {INFORMATIVO: 0, BAJO: 1, MEDIO: 2, ALTO: 3, CRITICO: 4}


class Confianza:
    """
    Que tan sostenida esta la hipotesis. NO es la gravedad: una situacion puede
    ser critica y de confianza baja al mismo tiempo, y confundir las dos cosas es
    como una sospecha termina presentada como un hecho.

    'SIN_HIPOTESIS' existe porque es el caso honesto mas comun al principio: hay
    una anomalia y todavia no hay explicacion.
    """

    SIN_HIPOTESIS = "sin_hipotesis"
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"

    TODAS = (SIN_HIPOTESIS, BAJA, MEDIA, ALTA)
    ETIQUETAS = tuple((c, c.replace("_", " ").capitalize()) for c in TODAS)


class TipoAfectado:
    """
    Que clase de cosa esta afectada. Lista cerrada: un tipo nuevo es un cambio de
    codigo revisado, no una cadena que alguien inventa en tiempo de ejecucion.

    'DATOS_INSUFICIENTES' no es un recurso: es la forma de registrar que SE SABE
    que hay algo afectado y NO se pudo identificar que. Sin este tipo, la unica
    alternativa seria no registrar nada --y perder la insuficiencia-- o inventar
    un identificador, que es peor.
    """

    ONT = "ont"
    PON = "pon"
    OLT = "olt"
    CLIENTE = "cliente"
    SERVICIO = "servicio"
    TICKET = "ticket"
    CASO = "caso"
    ZONA = "zona"
    ORDEN = "orden"
    DATOS_INSUFICIENTES = "datos_insuficientes"

    TODOS = (ONT, PON, OLT, CLIENTE, SERVICIO, TICKET, CASO, ZONA, ORDEN,
             DATOS_INSUFICIENTES)
    ETIQUETAS = tuple((t, t.replace("_", " ").capitalize()) for t in TODOS)


class TipoEvento:
    """Lo que puede pasarle a una situacion. Cerrado, y es el timeline."""

    DETECTADA = "detectada"
    ACTUALIZADA = "actualizada"
    EVIDENCIA = "evidencia_nueva"
    AFECTADO_NUEVO = "afectado_nuevo"
    AFECTADO_RECUPERADO = "afectado_recuperado"
    TICKET_ASOCIADO = "ticket_asociado"
    CAMBIO_ESTADO = "cambio_estado"
    CAMBIO_RIESGO = "cambio_riesgo"
    HIPOTESIS = "hipotesis"
    RECOMENDACION = "recomendacion"
    VERIFICACION = "verificacion"
    SENAL_AUSENTE = "senal_ausente"
    INCONCLUSA = "fuente_inconclusa"
    DESCARTE = "descarte"
    CIERRE = "cierre"
    RELACION = "relacion"
    #  05/10/2026, paso P6. Se PIDIO trabajo a partir de esta situacion. No es
    #  'RECOMENDACION': recomendar deja una PropuestaSupervisor que una persona
    #  todavia tiene que decidir; coordinar ya creo una ActividadOperativa en
    #  M02. Confundirlos haria que el timeline afirmara que alguien esta
    #  trabajando cuando solo se sugirio que alguien trabajara.
    COORDINACION = "coordinacion"

    TODOS = (DETECTADA, ACTUALIZADA, EVIDENCIA, AFECTADO_NUEVO,
             AFECTADO_RECUPERADO, TICKET_ASOCIADO, CAMBIO_ESTADO, CAMBIO_RIESGO,
             HIPOTESIS, RECOMENDACION, VERIFICACION, SENAL_AUSENTE, INCONCLUSA,
             DESCARTE, CIERRE, RELACION, COORDINACION)
    ETIQUETAS = tuple((t, t.replace("_", " ").capitalize()) for t in TODOS)


class TipoRelacion:
    """Como se relacionan dos situaciones. Sin causalidad implicita."""

    #  Comparten topologia o ventana: se parecen, y nada mas. Es el unico que la
    #  correlacion automatica puede afirmar sola.
    COINCIDE = "coincide"
    #  Una contiene a la otra (la caida de una OLT contiene la de sus PONs).
    CONTIENE = "contiene"
    CONTENIDA_EN = "contenida_en"
    #  Es la MISMA situacion vista dos veces. Lo marca una persona o la
    #  deduplicacion, nunca la cercania temporal.
    DUPLICADA_DE = "duplicada_de"
    #  Una explica a la otra. SOLO lo pone una persona: la correlacion no puede
    #  afirmar causalidad, y este tipo es precisamente esa afirmacion.
    EXPLICA = "explica"
    #  P8.2 (05/10/2026). La de antes volvio a pasar en el mismo sitio.
    #
    #  NO esta en AUTOMATICOS, y es la decision entera de este tipo: que dos
    #  situaciones compartan PON no prueba que una sea reincidencia de la
    #  otra -- un PON con una caida por semana puede estar sufriendo tres
    #  causas distintas. Afirmar reincidencia sola convertiria una
    #  coincidencia en un diagnostico. 'gobierno.candidatas_de_reincidencia'
    #  las PROPONE; ponerla exige una persona.
    REINCIDENCIA = "reincidencia"

    TODOS = (COINCIDE, CONTIENE, CONTENIDA_EN, DUPLICADA_DE,
             EXPLICA, REINCIDENCIA)
    ETIQUETAS = tuple((t, t.replace("_", " ").capitalize()) for t in TODOS)

    #  Los que la maquina puede poner sola. El resto exige un actor humano, y
    #  'situaciones.relacionar' lo hace cumplir.
    AUTOMATICOS = (COINCIDE, CONTIENE, CONTENIDA_EN)


# =============================================================================
#  LA SITUACION
# =============================================================================

class SituacionOperativa(BaseModel):
    """
    Un problema sostenido entre ciclos, con su estado y su evidencia.

    LOS OCHO ESTADOS, Y QUE SIGNIFICA CADA UNO
    ------------------------------------------
        DETECTADA        acaba de aparecer. Nadie la mira todavia.
        INVESTIGANDO     se esta juntando informacion.
        CONFIRMADA       hay evidencia suficiente de que el problema existe.
        EN_ATENCION      alguien esta trabajando en resolverlo.
        EN_VERIFICACION  la señal bajo o desaparecio, y hay que comprobar que de
                         verdad se resolvio. NO es "resuelta".
        RESUELTA         comprobado que se resolvio.
        CERRADA          terminada y archivada.
        DESCARTADA       no era un problema. Es distinto de RESUELTA: una se
                         arreglo, la otra nunca existio.

    POR QUE 'EN_VERIFICACION' NO SE PUEDE SALTEAR
    ---------------------------------------------
    Porque una señal que desaparece no prueba que el problema se resolvio. Puede
    haberse resuelto, o puede que la fuente dejo de contestar -- y la capa de
    fuentes existe justamente porque esas dos cosas se confunden. El proyecto ya
    tiene esta cicatriz escrita: 'ACCION_CONFIRMADA no significa que el problema
    del cliente este resuelto' (CLAUDE.md §12). Mismo criterio aqui.

    Asi que cerrar exige evidencia de verificacion, y la base lo obliga con una
    restriccion -- no depende de que alguien se acuerde.

    LA HUELLA ES LO QUE EVITA DUPLICADOS
    ------------------------------------
    'huella' es una clave DETERMINISTICA de lo que la situacion es: su tipo mas
    la dimension que la define ('pon:3/1/4'). Dos ciclos que ven la misma
    anomalia calculan la misma huella, y un indice unico PARCIAL --solo sobre las
    situaciones vivas-- hace que la segunda insercion falle en la base en vez de
    crear una situacion gemela.

    Parcial y no total a proposito: cuando el PON 3/1/4 se cae otra vez el mes
    que viene, eso es una situacion NUEVA. Un indice total lo impediria para
    siempre, que es peor que el duplicado que evita.
    """

    # --- estados -----------------------------------------------------------
    DETECTADA = "detectada"
    INVESTIGANDO = "investigando"
    CONFIRMADA = "confirmada"
    EN_ATENCION = "en_atencion"
    EN_VERIFICACION = "en_verificacion"
    RESUELTA = "resuelta"
    CERRADA = "cerrada"
    DESCARTADA = "descartada"

    ESTADOS = (
        (DETECTADA, "Detectada"),
        (INVESTIGANDO, "Investigando"),
        (CONFIRMADA, "Confirmada"),
        (EN_ATENCION, "En atención"),
        (EN_VERIFICACION, "En verificación"),
        (RESUELTA, "Resuelta"),
        (CERRADA, "Cerrada"),
        (DESCARTADA, "Descartada"),
    )

    #  Las que siguen VIVAS: una señal nueva se agrupa en una de estas, y son las
    #  que el indice unico parcial protege.
    VIVAS = (DETECTADA, INVESTIGANDO, CONFIRMADA, EN_ATENCION, EN_VERIFICACION)
    #  Las terminales. 'RESUELTA' no esta aqui: se resolvio pero sigue abierta
    #  hasta que alguien la cierra, y mientras tanto una recaida la reabre.
    TERMINALES = (CERRADA, DESCARTADA)

    # --- tipos de situacion ------------------------------------------------
    #  Lo que la situacion AFIRMA que pasa, en una palabra. Entra en la huella,
    #  asi que una caida de PON y una de OLT sobre la misma topologia no se
    #  confunden.
    AFECTACION_PON = "afectacion_pon"
    AFECTACION_OLT = "afectacion_olt"
    AFECTACION_ZONA = "afectacion_zona"
    PATRON_REPETIDO = "patron_repetido"
    OTRA = "otra"

    TIPOS = (
        (AFECTACION_PON, "Posible afectación de un PON"),
        (AFECTACION_OLT, "Posible afectación de una OLT"),
        (AFECTACION_ZONA, "Posible afectación de una zona"),
        (PATRON_REPETIDO, "Patrón repetido"),
        (OTRA, "Otra"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="situaciones_operativas")

    #  El identificador legible, el que una persona nombra en voz alta ("S-001").
    #  Se asigna por organizacion, no global: el consecutivo de una empresa no
    #  tiene por que depender de cuantas situaciones tuvo otra.
    codigo = models.CharField(max_length=16)

    tipo = models.CharField(max_length=32, choices=TIPOS, default=OTRA)
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, default="")

    estado = models.CharField(max_length=20, choices=ESTADOS, default=DETECTADA)
    riesgo = models.CharField(max_length=16, choices=Riesgo.ETIQUETAS,
                              default=Riesgo.INFORMATIVO)

    # --- la clave determinista de deduplicacion ----------------------------
    huella = models.CharField(max_length=160)

    # --- tiempos -----------------------------------------------------------
    detectada_en = models.DateTimeField()
    actualizada_en = models.DateTimeField()
    #  Cuando conviene mirarla de nuevo. La pone quien la actualiza; no es un
    #  temporizador -- nada la dispara sola.
    proxima_revision_en = models.DateTimeField(null=True, blank=True)
    #  Cuando se vio la señal por ULTIMA vez. Es lo que permite distinguir "sigue
    #  pasando" de "dejo de verse hace 40 minutos".
    senal_vista_en = models.DateTimeField(null=True, blank=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)

    # --- de donde salio ----------------------------------------------------
    #  La fuente que la origino, con el vocabulario de 'fuentes_modelos.Fuente'.
    #  No es una FK: la fuente es un catalogo de codigo, no una fila.
    fuente_origen = models.CharField(max_length=32, blank=True, default="")
    #  El snapshot concreto que la disparo, para poder volver al dato crudo.
    snapshot_origen_id = models.UUIDField(null=True, blank=True)

    # --- lo que el Supervisor CREE, separado de lo que SABE ----------------
    #  Vacio mientras no haya explicacion. Una hipotesis en blanco es mas honesta
    #  que una inventada, y la confianza de al lado lo dice.
    hipotesis = models.TextField(blank=True, default="")
    confianza = models.CharField(max_length=16, choices=Confianza.ETIQUETAS,
                                default=Confianza.SIN_HIPOTESIS)
    recomendacion = models.TextField(blank=True, default="")

    #  Los HECHOS que la sostienen: cada uno con su fuente y su momento. Es una
    #  lista de observaciones, no una narracion.
    evidencia = models.JSONField(default=list, blank=True)

    #  Cuantos recursos afectados se contaron en la ultima actualizacion. Es un
    #  DERIVADO de 'SituacionAfectado' que se guarda para poder ordenar y mostrar
    #  sin recorrer la tabla; la fuente de verdad son las filas.
    afectados_contados = models.PositiveIntegerField(default=0)

    # --- verificacion antes de cerrar --------------------------------------
    #  Que se comprobo, y cuando. La base EXIGE las dos cosas para cerrar.
    verificacion = models.TextField(blank=True, default="")
    verificada_en = models.DateTimeField(null=True, blank=True)

    responsable = models.ForeignKey(
        Profile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="situaciones_a_cargo")

    class Meta:
        db_table = "operaciones_situacion"
        ordering = ["-detectada_en"]
        indexes = [
            models.Index(fields=["org", "estado", "-detectada_en"]),
            models.Index(fields=["org", "huella"]),
            models.Index(fields=["org", "tipo", "estado"]),
        ]
        constraints = [
            #  El codigo legible es unico por empresa.
            models.UniqueConstraint(fields=["org", "codigo"],
                                    name="situacion_codigo_unico_por_org"),
            #  LA DEDUPLICACION, EN LA BASE Y NO EN UN 'IF'. Unico PARCIAL: solo
            #  una situacion VIVA por huella. Dos ciclos concurrentes que vean la
            #  misma anomalia no pueden crear dos filas -- la segunda falla aqui.
            #  Y cuando la vieja se cierra, la huella se libera: la proxima caida
            #  del mismo PON es otra situacion.
            models.UniqueConstraint(
                fields=["org", "huella"],
                condition=models.Q(estado__in=["detectada", "investigando",
                                               "confirmada", "en_atencion",
                                               "en_verificacion"]),
                name="situacion_viva_unica_por_huella"),
            #  CERRAR EXIGE HABER VERIFICADO. Una señal que desaparece no prueba
            #  que el problema se resolvio, y esta restriccion es lo que impide
            #  que un cierre automatico lo afirme.
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado="cerrada")
                    | (~models.Q(verificacion="")
                       & models.Q(verificada_en__isnull=False))),
                name="situacion_cierre_con_verificacion"),
            #  Una descartada tiene que decir por que. 'DESCARTADA' sin motivo es
            #  indistinguible de un borrado silencioso.
            models.CheckConstraint(
                condition=(~models.Q(estado="descartada")
                           | ~models.Q(descripcion="")),
                name="situacion_descarte_con_motivo"),
            #  Una hipotesis sin confianza declarada, o una confianza declarada
            #  sin hipotesis, son las dos formas de presentar una sospecha como
            #  un hecho.
            models.CheckConstraint(
                condition=(models.Q(hipotesis="")
                           & models.Q(confianza="sin_hipotesis"))
                | (~models.Q(hipotesis="")
                   & ~models.Q(confianza="sin_hipotesis")),
                name="situacion_hipotesis_con_confianza"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo} [{self.estado}]"

    @property
    def viva(self) -> bool:
        return self.estado in self.VIVAS


# =============================================================================
#  LOS AFECTADOS
# =============================================================================

class SituacionAfectado(BaseModel):
    """
    QUE esta afectado. Una fila por recurso, y la unicidad esta en la base.

    POR QUE UNA TABLA Y NO UNA LISTA EN LA SITUACION
    ------------------------------------------------
    Porque "agregar un afectado" tiene que poder pasar dos veces sin contar dos.
    Con una lista JSON en la fila de la situacion, dos ciclos concurrentes leen la
    misma lista, cada uno agrega su elemento y el ultimo que escribe borra al
    otro -- la actualizacion perdida clasica. Con una fila por recurso y un unico
    sobre (situacion, tipo, identificador), la base resuelve la carrera.

    'recuperado_en' en vez de borrar: cuando una ONT vuelve, la fila se MARCA, no
    se elimina. Borrarla perderia que estuvo caida, que es justo lo que hace
    posible contar la evolucion entre ciclos.
    """

    situacion = models.ForeignKey(
        SituacionOperativa, on_delete=models.CASCADE, related_name="afectados")
    #  Se repite la organizacion aunque cuelgue de la situacion: es lo que
    #  permite filtrar por tenant sin un JOIN, y lo que hace que una politica RLS
    #  sobre esta tabla sea posible.
    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="situacion_afectados")

    tipo = models.CharField(max_length=24, choices=TipoAfectado.ETIQUETAS)
    #  El identificador EN SU SISTEMA: el serial de una ONT, 'olt/board/port' de
    #  un PON, el id de un caso. Texto porque viene de sistemas distintos.
    identificador = models.CharField(max_length=160)
    #  Una etiqueta legible, cuando la hay y NO es un dato de cliente. El nombre
    #  de una caja ('CTO 56') si; el nombre de una persona no.
    etiqueta = models.CharField(max_length=120, blank=True, default="")

    detectado_en = models.DateTimeField()
    visto_en = models.DateTimeField()
    recuperado_en = models.DateTimeField(null=True, blank=True)

    #  De donde salio este afectado, para poder volver al dato.
    fuente = models.CharField(max_length=32, blank=True, default="")
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "operaciones_situacion_afectado"
        ordering = ["tipo", "identificador"]
        constraints = [
            #  LO QUE HACE QUE 12 + 12 SIGAN SIENDO 12.
            models.UniqueConstraint(
                fields=["situacion", "tipo", "identificador"],
                name="afectado_unico_en_situacion"),
            #  Un afectado de tipo 'datos_insuficientes' no puede traer un
            #  identificador que parezca real: si se supiera, no serian
            #  insuficientes.
            models.CheckConstraint(
                condition=(~models.Q(tipo="datos_insuficientes")
                           | models.Q(identificador="datos_insuficientes")),
                name="afectado_insuficiente_sin_identificador"),
        ]
        indexes = [
            models.Index(fields=["org", "tipo", "identificador"]),
            models.Index(fields=["situacion", "recuperado_en"]),
        ]

    def __str__(self):
        return f"{self.tipo}:{self.identificador}"


# =============================================================================
#  EL TIMELINE  --  append-only
# =============================================================================

class SituacionEvento(BaseModel):
    """
    Lo que le fue pasando a la situacion. SOLO SE AGREGA.

    COMO SE HACE CUMPLIR EL 'APPEND-ONLY'
    -------------------------------------
    No con una promesa en un docstring: 'save()' rechaza cualquier intento de
    guardar una fila que ya existe, y 'delete()' rechaza el borrado. Los dos
    levantan. Una prueba lo afirma intentandolo.

    Eso no impide un UPDATE por SQL crudo --nada en el ORM puede-- y por eso el
    orden importa: este historial es la version del sistema de lo que paso, y lo
    que lo protege de verdad es que ningun codigo de la aplicacion tenga un
    camino para reescribirlo.

    'ocurrido_en' y 'registrado_en' son dos cosas: cuando PASO y cuando lo
    anotamos. En un ciclo que procesa una foto de hace tres minutos no son el
    mismo instante, y mezclarlos hace que un timeline mienta sobre el orden.
    """

    situacion = models.ForeignKey(
        SituacionOperativa, on_delete=models.CASCADE, related_name="eventos")
    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="situacion_eventos")

    tipo = models.CharField(max_length=24, choices=TipoEvento.ETIQUETAS)
    resumen = models.CharField(max_length=255)
    #  Lo que haga falta para reconstruir el evento: conteos, estados, el id del
    #  snapshot. Nunca datos de cliente.
    datos = models.JSONField(default=dict, blank=True)

    ocurrido_en = models.DateTimeField()
    registrado_en = models.DateTimeField(auto_now_add=True)

    #  Quien lo produjo. Nulo cuando fue el Supervisor: el actor nulo ES la marca
    #  de "lo hizo la IA", igual que en 'operaciones/auditoria.py'.
    actor = models.ForeignKey(
        Profile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="eventos_de_situacion")

    class Meta:
        db_table = "operaciones_situacion_evento"
        ordering = ["ocurrido_en", "registrado_en"]
        indexes = [
            models.Index(fields=["situacion", "ocurrido_en"]),
            models.Index(fields=["org", "tipo", "-ocurrido_en"]),
        ]

    class NoSeReescribe(Exception):
        """El timeline es append-only: no se actualiza y no se borra."""

    def save(self, *args, **kwargs):
        #  'self._state.adding' es False en cuanto la fila existe en la base.
        #  Comprobarlo asi --y no con 'self.pk is not None'-- es lo correcto con
        #  una clave primaria UUID asignada por 'default', que ya viene puesta
        #  ANTES del primer save: con 'pk is not None' ninguna fila podria
        #  crearse nunca.
        if not self._state.adding:
            raise self.NoSeReescribe(
                f"El evento {self.pk} ya existe. El timeline de una situacion "
                f"solo se agrega: para corregir algo se anota un evento nuevo.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise self.NoSeReescribe(
            "Un evento del timeline no se borra. Si fue un error, se anota el "
            "evento que lo corrige -- borrarlo haria que el historial afirme "
            "algo que no paso.")

    def __str__(self):
        return f"{self.ocurrido_en:%Y-%m-%d %H:%M} {self.tipo}"


# =============================================================================
#  LAS RELACIONES ENTRE SITUACIONES
# =============================================================================

class SituacionRelacion(BaseModel):
    """
    Que una situacion tiene algo que ver con otra. Sin causalidad implicita.

    POR QUE LOS TIPOS ESTAN PARTIDOS EN AUTOMATICOS Y HUMANOS
    --------------------------------------------------------
    Porque la correlacion puede afirmar que dos cosas COINCIDEN --comparten PON,
    OLT o ventana-- y no puede afirmar que una EXPLICA a la otra. Dos eventos
    cercanos en el tiempo no son causa y efecto, y un sistema que los presenta
    asi produce diagnosticos con aire de certeza.

    'situaciones.relacionar' exige un actor para los tipos que no estan en
    'TipoRelacion.AUTOMATICOS', y hay una prueba que lo intenta sin actor.
    """

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="situacion_relaciones")
    origen = models.ForeignKey(
        SituacionOperativa, on_delete=models.CASCADE,
        related_name="relaciones_salientes")
    destino = models.ForeignKey(
        SituacionOperativa, on_delete=models.CASCADE,
        related_name="relaciones_entrantes")

    tipo = models.CharField(max_length=20, choices=TipoRelacion.ETIQUETAS)
    #  Por que se las relaciono. Obligatorio: una relacion sin motivo es una
    #  afirmacion sin respaldo.
    motivo = models.CharField(max_length=255)
    creada_en = models.DateTimeField()
    actor = models.ForeignKey(
        Profile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="relaciones_de_situacion")

    class Meta:
        db_table = "operaciones_situacion_relacion"
        ordering = ["-creada_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["origen", "destino", "tipo"],
                name="relacion_unica_por_tipo"),
            #  Una situacion no se relaciona consigo misma: seria una relacion
            #  que no dice nada y que ensucia cualquier recorrido del grafo.
            models.CheckConstraint(
                condition=~models.Q(origen=models.F("destino")),
                name="relacion_no_consigo_misma"),
            models.CheckConstraint(condition=~models.Q(motivo=""),
                                   name="relacion_con_motivo"),
        ]

    def __str__(self):
        return f"{self.origen_id} {self.tipo} {self.destino_id}"
