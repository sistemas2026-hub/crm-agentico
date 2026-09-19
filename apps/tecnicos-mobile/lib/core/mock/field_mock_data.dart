/// Catálogo de los datos que Dexter Campo **va a tener** y todavía no tiene.
///
/// El diseño de Stitch muestra información que ningún sistema entrega hoy. En
/// vez de esconder esas partes —así nadie vería a dónde va el producto— se
/// pintan con los valores de acá. Sirven para dos cosas a la vez: mostrar el
/// producto completo, y **especificar qué hay que construir después**.
///
/// Cada dato futuro tiene un identificador `CAMPO-DATA-XXX` que se busca en
/// todo el repositorio y aparece en `docs/campo_datos_pendientes.md` con su
/// fuente prevista y el desarrollo que falta.
///
/// Tres reglas que no se negocian:
///
/// 1. **Nada de acá decide.** No habilita un botón, no filtra, no ordena, no
///    cambia un estado y no dispara una alerta. Solo se muestra.
/// 2. **Nada de acá inventa trabajo.** Puede completar un campo futuro de una
///    orden que existe; jamás agrega una orden, un aviso o una tarea.
/// 3. **Fuera del modo demostración no se muestran como datos operativos.**
///    Un técnico en la calle no puede confundir un valor de ejemplo con la
///    señal real de la casa donde está parado.
class FieldMockData {
  const FieldMockData._();

  /// Modo demostración: enciende los datos futuros para poder ver el producto
  /// completo. Se activa al compilar con `--dart-define=DEXTER_DEMO=true`.
  ///
  /// Apagado —lo normal en producción— nada de este archivo llega a pantalla
  /// como información operativa. Los fixtures **no se borran**: son la
  /// especificación de lo que falta construir.
  static const bool modoDemo = bool.fromEnvironment('DEXTER_DEMO');

  /// CAMPO-DATA-010 · Notificaciones sin leer.
  /// Futuro: avisos del backend de Dexter (`notificaciones.sin_leer`).
  static const int notificacionesSinLeer = modoDemo ? 2 : 0;

  /// Nombre a mostrar mientras la sesión todavía no se leyó. No es un dato
  /// futuro: es el texto neutro de un instante, no una identidad inventada.
  static const String tecnicoPorDefecto = 'Técnico';
  static const String empresaPorDefecto = 'Dexter Campo';

  // --- La jornada ----------------------------------------------------------

  /// CAMPO-DATA-006 · Turno del técnico.
  /// Futuro: jornada/turno en el backend de Campo (`jornada.turno`).
  static const String turno = '07:30 - 17:00';

  /// CAMPO-DATA-007 · Cuadrilla y móvil asignados.
  /// Futuro: asignación de cuadrilla en el backend de Campo (`jornada.cuadrilla`).
  static const String cuadrilla = 'Cuadrilla 04 · Móvil 12';

  /// CAMPO-DATA-008 · Vehículo y su preoperacional del día.
  /// Futuro: módulo de vehículos (`vehiculo.placa`, `vehiculo.preoperacional_ok`).
  static const String vehiculoPlaca = 'ABC123';
  static const bool vehiculoPreoperacionalHecho = true;

  // --- El kit del técnico --------------------------------------------------

  /// CAMPO-DATA-009 · Resumen del kit diario.
  /// Futuro: inventario de Dexter (`kit.recibidos`, `kit.consumidos`,
  /// `kit.disponibles`). Es el mismo dato que va a alimentar la Fase 8.
  static const int kitRecibidos = 24;
  static const int kitConsumidos = 8;
  static const int kitDisponibles = 16;
  static const String kitOrigen = 'Depósito Central · Bodega 2';

  // --- La red, por trabajo -------------------------------------------------

  /// CAMPO-DATA-001 · Potencia óptica RX de la ONT.
  /// Futuro: SmartOLT a través del backend (`telemetria.rx_dbm`).
  static const double potenciaRxDbm = -18.7;

  /// CAMPO-DATA-011 · Identificadores de red del cliente.
  /// Futuro: SmartOLT/WispHub (`telemetria.cto`, `.pon`, `.serial_ont`).
  static const String cto = 'CTO-04-A';
  static const String puertoPon = 'PON 0/1/4';
  static const String serialOnt = '48575443-B981F';

  // --- Campos futuros de cada trabajo --------------------------------------
  // Se derivan del identificador de la orden para que un mismo trabajo muestre
  // siempre lo mismo: si cambiaran en cada refresco, la pantalla parecería
  // estar recibiendo datos en vivo.

  static const List<String> _zonas = <String>[
    'Norte Urbano',
    'Sur Urbano',
    'Centro',
    'Rural Oriente',
  ];

  static const List<String> _prioridades = <String>['Alta', 'Media', 'Baja'];

  /// Lo que el diseño muestra de un trabajo y ningún sistema entrega todavía.
  static TrabajoFuturoMock trabajoFuturo(String idOrden) {
    final semilla = _semilla(idOrden);
    return TrabajoFuturoMock(
      zona: _zonas[semilla % _zonas.length],
      prioridad: _prioridades[(semilla ~/ 7) % _prioridades.length],
      slaRestante: '0${1 + semilla % 5}:${((semilla % 6) * 10).toString().padLeft(2, '0')}',
      distanciaKm: (1 + semilla % 90) / 10,
      minutosDeViaje: 3 + semilla % 25,
      potenciaRxDbm: potenciaRxDbm,
    );
  }

  static int _semilla(String texto) {
    var acumulado = 7;
    for (var i = 0; i < texto.length; i++) {
      acumulado = (acumulado * 31 + texto.codeUnitAt(i)) & 0x7FFFFFFF;
    }
    return acumulado;
  }
}

/// Campos futuros de un trabajo real.
class TrabajoFuturoMock {
  const TrabajoFuturoMock({
    required this.zona,
    required this.prioridad,
    required this.slaRestante,
    required this.distanciaKm,
    required this.minutosDeViaje,
    required this.potenciaRxDbm,
  });

  /// CAMPO-DATA-003 · Futuro: `trabajo.zona` (backend de Campo).
  final String zona;

  /// CAMPO-DATA-004 · Futuro: `trabajo.prioridad` (backend de Campo).
  final String prioridad;

  /// CAMPO-DATA-002 · Futuro: `trabajo.sla_restante` (backend de Campo).
  /// Formato `HH:mm`.
  final String slaRestante;

  /// CAMPO-DATA-005 · Futuro: distancia y tiempo de viaje calculados con la
  /// ubicación del técnico y la del cliente.
  final double distanciaKm;
  final int minutosDeViaje;

  /// CAMPO-DATA-001 · Futuro: `telemetria.rx_dbm` (SmartOLT).
  final double potenciaRxDbm;
}
