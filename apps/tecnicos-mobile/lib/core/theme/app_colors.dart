import 'package:flutter/material.dart';

/// Los colores exactos del diseño "DEXTER CAMPO" de Stitch.
///
/// Salen tal cual de la configuración de Tailwind que acompaña a las seis
/// pantallas de esa familia (`projects/1600097754179356553`, bajadas el
/// 25/09/2026): Detalle de Orden, Validación Técnica, Inicio del Técnico,
/// Materiales Utilizados, Evidencia Fotográfica y Cierre de Trabajo. Todas
/// llevan el sufijo "- DEXTER CAMPO" en el título, que es lo que las
/// distingue de los otros diseños del mismo proyecto.
///
/// POR QUE CAMBIARON RESPECTO DEL 22/09/2026
/// -----------------------------------------
/// La versión anterior de este archivo salía de "Dexter Campo Mobile App",
/// otro diseño del mismo producto: mismos NOMBRES de token, tonos distintos.
/// Dos diferencias se notan a simple vista y no son cosméticas:
///
///   * El terciario de aquel era un azul oscuro, así que el verde de "esto
///     está bien" hubo que inventarlo aparte. Acá NO hace falta: el verde es
///     un token del sistema, [onTertiaryContainer] (#009971), y el diseño lo
///     usa 17 veces como texto y 16 como fondo.
///   * El azul de acción era un celeste (#5BB8FE). Acá el botón dominante va
///     en [secondaryContainer] (#116df4), un azul saturado.
///
/// LO QUE ESTA FAMILIA NO TIENE
/// ----------------------------
/// No hay ámbar ni amarillo: se buscó en las seis pantallas y las únicas
/// apariciones son nombres de ícono. Un estado que pide atención se pinta con
/// [error] o con los verdes del sistema, nunca con un naranja que el diseño
/// no declara.
class AppColors {
  const AppColors._();

  // --- Marca ---------------------------------------------------------------
  /// El azul casi negro de la marca: títulos de dato y cifras destacadas.
  static const Color primary = Color(0xFF000615);
  static const Color onPrimary = Color(0xFFFFFFFF);

  /// El navy de las cintas y los bloques oscuros.
  static const Color primaryContainer = Color(0xFF0B1F3A);
  static const Color onPrimaryContainer = Color(0xFF7587A7);
  static const Color primaryFixed = Color(0xFFD6E3FF);
  static const Color primaryFixedDim = Color(0xFFB5C7EA);
  static const Color onPrimaryFixed = Color(0xFF071C36);
  static const Color onPrimaryFixedVariant = Color(0xFF364764);

  /// El azul de acción: íconos, enlaces y acentos.
  static const Color secondary = Color(0xFF0055C6);
  static const Color onSecondary = Color(0xFFFFFFFF);

  /// El azul del botón dominante. Más saturado que [secondary] a propósito:
  /// en el diseño es el único relleno de ese tono y marca la acción principal
  /// de cada pantalla.
  static const Color secondaryContainer = Color(0xFF116DF4);
  static const Color onSecondaryContainer = Color(0xFFFEFCFF);
  static const Color secondaryFixed = Color(0xFFD9E2FF);
  static const Color secondaryFixedDim = Color(0xFFB0C6FF);
  static const Color onSecondaryFixed = Color(0xFF001945);
  static const Color onSecondaryFixedVariant = Color(0xFF00429C);

  // --- Terciario: el verde del sistema ------------------------------------
  // Ojo con los nombres, que acá son contraintuitivos: 'tertiary' es un verde
  // tan oscuro que se lee negro, y el verde que se VE es 'onTertiaryContainer'.

  static const Color tertiary = Color(0xFF000704);
  static const Color onTertiary = Color(0xFFFFFFFF);

  /// El verde oscuro de fondo, para bloques que afirman algo cumplido.
  static const Color tertiaryContainer = Color(0xFF002418);

  /// EL VERDE. Relleno de las insignias en regla y de los tramos buenos de
  /// una barra; también el texto verde sobre superficie clara.
  static const Color onTertiaryContainer = Color(0xFF009971);

  /// Verde claro, para texto sobre [tertiaryContainer].
  static const Color tertiaryFixed = Color(0xFF67FCC6);

  /// Verde medio: el tramo "aceptable pero no ideal" de una barra segmentada.
  static const Color tertiaryFixedDim = Color(0xFF44DFAB);
  static const Color onTertiaryFixed = Color(0xFF002116);
  static const Color onTertiaryFixedVariant = Color(0xFF00513A);

  // --- Superficies ---------------------------------------------------------
  static const Color surface = Color(0xFFF7F9FF);
  static const Color surfaceBright = Color(0xFFF7F9FF);
  static const Color surfaceDim = Color(0xFFCDDCED);
  static const Color surfaceContainerLowest = Color(0xFFFFFFFF);
  static const Color surfaceContainerLow = Color(0xFFEDF4FF);
  static const Color surfaceContainer = Color(0xFFE2EFFF);
  static const Color surfaceContainerHigh = Color(0xFFDBEAFB);
  static const Color surfaceContainerHighest = Color(0xFFD6E4F5);
  static const Color surfaceVariant = Color(0xFFD6E4F5);

  static const Color onSurface = Color(0xFF0F1D29);
  static const Color onSurfaceVariant = Color(0xFF44474D);
  static const Color outline = Color(0xFF75777E);
  static const Color outlineVariant = Color(0xFFC4C6CE);

  /// La franja oscura: cola de datos, cintas de estado invertidas.
  static const Color inverseSurface = Color(0xFF24323F);
  static const Color inverseOnSurface = Color(0xFFE8F2FF);
  static const Color inversePrimary = Color(0xFFB5C7EA);

  // --- Error ---------------------------------------------------------------
  static const Color error = Color(0xFFBA1A1A);
  static const Color onError = Color(0xFFFFFFFF);
  static const Color errorContainer = Color(0xFFFFDAD6);
  static const Color onErrorContainer = Color(0xFF93000A);

  /// Velo de diálogos y hojas.
  static const Color velo = Color(0x990F1D29);

  // --- Nombres de la primera versión --------------------------------------
  // El código de las pantallas ya construidas los usa. Se mantienen apuntando
  // al token de Stitch que les corresponde, así cambiar la paleta no obliga a
  // tocar cada widget en el mismo commit.

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

  /// El verde de "esto está bien", que acá SÍ es un token del sistema.
  static const Color exito = onTertiaryContainer;
  static const Color exitoFuerte = tertiaryFixedDim;

  /// Fondo de una insignia verde. En el diseño el chip no lleva un verde
  /// claro propio: es [surfaceContainerHigh] con el texto en verde. Se
  /// respeta eso y no se inventa un tinte que la paleta no declara.
  static const Color exitoFondo = surfaceContainerHigh;
  static const Color exitoTexto = onTertiaryFixedVariant;

  /// Esta familia no declara un ámbar. Lo que pide atención se dice con el
  /// azul de acción sobre superficie elevada —que es como el diseño marca lo
  /// pendiente— y lo que está mal, con [error].
  static const Color precaucion = onSecondaryFixedVariant;
  static const Color precaucionFondo = secondaryFixed;

  static const Color errorFondo = errorContainer;
  static const Color info = secondary;
  static const Color infoFondo = secondaryFixed;
  static const Color inactivo = outline;
  static const Color inactivoFondo = surfaceContainer;
}
