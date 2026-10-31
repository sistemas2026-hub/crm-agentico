import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Qué mostrar cuando una lista no tiene nada.
///
/// Distingue el vacío tranquilo ("no hay trabajos para hoy") del vacío que
/// avisa de un problema ("no se pudo leer"), porque para el técnico no
/// significan lo mismo.
class DexterEmptyState extends StatelessWidget {
  const DexterEmptyState({
    super.key,
    required this.icono,
    required this.titulo,
    this.mensaje,
    this.textoAccion,
    this.onAccion,
    this.esAdvertencia = false,
  });

  final IconData icono;
  final String titulo;
  final String? mensaje;

  /// Si se pasan los dos, aparece un botón. Por ejemplo, reintentar.
  final String? textoAccion;
  final VoidCallback? onAccion;

  final bool esAdvertencia;

  @override
  Widget build(BuildContext context) {
    final color = esAdvertencia ? AppColors.precaucion : AppColors.inactivo;

    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.xl,
        vertical: AppSpacing.xl,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: esAdvertencia ? AppColors.precaucionFondo : AppColors.fondoHundido,
              borderRadius: AppRadius.brTarjeta,
            ),
            child: Icon(icono, size: 28, color: color),
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            titulo,
            style: AppTypography.tituloChico,
            textAlign: TextAlign.center,
          ),
          if (mensaje != null) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(
              mensaje!,
              style: AppTypography.cuerpo.copyWith(color: AppColors.textoSecundario),
              textAlign: TextAlign.center,
            ),
          ],
          if (textoAccion != null && onAccion != null) ...<Widget>[
            const SizedBox(height: AppSpacing.lg),
            OutlinedButton(onPressed: onAccion, child: Text(textoAccion!)),
          ],
        ],
      ),
    );
  }
}
