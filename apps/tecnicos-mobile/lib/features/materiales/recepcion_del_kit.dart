import 'package:dio/dio.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';

/// LA RECEPCIÓN DEL KIT (28/10/2026, fase 2 del material del día).
///
/// Lo que el técnico hace al recibir su material en la bodega: confirmar que
/// coincide con el acta —o decir qué no llegó— y escanear los equipos con
/// serie que el Supervisor le dejó apartados. Ver `campo/recepcion_del_kit.py`.
///
/// VA EN LÍNEA, NO POR LA COLA. Confirmar y escanear pasan en la bodega, con
/// el material en la mano: si no hay señal se dice, y se hace cuando la haya.
/// Escanear sin señal no puede saber si esa serie es la que le apartaron.

/// Una línea del acta.
class LineaDeEntrega {
  const LineaDeEntrega({
    required this.codigo,
    required this.nombre,
    required this.unidad,
    required this.cantidad,
    this.serie = '',
  });

  final String codigo;
  final String nombre;
  final String unidad;
  final String cantidad;
  final String serie;

  factory LineaDeEntrega.desde(Map<String, dynamic> d) => LineaDeEntrega(
        codigo: '${d['codigo'] ?? ''}',
        nombre: '${d['nombre'] ?? ''}',
        unidad: '${d['unidad'] ?? ''}',
        cantidad: '${d['cantidad'] ?? '0'}',
        serie: '${d['serie'] ?? ''}',
      );
}

/// Un acta de entrega todavía sin confirmar.
class EntregaPorConfirmar {
  const EntregaPorConfirmar({
    required this.id,
    required this.acta,
    required this.bodega,
    required this.lineas,
  });

  final String id;
  final String acta;
  final String bodega;
  final List<LineaDeEntrega> lineas;

  factory EntregaPorConfirmar.desde(Map<String, dynamic> d) => EntregaPorConfirmar(
        id: '${d['id']}',
        acta: '${d['acta'] ?? ''}',
        bodega: '${d['bodega'] ?? ''}',
        lineas: <LineaDeEntrega>[
          for (final dynamic l in (d['lineas'] as List? ?? const <dynamic>[]))
            LineaDeEntrega.desde(Map<String, dynamic>.from(l as Map)),
        ],
      );
}

/// Equipos con serie apartados a su nombre, por material y bodega.
class EquipoPorEscanear {
  const EquipoPorEscanear({
    required this.codigo,
    required this.nombre,
    required this.bodega,
    required this.cantidad,
  });

  final String codigo;
  final String nombre;
  final String bodega;
  final String cantidad;

  factory EquipoPorEscanear.desde(Map<String, dynamic> d) => EquipoPorEscanear(
        codigo: '${d['codigo'] ?? ''}',
        nombre: '${d['nombre'] ?? ''}',
        bodega: '${d['bodega'] ?? ''}',
        cantidad: '${d['cantidad'] ?? '0'}',
      );
}

class PendienteDeRecepcion {
  const PendienteDeRecepcion({
    this.porConfirmar = const <EntregaPorConfirmar>[],
    this.porEscanear = const <EquipoPorEscanear>[],
  });

  final List<EntregaPorConfirmar> porConfirmar;
  final List<EquipoPorEscanear> porEscanear;

  bool get hayAlgo => porConfirmar.isNotEmpty || porEscanear.isNotEmpty;
}

/// Lo que el técnico dice que recibió de un material, cuando no coincide.
class Diferencia {
  const Diferencia({
    required this.codigo,
    required this.recibido,
    required this.motivo,
  });

  final String codigo;
  final String recibido;
  final String motivo;

  Map<String, dynamic> aJson() =>
      <String, dynamic>{'codigo': codigo, 'recibido': recibido, 'motivo': motivo};
}

/// Lo que se rechaza o no se pudo, con la frase que se le muestra al técnico.
class RecepcionError implements Exception {
  const RecepcionError(this.mensaje);
  final String mensaje;

  @override
  String toString() => mensaje;
}

/// El servidor de la recepción. Abstracta para poder probar la pantalla sin red.
abstract class RecepcionDelKit {
  Future<PendienteDeRecepcion> leer();
  Future<void> confirmar(String entregaId,
      {required bool conforme, List<Diferencia> diferencias = const <Diferencia>[]});

  /// Devuelve lo que se recibió, para decírselo al técnico.
  Future<String> escanear(String serie);

  factory RecepcionDelKit.real() => _RecepcionReal(ApiClient());
}

class _RecepcionReal implements RecepcionDelKit {
  _RecepcionReal(this._api);
  final ApiClient _api;

  static const String _sinSenal =
      'Sin conexión con el servidor: se confirma cuando haya señal.';

  RecepcionError _error(Object e) {
    if (e is DioException) {
      final dynamic datos = e.response?.data;
      if (datos is Map && datos['detail'] != null) {
        return RecepcionError('${datos['detail']}');
      }
      if (e.response == null) return const RecepcionError(_sinSenal);
    }
    return const RecepcionError('No se pudo: probá de nuevo en un momento.');
  }

  @override
  Future<PendienteDeRecepcion> leer() async {
    try {
      final r = await _api.get<dynamic>(ApiEndpoints.recepcion);
      final Map<String, dynamic> d = Map<String, dynamic>.from(r.data as Map);
      return PendienteDeRecepcion(
        porConfirmar: <EntregaPorConfirmar>[
          for (final dynamic e in (d['por_confirmar'] as List? ?? const <dynamic>[]))
            EntregaPorConfirmar.desde(Map<String, dynamic>.from(e as Map)),
        ],
        porEscanear: <EquipoPorEscanear>[
          for (final dynamic e in (d['por_escanear'] as List? ?? const <dynamic>[]))
            EquipoPorEscanear.desde(Map<String, dynamic>.from(e as Map)),
        ],
      );
    } catch (e) {
      throw _error(e);
    }
  }

  @override
  Future<void> confirmar(String entregaId,
      {required bool conforme, List<Diferencia> diferencias = const <Diferencia>[]}) async {
    try {
      await _api.post<dynamic>(ApiEndpoints.confirmarEntrega(entregaId), data: <String, dynamic>{
        'conforme': conforme,
        'diferencias': <Map<String, dynamic>>[for (final Diferencia d in diferencias) d.aJson()],
      });
    } catch (e) {
      throw _error(e);
    }
  }

  @override
  Future<String> escanear(String serie) async {
    try {
      final r = await _api.post<dynamic>(ApiEndpoints.recepcionEscanear,
          data: <String, dynamic>{'serie': serie});
      final Map<String, dynamic> d = Map<String, dynamic>.from(r.data as Map);
      return 'Recibido: ${d['material']} · ${d['serie']}';
    } catch (e) {
      throw _error(e);
    }
  }
}
