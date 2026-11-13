import 'package:campo/core/storage/local_database.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' show join;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// LA SALIDA DEL CALLEJON  --  10/11/2026.
///
/// El usuario: «los cambios no se envían desde la app, quedan ahí
/// acumulándose», con la pastilla en «9 cambios necesitan que alguien lo
/// revise» y la red en verde. Un `conflicto` (409) y un `error_validacion`
/// (400) salen del reintento automático a propósito, pero hasta hoy NADA los
/// devolvía a `pendiente`: el aviso mandaba a revisar y no existía el cómo.
///
/// LO QUE ESTAS PRUEBAS AFIRMAN, Y POR QUE ES EL EFECTO Y NO EL MECANISMO:
///
/// * **La clave de idempotencia CAMBIA.** No es un detalle de
///   implementación: medido en `campo/services/idempotencia.py`, el servidor
///   guarda la respuesta de todo lo que devuelve menos de 500 --los 400 y los
///   409 incluidos--, así que reenviar con la misma clave devuelve el rechazo
///   viejo sin volver a evaluar. Si esta prueba pasara con la clave intacta,
///   estaría diciendo que el botón funciona cuando no hace nada.
/// * **La revisión se adelanta a la del teléfono.** Un 409 nace de mandar una
///   revisión vieja; reintentar con la misma vuelve a chocar.
/// * **Solo esos dos estados se mueven.** Un `error_auth` o un timeout no
///   prueban que la operación no saliera, así que reencolarlos podría aplicar
///   un efecto dos veces. El `where` nombra los dos estados en vez de decir
///   «lo que no está pendiente», y esto lo defiende.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  LocalDatabase.usarBaseDePruebas('pruebas_reencolar_rechazadas.db');

  const String org = 'org-1';
  const String perfil = 'perfil-1';

  late LocalDatabase base;

  setUp(() async {
    LocalDatabase.resetForTesting();
    base = LocalDatabase();
  });

  tearDown(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(
        await databaseFactory.getDatabasesPath(),
        'pruebas_reencolar_rechazadas.db',
      ),
    );
  });

  /// Una orden en el teléfono, con la revisión que el teléfono conoce.
  Future<void> orden(String id, {required int revision}) async {
    final db = await base.database;
    await db.insert('local_ordenes', <String, Object?>{
      'id': id,
      'org_id': org,
      'profile_id': perfil,
      'numero': 4832,
      'estado': 'en_sitio',
      'cliente_nombre': 'CLIENTE DE PRUEBA',
      'direccion': 'DIRECCION DE PRUEBA',
      'tipo_nombre': 'Instalación',
      'tipo_codigo': 'instalacion',
      'revision': revision,
      'updated_at': DateTime.now().millisecondsSinceEpoch,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  /// Un cambio en la cola, ya rechazado por el servidor.
  Future<void> rechazada(
    String id, {
    required String estado,
    String ordenId = 'ot-1',
    int revisionBase = 3,
    String motivo = 'motivo viejo',
  }) async {
    final db = await base.database;
    await db.insert('cola_mutaciones', <String, Object?>{
      'id': id,
      'org_id': org,
      'profile_id': perfil,
      'orden_id': ordenId,
      'tipo': 'completar',
      'payload_json': null,
      'revision_base': revisionBase,
      'idempotency_key': id,
      'estado': estado,
      'error_mensaje': motivo,
      'reintentos': 7,
      'next_attempt_at': 0,
      'created_at': DateTime.now().millisecondsSinceEpoch,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<Map<String, Object?>> fila(String id) async {
    final db = await base.database;
    final r = await db.query('cola_mutaciones', where: 'id = ?', whereArgs: [id]);
    return r.first;
  }

  group('A · el rechazo vuelve a la cola', () {
    test('a1 · un error de validación vuelve a pendiente, y con clave nueva',
        () async {
      await orden('ot-1', revision: 5);
      await rechazada('m1', estado: 'error_validacion');

      final movidas = await base.reencolarRechazadas(
          orgId: org, profileId: perfil);

      expect(movidas, 1);
      final f = await fila('m1');
      expect(f['estado'], 'pendiente');
      //  EL EFECTO QUE DECIDE SI EL BOTON SIRVE: la clave cambió. Con la
      //  misma, el servidor contesta con su copia del rechazo y el reintento
      //  no evalúa nada.
      expect(f['idempotency_key'], isNot('m1'));
      expect((f['idempotency_key'] as String).length, greaterThan(20));
      //  Y vuelve a estar elegible ya: sin reintentos acumulados ni espera.
      expect(f['reintentos'], 0);
      expect(f['next_attempt_at'], 0);
    });

    test('a2 · un conflicto sale con la revisión que el teléfono tiene AHORA',
        () async {
      await orden('ot-1', revision: 9);
      await rechazada('m1', estado: 'conflicto', revisionBase: 3);

      await base.reencolarRechazadas(orgId: org, profileId: perfil);

      //  Un 409 nace de mandar una revisión vieja. Si saliera con la misma,
      //  el servidor volvería a rechazarlo por lo mismo.
      expect((await fila('m1'))['revision_base'], 9);
    });

    test('a3 · el motivo viejo se borra', () async {
      await orden('ot-1', revision: 5);
      await rechazada('m1', estado: 'conflicto', motivo: 'STALE_WORK_ORDER');

      await base.reencolarRechazadas(orgId: org, profileId: perfil);

      //  Si vuelve a fallar, el motivo que quede tiene que ser de ESTE
      //  intento. Dejar el viejo haría leer una causa que ya no se midió.
      expect((await fila('m1'))['error_mensaje'], isNull);
    });

    test('a4 · sin la orden en el teléfono, no se inventa una revisión',
        () async {
      //  Sin `orden(...)`: la orden ya no está local.
      await rechazada('m1', estado: 'conflicto', revisionBase: 3);

      await base.reencolarRechazadas(orgId: org, profileId: perfil);

      final f = await fila('m1');
      expect(f['estado'], 'pendiente');
      expect(f['revision_base'], 3, reason: 'la que tenía, no un cero');
    });
  });

  group('B · lo que NO se mueve', () {
    test('b1 · un error de sesión se queda donde está', () async {
      await orden('ot-1', revision: 5);
      await rechazada('m1', estado: 'error_auth');

      final movidas = await base.reencolarRechazadas(
          orgId: org, profileId: perfil);

      //  Un `error_auth` no prueba que la operación no saliera. Reencolarlo
      //  podría aplicar el mismo efecto dos veces.
      expect(movidas, 0);
      final f = await fila('m1');
      expect(f['estado'], 'error_auth');
      expect(f['idempotency_key'], 'm1', reason: 'ni la clave se le toca');
    });

    test('b2 · una que ya está pendiente no se re-clava', () async {
      await orden('ot-1', revision: 5);
      await rechazada('m1', estado: 'pendiente');

      expect(
          await base.reencolarRechazadas(orgId: org, profileId: perfil), 0);
      //  Renovarle la clave a algo que todavía puede estar en vuelo es
      //  exactamente cómo se aplica una operación dos veces.
      expect((await fila('m1'))['idempotency_key'], 'm1');
    });

    test('b3 · un 404 terminal tampoco: la orden no existe', () async {
      await rechazada('m1', estado: 'terminal_404');
      expect(
          await base.reencolarRechazadas(orgId: org, profileId: perfil), 0);
    });

    test('b4 · lo de otro técnico en el mismo teléfono no se toca', () async {
      await orden('ot-1', revision: 5);
      await rechazada('m1', estado: 'conflicto');
      final db = await base.database;
      await db.insert('cola_mutaciones', <String, Object?>{
        'id': 'm2',
        'org_id': org,
        'profile_id': 'OTRO-PERFIL',
        'orden_id': 'ot-1',
        'tipo': 'completar',
        'revision_base': 3,
        'idempotency_key': 'm2',
        'estado': 'conflicto',
        'reintentos': 0,
        'next_attempt_at': 0,
        'created_at': 1,
      });

      expect(
          await base.reencolarRechazadas(orgId: org, profileId: perfil), 1);
      expect((await fila('m2'))['estado'], 'conflicto');
      expect((await fila('m2'))['idempotency_key'], 'm2');
    });
  });

  group('C · de una en una', () {
    test('c1 · con soloId se mueve esa y nada más', () async {
      await orden('ot-1', revision: 5);
      await rechazada('m1', estado: 'conflicto');
      await rechazada('m2', estado: 'error_validacion');

      final movidas = await base.reencolarRechazadas(
          orgId: org, profileId: perfil, soloId: 'm1');

      expect(movidas, 1);
      expect((await fila('m1'))['estado'], 'pendiente');
      expect((await fila('m2'))['estado'], 'error_validacion');
    });

    test('c2 · varias a la vez se cuentan todas', () async {
      await orden('ot-1', revision: 5);
      await rechazada('m1', estado: 'conflicto');
      await rechazada('m2', estado: 'error_validacion');
      await rechazada('m3', estado: 'error_auth');

      expect(
          await base.reencolarRechazadas(orgId: org, profileId: perfil), 2);
    });

    test('c3 · dos reencolados seguidos no dan la misma clave', () async {
      //  Dos rechazos distintos no pueden terminar compartiendo clave: el
      //  servidor contaría uno de los dos como repetición del otro.
      await orden('ot-1', revision: 5);
      await rechazada('m1', estado: 'conflicto');
      await rechazada('m2', estado: 'conflicto');

      await base.reencolarRechazadas(orgId: org, profileId: perfil);

      expect((await fila('m1'))['idempotency_key'],
          isNot((await fila('m2'))['idempotency_key']));
    });
  });

  group('D · el motivo llega a quien lo muestra', () {
    test('d1 · el detalle de pendientes trae el motivo del servidor',
        () async {
      //  La consulta que alimenta la hoja de pendientes no traía
      //  `error_mensaje`: la pantalla no podía decir qué revisar ni queriendo.
      await orden('ot-1', revision: 5);
      await rechazada('m1',
          estado: 'error_validacion',
          motivo: "El campo 'potencia_rx' no existe en la plantilla.");

      final detalle = await base.getMutacionesPendientesDetalle(
          orgId: org, profileId: perfil);

      expect(detalle, hasLength(1));
      expect(detalle.first['error_mensaje'], contains('potencia_rx'));
    });
  });
}
