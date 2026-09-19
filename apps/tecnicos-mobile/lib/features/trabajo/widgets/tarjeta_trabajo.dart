import 'package:flutter/material.dart';

import '../../../core/mock/field_mock_data.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/dexter_card.dart';
import '../../../core/widgets/dexter_status_badge.dart';
import '../trabajo_vista.dart';

/// Un trabajo en la lista.
///
/// La clase de trabajo cambia el icono, la palabra y el color del acento; el
/// estado cambia la pastilla. Son dos cosas distintas y se leen por separado.
class TarjetaTrabajo extends StatelessWidget {
  const TarjetaTrabajo({
    super.key,
    required this.trabajo,
    this.onTap,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final TrabajoVista trabajo;
  final VoidCallback? onTap;

  /// SLA, zona, prioridad y distancia son datos de ejemplo (CAMPO-DATA-002 a
  /// 005). Fuera del modo demostración no se dibujan: un técnico parado en la
  /// puerta de un cliente no puede leer una zona inventada como si fuera la
  /// suya.
  final bool mostrarDatosFuturos;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: DexterCard(
        onTap: onTap,
        colorAcento: trabajo.estado.enMarcha ? AppColors.azulAccion : null,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(_iconoFamilia, size: 16, color: AppColors.azulMarino),
                const SizedBox(width: AppSpacing.xs),
                Flexible(
                  child: Text(
                    _textoFamilia.toUpperCase(),
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.azulMarino,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                if (trabajo.numero != null)
                  Text(
                    '#${trabajo.numero}',
                    style: AppTypography.etiqueta.copyWith(
                      color: AppColors.textoSecundario,
                    ),
                  ),
                const Spacer(),
                DexterStatusBadge(
                  estado: trabajo.estado.presentacion,
                  etiqueta: trabajo.estado.etiqueta,
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              trabajo.clienteNombre,
              style: AppTypography.tituloChico,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: AppSpacing.xs),
            Row(
              children: <Widget>[
                const Icon(Icons.location_on_outlined,
                    size: 14, color: AppColors.textoSecundario),
                const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Text(
                    trabajo.direccion,
                    style: AppTypography.cuerpoChico,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            if (trabajo.requiereActualizacion) ...<Widget>[
              const SizedBox(height: AppSpacing.sm),
              Row(
                children: <Widget>[
                  const Icon(Icons.system_update, size: 14, color: AppColors.error),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      'Necesita una versión más nueva de la aplicación',
                      style: AppTypography.cuerpoChico.copyWith(
                        color: AppColors.error,
                      ),
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.xs,
              children: <Widget>[
                // La hora sí es real: sale de la fecha de compromiso.
                if (trabajo.compromiso != null)
                  _Dato(
                    icono: Icons.schedule,
                    texto: _hora(trabajo.compromiso!),
                  ),
                // Lo que sigue todavía no lo entrega ningún sistema. Se ve solo
                // en modo demostración; no filtra, no ordena y no habilita nada.
                if (mostrarDatosFuturos) ...<Widget>[
                  // CAMPO-DATA-002
                  _Dato(
                    icono: Icons.timer_outlined,
                    texto: 'SLA ${trabajo.futuro.slaRestante}',
                  ),
                  // CAMPO-DATA-003
                  _Dato(icono: Icons.map_outlined, texto: trabajo.futuro.zona),
                  // CAMPO-DATA-004
                  _Dato(icono: Icons.flag_outlined, texto: trabajo.futuro.prioridad),
                  // CAMPO-DATA-005
                  _Dato(
                    icono: Icons.navigation_outlined,
                    texto: '${trabajo.futuro.distanciaKm.toStringAsFixed(1)} km',
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  String get _textoFamilia => trabajo.familia == FamiliaTrabajo.otro
      ? trabajo.tipoNombre
      : trabajo.familia.etiqueta;

  IconData get _iconoFamilia => switch (trabajo.familia) {
        FamiliaTrabajo.instalacion => Icons.add_circle_outline,
        FamiliaTrabajo.incidencia => Icons.report_problem_outlined,
        FamiliaTrabajo.mantenimiento => Icons.build_outlined,
        FamiliaTrabajo.otro => Icons.assignment_outlined,
      };

  static String _hora(DateTime fecha) =>
      '${fecha.hour.toString().padLeft(2, '0')}:${fecha.minute.toString().padLeft(2, '0')}';
}

class _Dato extends StatelessWidget {
  const _Dato({required this.icono, required this.texto});

  final IconData icono;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(icono, size: 13, color: AppColors.inactivo),
        const SizedBox(width: AppSpacing.xs),
        Text(texto, style: AppTypography.etiquetaChica),
      ],
    );
  }
}
