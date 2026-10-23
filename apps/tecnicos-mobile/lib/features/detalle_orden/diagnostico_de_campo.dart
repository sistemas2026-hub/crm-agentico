import 'acciones_orden.dart';

/// QUÉ DICE LO MEDIDO, EN UNA FRASE.
///
/// Junta lo que ya está en la pantalla —el ping, la potencia óptica y el
/// estado de la ONU— y dice qué tramo conviene mirar. No agrega ningún dato:
/// solo combina los que hay.
///
/// POR QUÉ EN CÓDIGO Y NO CON EL MODELO
/// ------------------------------------
/// Las reglas ya estaban decididas antes de escribir esto: el rango óptico lo
/// fija G-GO-04 y el resto sale de la guía de diagnóstico del proveedor. El
/// modelo no aportaría criterio, solo redacción — y a cambio cobraría unos
/// segundos, una conexión que en campo falta la mitad del tiempo, y el riesgo
/// de inventar una causa.
///
/// Ese riesgo está medido en este proyecto: **el ping no es un veredicto**. El
/// mismo equipo sano devuelve `1 de 3`, `2 de 3` y `3 de 3` en corridas
/// seguidas (15/08/2026), y un reinicio real y confirmado dejó el ping igual
/// antes y después (02/09/2026). Un modelo mirando «8 de 10» va a querer
/// explicar los dos que faltaron.
///
/// LO QUE ESTO NO HACE
/// -------------------
/// No dictamina y no cierra el caso. Dice **qué tramo mirar primero**, que es
/// una decisión de orden de trabajo, no una afirmación sobre la falla. Y nunca
/// habla de lo que no midió: si no hubo ping, no opina del enlace.
class DiagnosticoDeCampo {
  const DiagnosticoDeCampo({
    required this.texto,
    required this.malo,
  });

  final String texto;

  /// Si conviene pintarlo como problema. No es "hay falla": es "esto no está
  /// como debería y vale mirarlo".
  final bool malo;

  /// Ninguna lectura alcanza para decir nada.
  static const DiagnosticoDeCampo ninguno =
      DiagnosticoDeCampo(texto: '', malo: false);

  bool get hayAlgoQueDecir => texto.isNotEmpty;

  /// [veredicto] es el del motor sobre la potencia de bajada
  /// (`onu_signal_1490_veredicto`), no se recalcula acá.
  /// [estadoOnu] es lo que la OLT ve (`Online` / `Offline`).
  /// [ping] es null mientras nadie lo haya pedido.
  static DiagnosticoDeCampo de({
    required String veredicto,
    required String estadoOnu,
    ResultadoPing? ping,
  }) {
    final bool enLinea = estadoOnu.toLowerCase() == 'online';
    final bool sabeEstado = estadoOnu.isNotEmpty;
    final bool senalMala = veredicto.isNotEmpty && veredicto != 'aceptable';
    final bool sabeSenal = veredicto.isNotEmpty;

    final int volvieron =
        ping == null ? 0 : ping.paquetes.where((PaqueteDePing p) => p.respondio).length;
    final int mandados = ping?.paquetes.length ?? 0;
    final bool hayPing = ping != null && ping.medido && mandados > 0;

    // 1 · LA OLT NO LO VE. Manda sobre todo lo demás: sin enlace óptico no
    //     hay nada que discutir del router.
    if (sabeEstado && !enLinea) {
      return const DiagnosticoDeCampo(
        texto: 'La OLT no ve el equipo. Revisar energía en el domicilio y el '
            'tramo de fibra desde la caja NAP.',
        malo: true,
      );
    }

    // 2 · SIN PING NO SE OPINA DEL ENLACE. Solo de la señal, que es lo único
    //     medido hasta acá.
    if (!hayPing) {
      if (senalMala) {
        return const DiagnosticoDeCampo(
          texto: 'La señal está fuera de rango. Medir en la caja NAP para '
              'separar el tramo de acometida del troncal.',
          malo: true,
        );
      }
      return ninguno;
    }

    // 3 · NO CONTESTÓ NINGUNO, PERO LA OLT SÍ LO VE. El tramo óptico llega;
    //     lo que no responde es el equipo o su configuración.
    if (volvieron == 0) {
      return DiagnosticoDeCampo(
        texto: sabeEstado && enLinea
            ? 'La OLT ve el equipo pero no contesta ningún paquete. Mirar el '
                'router del cliente y su configuración antes que el tramo '
                'óptico.'
            : 'No contestó ningún paquete.',
        malo: true,
      );
    }

    // 4 · CONTESTÓ TODO. Con la señal en rango, el tramo óptico hasta la caja
    //     NAP queda descartado — y eso es lo más útil que puede decir esta
    //     medición.
    if (volvieron == mandados) {
      if (senalMala) {
        return const DiagnosticoDeCampo(
          texto: 'Responde completo, pero la señal está fuera de rango: va a '
              'volver a fallar. Medir en la caja NAP.',
          malo: true,
        );
      }
      return DiagnosticoDeCampo(
        texto: sabeSenal
            ? 'Responde completo y la señal está en rango. Si el cliente sigue '
                'sin servicio, la falla está de la caja NAP hacia el equipo, '
                'no en el tramo óptico.'
            : 'Responde completo.',
        malo: false,
      );
    }

    // 5 · CONTESTÓ A MEDIAS. Se dice lo que se vio, sin nombrar una causa: con
    //     diez muestras la pérdida es real, pero cuál tramo la produce no lo
    //     dice el ping.
    return DiagnosticoDeCampo(
      texto: 'Contestó $volvieron de $mandados: el enlace pierde paquetes. '
          '${senalMala ? 'Con la señal fuera de rango, empezar por la caja NAP.' : 'Con la señal en rango, revisar conectores y empalmes desde la caja NAP.'}',
      malo: true,
    );
  }
}
