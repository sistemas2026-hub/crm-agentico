import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Escala tipográfica de "Field Ops Precision".
///
/// Dos motores distintos, a propósito:
///   * texto de interfaz  -> Geist
///   * datos técnicos     -> JetBrains Mono (cifras tabulares: una medición que
///     cambia en vivo no debe mover el resto de la fila)
///
/// Las dos familias van empaquetadas en la aplicación y se declaran en
/// `pubspec.yaml`; su origen, versión y licencia están en
/// `assets/fonts/LEEME.md`. Los nombres viven acá y en ningún otro lado:
/// ningún widget escribe 'Geist' ni 'JetBrainsMono'.
class AppTypography {
  const AppTypography._();

  static const String familiaTexto = 'Geist';
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

  // --- Títulos -------------------------------------------------------------

  static const TextStyle tituloGrande = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 24, // headline-lg-mobile: la app es de móvil
    height: 30 / 24,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.36, // -0.015em
    color: AppColors.texto,
  );

  static const TextStyle tituloMedio = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 20,
    height: 26 / 20,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.2,
    color: AppColors.texto,
  );

  static const TextStyle tituloChico = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 18,
    height: 24 / 18,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.09,
    color: AppColors.texto,
  );

  // --- Cuerpo --------------------------------------------------------------

  static const TextStyle cuerpoGrande = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 16,
    height: 24 / 16,
    fontWeight: FontWeight.w500,
    color: AppColors.texto,
  );

  static const TextStyle cuerpo = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 15,
    height: 22 / 15,
    fontWeight: FontWeight.w400,
    color: AppColors.texto,
  );

  static const TextStyle cuerpoChico = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 13,
    height: 18 / 13,
    fontWeight: FontWeight.w400,
    color: AppColors.textoSecundario,
  );

  // --- Etiquetas técnicas (monoespaciadas) ---------------------------------

  static const TextStyle etiquetaGrande = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 14,
    height: 20 / 14,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.28, // 0.02em
    color: AppColors.texto,
  );

  static const TextStyle etiqueta = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 12,
    height: 16 / 12,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.36,
    color: AppColors.textoSecundario,
  );

  static const TextStyle etiquetaChica = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 11,
    height: 14 / 11,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.44,
    color: AppColors.textoSecundario,
  );

  /// Lectura grande: potencia óptica, metraje, conteos del kit.
  static const TextStyle medicion = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 28,
    height: 32 / 28,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.84,
    color: AppColors.texto,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// Mapa a las ranuras de Material, para que un `Text` sin estilo propio
  /// caiga igual dentro del sistema.
  static const TextTheme temaTexto = TextTheme(
    headlineLarge: tituloGrande,
    headlineMedium: tituloMedio,
    headlineSmall: tituloChico,
    titleLarge: tituloChico,
    titleMedium: cuerpoGrande,
    bodyLarge: cuerpoGrande,
    bodyMedium: cuerpo,
    bodySmall: cuerpoChico,
    labelLarge: etiquetaGrande,
    labelMedium: etiqueta,
    labelSmall: etiquetaChica,
  );
}
