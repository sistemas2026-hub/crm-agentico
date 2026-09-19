import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Qué se sabe del enlace con el servidor.
///
/// No es un adorno: el técnico decide si esperar o seguir trabajando sin
/// conexión mirando esto, así que cada valor tiene que poder afirmarse.
enum EstadoConexion {
  /// El teléfono tiene una red disponible. Es lo máximo que se puede afirmar
  /// hoy: tener wifi no prueba que el servidor conteste.
  conRed,

  /// El teléfono no tiene ninguna red: ni datos ni wifi.
  sinRed,

  /// Hay red, pero el último intento no llegó al servidor.
  sinServidor,

  /// Todavía no se pudo determinar.
  desconocido,

  /// Reservado: el servidor contestó recién. Nada lo devuelve todavía —
  /// hace falta una comprobación periódica contra el backend (un `/salud`
  /// propio). Hasta que exista, decir "en línea" sería afirmar de más.
  enLinea,
}

/// Encabezado de la aplicación: logo, enlace, notificaciones y perfil.
///
/// Solo dibuja lo que recibe. No consulta la sesión, la red ni la cola.
class DexterAppHeader extends StatelessWidget {
  const DexterAppHeader({
    super.key,
    required this.empresa,
    required this.conexion,
    this.iniciales,
    this.notificacionesSinLeer = 0,
    this.onPerfil,
  });

  /// Nombre de la empresa del técnico. Sale de la sesión.
  final String empresa;

  final EstadoConexion conexion;

  /// Una o dos letras del nombre del técnico.
  final String? iniciales;

  /// Número sobre la campana. En cero no se dibuja nada: un contador que no
  /// corresponde a avisos reales se lee como "tenés dos cosas sin ver".
  final int notificacionesSinLeer;

  final VoidCallback? onPerfil;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.superficie,
      child: SafeArea(
        bottom: false,
        child: Container(
          height: AppSpacing.barraInferior,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.margen),
          decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: AppColors.borde)),
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
                      style: AppTypography.etiquetaGrande,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      empresa,
                      style: AppTypography.etiquetaChica,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              _ChipConexion(estado: conexion),
              const SizedBox(width: AppSpacing.sm),
              _Campana(sinLeer: notificacionesSinLeer),
              const SizedBox(width: AppSpacing.xs),
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
      EstadoConexion.enLinea => ('EN LÍNEA', AppColors.exito, AppColors.exitoFondo),
      EstadoConexion.conRed => ('CON RED', AppColors.exito, AppColors.exitoFondo),
      EstadoConexion.sinRed => ('SIN RED', AppColors.error, AppColors.errorFondo),
      EstadoConexion.sinServidor => ('SIN SERVIDOR', AppColors.precaucion, AppColors.precaucionFondo),
      EstadoConexion.desconocido => ('VERIFICANDO', AppColors.inactivo, AppColors.inactivoFondo),
    };

    return Semantics(
      label: 'Conexión: $texto',
      excludeSemantics: true,
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
            // Un punto solo no alcanza: al lado va siempre el texto.
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(AppRadius.completo),
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            Text(texto, style: AppTypography.etiquetaChica.copyWith(color: color)),
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
        width: 32,
        height: AppSpacing.objetivoTactil,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            const Icon(Icons.notifications_none, size: 22, color: AppColors.texto),
            if (sinLeer > 0)
              Positioned(
                top: 8,
                right: 0,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                  decoration: BoxDecoration(
                    color: AppColors.error,
                    borderRadius: BorderRadius.circular(AppRadius.completo),
                  ),
                  child: Text(
                    '$sinLeer',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.textoSobreOscuro,
                      fontSize: 10,
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
        borderRadius: BorderRadius.circular(AppRadius.completo),
        child: SizedBox(
          width: AppSpacing.objetivoTactil,
          height: AppSpacing.objetivoTactil,
          child: Center(
            child: Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: AppColors.azulMarino,
                borderRadius: BorderRadius.circular(AppRadius.completo),
              ),
              alignment: Alignment.center,
              child: iniciales == null || iniciales!.isEmpty
                  ? const Icon(Icons.person, size: 18, color: AppColors.textoSobreOscuro)
                  : Text(
                      iniciales!,
                      style: AppTypography.etiqueta.copyWith(
                        color: AppColors.textoSobreOscuro,
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
