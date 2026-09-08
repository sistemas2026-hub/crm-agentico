# -*- coding: utf-8 -*-
"""Rutas de la API REST del módulo campo."""

from django.urls import path

from campo import views

app_name = "campo"

urlpatterns = [
    path("bootstrap/", views.BootstrapView.as_view(), name="bootstrap"),
    path("trabajos/", views.TrabajosListView.as_view(), name="trabajos_list"),
    path("trabajos/<uid:pk>/", views.TrabajoDetailView.as_view(), name="trabajo_detail"),
    path("trabajos/<uid:pk>/acciones/", views.AccionesTrabajoView.as_view(), name="trabajo_acciones"),
    path("trabajos/<uid:pk>/datos/", views.GuardarDatosTrabajoView.as_view(), name="trabajo_datos"),
    path("trabajos/<uid:pk>/evidencias/", views.EvidenciasTrabajoView.as_view(), name="trabajo_evidencias"),
    path("trabajos/<uid:pk>/completar/", views.CompletarTrabajoView.as_view(), name="trabajo_completar"),
    path("evidencias/<uid:pk>/confirmar/", views.ConfirmarEvidenciaView.as_view(), name="evidencia_confirmar"),
    path("evidencias/<uid:pk>/url/", views.ObtenerUrlEvidenciaView.as_view(), name="evidencia_url"),
]
