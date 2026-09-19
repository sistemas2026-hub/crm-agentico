import '../../core/widgets/dexter_status_badge.dart';

/// Los estados que una orden puede tener de verdad.
///
/// Siete salen del backend (`OrdenTrabajo.ESTADOS_OPERATIVOS`, en
/// `django-crm/backend/campo/models.py`) y uno es solo del teléfono:
/// [completadaSinEnviar], que es como queda una orden terminada en campo hasta
/// que la cola logra avisarle al servidor. No hay más; cualquier otro texto que
/// llegue cae en [desconocido] en vez de hacer de cuenta que es uno de estos.
enum EstadoTrabajo {
  asignada,
  enCamino,
  enSitio,

  /// Terminada en el teléfono, todavía sin confirmar por el servidor.
  completadaSinEnviar,
  completadaCampo,

  /// El supervisor la devolvió: hay que rehacer algo. No es "en proceso otra
  /// vez", es un estado propio (así lo dice el modelo del backend).
  correccionRequerida,
  cerrada,
  cancelada,
  desconocido;

  static EstadoTrabajo desde(String? valor) => switch (valor) {
        'asignada' => EstadoTrabajo.asignada,
        'en_camino' => EstadoTrabajo.enCamino,
        'en_sitio' => EstadoTrabajo.enSitio,
        'completada_pendiente_sync' => EstadoTrabajo.completadaSinEnviar,
        'completada_campo' => EstadoTrabajo.completadaCampo,
        'correccion_requerida' => EstadoTrabajo.correccionRequerida,
        'cerrada' => EstadoTrabajo.cerrada,
        'cancelada' => EstadoTrabajo.cancelada,
        _ => EstadoTrabajo.desconocido,
      };

  /// Cómo se llama en pantalla.
  String get etiqueta => switch (this) {
        EstadoTrabajo.asignada => 'Asignada',
        EstadoTrabajo.enCamino => 'En camino',
        EstadoTrabajo.enSitio => 'En sitio',
        EstadoTrabajo.completadaSinEnviar => 'Lista, sin enviar',
        EstadoTrabajo.completadaCampo => 'Completada',
        EstadoTrabajo.correccionRequerida => 'Corrección requerida',
        EstadoTrabajo.cerrada => 'Cerrada',
        EstadoTrabajo.cancelada => 'Cancelada',
        EstadoTrabajo.desconocido => 'Estado desconocido',
      };

  /// Cómo se pinta. El color y el icono salen de acá, no del texto.
  DexterOperationalStatus get presentacion => switch (this) {
        EstadoTrabajo.asignada => DexterOperationalStatus.pendiente,
        EstadoTrabajo.enCamino => DexterOperationalStatus.enProceso,
        EstadoTrabajo.enSitio => DexterOperationalStatus.enProceso,
        EstadoTrabajo.completadaSinEnviar => DexterOperationalStatus.completada,
        EstadoTrabajo.completadaCampo => DexterOperationalStatus.completada,
        EstadoTrabajo.cerrada => DexterOperationalStatus.completada,
        EstadoTrabajo.correccionRequerida => DexterOperationalStatus.bloqueada,
        EstadoTrabajo.cancelada => DexterOperationalStatus.bloqueada,
        EstadoTrabajo.desconocido => DexterOperationalStatus.bloqueada,
      };

  /// Si todavía le toca al técnico hacer algo con esta orden.
  ///
  /// Es la definición del contador de la barra inferior: lo que le falta por
  /// hacer, no lo que tiene descargado. Una orden completada, cerrada o
  /// cancelada no cuenta; una devuelta para corregir, sí.
  bool get leTocaAlTecnico => switch (this) {
        EstadoTrabajo.asignada => true,
        EstadoTrabajo.enCamino => true,
        EstadoTrabajo.enSitio => true,
        EstadoTrabajo.correccionRequerida => true,
        EstadoTrabajo.completadaSinEnviar => false,
        EstadoTrabajo.completadaCampo => false,
        EstadoTrabajo.cerrada => false,
        EstadoTrabajo.cancelada => false,
        // Sin saber qué es, no se suma a un número que el técnico usa para
        // saber cuánto le queda.
        EstadoTrabajo.desconocido => false,
      };

  /// Si ya empezó a trabajarse.
  bool get enMarcha =>
      this == EstadoTrabajo.enCamino || this == EstadoTrabajo.enSitio;

  /// Si está terminada, sin importar cómo.
  bool get terminada => switch (this) {
        EstadoTrabajo.completadaSinEnviar => true,
        EstadoTrabajo.completadaCampo => true,
        EstadoTrabajo.cerrada => true,
        EstadoTrabajo.cancelada => true,
        _ => false,
      };
}

/// Las cuatro pestañas de la pantalla Trabajo.
enum PestanaTrabajo { hoy, pendientes, enProceso, finalizadas }

extension EtiquetaPestana on PestanaTrabajo {
  String get etiqueta => switch (this) {
        PestanaTrabajo.hoy => 'Hoy',
        PestanaTrabajo.pendientes => 'Pendientes',
        PestanaTrabajo.enProceso => 'En proceso',
        PestanaTrabajo.finalizadas => 'Finalizadas',
      };
}

/// Si un trabajo entra en una pestaña.
///
/// - **Hoy**: su fecha de compromiso cae hoy y todavía no está terminado. Una
///   orden sin fecha no entra: no se puede afirmar que sea de hoy.
/// - **Pendientes**: no arrancó. Incluye las devueltas para corregir, que
///   vuelven a estar sin empezar.
/// - **En proceso**: en camino o en sitio.
/// - **Finalizadas**: terminadas, enviadas o no, más las canceladas.
bool perteneceA(
  PestanaTrabajo pestana,
  EstadoTrabajo estado,
  DateTime? compromiso, {
  required DateTime ahora,
}) {
  return switch (pestana) {
    PestanaTrabajo.hoy =>
      !estado.terminada && compromiso != null && esMismoDia(compromiso, ahora),
    PestanaTrabajo.pendientes => estado == EstadoTrabajo.asignada ||
        estado == EstadoTrabajo.correccionRequerida,
    PestanaTrabajo.enProceso => estado.enMarcha,
    PestanaTrabajo.finalizadas => estado.terminada,
  };
}

bool esMismoDia(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;
