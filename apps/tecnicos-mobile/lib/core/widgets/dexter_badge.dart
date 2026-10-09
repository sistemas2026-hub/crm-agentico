import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Pastilla compacta: icono + texto en mayúsculas, sobre un fondo tenue.
///
/// Es solo presentación. No sabe qué significa lo que muestra: el significado
/// lo ponen [DexterStatusBadge] (estado del trabajo) y [DexterSyncBadge]
/// (estado de la sincronización), que son dominios distintos aunque se vean
/// parecido.
///
/// El icono no es decorativo: bajo el sol, o para quien distingue mal los
/// colores, el color solo no alcanza para diferenciar un estado de otro.
class DexterBadge extends StatelessWidget {
  const DexterBadge({
    super.key,
    required this.icono,
    required this.texto,
    required this.color,
    required this.fondo,
    this.descripcionAccesible,
  });

  final IconData icono;
  final String texto;

  /// Color del icono y del texto.
  final Color color;
  final Color fondo;

  /// Qué anuncia un lector de pantalla. Si no se pasa, lee [texto].
  final String? descripcionAccesible;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: descripcionAccesible ?? texto,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: fondo,
          borderRadius: AppRadius.brChico,
          border: Border.all(color: color.withValues(alpha: 0.30)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icono, size: 14, color: color),
            const SizedBox(width: AppSpacing.xs),
            Flexible(
              child: Text(
                texto.toUpperCase(),
                style: AppTypography.etiquetaChica.copyWith(color: color),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
