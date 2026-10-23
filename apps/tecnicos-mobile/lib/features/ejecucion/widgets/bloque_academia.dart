import 'package:flutter/material.dart';

import '../../../demo/field_mock_data.dart';
import '../../../core/theme/app_theme.dart';

/// CAMPO-DATA-028 · Academia dentro de la orden.
///
/// El diseño pone el material de consulta al lado del formulario, para que
/// nadie tenga que salirse del trabajo para recordar un procedimiento. El
/// módulo de Academia todavía no existe, así que el bloque entero vive detrás
/// del modo demostración: no valida nada, no completa ninguna respuesta y no
/// habilita el cierre de la orden.
class BloqueAcademia extends StatelessWidget {
  const BloqueAcademia({
    super.key,
    this.capsulas = FieldMockData.capsulasAcademia,
  });

  final List<CapsulaAcademia> capsulas;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: const BoxDecoration(
        color: AppColors.surfaceVariant,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.school, size: 20, color: AppColors.primary),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  'ACADEMIA DEXTER',
                  style: AppTypography.etiqueta.copyWith(
                    color: AppColors.primary,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.primary,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Text(
                  'Soporte In-Situ',
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            '¿Dudas con este procedimiento? Consultá las cápsulas rápidas sin '
            'salir de la orden de trabajo:',
            style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurface),
          ),
          const SizedBox(height: AppSpacing.md),
          for (final CapsulaAcademia capsula in capsulas) ...<Widget>[
            _FilaCapsula(
              capsula: capsula,
              alTocar: () => _abrir(context, capsula),
            ),
            if (capsula != capsulas.last) const SizedBox(height: AppSpacing.xs),
          ],
        ],
      ),
    );
  }

  Future<void> _abrir(BuildContext context, CapsulaAcademia capsula) {
    return showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.surfaceContainerLowest,
      shape: const RoundedRectangleBorder(borderRadius: AppRadius.brHoja),
      // La guía puede ser más alta que media pantalla: que se pueda desplazar
      // es parte de poder leerla parado en la calle.
      isScrollControlled: true,
      builder: (BuildContext hoja) {
        return SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    const Icon(Icons.verified, size: 20, color: AppColors.secondary),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        'Guía de Campo Express',
                        style: AppTypography.tituloChico,
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () => Navigator.of(hoja).pop(),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  capsula.encabezado,
                  style: AppTypography.cuerpo.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: AppSpacing.sm),
                for (final String paso in capsula.pasos)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.xs),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text('· ', style: AppTypography.cuerpoChico),
                        Expanded(child: Text(paso, style: AppTypography.cuerpoChico)),
                      ],
                    ),
                  ),
                const SizedBox(height: AppSpacing.md),
                SizedBox(
                  width: double.infinity,
                  height: AppSpacing.objetivoTactil,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      foregroundColor: AppColors.onPrimary,
                      shape: const RoundedRectangleBorder(
                        borderRadius: AppRadius.brTarjeta,
                      ),
                    ),
                    onPressed: () => Navigator.of(hoja).pop(),
                    child: const Text('Entendido, continuar trabajo'),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _FilaCapsula extends StatelessWidget {
  const _FilaCapsula({required this.capsula, required this.alTocar});

  final CapsulaAcademia capsula;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surfaceContainerLowest,
      borderRadius: AppRadius.brTarjeta,
      child: InkWell(
        borderRadius: AppRadius.brTarjeta,
        onTap: alTocar,
        child: Container(
          height: AppSpacing.objetivoTactil,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          child: Row(
            children: <Widget>[
              Icon(
                capsula.esVideo ? Icons.play_circle : Icons.menu_book,
                size: 20,
                color: capsula.esVideo ? AppColors.error : AppColors.secondary,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  capsula.titulo,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
                ),
              ),
              const Icon(Icons.chevron_right, size: 18, color: AppColors.outline),
            ],
          ),
        ),
      ),
    );
  }
}
