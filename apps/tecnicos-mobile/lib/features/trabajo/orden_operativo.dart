import 'estado_trabajo.dart';
import 'trabajo_vista.dart';

/// En qué orden se miran los trabajos del día. UNA sola regla.
///
/// La usan Inicio —«Próximo trabajo» es el primero de esta lista— y la lista
/// de Órdenes. Hasta el 17/10/2026 eran dos cosas: Inicio elegía con este
/// criterio y la lista ordenaba por número de OT, que es un identificador de la
/// oficina y no dice nada de qué hacer primero. Las dos pantallas podían
/// contradecirse sobre el mismo día; ahora no pueden, porque leen esto.
///
/// EL CRITERIO (el que ya tenía Inicio, sin cambios)
/// -------------------------------------------------
///   1. el que está en sitio: dejarlo a medias es lo que hace que no cierre;
///   2. el que va en camino;
///   3. lo vencido y lo que vence antes;
///   4. la prioridad que puso la oficina (alta, media, baja);
///   5. el resto, en el orden en que llegó;
///   6. al final, lo terminado o cancelado.
///
/// Dentro de cada escalón se respeta el orden de llegada: `List.sort` de Dart
/// no es estable, y sin el desempate por posición dos trabajos iguales podían
/// cambiar de lugar entre una lectura y otra.
///
/// Es lógica pura sobre lo que ya está en el teléfono: funciona sin señal.
class OrdenOperativo {
  const OrdenOperativo._();

  static const Map<String, int> _prioridad = <String, int>{
    'alta': 0,
    'media': 1,
    'baja': 2,
  };

  /// Terminado para este criterio: completado (enviado o no), cerrado o
  /// cancelado. Una devuelta para corregir o una detenida NO lo están.
  static bool terminado(TrabajoVista t) =>
      t.estado == EstadoTrabajo.completadaCampo ||
      t.estado == EstadoTrabajo.completadaSinEnviar ||
      t.estado == EstadoTrabajo.cerrada ||
      t.estado == EstadoTrabajo.cancelada;

  static List<TrabajoVista> ordenar(
    List<TrabajoVista> trabajos, {
    required DateTime ahora,
  }) {
    final List<(int, TrabajoVista)> conPosicion = <(int, TrabajoVista)>[
      for (int i = 0; i < trabajos.length; i++) (i, trabajos[i]),
    ];

    int escalon(TrabajoVista t) {
      if (terminado(t)) return 5;
      if (t.estado == EstadoTrabajo.enSitio) return 0;
      if (t.estado == EstadoTrabajo.enCamino) return 1;
      if (t.minutosParaVencer(ahora: ahora) != null) return 2;
      if (t.prioridad.isNotEmpty) return 3;
      return 4;
    }

    conPosicion.sort(((int, TrabajoVista) a, (int, TrabajoVista) b) {
      final int ea = escalon(a.$2);
      final int eb = escalon(b.$2);
      if (ea != eb) return ea.compareTo(eb);
      if (ea == 2) {
        final int c = a.$2
            .minutosParaVencer(ahora: ahora)!
            .compareTo(b.$2.minutosParaVencer(ahora: ahora)!);
        if (c != 0) return c;
      }
      if (ea == 3) {
        final int c = (_prioridad[a.$2.prioridad] ?? 9)
            .compareTo(_prioridad[b.$2.prioridad] ?? 9);
        if (c != 0) return c;
      }
      return a.$1.compareTo(b.$1);
    });

    return <TrabajoVista>[for (final (int, TrabajoVista) p in conPosicion) p.$2];
  }

  /// El próximo trabajo: el primero de la lista que no está terminado.
  static TrabajoVista? siguiente(
    List<TrabajoVista> trabajos, {
    required DateTime ahora,
  }) {
    final List<TrabajoVista> ordenados = ordenar(trabajos, ahora: ahora);
    if (ordenados.isEmpty || terminado(ordenados.first)) return null;
    return ordenados.first;
  }
}
