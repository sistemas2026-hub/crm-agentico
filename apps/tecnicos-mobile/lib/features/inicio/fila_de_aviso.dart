/// Una alerta de la jornada, dibujada.
///
/// Salió de `inicio_screen.dart` el 09/11/2026, cuando estas alertas se
/// mudaron al panel de la campana: era un widget privado de esa pantalla y el
/// contenedor no podía dibujarlo. Lo que hace es lo mismo que hacía ahí.
///
/// Lo grave va en rojo con su triángulo; lo demás, en gris con la nube. El
/// color lo decide la gravedad que trae el aviso, nunca este widget: acá no
/// vive ningún umbral.
library;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import 'resumen_de_inicio.dart';

class FilaDeAviso extends StatelessWidget {
  const FilaDeAviso({super.key, required this.aviso, this.alTocar});

  final AvisoDeInicio aviso;

  /// Qué hacer al tocarla (09/11/2026). Nulo cuando el aviso no lleva a
  /// ningún lado, y entonces no se dibuja la flecha ni reacciona al toque: un
  /// toque que no hace nada se siente como una aplicación rota.
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    final Widget fila = _fila();
    if (alTocar == null) return fila;
    return Semantics(
      container: true,
      button: true,
      label: '${aviso.titulo}. ${aviso.detalle}',
      excludeSemantics: true,
      child: InkWell(
        onTap: alTocar,
        borderRadius: AppRadius.brTarjeta,
        child: fila,
      ),
    );
  }

  Widget _fila() {
    final bool grave = aviso.gravedad == GravedadDeAviso.alta;
    final Color color = grave ? AppColors.error : AppColors.onSurfaceVariant;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: grave
            ? AppColors.errorContainer
            : AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            grave ? Icons.warning_amber_rounded : Icons.cloud_upload_outlined,
            size: 18,
            color: grave ? AppColors.onErrorContainer : color,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  aviso.titulo,
                  style: AppTypography.etiquetaGrande.copyWith(
                    color:
                        grave ? AppColors.onErrorContainer : AppColors.onSurface,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  aviso.detalle,
                  style: AppTypography.cuerpoChico.copyWith(
                    color: grave ? AppColors.onErrorContainer : color,
                  ),
                ),
              ],
            ),
          ),
          // La flecha solo cuando lleva a algún lado: es lo que distingue, de
          // un vistazo, el aviso que se puede tocar del que solo informa.
          if (alTocar != null) ...<Widget>[
            const SizedBox(width: AppSpacing.xs),
            Icon(
              Icons.chevron_right,
              size: 20,
              color: grave ? AppColors.onErrorContainer : color,
            ),
          ],
        ],
      ),
    );
  }
}
