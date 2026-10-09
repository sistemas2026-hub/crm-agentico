import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Devolución y cierre de jornada.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// Que los números que el técnico ve sean los mismos que va a firmar. El
/// resumen lo calcula el dominio; el teléfono solo lo muestra y le suma lo que
/// todavía no subió. Si la pantalla hiciera su propia cuenta, el día que las
/// dos difieran una de ellas estaría en un papel firmado.
///
/// Y que lo que bloquea el cierre sea que la jornada se contradiga —una
/// diferencia sin explicar, un equipo sin ubicar— nunca la falta de señal.
/// Bloquear por red deja a alguien sin poder irse a su casa.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_jornada.db');

  const orgA = 'org_rapilink';
  const perfilA = 'prof_carlos';

  late LocalDatabase db;

  setUp(() async {
    db = LocalDatabase();
    final base = await db.database;
    for (final t in const [
      'local_kit',
      'cola_movimientos_material',
      'local_jornada',
    ]) {
      await base.delete(t);
    }
  });

  /// Lo que contestaría el servidor.
  Map<String, dynamic> respuesta({
    String recibido = '24',
    String consumido = '14',
    String aDevolver = '10',
    String devuelto = '10',
    List<Map<String, dynamic>>? detalle,
    List<String> motivos = const <String>[],
    List<String> series = const <String>[],
    List<Map<String, dynamic>> transferencias = const <Map<String, dynamic>>[],
    String estado = 'pendiente',
    int asignadas = 8,
    int completadas = 7,
  }) =>
      <String, dynamic>{
        'estado': estado,
        'puede_cerrar': motivos.isEmpty,
        'motivos': motivos,
        'series_sin_devolver': series,
        'transferencias_pendientes': transferencias,
        'resumen': <String, dynamic>{
          'ordenes': <String, dynamic>{
            'asignadas': asignadas,
            'completadas': completadas,
            'pendientes': asignadas - completadas,
          },
          'material': <String, dynamic>{
            'recibido': recibido,
            'consumido': consumido,
            'a_devolver': aDevolver,
            'devuelto': devuelto,
            'diferencias': 0,
          },
          'detalle': detalle ??
              <Map<String, dynamic>>[
                {
                  'codigo': 'CON-SC-APC',
                  'nombre': 'Conector SC/APC',
                  'unidad': 'unidades',
                  'clase': 'consumible',
                  'entregado': '24',
                  'consumido': '14',
                  'esperado_devolver': '10',
                  'devuelto': '10',
                  'diferencia': '0',
                },
              ],
        },
      };

  Future<EstadoDeJornada> leer() => EstadoDeJornada.leer(
        baseLocal: db,
        almacenamiento: _Sesion(orgA, perfilA),
      );

  group('1. El kit completo', () {
    test('Los números son los del servidor, sin recalcular', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );

      final estado = await leer();

      expect(estado.recibido, '24');
      expect(estado.consumido, '14');
      expect(estado.aDevolver, '10');
      expect(estado.ordenesAsignadas, 8);
      expect(estado.ordenesCompletadas, 7);
      expect(estado.ordenesPendientes, 1);
    });

    test('Sin jornada guardada, no se inventa ninguna', () async {
      final estado = await leer();

      expect(estado.hayJornada, isFalse);
      expect(estado.puedeCerrar, isFalse);
    });
  });

  group('2. La devolución', () {
    test('Todo devuelto: la línea cuadra y no ofrece devolver', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );

      final material = (await leer()).materiales.single;

      expect(material.esperado, '10');
      expect(material.devuelto, '10');
      expect(material.diferencia, 0);
      expect(material.porDevolver, 0);
    });

    test('Una devolución sin subir YA cuenta como devuelta', () async {
      // Si no contara, el técnico devuelve siete, no ve el cambio, y los
      // devuelve otra vez.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(devuelto: '0', detalle: <Map<String, dynamic>>[
          {
            'codigo': 'CON-SC-APC', 'nombre': 'Conector SC/APC',
            'unidad': 'unidades', 'esperado_devolver': '10', 'devuelto': '0',
          },
        ]),
      );
      await db.encolarMovimientoMaterial(
        id: 'd1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', tipo: 'devolucion', cantidad: '10',
      );

      final material = (await leer()).materiales.single;

      expect(material.devuelto, '10');
      expect(material.diferencia, 0);
    });
  });

  group('3. Las diferencias no se esconden', () {
    test('Lo que falta se ve como diferencia', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(detalle: <Map<String, dynamic>>[
          {
            'codigo': 'CON-SC-APC', 'nombre': 'Conector SC/APC',
            'unidad': 'unidades', 'esperado_devolver': '10', 'devuelto': '8',
          },
        ]),
      );

      final estado = await leer();

      expect(estado.materiales.single.diferencia, 2);
      expect(estado.diferencias, 1);
    });

    test('Y bloquea el cierre con el motivo del servidor', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: <String>[
          'Conector SC/APC: faltan 2 unidades sin explicar.',
        ]),
      );

      final estado = await leer();

      expect(estado.puedeCerrar, isFalse);
      expect(estado.motivos.single, contains('faltan 2'));
    });
  });

  group('4. Los equipos con número', () {
    test('Se muestran con su serie, no como cantidad', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(detalle: <Map<String, dynamic>>[
          {
            'codigo': 'ONT-HG8145', 'nombre': 'ONT Huawei HG8145V5',
            'unidad': 'unidades', 'clase': 'serializado',
            'serie': '48575448A9B0C1',
            'esperado_devolver': '1', 'devuelto': '0',
          },
        ]),
      );

      final material = (await leer()).materiales.single;

      expect(material.serie, '48575448A9B0C1');
      expect(material.diferencia, 1);
    });

    test('Uno sin ubicar bloquea el cierre', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(
          series: <String>['48575448A9B0C1'],
          motivos: <String>[
            'El equipo con serie 48575448A9B0C1 no se instaló ni volvió a '
                'bodega: hay que decir dónde está.',
          ],
        ),
      );

      final estado = await leer();

      expect(estado.puedeCerrar, isFalse);
      expect(estado.motivos.single, contains('48575448A9B0C1'));
    });
  });

  group('5. Las transferencias explican un saldo que no baja', () {
    test('Se listan como pendientes de aceptación', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(transferencias: <Map<String, dynamic>>[
          {
            'material_nombre': 'Conector SC/APC',
            'cantidad': '4',
            'recibe': 'Pedro',
          },
        ]),
      );

      final estado = await leer();

      expect(estado.transferencias.single.recibe, 'Pedro');
      expect(estado.transferencias.single.cantidad, '4');
    });
  });

  group('6. Qué bloquea y qué no', () {
    test('Sin señal, con todo cuadrado, SE PUEDE cerrar', () async {
      // Esperar señal para cerrar dejaría a alguien sin poder irse a su casa.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );
      await db.encolarMovimientoMaterial(
        id: 'd1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', tipo: 'devolucion', cantidad: '1',
      );

      final estado = await leer();

      expect(estado.sinSubir, 1, reason: 'se avisa');
      expect(estado.puedeCerrar, isTrue, reason: 'pero no bloquea');
    });

    test('Una jornada ya cerrada no se vuelve a cerrar', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(estado: 'confirmada'),
      );

      final estado = await leer();

      expect(estado.cerrada, isTrue);
      expect(estado.puedeCerrar, isFalse);
    });

    test('La jornada de otra persona no se ve', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );

      final ajena = await EstadoDeJornada.leer(
        baseLocal: db,
        almacenamiento: _Sesion(orgA, 'prof_pedro'),
      );

      expect(ajena.hayJornada, isFalse);
    });
  });
}

class _Sesion implements SecureStorageLectura {
  _Sesion(this._org, this._perfil);

  final String? _org;
  final String? _perfil;

  @override
  Future<String?> getOrgId() async => _org;

  @override
  Future<String?> getProfileId() async => _perfil;
}
