import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

/// COMPARTIR LA UBICACIÓN CON LA OFICINA (31/10/2026).
///
/// El usuario: «un mapa donde uno pueda ver la posición actual de cada
/// técnico, con el fin de hacerle seguimiento».
///
/// COMPARTE SOLA, Y ESA ES LA DECISIÓN (02/11/2026)
/// ------------------------------------------------
/// El usuario: «es mejor que el técnico no tenga que estar presionando un
/// botón; solo estará enterado de que la aplicación comparte la ubicación, y
/// al momento de instalar la app que pida el permiso y ya».
///
/// Tiene razón en lo que importa: un técnico que tiene que acordarse de
/// prender algo cada mañana, no lo prende, y entonces el mapa miente por
/// omisión. Así que **nace encendida**: al abrir la aplicación pide el
/// permiso del sistema y empieza.
///
/// EL CONSENTIMIENTO NO DESAPARECE, CAMBIA DE LUGAR. Android obliga a mostrar
/// el diálogo de permiso, y sin un «permitir» del técnico no se lee ni una
/// coordenada. Lo que se fue es tener que repetirlo cada día.
///
/// Y SIGUE PUDIENDO APAGARLA. El interruptor queda, encendido por omisión:
/// una aplicación de trabajo que comparte dónde está alguien y no le deja
/// pararlo es otra cosa. Apagarla se recuerda --no se vuelve a encender sola
/// al día siguiente-- hasta que él la prenda.
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
    required this.leerApagada,
    required this.guardarApagada,
    this.cada = const Duration(minutes: 3),
    this.plazoDeLectura = const Duration(seconds: 20),
  });

  /// Manda la posición. Devuelve `false` si el servidor la rechazó por estar
  /// fuera de la jornada o del horario: entonces se deja de insistir hasta la
  /// próxima vez que el técnico abra la aplicación.
  final Future<bool> Function(Position posicion, int? bateria) enviar;

  /// Si el técnico la APAGÓ a mano (sobrevive a cerrar la aplicación).
  ///
  /// Se guarda el apagado y no el encendido, a propósito: lo normal es
  /// compartir, así que lo que hay que recordar es la excepción. Un teléfono
  /// recién instalado no tiene nada guardado y comparte, que es lo que se
  /// decidió.
  final Future<bool> Function() leerApagada;
  final Future<void> Function(bool) guardarApagada;

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

  /// Al abrir la aplicación: comparte, salvo que el técnico la haya apagado.
  ///
  /// PIDE EL PERMISO ACÁ. Es el «al momento de instalar la app que pida el
  /// permiso»: la primera vez que se abre. Si el técnico lo niega, Android
  /// deja de preguntar solo, y la tarjeta se lo dice.
  Future<void> alArrancar() async {
    if (await leerApagada()) {
      estado.value = EstadoDeUbicacion.apagado;
      return;
    }
    await encender();
  }

  /// La prende: la primera vez pide el permiso del sistema si falta.
  Future<bool> encender({bool pedirPermiso = true}) async {
    if (!await _hayPermiso(pedir: pedirPermiso)) {
      estado.value = EstadoDeUbicacion.sinPermiso;
      return false;
    }
    _encendido = true;
    await guardarApagada(false);
    estado.value = EstadoDeUbicacion.compartiendo;
    _reloj?.cancel();
    _reloj = Timer.periodic(cada, (_) => _mandarUna());
    await _mandarUna();
    return true;
  }

  /// La apaga el técnico, o el servidor al decir que no corresponde.
  ///
  /// `recordarlo` distingue las dos: lo que el técnico apaga se recuerda y no
  /// vuelve solo; lo que para el servidor --fuera de jornada u horario-- NO
  /// se recuerda, porque mañana a las siete sí corresponde y nadie tendría
  /// que volver a prenderla a mano.
  Future<void> apagar({bool recordarlo = true}) async {
    _encendido = false;
    _reloj?.cancel();
    _reloj = null;
    if (recordarlo) await guardarApagada(true);
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
        await apagar(recordarlo: false);
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
