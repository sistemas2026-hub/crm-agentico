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
    this.reencolarRechazadas,
  });

  final ResumenPendientes pendientes;

  /// Intenta subir lo que falta. Devuelve lo que quedó pendiente después.
  final Future<ResumenPendientes> Function() sincronizar;

  /// Devuelve a la cola lo que el servidor RECHAZO, y responde cuántos movió.
  ///
  /// POR QUE ES UN CAMINO APARTE Y NO «Sincronizar ahora» (10/11/2026):
  /// sincronizar no toca un `conflicto` ni un `error_validacion` --salen del
  /// reintento automático a propósito, porque repetirlos tal cual es un
  /// bucle--. Sin este botón el aviso «necesitan que alguien lo revise»
  /// mandaba a revisar sin que existiera el cómo: el técnico tocaba
  /// «Sincronizar ahora», veía «Enviando cambios» y volvía al mismo número.
  ///
  /// Opcional: donde no se pase, la hoja se comporta como antes.
  final Future<int> Function()? reencolarRechazadas;

  static Future<SalidaDePendientes?> mostrar(
    BuildContext context, {
    required ResumenPendientes pendientes,
    required Future<ResumenPendientes> Function() sincronizar,
    Future<int> Function()? reencolarRechazadas,
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
        reencolarRechazadas: reencolarRechazadas,
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

  /// Lo que dejó el último reintento de los rechazados. Se muestra tal cual:
  /// «no había ninguno» es una respuesta, no un error.
  String? _dichoDelReintento;

  /// Vuelve a poner en la cola lo que el servidor rechazó y lo manda.
  ///
  /// Dice CUANTOS movió antes de intentar, porque cero y tres son dos
  /// respuestas distintas y la pantalla no puede hacerlas parecer la misma.
  Future<void> _volverAIntentarRechazados() async {
    final Future<int> Function()? reencolar = widget.reencolarRechazadas;
    if (reencolar == null) return;

    setState(() {
      _sincronizando = true;
      _dichoDelReintento = null;
    });

    int movidas = 0;
    try {
      movidas = await reencolar();
    } catch (_) {
      //  Un fallo al escribir en la base del teléfono no puede tumbar esta
      //  hoja: el técnico tiene que poder salir de acá.
      movidas = 0;
    }
    if (!mounted) return;

    if (movidas == 0) {
      setState(() {
        _sincronizando = false;
        _dichoDelReintento = 'No había ningún cambio rechazado para reintentar.';
      });
      return;
    }

    setState(() {
      _dichoDelReintento = movidas == 1
          ? '1 cambio vuelve a la cola. Mandándolo…'
          : '$movidas cambios vuelven a la cola. Mandándolos…';
      _sincronizando = false;
    });
    await _intentarSincronizar();
  }

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
            // El material se nombra aparte porque no se recupera igual que lo
            // demás: una foto se puede volver a tomar y una transición se
            // puede repetir, pero lo que se gastó en la calle solo consta acá.
            // Si se pierde, el inventario de la empresa sigue diciendo que el
            // material está en la camioneta.
            if (_pendientes.movimientosDeMaterial > 0) ...<Widget>[
              const SizedBox(height: 6),
              Text(
                'Hay movimientos de materiales pendientes de sincronizar.',
                style: AppTypography.cuerpoChico.copyWith(
                  color: AppColors.onSurface,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
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
            if (_dichoDelReintento != null) ...<Widget>[
              const SizedBox(height: 12),
              Text(
                _dichoDelReintento!,
                style: AppTypography.cuerpoChico,
              ),
            ],
            if (_falloElIntento) ...<Widget>[
              const SizedBox(height: 12),
              //  EL TEXTO CULPABA A LA SEÑAL  --  10/11/2026.
              //
              //  Decía «Puede ser que no haya señal acá» pase lo que pase. Con
              //  la red en verde y el servidor rechazando, eso manda a buscar
              //  señal a quien ya la tiene, y el cambio no iba a salir ni
              //  parado en la antena. Ahora la frase depende de lo que la
              //  lista de arriba dice de verdad.
              Text(
                widget.reencolarRechazadas != null
                    ? 'No se pudo subir todo. Lo que dice «el servidor lo '
                        'rechazó» no es falta de señal: no va a salir solo.'
                    : 'No se pudo subir todo. Puede ser que no haya señal acá.',
                style: AppTypography.cuerpoChico.copyWith(color: AppColors.error),
              ),
            ],
            if (_falloElIntento && widget.reencolarRechazadas != null) ...<Widget>[
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: OutlinedButton(
                  onPressed:
                      _sincronizando ? null : _volverAIntentarRechazados,
                  child: const Text('Volver a intentar los rechazados'),
                ),
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
