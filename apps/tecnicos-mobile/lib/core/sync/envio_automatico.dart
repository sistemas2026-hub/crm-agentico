import 'dart:async';

/// EL ENVÍO AUTOMÁTICO (30/10/2026).
///
/// El usuario: «¿no debería ser mejor que si no tiene internet y hace un
/// cambio, apenas la app tenga conexión envíe los datos automático?». Hasta
/// hoy la app oía el cambio de red solo para pintar «CON RED»: lo pendiente
/// salía con la siguiente acción del técnico o con «Enviar ahora». Se vio con
/// una OT real: quedó con «5 cambios locales» hasta que alguien tocara algo.
///
/// Tres momentos, y la cola no deja correr dos envíos a la vez:
///
///   1. Vuelve la red: se envía [espera] después. Una red que parpadea no
///      dispara un envío por parpadeo: el último cambio reinicia la espera.
///   2. El técnico vuelve a la app (estaba en WhatsApp): lo mismo.
///   3. Con la app abierta y algo pendiente, cada [cada]: cubre la red que
///      dice que hay señal y no llega, y el servidor que rechazó un rato. Sin
///      pendientes no hace nada: no gasta datos ni batería.
///
/// Con la app CERRADA no envía: eso pide un proceso de fondo del sistema, que
/// es otro trabajo. Al abrirla, la primera pantalla ya sincroniza.
class EnvioAutomatico {
  EnvioAutomatico({
    required this.enviar,
    required this.hayPendientes,
    this.espera = const Duration(seconds: 3),
    this.cada = const Duration(minutes: 2),
  });

  /// La cola: envía lo pendiente y baja lo nuevo.
  final Future<void> Function() enviar;

  /// Si hay algo sin enviar, según el último resumen de la cola.
  final bool Function() hayPendientes;

  final Duration espera;
  final Duration cada;

  bool? _hayRed;
  Timer? _enEspera;
  Timer? _reloj;

  /// Arranca el reintento periódico. Una sola vez: llamarlo de nuevo no suma
  /// otro reloj.
  void arrancar() {
    _reloj ??= Timer.periodic(cada, (_) {
      if (_hayRed != false && hayPendientes()) _disparar();
    });
  }

  /// Lo que dice el teléfono de su red. Solo el paso de SIN red a CON red
  /// dispara: el primer dato al abrir no es una vuelta, y para eso ya
  /// sincroniza la primera pantalla.
  void alCambiarLaRed(bool hayRed) {
    final bool volvio = hayRed && _hayRed == false;
    _hayRed = hayRed;
    if (volvio) {
      _programar();
    } else if (!hayRed) {
      _enEspera?.cancel();
      _enEspera = null;
    }
  }

  /// El técnico volvió a la app. Sin red, no se intenta: se enviará cuando
  /// vuelva.
  void alVolverALaApp() {
    if (_hayRed != false) _programar();
  }

  void parar() {
    _enEspera?.cancel();
    _reloj?.cancel();
    _enEspera = null;
    _reloj = null;
  }

  void _programar() {
    _enEspera?.cancel();
    _enEspera = Timer(espera, () {
      _enEspera = null;
      _disparar();
    });
  }

  void _disparar() {
    //  Un envío que falla no puede tumbar nada: la cola anota su propio
    //  error, y el próximo momento lo vuelve a intentar.
    unawaited(enviar().catchError((Object _) {}));
  }
}
