import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'dexter_sync_badge.dart';

/// Franja oscura bajo el encabezado: en qué anda lo que el técnico ya hizo.
///
/// Recibe todo armado. No consulta la cola ni la base: quien la usa le pasa el
/// estado, la frase y, si corresponde, qué hacer al tocar "Enviar ahora".
class DexterSyncStrip extends StatelessWidget {
  const DexterSyncStrip({
    super.key,
    required this.estado,
    required this.frase,
    this.onSincronizar,
  });

  final DexterSyncStatus estado;
  final String frase;

  /// Si es nulo, la franja solo informa.
  final VoidCallback? onSincronizar;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.tintaProfunda,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.margen,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          children: <Widget>[
            Icon(_icono, size: 16, color: _color),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                frase,
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.textoSobreOscuro,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (onSincronizar != null) ...<Widget>[
              const SizedBox(width: AppSpacing.sm),
              InkWell(
                onTap: onSincronizar,
                borderRadius: AppRadius.brChico,
                child: Container(
                  constraints: const BoxConstraints(
                    minHeight: AppSpacing.objetivoTactil,
                  ),
                  alignment: Alignment.center,
                  padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                  child: Text(
                    'ENVIAR AHORA',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.precaucion,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  IconData get _icono => switch (estado) {
        DexterSyncStatus.sincronizado => Icons.cloud_done_outlined,
        DexterSyncStatus.pendiente => Icons.arrow_upward,
        DexterSyncStatus.sincronizando => Icons.sync,
        DexterSyncStatus.error => Icons.warning_amber_rounded,
      };

  Color get _color => switch (estado) {
        DexterSyncStatus.sincronizado => AppColors.exito,
        DexterSyncStatus.pendiente => AppColors.precaucion,
        DexterSyncStatus.sincronizando => AppColors.textoSobreOscuro,
        DexterSyncStatus.error => AppColors.error,
      };
}
