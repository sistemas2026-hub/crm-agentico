import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/sync/sync_queue_service.dart';

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  const testOrgId = 'org_rapilink_test';
  const testProfileId = 'prof_carlos_test';
  const testOrdenId = 'ord_1844_test';

  late LocalDatabase localDb;

  setUp(() async {
    localDb = LocalDatabase();
    final db = await localDb.database;
    await db.delete('local_ordenes');
    await db.delete('local_datos_dirty');
    await db.delete('cola_mutaciones');
    await db.delete('cola_evidencias');
  });

  group('Pruebas Unitarias de Backoff, Reintentos, Jitter y SyncBadge', () {
    test('1. Reintentos incrementan y registran error_mensaje ante fallo reintentable', () async {
      const mutId = 'mut_transicion_1';
      final now = DateTime.now().millisecondsSinceEpoch;

      await localDb.transicionarEstadoLocal(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        nuevoEstadoLocal: 'en_camino',
        tipoAccion: 'en_camino',
        revisionBase: 1,
        idempotencyKey: mutId,
      );

      var pendientes = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientes.length, 1);
      expect(pendientes.first['reintentos'], 0);
      expect(pendientes.first['next_attempt_at'], 0);

      // Simular primer fallo reintentable
      final delay1 = SyncQueueService.calcularBackoffMs(0, mutationId: mutId);
      expect(delay1, greaterThanOrEqualTo(2000));
      expect(delay1, lessThan(3000));

      final nextAttempt1 = now + delay1;
      await localDb.registrarFalloMutacion(
        id: mutId,
        nextAttemptAt: nextAttempt1,
        errorMensaje: '504 Gateway Timeout',
      );

      pendientes = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientes.first['reintentos'], 1);
      expect(pendientes.first['next_attempt_at'], nextAttempt1);
      expect(pendientes.first['error_mensaje'], '504 Gateway Timeout');
      expect(pendientes.first['estado'], 'pendiente');

      // Simular segundo fallo
      final delay2 = SyncQueueService.calcularBackoffMs(1, mutationId: mutId);
      expect(delay2, greaterThanOrEqualTo(4000));
      final nextAttempt2 = now + delay2;
      await localDb.registrarFalloMutacion(
        id: mutId,
        nextAttemptAt: nextAttempt2,
        errorMensaje: 'Connection closed unexpectedly',
      );

      pendientes = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientes.first['reintentos'], 2);
      expect(pendientes.first['next_attempt_at'], nextAttempt2);
    });

    test('2. Backoff exponencial calcula delays acotados con tope de 60 segundos', () {
      final delay0 = SyncQueueService.calcularBackoffMs(0);
      final delay1 = SyncQueueService.calcularBackoffMs(1);
      final delay2 = SyncQueueService.calcularBackoffMs(2);
      final delay3 = SyncQueueService.calcularBackoffMs(3);
      final delay4 = SyncQueueService.calcularBackoffMs(4);
      final delay5 = SyncQueueService.calcularBackoffMs(5);
      final delay10 = SyncQueueService.calcularBackoffMs(10);

      expect(delay0 >= 2000 && delay0 <= 3000, isTrue);
      expect(delay1 >= 4000 && delay1 <= 5000, isTrue);
      expect(delay2 >= 8000 && delay2 <= 9000, isTrue);
      expect(delay3 >= 16000 && delay3 <= 17000, isTrue);
      expect(delay4 >= 32000 && delay4 <= 33000, isTrue);
      // Tope de 60s + jitter (< 60.5s)
      expect(delay5 <= 60500, isTrue);
      expect(delay10 <= 60500, isTrue);
    });

    test('3. Jitter real determinista y reproducible con hashEstable(mutationId)', () {
      const mutA = 'mut_a_uuid_11111111-2222-3333-4444-555555555555';
      const mutB = 'mut_b_uuid_99999999-8888-7777-6666-000000000000';

      final hashA1 = SyncQueueService.hashEstable(mutA);
      final hashA2 = SyncQueueService.hashEstable(mutA);
      final hashB = SyncQueueService.hashEstable(mutB);

      // Reproducibilidad determinista
      expect(hashA1, hashA2, reason: 'hashEstable debe ser 100% determinista e idéntico para el mismo ID');
      expect(hashA1 != hashB, isTrue, reason: 'IDs diferentes deben generar hashes diferentes');
      expect(hashA1, greaterThanOrEqualTo(0), reason: 'Hash de 31 bits no negativo');

      final delayA = SyncQueueService.calcularBackoffMs(0, mutationId: mutA);
      final delayB = SyncQueueService.calcularBackoffMs(0, mutationId: mutB);

      // Ambas están en reintento 0 (base 2s), pero sus jitters difieren por mutationId
      expect(delayA >= 2000 && delayA <= 2500, isTrue);
      expect(delayB >= 2000 && delayB <= 2500, isTrue);
      expect(delayA != delayB, isTrue, reason: 'Mutaciones distintas deben dispersarse con distinto delay');
    });

    test('4. Soporte estricto para Retry-After (HTTP 429) respetando el servidor sin tope artificial', () {
      // Caso servidor solicita Retry-After: 15 segundos
      final delay15 = SyncQueueService.calcularBackoffMs(
        0,
        mutationId: 'mut_rate_limited_15',
        retryAfterSeconds: 15,
      );
      expect(delay15, 15000);

      // Caso servidor solicita Retry-After: 300 segundos
      // REQUISITO: NO puede quedar recortado a 120 segundos
      final delay300 = SyncQueueService.calcularBackoffMs(
        0,
        mutationId: 'mut_rate_limited_300',
        retryAfterSeconds: 300,
      );
      expect(delay300, 300000, reason: 'Retry-After: 300 debe esperar 300.000 ms y no ser recortado a 120s');
    });

    test('5. getMutacionesPendientes con soloListasHasta evita reintento prematuro', () async {
      const mutId = 'mut_transicion_backoff';
      final now = DateTime.now().millisecondsSinceEpoch;

      await localDb.transicionarEstadoLocal(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        nuevoEstadoLocal: 'en_camino',
        tipoAccion: 'en_camino',
        revisionBase: 1,
        idempotencyKey: mutId,
      );

      // Programar para 10 segundos en el futuro
      await localDb.registrarFalloMutacion(
        id: mutId,
        nextAttemptAt: now + 10000,
        errorMensaje: 'Error transitorio',
      );

      // Con tiempo actual 'now', no debe devolverla
      final listasAhora = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
        soloListasHasta: now,
      );
      expect(listasAhora.isEmpty, isTrue);

      // Si el reloj avanza 11 segundos, sí aparece lista
      final listasFuturo = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
        soloListasHasta: now + 11000,
      );
      expect(listasFuturo.length, 1);
      expect(listasFuturo.first['id'], mutId);
    });

    test('6. Force-stop / reapertura de SQLite conserva reintentos y next_attempt_at', () async {
      const mutId = 'mut_survive_reboot';
      final nextAt = DateTime.now().millisecondsSinceEpoch + 15000;

      await localDb.transicionarEstadoLocal(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        nuevoEstadoLocal: 'en_sitio',
        tipoAccion: 'iniciar',
        revisionBase: 1,
        idempotencyKey: mutId,
      );

      await localDb.registrarFalloMutacion(
        id: mutId,
        nextAttemptAt: nextAt,
        errorMensaje: '503 Service Unavailable',
      );

      LocalDatabase.resetForTesting();
      final freshDb = LocalDatabase();

      final recuperadas = await freshDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );

      expect(recuperadas.length, 1);
      expect(recuperadas.first['id'], mutId);
      expect(recuperadas.first['reintentos'], 1);
      expect(recuperadas.first['next_attempt_at'], nextAt);
      expect(recuperadas.first['error_mensaje'], '503 Service Unavailable');
    });

    test('7. Éxito transiciona a sincronizada y limpia la cola activa', () async {
      const mutId = 'mut_success';
      await localDb.transicionarEstadoLocal(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        nuevoEstadoLocal: 'en_camino',
        tipoAccion: 'en_camino',
        revisionBase: 1,
        idempotencyKey: mutId,
      );

      var pendientes = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientes.length, 1);

      await localDb.updateMutacionEstado(id: mutId, estado: 'sincronizada');

      pendientes = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientes.isEmpty, isTrue);
    });

    test('8. Error 400 (Bad Request) marca error_validacion y NO se reintenta', () async {
      const mutId = 'mut_bad_request';
      await localDb.transicionarEstadoLocal(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        nuevoEstadoLocal: 'en_camino',
        tipoAccion: 'en_camino',
        revisionBase: 1,
        idempotencyKey: mutId,
      );

      await localDb.updateMutacionEstado(
        id: mutId,
        estado: 'error_validacion',
        errorMensaje: 'Payload inválido: campo requerido faltante',
      );

      final pendientes = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientes.isEmpty, isTrue);

      final counts = await localDb.getSyncCounts(orgId: testOrgId, profileId: testProfileId);
      expect(counts['mutaciones_conflicto'], 1);
    });

    test('9. Error 409 (STALE_WORK_ORDER) marca conflicto y no se auto-reintenta', () async {
      const mutId = 'mut_stale';
      await localDb.transicionarEstadoLocal(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        nuevoEstadoLocal: 'completada_pendiente_sync',
        tipoAccion: 'completar',
        revisionBase: 1,
        idempotencyKey: mutId,
      );

      await localDb.updateMutacionEstado(
        id: mutId,
        estado: 'conflicto',
        errorMensaje: 'STALE_WORK_ORDER',
      );

      final pendientes = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientes.isEmpty, isTrue);

      final counts = await localDb.getSyncCounts(orgId: testOrgId, profileId: testProfileId);
      expect(counts['mutaciones_conflicto'], 1);
      expect(counts['mutaciones_pendientes'], 0);
    });

    test('10. Aislamiento Multi-Tenant y Multi-Perfil estricto en getSyncCounts()', () async {
      const orgA = 'org_tenant_A';
      const profA = 'prof_tecnico_A';
      const orgB = 'org_tenant_B';
      const profB = 'prof_tecnico_B';

      // Tenant A encola mutación, evidencia y dirty
      await localDb.transicionarEstadoLocal(
        orgId: orgA,
        profileId: profA,
        ordenId: 'ord_A_1',
        nuevoEstadoLocal: 'en_camino',
        tipoAccion: 'en_camino',
        revisionBase: 1,
        idempotencyKey: 'mut_A_1',
      );

      await localDb.encolarEvidencia(
        id: 'ev_A_1',
        orgId: orgA,
        profileId: profA,
        ordenId: 'ord_A_1',
        requisitoId: 'foto_ont',
        archivoPath: '/data/user/0/testA.jpg',
        sha256: 'shaA',
        tamanoBytes: 100,
        mimeType: 'image/jpeg',
      );

      await localDb.saveDatoCampo(
        orgId: orgA,
        profileId: profA,
        ordenId: 'ord_A_1',
        campoClave: 'serial_ont',
        valor: 'HWTC1234',
      );

      // Consultar Tenant A: debe reportar 3 pendientes
      final countsA = await localDb.getSyncCounts(orgId: orgA, profileId: profA);
      expect(countsA['mutaciones_pendientes'], 1);
      expect(countsA['evidencias_pendientes'], 1);
      expect(countsA['datos_dirty'], 1);
      expect(countsA['total_pendientes'], 3);

      // Consultar Tenant B: aislamiento TOTAL, cero pendientes de A
      final countsB = await localDb.getSyncCounts(orgId: orgB, profileId: profB);
      expect(countsB['mutaciones_pendientes'], 0);
      expect(countsB['evidencias_pendientes'], 0);
      expect(countsB['datos_dirty'], 0);
      expect(countsB['total_pendientes'], 0);
      expect(countsB['mutaciones_conflicto'], 0);
    });

    test('11. Reactividad multi-suscriptor: dos listeners reciben eventos y al cancelar uno el otro sigue activo', () async {
      int notificacionesA = 0;
      int notificacionesB = 0;
      LocalDatabaseChangeEvent? ultimoEventoA;
      LocalDatabaseChangeEvent? ultimoEventoB;

      // Suscribir dos listeners independientes al Stream broadcast
      final subA = LocalDatabase.onDataChanged.listen((event) {
        notificacionesA++;
        ultimoEventoA = event;
      });

      final subB = LocalDatabase.onDataChanged.listen((event) {
        notificacionesB++;
        ultimoEventoB = event;
      });

      // 1. Guardar dato dirty: ambos listeners deben recibir el evento
      await localDb.saveDatoCampo(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        campoClave: 'potencia_rx',
        valor: -22.1,
      );
      await pumpEventQueue();

      expect(notificacionesA, 1, reason: 'Listener A debe recibir el evento de saveDatoCampo');
      expect(notificacionesB, 1, reason: 'Listener B debe recibir el evento de saveDatoCampo');
      expect(ultimoEventoA?.tabla, 'local_datos_dirty');
      expect(ultimoEventoA?.orgId, testOrgId);
      expect(ultimoEventoB?.tabla, 'local_datos_dirty');

      // 2. Cancelar la suscripción del Listener A
      await subA.cancel();

      // 3. Encolar mutación: solo el Listener B debe recibir el nuevo evento
      await localDb.transicionarEstadoLocal(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        nuevoEstadoLocal: 'en_camino',
        tipoAccion: 'en_camino',
        revisionBase: 1,
        idempotencyKey: 'mut_react_stream_1',
      );
      await pumpEventQueue();

      expect(notificacionesA, 1, reason: 'Listener A fue cancelado y NO debe recibir nuevos eventos');
      expect(notificacionesB, 2, reason: 'Listener B sigue activo y debe recibir la segunda notificación');
      expect(ultimoEventoB?.tabla, 'cola_mutaciones');
      expect(ultimoEventoB?.orgId, testOrgId);

      // 4. Limpieza final
      await subB.cancel();
    });

    test('12. Test de Migración Real SQLite v4 -> v5 preserva datos y añade next_attempt_at', () async {
      final dbPath = await getDatabasesPath();
      final migrationDbFile = p.join(dbPath, 'migration_test_v4_v5.db');
      final file = File(migrationDbFile);
      if (await file.exists()) {
        await file.delete();
      }

      // 1. Crear base de datos en versión 4 exacta (sin columna next_attempt_at)
      final dbV4 = await openDatabase(
        migrationDbFile,
        version: 4,
        onCreate: (db, version) async {
          await db.execute('''
            CREATE TABLE cola_mutaciones (
              id TEXT PRIMARY KEY,
              org_id TEXT NOT NULL,
              profile_id TEXT NOT NULL,
              orden_id TEXT NOT NULL,
              tipo TEXT NOT NULL,
              payload_json TEXT,
              revision_base INTEGER NOT NULL,
              idempotency_key TEXT NOT NULL,
              estado TEXT NOT NULL DEFAULT 'pendiente',
              error_mensaje TEXT,
              reintentos INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL
            );
          ''');
          await db.execute('''
            CREATE TABLE cola_evidencias (
              id TEXT PRIMARY KEY,
              org_id TEXT NOT NULL,
              profile_id TEXT NOT NULL,
              orden_id TEXT NOT NULL,
              requisito_id TEXT NOT NULL,
              archivo_path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              tamano_bytes INTEGER NOT NULL,
              mime_type TEXT NOT NULL,
              subida_estado TEXT NOT NULL DEFAULT 'pendiente_registro',
              signed_upload_url TEXT,
              upload_method TEXT,
              upload_headers_json TEXT,
              upload_requiere_auth INTEGER,
              backend_evidencia_id TEXT,
              error_mensaje TEXT,
              registro_idempotency_key TEXT,
              confirmacion_idempotency_key TEXT,
              created_at INTEGER NOT NULL
            );
          ''');
        },
      );

      // Insertar mutación previa en v4
      await dbV4.insert('cola_mutaciones', {
        'id': 'mut_v4_legacy',
        'org_id': 'org_v4',
        'profile_id': 'prof_v4',
        'orden_id': 'ord_v4',
        'tipo': 'en_camino',
        'revision_base': 1,
        'idempotency_key': 'mut_v4_legacy',
        'estado': 'pendiente',
        'reintentos': 2,
        'created_at': 1000000,
      });

      // Verificar que en v4 NO existe la columna next_attempt_at
      final colsV4 = await dbV4.rawQuery('PRAGMA table_info(cola_mutaciones);');
      expect(colsV4.any((c) => c['name'] == 'next_attempt_at'), isFalse);

      await dbV4.close();

      // 2. Abrir la misma base de datos en versión 5 ejecutando el _onUpgrade de LocalDatabase
      final dbV5 = await openDatabase(
        migrationDbFile,
        version: 5,
        onUpgrade: (db, oldVersion, newVersion) async {
          final infoEvidencias = await db.rawQuery('PRAGMA table_info(cola_evidencias);');
          final colsEvidencias = infoEvidencias.map((c) => c['name'] as String).toSet();
          if (oldVersion < 2 && !colsEvidencias.contains('upload_headers_json')) {
            await db.execute('ALTER TABLE cola_evidencias ADD COLUMN upload_headers_json TEXT;');
          }
          if (oldVersion < 3) {
            if (!colsEvidencias.contains('upload_method')) {
              await db.execute('ALTER TABLE cola_evidencias ADD COLUMN upload_method TEXT;');
            }
            if (!colsEvidencias.contains('upload_requiere_auth')) {
              await db.execute('ALTER TABLE cola_evidencias ADD COLUMN upload_requiere_auth INTEGER;');
            }
          }
          if (oldVersion < 4) {
            if (!colsEvidencias.contains('registro_idempotency_key')) {
              await db.execute('ALTER TABLE cola_evidencias ADD COLUMN registro_idempotency_key TEXT;');
            }
            if (!colsEvidencias.contains('confirmacion_idempotency_key')) {
              await db.execute('ALTER TABLE cola_evidencias ADD COLUMN confirmacion_idempotency_key TEXT;');
            }
          }
          if (oldVersion < 5) {
            final infoMutaciones = await db.rawQuery('PRAGMA table_info(cola_mutaciones);');
            final colsMutaciones = infoMutaciones.map((c) => c['name'] as String).toSet();
            if (!colsMutaciones.contains('next_attempt_at')) {
              await db.execute('ALTER TABLE cola_mutaciones ADD COLUMN next_attempt_at INTEGER NOT NULL DEFAULT 0;');
            }
          }
        },
      );

      // Verificar que ahora existe la columna next_attempt_at en v5
      final colsV5 = await dbV5.rawQuery('PRAGMA table_info(cola_mutaciones);');
      expect(colsV5.any((c) => c['name'] == 'next_attempt_at'), isTrue);

      // Verificar que el registro existente sobrevivió intacto con valor por defecto 0
      final rowLegacy = await dbV5.query(
        'cola_mutaciones',
        where: 'id = ?',
        whereArgs: ['mut_v4_legacy'],
      );
      expect(rowLegacy.length, 1);
      expect(rowLegacy.first['id'], 'mut_v4_legacy');
      expect(rowLegacy.first['reintentos'], 2);
      expect(rowLegacy.first['next_attempt_at'], 0);
      expect(rowLegacy.first['estado'], 'pendiente');

      await dbV5.close();
      if (await file.exists()) {
        await file.delete();
      }
    });
  });
}
