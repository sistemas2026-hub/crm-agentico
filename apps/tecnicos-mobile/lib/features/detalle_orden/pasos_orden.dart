import '../trabajo/estado_trabajo.dart';

/// Los pasos que se dibujan en la barra de progreso.
///
/// **No son la máquina de estados**: son una lectura de ella. El grafo real
/// vive en el backend (`campo/services/transiciones.py`) y no es una línea:
///
/// ```
/// asignada ──────────► en_camino ──► en_sitio ──► completada_campo ──► cerrada
///    │  └──────────────────────────────┘             │
///    │        (se puede llegar sin avisar)           ▼
///    │                                      correccion_requerida
///    │                                          │        │
///    └──────────────► cancelada ◄───────────────┘        └──► en_camino / en_sitio
/// ```
///
/// Por eso `correccion_requerida` y `cancelada` **no son pasos**: son
/// excepciones que se muestran aparte. Meterlas en la línea haría creer que
/// una orden devuelta "avanzó" o que una cancelada está completa.
enum PasoOrden { asignada, enCamino, enSitio, completada, cerrada }

extension EtiquetaPaso on PasoOrden {
  String get etiqueta => switch (this) {
        PasoOrden.asignada => 'Asignada',
        PasoOrden.enCamino => 'En camino',
        PasoOrden.enSitio => 'En sitio',
        PasoOrden.completada => 'Completada',
        PasoOrden.cerrada => 'Cerrada',
      };
}

/// Cómo se ve la orden en la barra de progreso.
class LecturaDePasos {
  const LecturaDePasos({
    required this.pasoActual,
    required this.excepcion,
    required this.avisoExcepcion,
  });

  /// Hasta dónde llegó, de 0 a 4. En una orden cancelada es hasta dónde había
  /// llegado antes de cancelarse, que no se sabe: se muestra sin avance.
  final int pasoActual;

  /// La orden está fuera del camino normal.
  final bool excepcion;

  /// Qué decir cuando lo está.
  final String? avisoExcepcion;

  static LecturaDePasos de(EstadoTrabajo estado) => switch (estado) {
        EstadoTrabajo.asignada => const LecturaDePasos(
            pasoActual: 0,
            excepcion: false,
            avisoExcepcion: null,
          ),
        EstadoTrabajo.enCamino => const LecturaDePasos(
            pasoActual: 1,
            excepcion: false,
            avisoExcepcion: null,
          ),
        EstadoTrabajo.enSitio => const LecturaDePasos(
            pasoActual: 2,
            excepcion: false,
            avisoExcepcion: null,
          ),
        // Terminada en el teléfono: el paso está alcanzado, pero el servidor
        // todavía no lo sabe. Lo dice el aviso, no la barra.
        EstadoTrabajo.completadaSinEnviar => const LecturaDePasos(
            pasoActual: 3,
            excepcion: false,
            avisoExcepcion: null,
          ),
        EstadoTrabajo.completadaCampo => const LecturaDePasos(
            pasoActual: 3,
            excepcion: false,
            avisoExcepcion: null,
          ),
        EstadoTrabajo.cerrada => const LecturaDePasos(
            pasoActual: 4,
            excepcion: false,
            avisoExcepcion: null,
          ),
        // Volvió del supervisor: no es "en proceso otra vez" ni un paso más.
        EstadoTrabajo.correccionRequerida => const LecturaDePasos(
            pasoActual: 2,
            excepcion: true,
            avisoExcepcion:
                'El supervisor devolvió este trabajo. Hay que rehacer lo que '
                'quedó mal y volver a completarlo.',
          ),
        EstadoTrabajo.cancelada => const LecturaDePasos(
            pasoActual: -1,
            excepcion: true,
            avisoExcepcion: 'Este trabajo fue cancelado. No hay nada que hacer.',
          ),
        EstadoTrabajo.desconocido => const LecturaDePasos(
            pasoActual: -1,
            excepcion: true,
            avisoExcepcion:
                'Esta orden llegó con un estado que esta versión no conoce. '
                'Actualizá la aplicación antes de tocarla.',
          ),
      };
}

/// Una cosa que el técnico puede hacer con la orden desde esta pantalla.
///
/// Todas existen en el backend: [tipoAccion] es el nombre que la cola le manda
/// a `/acciones/`, y [nuevoEstadoLocal] el estado con que la orden queda
/// guardada mientras tanto. No hay ninguna acción inventada acá.
class AccionOrden {
  const AccionOrden({
    required this.etiqueta,
    required this.tipoAccion,
    required this.nuevoEstadoLocal,
  });

  /// Abre la pantalla de ejecución en vez de mover el estado. El cierre lo
  /// hace esa pantalla, después de validar el formulario y las evidencias.
  const AccionOrden.ejecutar()
      : etiqueta = 'Ejecutar el trabajo',
        tipoAccion = null,
        nuevoEstadoLocal = null;

  final String etiqueta;
  final String? tipoAccion;
  final String? nuevoEstadoLocal;

  bool get abreEjecucion => tipoAccion == null;
}

/// Qué puede hacer el técnico ahora, según el estado.
///
/// Sale del grafo del backend, no del diseño:
///   * `asignada` → en camino (y también directo a en sitio: la matriz lo
///     permite, porque a veces se llega antes de acordarse de avisar);
///   * `en_camino` → en sitio;
///   * `en_sitio` → ejecutar, que es lo que termina en `completada_campo`;
///   * `correccion_requerida` → volver al sitio, el único camino de vuelta;
///   * terminada, cerrada o cancelada → nada.
///
/// `cancelar` existe en el backend y **no se ofrece acá**: la aplicación nunca
/// la tuvo y cancelar un trabajo es una decisión de operaciones, no del
/// técnico parado en la puerta. Está anotado en el informe de la fase.
class AccionesDisponibles {
  const AccionesDisponibles({required this.primaria, required this.secundarias});

  final AccionOrden? primaria;
  final List<AccionOrden> secundarias;

  static const AccionesDisponibles ninguna =
      AccionesDisponibles(primaria: null, secundarias: <AccionOrden>[]);

  static AccionesDisponibles para(EstadoTrabajo estado) => switch (estado) {
        EstadoTrabajo.asignada => const AccionesDisponibles(
            primaria: AccionOrden(
              etiqueta: 'Voy en camino',
              tipoAccion: 'marcar_en_camino',
              nuevoEstadoLocal: 'en_camino',
            ),
            secundarias: <AccionOrden>[
              AccionOrden(
                etiqueta: 'Ya estoy en el sitio',
                tipoAccion: 'iniciar',
                nuevoEstadoLocal: 'en_sitio',
              ),
            ],
          ),
        EstadoTrabajo.enCamino => const AccionesDisponibles(
            primaria: AccionOrden(
              etiqueta: 'Llegué al sitio',
              tipoAccion: 'iniciar',
              nuevoEstadoLocal: 'en_sitio',
            ),
            secundarias: <AccionOrden>[],
          ),
        EstadoTrabajo.enSitio => const AccionesDisponibles(
            primaria: AccionOrden.ejecutar(),
            secundarias: <AccionOrden>[],
          ),
        // Sin esto, una orden devuelta quedaba sin ninguna salida en la
        // aplicación: el técnico veía el trabajo y no tenía cómo retomarlo.
        EstadoTrabajo.correccionRequerida => const AccionesDisponibles(
            primaria: AccionOrden(
              etiqueta: 'Volver al sitio',
              tipoAccion: 'iniciar',
              nuevoEstadoLocal: 'en_sitio',
            ),
            secundarias: <AccionOrden>[
              AccionOrden(
                etiqueta: 'Voy en camino',
                tipoAccion: 'marcar_en_camino',
                nuevoEstadoLocal: 'en_camino',
              ),
            ],
          ),
        EstadoTrabajo.completadaSinEnviar => ninguna,
        EstadoTrabajo.completadaCampo => ninguna,
        EstadoTrabajo.cerrada => ninguna,
        EstadoTrabajo.cancelada => ninguna,
        EstadoTrabajo.desconocido => ninguna,
      };
}
