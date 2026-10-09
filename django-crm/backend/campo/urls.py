# -*- coding: utf-8 -*-
"""Rutas de la API REST del módulo campo."""

from django.urls import path

from campo import (
    avisos_views,
    cuadrillas_views,
    despacho_views,
    inventario_operacion_views,
    inventario_views,
    materiales_views,
    pedidos_views,
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
    # Las cuadrillas: quienes son, y que hacen cada dia.
    path("cuadrillas/", cuadrillas_views.CuadrillasView.as_view(), name="cuadrillas"),
    path("zonas/", cuadrillas_views.ZonasView.as_view(), name="zonas"),
    path("zonas/<uid:pk>/", cuadrillas_views.ZonaView.as_view(), name="zona"),
    path("zonas/<uid:pk>/localidades/", cuadrillas_views.LocalidadesDeZonaView.as_view(), name="zona_localidades"),
    #  Quien trabaja en campo, tenga cuenta o no: un auxiliar sin celular
    #  no puede tener `Profile` y aun asi integra la cuadrilla.
    path("personas-de-campo/", cuadrillas_views.PersonasDeCampoView.as_view(), name="personas_de_campo"),
    path("personas-de-campo/<uid:pk>/", cuadrillas_views.PersonaDeCampoView.as_view(), name="persona_de_campo"),
    #  Como y a que hora reparte esta empresa. Es configuracion, no
    #  constantes: el tope vivia fijo en el codigo y la hora habria vivido
    #  fija en Celery beat, y las dos varian por empresa.
    #  Que labor tiene cada tipo de trabajo. Define que cuadrillas pueden
    #  tomarlo; lo que no se clasifica NO se reparte, asi que sin esta
    #  pantalla el reparto no tendria como arrancar.
    path("tipos-de-trabajo/", cuadrillas_views.TiposDeTrabajoView.as_view(), name="tipos_de_trabajo"),
    path("tipos-de-trabajo/<uid:pk>/", cuadrillas_views.TiposDeTrabajoView.as_view(), name="tipo_de_trabajo"),
    path("cuadrillas/configuracion/", cuadrillas_views.ConfiguracionDeRepartoView.as_view(), name="reparto_configuracion"),
    path("cuadrillas/reparto/", cuadrillas_views.RepartoView.as_view(), name="cuadrilla_reparto"),
    path("cuadrillas/jornada/", cuadrillas_views.JornadaDeCuadrillaView.as_view(), name="cuadrilla_jornada"),
    path("cuadrillas/<uid:pk>/", cuadrillas_views.CuadrillaView.as_view(), name="cuadrilla"),
    path("inventario/series/", inventario_views.SeriesDisponiblesView.as_view(), name="inv_series"),
    path("inventario/existencias/", inventario_views.ExistenciasView.as_view(), name="inv_existencias"),
    path("inventario/catalogo/", inventario_views.CatalogoView.as_view(), name="inv_catalogo"),
    # El maestro del catalogo: `catalogo/` sirve los desplegables (solo activos),
    # `materiales/` administra (todos, y escribe).
    path("inventario/materiales/", inventario_views.MaterialesView.as_view(), name="inv_materiales"),
    path("inventario/materiales/<uid:pk>/", inventario_views.MaterialView.as_view(), name="inv_material"),
    path("inventario/materiales/<uid:pk>/imagen/", inventario_views.MaterialImagenView.as_view(), name="inv_material_imagen"),
    path("inventario/entradas/", inventario_views.EntradasView.as_view(), name="inv_entradas"),
    path("inventario/despachos/", inventario_views.DespachosView.as_view(), name="inv_despachos"),
    path("inventario/devoluciones/", inventario_views.DevolucionesView.as_view(), name="inv_devoluciones"),
    path("inventario/serie/<str:serie>/", inventario_views.HistoriaDeSerieView.as_view(), name="inv_serie"),
    # Fase 2: reservas, traslados y conteo fisico.
    # Pedir material a bodega desde el terreno. NO es un movimiento: un
    # movimiento es un hecho que ya ocurrio, y esto todavia no paso.
    path("inventario/pedidos/", pedidos_views.PedidosDeMaterialView.as_view(), name="inv_pedidos"),
    path("inventario/libre/", inventario_operacion_views.LibreView.as_view(), name="inv_libre"),
    path("inventario/reservas/", inventario_operacion_views.ReservasView.as_view(), name="inv_reservas"),
    path("inventario/reservas/<uid:pk>/liberar/", inventario_operacion_views.LiberarReservaView.as_view(), name="inv_reserva_liberar"),
    path("inventario/traslados/", inventario_operacion_views.TrasladosView.as_view(), name="inv_traslados"),
    path("inventario/conteos/", inventario_operacion_views.ConteosView.as_view(), name="inv_conteos"),
    path("inventario/conteos/<uid:pk>/anotar/", inventario_operacion_views.AnotarConteoView.as_view(), name="inv_conteo_anotar"),
    path("inventario/conteos/<uid:pk>/cerrar/", inventario_operacion_views.CerrarConteoView.as_view(), name="inv_conteo_cerrar"),
    # Fase 3: proveedores, compras y valorizacion.
    path("inventario/plantillas/", inventario_operacion_views.PlantillasView.as_view(), name="inv_plantillas"),
    path("inventario/plantillas/<uid:pk>/", inventario_operacion_views.PlantillaView.as_view(), name="inv_plantilla"),
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
    # Que material toco esta orden. Solo lectura: mover inventario entra por
    # las rutas de inventario/, que son las que tienen la frontera puesta.
    path("trabajos/<uid:pk>/materiales/", views.MaterialesDeOrdenView.as_view(), name="trabajo_materiales"),
    # Las ultimas visitas al mismo servicio. La llamada al NOC mas frecuente
    # del tecnico, con el dato que ya estaba en la base.
    path("trabajos/<uid:pk>/historial/", views.HistorialDelServicioView.as_view(), name="trabajo_historial"),
    # La bitacora de la intervencion: INICIO, AVANCE, BLOQUEO y CIERRE. No
    # mueve el estado operativo; eso sigue siendo cosa de las transiciones.
    path("trabajos/<uid:pk>/seguimiento/", views.SeguimientoDeOrdenView.as_view(), name="trabajo_seguimiento"),
    # Destrabar un trabajo detenido. El estado al que vuelve lo guardo el
    # bloqueo al abrirse, y la maquina de transiciones lo valida.
    path("trabajos/<uid:pk>/bloqueo/resolver/", views.ResolverBloqueoView.as_view(), name="trabajo_bloqueo_resolver"),
    # Los bloqueos vivos de la empresa. `?requiere_noc=1` es el otro filtro:
    # estar detenido y necesitar al NOC no son lo mismo.
    path("bloqueos/", views.BloqueosAbiertosView.as_view(), name="bloqueos_abiertos"),
    # La salud del seguimiento de la jornada. Se CALCULA al preguntar: no hay
    # ningun "estado_seguimiento" guardado que pueda quedar viejo.
    path("seguimiento/salud/", views.SaludDelSeguimientoView.as_view(), name="seguimiento_salud"),
    # El telefono se registra para poder recibir un aviso. POST al entrar y cada
    # vez que el token cambia; DELETE al cerrar sesion, porque un telefono de
    # cuadrilla pasa de mano en mano.
    path("dispositivo/", views.DispositivoDeCampoView.as_view(), name="dispositivo_campo"),
    # La configuracion de avisos, que la empresa edita desde su pantalla. No es
    # una fila que carga un programador: ver el encabezado de `avisos_views`.
    path("avisos/canales/", avisos_views.CanalesDeAvisosView.as_view(), name="avisos_canales"),
    path("avisos/canales/<uid:pk>/", avisos_views.CanalDeAvisosView.as_view(), name="avisos_canal"),
    path("avisos/canales/<uid:pk>/probar/", avisos_views.ProbarCanalView.as_view(), name="avisos_probar"),
    path("trabajos/<uid:pk>/datos/", views.GuardarDatosTrabajoView.as_view(), name="trabajo_datos"),
    path("trabajos/<uid:pk>/probar-conexion/", views.ProbarConexionView.as_view(), name="trabajo_probar_conexion"),
    # Volver a medir la señal AHORA. La de la ficha es de cuando se armo la
    # orden, y despues de mover un conector eso ya no contesta nada.
    path("trabajos/<uid:pk>/medir-senal/", views.MedirSenalView.as_view(), name="trabajo_medir_senal"),

    # RESTAURADAS  --  estas ocho desaparecieron en 59cf2a6 junto con sus vistas.
    # El frontend nunca dejo de llamar a 'programar' y 'reprogramar'
    # (programacion-noc.js:398 y :316), asi que programar una orden devolvia 404
    # en produccion. Se reponen con los MISMOS nombres de ruta: cambiar uno
    # habria roto cualquier 'reverse()' que los use.
    #
    # Cuadrilla ad-hoc por OT  --  M03-F-B. 'asignar' pone al responsable;
    # estas cuatro manejan la composicion sin moverlo por accidente.
    path("trabajos/<uid:pk>/cuadrilla/agregar/", despacho_views.AgregarIntegranteView.as_view(), name="cuadrilla_agregar"),
    path("trabajos/<uid:pk>/cuadrilla/principal/", despacho_views.CambiarPrincipalView.as_view(), name="cuadrilla_principal"),
    path("trabajos/<uid:pk>/cuadrilla/retirar/", despacho_views.RetirarIntegranteView.as_view(), name="cuadrilla_retirar"),
    path("trabajos/<uid:pk>/cuadrilla/desasignar/", despacho_views.DesasignarTrabajoView.as_view(), name="cuadrilla_desasignar"),
    path("trabajos/<uid:pk>/programar/", despacho_views.ProgramarTrabajoView.as_view(), name="trabajo_programar"),
    path("trabajos/<uid:pk>/reprogramar/", despacho_views.ReprogramarTrabajoView.as_view(), name="trabajo_reprogramar"),
    path("trabajos/<uid:pk>/contingencia/", despacho_views.ContingenciaTrabajoView.as_view(), name="trabajo_contingencia"),
    #  El ultimo paso del recorrido. 'cerrar_orden' existia en el servicio desde
    #  el primer dia y no la llamaba nadie: una orden aprobada se quedaba en
    #  'completada_campo' para siempre.
    path("trabajos/<uid:pk>/cerrar/", despacho_views.CerrarTrabajoView.as_view(), name="trabajo_cerrar"),
    path("trabajos/<uid:pk>/evidencias/", views.EvidenciasTrabajoView.as_view(), name="trabajo_evidencias"),
    path("trabajos/<uid:pk>/completar/", views.CompletarTrabajoView.as_view(), name="trabajo_completar"),
    # Solo backend local de desarrollo: en produccion la subida va
    # directo al proveedor con una URL prefirmada y esta vista devuelve
    # 404. Ver CampoStorage.descriptor_subida.
    path("evidencias/<uid:pk>/subir/", views.SubirEvidenciaDirectoView.as_view(), name="evidencia_subir"),
    path("evidencias/<uid:pk>/confirmar/", views.ConfirmarEvidenciaView.as_view(), name="evidencia_confirmar"),
    path("evidencias/<uid:pk>/url/", views.ObtenerUrlEvidenciaView.as_view(), name="evidencia_url"),
]
