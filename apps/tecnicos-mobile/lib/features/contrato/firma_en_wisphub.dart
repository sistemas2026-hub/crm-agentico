/// LA FIRMA EN EL PORTAL DEL PROVEEDOR, DENTRO DE LA APP (27/11/2026).
///
/// El enlace de firma entra al portal del cliente SIN clave. Abierto en el
/// navegador del teléfono quedaba en su historial (y en la sincronización de
/// la cuenta), y cualquiera con ese teléfono podía volver a entrar al portal
/// de ese cliente (revisión de privacidad, 27/11/2026). Aquí se abre en una
/// vista dentro de Dexter que, al cerrarse, borra cookies, caché y
/// almacenamiento: no queda nada en el teléfono.
///
/// El enlace llega SIEMPRE por https (el motor lo asegura). Al terminar, el
/// técnico toca «Listo» y en el contrato «Ya firmó: comprobar».
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../../core/theme/app_theme.dart';

/// Abre el enlace dentro de la app. Devuelve si se pudo abrir.
Future<bool> abrirFirmaDentroDeLaApp(BuildContext context, String enlace) async {
  final Uri? uri = Uri.tryParse(enlace);
  if (uri == null || uri.scheme != 'https') return false;
  await Navigator.of(context).push<void>(
    MaterialPageRoute<void>(builder: (_) => FirmaEnWispHub(enlace: uri)),
  );
  return true;
}

class FirmaEnWispHub extends StatefulWidget {
  const FirmaEnWispHub({super.key, required this.enlace});

  final Uri enlace;

  @override
  State<FirmaEnWispHub> createState() => _EstadoFirma();
}

class _EstadoFirma extends State<FirmaEnWispHub> {
  late final WebViewController _vista;
  int _progreso = 0;

  @override
  void initState() {
    super.initState();
    _vista = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onProgress: (int p) {
          if (mounted) setState(() => _progreso = p);
        },
      ));
    unawaited(_abrir());
  }

  Future<void> _abrir() async {
    //  Empieza limpia: nada de una firma anterior.
    await _limpiar();
    await _vista.loadRequest(widget.enlace);
  }

  Future<void> _limpiar() async {
    try {
      await _vista.clearCache();
      await _vista.clearLocalStorage();
      await WebViewCookieManager().clearCookies();
    } catch (_) {
      //  Limpiar no puede tumbar la pantalla del técnico.
    }
  }

  @override
  void dispose() {
    unawaited(_limpiar());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Firma en WispHub'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Listo'),
          ),
        ],
      ),
      body: Column(
        children: <Widget>[
          if (_progreso < 100)
            LinearProgressIndicator(
              value: _progreso == 0 ? null : _progreso / 100,
              color: AppColors.azulAccion,
            ),
          Expanded(child: WebViewWidget(controller: _vista)),
        ],
      ),
    );
  }
}
