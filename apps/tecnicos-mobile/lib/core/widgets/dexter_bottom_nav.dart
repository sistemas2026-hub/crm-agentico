import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Las secciones de la aplicación.
///
/// El enum las lista todas, incluidas las que todavía no existen: es el
/// producto que se está construyendo. Cuáles se **ofrecen** es otra cosa, y la
/// decide [DexterBottomNav.visibles].
enum SeccionCampo { inicio, trabajo, materiales, perfil, academia, mas }

/// Barra inferior fija, tal como la dibuja el diseño "DEXTER CAMPO".
///
/// Cuatro destinos repartidos a lo ancho, 80 px de alto, ícono de 24 y el
/// rótulo debajo en `label-caption`. La sección activa se pinta con el azul de
/// acción.
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
  /// POR QUÉ NO ESTÁN LAS SEIS
  /// -------------------------
  /// Academia y Más llevaban a una pantalla que dice "en construcción". Un
  /// destino en la barra principal es una promesa: quien lo toca espera que
  /// haga algo, y al tocarlo dos veces aprende que la barra miente. El diseño
  /// tampoco las dibuja.
  ///
  /// Perfil sí entra —el diseño lo pone cuarto— y lleva a algo que ya existe:
  /// la hoja de identidad y cierre de sesión.
  static const List<SeccionCampo> visibles = <SeccionCampo>[
    SeccionCampo.inicio,
    SeccionCampo.trabajo,
    SeccionCampo.materiales,
    SeccionCampo.perfil,
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
      color: AppColors.surface,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          color: AppColors.surface,
          boxShadow: <BoxShadow>[
            BoxShadow(color: Color(0x0A000000), blurRadius: 8, offset: Offset(0, -1)),
          ],
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: AppSpacing.barraInferior,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.margen),
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
    final color = activa ? AppColors.secondary : AppColors.onSurfaceVariant;

    return Semantics(
      button: true,
      selected: activa,
      label: etiquetaDe(seccion),
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadius.brTarjeta,
        // La sección activa se marca con el color Y con el ícono relleno. El
        // diseño solo cambia el color; se le suma el relleno porque el color
        // por sí solo no distingue para quien no lo ve igual — y el diseño ya
        // carga el eje FILL de los íconos, así que no es un invento ajeno.
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Stack(
                clipBehavior: Clip.none,
                children: <Widget>[
                  Icon(activa ? _iconoLleno : _icono, size: 24, color: color),
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
                          color: AppColors.secondaryContainer,
                          shape: BoxShape.circle,
                        ),
                        child: Text(
                          '${indicador!}',
                          style: AppTypography.labelBadge.copyWith(
                            color: AppColors.onSecondary,
                            fontSize: 9,
                            letterSpacing: 0,
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
                        decoration: const BoxDecoration(
                          color: AppColors.secondary,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                etiquetaDe(seccion),
                style: AppTypography.labelCaption.copyWith(
                  color: color,
                  fontWeight: activa ? FontWeight.w700 : FontWeight.w600,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }

  IconData get _icono => switch (seccion) {
        SeccionCampo.inicio => Icons.dashboard_outlined,
        SeccionCampo.trabajo => Icons.assignment_outlined,
        SeccionCampo.materiales => Icons.inventory_2_outlined,
        SeccionCampo.perfil => Icons.badge_outlined,
        SeccionCampo.academia => Icons.school_outlined,
        SeccionCampo.mas => Icons.grid_view_outlined,
      };

  IconData get _iconoLleno => switch (seccion) {
        SeccionCampo.inicio => Icons.dashboard,
        SeccionCampo.trabajo => Icons.assignment,
        SeccionCampo.materiales => Icons.inventory_2,
        SeccionCampo.perfil => Icons.badge,
        SeccionCampo.academia => Icons.school,
        SeccionCampo.mas => Icons.grid_view,
      };
}

/// Nombre visible de cada sección, con las palabras del diseño.
String etiquetaDe(SeccionCampo seccion) => switch (seccion) {
      SeccionCampo.inicio => 'Inicio',
      SeccionCampo.trabajo => 'Órdenes',
      SeccionCampo.materiales => 'Materiales',
      SeccionCampo.perfil => 'Perfil',
      SeccionCampo.academia => 'Academia',
      SeccionCampo.mas => 'Más',
    };
