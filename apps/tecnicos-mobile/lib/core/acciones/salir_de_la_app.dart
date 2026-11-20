import 'package:flutter/foundation.dart';
import 'package:url_launcher/url_launcher.dart';

/// Llamar al cliente y abrir el mapa: las dos cosas que el técnico hacía
/// saliendo de la aplicación.
///
/// POR QUÉ ESTE ARCHIVO EXISTE, Y POR QUÉ SEPARADO DE LA PANTALLA
/// --------------------------------------------------------------
/// Los botones «Llamar Cliente» y «Ruta GPS» estaban dibujados y **no hacían
/// nada**: `alTocar: null`, sin lanzador de aplicaciones en las dependencias.
/// Estar parado en la puerta del cliente, necesitar llamar, y que la app no te
/// deje es lo que enseña a no confiar en la app — y un técnico que no confía
/// pasa a llenar lo justo y hacer el trabajo real por fuera.
///
/// Lo que se decide acá —**qué** URI se arma, y cuándo **no** hay nada que
/// abrir— es lógica, y se prueba sin teléfono. Lo que no se puede probar es que
/// el sistema operativo abra algo; eso queda detrás de [abrir], que es lo único
/// que se reemplaza en una prueba.
///
/// LO QUE NO HACE, Y ES A PROPÓSITO
/// --------------------------------
/// **No manda WhatsApp.** Se quitó de las acciones rápidas por decisión del
/// usuario: los técnicos de Rapilink no se comunican por ahí. Agregarlo de
/// vuelta acá sería reponer en silencio algo que se sacó con un motivo.
///
/// **No elige la aplicación de mapas.** Se pide `geo:` —el esquema estándar de
/// Android— y decide el teléfono con lo que tenga instalado: Waze, Google Maps,
/// Maps.me. Imponer una obliga a instalarla, y en un teléfono de empresa eso no
/// lo decide la app.
class SalirDeLaApp {
  const SalirDeLaApp({Future<bool> Function(Uri)? abrir})
      : _abrir = abrir ?? launchUrl;

  final Future<bool> Function(Uri) _abrir;

  /// Marca el teléfono del cliente. Devuelve si se pudo.
  ///
  /// `tel:` abre el marcador **con el número puesto**, sin llamar: la llamada la
  /// inicia la persona. Es a propósito — un toque accidental con guantes no
  /// puede marcarle a un cliente.
  Future<bool> llamar(String telefono) async {
    final Uri? destino = uriDeTelefono(telefono);
    if (destino == null) return false;
    return _intentar(destino);
  }

  /// Abre el mapa en la ubicación del cliente.
  Future<bool> navegar({double? latitud, double? longitud, String? etiqueta}) {
    final Uri? destino = uriDeMapa(
      latitud: latitud,
      longitud: longitud,
      etiqueta: etiqueta,
    );
    if (destino == null) return Future<bool>.value(false);
    return _intentar(destino);
  }

  Future<bool> _intentar(Uri destino) async {
    try {
      return await _abrir(destino);
    } catch (e) {
      // Un teléfono sin marcador ni mapa instalado existe: una tableta de
      // campo. No puede tumbar la pantalla de la orden.
      debugPrint('salir: no se pudo abrir ${destino.scheme} (${e.runtimeType})');
      return false;
    }
  }

  // --- Lo que se puede probar sin teléfono ---------------------------------

  /// El `tel:` de un número, o `null` si no hay número que marcar.
  ///
  /// SE LIMPIA, PERO NO SE VALIDA. Los números llegan de WispHub escritos por
  /// personas: `+57 312 455 8901`, `312-455-8901`, `(312) 4558901`. Los
  /// separadores se sacan porque el marcador no los necesita; el `+` se
  /// conserva porque sin él un número internacional no marca.
  ///
  /// No se exige largo ni prefijo: un plan de numeración no es igual en dos
  /// países, y rechazar un número raro le quitaría al técnico la única forma de
  /// llamar que tiene. Si está mal, el marcador se lo muestra y él decide.
  static Uri? uriDeTelefono(String crudo) {
    final String limpio = crudo.replaceAll(RegExp(r'[^0-9+]'), '');
    // Un `+` suelto, o una cadena sin un solo dígito, no es un teléfono.
    if (!RegExp(r'[0-9]').hasMatch(limpio)) return null;
    return Uri(scheme: 'tel', path: limpio);
  }

  /// El `geo:` de una coordenada, o `null` si no hay dónde ir.
  ///
  /// POR QUÉ HACEN FALTA LAS DOS COORDENADAS
  /// ---------------------------------------
  /// Media coordenada no es media ubicación: es una ubicación equivocada. El
  /// backend puede mandar una sin la otra —ya pasó— y abrir el mapa en
  /// `lat, 0` manda al técnico al Golfo de Guinea.
  ///
  /// El `q=` con la etiqueta hace que el mapa muestre el nombre en el pin en
  /// vez de las coordenadas. Va dentro del `q`, no como parámetro aparte, que
  /// es como lo lee Android.
  static Uri? uriDeMapa({double? latitud, double? longitud, String? etiqueta}) {
    if (latitud == null || longitud == null) return null;
    if (!_coordenadaValida(latitud, 90) || !_coordenadaValida(longitud, 180)) {
      return null;
    }
    // `0,0` es la Isla Nula: casi siempre significa «el backend no sabe», no
    // un cliente en el Atlántico. Mandar ahí a alguien es peor que no abrir.
    if (latitud == 0 && longitud == 0) return null;

    final String punto = '$latitud,$longitud';
    final String nombre = (etiqueta ?? '').trim();
    final String consulta =
        nombre.isEmpty ? punto : '$punto(${nombre.replaceAll('(', ' ').replaceAll(')', ' ')})';
    return Uri(scheme: 'geo', path: punto, queryParameters: {'q': consulta});
  }

  static bool _coordenadaValida(double v, double tope) =>
      v.isFinite && v.abs() <= tope;
}
