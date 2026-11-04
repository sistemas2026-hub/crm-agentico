import 'package:dio/dio.dart';
import 'package:geolocator/geolocator.dart';

import '../api/api_client.dart';
import '../api/api_endpoints.dart';

/// MANDAR LA POSICIÓN AL SERVIDOR (31/10/2026).
///
/// Devuelve `true` si el servidor la guardó y `false` si contestó que no
/// corresponde —fuera de la jornada o del horario de las cuadrillas—. Esa
/// diferencia la usa `CompartirUbicacion` para apagarse en vez de insistir.
///
/// Un error de red NO es un `false`: se propaga, porque «no hubo señal» y
/// «el servidor dice que no compartas» son dos cosas distintas y la segunda
/// apaga el compartir.
Future<bool> mandarUbicacion(
  ApiClient api,
  Position p,
  int? bateria,
) async {
  final Response<dynamic> r = await api.post(
    ApiEndpoints.ubicacion,
    data: <String, dynamic>{
      'latitud': p.latitude,
      'longitud': p.longitude,
      'medida_en': p.timestamp.toUtc().toIso8601String(),
      //  `accuracy` viene en metros y puede ser 0 cuando el teléfono no la
      //  sabe: ahí se manda nulo en vez de prometer precisión perfecta.
      'precision_m': p.accuracy > 0 ? p.accuracy.round() : null,
      'bateria': bateria,
    },
  );
  final dynamic datos = r.data;
  //  Sin cuerpo entendible se asume que se guardó: el caso que importa
  //  --que el servidor diga explícitamente que no-- sí viene marcado.
  if (datos is! Map) return true;
  return datos['guardada'] != false;
}
