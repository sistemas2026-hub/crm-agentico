import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Las cinco secciones de la aplicación.
///
/// Están las cinco desde ahora, aunque algunas todavía no tengan contenido:
/// son el producto que se está construyendo, no una lista provisoria.
enum SeccionCampo { inicio, trabajo, materiales, academia, mas }

/// Barra inferior fija, de ranuras iguales.
class DexterBottomNav extends StatelessWidget {
  const DexterBottomNav({
    super.key,
    required this.seleccionada,
    required this.onSeleccion,
    this.indicadores = const <SeccionCampo, int>{},
  });

  final SeccionCampo seleccionada;
  final ValueChanged<SeccionCampo> onSeleccion;

  /// Número sobre el icono de una sección, cuando haya un dato real que
  /// mostrar. Vacío mientras tanto: un contador inventado en la barra es lo
  /// primero que el técnico mira al abrir la aplicación.
  final Map<SeccionCampo, int> indicadores;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.superficie,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: AppColors.bordeFuerte)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: AppSpacing.barraInferior,
            child: Row(
              children: <Widget>[
                for (final SeccionCampo seccion in SeccionCampo.values)
                  Expanded(
                    child: _Ranura(
                      seccion: seccion,
                      activa: seccion == seleccionada,
                      indicador: indicadores[seccion],
                      onTap: () => onSeleccion(seccion),
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

class _Ranura extends StatelessWidget {
  const _Ranura({
    required this.seccion,
    required this.activa,
    required this.indicador,
    required this.onTap,
  });

  final SeccionCampo seccion;
  final bool activa;
  final int? indicador;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = activa ? AppColors.azulAccion : AppColors.inactivo;

    return Semantics(
      button: true,
      selected: activa,
      label: etiquetaDe(seccion),
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        child: Stack(
          children: <Widget>[
            // La sección activa se marca con la línea de arriba, el icono
            // relleno y el color: tres señales, no solo el color.
            if (activa)
              const Align(
                alignment: Alignment.topCenter,
                child: SizedBox(
                  height: 3,
                  width: double.infinity,
                  child: ColoredBox(color: AppColors.azulAccion),
                ),
              ),
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Stack(
                    clipBehavior: Clip.none,
                    children: <Widget>[
                      Icon(activa ? _iconoLleno : _icono, size: 22, color: color),
                      if (indicador != null && indicador! > 0)
                        Positioned(
                          top: -4,
                          right: -8,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 4,
                              vertical: 1,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.azulMarino,
                              borderRadius: BorderRadius.circular(AppRadius.completo),
                            ),
                            child: Text(
                              '${indicador!}',
                              style: AppTypography.etiquetaChica.copyWith(
                                color: AppColors.textoSobreOscuro,
                                fontSize: 10,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    etiquetaDe(seccion).toUpperCase(),
                    style: AppTypography.etiquetaChica.copyWith(
                      color: color,
                      fontWeight: activa ? FontWeight.w600 : FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  IconData get _icono => switch (seccion) {
        SeccionCampo.inicio => Icons.home_outlined,
        SeccionCampo.trabajo => Icons.assignment_outlined,
        SeccionCampo.materiales => Icons.inventory_2_outlined,
        SeccionCampo.academia => Icons.school_outlined,
        SeccionCampo.mas => Icons.grid_view_outlined,
      };

  IconData get _iconoLleno => switch (seccion) {
        SeccionCampo.inicio => Icons.home,
        SeccionCampo.trabajo => Icons.assignment,
        SeccionCampo.materiales => Icons.inventory_2,
        SeccionCampo.academia => Icons.school,
        SeccionCampo.mas => Icons.grid_view,
      };
}

/// Nombre visible de cada sección.
String etiquetaDe(SeccionCampo seccion) => switch (seccion) {
      SeccionCampo.inicio => 'Inicio',
      SeccionCampo.trabajo => 'Trabajo',
      SeccionCampo.materiales => 'Materiales',
      SeccionCampo.academia => 'Academia',
      SeccionCampo.mas => 'Más',
    };
