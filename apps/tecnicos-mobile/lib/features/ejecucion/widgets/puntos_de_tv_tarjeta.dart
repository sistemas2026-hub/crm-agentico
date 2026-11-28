/// LOS PUNTOS DE TV, EN «MATERIAL UTILIZADO» (26/11/2026).
///
/// El usuario: «unos botones, primero preguntando cuántos puntos de TV, y se
/// despliega una lista; cada uno ya tendría el material utilizado; preguntar
/// si utilizó el cable de la empresa y cuántos metros». La cuenta está en
/// `puntos_de_tv.dart`; acá se elige, se muestra y se registra.
library;

import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/dexter_bloques.dart';
import '../puntos_de_tv.dart';
import 'material_precargado.dart';

class PuntosDeTvTarjeta extends StatefulWidget {
  const PuntosDeTvTarjeta({
    super.key,
    required this.config,
    required this.kit,
    required this.alRegistrar,
  });

  /// `tipo.puntos_de_tv` de la orden.
  final Map<String, dynamic> config;
  final List<Map<String, dynamic>> kit;
  final Future<void> Function(List<LineaDeConsumo> lineas) alRegistrar;

  @override
  State<PuntosDeTvTarjeta> createState() => _EstadoPuntosDeTv();
}

class _EstadoPuntosDeTv extends State<PuntosDeTvTarjeta> {
  int? _puntos;
  //  Si el técnico cambió el spliter que se propuso (usó otro).
  String? _spliterElegido;
  bool? _usoCable;
  final TextEditingController _metros = TextEditingController();
  bool _guardando = false;
  String? _error;

  int get _maximo => int.tryParse('${widget.config['maximo_de_puntos'] ?? ''}') ?? 5;

  Map<String, dynamic>? get _cable => widget.config['cable'] is Map
      ? Map<String, dynamic>.from(widget.config['cable'] as Map)
      : null;

  Map<String, dynamic> get _conector =>
      Map<String, dynamic>.from(widget.config['conector'] as Map? ?? const <String, dynamic>{});

  @override
  void dispose() {
    _metros.dispose();
    super.dispose();
  }

  double _tiene(String codigo) {
    for (final Map<String, dynamic> k in widget.kit) {
      if (k['codigo'] == codigo) return double.tryParse('${k['disponible'] ?? ''}') ?? 0;
    }
    return 0;
  }

  String _n(double v) => v == v.roundToDouble() ? v.toInt().toString() : v.toString();

  CuentaDeTv? get _cuenta => _puntos == null
      ? null
      : cuentaDeTv(config: widget.config, puntos: _puntos!, kit: widget.kit);

  MaterialDeLaCuenta? get _spliter {
    final CuentaDeTv? c = _cuenta;
    if (c == null || c.puntos < 2) return null;
    if (_spliterElegido != null) {
      return spliteresDe(widget.config)
          .where((MaterialDeLaCuenta s) => s.codigo == _spliterElegido)
          .firstOrNull;
    }
    return c.spliter;
  }

  Future<void> _registrar() async {
    final CuentaDeTv? c = _cuenta;
    if (c == null || c.puntos <= 0) return;
    final List<LineaDeConsumo> lineas = <LineaDeConsumo>[
      LineaDeConsumo(
        codigo: (_conector['codigo'] ?? '').toString(),
        nombre: (_conector['nombre'] ?? '').toString(),
        cantidad: '${c.conectores}',
      ),
    ];
    final MaterialDeLaCuenta? spl = _spliter;
    if (c.puntos >= 2) {
      if (spl == null) {
        setState(() => _error = 'Elige el spliter que usaste.');
        return;
      }
      lineas.add(LineaDeConsumo(codigo: spl.codigo, nombre: spl.nombre, cantidad: '1'));
    }
    final Map<String, dynamic>? cable = _cable;
    if (cable != null) {
      if (_usoCable == null) {
        setState(() => _error = 'Di si usaste cable de la empresa.');
        return;
      }
      if (_usoCable!) {
        final double? m = double.tryParse(_metros.text.trim().replaceAll(',', '.'));
        if (m == null || m <= 0) {
          setState(() => _error = 'Escribe cuántos metros de cable usaste.');
          return;
        }
        lineas.add(LineaDeConsumo(
            codigo: (cable['codigo'] ?? '').toString(),
            nombre: (cable['nombre'] ?? '').toString(),
            cantidad: _n(m)));
      }
    }
    setState(() {
      _guardando = true;
      _error = null;
    });
    await widget.alRegistrar(lineas);
    if (mounted) setState(() => _guardando = false);
  }

  @override
  Widget build(BuildContext context) {
    final CuentaDeTv? c = _cuenta;
    final MaterialDeLaCuenta? spl = _spliter;
    return DexterHundido(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(children: <Widget>[
            const Icon(Icons.tv, size: 20, color: AppColors.secondary),
            const SizedBox(width: AppSpacing.xs),
            Expanded(child: Text('Puntos de TV', style: AppTypography.tituloChico)),
          ]),
          const SizedBox(height: 2),
          Text('¿Cuántos puntos de TV instalaste?',
              style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant)),
          const SizedBox(height: AppSpacing.sm),
          Wrap(spacing: AppSpacing.xs, runSpacing: AppSpacing.xs, children: <Widget>[
            _Opcion(
              texto: 'Ninguno',
              elegida: _puntos == 0,
              alTocar: () => setState(() {
                _puntos = 0;
                _error = null;
              }),
            ),
            for (int n = 1; n <= _maximo; n++)
              _Opcion(
                texto: '$n',
                elegida: _puntos == n,
                alTocar: () => setState(() {
                  _puntos = n;
                  _spliterElegido = null;
                  _error = null;
                }),
              ),
          ]),
          if (c != null && c.puntos > 0) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            _Fila(
              nombre: '${_conector['nombre'] ?? 'Conector coaxial'}',
              cantidad: '× ${c.conectores}',
              nota: 'Tienes ${_n(_tiene('${_conector['codigo']}'))}',
              alerta: _tiene('${_conector['codigo']}') < c.conectores,
            ),
            if (c.puntos >= 2) ...<Widget>[
              if (spl != null)
                _Fila(
                  nombre: spl.nombre,
                  cantidad: '× 1',
                  nota: _tiene(spl.codigo) > 0
                      ? 'Tienes ${_n(_tiene(spl.codigo))} · de ${spl.salidas} salidas'
                      : 'No está en tu kit · de ${spl.salidas} salidas',
                  alerta: _tiene(spl.codigo) <= 0,
                )
              else
                Text(
                  c.ningunSpliterAlcanza
                      ? 'Ningún spliter de la empresa tiene $_puntos salidas: elige el que usaste.'
                      : 'Elige el spliter que usaste.',
                  style: AppTypography.cuerpoChico.copyWith(color: AppColors.precaucion),
                ),
              //  Si usó otro, lo cambia: los que alcanzan, y los demás también.
              Wrap(spacing: AppSpacing.xs, runSpacing: AppSpacing.xs, children: <Widget>[
                for (final MaterialDeLaCuenta s in spliteresDe(widget.config))
                  _Opcion(
                    texto: 'De ${s.salidas}',
                    elegida: spl?.codigo == s.codigo,
                    alTocar: () => setState(() => _spliterElegido = s.codigo),
                  ),
              ]),
            ],
            if (_cable != null) ...<Widget>[
              const SizedBox(height: AppSpacing.sm),
              Text('¿Usaste cable de la empresa?', style: AppTypography.etiquetaGrande),
              const SizedBox(height: AppSpacing.xs),
              Row(children: <Widget>[
                _Opcion(texto: 'Sí', elegida: _usoCable == true,
                    alTocar: () => setState(() => _usoCable = true)),
                const SizedBox(width: AppSpacing.xs),
                _Opcion(texto: 'No', elegida: _usoCable == false,
                    alTocar: () => setState(() => _usoCable = false)),
                if (_usoCable == true) ...<Widget>[
                  const SizedBox(width: AppSpacing.sm),
                  SizedBox(
                    width: 120,
                    child: TextField(
                      controller: _metros,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(
                          hintText: 'Metros', suffixText: 'm', isDense: true),
                    ),
                  ),
                ],
              ]),
            ],
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
                icon: const Icon(Icons.check),
                label: const Text('Registrar el material de TV'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _Fila extends StatelessWidget {
  const _Fila({required this.nombre, required this.cantidad, required this.nota, this.alerta = false});
  final String nombre;
  final String cantidad;
  final String nota;
  final bool alerta;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
        child: Row(children: <Widget>[
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
              Text(nombre, style: AppTypography.etiquetaGrande),
              Text(nota,
                  style: AppTypography.etiquetaChica.copyWith(
                      color: alerta ? AppColors.precaucion : AppColors.onSurfaceVariant)),
            ]),
          ),
          Text(cantidad, style: AppTypography.labelTelemetry.copyWith(color: AppColors.onSurface)),
        ]),
      );
}

/// Una opción para tocar: grande, con el azul de acción cuando está elegida.
class _Opcion extends StatelessWidget {
  const _Opcion({required this.texto, required this.elegida, required this.alTocar});
  final String texto;
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
            //  Sin «alignment»: con él, el recuadro se estira a todo el ancho
            //  dentro del Wrap y las opciones quedan una debajo de otra.
            child: Container(
              constraints: const BoxConstraints(minWidth: 48, minHeight: 44),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
              child: Text(texto,
                  textAlign: TextAlign.center,
                  style: AppTypography.etiquetaGrande.copyWith(
                      color: elegida ? AppColors.onSecondary : AppColors.onSurface)),
            ),
          ),
        ),
      );
}
