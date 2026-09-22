import 'dart:convert';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import 'material_en_custodia.dart';

/// Lo que el técnico tiene a cargo, leído de la base del teléfono.
///
/// POR QUÉ ESTO EXISTE
/// -------------------
/// La pantalla de materiales dibujaba un catálogo de ejemplo. Ahora hay
/// custodia de verdad —entregas, consumos, devoluciones, una cola que sube sin
/// señal— y esta clase es el puente: convierte lo que guarda la base en la
/// misma forma que la pantalla ya sabía dibujar.
///
/// EL SALDO SE ARMA AL LEER
/// ------------------------
/// `local_kit` es lo que dijo el servidor la última vez que hubo señal, y la
/// cola es lo que pasó después. Lo que se muestra son las dos cosas sumadas en
/// este momento, nunca un número guardado: un contador y una cola que
/// reintenta se desincronizan en cuanto algo se reenvía, y a partir de ahí
/// nadie sabe cuál de los dos es el bueno.
///
/// Por eso el técnico ve el descuento apenas registra el consumo, esté o no
/// conectado. Si tuviera que esperar a la sincronización para ver su saldo,
/// llegaría a la siguiente casa creyendo que tiene material que ya gastó.
class KitDeJornada {
  const KitDeJornada({
    required this.materiales,
    required this.acta,
    required this.sinSubir,
    required this.conNovedad,
  });

  const KitDeJornada.vacio()
      : materiales = const <MaterialEnCustodia>[],
        acta = '',
        sinSubir = 0,
        conNovedad = const <MovimientoConNovedad>[];

  final List<MaterialEnCustodia> materiales;

  /// El acta con la que la bodega entregó este kit.
  final String acta;

  /// Cuántos movimientos esperan turno para subir.
  final int sinSubir;

  /// Lo que el servidor aceptó pero marcó: descuadres y conflictos.
  final List<MovimientoConNovedad> conNovedad;

  bool get hayAlgo => materiales.isNotEmpty;

  static Future<KitDeJornada> leer({
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
      // Sin acceso al almacenamiento seguro no hay identidad, y sin identidad
      // no hay kit que mostrar. Se devuelve vacio en vez de propagar: una
      // pantalla que no puede leer tiene que decir que no hay nada, no
      // quedarse girando para siempre.
      return const KitDeJornada.vacio();
    }
    if (orgId == null || orgId.isEmpty || profileId == null || profileId.isEmpty) {
      return const KitDeJornada.vacio();
    }

    final List<Map<String, dynamic>> filas;
    final List<Map<String, dynamic>> sinConfirmar;
    final List<Map<String, dynamic>> novedades;
    try {
      filas = await db.getKit(orgId: orgId, profileId: profileId);
      sinConfirmar = await db.getMovimientosMaterialSinConfirmar(
        orgId: orgId,
        profileId: profileId,
      );
      novedades = await db.getMovimientosMaterialConNovedad(
        orgId: orgId,
        profileId: profileId,
      );
    } catch (_) {
      return const KitDeJornada.vacio();
    }

    final materiales = <MaterialEnCustodia>[];
    for (final fila in filas) {
      final codigo = (fila['codigo'] ?? '').toString();
      final unidad = (fila['unidad'] ?? 'unidades').toString();

      // Lo consumido incluye lo que todavía no subió: para quien está en la
      // calle, un conector que ya puso es un conector que ya no tiene.
      final consumidoServidor = _numero(fila['consumido']);
      final pendientePropio = sinConfirmar
          .where((m) => (m['material_codigo'] ?? '').toString() == codigo)
          .fold<double>(0, (suma, m) {
        final tipo = (m['tipo'] ?? '').toString();
        final cantidad = _numero(m['cantidad']);
        // Consumir y devolver sacan material de la camioneta; un ajuste lo
        // suma. Es la misma cuenta que hace `saldoLocalDe`.
        if (tipo == 'consumo' || tipo == 'devolucion') return suma + cantidad;
        return suma - cantidad;
      });

      final series = <String>[];
      final crudo = fila['series_json'];
      if (crudo is String && crudo.isNotEmpty) {
        try {
          final lista = jsonDecode(crudo);
          if (lista is List) {
            series.addAll(lista.map((s) => s.toString()));
          }
        } catch (_) {
          // Una lista ilegible no puede tumbar la pantalla: se muestra el
          // material sin sus números, que es mejor que no mostrarlo.
        }
      }

      materiales.add(MaterialEnCustodia(
        categoria: (fila['categoria'] ?? '').toString(),
        nombre: (fila['nombre'] ?? codigo).toString(),
        detalle: codigo,
        clase: _clase((fila['clase'] ?? '').toString()),
        recibidos: _numero(fila['recibido']).round(),
        usados: (consumidoServidor + pendientePropio).round(),
        unidad: unidad,
        serie: series.isEmpty ? null : series.first,
      ));
    }

    return KitDeJornada(
      materiales: materiales,
      acta: filas.isEmpty ? '' : (filas.first['acta'] ?? '').toString(),
      sinSubir: sinConfirmar.length,
      conNovedad: <MovimientoConNovedad>[
        for (final m in novedades)
          MovimientoConNovedad(
            material: (m['material_nombre'] ?? m['material_codigo'] ?? '')
                .toString(),
            cantidad: (m['cantidad'] ?? '').toString(),
            resultado: (m['resultado'] ?? '').toString(),
            motivo: (m['motivo'] ?? '').toString(),
            ordenNumero: m['orden_numero'] as int?,
          ),
      ],
    );
  }

  static double _numero(Object? valor) =>
      double.tryParse(valor?.toString() ?? '0') ?? 0;

  static ClaseMaterial _clase(String valor) => switch (valor) {
        'bobina' => ClaseMaterial.bobina,
        'serializado' => ClaseMaterial.serializado,
        'terminal' => ClaseMaterial.terminal,
        _ => ClaseMaterial.consumible,
      };
}

/// Un movimiento que subió, pero con algo que alguien tiene que mirar.
///
/// Se muestra aunque ya esté confirmado: un descuadre que se resuelve en
/// silencio es un faltante que aparece en el conteo del mes que viene, y un
/// conflicto silencioso es un equipo figurando instalado dos veces.
class MovimientoConNovedad {
  const MovimientoConNovedad({
    required this.material,
    required this.cantidad,
    required this.resultado,
    required this.motivo,
    this.ordenNumero,
  });

  final String material;
  final String cantidad;

  /// `descuadre`, `conflicto` o `rechazado`.
  final String resultado;
  final String motivo;
  final int? ordenNumero;

  String get titulo => switch (resultado) {
        'descuadre' => 'No cuadra con el kit',
        'conflicto' => 'Ese equipo ya figura instalado',
        'rechazado' => 'No se pudo registrar',
        _ => 'Revisar',
      };
}
