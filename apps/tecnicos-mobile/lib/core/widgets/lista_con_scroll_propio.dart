import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Una lista que deja a la vista las primeras [visibles] filas y pone el resto
/// en el mismo recuadro, con su propio scroll (29/10/2026). La pidió el
/// usuario dos veces: en Avisos («que muestre dos, y si quiere ver más, que
/// arrastre un scroll independiente») y en Después («cuando salgan más de 3
/// tickets se va a alargar»). Inicio no crece con cada fila y lo de abajo
/// queda a la vista.
///
/// La altura del recuadro sale de lo DIBUJADO, no de una estimación: una
/// alerta ocupa el doble que un aviso, y un alto fijo cortaría una por la
/// mitad. Debajo dice cuántas quedan, porque un scroll sin aviso es una fila
/// que nadie ve.
class ListaConScrollPropio extends StatefulWidget {
  const ListaConScrollPropio({
    super.key,
    required this.filas,
    required this.visibles,
    this.claveDelRecuadro = const ValueKey<String>('lista-con-scroll'),
    this.altoEstimado = 76,
  });

  final List<Widget> filas;
  final int visibles;

  /// Para encontrar el recuadro desde una prueba.
  final Key claveDelRecuadro;

  /// El alto de una fila antes de medir: solo el primer cuadro.
  final double altoEstimado;

  @override
  State<ListaConScrollPropio> createState() => _ListaConScrollPropioState();
}

class _ListaConScrollPropioState extends State<ListaConScrollPropio> {
  final ScrollController _scroll = ScrollController();
  late final List<GlobalKey> _llaves =
      List<GlobalKey>.generate(widget.visibles, (_) => GlobalKey());
  double? _altoMedido;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _medir() {
    if (!mounted) return;
    double suma = 0;
    for (final GlobalKey llave in _llaves) {
      final RenderObject? r = llave.currentContext?.findRenderObject();
      if (r is! RenderBox || !r.hasSize) return;
      suma += r.size.height;
    }
    if (_altoMedido == null || (suma - _altoMedido!).abs() > 0.5) {
      setState(() => _altoMedido = suma);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<Widget> filas = widget.filas;
    final int visibles = widget.visibles;
    if (filas.length <= visibles) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: filas,
      );
    }

    WidgetsBinding.instance.addPostFrameCallback((_) => _medir());
    final int mas = filas.length - visibles;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        ConstrainedBox(
          key: widget.claveDelRecuadro,
          constraints: BoxConstraints(
            maxHeight: _altoMedido ?? widget.altoEstimado * visibles,
          ),
          child: Scrollbar(
            controller: _scroll,
            thumbVisibility: true,
            child: ListView(
              controller: _scroll,
              shrinkWrap: true,
              padding: const EdgeInsets.only(right: AppSpacing.sm),
              children: <Widget>[
                for (int i = 0; i < filas.length; i++)
                  i < visibles
                      ? KeyedSubtree(key: _llaves[i], child: filas[i])
                      : filas[i],
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Deslizá dentro del recuadro para ver '
          '${mas == 1 ? 'el otro' : 'los otros $mas'}',
          style: AppTypography.etiquetaChica,
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
