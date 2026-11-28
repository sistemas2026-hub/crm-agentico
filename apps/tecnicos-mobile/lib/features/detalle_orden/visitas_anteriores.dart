import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';

/// Lo que ya se hizo en este mismo servicio.
///
/// LA PREGUNTA QUE CONTESTA
/// ------------------------
/// El técnico toca el timbre y el cliente le dice *«ya llamé tres veces»*. Hasta
/// acá no tenía con qué contestar: la ficha le daba el número de ticket y nada
/// más — el número que sirve para buscar el historial **en otro lado**, o sea
/// para llamar al NOC. Es la llamada más frecuente de las que el técnico
/// enumeró, y el dato ya estaba en la base.
///
/// TRES ESTADOS QUE NO SON EL MISMO
/// --------------------------------
/// | Qué pasa | Qué significa | Qué hace el técnico |
/// |---|---|---|
/// | `null` | nunca se bajó | sincronizar, o llamar |
/// | `hayServicio == false` | no se puede saber | llamar al NOC |
/// | lista vacía | es la primera vez | contestarle al cliente |
///
/// Resumir los tres en «sin visitas anteriores» es el error que importa: le
/// haría decir *«es la primera vez que venimos»* a alguien que vino tres veces.
class VisitasAnteriores extends StatelessWidget {
  const VisitasAnteriores({super.key, required this.historial});

  /// Lo que devolvió el servidor, tal cual. `null` = todavía no se bajó.
  final Map<String, dynamic>? historial;

  bool get _hayServicio => historial?['hay_servicio'] == true;

  List<Map<String, dynamic>> get _visitas {
    final Object? v = historial?['visitas'];
    if (v is! List) return const <Map<String, dynamic>>[];
    return v
        .whereType<Map>()
        .map((Map m) => Map<String, dynamic>.from(m))
        .toList();
  }

  /// Los tickets anteriores del mismo servicio, en el sistema del ISP.
  ///
  /// 18/10/2026: las órdenes de campo de Dexter son nuevas, así que con solo
  /// ellas casi todo decía «primera visita». La historia real del servicio son
  /// sus tickets. Vienen sin asunto: el servidor no lo manda, porque trae
  /// nombres y barrios escritos a mano.
  List<Map<String, dynamic>> get _tickets {
    final Object? v = historial?['tickets'];
    if (v is! List) return const <Map<String, dynamic>>[];
    return v
        .whereType<Map>()
        .map((Map m) => Map<String, dynamic>.from(m))
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    return DexterBloque(
      titulo: 'Visitas anteriores',
      icono: Icons.history,
      children: _cuerpo(),
    );
  }

  List<Widget> _cuerpo() {
    if (historial == null) {
      return <Widget>[
        Text('Todavía no se descargó.', style: AppTypography.cuerpo),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Se baja al sincronizar. Bajala con señal antes de salir.',
          style: AppTypography.etiquetaChica,
        ),
      ];
    }

    if (!_hayServicio) {
      // NO es lo mismo que «no hubo visitas». Esta orden no tiene identificado
      // el servicio en el sistema del ISP, así que no se puede saber — y
      // adivinar por nombre o dirección devolvería visitas del vecino.
      return <Widget>[
        Text('No se puede saber.', style: AppTypography.cuerpo),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Esta orden no tiene el servicio identificado en el sistema del ISP. '
          'Si el cliente dice que ya llamó, preguntá al NOC.',
          style: AppTypography.etiquetaChica,
        ),
      ];
    }

    final List<Map<String, dynamic>> visitas = _visitas;
    final List<Map<String, dynamic>> tickets = _tickets;
    if (visitas.isEmpty && tickets.isEmpty) {
      return <Widget>[
        Text('Es la primera visita a este servicio.',
            style: AppTypography.cuerpo),
      ];
    }

    return <Widget>[
      if (visitas.isNotEmpty) ...<Widget>[
        _subtitulo('Visitas de campo'),
        for (int i = 0; i < visitas.length; i++) ...<Widget>[
          const SizedBox(height: AppSpacing.xs),
          _unaVisita(visitas[i]),
        ],
      ] else
        Text('Ninguna visita de campo anterior registrada.',
            style: AppTypography.cuerpoChico),
      if (tickets.isNotEmpty) ...<Widget>[
        const SizedBox(height: AppSpacing.md),
        _subtitulo('Tickets anteriores de este servicio'),
        for (final Map<String, dynamic> t in tickets) ...<Widget>[
          const SizedBox(height: AppSpacing.xs),
          _unTicket(t),
        ],
      ],
    ];
  }

  Widget _subtitulo(String texto) => Text(
        texto.toUpperCase(),
        style: AppTypography.labelCaption.copyWith(color: AppColors.outline),
      );

  /// Un ticket: su número, cuándo se abrió y si se cerró.
  Widget _unTicket(Map<String, dynamic> t) {
    final String numero = (t['numero'] ?? '').toString();
    final bool abierto = (t['estado'] ?? '') == 'abierto';
    final String abiertoEn = _cuando(t['abierto_en']);
    final String cerradoEn = _cuando(t['cerrado_en']);
    final String area = (t['area'] ?? '').toString().replaceAll('_', ' ');
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
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  numero.isEmpty ? 'Ticket' : 'Ticket #$numero',
                  style: AppTypography.cuerpo,
                ),
              ),
              if (abierto)
                DexterPastilla.alerta(texto: 'abierto')
              else
                DexterPastilla.neutra(texto: 'cerrado'),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            <String>[
              if (abiertoEn.isNotEmpty) 'Abierto el $abiertoEn',
              if (!abierto && cerradoEn.isNotEmpty) 'cerrado el $cerradoEn',
              if (area.isNotEmpty) area,
            ].join(' · '),
            style: AppTypography.etiquetaChica,
          ),
        ],
      ),
    );
  }

  Widget _unaVisita(Map<String, dynamic> v) {
    final String tipo = (v['tipo'] ?? '').toString();
    final String termino = (v['como_termino'] ?? '').toString();
    final String quien = (v['quien'] ?? '').toString();
    final bool cambioEquipo = v['cambio_equipo'] == true;
    final List<dynamic> materiales =
        (v['materiales'] as List<dynamic>?) ?? const <dynamic>[];

    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  tipo.isEmpty ? 'OT #${v['numero']}' : '$tipo · #${v['numero']}',
                  style: AppTypography.cuerpo,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (termino.isNotEmpty) _comoTermino(termino),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            <String>[
              _cuando(v['cuando']),
              if (quien.isNotEmpty) quien,
            ].where((String s) => s.isNotEmpty).join(' · '),
            style: AppTypography.etiquetaChica,
          ),
          if (cambioEquipo) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            // La pregunta que el técnico hace distinto del resto: «¿ya le
            // cambiaron la ONT?». Va destacada porque cambia qué va a hacer.
            Row(
              children: <Widget>[
                const Icon(Icons.swap_horiz, size: 14, color: AppColors.secondary),
                const SizedBox(width: 4),
                Text(
                  'Se cambió el equipo',
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.secondary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ],
          if (materiales.isNotEmpty) ...<Widget>[
            const SizedBox(height: 2),
            Text(
              'Se usó: ${_materiales(materiales)}',
              style: AppTypography.etiquetaChica,
            ),
          ],
        ],
      ),
    );
  }

  Widget _comoTermino(String termino) {
    return switch (termino) {
      'resuelto' => DexterPastilla.enRegla(texto: termino),
      'cancelado' || 'quedó trabado' || 'quedo trabado' =>
        DexterPastilla.alerta(texto: termino),
      _ => DexterPastilla.neutra(texto: termino),
    };
  }

  static String _materiales(List<dynamic> crudo) {
    return crudo
        .whereType<Map>()
        .map((Map m) =>
            '${m['material']} ${m['cantidad']}${m['unidad'] == null || (m['unidad'] as String).isEmpty ? '' : ' ${m['unidad']}'}')
        .join(', ');
  }

  /// La fecha, en el huso del teléfono.
  ///
  /// El servidor manda UTC. Mostrarla sin convertir le restaría cinco horas a
  /// cada visita en Colombia, y una visita «de ayer» aparecería como de
  /// anteayer justo cuando el técnico está contando cuántas van.
  static String _cuando(Object? iso) {
    final DateTime? f = DateTime.tryParse(iso?.toString() ?? '')?.toLocal();
    if (f == null) return '';
    final String dia = f.day.toString().padLeft(2, '0');
    final String mes = f.month.toString().padLeft(2, '0');
    return '$dia/$mes/${f.year}';
  }
}
