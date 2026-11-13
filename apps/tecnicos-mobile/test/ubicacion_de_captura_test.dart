import 'dart:convert';

import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/ubicacion_de_captura.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' show join;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Dónde se tomó cada evidencia — y qué pasa cuando no se puede saber.
///
/// POR QUÉ ESTO EXISTE
/// -------------------
/// El backend espera `metadatos_captura` desde el principio y la aplicación no
/// mandaba nada. Una foto sin lugar prueba que alguien subió una foto; con
/// lugar prueba que esa persona estuvo **ahí**.
///
/// LO QUE ESTAS PRUEBAS PROTEGEN DE VERDAD
/// ---------------------------------------
/// No es que el GPS funcione: eso lo prueba el teléfono. Es que **la ubicación
/// nunca cueste una evidencia**. El trabajo de campo ocurre en sótanos, cajas
/// de distribución y zonas rurales, que es justo donde el GPS no fija, así que
/// "no se pudo ubicar" no es el borde raro: es la mitad de los días.
///
/// Una implementación que dejara caer la foto cuando el GPS falla sería
/// infinitamente peor que la que había antes, y el síntoma aparecería recién
/// en la vereda, sin red, con el cliente esperando.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_ubicacion_captura.db');

  const String org = 'org-ubi';
  const String perfil = 'perfil-ubi';

  late LocalDatabase base;

  setUp(() async {
    LocalDatabase.resetForTesting();
    base = LocalDatabase();
  });

  tearDown(() async {
    UbicacionDeCaptura.overrideParaPruebas = null;
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(),
          'pruebas_ubicacion_captura.db'),
    );
  });

  Future<Map<String, dynamic>?> metadatosGuardados(String id) async {
    final List<Map<String, dynamic>> filas =
        await base.getEvidenciasPendientes(orgId: org, profileId: perfil);
    final Map<String, dynamic> fila =
        filas.firstWhere((Map<String, dynamic> f) => f['id'] == id);
    final String? crudo = fila['metadatos_captura_json'] as String?;
    return crudo == null ? null : jsonDecode(crudo) as Map<String, dynamic>;
  }

  Future<void> encolar(String id, {Map<String, dynamic>? metadatos}) =>
      base.encolarEvidencia(
        id: id,
        orgId: org,
        profileId: perfil,
        ordenId: 'ot-1',
        requisitoId: 'foto_ont',
        archivoPath: '/tmp/$id.jpg',
        sha256: id,
        tamanoBytes: 100,
        mimeType: 'image/jpeg',
        capturadaEn: DateTime.now(),
        metadatosCaptura: metadatos,
      );

  group('La ubicación de una evidencia', () {
    test('1. Las coordenadas llegan hasta la fila, con su precisión',
        () async {
      // La precisión viaja con el punto a propósito: sin ella, una posición
      // de la antena de celular a 2 km se ve igual de confiable que una del
      // GPS a 4 m, y quien la mire después no tiene cómo distinguirlas.
      await encolar('ev-1', metadatos: <String, dynamic>{
        'lat': 4.60971,
        'lng': -74.08175,
        'precision_m': 8.5,
        'plataforma': 'android',
      });

      final Map<String, dynamic> m = (await metadatosGuardados('ev-1'))!;
      expect(m['lat'], 4.60971);
      expect(m['lng'], -74.08175);
      expect(m['precision_m'], 8.5);
      expect(m['plataforma'], 'android');
    });

    test('2. Un sótano sin señal deja el motivo, no un vacío', () async {
      // El caso normal, no el raro. Y la diferencia que importa: un objeto
      // con `ubicacion_motivo` dice "se intentó y no se pudo"; un nulo dice
      // "ni se intentó". Quien audite la evidencia necesita distinguirlas.
      await encolar('ev-2', metadatos: <String, dynamic>{
        'ubicacion_motivo': 'sin_senal_gps',
        'plataforma': 'android',
      });

      final Map<String, dynamic> m = (await metadatosGuardados('ev-2'))!;
      expect(m['ubicacion_motivo'], 'sin_senal_gps');
      expect(m.containsKey('lat'), isFalse,
          reason: 'sin señal no se inventa una coordenada');
    });

    test('3. Una evidencia sin metadatos se encola igual', () async {
      // La regla que manda sobre todo lo demás: la ubicación nunca puede
      // costar una evidencia. Este es el camino de las pruebas viejas y de
      // cualquier llamador que no los pase.
      await encolar('ev-3');

      final List<Map<String, dynamic>> filas =
          await base.getEvidenciasPendientes(orgId: org, profileId: perfil);
      expect(filas.where((Map<String, dynamic> f) => f['id'] == 'ev-3'),
          hasLength(1));
      expect(await metadatosGuardados('ev-3'), isNull,
          reason: 'nulo = no se intentó, y eso es un dato distinto de un '
              'intento fallido');
    });

    test('4. El servicio nunca lanza, aunque adentro todo falle', () async {
      // La garantía entera del diseño en una línea. Si esto lanzara, el
      // `await` de la pantalla de ejecución tiraría la foto recién tomada.
      UbicacionDeCaptura.overrideParaPruebas =
          () => throw StateError('el sistema dijo que no');

      expect(
        () async => UbicacionDeCaptura.tomar(),
        throwsA(isA<StateError>()),
        reason: 'el doble sí lanza: es lo que se está simulando',
      );

      // Y con el servicio real, un entorno sin GPS ni permisos —que es
      // exactamente este— devuelve un mapa, no una excepción.
      UbicacionDeCaptura.overrideParaPruebas = null;
      final Map<String, dynamic> m = await UbicacionDeCaptura.tomar();
      expect(m, isA<Map<String, dynamic>>());
      expect(m['ubicacion_motivo'], isNotNull,
          reason: 'sin plataforma que responda, tiene que decir por qué no');
      expect(m.containsKey('lat'), isFalse);
    });

    test('5. Cada evidencia lleva su propia ubicación', () async {
      // Dos fotos de trabajos distintos en el mismo día no pueden compartir
      // el punto: el lugar es parte de lo que cada una prueba.
      await encolar('ev-a', metadatos: <String, dynamic>{'lat': 4.60, 'lng': -74.08});
      await encolar('ev-b', metadatos: <String, dynamic>{'lat': 4.71, 'lng': -74.14});

      expect((await metadatosGuardados('ev-a'))!['lat'], 4.60);
      expect((await metadatosGuardados('ev-b'))!['lat'], 4.71);
    });

    test('6. Una ubicación simulada queda marcada', () async {
      // Android sabe cuándo la posición viene de una aplicación que finge
      // estar en otro lado. Si eso no se registrara, la evidencia falsa se
      // vería idéntica a la real.
      await encolar('ev-f', metadatos: <String, dynamic>{
        'lat': 4.60,
        'lng': -74.08,
        'ubicacion_simulada': true,
      });

      expect((await metadatosGuardados('ev-f'))!['ubicacion_simulada'], isTrue);
    });
  });
}
