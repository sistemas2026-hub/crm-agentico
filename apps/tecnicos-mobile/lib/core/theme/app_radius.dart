import 'package:flutter/widgets.dart';

/// Curvatura de "Field Ops Precision": industrial y contenida.
///
/// El diseño rechaza a propósito las formas de píldora, salvo en elementos
/// que son un punto o un contador circular.
class AppRadius {
  const AppRadius._();

  static const double chico = 4; // badges, etiquetas técnicas
  static const double campo = 6; // campos de formulario
  static const double tarjeta = 8; // tarjetas y botones
  static const double hoja = 12; // hojas inferiores y diálogos
  static const double completo = 999; // solo puntos e indicadores redondos

  static const BorderRadius brChico = BorderRadius.all(Radius.circular(chico));
  static const BorderRadius brCampo = BorderRadius.all(Radius.circular(campo));
  static const BorderRadius brTarjeta = BorderRadius.all(Radius.circular(tarjeta));
  static const BorderRadius brHoja = BorderRadius.all(Radius.circular(hoja));
}
