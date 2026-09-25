import 'package:dio/dio.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';

/// Ejecutar una transición de estado, igual que antes.
///
/// El mecanismo no cambió en esta fase: se guarda el estado nuevo en la base
/// local y se encola la mutación en la misma transacción —así, sin señal, la
/// orden avanza igual y el servidor se entera cuando puede— y recién después
/// se intenta enviar. Lo único nuevo es que está detrás de una interfaz, para
/// poder probar la pantalla sin base ni red.
class AccionesOrden {
  const AccionesOrden({
    required this.transicionar,
    required this.sincronizar,
    this.probarConexion,
  });

  /// [tipoAccion] es el nombre que la cola le manda al backend
  /// (`marcar_en_camino`, `iniciar`, `completar`).
  final Future<void> Function({
    required String ordenId,
    required String nuevoEstadoLocal,
    required String tipoAccion,
    required int revisionBase,
  }) transicionar;

  final Future<void> Function() sincronizar;

  /// Probar la conexion del cliente, AHORA, parado en la casa.
  ///
  /// No pasa por la cola y no es un descuido: la cola existe para lo que
  /// cambia el mundo y puede esperar. Un ping encolado se ejecutaria cuando el
  /// tecnico ya se fue, midiendo un momento que a nadie le importa y con cara
  /// de respuesta a lo que pregunto. Sin señal se dice que no se pudo, y ya.
  final Future<ResultadoPing> Function(String ordenId, int paquetes)?
      probarConexion;

  factory AccionesOrden.reales() {
    final baseLocal = LocalDatabase();
    final almacenamiento = SecureStorageService();
    final sincronizacion = SyncQueueService();

    return AccionesOrden(
      transicionar: ({
        required String ordenId,
        required String nuevoEstadoLocal,
        required String tipoAccion,
        required int revisionBase,
      }) async {
        final orgId = await almacenamiento.getOrgId();
        final profileId = await almacenamiento.getProfileId();
        if (orgId == null || profileId == null) return;

        await baseLocal.transicionarEstadoLocal(
          orgId: orgId,
          profileId: profileId,
          ordenId: ordenId,
          nuevoEstadoLocal: nuevoEstadoLocal,
          tipoAccion: tipoAccion,
          revisionBase: revisionBase,
          idempotencyKey: const Uuid().v4(),
        );

        // Oportunista: si hay señal sale ahora; si no, queda en la cola.
        await sincronizacion.procesarCola();
      },
      sincronizar: sincronizacion.procesarCola,
      probarConexion: (String ordenId, int paquetes) async {
        try {
          final Response<dynamic> r = await ApiClient().dio.post<dynamic>(
                ApiEndpoints.trabajoProbarConexion(ordenId),
                data: <String, dynamic>{'paquetes': paquetes},
              );
          return ResultadoPing.desde(r.data as Map<String, dynamic>?);
        } on DioException catch (e) {
          // Sin conexion es el caso NORMAL de esta aplicacion, no una
          // excepcion: se nombra distinto que un rechazo del servidor porque
          // el tecnico tiene que saber si volver a intentar mas tarde o si el
          // problema es otro.
          final bool sinRed = e.type == DioExceptionType.connectionError ||
              e.type == DioExceptionType.connectionTimeout ||
              e.type == DioExceptionType.receiveTimeout;
          return ResultadoPing.noSePudo(sinRed ? 'sin_conexion' : 'servidor');
        }
      },
    );
  }
}

/// Lo que devuelve un ping, con la distincion que importa: **no se pudo
/// medir** no es lo mismo que **se midio y no respondio**. La primera se
/// reintenta; la segunda es un dato sobre el equipo del cliente.
class ResultadoPing {
  const ResultadoPing({
    required this.medido,
    this.respondieron = '',
    this.paquetes = const <PaqueteDePing>[],
    this.motivo = '',
  });

  factory ResultadoPing.desde(Map<String, dynamic>? cuerpo) {
    final Map<String, dynamic> d = cuerpo ?? <String, dynamic>{};
    if (d['medido'] != true) {
      return ResultadoPing.noSePudo(d['motivo']?.toString() ?? 'desconocido');
    }
    return ResultadoPing(
      medido: true,
      respondieron: d['respondieron']?.toString() ?? '',
      paquetes: (d['paquetes'] as List<dynamic>? ?? <dynamic>[])
          .whereType<Map<dynamic, dynamic>>()
          .map(PaqueteDePing.desde)
          .toList(),
    );
  }

  factory ResultadoPing.noSePudo(String motivo) =>
      ResultadoPing(medido: false, motivo: motivo);

  final bool medido;

  /// Texto crudo de WispHub: '10 de 10', '0 de 10'. **No se convierte a
  /// numero**: esta medido dos veces que el mismo equipo sano da 1, 2 y 3 de 3
  /// en corridas seguidas, asi que no es una escala -- es una muestra.
  final String respondieron;

  /// Los diez, uno por uno. Un promedio esconde si el enlace es intermitente o
  /// esta caido parejo, que es justo lo que decide que hace el tecnico -- y
  /// con tres muestras esa diferencia no se dibuja.
  final List<PaqueteDePing> paquetes;

  final String motivo;
}

/// Un intento del ping: cual fue, si volvio, y cuanto tardo.
///
/// 'respondio' llega resuelto del backend y no se deduce del texto del tiempo:
/// un paquete perdido trae el tiempo vacio, y leer "sin tiempo" como "no
/// volvio" funcionaria hasta el dia que el proveedor mande un cero.
class PaqueteDePing {
  const PaqueteDePing({
    required this.n,
    required this.respondio,
    this.rtt = '',
    this.perdida = '',
  });

  factory PaqueteDePing.desde(Map<dynamic, dynamic> d) => PaqueteDePing(
        n: int.tryParse('${d['n']}') ?? 0,
        respondio: d['respondio'] == true,
        rtt: d['rtt']?.toString() ?? '',
        perdida: d['perdida']?.toString() ?? '',
      );

  final int n;
  final bool respondio;
  final String rtt;
  final String perdida;
}
