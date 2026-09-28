# -*- coding: utf-8 -*-
"""Rutas de la API REST del módulo campo."""

from django.urls import path

from campo import (
    despacho_views,
    inventario_operacion_views,
    inventario_views,
    materiales_views,
    views,
)

app_name = "campo"

urlpatterns = [
    path("bootstrap/", views.BootstrapView.as_view(), name="bootstrap"),
    path("trabajos/", views.TrabajosListView.as_view(), name="trabajos_list"),
    # Materiales: la custodia del tecnico y lo que gasta en la calle.
    path("kit/", materiales_views.KitView.as_view(), name="kit"),
    path(
        "materiales/movimientos/",
        materiales_views.MovimientosMaterialView.as_view(),
        name="materiales_movimientos",
    ),
    path(
        "materiales/incidencias/",
        materiales_views.IncidenciasMaterialView.as_view(),
        name="materiales_incidencias",
    ),
    path("jornada/", materiales_views.JornadaView.as_view(), name="jornada"),
    path(
        "jornada/cerrar/",
        materiales_views.CerrarJornadaView.as_view(),
        name="jornada_cerrar",
    ),
    # Inventario: lo que hace la oficina. Ver campo/inventario_views.py sobre
    # por que el bodeguero es un rol aparte y no hereda lo de un supervisor.
    path("inventario/personas/", inventario_views.PersonasView.as_view(), name="inv_personas"),
    path("inventario/ubicaciones/", inventario_views.UbicacionesView.as_view(), name="inv_ubicaciones"),
    path("inventario/existencias/", inventario_views.ExistenciasView.as_view(), name="inv_existencias"),
    path("inventario/catalogo/", inventario_views.CatalogoView.as_view(), name="inv_catalogo"),
    path("inventario/entradas/", inventario_views.EntradasView.as_view(), name="inv_entradas"),
    path("inventario/despachos/", inventario_views.DespachosView.as_view(), name="inv_despachos"),
    path("inventario/devoluciones/", inventario_views.DevolucionesView.as_view(), name="inv_devoluciones"),
    path("inventario/serie/<str:serie>/", inventario_views.HistoriaDeSerieView.as_view(), name="inv_serie"),
    # Fase 2: reservas, traslados y conteo fisico.
    path("inventario/libre/", inventario_operacion_views.LibreView.as_view(), name="inv_libre"),
    path("inventario/reservas/", inventario_operacion_views.ReservasView.as_view(), name="inv_reservas"),
    path("inventario/reservas/<uid:pk>/liberar/", inventario_operacion_views.LiberarReservaView.as_view(), name="inv_reserva_liberar"),
    path("inventario/traslados/", inventario_operacion_views.TrasladosView.as_view(), name="inv_traslados"),
    path("inventario/conteos/", inventario_operacion_views.ConteosView.as_view(), name="inv_conteos"),
    path("inventario/conteos/<uid:pk>/anotar/", inventario_operacion_views.AnotarConteoView.as_view(), name="inv_conteo_anotar"),
    path("inventario/conteos/<uid:pk>/cerrar/", inventario_operacion_views.CerrarConteoView.as_view(), name="inv_conteo_cerrar"),
    # Fase 3: proveedores, compras y valorizacion.
    path("inventario/proveedores/", inventario_operacion_views.ProveedoresView.as_view(), name="inv_proveedores"),
    path("inventario/compras/", inventario_operacion_views.ComprasView.as_view(), name="inv_compras"),
    path("inventario/valorizacion/", inventario_operacion_views.ValorizacionView.as_view(), name="inv_valorizacion"),
    path("inventario/reportes/", inventario_operacion_views.ReportesView.as_view(), name="inv_reportes"),
    # Despacho: lo que hace la oficina, no el tecnico.
    path("trabajos/crear/", despacho_views.CrearOrdenView.as_view(), name="trabajo_crear"),
    path("trabajos/<uid:pk>/asignar/", despacho_views.AsignarTrabajoView.as_view(), name="trabajo_asignar"),
    path("trabajos/<uid:pk>/validar/", despacho_views.ValidarTrabajoView.as_view(), name="trabajo_validar"),
    path("trabajos/<uid:pk>/", views.TrabajoDetailView.as_view(), name="trabajo_detail"),
    path("trabajos/<uid:pk>/acciones/", views.AccionesTrabajoView.as_view(), name="trabajo_acciones"),
    path("trabajos/<uid:pk>/datos/", views.GuardarDatosTrabajoView.as_view(), name="trabajo_datos"),
    path("trabajos/<uid:pk>/probar-conexion/", views.ProbarConexionView.as_view(), name="trabajo_probar_conexion"),
    path("trabajos/<uid:pk>/evidencias/", views.EvidenciasTrabajoView.as_view(), name="trabajo_evidencias"),
    path("trabajos/<uid:pk>/completar/", views.CompletarTrabajoView.as_view(), name="trabajo_completar"),
    # Solo backend local de desarrollo: en produccion la subida va
    # directo al proveedor con una URL prefirmada y esta vista devuelve
    # 404. Ver CampoStorage.descriptor_subida.
    path("evidencias/<uid:pk>/subir/", views.SubirEvidenciaDirectoView.as_view(), name="evidencia_subir"),
    path("evidencias/<uid:pk>/confirmar/", views.ConfirmarEvidenciaView.as_view(), name="evidencia_confirmar"),
    path("evidencias/<uid:pk>/url/", views.ObtenerUrlEvidenciaView.as_view(), name="evidencia_url"),
]
