import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../../core/storage/local_database.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radius.dart';
import '../../../core/theme/app_typography.dart';
import '../estado_de_jornada.dart';

/// Por qué falta material, dicho por quien lo tenía.
///
/// POR QUÉ EL MOTIVO ES OBLIGATORIO
/// --------------------------------
/// No por rigor administrativo. Sin esa frase, el faltante aparece en el
/// conteo físico dentro de tres meses y ya no hay a quién preguntarle: la
/// persona que sabía qué pasó está en otra jornada, o en otra empresa. Cinco
/// segundos ahora ahorran una discusión imposible después.
///
/// LOS CINCO MOTIVOS SON LOS DEL DOMINIO
/// -------------------------------------
/// No se inventan acá ni se traducen a otra cosa: son los mismos que acepta el
/// servidor. Una lista propia en la pantalla se desincronizaría el día que el
/// backend agregue uno, y la app seguiría ofreciendo opciones que ya no
/// existen.
class MotivoDeDiferencia extends StatefulWidget {
  const MotivoDeDiferencia({
    super.key,
    required this.orgId,
    required this.profileId,
    required this.material,
    this.baseLocal,
  });

  final String orgId;
  final String profileId;
  final MaterialDeJornada material;
  final LocalDatabase? baseLocal;

  static Future<bool?> abrir(
    BuildContext context, {
    required String orgId,
    required String profileId,
    required MaterialDeJornada material,
    LocalDatabase? baseLocal,
  }) {
    return showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.hoja)),
      ),
      builder: (_) => MotivoDeDiferencia(
        orgId: orgId,
        profileId: profileId,
        material: material,
        baseLocal: baseLocal,
      ),
    );
  }

  @override
  State<MotivoDeDiferencia> createState() => _MotivoDeDiferenciaState();
}

/// Los tipos que acepta el servidor, con el nombre que usa la cuadrilla.
///
/// El valor es el del dominio; la etiqueta es la que alguien entiende parado
/// en una bodega a las siete de la tarde.
const Map<String, String> motivosDeDiferencia = <String, String>{
  'perdido': 'Perdido',
  'danado': 'Dañado',
  'usado_sin_registrar': 'Utilizado y no registrado',
  'entregado_a_otro': 'Entregado a otro técnico',
  'otro': 'Otro',
};

class _MotivoDeDiferenciaState extends State<MotivoDeDiferencia> {
  late final LocalDatabase _db = widget.baseLocal ?? LocalDatabase();
  final TextEditingController _detalle = TextEditingController();
  String? _tipo;
  bool _guardando = false;
  String? _error;

  @override
  void dispose() {
    _detalle.dispose();
    super.dispose();
  }

  /// "Otro" sin explicación no explica nada: ahí el detalle es obligatorio.
  bool get _exigeDetalle => _tipo == 'otro';

  Future<void> _guardar() async {
    if (_tipo == null) {
      setState(() => _error = 'Elegí qué pasó con el material.');
      return;
    }
    if (_exigeDetalle && _detalle.text.trim().isEmpty) {
      setState(() => _error = 'Contá qué pasó, aunque sea en una línea.');
      return;
    }

    setState(() {
      _guardando = true;
      _error = null;
    });

    // El motivo que se guarda junta la etiqueta y lo que la persona escribió:
    // "Dañado" solo no le sirve a quien lea esto en dos meses.
    final etiqueta = motivosDeDiferencia[_tipo] ?? 'Otro';
    final detalle = _detalle.text.trim();
    final motivo = detalle.isEmpty ? etiqueta : '$etiqueta: $detalle';

    await _db.encolarIncidencia(
      id: const Uuid().v4(),
      orgId: widget.orgId,
      profileId: widget.profileId,
      materialCodigo: widget.material.codigo,
      materialNombre: widget.material.nombre,
      tipo: _tipo!,
      cantidad: widget.material.diferencia.toString(),
      serie: widget.material.serie ?? '',
      motivo: motivo,
    );

    if (mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final material = widget.material;
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
              Text('¿Qué pasó con este material?',
                  style: AppTypography.tituloChico),
              const SizedBox(height: 6),
              Text(
                material.serie == null
                    ? 'Faltan ${_texto(material.diferencia)} '
                        '${material.unidad} de ${material.nombre}.'
                    : '${material.nombre}, serie ${material.serie}, no volvió '
                        'ni quedó instalado.',
                style: AppTypography.cuerpo,
              ),
              const SizedBox(height: 16),
              // Botones en vez de una lista de radios: se eligen de un
              // toque con guantes puestos, y los cinco se ven a la vez sin
              // tener que desplazar nada.
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  for (final entrada in motivosDeDiferencia.entries)
                    ChoiceChip(
                      label: Text(entrada.value),
                      selected: _tipo == entrada.key,
                      onSelected: _guardando
                          ? null
                          : (_) => setState(() {
                                _tipo = entrada.key;
                                _error = null;
                              }),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _detalle,
                maxLines: 2,
                decoration: InputDecoration(
                  labelText: _exigeDetalle
                      ? 'Contá qué pasó'
                      : 'Detalle (opcional)',
                  helperText: 'Lo va a leer alguien en la oficina.',
                ),
              ),
              if (_error != null) ...<Widget>[
                const SizedBox(height: 8),
                Text(_error!,
                    style: AppTypography.cuerpoChico
                        .copyWith(color: AppColors.error)),
              ],
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: FilledButton(
                  onPressed: _guardando ? null : _guardar,
                  child: _guardando
                      ? const SizedBox(
                          width: 18, height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Guardar explicación'),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Queda en el teléfono y sube cuando haya señal.',
                style: AppTypography.cuerpoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _texto(double valor) => valor == valor.roundToDouble()
      ? valor.round().toString()
      : valor.toString();
}
