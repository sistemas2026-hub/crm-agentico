// ============================================================================
//  LA COLA GENERAL Y LA DE UNA ORDEN  --  dos cuentas, ninguna que mienta
// ============================================================================
//
// Había dos frases sobre lo mismo y podían contradecirse de verdad, no por
// redacción:
//
//   1. `cola_seguimiento` se sincroniza igual que las otras tres colas, pero
//      NO entraba en `getSyncCounts`. La pastilla del encabezado decía
//      «Sincronizado» con reportes esperando adentro de la orden.
//   2. `contarSeguimientosPendientes` no filtraba por `orden_id`, y la
//      pantalla rotulaba ese número «escritos acá». Un reporte de la orden
//      anterior se leía como pendiente de la que se estaba mirando.
//
// Las pruebas afirman sobre el EFECTO —qué número sale de la base en cada
// caso— contra PostgreSQL no, pero sí contra el SQLite real de la aplicación,
// que es donde vive esta cola. No se prueba que los contadores existan.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:campo/core/sync/sync_presentacion.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/widgets/dexter_sync_badge.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  late Database db;

  setUp(() async {
    db = await databaseFactory.openDatabase(inMemoryDatabasePath);
    // Solo las columnas que estas cuentas usan: la tabla real tiene más, y
    // copiarla entera acá la volvería una segunda definición que se
    // desactualiza sola.
    await db.execute('''
      CREATE TABLE cola_seguimiento (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        orden_id TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'pendiente'
      )
    ''');
  });

  tearDown(() async => db.close());

  Future<void> reporte(String id, String ordenId, String estado) =>
      db.insert('cola_seguimiento', <String, Object?>{
        'id': id,
        'org_id': 'org-1',
        'profile_id': 'tec-1',
        'orden_id': ordenId,
        'estado': estado,
      });

  /// La cuenta acotada a una orden, como la hace `local_database.dart`.
  Future<int> pendientesDe(String? ordenId) async {
    final List<Map<String, Object?>> filas = await db.rawQuery(
      "SELECT COUNT(*) AS n FROM cola_seguimiento "
      "WHERE org_id = ? AND profile_id = ? AND estado = 'pendiente'"
      "${ordenId == null ? '' : ' AND orden_id = ?'}",
      <Object?>['org-1', 'tec-1', ?ordenId],
    );
    return (filas.first['n'] as int?) ?? 0;
  }

  group('Cada cuenta cuenta lo suyo', () {
    test('Un reporte de OTRA orden no se cuenta como de esta', () async {
      // El defecto exacto: el técnico abre la OT 200 sin haber escrito nada,
      // y la pantalla le decía «1 reporte escrito acá todavía no subió».
      await reporte('r1', 'ot-100', 'pendiente');

      expect(await pendientesDe('ot-200'), 0,
          reason: 'en esta orden no se escribió nada');
      expect(await pendientesDe('ot-100'), 1);
      expect(await pendientesDe(null), 1,
          reason: 'la cola general sí lo tiene, y es correcto');
    });

    test('Dos órdenes con reportes: cada una ve los suyos, la cola ve los dos',
        () async {
      await reporte('r1', 'ot-100', 'pendiente');
      await reporte('r2', 'ot-200', 'pendiente');
      await reporte('r3', 'ot-200', 'pendiente');

      expect(await pendientesDe('ot-100'), 1);
      expect(await pendientesDe('ot-200'), 2);
      expect(await pendientesDe(null), 3);
    });

    test('Lo ya sincronizado no cuenta en ninguna de las dos', () async {
      await reporte('r1', 'ot-100', 'sincronizado');

      expect(await pendientesDe('ot-100'), 0);
      expect(await pendientesDe(null), 0);
    });
  });

  group('Y el código real sigue haciendo estas dos consultas', () {
    // POR QUE ESTE GRUPO EXISTE. Las pruebas de arriba replican el SQL sobre
    // una base en memoria: afirman que la LOGICA es correcta, no que
    // `local_database.dart` siga teniéndola. Si alguien le saca el filtro por
    // orden, las de arriba quedan verdes con el defecto vivo — que es
    // exactamente el patrón que este repositorio llama «una prueba que dice
    // que algo existe no prueba que funcione», en su forma inversa.
    final String fuente =
        File('lib/core/storage/local_database.dart').readAsStringSync();

    test('La cuenta de seguimiento sigue aceptando un orden_id', () {
      // ACOTADO A SU FUNCION, y aprendido de la primera versión de esta misma
      // prueba: buscaba «AND orden_id = ?» en todo el archivo y quedó verde
      // con el filtro quitado, porque otras consultas del archivo lo usan.
      // Una guarda que mira el lugar equivocado no es una guarda a medias: es
      // ninguna, y encima tranquiliza.
      final int inicio =
          fuente.indexOf('Future<int> contarSeguimientosPendientes');
      expect(inicio, greaterThan(-1),
          reason: 'contarSeguimientosPendientes se renombró');
      final String cuerpo = fuente.substring(inicio, inicio + 900);

      expect(cuerpo, contains('cola_seguimiento'),
          reason: 'la función dejó de leer esta tabla');
      expect(cuerpo, contains('orden_id'),
          reason: 'sin este filtro, «Esta OT: n» cuenta la cola de todas');
    });

    test('El resumen general sigue contando la cola de seguimiento', () {
      final int inicio = fuente.indexOf('Future<Map<String, int>> getSyncCounts');
      expect(inicio, greaterThan(-1), reason: 'getSyncCounts se renombró');
      final String cuerpo = fuente.substring(inicio, inicio + 3000);

      expect(cuerpo, contains('cola_seguimiento'),
          reason: 'una cola que se sube y no se cuenta hace que el '
              'encabezado diga «Sincronizado» con reportes esperando');
      expect(cuerpo, contains('seguimientos_pendientes'));
    });
  });

  group('Y la pastilla del encabezado deja de decir «Sincronizado»', () {
    // ESTE ES EL CASO QUE SE VE EN LA PANTALLA, y el que de verdad cerraba
    // el defecto: `SyncSummary.totalPendientes` recalculaba el total por su
    // cuenta e ignoraba la cola de seguimiento, asi que arreglar
    // `getSyncCounts` solo no alcanzaba.
    SyncSummary conSeguimientos(int n) => SyncSummary(
          status: SyncStatus.idle,
          isSyncing: false,
          hasConnectionError: false,
          mutacionesPendientes: 0,
          mutacionesConflicto: 0,
          evidenciasPendientes: 0,
          seguimientosPendientes: n,
          datosDirty: 0,
        );

    test('Con reportes esperando, NO dice sincronizado', () {
      final SyncSummary r = conSeguimientos(2);

      expect(r.totalPendientes, 2,
          reason: 'la cola de seguimiento tiene que entrar en el total');
      expect(r.isClean, isFalse);
      expect(SyncPresentacion.estado(r), DexterSyncStatus.pendiente,
          reason: 'decía «Sincronizado» con reportes adentro de la orden');
      expect(SyncPresentacion.detalle(r), '2 en cola',
          reason: 'y el detalle dice de QUE cola habla, para no confundirse '
              'con el «Esta OT: n» del bloque de la orden');
    });

    test('Sin nada esperando, sí dice sincronizado', () {
      final SyncSummary r = conSeguimientos(0);

      expect(r.totalPendientes, 0);
      expect(SyncPresentacion.estado(r), DexterSyncStatus.sincronizado);
    });

    test('El botón de sincronizar ahora se ofrece por esta cola también', () {
      // Antes no: `puedeSincronizarAhora` mira `totalPendientes`, que no la
      // contaba. Un técnico con reportes esperando no tenía cómo empujarlos.
      expect(SyncPresentacion.puedeSincronizarAhora(conSeguimientos(1)), isTrue);
      expect(SyncPresentacion.puedeSincronizarAhora(conSeguimientos(0)), isFalse);
    });
  });

  group('La contradicción que era posible', () {
    test('La cola general NUNCA puede ser menor que la de una sola orden',
        () async {
      // Esta es la invariante que faltaba. Mientras `cola_seguimiento` no
      // entraba en el total general, la general podía dar 0 con una orden
      // dando 2 — y el técnico veía «Sincronizado» arriba y «2 sin enviar»
      // adentro, sin forma de saber cuál creer.
      await reporte('r1', 'ot-100', 'pendiente');
      await reporte('r2', 'ot-100', 'pendiente');

      final int general = await pendientesDe(null);
      final int deLaOrden = await pendientesDe('ot-100');

      expect(general, greaterThanOrEqualTo(deLaOrden));
      expect(general, 2);
      expect(deLaOrden, 2);
    });
  });
}
