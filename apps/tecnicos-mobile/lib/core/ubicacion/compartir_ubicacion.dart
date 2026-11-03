import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

/// COMPARTIR LA UBICACIÓN CON LA OFICINA (31/10/2026).
///
/// El usuario: «un mapa donde uno pueda ver la posición actual de cada
/// técnico, con el fin de hacerle seguimiento».
///
/// LA ENCIENDE EL ARRANQUE DE LA JORNADA (02/11/2026)
/// --------------------------------------------------
/// El usuario, en dos pasos. Primero: «es mejor que el técnico no tenga que
/// estar presionando un botón... que al instalar la app pida el permiso y
/// ya». Después: «en la pantalla de inicio colocá un botón para iniciar la
/// jornada y así se empieza a tomar la ubicación automática».
///
/// Lo segundo es mejor que lo primero y resuelve lo mismo. Un botón que hay
/// que prender *para compartir ubicación* se siente vigilancia y nadie lo
/// toca; **«Iniciar jornada» es algo que el técnico quiere tocar**, porque es
/// el arranque de su día. Y encima deja la ubicación atada a un hecho real:
/// se comparte los días que él trabajó, no todos.
///
/// POR ESO LA MARCA ES UN DÍA, NO UN BOOLEANO. Se guarda la FECHA en que
/// arrancó. Mañana esa fecha ya no es hoy, y la ubicación no sale hasta que
/// vuelva a arrancar. No hay que apagar nada: se apaga sola a medianoche.
///
/// EL CONSENTIMIENTO SIGUE SIENDO SUYO, dos veces: Android le pide el permiso
/// --sin un «permitir» no se lee ni una coordenada-- y él decide cuándo
/// empieza su día.
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
    required this.leerDiaIniciado,
    required this.guardarDiaIniciado,
    String Function()? hoyTexto,

    this.cada = const Duration(minutes: 3),
    this.plazoDeLectura = const Duration(seconds: 20),
  }) : hoyTexto = hoyTexto ?? _hoyDelSistema;

  static String _hoyDelSistema() {
    final DateTime d = DateTime.now();
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  /// Manda la posición. Devuelve `false` si el servidor la rechazó por estar
  /// fuera de la jornada o del horario: entonces se deja de insistir hasta la
  /// próxima vez que el técnico abra la aplicación.
  final Future<bool> Function(Position posicion, int? bateria) enviar;

  /// El día (AAAA-MM-DD) en que el técnico arrancó su jornada, o null.
  /// Sobrevive a cerrar la aplicación; a medianoche deja de ser hoy solo.
  final Future<String?> Function() leerDiaIniciado;
  final Future<void> Function(String) guardarDiaIniciado;

  /// Hoy, en texto AAAA-MM-DD. Inyectable para poder probar el cambio de día
  /// sin esperar a medianoche.
  final String Function() hoyTexto;

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

  /// Si el técnico ya arrancó su jornada HOY.
  bool _jornadaDeHoy = false;
  bool get jornadaIniciada => _jornadaDeHoy;

  /// Al abrir la aplicación: retoma solo si la jornada arrancada es la de HOY.
  ///
  /// NO pide el permiso acá: el diálogo del sistema aparece cuando el técnico
  /// toca «Iniciar jornada», que es cuando tiene sentido explicárselo. Abrir
  /// la aplicación no es decir que empezó a trabajar.
  Future<void> alArrancar() async {
    _jornadaDeHoy = await leerDiaIniciado() == hoyTexto();
    if (!_jornadaDeHoy) {
      estado.value = EstadoDeUbicacion.apagado;
      return;
    }
    await encender(pedirPermiso: false);
  }

  /// ARRANCA LA JORNADA: pide el permiso, lo deja escrito para hoy y empieza
  /// a compartir. Es lo que hace el botón de Inicio.
  Future<bool> iniciarJornada() async {
    final bool pudo = await encender();
    if (pudo) {
      _jornadaDeHoy = true;
      await guardarDiaIniciado(hoyTexto());
    }
    return pudo;
  }

  /// La prende: la primera vez pide el permiso del sistema si falta.
  Future<bool> encender({bool pedirPermiso = true}) async {
    if (!await _hayPermiso(pedir: pedirPermiso)) {
      estado.value = EstadoDeUbicacion.sinPermiso;
      return false;
    }
    _encendido = true;
    estado.value = EstadoDeUbicacion.compartiendo;
    _reloj?.cancel();
    _reloj = Timer.periodic(cada, (_) => _mandarUna());
    await _mandarUna();
    return true;
  }

  /// Para de compartir. NO borra el día arrancado: la jornada sigue siendo
  /// la de hoy, y si el motivo fue el horario, al reabrir la aplicación
  /// dentro de la ventana vuelve sola. A medianoche se apaga sin que nadie
  /// haga nada: el día guardado deja de ser hoy.
  Future<void> apagar() async {
    _encendido = false;
    _reloj?.cancel();
    _reloj = null;
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
        //  horario): se para por hoy, pero NO se recuerda apagada --mañana
        //  dentro del horario sí corresponde, y el técnico no tiene por qué
        //  volver a prenderla.
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

  /// Si se le PIDIÓ el permiso al sistema en la última vuelta. Importa por sí
  /// solo: abrir la aplicación no puede tirarle un diálogo en la cara a quien
  /// todavía no dijo que empezó a trabajar.
  @visibleForTesting
  bool? sePidioElPermiso;

  Future<bool> _hayPermiso({required bool pedir}) async {
    sePidioElPermiso = pedir;
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
