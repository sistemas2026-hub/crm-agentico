import '../widgets/dexter_sync_badge.dart';
import 'sync_queue_service.dart';

/// Traduce el resumen real de la cola a lo que se muestra en pantalla.
///
/// Son funciones puras: entra un [SyncSummary], sale texto y estado. Viven
/// aparte de los widgets para poder probarse sin montar nada, y aparte del
/// servicio para que la pastilla no tenga que conocer la cola.
///
/// Todo lo que devuelven se puede afirmar con lo que el servicio ya sabe. No
/// hay "última sincronización hace 2 minutos": ese dato no existe todavía y
/// decirlo sería inventarlo.
class SyncPresentacion {
  const SyncPresentacion._();

  /// Estado para la pastilla del encabezado.
  static DexterSyncStatus estado(SyncSummary? resumen) {
    if (resumen == null) return DexterSyncStatus.sincronizando;
    if (resumen.isSyncing) return DexterSyncStatus.sincronizando;
    if (resumen.mutacionesConflicto > 0) return DexterSyncStatus.error;
    if (resumen.totalPendientes > 0) return DexterSyncStatus.pendiente;
    // Sin nada pendiente, pero el último intento no llegó al servidor: no se
    // puede decir "sincronizado" con la misma cara de siempre.
    if (resumen.hasConnectionError) return DexterSyncStatus.pendiente;
    return DexterSyncStatus.sincronizado;
  }

  /// Detalle corto que acompaña a la pastilla. `null` si no hay nada que sumar.
  static String? detalle(SyncSummary? resumen) {
    if (resumen == null) return 'Verificando';
    if (resumen.isSyncing) return null;
    if (resumen.mutacionesConflicto > 0) {
      return '${resumen.mutacionesConflicto} sin resolver';
    }
    if (resumen.totalPendientes > 0) {
      // DICE «COLA» A PROPOSITO: esta pastilla cuenta TODO lo que el tecnico
      // tiene sin enviar, de cualquier orden, y adentro de una orden hay otra
      // frase que cuenta solo la de ella. Sin decir cual es cual, las dos
      // parecen significar lo mismo y una de las dos parece estar mintiendo.
      // EL NUMERO PRIMERO, Y NO ES ESTILO.
      //
      // Estuvo como «cola: 3» y la guarda de la matriz lo cazo: esta pastilla
      // esta capada a 150 px, el corte caia ANTES del digito, y «Pendiente ·
      // cola: 3» y «Pendiente · cola: 1 · sin conexion» se dibujaban iguales
      // --«PENDIENTE · CO...»--. Dos estados distintos que se ven igual son
      // peores que uno mal escrito.
      //
      // Con el numero adelante sobrevive al corte, y «en cola» sigue diciendo
      // de QUE cola habla, que es lo que la distingue del «Esta OT: n» del
      // bloque de la orden.
      final pendientes = '${resumen.totalPendientes} en cola';
      return resumen.hasConnectionError ? '$pendientes · sin conexión' : pendientes;
    }
    if (resumen.hasConnectionError) return 'Sin conexión';
    return null;
  }

  /// Frase de la franja oscura, que tiene más espacio que la pastilla.
  static String fraseFranja(SyncSummary? resumen) {
    if (resumen == null) return 'Revisando cambios guardados en el teléfono';
    if (resumen.isSyncing) return 'Enviando cambios al servidor';
    if (resumen.mutacionesConflicto > 0) {
      final n = resumen.mutacionesConflicto;
      return n == 1
          ? 'Un cambio necesita que alguien lo revise'
          : '$n cambios necesitan que alguien los revise';
    }
    if (resumen.totalPendientes > 0) {
      final n = resumen.totalPendientes;
      final base = n == 1 ? 'Un cambio guardado acá' : '$n cambios guardados acá';
      return resumen.hasConnectionError
          ? '$base · se envían al volver la conexión'
          : '$base · esperando turno para enviarse';
    }
    if (resumen.hasConnectionError) {
      return 'Sin conexión con el servidor · lo que hagas se guarda igual';
    }
    return 'Todo sincronizado';
  }

  /// Si conviene ofrecer el botón de sincronizar ahora.
  static bool puedeSincronizarAhora(SyncSummary? resumen) {
    if (resumen == null) return false;
    if (resumen.isSyncing) return false;
    return resumen.totalPendientes > 0 || resumen.hasConnectionError;
  }
}
