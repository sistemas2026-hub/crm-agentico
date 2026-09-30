# -*- coding: utf-8 -*-
"""Configuración del panel de administración Django para el dominio Campo."""

from django.contrib import admin
from django.utils.html import format_html

from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    EvidenciaTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)


class AsignacionTrabajoInline(admin.TabularInline):
    model = AsignacionTrabajo
    extra = 0
    fields = ("profile", "rol", "es_principal", "asignado_en")
    readonly_fields = ("asignado_en",)


class EvidenciaTrabajoInline(admin.TabularInline):
    model = EvidenciaTrabajo
    extra = 0
    fields = ("requisito_id", "nombre_original", "estado_archivo", "bytes", "recibida_en_servidor")
    # TODOS de solo lectura, no solo tres. 'estado_archivo' quedaba editable, y
    # es el campo que decide si el checklist esta completo: ponerlo a mano en
    # 'recibido' deja cerrar una orden sin que exista el archivo (ver
    # validador.verificar_checklist_completo, que solo mira el estado).
    readonly_fields = ("requisito_id", "nombre_original", "estado_archivo",
                       "bytes", "recibida_en_servidor", "sha256")

    def has_add_permission(self, request, obj=None):
        # Una evidencia nace subiendo un archivo, no escribiendo una fila.
        return False


class EventoTrabajoInline(admin.TabularInline):
    model = EventoTrabajo
    extra = 0
    fields = ("tipo", "profile", "datos", "created_at")
    readonly_fields = ("tipo", "profile", "datos", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrdenTrabajo)
class OrdenTrabajoAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "cliente_nombre",
        "cliente_telefono",
        "estado_badge",
        "validacion_badge",
        "tecnico_responsable",
        "origen_info",
        "created_at",
    )
    list_filter = (
        "estado_operativo",
        "estado_validacion",
        "origen_sistema",
        "org",
        "tipo_trabajo_version__work_type",
    )
    search_fields = (
        "numero",
        "cliente_nombre",
        "cliente_telefono",
        "cliente_direccion",
        "origen_ref",
    )
    # Lo que escribe 'services/transiciones.py' no se toca desde aca.
    #
    # '_aplicar_transicion' hace CUATRO cosas juntas: comprueba que el paso sea
    # legal contra TRANSICIONES_PERMITIDAS, sube 'revision', sella las fechas y
    # escribe la bitacora ('EventoTrabajo'). Editar 'estado_operativo' a mano
    # se saltea las cuatro -- y la peor no es la primera: deja la bitacora con
    # un hueco justo donde el estado cambio, que es donde alguien va a mirar.
    #
    # 'datos' tampoco: lo valida 'validar_campos_tecnicos' contra la plantilla
    # inmutable, y 'revision' es el control de concurrencia con la cola offline
    # del movil. Escribirlo crudo puede guardar lo que el esquema rechazaria y
    # pisar el trabajo de un tecnico sin que la app se entere.
    #
    # 'estado_validacion' SI queda editable, a proposito: hoy ningun codigo lo
    # escribe -- el flujo de aprobacion no existe todavia -- asi que esto es lo
    # unico que puede moverlo. Cuando exista, entra a esta lista.
    readonly_fields = (
        "created_at", "updated_at", "revision", "numero",
        "estado_operativo",
        "iniciada_en", "completada_campo_en", "cerrada_en",
        "datos",
    )
    inlines = [AsignacionTrabajoInline, EvidenciaTrabajoInline, EventoTrabajoInline]
    fieldsets = (
        (
            "Identificación y Organización",
            {
                "fields": (
                    "org",
                    "numero",
                    "tipo_trabajo_version",
                    "revision",
                )
            },
        ),
        (
            "Cliente y Ubicación",
            {
                "fields": (
                    "cliente_nombre",
                    "cliente_telefono",
                    "cliente_direccion",
                    ("gps_lat", "gps_lng"),
                )
            },
        ),
        (
            "Origen (Ticket / WispHub / CRM)",
            {
                "fields": (
                    "origen_sistema",
                    "origen_tipo",
                    "origen_ref",
                    "diagnostico_previo",
                )
            },
        ),
        (
            "Estados y Tiempos",
            {
                "fields": (
                    ("estado_operativo", "estado_validacion"),
                    ("programada_para", "iniciada_en"),
                    ("completada_campo_en", "cerrada_en"),
                )
            },
        ),
        (
            "Datos Técnicos Recolectados",
            {
                "fields": ("datos",),
                "classes": ("collapse",),
            },
        ),
        (
            "Auditoría",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Técnico Principal")
    def tecnico_responsable(self, obj: OrdenTrabajo):
        tec = obj.tecnico_principal
        if tec and tec.user:
            return tec.user.name or tec.user.email
        return format_html('<span style="color: #999;">Sin asignar</span>')

    @admin.display(description="Estado Operativo")
    def estado_badge(self, obj: OrdenTrabajo):
        colores = {
            OrdenTrabajo.ASIGNADA: "#17a2b8",
            OrdenTrabajo.EN_CAMINO: "#ffc107",
            OrdenTrabajo.EN_SITIO: "#fd7e14",
            OrdenTrabajo.COMPLETADA_CAMPO: "#28a745",
            OrdenTrabajo.CERRADA: "#6c757d",
            OrdenTrabajo.CANCELADA: "#dc3545",
        }
        color = colores.get(obj.estado_operativo, "#333")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_estado_operativo_display(),
        )

    @admin.display(description="Validación")
    def validacion_badge(self, obj: OrdenTrabajo):
        colores = {
            OrdenTrabajo.SIN_EVALUAR: "#6c757d",
            OrdenTrabajo.PENDIENTE: "#ffc107",
            OrdenTrabajo.APROBABLE: "#17a2b8",
            OrdenTrabajo.APROBADO: "#28a745",
            OrdenTrabajo.REQUIERE_CORRECCION: "#dc3545",
            OrdenTrabajo.REQUIERE_REVISION: "#fd7e14",
        }
        color = colores.get(obj.estado_validacion, "#333")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">{}</span>',
            color,
            obj.get_estado_validacion_display(),
        )

    @admin.display(description="Origen")
    def origen_info(self, obj: OrdenTrabajo):
        if obj.origen_ref:
            return f"{obj.origen_sistema.upper()}: {obj.origen_ref}"
        return obj.origen_sistema.upper()


@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "org", "activo", "created_at")
    list_filter = ("activo", "org")
    search_fields = ("codigo", "nombre")


@admin.register(WorkTypeVersion)
class WorkTypeVersionAdmin(admin.ModelAdmin):
    list_display = (
        "work_type",
        "version",
        "schema_version",
        "estado",
        "publicada_en",
        "schema_hash_short",
    )
    list_filter = ("estado", "schema_version", "work_type__org")
    search_fields = ("work_type__nombre", "work_type__codigo")
    readonly_fields = ("schema_hash", "publicada_en", "created_at", "updated_at")

    @admin.display(description="Hash")
    def schema_hash_short(self, obj: WorkTypeVersion):
        return obj.schema_hash[:10] if obj.schema_hash else "-"


@admin.register(EvidenciaTrabajo)
class EvidenciaTrabajoAdmin(admin.ModelAdmin):
    """
    Una evidencia es un registro de auditoria: se mira, no se corrige.

    Aca 'sha256' quedaba editable mientras en el inline ya estaba protegido --
    la misma columna, dos criterios. Es parte de
    UniqueConstraint(orden_trabajo, requisito_id, sha256), que es lo que impide
    que un reintento del movil duplique la evidencia; y 'storage_key' es lo que
    ata la fila al archivo guardado. Cambiar cualquiera de los dos rompe esa
    relacion sin que nada avise.

    Se puede BORRAR una fila espuria (eso es una decision explicita y deja
    rastro en el log del admin); lo que no se puede es reescribirla para que
    diga otra cosa.
    """
    list_display = (
        "orden_trabajo",
        "requisito_id",
        "nombre_original",
        "estado_archivo",
        "bytes",
        "recibida_en_servidor",
    )
    list_filter = ("estado_archivo", "org")
    search_fields = ("orden_trabajo__numero", "requisito_id", "nombre_original")
    readonly_fields = (
        "org", "orden_trabajo", "requisito_id", "storage_key", "nombre_original",
        "mime_type", "bytes", "sha256", "estado_archivo", "capturada_en_cliente",
        "metadatos_captura", "recibida_en_servidor", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False
