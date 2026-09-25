import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:campo/core/storage/local_database.dart';

void main() {
  // Inicializar FFI para SQLite en entorno de prueba
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  const orgA = 'org_rapilink_alpha';
  const profileA = 'prof_carlos_tecnico';
  const ordenA = 'orden_ftth_alpha_001';

  const orgB = 'org_conexiones_beta';
  const profileB = 'prof_pedro_tecnico';
  const ordenB = 'orden_ftth_beta_002';

  late LocalDatabase localDb;

  setUp(() async {
    localDb = LocalDatabase();
    final db = await localDb.database;
    await db.delete('local_ordenes');
    await db.delete('local_datos_dirty');
    await db.delete('cola_mutaciones');
    await db.delete('cola_evidencias');
  });

  group('Aislamiento Estricto Multi-Tenant / Multi-Profile en SQLite Local', () {
    test('Org/Profile B no puede ver ni sincronizar datos de Org/Profile A, y volver a A recupera todo intacto', () async {
      // -------------------------------------------------------------
      // 1. CONTEXTO A: Guardar orden, datos técnicos dirty, evidencia y mutación
      // -------------------------------------------------------------
      final ordenDataA = {
        'id': ordenA,
        'numero': 1842,
        'estado': 'en_sitio',
        'cliente': {
          'nombre': 'María Fernández',
          'direccion': 'Cra. 48 # 12-30, Apto 402',
          'telefono': '+57 300 999 8877',
        },
        'tipo_trabajo_nombre': 'Instalación Fibra Óptica (FTTH)',
        'tipo_trabajo_codigo': 'ftth_instalacion',
        'schema_version': 1,
        'tipo_trabajo_version': {
          'formulario': {
            'campos': [
              {'clave': 'serial_ont', 'etiqueta': 'Número de Serie ONT', 'tipo': 'texto', 'obligatorio': true},
              {'clave': 'potencia_rx', 'etiqueta': 'Potencia Óptica RX', 'tipo': 'numero', 'obligatorio': true},
            ],
            'evidencias': [
              {'id': 'foto_ont', 'descripcion': 'Fotografía ONT Instalada', 'obligatorio': true},
            ]
          }
        },
        'revision': 4,
        'diagnostico_previo_ia': 'Cliente nuevo en caja NAP-1042',
        'datos': {'serial_ont': 'ZTEG98765432'},
      };

      await localDb.upsertOrden(
        orgId: orgA,
        profileId: profileA,
        ordenData: ordenDataA,
      );

      // Guardar dirty data local (potencia_rx)
      await localDb.saveDatoCampo(
        orgId: orgA,
        profileId: profileA,
        ordenId: ordenA,
        campoClave: 'potencia_rx',
        valor: -19.5,
      );

      // Encolar evidencia local (foto)
      const evIdA = 'ev-foto-alpha-001';
      await localDb.encolarEvidencia(
        id: evIdA,
        orgId: orgA,
        profileId: profileA,
        ordenId: ordenA,
        requisitoId: 'foto_ont',
        archivoPath: '/data/user/0/com.dexter.campo/app_flutter/foto_ont.jpg',
        sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        tamanoBytes: 524288,
        mimeType: 'image/jpeg',
      );

      // Encolar mutación de estado
      const mutIdA = 'mut-alpha-transicion-001';
      await localDb.transicionarEstadoLocal(
        orgId: orgA,
        profileId: profileA,
        ordenId: ordenA,
        nuevoEstadoLocal: 'en_sitio',
        tipoAccion: 'iniciar',
        revisionBase: 4,
        idempotencyKey: mutIdA,
      );

      // -------------------------------------------------------------
      // 2. CAMBIO DE CONTEXTO A B (Org B / Profile B)
      // -------------------------------------------------------------
      // B consulta órdenes: debe estar VACÍO
      final ordenesB = await localDb.getOrdenes(orgId: orgB, profileId: profileB);
      expect(ordenesB, isEmpty, reason: 'Profile B no debe ver órdenes de Org A / Profile A');

      // B intenta consultar la orden específica de A: debe ser null
      final ordenEspecificaB = await localDb.getOrden(orgId: orgB, profileId: profileB, id: ordenA);
      expect(ordenEspecificaB, isNull, reason: 'Profile B no debe acceder a la orden de A por ID');

      // B consulta datos técnicos sucios de la orden de A: debe ser vacío
      final dirtyDatosB = await localDb.getDirtyDatosForSync(orgId: orgB, profileId: profileB, ordenId: ordenA);
      expect(dirtyDatosB, isEmpty, reason: 'Profile B no debe ver los valores técnicos dirty de A');

      final mergedDatosB = await localDb.getMergedDatosOrden(orgId: orgB, profileId: profileB, ordenId: ordenA);
      expect(mergedDatosB, isEmpty, reason: 'Profile B no debe ver los valores combinados de A');

      // B consulta cola de mutaciones para sincronizar: debe estar vacía
      final mutacionesB = await localDb.getMutacionesPendientes(orgId: orgB, profileId: profileB);
      expect(mutacionesB.where((m) => m['id'] == mutIdA), isEmpty,
          reason: 'El worker de sincronización de B jamás debe enviar mutaciones de A');

      // B consulta cola de evidencias para subir fotos: debe estar vacía
      final evidenciasB = await localDb.getEvidenciasPendientes(orgId: orgB, profileId: profileB);
      expect(evidenciasB.where((e) => e['id'] == evIdA), isEmpty,
          reason: 'El worker de sincronización de B jamás debe subir fotos de A');

      // Si B crea su propia orden, mutación o foto...
      final ordenDataB = {
        'id': ordenB,
        'numero': 2001,
        'estado': 'asignada',
        'cliente': {'nombre': 'Carlos Ruiz', 'direccion': 'Av. Central # 4', 'telefono': '3000000000'},
        'tipo_trabajo_nombre': 'Reparación Cobre',
        'schema_version': 1,
        'revision': 1,
      };
      await localDb.upsertOrden(orgId: orgB, profileId: profileB, ordenData: ordenDataB);

      // -------------------------------------------------------------
      // 3. RETORNO AL CONTEXTO A (Org A / Profile A)
      // -------------------------------------------------------------
      // A debe recuperar exactamente su orden intacta
      final ordenesA = await localDb.getOrdenes(orgId: orgA, profileId: profileA);
      expect(ordenesA.length, 1);
      expect(ordenesA.first['id'], ordenA);
      expect(ordenesA.first['cliente_nombre'], 'María Fernández');
      expect(ordenesA.first['estado'], 'en_sitio');

      // A debe conservar sus datos dirty locales intactos
      final dirtyDatosA = await localDb.getDirtyDatosForSync(orgId: orgA, profileId: profileA, ordenId: ordenA);
      expect(dirtyDatosA['potencia_rx'], -19.5);

      final mergedDatosA = await localDb.getMergedDatosOrden(orgId: orgA, profileId: profileA, ordenId: ordenA);
      expect(mergedDatosA['potencia_rx'], -19.5);
      expect(mergedDatosA['serial_ont'], 'ZTEG98765432');

      // A debe conservar sus mutaciones pendientes listas para sync
      final mutacionesA = await localDb.getMutacionesPendientes(orgId: orgA, profileId: profileA);
      expect(mutacionesA.any((m) => m['id'] == mutIdA), isTrue);

      // A debe conservar sus fotos/evidencias en cola listas para subida
      final evidenciasA = await localDb.getEvidenciasPendientes(orgId: orgA, profileId: profileA);
      expect(evidenciasA.any((e) => e['id'] == evIdA), isTrue);
      final evGuardada = evidenciasA.firstWhere((e) => e['id'] == evIdA);
      expect(evGuardada['requisito_id'], 'foto_ont');
      expect(evGuardada['subida_estado'], 'pendiente_registro');
    });
  });
}
