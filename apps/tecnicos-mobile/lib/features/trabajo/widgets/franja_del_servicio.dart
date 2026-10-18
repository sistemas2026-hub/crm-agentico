import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_theme.dart';
import '../trabajo_vista.dart';

/// Los datos que le preguntan al técnico, siempre a la vista.
///
/// POR QUÉ (18/10/2026, pedido del usuario)
/// ---------------------------------------
/// La IP, el serial y el ticket vivían solo en el detalle, y la potencia
/// quedaba al fondo de Ejecutar. Al técnico se los preguntan —el NOC, el
/// cliente, el supervisor— justo mientras trabaja, y para contestar tenía que
/// salir de la pantalla. Esta franja va fija debajo del encabezado, igual en
/// el detalle y en Ejecutar.
///
/// QUÉ LLEVA, Y QUÉ NO
/// -------------------
/// Solo lo que otro le pide: ticket, serial, IP, caja y la señal de la ficha.
/// La historia y el diagnóstico son para entender la falla, y siguen en el
/// detalle. Plegada ocupa una línea: a 360 px ya están fijos el encabezado y la
/// franja «Falta». Sale todo de la ficha guardada en el teléfono, así que se ve
/// sin señal.
///
/// La señal es la de la ficha y lo dice: «al despachar» con su hora. No es una
/// medición de ahora; esa vive en «Comprobar conexión».
class FranjaDelServicio extends StatefulWidget {
  const FranjaDelServicio({super.key, required this.trabajo});

  final TrabajoVista trabajo;

  @override
  State<FranjaDelServicio> createState() => _FranjaDelServicioState();
}

class _FranjaDelServicioState extends State<FranjaDelServicio> {
  bool _abierta = false;

  TrabajoVista get t => widget.trabajo;

  static String _hora(DateTime d) =>
      '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

  static String _fecha(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')} ${_hora(d)}';

  Future<void> _copiar(String que, String valor) async {
    await Clipboard.setData(ClipboardData(text: valor));
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      SnackBar(content: Text('$que copiado')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final String ticket = t.numeroTicket.trim();
    final String serial = t.serialOnu.trim();
    final String ip = t.ipCliente.trim();
    // PLEGADA, SOLO EL TICKET (18/10/2026, pedido del usuario): el serial y
    // la IP estaban también en la línea, y al desplegar se repetían abajo.
    // El ticket es lo primero que piden; lo demás, a un toque.
    final bool hayAlgo = ticket.isNotEmpty ||
        serial.isNotEmpty ||
        ip.isNotEmpty ||
        t.potenciaOptica.isNotEmpty;
    // Sin ningún dato no hay franja: una línea vacía fija arriba es ruido.
    if (!hayAlgo) {
      return const SizedBox.shrink();
    }

    return Material(
      color: AppColors.surfaceContainerLow,
      child: InkWell(
        onTap: () => setState(() => _abierta = !_abierta),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.margen,
            vertical: AppSpacing.xs,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Icon(Icons.badge_outlined, size: 16, color: AppColors.secondary),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      ticket.isEmpty ? 'Datos del servicio' : 'Ticket #$ticket',
                      style: AppTypography.dato.copyWith(color: AppColors.onSurface),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Icon(
                    _abierta ? Icons.expand_less : Icons.expand_more,
                    size: 20,
                    color: AppColors.outline,
                    semanticLabel: _abierta ? 'Ocultar datos' : 'Ver datos',
                  ),
                ],
              ),
              if (_abierta) ...<Widget>[
                const SizedBox(height: AppSpacing.xs),
                if (t.clienteNombre.trim().isNotEmpty)
                  _fila('Cliente', t.clienteNombre),
                if (t.telefono.trim().isNotEmpty) _fila('Teléfono', t.telefono),
                if (ticket.isNotEmpty) _fila('Ticket', '#$ticket'),
                if (serial.isNotEmpty) _fila('Serial', serial, copiar: true),
                if (ip.isNotEmpty) _fila('IP', ip, copiar: true),
                if (t.cajaDeDistribucion.trim().isNotEmpty)
                  _fila('Caja', t.cajaDeDistribucion),
                if (t.puertoPon.trim().isNotEmpty) _fila('Puerto PON', t.puertoPon),
                if (t.potenciaOptica.isNotEmpty)
                  _fila(
                    'Señal Rx',
                    '${t.potenciaOptica}'
                        '${t.veredictoSenal.isEmpty ? '' : ' · ${t.veredictoSenal.replaceAll('_', ' ')}'}'
                        '${t.fichaCapturadaEn == null ? '' : ' · al despachar ${_fecha(t.fichaCapturadaEn!.toLocal())}'}',
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _fila(String titulo, String valor, {bool copiar = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          SizedBox(
            width: 88,
            child: Text(titulo, style: AppTypography.etiquetaChica),
          ),
          Expanded(
            child: SelectableText(
              valor,
              style: AppTypography.dato.copyWith(color: AppColors.onSurface),
            ),
          ),
          if (copiar)
            IconButton(
              tooltip: 'Copiar $titulo',
              icon: const Icon(Icons.copy, size: 18),
              visualDensity: VisualDensity.compact,
              onPressed: () => _copiar(titulo, valor),
            ),
        ],
      ),
    );
  }
}
