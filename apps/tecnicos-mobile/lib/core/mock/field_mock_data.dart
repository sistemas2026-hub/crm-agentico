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

  /// CAMPO-DATA-007 · Cuadrilla asignada.
  /// Futuro: asignación de cuadrilla en el backend de Campo (`jornada.cuadrilla`).
  static const String cuadrilla = 'Cuadrilla 04 · Rapilink Fibra';

  /// CAMPO-DATA-018 · Formación pendiente del técnico.
  /// Futuro: módulo de Academia (`academia.cursos_pendientes`).
  static const int cursosPendientes = 1;

  /// CAMPO-DATA-019 · Foto del técnico.
  /// Futuro: perfil del colaborador en el CRM (`profile.foto_url`). Hasta que
  /// exista, el encabezado muestra sus iniciales, que sí son reales.
  static const String? fotoTecnico = null;

  /// CAMPO-DATA-020 · Ventana horaria comprometida con el cliente.
  /// Futuro: `trabajo.ventana_inicio` y `trabajo.ventana_fin` (backend de Campo).
  static const String ventanaHoraria = '10:00 - 12:00';

  /// CAMPO-DATA-021 · Cuándo y quién confirmó la entrega del kit.
  /// Futuro: inventario de Dexter (`kit.confirmado_en`).
  static const String kitConfirmadoHora = '08:02 AM';

  /// CAMPO-DATA-022 · Cambios locales sin enviar, tal como los cuenta el
  /// diseño en la franja oscura. En la aplicación esto **sí** es real: sale de
  /// la cola de sincronización. Queda acá solo el texto del modo de trabajo.
  static const String modoDatos = 'Modo Dinámico';

  /// CAMPO-DATA-008 · Vehículo y su preoperacional del día.
  /// Futuro: módulo de vehículos (`vehiculo.placa`, `vehiculo.preoperacional_ok`).
  static const String vehiculoPlaca = 'ABC123';
  static const bool vehiculoPreoperacionalHecho = true;

  // --- El modo de trabajo del técnico --------------------------------------

  /// CAMPO-DATA-038 · En qué está el técnico ahora mismo: en sitio, viajando,
  /// disponible o en pausa.
  ///
  /// Futuro: jornada en el backend de Campo (`jornada.estado`), con su propia
  /// cola de cambios para que se pueda marcar sin señal. Hoy el selector
  /// cambia solo lo que se ve: no se guarda, no viaja y no cambia ninguna
  /// orden.
  static const List<EstadoJornada> estadosDeJornada = <EstadoJornada>[
    EstadoJornada('En sitio', 'Activo'),
    EstadoJornada('En ruta', 'Tránsito'),
    EstadoJornada('Disponible', 'Espera'),
    EstadoJornada('Pausa', 'Colación'),
  ];

  /// CAMPO-DATA-039 · Hora estimada de llegada al trabajo en curso.
  /// Futuro: cálculo con la posición del técnico y la del cliente.
  static const String etaTrabajoActual = '10:15 AM';

  /// CAMPO-DATA-040 · Identificador del abonado en el sistema del ISP.
  /// Futuro: `cliente.id_abonado` (WispHub vía backend).
  static const String idAbonado = 'ID 10984214';

  /// CAMPO-DATA-041 · Cómo se entra: piso, torre, apartamento.
  /// Futuro: `cliente.detalle_acceso` (backend de Campo).
  static const String detalleAcceso = 'Interior 3 - Apto 402 · Torre Norte';

  /// CAMPO-DATA-042 · El vehículo del turno, más allá de la placa.
  /// Futuro: módulo de vehículos (`vehiculo.modelo`, `.odometro`, `.combustible`).
  static const String vehiculoModelo = 'Kangoo';
  static const String vehiculoOdometro = '82.451 km';
  static const int vehiculoCombustible = 75;

  /// CAMPO-DATA-043 · El curso obligatorio que vence.
  /// Futuro: módulo de Academia (`academia.obligatorio`, `.vence_en`).
  static const String cursoObligatorio = 'Trabajo Seguro en Alturas (SST)';
  static const String cursoVence = 'Vence hoy 18:00';

  /// CAMPO-DATA-044 · Lector de código del equipo del cliente.
  /// Futuro: cámara + validación contra el inventario (`equipo.serial`).
  /// Mientras no exista, el botón avisa que falta en vez de fingir que lee.
  static const String escanerPendiente =
      'El lector de códigos todavía no está integrado (CAMPO-DATA-044).';

  /// CAMPO-DATA-045 · Requisitos de seguridad del trabajo.
  ///
  /// Futuro: `trabajo.requisitos[]` cruzado con las certificaciones vigentes
  /// del técnico (`perfil.certificaciones`). Hoy la orden no dice si hay que
  /// trabajar en altura, y el técnico se entera en el sitio.
  ///
  /// **No habilita ni bloquea nada**: se muestra, y la aptitud que anuncia es
  /// la del ejemplo, no una verificación real.
  static const String requisitoSeguridad =
      'Requiere Certificación de Alturas Vigente';
  static const String aptitudTecnico = 'Técnico C-04 Calificado y Apto';

  /// CAMPO-DATA-046 · El acta de cierre de un trabajo terminado.
  /// Futuro: `trabajo.acta` (backend de Campo), con la firma del cliente y la
  /// medición final.
  static const String actaPotenciaFinal = '-19.4 dBm';
  static const String actaEstado = 'Aprobado · Acta firmada';

  /// CAMPO-DATA-047 · De dónde salió la orden: quién la abrió y cuándo.
  /// Futuro: `trabajo.origen` (backend de Campo, con el ticket del NOC).
  static const String origenApertura = 'Apertura: 08:15 AM por Centro NOC Central';

  /// CAMPO-DATA-048 · La matriz de telemetría completa del diseño.
  /// Futuro: SmartOLT vía Dexter API (`telemetria.olt`, `.distancia_splitter`,
  /// `.tx_dbm`).
  static const String oltYPuerto = 'OLT-HUAWEI-SUR-02 (C1/S4/P03)';
  static const String distanciaSplitter = '284 metros';
  static const String potenciaTxOlt = '+2.8 dBm (Óptimo)';
  static const String fuenteTelemetria =
      'Fuente: SmartOLT vía Dexter API · Actualizado hace 1 min';

  /// CAMPO-DATA-049 · El protocolo de atención del tipo de trabajo.
  ///
  /// Futuro: `tipo_trabajo.protocolo[]` (backend de Campo). **No es la máquina
  /// de estados**: son los pasos del procedimiento dentro del trabajo, y por
  /// eso se muestran aparte de la barra de estados, que sí es real y sí
  /// avanza con lo que el técnico marca.
  static const List<String> protocoloAtencion = <String>[
    'Notificación de Llegada al Inmueble',
    'Inspección Visual de Acometida y Roseta',
    'Medición Óptica con VFL / Power Meter',
    'Reconectorización / Fusión en CTO o Roseta',
    'Prueba de Servicio y Velocidad',
    'Registro Fotográfico de Evidencias',
    'Firma del Abonado',
    'Cierre y Sincronización',
  ];

  /// En qué paso del protocolo va. Tampoco existe: no hay dónde guardarlo.
  static const int protocoloPasoActual = 3;

  /// CAMPO-DATA-050 · El procedimiento recomendado para la falla detectada.
  /// Futuro: base de conocimiento de Dexter (`procedimiento.pasos[]`), elegida
  /// por el tipo de falla. Es material de consulta: no valida ni completa nada.
  static const String procedimientoTitulo = 'Procedimiento Atenuación';
  static const List<String> procedimientoPasos = <String>[
    'Limpiar conectores SC/APC con alcohol isopropílico antes de medir.',
    'Probar potencia directa en el puerto de la CTO.',
    'Si la potencia en la CTO es normal (> -21 dBm), reemplazar el tramo de drop por quiebre mecánico.',
    'Validar la reapertura del puerto en SmartOLT antes de firmar el cierre.',
  ];

  // --- El kit del técnico --------------------------------------------------

  /// CAMPO-DATA-009 · Resumen del kit diario.
  /// Futuro: inventario de Dexter (`kit.recibidos`, `kit.consumidos`,
  /// `kit.disponibles`). Es el mismo dato que va a alimentar la Fase 8.
  static const int kitRecibidos = 24;
  static const int kitConsumidos = 8;
  static const int kitDisponibles = 16;
  static const String kitOrigen = 'Depósito Central · Bodega 2';

  // --- El día, en números --------------------------------------------------

  /// CAMPO-DATA-013 · Trabajos del día con la señal fuera de rango.
  /// Futuro: telemetría de SmartOLT cruzada con las órdenes de la jornada
  /// (`jornada.alertas_rx`). Estaba escrito a mano dentro de la pantalla de
  /// Trabajo; acá queda con su identificador, como el resto.
  static const int alertasRxDelDia = 1;

  /// CAMPO-DATA-014 · Cumplimiento del SLA del día, en porcentaje.
  /// Futuro: backend de Campo (`jornada.cumplimiento_sla`).
  static const int cumplimientoSlaHoy = 94;

  // --- El enlace con el servidor -------------------------------------------

  /// CAMPO-DATA-035 · Nombre y versión del enlace de sincronización, tal como
  /// lo rotula el diseño. Futuro: lo informaría el propio backend
  /// (`enlace.nombre`, `enlace.version`); hoy la aplicación no lo pregunta.
  static const String enlaceDexter = 'Dexter Link v4.2';

  /// CAMPO-DATA-036 · Cuándo fue la última sincronización con éxito.
  ///
  /// **No es deuda del backend: es de la aplicación.** La cola sabe cuántos
  /// cambios quedan sin enviar, pero no guarda la marca de tiempo del último
  /// envío bueno, así que todavía no hay nada real que mostrar.
  static const String ultimaSincronizacion = 'Hace 1 min';

  /// CAMPO-DATA-037 · Qué hay que hacer, en una línea.
  /// Futuro: `trabajo.resumen` (backend de Campo). Hoy la orden trae el tipo y
  /// el diagnóstico, pero no un resumen del procedimiento.
  static const String resumenDelTrabajo =
      'Diagnóstico en domicilio y verificación de potencia';

  // --- La red, por trabajo -------------------------------------------------

  /// CAMPO-DATA-001 · Potencia óptica RX de la ONT.
  /// Futuro: SmartOLT a través del backend (`telemetria.rx_dbm`).
  static const double potenciaRxDbm = -18.7;

  /// CAMPO-DATA-011 · Identificadores de red del cliente.
  /// Futuro: SmartOLT/WispHub (`telemetria.cto`, `.pon`, `.serial_ont`).
  static const String cto = 'CTO-04-A';

  /// Terminal tal como lo escribe el diseño: caja y puerto.
  static const String terminal = 'CTO-04-A (Pto 6)';

  /// Lectura previa, la que el técnico ve antes de salir. El diseño muestra
  /// una fuera de rango, que es el caso que importa.
  static const double potenciaRxPrevia = -28.9;
  static const String rangoOpticoAceptable = 'Fuera de rango estándar';
  static const String puertoPon = 'PON 0/1/4';
  static const String serialOnt = '48575443-B981F';

  /// CAMPO-DATA-030 · Cómo se movió la potencia en las últimas 48 horas.
  /// Futuro: histórico de SmartOLT (`telemetria.rx_48h[]`). El diseño lo dibuja
  /// como una curva; para dibujarla hace falta la serie, no solo el delta.
  static const double deltaPotencia48h = -4.2;
  static const List<double> historicoRx48h = <double>[
    -24.1, -24.4, -25.0, -25.6, -26.2, -26.1, -27.0, -27.8, -28.2, -28.9,
  ];

  /// CAMPO-DATA-031 · Rango óptico esperado para la instalación.
  /// Futuro: parámetro de la empresa (`red.rango_optico`), no un número fijo:
  /// cada ISP define el suyo.
  static const String rangoOptimoTexto = 'Rango óptimo: -18.0 dBm a -25.0 dBm';

  /// CAMPO-DATA-032 · Longitud de onda con la que se mide en campo.
  /// Futuro: catálogo de la red (`red.longitud_onda_medicion`).
  static const String longitudOndaMedicion = '1490nm Óptico';

  /// CAMPO-DATA-033 · Umbral de aceptación de una lectura de campo.
  /// Futuro: parámetro de la empresa (`red.umbral_aceptacion_campo`).
  ///
  /// Se muestra como referencia junto a la medición. **No valida**: no bloquea
  /// el cierre de la orden ni marca la respuesta como incorrecta.
  static const double umbralOptimoMin = -25.0;
  static const double umbralOptimoMax = -15.0;
  static const String umbralAceptacionTexto = 'umbral de aceptación (-15 a -25 dBm)';

  // --- Lo que el formulario de campo todavía no tiene ----------------------

  /// CAMPO-DATA-026 · Equipo sugerido para reemplazar y su stock a bordo.
  /// Futuro: inventario de Dexter cruzado con el tipo de falla
  /// (`kit.sugerencia_reemplazo`). Hoy el formulario no sugiere nada: la
  /// sugerencia se muestra, no se guarda y no cambia ninguna respuesta.
  static const String equipoSugerido = 'ONT Huawei GPON HG8145V5';
  static const String equipoSugeridoStock = 'STOCK EN CAMIONETA (2)';

  /// CAMPO-DATA-027 · Medidor óptico por Bluetooth.
  /// Futuro: integración con el power meter (`medicion.bluetooth`).
  ///
  /// Mientras no exista, el botón **no escribe** ninguna lectura en el
  /// formulario: una medición inventada quedaría firmada por el técnico como
  /// si la hubiera tomado, y eso no es un dato de ejemplo, es un dato falso.
  static const String medidorBluetooth = 'Medir Power Meter';
  static const String medidorPendiente =
      'El medidor por Bluetooth todavía no está integrado (CAMPO-DATA-027). '
      'La lectura se escribe a mano.';

  /// CAMPO-DATA-028 · Cápsulas de Academia para el procedimiento en curso.
  /// Futuro: módulo de Academia (`academia.capsulas[]`), filtradas por el tipo
  /// de trabajo. Son material de consulta: no validan ni completan nada.
  static const List<CapsulaAcademia> capsulasAcademia = <CapsulaAcademia>[
    CapsulaAcademia(
      titulo: 'Guía: Limpieza de Conector SC/APC con Clicker',
      encabezado: 'Técnica de Limpieza en Seco con Clicker Cleaner:',
      esVideo: false,
      pasos: <String>[
        'Retire la tapa protectora sin tocar la punta de la férula de zirconio con los dedos.',
        'Inserte el limpiador recto dentro del acoplador o sobre el ferrule macho.',
        'Presione hasta escuchar un "click" audible firme. Nunca gire la herramienta con fuerza excesiva.',
        'Realice la medición inmediata antes de volver a insertar a la ONT.',
      ],
    ),
    CapsulaAcademia(
      titulo: 'Video (1 min): Verificación de Roseta y Curvatura',
      encabezado: 'Puntos a revisar en la roseta del abonado:',
      esVideo: true,
      pasos: <String>[
        'Revise que el radio de curvatura del drop no baje de 3 cm.',
        'Verifique que la roseta quede fijada y sin tensión sobre el pigtail.',
        'Mida de nuevo después de reacomodar el tendido.',
      ],
    ),
  ];

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

  /// CAMPO-DATA-029 · Por qué se abrió el ticket que originó la orden.
  static const List<String> _motivos = <String>[
    'Sin internet nocturno',
    'Intermitencias en la noche',
    'Lentitud reportada por el abonado',
  ];

  /// Lo que el diseño muestra de un trabajo y ningún sistema entrega todavía.
  static TrabajoFuturoMock trabajoFuturo(String idOrden) {
    final semilla = _semilla(idOrden);
    return TrabajoFuturoMock(
      zona: _zonas[semilla % _zonas.length],
      prioridad: _prioridades[(semilla ~/ 7) % _prioridades.length],
      slaRestante: '0${1 + semilla % 5}:${((semilla % 6) * 10).toString().padLeft(2, '0')}',
      slaRestanteMinutos: 15 + semilla % 46,
      ticketOrigen: 'Ticket #${1200 + semilla % 800}',
      requiereAlturas: semilla % 3 == 0,
      motivoTicket: _motivos[semilla % _motivos.length],
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
    required this.slaRestanteMinutos,
    required this.ticketOrigen,
    required this.motivoTicket,
    required this.requiereAlturas,
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

  /// CAMPO-DATA-002 · El mismo dato en minutos: así lo rotula el diseño en
  /// Inicio, donde lo que importa es cuánto queda, no una hora.
  final int slaRestanteMinutos;

  /// CAMPO-DATA-029 · El ticket del que nació esta orden y su motivo.
  /// Futuro: `trabajo.ticket_origen` (backend de Campo). Hoy la aplicación
  /// recibe la orden sin rastro de quién la pidió.
  final String ticketOrigen;
  final String motivoTicket;

  /// CAMPO-DATA-045 · Si el trabajo exige certificación de alturas. Se deriva
  /// del identificador para que un mismo trabajo diga siempre lo mismo: un
  /// requisito de seguridad que cambia en cada refresco no se puede creer.
  final bool requiereAlturas;

  /// CAMPO-DATA-005 · Futuro: distancia y tiempo de viaje calculados con la
  /// ubicación del técnico y la del cliente.
  final double distanciaKm;
  final int minutosDeViaje;

  /// CAMPO-DATA-001 · Futuro: `telemetria.rx_dbm` (SmartOLT).
  final double potenciaRxDbm;
}

/// CAMPO-DATA-028 · Una cápsula de Academia: lo que el técnico puede consultar
/// sin salir de la orden. Futuro: `academia.capsulas[]`.
class CapsulaAcademia {
  const CapsulaAcademia({
    required this.titulo,
    required this.encabezado,
    required this.esVideo,
    required this.pasos,
  });

  final String titulo;

  /// Lo que encabeza la guía cuando se abre: el diseño no repite ahí el
  /// nombre del botón, lo enuncia como procedimiento.
  final String encabezado;

  /// Cambia el ícono y nada más: hoy ninguna de las dos reproduce nada.
  final bool esVideo;

  /// El contenido que se abre al tocarla.
  final List<String> pasos;
}

/// CAMPO-DATA-038 · Un modo de trabajo del técnico: cómo se llama y qué dice
/// debajo. Futuro: `jornada.estado`.
class EstadoJornada {
  const EstadoJornada(this.nombre, this.detalle);

  final String nombre;
  final String detalle;
}
