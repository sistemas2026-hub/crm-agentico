import 'package:flutter/material.dart';

/// Los colores exactos del proyecto de Stitch "Dexter Campo  App".
///
/// Salen de la configuración de Tailwind que acompaña a las pantallas, que es
/// lo que se ve en el diseño.
///
/// El 22/09/2026 se migró desde el otro proyecto de Stitch del mismo producto
/// ("Dexter Campo Mobile App"): mismos nombres de token, tonos distintos. La
/// diferencia que más se nota es el terciario, que acá es un azul oscuro y no
/// un verde; lo correcto se pinta con [exito], que sí es verde.
class AppColors {
  const AppColors._();

  // --- Marca ---------------------------------------------------------------
  /// Texto y acentos de marca. El azul más oscuro.
  static const Color primary = Color(0xFF001D41);
  static const Color onPrimary = Color(0xFFFFFFFF);

  /// Barras y cintas de estado.
  static const Color primaryContainer = Color(0xFF0F3260);
  static const Color onPrimaryContainer = Color(0xFF7E9BD0);
  static const Color primaryFixed = Color(0xFFD6E3FF);
  static const Color primaryFixedDim = Color(0xFFAAC7FE);

  /// El azul de acción: botones principales y enlaces.
  static const Color secondary = Color(0xFF006398);
  static const Color onSecondary = Color(0xFFFFFFFF);
  static const Color secondaryContainer = Color(0xFF5BB8FE);
  static const Color onSecondaryContainer = Color(0xFF00476E);
  static const Color secondaryFixed = Color(0xFFCCE5FF);
  static const Color secondaryFixedDim = Color(0xFF93CCFF);

  /// El verde de "esto está bien".
  static const Color tertiary = Color(0xFF0F1E30);
  static const Color onTertiary = Color(0xFFFFFFFF);
  static const Color tertiaryContainer = Color(0xFF253346);
  static const Color onTertiaryContainer = Color(0xFF8D9BB2);
  static const Color tertiaryFixed = Color(0xFFD5E3FC);
  static const Color tertiaryFixedDim = Color(0xFFB9C7DF);

  // --- Superficies ---------------------------------------------------------
  static const Color surface = Color(0xFFF8F9FF);
  static const Color surfaceBright = Color(0xFFF8F9FF);
  static const Color surfaceDim = Color(0xFFCBDBF5);
  static const Color surfaceContainerLowest = Color(0xFFFFFFFF);
  static const Color surfaceContainerLow = Color(0xFFEFF4FF);
  static const Color surfaceContainer = Color(0xFFE5EEFF);
  static const Color surfaceContainerHigh = Color(0xFFDCE9FF);
  static const Color surfaceContainerHighest = Color(0xFFD3E4FE);
  static const Color surfaceVariant = Color(0xFFD3E4FE);

  static const Color onSurface = Color(0xFF0B1C30);
  static const Color onSurfaceVariant = Color(0xFF43474F);
  static const Color outline = Color(0xFF747780);
  static const Color outlineVariant = Color(0xFFC4C6D0);

  /// La franja oscura de la cola de datos.
  static const Color inverseSurface = Color(0xFF213145);
  static const Color inverseOnSurface = Color(0xFFEAF1FF);
  static const Color inversePrimary = Color(0xFFAAC7FE);

  // --- Error ---------------------------------------------------------------
  static const Color error = Color(0xFFBA1A1A);
  static const Color onError = Color(0xFFFFFFFF);
  static const Color errorContainer = Color(0xFFFFDAD6);
  static const Color onErrorContainer = Color(0xFF93000A);

  /// Velo de diálogos y hojas.
  static const Color velo = Color(0x990B1C30);

  // --- Nombres de la primera versión --------------------------------------
  // El código de las pantallas ya construidas los usa. Se mantienen apuntando
  // al token de Stitch que les corresponde, así el cambio de paleta no exige
  // tocar cada widget de una sola vez.

  static const Color azulMarino = primaryContainer;
  static const Color azulAccion = secondary;
  static const Color tintaProfunda = onSurface;
  static const Color fondo = surface;
  static const Color fondoHundido = surfaceContainerLow;
  static const Color superficie = surfaceContainerLowest;
  static const Color borde = surfaceContainerHigh;
  static const Color bordeFuerte = outlineVariant;
  static const Color texto = onSurface;
  static const Color textoSecundario = onSurfaceVariant;
  static const Color textoSobreOscuro = onPrimary;

  /// El verde del diseño. En este sistema visual el terciario tonal es un
  /// azul oscuro, así que lo correcto —una verificación hecha, una lectura en
  /// rango— se pinta con un verde propio, como en las pantallas.
  static const Color exito = Color(0xFF059669);
  static const Color exitoFuerte = Color(0xFF10B981);
  static const Color exitoFondo = Color(0xFFECFDF5);
  static const Color exitoTexto = Color(0xFF047857);
  static const Color precaucion = Color(0xFF8A5100);
  static const Color precaucionFondo = Color(0xFFFFDDB3);
  static const Color errorFondo = errorContainer;
  static const Color info = secondary;
  static const Color infoFondo = secondaryFixed;
  static const Color inactivo = outline;
  static const Color inactivoFondo = surfaceContainer;
}
