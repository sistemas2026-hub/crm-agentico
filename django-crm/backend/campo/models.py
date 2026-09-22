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

        # Una plantilla se vuelve inmutable al publicarse, y a partir de ahi
        # viaja a los telefonos. Si su vocabulario no es el que la aplicacion
        # sabe ejecutar, el error no aparece aca: aparece en la calle, cuando
        # el tecnico abre la orden y el formulario no se puede responder.
        #
        # `validar_esquema_plantilla` existia desde el principio y no la
        # llamaba nadie (hallazgo del inventario del 22/09/2026). Se llama al
        # publicar, no en borrador: un borrador puede estar a medias.
        if self.estado == self.PUBLICADA and self.schema_version == 1:
            from campo.services.validador import validar_esquema_plantilla

            validar_esquema_plantilla(self.esquema or {})

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

    # Como se entra al inmueble: torre, piso, apartamento, a quien preguntar.
    #
    # Sin esto el tecnico llega al edificio y no al apartamento. La direccion
    # sola alcanza para el GPS y no para tocar la puerta correcta.
    cliente_detalle_acceso = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Torre, piso, apartamento, portería: cómo se entra.",
    )

    # El identificador del abonado en el sistema del ISP. Sirve para que el
    # tecnico lo dicte por telefono al NOC sin tener que buscarlo.
    cliente_id_abonado = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Identificador del abonado en el sistema del ISP (ej. WispHub).",
    )

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

    # --- Lo que la orden promete -------------------------------------------

    #: Prioridades. Se ordena por ellas, asi que el valor guardado importa.
    PRIORIDAD_ALTA = "alta"
    PRIORIDAD_MEDIA = "media"
    PRIORIDAD_BAJA = "baja"
    PRIORIDADES = [
        (PRIORIDAD_ALTA, "Alta"),
        (PRIORIDAD_MEDIA, "Media"),
        (PRIORIDAD_BAJA, "Baja"),
    ]

    prioridad = models.CharField(
        max_length=10,
        choices=PRIORIDADES,
        default=PRIORIDAD_MEDIA,
        db_index=True,
        help_text="Con qué urgencia se despacha. Ordena la lista del técnico.",
    )

    zona = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_index=True,
        help_text="Zona operativa del trabajo. Agrupa la jornada por cercanía.",
    )

    resumen = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Qué hay que hacer, en una línea. El tipo de trabajo dice la "
                  "categoría; esto dice el caso.",
    )

    # La franja que se le prometio al cliente.
    #
    # No alcanza con 'programada_para', que es un instante: al abonado se le
    # dice "entre 9 y 11", y el SLA de la visita se mide contra esa franja.
    ventana_inicio = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Comienzo de la franja comprometida con el cliente.",
    )
    ventana_fin = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fin de la franja comprometida con el cliente.",
    )

    # Cuando vence el compromiso de atencion.
    #
    # El telefono no puede calcularlo: no sabe las reglas de SLA de la empresa
    # ni su calendario laboral. Si lo calculara, cada version de la aplicacion
    # tendria su propia idea de cuando una orden esta vencida.
    sla_vence_en = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Cuándo vence el compromiso. Lo calcula el backend, no la app.",
    )

    # Que hace falta para poder ejecutar este trabajo.
    #
    # Lista de identificadores de requisito (trabajo en altura, espacios
    # confinados, certificacion electrica). Se MUESTRA; no habilita ni bloquea:
    # decidir si alguien puede subir a un poste exige saber si su certificacion
    # esta vigente, y eso todavia no vive en ningun lado.
    requisitos_seguridad = models.JSONField(
        default=list,
        blank=True,
        help_text="Requisitos de seguridad del trabajo. Se informan; no habilitan.",
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


# =============================================================================
# Materiales: la custodia del tecnico
#
# POR QUE ESTO VIVE EN DEXTER Y NO ES UN ESPEJO DEL ISP
# -----------------------------------------------------
# La pregunta quedo abierta en SPEC/BACKEND_CAMPO_DATOS.md (tanda 4) y se
# resolvio mirando que expone el ISP: WispHub y SmartOLT hablan de equipos ya
# instalados en un cliente (consultar_estado_ont, cambiar_tipo_onu), no de
# bodega ni de custodia. No hay de que ser espejo. Y hacerlo depender del
# sistema de cada empresa obligaria a una integracion distinta por tenant, que
# es justo lo que la regla multi-tenant del proyecto prohibe.
#
# Lo que si viaja hacia el ISP es el serial instalado, que ya va hoy en el
# `datos_json` de la orden.
#
# LA DECISION QUE ORDENA TODO EL DISENO
# -------------------------------------
# Un movimiento de material **es un hecho que ya ocurrio en la calle**, no una
# solicitud que el servidor pueda aprobar. Cuando el telefono lo envia, el
# conector ya esta ponchado y los metros de fibra ya no estan en la bobina.
#
# De ahi sale todo lo demas: la tabla es append-only como la bitacora, el saldo
# se calcula y no se guarda, y un consumo que deja el saldo en negativo **se
# acepta igual** y se marca como descuadre. Rechazarlo no devolveria el
# material a la camioneta: solo borraria el unico registro de que se uso, y
# dejaria al tecnico explicando de memoria a fin de mes.
# =============================================================================


class MaterialCatalogo(BaseModel):
    """Que materiales maneja esta empresa. Uno por codigo y por organizacion."""

    CONSUMIBLE = "consumible"
    BOBINA = "bobina"
    SERIALIZADO = "serializado"
    TERMINAL = "terminal"
    CLASES = (
        (CONSUMIBLE, "Consumible"),
        (BOBINA, "Bobina"),
        (SERIALIZADO, "Serializado"),
        (TERMINAL, "Terminal"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="materiales_campo"
    )
    codigo = models.CharField(max_length=64)
    nombre = models.CharField(max_length=200)
    categoria = models.CharField(max_length=100, blank=True, default="")
    clase = models.CharField(max_length=20, choices=CLASES, default=CONSUMIBLE)
    unidad = models.CharField(
        max_length=20,
        default="unidades",
        help_text="Como se cuenta: unidades, m, kg.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "campo_material_catalogo"
        ordering = ["categoria", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "codigo"], name="unique_material_codigo_por_org"
            )
        ]

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nombre}"

    @property
    def es_serializado(self) -> bool:
        return self.clase == self.SERIALIZADO

    @property
    def admite_fraccion(self) -> bool:
        """Una bobina se consume en metros con decimales; un conector, no."""
        return self.clase == self.BOBINA


class EntregaDeKit(BaseModel):
    """El acta de lo que la bodega le entrego a un tecnico.

    Es el punto de partida de la custodia: sin una entrega, un consumo no
    tiene contra que descontarse.
    """

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="kits_campo")
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="kits_recibidos"
    )
    acta = models.CharField(max_length=64, blank=True, default="")
    despachado_por = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kits_despachados",
    )
    entregado_en = models.DateTimeField(default=timezone.now)
    confirmado_en = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Cuando el tecnico confirmo que recibio lo que dice el acta.",
    )
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_entrega_kit"
        ordering = ["-entregado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "acta"],
                condition=models.Q(acta__gt=""),
                name="unique_acta_por_org",
            )
        ]

    def __str__(self) -> str:
        return f"Kit {self.acta or self.pk}"


class ItemDeKit(BaseModel):
    """Una linea del acta: cuanto de un material se entrego."""

    entrega = models.ForeignKey(
        EntregaDeKit, on_delete=models.CASCADE, related_name="items"
    )
    material = models.ForeignKey(
        MaterialCatalogo, on_delete=models.PROTECT, related_name="entregas"
    )
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    serie = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Solo para material serializado. Una serie, una unidad.",
    )

    class Meta:
        db_table = "campo_item_kit"
        constraints = [
            # Una serie no se entrega dos veces sin haber vuelto: es el mismo
            # aparato fisico.
            models.UniqueConstraint(
                fields=["material", "serie"],
                condition=models.Q(serie__gt=""),
                name="unique_serie_entregada_por_material",
            )
        ]

    def __str__(self) -> str:
        return f"{self.material.codigo} x{self.cantidad}"


class MovimientoDeMaterial(BaseModel):
    """Append-only: lo que se consumio, se devolvio o se ajusto.

    Nunca se edita ni se borra. Corregir un movimiento es registrar otro en
    sentido contrario, igual que en cualquier libro contable, porque lo que
    paso en la calle paso y el registro tiene que poder explicarlo despues.
    """

    CONSUMO = "consumo"
    DEVOLUCION = "devolucion"
    AJUSTE = "ajuste"
    TIPOS = (
        (CONSUMO, "Consumo"),
        (DEVOLUCION, "Devolucion"),
        (AJUSTE, "Ajuste"),
    )

    #: El movimiento entro y cuadra con lo que el tecnico tenia.
    ACEPTADO = "aceptado"
    #: Entro, pero deja el saldo en negativo. El hecho se respeta; la oficina
    #: tiene que mirarlo.
    DESCUADRE = "descuadre"
    #: Una serie que otro ya consumio. Dos tecnicos no instalaron la misma ONT.
    CONFLICTO = "conflicto"
    ESTADOS = (
        (ACEPTADO, "Aceptado"),
        (DESCUADRE, "Descuadre"),
        (CONFLICTO, "Conflicto"),
    )

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="movimientos_material"
    )
    profile = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_material",
    )
    material = models.ForeignKey(
        MaterialCatalogo, on_delete=models.PROTECT, related_name="movimientos"
    )
    orden = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_material",
        help_text="En que trabajo se uso. Vacio para una devolucion de jornada.",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS, default=CONSUMO)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    serie = models.CharField(max_length=128, blank=True, default="")
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ACEPTADO)
    motivo = models.TextField(
        blank=True,
        default="",
        help_text="Por que quedo en descuadre o conflicto, en palabras.",
    )
    idempotency_key = models.CharField(max_length=128, db_index=True)
    ocurrido_en = models.DateTimeField(
        default=timezone.now,
        help_text=(
            "Cuando paso en la calle, segun el telefono. No es created_at: un "
            "movimiento sin senal puede llegar horas despues, y el orden del "
            "consumo importa para explicar un saldo."
        ),
    )
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "campo_movimiento_material"
        ordering = ["ocurrido_en", "created_at"]
        constraints = [
            # El reenvio de una cola offline no puede duplicar un consumo.
            models.UniqueConstraint(
                fields=["org", "idempotency_key"],
                name="unique_movimiento_idempotente_por_org",
            ),
            # Un serializado se consume una sola vez. El segundo intento entra
            # como conflicto, no como consumo, y por eso la condicion mira el
            # estado: los conflictos pueden repetirse, los consumos buenos no.
            models.UniqueConstraint(
                fields=["org", "material", "serie"],
                condition=models.Q(serie__gt="", tipo="consumo", estado="aceptado"),
                name="unique_serie_consumida_por_org",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} {self.material.codigo} x{self.cantidad}"


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
