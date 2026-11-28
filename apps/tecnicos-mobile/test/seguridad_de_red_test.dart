import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// El APK que se instala en el teléfono de un técnico no habla HTTP en claro.
///
/// POR QUÉ ESTO SE PRUEBA
/// ----------------------
/// Es una regla que vive en un archivo de configuración, no en código: nadie
/// la ve al revisar un cambio de Dart, y se rompe con una línea. Ya pasó una
/// vez -- `usesCleartextTraffic="true"` estaba puesto en el manifest para
/// poder apuntar a `127.0.0.1:8000` mientras se desarrolla, y esa comodidad
/// viajaba dentro del APK de producción.
///
/// Lo que va en claro es la libreta de clientes del ISP: nombre, dirección,
/// teléfono y las coordenadas del domicilio. Una cuadrilla trabaja desde la
/// red wifi del cliente; ahí cualquiera con el mismo router lo lee.
///
/// Estas pruebas leen los archivos de Android de verdad. No reemplazan a la
/// verificación del manifest fusionado por Gradle —eso es lo único que prueba
/// lo que termina dentro del APK— pero corren en dos segundos con el resto de
/// la suite, así que avisan el día que alguien lo vuelva a abrir.
void main() {
  final manifestPrincipal = File('android/app/src/main/AndroidManifest.xml');
  final configRelease = File('android/app/src/main/res/xml/seguridad_de_red.xml');
  final configDebug = File('android/app/src/debug/res/xml/seguridad_de_red.xml');
  final configProfile = File('android/app/src/profile/res/xml/seguridad_de_red.xml');

  group('1. El manifest no abre el tráfico en claro', () {
    test('No declara usesCleartextTraffic en ninguna variante', () {
      for (final archivo in <File>[
        manifestPrincipal,
        File('android/app/src/debug/AndroidManifest.xml'),
        File('android/app/src/profile/AndroidManifest.xml'),
      ]) {
        expect(archivo.existsSync(), isTrue, reason: '${archivo.path} no está');
        expect(
          archivo.readAsStringSync(),
          isNot(contains('usesCleartextTraffic="true"')),
          reason: 'el atributo del manifest gana sobre la configuración de red '
              'y se aplicaría a release: la excepción va en la variante de '
              'desarrollo, no acá',
        );
      }
    });

    test('Apunta a la configuración de seguridad de red', () {
      expect(
        manifestPrincipal.readAsStringSync(),
        contains('android:networkSecurityConfig="@xml/seguridad_de_red"'),
      );
    });
  });

  group('2. Release prohíbe el tráfico en claro', () {
    test('La configuración base lo niega', () {
      expect(configRelease.existsSync(), isTrue);
      expect(
        configRelease.readAsStringSync(),
        contains('<base-config cleartextTrafficPermitted="false">'),
      );
    });

    test('Y no hace ninguna excepción por dominio', () {
      // Una sola excepción acá es una excepción en el teléfono del técnico.
      expect(
        configRelease.readAsStringSync(),
        isNot(contains('cleartextTrafficPermitted="true"')),
        reason: 'la versión de release no puede tener ni un host abierto',
      );
      expect(configRelease.readAsStringSync(), isNot(contains('<domain')));
    });
  });

  group('3. Desarrollo abre lo mínimo, y solo hacia la máquina de quien programa', () {
    for (final caso in <List<Object>>[
      <Object>['debug', configDebug],
      <Object>['profile', configProfile],
    ]) {
      final nombre = caso[0] as String;
      final archivo = caso[1] as File;

      test('$nombre existe y su base sigue negando el claro', () {
        expect(archivo.existsSync(), isTrue);
        expect(
          archivo.readAsStringSync(),
          contains('<base-config cleartextTrafficPermitted="false">'),
          reason: 'la apertura es por host, no general: apuntar a un servidor '
              'de verdad por HTTP tiene que fallar también en $nombre',
        );
      });

      test('$nombre permite solo el equipo local y el emulador', () {
        final contenido = archivo.readAsStringSync();
        expect(contenido, contains('<domain includeSubdomains="false">10.0.2.2</domain>'));
        expect(contenido, contains('<domain includeSubdomains="false">localhost</domain>'));
        expect(contenido, contains('<domain includeSubdomains="false">127.0.0.1</domain>'));

        // Exactamente esos tres. Una IP de red local o un dominio de verdad
        // acá sería la misma puerta de antes, abierta más despacio.
        final dominios = RegExp(r'<domain[^>]*>([^<]+)</domain>')
            .allMatches(contenido)
            .map((m) => m.group(1))
            .toSet();
        expect(dominios, <String>{'10.0.2.2', 'localhost', '127.0.0.1'});
      });
    }
  });

  group('4. El respaldo del dispositivo sigue cerrado', () {
    test('El manifest desactiva el backup y declara sus reglas', () {
      final contenido = manifestPrincipal.readAsStringSync();
      expect(contenido, contains('android:allowBackup="false"'));
      expect(contenido, contains('android:dataExtractionRules="@xml/reglas_de_respaldo"'));
    });

    test('Las reglas excluyen la nube y la transferencia entre equipos', () {
      final reglas = File('android/app/src/main/res/xml/reglas_de_respaldo.xml');
      expect(reglas.existsSync(), isTrue);
      final contenido = reglas.readAsStringSync();
      expect(contenido, contains('<cloud-backup>'));
      expect(contenido, contains('<device-transfer>'));
      for (final dominio in const ['root', 'file', 'database', 'sharedpref']) {
        // Dos veces cada uno: una por la nube, otra por el traspaso de equipo.
        expect(
          RegExp('<exclude domain="$dominio" />').allMatches(contenido).length,
          2,
          reason: 'falta excluir "$dominio" en uno de los dos caminos de salida',
        );
      }
    });
  });
}
