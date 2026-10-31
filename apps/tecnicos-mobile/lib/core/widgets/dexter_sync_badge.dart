import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'dexter_badge.dart';

/// Si lo hecho en el teléfono ya viajó al servidor.
///
/// Dominio distinto del estado del trabajo ([DexterOperationalStatus]): una
/// orden terminada puede seguir sin sincronizar, y una sincronizada puede estar
/// a medio hacer.
enum DexterSyncStatus {
  /// Nada por enviar.
  sincronizado,

  /// Hay cambios guardados en el teléfono esperando su turno.
  pendiente,

  /// Enviando en este momento.
  sincronizando,

  /// El servidor rechazó algo, o hay un conflicto que alguien debe resolver.
  error,
}

/// Pastilla del estado de sincronización.
///
/// Solo dibuja. Quien la usa le pasa el estado y, si quiere, un detalle como
/// "4 pendientes" o "hace 2 min"; este widget no consulta la cola ni la base.
class DexterSyncBadge extends StatelessWidget {
  const DexterSyncBadge({
    super.key,
    required this.estado,
    this.detalle,
    this.onTap,
  });

  final DexterSyncStatus estado;

  /// Texto corto que acompaña al estado, ya armado por quien llama.
  final String? detalle;

  /// Por ejemplo, forzar una sincronización. Si es nulo, la pastilla no se toca.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final texto = detalle == null ? _textoPorDefecto : '$_textoPorDefecto · $detalle';
    final pastilla = DexterBadge(
      icono: _icono,
      texto: texto,
      color: _color,
      fondo: _fondo,
      descripcionAccesible: 'Sincronización: $texto',
    );

    if (onTap == null) return pastilla;

    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadius.brChico,
        child: ConstrainedBox(
          // Se toca, así que tiene que poder tocarse con guantes puestos.
          constraints: const BoxConstraints(
            minHeight: AppSpacing.objetivoTactil,
            minWidth: AppSpacing.objetivoTactil,
          ),
          child: Center(widthFactor: 1, child: pastilla),
        ),
      ),
    );
  }

  String get _textoPorDefecto => switch (estado) {
        DexterSyncStatus.sincronizado => 'Sincronizado',
        DexterSyncStatus.pendiente => 'Pendiente',
        DexterSyncStatus.sincronizando => 'Sincronizando',
        DexterSyncStatus.error => 'Conflicto',
      };

  IconData get _icono => switch (estado) {
        DexterSyncStatus.sincronizado => Icons.cloud_done_outlined,
        DexterSyncStatus.pendiente => Icons.arrow_upward,
        DexterSyncStatus.sincronizando => Icons.sync,
        DexterSyncStatus.error => Icons.warning_amber_rounded,
      };

  Color get _color => switch (estado) {
        DexterSyncStatus.sincronizado => AppColors.exito,
        DexterSyncStatus.pendiente => AppColors.precaucion,
        DexterSyncStatus.sincronizando => AppColors.info,
        DexterSyncStatus.error => AppColors.error,
      };

  Color get _fondo => switch (estado) {
        DexterSyncStatus.sincronizado => AppColors.exitoFondo,
        DexterSyncStatus.pendiente => AppColors.precaucionFondo,
        DexterSyncStatus.sincronizando => AppColors.infoFondo,
        DexterSyncStatus.error => AppColors.errorFondo,
      };
}
