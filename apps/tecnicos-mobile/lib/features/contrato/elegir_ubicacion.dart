/// ELEGIR EN EL MAPA DÓNDE QUEDA LA CASA (26/11/2026).
///
/// El usuario, probando el contrato: «en la parte de coordenadas que permita
/// editar, y si sale un mapa para que seleccione la ubicación correcta sería
/// mejor». Las coordenadas del ticket las escribió alguien que no estaba en
/// la casa; el técnico sí está.
///
/// CÓMO SE ELIGE. El pin está quieto en el centro y se mueve el MAPA, no el
/// pin: con el dedo encima, un pin que sigue al dedo tapa justo lo que hay que
/// ver. Al soltar, la coordenada es la del centro. «Mi ubicación» lleva el mapa
/// al GPS del teléfono, que se puede afinar a mano después.
///
/// EL MISMO MAPA QUE LA FICHA: satelital de Esri, sin clave y sin un proveedor
/// nuevo en la autorización de datos (ver `MapaDelCliente`). Lo que viaja a
/// Esri es el número de la tesela, no la coordenada.
library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../core/storage/ubicacion_de_captura.dart';
import '../../core/theme/app_theme.dart';

class ElegirUbicacion extends StatefulWidget {
  const ElegirUbicacion({super.key, this.lat, this.lng});

  /// Dónde empieza el mapa: las coordenadas que hay. Sin ellas, el GPS.
  final double? lat;
  final double? lng;

  @override
  State<ElegirUbicacion> createState() => _EstadoElegirUbicacion();
}

class _EstadoElegirUbicacion extends State<ElegirUbicacion> {
  final MapController _mapa = MapController();
  LatLng? _centro;
  bool _buscando = false;

  static const double _zoomDeCasa = 18;

  @override
  void initState() {
    super.initState();
    if (widget.lat != null && widget.lng != null) {
      _centro = LatLng(widget.lat!, widget.lng!);
    } else {
      //  Sin coordenadas, el primer lugar razonable es donde está el técnico.
      WidgetsBinding.instance.addPostFrameCallback((_) => _irAMiUbicacion());
    }
  }

  @override
  void dispose() {
    _mapa.dispose();
    super.dispose();
  }

  Future<void> _irAMiUbicacion() async {
    setState(() => _buscando = true);
    final Map<String, dynamic> u = await UbicacionDeCaptura.tomar();
    if (!mounted) return;
    final double? lat = double.tryParse('${u['lat'] ?? ''}');
    final double? lng = double.tryParse('${u['lng'] ?? ''}');
    setState(() => _buscando = false);
    if (lat == null || lng == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('El teléfono no pudo decir dónde estás. Mueve el mapa hasta la casa.')));
      return;
    }
    final LatLng aqui = LatLng(lat, lng);
    setState(() => _centro = aqui);
    _mapa.move(aqui, _zoomDeCasa);
  }

  @override
  Widget build(BuildContext context) {
    final LatLng? centro = _centro;
    return Scaffold(
      backgroundColor: AppColors.fondo,
      appBar: AppBar(title: const Text('Dónde queda la casa')),
      body: Stack(children: <Widget>[
        FlutterMap(
          mapController: _mapa,
          options: MapOptions(
            //  Sin punto todavía (esperando el GPS), el mundo entero: no se
            //  inventa una ciudad.
            initialCenter: centro ?? const LatLng(0, 0),
            initialZoom: centro == null ? 2 : _zoomDeCasa,
            interactionOptions: const InteractionOptions(
              flags: InteractiveFlag.pinchZoom |
                  InteractiveFlag.drag |
                  InteractiveFlag.doubleTapZoom,
            ),
            onPositionChanged: (MapCamera camara, bool conGesto) {
              if (conGesto) setState(() => _centro = camara.center);
            },
          ),
          children: <Widget>[
            TileLayer(
              urlTemplate: 'https://server.arcgisonline.com/ArcGIS/rest/services/'
                  'World_Imagery/MapServer/tile/{z}/{y}/{x}',
              userAgentPackageName: 'co.rapilinksas.dexter.campo',
              maxNativeZoom: 19,
            ),
          ],
        ),
        //  EL PIN, QUIETO EN EL CENTRO. La punta queda justo en el centro del
        //  mapa: por eso se sube la mitad de su alto.
        const IgnorePointer(
          child: Center(
            child: Padding(
              padding: EdgeInsets.only(bottom: 48),
              child: Icon(Icons.location_on, size: 48, color: AppColors.error, shadows: <Shadow>[
                Shadow(blurRadius: 8, color: Colors.black54),
              ]),
            ),
          ),
        ),
        //  Arriba: qué hacer y la coordenada que va quedando.
        Positioned(
          left: AppSpacing.margen,
          right: AppSpacing.margen,
          top: AppSpacing.md,
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md, vertical: AppSpacing.sm),
            decoration: BoxDecoration(
              color: AppColors.surfaceContainerLowest,
              borderRadius: AppRadius.brTarjeta,
              boxShadow: AppTheme.sombraNivel1,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text('Mueve el mapa hasta que el pin quede en la casa.',
                    style: AppTypography.cuerpoChico),
                if (centro != null)
                  Text(
                    '${centro.latitude.toStringAsFixed(6)}, ${centro.longitude.toStringAsFixed(6)}',
                    style: AppTypography.labelTelemetry.copyWith(color: AppColors.secondary),
                  ),
              ],
            ),
          ),
        ),
        //  Abajo: mi ubicación y confirmar.
        Positioned(
          left: AppSpacing.margen,
          right: AppSpacing.margen,
          bottom: AppSpacing.lg,
          child: SafeArea(
            top: false,
            child: Row(children: <Widget>[
              SizedBox(
                height: AppSpacing.objetivoTactilAmplio,
                width: AppSpacing.objetivoTactilAmplio,
                child: Material(
                  color: AppColors.surfaceContainerLowest,
                  borderRadius: AppRadius.brTarjeta,
                  elevation: 2,
                  child: InkWell(
                    borderRadius: AppRadius.brTarjeta,
                    onTap: _buscando ? null : _irAMiUbicacion,
                    child: Semantics(
                      button: true,
                      label: 'Mi ubicación',
                      child: Center(
                        child: _buscando
                            ? const SizedBox(
                                width: 22,
                                height: 22,
                                child: CircularProgressIndicator(strokeWidth: 2))
                            : const Icon(Icons.my_location, color: AppColors.secondary),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: SizedBox(
                  height: AppSpacing.objetivoTactilAmplio,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.azulAccion,
                      shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
                    ),
                    icon: const Icon(Icons.check),
                    label: const Text('Usar esta ubicación',
                        maxLines: 1, overflow: TextOverflow.ellipsis),
                    onPressed: centro == null
                        ? null
                        : () => Navigator.of(context)
                            .pop<({double lat, double lng})>(
                                (lat: centro.latitude, lng: centro.longitude)),
                  ),
                ),
              ),
            ]),
          ),
        ),
      ]),
    );
  }
}
