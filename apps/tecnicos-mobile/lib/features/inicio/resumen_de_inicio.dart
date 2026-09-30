/// Las tres preguntas que se hace alguien al abrir la aplicación.
///
/// POR QUÉ ESTO ES LÓGICA PURA
/// ---------------------------
/// Porque decidir **cuál es el próximo trabajo** es una regla de operación, no
/// una decisión de dibujo, y equivocarse manda a una persona a la otra punta
/// de la ciudad. Acá se puede probar sin base, sin red y sin emulador.
///
/// LAS TRES PREGUNTAS, EN ESTE ORDEN
/// ---------------------------------
/// 1. ¿Qué tengo hoy?     → cuántos trabajos, cuántos cerrados, qué llevo.
/// 2. ¿Qué hago ahora?    → uno solo, el siguiente.
/// 3. ¿Tengo problemas?   → lo que se rompió y alguien tiene que mirar.
///
/// El orden importa. Una pantalla de inicio que empieza por los problemas
/// hace que el día arranque en rojo aunque no haya ninguno; una que no los
/// muestra deja que un descuadre o una cola trabada pasen desapercibidos toda
/// la jornada.
///
/// LO QUE NO SE INVENTA
/// --------------------
/// Si no hay dato, no hay línea. Un "próximo trabajo" elegido al azar, una
/// hora estimada de llegada calculada a ojo o un kit supuesto son peores que
/// un espacio vacío: el técnico los usa para decidir a dónde va.
library;

import '../materiales/estado_de_jornada.dart';
import '../trabajo/estado_trabajo.dart';
import '../trabajo/trabajo_vista.dart';

/// Algo que alguien tiene que mirar.
class AvisoDeInicio {
  const AvisoDeInicio({
    required this.titulo,
    required this.detalle,
    required this.gravedad,
  });

  final String titulo;
  final String detalle;

  /// `alta` pide acción hoy; `media` se puede resolver al cerrar la jornada.
  final GravedadDeAviso gravedad;
}

enum GravedadDeAviso {
  /// Bloquea o puede perder trabajo: se ve primero.
  alta,

  /// Hay que resolverlo antes de cerrar, pero no ahora mismo.
  media,
}

/// Lo que muestra la pantalla de inicio, ya decidido.
class ResumenDeInicio {
  const ResumenDeInicio({
    required this.totalDeTrabajos,
    required this.completados,
    required this.siguiente,
    required this.avisos,
    required this.kitRecibido,
    required this.kitDisponible,
    required this.kitConsumido,
    required this.hayKit,
    required this.jornadaCerrada,
  });

  /// Los trabajos de la jornada.
  final int totalDeTrabajos;
  final int completados;

  int get pendientes => totalDeTrabajos - completados;

  /// El próximo trabajo. Nulo cuando no queda ninguno, y eso se dice.
  final TrabajoVista? siguiente;

  final List<AvisoDeInicio> avisos;

  /// Lo que lleva encima, si hay kit cargado.
  final String kitRecibido;
  final String kitDisponible;
  final String kitConsumido;
  final bool hayKit;

  final bool jornadaCerrada;

  bool get hayProblemas => avisos.isNotEmpty;
  bool get terminoLaJornada => totalDeTrabajos > 0 && pendientes == 0;

  /// Arma el resumen con lo que ya está en el teléfono.
  ///
  /// [ahora] entra por parámetro para que las pruebas no dependan del reloj:
  /// un trabajo "vencido" depende de qué hora es, y una prueba que dependa de
  /// la hora real falla sola a las cinco de la tarde.
  static ResumenDeInicio armar({
    required List<TrabajoVista> trabajos,
    EstadoDeJornada? jornada,
    int movimientosSinSubir = 0,
    int evidenciasSinSubir = 0,
    int mutacionesEnConflicto = 0,
    DateTime? ahora,
  }) {
    final momento = ahora ?? DateTime.now();

    // `completadaSinEnviar` cuenta como hecho: el trabajo se termino, lo que
    // falta es que suba. Dejarlo como pendiente le diria al tecnico que
    // todavia tiene que ir, y ya fue.
    final completados = trabajos.where(_estaTerminado).length;

    final avisos = <AvisoDeInicio>[];

    // 1. Lo que puede perderse: trabajo hecho que no salió del teléfono.
    final sinSubir = movimientosSinSubir + evidenciasSinSubir;
    if (sinSubir > 0) {
      avisos.add(AvisoDeInicio(
        titulo: sinSubir == 1
            ? '1 registro sin enviar'
            : '$sinSubir registros sin enviar',
        detalle: 'Suben solos cuando haya señal. No hace falta esperar acá.',
        // Media y no alta: no se pierde nada, sube solo. Marcarlo en rojo
        // enseñaría a ignorar los rojos.
        gravedad: GravedadDeAviso.media,
      ));
    }

    // 2. Lo que ya se rompió y nadie va a resolver solo.
    if (mutacionesEnConflicto > 0) {
      avisos.add(AvisoDeInicio(
        titulo: mutacionesEnConflicto == 1
            ? '1 cambio rechazado'
            : '$mutacionesEnConflicto cambios rechazados',
        detalle: 'El servidor no los aceptó. Hay que revisarlos.',
        gravedad: GravedadDeAviso.alta,
      ));
    }

    // 3. Lo que impide cerrar la jornada, dicho por el servidor.
    if (jornada != null && jornada.hayJornada && !jornada.cerrada) {
      // El disparador son los MOTIVOS, no el contador de diferencias.
      //
      // `diferencias` cuenta materiales cuyo devuelto todavía no llega a lo
      // esperado, y eso es cierto desde que arranca el día: a las siete de la
      // mañana falta devolver el kit entero. Avisarlo como "no cuadra" pone
      // un rojo permanente en la pantalla de inicio, y un rojo que está todos
      // los días deja de leerse — que es exactamente lo que esta clase trata
      // de evitar en todos los demás avisos.
      //
      // Lo que sí es un problema es que el servidor lo declare al evaluar el
      // cierre. Eso llega en `motivos`, escrito por quien hizo la cuenta.
      if (jornada.motivos.isNotEmpty && jornada.diferencias > 0) {
        avisos.add(AvisoDeInicio(
          titulo: jornada.diferencias == 1
              ? '1 material no cuadra'
              : '${jornada.diferencias} materiales no cuadran',
          detalle: 'Hay que explicar qué pasó antes de cerrar la jornada.',
          gravedad: GravedadDeAviso.alta,
        ));
      }
      // Los motivos del servidor se muestran tal cual: los escribió quien
      // sabe por qué no cuadra, y reescribirlos acá sería adivinar.
      for (final motivo in jornada.motivos) {
        if (motivo.toLowerCase().contains('serie')) {
          avisos.add(AvisoDeInicio(
            titulo: 'Un equipo sin ubicar',
            detalle: motivo,
            gravedad: GravedadDeAviso.alta,
          ));
        }
      }
    }

    return ResumenDeInicio(
      totalDeTrabajos: trabajos.length,
      completados: completados,
      siguiente: _elegirSiguiente(trabajos, momento),
      // Lo grave primero. Dentro de cada grupo se respeta el orden en que se
      // agregó, que va de lo que se pierde a lo que se explica.
      avisos: <AvisoDeInicio>[
        ...avisos.where((a) => a.gravedad == GravedadDeAviso.alta),
        ...avisos.where((a) => a.gravedad == GravedadDeAviso.media),
      ],
      kitRecibido: jornada?.recibido ?? '0',
      kitDisponible: jornada?.aDevolver ?? '0',
      kitConsumido: jornada?.consumido ?? '0',
      hayKit: jornada?.hayJornada ?? false,
      jornadaCerrada: jornada?.cerrada ?? false,
    );
  }

  /// Un trabajo que ya no hay que ir a hacer.
  ///
  /// La correccion requerida NO entra: el supervisor la devolvio y hay que
  /// rehacer algo, asi que sigue siendo trabajo del dia.
  static bool _estaTerminado(TrabajoVista t) =>
      t.estado == EstadoTrabajo.completadaCampo ||
      t.estado == EstadoTrabajo.completadaSinEnviar ||
      t.estado == EstadoTrabajo.cerrada ||
      t.estado == EstadoTrabajo.cancelada;

  /// Cuál es el próximo trabajo.
  ///
  /// EL CRITERIO, Y POR QUÉ ÉSTE
  /// ---------------------------
  /// Primero el que ya se empezó: dejar un trabajo a medias para ir a otro es
  /// lo que hace que ninguno de los dos cierre. Después lo vencido, después lo
  /// que vence antes, y recién al final la prioridad que puso la oficina.
  ///
  /// El compromiso con el cliente le gana a la etiqueta de prioridad porque es
  /// una hora prometida a una persona que está esperando; la prioridad es una
  /// intención de la oficina, y se puso antes de saber cómo iba a ir el día.
  ///
  /// Sin ninguna señal —ni empezado, ni vencimiento, ni prioridad— se devuelve
  /// el primero de la lista tal como vino del servidor, que ya llega ordenado.
  /// No se inventa un criterio propio para desempatar.
  static TrabajoVista? _elegirSiguiente(
    List<TrabajoVista> trabajos,
    DateTime ahora,
  ) {
    final abiertos = trabajos.where((t) => !_estaTerminado(t)).toList();
    if (abiertos.isEmpty) return null;

    final empezado =
        abiertos.where((t) => t.estado == EstadoTrabajo.enSitio).toList();
    if (empezado.isNotEmpty) return empezado.first;

    final enCamino =
        abiertos.where((t) => t.estado == EstadoTrabajo.enCamino).toList();
    if (enCamino.isNotEmpty) return enCamino.first;

    final conVencimiento = abiertos
        .where((t) => t.minutosParaVencer(ahora: ahora) != null)
        .toList()
      ..sort((a, b) => a
          .minutosParaVencer(ahora: ahora)!
          .compareTo(b.minutosParaVencer(ahora: ahora)!));
    if (conVencimiento.isNotEmpty) return conVencimiento.first;

    const orden = <String, int>{'alta': 0, 'media': 1, 'baja': 2};
    final porPrioridad = abiertos.where((t) => t.prioridad.isNotEmpty).toList()
      ..sort((a, b) => (orden[a.prioridad] ?? 9).compareTo(orden[b.prioridad] ?? 9));
    if (porPrioridad.isNotEmpty) return porPrioridad.first;

    return abiertos.first;
  }
}
