import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Qué tan grave es lo que dice una cifra. Lo decide quien la muestra, nunca
/// este widget: acá no vive ningún umbral.
enum DexterMetricTone { neutro, exito, precaucion, error, info }

/// Una cifra con su etiqueta y, si corresponde, su unidad.
///
/// Sirve igual para una potencia óptica, un SLA, una distancia o un conteo de
/// materiales, porque no conoce ninguna de esas cosas: recibe textos ya
/// formateados. Tampoco distingue si el valor es real o de ejemplo — así una
/// pantalla no cambia de forma el día que el backend empiece a entregarlo.
///
/// El valor va en la tipografía monoespaciada de cifras tabulares: una lectura
/// que cambia en vivo no debe mover lo que tiene al lado.
class DexterMetricTile extends StatelessWidget {
  const DexterMetricTile({
    super.key,
    required this.etiqueta,
    required this.valor,
    this.unidad,
    this.icono,
    this.tono = DexterMetricTone.neutro,
    this.compacto = false,
    this.nota,
  });

  /// Qué se está midiendo. Por ejemplo "Potencia RX".
  final String etiqueta;

  /// La cifra, ya formateada. Por ejemplo "-18.7", "01:42" o "14".
  final String valor;

  /// Por ejemplo "dBm", "km" o "unidades". Nunca se asume una.
  final String? unidad;

  final IconData? icono;
  final DexterMetricTone tono;

  /// Reduce el tamaño del valor, para filas de varias cifras juntas.
  final bool compacto;

  /// Aclaración breve debajo. Por ejemplo un rango esperado.
  final String? nota;

  @override
  Widget build(BuildContext context) {
    final color = _color;
    final estiloValor = (compacto ? AppTypography.tituloMedio : AppTypography.medicion)
        .copyWith(
      color: color,
      fontFamily: AppTypography.familiaMono,
      fontFamilyFallback: AppTypography.respaldoMono,
      fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
    );

    return Semantics(
      label: '$etiqueta: $valor${unidad == null ? '' : ' $unidad'}',
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            children: <Widget>[
              if (icono != null) ...<Widget>[
                Icon(icono, size: 14, color: color),
                const SizedBox(width: AppSpacing.xs),
              ],
              Flexible(
                child: Text(
                  etiqueta.toUpperCase(),
                  style: AppTypography.etiquetaChica,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: <Widget>[
              Flexible(
                child: Text(
                  valor,
                  style: estiloValor,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (unidad != null) ...<Widget>[
                const SizedBox(width: AppSpacing.xs),
                Text(
                  unidad!,
                  style: AppTypography.etiqueta.copyWith(color: color),
                ),
              ],
            ],
          ),
          if (nota != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(nota!, style: AppTypography.cuerpoChico),
          ],
        ],
      ),
    );
  }

  Color get _color => switch (tono) {
        DexterMetricTone.neutro => AppColors.texto,
        DexterMetricTone.exito => AppColors.exito,
        DexterMetricTone.precaucion => AppColors.precaucion,
        DexterMetricTone.error => AppColors.error,
        DexterMetricTone.info => AppColors.info,
      };
}
