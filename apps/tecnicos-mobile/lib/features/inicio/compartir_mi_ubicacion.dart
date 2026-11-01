import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/ubicacion/compartir_ubicacion.dart';

/// EL INTERRUPTOR DE LA UBICACIÓN, en Inicio (31/10/2026).
///
/// Dice las tres cosas que el técnico necesita para decidir, en su idioma:
/// qué se comparte, cuándo deja de compartirse, y que lo puede apagar él.
/// Sin eso, un interruptor de ubicación en una aplicación de trabajo se lee
/// como «la empresa me está siguiendo», y la respuesta razonable del técnico
/// sería no prenderlo nunca.
///
/// NO MUESTRA LA COORDENADA. Al técnico no le sirve ver sus grados; le sirve
/// saber si la oficina lo está viendo ahora mismo.
class CompartirMiUbicacion extends StatelessWidget {
  const CompartirMiUbicacion({
    super.key,
    required this.servicio,
    this.alCambiar,
  });

  final CompartirUbicacion servicio;

  /// Para que la pantalla se entere: el estado vive en el servicio.
  final VoidCallback? alCambiar;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<EstadoDeUbicacion>(
      valueListenable: servicio.estado,
      builder: (BuildContext contexto, EstadoDeUbicacion estado, _) {
        final bool prendido = servicio.encendido;
        final bool mal = estado == EstadoDeUbicacion.sinPermiso ||
            estado == EstadoDeUbicacion.fueraDeJornada;
        return Container(
          margin: const EdgeInsets.only(bottom: AppSpacing.lg),
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(AppSpacing.md),
            border: Border.all(
              color: prendido ? AppColors.secondary : AppColors.outlineVariant,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Icon(
                    prendido ? Icons.location_on : Icons.location_off,
                    color: prendido ? AppColors.secondary : AppColors.onSurfaceVariant,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  const Expanded(
                    child: Text(
                      'Compartir mi ubicación',
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
                    ),
                  ),
                  Switch(
                    value: prendido,
                    onChanged: (bool v) async {
                      if (v) {
                        await servicio.encender();
                      } else {
                        await servicio.apagar();
                      }
                      alCambiar?.call();
                    },
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                textoDeUbicacion(estado),
                style: TextStyle(
                  fontSize: 13,
                  color: mal ? AppColors.error : AppColors.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: AppSpacing.xs),
              const Text(
                'La oficina ve dónde está tu cuadrilla para saber a quién '
                'mandar al próximo caso. Solo mientras dura tu jornada y '
                'mientras tengas la app abierta. Lo podés apagar cuando '
                'quieras, y nadie guarda por dónde pasaste.',
                style: TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
              ),
            ],
          ),
        );
      },
    );
  }
}
