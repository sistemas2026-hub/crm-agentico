import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'dexter_sync_badge.dart';

/// La franja oscura del diseño, debajo del encabezado.
///
/// Dice cuánto trabajo hecho todavía no salió del teléfono, y el número es
/// real: sale de la cola.
///
/// POR QUÉ ESTE WIDGET NO SABE QUÉ ES UNA DEMOSTRACIÓN
/// ---------------------------------------------------
/// Antes leía él mismo la bandera y el texto del modo de trabajo desde los
/// datos de ejemplo. Eso ponía al núcleo a depender de la demostración: un
/// widget que cualquiera reutiliza traía adentro una palabra que ningún
/// sistema entrega, y quien lo usara en otra pantalla se la llevaba sin
/// enterarse.
///
/// Ahora [etiquetaDeModo] entra por parámetro. Nula —lo normal— no se dibuja
/// nada. Quien quiera poner algo ahí tiene que decidirlo y escribirlo en su
/// propia pantalla, que es donde se puede ver de dónde salió.
class DexterSyncStrip extends StatelessWidget {
  const DexterSyncStrip({
    super.key,
    required this.estado,
    required this.frase,
    this.cambiosLocales,
    this.onSincronizar,
    this.etiquetaDeModo,
  });

  final DexterSyncStatus estado;
  final String frase;

  /// Cuántos cambios hay guardados y sin enviar. Nulo mientras no se sabe.
  final int? cambiosLocales;

  final VoidCallback? onSincronizar;

  /// Qué dice la esquina derecha cuando no hay nada que enviar. Nula: nada.
  ///
  /// El widget no sabe si eso es real o un ejemplo, y no tiene por qué: lo
  /// decide quien lo arma.
  final String? etiquetaDeModo;

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
              else if (etiquetaDeModo != null)
                Text(
                  etiquetaDeModo!.toUpperCase(),
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
