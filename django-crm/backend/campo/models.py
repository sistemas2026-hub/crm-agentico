# -*- coding: utf-8 -*-
"""Modelos del dominio Campo para operaciones de cuadrillas y app móvil."""

from __future__ import annotations

import hashlib
import json
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from common.base import BaseModel
from common.models import Org, Profile


class WorkType(BaseModel):
    """Catálogo de tipos de trabajo configurados por organización."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="work_types")
    codigo = models.CharField(max_length=64)
    nombre = models.CharField(max_length=128)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "campo_work_type"
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "codigo"],
                name="unique_work_type_codigo_per_org",
            )
        ]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.codigo})"


class WorkTypeVersionQuerySet(models.QuerySet):
    """Protege la inmutabilidad contra escrituras directas por queryset.update()."""

    CAMPOS_PROTEGIDOS = {
        "work_type",
        "work_type_id",
        "version",
        "schema_version",
        "esquema",
        "schema_hash",
    }

    def update(self, **kwargs):
        # Bloquear mutación directa si el queryset incluye versiones publicadas o retiradas
        congeladas = self.filter(estado__in=[WorkTypeVersion.PUBLICADA, WorkTypeVersion.RETIRADA])
        if congeladas.exists():
            if any(campo in kwargs for campo in self.CAMPOS_PROTEGIDOS):
                raise ValidationError(
                    "Operación prohibida: No se permite modificar el esquema ni la definición de versiones "
                    "PUBLICADAS o RETIRADAS mediante update() de ORM. Cree una nueva versión vN+1."
                )
            if kwargs.get("estado") == WorkTypeVersion.BORRADOR:
                raise ValidationError(
                    "Operación prohibida: Una versión PUBLICADA o RETIRADA no puede regresar a BORRADOR."
                )
        return super().update(**kwargs)


class WorkTypeVersion(BaseModel):
    """
    Versión inmutable de una plantilla de trabajo.
    Inmutabilidad garantizada por dominio, Custom QuerySet y servicio;
    escrituras directas por ORM quedan interceptadas.
    """

    BORRADOR = "borrador"
    PUBLICADA = "publicada"
    RETIRADA = "retirada"
    ESTADOS = (
        (BORRADOR, "Borrador"),
        (PUBLICADA, "Publicada"),
        (RETIRADA, "Retirada"),
    )

    work_type = models.ForeignKey(
        WorkType, on_delete=models.CASCADE, related_name="versions"
    )
    version = models.PositiveIntegerField(default=1)
    schema_version = models.PositiveIntegerField(
        default=1,
        help_text="Versión del contrato de interfaz que entiende la aplicación móvil",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default=BORRADOR)
    esquema = models.JSONField(
        default=dict,
        help_text="Pasos, campos técnicos, evidencias requeridas y validaciones deterministas",
    )
    schema_hash = models.CharField(max_length=64, blank=True, default="")
    publicada_en = models.DateTimeField(null=True, blank=True)

    objects = WorkTypeVersionQuerySet.as_manager()

    class Meta:
        db_table = "campo_work_type_version"
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["work_type", "version"],
                name="unique_version_per_work_type",
            )
        ]

    def __str__(self) -> str:
        return f"{self.work_type.nombre} v{self.version} [{self.get_estado_display()}]"

    def clean(self):
        super().clean()
        if self.pk:
            original = WorkTypeVersion.objects.filter(pk=self.pk).first()
            if original and original.estado == self.PUBLICADA:
                # Una versión publicada SOLO puede cambiar su estado a RETIRADA
                if self.estado not in (self.PUBLICADA, self.RETIRADA):
                    raise ValidationError(
                        "Una versión de trabajo PUBLICADA no puede regresar a borrador."
                    )
                # El resto de los campos de definición son inmutables
                campos_inmutables = [
                    "work_type_id",
                    "version",
                    "schema_version",
                    "esquema",
                    "schema_hash",
                ]
                for campo in campos_inmutables:
                    if getattr(self, campo) != getattr(original, campo):
                        raise ValidationError(
                            f"El campo '{campo}' no puede modificarse en una versión PUBLICADA. "
                            "Cree una nueva versión (vN+1) para alterar la plantilla."
                        )

    def save(self, *args, **kwargs):
        self.clean()
        # Si se publica por primera vez, congelar hash y fecha de publicación
        if self.estado == self.PUBLICADA and not self.publicada_en:
            self.publicada_en = timezone.now()
            canonica = json.dumps(self.esquema, sort_keys=True, separators=(",", ":"))
            self.schema_hash = hashlib.sha256(canonica.encode("utf-8")).hexdigest()
        super().save(*args, **kwargs)


class OrdenTrabajo(BaseModel):
    """Orden de trabajo unificada de campo (Instalación, Correctivo, Mantenimiento, etc.)."""

    ASIGNADA = "asignada"
    EN_CAMINO = "en_camino"
    EN_SITIO = "en_sitio"
    COMPLETADA_CAMPO = "completada_campo"
    # El supervisor devolvio el trabajo. La orden vuelve a estar disponible
    # para el tecnico, con una vuelta mas y una lista de que hay que rehacer.
    # No es "en proceso otra vez": es un estado propio para poder contarlo,
    # filtrarlo en la bandeja y medir cuantas ordenes se aprueban a la primera.
    CORRECCION_REQUERIDA = "correccion_requerida"
    CERRADA = "cerrada"
    CANCELADA = "cancelada"
    ESTADOS_OPERATIVOS = (
        (ASIGNADA, "Asignada"),
        (EN_CAMINO, "En camino"),
        (EN_SITIO, "En sitio"),
        (COMPLETADA_CAMPO, "Completada en campo"),
        (CORRECCION_REQUERIDA, "Corrección requerida"),
        (CERRADA, "Cerrada"),
        (CANCELADA, "Cancelada"),
    )

    SIN_EVALUAR = "sin_evaluar"
    PENDIENTE = "pendiente"
    APROBABLE = "aprobable"
    REQUIERE_CORRECCION = "requiere_correccion"
    REQUIERE_REVISION = "requiere_revision"
    APROBADO = "aprobado"
    ESTADOS_VALIDACION = (
        (SIN_EVALUAR, "Sin evaluar"),
        (PENDIENTE, "Pendiente de validación"),
        (APROBABLE, "Aprobable"),
        (REQUIERE_CORRECCION, "Requiere corrección"),
        (REQUIERE_REVISION, "Requiere revisión humana"),
        (APROBADO, "Aprobado"),
    )

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="ordenes_trabajo")
    numero = models.PositiveIntegerField(help_text="Consecutivo interno por organización")
    tipo_trabajo_version = models.ForeignKey(
        WorkTypeVersion, on_delete=models.PROTECT, related_name="ordenes"
    )

    # Origen desacoplado (polimórfico sin GenericForeignKey)
    origen_sistema = models.CharField(
        max_length=64,
        default="manual",
        help_text="Sistema originador: wisphub, solicitudes, crm, manual",
    )
    origen_tipo = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Entidad originadora: ticket, solicitud, case, orden_manual",
    )
    origen_ref = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="ID o número del origen externo (ej. #91288)",
    )

    # Datos del cliente y ubicación física
    cliente_nombre = models.CharField(max_length=255)
    cliente_telefono = models.CharField(max_length=64, blank=True, default="")
    cliente_direccion = models.CharField(max_length=255)
    gps_lat = models.FloatField(null=True, blank=True)
    gps_lng = models.FloatField(null=True, blank=True)

    # Contexto técnico y datos recolectados
    diagnostico_previo = models.JSONField(
        default=dict,
        blank=True,
        help_text="Diagnóstico previo arrojado por el asistente IA en WhatsApp o SmartOLT",
    )
    datos = models.JSONField(
        default=dict,
        blank=True,
        help_text="Valores de campos técnicos diligenciados en campo (serial_ont, potencia_rx, etc.)",
    )
    revision = models.PositiveIntegerField(
        default=1,
        help_text="Control de concurrencia optimista para sincronización offline",
    )

    # Estados
    estado_operativo = models.CharField(
        max_length=32, choices=ESTADOS_OPERATIVOS, default=ASIGNADA
    )
    estado_validacion = models.CharField(
        max_length=32, choices=ESTADOS_VALIDACION, default=SIN_EVALUAR
    )

    # Cuantas veces se presento este trabajo a validacion. Empieza en 1 y sube
    # con cada devolucion.
    #
    # No es lo mismo que 'revision', que cuenta ESCRITURAS y existe para que la
    # cola offline detecte que alguien piso sus datos. 'vuelta' cuenta INTENTOS
    # de dar el trabajo por terminado, que es una nocion del negocio: de aca
    # salen "aprobadas a la primera" y "cuantas veces volvio".
    vuelta = models.PositiveIntegerField(
        default=1,
        help_text="Presentacion a validacion. Sube con cada devolucion a correccion.",
    )

    # Lo que se sabia del cliente y del equipo CUANDO SE DESPACHO al tecnico.
    #
    # Es una fotografia, no una fuente de verdad: el Case sigue resolviendo en
    # vivo contra el sistema del ISP en cada apertura. Aca se congela porque el
    # tecnico sale sin red y porque, al cerrar el trabajo, importa contra que
    # datos se lo despacho -- la ONU pudo haberse reemplazado desde entonces.
    #
    # Solo campos ya filtrados por las listas blancas del motor: nunca la
    # respuesta cruda del proveedor, que trae cuatro contraseñas y el GPS del
    # domicilio. Toda medicion viva viaja con su hora adentro.
    contexto = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot tecnico al momento de crear la orden. Historico, no vigente.",
    )

    # Tiempos
    programada_para = models.DateTimeField(null=True, blank=True)
    iniciada_en = models.DateTimeField(null=True, blank=True)
    completada_campo_en = models.DateTimeField(null=True, blank=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "campo_orden_trabajo"
        ordering = ["-numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "numero"],
                name="unique_numero_orden_per_org",
            ),
            # Una sola orden por identidad externa, PERO solo donde duplicar
            # seria un error de maquina.
            #
            # 'wisphub' y 'solicitudes' entran por importadores automaticos: si
            # aparecen dos ordenes para el mismo ticket, eso es un bug y la base
            # tiene que cortarlo. 'crm' y 'manual' los origina una persona, y
            # una segunda visita al mismo caso es normal -- la falla volvio dos
            # dias despues, hay que rehacer el trabajo, hay una etapa mas. Ahi
            # el duplicado accidental se evita con Idempotency-Key, que es el
            # mecanismo para "el mismo clic dos veces", no con una restriccion
            # que tambien prohibe la segunda visita legitima.
            models.UniqueConstraint(
                fields=["org", "origen_sistema", "origen_tipo", "origen_ref"],
                condition=~models.Q(origen_sistema__in=["manual", "crm"]),
                name="unique_origen_externo_por_org",
            ),
        ]

    def __str__(self) -> str:
        return f"OT #{self.numero} - {self.cliente_nombre} ({self.get_estado_operativo_display()})"

    @property
    def tecnico_principal(self) -> Profile | None:
        """Fuente única de verdad: obtiene el responsable principal desde AsignacionTrabajo."""
        asig = (
            self.asignaciones.filter(es_principal=True)
            .select_related("profile__user")
            .first()
        )
        return asig.profile if asig else None


class AsignacionTrabajo(BaseModel):
    """Asignación de un colaborador o cuadrilla a una orden de trabajo."""

    orden = models.ForeignKey(
        OrdenTrabajo, on_delete=models.CASCADE, related_name="asignaciones"
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="asignaciones_campo"
    )
    rol = models.CharField(
        max_length=64,
        default="tecnico",
        help_text="Rol en la cuadrilla: tecnico, ayudante, chofer, supervisor",
    )
    es_principal = models.BooleanField(
        default=False,
        help_text="Marca si este técnico es el responsable principal de la orden",
    )
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "campo_asignacion_trabajo"
        ordering = ["-es_principal", "asignado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["orden", "profile"],
                name="unique_profile_per_orden",
            ),
            models.UniqueConstraint(
                fields=["orden"],
                condition=models.Q(es_principal=True),
                name="unique_tecnico_principal_por_orden",
            ),
        ]

    def __str__(self) -> str:
        quien = self.profile.user.name or self.profile.user.email
        cargo = " (Principal)" if self.es_principal else ""
        return f"{quien} -> OT #{self.orden.numero}{cargo}"


class EventoTrabajo(BaseModel):
    """Bitácora append-only de eventos y auditoría operativa de campo."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="eventos_campo")
    orden = models.ForeignKey(
        OrdenTrabajo, on_delete=models.CASCADE, related_name="eventos"
    )
    tipo = models.CharField(
        max_length=64,
        help_text="Ej: orden_creada, tecnico_asignado, trabajo_iniciado, datos_actualizados, etc.",
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.SET_NULL, null=True, blank=True
    )
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "campo_evento_trabajo"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"OT #{self.orden.numero}: {self.tipo} ({self.created_at})"


class EvidenciaTrabajo(BaseModel):
    """Evidencia fotográfica o documental de campo ligada a un requisito."""

    PENDIENTE = "pendiente"
    SUBIENDO = "subiendo"
    RECIBIDO = "recibido"
    VERIFICADO = "verificado"
    FALLIDO = "fallido"
    ESTADOS_ARCHIVO = (
        (PENDIENTE, "Pendiente"),
        (SUBIENDO, "Subiendo"),
        (RECIBIDO, "Recibido"),
        (VERIFICADO, "Verificado"),
        (FALLIDO, "Fallido"),
    )

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="evidencias_campo")
    orden_trabajo = models.ForeignKey(
        OrdenTrabajo, on_delete=models.CASCADE, related_name="evidencias"
    )
    requisito_id = models.CharField(
        max_length=64,
        help_text="Identificador del requisito en la versión de plantilla (ej. foto_ont)",
    )
    # En que presentacion del trabajo se tomo esta evidencia. La pone el
    # servidor desde 'orden.vuelta' -- nunca el cliente, que podria declarar
    # cualquier numero y dar por corregido lo que no corrigio.
    #
    # Sirve para que una foto de la vuelta 1 no satisfaga un requisito que el
    # supervisor devolvio en la vuelta 2. Sin esto la devolucion no tendria
    # dientes: el checklist mira si EXISTE evidencia del requisito, y la vieja
    # sigue ahi.
    vuelta = models.PositiveIntegerField(default=1)
    storage_key = models.CharField(max_length=255, blank=True, default="")
    nombre_original = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=128)
    bytes = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    estado_archivo = models.CharField(
        max_length=32, choices=ESTADOS_ARCHIVO, default=PENDIENTE
    )
    capturada_en_cliente = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp del reloj del dispositivo en el momento de la captura",
    )
    recibida_en_servidor = models.DateTimeField(auto_now_add=True)
    metadatos_captura = models.JSONField(
        default=dict,
        blank=True,
        help_text="Metadatos técnicos: coordenadas GPS del móvil, precisión, modelo, etc.",
    )

    class Meta:
        db_table = "campo_evidencia_trabajo"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["orden_trabajo", "requisito_id", "sha256"],
                name="unique_evidencia_requisito_sha",
            )
        ]

    def __str__(self) -> str:
        return f"Evidencia {self.requisito_id} en OT #{self.orden_trabajo.numero}"


class MutacionIdempotente(BaseModel):
    """Registro de control de idempotencia para mutaciones offline y reintentos móviles."""

    PROCESANDO = "procesando"
    COMPLETADA = "completada"
    ESTADOS = (
        (PROCESANDO, "Procesando"),
        (COMPLETADA, "Completada"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="mutaciones_idempotentes"
    )
    idempotency_key = models.CharField(max_length=128, db_index=True)
    http_method = models.CharField(max_length=10)
    endpoint = models.CharField(max_length=255)
    request_hash = models.CharField(
        max_length=64,
        help_text="SHA256 del cuerpo canónico de la petición",
    )
    status_code = models.PositiveIntegerField(null=True, blank=True)
    respuesta_json = models.JSONField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=PROCESANDO)

    class Meta:
        db_table = "campo_mutacion_idempotente"
        constraints = [
            models.UniqueConstraint(
                fields=["org", "idempotency_key"],
                name="unique_idempotency_key_per_org",
            )
        ]

    def __str__(self) -> str:
        return f"{self.org.name} - Key {self.idempotency_key} [{self.estado}]"
