import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Qué se sabe del enlace con el servidor.
enum EstadoConexion {
  /// El teléfono tiene una red disponible.
  conRed,

  /// El teléfono no tiene ninguna red: ni datos ni wifi.
  sinRed,

  /// Hay red, pero el último intento no llegó al servidor.
  sinServidor,

  /// Todavía no se pudo determinar.
  desconocido,

  /// Reservado: el servidor contestó recién. Nada lo devuelve todavía —
  /// hace falta una comprobación periódica contra el backend.
  enLinea,
}

/// El encabezado del diseño: logo, empresa, sección, enlace, avisos y perfil.
class DexterAppHeader extends StatelessWidget {
  const DexterAppHeader({
    super.key,
    required this.empresa,
    required this.conexion,
    this.seccion,
    this.iniciales,
    this.notificacionesSinLeer = 0,
    this.onPerfil,
  });

  final String empresa;
  final EstadoConexion conexion;

  /// En qué sección está parado el técnico.
  final String? seccion;

  final String? iniciales;
  final int notificacionesSinLeer;
  final VoidCallback? onPerfil;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.margen,
            AppSpacing.sm,
            AppSpacing.margen,
            AppSpacing.sm,
          ),
          child: Row(
            children: <Widget>[
              Image.asset(
                'assets/images/logo_dexter_campo.png',
                width: 32,
                height: 32,
                filterQuality: FilterQuality.medium,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    Text(
                      'DEXTER CAMPO',
                      style: AppTypography.etiqueta.copyWith(
                        color: AppColors.primary,
                        fontWeight: FontWeight.w700,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Row(
                      children: <Widget>[
                        // La empresa cede espacio despues que la seccion: es
                        // la identidad del tenant, y recortada a "RAPIL..." no
                        // dice de quien es la aplicacion. En que seccion esta
                        // parado, en cambio, ya lo marca la barra de abajo.
                        Flexible(
                          flex: 3,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: const BoxDecoration(
                              color: AppColors.surfaceContainer,
                              borderRadius: AppRadius.brChico,
                            ),
                            child: Text(
                              empresa.toUpperCase(),
                              style: AppTypography.etiquetaChica.copyWith(
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ),
                        if (seccion != null) ...<Widget>[
                          const SizedBox(width: 6),
                          Flexible(
                            flex: 2,
                            child: Text(
                              seccion!,
                              style: AppTypography.cuerpoChico.copyWith(
                                color: AppColors.onSurface,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              _ChipConexion(estado: conexion),
              const SizedBox(width: AppSpacing.xs),
              _Campana(sinLeer: notificacionesSinLeer),
              _BotonPerfil(iniciales: iniciales, onTap: onPerfil),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChipConexion extends StatelessWidget {
  const _ChipConexion({required this.estado});

  final EstadoConexion estado;

  @override
  Widget build(BuildContext context) {
    final (String texto, Color color, Color fondo) = switch (estado) {
      EstadoConexion.enLinea => (
          'EN LÍNEA',
          AppColors.exito,
          AppColors.exito
        ),
      EstadoConexion.conRed => (
          'CON RED',
          AppColors.exito,
          AppColors.exito
        ),
      EstadoConexion.sinRed => (
          'SIN RED',
          AppColors.onErrorContainer,
          AppColors.errorContainer
        ),
      EstadoConexion.sinServidor => (
          'SIN SERVIDOR',
          AppColors.onErrorContainer,
          AppColors.errorContainer
        ),
      EstadoConexion.desconocido => (
          'BUSCANDO',
          AppColors.onSurfaceVariant,
          AppColors.surfaceContainerHigh
        ),
    };

    return Semantics(
      label: 'Conexión: $texto',
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 4),
        decoration: BoxDecoration(
          color: fondo,
          borderRadius: AppRadius.brChico,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
            const SizedBox(width: AppSpacing.xs),
            Text(
              texto,
              style: AppTypography.etiquetaChica.copyWith(
                color: color,
                letterSpacing: 0.8,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Campana extends StatelessWidget {
  const _Campana({required this.sinLeer});

  final int sinLeer;

  @override
  Widget build(BuildContext context) {
    // Sin onTap a propósito: todavía no hay ninguna pantalla de notificaciones
    // y un botón que no lleva a ningún lado promete algo que no existe.
    return Semantics(
      label: sinLeer == 0 ? 'Notificaciones' : 'Notificaciones: $sinLeer sin leer',
      excludeSemantics: true,
      child: SizedBox(
        width: 40,
        height: AppSpacing.objetivoTactil,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            const Icon(Icons.notifications_none, size: 24, color: AppColors.onSurface),
            if (sinLeer > 0)
              Positioned(
                top: 8,
                right: 6,
                child: Container(
                  width: 16,
                  height: 16,
                  alignment: Alignment.center,
                  decoration: const BoxDecoration(
                    color: AppColors.error,
                    shape: BoxShape.circle,
                  ),
                  child: Text(
                    '$sinLeer',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.onError,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _BotonPerfil extends StatelessWidget {
  const _BotonPerfil({required this.iniciales, required this.onTap});

  final String? iniciales;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: onTap != null,
      label: 'Perfil y sesión',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.circulo),
        child: SizedBox(
          width: AppSpacing.objetivoTactil,
          height: AppSpacing.objetivoTactil,
          child: Center(
            child: Container(
              width: 32,
              height: 32,
              // El avatar vuelve a ser redondo: en este sistema `full` es un
              // círculo, no 12 px.
              decoration: const BoxDecoration(
                color: AppColors.primary,
                shape: BoxShape.circle,
              ),
              alignment: Alignment.center,
              child: iniciales == null || iniciales!.isEmpty
                  ? const Icon(Icons.person, size: 18, color: AppColors.onPrimary)
                  : Text(
                      iniciales!,
                      style: AppTypography.etiqueta.copyWith(
                        color: AppColors.onPrimary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
