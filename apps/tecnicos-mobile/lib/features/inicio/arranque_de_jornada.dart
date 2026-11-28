import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../materiales/estado_de_jornada.dart';

/// LO QUE SE LE DICE AL TÉCNICO AL ARRANCAR LA JORNADA (02/11/2026).
///
/// El usuario: «ponés el botón y enseguida le indique pa qué va, y lo muestre,
/// que revise el inventario para salir».
///
/// Dos cosas en una hoja, en ese orden:
///
///   1. QUÉ VA A PASAR. Que desde ahora la oficina ve dónde está su cuadrilla,
///      hasta que termine el día. Se lo dice antes de que pase, no después:
///      enterarse de que lo están ubicando es distinto de que se lo avisen.
///   2. QUÉ TIENE QUE REVISAR ANTES DE SALIR. El material que lleva. Volver
///      a la bodega por un conector es media mañana perdida, y es el momento
///      en que todavía se puede arreglar.
///
/// NO PIDE EL PERMISO ACÁ. Lo pide el servicio cuando el técnico confirma:
/// primero se le explica, después el sistema le pregunta. Al revés, el
/// diálogo de Android aparece sin contexto y lo razonable es negarlo.
class ArranqueDeJornada extends StatelessWidget {
  const ArranqueDeJornada({
    super.key,
    required this.estado,
    required this.alConfirmar,
  });

  /// El kit del día, para mostrarlo. Null si todavía no se pudo leer.
  final EstadoDeJornada? estado;

  /// Lo que hace «Ya revisé, arrancar».
  final VoidCallback alConfirmar;

  /// Abre la hoja. Devuelve `true` si el técnico confirmó.
  static Future<bool> mostrar(
    BuildContext contexto, {
    required EstadoDeJornada? estado,
  }) async {
    final bool? r = await showModalBottomSheet<bool>(
      context: contexto,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppSpacing.lg)),
      ),
      builder: (BuildContext c) => ArranqueDeJornada(
        estado: estado,
        alConfirmar: () => Navigator.of(c).pop(true),
      ),
    );
    return r ?? false;
  }

  @override
  Widget build(BuildContext context) {
    final List<MaterialDeJornada> kit = estado?.materiales ?? const [];
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Text(
              'Arrancar mi jornada',
              style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: AppSpacing.md),

            // 1 · QUÉ VA A PASAR.
            _Bloque(
              icono: Icons.location_on,
              titulo: 'La oficina va a ver dónde está tu cuadrilla',
              texto: 'Desde que arrancás y hasta que termine el día, para '
                  'saber a quién mandar al próximo caso. No se guarda por '
                  'dónde pasaste. Mañana no comparte nada hasta que vuelvas '
                  'a arrancar.',
            ),
            const SizedBox(height: AppSpacing.md),

            // 2 · QUÉ REVISAR ANTES DE SALIR.
            _Bloque(
              icono: Icons.inventory_2_outlined,
              titulo: 'Revisá el material antes de salir',
              texto: kit.isEmpty
                  ? 'No figura material entregado para hoy. Si tenías que '
                      'recibir un kit, pasá por bodega antes de salir.'
                  : 'Esto es lo que figura a tu nombre. Si falta algo, '
                      'resolvelo en bodega ahora: volver después es media '
                      'mañana.',
            ),
            if (kit.isNotEmpty) ...<Widget>[
              const SizedBox(height: AppSpacing.sm),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 220),
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: kit.length,
                  itemBuilder: (BuildContext c, int i) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
                    child: Row(
                      children: <Widget>[
                        Expanded(
                          child: Text(kit[i].nombre,
                              style: const TextStyle(fontSize: 14)),
                        ),
                        Text(
                          //  Lo que sigue a su nombre: lo que lleva encima y
                          //  todavía no devolvió.
                          '${MaterialDeJornada.numero(kit[i].porDevolver)}'
                          ' ${kit[i].unidad}',
                          style: const TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],

            const SizedBox(height: AppSpacing.lg),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: alConfirmar,
                child: const Text('Ya revisé, arrancar'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Bloque extends StatelessWidget {
  const _Bloque({
    required this.icono,
    required this.titulo,
    required this.texto,
  });

  final IconData icono;
  final String titulo;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(icono, size: 20, color: AppColors.secondary),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(titulo,
                  style: const TextStyle(
                      fontSize: 14.5, fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Text(texto,
                  style: const TextStyle(
                      fontSize: 13, color: AppColors.onSurfaceVariant)),
            ],
          ),
        ),
      ],
    );
  }
}
