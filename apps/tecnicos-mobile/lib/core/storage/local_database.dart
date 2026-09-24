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

/// De dónde salió el retrato de una orden.
///
/// No es lo mismo un detalle que un listado: el listado no trae formulario, ni
/// evidencias, ni diagnóstico, ni datos técnicos, ni la versión del esquema.
/// Si se guarda un listado como si fuera un detalle, esos campos se vacían —y
/// el teléfono pierde información que ya tenía, por un fallo de red pasajero.
///
/// La diferencia se decide por **procedencia**, nunca por el valor: un detalle
/// puede decir legítimamente que el formulario está vacío, y eso hay que
/// obedecerlo. Un listado no puede afirmar nada sobre ese campo, ni siquiera
/// que está vacío.
enum FuenteOrden {
  /// `GET /trabajos/{id}/`: puede afirmar todo, incluso que algo quedó vacío.
  detalle,

  /// `GET /trabajos/`: solo puede afirmar lo que trae.
  listado,
}

class LocalDatabase {
  /// Todavía no se sabe qué versión de esquema exige la orden.
  ///
  /// Pasa con una orden que se vio por primera vez en el listado mientras el
  /// detalle no llegaba: el listado no trae `tipo.schema_version`. Antes se
  /// guardaba un 1, que es la versión que esta aplicación sabe ejecutar — o
  /// sea, se afirmaba compatibilidad sin tener con qué. Un cero no afirma
  /// nada, y quien decide si la orden se puede trabajar lo trata como
  /// incompatible hasta que llegue el detalle.
  ///
  /// Es un centinela y no un `null` porque la columna es `NOT NULL DEFAULT 1`
  /// desde la v1: hacerla anulable obligaría a reconstruir la tabla, que es
  /// justo lo que ninguna migración de esta base hace.
  static const int versionEsquemaDesconocida = 0;

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

  /// El archivo de la base. Solo las pruebas lo cambian.
  ///
  /// `flutter test` corre cada archivo de prueba en paralelo, y todos abrían
  /// la MISMA base: una suite que vacía tablas en su preparación le borraba
  /// las filas a la que corría al lado. Los fallos aparecían y desaparecían
  /// según el orden, que es la peor forma de fallar -- se culpa al último
  /// cambio y no al que comparte el archivo.
  static String _nombreDeArchivo = 'dexter_campo.db';

  /// Le da a este archivo de pruebas una base propia. Llamarlo antes de abrir.
  static void usarBaseDePruebas(String nombre) {
    _nombreDeArchivo = nombre;
    resetForTesting();
  }

  Future<Database> _initDatabase() async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, _nombreDeArchivo);

    final db = await openDatabase(
      path,
      version: 14,
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
    // v9: materiales. Aditiva y sin tocar nada de lo anterior -- un telefono
    // con media jornada sin subir no puede perderla por actualizar la app.
    if (oldVersion < 9) {
      await _crearTablasDeMateriales(db);
    }

    // v11: el ultimo estado de jornada que dijo el servidor, para poder
    // mostrarlo sin senal. Es un espejo: se reemplaza entero en cada
    // sincronizacion y nunca se edita desde el telefono.
    if (oldVersion < 11) {
      await _crearTablaDeJornada(db);
    }

    // v12: las diferencias que el tecnico explica, y el cierre que afirma.
    // Las dos cosas pueden ocurrir sin senal: la jornada termina en la calle,
    // no cuando el telefono encuentra red.
    if (oldVersion < 12) {
      await _crearTablaDeIncidencias(db);
      final info = await db.rawQuery('PRAGMA table_info(local_jornada);');
      final cols = info.map((c) => c['name'] as String).toSet();
      if (!cols.contains('cierre_local_en')) {
        await db.execute(
          'ALTER TABLE local_jornada ADD COLUMN cierre_local_en INTEGER;',
        );
      }
      if (!cols.contains('cierre_clave')) {
        await db.execute('ALTER TABLE local_jornada ADD COLUMN cierre_clave TEXT;');
      }
    }

    // v13: cuando se tomo la foto, no cuando llego al servidor.
    //
    // El backend esperaba `capturada_en_cliente` desde siempre y la aplicacion
    // no la mandaba nunca: la columna existia del otro lado y quedaba vacia en
    // todas las filas. Una foto sin hora prueba que alguien subio una foto;
    // con hora prueba que se tomo ANTES de subirla, que es lo que se discute
    // cuando alguien la revisa meses despues.
    //
    // Nula en lo ya encolado, a proposito: de esas fotos no se sabe cuando se
    // tomaron, y escribirles la hora de la migracion seria inventar el dato
    // que esto viene a registrar.
    if (oldVersion < 13) {
      // `infoEv` vacio significa que la tabla NO EXISTE, no que no tenga
      // columnas. Sin esa distincion, una base vieja sin `cola_evidencias`
      // entraba al ALTER y la actualizacion moria al abrir -- o sea, el
      // camino por el que actualizar la aplicacion le borra la jornada a un
      // tecnico. Lo cazo `migracion_v7_test`, que simula justo esa base.
      //
      // Cuando la tabla se cree mas adelante, nace con la columna: esta en el
      // CREATE TABLE.
      final infoEv = await db.rawQuery('PRAGMA table_info(cola_evidencias);');
      final colsEv = infoEv.map((c) => c['name'] as String).toSet();
      if (infoEv.isNotEmpty && !colsEv.contains('capturada_en')) {
        await db.execute(
          'ALTER TABLE cola_evidencias ADD COLUMN capturada_en INTEGER;',
        );
      }
    }

    // v14: donde se tomo, con que equipo, y -- cuando no se pudo saber -- por
    // que no. Un `metadatos_captura` vacio es ambiguo: no distingue un sotano
    // sin senal de un permiso negado ni de una version que ni lo intentaba.
    //
    // Misma guarda que v13, por la misma razon: `table_info` vacio significa
    // que la tabla no existe.
    if (oldVersion < 14) {
      final infoEv = await db.rawQuery('PRAGMA table_info(cola_evidencias);');
      final colsEv = infoEv.map((c) => c['name'] as String).toSet();
      if (infoEv.isNotEmpty && !colsEv.contains('metadatos_captura_json')) {
        await db.execute(
          'ALTER TABLE cola_evidencias '
          'ADD COLUMN metadatos_captura_json TEXT;',
        );
      }
    }

    // v10: el motivo que escribe el tecnico cuando usa mas de lo habitual, y
    // la regla que el servidor manda con cada material para poder avisarlo
    // sin senal.
    if (oldVersion < 10) {
      final infoMovimientos =
          await db.rawQuery('PRAGMA table_info(cola_movimientos_material);');
      final cols = infoMovimientos.map((c) => c['name'] as String).toSet();
      if (!cols.contains('motivo_tecnico')) {
        await db.execute(
          'ALTER TABLE cola_movimientos_material ADD COLUMN motivo_tecnico TEXT;',
        );
      }
      final infoKit = await db.rawQuery('PRAGMA table_info(local_kit);');
      final colsKit = infoKit.map((c) => c['name'] as String).toSet();
      if (!colsKit.contains('regla_json')) {
        await db.execute('ALTER TABLE local_kit ADD COLUMN regla_json TEXT;');
      }
    }

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

    if (oldVersion < 6) {
      // Cinco datos que el backend ya entregaba y esta base tiraba al guardar
      // la orden. Se agregan como columnas nuevas y anulables, con el mismo
      // patron que las cuatro migraciones anteriores: nada se recrea, nada se
      // borra, y una orden o una mutacion que ya estaba sigue estando.
      final infoOrdenes = await db.rawQuery('PRAGMA table_info(local_ordenes);');
      final colsOrdenes = infoOrdenes.map((c) => c['name'] as String).toSet();

      const nuevas = <String, String>{
        'estado_validacion': 'TEXT',
        'cliente_lat': 'REAL',
        'cliente_lng': 'REAL',
        'iniciada_en': 'TEXT',
        'completada_campo_en': 'TEXT',
      };

      for (final entrada in nuevas.entries) {
        if (!colsOrdenes.contains(entrada.key)) {
          await db.execute(
            'ALTER TABLE local_ordenes ADD COLUMN ${entrada.key} ${entrada.value};',
          );
        }
      }
    }

    if (oldVersion < 7) {
      // Siete datos que el servidor ya tenia guardados y ningun serializador
      // devolvia (tanda 1 de SPEC/BACKEND_CAMPO_DATOS.md). El mas importante
      // es `correccion_json`: que pidio rehacer el supervisor. Hasta ahora una
      // orden devuelta llegaba sin decir que corregir.
      //
      // Mismo patron aditivo: columnas nuevas y anulables, nada se recrea.
      final infoOrdenes = await db.rawQuery('PRAGMA table_info(local_ordenes);');
      final colsOrdenes = infoOrdenes.map((c) => c['name'] as String).toSet();

      const nuevas = <String, String>{
        'cerrada_en': 'TEXT',
        'vuelta': 'INTEGER',
        'origen_json': 'TEXT',
        'contexto_json': 'TEXT',
        'correccion_json': 'TEXT',
        'pasos_json': 'TEXT',
        'cuadrilla_json': 'TEXT',
      };

      for (final entrada in nuevas.entries) {
        if (!colsOrdenes.contains(entrada.key)) {
          await db.execute(
            'ALTER TABLE local_ordenes ADD COLUMN ${entrada.key} ${entrada.value};',
          );
        }
      }
    }

    if (oldVersion < 8) {
      // Lo que decide la oficina y el tecnico no puede deducir: con que
      // urgencia, en que zona, que franja se le prometio al cliente, cuando
      // vence el compromiso, como se entra al inmueble y que requisitos de
      // seguridad tiene el trabajo (tanda 2).
      //
      // La prioridad y la ventana dejan de ser datos de ejemplo: ahora se
      // pueden usar para ordenar y para avisar, porque vienen del servidor.
      final infoOrdenes = await db.rawQuery('PRAGMA table_info(local_ordenes);');
      final colsOrdenes = infoOrdenes.map((c) => c['name'] as String).toSet();

      const nuevas = <String, String>{
        'prioridad': 'TEXT',
        'zona': 'TEXT',
        'resumen': 'TEXT',
        'ventana_inicio': 'TEXT',
        'ventana_fin': 'TEXT',
        'sla_vence_en': 'TEXT',
        'detalle_acceso': 'TEXT',
        'id_abonado': 'TEXT',
        'requisitos_seguridad_json': 'TEXT',
      };

      for (final entrada in nuevas.entries) {
        if (!colsOrdenes.contains(entrada.key)) {
          await db.execute(
            'ALTER TABLE local_ordenes ADD COLUMN ${entrada.key} ${entrada.value};',
          );
        }
      }
    }
  }

  /// Las dos tablas de materiales, creadas igual desde cero que al migrar.
  ///
  /// Escritas una sola vez porque ya paso: un `CREATE` en `_onCreate` y otro
  /// distinto en `_onUpgrade` dejan dos esquemas parecidos segun por donde
  /// haya entrado cada telefono, y la diferencia solo aparece meses despues
  /// en un aparato que nadie puede reproducir.
  static Future<void> _crearTablasDeMateriales(DatabaseExecutor db) async {
    // Lo que el tecnico tiene a cargo, como se lo entrego el servidor.
    //
    // Es un espejo de lectura: se reescribe con cada sincronizacion y no se
    // edita a mano. Lo que el tecnico hace --gastar, devolver-- vive en la
    // cola, y el saldo que se muestra es este espejo ajustado con lo que la
    // cola todavia no subio. Guardar un saldo ya ajustado haria que un
    // reintento lo descontara dos veces.
    await db.execute('''
      CREATE TABLE IF NOT EXISTS local_kit (
        org_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        codigo TEXT NOT NULL,
        nombre TEXT NOT NULL,
        categoria TEXT,
        clase TEXT NOT NULL,
        unidad TEXT NOT NULL,
        recibido TEXT NOT NULL,
        consumido TEXT NOT NULL,
        devuelto TEXT NOT NULL,
        disponible TEXT NOT NULL,
        series_json TEXT,
        acta TEXT,
        entregado_en TEXT,
        regla_json TEXT,
        updated_at INTEGER NOT NULL,
        PRIMARY KEY (codigo, org_id, profile_id)
      )
    ''');

    // Lo que paso en la calle y todavia no subio.
    //
    // `id` ES la clave de idempotencia: el servidor la usa para reconocer un
    // reintento, asi que no puede haber dos ids para el mismo hecho ni un
    // hecho sin id. Tenerlos separados invitaba a regenerar uno al reintentar,
    // que es justo lo que duplica un consumo.
    await db.execute('''
      CREATE TABLE IF NOT EXISTS cola_movimientos_material (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        material_codigo TEXT NOT NULL,
        material_nombre TEXT,
        tipo TEXT NOT NULL,
        cantidad TEXT NOT NULL,
        serie TEXT,
        orden_id TEXT,
        orden_numero INTEGER,
        motivo_tecnico TEXT,
        estado TEXT NOT NULL DEFAULT 'pendiente',
        resultado TEXT,
        motivo TEXT,
        intentos INTEGER NOT NULL DEFAULT 0,
        error_mensaje TEXT,
        next_attempt_at INTEGER NOT NULL DEFAULT 0,
        ocurrido_en TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        confirmado_en INTEGER
      )
    ''');

    await db.execute(
      'CREATE INDEX IF NOT EXISTS idx_kit_org_user ON local_kit (org_id, profile_id)',
    );
    // El indice lleva la identidad adelante porque toda consulta de la cola
    // empieza por "lo mio": sin eso, un telefono que acumulo la jornada de
    // dos personas recorre filas ajenas para descartarlas.
    await db.execute(
      'CREATE INDEX IF NOT EXISTS idx_movimientos_pendientes '
      'ON cola_movimientos_material (org_id, profile_id, estado)',
    );
  }

  /// Las diferencias que el tecnico explico, esperando subir.
  ///
  /// Va en su propia tabla y no en la cola de movimientos porque no es un
  /// movimiento: no mueve material de un lado a otro, explica por que algo no
  /// esta. Mezclarlas obligaria a que cada consulta de la cola supiera
  /// distinguir dos cosas distintas dentro de la misma tabla.
  ///
  /// Comparte, eso si, toda la disciplina: identidad, clave de idempotencia,
  /// estado de envio e intentos.
  static Future<void> _crearTablaDeIncidencias(DatabaseExecutor db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS cola_incidencias (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        material_codigo TEXT NOT NULL,
        material_nombre TEXT,
        tipo TEXT NOT NULL,
        cantidad TEXT NOT NULL,
        serie TEXT,
        motivo TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'pendiente',
        resultado TEXT,
        error_mensaje TEXT,
        intentos INTEGER NOT NULL DEFAULT 0,
        next_attempt_at INTEGER NOT NULL DEFAULT 0,
        ocurrido_en TEXT NOT NULL,
        created_at INTEGER NOT NULL
      )
    ''');
    await db.execute(
      'CREATE INDEX IF NOT EXISTS idx_incidencias_pendientes '
      'ON cola_incidencias (org_id, profile_id, estado)',
    );
  }

  /// El espejo de la jornada, tal como lo calculo el servidor.
  ///
  /// Una sola fila por identidad. No se calcula nada aca: la regla del modulo
  /// es que los numeros de la jornada los hace el dominio, y el telefono los
  /// muestra. Guardar un calculo propio abriria la puerta a que la pantalla
  /// diga un numero y el acta diga otro.
  static Future<void> _crearTablaDeJornada(DatabaseExecutor db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS local_jornada (
        org_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        estado TEXT NOT NULL,
        resumen_json TEXT NOT NULL,
        detalle_json TEXT,
        series_sin_devolver_json TEXT,
        transferencias_json TEXT,
        motivos_json TEXT,
        puede_cerrar INTEGER NOT NULL DEFAULT 0,
        -- Cuando el tecnico afirmo que termino, aunque no hubiera senal. Es
        -- distinto de `estado`: eso lo dice el servidor cuando valido y
        -- congelo el acta.
        cierre_local_en INTEGER,
        cierre_clave TEXT,
        actualizado_en INTEGER NOT NULL,
        PRIMARY KEY (org_id, profile_id)
      )
    ''');
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
        estado_validacion TEXT,
        cliente_lat REAL,
        cliente_lng REAL,
        iniciada_en TEXT,
        completada_campo_en TEXT,
        cerrada_en TEXT,
        vuelta INTEGER,
        prioridad TEXT,
        zona TEXT,
        resumen TEXT,
        ventana_inicio TEXT,
        ventana_fin TEXT,
        sla_vence_en TEXT,
        detalle_acceso TEXT,
        id_abonado TEXT,
        requisitos_seguridad_json TEXT,
        origen_json TEXT,
        contexto_json TEXT,
        correccion_json TEXT,
        pasos_json TEXT,
        cuadrilla_json TEXT,
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
        capturada_en INTEGER,
        metadatos_captura_json TEXT,
        created_at INTEGER NOT NULL
      )
    ''');

    await _crearTablasDeMateriales(db);
    await _crearTablaDeJornada(db);
    await _crearTablaDeIncidencias(db);

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
    FuenteOrden fuente = FuenteOrden.detalle,
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
    // Sin valor no se inventa una versión compatible: se marca desconocida.
    final schemaVersion = tipoObj['schema_version'] ??
        ordenData['schema_version'] ??
        versionEsquemaDesconocida;

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
    // Cuando hay que estar: la hora agendada, la franja prometida al cliente y
    // el vencimiento del compromiso. Son tres cosas distintas.
    final Map<dynamic, dynamic> compromiso =
        (ordenData['compromiso'] as Map?) ?? const <dynamic, dynamic>{};

    // Lo que solo el detalle puede afirmar (CAMPO-D2).
    //
    // El listado no trae formulario, evidencias, diagnóstico, datos técnicos ni
    // la versión del esquema. Guardar un listado como si fuera un detalle
    // dejaba el formulario en `[]`, las fotos requeridas en `[]` y el
    // diagnóstico vacío: un fallo de red de un segundo le borraba al técnico lo
    // que necesitaba para trabajar.
    //
    // La decisión es por **procedencia, no por valor**: un detalle que dice que
    // el formulario está vacío se obedece; un listado no puede decir nada sobre
    // eso, ni siquiera que está vacío. Con una orden nueva que solo llegó por
    // listado, se guarda con lo disponible y sin inventar nada.
    final ricosPrevios = fuente == FuenteOrden.detalle
        ? const <String, Object?>{}
        : (await db.query(
            'local_ordenes',
            columns: <String>[
              'formulario_campos_json',
              'formulario_evidencias_json',
              'diagnostico_previo_ia',
              'datos_json',
              'schema_version',
              // El listado tampoco trae nada de esto: son del detalle.
              'contexto_json',
              'correccion_json',
              'pasos_json',
              'cuadrilla_json',
              'requisitos_seguridad_json',
            ],
            where: 'id = ? AND org_id = ? AND profile_id = ?',
            whereArgs: <Object?>[id, orgId, profileId],
            limit: 1,
          ))
            .firstOrNull ??
            const <String, Object?>{};

    Object? soloDetalle(String columna, Object? valorSiEsDetalle) {
      if (fuente == FuenteOrden.detalle) return valorSiEsDetalle;
      return ricosPrevios[columna] ?? valorSiEsDetalle;
    }

    // Los cinco campos que el backend entrega y antes se descartaban.
    //
    // Este upsert reemplaza la fila entera, así que lo que no se escriba se
    // pierde. Y el payload no siempre es el mismo: cuando la llamada al detalle
    // falla se guarda lo que trajo el listado, que no incluye
    // `completada_campo_en`. Para que una sincronización a medias no borre un
    // dato que ya estaba, la clave ausente conserva el valor guardado; una
    // clave presente —aunque venga en null— sí manda, porque ahí el servidor
    // está diciendo algo.
    final previas = await db.query(
      'local_ordenes',
      columns: <String>[
        'estado_validacion',
        'cliente_lat',
        'cliente_lng',
        'iniciada_en',
        'completada_campo_en',
        'cerrada_en',
        'vuelta',
        'origen_json',
        'prioridad',
        'zona',
        'resumen',
        'ventana_inicio',
        'ventana_fin',
        'sla_vence_en',
        'detalle_acceso',
        'id_abonado',
        'requisitos_seguridad_json',
      ],
      where: 'id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: <Object?>[id, orgId, profileId],
      limit: 1,
    );
    final anterior = previas.isEmpty ? const <String, Object?>{} : previas.first;

    Object? conservando(Map<dynamic, dynamic> origen, String clave, String columna) {
      if (origen.containsKey(clave)) return origen[clave];
      return anterior[columna];
    }

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
        // La version del esquema decide si la orden se puede trabajar con esta
        // version de la aplicacion. El listado no la trae, y caer al 1 por
        // defecto desbloquearia una orden que tiene que quedar bloqueada.
        'schema_version': soloDetalle('schema_version', schemaVersion),
        'formulario_campos_json':
            soloDetalle('formulario_campos_json', jsonEncode(fields)),
        'formulario_evidencias_json':
            soloDetalle('formulario_evidencias_json', jsonEncode(evidences)),
        'revision': ordenData['revision'] ?? 1,
        'diagnostico_previo_ia':
            soloDetalle('diagnostico_previo_ia', diagnosticoTexto),
        'datos_json':
            soloDetalle('datos_json', jsonEncode(ordenData['datos'] ?? {})),
        'fecha_compromiso': ordenData['programada_para']?.toString() ??
            compromiso['programada_para']?.toString() ??
            ordenData['fecha_compromiso']?.toString(),
        // Estado de la máquina de validación. Se guarda tal cual llega y no
        // toca `estado`: son dos máquinas distintas, y una orden puede estar
        // completada en campo y devuelta al mismo tiempo.
        'estado_validacion':
            conservando(ordenData, 'estado_validacion', 'estado_validacion')?.toString(),
        // Coordenadas del cliente. Se guardan como vienen; puede existir una
        // sin la otra.
        'cliente_lat': _comoDecimal(conservando(clienteObj, 'lat', 'cliente_lat')),
        'cliente_lng': _comoDecimal(conservando(clienteObj, 'lng', 'cliente_lng')),
        // Marcas de tiempo del servidor. No se regeneran con la hora del
        // teléfono: dicen cuándo pasó algo allá, no cuándo sincronizamos acá.
        'iniciada_en': conservando(ordenData, 'iniciada_en', 'iniciada_en')?.toString(),
        'completada_campo_en':
            conservando(ordenData, 'completada_campo_en', 'completada_campo_en')?.toString(),
        'cerrada_en': conservando(ordenData, 'cerrada_en', 'cerrada_en')?.toString(),
        // Lo que decide la oficina. Viene en las dos respuestas.
        'prioridad': conservando(ordenData, 'prioridad', 'prioridad')?.toString(),
        'zona': conservando(ordenData, 'zona', 'zona')?.toString(),
        'resumen': conservando(ordenData, 'resumen', 'resumen')?.toString(),
        'ventana_inicio':
            conservando(compromiso, 'ventana_inicio', 'ventana_inicio')?.toString(),
        'ventana_fin':
            conservando(compromiso, 'ventana_fin', 'ventana_fin')?.toString(),
        'sla_vence_en':
            conservando(compromiso, 'sla_vence_en', 'sla_vence_en')?.toString(),
        'detalle_acceso':
            conservando(clienteObj, 'detalle_acceso', 'detalle_acceso')?.toString(),
        'id_abonado':
            conservando(clienteObj, 'id_abonado', 'id_abonado')?.toString(),
        // Los requisitos de seguridad solo los dice el detalle.
        'requisitos_seguridad_json': soloDetalle(
          'requisitos_seguridad_json',
          ordenData['requisitos_seguridad'] == null
              ? null
              : jsonEncode(ordenData['requisitos_seguridad']),
        ),
        // En que vuelta de validacion va la orden. Viene en las dos respuestas.
        'vuelta': _comoEntero(conservando(ordenData, 'vuelta', 'vuelta')),
        // De que ticket nacio la orden. Tambien viene en las dos.
        'origen_json': ordenData.containsKey('origen')
            ? jsonEncode(ordenData['origen'])
            : anterior['origen_json'],
        // Lo que solo dice el detalle: el snapshot tecnico congelado al
        // despachar, que pidio rehacer el supervisor, el procedimiento del
        // tipo de trabajo y quienes van al trabajo.
        'contexto_json': soloDetalle(
          'contexto_json',
          ordenData['contexto'] == null ? null : jsonEncode(ordenData['contexto']),
        ),
        'correccion_json': soloDetalle(
          'correccion_json',
          ordenData['correccion'] == null ? null : jsonEncode(ordenData['correccion']),
        ),
        'pasos_json': soloDetalle(
          'pasos_json',
          tipoObj['pasos'] == null ? null : jsonEncode(tipoObj['pasos']),
        ),
        'cuadrilla_json': soloDetalle(
          'cuadrilla_json',
          ordenData['cuadrilla'] == null ? null : jsonEncode(ordenData['cuadrilla']),
        ),
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  /// La vuelta puede llegar como número o como texto según el serializador.
  static int? _comoEntero(Object? valor) {
    if (valor == null) return null;
    if (valor is int) return valor;
    if (valor is num) return valor.toInt();
    return int.tryParse(valor.toString());
  }

  /// Una coordenada puede llegar como número o como texto según el serializador.
  static double? _comoDecimal(Object? valor) {
    if (valor == null) return null;
    if (valor is num) return valor.toDouble();
    return double.tryParse(valor.toString());
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
    DateTime? capturadaEn,
    Map<String, dynamic>? metadatosCaptura,
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
        // Sin valor explicito se usa el momento de encolar. No es un relleno:
        // entre apretar el obturador y encolar hay una copia de archivo y un
        // sha256 -- decimas de segundo. Quien conoce el instante exacto lo
        // pasa igual, porque decimas gratis son decimas.
        'capturada_en':
            (capturadaEn ?? DateTime.now()).millisecondsSinceEpoch,
        // Nulo cuando no se intento; un objeto con `ubicacion_motivo` cuando
        // se intento y no se pudo. No son lo mismo y la fila los distingue.
        'metadatos_captura_json':
            metadatosCaptura == null ? null : jsonEncode(metadatosCaptura),
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
    required String orgId,
    required String profileId,
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
      WHERE id = ? AND org_id = ? AND profile_id = ?
    ''', [nextAttemptAt, errorMensaje, id, orgId, profileId]);
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_mutaciones');
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

  /// La identidad es obligatoria aunque el `id` ya sea único.
  ///
  /// El id de una mutación es un UUID y basta para encontrar la fila, así que
  /// pedir org y perfil parece de más. Lo que compra es que una escritura no
  /// PUEDA tocar la fila de otra cuenta ni por error de programación: si el
  /// filtro no coincide, la actualización no escribe nada en vez de escribir
  /// donde no debía. Cerrado por defecto, no abierto por descuido.
  Future<void> updateMutacionEstado({
    required String id,
    required String orgId,
    required String profileId,
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
      where: 'id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [id, orgId, profileId],
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_mutaciones');
  }

  /// Misma regla que `updateMutacionEstado`: la identidad va en el WHERE.
  Future<void> updateEvidenciaEstado({
    required String id,
    required String orgId,
    required String profileId,
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
      where: 'id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [id, orgId, profileId],
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_evidencias');
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

  // ---------------------------------------------------------------------------
  // Materiales: el kit que se lleva y lo que se gasta
  //
  // El espejo del kit y la cola de movimientos viven separados a proposito. El
  // kit es lo que dijo el servidor la ultima vez que hubo senal; la cola es lo
  // que paso despues. Mezclarlos --guardar un saldo ya descontado-- haria que
  // un reintento descontara dos veces, porque la cola volveria a aplicarse
  // sobre un numero que ya la incluia.
  //
  // Por eso `saldoLocalDe` suma las dos cosas en el momento de leer, y nunca
  // escribe el resultado.
  // ---------------------------------------------------------------------------

  /// Reemplaza el espejo del kit con lo que acaba de decir el servidor.
  ///
  /// Se borra y se reescribe en una transaccion en vez de ir fila por fila: un
  /// material que dejo de estar en el kit tiene que desaparecer, y un upsert
  /// sin borrado lo dejaria para siempre mostrando un saldo que ya no existe.
  Future<void> reemplazarKit({
    required String orgId,
    required String profileId,
    required List<Map<String, dynamic>> materiales,
  }) async {
    final db = await database;
    final ahora = DateTime.now().millisecondsSinceEpoch;

    await db.transaction((txn) async {
      await txn.delete(
        'local_kit',
        where: 'org_id = ? AND profile_id = ?',
        whereArgs: [orgId, profileId],
      );
      for (final material in materiales) {
        await txn.insert('local_kit', <String, Object?>{
          'org_id': orgId,
          'profile_id': profileId,
          'codigo': material['codigo']?.toString() ?? '',
          'nombre': material['nombre']?.toString() ?? '',
          'categoria': material['categoria']?.toString() ?? '',
          'clase': material['clase']?.toString() ?? 'consumible',
          'unidad': material['unidad']?.toString() ?? 'unidades',
          // Las cantidades se guardan como TEXTO, igual que viajan. 42.5
          // metros en coma flotante dejan de ser 42.5 en cuanto alguien suma,
          // y un saldo que falla por milesimas no se distingue de un
          // descuadre real.
          'recibido': material['recibido']?.toString() ?? '0',
          'consumido': material['consumido']?.toString() ?? '0',
          'devuelto': material['devuelto']?.toString() ?? '0',
          'disponible': material['disponible']?.toString() ?? '0',
          'series_json': jsonEncode(material['series'] ?? <String>[]),
          'acta': material['acta']?.toString() ?? '',
          'entregado_en': material['entregado_en']?.toString(),
          // La regla de cantidad viaja con el material para poder avisar sin
          // senal. Si llegara solo al sincronizar, el aviso apareceria horas
          // despues de que el material ya se gasto.
          'regla_json':
              material['regla'] == null ? null : jsonEncode(material['regla']),
          'updated_at': ahora,
        }, conflictAlgorithm: ConflictAlgorithm.replace);
      }
    });
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'local_kit');
  }

  Future<List<Map<String, dynamic>>> getKit({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    return db.query(
      'local_kit',
      where: 'org_id = ? AND profile_id = ?',
      whereArgs: [orgId, profileId],
      orderBy: 'categoria ASC, nombre ASC',
    );
  }

  /// Encola un movimiento que acaba de ocurrir.
  ///
  /// `id` es la clave de idempotencia y la pone quien llama, una sola vez: el
  /// servidor la usa para reconocer un reintento. Regenerarla al reintentar es
  /// exactamente lo que duplica un consumo, asi que no se genera aca.
  Future<void> encolarMovimientoMaterial({
    required String id,
    required String orgId,
    required String profileId,
    required String materialCodigo,
    required String tipo,
    required String cantidad,
    String materialNombre = '',
    String serie = '',
    String? ordenId,
    int? ordenNumero,
    String motivoTecnico = '',
    DateTime? ocurridoEn,
  }) async {
    final db = await database;
    await db.insert(
      'cola_movimientos_material',
      <String, Object?>{
        'id': id,
        'org_id': orgId,
        'profile_id': profileId,
        'material_codigo': materialCodigo,
        'material_nombre': materialNombre,
        'tipo': tipo,
        'cantidad': cantidad,
        'serie': serie,
        'orden_id': ordenId,
        'orden_numero': ordenNumero,
        'motivo_tecnico': motivoTecnico,
        'estado': 'pendiente',
        'intentos': 0,
        'next_attempt_at': 0,
        'ocurrido_en': (ocurridoEn ?? DateTime.now()).toIso8601String(),
        'created_at': DateTime.now().millisecondsSinceEpoch,
      },
      // Encolar dos veces el mismo id es un reintento de la pantalla, no un
      // consumo nuevo: se ignora en vez de romper.
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
    _notifyChange(
      orgId: orgId,
      profileId: profileId,
      tabla: 'cola_movimientos_material',
    );
  }

  /// Los movimientos que toca intentar ahora.
  ///
  /// `soloListosHasta` deja afuera los que estan esperando su turno despues de
  /// un fallo: sin eso, un error permanente se reintentaria en cada ciclo y
  /// gastaria la bateria de alguien que esta trabajando.
  Future<List<Map<String, dynamic>>> getMovimientosMaterialPendientes({
    required String orgId,
    required String profileId,
    int? soloListosHasta,
  }) async {
    final db = await database;
    final ahora = soloListosHasta ?? DateTime.now().millisecondsSinceEpoch;
    return db.query(
      'cola_movimientos_material',
      where: 'org_id = ? AND profile_id = ? AND estado IN (?, ?) '
          'AND next_attempt_at <= ?',
      whereArgs: [orgId, profileId, 'pendiente', 'error', ahora],
      orderBy: 'created_at ASC',
    );
  }

  /// Todo lo que esta persona tiene sin confirmar, sin importar su turno.
  ///
  /// Es lo que mira el cierre de sesion: ahi la pregunta no es "que se puede
  /// reintentar ahora" sino "que se perderia si borro".
  Future<List<Map<String, dynamic>>> getMovimientosMaterialSinConfirmar({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    return db.query(
      'cola_movimientos_material',
      where: 'org_id = ? AND profile_id = ? AND estado != ?',
      whereArgs: [orgId, profileId, 'confirmado'],
      orderBy: 'created_at ASC',
    );
  }

  /// Lo que se registro como usado en una orden concreta.
  ///
  /// Incluye lo confirmado y lo que todavia espera: para quien esta en la
  /// casa del cliente, un conector que ya puso es un conector que ya puso,
  /// haya subido o no.
  Future<List<Map<String, dynamic>>> getMovimientosMaterialDeOrden({
    required String orgId,
    required String profileId,
    required String ordenId,
  }) async {
    final db = await database;
    return db.query(
      'cola_movimientos_material',
      where: 'org_id = ? AND profile_id = ? AND orden_id = ?',
      whereArgs: [orgId, profileId, ordenId],
      orderBy: 'created_at ASC',
    );
  }

  /// Los que el servidor acepto pero con novedad: descuadre o conflicto.
  ///
  /// Estan confirmados --ya subieron-- y aun asi hay que mostrarlos: un
  /// conflicto que se resuelve solo, en silencio, es un equipo que figura
  /// instalado dos veces y nadie se entera.
  Future<List<Map<String, dynamic>>> getMovimientosMaterialConNovedad({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    return db.query(
      'cola_movimientos_material',
      where: 'org_id = ? AND profile_id = ? AND resultado IS NOT NULL '
          'AND resultado != ?',
      whereArgs: [orgId, profileId, 'aceptado'],
      orderBy: 'created_at DESC',
    );
  }

  /// Marca un grupo como "enviando", antes de salir a la red.
  ///
  /// Sirve para que la pantalla pueda distinguir lo que esta en vuelo de lo
  /// que todavia no salio, y para que un segundo ciclo de sincronizacion no
  /// vuelva a tomar lo que ya va en camino.
  Future<void> marcarMovimientosEnviando({
    required String orgId,
    required String profileId,
    required List<String> ids,
  }) async {
    if (ids.isEmpty) return;
    final db = await database;
    final marcas = List.filled(ids.length, '?').join(',');
    await db.rawUpdate(
      'UPDATE cola_movimientos_material SET estado = ? '
      'WHERE org_id = ? AND profile_id = ? AND id IN ($marcas)',
      <Object?>['enviando', orgId, profileId, ...ids],
    );
    _notifyChange(
      orgId: orgId,
      profileId: profileId,
      tabla: 'cola_movimientos_material',
    );
  }

  /// El servidor contesto por este movimiento.
  ///
  /// `resultado` es lo que dijo --aceptado, descuadre, conflicto-- y es
  /// distinto del estado de sincronizacion: los tres CONFIRMAN que el
  /// movimiento subio. Mezclarlos haria que un descuadre pareciera un fallo de
  /// red y se reintentara para siempre.
  /// El servidor aceptó —o rechazó— un movimiento.
  ///
  /// CUANDO SE ACEPTA, EL CONSUMO PASA AL KIT
  /// ----------------------------------------
  /// El saldo que ve el técnico es lo que dijo el servidor en `local_kit` más
  /// lo que todavía está en la cola sin confirmar. Al confirmar, el movimiento
  /// sale de esa cuenta — y si `local_kit` no se actualizara, el saldo
  /// **rebotaría**: dos conectores consumidos harían bajar el disponible de
  /// diez a ocho, y al volver la señal subiría solo a diez otra vez, hasta que
  /// el servidor mandara el kit recalculado.
  ///
  /// Eso es peor que un número desactualizado: es un número que se mueve sin
  /// que nadie lo haya tocado, justo en la pantalla donde alguien decide si le
  /// alcanza el material para el próximo trabajo. Y si la bajada del kit falla
  /// —sincronizar son dos peticiones, no una—, la mentira se queda.
  ///
  /// Por eso el consumo aceptado se suma acá. Cuando después baje el kit del
  /// servidor, `reemplazarKit` pisa la fila entera, así que no hay doble
  /// conteo.
  ///
  /// Lo encontró la prueba del día completo: cada pieza estaba bien y el
  /// conjunto mentía.
  Future<void> confirmarMovimientoMaterial({
    required String id,
    required String orgId,
    required String profileId,
    required String resultado,
    String motivo = '',
  }) async {
    final db = await database;

    // Qué movimiento es, antes de marcarlo: después ya no está pendiente.
    final List<Map<String, dynamic>> filas = await db.query(
      'cola_movimientos_material',
      columns: <String>['material_codigo', 'tipo', 'cantidad', 'estado'],
      where: 'id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: <Object?>[id, orgId, profileId],
      limit: 1,
    );

    await db.update(
      'cola_movimientos_material',
      <String, Object?>{
        'estado': 'confirmado',
        'resultado': resultado,
        'motivo': motivo,
        'error_mensaje': null,
        'confirmado_en': DateTime.now().millisecondsSinceEpoch,
      },
      where: 'id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [id, orgId, profileId],
    );

    // Sólo lo aceptado entra al kit. Un descuadre o un conflicto no: el
    // servidor no los contabilizó, y sumarlos acá haría que el teléfono y la
    // oficina discutan por un material que nadie sabe dónde está.
    if (resultado == 'aceptado' && filas.isNotEmpty) {
      final Map<String, dynamic> m = filas.first;
      // Si ya estaba confirmado, no se suma de nuevo: confirmar dos veces el
      // mismo movimiento es algo que un reintento puede hacer.
      if ((m['estado'] ?? '').toString() != 'confirmado') {
        await _sumarAlKit(
          db,
          orgId: orgId,
          profileId: profileId,
          codigo: (m['material_codigo'] ?? '').toString(),
          tipo: (m['tipo'] ?? '').toString(),
          cantidad: (m['cantidad'] ?? '0').toString(),
        );
      }
    }

    _notifyChange(
      orgId: orgId,
      profileId: profileId,
      tabla: 'cola_movimientos_material',
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'local_kit');
  }

  /// Traslada un movimiento ya aceptado a las cifras del kit.
  ///
  /// Las cantidades se guardan como texto, igual que viajan: convertir a coma
  /// flotante y volver hace que 42.5 metros deje de ser 42.5 en cuanto alguien
  /// suma, y un saldo que falla por milésimas no se distingue de un faltante.
  Future<void> _sumarAlKit(
    Database db, {
    required String orgId,
    required String profileId,
    required String codigo,
    required String tipo,
    required String cantidad,
  }) async {
    if (codigo.isEmpty) return;

    final List<Map<String, dynamic>> kit = await db.query(
      'local_kit',
      where: 'org_id = ? AND profile_id = ? AND codigo = ?',
      whereArgs: <Object?>[orgId, profileId, codigo],
      limit: 1,
    );
    if (kit.isEmpty) return;

    final double cuanto = double.tryParse(cantidad.trim()) ?? 0;
    if (cuanto == 0) return;

    final Map<String, Object?> cambios = <String, Object?>{};
    if (tipo == 'consumo') {
      final double antes =
          double.tryParse((kit.first['consumido'] ?? '0').toString()) ?? 0;
      cambios['consumido'] = _comoTexto(antes + cuanto);
    } else if (tipo == 'devolucion') {
      final double antes =
          double.tryParse((kit.first['devuelto'] ?? '0').toString()) ?? 0;
      cambios['devuelto'] = _comoTexto(antes + cuanto);
    } else {
      // Un ajuste lo decide el servidor con el kit completo: no se adivina.
      return;
    }

    await db.update(
      'local_kit',
      cambios,
      where: 'org_id = ? AND profile_id = ? AND codigo = ?',
      whereArgs: <Object?>[orgId, profileId, codigo],
    );
  }

  /// Un número sin cola de decimales cuando no hace falta: 8 y no 8.0.
  static String _comoTexto(double valor) =>
      valor == valor.roundToDouble() ? valor.round().toString() : '$valor';

  /// El envio fallo: se cuenta el intento y se agenda el proximo.
  ///
  /// El mensaje llega ya saneado por quien llama: en esta columna no puede
  /// terminar una URL firmada ni una cabecera de autorizacion, porque la base
  /// del telefono sobrevive al cierre de sesion mientras haya pendientes.
  Future<void> registrarFalloMovimientoMaterial({
    required String id,
    required String orgId,
    required String profileId,
    required int nextAttemptAt,
    String? errorMensaje,
  }) async {
    final db = await database;
    await db.rawUpdate(
      'UPDATE cola_movimientos_material '
      'SET intentos = intentos + 1, next_attempt_at = ?, error_mensaje = ?, '
      "estado = 'error' "
      'WHERE id = ? AND org_id = ? AND profile_id = ?',
      <Object?>[nextAttemptAt, errorMensaje, id, orgId, profileId],
    );
    _notifyChange(
      orgId: orgId,
      profileId: profileId,
      tabla: 'cola_movimientos_material',
    );
  }

  /// El saldo que se puede mostrar sin señal.
  ///
  /// Es el espejo del servidor ajustado con lo que la cola todavia no subio.
  /// Se calcula al leer y no se guarda: un saldo persistido y una cola que se
  /// reintenta se desincronizan en cuanto algo se reenvia, y despues nadie
  /// sabe cual de los dos numeros es el bueno.
  Future<double> saldoLocalDe({
    required String orgId,
    required String profileId,
    required String codigo,
  }) async {
    final db = await database;
    final filas = await db.query(
      'local_kit',
      columns: ['disponible'],
      where: 'org_id = ? AND profile_id = ? AND codigo = ?',
      whereArgs: [orgId, profileId, codigo],
      limit: 1,
    );
    var saldo = filas.isEmpty
        ? 0.0
        : double.tryParse(filas.first['disponible']?.toString() ?? '0') ?? 0.0;

    // Solo lo que el servidor todavia no confirmo: lo confirmado ya esta
    // descontado dentro de `disponible`.
    final pendientes = await db.query(
      'cola_movimientos_material',
      columns: ['tipo', 'cantidad'],
      where: 'org_id = ? AND profile_id = ? AND material_codigo = ? '
          'AND estado != ?',
      whereArgs: [orgId, profileId, codigo, 'confirmado'],
    );
    for (final fila in pendientes) {
      final cantidad =
          double.tryParse(fila['cantidad']?.toString() ?? '0') ?? 0.0;
      final tipo = fila['tipo']?.toString() ?? '';
      if (tipo == 'consumo' || tipo == 'devolucion') {
        saldo -= cantidad;
      } else if (tipo == 'ajuste') {
        saldo += cantidad;
      }
    }
    return saldo;
  }

  // ---------------------------------------------------------------------------
  // La jornada: lo que dijo el servidor, guardado para verlo sin senal
  // ---------------------------------------------------------------------------

  /// Reemplaza el espejo de la jornada con lo que acaba de contestar el
  /// servidor. Es un reemplazo y no una fusion: un dato viejo mezclado con uno
  /// nuevo daria un resumen que nunca existio.
  Future<void> guardarJornada({
    required String orgId,
    required String profileId,
    required Map<String, dynamic> datos,
  }) async {
    final db = await database;
    final resumen = datos['resumen'];
    await db.insert(
      'local_jornada',
      <String, Object?>{
        'org_id': orgId,
        'profile_id': profileId,
        'estado': (datos['estado'] ?? 'pendiente').toString(),
        'resumen_json': jsonEncode(resumen ?? <String, dynamic>{}),
        'detalle_json': jsonEncode(
          (resumen is Map ? resumen['detalle'] : null) ?? <dynamic>[],
        ),
        'series_sin_devolver_json':
            jsonEncode(datos['series_sin_devolver'] ?? <dynamic>[]),
        'transferencias_json':
            jsonEncode(datos['transferencias_pendientes'] ?? <dynamic>[]),
        'motivos_json': jsonEncode(datos['motivos'] ?? <dynamic>[]),
        'puede_cerrar': (datos['puede_cerrar'] == true) ? 1 : 0,
        'actualizado_en': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'local_jornada');
  }

  Future<Map<String, dynamic>?> getJornada({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    final filas = await db.query(
      'local_jornada',
      where: 'org_id = ? AND profile_id = ?',
      whereArgs: [orgId, profileId],
      limit: 1,
    );
    return filas.isEmpty ? null : filas.first;
  }

  /// Guarda una diferencia explicada, para que suba cuando haya senal.
  ///
  /// El motivo no puede ir vacio: una diferencia sin explicacion es
  /// exactamente lo que despues nadie puede reconstruir. Se valida aca ademas
  /// de en el servidor porque aca es donde la persona todavia esta parada
  /// frente al material.
  Future<void> encolarIncidencia({
    required String id,
    required String orgId,
    required String profileId,
    required String materialCodigo,
    required String tipo,
    required String cantidad,
    required String motivo,
    String materialNombre = '',
    String serie = '',
    DateTime? ocurridoEn,
  }) async {
    if (motivo.trim().isEmpty) {
      throw ArgumentError('Una diferencia sin motivo no se puede registrar.');
    }
    final db = await database;
    await db.insert(
      'cola_incidencias',
      <String, Object?>{
        'id': id,
        'org_id': orgId,
        'profile_id': profileId,
        'material_codigo': materialCodigo,
        'material_nombre': materialNombre,
        'tipo': tipo,
        'cantidad': cantidad,
        'serie': serie,
        'motivo': motivo.trim(),
        'estado': 'pendiente',
        'intentos': 0,
        'next_attempt_at': 0,
        'ocurrido_en': (ocurridoEn ?? DateTime.now()).toIso8601String(),
        'created_at': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_incidencias');
  }

  Future<List<Map<String, dynamic>>> getIncidenciasPendientes({
    required String orgId,
    required String profileId,
    int? soloListasHasta,
  }) async {
    final db = await database;
    final ahora = soloListasHasta ?? DateTime.now().millisecondsSinceEpoch;
    return db.query(
      'cola_incidencias',
      where: 'org_id = ? AND profile_id = ? AND estado IN (?, ?) '
          'AND next_attempt_at <= ?',
      whereArgs: [orgId, profileId, 'pendiente', 'error', ahora],
      orderBy: 'created_at ASC',
    );
  }

  Future<List<Map<String, dynamic>>> getIncidenciasSinConfirmar({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    return db.query(
      'cola_incidencias',
      where: 'org_id = ? AND profile_id = ? AND estado != ?',
      whereArgs: [orgId, profileId, 'confirmada'],
      orderBy: 'created_at ASC',
    );
  }

  /// Las diferencias explicadas de un material, hayan subido o no.
  ///
  /// La pantalla las necesita para no volver a pedir un motivo que la persona
  /// ya escribio hace cinco minutos y todavia no salio del telefono.
  Future<List<Map<String, dynamic>>> getIncidenciasDeMaterial({
    required String orgId,
    required String profileId,
    required String materialCodigo,
  }) async {
    final db = await database;
    return db.query(
      'cola_incidencias',
      where: 'org_id = ? AND profile_id = ? AND material_codigo = ?',
      whereArgs: [orgId, profileId, materialCodigo],
    );
  }

  Future<void> confirmarIncidencia({
    required String id,
    required String orgId,
    required String profileId,
    required String resultado,
    String? errorMensaje,
  }) async {
    final db = await database;
    await db.update(
      'cola_incidencias',
      <String, Object?>{
        'estado': 'confirmada',
        'resultado': resultado,
        'error_mensaje': errorMensaje,
      },
      where: 'id = ? AND org_id = ? AND profile_id = ?',
      whereArgs: [id, orgId, profileId],
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_incidencias');
  }

  Future<void> registrarFalloIncidencia({
    required String id,
    required String orgId,
    required String profileId,
    required int nextAttemptAt,
    String? errorMensaje,
  }) async {
    final db = await database;
    await db.rawUpdate(
      'UPDATE cola_incidencias SET intentos = intentos + 1, '
      "next_attempt_at = ?, error_mensaje = ?, estado = 'error' "
      'WHERE id = ? AND org_id = ? AND profile_id = ?',
      <Object?>[nextAttemptAt, errorMensaje, id, orgId, profileId],
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_incidencias');
  }

  /// El tecnico afirmo que su jornada termino, aunque no haya senal.
  ///
  /// Se guarda la hora y una clave: la jornada termina en la calle, no cuando
  /// el telefono encuentra red. Lo que NO se hace es marcarla como confirmada
  /// -- eso solo lo dice el servidor, que es quien valida que todo cuadre.
  Future<void> marcarCierreLocal({
    required String orgId,
    required String profileId,
    required String clave,
  }) async {
    final db = await database;
    await db.update(
      'local_jornada',
      <String, Object?>{
        'cierre_local_en': DateTime.now().millisecondsSinceEpoch,
        'cierre_clave': clave,
      },
      where: 'org_id = ? AND profile_id = ?',
      whereArgs: [orgId, profileId],
    );
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'local_jornada');
  }

  // ---------------------------------------------------------------------------
  // Ciclo de vida de los datos locales
  //
  // Lo que sigue existe porque cerrar sesión no borraba nada: las órdenes
  // descargadas -- con el nombre del cliente, su dirección, su teléfono y las
  // coordenadas de su casa -- se quedaban en el teléfono. El filtro por
  // (org_id, profile_id) impide *verlas* con otra cuenta, pero el archivo
  // seguía ahí, y un teléfono de cuadrilla cambia de manos.
  //
  // Borrar sin más tampoco sirve: el trabajo que todavía no subió vive en
  // estas mismas tablas, y borrarlo es destruir la jornada de alguien. Por eso
  // el borrado se pide por identidad y siempre después de contar lo pendiente.
  // ---------------------------------------------------------------------------

  /// Cada (org_id, profile_id) que dejó algo guardado en este dispositivo.
  ///
  /// Se recorren las cuatro tablas y no solo `local_ordenes`: una cuenta puede
  /// no tener órdenes cacheadas y sí una evidencia a medio subir, y esa es
  /// justamente la que no hay que perder de vista.
  Future<List<Map<String, String>>> getIdentidadesLocales() async {
    final db = await database;
    final filas = await db.rawQuery('''
      SELECT DISTINCT org_id, profile_id FROM local_ordenes
      UNION SELECT DISTINCT org_id, profile_id FROM local_datos_dirty
      UNION SELECT DISTINCT org_id, profile_id FROM cola_mutaciones
      UNION SELECT DISTINCT org_id, profile_id FROM cola_evidencias
      UNION SELECT DISTINCT org_id, profile_id FROM local_kit
      UNION SELECT DISTINCT org_id, profile_id FROM cola_movimientos_material
      UNION SELECT DISTINCT org_id, profile_id FROM local_jornada
      UNION SELECT DISTINCT org_id, profile_id FROM cola_incidencias
    ''');
    return filas
        .map((f) => <String, String>{
              'org_id': (f['org_id'] ?? '').toString(),
              'profile_id': (f['profile_id'] ?? '').toString(),
            })
        .where((f) => f['org_id']!.isNotEmpty && f['profile_id']!.isNotEmpty)
        .toList();
  }

  /// Lo pendiente de una identidad, con el detalle que hace falta para
  /// nombrarlo en pantalla: qué orden, qué acción.
  ///
  /// `getSyncCounts` devuelve números; esto devuelve las filas. A alguien que
  /// está por cerrar sesión, "4 cambios" no le dice si puede irse tranquilo:
  /// "OT #4832 · cierre" sí.
  Future<List<Map<String, dynamic>>> getMutacionesPendientesDetalle({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    return await db.rawQuery('''
      SELECT m.id, m.tipo, m.orden_id, m.estado, o.numero
      FROM cola_mutaciones m
      LEFT JOIN local_ordenes o
        ON o.id = m.orden_id AND o.org_id = m.org_id AND o.profile_id = m.profile_id
      WHERE m.org_id = ? AND m.profile_id = ?
        AND m.estado IN ('pendiente', 'conflicto', 'error_validacion')
      ORDER BY m.created_at ASC
    ''', [orgId, profileId]);
  }

  /// Las órdenes que tienen datos escritos y todavía sin subir.
  Future<List<Map<String, dynamic>>> getDatosDirtyDetalle({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    return await db.rawQuery('''
      SELECT d.orden_id, o.numero, COUNT(*) AS campos
      FROM local_datos_dirty d
      LEFT JOIN local_ordenes o
        ON o.id = d.orden_id AND o.org_id = d.org_id AND o.profile_id = d.profile_id
      WHERE d.org_id = ? AND d.profile_id = ?
      GROUP BY d.orden_id, o.numero
    ''', [orgId, profileId]);
  }

  /// Las rutas de archivo que esta identidad tiene registradas.
  ///
  /// `confirmadas: true` devuelve solo las que ya viajaron al servidor -- las
  /// únicas que se pueden borrar sin perder nada.
  Future<List<String>> getRutasDeEvidencia({
    required String orgId,
    required String profileId,
    bool? confirmadas,
  }) async {
    final db = await database;
    final filas = await db.query(
      'cola_evidencias',
      columns: ['archivo_path'],
      where: confirmadas == null
          ? 'org_id = ? AND profile_id = ?'
          : 'org_id = ? AND profile_id = ? AND subida_estado '
              '${confirmadas ? '=' : '!='} ?',
      whereArgs: <Object?>[
        orgId,
        profileId,
        if (confirmadas != null) 'confirmada',
      ],
    );
    return filas
        .map((f) => (f['archivo_path'] ?? '').toString())
        .where((r) => r.isNotEmpty)
        .toList();
  }

  /// Toda ruta de archivo registrada, de cualquier identidad.
  ///
  /// Sirve para reconocer un archivo huérfano: uno que está en el disco y que
  /// ninguna fila reclama. Un huérfano no se puede atribuir a nadie, así que
  /// tampoco se puede aislar por identidad; solo borrar.
  Future<Set<String>> getTodasLasRutasDeEvidencia() async {
    final db = await database;
    final filas = await db.query('cola_evidencias', columns: ['archivo_path']);
    return filas
        .map((f) => (f['archivo_path'] ?? '').toString())
        .where((r) => r.isNotEmpty)
        .toSet();
  }

  /// Borra de las cuatro tablas todo lo de una identidad. No toca archivos:
  /// de eso se ocupa quien sí sabe de disco, y en este orden -- primero los
  /// archivos, después las filas que los nombran -- para no dejar huérfanos.
  Future<void> borrarDatosDeIdentidad({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    await db.transaction((txn) async {
      for (final tabla in const [
        'local_ordenes',
        'local_datos_dirty',
        'cola_mutaciones',
        'cola_evidencias',
        'local_kit',
        'cola_movimientos_material',
        'local_jornada',
        'cola_incidencias',
      ]) {
        await txn.delete(
          tabla,
          where: 'org_id = ? AND profile_id = ?',
          whereArgs: [orgId, profileId],
        );
      }
    });
    _notifyChange(orgId: orgId, profileId: profileId, tabla: 'local_ordenes');
  }

  /// Borra solo las evidencias ya confirmadas de una identidad.
  ///
  /// Se usa al cerrar sesión con todo sincronizado: la foto ya está en el
  /// servidor, la copia del teléfono no agrega nada y sí es la foto de la
  /// casa de un cliente.
  Future<int> borrarEvidenciasConfirmadas({
    required String orgId,
    required String profileId,
  }) async {
    final db = await database;
    final borradas = await db.delete(
      'cola_evidencias',
      where: 'org_id = ? AND profile_id = ? AND subida_estado = ?',
      whereArgs: [orgId, profileId, 'confirmada'],
    );
    if (borradas > 0) {
      _notifyChange(orgId: orgId, profileId: profileId, tabla: 'cola_evidencias');
    }
    return borradas;
  }
}
