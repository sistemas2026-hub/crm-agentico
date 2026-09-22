import 'package:flutter/material.dart';

import '../../core/storage/ciclo_de_vida_local.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_typography.dart';

/// Qué eligió la persona en la hoja de pendientes.
enum SalidaDePendientes {
  /// Quiere subir lo que falta antes de irse.
  sincronizar,

  /// Se queda: cancela el cierre de sesión.
  cancelar,

  /// Se va sabiendo que su trabajo NO subió y queda solo en este teléfono.
  /// Esta opción aparece únicamente si el intento de sincronizar falló.
  salirConservando,
}

/// Lo que se ve al intentar cerrar sesión con trabajo sin subir.
///
/// POR QUÉ ES UNA INTERRUPCIÓN Y NO UN AVISO
/// -----------------------------------------
/// Porque lo que está en juego no se puede deshacer. Una jornada de cuadrilla
/// sin señal son horas de trabajo que viven solo en este teléfono; si se
/// cierra sesión y se borra, no hay de dónde recuperarlas. Un cartel que se
/// va solo no alcanza para eso.
///
/// Y por eso dice **qué** quedó pendiente, no cuántos. "4 cambios" no ayuda a
/// decidir; "OT #4832 · cierre" sí: quien lo lee reconoce el trabajo que hizo
/// hace una hora y entiende qué está por dejar a medias.
///
/// LA TERCERA OPCIÓN, Y CUÁNDO APARECE
/// -----------------------------------
/// De entrada hay dos caminos: sincronizar o quedarse. Irse perdiendo trabajo
/// no se ofrece, porque nadie elige eso a propósito.
///
/// Pero si el intento de sincronizar falla —y va a fallar, porque justamente
/// se cierra sesión al terminar una jornada donde no había señal— quedarse
/// sin salida tampoco sirve: el teléfono puede tener que pasar a otra persona
/// ahora. Entonces sí aparece "Salir dejando los cambios en este teléfono".
///
/// Ese texto dice las cuatro cosas, y en ese orden: que **no llegaron al
/// servidor**, que **no se borran**, que quedan **solo en este teléfono** y
/// que para subirlos hay que **volver con la misma cuenta en el mismo
/// equipo**. Es más largo que "se guardó", y tiene que serlo: "guardado" es
/// justamente la palabra que alguien puede leer como "la oficina ya lo
/// tiene".
class HojaDePendientes extends StatefulWidget {
  const HojaDePendientes({
    super.key,
    required this.pendientes,
    required this.sincronizar,
  });

  final ResumenPendientes pendientes;

  /// Intenta subir lo que falta. Devuelve lo que quedó pendiente después.
  final Future<ResumenPendientes> Function() sincronizar;

  static Future<SalidaDePendientes?> mostrar(
    BuildContext context, {
    required ResumenPendientes pendientes,
    required Future<ResumenPendientes> Function() sincronizar,
  }) {
    return showModalBottomSheet<SalidaDePendientes>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.hoja)),
      ),
      builder: (_) => HojaDePendientes(
        pendientes: pendientes,
        sincronizar: sincronizar,
      ),
    );
  }

  @override
  State<HojaDePendientes> createState() => _HojaDePendientesState();
}

class _HojaDePendientesState extends State<HojaDePendientes> {
  late ResumenPendientes _pendientes = widget.pendientes;
  bool _sincronizando = false;

  /// Se enciende cuando un intento de sincronizar no logró vaciar la cola.
  /// Recién entonces se ofrece salir sin subir.
  bool _falloElIntento = false;

  Future<void> _intentarSincronizar() async {
    setState(() {
      _sincronizando = true;
      _falloElIntento = false;
    });

    ResumenPendientes despues;
    try {
      despues = await widget.sincronizar();
    } catch (_) {
      // Sin red, el servidor caído, un token vencido: para esta pantalla son
      // el mismo caso. Lo que importa no es por qué falló sino que el trabajo
      // sigue acá.
      despues = _pendientes;
    }
    if (!mounted) return;

    if (!despues.hayPendientes) {
      // Ya está todo arriba: se puede salir y limpiar.
      Navigator.of(context).pop(SalidaDePendientes.sincronizar);
      return;
    }

    setState(() {
      _pendientes = despues;
      _sincronizando = false;
      _falloElIntento = true;
    });
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
            Row(
              children: <Widget>[
                const Icon(Icons.cloud_upload_outlined,
                    color: AppColors.secondary, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _pendientes.titulo,
                    style: AppTypography.tituloChico,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'Todavía no llegaron al servidor. Si cerrás sesión ahora, se quedan '
              'en este teléfono.',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.surfaceContainer,
                borderRadius: AppRadius.brTarjeta,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  for (final linea in _pendientes.detalle)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text('· ', style: AppTypography.cuerpo),
                          Expanded(
                            child: Text(linea, style: AppTypography.cuerpo),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            if (_falloElIntento) ...<Widget>[
              const SizedBox(height: 12),
              Text(
                'No se pudo subir todo. Puede ser que no haya señal acá.',
                style: AppTypography.cuerpoChico.copyWith(color: AppColors.error),
              ),
            ],
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: FilledButton(
                onPressed: _sincronizando ? null : _intentarSincronizar,
                child: _sincronizando
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Sincronizar ahora'),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: OutlinedButton(
                onPressed: _sincronizando
                    ? null
                    : () => Navigator.of(context).pop(SalidaDePendientes.cancelar),
                child: const Text('Cancelar'),
              ),
            ),
            if (_falloElIntento) ...<Widget>[
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: TextButton(
                  onPressed: _sincronizando
                      ? null
                      : () => Navigator.of(context)
                          .pop(SalidaDePendientes.salirConservando),
                  child: Text(
                    'Salir dejando los cambios en este teléfono',
                    style: AppTypography.etiquetaGrande.copyWith(
                      color: AppColors.onSurfaceVariant,
                    ),
                  ),
                ),
              ),
              // Las cuatro cosas que esta persona necesita saber, dichas sin
              // rodeos. "Se guardó" y "quedó pendiente" suenan parecido y
              // significan lo contrario: uno puede entenderse como que la
              // oficina ya lo tiene. Por eso acá se dice primero lo que NO
              // pasó.
              Text(
                'Estos cambios NO llegaron al servidor. No se borran, pero quedan '
                'únicamente en este teléfono: en la oficina nadie los ve todavía, y '
                'desde otro equipo no se pueden recuperar. Para que suban hay que '
                'volver a entrar en este mismo teléfono, con esta misma cuenta.',
                style: AppTypography.cuerpoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
