/// La campana del encabezado y el panel que se despliega al tocarla.
///
/// EL PEDIDO (09/11/2026)
/// ----------------------
/// El usuario, sobre la app en uso: «la pantalla de avisos: que salga una
/// campanita, y para ver las notificaciones que sea dando clic para verlas, y
/// cuando le den clic afuera se recoja».
///
/// QUÉ HABÍA ANTES
/// ---------------
/// Los avisos vivían metidos dentro de la pantalla de Inicio, debajo del
/// trabajo del día, y lo único que anunciaba uno nuevo era un punto en la barra
/// de abajo. Para leerlos había que estar en Inicio y bajar. Desde cualquier
/// otra pantalla no existían.
///
/// EL CONTADOR ES REAL, Y ESO NO ES UN DETALLE
/// --------------------------------------------
/// `DexterAppHeader` ya recibía `notificacionesSinLeer`, pero el contenedor le
/// pasaba `FieldMockData.notificacionesSinLeer` con un comentario que decía
/// «Dato de ejemplo: todavía no hay notificaciones de verdad». Una campana con
/// un número inventado enseña, en dos días, a no mirar la campana. Acá el
/// número entra por parámetro y el contenedor pasa el que ya calculaba contra
/// `local_notificaciones`.
library;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Qué se dibuja en la chapita roja, o vacío si no hay nada que mostrar.
///
/// Tres dígitos no entran en una chapita de 18 px y, sobre todo, no cambian
/// ninguna decisión: con 12 avisos o con 300, lo que hace el técnico es
/// abrirla. Por eso se corta en «9+» en vez de achicar la letra.
String textoDelBadge(int sinLeer) {
  if (sinLeer <= 0) return '';
  if (sinLeer > 9) return '9+';
  return '$sinLeer';
}

/// Qué anuncia la campana a un lector de pantalla.
///
/// «Avisos» a secas no dice lo único que importa: si hay algo sin leer. Quien
/// no ve la chapita roja tiene que oírlo.
String etiquetaDeLaCampana(int sinLeer) {
  if (sinLeer <= 0) return 'Avisos, ninguno sin leer';
  if (sinLeer == 1) return 'Avisos, 1 sin leer';
  return 'Avisos, $sinLeer sin leer';
}

/// El botón del encabezado.
class CampanaDeAvisos extends StatelessWidget {
  const CampanaDeAvisos({
    super.key,
    required this.sinLeer,
    required this.onTap,
  });

  final int sinLeer;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final String badge = textoDelBadge(sinLeer);

    return Semantics(
      container: true,
      button: true,
      label: etiquetaDeLaCampana(sinLeer),
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadius.brChico,
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Stack(
            clipBehavior: Clip.none,
            children: <Widget>[
              Icon(
                sinLeer > 0
                    ? Icons.notifications_active_outlined
                    : Icons.notifications_none,
                size: 24,
                color: sinLeer > 0 ? AppColors.primary : AppColors.onSurfaceVariant,
              ),
              if (badge.isNotEmpty)
                Positioned(
                  right: -4,
                  top: -4,
                  child: Container(
                    constraints: const BoxConstraints(minWidth: 16),
                    padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1),
                    decoration: BoxDecoration(
                      color: AppColors.error,
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(color: AppColors.surface, width: 1.5),
                    ),
                    child: Text(
                      badge,
                      textAlign: TextAlign.center,
                      style: AppTypography.labelBadge.copyWith(
                        color: AppColors.onError,
                        height: 1.1,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Despliega el panel de avisos debajo de la campana.
///
/// `barrierDismissible: true` es, literalmente, el «cuando le den clic afuera
/// se recoja» del pedido: el velo invisible ocupa la pantalla entera y un
/// toque fuera del panel lo cierra. No hace falta un detector propio, y uno
/// hecho a mano se olvidaría del botón Atrás de Android, que acá también
/// cierra.
///
/// El panel se ancla arriba a la derecha, debajo del encabezado, para que
/// salga de donde se tocó. `topPadding` es el alto del encabezado más la
/// franja de estado del teléfono.
Future<void> mostrarPanelDeAvisos(
  BuildContext context, {
  required Widget Function(BuildContext) contenido,
  double topPadding = 72,
}) {
  return showGeneralDialog<void>(
    context: context,
    barrierDismissible: true,
    barrierLabel: 'Cerrar los avisos',
    barrierColor: Colors.black.withValues(alpha: 0.18),
    transitionDuration: const Duration(milliseconds: 140),
    pageBuilder: (BuildContext ctx, Animation<double> a, Animation<double> b) {
      final double arriba = MediaQuery.of(ctx).padding.top + topPadding;
      return Stack(
        children: <Widget>[
          Positioned(
            top: arriba,
            right: AppSpacing.sm,
            left: AppSpacing.sm,
            child: Align(
              alignment: Alignment.topRight,
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  maxWidth: 420,
                  //  Nunca más alto que la pantalla menos el encabezado: con
                  //  veinte avisos el panel se desliza por dentro en vez de
                  //  salirse por abajo.
                  maxHeight: MediaQuery.of(ctx).size.height - arriba - 24,
                ),
                child: Material(
                  color: AppColors.surface,
                  elevation: 8,
                  borderRadius: AppRadius.brTarjeta,
                  clipBehavior: Clip.antiAlias,
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    child: contenido(ctx),
                  ),
                ),
              ),
            ),
          ),
        ],
      );
    },
    transitionBuilder: (BuildContext ctx, Animation<double> a,
        Animation<double> b, Widget hijo) {
      //  Baja desde la campana, no aparece de la nada: así se entiende de
      //  dónde salió.
      return FadeTransition(
        opacity: a,
        child: SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(0, -0.04),
            end: Offset.zero,
          ).animate(CurvedAnimation(parent: a, curve: Curves.easeOut)),
          child: hijo,
        ),
      );
    },
  );
}
