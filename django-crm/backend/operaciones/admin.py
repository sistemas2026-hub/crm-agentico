# -*- coding: utf-8 -*-
"""
Registro minimo en el admin de Django.

Solo LECTURA para las propuestas: moverlas de estado tiene que pasar por
'supervisor.revisar', que es lo unico que deja auditoria. Un admin que permita
editar el estado a mano abre un camino sin rastro.
"""

from django.contrib import admin

from operaciones.models import (
    ActividadOperativa,
    DisponibilidadTecnico,
    NovedadOperativa,
    ProgramacionOrden,
    ProgramacionSemanal,
    PropuestaSupervisor,
)


@admin.register(PropuestaSupervisor)
class PropuestaSupervisorAdmin(admin.ModelAdmin):
    list_display = ("tipo_senal", "accion_propuesta", "prioridad", "estado",
                    "nivel_autonomia_requerido", "created_at")
    list_filter = ("estado", "tipo_senal", "nivel_autonomia_requerido")
    search_fields = ("accion_propuesta", "origen_id")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


admin.site.register(ActividadOperativa)
admin.site.register(DisponibilidadTecnico)
admin.site.register(ProgramacionSemanal)
admin.site.register(ProgramacionOrden)
admin.site.register(NovedadOperativa)
