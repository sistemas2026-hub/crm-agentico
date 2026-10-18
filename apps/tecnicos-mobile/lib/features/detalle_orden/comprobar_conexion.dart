import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';
import '../trabajo/trabajo_vista.dart';
import 'acciones_orden.dart';

/// «¿Quedó bien?», sin salir de la intervención.
///
/// POR QUÉ EXISTE (17/10/2026)
/// ---------------------------
/// Volver a medir y el ping vivían solo en el detalle de la orden. El técnico
/// limpia un conector frente a la caja NAP, en la pantalla de ejecución, y para
/// saber si sirvió tenía que salir de ahí. Y peor: si la ficha del equipo no
/// llegó al crear la orden, no había niveles, ni serial, ni forma de medir
/// —el botón solo aparecía con una lectura congelada—.
///
/// QUÉ MUESTRA, Y QUÉ NO
/// ---------------------
///   - la lectura de la ficha, rotulada «Al despachar» con su hora: es
///     historia, no el presente;
///   - la medición de ahora, rotulada «Ahora» con su hora;
///   - el ping como lo que es, una medición: «respondieron x de y». Nunca
///     «internet bien» ni «servicio caído»;
///   - el veredicto de la señal sale del servidor; acá no se calcula ningún
///     umbral, y la Rx OLT no lleva veredicto porque nadie la juzgó.
///
/// Las tres acciones necesitan señal y lo dicen. Todo lo demás de la pantalla
/// sigue funcionando sin ella.
class ComprobarConexion extends StatefulWidget {
  const ComprobarConexion({
    super.key,
    required this.ordenId,
    required this.trabajo,
    required this.acciones,
    this.alActualizarFicha,
    this.mostrarFicha = true,
  });

  /// Si dibuja la lectura de la ficha, o por qué no la hay. En el detalle va
  /// apagado: la telemetría de arriba ya lo dice, y repetirlo dos tarjetas más
  /// abajo es ruido.
  final bool mostrarFicha;

  final String ordenId;

  /// La orden tal como está en el teléfono: de acá sale la ficha congelada.
  final TrabajoVista trabajo;
  final AccionesOrden acciones;

  /// Después de volver a pedir la ficha con éxito: quien la muestra relee la
  /// orden del teléfono, que ya quedó actualizada.
  final Future<void> Function()? alActualizarFicha;

  @override
  State<ComprobarConexion> createState() => _ComprobarConexionState();
}

class _ComprobarConexionState extends State<ComprobarConexion> {
  MedicionDeSenal? _medicion;
  ResultadoPing? _ping;
  DateTime? _pingEn;
  String? _avisoFicha;
  bool _midiendo = false;
  bool _pingueando = false;
  bool _consultando = false;

  TrabajoVista get t => widget.trabajo;
  bool get _haySerial => t.serialOnu.trim().isNotEmpty;

  Future<void> _medir() async {
    final f = widget.acciones.medirSenal;
    if (f == null) return;
    setState(() => _midiendo = true);
    final MedicionDeSenal m = await f(widget.ordenId);
    if (!mounted) return;
    setState(() {
      _medicion = m;
      _midiendo = false;
    });
  }

  Future<void> _pinguear() async {
    final f = widget.acciones.probarConexion;
    if (f == null) return;
    setState(() => _pingueando = true);
    // Una tanda de cuatro: el proveedor rechaza menos de tres, y acá se quiere
    // una respuesta rápida al lado del conector, no la prueba larga del
    // detalle.
    final ResultadoPing r = await f(widget.ordenId, 4);
    if (!mounted) return;
    setState(() {
      _ping = r;
      _pingEn = DateTime.now();
      _pingueando = false;
    });
  }

  Future<void> _consultarFicha() async {
    final f = widget.acciones.refrescarFicha;
    if (f == null) return;
    setState(() {
      _consultando = true;
      _avisoFicha = null;
    });
    final ResultadoRefresco r = await f(widget.ordenId);
    if (!mounted) return;
    setState(() {
      _consultando = false;
      _avisoFicha = r.texto;
    });
    if (r.ok) await widget.alActualizarFicha?.call();
  }

  static String _hora(DateTime d) =>
      '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

  static String _fecha(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')} ${_hora(d)}';

  static String _dbm(double? v) => v == null ? '—' : '${v.toStringAsFixed(2)} dBm';

  /// La misma lectura del motivo que el detalle: cada uno se arregla distinto.
  static String _motivoDeMedicion(String motivo) => switch (motivo) {
        'sin_conexion' => 'Sin señal no se puede medir. No queda pendiente: '
            'medí de nuevo cuando tengas.',
        'sin_equipo' => 'Esta orden no tiene el serial del equipo cargado.',
        'medicion_no_habilitada' =>
          'La empresa todavía no habilitó la medición en vivo.',
        'motor_no_responde' || 'motor_rechazo' =>
          'El sistema no contestó. No dice nada del equipo del cliente.',
        'sin_lectura' || 'respuesta_vacia' =>
          'Contestó, pero sin niveles. Probá de nuevo en un rato.',
        _ => 'No se pudo medir.',
      };

  static String _motivoDePing(String motivo) => switch (motivo) {
        'sin_conexion' => 'Sin señal no se puede probar. Se repite cuando haya.',
        'ping_no_habilitado' =>
          'La prueba no está habilitada para esta empresa todavía.',
        'motor_no_responde' =>
          'No se pudo preguntar. No dice nada del equipo del cliente.',
        _ => 'No se pudo probar.',
      };

  Widget _pastilla(String veredicto) {
    if (veredicto.isEmpty) return const SizedBox.shrink();
    final String texto = veredicto.replaceAll('_', ' ');
    return veredicto == 'aceptable'
        ? DexterPastilla.enRegla(texto: texto)
        : DexterPastilla.critica(texto: texto);
  }

  /// Una lectura: de cuándo es, y qué dijo.
  Widget _lectura({
    required String cuando,
    required String rxOnu,
    required String rxOlt,
    required String estado,
    required String veredicto,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(cuando.toUpperCase(),
              style: AppTypography.labelCaption.copyWith(color: AppColors.outline)),
          const SizedBox(height: 4),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              Text('Rx ONU $rxOnu', style: AppTypography.cuerpo),
              _pastilla(veredicto),
            ],
          ),
          if (rxOlt.isNotEmpty)
            Text('Rx OLT $rxOlt', style: AppTypography.cuerpoChico),
          if (estado.isNotEmpty)
            Text(
              'La OLT ve el equipo: $estado. Eso no confirma que el cliente '
              'tenga internet.',
              style: AppTypography.etiquetaChica,
            ),
        ],
      ),
    );
  }

  /// La ficha congelada, o por qué no hay.
  Widget _deLaFicha() {
    if (t.hayLecturaDeEquipo) {
      final DateTime? cuando = t.fichaCapturadaEn;
      return _lectura(
        cuando: cuando == null ? 'Al despachar' : 'Al despachar · ${_fecha(cuando.toLocal())}',
        rxOnu: t.potenciaOptica.isEmpty ? '—' : t.potenciaOptica,
        rxOlt: t.potenciaOpticaSubida,
        estado: t.estadoOnu,
        veredicto: t.veredictoSenal,
      );
    }
    final String porQue = switch (t.sinEquipo) {
      SinEquipo.serialNoCargado =>
        'Este cliente no tiene el equipo cargado en el sistema del ISP: no hay '
            'señal que consultar. Eso no dice si la red está bien o mal.',
      SinEquipo.serialDesactualizado =>
        'El serial que figura no existe en la OLT. Suele pasar cuando se le '
            'cambió el equipo al cliente.',
      _ => t.contextoDisponible
          ? 'La ficha no trajo la señal del equipo.'
          : 'La ficha del equipo no llegó cuando se creó la orden.',
    };
    return Text(porQue, style: AppTypography.cuerpoChico);
  }

  @override
  Widget build(BuildContext context) {
    final MedicionDeSenal? m = _medicion;
    final ResultadoPing? p = _ping;

    final bool puedeMedir = widget.acciones.medirSenal != null && _haySerial;
    final bool puedePing = widget.acciones.probarConexion != null;
    // Volver a pedir la ficha tiene sentido cuando falta algo: sin serial no
    // se puede medir, sin ficha no hay con qué comparar, y una ficha que llegó
    // sin la lectura puede traerla en un segundo intento.
    final bool puedeConsultar = widget.acciones.refrescarFicha != null &&
        (!_haySerial || !t.contextoDisponible || !t.hayLecturaDeEquipo);

    return DexterBloque(
      titulo: 'Comprobar conexión',
      icono: Icons.network_check,
      children: <Widget>[
        if (widget.mostrarFicha) _deLaFicha(),
        if (m != null) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          if (m.medido)
            _lectura(
              cuando: m.medidoEn == null ? 'Ahora' : 'Ahora · ${_hora(m.medidoEn!)}',
              rxOnu: _dbm(m.senal1490),
              rxOlt: m.senal1310 == null ? '' : _dbm(m.senal1310),
              estado: m.estadoOnu,
              veredicto: m.veredicto,
            )
          else
            Text(_motivoDeMedicion(m.motivo), style: AppTypography.cuerpoChico),
        ],
        if (p != null) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          Text(
            p.medido
                ? 'Ping · ${_hora(_pingEn!)} · respondieron '
                    '${p.paquetes.where((PaqueteDePing x) => x.respondio).length} '
                    'de ${p.paquetes.length}'
                : _motivoDePing(p.motivo),
            style: AppTypography.cuerpoChico,
          ),
        ],
        if (_avisoFicha != null) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          Text(_avisoFicha!, style: AppTypography.cuerpoChico),
        ],
        const SizedBox(height: AppSpacing.sm),
        // EN UNA FILA, ÍCONO Y UNA PALABRA (18/10/2026): eran tres botones
        // con frase larga, uno debajo del otro.
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (final (int i, Widget b) in <Widget>[
              if (puedeMedir)
                DexterAccionCompacta(
                  texto: _midiendo ? 'Midiendo…' : 'Medir',
                  descripcion: 'Medir la señal ahora',
                  icono: Icons.speed,
                  alTocar: _midiendo ? null : _medir,
                ),
              if (puedePing)
                DexterAccionCompacta(
                  texto: _pingueando ? 'Probando…' : 'Ping',
                  descripcion: 'Probar la conexión con un ping',
                  icono: Icons.wifi_tethering,
                  alTocar: _pingueando ? null : _pinguear,
                ),
              if (puedeConsultar)
                DexterAccionCompacta(
                  texto: _consultando ? 'Consultando…' : 'Consultar',
                  descripcion: 'Volver a consultar el equipo',
                  icono: Icons.sync,
                  alTocar: _consultando ? null : _consultarFicha,
                ),
            ].indexed) ...<Widget>[
              if (i > 0) const SizedBox(width: AppSpacing.xs),
              Expanded(child: b),
            ],
          ],
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Estas pruebas necesitan señal. Lo demás de esta pantalla se guarda '
          'en el teléfono sin ella.',
          style: AppTypography.etiquetaChica,
        ),
      ],
    );
  }
}
