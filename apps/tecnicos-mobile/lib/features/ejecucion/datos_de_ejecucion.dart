import 'dart:convert';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';
import 'campo_del_formulario.dart';
import 'cierre_de_orden.dart';

/// Lo que la pantalla de ejecución necesita para dibujarse, ya leído.
///
/// POR QUÉ EXISTE ESTE OBJETO
/// --------------------------
/// Hasta acá la pantalla leía ella misma de SQLite y del almacenamiento
/// seguro. Eso la volvía imposible de montar en una prueba o en una captura:
/// había que levantar la base entera, y mezclar eso con pruebas de widget ya
/// colgó la suite una vez en este proyecto.
///
/// El corte es por **dónde vienen los datos**, no por capas abstractas: la
/// pantalla recibe esto armado y no sabe si salió de la base del teléfono o
/// de un fixture. Las reglas que derivan de estos datos —si falta firma, qué
/// campos obligatorios están vacíos— viven acá y no en el widget, porque son
/// las que hay que poder probar sin emulador.
class DatosDeEjecucion {
  const DatosDeEjecucion({
    required this.orgId,
    required this.profileId,
    required this.orden,
    required this.campos,
    required this.requisitosDeEvidencia,
    required this.valores,
    required this.evidenciasCapturadas,
    required this.materialesUsados,
  });

  /// El caso en que no hay nada que dibujar: sin identidad o sin la orden en
  /// la base. La pantalla muestra su estado de carga y no inventa una orden.
  static const DatosDeEjecucion? ninguno = null;

  final String orgId;
  final String profileId;

  /// La fila de la orden, tal como está en la base.
  final Map<String, dynamic> orden;

  /// Los campos del formulario que pide la plantilla.
  final List<dynamic> campos;

  /// Las evidencias que pide la plantilla: fotos y, si corresponde, la firma.
  final List<dynamic> requisitosDeEvidencia;

  /// Lo que ya se respondió, mezclando lo del servidor con lo escrito acá.
  final Map<String, dynamic> valores;

  /// Las evidencias que ya se capturaron en el teléfono.
  final List<Map<String, dynamic>> evidenciasCapturadas;

  /// El material que se registró contra esta orden.
  final List<Map<String, dynamic>> materialesUsados;

  int? get numeroDeOrden {
    final dynamic n = orden['numero'];
    if (n is int) return n;
    return int.tryParse(n?.toString() ?? '');
  }

  int get revision => orden['revision'] as int? ?? 0;

  // --- Reglas derivadas ----------------------------------------------------
  // Estaban dentro del widget. No dibujan nada: deciden si el trabajo se
  // puede cerrar, que es lo que más importa probar de esta pantalla.

  /// El requisito de firma, si la plantilla lo pide.
  Map<String, dynamic>? get requisitoDeFirma {
    for (final dynamic req in requisitosDeEvidencia) {
      if (req is Map && (req['tipo'] ?? '').toString() == 'firma') {
        return Map<String, dynamic>.from(req);
      }
    }
    return null;
  }

  bool get exigeFirma => requisitoDeFirma != null;

  bool get hayFirma {
    final Map<String, dynamic>? requisito = requisitoDeFirma;
    if (requisito == null) return false;
    return evidenciasCapturadas
        .any((Map<String, dynamic> e) => e['requisito_id'] == requisito['id']);
  }

  /// La firma existe pero todavía no la confirmó el servidor.
  bool get firmaSinSubir {
    final Map<String, dynamic>? requisito = requisitoDeFirma;
    if (requisito == null) return false;
    return evidenciasCapturadas.any((Map<String, dynamic> e) =>
        e['requisito_id'] == requisito['id'] &&
        (e['subida_estado'] ?? '') != 'confirmada');
  }

  /// Los campos del formulario, ya interpretados.
  ///
  /// Una sola lectura del esquema para todos: el formulario que se dibuja, el
  /// checklist de cierre y la validación. Antes cada uno lo leía a su manera y
  /// no coincidían — ver `campo_del_formulario.dart`.
  List<CampoDelFormulario> get camposNormalizados =>
      CampoDelFormulario.normalizar(campos, valores);

  /// Lo que impide cerrar, por el lado de los datos.
  ///
  /// Incluye los obligatorios sin responder y también los que tienen un valor
  /// que no sirve: un número fuera del rango que pide el esquema se firma como
  /// si fuera una medición buena, así que no puede pasar por completo.
  List<String> get camposObligatoriosSinLlenar => <String>[
        for (final CampoDelFormulario campo in camposNormalizados)
          if (campo.bloqueaCierre) campo.titulo,
      ];

  /// Si el trabajo se puede dar por terminado, y qué falta si no.
  ///
  /// La decisión la toma `CierreDeOrden`, que ya vivía aparte: acá sólo se le
  /// pasan los datos que tiene esta pantalla.
  CierreDeOrden get cierre => CierreDeOrden.evaluar(
        camposObligatoriosSinLlenar: camposObligatoriosSinLlenar,
        requisitosDeFoto: <dynamic>[
          for (final dynamic r in requisitosDeEvidencia)
            if (!(r is Map && (r['tipo'] ?? '').toString() == 'firma')) r,
        ],
        fotosCapturadas: evidenciasCapturadas,
        materialesRegistrados: materialesUsados,
        exigeFirma: exigeFirma,
        hayFirma: hayFirma,
        firmaSinSubir: firmaSinSubir,
      );

  DatosDeEjecucion copiaCon({
    Map<String, dynamic>? valores,
    List<Map<String, dynamic>>? evidenciasCapturadas,
    List<Map<String, dynamic>>? materialesUsados,
  }) =>
      DatosDeEjecucion(
        orgId: orgId,
        profileId: profileId,
        orden: orden,
        campos: campos,
        requisitosDeEvidencia: requisitosDeEvidencia,
        valores: valores ?? this.valores,
        evidenciasCapturadas: evidenciasCapturadas ?? this.evidenciasCapturadas,
        materialesUsados: materialesUsados ?? this.materialesUsados,
      );
}

/// De dónde salen y a dónde van los datos de la ejecución.
///
/// La pantalla habla con esto y no con la base. En la aplicación la
/// implementación es [FuenteLocalDeEjecucion]; en una prueba o una captura se
/// pasa otra, y el dibujo es el mismo.
abstract class FuenteDeEjecucion {
  /// Todo lo de la orden, o `null` si no hay identidad o la orden no está.
  Future<DatosDeEjecucion?> cargar(String ordenId);

  /// Guarda una respuesta apenas se escribe. No espera a nada.
  Future<void> guardarCampo({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String clave,
    required dynamic valor,
  });

  /// Deja una foto o una firma esperando turno para subir.
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
    required String registroIdempotencyKey,
    required String confirmacionIdempotencyKey,
    required DateTime capturadaEn,
  });

  Future<List<Map<String, dynamic>>> evidenciasDe({
    required String orgId,
    required String profileId,
    required String ordenId,
  });

  Future<List<Map<String, dynamic>>> materialesDe({
    required String orgId,
    required String profileId,
    required String ordenId,
  });

  /// Marca la orden como terminada en el teléfono y encola el aviso.
  Future<void> transicionar({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String nuevoEstadoLocal,
    required String tipoAccion,
    required int revisionBase,
    required String idempotencyKey,
  });

  /// Que la cola vuelva a contar lo pendiente.
  void refrescarResumen();

  /// Intentar enviar ahora, sin bloquear a nadie si no hay señal.
  void procesarCola();
}

/// La fuente de verdad: la base del teléfono y la sesión guardada.
///
/// Es el mismo código que estaba dentro de la pantalla, movido tal cual. No
/// cambia ninguna consulta ni ningún orden de operaciones.
class FuenteLocalDeEjecucion implements FuenteDeEjecucion {
  FuenteLocalDeEjecucion({
    LocalDatabase? baseLocal,
    SecureStorageLectura? almacenamiento,
    SyncQueueService? cola,
  })  : _db = baseLocal ?? LocalDatabase(),
        _storage = almacenamiento ?? SecureStorageService(),
        _colaDada = cola;

  final LocalDatabase _db;
  final SecureStorageLectura _storage;
  final SyncQueueService? _colaDada;

  /// La cola se crea recién cuando hace falta.
  ///
  /// Construirla al instante tiene efecto: su constructor se suscribe a los
  /// cambios de la base y consulta el almacenamiento seguro. En una prueba
  /// contra SQLite eso explota con MissingPluginException al primer write,
  /// aunque nadie haya pedido sincronizar nada.
  late final SyncQueueService _cola = _colaDada ?? SyncQueueService();

  @override
  Future<DatosDeEjecucion?> cargar(String ordenId) async {
    final String? orgId = await _storage.getOrgId();
    final String? profileId = await _storage.getProfileId();
    if (orgId == null || profileId == null) return null;

    final Map<String, dynamic>? orden = await _db.getOrden(
      orgId: orgId,
      profileId: profileId,
      id: ordenId,
    );
    if (orden == null) return null;

    final String camposStr =
        orden['formulario_campos_json'] as String? ?? '[]';
    final String evidenciasStr =
        orden['formulario_evidencias_json'] as String? ?? '[]';

    return DatosDeEjecucion(
      orgId: orgId,
      profileId: profileId,
      orden: orden,
      campos: jsonDecode(camposStr) as List<dynamic>,
      requisitosDeEvidencia: jsonDecode(evidenciasStr) as List<dynamic>,
      valores: await _db.getMergedDatosOrden(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
      ),
      materialesUsados: await _db.getMovimientosMaterialDeOrden(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
      ),
      evidenciasCapturadas: await _db.getEvidenciasOrden(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
      ),
    );
  }

  @override
  Future<void> guardarCampo({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String clave,
    required dynamic valor,
  }) =>
      _db.saveDatoCampo(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
        campoClave: clave,
        valor: valor,
      );

  @override
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
    required String registroIdempotencyKey,
    required String confirmacionIdempotencyKey,
    required DateTime capturadaEn,
  }) =>
      _db.encolarEvidencia(
        id: id,
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
        requisitoId: requisitoId,
        archivoPath: archivoPath,
        sha256: sha256,
        tamanoBytes: tamanoBytes,
        mimeType: mimeType,
        registroIdempotencyKey: registroIdempotencyKey,
        confirmacionIdempotencyKey: confirmacionIdempotencyKey,
        capturadaEn: capturadaEn,
      );

  @override
  Future<List<Map<String, dynamic>>> evidenciasDe({
    required String orgId,
    required String profileId,
    required String ordenId,
  }) =>
      _db.getEvidenciasOrden(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
      );

  @override
  Future<List<Map<String, dynamic>>> materialesDe({
    required String orgId,
    required String profileId,
    required String ordenId,
  }) =>
      _db.getMovimientosMaterialDeOrden(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
      );

  @override
  Future<void> transicionar({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String nuevoEstadoLocal,
    required String tipoAccion,
    required int revisionBase,
    required String idempotencyKey,
  }) =>
      _db.transicionarEstadoLocal(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
        nuevoEstadoLocal: nuevoEstadoLocal,
        tipoAccion: tipoAccion,
        revisionBase: revisionBase,
        idempotencyKey: idempotencyKey,
      );

  @override
  void refrescarResumen() => _cola.refreshSyncSummary();

  @override
  void procesarCola() => _cola.procesarCola();
}
