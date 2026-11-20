import 'package:flutter/material.dart';

import '../../../core/acciones/lector_de_codigo.dart';
import '../../../core/theme/app_theme.dart';
import '../recepcion_del_kit.dart';

/// Cómo se lee un código. Se inyecta en las pruebas: la cámara no existe ahí.
typedef LeerCodigo = Future<String?> Function(BuildContext contexto);

Future<String?> leerConLaCamara(BuildContext contexto) => LectorDeCodigo.abrir(
      contexto,
      titulo: 'Escanear equipo',
      ayuda: 'Apuntá al código del equipo que te entregaron.',
    );

/// LO QUE HAY QUE CONFIRMAR AL RECIBIR EL KIT (28/10/2026, fase 2).
///
/// Arriba de Materiales: cada acta sin confirmar, con «Recibí todo» y «No
/// coincide», y los equipos con serie apartados a su nombre, con «Escanear».
/// No aparece si no hay nada. Sin señal lo dice, en una línea: confirmar y
/// escanear van en línea (ver `recepcion_del_kit.dart`).
class TarjetaDeRecepcion extends StatefulWidget {
  const TarjetaDeRecepcion({
    super.key,
    required this.recepcion,
    this.leerCodigo = leerConLaCamara,
    this.alCambiar,
    this.recargarCon,
  });

  final RecepcionDelKit recepcion;
  final LeerCodigo leerCodigo;

  /// Cuando cambia, se vuelve a leer: el kit se bajó y puede haber una
  /// entrega nueva.
  final Object? recargarCon;

  /// Después de confirmar o escanear: para que el kit se vuelva a bajar.
  final Future<void> Function()? alCambiar;

  @override
  State<TarjetaDeRecepcion> createState() => _TarjetaDeRecepcionState();
}

class _TarjetaDeRecepcionState extends State<TarjetaDeRecepcion> {
  PendienteDeRecepcion _pendiente = const PendienteDeRecepcion();
  String? _sinSenal;
  bool _ocupado = false;

  @override
  void initState() {
    super.initState();
    _leer();
  }

  @override
  void didUpdateWidget(TarjetaDeRecepcion anterior) {
    super.didUpdateWidget(anterior);
    if (anterior.recargarCon != widget.recargarCon) _leer();
  }

  Future<void> _leer() async {
    try {
      final PendienteDeRecepcion p = await widget.recepcion.leer();
      if (mounted) {
        setState(() {
          _pendiente = p;
          _sinSenal = null;
        });
      }
    } on RecepcionError catch (e) {
      if (mounted) setState(() => _sinSenal = e.mensaje);
    }
  }

  void _decir(String texto, {bool esProblema = false}) {
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(SnackBar(
      content: Text(texto),
      backgroundColor: esProblema ? AppColors.error : null,
    ));
  }

  Future<void> _hacer(Future<String> Function() accion) async {
    if (_ocupado) return;
    setState(() => _ocupado = true);
    try {
      final String hecho = await accion();
      _decir(hecho);
      await widget.alCambiar?.call();
      await _leer();
    } on RecepcionError catch (e) {
      _decir(e.mensaje, esProblema: true);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<void> _todo(EntregaPorConfirmar e) => _hacer(() async {
        await widget.recepcion.confirmar(e.id, conforme: true);
        return 'Listo: confirmaste que recibiste todo.';
      });

  Future<void> _noCoincide(EntregaPorConfirmar e) async {
    final List<Diferencia>? diferencias = await showModalBottomSheet<List<Diferencia>>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _HojaDeDiferencias(entrega: e),
    );
    if (diferencias == null || diferencias.isEmpty || !mounted) return;
    await _hacer(() async {
      await widget.recepcion.confirmar(e.id, conforme: false, diferencias: diferencias);
      return 'Quedó anotado lo que no llegó.';
    });
  }

  Future<void> _escanear() async {
    final String? leido = await widget.leerCodigo(context);
    if (leido == null || leido.trim().isEmpty || !mounted) return;
    await _hacer(() => widget.recepcion.escanear(leido.trim()));
  }

  @override
  Widget build(BuildContext context) {
    // Sin señal se dice, sin borrar lo que ya se sabía que estaba pendiente.
    final Widget? aviso = _sinSenal == null
        ? null
        : Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Text(_sinSenal!, style: AppTypography.cuerpoChico),
          );
    if (!_pendiente.hayAlgo) return aviso ?? const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          ?aviso,
          for (final EntregaPorConfirmar e in _pendiente.porConfirmar)
            _Caja(
              rotulo: 'ENTREGA POR CONFIRMAR',
              titulo: e.acta.isEmpty ? 'Material recibido' : 'Acta ${e.acta}',
              detalle: e.bodega.isEmpty ? null : 'Desde ${e.bodega}',
              hijos: <Widget>[
                for (final LineaDeEntrega l in e.lineas)
                  Text('${l.nombre}: ${l.cantidad} ${l.unidad}${l.serie.isEmpty ? '' : ' · ${l.serie}'}',
                      style: AppTypography.cuerpoChico),
                const SizedBox(height: AppSpacing.sm),
                Wrap(spacing: AppSpacing.sm, runSpacing: AppSpacing.sm, children: <Widget>[
                  FilledButton(
                    onPressed: _ocupado ? null : () => _todo(e),
                    child: const Text('Recibí todo'),
                  ),
                  // Un equipo con serie no se corrige acá: se escanea o no.
                  if (e.lineas.any((LineaDeEntrega l) => l.serie.isEmpty))
                    OutlinedButton(
                      onPressed: _ocupado ? null : () => _noCoincide(e),
                      child: const Text('No coincide'),
                    ),
                ]),
              ],
            ),
          if (_pendiente.porEscanear.isNotEmpty)
            _Caja(
              rotulo: 'EQUIPOS POR ESCANEAR',
              titulo: 'Escaneá cada equipo al recibirlo',
              detalle: 'Hasta que lo escanees no queda a tu nombre.',
              hijos: <Widget>[
                for (final EquipoPorEscanear q in _pendiente.porEscanear)
                  Text('${q.nombre}: ${q.cantidad} por escanear (${q.bodega})',
                      style: AppTypography.cuerpoChico),
                const SizedBox(height: AppSpacing.sm),
                FilledButton.icon(
                  onPressed: _ocupado ? null : _escanear,
                  icon: const Icon(Icons.qr_code_scanner),
                  label: const Text('Escanear'),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _Caja extends StatelessWidget {
  const _Caja({required this.rotulo, required this.titulo, this.detalle, required this.hijos});

  final String rotulo;
  final String titulo;
  final String? detalle;
  final List<Widget> hijos;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(rotulo, style: AppTypography.labelBadge.copyWith(color: AppColors.outline)),
          Text(titulo, style: AppTypography.headlineMd),
          if (detalle != null) Text(detalle!, style: AppTypography.cuerpoChico),
          const SizedBox(height: AppSpacing.xs),
          ...hijos,
        ],
      ),
    );
  }
}

/// «No coincide»: lo que recibió de cada material y por qué.
class _HojaDeDiferencias extends StatefulWidget {
  const _HojaDeDiferencias({required this.entrega});
  final EntregaPorConfirmar entrega;

  @override
  State<_HojaDeDiferencias> createState() => _HojaDeDiferenciasState();
}

/// Un material sin serie del acta, con lo que dice el acta sumado: el
/// servidor compara por material, y dos líneas del mismo serían dos campos
/// con la misma llave.
class _Renglon {
  _Renglon(this.linea, this.enElActa);
  final LineaDeEntrega linea;
  double enElActa;
}

class _HojaDeDiferenciasState extends State<_HojaDeDiferencias> {
  late final List<_Renglon> _renglones = () {
    final Map<String, _Renglon> por = <String, _Renglon>{};
    for (final LineaDeEntrega l in widget.entrega.lineas) {
      if (l.serie.isNotEmpty) continue;
      final double n = double.tryParse(l.cantidad) ?? 0;
      por.update(l.codigo, (_Renglon r) => r..enElActa += n,
          ifAbsent: () => _Renglon(l, n));
    }
    return por.values.toList();
  }();
  late final Map<String, TextEditingController> _recibido = <String, TextEditingController>{
    for (final _Renglon r in _renglones)
      r.linea.codigo: TextEditingController(text: _numero(r.enElActa)),
  };
  final TextEditingController _motivo = TextEditingController();
  String? _problema;

  static String _numero(double n) =>
      n == n.roundToDouble() ? n.toStringAsFixed(0) : '$n';

  /// Lo escrito, con coma o con punto.
  String _escrito(String codigo) =>
      _recibido[codigo]!.text.trim().replaceAll(',', '.');

  @override
  void dispose() {
    for (final TextEditingController c in _recibido.values) {
      c.dispose();
    }
    _motivo.dispose();
    super.dispose();
  }

  void _enviar() {
    final String motivo = _motivo.text.trim();
    final List<Diferencia> diferencias = <Diferencia>[
      for (final _Renglon r in _renglones)
        if (double.tryParse(_escrito(r.linea.codigo)) != r.enElActa)
          Diferencia(codigo: r.linea.codigo, recibido: _escrito(r.linea.codigo), motivo: motivo),
    ];
    if (diferencias.isEmpty) {
      setState(() => _problema = 'Cambiá la cantidad de lo que no te llegó completo.');
      return;
    }
    if (motivo.isEmpty) {
      setState(() => _problema = 'Contá qué pasó: queda escrito para la bodega.');
      return;
    }
    Navigator.of(context).pop(diferencias);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.margen,
        right: AppSpacing.margen,
        top: AppSpacing.md,
        bottom: MediaQuery.of(context).viewInsets.bottom + AppSpacing.md,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('¿Qué recibiste?', style: AppTypography.headlineMd),
            Text('Corregí la cantidad de lo que no llegó completo.',
                style: AppTypography.cuerpoChico),
            const SizedBox(height: AppSpacing.sm),
            for (final _Renglon r in _renglones)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.xs),
                child: TextField(
                  key: ValueKey<String>('recibido-${r.linea.codigo}'),
                  controller: _recibido[r.linea.codigo],
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(
                    labelText:
                        '${r.linea.nombre} (en el acta: ${_numero(r.enElActa)} ${r.linea.unidad})',
                  ),
                ),
              ),
            TextField(
              key: const ValueKey<String>('motivo'),
              controller: _motivo,
              decoration: const InputDecoration(labelText: '¿Qué pasó?'),
            ),
            if (_problema != null) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(_problema!, style: AppTypography.cuerpoChico.copyWith(color: AppColors.error)),
            ],
            const SizedBox(height: AppSpacing.md),
            FilledButton(onPressed: _enviar, child: const Text('Enviar')),
          ],
        ),
      ),
    );
  }
}
