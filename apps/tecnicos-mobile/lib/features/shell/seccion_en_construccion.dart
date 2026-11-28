import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_empty_state.dart';

/// Contenedor de una sección que todavía no se construyó.
///
/// Existe para que la navegación esté completa desde ahora sin fingir una
/// pantalla: dice qué va a haber ahí y no muestra datos de ninguna clase.
class SeccionEnConstruccion extends StatelessWidget {
  const SeccionEnConstruccion({
    super.key,
    required this.titulo,
    required this.descripcion,
    required this.icono,
  });

  final String titulo;
  final String descripcion;
  final IconData icono;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.fondo,
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.margen),
          child: DexterEmptyState(
            icono: icono,
            titulo: titulo,
            mensaje: descripcion,
          ),
        ),
      ),
    );
  }
}
