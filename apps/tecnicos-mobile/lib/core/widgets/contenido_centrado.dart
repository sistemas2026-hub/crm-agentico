import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Le pone un techo al ancho del contenido.
///
/// POR QUÉ
/// -------
/// Dexter Campo se diseñó para un teléfono de 390 px y se usa en uno. Pero la
/// aplicación corre igual en una tablet apaisada o en el escritorio de un
/// supervisor, y ahí, sin techo, todo se estira: botones de mil píxeles de
/// ancho, direcciones en una sola línea larguísima y tarjetas que separan sus
/// dos extremos tanto que hay que mover la cabeza para leerlas.
///
/// No es un problema de estética. Una línea de texto muy larga se relee sola:
/// el ojo vuelve al renglón equivocado. Y un botón que ocupa todo el ancho
/// deja de leerse como un botón.
///
/// POR QUÉ ACÁ Y NO EN CADA PANTALLA
/// ---------------------------------
/// Porque el techo tiene que ser el mismo en las cinco. Si cada pantalla
/// eligiera el suyo, el encabezado quedaría alineado con una cosa y el
/// contenido con otra, y al cambiar de sección todo se correría de lugar.
/// Se aplica una vez, donde vive la estructura común.
class ContenidoCentrado extends StatelessWidget {
  const ContenidoCentrado({
    super.key,
    required this.child,
    this.color,
    this.ajustadoAlContenido = false,
  });

  final Widget child;

  /// El color de la columna de contenido. Los lados siempre quedan con el
  /// fondo de la aplicación, para que se lea como una hoja sobre la mesa y no
  /// como una pantalla rota.
  final Color? color;

  /// Para las barras: el alto lo pone el hijo, no el espacio disponible.
  ///
  /// Sin esto una barra inferior centrada se estira hasta llenar la pantalla
  /// y tapa el contenido. Pasó en la primera vuelta: a 1440 px la aplicación
  /// quedó con la barra de navegación flotando en el medio y nada más.
  final bool ajustadoAlContenido;

  /// El techo.
  ///
  /// 600 y no 390: una tablet vertical aprovecha algo más de ancho sin que el
  /// renglón se vuelva incómodo. Por debajo de este número el widget no hace
  /// nada, así que en un teléfono es como si no existiera.
  static const double anchoMaximo = 600;

  /// Para encontrarlo en una prueba.
  static const Key claveDelTecho = ValueKey<String>('techo-de-ancho');

  @override
  Widget build(BuildContext context) {
    final Widget columna = ConstrainedBox(
      // La clave existe para que una prueba pueda medir ESTE widget: un
      // `byType(ConstrainedBox).first` encuentra el del Scaffold y mide otra
      // cosa, que fue lo que paso la primera vez.
      key: claveDelTecho,
      constraints: const BoxConstraints(maxWidth: anchoMaximo),
      child: ColoredBox(color: color ?? AppColors.surface, child: child),
    );

    return ColoredBox(
      color: AppColors.surfaceDim,
      child: ajustadoAlContenido
          ? Align(
              alignment: Alignment.bottomCenter,
              heightFactor: 1,
              child: columna,
            )
          : Center(child: columna),
    );
  }
}
