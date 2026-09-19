import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'dexter_badge.dart';

/// En qué punto está un trabajo, desde el punto de vista de la operación.
///
/// Es deliberadamente corto y genérico: los estados concretos de una orden
/// (`asignada`, `en_camino`, `en_sitio`, `completada_pendiente_sync`…) se
/// traducen a uno de estos al dibujar cada pantalla, sin que este widget
/// conozca la máquina de estados ni la base de datos.
///
/// No confundir con [DexterSyncStatus]: que un trabajo esté completado no dice
/// nada sobre si su información ya viajó al servidor.
enum DexterOperationalStatus {
  /// Todavía no empezó.
  pendiente,

  /// En camino o en el sitio.
  enProceso,

  /// Terminado en campo.
  completada,

  /// No se puede avanzar: falta algo o alguien tiene que intervenir.
  bloqueada,
}

/// Pastilla del estado operativo de un trabajo.
class DexterStatusBadge extends StatelessWidget {
  const DexterStatusBadge({super.key, required this.estado, this.etiqueta});

  final DexterOperationalStatus estado;

  /// Texto a mostrar. Sin esto se usa el nombre genérico del estado; con esto
  /// se puede decir "EN CAMINO" o "EN SITIO" sin inventar un estado nuevo.
  final String? etiqueta;

  @override
  Widget build(BuildContext context) {
    final texto = etiqueta ?? _textoPorDefecto;
    return DexterBadge(
      icono: _icono,
      texto: texto,
      color: _color,
      fondo: _fondo,
      descripcionAccesible: 'Estado del trabajo: $texto',
    );
  }

  String get _textoPorDefecto => switch (estado) {
        DexterOperationalStatus.pendiente => 'Pendiente',
        DexterOperationalStatus.enProceso => 'En proceso',
        DexterOperationalStatus.completada => 'Completada',
        DexterOperationalStatus.bloqueada => 'Bloqueada',
      };

  IconData get _icono => switch (estado) {
        DexterOperationalStatus.pendiente => Icons.schedule,
        DexterOperationalStatus.enProceso => Icons.play_arrow,
        DexterOperationalStatus.completada => Icons.check_circle_outline,
        DexterOperationalStatus.bloqueada => Icons.pan_tool_outlined,
      };

  Color get _color => switch (estado) {
        DexterOperationalStatus.pendiente => AppColors.precaucion,
        DexterOperationalStatus.enProceso => AppColors.info,
        DexterOperationalStatus.completada => AppColors.exito,
        DexterOperationalStatus.bloqueada => AppColors.error,
      };

  Color get _fondo => switch (estado) {
        DexterOperationalStatus.pendiente => AppColors.precaucionFondo,
        DexterOperationalStatus.enProceso => AppColors.infoFondo,
        DexterOperationalStatus.completada => AppColors.exitoFondo,
        DexterOperationalStatus.bloqueada => AppColors.errorFondo,
      };
}
