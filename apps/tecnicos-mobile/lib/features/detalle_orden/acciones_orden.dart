import 'package:uuid/uuid.dart';

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
  const AccionesOrden({required this.transicionar, required this.sincronizar});

  /// [tipoAccion] es el nombre que la cola le manda al backend
  /// (`marcar_en_camino`, `iniciar`, `completar`).
  final Future<void> Function({
    required String ordenId,
    required String nuevoEstadoLocal,
    required String tipoAccion,
    required int revisionBase,
  }) transicionar;

  final Future<void> Function() sincronizar;

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
    );
  }
}
