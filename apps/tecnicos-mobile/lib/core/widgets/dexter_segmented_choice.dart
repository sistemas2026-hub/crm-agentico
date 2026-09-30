import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Una opción de [DexterSegmentedChoice].
class DexterChoiceOption<T> {
  const DexterChoiceOption({
    required this.valor,
    required this.etiqueta,
    this.icono,
  });

  final T valor;
  final String etiqueta;
  final IconData? icono;
}

/// Grupo de opciones excluyentes, en botones anchos.
///
/// Reemplaza a los botones de radio en una pantalla que se usa de pie, con
/// guantes y una sola mano: cada opción es un blanco de 48 px, no un punto de
/// 20. La elegida se marca con color **y** con un tilde, porque el color solo
/// no se distingue al sol.
///
/// Es genérico a propósito: no sabe qué se está eligiendo. La conexión con el
/// formulario dinámico llega en la Fase 7; hasta entonces sirve para cualquier
/// elección de la interfaz.
class DexterSegmentedChoice<T> extends StatelessWidget {
  const DexterSegmentedChoice({
    super.key,
    required this.opciones,
    required this.valor,
    required this.onChanged,
    this.habilitado = true,
  });

  final List<DexterChoiceOption<T>> opciones;

  /// La opción elegida, o `null` si todavía no se eligió ninguna.
  final T? valor;

  /// Nulo deja el grupo en modo lectura.
  final ValueChanged<T>? onChanged;

  final bool habilitado;

  @override
  Widget build(BuildContext context) {
    final activo = habilitado && onChanged != null;

    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: <Widget>[
        for (final DexterChoiceOption<T> opcion in opciones)
          _Opcion<T>(
            opcion: opcion,
            seleccionada: opcion.valor == valor,
            onTap: activo ? () => onChanged!(opcion.valor) : null,
          ),
      ],
    );
  }
}

class _Opcion<T> extends StatelessWidget {
  const _Opcion({
    required this.opcion,
    required this.seleccionada,
    required this.onTap,
  });

  final DexterChoiceOption<T> opcion;
  final bool seleccionada;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final color = seleccionada ? AppColors.textoSobreOscuro : AppColors.texto;
    final fondo = seleccionada ? AppColors.azulMarino : AppColors.superficie;
    final borde = seleccionada ? AppColors.azulMarino : AppColors.borde;

    return Semantics(
      button: true,
      selected: seleccionada,
      enabled: onTap != null,
      label: opcion.etiqueta,
      excludeSemantics: true,
      child: Material(
        color: fondo,
        borderRadius: AppRadius.brCampo,
        child: InkWell(
          onTap: onTap,
          borderRadius: AppRadius.brCampo,
          child: Container(
            constraints: const BoxConstraints(
              minHeight: AppSpacing.objetivoTactil,
              minWidth: 96,
            ),
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            decoration: BoxDecoration(
              borderRadius: AppRadius.brCampo,
              border: Border.all(color: borde),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                if (seleccionada) ...<Widget>[
                  Icon(Icons.check, size: 16, color: color),
                  const SizedBox(width: AppSpacing.xs),
                ] else if (opcion.icono != null) ...<Widget>[
                  Icon(opcion.icono, size: 16, color: AppColors.textoSecundario),
                  const SizedBox(width: AppSpacing.xs),
                ],
                Flexible(
                  child: Text(
                    opcion.etiqueta,
                    style: AppTypography.cuerpoGrande.copyWith(
                      color: color,
                      fontWeight: seleccionada ? FontWeight.w600 : FontWeight.w500,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
