import 'dart:convert';

import 'package:campo/core/storage/local_database.dart';
import 'package:campo/features/trabajo/estado_trabajo.dart';
import 'package:campo/features/trabajo/estado_validacion.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// La v5 tal como estaba antes de esta fase: sin las cinco columnas nuevas.
/// Se escribe a mano para poder abrir una base vieja de verdad y comprobar que
/// actualizar la aplicación no le cuesta el trabajo al técnico.
const String _tablaOrdenesV5 = '''
  CREATE TABLE local_ordenes (
    id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    numero INTEGER,
    estado TEXT NOT NULL,
    cliente_nombre TEXT NOT NULL,
    direccion TEXT NOT NULL,
    telefono TEXT,
    tipo_nombre TEXT NOT NULL,
    tipo_codigo TEXT NOT NULL,
    work_type_version_id TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    formulario_campos_json TEXT,
    formulario_evidencias_json TEXT,
    revision INTEGER NOT NULL DEFAULT 0,
    diagnostico_previo_ia TEXT,
    datos_json TEXT,
    fecha_compromiso TEXT,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (id, org_id, profile_id)
  )
''';

const String _tablaMutacionesV5 = '''
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
    next_attempt_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
  )
''';

const String _tablaDatosV5 = '''
  CREATE TABLE local_datos_dirty (
    orden_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    campo_clave TEXT NOT NULL,
    valor_json TEXT,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (orden_id, org_id, profile_id, campo_clave)
  )
''';

const String _tablaEvidenciasV5 = '''
  CREATE TABLE cola_evidencias (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    orden_id TEXT NOT NULL,
    requisito_id TEXT NOT NULL,
    archivo_path TEXT NOT NULL,
    hash_sha256 TEXT,
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
  )
''';

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  // Base propia. Esta suite BORRA el archivo de base para simular una
  // version anterior; contra el dexter_campo.db compartido, se llevaba
  // puesta a cualquier otra suite que estuviera corriendo en paralelo.
  LocalDatabase.usarBaseDePruebas('pruebas_migracion_v6.db');

  const orgId = 'org_rapilink';
  const profileId = 'prof_carlos';
  const ordenId = 'ot-4832';

  late String rutaBase;

  setUp(() async {
    rutaBase = join(await databaseFactory.getDatabasesPath(), 'pruebas_migracion_v6.db');
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(rutaBase);
  });

  tearDown(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(rutaBase);
  });

  /// Deja en disco una base v5 con una orden y una mutación pendiente, igual a
  /// la que tendría un técnico que trabajó sin señal y todavía no actualizó.
  Future<void> baseVieja() async {
    final db = await databaseFactory.openDatabase(
      rutaBase,
      options: OpenDatabaseOptions(version: 5),
    );
    await db.execute(_tablaOrdenesV5);
    await db.execute(_tablaDatosV5);
    await db.execute(_tablaMutacionesV5);
    await db.execute(_tablaEvidenciasV5);

    await db.insert('local_ordenes', <String, Object?>{
      'id': ordenId,
      'org_id': orgId,
      'profile_id': profileId,
      'numero': 4832,
      'estado': 'en_sitio',
      'cliente_nombre': 'Carlos Gomez',
      'direccion': 'Cra 45 #12-88',
      'telefono': '3001234567',
      'tipo_nombre': 'Instalación FTTH',
      'tipo_codigo': 'ftth_instalacion',
      'schema_version': 1,
      'formulario_campos_json': '[]',
      'formulario_evidencias_json': '[]',
      'revision': 7,
      'diagnostico_previo_ia': 'Cortes intermitentes',
      'datos_json': '{}',
      'fecha_compromiso': '2026-09-18T10:30:00Z',
      'updated_at': 1700000000000,
    });

    await db.insert('cola_mutaciones', <String, Object?>{
      'id': 'mut-1',
      'org_id': orgId,
      'profile_id': profileId,
      'orden_id': ordenId,
      'tipo': 'completar',
      'payload_json': jsonEncode(<String, Object?>{
        'valores': <String, Object?>{'potencia_rx': -18.7},
        'revision_base': 7,
      }),
      'revision_base': 7,
      'idempotency_key': 'clave-idempotente-1',
      'estado': 'pendiente',
      'reintentos': 2,
      'next_attempt_at': 1700000100000,
      'created_at': 1700000000000,
    });

    await db.close();
  }

  group('Migración v5 → v6', () {
    test('1. Una base nueva ya trae las cinco columnas', () async {
      final db = await LocalDatabase().database;
      final columnas = (await db.rawQuery('PRAGMA table_info(local_ordenes);'))
          .map((Map<String, Object?> c) => c['name'] as String)
          .toSet();

      for (final String col in <String>[
        'estado_validacion',
        'cliente_lat',
        'cliente_lng',
        'iniciada_en',
        'completada_campo_en',
      ]) {
        expect(columnas, contains(col), reason: col);
      }
      // La base sigue subiendo de versión; lo que importa acá es que la
      // migración v5 → v6 no perdió nada.
      expect(await db.getVersion(), greaterThanOrEqualTo(6));
    });

    test('2. Actualizar no le cuesta al técnico la orden que ya tenía', () async {
      await baseVieja();

      final db = await LocalDatabase().database;
      final ordenes = await db.query('local_ordenes');

      expect(ordenes, hasLength(1));
      final orden = ordenes.first;
      expect(orden['id'], ordenId);
      expect(orden['estado'], 'en_sitio', reason: 'la migracion no toca el estado');
      expect(orden['cliente_nombre'], 'Carlos Gomez');
      expect(orden['revision'], 7);
      expect(orden['diagnostico_previo_ia'], 'Cortes intermitentes');
      expect(orden['fecha_compromiso'], '2026-09-18T10:30:00Z');
      // Las columnas nuevas nacen vacías, no con un valor inventado.
      expect(orden['estado_validacion'], isNull);
      expect(orden['cliente_lat'], isNull);
    });

    test('3. Actualizar tampoco le cuesta el trabajo que no se envió', () async {
      await baseVieja();

      final db = await LocalDatabase().database;
      final mutaciones = await db.query('cola_mutaciones');

      expect(mutaciones, hasLength(1), reason: 'la cola offline sobrevive');
      final m = mutaciones.first;
      expect(m['id'], 'mut-1');
      expect(m['tipo'], 'completar');
      expect(m['estado'], 'pendiente');
      expect(m['idempotency_key'], 'clave-idempotente-1');
      expect(m['revision_base'], 7);
      expect(m['reintentos'], 2);
      expect(m['next_attempt_at'], 1700000100000);

      // El payload llega intacto: sin él, el trabajo hecho en campo se pierde.
      final payload = jsonDecode(m['payload_json']! as String) as Map<String, dynamic>;
      expect((payload['valores'] as Map<String, dynamic>)['potencia_rx'], -18.7);
    });

    test('4. La migración es idempotente: abrir dos veces no rompe nada', () async {
      await baseVieja();
      await LocalDatabase().database;
      LocalDatabase.resetForTesting();

      final db = await LocalDatabase().database;
      // La base sigue subiendo de versión; lo que importa acá es que la
      // migración v5 → v6 no perdió nada.
      expect(await db.getVersion(), greaterThanOrEqualTo(6));
      expect(await db.query('local_ordenes'), hasLength(1));
      expect(await db.query('cola_mutaciones'), hasLength(1));
    });
  });

  group('Los cinco datos, de la API al modelo', () {
    Map<String, dynamic> payloadDetalle({
      String estadoValidacion = 'pendiente',
      bool conCoordenadas = true,
      bool conCompletada = true,
    }) {
      return <String, dynamic>{
        'id': ordenId,
        'numero': 4832,
        'estado_operativo': 'completada_campo',
        'estado_validacion': estadoValidacion,
        'revision': 8,
        'cliente': <String, dynamic>{
          'nombre': 'Carlos Gomez',
          'direccion': 'Cra 45 #12-88',
          'telefono': '3001234567',
          if (conCoordenadas) 'lat': 6.244203,
          if (conCoordenadas) 'lng': -75.581212,
        },
        'tipo': <String, dynamic>{
          'nombre': 'Instalación FTTH',
          'codigo': 'ftth_instalacion',
          'schema_version': 1,
        },
        'programada_para': '2026-09-18T10:30:00Z',
        'iniciada_en': '2026-09-18T11:02:00Z',
        if (conCompletada) 'completada_campo_en': '2026-09-18T12:40:00Z',
      };
    }

    test('5. Se guardan al insertar y se leen en el modelo', () async {
      final baseLocal = LocalDatabase();
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: payloadDetalle(),
      );

      final filas = await baseLocal.getOrdenes(orgId: orgId, profileId: profileId);
      final vista = TrabajoVista.desdeOrden(filas.single);

      expect(vista.estadoValidacion, EstadoValidacion.pendiente);
      expect(vista.latitud, closeTo(6.244203, 0.000001));
      expect(vista.longitud, closeTo(-75.581212, 0.000001));
      expect(vista.iniciadaEn, isNotNull);
      expect(vista.completadaEn, isNotNull);
      // La hora es la del servidor, no la del teléfono.
      expect(vista.iniciadaEn!.toUtc().toIso8601String(), '2026-09-18T11:02:00.000Z');
      expect(vista.completadaEn!.toUtc().toIso8601String(), '2026-09-18T12:40:00.000Z');
    });

    test('6. Un segundo upsert actualiza el valor, no lo duplica', () async {
      final baseLocal = LocalDatabase();
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: payloadDetalle(),
      );
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: payloadDetalle(estadoValidacion: 'aprobado'),
      );

      final filas = await baseLocal.getOrdenes(orgId: orgId, profileId: profileId);
      expect(filas, hasLength(1));
      expect(
        TrabajoVista.desdeOrden(filas.single).estadoValidacion,
        EstadoValidacion.aprobado,
      );
    });

    test('7. Una clave ausente conserva lo guardado; una clave en null manda',
        () async {
      final baseLocal = LocalDatabase();
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: payloadDetalle(),
      );

      // Lo que llega cuando falla el detalle y solo se tiene el listado: sin
      // `completada_campo_en` y sin coordenadas.
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: payloadDetalle(conCoordenadas: false, conCompletada: false),
      );

      var vista = TrabajoVista.desdeOrden(
        (await baseLocal.getOrdenes(orgId: orgId, profileId: profileId)).single,
      );
      expect(
        vista.completadaEn,
        isNotNull,
        reason: 'una sincronizacion a medias no puede borrar un dato que ya estaba',
      );
      expect(vista.latitud, isNotNull);

      // En cambio, si el servidor dice explícitamente null, eso sí manda.
      final borrando = payloadDetalle();
      borrando['completada_campo_en'] = null;
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: borrando,
      );

      vista = TrabajoVista.desdeOrden(
        (await baseLocal.getOrdenes(orgId: orgId, profileId: profileId)).single,
      );
      expect(vista.completadaEn, isNull);
    });

    test('8. Una orden sin ninguno de los cinco no rompe nada', () async {
      final baseLocal = LocalDatabase();
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: <String, dynamic>{
          'id': 'ot-sin-datos',
          'numero': 1,
          'estado': 'asignada',
          'cliente': <String, dynamic>{'nombre': 'Sin coordenadas'},
        },
      );

      final fila = (await baseLocal.getOrdenes(orgId: orgId, profileId: profileId))
          .firstWhere((Map<String, dynamic> f) => f['id'] == 'ot-sin-datos');
      final vista = TrabajoVista.desdeOrden(fila);

      expect(vista.estadoValidacion, EstadoValidacion.desconocido);
      expect(vista.latitud, isNull);
      expect(vista.longitud, isNull);
      expect(vista.iniciadaEn, isNull);
      expect(vista.completadaEn, isNull);
      expect(vista.estado, EstadoTrabajo.asignada);
    });

    test('9. Puede llegar una coordenada sin la otra', () async {
      final baseLocal = LocalDatabase();
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: <String, dynamic>{
          'id': 'ot-media-coordenada',
          'numero': 2,
          'estado': 'asignada',
          'cliente': <String, dynamic>{'nombre': 'Media', 'lat': 6.1},
        },
      );

      final fila = (await baseLocal.getOrdenes(orgId: orgId, profileId: profileId))
          .firstWhere((Map<String, dynamic> f) => f['id'] == 'ot-media-coordenada');
      final vista = TrabajoVista.desdeOrden(fila);

      expect(vista.latitud, closeTo(6.1, 0.000001));
      expect(vista.longitud, isNull);
    });
  });

  group('Dos máquinas, no una', () {
    test('10. El estado de validación no mueve el estado operativo', () async {
      final baseLocal = LocalDatabase();

      Future<TrabajoVista> conValidacion(String validacion) async {
        await baseLocal.upsertOrden(
          orgId: orgId,
          profileId: profileId,
          ordenData: <String, dynamic>{
            'id': ordenId,
            'numero': 4832,
            'estado_operativo': 'completada_campo',
            'estado_validacion': validacion,
            'cliente': <String, dynamic>{'nombre': 'Carlos Gomez'},
          },
        );
        return TrabajoVista.desdeOrden(
          (await baseLocal.getOrdenes(orgId: orgId, profileId: profileId)).single,
        );
      }

      // Devuelta por el supervisor: la validación cambia, el trabajo sigue
      // donde estaba. No se convierte en `correccion_requerida` por su cuenta.
      final devuelta = await conValidacion('requiere_correccion');
      expect(devuelta.estadoValidacion, EstadoValidacion.requiereCorreccion);
      expect(devuelta.estado, EstadoTrabajo.completadaCampo);

      final aprobada = await conValidacion('aprobado');
      expect(aprobada.estadoValidacion, EstadoValidacion.aprobado);
      expect(aprobada.estado, EstadoTrabajo.completadaCampo);
    });

    test('11. Una validación que la app no conoce no rompe ni contamina', () async {
      final baseLocal = LocalDatabase();
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: <String, dynamic>{
          'id': ordenId,
          'numero': 4832,
          'estado_operativo': 'en_sitio',
          'estado_validacion': 'en_comite_de_revision',
          'cliente': <String, dynamic>{'nombre': 'Carlos Gomez'},
        },
      );

      final vista = TrabajoVista.desdeOrden(
        (await baseLocal.getOrdenes(orgId: orgId, profileId: profileId)).single,
      );
      expect(vista.estadoValidacion, EstadoValidacion.desconocido);
      expect(vista.estado, EstadoTrabajo.enSitio);
    });

    test('12. Una transición local no toca el estado de validación', () async {
      final baseLocal = LocalDatabase();
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: <String, dynamic>{
          'id': ordenId,
          'numero': 4832,
          'estado_operativo': 'asignada',
          'estado_validacion': 'sin_evaluar',
          'cliente': <String, dynamic>{'nombre': 'Carlos Gomez'},
        },
      );

      await baseLocal.transicionarEstadoLocal(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
        nuevoEstadoLocal: 'en_camino',
        tipoAccion: 'marcar_en_camino',
        revisionBase: 1,
        idempotencyKey: 'clave-1',
      );

      final vista = TrabajoVista.desdeOrden(
        (await baseLocal.getOrdenes(orgId: orgId, profileId: profileId)).single,
      );
      expect(vista.estado, EstadoTrabajo.enCamino);
      expect(
        vista.estadoValidacion,
        EstadoValidacion.sinEvaluar,
        reason: 'mover el trabajo no es un juicio sobre el trabajo',
      );
    });
  });
}
