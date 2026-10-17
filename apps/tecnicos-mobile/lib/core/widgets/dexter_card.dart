import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Superficie base del diseño: blanca, con borde fino y esquinas contenidas.
///
/// La profundidad la da el borde, no una sombra difusa: al sol una sombra se
/// lava y la tarjeta pierde su límite.
class DexterCard extends StatelessWidget {
  const DexterCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(AppSpacing.md),
    this.onTap,
    this.colorAcento,
    this.colorBorde,
    this.colorFondo,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  /// Si se pasa, toda la tarjeta se vuelve tocable.
  final VoidCallback? onTap;

  /// Barra vertical a la izquierda. Sirve para destacar una tarjeta dentro de
  /// una lista (el trabajo en curso, un equipo serializado) sin cambiarle el
  /// fondo ni el tamaño.
  final Color? colorAcento;

  final Color? colorBorde;
  final Color? colorFondo;

  @override
  Widget build(BuildContext context) {
    final lineaFina = BorderSide(color: colorBorde ?? AppColors.borde);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colorFondo ?? AppColors.superficie,
        borderRadius: AppRadius.brTarjeta,
        border: Border.fromBorderSide(lineaFina),
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: ClipRRect(
        borderRadius: AppRadius.brTarjeta,
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            onTap: onTap,
            child: Container(
              // El acento es una franja a la izquierda, dentro del recorte:
              // así sigue el redondeo de la tarjeta y el alto lo sigue dando
              // el contenido, sin medirlo aparte en cada fila de la lista.
              decoration: colorAcento == null
                  ? null
                  : BoxDecoration(
                      border: Border(
                        left: BorderSide(color: colorAcento!, width: 4),
                      ),
                    ),
              padding: padding,
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}
