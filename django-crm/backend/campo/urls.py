# -*- coding: utf-8 -*-
"""Rutas de la API REST del módulo campo."""

from django.urls import path

from campo import despacho_views, views

app_name = "campo"

urlpatterns = [
    path("bootstrap/", views.BootstrapView.as_view(), name="bootstrap"),
    path("trabajos/", views.TrabajosListView.as_view(), name="trabajos_list"),
    # Despacho: lo que hace la oficina, no el tecnico.
    path("trabajos/crear/", despacho_views.CrearOrdenView.as_view(), name="trabajo_crear"),
    path("trabajos/<uid:pk>/asignar/", despacho_views.AsignarTrabajoView.as_view(), name="trabajo_asignar"),
    path("trabajos/<uid:pk>/validar/", despacho_views.ValidarTrabajoView.as_view(), name="trabajo_validar"),
    path("trabajos/<uid:pk>/", views.TrabajoDetailView.as_view(), name="trabajo_detail"),
    path("trabajos/<uid:pk>/acciones/", views.AccionesTrabajoView.as_view(), name="trabajo_acciones"),
    path("trabajos/<uid:pk>/datos/", views.GuardarDatosTrabajoView.as_view(), name="trabajo_datos"),
    path("trabajos/<uid:pk>/evidencias/", views.EvidenciasTrabajoView.as_view(), name="trabajo_evidencias"),
    path("trabajos/<uid:pk>/completar/", views.CompletarTrabajoView.as_view(), name="trabajo_completar"),
    # Solo backend local de desarrollo: en produccion la subida va
    # directo al proveedor con una URL prefirmada y esta vista devuelve
    # 404. Ver CampoStorage.descriptor_subida.
    path("evidencias/<uid:pk>/subir/", views.SubirEvidenciaDirectoView.as_view(), name="evidencia_subir"),
    path("evidencias/<uid:pk>/confirmar/", views.ConfirmarEvidenciaView.as_view(), name="evidencia_confirmar"),
    path("evidencias/<uid:pk>/url/", views.ObtenerUrlEvidenciaView.as_view(), name="evidencia_url"),
]
