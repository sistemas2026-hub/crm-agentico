import 'dart:async';
import 'dart:convert';
import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

class LocalDatabaseChangeEvent {
  final String? orgId;
  final String? profileId;
  final String tabla;

  const LocalDatabaseChangeEvent({
    this.orgId,
    this.profileId,
    required this.tabla,
  });
}

class LocalDatabase {
  static final LocalDatabase _instance = LocalDatabase._internal();
  factory LocalDatabase() => _instance;
  LocalDatabase._internal();

  Database? _db;

  static final StreamController<LocalDatabaseChangeEvent> _changeController =
      StreamController<LocalDatabaseChangeEvent>.broadcast();

  /// Stream broadcast para múltiples suscriptores que notifica cambios reactivos en SQLite
  static Stream<LocalDatabaseChangeEvent> get onDataChanged => _changeController.stream;

  static void _notifyChange({String? orgId, String? profileId, required String tabla}) {
    if (!_changeController.isClosed) {
      _changeController.add(LocalDatabaseChangeEvent(
        orgId: orgId,
        profileId: profileId,
        tabla: tabla,
      ));
    }
  }

  static void resetForTesting() {
    _instance._db = null;
  }

  Future<Database> get database async {
    if (_db != null && _db!.isOpen) return _db!;
    _db = await _initDatabase();
    return _db!;
  }

  Future<Database> _initDatabase() async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, 'dexter_campo.db');

    final db = await openDatabase(
      path,
      version: 5,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );

    // Asignar keys estables a evidencias existentes que no tengan confirmacion_idempotency_key
    try {
      final sinConf = await db.query(
        'cola_evidencias',
        columns: ['id'],
        where: 'confirmacion_idempotency_key IS NULL',
      );
      for (final row in sinConf) {
        await db.update(
          'cola_evidencias',
          {'confirmacion_idempotency_key': const Uuid().v4()},
          where: 'id = ?',
          whereArgs: [row['id']],
        );
      }
    } catch (_) {}

    return db;
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
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
      await db.execute('UPDATE cola_evidencias SET registro_idempotency_key = id WHERE registro_idempotency_key IS NULL;');
    }
    if (oldVersion < 5) {
      final infoMutaciones = await db.rawQuery('PRAGMA table_info(cola_mutaciones);');
      final colsMutaciones = infoMutaciones.map((c) => c['name'] as String).toSet();
      if (!colsMutaciones.contains('next_attempt_at')) {
        await db.execute('ALTER TABLE cola_mutaciones ADD COLUMN next_attempt_at INTEGER NOT NULL DEFAULT 0;');
      }
    }
  }

  Future<void> _onCreate(Database db, int version) async {
    // 1. Tabla de órdenes cacheadas / activas
    await db.execute('''
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
    ''');

    // 2. Tabla de datos técnicos editados localmente (dirty)
    await db.execute('''
      CREATE TABLE local_datos_dirty (
        orden_id TEXT NOT NULL,
        org_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        campo_clave TEXT NOT NULL,
        valor_json TEXT,
        updated_at INTEGER NOT NULL,
        PRIMARY KEY (orden_id, org_id, profile_id, campo_clave)
      )
    ''');

    // 3. Cola de mutaciones / transiciones
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
        next_attempt_at INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
      )
    ''');

    // 4. Cola de evidencias offline
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
      )
    ''');

    // Índices para optimizar consultas por tenant/usuario
    await db.execute('CREATE INDEX idx_ordenes_org_user ON local_ordenes (org_id, profile_id)');
    await db.execute('CREATE INDEX idx_mutaciones_orden ON cola_mutaciones (orden_id, estado)');
    await db.execute('CREATE INDEX idx_evidencias_orden ON cola_evidencias (orden_id, subida_estado)');
  }

  // Operaciones atómicas para Órdenes
  Future<void> upsertOrden({
    required String orgId,
    required String profileId,
    required Map<String, dynamic> ordenData,
  }) async {
    final db = await database;
    final id = ordenData['id'] as String;

    // Soportar schema directo (detalle) o anidado en tipo_trabajo_version
    final schema = ordenData['schema'] ??
        ordenData['tipo_trabajo_version']?['esquema'] ??
        ordenData['tipo_trabajo_version']?['formulario'] ??
        {};

    final fields = schema['campos'] ?? [];
    final evidences = schema['evidencias'] ?? [];

    final tipoObj = ordenData['tipo'] ?? ordenData['tipo_trabajo'] ?? {};
    final tipoNombre = tipoObj['nombre'] ?? ordenData['tipo_trabajo_nombre'] ?? 'Instalación FTTH';
    final tipoCodigo = tipoObj['codigo'] ?? ordenData['tipo_trabajo_codigo'] ?? 'ftth';
    final schemaVersion = tipoObj['schema_version'] ?? ordenData['schema_version'] ?? 1;

    final estado = ordenData['estado_operativo'] ?? ordenData['estado'] ?? 'asignada';

    // Diagnóstico previo IA
    String diagnosticoTexto = '';
    final diag = ordenData['diagnostico_previo'] ?? ordenData['diagnostico_previo_ia'];
    if (diag is Map) {
      final partes = [
        if (diag['resumen'] != null) diag['resumen'],
        if (diag['nap_sugerida'] != null) 'NAP: ${diag['nap_sugerida']}',
        if (diag['puerto_sugerido'] != null) 'Puerto: ${diag['puerto_sugerido']}',
        if (diag['notas'] != null) 'Notas: ${diag['notas']}',
      ];
      diagnosticoTexto = partes.join(' | ');
    } else if (diag != null) {
      diagnosticoTexto = diag.toString();
    }

    final clienteObj = ordenData['cliente'] ?? {};

    await db.insert(
      'local_ordenes',
      {
        'id': id,
        'org_id': orgId,
        'profile_id': profileId,
        'numero': ordenData['numero'] ?? 0,
        'estado': estado,
        'cliente_nombre': clienteObj['nombre'] ?? ordenData['cliente_nombre'] ?? 'Sin cliente',
        'direccion': clienteObj['direccion'] ?? ordenData['direccion'] ?? 'Sin dirección',
        'telefono': clienteObj['telefono'] ?? ordenData['telefono'] ?? '',
        'tipo_nombre': tipoNombre,
        'tipo_codigo': tipoCodigo,
        'work_type_version_id': ordenData['work_type_version_id']?.toString(),
        'schema_version': schemaVersion,
        'formulario_campos_json': jsonEncode(fields),
        'formulario_evidencias_json': jsonEncode(evidences),
        'revision': ordenData['revision'] ?? 1,
        'diagnostico_previo_ia': diagnosticoTexto,
        'datos_json': jsonEncode(ordenData['datos'] ?? {}),
        'fecha_compromiso': ordenData['programada_para']?.toString() ?? ordenData['fecha_compromiso']?.toString(),
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<List<Map<String, dynamic>>> getOrdenes({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    return await db.query(
      'local_ordenes',
      where: 'org_id = ? AND profile_id = ?',
      whereArgs: [orgId, profileId],
      orderBy: 'numero ASC',
    );
  }

  Future<Map<String, dynamic>?> getOrden({
    required String orgId,
    required String profileId,
    required String id,
  }) async {
    final db = await database;
    final results = await db.query(
      'local_ordenes',
      where: 'id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [id, orgId, profileId],
      limit: 1,
    );
    if (results.isEmpty) return null;
    return results.first;
  }

  // Operaciones atómicas de guardado de datos (por tecla)
  Future<void> saveDatoCampo({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String campoClave,
    required dynamic valor,
  }) async {
    final db = await database;
    await db.insert(
      'local_datos_dirty',
      {
        'orden_id': ordenId,
        'org_id': orgId,
        'profile_id': profileId,
        'campo_clave': campoClave,
        'valor_json': jsonEncode(valor),
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'local_datos_dirty');
  }

  Future<Map<String, dynamic>> getMergedDatosOrden({
    required String orgId,
    required String profileId,
    required String ordenId,
  }) async {
    final db = await database;
    // 1. Obtener datos base
    final orden = await getOrden(orgId: orgId, profileId: profileId, id: ordenId);
    Map<String, dynamic> datos = {};
    if (orden != null && orden['datos_json'] != null) {
      try {
        datos = Map<String, dynamic>.from(jsonDecode(orden['datos_json']));
      } catch (_) {}
    }

    // 2. Sobrescribir con dirty locales
    final dirtyList = await db.query(
      'local_datos_dirty',
      where: 'orden_id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [ordenId, orgId, profileId],
    );

    for (final row in dirtyList) {
      final key = row['campo_clave'] as String;
      final valStr = row['valor_json'] as String?;
      if (valStr != null) {
        try {
          datos[key] = jsonDecode(valStr);
        } catch (_) {
          datos[key] = valStr;
        }
      }
    }

    return datos;
  }

  Future<Map<String, dynamic>> getDirtyDatosForSync({
    required String orgId,
    required String profileId,
    required String ordenId,
  }) async {
    final db = await database;
    final dirtyList = await db.query(
      'local_datos_dirty',
      where: 'orden_id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [ordenId, orgId, profileId],
    );

    final Map<String, dynamic> dirty = {};
    for (final row in dirtyList) {
      final key = row['campo_clave'] as String;
      final valStr = row['valor_json'] as String?;
      if (valStr != null) {
        try {
          dirty[key] = jsonDecode(valStr);
        } catch (_) {
          dirty[key] = valStr;
        }
      }
    }
    return dirty;
  }

  Future<void> clearDirtyDatos({
    required String orgId,
    required String profileId,
    required String ordenId,
    required List<String> claves,
  }) async {
    final db = await database;
    final placeholders = List.filled(claves.length, '?').join(',');
    await db.delete(
      'local_datos_dirty',
      where: 'orden_id = ? AND org_id = ? AND profile_id = ? AND campo_clave IN ($placeholders)',
      whereArgs: [ordenId, orgId, profileId, ...claves],
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'local_datos_dirty');
  }

  // Transición offline atómica: guarda estado local + encola mutación en una sola transacción
  Future<void> transicionarEstadoLocal({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String nuevoEstadoLocal,
    required String tipoAccion, // iniciar, en_camino, suspender, completar
    required int revisionBase,
    required String idempotencyKey,
    Map<String, dynamic>? payload,
  }) async {
    final db = await database;
    await db.transaction((txn) async {
      // 1. Actualizar orden local
      await txn.update(
        'local_ordenes',
        {
          'estado': nuevoEstadoLocal,
          'updated_at': DateTime.now().millisecondsSinceEpoch,
        },
        where: 'id = ? AND org_id = ? AND profile_id = ?',
        whereArgs: [ordenId, orgId, profileId],
      );

      // 2. Encolar mutación
      await txn.insert(
        'cola_mutaciones',
        {
          'id': idempotencyKey,
          'org_id': orgId,
          'profile_id': profileId,
          'orden_id': ordenId,
          'tipo': tipoAccion,
          'payload_json': payload != null ? jsonEncode(payload) : null,
          'revision_base': revisionBase,
          'idempotency_key': idempotencyKey,
          'estado': 'pendiente',
          'created_at': DateTime.now().millisecondsSinceEpoch,
        },
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
    });
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_mutaciones');
  }

  // Cola de evidencias
  Future<void> encolarEvidencia({
    required String id,
    required String orgId,
    required String profileId,
    required String ordenId,
    required String requisitoId,
    required String archivoPath,
    required String sha256,
    required int tamanoBytes,
    required String mimeType,
    String? registroIdempotencyKey,
    String? confirmacionIdempotencyKey,
  }) async {
    final db = await database;
    final regKey = registroIdempotencyKey ?? const Uuid().v4();
    final confKey = confirmacionIdempotencyKey ?? const Uuid().v4();
    await db.insert(
      'cola_evidencias',
      {
        'id': id,
        'org_id': orgId,
        'profile_id': profileId,
        'orden_id': ordenId,
        'requisito_id': requisitoId,
        'archivo_path': archivoPath,
        'sha256': sha256,
        'tamano_bytes': tamanoBytes,
        'mime_type': mimeType,
        'subida_estado': 'pendiente_registro',
        'registro_idempotency_key': regKey,
        'confirmacion_idempotency_key': confKey,
        'created_at': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_evidencias');
  }

  Future<List<Map<String, dynamic>>> getEvidenciasOrden({
    required String orgId,
    required String profileId,
    required String ordenId,
  }) async {
    final db = await database;
    return await db.query(
      'cola_evidencias',
      where: 'orden_id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [ordenId, orgId, profileId],
    );
  }

  Future<List<Map<String, dynamic>>> getMutacionesPendientes({
    required String orgId,
    required String profileId,
    int? soloListasHasta,
  }) async {
    final db = await database;
    if (soloListasHasta != null) {
      return await db.query(
        'cola_mutaciones',
        where: 'org_id = ? AND profile_id = ? AND estado = ? AND next_attempt_at <= ?',
        whereArgs: [orgId, profileId, 'pendiente', soloListasHasta],
        orderBy: 'created_at ASC',
      );
    }
    return await db.query(
      'cola_mutaciones',
      where: 'org_id = ? AND profile_id = ? AND estado = ?',
      whereArgs: [orgId, profileId, 'pendiente'],
      orderBy: 'created_at ASC',
    );
  }

  Future<void> registrarFalloMutacion({
    required String id,
    required int nextAttemptAt,
    String? errorMensaje,
  }) async {
    final db = await database;
    await db.rawUpdate('''
      UPDATE cola_mutaciones
      SET reintentos = reintentos + 1,
          next_attempt_at = ?,
          error_mensaje = ?,
          estado = 'pendiente'
      WHERE id = ?
    ''', [nextAttemptAt, errorMensaje, id]);
    _notifyChange(tabla: 'cola_mutaciones');
  }

  Future<Map<String, int>> getSyncCounts({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;

    final mutPendList = await db.rawQuery(
      "SELECT COUNT(*) as c FROM cola_mutaciones WHERE org_id = ? AND profile_id = ? AND estado = 'pendiente'",
      [orgId, profileId],
    );
    final mutPend = (mutPendList.isNotEmpty ? mutPendList.first['c'] as int? : 0) ?? 0;

    final mutConfList = await db.rawQuery(
      "SELECT COUNT(*) as c FROM cola_mutaciones WHERE org_id = ? AND profile_id = ? AND estado IN ('conflicto', 'error_validacion')",
      [orgId, profileId],
    );
    final mutConf = (mutConfList.isNotEmpty ? mutConfList.first['c'] as int? : 0) ?? 0;

    final evPendList = await db.rawQuery(
      "SELECT COUNT(*) as c FROM cola_evidencias WHERE org_id = ? AND profile_id = ? AND subida_estado != 'confirmada'",
      [orgId, profileId],
    );
    final evPend = (evPendList.isNotEmpty ? evPendList.first['c'] as int? : 0) ?? 0;

    final dirtyList = await db.rawQuery(
      "SELECT COUNT(DISTINCT campo_clave) as c FROM local_datos_dirty WHERE org_id = ? AND profile_id = ?",
      [orgId, profileId],
    );
    final dirtyCount = (dirtyList.isNotEmpty ? dirtyList.first['c'] as int? : 0) ?? 0;

    return {
      'mutaciones_pendientes': mutPend,
      'mutaciones_conflicto': mutConf,
      'evidencias_pendientes': evPend,
      'datos_dirty': dirtyCount,
      'total_pendientes': mutPend + evPend + (dirtyCount > 0 ? 1 : 0),
    };
  }

  Future<List<Map<String, dynamic>>> getEvidenciasPendientes({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    return await db.query(
      'cola_evidencias',
      where: 'org_id = ? AND profile_id = ? AND subida_estado != ?',
      whereArgs: [orgId, profileId, 'confirmada'],
      orderBy: 'created_at ASC',
    );
  }

  Future<void> updateMutacionEstado({
    required String id,
    required String estado,
    String? errorMensaje,
  }) async {
    final db = await database;
    await db.update(
      'cola_mutaciones',
      {
        'estado': estado,
        'error_mensaje': errorMensaje,
      },
      where: 'id = ?',
      whereArgs: [id],
    );
    _notifyChange(tabla: 'cola_mutaciones');
  }

  Future<void> updateEvidenciaEstado({
    required String id,
    required String subidaEstado,
    String? signedUploadUrl,
    String? uploadMethod,
    String? uploadHeadersJson,
    bool? uploadRequiereAuth,
    String? backendEvidenciaId,
    String? errorMensaje,
    String? registroIdempotencyKey,
    String? confirmacionIdempotencyKey,
  }) async {
    final db = await database;
    final Map<String, dynamic> data = {'subida_estado': subidaEstado};
    if (signedUploadUrl != null) data['signed_upload_url'] = signedUploadUrl;
    if (uploadMethod != null) data['upload_method'] = uploadMethod;
    if (uploadHeadersJson != null) data['upload_headers_json'] = uploadHeadersJson;
    if (uploadRequiereAuth != null) data['upload_requiere_auth'] = uploadRequiereAuth ? 1 : 0;
    if (backendEvidenciaId != null) data['backend_evidencia_id'] = backendEvidenciaId;
    if (errorMensaje != null) data['error_mensaje'] = errorMensaje;
    if (registroIdempotencyKey != null) data['registro_idempotency_key'] = registroIdempotencyKey;
    if (confirmacionIdempotencyKey != null) data['confirmacion_idempotency_key'] = confirmacionIdempotencyKey;

    await db.update(
      'cola_evidencias',
      data,
      where: 'id = ?',
      whereArgs: [id],
    );
    _notifyChange(tabla: 'cola_evidencias');
  }

  Future<void> updateOrdenRevisionYEstado({
    required String orgId,
    required String profileId,
    required String ordenId,
    required int nuevaRevision,
    required String nuevoEstado,
  }) async {
    final db = await database;
    await db.update(
      'local_ordenes',
      {
        'revision': nuevaRevision,
        'estado': nuevoEstado,
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      },
      where: 'id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [ordenId, orgId, profileId],
    );
  }
}
