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
///
/// SIN INTERRUPTOR (02/11/2026). El usuario: «quita el botón de la app de
/// compartir mi ubicación». La tarjeta informa y no se toca: el técnico tiene
/// que estar enterado —para eso sigue acá— pero no decide cada día.
///
/// Lo que NO queda sin salida: apagarlo sigue siendo posible desde los
/// ajustes del teléfono, revocando el permiso de ubicación. Ese control lo
/// garantiza Android y ninguna aplicación lo puede quitar, así que esto no
/// deja a nadie compartiendo sin forma de pararlo.
class CompartirMiUbicacion extends StatelessWidget {
  const CompartirMiUbicacion({
    super.key,
    required this.servicio,
  });

  final CompartirUbicacion servicio;

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
                'Se comparte sola mientras dura tu jornada y tengas la app '
                'abierta, para que la oficina sepa a quién mandar al próximo '
                'caso. No guarda por dónde pasaste. Si la apagás, no vuelve a '
                'encenderse sola.',
                style: TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
              ),
            ],
          ),
        );
      },
    );
  }
}
