import 'package:campo/core/storage/local_database.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' show join;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Una evidencia dice cuándo se capturó, no sólo cuándo llegó.
///
/// POR QUÉ ESTO EXISTE
/// -------------------
/// El backend espera `capturada_en_cliente` desde el principio —está en el
/// serializer, con su ayuda escrita— y la aplicación **no la mandaba nunca**.
/// Se buscó en todo `lib/`: cero ocurrencias. La columna existía del otro lado
/// y quedaba vacía en todas las filas.
///
/// Importa más de lo que parece. Una foto sin hora prueba que *alguien subió
/// una foto*. Con hora prueba que se tomó **antes** de subirla, que es lo que
/// se discute cuando alguien la revisa meses después. El servidor guarda por
/// su cuenta `recibida_en_servidor`, y la distancia entre las dos es
/// información: una foto que dice haberse tomado después de recibida es una
/// señal, no un dato.
///
/// Lo que estas pruebas NO afirman: que el campo exista. Afirman que el valor
/// llega hasta la fila y que es el que se pidió — una prueba que sólo mirara
/// si la columna está presente sobreviviría intacta a que se guarde siempre
/// `null`, que es exactamente como estaba antes de este cambio.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  // Base propia: `flutter test` corre los archivos en paralelo y contra el
  // `dexter_campo.db` compartido la preparación de una suite le vacía las
  // tablas a la de al lado.
  LocalDatabase.usarBaseDePruebas('pruebas_hora_de_captura.db');

  const String org = 'org-hora';
  const String perfil = 'perfil-hora';

  late LocalDatabase base;

  setUp(() async {
    LocalDatabase.resetForTesting();
    base = LocalDatabase();
  });

  tearDown(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(),
          'pruebas_hora_de_captura.db'),
    );
  });

  Future<void> encolar(
    String id,
    String requisito, {
    DateTime? capturadaEn,
  }) =>
      base.encolarEvidencia(
        id: id,
        orgId: org,
        profileId: perfil,
        ordenId: 'ot-1',
        requisitoId: requisito,
        archivoPath: '/tmp/$id.jpg',
        sha256: id,
        tamanoBytes: 100,
        mimeType: 'image/jpeg',
        capturadaEn: capturadaEn,
      );

  Future<Map<String, int?>> horasPorId() async {
    final List<Map<String, dynamic>> filas =
        await base.getEvidenciasPendientes(orgId: org, profileId: perfil);
    return <String, int?>{
      for (final Map<String, dynamic> f in filas)
        f['id'] as String: f['capturada_en'] as int?,
    };
  }

  group('La hora de captura de una evidencia', () {
    test('1. Se guarda la hora que se pidió, no la de encolar', () async {
      // Distinta de "ahora" por horas a propósito. Si el código ignorara el
      // parámetro y usara su propio reloj, la diferencia sería evidente; una
      // prueba que pasara una hora cercana a la actual no podría distinguir
      // las dos cosas y pasaría por la razón equivocada.
      final DateTime cuandoSeTomo =
          DateTime.now().subtract(const Duration(hours: 3));

      await encolar('ev-1', 'foto_ont', capturadaEn: cuandoSeTomo);

      expect(
        (await horasPorId())['ev-1'],
        cuandoSeTomo.millisecondsSinceEpoch,
        reason: 'la hora que llega a la fila es la que se pidió',
      );
    });

    test('2. Sin valor explícito queda la de encolar, nunca vacía', () async {
      // El camino de cualquier llamador que no la pase. Encolar es décimas
      // después de capturar —entre medio hay una copia de archivo y un
      // sha256— así que no es un relleno: es el mismo hecho medido un
      // instante más tarde. Lo que no puede quedar es vacío, que es
      // exactamente como estaba antes.
      final int antes = DateTime.now().millisecondsSinceEpoch;

      await encolar('ev-2', 'foto_roseta');

      final int? capturada = (await horasPorId())['ev-2'];
      expect(capturada, isNotNull);
      expect(capturada! >= antes, isTrue);
      expect(capturada <= DateTime.now().millisecondsSinceEpoch, isTrue);
    });

    test('3. Cada evidencia lleva la suya', () async {
      // Dos fotos del mismo trabajo tomadas con una hora de diferencia no
      // pueden terminar con la misma hora: la secuencia es parte de lo que
      // una evidencia prueba.
      final DateTime primera =
          DateTime.now().subtract(const Duration(hours: 2));
      final DateTime segunda =
          DateTime.now().subtract(const Duration(hours: 1));

      await encolar('ev-a', 'foto_cto', capturadaEn: primera);
      await encolar('ev-b', 'foto_potencia', capturadaEn: segunda);

      final Map<String, int?> horas = await horasPorId();
      expect(horas['ev-a'], primera.millisecondsSinceEpoch);
      expect(horas['ev-b'], segunda.millisecondsSinceEpoch);
      expect(horas['ev-a'], isNot(horas['ev-b']));
    });

    test('4. Una foto de ayer conserva su hora, no la de subirla', () async {
      // El caso que da sentido a todo: un día sin señal. La foto se toma en
      // un sótano y sube al día siguiente. Si la hora se calculara al subir,
      // la evidencia diría que el técnico estuvo ahí un día después — y sería
      // justo en las fotos que más necesitan probar cuándo se tomaron.
      final DateTime ayer =
          DateTime.now().subtract(const Duration(days: 1, minutes: 30));

      await encolar('ev-ayer', 'firma_cliente', capturadaEn: ayer);

      final List<Map<String, dynamic>> pendientes =
          await base.getEvidenciasPendientes(orgId: org, profileId: perfil);

      expect(pendientes, hasLength(1),
          reason: 'sigue en la cola: todavía no subió');
      expect(pendientes.first['capturada_en'], ayer.millisecondsSinceEpoch);
      expect(
        pendientes.first['created_at'] as int,
        greaterThan(ayer.millisecondsSinceEpoch),
        reason: 'encolada hoy, capturada ayer: son dos hechos distintos y la '
            'fila los distingue',
      );
    });
  });
}
