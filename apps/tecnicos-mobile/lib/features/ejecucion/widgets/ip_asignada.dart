/// LA IP QUE ASIGNÓ EL SISTEMA, PARA COPIARLA (26/11/2026).
///
/// El usuario: «en el paso 4 debe salir la IP que asignó el sistema, y que
/// deje copiar pero no modificar». La asigna el servidor al crear el contrato
/// (`contrato._ip_automatica`); acá se lee del contrato firmado y se muestra
/// como texto, no como campo: no hay nada que editar. El botón la copia para
/// pegarla al configurar el equipo.
///
/// Necesita señal, como el contrato: la IP existe recién cuando el contrato se
/// firmó, y eso ya pidió señal.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_theme.dart';
import '../../contrato/contrato_screen.dart';

class IpAsignada extends StatefulWidget {
  const IpAsignada({super.key, required this.ordenId, this.api = const ApiDelContrato()});

  final String ordenId;
  final ApiDelContrato api;

  @override
  State<IpAsignada> createState() => _EstadoIpAsignada();
}

class _EstadoIpAsignada extends State<IpAsignada> {
  bool _leyendo = true;
  String? _ip;
  String? _error;
  bool _hayContrato = false;

  @override
  void initState() {
    super.initState();
    _leer();
  }

  Future<void> _leer() async {
    setState(() {
      _leyendo = true;
      _error = null;
    });
    final RespuestaDelServidor r = await widget.api.leer(widget.ordenId);
    if (!mounted) return;
    final dynamic contrato = r.cuerpo?['contrato'];
    setState(() {
      _leyendo = false;
      _error = r.error;
      _hayContrato = contrato is Map;
      final String ip = contrato is Map ? (contrato['ip_elegida'] ?? '').toString().trim() : '';
      _ip = ip.isEmpty ? null : ip;
    });
  }

  Future<void> _copiar(String ip) async {
    await Clipboard.setData(ClipboardData(text: ip));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text('IP $ip copiada')));
  }

  @override
  Widget build(BuildContext context) {
    final String? ip = _ip;
    final String nota = _leyendo
        ? 'Buscando la IP del contrato…'
        : _error != null
            ? 'Sin señal: la IP se ve cuando haya señal.'
            : !_hayContrato
                ? 'Todavía no hay contrato: la IP se asigna al crearlo.'
                : ip == null
                    ? 'El contrato se firmó sin IP: la asigna la oficina.'
                    : 'La asignó el sistema. Cópiala para configurar el equipo.';
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brCompleto,
        border: Border.all(color: AppColors.surfaceContainerHigh),
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Row(children: <Widget>[
        Container(
          width: 48,
          height: 48,
          alignment: Alignment.center,
          decoration: const BoxDecoration(
            color: AppColors.infoFondo,
            borderRadius: AppRadius.brTarjeta,
          ),
          child: const Icon(Icons.lan_outlined, size: 26, color: AppColors.secondary),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text('IP ASIGNADA',
                  style: AppTypography.labelCaption.copyWith(color: AppColors.outline)),
              //  Texto seleccionable y no un campo: se puede copiar a mano
              //  también, pero no hay nada que escribir.
              SelectableText(
                ip ?? '—',
                style: AppTypography.labelTelemetry.copyWith(
                    fontSize: 20,
                    color: ip == null ? AppColors.outline : AppColors.onSurface),
              ),
              Text(nota,
                  style: AppTypography.cuerpoChico.copyWith(color: AppColors.onSurfaceVariant)),
            ],
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        if (ip != null)
          Semantics(
            button: true,
            label: 'Copiar la IP',
            child: Material(
              color: AppColors.secondary,
              shape: const CircleBorder(),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: () => _copiar(ip),
                child: const SizedBox(
                  width: 48,
                  height: 48,
                  child: Icon(Icons.copy, size: 22, color: AppColors.onSecondary),
                ),
              ),
            ),
          )
        else if (!_leyendo)
          IconButton(
            tooltip: 'Volver a buscar',
            onPressed: _leer,
            icon: const Icon(Icons.refresh, color: AppColors.secondary),
          ),
      ]),
    );
  }
}
