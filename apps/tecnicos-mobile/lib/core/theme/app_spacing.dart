/// Ritmo vertical y márgenes de "Field Ops Precision".
///
/// Son los valores del diseño pasados de rem a píxeles lógicos de Flutter.
/// No se copian alturas fijas de la maqueta web: el alto lo da el contenido.
class AppSpacing {
  const AppSpacing._();

  static const double xs = 4; // 0.25rem
  static const double sm = 8; // 0.5rem
  static const double md = 12; // 0.75rem — separación entre ítems de una lista
  static const double lg = 16; // 1rem — separación entre bloques distintos
  static const double xl = 24; // 1.5rem

  /// Margen lateral del lienzo en móvil: el contenido nunca toca el borde.
  static const double margen = lg;

  /// Separación interna entre columnas de una misma fila.
  static const double canal = md;

  /// Alto mínimo de cualquier cosa que se toque: pensado para guantes.
  static const double objetivoTactil = 48;

  /// Alto de los botones de paso y de los contadores de material.
  static const double objetivoTactilAmplio = 56;

  /// Alto de la barra de navegación inferior, sin contar el área segura.
  static const double barraInferior = 64;
}
