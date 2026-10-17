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
    this.pasos = const <dynamic>[],
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

  /// Los pasos del protocolo, tal como los declara la plantilla.
  ///
  /// Hacen falta acá —y no solo en la ficha— porque una evidencia puede decir a
  /// qué paso pertenece, y entonces la foto se toma **desde el paso**. El
  /// técnico trabaja siguiendo el protocolo: «3. Medición óptica con power
  /// meter» y «Fotografía de la medición» son lo mismo, y vivían en dos
  /// pantallas sin nada que las relacionara.
  final List<dynamic> pasos;

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
    required Map<String, dynamic> metadatosCaptura,
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

  /// Deja un reporte de seguimiento esperando turno, con las fotos de su
  /// borrador. Devuelve el id con el que quedó.
  ///
  /// `idFijo` es para el reporte que no puede repetirse —el cierre que sale de
  /// «Finalizar»—: con el mismo id no se escribe otro (17/10/2026).
  Future<String> encolarReporte({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String momento,
    required Map<String, dynamic> respuestas,
    required String borradorId,
    bool requiereNoc = false,
    bool detener = true,
    String? idFijo,
  });

  /// Si ya hay un reporte con ese id en el teléfono.
  Future<bool> existeReporte(String id);

  /// El seguimiento de la orden —sobre todo sus `formularios`, que dicen qué
  /// pide cada reporte—: primero el espejo del teléfono, después la red.
  Future<Map<String, dynamic>?> seguimiento(String ordenId);
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
      pasos: jsonDecode(orden['pasos_json'] as String? ?? '[]') as List<dynamic>,
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
    required Map<String, dynamic> metadatosCaptura,
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
        metadatosCaptura: metadatosCaptura,
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

  @override
  Future<String> encolarReporte({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String momento,
    required Map<String, dynamic> respuestas,
    required String borradorId,
    bool requiereNoc = false,
    bool detener = true,
    String? idFijo,
  }) async {
    final String reporteId = await _db.encolarSeguimiento(
      ordenId: ordenId,
      orgId: orgId,
      profileId: profileId,
      momento: momento,
      respuestas: respuestas,
      requiereNoc: requiereNoc,
      detener: detener,
      idFijo: idFijo,
    );
    // Las fotos del borrador pasan a ser de este reporte: es lo que permite que
    // la sincronización las encuentre cuando el servidor devuelva el evento.
    await _db.reasignarEvidenciasDeBorrador(
      borradorId: borradorId,
      reporteLocalId: reporteId,
      orgId: orgId,
      profileId: profileId,
    );
    return reporteId;
  }

  @override
  Future<bool> existeReporte(String id) => _db.existeSeguimiento(id);

  /// Espejo primero, red después: si se pidiera la red primero, un técnico sin
  /// señal esperaría el timeout completo mirando una pantalla sin botones,
  /// teniendo el dato guardado en el teléfono. Movido tal cual de la pantalla.
  @override
  Future<Map<String, dynamic>?> seguimiento(String ordenId) async {
    final String? orgId = await _storage.getOrgId();
    if (orgId == null) return null;
    final Map<String, dynamic>? local =
        await _db.leerSeguimiento(ordenId: ordenId, orgId: orgId);
    final bool actualizo =
        await _cola.descargarSeguimientoDeOrden(ordenId: ordenId, orgId: orgId);
    if (!actualizo) return local;
    return await _db.leerSeguimiento(ordenId: ordenId, orgId: orgId) ?? local;
  }
}

/// Las fotos de un paso del protocolo.
///
/// Si ninguna evidencia declara su paso, [titulo] queda vacío y entra todo en un
/// solo grupo: la pantalla se dibuja como siempre. Agrupar por paso es algo que
/// **cada empresa decide en su plantilla**, no el código.
class GrupoDeEvidencias {
  const GrupoDeEvidencias({required this.titulo, required this.requisitos});

  /// El título del paso, o vacío cuando el grupo no pertenece a ninguno.
  final String titulo;

  final List<dynamic> requisitos;
}

/// Agrupa las evidencias por el paso del protocolo que las pide.
///
/// POR QUE ESTO ES UNA FUNCION Y NO UN `for` DENTRO DEL WIDGET
/// -----------------------------------------------------------
/// Porque decide, y lo que decide hay que poder medirlo sin emulador: el orden
/// de los grupos, qué pasa con una evidencia sin paso, y qué pasa con un paso
/// que no pide ninguna foto.
///
/// REGLAS, Y CADA UNA TIENE UN MOTIVO
/// ----------------------------------
/// * Los grupos salen **en el orden del protocolo**, no en el de las
///   evidencias. El técnico recorre el protocolo de arriba abajo.
/// * Un paso sin fotos **no se dibuja**. Un encabezado vacío debajo de otro
///   encabezado vacío convierte la pantalla en una lista de títulos.
/// * Las evidencias sin paso van **al final**, juntas y sin encabezado. Mezclar
///   las sueltas con las de un paso diría que pertenecen a ese paso.
/// * Si NINGUNA declara paso, devuelve un solo grupo sin título: exactamente lo
///   que se dibujaba antes de esto.
List<GrupoDeEvidencias> agruparPorPaso({
  required List<dynamic> requisitos,
  required List<dynamic> pasos,
}) {
  // SIN ATAJO PARA EL CASO «NADIE DECLARA PASO».
  //
  // Habia uno --`if (!algunaDeclara) return [un grupo]`-- y al mutarlo la
  // prueba siguio en VERDE: el camino general ya produce exactamente eso.
  // Ninguna evidencia encuentra su paso, ningun grupo se arma, y todas caen en
  // las sueltas, que es un solo grupo sin titulo.
  //
  // Se quito. Un atajo que no cambia el resultado es una segunda implementacion
  // del mismo comportamiento esperando a divergir.
  final List<GrupoDeEvidencias> grupos = <GrupoDeEvidencias>[];
  final Set<String> usados = <String>{};

  for (final dynamic paso in pasos) {
    if (paso is! Map) continue;
    final String id = (paso['id'] ?? '').toString();
    if (id.isEmpty) continue;
    final List<dynamic> suyas = <dynamic>[
      for (final dynamic r in requisitos)
        if (r is Map && (r['paso'] ?? '').toString() == id) r,
    ];
    if (suyas.isEmpty) continue;
    usados.add(id);
    grupos.add(GrupoDeEvidencias(
      titulo: (paso['titulo'] ?? '').toString(),
      requisitos: suyas,
    ));
  }

  final List<dynamic> sueltas = <dynamic>[
    for (final dynamic r in requisitos)
      if (r is! Map || !usados.contains((r['paso'] ?? '').toString())) r,
  ];
  if (sueltas.isNotEmpty) {
    grupos.add(GrupoDeEvidencias(titulo: '', requisitos: sueltas));
  }
  return grupos;
}


/// Un paso de la intervención, con lo que se registra en él.
class PasoDeEjecucion {
  const PasoDeEjecucion({
    required this.id,
    required this.titulo,
    required this.campos,
    required this.evidencias,
    this.descripcion = '',
  });

  /// El id del paso en la plantilla, o vacío para «Otros datos».
  final String id;
  final String titulo;
  final String descripcion;

  /// Los campos CRUDOS de este paso, tal como los mandó la plantilla. Quien los
  /// dibuja los normaliza con el mismo lector que el resto de la pantalla.
  final List<dynamic> campos;

  /// Las fotos que este paso pide. La firma no entra: es del cierre.
  final List<dynamic> evidencias;
}

/// Reparte los campos y las fotos de la plantilla en sus pasos.
///
/// POR QUÉ (17/10/2026)
/// --------------------
/// La pantalla de ejecución estaba ordenada por tipo de registro —todos los
/// datos, después todas las fotos, después el material—, que es el orden de la
/// base y no el del trabajo. La plantilla ya dice en qué paso va cada cosa
/// («Correctivo» trae «Diagnóstico» y «Solución»): con eso, el técnico tiene en
/// un mismo lugar la instrucción, el dato y la foto de lo que está haciendo.
///
/// LAS REGLAS
/// ----------
/// * Los pasos salen en el orden del protocolo. Los pasos son los de la
///   plantilla real: la app no trae ningún protocolo propio.
/// * Un paso sin campos ni fotos no aparece: sería un título sin nada que hacer.
/// * Lo que no declara paso va a un último paso, «Otros datos». Mezclarlo con un
///   paso diría que pertenece a él.
/// * Si NINGÚN campo ni foto declara un paso que exista, devuelve una lista
///   vacía: la plantilla no está organizada por pasos y la pantalla se dibuja
///   como siempre. Las plantillas sin pasos no cambian.
List<PasoDeEjecucion> pasosDeEjecucion({
  required List<dynamic> campos,
  required List<dynamic> requisitos,
  required List<dynamic> pasos,
}) {
  bool esFirma(dynamic r) => r is Map && (r['tipo'] ?? '').toString() == 'firma';
  String pasoDe(dynamic x) => x is Map ? (x['paso'] ?? '').toString() : '';
  final List<dynamic> fotos = <dynamic>[
    for (final dynamic r in requisitos)
      if (!esFirma(r)) r,
  ];

  final List<PasoDeEjecucion> salida = <PasoDeEjecucion>[];
  final Set<String> usados = <String>{};
  for (final dynamic paso in pasos) {
    if (paso is! Map) continue;
    final String id = (paso['id'] ?? '').toString();
    if (id.isEmpty) continue;
    final List<dynamic> susCampos = <dynamic>[
      for (final dynamic c in campos)
        if (pasoDe(c) == id) c,
    ];
    final List<dynamic> susFotos = <dynamic>[
      for (final dynamic r in fotos)
        if (pasoDe(r) == id) r,
    ];
    if (susCampos.isEmpty && susFotos.isEmpty) continue;
    usados.add(id);
    salida.add(PasoDeEjecucion(
      id: id,
      titulo: (paso['titulo'] ?? '').toString(),
      descripcion: (paso['descripcion'] ?? paso['instrucciones'] ?? '').toString(),
      campos: susCampos,
      evidencias: susFotos,
    ));
  }
  if (salida.isEmpty) return const <PasoDeEjecucion>[];

  final List<dynamic> camposSueltos = <dynamic>[
    for (final dynamic c in campos)
      if (!usados.contains(pasoDe(c))) c,
  ];
  final List<dynamic> fotosSueltas = <dynamic>[
    for (final dynamic r in fotos)
      if (!usados.contains(pasoDe(r))) r,
  ];
  if (camposSueltos.isNotEmpty || fotosSueltas.isNotEmpty) {
    salida.add(PasoDeEjecucion(
      id: '',
      titulo: 'Otros datos',
      campos: camposSueltos,
      evidencias: fotosSueltas,
    ));
  }
  return salida;
}
