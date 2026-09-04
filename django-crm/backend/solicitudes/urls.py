"""Rutas de solicitudes. Publica y anonima: el token es la unica credencial."""

from django.urls import path

from solicitudes.gestion import (
    AjustesView,
    BandejaView,
    DecidirView,
    TecnicosView,
)
from solicitudes.views import SolicitudCrearView, SolicitudPublicaView

app_name = "solicitudes"

urlpatterns = [
    path("public/solicitud/<str:token>/", SolicitudPublicaView.as_view(),
         name="solicitud-publica"),
    # La llama el motor cuando el asistente cierra una venta: crea el lead y
    # su solicitud, y devuelve el link con token. Autenticada.
    path("solicitudes/", SolicitudCrearView.as_view(), name="solicitud-crear"),
    # Lo que usa el equipo, todo autenticado.
    path("solicitudes/bandeja/", BandejaView.as_view(), name="solicitud-bandeja"),
    path("solicitudes/ajustes/", AjustesView.as_view(), name="solicitud-ajustes"),
    path("solicitudes/tecnicos/", TecnicosView.as_view(), name="solicitud-tecnicos"),
    path("solicitudes/<uuid:solicitud_id>/decidir/", DecidirView.as_view(),
         name="solicitud-decidir"),
]
