import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

/// COMPARTIR LA UBICACIÓN CON LA OFICINA (31/10/2026).
///
/// El usuario: «un mapa donde uno pueda ver la posición actual de cada
/// técnico, con el fin de hacerle seguimiento».
///
/// SE ENCIENDE A MANO, Y ESA ES LA DECISIÓN
/// ----------------------------------------
/// Nace apagado. El técnico lo prende, ve el permiso del sistema con su
/// explicación, y puede apagarlo cuando quiera. No hay interruptor del
/// servidor que lo encienda por él.
///
/// Eso resuelve dos cosas de una: el piloto con un solo técnico no necesita
/// nada especial —los demás simplemente no lo prenden— y el consentimiento es
/// un acto de la persona, no una casilla en una pantalla de oficina.
///
/// LO QUE NO SE HACE, Y POR QUÉ
/// ----------------------------
/// **No se encola lo que no se pudo enviar.** En todo el sistema se guarda
/// UNA posición por persona, la última: una coordenada de hace veinte minutos
/// que llega ahora no dice dónde está el técnico, dice dónde estuvo, y
/// pisaría a la buena. Sin señal se saltea y se manda la próxima. Es al revés
/// que la cola de reportes (`envio_automatico.dart`), donde cada cambio
/// importa y ninguno se puede perder.
///
/// **No se manda con la aplicación cerrada.** Eso pide un servicio de fondo
/// del sistema, que es otro trabajo y otra conversación con el técnico. Hoy
/// comparte mientras la aplicación está abierta o en segundo plano reciente,
/// que es como anda un teléfono en la mano durante la jornada.
///
/// **El servidor manda sobre el horario.** Aunque esto siguiera despierto a
/// las diez de la noche, `campo/ubicacion_de_cuadrilla.py` rechaza la
/// posición fuera del horario de las cuadrillas. Acá se para igual al recibir
/// ese rechazo: no se insiste contra una puerta cerrada.
class CompartirUbicacion {
  CompartirUbicacion({
    required this.enviar,
    required this.leerEncendido,
    required this.guardarEncendido,
    this.cada = const Duration(minutes: 3),
    this.plazoDeLectura = const Duration(seconds: 20),
  });

  /// Manda la posición. Devuelve `false` si el servidor la rechazó por estar
  /// fuera de la jornada o del horario: entonces se deja de insistir hasta la
  /// próxima vez que el técnico abra la aplicación.
  final Future<bool> Function(Position posicion, int? bateria) enviar;

  /// Si el técnico lo dejó encendido (sobrevive a cerrar la aplicación).
  final Future<bool> Function() leerEncendido;
  final Future<void> Function(bool) guardarEncendido;

  final Duration cada;
  final Duration plazoDeLectura;

  Timer? _reloj;
  bool _encendido = false;
  bool _enviando = false;

  /// Lo que la pantalla muestra. Nunca una coordenada: al técnico no le sirve
  /// ver sus grados, le sirve saber si la oficina lo está viendo.
  final ValueNotifier<EstadoDeUbicacion> estado =
      ValueNotifier<EstadoDeUbicacion>(EstadoDeUbicacion.apagado);

  bool get encendido => _encendido;

  /// Al abrir la aplicación: si quedó encendido, se retoma.
  Future<void> alArrancar() async {
    if (await leerEncendido()) await encender(pedirPermiso: false);
  }

  /// Lo prende el técnico. Con [pedirPermiso] pide el del sistema si falta;
  /// al retomar no se pide, para no interrumpir con un diálogo al abrir.
  Future<bool> encender({bool pedirPermiso = true}) async {
    if (!await _hayPermiso(pedir: pedirPermiso)) {
      estado.value = EstadoDeUbicacion.sinPermiso;
      return false;
    }
    _encendido = true;
    await guardarEncendido(true);
    estado.value = EstadoDeUbicacion.compartiendo;
    _reloj?.cancel();
    _reloj = Timer.periodic(cada, (_) => _mandarUna());
    await _mandarUna();
    return true;
  }

  /// Lo apaga el técnico, o el servidor al decir que está fuera de horario.
  Future<void> apagar({bool recordarlo = true}) async {
    _encendido = false;
    _reloj?.cancel();
    _reloj = null;
    if (recordarlo) await guardarEncendido(false);
    estado.value = EstadoDeUbicacion.apagado;
  }

  /// Al cerrar la pantalla: se corta el reloj SIN olvidar la preferencia.
  void soltar() {
    _reloj?.cancel();
    _reloj = null;
    estado.dispose();
  }

  Future<void> _mandarUna() async {
    if (!_encendido || _enviando) return;
    _enviando = true;
    try {
      final Position? p = await _leerPosicion();
      if (p == null) {
        //  Sin señal NO se encola: la próxima dirá dónde está de verdad.
        estado.value = EstadoDeUbicacion.sinSenal;
        return;
      }
      final bool aceptada = await enviar(p, await _bateria());
      if (!aceptada) {
        //  El servidor dice que no corresponde (fuera de jornada o de
        //  horario): se para, y se recuerda apagado para no reintentar
        //  mañana a la madrugada.
        await apagar();
        estado.value = EstadoDeUbicacion.fueraDeJornada;
        return;
      }
      estado.value = EstadoDeUbicacion.compartiendo;
    } catch (e) {
      //  El tipo, nunca el texto: un mensaje de error puede arrastrar datos.
      debugPrint('ubicacion: no se pudo enviar (${e.runtimeType})');
      estado.value = EstadoDeUbicacion.sinSenal;
    } finally {
      _enviando = false;
    }
  }

  /// La costura para probar sin teléfono: devuelve la posición en vez de
  /// pedírsela al sistema. El permiso y el GPS son del sistema operativo y no
  /// se pueden ejercitar en una prueba; la DECISIÓN de qué hacer con lo que
  /// llega —o con que no llegue— sí, y es lo que importa.
  @visibleForTesting
  Position? Function()? posicionDePrueba;

  Future<Position?> _leerPosicion() async {
    if (posicionDePrueba != null) return posicionDePrueba!();
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return null;
      return await Geolocator.getCurrentPosition(
        locationSettings: LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: plazoDeLectura,
        ),
      );
    } catch (e) {
      debugPrint('ubicacion: no se pudo leer (${e.runtimeType})');
      return null;
    }
  }

  /// La otra costura de plataforma: el permiso lo concede el sistema y una
  /// prueba no puede concederlo. Lo que se prueba no es el diálogo, es qué
  /// hace el servicio con el sí y con el no.
  @visibleForTesting
  bool? permisoDePrueba;

  Future<bool> _hayPermiso({required bool pedir}) async {
    if (permisoDePrueba != null) return permisoDePrueba!;
    try {
      LocationPermission permiso = await Geolocator.checkPermission();
      if (permiso == LocationPermission.denied && pedir) {
        permiso = await Geolocator.requestPermission();
      }
      return permiso == LocationPermission.always ||
          permiso == LocationPermission.whileInUse;
    } catch (e) {
      debugPrint('ubicacion: no se pudo ver el permiso (${e.runtimeType})');
      return false;
    }
  }

  /// La batería, si el teléfono la dice. Que no la diga no cuesta la posición.
  Future<int?> _bateria() async => bateriaDelTelefono?.call();

  /// Lo pone quien arma la aplicación; sin esto, la batería va vacía.
  static Future<int?> Function()? bateriaDelTelefono;
}

/// Lo que la pantalla le dice al técnico. Nunca una coordenada.
enum EstadoDeUbicacion {
  apagado,
  compartiendo,
  sinSenal,
  sinPermiso,
  fueraDeJornada,
}

/// El texto de cada estado, para que la pantalla no invente el suyo.
String textoDeUbicacion(EstadoDeUbicacion e) {
  switch (e) {
    case EstadoDeUbicacion.apagado:
      return 'No estás compartiendo tu ubicación.';
    case EstadoDeUbicacion.compartiendo:
      return 'La oficina ve dónde está tu cuadrilla.';
    case EstadoDeUbicacion.sinSenal:
      return 'Sin señal de GPS por ahora. Se reintenta solo.';
    case EstadoDeUbicacion.sinPermiso:
      return 'Falta el permiso de ubicación. Activalo en los ajustes del teléfono.';
    case EstadoDeUbicacion.fueraDeJornada:
      return 'Fuera del horario de la jornada: se dejó de compartir.';
  }
}
