# -*- coding: utf-8 -*-
"""
Rutas de la escritura de casos importados.

Van bajo '/api/importacion/' y no bajo '/api/cases/' a proposito: el alcance de
un token no interactivo se calcula con el PRIMER segmento despues de '/api/'
(ver common/scopes.py), asi que colgarlas de 'cases' obligaria a darle
'cases:write' al motor -- permiso para escribir cualquier caso del CRM. Con
recurso propio, el token del importador lleva 'importacion:write' y no puede
tocar nada mas.
"""

from django.urls import path

from cases import importacion_views as vistas

app_name = "importacion"

urlpatterns = [
    path("tickets-conocidos/", vistas.TicketsConocidosView.as_view(),
         name="tickets_conocidos"),
    path("casos/", vistas.ImportarCaseView.as_view(), name="importar"),
    path("casos-externos/", vistas.CasosExternosView.as_view(), name="casos_externos"),
    path("casos/<uuid:pk>/reconciliar/", vistas.ReconciliarCaseView.as_view(),
         name="reconciliar"),
    path("casos/<uuid:pk>/respuestas/", vistas.RespuestasExternasView.as_view(),
         name="respuestas"),
    #  Va ANTES de 'casos/<uuid:pk>/...' en el orden de lectura mental, pero no
    #  compite con ellas: 'nombre-cliente' no es un UUID, asi que el convertidor
    #  de la ruta de arriba no la captura. La llave de esta es el SERVICIO, no
    #  el caso -- el motor no conoce los ids de los casos.
    path("casos/nombre-cliente/", vistas.NombreClienteView.as_view(),
         name="nombre_cliente"),
]
