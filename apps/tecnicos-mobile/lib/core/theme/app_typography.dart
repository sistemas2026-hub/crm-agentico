import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Escala tipográfica del diseño "DEXTER CAMPO" de Stitch.
///
/// Las seis pantallas de esa familia declaran exactamente la misma escala
/// —se comparó token por token, 25/09/2026—, así que esto es un sistema y no
/// la copia de una pantalla.
///
/// DOS MOTORES, Y ACÁ LA MONOESPACIADA LLEGA MÁS LEJOS
/// ---------------------------------------------------
///   * texto de interfaz -> Inter
///   * dato técnico      -> JetBrains Mono (cifras tabulares: una medición
///     que cambia en vivo no debe mover el resto de la fila)
///
/// La versión del 22/09/2026 salía del otro diseño del producto y dejaba la
/// monoespaciada SOLO para los números. Acá no alcanza: en esta familia
/// `label-badge` —la insignia de estado, el número de orden, el "P1
/// CRÍTICO"— es JetBrains Mono, y `label-telemetry` también. Es lo que
/// distingue un dato del sistema de una palabra escrita por una persona.
///
/// Las dos familias van empaquetadas en la aplicación y se declaran en
/// `pubspec.yaml`; su origen, versión y licencia están en
/// `assets/fonts/LEEME.md`. Los nombres viven acá y en ningún otro lado:
/// ningún widget escribe el nombre de una fuente.
class AppTypography {
  const AppTypography._();

  static const String familiaTexto = 'Inter';
  static const String familiaMono = 'JetBrainsMono';

  /// Respaldo por si un glifo no existe en JetBrains Mono: cae en otra
  /// monoespaciada y no en la fuente de interfaz, que rompería la alineación
  /// de una columna de cifras.
  static const List<String> respaldoMono = <String>[
    'JetBrains Mono',
    'Consolas',
    'Roboto Mono',
    'monospace',
  ];

  // --- Los tokens del diseño, con su nombre --------------------------------
  // Un widget nuevo nombra estos. Los alias de más abajo existen para las
  // pantallas que todavía no se migraron.

  /// `headline-xl`: 36/44, -0.02em, w700. La cifra que se mira de lejos.
  static const TextStyle headlineXl = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 36,
    height: 44 / 36,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.72,
    color: AppColors.onSurface,
  );

  /// `headline-xl-mobile`: 28/36, -0.01em, w700.
  static const TextStyle headlineXlMovil = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 28,
    height: 36 / 28,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.28,
    color: AppColors.onSurface,
  );

  /// `headline-lg`: 24/32, -0.01em, w700.
  static const TextStyle headlineLg = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 24,
    height: 32 / 24,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.24,
    color: AppColors.onSurface,
  );

  /// `headline-md`: 20/28, w600. El título de cada bloque.
  static const TextStyle headlineMd = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 20,
    height: 28 / 20,
    fontWeight: FontWeight.w600,
    color: AppColors.onSurface,
  );

  /// `body-lg`: 18/26, w500. Texto del botón dominante.
  static const TextStyle bodyLg = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 18,
    height: 26 / 18,
    fontWeight: FontWeight.w500,
    color: AppColors.onSurface,
  );

  /// `body-md`: 16/24, w400. La prosa.
  static const TextStyle bodyMd = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 16,
    height: 24 / 16,
    fontWeight: FontWeight.w400,
    color: AppColors.onSurface,
  );

  /// `body-sm`: 14/20, w500. La bajada de un título y el texto de una fila.
  static const TextStyle bodySm = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 14,
    height: 20 / 14,
    fontWeight: FontWeight.w500,
    color: AppColors.onSurface,
  );

  /// `label-caption`: Inter 12/16, 0.03em, w600. El rótulo gris en
  /// mayúsculas que va arriba de un valor.
  static const TextStyle labelCaption = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 12,
    height: 16 / 12,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.36,
    color: AppColors.onSurfaceVariant,
  );

  /// `label-badge`: JetBrains Mono 12/16, 0.05em, w700. Las insignias, los
  /// números de orden y todo lo que el sistema afirma en una pastilla.
  static const TextStyle labelBadge = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 12,
    height: 16 / 12,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.6,
    color: AppColors.onSurface,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// `label-telemetry`: JetBrains Mono 16/20, 0.02em, w600. La medición
  /// dentro de una fila: potencia, IP, puerto, teléfono.
  static const TextStyle labelTelemetry = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 16,
    height: 20 / 16,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.32,
    color: AppColors.onSurface,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// La medición grande: `headline-xl-mobile` con la familia monoespaciada,
  /// que es como el diseño escribe la potencia óptica (las dos clases
  /// conviven en el mismo span y la última fija la familia).
  static const TextStyle medicion = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 28,
    height: 36 / 28,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.28,
    color: AppColors.onSurface,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  // --- Nombres de la primera versión ---------------------------------------
  // Apuntan al token del diseño que les corresponde, para que migrar sea
  // pantalla por pantalla y no un cambio de todo a la vez.

  static const TextStyle tituloGrande = headlineLg;
  static const TextStyle tituloMedio = headlineMd;

  /// Esta familia no declara un `headline-sm`. Se deja el escalón intermedio
  /// que las pantallas ya construidas necesitan, dicho como lo que es: un
  /// puente, no un token del diseño.
  static const TextStyle tituloChico = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 16,
    height: 24 / 16,
    fontWeight: FontWeight.w600,
    color: AppColors.onSurface,
  );

  static const TextStyle cuerpoGrande = bodyMd;
  static const TextStyle cuerpo = bodySm;

  /// Lo mismo que [bodySm] pero en gris: es como el diseño escribe la bajada
  /// de un título.
  static const TextStyle cuerpoChico = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 14,
    height: 20 / 14,
    fontWeight: FontWeight.w500,
    color: AppColors.onSurfaceVariant,
  );

  /// `body-sm` en semibold: el texto de los botones secundarios, tal como lo
  /// escribe el diseño.
  static const TextStyle etiquetaGrande = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 14,
    height: 20 / 14,
    fontWeight: FontWeight.w600,
    color: AppColors.onSurface,
  );

  static const TextStyle etiqueta = labelCaption;
  static const TextStyle etiquetaChica = labelCaption;

  /// Un serial o un identificador dentro de una fila apretada. Más chico que
  /// [labelTelemetry] a propósito: una tabla de diez filas con 16 px de
  /// monoespaciada no entra en un teléfono angosto.
  static const TextStyle datoChico = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 12,
    height: 16 / 12,
    fontWeight: FontWeight.w500,
    color: AppColors.onSurface,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// Igual que [datoChico] pero al tamaño de una fila normal.
  static const TextStyle dato = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 14,
    height: 20 / 14,
    fontWeight: FontWeight.w500,
    letterSpacing: -0.14,
    color: AppColors.onSurface,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// La medición dentro de una tarjeta, más chica que [medicion].
  static const TextStyle medicionChica = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 18,
    height: 24 / 18,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.18,
    color: AppColors.onSurface,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// Mapa a las ranuras de Material, para que un `Text` sin estilo propio
  /// caiga igual dentro del sistema.
  static const TextTheme temaTexto = TextTheme(
    headlineLarge: headlineXlMovil,
    headlineMedium: headlineLg,
    headlineSmall: headlineMd,
    titleLarge: headlineMd,
    titleMedium: tituloChico,
    bodyLarge: bodyMd,
    bodyMedium: bodySm,
    bodySmall: cuerpoChico,
    labelLarge: etiquetaGrande,
    labelMedium: labelCaption,
    labelSmall: labelBadge,
  );
}
