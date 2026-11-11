import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_typography.dart';

/// El mapa de la casa, dentro de la ficha.
///
/// POR QUE EXISTE  --  11/11/2026. La pantalla mostraba la coordenada como
/// texto y un boton que abria Google Maps. Dos numeros no le dicen a nadie
/// donde queda una casa, y salir de la aplicacion para verlo es perder el
/// hilo del trabajo: el tecnico vuelve y tiene que reencontrar donde estaba.
///
/// POR QUE ESRI Y NO GOOGLE. No necesita clave de API ni cuenta de
/// facturacion, y sobre todo NO METE UN PROVEEDOR NUEVO en la autorizacion de
/// tratamiento de datos: es el mismo origen de teselas que ya usa el mapa de
/// cuadrillas del panel web. Lo que viaja a Esri es el numero de la tesela
/// --un cuadrado de territorio-- no la coordenada del cliente ni quien la
/// mira.
///
/// SATELITAL Y NO CALLEJERO, a proposito: el tecnico busca una casa, y el
/// techo y el patio se reconocen; el nombre de la calle ya lo tiene escrito
/// arriba.
class MapaDelCliente extends StatelessWidget {
  const MapaDelCliente({
    super.key,
    required this.latitud,
    required this.longitud,
    this.alto = 180,
    this.etiqueta,
  });

  final double latitud;
  final double longitud;
  final double alto;

  /// Que se nombra en el aviso de abajo. Normalmente la direccion.
  final String? etiqueta;

  /// Zoom de barrio: se ven las casas vecinas y la esquina mas cercana, que
  /// es lo que hace reconocible un punto. Mas cerca y no se sabe donde esta;
  /// mas lejos y no se distingue la casa.
  static const double _zoom = 17;

  @override
  Widget build(BuildContext context) {
    final LatLng punto = LatLng(latitud, longitud);
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppRadius.tarjeta),
      child: SizedBox(
        height: alto,
        child: Stack(
          children: <Widget>[
            FlutterMap(
              options: MapOptions(
                initialCenter: punto,
                initialZoom: _zoom,
                //  SIN ROTAR. Un mapa girado desorienta a quien lo mira de
                //  reojo mientras maneja, y no agrega nada para encontrar una
                //  casa.
                interactionOptions: const InteractionOptions(
                  flags: InteractiveFlag.pinchZoom |
                      InteractiveFlag.drag |
                      InteractiveFlag.doubleTapZoom,
                ),
              ),
              children: <Widget>[
                TileLayer(
                  urlTemplate:
                      'https://server.arcgisonline.com/ArcGIS/rest/services/'
                      'World_Imagery/MapServer/tile/{z}/{y}/{x}',
                  //  Sin conexion las teselas no cargan y el fondo queda
                  //  oscuro; el marcador y el aviso de abajo siguen
                  //  dibujandose, asi que la pantalla no miente: muestra que
                  //  hay un punto y que el mapa no se pudo traer.
                  userAgentPackageName: 'co.rapilinksas.dexter.campo',
                  maxNativeZoom: 19,
                ),
                MarkerLayer(
                  markers: <Marker>[
                    Marker(
                      point: punto,
                      width: 44,
                      height: 44,
                      //  El pin apunta al punto con su PUNTA, no con su
                      //  centro: un icono centrado marca una casa que puede
                      //  estar media cuadra mas arriba.
                      alignment: Alignment.topCenter,
                      child: const Icon(
                        Icons.location_on,
                        size: 44,
                        color: AppColors.error,
                        shadows: <Shadow>[
                          Shadow(blurRadius: 6, color: Colors.black54),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
            if (etiqueta != null && etiqueta!.trim().isNotEmpty)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 6),
                  color: Colors.black.withValues(alpha: 0.55),
                  child: Text(
                    etiqueta!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.cuerpoChico
                        .copyWith(color: Colors.white),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
