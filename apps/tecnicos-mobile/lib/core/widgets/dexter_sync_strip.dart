import 'package:flutter/material.dart';

import '../mock/field_mock_data.dart';
import '../theme/app_theme.dart';
import 'dexter_sync_badge.dart';

/// La franja oscura del diseño, debajo del encabezado.
///
/// Dice cuánto trabajo hecho todavía no salió del teléfono. El número es real
/// —sale de la cola—; lo único de ejemplo es la palabra de la derecha, que en
/// el diseño describe el modo de trabajo.
class DexterSyncStrip extends StatelessWidget {
  const DexterSyncStrip({
    super.key,
    required this.estado,
    required this.frase,
    this.cambiosLocales,
    this.onSincronizar,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final DexterSyncStatus estado;
  final String frase;

  /// Cuántos cambios hay guardados y sin enviar. Nulo mientras no se sabe.
  final int? cambiosLocales;

  final VoidCallback? onSincronizar;
  final bool mostrarDatosFuturos;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.margen,
          0,
          AppSpacing.margen,
          AppSpacing.sm,
        ),
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: 6,
          ),
          decoration: const BoxDecoration(
            color: AppColors.inverseSurface,
            borderRadius: AppRadius.brChico,
          ),
          child: Row(
            children: <Widget>[
              Icon(_icono, size: 14, color: _color),
              const SizedBox(width: 6),
              Expanded(
                child: Text.rich(
                  TextSpan(
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.inverseOnSurface,
                    ),
                    children: <InlineSpan>[
                      TextSpan(text: cambiosLocales == null ? '' : 'Cola de datos: '),
                      TextSpan(
                        text: cambiosLocales == null
                            ? frase
                            : cambiosLocales == 1
                                ? '1 cambio local'
                                : '$cambiosLocales cambios locales',
                        style: AppTypography.etiquetaChica.copyWith(
                          color: AppColors.surfaceBright,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (onSincronizar != null)
                InkWell(
                  onTap: onSincronizar,
                  borderRadius: AppRadius.brChico,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: 4,
                    ),
                    child: Text(
                      'ENVIAR AHORA',
                      style: AppTypography.etiquetaChica.copyWith(
                        color: AppColors.exitoFuerte,
                        fontWeight: FontWeight.w700,
                        fontSize: 10,
                      ),
                    ),
                  ),
                )
              else if (mostrarDatosFuturos)
                // CAMPO-DATA-022
                Text(
                  FieldMockData.modoDatos.toUpperCase(),
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.surfaceDim,
                    fontSize: 10,
                    letterSpacing: 0.8,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  IconData get _icono => switch (estado) {
        DexterSyncStatus.sincronizado => Icons.bolt,
        DexterSyncStatus.pendiente => Icons.bolt,
        DexterSyncStatus.sincronizando => Icons.sync,
        DexterSyncStatus.error => Icons.warning_amber_rounded,
      };

  Color get _color => switch (estado) {
        DexterSyncStatus.sincronizado => AppColors.exitoFuerte,
        DexterSyncStatus.pendiente => AppColors.exitoFuerte,
        DexterSyncStatus.sincronizando => AppColors.inverseOnSurface,
        DexterSyncStatus.error => AppColors.errorContainer,
      };
}
