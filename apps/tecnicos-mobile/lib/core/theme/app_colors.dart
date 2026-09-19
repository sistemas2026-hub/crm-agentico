import 'package:flutter/material.dart';

/// Paleta del sistema visual "Field Ops Precision" (Google Stitch).
///
/// Calibrada para leerse bajo luz solar directa: fondos fríos, tarjetas
/// blancas con borde de 1 px y estados con color fuerte sobre fondo tenue.
/// Los valores salen del diseño, no se inventan: si hace falta un color que
/// Stitch no define, se agrega acá y se deja anotado de dónde salió.
class AppColors {
  const AppColors._();

  // Marca
  static const Color azulMarino = Color(0xFF1E3A8A); // barras, encabezados, CTA principal
  static const Color azulAccion = Color(0xFF2563EB); // botones, enlaces, pestaña activa
  static const Color tintaProfunda = Color(0xFF0F172A); // texto principal e iconos

  // Lienzo y superficies
  static const Color fondo = Color(0xFFF8FAFC);
  static const Color fondoHundido = Color(0xFFF1F5F9);
  static const Color superficie = Color(0xFFFFFFFF); // tarjetas y hojas
  static const Color borde = Color(0xFFE2E8F0); // keyline de 1 px
  static const Color bordeFuerte = Color(0xFFCBD5E1); // elementos fijos y barras

  // Texto
  static const Color texto = tintaProfunda;
  static const Color textoSecundario = Color(0xFF444651);
  static const Color textoSobreOscuro = Color(0xFFFFFFFF);

  // Estados operativos. Cada uno con su fondo tenue para badges y avisos.
  static const Color exito = Color(0xFF059669); // sincronizado, dentro de umbral
  static const Color exitoFondo = Color(0xFFECFDF5);
  static const Color precaucion = Color(0xFFD97706); // pendiente, en espera
  static const Color precaucionFondo = Color(0xFFFFFBEB);
  static const Color error = Color(0xFFDC2626); // conflicto, fuera de rango
  static const Color errorFondo = Color(0xFFFEF2F2);
  static const Color info = azulAccion; // en curso
  static const Color infoFondo = Color(0xFFEFF6FF);
  static const Color inactivo = Color(0xFF64748B); // offline, borrador guardado
  // Stitch no define fondo para el estado inactivo; se usa el lienzo hundido,
  // que es el tono que ya emplea para bloques neutros.
  static const Color inactivoFondo = fondoHundido;

  /// Velo de los diálogos y hojas inferiores (60 % sobre la tinta profunda).
  static const Color velo = Color(0x990F172A);
}
