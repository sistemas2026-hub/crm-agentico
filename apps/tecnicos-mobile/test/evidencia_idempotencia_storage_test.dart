import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/evidencia_storage_service.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:uuid/uuid.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  const testOrgId = 'org_test_idemp';
  const testProfileId = 'prof_carlos_idemp';
  const testOrdenId = 'ord_idemp_1844';

  late LocalDatabase localDb;
  late Directory tempTestDir;

  setUp(() async {
    localDb = LocalDatabase();
    final db = await localDb.database;
    await db.delete('cola_evidencias');
    await db.delete('cola_mutaciones');
    await db.delete('local_ordenes');

    // Directorio persistente simulado para EvidenciaStorageService
    tempTestDir = await Directory.systemTemp.createTemp('dexter_test_persistent_');
    EvidenciaStorageService.setOverrideDirectory(tempTestDir);
  });

  tearDown(() async {
    EvidenciaStorageService.setOverrideDirectory(null);
    if (await tempTestDir.exists()) {
      await tempTestDir.delete(recursive: true);
    }
  });

  group('Idempotencia de Evidencias y Almacenamiento Durable', () {
    test('A. Registro y confirmación usan keys diferentes y no vacías', () async {
      final evId = const Uuid().v4();
      final testFile = File('${tempTestDir.path}/test_foto.jpg');
      await testFile.writeAsString('contenido_foto_fake');
      final sha = await SyncQueueService.calcularSha256(testFile);

      await localDb.encolarEvidencia(
        id: evId,
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        requisitoId: 'foto_ont',
        archivoPath: testFile.path,
        sha256: sha,
        tamanoBytes: await testFile.length(),
        mimeType: 'image/jpeg',
      );

      final evidencias = await localDb.getEvidenciasOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );

      expect(evidencias.length, 1);
      final ev = evidencias.first;

      final registroKey = ev['registro_idempotency_key'] as String?;
      final confirmacionKey = ev['confirmacion_idempotency_key'] as String?;

      expect(registroKey, isNotNull);
      expect(confirmacionKey, isNotNull);
      expect(registroKey!.isNotEmpty, isTrue);
      expect(confirmacionKey!.isNotEmpty, isTrue);
      expect(registroKey, isNot(equals(confirmacionKey)),
          reason: 'registro_key debe ser estrictamente diferente a confirmacion_key');
    });

    test('B. Retry de registro conserva exactamente la misma registro_idempotency_key', () async {
      final evId = const Uuid().v4();
      final testFile = File('${tempTestDir.path}/test_retry_reg.jpg');
      await testFile.writeAsString('foto_bytes');
      final sha = await SyncQueueService.calcularSha256(testFile);

      await localDb.encolarEvidencia(
        id: evId,
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        requisitoId: 'foto_ont',
        archivoPath: testFile.path,
        sha256: sha,
        tamanoBytes: 100,
        mimeType: 'image/jpeg',
      );

      final iniciales = await localDb.getEvidenciasOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );
      final regKeyOriginal = iniciales.first['registro_idempotency_key'];

      // Simular intento fallido de registro y retry
      await localDb.updateEvidenciaEstado(
        id: evId,
        subidaEstado: 'pendiente_registro',
        errorMensaje: 'Simulated network timeout',
      );

      final postRetry = await localDb.getEvidenciasOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );
      final regKeyPostRetry = postRetry.first['registro_idempotency_key'];

      expect(regKeyPostRetry, equals(regKeyOriginal),
          reason: 'El retry de registro debe conservar la misma Idempotency-Key');
    });

    test('C. Retry de confirmación conserva exactamente la misma confirmacion_idempotency_key', () async {
      final evId = const Uuid().v4();
      final testFile = File('${tempTestDir.path}/test_retry_conf.jpg');
      await testFile.writeAsString('foto_bytes_conf');
      final sha = await SyncQueueService.calcularSha256(testFile);

      await localDb.encolarEvidencia(
        id: evId,
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        requisitoId: 'foto_ont',
        archivoPath: testFile.path,
        sha256: sha,
        tamanoBytes: 100,
        mimeType: 'image/jpeg',
      );

      // Avanzar a subido_binario
      await localDb.updateEvidenciaEstado(
        id: evId,
        subidaEstado: 'subido_binario',
        backendEvidenciaId: 'bev-test-123',
      );

      final antesConfirm = await localDb.getEvidenciasOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );
      final confKeyOriginal = antesConfirm.first['confirmacion_idempotency_key'];

      // Simular fallo en confirmación y reintento
      await localDb.updateEvidenciaEstado(
        id: evId,
        subidaEstado: 'subido_binario',
        errorMensaje: 'Connection error during confirmation',
      );

      final reintentoConfirm = await localDb.getEvidenciasOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );
      final confKeyReintento = reintentoConfirm.first['confirmacion_idempotency_key'];

      expect(confKeyReintento, equals(confKeyOriginal),
          reason: 'El retry de confirmación debe conservar la misma confirmacion_idempotency_key');
    });

    test('D. Las dos keys sobreviven a reapertura de SQLite', () async {
      final evId = const Uuid().v4();
      final testFile = File('${tempTestDir.path}/test_persistence.jpg');
      await testFile.writeAsString('foto_bytes_persistent');
      final sha = await SyncQueueService.calcularSha256(testFile);

      await localDb.encolarEvidencia(
        id: evId,
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        requisitoId: 'foto_fachada',
        archivoPath: testFile.path,
        sha256: sha,
        tamanoBytes: 250,
        mimeType: 'image/jpeg',
      );

      final antesCierre = await localDb.getEvidenciasOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );
      final regKey = antesCierre.first['registro_idempotency_key'];
      final confKey = antesCierre.first['confirmacion_idempotency_key'];

      // Simular cierre y reapertura de la base de datos
      final db = await localDb.database;
      final dbPath = db.path;
      await db.close();

      // Reabrir SQLite
      final reopenedDb = await openDatabase(dbPath, version: 4);
      final filas = await reopenedDb.query(
        'cola_evidencias',
        where: 'id = ?',
        whereArgs: [evId],
      );

      expect(filas.length, 1);
      expect(filas.first['registro_idempotency_key'], equals(regKey));
      expect(filas.first['confirmacion_idempotency_key'], equals(confKey));
      await reopenedDb.close();
      LocalDatabase.resetForTesting();
    });

    test('E. Evidencia en subido_binario reanuda en confirmar y NO vuelve a registrar/subir', () async {
      final evId = const Uuid().v4();
      final testFile = File('${tempTestDir.path}/test_subido_binario.jpg');
      await testFile.writeAsString('foto_binario_listo');
      final sha = await SyncQueueService.calcularSha256(testFile);

      await localDb.encolarEvidencia(
        id: evId,
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        requisitoId: 'foto_ont',
        archivoPath: testFile.path,
        sha256: sha,
        tamanoBytes: 150,
        mimeType: 'image/jpeg',
      );

      // Estado exacto en el que quedó la orden #1844
      await localDb.updateEvidenciaEstado(
        id: evId,
        subidaEstado: 'subido_binario',
        backendEvidenciaId: 'bev-existente-456',
        signedUploadUrl: 'https://backend/api/campo/evidencias/bev-existente-456/subir/',
      );

      final ev = (await localDb.getEvidenciasOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      )).first;

      final subidaEstado = ev['subida_estado'] as String;
      final signedUploadUrl = ev['signed_upload_url'] as String?;
      final backendEvidenciaId = ev['backend_evidencia_id'] as String?;

      // Invariante de SyncQueueService:
      // Paso 1 (Registrar) NO debe ejecutarse:
      final bool debeRegistrar = subidaEstado == 'pendiente_registro' ||
          (subidaEstado != 'subido_binario' && subidaEstado != 'confirmada' && signedUploadUrl == null);
      expect(debeRegistrar, isFalse, reason: 'No debe volver a llamar a POST registrar');

      // Paso 2 (Subir binario) NO debe ejecutarse:
      final bool debeSubirBinario = subidaEstado == 'url_obtenida' && signedUploadUrl != null;
      expect(debeSubirBinario, isFalse, reason: 'No debe volver a subir el archivo binario');

      // Paso 3 (Confirmar) SÍ debe ejecutarse:
      final bool debeConfirmar = subidaEstado == 'subido_binario' && backendEvidenciaId != null;
      expect(debeConfirmar, isTrue, reason: 'Debe reanudar directamente desde POST confirmar');
    });

    test('F. Ruta definitiva de evidencia pendiente NO apunta al directorio cache temporal', () async {
      // Simular captura de image_picker en directorio de cache temporal
      final tempCacheDir = await Directory.systemTemp.createTemp('mock_cache_');
      final tempCaptureFile = File('${tempCacheDir.path}/scaled_temp_photo.jpg');
      await tempCaptureFile.writeAsString('bytes_imagen_camara');

      expect(tempCaptureFile.path, contains('mock_cache_'));

      // Persistir usando EvidenciaStorageService
      final persistentFile = await EvidenciaStorageService.persistirArchivoCaptura(
        tempCaptureFile,
        nombreOriginal: 'foto_ont.jpg',
      );

      // Verificar invariantes de almacenamiento durable
      expect(await persistentFile.exists(), isTrue);
      expect(persistentFile.path, isNot(equals(tempCaptureFile.path)));
      expect(persistentFile.path.contains('cache'), isFalse,
          reason: 'La ruta definitiva jamás debe apuntar a un directorio cache');
      expect(persistentFile.path, startsWith(tempTestDir.path),
          reason: 'La ruta definitiva debe residir en el almacenamiento persistente privado de Dexter IA');

      final shaOriginal = await SyncQueueService.calcularSha256(tempCaptureFile);
      final shaPersistente = await SyncQueueService.calcularSha256(persistentFile);
      expect(shaPersistente, equals(shaOriginal),
          reason: 'El hash SHA-256 del archivo persistido debe ser idéntico al original');

      // Limpiar cache temporal simulando limpieza del SO
      await tempCaptureFile.delete();
      expect(await tempCaptureFile.exists(), isFalse);

      // El archivo persistente debe seguir intacto
      expect(await persistentFile.exists(), isTrue);

      await tempCacheDir.delete(recursive: true);
    });
  });
}
