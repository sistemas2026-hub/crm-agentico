import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../theme/app_theme.dart';

/// Leer un serial con la cámara en vez de tipearlo con guantes.
///
/// POR QUÉ ESTO VALE LO QUE PESA
/// -----------------------------
/// Un serial de ONT son 12 a 16 caracteres alfanuméricos, y el técnico los
/// escribe parado, al sol, con guantes, y a veces sobre una escalera. Un dígito
/// mal no da error: queda un equipo registrado con un serial que no existe, y el
/// problema aparece semanas después cuando alguien busca ese equipo y no está.
/// Es la función que las plataformas de campo del rubro ponen primero.
///
/// LO QUE DEVUELVE, Y LO QUE NO
/// ----------------------------
/// Devuelve **el texto leído, sin interpretarlo**. No valida largo, ni formato,
/// ni prefijo de fabricante: un plan de seriales no es igual en dos marcas de
/// ONT, y rechazar el que no encaja le quitaría al técnico la única forma rápida
/// que tiene. Quien lo recibe decide qué hacer con él — compararlo, guardarlo o
/// pedir confirmación.
///
/// Devuelve `null` si la persona salió sin leer nada. `null` y cadena vacía son
/// cosas distintas y acá importa: cancelar no puede borrar lo que ya estaba
/// escrito en el campo.
class LectorDeCodigo extends StatefulWidget {
  const LectorDeCodigo({
    super.key,
    this.titulo = 'Escaneá el código',
    this.ayuda = '',
  });

  final String titulo;

  /// Una línea que dice QUÉ hay que apuntar. Cambia por sitio de uso: no es lo
  /// mismo «el serial del equipo que instalaste» que «el que te entregaron».
  final String ayuda;

  /// Abre el lector y devuelve lo leído, o `null` si se canceló.
  static Future<String?> abrir(
    BuildContext context, {
    String titulo = 'Escaneá el código',
    String ayuda = '',
  }) {
    return Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => LectorDeCodigo(titulo: titulo, ayuda: ayuda),
        fullscreenDialog: true,
      ),
    );
  }

  @override
  State<LectorDeCodigo> createState() => _LectorDeCodigoState();
}

class _LectorDeCodigoState extends State<LectorDeCodigo> {
  final MobileScannerController _control = MobileScannerController(
    // Los seriales vienen en etiqueta de código de barras más que en QR, y las
    // dos formas conviven en la misma caja. Se aceptan las dos en vez de
    // obligar al técnico a saber cuál es cuál.
    formats: const <BarcodeFormat>[
      BarcodeFormat.qrCode,
      BarcodeFormat.code128,
      BarcodeFormat.code39,
      BarcodeFormat.ean13,
      BarcodeFormat.dataMatrix,
    ],
    detectionSpeed: DetectionSpeed.noDuplicates,
  );

  /// Que ya se devolvió una lectura.
  ///
  /// El detector dispara varias veces por segundo. Sin esto, el primer código
  /// cierra la pantalla y los siguientes intentan cerrarla otra vez —
  /// `Navigator.pop` sobre una ruta que ya no está.
  bool _listo = false;

  String? _error;

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  void _alDetectar(BarcodeCapture captura) {
    if (_listo) return;
    for (final Barcode b in captura.barcodes) {
      final String texto = (b.rawValue ?? '').trim();
      if (texto.isEmpty) continue;
      _listo = true;
      Navigator.of(context).pop(texto);
      return;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(widget.titulo),
        // Salir tiene que estar siempre a mano: si el código está rayado o la
        // luz no da, el técnico vuelve a tipear y sigue trabajando.
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Cancelar',
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.flashlight_on),
            // Una caja NAP a las seis de la tarde no tiene luz. La linterna no
            // es un lujo acá.
            tooltip: 'Linterna',
            onPressed: () => _control.toggleTorch(),
          ),
        ],
      ),
      body: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          MobileScanner(
            controller: _control,
            onDetect: _alDetectar,
            errorBuilder: (BuildContext _, MobileScannerException e) {
              // Cámara negada o en uso por otra app. Se dice; dejar la pantalla
              // en negro parece que la app se colgó.
              return _mensaje(
                'No se pudo abrir la cámara.\n'
                'Revisá el permiso en los ajustes del teléfono.',
              );
            },
          ),
          if (_error != null) _mensaje(_error!),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              color: Colors.black.withValues(alpha: 0.6),
              child: Text(
                widget.ayuda.isEmpty
                    ? 'Apuntá al código. Se lee solo.'
                    : widget.ayuda,
                textAlign: TextAlign.center,
                style: AppTypography.cuerpo.copyWith(color: Colors.white),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _mensaje(String texto) => Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Text(
            texto,
            textAlign: TextAlign.center,
            style: AppTypography.cuerpo.copyWith(color: Colors.white),
          ),
        ),
      );
}

/// Si dos seriales son el mismo, para una persona.
///
/// POR QUÉ NO ALCANZA CON `==`
/// ---------------------------
/// El mismo equipo aparece escrito de tres formas en el mismo día: la etiqueta
/// dice `ZTEG-C0A1B2C3`, el despacho cargó `zteg c0a1b2c3`, y el código de
/// barras devuelve `ZTEGC0A1B2C3`. Un `==` los declara distintos y le dice al
/// técnico que trajo el equipo equivocado — y entonces deja de usar el lector.
///
/// Se comparan solo las letras y los números, sin distinguir mayúsculas. Lo que
/// **no** se hace es comparar por coincidencia parcial: un serial que *contiene*
/// a otro no es el mismo equipo, y aflojar eso convierte la verificación en algo
/// que siempre dice que sí.
bool mismoSerial(String a, String b) {
  final String na = _soloAlfanumerico(a);
  final String nb = _soloAlfanumerico(b);
  if (na.isEmpty || nb.isEmpty) return false;
  return na == nb;
}

String _soloAlfanumerico(String s) =>
    s.replaceAll(RegExp(r'[^A-Za-z0-9]'), '').toUpperCase();
