"""Rutas de solicitudes. Publica y anonima: el token es la unica credencial."""

from django.urls import path

from solicitudes.views import SolicitudPublicaView

app_name = "solicitudes"

urlpatterns = [
    path("public/solicitud/<str:token>/", SolicitudPublicaView.as_view(),
         name="solicitud-publica"),
]
