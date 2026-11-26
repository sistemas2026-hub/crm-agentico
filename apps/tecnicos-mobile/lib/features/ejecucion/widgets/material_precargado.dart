/// EL MATERIAL QUE YA VIENE PUESTO (26/11/2026).
///
/// El usuario, probando una instalación: «como sale el material en esta orden
/// debería ir material utilizado, que sea precargado. Cuando se hace una
/// instalación se utilizan 2 conectores APC, una ONU, dos tensores, un
/// precinto, dos chazos y dos tornillos para anclar la ONU; las grapas y la
/// fibra son variadas». Decidió: vienen puestas y el técnico las ajusta.
///
/// Lo que se muestra lo decide la empresa (la plantilla, en la plataforma); la
/// app solo lo trae puesto. Una línea sin cantidad se escribe acá. Un equipo
/// con serie (la ONU) se elige de los que el técnico tiene a cargo, y si una
/// serie que ya escribió en el formulario —el serial de la ONU— es una de
/// ellas, viene marcada.
///
/// Registrar es lo mismo que «Agregar material», una línea por material, cada
/// una con su clave de idempotencia: el servidor no sabe que vinieron juntas.
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/dexter_bloques.dart';

/// Lo que se registra de una línea.
@immutable
class LineaDeConsumo {
  const LineaDeConsumo({
    required this.codigo,
    required this.nombre,
    required this.cantidad,
    this.serie = '',
  });

  final String codigo;
  final String nombre;

  /// Como texto, que es como viaja en la cola (sin errores de coma flotante).
  final String cantidad;
  final String serie;
}

class MaterialPrecargado extends StatefulWidget {
  const MaterialPrecargado({
    super.key,
    required this.lineas,
    required this.kit,
    required this.alRegistrar,
    this.seriesEscritas = const <String>{},
    this.cantidadesDeCampos = const <String, double?>{},
    this.textosDeCampos = const <String, String?>{},
  });

  /// Las líneas que faltan registrar: `{codigo, nombre, unidad, clase, cantidad}`.
  final List<Map<String, dynamic>> lineas;

  /// El kit del técnico, de la base del teléfono (disponible y series).
  final List<Map<String, dynamic>> kit;

  /// Lo que el técnico ya escribió en los campos que se leen con la cámara,
  /// para marcar la serie que coincida.
  final Set<String> seriesEscritas;

  /// Por código, la cantidad que sale de un campo de la plantilla (los metros
  /// de fibra). Esas líneas no se editan acá: se corrigen en su campo, que es
  /// una sola fuente para el mismo dato.
  final Map<String, double?> cantidadesDeCampos;

  /// Por código, lo escrito en el campo de donde sale la SERIE de un equipo
  /// (el serial de la ONU). El usuario, 26/11/2026: «donde dice ONU GPON debe
  /// llenarse solo al momento que el técnico escanea, para no volver a
  /// escribir».
  final Map<String, String?> textosDeCampos;

  final Future<void> Function(List<LineaDeConsumo> lineas) alRegistrar;

  @override
  State<MaterialPrecargado> createState() => _EstadoMaterialPrecargado();
}

class _EstadoMaterialPrecargado extends State<MaterialPrecargado> {
  final Map<String, double> _cantidad = <String, double>{};
  final Map<String, TextEditingController> _escrita = <String, TextEditingController>{};
  final Map<String, String> _serie = <String, String>{};
  bool _guardando = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    for (final Map<String, dynamic> l in widget.lineas) {
      final String codigo = _codigo(l);
      final double? c = _numero(l['cantidad']);
      if (_cantidadDeCampo(l)) continue;
      if (_esSerializado(l)) {
        _cantidad[codigo] = 1;
        if (_serieDeCampo(l)) continue;
        final String? sugerida = _seriesDe(codigo).where(
          (String s) => widget.seriesEscritas.contains(s.trim().toUpperCase()),
        ).firstOrNull;
        if (sugerida != null) _serie[codigo] = sugerida;
      } else if (c != null) {
        _cantidad[codigo] = c;
      } else {
        _escrita[codigo] = TextEditingController();
      }
    }
  }

  @override
  void dispose() {
    for (final TextEditingController c in _escrita.values) {
      c.dispose();
    }
    super.dispose();
  }

  static String _codigo(Map<String, dynamic> l) => (l['codigo'] ?? '').toString();

  static bool _desdeCampo(Map<String, dynamic> l) =>
      (l['campo'] ?? '').toString().trim().isNotEmpty;

  static bool _esSerializado(Map<String, dynamic> l) =>
      (l['clase'] ?? '').toString() == 'serializado';

  /// Lo que sale del campo es la CANTIDAD (los metros de fibra)...
  static bool _cantidadDeCampo(Map<String, dynamic> l) => _desdeCampo(l) && !_esSerializado(l);

  /// ...o, en un equipo con serie, la SERIE (el serial de la ONU).
  static bool _serieDeCampo(Map<String, dynamic> l) => _desdeCampo(l) && _esSerializado(l);

  String _serieEscaneada(String codigo) =>
      (widget.textosDeCampos[codigo] ?? '').replaceAll(RegExp(r'\s+'), '').toUpperCase();

  static double? _numero(dynamic v) =>
      v == null ? null : double.tryParse(v.toString().replaceAll(',', '.'));

  static String _texto(double v) =>
      v == v.roundToDouble() ? v.toInt().toString() : v.toString();

  Map<String, dynamic>? _delKit(String codigo) =>
      widget.kit.where((Map<String, dynamic> k) => k['codigo'] == codigo).firstOrNull;

  /// Las series que el técnico tiene a cargo de ese equipo.
  List<String> _seriesDe(String codigo) {
    final dynamic crudo = _delKit(codigo)?['series_json'];
    if (crudo == null) return const <String>[];
    try {
      final dynamic lista = crudo is String ? jsonDecode(crudo) : crudo;
      return <String>[
        for (final dynamic s in (lista as List<dynamic>))
          if ((s is Map ? s['serie'] : s)?.toString().trim().isNotEmpty ?? false)
            (s is Map ? s['serie'] : s).toString().trim(),
      ];
    } catch (_) {
      return const <String>[];
    }
  }

  Future<void> _registrar() async {
    final List<LineaDeConsumo> salen = <LineaDeConsumo>[];
    for (final Map<String, dynamic> l in widget.lineas) {
      final String codigo = _codigo(l);
      final String nombre = (l['nombre'] ?? codigo).toString();
      final double cantidad = _cantidadDeCampo(l)
          ? (widget.cantidadesDeCampos[codigo] ?? 0)
          : _escrita.containsKey(codigo)
              ? (_numero(_escrita[codigo]!.text.trim()) ?? 0)
              : (_cantidad[codigo] ?? 0);
      if (cantidad <= 0) continue;
      if (_esSerializado(l)) {
        final String serie =
            _serieDeCampo(l) ? _serieEscaneada(codigo) : (_serie[codigo] ?? '').trim();
        if (serie.isEmpty) {
          setState(() => _error = _serieDeCampo(l)
              ? 'Escanea el serial en «${l['campo']}»: de ahí sale la serie de $nombre.'
              : 'Elige la serie de $nombre: sin ella no se sabe cuál equipo quedó en la casa.');
          return;
        }
        salen.add(LineaDeConsumo(codigo: codigo, nombre: nombre, cantidad: '1', serie: serie));
        continue;
      }
      salen.add(LineaDeConsumo(codigo: codigo, nombre: nombre, cantidad: _texto(cantidad)));
    }
    if (salen.isEmpty) {
      setState(() => _error = 'No hay nada para registrar: todas las cantidades están en cero.');
      return;
    }
    setState(() {
      _guardando = true;
      _error = null;
    });
    await widget.alRegistrar(salen);
    if (mounted) setState(() => _guardando = false);
  }

  @override
  Widget build(BuildContext context) {
    return DexterHundido(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(children: <Widget>[
            const Icon(Icons.playlist_add_check, size: 20, color: AppColors.secondary),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text('Lo que se usa en este trabajo', style: AppTypography.tituloChico),
            ),
          ]),
          const SizedBox(height: 2),
          Text(
            'Viene puesto. Ajusta lo que usaste de más o de menos y regístralo.',
            style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant),
          ),
          const SizedBox(height: AppSpacing.sm),
          for (final Map<String, dynamic> l in widget.lineas) _linea(l),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text(_error!,
                  style: AppTypography.cuerpoChico.copyWith(color: AppColors.error)),
            ),
          const SizedBox(height: AppSpacing.sm),
          SizedBox(
            height: AppSpacing.objetivoTactil,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.azulAccion,
                shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
              ),
              onPressed: _guardando ? null : _registrar,
              icon: _guardando
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.check),
              label: const Text('Registrar este material'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _linea(Map<String, dynamic> l) {
    final String codigo = _codigo(l);
    final String nombre = (l['nombre'] ?? codigo).toString();
    final String unidad = (l['unidad'] ?? '').toString();
    final Map<String, dynamic>? delKit = _delKit(codigo);
    final double? disponible = _numero(delKit?['disponible']);
    final double usada = _cantidadDeCampo(l)
        ? (widget.cantidadesDeCampos[codigo] ?? 0)
        : _escrita.containsKey(codigo)
            ? (_numero(_escrita[codigo]!.text) ?? 0)
            : (_cantidad[codigo] ?? 0);
    final String aviso = delKit == null
        ? 'No está en tu kit'
        : (disponible != null && usada > disponible
            ? 'Tienes ${_texto(disponible)}: te faltan ${_texto(usada - disponible)}'
            : 'Tienes ${disponible == null ? '—' : _texto(disponible)}');
    final bool alerta = delKit == null || (disponible != null && usada > disponible);

    final Widget control;
    if (_cantidadDeCampo(l)) {
      //  Lo que escribió en su campo, sin poder cambiarlo acá.
      final double? v = widget.cantidadesDeCampos[codigo];
      control = Text(
        v == null ? '—' : '${_texto(v)}${unidad == 'unidades' ? '' : ' $unidad'}',
        style: AppTypography.labelTelemetry.copyWith(
            color: v == null ? AppColors.outline : AppColors.onSurface),
      );
    } else if (_esSerializado(l)) {
      control = const SizedBox.shrink();
    } else if (_escrita.containsKey(codigo)) {
      control = SizedBox(
        width: 110,
        child: TextField(
          controller: _escrita[codigo],
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textAlign: TextAlign.center,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            hintText: 'Cuánto',
            suffixText: unidad == 'unidades' ? null : unidad,
            isDense: true,
          ),
        ),
      );
    } else {
      control = _Pasos(
        valor: _cantidad[codigo] ?? 0,
        alCambiar: (double v) => setState(() => _cantidad[codigo] = v),
      );
    }

    final List<String> series = _esSerializado(l) ? _seriesDe(codigo) : const <String>[];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(nombre, style: AppTypography.etiquetaGrande),
                  if (_cantidadDeCampo(l))
                    Text(
                      widget.cantidadesDeCampos[codigo] == null
                          ? 'Escríbelos en «${l['campo']}»'
                          : 'De «${l['campo']}»',
                      style: AppTypography.etiquetaChica.copyWith(color: AppColors.secondary),
                    ),
                  if (_serieDeCampo(l))
                    Text(
                      _serieEscaneada(codigo).isEmpty
                          ? 'Escanéalo en «${l['campo']}»'
                          : 'Serie de «${l['campo']}»',
                      style: AppTypography.etiquetaChica.copyWith(color: AppColors.secondary),
                    ),
                  Text(aviso,
                      style: AppTypography.etiquetaChica.copyWith(
                          color: alerta ? AppColors.precaucion : AppColors.onSurfaceVariant)),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            control,
          ]),
          //  LA SERIE YA ESCANEADA: se muestra, no se elige ni se escribe. Si
          //  no es una del kit del técnico se avisa, y se registra igual: el
          //  equipo está instalado, y la diferencia la cuadra la bodega.
          if (_serieDeCampo(l)) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(_serieEscaneada(codigo).isEmpty ? '—' : _serieEscaneada(codigo),
                style: AppTypography.labelTelemetry.copyWith(
                    color: _serieEscaneada(codigo).isEmpty ? AppColors.outline : AppColors.secondary)),
            if (_serieEscaneada(codigo).isNotEmpty && series.isNotEmpty &&
                !series.map((String s) => s.toUpperCase()).contains(_serieEscaneada(codigo)))
              Text('Esa serie no está en tu kit: se registra igual y la cuadra la bodega.',
                  style: AppTypography.etiquetaChica.copyWith(color: AppColors.precaucion)),
          ] else if (_esSerializado(l)) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            if (series.isEmpty)
              TextField(
                onChanged: (String v) => setState(() => _serie[codigo] = v),
                decoration: const InputDecoration(labelText: 'Serie del equipo', isDense: true),
              )
            else
              Wrap(
                spacing: AppSpacing.xs,
                runSpacing: AppSpacing.xs,
                children: <Widget>[
                  for (final String s in series)
                    _PildoraDeSerie(
                      serie: s,
                      elegida: _serie[codigo] == s,
                      alTocar: () => setState(() => _serie[codigo] = s),
                    ),
                ],
              ),
          ],
        ],
      ),
    );
  }
}

/// − n +, con objetivos de 44 px: se toca con guante.
class _Pasos extends StatelessWidget {
  const _Pasos({required this.valor, required this.alCambiar});
  final double valor;
  final ValueChanged<double> alCambiar;

  @override
  Widget build(BuildContext context) {
    final String texto = valor == valor.roundToDouble() ? valor.toInt().toString() : valor.toString();
    Widget boton(IconData icono, String etiqueta, VoidCallback? alTocar) => Semantics(
          button: true,
          label: etiqueta,
          child: Material(
            color: AppColors.surfaceContainerLowest,
            shape: const CircleBorder(),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: alTocar,
              child: SizedBox(
                width: 44,
                height: 44,
                child: Icon(icono, size: 20,
                    color: alTocar == null ? AppColors.inactivo : AppColors.secondary),
              ),
            ),
          ),
        );
    return Row(mainAxisSize: MainAxisSize.min, children: <Widget>[
      boton(Icons.remove, 'Uno menos', valor > 0 ? () => alCambiar(valor - 1) : null),
      SizedBox(
        width: 36,
        child: Text(texto,
            textAlign: TextAlign.center,
            style: AppTypography.labelTelemetry.copyWith(color: AppColors.onSurface)),
      ),
      boton(Icons.add, 'Uno más', () => alCambiar(valor + 1)),
    ]);
  }
}

class _PildoraDeSerie extends StatelessWidget {
  const _PildoraDeSerie({required this.serie, required this.elegida, required this.alTocar});
  final String serie;
  final bool elegida;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) => Semantics(
        button: true,
        selected: elegida,
        child: Material(
          color: elegida ? AppColors.secondary : AppColors.surfaceContainerLowest,
          borderRadius: AppRadius.brChico,
          child: InkWell(
            onTap: alTocar,
            borderRadius: AppRadius.brChico,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Text(serie,
                  style: AppTypography.labelTelemetry.copyWith(
                      color: elegida ? AppColors.onSecondary : AppColors.onSurface)),
            ),
          ),
        ),
      );
}
