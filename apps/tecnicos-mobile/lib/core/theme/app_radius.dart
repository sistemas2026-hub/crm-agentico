import 'package:flutter/widgets.dart';

/// Curvatura, con los valores exactos del diseño.
///
/// Salen de la configuración de Tailwind de las pantallas de Stitch
/// ("Dexter Campo  App", 22/09/2026):
///
/// ```
/// DEFAULT : 0.25rem  →  4 px
/// lg      : 0.5rem   →  8 px
/// xl      : 0.75rem  → 12 px
/// full    : 9999px   → círculo
/// ```
///
/// Cambio respecto del proyecto anterior: acá `rounded-full` **sí** es un
/// círculo, así que los avatares y los chips vuelven a ser redondos.
class AppRadius {
  const AppRadius._();

  /// Pastillas y etiquetas técnicas.
  static const double chico = 4;

  /// Campos, botones chicos e iconos en caja.
  static const double campo = 4;

  /// Tarjetas y botones grandes.
  static const double tarjeta = 8;

  /// Tarjetas grandes, hojas y modales: lo que el diseño llama `xl`.
  static const double completo = 12;

  /// Lo que el diseño llama "full": avatares, chips y puntos de estado.
  static const double circulo = 999;

  static const BorderRadius brChico = BorderRadius.all(Radius.circular(chico));
  static const BorderRadius brCampo = BorderRadius.all(Radius.circular(campo));
  static const BorderRadius brTarjeta = BorderRadius.all(Radius.circular(tarjeta));
  static const BorderRadius brCompleto = BorderRadius.all(Radius.circular(completo));

  /// Nombre de la primera versión: las hojas y diálogos usan el radio "full".
  static const double hoja = completo;
  static const BorderRadius brHoja = brCompleto;
}
