import 'package:flutter/material.dart';

import 'app_colors.dart';
import 'app_radius.dart';
import 'app_spacing.dart';
import 'app_typography.dart';

export 'app_colors.dart';
export 'app_radius.dart';
export 'app_spacing.dart';
export 'app_typography.dart';

/// Tema de la aplicación, armado con los tokens de "Field Ops Precision".
///
/// Los colores, tamaños y radios no viven acá: viven en [AppColors],
/// [AppTypography], [AppSpacing] y [AppRadius]. Esta clase solo los conecta
/// con Material.
class AppTheme {
  const AppTheme._();

  // --- Elevación -----------------------------------------------------------
  // Bajo el sol una sombra difusa desaparece, así que la profundidad la dan
  // el borde y el tono de la superficie. Estas dos sombras son casi
  // imperceptibles a propósito.

  /// Tarjetas y módulos.
  static const List<BoxShadow> sombraNivel1 = <BoxShadow>[
    BoxShadow(color: Color(0x0F0F172A), blurRadius: 2, offset: Offset(0, 1)),
  ];

  /// Elementos fijos: encabezado, franja de sincronización, barra inferior.
  static const List<BoxShadow> sombraNivel2 = <BoxShadow>[
    BoxShadow(color: Color(0x140F172A), blurRadius: 12, offset: Offset(0, 4)),
  ];

  static ThemeData get lightTheme {
    const esquema = ColorScheme.light(
      primary: AppColors.azulAccion,
      onPrimary: AppColors.textoSobreOscuro,
      primaryContainer: AppColors.azulMarino,
      onPrimaryContainer: AppColors.textoSobreOscuro,
      secondary: AppColors.azulMarino,
      onSecondary: AppColors.textoSobreOscuro,
      tertiary: AppColors.exito,
      onTertiary: AppColors.textoSobreOscuro,
      surface: AppColors.superficie,
      onSurface: AppColors.texto,
      surfaceContainerLowest: AppColors.superficie,
      surfaceContainerLow: AppColors.fondo,
      surfaceContainer: AppColors.fondoHundido,
      onSurfaceVariant: AppColors.textoSecundario,
      outline: AppColors.bordeFuerte,
      outlineVariant: AppColors.borde,
      error: AppColors.error,
      onError: AppColors.textoSobreOscuro,
      errorContainer: AppColors.errorFondo,
      onErrorContainer: AppColors.error,
      scrim: AppColors.velo,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: esquema,
      scaffoldBackgroundColor: AppColors.fondo,
      fontFamily: AppTypography.familiaTexto,
      textTheme: AppTypography.temaTexto,
      dividerTheme: const DividerThemeData(
        color: AppColors.borde,
        thickness: 1,
        space: 1,
      ),

      // El encabezado propio del diseño (logo, estado de conexión, perfil)
      // llega en la Fase 3. Hasta entonces la barra sigue siendo sólida, para
      // no dejar ilegible el texto blanco que hoy escriben SyncBadge y las
      // pantallas existentes.
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.azulMarino,
        foregroundColor: AppColors.textoSobreOscuro,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontFamily: AppTypography.familiaTexto,
          fontSize: 18,
          height: 24 / 18,
          fontWeight: FontWeight.w600,
          color: AppColors.textoSobreOscuro,
        ),
      ),

      cardTheme: const CardThemeData(
        color: AppColors.superficie,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.brTarjeta,
          side: BorderSide(color: AppColors.borde),
        ),
        margin: EdgeInsets.symmetric(
          horizontal: AppSpacing.margen,
          vertical: AppSpacing.sm,
        ),
      ),

      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.azulAccion,
          foregroundColor: AppColors.textoSobreOscuro,
          disabledBackgroundColor: AppColors.fondoHundido,
          disabledForegroundColor: AppColors.inactivo,
          minimumSize: const Size.fromHeight(AppSpacing.objetivoTactil),
          elevation: 0,
          shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
          textStyle: AppTypography.cuerpoGrande.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.azulAccion,
          backgroundColor: AppColors.superficie,
          minimumSize: const Size.fromHeight(AppSpacing.objetivoTactil),
          side: const BorderSide(color: AppColors.borde),
          shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
          textStyle: AppTypography.cuerpoGrande.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.azulAccion,
          minimumSize: const Size(0, AppSpacing.objetivoTactil),
          textStyle: AppTypography.cuerpoGrande.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
      ),

      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: AppColors.superficie,
        contentPadding: EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.md,
        ),
        border: OutlineInputBorder(
          borderRadius: AppRadius.brCampo,
          borderSide: BorderSide(color: AppColors.bordeFuerte),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppRadius.brCampo,
          borderSide: BorderSide(color: AppColors.bordeFuerte),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppRadius.brCampo,
          borderSide: BorderSide(color: AppColors.azulAccion, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: AppRadius.brCampo,
          borderSide: BorderSide(color: AppColors.error),
        ),
        labelStyle: TextStyle(color: AppColors.textoSecundario),
        helperStyle: AppTypography.cuerpoChico,
      ),

      chipTheme: const ChipThemeData(
        backgroundColor: AppColors.fondoHundido,
        side: BorderSide(color: AppColors.borde),
        shape: RoundedRectangleBorder(borderRadius: AppRadius.brChico),
        labelStyle: AppTypography.etiqueta,
      ),

      snackBarTheme: const SnackBarThemeData(
        backgroundColor: AppColors.tintaProfunda,
        contentTextStyle: TextStyle(color: AppColors.textoSobreOscuro),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
      ),

      dialogTheme: const DialogThemeData(
        backgroundColor: AppColors.superficie,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: AppRadius.brHoja),
      ),

      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: AppColors.superficie,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppRadius.hoja),
          ),
        ),
      ),
    );
  }

  // --- Nombres anteriores --------------------------------------------------
  // Las pantallas actuales todavía nombran estos colores. Se mantienen
  // apuntando a los tokens nuevos para que la migración sea pantalla por
  // pantalla (Fases 4 a 10) y no un cambio de todo a la vez. Cuando la última
  // pantalla deje de usarlos, este bloque se borra.

  static const Color primaryBlue = AppColors.azulAccion;
  static const Color primaryDark = AppColors.azulMarino;
  static const Color accentAmber = AppColors.precaucion;
  static const Color surfaceLight = AppColors.fondo;
  static const Color cardBg = AppColors.superficie;
  static const Color textMain = AppColors.texto;
  static const Color textMuted = AppColors.textoSecundario;
  static const Color successGreen = AppColors.exito;
  static const Color warningOrange = AppColors.precaucion;
  static const Color errorRed = AppColors.error;
}
