import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Las secciones de la aplicación.
///
/// El enum las lista todas, incluidas las que todavía no existen: es el
/// producto que se está construyendo. Cuáles se **ofrecen** es otra cosa, y la
/// decide [DexterBottomNav.visibles].
enum SeccionCampo { inicio, trabajo, materiales, academia, mas }

/// Barra inferior fija, de ranuras iguales.
class DexterBottomNav extends StatelessWidget {
  const DexterBottomNav({
    super.key,
    required this.seleccionada,
    required this.onSeleccion,
    this.indicadores = const <SeccionCampo, int>{},
    this.avisos = const <SeccionCampo>{},
  });

  /// Las secciones que se ofrecen hoy.
  ///
  /// POR QUÉ NO ESTÁN LAS CINCO
  /// --------------------------
  /// Academia y Más llevaban a una pantalla que dice "en construcción". Un
  /// destino en la barra principal es una promesa: quien lo toca espera que
  /// haga algo, y al tocarlo dos veces aprende que la barra miente.
  ///
  /// Vuelven cuando tengan contenido. El enum las conserva para que ese día
  /// sea agregar una línea acá y nada más.
  static const List<SeccionCampo> visibles = <SeccionCampo>[
    SeccionCampo.inicio,
    SeccionCampo.trabajo,
    SeccionCampo.materiales,
  ];

  final SeccionCampo seleccionada;
  final ValueChanged<SeccionCampo> onSeleccion;

  /// Número sobre el icono de una sección, cuando haya un dato real que
  /// mostrar. Vacío mientras tanto: un contador inventado en la barra es lo
  /// primero que el técnico mira al abrir la aplicación.
  final Map<SeccionCampo, int> indicadores;

  /// Secciones con un aviso sin número: el punto de color del diseño.
  final Set<SeccionCampo> avisos;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surfaceContainerLowest,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          color: AppColors.surfaceContainerLowest,
          border: Border(top: BorderSide(color: AppColors.surfaceContainerHigh)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: AppSpacing.barraInferior,
            child: Row(
              children: <Widget>[
                for (final SeccionCampo seccion in visibles)
                  Expanded(
                    child: _Ranura(
                      seccion: seccion,
                      activa: seccion == seleccionada,
                      indicador: indicadores[seccion],
                      aviso: avisos.contains(seccion),
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
    required this.aviso,
    required this.onTap,
  });

  final SeccionCampo seccion;
  final bool activa;
  final int? indicador;
  final bool aviso;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = activa ? AppColors.primary : AppColors.onSurfaceVariant;

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
                  child: ColoredBox(color: AppColors.primary),
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
                            height: 16,
                            constraints: const BoxConstraints(minWidth: 16),
                            padding: const EdgeInsets.symmetric(horizontal: 4),
                            alignment: Alignment.center,
                            decoration: const BoxDecoration(
                              color: AppColors.primary,
                              shape: BoxShape.circle,
                            ),
                            child: Text(
                              '${indicador!}',
                              style: AppTypography.etiquetaChica.copyWith(
                                color: AppColors.onPrimary,
                                fontSize: 9,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        )
                      else if (aviso)
                        Positioned(
                          top: -2,
                          right: -6,
                          child: Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              color: seccion == SeccionCampo.mas
                                  ? AppColors.error
                                  : AppColors.secondary,
                              shape: BoxShape.circle,
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
