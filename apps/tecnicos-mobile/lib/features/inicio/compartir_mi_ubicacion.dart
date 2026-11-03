import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/ubicacion/compartir_ubicacion.dart';
import '../materiales/estado_de_jornada.dart';
import 'arranque_de_jornada.dart';

/// ARRANCAR LA JORNADA, en Inicio (02/11/2026).
///
/// El usuario: «en la pantalla de inicio colocá un botón para iniciar la
/// jornada y así se empieza a tomar la ubicación automática», y después:
/// «ponés el botón y enseguida le indique pa qué va, y lo muestre, que revise
/// el inventario para salir».
///
/// DOS ESTADOS, Y UNO SOLO SE TOCA:
///
///   - antes de arrancar: el botón. Al tocarlo se abre la hoja que explica
///     qué va a pasar y le muestra su material (`ArranqueDeJornada`); recién
///     si confirma, el sistema le pide el permiso y empieza a compartir;
///   - ya arrancada: informa, y no se toca. Lo que la apaga es que termine
///     el día: la marca es la FECHA, así que a medianoche deja de ser hoy
///     sola, sin que nadie apague nada.
///
/// NO MUESTRA LA COORDENADA. Al técnico no le sirve ver sus grados; le sirve
/// saber si la oficina lo está viendo ahora mismo.
class CompartirMiUbicacion extends StatelessWidget {
  const CompartirMiUbicacion({
    super.key,
    required this.servicio,
    this.estadoDeJornada,
    this.alArrancar,
  });

  final CompartirUbicacion servicio;

  /// El kit del día, para mostrarlo en la hoja. Null si no se pudo leer.
  final EstadoDeJornada? estadoDeJornada;

  /// Para que la pantalla se redibuje cuando la jornada arranca.
  final VoidCallback? alArrancar;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<EstadoDeUbicacion>(
      valueListenable: servicio.estado,
      builder: (BuildContext contexto, EstadoDeUbicacion estado, _) {
        final bool arrancada = servicio.jornadaIniciada;
        final bool mal = estado == EstadoDeUbicacion.sinPermiso ||
            estado == EstadoDeUbicacion.fueraDeJornada;
        return Container(
          margin: const EdgeInsets.only(bottom: AppSpacing.lg),
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(AppSpacing.md),
            border: Border.all(
              color: arrancada ? AppColors.secondary : AppColors.outlineVariant,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Icon(
                    arrancada ? Icons.location_on : Icons.wb_sunny_outlined,
                    color: arrancada
                        ? AppColors.secondary
                        : AppColors.onSurfaceVariant,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      arrancada ? 'Tu jornada está en marcha' : 'Tu jornada',
                      style: const TextStyle(
                          fontWeight: FontWeight.w600, fontSize: 15),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xs),
              if (arrancada) ...<Widget>[
                Text(
                  textoDeUbicacion(estado),
                  style: TextStyle(
                    fontSize: 13,
                    color: mal ? AppColors.error : AppColors.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                const Text(
                  'Termina sola al final del día. Mañana no se comparte nada '
                  'hasta que vuelvas a arrancar.',
                  style: TextStyle(
                      fontSize: 12, color: AppColors.onSurfaceVariant),
                ),
              ] else ...<Widget>[
                const Text(
                  'Arrancá tu día: revisás el material que llevás y la oficina '
                  'sabe a quién mandar al próximo caso.',
                  style: TextStyle(
                      fontSize: 13, color: AppColors.onSurfaceVariant),
                ),
                const SizedBox(height: AppSpacing.md),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Iniciar jornada'),
                    onPressed: () => _arrancar(contexto),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Future<void> _arrancar(BuildContext contexto) async {
    //  PRIMERO SE LE EXPLICA, DESPUÉS EL SISTEMA LE PREGUNTA. Al revés, el
    //  diálogo de Android aparece sin contexto y lo razonable es negarlo.
    final bool confirmo = await ArranqueDeJornada.mostrar(
      contexto,
      estado: estadoDeJornada,
    );
    if (!confirmo) return;
    await servicio.iniciarJornada();
    alArrancar?.call();
  }
}
