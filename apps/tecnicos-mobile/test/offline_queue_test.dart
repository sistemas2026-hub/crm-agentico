import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:campo/core/storage/local_database.dart';

void main() {
  // Inicializar FFI para pruebas de base de datos SQLite en máquina local
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  const testOrgId = 'org_test_123';
  const testProfileId = 'prof_carlos_456';
  const testOrdenId = 'ord_ftth_789';

  late LocalDatabase localDb;

  setUp(() async {
    localDb = LocalDatabase();
    final db = await localDb.database;
    await db.delete('local_ordenes');
    await db.delete('local_datos_dirty');
    await db.delete('cola_mutaciones');
    await db.delete('cola_evidencias');
  });

  group('Pruebas Ácidas de Persistencia Offline SQLite Multi-Tenant', () {
    test('1. Upsert y lectura aislada por (org_id, profile_id)', () async {
      final ordenData = {
        'id': testOrdenId,
        'numero': 1842,
        'estado': 'asignada',
        'cliente': {
          'nombre': 'María Fernández',
          'direccion': 'Calle 45 # 12-34',
          'telefono': '3001234567',
        },
        'tipo_trabajo_nombre': 'Instalación FTTH',
        'tipo_trabajo_codigo': 'INST_FTTH',
        'schema_version': 1,
        'tipo_trabajo_version': {
          'formulario': {
            'campos': [
              {'clave': 'serial_ont', 'etiqueta': 'Serial ONT', 'tipo': 'texto', 'obligatorio': true},
              {'clave': 'potencia_rx', 'etiqueta': 'Potencia RX', 'tipo': 'numero', 'obligatorio': true},
            ],
            'evidencias': [
              {'id': 'foto_potencia', 'descripcion': 'Foto de la potencia', 'obligatorio': true},
            ]
          }
        },
        'revision': 3,
        'diagnostico_previo_ia': 'Ruta óptima validada',
        'datos': {'serial_ont': 'BASE4857'},
      };

      await localDb.upsertOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenData: ordenData,
      );

      // Verificación en el tenant correcto
      final orden = await localDb.getOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        id: testOrdenId,
      );

      expect(orden, isNotNull);
      expect(orden!['numero'], 1842);
      expect(orden['cliente_nombre'], 'María Fernández');
      expect(orden['revision'], 3);

      // Aislamiento: otro tenant/usuario no debe ver la orden
      final ordenOtro = await localDb.getOrden(
        orgId: 'otra_org',
        profileId: 'otro_perfil',
        id: testOrdenId,
      );
      expect(ordenOtro, isNull);
    });

    test('2. Persistencia atómica por tecla y coalescing de datos dirty', () async {
      // Simulación de digitación del técnico por tecla
      await localDb.saveDatoCampo(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        campoClave: 'serial_ont',
        valor: '48575443ABC1',
      );

      await localDb.saveDatoCampo(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        campoClave: 'potencia_rx',
        valor: -19.45,
      );

      // Los datos dirty deben retornar los valores exactos
      final dirty = await localDb.getDirtyDatosForSync(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );

      expect(dirty['serial_ont'], '48575443ABC1');
      expect(dirty['potencia_rx'], -19.45);

      // Los datos mezclados para la UI deben incluir tanto la base como los dirty
      final merged = await localDb.getMergedDatosOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );
      expect(merged['serial_ont'], '48575443ABC1');
      expect(merged['potencia_rx'], -19.45);

      // Limpieza de dirty tras sync exitoso
      await localDb.clearDirtyDatos(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        claves: ['serial_ont', 'potencia_rx'],
      );

      final dirtyDespues = await localDb.getDirtyDatosForSync(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );
      expect(dirtyDespues.isEmpty, isTrue);
    });

    test('3. Transición atómica local y encolado de mutación con Idempotency-Key', () async {
      await localDb.upsertOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenData: {
          'id': testOrdenId,
          'numero': 1842,
          'estado': 'asignada',
          'cliente': {'nombre': 'María Fernández', 'direccion': 'Calle 45', 'telefono': '3001234567'},
          'tipo_trabajo_nombre': 'Instalación FTTH',
          'tipo_trabajo_codigo': 'INST_FTTH',
          'schema_version': 1,
          'revision': 3,
        },
      );

      const idempotencyKey = 'test-idemp-uuid-123';

      await localDb.transicionarEstadoLocal(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        nuevoEstadoLocal: 'en_sitio',
        tipoAccion: 'iniciar',
        revisionBase: 3,
        idempotencyKey: idempotencyKey,
      );

      // 1. Estado local de la orden actualizado inmediatamente
      final orden = await localDb.getOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        id: testOrdenId,
      );
      expect(orden!['estado'], 'en_sitio');

      // 2. Mutación encolada en SQLite
      final mutaciones = await localDb.getMutacionesPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(mutaciones.length, greaterThanOrEqualTo(1));
      final mutacion = mutaciones.firstWhere((m) => m['id'] == idempotencyKey);
      expect(mutacion['tipo'], 'iniciar');
      expect(mutacion['revision_base'], 3);
      expect(mutacion['estado'], 'pendiente');
    });

    test('4. Cola de evidencias offline y estados de subida en 3 pasos', () async {
      const evId = 'ev-foto-001';
      await localDb.encolarEvidencia(
        id: evId,
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
        requisitoId: 'foto_potencia',
        archivoPath: '/storage/emulated/0/DCIM/foto.jpg',
        sha256: 'a1b2c3d4e5f6',
        tamanoBytes: 102450,
        mimeType: 'image/jpeg',
      );

      final pendientes = await localDb.getEvidenciasPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientes.any((e) => e['id'] == evId), isTrue);

      // Avance a url_obtenida con descriptor oficial
      await localDb.updateEvidenciaEstado(
        id: evId,
        subidaEstado: 'url_obtenida',
        signedUploadUrl: 'https://s3.amazonaws.com/test-bucket/signed-url',
        uploadMethod: 'PUT',
        uploadHeadersJson: '{"x-amz-server-side-encryption":"AES256"}',
        uploadRequiereAuth: false,
        backendEvidenciaId: 'backend-ev-999',
      );

      final dbCheck = await localDb.getEvidenciasOrden(
        orgId: testOrgId,
        profileId: testProfileId,
        ordenId: testOrdenId,
      );
      final evCheck = dbCheck.firstWhere((e) => e['id'] == evId);
      expect(evCheck['upload_method'], 'PUT');
      expect(evCheck['upload_requiere_auth'], 0);
      expect(evCheck['upload_headers_json'], contains('x-amz-server-side-encryption'));

      // Avance a confirmada
      await localDb.updateEvidenciaEstado(
        id: evId,
        subidaEstado: 'confirmada',
      );

      final pendientesFin = await localDb.getEvidenciasPendientes(
        orgId: testOrgId,
        profileId: testProfileId,
      );
      expect(pendientesFin.any((e) => e['id'] == evId), isFalse);
    });
  });
}
