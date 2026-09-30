import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../../core/storage/local_database.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radius.dart';
import '../../../core/theme/app_typography.dart';

/// Registrar lo que se gastó, dentro del trabajo donde se gastó.
///
/// POR QUÉ ESTE GESTO VIVE ACÁ Y NO EN LA PANTALLA DE MATERIALES
/// -------------------------------------------------------------
/// Porque es donde ocurre. El técnico está con las manos en la caja terminal;
/// si para anotar dos conectores tuviera que salir del trabajo, ir a otra
/// pantalla, buscar el material y volver, no lo anota — y el inventario pasa a
/// ser una ficción que se corrige a fin de mes de memoria.
///
/// Además, el consumo necesita saber en qué orden ocurrió: es la regla del
/// dominio, y acá la orden es el contexto, no algo que haya que elegir.
///
/// LO QUE SE MUESTRA ANTES DE CONFIRMAR
/// ------------------------------------
/// El disponible sale de la base local, así que incluye lo que todavía no
/// subió. Y la regla de la empresa —cuánto se suele usar— viaja con el
/// material justamente para poder avisar acá, sin señal: si el aviso llegara
/// al sincronizar, aparecería horas después de que el material ya se gastó.
class ConsumoDeMaterial extends StatefulWidget {
  const ConsumoDeMaterial({
    super.key,
    required this.orgId,
    required this.profileId,
    required this.ordenId,
    required this.ordenNumero,
    this.baseLocal,
    this.alRegistrar,
  });

  final String orgId;
  final String profileId;
  final String ordenId;
  final int? ordenNumero;
  final LocalDatabase? baseLocal;
  final VoidCallback? alRegistrar;

  /// Abre la hoja para elegir material y cantidad.
  static Future<bool?> abrir(
    BuildContext context, {
    required String orgId,
    required String profileId,
    required String ordenId,
    int? ordenNumero,
    LocalDatabase? baseLocal,
  }) {
    return showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.hoja)),
      ),
      builder: (_) => ConsumoDeMaterial(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
        ordenNumero: ordenNumero,
        baseLocal: baseLocal,
      ),
    );
  }

  @override
  State<ConsumoDeMaterial> createState() => _ConsumoDeMaterialState();
}

class _ConsumoDeMaterialState extends State<ConsumoDeMaterial> {
  late final LocalDatabase _db = widget.baseLocal ?? LocalDatabase();

  List<Map<String, dynamic>> _kit = <Map<String, dynamic>>[];
  bool _cargando = true;

  Map<String, dynamic>? _elegido;
  double _disponible = 0;
  int _cantidad = 1;
  final TextEditingController _serie = TextEditingController();
  final TextEditingController _motivo = TextEditingController();
  bool _guardando = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  @override
  void dispose() {
    _serie.dispose();
    _motivo.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    final filas = await _db.getKit(
      orgId: widget.orgId,
      profileId: widget.profileId,
    );
    if (!mounted) return;
    setState(() {
      _kit = filas;
      _cargando = false;
    });
  }

  Future<void> _elegir(Map<String, dynamic> material) async {
    final saldo = await _db.saldoLocalDe(
      orgId: widget.orgId,
      profileId: widget.profileId,
      codigo: (material['codigo'] ?? '').toString(),
    );
    if (!mounted) return;
    setState(() {
      _elegido = material;
      _disponible = saldo;
      _cantidad = 1;
      _error = null;
      _serie.clear();
      _motivo.clear();
    });
  }

  Map<String, dynamic>? get _regla => ReglaDeMaterial.desde(_elegido);

  bool get _esSerializado =>
      (_elegido?['clase'] ?? '').toString() == 'serializado';

  /// Cuánto se suele usar, si la empresa lo configuró.
  double? get _habitual {
    final valor = _regla?['cantidad_habitual'];
    return valor == null ? null : double.tryParse(valor.toString());
  }

  bool get _pasaLoHabitual {
    final habitual = _habitual;
    return habitual != null && _cantidad > habitual;
  }

  bool get _exigeMotivo =>
      _pasaLoHabitual && (_regla?['exige_motivo'] == true);

  Future<void> _registrar() async {
    final material = _elegido;
    if (material == null) return;

    if (_esSerializado && _serie.text.trim().isEmpty) {
      setState(() => _error =
          'Este equipo tiene número de serie. Sin él no se sabe cuál se '
          'instaló, ni se lo encuentra después si el cliente reclama.');
      return;
    }
    if (_exigeMotivo && _motivo.text.trim().isEmpty) {
      setState(() => _error = 'Escribí por qué se usó más de lo habitual.');
      return;
    }

    setState(() {
      _guardando = true;
      _error = null;
    });

    await _db.encolarMovimientoMaterial(
      // La clave se genera UNA vez, acá. El servidor la usa para reconocer un
      // reintento: regenerarla al reenviar es lo que duplica un consumo.
      id: const Uuid().v4(),
      orgId: widget.orgId,
      profileId: widget.profileId,
      materialCodigo: (material['codigo'] ?? '').toString(),
      materialNombre: (material['nombre'] ?? '').toString(),
      tipo: 'consumo',
      cantidad: _cantidad.toString(),
      serie: _serie.text.trim(),
      ordenId: widget.ordenId,
      ordenNumero: widget.ordenNumero,
      motivoTecnico: _motivo.text.trim(),
    );

    widget.alRegistrar?.call();
    if (mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: AppColors.outlineVariant,
                    borderRadius: AppRadius.brChico,
                  ),
                ),
              ),
              Text('Material utilizado', style: AppTypography.tituloChico),
              const SizedBox(height: 4),
              Text(
                widget.ordenNumero == null
                    ? 'Queda registrado en este trabajo.'
                    : 'Queda registrado en la OT #${widget.ordenNumero}.',
                style: AppTypography.cuerpoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 16),
              if (_cargando)
                const Center(child: Padding(
                  padding: EdgeInsets.all(24),
                  child: CircularProgressIndicator(),
                ))
              else if (_kit.isEmpty)
                _sinKit()
              else if (_elegido == null)
                _listaDeMateriales()
              else
                _contador(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sinKit() => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainer,
          borderRadius: AppRadius.brTarjeta,
        ),
        child: Text(
          'Todavía no hay un kit cargado en este teléfono. Aparece cuando la '
          'bodega registre la entrega y haya señal para sincronizar.',
          style: AppTypography.cuerpoChico.copyWith(
            color: AppColors.onSurfaceVariant,
          ),
        ),
      );

  Widget _listaDeMateriales() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          for (final material in _kit)
            InkWell(
              onTap: () => _elegir(material),
              borderRadius: AppRadius.brTarjeta,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text((material['nombre'] ?? '').toString(),
                              style: AppTypography.cuerpoGrande),
                          Text(
                            'Disponible: ${_texto(material['disponible'])} '
                            '${(material['unidad'] ?? '').toString()}',
                            style: AppTypography.cuerpoChico.copyWith(
                              color: AppColors.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const Icon(Icons.chevron_right,
                        color: AppColors.onSurfaceVariant),
                  ],
                ),
              ),
            ),
        ],
      );

  Widget _contador() {
    final material = _elegido!;
    final unidad = (material['unidad'] ?? '').toString();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text((material['nombre'] ?? '').toString(),
                  style: AppTypography.cuerpoGrande),
            ),
            TextButton(
              onPressed: _guardando ? null : () => setState(() => _elegido = null),
              child: const Text('Cambiar'),
            ),
          ],
        ),
        Text(
          'Disponible: ${_texto(_disponible)} $unidad',
          style: AppTypography.cuerpoChico.copyWith(
            color: AppColors.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 16),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            _boton(Icons.remove, _cantidad > 1
                ? () => setState(() => _cantidad--)
                : null),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text('$_cantidad', style: AppTypography.tituloGrande),
            ),
            _boton(Icons.add, () => setState(() => _cantidad++)),
          ],
        ),
        const SizedBox(height: 12),
        // El aviso no impide registrar: el material ya se gastó cuando esto
        // se anota. Solo dice que se pasó de lo que la empresa espera.
        if (_pasaLoHabitual)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
              color: AppColors.surfaceContainer,
              borderRadius: AppRadius.brTarjeta,
            ),
            child: Text(
              'Cantidad superior a lo habitual: se suelen usar '
              '${_texto(_habitual)} $unidad.',
              style: AppTypography.cuerpoChico,
            ),
          ),
        if (_esSerializado)
          TextField(
            controller: _serie,
            decoration: const InputDecoration(
              labelText: 'Número de serie',
              helperText: 'El del equipo que se instaló.',
            ),
          ),
        if (_exigeMotivo)
          TextField(
            controller: _motivo,
            maxLines: 2,
            decoration: const InputDecoration(
              labelText: 'Por qué se usó más de lo habitual',
            ),
          ),
        if (_error != null) ...<Widget>[
          const SizedBox(height: 10),
          Text(_error!,
              style: AppTypography.cuerpoChico.copyWith(color: AppColors.error)),
        ],
        const SizedBox(height: 18),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: FilledButton(
            onPressed: _guardando ? null : _registrar,
            child: _guardando
                ? const SizedBox(
                    width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Registrar consumo'),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Se guarda en el teléfono y sube cuando haya señal.',
          style: AppTypography.cuerpoChico.copyWith(
            color: AppColors.onSurfaceVariant,
          ),
        ),
      ],
    );
  }

  Widget _boton(IconData icono, VoidCallback? alTocar) => SizedBox(
        width: 48,
        height: 48,
        child: OutlinedButton(
          onPressed: alTocar,
          style: OutlinedButton.styleFrom(
            padding: EdgeInsets.zero,
            shape: const CircleBorder(),
          ),
          child: Icon(icono),
        ),
      );

  static String _texto(Object? valor) {
    final numero = valor is double
        ? valor
        : double.tryParse(valor?.toString() ?? '0') ?? 0;
    return numero == numero.roundToDouble()
        ? numero.round().toString()
        : numero.toString();
  }
}

/// La regla de cantidad que el servidor mandó con este material.
///
/// Vive en una clase aparte porque llega como texto JSON dentro de la fila y
/// nadie más debería tener que saber eso.
class ReglaDeMaterial {
  static Map<String, dynamic>? desde(Map<String, dynamic>? fila) {
    final crudo = fila?['regla_json'];
    if (crudo is! String || crudo.isEmpty) return null;
    try {
      final datos = _decodificar(crudo);
      return datos is Map<String, dynamic> ? datos : null;
    } catch (_) {
      // Una regla ilegible se trata como si no existiera: avisar de más
      // molesta, pero impedir registrar por un JSON roto sería peor.
      return null;
    }
  }

  static Object? _decodificar(String crudo) => jsonDecode(crudo);
}
