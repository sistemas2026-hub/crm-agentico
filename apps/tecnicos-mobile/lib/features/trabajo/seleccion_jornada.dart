import 'estado_trabajo.dart';
import 'trabajo_vista.dart';

/// Cómo se lee la jornada. Una sola vez, para las dos pantallas.
///
/// Inicio y Trabajo responden preguntas distintas sobre la misma lista, pero
/// "pendiente", "en curso" y "terminado" tienen que significar lo mismo en las
/// dos. Por eso la clasificación vive acá y no adentro de cada pantalla.
///
/// Son funciones puras sobre la lista ya cargada: no consultan nada.
class SeleccionJornada {
  const SeleccionJornada._();

  /// Lo que todavía le toca hacer al técnico.
  static List<TrabajoVista> activos(List<TrabajoVista> trabajos) =>
      trabajos.where((TrabajoVista t) => t.estado.leTocaAlTecnico).toList();

  /// Empezados: en camino o en sitio.
  static List<TrabajoVista> enCurso(List<TrabajoVista> trabajos) =>
      trabajos.where((TrabajoVista t) => t.estado.enMarcha).toList();

  /// Sin empezar. Incluye las devueltas para corregir.
  static List<TrabajoVista> pendientes(List<TrabajoVista> trabajos) => trabajos
      .where((TrabajoVista t) =>
          t.estado == EstadoTrabajo.asignada ||
          t.estado == EstadoTrabajo.correccionRequerida)
      .toList();

  /// Terminados, enviados o no, más los cancelados.
  static List<TrabajoVista> terminados(List<TrabajoVista> trabajos) =>
      trabajos.where((TrabajoVista t) => t.estado.terminada).toList();

  /// Cuál es *el* trabajo en curso.
  ///
  /// Con ninguno devuelve `null` — y entonces la pantalla dice que no hay
  /// ninguno empezado, en vez de mostrar el primero de la lista como si lo
  /// fuera. Con varios, que no debería pasar (el técnico está en un solo lugar
  /// a la vez), elige **siempre el mismo**: el de compromiso más temprano y,
  /// a igualdad, el de número más bajo. No toca ningún dato ni corrige nada;
  /// que haya más de uno se informa aparte, con [hayVariosEnCurso].
  static TrabajoVista? enCursoDestacado(List<TrabajoVista> trabajos) {
    final empezados = enCurso(trabajos);
    if (empezados.isEmpty) return null;
    empezados.sort(_porCompromisoYNumero);
    return empezados.first;
  }

  /// Más de un trabajo empezado a la vez: es una anomalía operativa, no un
  /// caso normal. La pantalla la muestra; nadie la "arregla" por su cuenta.
  static bool hayVariosEnCurso(List<TrabajoVista> trabajos) =>
      enCurso(trabajos).length > 1;

  /// Lo que viene después: sin empezar, con fecha, en orden cronológico.
  ///
  /// Una orden sin fecha **no entra**: ponerla en una agenda le inventaría un
  /// momento. Sigue estando en Trabajo, que es donde se la ve completa — ver
  /// [activosSinFecha] para el aviso que Inicio muestra.
  static List<TrabajoVista> proximos(
    List<TrabajoVista> trabajos, {
    required DateTime desde,
    int cuantos = 3,
  }) {
    final candidatos = trabajos
        .where((TrabajoVista t) => !t.estado.terminada && !t.estado.enMarcha)
        .where((TrabajoVista t) => t.compromiso != null)
        .toList()
      ..sort(_porCompromisoYNumero);

    return candidatos.take(cuantos).toList();
  }

  /// Trabajos que siguen pendientes y no tienen fecha de compromiso.
  static List<TrabajoVista> activosSinFecha(List<TrabajoVista> trabajos) =>
      trabajos
          .where((TrabajoVista t) => t.estado.leTocaAlTecnico)
          .where((TrabajoVista t) => t.compromiso == null)
          .toList();

  static int _porCompromisoYNumero(TrabajoVista a, TrabajoVista b) {
    final fechaA = a.compromiso;
    final fechaB = b.compromiso;
    if (fechaA != null && fechaB != null && fechaA != fechaB) {
      return fechaA.compareTo(fechaB);
    }
    // Sin fecha que los separe, el número de orden: es estable y no depende
    // del orden en que la base haya devuelto las filas.
    if (fechaA == null && fechaB != null) return 1;
    if (fechaA != null && fechaB == null) return -1;
    return (a.numero ?? 0).compareTo(b.numero ?? 0);
  }
}
