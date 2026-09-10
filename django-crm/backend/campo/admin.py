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
    readonly_fields = ("recibida_en_servidor", "bytes", "sha256")


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
    readonly_fields = ("created_at", "updated_at", "revision")
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
    readonly_fields = ("recibida_en_servidor", "created_at", "updated_at")
