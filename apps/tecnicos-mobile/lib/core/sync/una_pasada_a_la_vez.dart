import 'dart:async';

/// Deja correr UNA pasada por vez, y no pierde lo que llegó mientras tanto.
///
/// EL DEFECTO QUE ESTO CIERRA  --  06/11/2026, reportado por el usuario:
/// «los cambios de la app no salen enseguida apenas se reporta».
///
/// La sincronización ya se disparaba al guardar: cada pantalla llama a
/// `procesarCola()` apenas encola. Lo que faltaba era qué pasa si JUSTO hay
/// una pasada corriendo. La guarda era así:
///
///     if (_isSyncing) return;
///
/// — y ese `return` tiraba el disparo en silencio. Una pasada no es corta:
/// sube mutaciones, evidencias, movimientos, novedades, seguimiento y cierre,
/// y después baja órdenes, kit y jornada. La ventana para perderse un disparo
/// es de segundos a decenas de segundos, justo cuando el técnico está
/// escribiendo. Perdido el disparo, lo recién guardado esperaba al reloj de
/// `EnvioAutomatico`: hasta DOS MINUTOS mirando «pendiente» sin que nada se
/// mueva.
///
/// Y no alcanza con esperar a que la pasada en curso lo levante: esa pasada
/// pudo haber LEÍDO la cola antes de que esa fila existiera.
///
/// Vive en su propio archivo para que esta decisión se pueda probar sin
/// levantar la base, la sesión ni la red — que es lo que hace que la guarda
/// sirva de guarda.
class UnaPasadaALaVez {
  bool _corriendo = false;
  bool _pedidaDeNuevo = false;

  /// Si hay una pasada en curso ahora mismo.
  bool get corriendo => _corriendo;

  /// Si quedó un pedido anotado para cuando termine la actual.
  bool get hayPedidoPendiente => _pedidaDeNuevo;

  /// Corre [pasada], o la anota para después si ya hay una corriendo.
  ///
  /// Al terminar, si durante la pasada llegó al menos un pedido, se corre UNA
  /// vez más. Una, no una por pedido: diez guardados seguidos durante la
  /// misma pasada necesitan una sola vuelta extra — la que lee la cola ya
  /// completa —, y encadenar diez dejaría al teléfono subiendo para siempre.
  ///
  /// Un fallo de la pasada NO se traga: sube a quien llamó, igual que antes.
  /// Pero la vuelta pendiente se corre lo mismo, porque lo que se guardó
  /// mientras tanto no tiene la culpa de que esta pasada fallara.
  Future<void> correr(Future<void> Function() pasada) async {
    if (_corriendo) {
      _pedidaDeNuevo = true;
      return;
    }
    _corriendo = true;
    try {
      await pasada();
    } finally {
      _corriendo = false;
      //  La marca se baja ANTES de volver a entrar: lo que se guarde durante
      //  la vuelta extra tiene que poder pedir la siguiente, en vez de que
      //  este mismo disparo se consuma dos veces.
      if (_pedidaDeNuevo) {
        _pedidaDeNuevo = false;
        unawaited(correr(pasada));
      }
    }
  }
}
