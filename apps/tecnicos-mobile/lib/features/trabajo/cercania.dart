import 'dart:math' as math;

import 'trabajo_vista.dart';

/// A qué distancia queda cada trabajo, y en qué orden conviene hacerlos.
///
/// EL PROBLEMA
/// -----------
/// El técnico tiene tres órdenes en barrios distintos y la app se las muestra
/// **en el orden en que las creó la oficina**. Cuál conviene primero lo decide
/// él mirando direcciones y adivinando — y las coordenadas estaban ahí desde el
/// principio.
///
/// LO QUE ESTO NO ES
/// -----------------
/// **No es una ruta.** Es la distancia en línea recta entre dos puntos. Un río,
/// una vía férrea o un sentido único pueden hacer que lo más cercano en el mapa
/// sea lo más lejano en tiempo. Por eso se muestra como *«a 1,2 km»* y nunca
/// como *«12 minutos»*: lo segundo es una promesa que este cálculo no puede
/// cumplir, y el técnico ajusta su día con ella.
///
/// Y **no reemplaza al orden por hora**: una orden con ventana prometida se
/// atiende cuando se prometió, aunque quede lejos. La cercanía ordena lo que no
/// tiene hora, que es justo donde hoy no hay criterio ninguno.
class Cercania {
  const Cercania._();

  /// Radio medio de la Tierra, en metros. El valor de la IUGG.
  static const double _radioTierra = 6371008.8;

  /// Metros en línea recta entre dos puntos, por la fórmula del haversine.
  ///
  /// Haversine y no una resta de grados: un grado de longitud mide 111 km en el
  /// ecuador y 0 en el polo. En Colombia la diferencia ya es del 10 %, y a
  /// escala de ciudad eso ordena mal dos órdenes que están a la misma distancia.
  static double metrosEntre({
    required double latA,
    required double lngA,
    required double latB,
    required double lngB,
  }) {
    const double aRadianes = math.pi / 180;
    final double dLat = (latB - latA) * aRadianes;
    final double dLng = (lngB - lngA) * aRadianes;
    final double a = math.sin(dLat / 2) * math.sin(dLat / 2) +
        math.cos(latA * aRadianes) *
            math.cos(latB * aRadianes) *
            math.sin(dLng / 2) *
            math.sin(dLng / 2);
    return 2 * _radioTierra * math.atan2(math.sqrt(a), math.sqrt(1 - a));
  }

  /// La distancia a un trabajo, o `null` si no se puede saber.
  ///
  /// `null` cuando falta la posición del técnico **o** las coordenadas de la
  /// orden. Son dos causas distintas y las dos terminan igual: no se puede
  /// decir. Inventar un cero pondría esa orden primera, que es el peor lugar
  /// para una orden de la que no se sabe dónde queda.
  static double? metrosHasta(
    TrabajoVista trabajo, {
    required double? latTecnico,
    required double? lngTecnico,
  }) {
    if (latTecnico == null || lngTecnico == null) return null;
    final double? lat = trabajo.latitud;
    final double? lng = trabajo.longitud;
    if (lat == null || lng == null) return null;
    // `0,0` es la Isla Nula: casi siempre significa «el backend no sabe». Es el
    // mismo criterio que ya usa el botón de abrir el mapa.
    if (lat == 0 && lng == 0) return null;
    return metrosEntre(latA: latTecnico, lngA: lngTecnico, latB: lat, lngB: lng);
  }

  /// Los trabajos ordenados por cercanía, dejando al final los que no se saben.
  ///
  /// EL ORDEN RELATIVO DE LOS QUE NO SE SABEN NO CAMBIA. Si tres órdenes no
  /// traen coordenadas, siguen entre ellas como venían: reordenarlas sin motivo
  /// haría que la lista se mueva sola entre dos aperturas, y eso le hace perder
  /// el hilo a quien ya memorizó dónde estaba cada una.
  static List<TrabajoVista> ordenarPorCercania(
    List<TrabajoVista> trabajos, {
    required double? latTecnico,
    required double? lngTecnico,
  }) {
    if (latTecnico == null || lngTecnico == null) {
      return List<TrabajoVista>.of(trabajos);
    }

    final List<(int, TrabajoVista, double?)> conDistancia =
        <(int, TrabajoVista, double?)>[
      for (final (int i, TrabajoVista t) in trabajos.indexed)
        (
          i,
          t,
          metrosHasta(t, latTecnico: latTecnico, lngTecnico: lngTecnico),
        ),
    ];

    conDistancia.sort(((int, TrabajoVista, double?) a,
        (int, TrabajoVista, double?) b) {
      final double? da = a.$3;
      final double? db = b.$3;
      if (da == null && db == null) return a.$1.compareTo(b.$1);
      if (da == null) return 1;
      if (db == null) return -1;
      final int porDistancia = da.compareTo(db);
      // Empate a la misma distancia: se respeta el orden que venía. Sin esto el
      // `sort` puede intercambiarlos entre corridas y la lista «se mueve sola».
      return porDistancia != 0 ? porDistancia : a.$1.compareTo(b.$1);
    });

    return <TrabajoVista>[
      for (final (int, TrabajoVista, double?) f in conDistancia) f.$2,
    ];
  }

  /// La distancia en palabras, para la tarjeta.
  ///
  /// Debajo del kilómetro va en metros redondeados a la decena: a esa escala el
  /// técnico está en la cuadra y los metros exactos no le cambian nada. Arriba
  /// del kilómetro, un decimal — «1,2 km» decide si va caminando o maneja;
  /// «1,23 km» no agrega nada y ocupa más.
  ///
  /// Se usa coma decimal porque es la que se lee en Colombia, y el punto ahí
  /// separa miles.
  static String texto(double metros) {
    if (metros < 1000) {
      final int redondeado = (metros / 10).round() * 10;
      return '$redondeado m';
    }
    final double km = metros / 1000;
    return '${km.toStringAsFixed(1).replaceAll('.', ',')} km';
  }
}
