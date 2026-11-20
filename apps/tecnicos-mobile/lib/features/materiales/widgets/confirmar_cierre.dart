import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radius.dart';
import '../../../core/theme/app_typography.dart';
import '../estado_de_jornada.dart';

/// La última pantalla antes de dar la jornada por terminada.
///
/// POR QUÉ HAY UNA CONFIRMACIÓN
/// ----------------------------
/// Porque cerrar la jornada congela los números en un acta, y eso no se
/// deshace desde el teléfono. Un toque accidental en un botón al fondo de una
/// lista no puede producir un documento que dos personas van a dar por bueno.
///
/// Lo que se muestra no es un aviso genérico: son los mismos cuatro números
/// que van a quedar escritos. Quien confirma tiene que poder reconocerlos.
class ConfirmarCierre extends StatelessWidget {
  const ConfirmarCierre({super.key, required this.estado});

  final EstadoDeJornada estado;

  static Future<bool?> abrir(BuildContext context, EstadoDeJornada estado) {
    return showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.hoja)),
      ),
      builder: (_) => ConfirmarCierre(estado: estado),
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Vas a cerrar tu jornada', style: AppTypography.tituloChico),
            const SizedBox(height: 4),
            Text(
              'Estos números quedan firmados. Después no se cambian desde el '
              'teléfono.',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 16),
            _bloque('Trabajos', <String>[
              '${estado.ordenesCompletadas} completados',
              if (estado.ordenesPendientes > 0)
                '${estado.ordenesPendientes} sin terminar',
            ]),
            _bloque('Materiales', <String>[
              'Recibido ${estado.recibido}',
              'Consumido ${estado.consumido}',
              'Devuelto ${estado.devuelto}',
            ]),
            _bloque(
              'Diferencias',
              <String>[
                estado.diferencias == 0
                    ? 'Ninguna: todo cuadra'
                    : '${estado.diferencias} explicada(s)',
              ],
              // Cero diferencias es lo normal; tenerlas explicadas también lo
              // es. Ninguna de las dos se marca en rojo acá: si algo estuviera
              // sin resolver, esta pantalla no se habría abierto.
            ),
            _bloque('Sincronización', <String>[
              estado.sinSubir == 0
                  ? 'Todo enviado'
                  : '${estado.sinSubir} pendiente(s) de enviar',
            ]),
            if (estado.sinSubir > 0) ...<Widget>[
              const SizedBox(height: 4),
              Text(
                // Se dice la verdad exacta: el cierre queda tomado, y el
                // servidor lo confirma cuando haya red. Decir "cerrada" acá
                // sería afirmar algo que todavía no pasó.
                'Tu jornada queda cerrada en el teléfono y termina de '
                'registrarse cuando haya señal.',
                style: AppTypography.cuerpoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
            ],
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Sí, cerrar jornada'),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: OutlinedButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Volver'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _bloque(String titulo, List<String> lineas) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Icon(Icons.check, size: 18, color: AppColors.exito),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(titulo, style: AppTypography.etiquetaGrande),
                  for (final linea in lineas)
                    Text(linea, style: AppTypography.cuerpoChico),
                ],
              ),
            ),
          ],
        ),
      );
}
