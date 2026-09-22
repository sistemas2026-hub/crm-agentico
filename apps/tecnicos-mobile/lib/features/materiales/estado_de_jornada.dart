import 'dart:convert';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';

/// Cómo va la jornada, según el servidor y ajustado con lo que no subió.
///
/// DE DÓNDE SALE CADA NÚMERO
/// -------------------------
/// De `local_jornada`, que es el espejo de lo que calculó el dominio. Acá no
/// se recalcula nada: los números de la jornada los hace el mismo código que
/// después firma el acta, y una segunda cuenta en el teléfono solo serviría
/// para que algún día las dos difieran y nadie sepa cuál creer.
///
/// Lo único que se suma por cuenta propia es **lo que todavía no subió**, y
/// solo para no mostrarle al técnico un saldo de hace dos horas. Esa suma es
/// explícita y está aislada acá: no se mezcla con lo que dijo el servidor.
class EstadoDeJornada {
  const EstadoDeJornada({
    required this.recibido,
    required this.consumido,
    required this.aDevolver,
    required this.devuelto,
    required this.diferencias,
    required this.ordenesAsignadas,
    required this.ordenesCompletadas,
    required this.materiales,
    required this.transferencias,
    required this.motivos,
    required this.sinSubir,
    required this.cerrada,
    required this.hayJornada,
    this.cierreTomado = false,
  });

  const EstadoDeJornada.vacio()
      : recibido = '0',
        consumido = '0',
        aDevolver = '0',
        devuelto = '0',
        diferencias = 0,
        ordenesAsignadas = 0,
        ordenesCompletadas = 0,
        materiales = const <MaterialDeJornada>[],
        transferencias = const <TransferenciaPendiente>[],
        motivos = const <String>[],
        sinSubir = 0,
        cerrada = false,
        hayJornada = false,
        cierreTomado = false;

  final String recibido;
  final String consumido;
  final String aDevolver;
  final String devuelto;
  final int diferencias;
  final int ordenesAsignadas;
  final int ordenesCompletadas;
  final List<MaterialDeJornada> materiales;
  final List<TransferenciaPendiente> transferencias;

  /// Lo que impide cerrar, en frases. Las escribe el servidor.
  final List<String> motivos;

  /// Movimientos que todavía esperan señal. No bloquean.
  final int sinSubir;

  final bool cerrada;
  final bool hayJornada;

  /// El técnico ya dijo que terminó, pero el servidor todavía no lo confirmó.
  ///
  /// Se distingue de `cerrada` a propósito: una jornada cerrada tiene un acta
  /// con números congelados; una tomada es una intención que viaja en la cola.
  /// Decirle "cerrada" a la segunda sería afirmar algo que no pasó.
  final bool cierreTomado;

  int get ordenesPendientes => ordenesAsignadas - ordenesCompletadas;

  /// Si se puede afirmar que la jornada terminó.
  ///
  /// La señal NO entra en esta decisión. Lo que bloquea es que la jornada se
  /// contradiga —una diferencia sin explicar, un equipo sin ubicar—, no que el
  /// teléfono esté sin red: eso se resuelve solo, y esperar a que se resuelva
  /// dejaría a alguien sin poder irse a su casa.
  bool get puedeCerrar =>
      hayJornada && !cerrada && !cierreTomado && motivos.isEmpty;

  static Future<EstadoDeJornada> leer({
    LocalDatabase? baseLocal,
    SecureStorageLectura? almacenamiento,
  }) async {
    final db = baseLocal ?? LocalDatabase();
    final storage = almacenamiento ?? SecureStorageService();

    String? orgId;
    String? profileId;
    try {
      orgId = await storage.getOrgId();
      profileId = await storage.getProfileId();
    } catch (_) {
      return const EstadoDeJornada.vacio();
    }
    if (orgId == null || orgId.isEmpty || profileId == null || profileId.isEmpty) {
      return const EstadoDeJornada.vacio();
    }

    Map<String, dynamic>? fila;
    List<Map<String, dynamic>> pendientes = const <Map<String, dynamic>>[];
    try {
      fila = await db.getJornada(orgId: orgId, profileId: profileId);
      pendientes = await db.getMovimientosMaterialSinConfirmar(
        orgId: orgId,
        profileId: profileId,
      );
    } catch (_) {
      return const EstadoDeJornada.vacio();
    }
    if (fila == null) return const EstadoDeJornada.vacio();

    final resumen = _mapa(fila['resumen_json']);
    final material = _mapa(resumen['material']);
    final ordenes = _mapa(resumen['ordenes']);
    final detalle = _lista(fila['detalle_json']);

    // Lo devuelto por material incluye lo que espera turno: si no, el técnico
    // devuelve siete conectores, no ve el cambio, y los devuelve otra vez.
    final devueltoSinSubir = <String, double>{};
    for (final m in pendientes) {
      if ((m['tipo'] ?? '') != 'devolucion') continue;
      final codigo = (m['material_codigo'] ?? '').toString();
      devueltoSinSubir[codigo] =
          (devueltoSinSubir[codigo] ?? 0) + _numero(m['cantidad']);
    }

    final materiales = <MaterialDeJornada>[
      for (final d in detalle)
        if (d is Map)
          MaterialDeJornada.desde(
            Map<String, dynamic>.from(d),
            devueltoSinSubir: devueltoSinSubir[(d['codigo'] ?? '').toString()] ?? 0,
          ),
    ];

    return EstadoDeJornada(
      recibido: (material['recibido'] ?? '0').toString(),
      consumido: (material['consumido'] ?? '0').toString(),
      aDevolver: (material['a_devolver'] ?? '0').toString(),
      devuelto: (material['devuelto'] ?? '0').toString(),
      diferencias: materiales.where((m) => m.diferencia != 0).length,
      ordenesAsignadas: (ordenes['asignadas'] as int?) ?? 0,
      ordenesCompletadas: (ordenes['completadas'] as int?) ?? 0,
      materiales: materiales,
      transferencias: <TransferenciaPendiente>[
        for (final t in _lista(fila['transferencias_json']))
          if (t is Map)
            TransferenciaPendiente(
              material: (t['material_nombre'] ?? t['material'] ?? '').toString(),
              cantidad: (t['cantidad'] ?? '').toString(),
              recibe: (t['recibe'] ?? '').toString(),
            ),
      ],
      motivos: <String>[
        for (final m in _lista(fila['motivos_json'])) m.toString(),
      ],
      sinSubir: pendientes.length,
      cerrada: (fila['estado'] ?? '') == 'confirmada',
      hayJornada: true,
      cierreTomado: fila['cierre_local_en'] != null,
    );
  }

  static Map<String, dynamic> _mapa(Object? crudo) {
    if (crudo is Map) return Map<String, dynamic>.from(crudo);
    if (crudo is String && crudo.isNotEmpty) {
      try {
        final datos = jsonDecode(crudo);
        if (datos is Map) return Map<String, dynamic>.from(datos);
      } catch (_) {
        // Un espejo ilegible se trata como vacío: mejor decir que no hay
        // jornada que mostrar números a medias.
      }
    }
    return <String, dynamic>{};
  }

  static List<dynamic> _lista(Object? crudo) {
    if (crudo is List) return crudo;
    if (crudo is String && crudo.isNotEmpty) {
      try {
        final datos = jsonDecode(crudo);
        if (datos is List) return datos;
      } catch (_) {
        // Igual que arriba.
      }
    }
    return const <dynamic>[];
  }

  static double _numero(Object? valor) =>
      double.tryParse(valor?.toString() ?? '0') ?? 0;
}

/// Una línea de la conciliación, tal como la calculó el servidor.
class MaterialDeJornada {
  const MaterialDeJornada({
    required this.codigo,
    required this.nombre,
    required this.unidad,
    required this.esperado,
    required this.devuelto,
    required this.diferencia,
    required this.porDevolver,
    this.serie,
  });

  factory MaterialDeJornada.desde(
    Map<String, dynamic> datos, {
    double devueltoSinSubir = 0,
  }) {
    final esperado = EstadoDeJornada._numero(datos['esperado_devolver']);
    final devuelto =
        EstadoDeJornada._numero(datos['devuelto']) + devueltoSinSubir;
    final serie = (datos['serie'] ?? '').toString();

    return MaterialDeJornada(
      codigo: (datos['codigo'] ?? '').toString(),
      nombre: (datos['nombre'] ?? datos['codigo'] ?? '').toString(),
      unidad: (datos['unidad'] ?? 'unidades').toString(),
      esperado: _texto(esperado),
      devuelto: _texto(devuelto),
      diferencia: esperado - devuelto,
      porDevolver: esperado - devuelto > 0 ? esperado - devuelto : 0,
      serie: serie.isEmpty ? null : serie,
    );
  }

  final String codigo;
  final String nombre;
  final String unidad;
  final String esperado;
  final String devuelto;

  /// Lo que falta por devolver. Cero es lo normal.
  final double diferencia;

  /// Cuánto se ofrecería devolver de un toque.
  final double porDevolver;

  /// Solo para equipos con número. Nunca se muestran como cantidad suelta.
  final String? serie;

  static String _texto(double valor) => valor == valor.roundToDouble()
      ? valor.round().toString()
      : valor.toString();
}

/// Material que se le pasó a otro y todavía no aceptó.
class TransferenciaPendiente {
  const TransferenciaPendiente({
    required this.material,
    required this.cantidad,
    required this.recibe,
  });

  final String material;
  final String cantidad;
  final String recibe;
}
