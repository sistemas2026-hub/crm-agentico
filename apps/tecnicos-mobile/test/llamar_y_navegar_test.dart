import 'package:campo/core/acciones/salir_de_la_app.dart';
import 'package:flutter_test/flutter_test.dart';

/// Llamar al cliente y abrir el mapa.
///
/// POR QUÉ ESTO MERECE PRUEBAS Y NO ES "SOLO ABRIR UN ENLACE"
/// ----------------------------------------------------------
/// Los dos botones estaban dibujados y **no hacían nada**. Encenderlos mal es
/// peor que dejarlos apagados: un botón activo que marca un número cortado, o un
/// mapa que abre en el Golfo de Guinea, le cuesta al técnico un viaje — y el
/// síntoma aparece en la casa del cliente, no en la pantalla.
///
/// Lo que se afirma acá es **qué URI se arma** y, sobre todo, **cuándo no hay
/// nada que abrir**. Que el sistema operativo abra algo no se puede medir sin un
/// teléfono, y esa parte vive detrás de una función inyectable.
void main() {
  group('A · el número que se marca', () {
    test('a1 · un número con separadores se limpia, no se rechaza', () {
      // Los números llegan de WispHub escritos por personas. Rechazar los que no
      // tienen forma canónica le quita al técnico la única manera de llamar.
      for (final String crudo in <String>[
        '+57 312 455 8901',
        '312-455-8901',
        '(312) 4558901',
        '  3124558901  ',
      ]) {
        final Uri? u = SalirDeLaApp.uriDeTelefono(crudo);
        expect(u, isNotNull, reason: crudo);
        expect(u!.scheme, 'tel');
        expect(RegExp(r'^\+?[0-9]+$').hasMatch(u.path), isTrue, reason: u.path);
      }
    });

    test('a2 · el + se conserva: sin él un internacional no marca', () {
      expect(SalirDeLaApp.uriDeTelefono('+57 312 455 8901')!.path,
          '+573124558901');
    });

    test('a3 · sin un solo dígito NO hay nada que marcar', () {
      // El caso real: el backend manda cadena vacía, un guion, o un "N/A".
      for (final String vacio in <String>['', '   ', '-', 'N/A', '+', '()']) {
        expect(SalirDeLaApp.uriDeTelefono(vacio), isNull, reason: '«$vacio»');
      }
    });

    test('a4 · el URI no lleva el número escapado a medias', () {
      // `Uri(scheme:, path:)` es lo correcto; armar la cadena a mano y pasarla
      // por `Uri.parse` convierte el `+` en espacio en algunos marcadores.
      expect(SalirDeLaApp.uriDeTelefono('+573124558901').toString(),
          'tel:+573124558901');
    });
  });

  group('B · el punto del mapa', () {
    test('b1 · con las dos coordenadas abre geo: en ese punto', () {
      final Uri? u = SalirDeLaApp.uriDeMapa(latitud: 4.6482, longitud: -74.0776);
      expect(u, isNotNull);
      expect(u!.scheme, 'geo');
      expect(u.path, '4.6482,-74.0776');
    });

    test('b2 · MEDIA coordenada no es media ubicación: no abre', () {
      // Es el caso que manda al técnico a la dirección equivocada. El backend
      // puede mandar una sin la otra, y ya pasó.
      expect(SalirDeLaApp.uriDeMapa(latitud: 4.6482, longitud: null), isNull);
      expect(SalirDeLaApp.uriDeMapa(latitud: null, longitud: -74.0776), isNull);
      expect(SalirDeLaApp.uriDeMapa(), isNull);
    });

    test('b3 · 0,0 no abre: casi siempre significa «no se sabe»', () {
      // La Isla Nula, en el Atlántico. Mandar a alguien ahí es peor que no
      // abrir, porque el mapa responde y parece que funcionó.
      expect(SalirDeLaApp.uriDeMapa(latitud: 0, longitud: 0), isNull);
    });

    test('b4 · una coordenada imposible no abre', () {
      expect(SalirDeLaApp.uriDeMapa(latitud: 91, longitud: 0), isNull);
      expect(SalirDeLaApp.uriDeMapa(latitud: 0, longitud: 181), isNull);
      expect(SalirDeLaApp.uriDeMapa(latitud: double.nan, longitud: 0), isNull);
      expect(
          SalirDeLaApp.uriDeMapa(latitud: 0, longitud: double.infinity), isNull);
    });

    test('b5 · el nombre del cliente va en el pin, para reconocerlo', () {
      final Uri u = SalirDeLaApp.uriDeMapa(
        latitud: 4.6482,
        longitud: -74.0776,
        etiqueta: 'Beatriz Pinzón',
      )!;
      expect(u.queryParameters['q'], '4.6482,-74.0776(Beatriz Pinzón)');
    });

    test('b6 · sin nombre queda el punto, no un paréntesis vacío', () {
      for (final String? sin in <String?>[null, '', '   ']) {
        final Uri u = SalirDeLaApp.uriDeMapa(
            latitud: 4.6482, longitud: -74.0776, etiqueta: sin)!;
        expect(u.queryParameters['q'], '4.6482,-74.0776');
      }
    });

    test('b7 · un paréntesis en el nombre no rompe el punto', () {
      // «Beatriz Pinzón (apto 302)» existe en los datos reales, y un paréntesis
      // suelto corta el `q` y el mapa pierde la coordenada.
      final Uri u = SalirDeLaApp.uriDeMapa(
        latitud: 4.6482,
        longitud: -74.0776,
        etiqueta: 'Beatriz (apto 302)',
      )!;
      expect(u.queryParameters['q'], startsWith('4.6482,-74.0776('));
      expect(u.queryParameters['q']!.split('(').length, 2);
    });
  });

  group('C · qué pasa cuando el teléfono no puede abrirlo', () {
    test('c1 · si el lanzador devuelve false, se devuelve false', () async {
      // Una tableta de campo sin marcador. La pantalla usa esto para decirlo,
      // en vez de que el toque no haga nada — indistinguible de una app rota.
      final salir = SalirDeLaApp(abrir: (_) async => false);
      expect(await salir.llamar('+573124558901'), isFalse);
    });

    test('c2 · si el lanzador EXPLOTA, no se propaga', () async {
      // `launchUrl` lanza `PlatformException` cuando no hay ninguna app que
      // atienda el esquema. Eso no puede tumbar la ficha de la orden.
      final salir = SalirDeLaApp(abrir: (_) async => throw StateError('sin app'));
      expect(await salir.llamar('+573124558901'), isFalse);
      expect(await salir.navegar(latitud: 4.6, longitud: -74.0), isFalse);
    });

    test('c3 · sin nada que abrir NO se llama al lanzador', () async {
      // Afirmar sobre el EFECTO: cero intentos, no «devolvió false».
      final List<Uri> intentos = <Uri>[];
      final salir = SalirDeLaApp(abrir: (Uri u) async {
        intentos.add(u);
        return true;
      });

      expect(await salir.llamar(''), isFalse);
      expect(await salir.navegar(latitud: 4.6, longitud: null), isFalse);
      expect(await salir.navegar(latitud: 0, longitud: 0), isFalse);
      expect(intentos, isEmpty);
    });

    test('c4 · lo que se le pide al lanzador es exactamente el URI armado',
        () async {
      final List<Uri> intentos = <Uri>[];
      final salir = SalirDeLaApp(abrir: (Uri u) async {
        intentos.add(u);
        return true;
      });

      await salir.llamar('+57 312 455 8901');
      await salir.navegar(
          latitud: 4.6482, longitud: -74.0776, etiqueta: 'Beatriz');

      expect(intentos.map((Uri u) => u.scheme).toList(), <String>['tel', 'geo']);
      expect(intentos[0].path, '+573124558901');
      expect(intentos[1].queryParameters['q'], '4.6482,-74.0776(Beatriz)');
    });
  });
}
