import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Escala tipográfica del proyecto de Stitch "Dexter Campo  App".
///
/// Dos motores distintos, a propósito:
///   * texto de interfaz  -> Inter
///   * datos técnicos     -> JetBrains Mono (cifras tabulares: una medición que
///     cambia en vivo no debe mover el resto de la fila)
///
/// Migrado el 22/09/2026 desde el otro proyecto del mismo producto, que usaba
/// Geist y ponía también las etiquetas en monoespaciada. Acá la monoespaciada
/// queda solo para los datos (`data-mono-*`): las etiquetas son Inter.
///
/// Las dos familias van empaquetadas en la aplicación y se declaran en
/// `pubspec.yaml`; su origen, versión y licencia están en
/// `assets/fonts/LEEME.md`. Los nombres viven acá y en ningún otro lado:
/// ningún widget escribe 'Inter' ni 'JetBrainsMono'.
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

  // --- Títulos -------------------------------------------------------------

  static const TextStyle tituloGrande = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 24, // headline-lg-mobile: la app es de móvil
    height: 32 / 24,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.48, // -0.02em
    color: AppColors.texto,
  );

  static const TextStyle tituloMedio = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 20, // headline-md
    height: 28 / 20,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.2, // -0.01em
    color: AppColors.texto,
  );

  static const TextStyle tituloChico = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 16, // headline-sm
    height: 24 / 16,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.08, // -0.005em
    color: AppColors.texto,
  );

  // --- Cuerpo --------------------------------------------------------------

  static const TextStyle cuerpoGrande = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 16, // body-lg
    height: 24 / 16,
    fontWeight: FontWeight.w400,
    color: AppColors.texto,
  );

  static const TextStyle cuerpo = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 14, // body-md
    height: 20 / 14,
    fontWeight: FontWeight.w400,
    color: AppColors.texto,
  );

  static const TextStyle cuerpoChico = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 13, // body-sm
    height: 18 / 13,
    fontWeight: FontWeight.w400,
    color: AppColors.textoSecundario,
  );

  // --- Etiquetas -----------------------------------------------------------
  // En este sistema visual las etiquetas son de interfaz, no de dato: van en
  // Inter. La monoespaciada queda para los números que hay que leer y comparar.

  static const TextStyle etiquetaGrande = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 14, // label-lg
    height: 20 / 14,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.14, // 0.01em
    color: AppColors.texto,
  );

  static const TextStyle etiqueta = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 12, // label-md
    height: 16 / 12,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.24, // 0.02em
    color: AppColors.textoSecundario,
  );

  static const TextStyle etiquetaChica = TextStyle(
    fontFamily: familiaTexto,
    fontSize: 11, // label-sm
    height: 14 / 11,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.44, // 0.04em
    color: AppColors.textoSecundario,
  );

  // --- Datos técnicos (monoespaciados) -------------------------------------

  /// data-mono-sm: seriales, puertos, identificadores en una fila.
  static const TextStyle datoChico = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 12,
    height: 16 / 12,
    fontWeight: FontWeight.w500,
    color: AppColors.texto,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// data-mono-md: una cifra dentro de una fila de datos.
  static const TextStyle dato = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 14,
    height: 20 / 14,
    fontWeight: FontWeight.w500,
    letterSpacing: -0.14,
    color: AppColors.texto,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// Lectura grande: potencia óptica, metraje, conteos del kit. El diseño usa
  /// la familia `data-mono-lg` a 28 px para la medición que hay que mirar de
  /// lejos, y a 18 px cuando va dentro de una tarjeta.
  static const TextStyle medicion = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 28,
    height: 32 / 28,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.56, // -0.02em
    color: AppColors.texto,
    fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  );

  /// data-mono-lg tal cual: la medición dentro de una tarjeta.
  static const TextStyle medicionChica = TextStyle(
    fontFamily: familiaMono,
    fontFamilyFallback: respaldoMono,
    fontSize: 18,
    height: 24 / 18,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.36, // -0.02em
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
