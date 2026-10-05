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
    this.horasDelDia = const <HoraDelDia>[],
    this.consumidoSinEntrega,
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

  /// Las horas comprometidas del día, en orden, con lo que hace falta para
  /// leerlas de un vistazo.
  ///
  /// POR QUE ESTO ES LO PRIMERO QUE MIRA EL TECNICO
  /// -----------------------------------------------
  /// «3 ASIGNADAS» no dice si la primera es a las 8 o a las 2. Parado a las
  /// siete de la mañana, lo que decide el día es el ORDEN y las HORAS, y eso
  /// había que deducirlo abriendo las tres fichas.
  ///
  /// Vacía cuando ninguna orden trae hora —el caso real del laboratorio— y
  /// entonces la pantalla no dibuja la línea. Una fila de guiones ocuparía el
  /// lugar donde el técnico mira cuando SÍ hay horas.
  final List<HoraDelDia> horasDelDia;

  /// Cuánto material consumió de más respecto de lo que le entregaron.
  ///
  /// `null` cuando el saldo es posible. Cuando no lo es, trae el faltante en
  /// positivo —38.5, no -38.5— porque lo que hay que decir es «consumiste 38,5
  /// que no figuran entregados», no un saldo negativo.
  ///
  /// NO EXISTE TENER MENOS DE CERO EN LA MANO. La pantalla rotulaba
  /// `aDevolver` como «EN MANO», y con los consumos sin entrega eso daba
  /// «EN MANO -38.5»: una resta presentada como si fuera un saldo, con cara de
  /// dato preciso. Medido el 05/10/2026 sobre el técnico del laboratorio: dos
  /// consumos y cero entregas registradas.
  final String? consumidoSinEntrega;

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
      horasDelDia: _horasDe(trabajos, momento),
      consumidoSinEntrega: _consumidoSinEntrega(jornada?.aDevolver),
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

/// Una de las horas comprometidas del día.
///
/// Lleva el estado ya decidido —hecha, vencida, o por hacer— porque quién
/// decide eso es esta capa y no el widget: una segunda cuenta en la pantalla es
/// la forma más rápida de que dos partes de la misma app digan cosas distintas
/// del mismo día.
class HoraDelDia {
  const HoraDelDia({
    required this.ordenId,
    required this.hora,
    required this.hecha,
    required this.vencida,
  });

  final String ordenId;

  /// `08:30`, en el huso del teléfono. El servidor manda UTC.
  final String hora;

  final bool hecha;

  /// Pasó la hora y el trabajo sigue abierto. Nunca es `true` si [hecha] lo es:
  /// un trabajo terminado tarde ya no es un problema que mirar a las siete de
  /// la mañana.
  final bool vencida;
}

/// Las horas del día, en orden, solo de los trabajos que traen una.
///
/// Se usa la ventana prometida al cliente si existe, y si no el compromiso.
/// Son dos cosas distintas y la primera gana: al abonado se le dijo «entre 8 y
/// 10», y esa es la hora que él está esperando en la puerta.
List<HoraDelDia> _horasDe(List<TrabajoVista> trabajos, DateTime ahora) {
  final List<(DateTime, HoraDelDia)> conHora = <(DateTime, HoraDelDia)>[];
  for (final TrabajoVista t in trabajos) {
    final DateTime? cuando = t.ventanaInicio ?? t.compromiso;
    if (cuando == null) continue;
    final bool hecha = ResumenDeInicio._estaTerminado(t);
    conHora.add((
      cuando,
      HoraDelDia(
        ordenId: t.id,
        hora: _hhmm(cuando.toLocal()),
        hecha: hecha,
        vencida: !hecha && cuando.isBefore(ahora),
      ),
    ));
  }
  conHora.sort(((DateTime, HoraDelDia) a, (DateTime, HoraDelDia) b) =>
      a.$1.compareTo(b.$1));
  return <HoraDelDia>[for (final (DateTime, HoraDelDia) h in conHora) h.$2];
}

String _hhmm(DateTime f) =>
    '${f.hour.toString().padLeft(2, '0')}:${f.minute.toString().padLeft(2, '0')}';

/// Cuánto se consumió sin que figure una entrega, o `null` si el saldo cierra.
///
/// `aDevolver` lo calcula el dominio como `recibido − consumido`, y cuando da
/// negativo no es un saldo: es la señal de que se consumió material que bodega
/// nunca registró. Devolverlo en positivo es lo que permite decirlo en palabras
/// en vez de mostrar un «-38.5» con cara de medición.
String? _consumidoSinEntrega(String? aDevolver) {
  final double? saldo = double.tryParse((aDevolver ?? '').trim());
  if (saldo == null || saldo >= 0) return null;
  final double faltante = -saldo;
  // Sin ceros de relleno: `38.5`, no `38.500`. Mismo criterio que el historial
  // del servicio, y por el mismo motivo —en Colombia el punto separa miles—.
  final String texto = faltante.toStringAsFixed(3);
  return texto.contains('.')
      ? texto.replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '')
      : texto;
}
