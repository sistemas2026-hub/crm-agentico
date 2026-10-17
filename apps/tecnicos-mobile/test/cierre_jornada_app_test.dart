import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Cerrar la jornada desde el teléfono.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// La diferencia entre **tomar** el cierre y **tener** la jornada cerrada. Lo
/// primero pasa en la calle, cuando el técnico dice que terminó; lo segundo lo
/// dice el servidor cuando validó que todo cuadra y congeló el acta.
///
/// Confundirlas es lo que haría que alguien se vaya a su casa creyendo que
/// entregó, y descubra tres días después que su jornada nunca llegó.
///
/// También cuidan que una diferencia no se pueda guardar sin explicación: sin
/// esa frase, el faltante aparece en el conteo del mes que viene y ya no hay a
/// quién preguntarle.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_cierre_app.db');

  setUpAll(() async {
    // Se arranca de cero. Una base que quedo de una corrida anterior tiene el
    // esquema de entonces y la version ya aplicada, asi que no vuelve a
    // migrar: el fallo aparece como "no such column" y parece un bug del
    // codigo cuando es basura del entorno.
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(), 'pruebas_cierre_app.db'),
    );
  });

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
      'cola_incidencias',
    ]) {
      await base.delete(t);
    }
  });

  Map<String, dynamic> respuesta({
    List<String> motivos = const <String>[],
    String devuelto = '10',
  }) =>
      <String, dynamic>{
        'estado': 'pendiente',
        'puede_cerrar': motivos.isEmpty,
        'motivos': motivos,
        'series_sin_devolver': <String>[],
        'transferencias_pendientes': <Map<String, dynamic>>[],
        'resumen': <String, dynamic>{
          'ordenes': <String, dynamic>{
            'asignadas': 8, 'completadas': 7, 'pendientes': 1,
          },
          'material': <String, dynamic>{
            'recibido': '24', 'consumido': '14', 'a_devolver': '10',
            'devuelto': devuelto, 'diferencias': 0,
          },
          'detalle': <Map<String, dynamic>>[
            {
              'codigo': 'CON-SC-APC', 'nombre': 'Conector SC/APC',
              'unidad': 'unidades', 'esperado_devolver': '10',
              'devuelto': devuelto,
            },
          ],
        },
      };

  Future<EstadoDeJornada> leer() => EstadoDeJornada.leer(
        baseLocal: db,
        almacenamiento: _Sesion(orgA, perfilA),
      );

  group('1. Tomar el cierre no es tenerlo cerrado', () {
    test('Al tomarlo queda pendiente de sincronizar, no confirmado', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );

      await db.marcarCierreLocal(
        orgId: orgA, profileId: perfilA, clave: 'cierre-1',
      );
      final estado = await leer();

      expect(estado.cierreTomado, isTrue);
      expect(estado.cerrada, isFalse,
          reason: 'eso solo lo dice el servidor');
    });

    test('Y ya no se ofrece cerrar de nuevo', () async {
      // El doble toque no puede producir dos actas.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );
      expect((await leer()).puedeCerrar, isTrue);

      await db.marcarCierreLocal(
        orgId: orgA, profileId: perfilA, clave: 'cierre-1',
      );

      expect((await leer()).puedeCerrar, isFalse);
    });

    test('La clave se guarda para que el reintento use la misma', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );

      await db.marcarCierreLocal(
        orgId: orgA, profileId: perfilA, clave: 'cierre-unico',
      );
      final fila = await db.getJornada(orgId: orgA, profileId: perfilA);

      expect(fila!['cierre_clave'], 'cierre-unico');
      expect(fila['cierre_local_en'], isNotNull);
    });

    test('Cuando el servidor confirma, pasa a cerrada', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );
      await db.marcarCierreLocal(
        orgId: orgA, profileId: perfilA, clave: 'cierre-1',
      );

      // La sincronización baja el estado nuevo.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: <String, dynamic>{...respuesta(), 'estado': 'confirmada'},
      );
      final estado = await leer();

      expect(estado.cerrada, isTrue);
    });
  });

  group('2. Una diferencia sin motivo no se guarda', () {
    test('Encolar sin motivo se rechaza', () async {
      expect(
        () => db.encolarIncidencia(
          id: 'i1', orgId: orgA, profileId: perfilA,
          materialCodigo: 'CON-SC-APC', tipo: 'perdido', cantidad: '2',
          motivo: '   ',
        ),
        throwsArgumentError,
      );
    });

    test('Con motivo se encola y queda esperando señal', () async {
      await db.encolarIncidencia(
        id: 'i1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', materialNombre: 'Conector SC/APC',
        tipo: 'perdido', cantidad: '2',
        motivo: 'Perdido: se cayeron de la escalera.',
      );

      final pendientes = await db.getIncidenciasPendientes(
        orgId: orgA, profileId: perfilA,
      );

      expect(pendientes, hasLength(1));
      expect(pendientes.first['estado'], 'pendiente');
      expect(pendientes.first['motivo'], contains('escalera'));
    });

    test('La misma clave no la duplica', () async {
      for (var i = 0; i < 2; i++) {
        await db.encolarIncidencia(
          id: 'i1', orgId: orgA, profileId: perfilA,
          materialCodigo: 'CON-SC-APC', tipo: 'danado', cantidad: '2',
          motivo: 'Dañado',
        );
      }

      expect(
        await db.getIncidenciasSinConfirmar(orgId: orgA, profileId: perfilA),
        hasLength(1),
      );
    });

    test('Un fallo al subir no la descarta', () async {
      await db.encolarIncidencia(
        id: 'i1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', tipo: 'perdido', cantidad: '2',
        motivo: 'Perdido',
      );

      await db.registrarFalloIncidencia(
        id: 'i1', orgId: orgA, profileId: perfilA,
        nextAttemptAt: 0, errorMensaje: 'El servidor respondio 503.',
      );

      final pendientes = await db.getIncidenciasPendientes(
        orgId: orgA, profileId: perfilA,
      );
      expect(pendientes, hasLength(1));
      expect(pendientes.first['intentos'], 1);
    });

    test('Y la de otra persona no se ve ni se toca', () async {
      await db.encolarIncidencia(
        id: 'i1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', tipo: 'perdido', cantidad: '2',
        motivo: 'Perdido',
      );

      await db.confirmarIncidencia(
        id: 'i1', orgId: orgA, profileId: 'prof_pedro',
        resultado: 'registrada',
      );

      final mias = await db.getIncidenciasSinConfirmar(
        orgId: orgA, profileId: perfilA,
      );
      expect(mias, hasLength(1), reason: 'sigue siendo mía y sin confirmar');
    });
  });

  group('3. El cierre se toma sin señal', () {
    test('Con movimientos sin subir, igual se puede tomar', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );
      await db.encolarMovimientoMaterial(
        id: 'd1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', tipo: 'devolucion', cantidad: '1',
      );

      final antes = await leer();

      expect(antes.sinSubir, 1);
      expect(antes.puedeCerrar, isTrue, reason: 'la red no decide esto');
    });

    test('Con una diferencia sin explicar, NO se puede', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: <String>[
          'Conector SC/APC: faltan 2 unidades sin explicar.',
        ]),
      );

      expect((await leer()).puedeCerrar, isFalse);
    });

    test('Explicada, el servidor deja de objetarla', () async {
      // El telefono no decide esto: encola la explicacion y el servidor
      // recalcula. Lo que se prueba es que la pantalla refleja el cambio.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: <String>['faltan 2 sin explicar']),
      );
      await db.encolarIncidencia(
        id: 'i1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', tipo: 'perdido', cantidad: '2',
        motivo: 'Perdido: se cayeron.',
      );
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );

      expect((await leer()).puedeCerrar, isTrue);
    });
  });

  group('4. Nada de esto se mezcla entre personas', () {
    test('El cierre de uno no cierra el del otro', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );
      await db.guardarJornada(
        orgId: orgA, profileId: 'prof_pedro', datos: respuesta(),
      );

      await db.marcarCierreLocal(
        orgId: orgA, profileId: perfilA, clave: 'cierre-1',
      );

      final deOtro = await EstadoDeJornada.leer(
        baseLocal: db,
        almacenamiento: _Sesion(orgA, 'prof_pedro'),
      );
      expect(deOtro.cierreTomado, isFalse);
      expect(deOtro.puedeCerrar, isTrue);
    });

    test('Las incidencias de una jornada ajena no cuentan', () async {
      await db.encolarIncidencia(
        id: 'i1', orgId: orgA, profileId: 'prof_pedro',
        materialCodigo: 'CON-SC-APC', tipo: 'perdido', cantidad: '2',
        motivo: 'Perdido',
      );

      expect(
        await db.getIncidenciasSinConfirmar(orgId: orgA, profileId: perfilA),
        isEmpty,
      );
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
