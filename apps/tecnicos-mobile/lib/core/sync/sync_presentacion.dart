import '../tiempo/formato_de_momento.dart';
import '../tiempo/momento_leido.dart';
import '../widgets/dexter_sync_badge.dart';
import 'sync_queue_service.dart';

/// Traduce el resumen real de la cola a lo que se muestra en pantalla.
///
/// Son funciones puras: entra un [SyncSummary], sale texto y estado. Viven
/// aparte de los widgets para poder probarse sin montar nada, y aparte del
/// servicio para que la pastilla no tenga que conocer la cola.
///
/// Todo lo que devuelven se puede afirmar con lo que el servicio ya sabe.
///
/// Hasta el 06/11/2026 acá decía que «última sincronización hace 2 minutos»
/// no se podía escribir porque el dato no existía. Ya existe
/// —`SyncSummary.servidorContestoEn`, CAMPO-DATA-036— y la regla no cambió:
/// se escribe cuando hay marca, y cuando es `null` la frase no la menciona.
/// Un `null` ahí significa «este teléfono nunca habló con el servidor», que
/// es distinto de «hace mucho», y la primera vez que alguien abre la
/// aplicación es exactamente ese caso.
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
    //  Fallo CON red: no es «pendiente de que vuelva la señal», es algo roto
    //  del otro lado. Va como error para que se vea distinto de esperar.
    if (resumen.falloDelServidor) return DexterSyncStatus.error;
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
      if (resumen.hasConnectionError) return '$pendientes · sin conexión';
      //  CON red y fallando: decir «sin conexión» acá fue el reclamo entero
      //  --«sale sin internet teniendo internet»--. El técnico mira la barra
      //  de señal, la ve llena, y deja de creerle a la pastilla.
      if (resumen.falloDelServidor) return '$pendientes · el servidor falla';
      return pendientes;
    }
    if (resumen.hasConnectionError) return 'Sin conexión';
    if (resumen.falloDelServidor) return 'El servidor falla';
    return null;
  }

  /// Frase de la franja oscura, que tiene más espacio que la pastilla.
  static String fraseFranja(SyncSummary? resumen, {required DateTime ahora}) {
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
      if (resumen.hasConnectionError) {
        return '$base · se envían al volver la conexión';
      }
      //  Y acá se dice qué hacer, porque esperar NO lo arregla: es la
      //  diferencia práctica entre los dos estados.
      if (resumen.falloDelServidor) {
        return '$base · hay señal pero el servidor no responde · avisá al NOC';
      }
      return '$base · esperando turno para enviarse';
    }
    //  EL MOMENTO SE AGREGA EN ESTOS DOS Y NO EN TODOS, y no es por espacio.
    //
    //  Cuando hay cambios en cola, la frase ya dice que falta enviarlos: la
    //  hora del envío anterior no cambia qué hacer. En estos dos sí: «todo
    //  sincronizado» sin hora no dice si fue recién o hace un día, y «sin
    //  conexión» sin hora no distingue dos minutos de ayer a la tarde --que
    //  es la diferencia entre esperar y levantar el teléfono--.
    final String cuando = _momento(resumen, ahora);

    if (resumen.hasConnectionError) {
      return cuando.isEmpty
          ? 'Sin conexión con el servidor · lo que hagas se guarda igual'
          : 'Sin conexión · lo último llegó $cuando · se guarda igual';
    }
    if (resumen.falloDelServidor) {
      return cuando.isEmpty
          ? 'Hay señal pero el servidor no responde · avisá al NOC'
          : 'El servidor no responde · lo último llegó $cuando · avisá al NOC';
    }
    return cuando.isEmpty ? 'Todo sincronizado' : 'Todo sincronizado · $cuando';
  }

  /// Cómo se escribe el instante del último contacto, o `''` si no hay.
  ///
  /// La zona se declara en vez de adivinarse: la marca la puso este teléfono
  /// con su propio reloj, así que es comparable contra `ahora` sin el riesgo
  /// de las cinco horas que describe `momento_leido.dart`.
  static String _momento(SyncSummary resumen, DateTime ahora) {
    final DateTime? marca = resumen.servidorContestoEn;
    if (marca == null) return '';
    return textoDelMomento(
      MomentoLeido(cuando: marca, zona: ZonaDelMomento.declarada),
      ahora: ahora,
    );
  }

  /// Si conviene ofrecer el botón de sincronizar ahora.
  static bool puedeSincronizarAhora(SyncSummary? resumen) {
    if (resumen == null) return false;
    if (resumen.isSyncing) return false;
    return resumen.totalPendientes > 0 ||
        resumen.hasConnectionError ||
        resumen.falloDelServidor;
  }
}
