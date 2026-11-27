/// LA INSTALACIÓN QUE VALIDA UNA PERSONA (26/11/2026).
///
/// El usuario: «cuando el técnico manda finalizar trabajo entra en validación
/// humana, y si aprueba la instalación se le informa al técnico para que
/// valide servicio y entregue al cliente, y después cierra el ticket».
///
/// Este recuadro sale en una instalación ya finalizada:
///   * en validación → que espere: una persona la revisa y la activa;
///   * aprobada → que valide el servicio, la entregue y lo confirme aquí. Al
///     confirmar, el servidor cierra la orden y el ticket del proveedor.
///
/// EXIGE SEÑAL Y NO SE ENCOLA, como el contrato: cerrar el ticket del cliente
/// horas después, sin que nadie mire, no es una entrega.
library;

import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';
import '../trabajo/estado_validacion.dart';

/// La llamada. Reemplazable en pruebas. Devuelve `null` si quedó entregada, o
/// el porqué si no.
class ApiDeLaEntrega {
  const ApiDeLaEntrega();

  Future<String?> entregar(String ordenId) async {
    try {
      await ApiClient()
          .post<dynamic>(ApiEndpoints.instalacionEntregada(ordenId), data: <String, dynamic>{})
          .timeout(const Duration(seconds: 40));
      return null;
    } catch (e) {
      if (e is DioException) {
        final dynamic d = e.response?.data;
        if (d is Map && d['detail'] is String) return d['detail'] as String;
        if (e.response == null) return 'Sin señal: no se confirmó. Toca otra vez cuando tengas señal.';
        return 'El servidor no respondió bien (${e.response?.statusCode}). Intenta de nuevo.';
      }
      if (e is TimeoutException) return 'Sin señal: no se confirmó. Toca otra vez cuando tengas señal.';
      return 'No se pudo confirmar. Intenta de nuevo.';
    }
  }
}

class EntregaDeLaInstalacion extends StatefulWidget {
  const EntregaDeLaInstalacion({
    super.key,
    required this.ordenId,
    required this.validacion,
    this.api = const ApiDeLaEntrega(),
    this.alEntregar,
  });

  final String ordenId;
  final EstadoValidacion validacion;
  final ApiDeLaEntrega api;

  /// Después de entregar: que la pantalla vuelva a leer la orden.
  final Future<void> Function()? alEntregar;

  @override
  State<EntregaDeLaInstalacion> createState() => _EstadoEntrega();
}

class _EstadoEntrega extends State<EntregaDeLaInstalacion> {
  bool _enviando = false;
  bool _entregada = false;
  String? _error;

  Future<void> _entregar() async {
    setState(() {
      _enviando = true;
      _error = null;
    });
    final String? error = await widget.api.entregar(widget.ordenId);
    if (!mounted) return;
    setState(() {
      _enviando = false;
      _error = error;
      _entregada = error == null;
    });
    if (error == null) await widget.alEntregar?.call();
  }

  @override
  Widget build(BuildContext context) {
    final bool aprobada = widget.validacion == EstadoValidacion.aprobado;
    if (_entregada) {
      return const DexterBloque(
        titulo: 'Trabajo finalizado',
        icono: Icons.verified_outlined,
        insignia: DexterPastilla.enRegla(texto: 'Entregada'),
        children: <Widget>[
          Text('Listo: la instalación quedó entregada y se cerraron la orden y el '
              'ticket del cliente.'),
        ],
      );
    }
    if (!aprobada) {
      return DexterBloque(
        titulo: 'En validación',
        icono: Icons.hourglass_top,
        insignia: const DexterPastilla.neutra(texto: 'Esperando'),
        children: <Widget>[
          Text(
            'Una persona revisa la instalación y la activa. Te avisamos aquí cuando '
            'quede activa para que valides el servicio, lo entregues y finalices '
            'el trabajo.',
            style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant),
          ),
        ],
      );
    }
    return DexterBloque(
      titulo: 'Aprobada y activa',
      icono: Icons.task_alt,
      insignia: const DexterPastilla.enRegla(texto: 'Activa'),
      separacion: AppSpacing.sm,
      children: <Widget>[
        Text(
          'Valida que el servicio funcione y entrégalo al cliente. Al tocar '
          '«Finalizar trabajo» se cierran la orden y el ticket.',
          style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant),
        ),
        if (_error != null)
          Text(_error!, style: AppTypography.cuerpoChico.copyWith(color: AppColors.error)),
        SizedBox(
          height: AppSpacing.objetivoTactilAmplio,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.azulAccion,
              shape: const RoundedRectangleBorder(borderRadius: AppRadius.brTarjeta),
            ),
            onPressed: _enviando ? null : _entregar,
            icon: _enviando
                ? const SizedBox(
                    width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.handshake_outlined),
            //  «FINALIZAR TRABAJO» (27/11/2026). El usuario: «si confirman
            //  que está bien finaliza el trabajo». Antes decía «Servicio
            //  validado y entregado».
            label: Text(_enviando ? 'Finalizando…' : 'Finalizar trabajo',
                maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
        ),
      ],
    );
  }
}
