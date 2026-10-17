/// Ritmo vertical y márgenes del diseño "DEXTER CAMPO".
///
/// Son los valores de `spacing` que declaran las seis pantallas de Stitch,
/// pasados de rem a píxeles lógicos de Flutter. No se copian alturas fijas de
/// la maqueta web: el alto lo da el contenido.
///
/// Dos escalones cambiaron el 25/09/2026 al pasar a esta familia: `space-lg`
/// es 1.25rem (20 px, antes 16) y `space-xl` es 2rem (32 px, antes 24). El
/// margen lateral NO sigue a `space-lg`: el diseño tiene su propio token
/// `gutter`/`margin` de 1rem, y por eso acá es un 16 literal.
class AppSpacing {
  const AppSpacing._();

  static const double xs = 4; // 0.25rem
  static const double sm = 8; // 0.5rem
  static const double md = 12; // 0.75rem — separación entre ítems de una lista
  static const double lg = 20; // 1.25rem — separación entre bloques distintos
  static const double xl = 32; // 2rem

  /// Margen lateral del lienzo en móvil: el contenido nunca toca el borde.
  /// Es el token `gutter`/`margin` del diseño (1rem), no [lg].
  static const double margen = 16;

  /// Separación interna entre columnas de una misma fila.
  static const double canal = md;

  /// Alto mínimo de cualquier cosa que se toque: pensado para guantes.
  static const double objetivoTactil = 48;

  /// Alto de los botones de paso y de los contadores de material.
  static const double objetivoTactilAmplio = 56;

  /// Alto del encabezado fijo, sin contar el área segura de arriba.
  /// En el diseño es `h-16`.
  static const double encabezado = 64;

  /// Alto de la barra de navegación inferior, sin contar el área segura.
  /// En el diseño es `h-20`, y no es capricho: cada destino es un objetivo
  /// táctil de 56 con su rótulo debajo.
  static const double barraInferior = 80;
}
