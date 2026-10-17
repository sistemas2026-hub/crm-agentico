import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

/// Dónde y con qué se tomó una evidencia.
///
/// POR QUÉ EXISTE
/// --------------
/// El backend espera `metadatos_captura` desde el principio —*"coordenadas GPS
/// del móvil, precisión, modelo"*— y la aplicación no mandaba nada. Una foto
/// sin lugar prueba que alguien subió una foto; con lugar prueba que esa
/// persona estuvo **ahí**.
///
/// LA REGLA QUE MANDA SOBRE TODO LO DEMÁS
/// --------------------------------------
/// **La ubicación nunca puede costar una evidencia.** Ni bloquearla, ni
/// demorarla, ni hacerla fallar. El trabajo de campo ocurre en sótanos, cajas
/// de distribución y zonas rurales — justo donde el GPS no fija — así que el
/// caso "no se pudo ubicar" no es el borde: es la mitad de los días.
///
/// De ahí el diseño: plazo corto, todo dentro de un `try`, y si algo sale mal
/// se devuelve lo que se tenga. Una foto sin coordenadas vale muchísimo más
/// que ninguna foto.
///
/// Y POR ESO SE DISTINGUE "NO SE PUDO" DE "NO SE INTENTÓ"
/// ------------------------------------------------------
/// Un `metadatos_captura` vacío es ambiguo: no dice si el teléfono no tenía
/// señal, si la persona negó el permiso, o si la aplicación ni lo intentó.
/// Las tres cosas significan cosas distintas para quien después mira la
/// evidencia, así que cada una deja su motivo escrito.
class UbicacionDeCaptura {
  /// Cuánto se espera por una posición antes de seguir sin ella.
  ///
  /// Cinco segundos es la frontera entre "tardó" y "la persona piensa que la
  /// aplicación se colgó". Con el obturador ya apretado, esperar más no
  /// compra precisión: compra desconfianza.
  static const Duration _plazo = Duration(seconds: 5);

  /// Permite a las pruebas responder sin tocar el GPS del sistema.
  @visibleForTesting
  static Future<Map<String, dynamic>> Function()? overrideParaPruebas;

  /// Los metadatos de esta captura, listos para viajar con la evidencia.
  ///
  /// Nunca lanza. En el peor caso devuelve el equipo y el motivo por el que
  /// no hay coordenadas.
  static Future<Map<String, dynamic>> tomar() async {
    if (overrideParaPruebas != null) return overrideParaPruebas!();

    final Map<String, dynamic> datos = <String, dynamic>{
      'origen': 'app_campo',
      ..._equipo(),
    };

    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        datos['ubicacion_motivo'] = 'servicio_apagado';
        return datos;
      }

      LocationPermission permiso = await Geolocator.checkPermission();
      if (permiso == LocationPermission.denied) {
        permiso = await Geolocator.requestPermission();
      }
      if (permiso == LocationPermission.denied ||
          permiso == LocationPermission.deniedForever) {
        datos['ubicacion_motivo'] = 'permiso_denegado';
        return datos;
      }

      final Position p = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: _plazo,
        ),
      );

      datos.addAll(<String, dynamic>{
        'lat': p.latitude,
        'lng': p.longitude,
        // En metros. Sin esto, dos puntos separados por cien metros parecen
        // igual de confiables, y uno puede venir de la antena de celular.
        'precision_m': p.accuracy,
        // La hora que el GPS le pone a la posición, que no es la misma que la
        // del reloj del teléfono: un reloj se puede cambiar a mano.
        'ubicacion_en': p.timestamp.toUtc().toIso8601String(),
        if (p.isMocked) 'ubicacion_simulada': true,
      });
    } on TimeoutException {
      datos['ubicacion_motivo'] = 'sin_senal_gps';
    } catch (e) {
      // Cualquier otra cosa —el plugin, el sistema, un permiso revocado en el
      // medio— no puede tumbar una captura. Se anota el tipo, nunca el
      // mensaje: puede traer rutas del equipo.
      datos['ubicacion_motivo'] = 'error_${e.runtimeType}';
    }

    return datos;
  }

  /// Qué equipo tomó la evidencia. Sirve para explicar una foto rara sin
  /// tener que preguntarle a nadie: una cámara de 2 MP se reconoce.
  static Map<String, dynamic> _equipo() {
    try {
      return <String, dynamic>{
        'plataforma': Platform.operatingSystem,
        'version_so': Platform.operatingSystemVersion,
      };
    } catch (_) {
      return <String, dynamic>{};
    }
  }
}