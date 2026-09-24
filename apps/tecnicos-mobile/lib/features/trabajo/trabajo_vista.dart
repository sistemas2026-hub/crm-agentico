import 'dart:convert';

import 'estado_trabajo.dart';
import 'estado_validacion.dart';

/// Un trabajo, tal como lo muestra la lista.
///
/// Todo lo que hay acá **llega de la orden**. Nada se rellena.
///
/// Hasta el 22/09/2026 este modelo traía además un campo `futuro` con zona,
/// prioridad, SLA y distancia derivados de un hash del identificador. Eran
/// valores de ejemplo, pero vivían dentro del mismo objeto que los reales, y
/// eso los volvía indistinguibles para quien los leyera: `trabajo.futuro.zona`
/// devolvía siempre algo, hubiera o no zona.
///
/// Peor: ponía al modelo —y por él a `core/estado/ordenes_jornada.dart`, que
/// lo importa— a depender de `lib/demo/`. El núcleo terminaba alcanzando la
/// demostración a dos saltos, sin que ningún import de `core/` lo dijera.
///
/// Ahora una pantalla que quiera dibujar un dato de ejemplo lo pide donde lo
/// dibuja, dentro de su bloque con la bandera. Cuesta una línea más y se ve
/// en el diff, que es exactamente la idea.
///
/// Esto **no** se guarda. La fila de `local_ordenes` no cambia.
class TrabajoVista {
  const TrabajoVista({
    required this.id,
    required this.numero,
    required this.estado,
    required this.clienteNombre,
    required this.direccion,
    required this.telefono,
    required this.tipoNombre,
    required this.tipoCodigo,
    required this.familia,
    required this.compromiso,
    required this.revision,
    required this.estadoValidacion,
    required this.latitud,
    required this.longitud,
    required this.iniciadaEn,
    required this.completadaEn,
    required this.diagnosticoPrevio,
    required this.versionEsquema,
    required this.requiereActualizacion,
    this.correccion,
    this.origen,
    this.pasosDelProcedimiento = const <String>[],
    this.contexto = const <String, dynamic>{},
    this.titulosDeEvidencia = const <String, String>{},
    this.vuelta = 1,
    this.prioridad = '',
    this.zona = '',
    this.resumen = '',
    this.ventanaInicio,
    this.ventanaFin,
    this.slaVenceEn,
    this.detalleAcceso = '',
    this.idAbonado = '',
    this.requisitosSeguridad = const <String>[],
  });

  // --- Datos reales, de la orden -------------------------------------------
  final String id;
  final int? numero;
  final EstadoTrabajo estado;
  final String clienteNombre;
  final String direccion;
  final String telefono;
  final String tipoNombre;
  final String tipoCodigo;
  final FamiliaTrabajo familia;
  final DateTime? compromiso;

  /// Version de la orden en el servidor. La transicion la manda como base para
  /// que el backend detecte si alguien la movio mientras tanto.
  final int revision;

  /// Si el supervisor ya la revisó, y qué decidió. Es **otra máquina**: no
  /// tiene nada que ver con [estado] y no lo mueve. Ver `estado_validacion.dart`.
  final EstadoValidacion estadoValidacion;

  /// Dónde queda el cliente, tal como lo manda el servidor. Puede llegar una
  /// coordenada sin la otra.
  final double? latitud;
  final double? longitud;

  /// Cuándo arrancó y cuándo se completó en campo, según el servidor. No son
  /// la hora del teléfono.
  final DateTime? iniciadaEn;
  final DateTime? completadaEn;

  final String diagnosticoPrevio;

  /// Qué versión de esquema exige la orden. Cero significa que todavía no se
  /// sabe: llegó por el listado y el detalle no bajó.
  final int versionEsquema;

  /// Si la orden se sabe compatible con esta versión de la aplicación.
  bool get versionEsquemaConocida => versionEsquema > 0;

  /// No se puede trabajar: o exige una versión más nueva, o todavía no se sabe
  /// cuál exige. Las dos cosas bloquean, porque compatibilidad no demostrada
  /// no es compatibilidad.
  final bool requiereActualizacion;

  /// Qué pidió rehacer el supervisor, cuando la orden viene devuelta.
  ///
  /// Es `null` mientras nadie la haya devuelto. Antes del 22/09/2026 esta
  /// lista vivía solo en la bitácora del servidor: el técnico recibía la orden
  /// en `correccion_requerida` y averiguaba por teléfono qué corregir.
  final DevolucionDeValidacion? correccion;

  /// De qué ticket nació la orden. Real: `origen` del backend.
  final OrigenDeOrden? origen;

  /// Los pasos del procedimiento del tipo de trabajo, tal como vienen en la
  /// plantilla. **No es la máquina de estados**: es el procedimiento.
  final List<String> pasosDelProcedimiento;

  /// El snapshot técnico que el despacho congeló al crear la orden.
  final Map<String, dynamic> contexto;

  /// Cómo se llama cada evidencia que pide la plantilla, por su identificador.
  /// Sirve para nombrar lo que el supervisor devolvió: el técnico conoce esa
  /// foto por su título, no por `foto_potencia`.
  final Map<String, String> titulosDeEvidencia;

  /// En qué vuelta de validación va. 1 es la primera presentación.
  final int vuelta;

  // --- Lo que decide la oficina (tanda 2) ----------------------------------
  // Todos pueden venir vacíos: hay órdenes creadas antes de que existieran.

  /// Con qué urgencia se despachó: `alta`, `media` o `baja`.
  final String prioridad;

  /// Zona operativa del trabajo.
  final String zona;

  /// Qué hay que hacer, en una línea.
  final String resumen;

  /// La franja que se le prometió al cliente. No es lo mismo que [compromiso],
  /// que es la hora agendada.
  final DateTime? ventanaInicio;
  final DateTime? ventanaFin;

  /// Cuándo vence el compromiso de atención. Lo calcula el backend con las
  /// reglas de la empresa; el teléfono no las conoce.
  final DateTime? slaVenceEn;

  /// Cómo se entra al inmueble: torre, piso, apartamento.
  final String detalleAcceso;

  /// El identificador del abonado en el sistema del ISP.
  final String idAbonado;

  /// Qué hace falta para ejecutar el trabajo. Se informan; no habilitan nada.
  final List<String> requisitosSeguridad;

  factory TrabajoVista.desdeOrden(Map<String, dynamic> orden) {
    final id = orden['id']?.toString() ?? '';
    final tipoCodigo = orden['tipo_codigo']?.toString() ?? '';
    final tipoNombre = orden['tipo_nombre']?.toString() ?? 'Trabajo';

    return TrabajoVista(
      id: id,
      numero: orden['numero'] is int
          ? orden['numero'] as int
          : int.tryParse(orden['numero']?.toString() ?? ''),
      estado: EstadoTrabajo.desde(orden['estado']?.toString()),
      clienteNombre: orden['cliente_nombre']?.toString() ?? 'Sin cliente',
      direccion: orden['direccion']?.toString() ?? 'Sin dirección',
      telefono: orden['telefono']?.toString() ?? '',
      tipoNombre: tipoNombre,
      tipoCodigo: tipoCodigo,
      familia: FamiliaTrabajo.desde(codigo: tipoCodigo, nombre: tipoNombre),
      compromiso: DateTime.tryParse(orden['fecha_compromiso']?.toString() ?? '')
          ?.toLocal(),
      revision: orden['revision'] as int? ?? 0,
      estadoValidacion:
          EstadoValidacion.desde(orden['estado_validacion']?.toString()),
      latitud: _decimal(orden['cliente_lat']),
      longitud: _decimal(orden['cliente_lng']),
      iniciadaEn: _fecha(orden['iniciada_en']),
      completadaEn: _fecha(orden['completada_campo_en']),
      diagnosticoPrevio: orden['diagnostico_previo_ia']?.toString() ?? '',
      versionEsquema: orden['schema_version'] as int? ?? 0,
      correccion: DevolucionDeValidacion.desdeJson(orden['correccion_json']),
      origen: OrigenDeOrden.desdeJson(orden['origen_json']),
      pasosDelProcedimiento: _pasos(orden['pasos_json']),
      contexto: _mapa(orden['contexto_json']),
      titulosDeEvidencia: _titulos(orden['formulario_evidencias_json']),
      vuelta: orden['vuelta'] as int? ?? 1,
      prioridad: orden['prioridad']?.toString() ?? '',
      zona: orden['zona']?.toString() ?? '',
      resumen: orden['resumen']?.toString() ?? '',
      ventanaInicio: _fecha(orden['ventana_inicio']),
      ventanaFin: _fecha(orden['ventana_fin']),
      slaVenceEn: _fecha(orden['sla_vence_en']),
      detalleAcceso: orden['detalle_acceso']?.toString() ?? '',
      idAbonado: orden['id_abonado']?.toString() ?? '',
      requisitosSeguridad: <String>[
        for (final dynamic r in _lista(orden['requisitos_seguridad_json']))
          r.toString(),
      ],
      requiereActualizacion: _bloqueaPorEsquema(orden['schema_version'] as int?),
    );
  }

  /// Esta versión sabe ejecutar el esquema 1. Una orden que exige más, o una
  /// de la que todavía no se sabe qué exige, no se puede trabajar.
  static bool _bloqueaPorEsquema(int? version) {
    if (version == null || version <= 0) return true;
    return version > 1;
  }

  /// Los títulos de los pasos del procedimiento, en orden.
  static List<String> _pasos(Object? json) {
    final lista = _lista(json);
    return <String>[
      for (final dynamic paso in lista)
        if (paso is Map && paso['titulo'] != null)
          paso['titulo'].toString()
        else
          paso.toString(),
    ];
  }

  /// Los títulos de las evidencias de la plantilla, por identificador.
  static Map<String, String> _titulos(Object? json) {
    final Map<String, String> salida = <String, String>{};
    for (final dynamic requisito in _lista(json)) {
      if (requisito is! Map) continue;
      final String? id = requisito['id']?.toString();
      if (id == null) continue;
      salida[id] =
          (requisito['descripcion'] ?? requisito['titulo'] ?? id).toString();
    }
    return salida;
  }

  static List<dynamic> _lista(Object? json) {
    if (json == null) return const <dynamic>[];
    try {
      final dynamic decodificado = jsonDecode(json.toString());
      return decodificado is List ? decodificado : const <dynamic>[];
    } on FormatException {
      return const <dynamic>[];
    }
  }

  static Map<String, dynamic> _mapa(Object? json) {
    if (json == null) return const <String, dynamic>{};
    try {
      final dynamic decodificado = jsonDecode(json.toString());
      return decodificado is Map
          ? Map<String, dynamic>.from(decodificado)
          : const <String, dynamic>{};
    } on FormatException {
      return const <String, dynamic>{};
    }
  }

  /// La franja prometida, ya escrita: "09:30 - 11:00". Vacía si no hay.
  String get ventanaTexto {
    if (ventanaInicio == null || ventanaFin == null) return '';
    return '${_hora(ventanaInicio!)} - ${_hora(ventanaFin!)}';
  }

  /// Cuántos minutos quedan de compromiso. Negativo si ya venció; `null` si el
  /// servidor no dijo cuándo vence —y entonces no se inventa una cuenta—.
  int? minutosParaVencer({DateTime? ahora}) {
    if (slaVenceEn == null) return null;
    return slaVenceEn!.difference(ahora ?? DateTime.now()).inMinutes;
  }

  /// Si el compromiso ya venció. `false` cuando no se sabe: afirmar que algo
  /// está vencido sin saberlo es peor que callar.
  bool vencido({DateTime? ahora}) {
    final int? minutos = minutosParaVencer(ahora: ahora);
    return minutos != null && minutos < 0;
  }

  static String _hora(DateTime f) =>
      '${f.hour.toString().padLeft(2, '0')}:${f.minute.toString().padLeft(2, '0')}';

  /// Un dato de la ficha del cliente que el despacho congeló, si lo capturó.
  ///
  /// Se lee en UN solo lugar a propósito. El esquema del formulario ya enseñó
  /// lo que pasa cuando el mismo dato se interpreta en varios archivos: cinco
  /// defectos distintos, y ninguna lectura estaba mal escrita —el problema era
  /// que existieran varias— (contrato de versión candidata §3).
  String _delCliente(String clave) {
    final dynamic cliente = contexto['cliente'];
    if (cliente is Map && cliente[clave] != null) {
      return cliente[clave].toString();
    }
    return '';
  }

  /// El plan que tiene contratado el cliente, si el despacho lo capturó.
  String get planContratado => _delCliente('plan');

  /// La IP del router del cliente. La ve el técnico, no el modelo.
  String get ipCliente => _delCliente('ip');

  /// En qué parte del pueblo queda. La dirección dice el número de la casa;
  /// esto dice si la visita entra en la ruta de hoy.
  String get localidadCliente => _delCliente('localidad');

  /// Cómo está la cuenta en el sistema del ISP (activo, suspendido...). No es
  /// el estado de la ORDEN: una orden recién asignada de un cliente suspendido
  /// por mora no se resuelve cambiando una ONU.
  String get estadoCuenta => _delCliente('estado');

  /// El serial de la ONU del cliente, si el despacho lo capturó.
  String get serialOnu => contexto['sn_onu']?.toString() ?? '';

  /// La prioridad que le puso el operador en el sistema del ISP.
  ///
  /// **No es un juicio de Dexter.** Viaja aparte y se muestra aparte: mezclarla
  /// con la de Dexter haría que la pantalla afirme un análisis que no ocurrió.
  /// WispHub maneja cuatro niveles (1 Baja · 2 Normal · 3 Alta · 4 Muy Alta).
  String get prioridadProveedor {
    final dynamic p = contexto['prioridad_proveedor'];
    if (p is Map && p['etiqueta'] != null) return p['etiqueta'].toString();
    return '';
  }

  /// Si la prioridad de la orden la **calculó** Dexter, o solo la heredó.
  ///
  /// Hoy devuelve `false` siempre, y eso es correcto: Dexter todavía no
  /// prioriza. El campo `prioridad` lo pone quien despacha, con default
  /// `media`. Mostrar eso como juicio sería presentar una copia disfrazada de
  /// análisis.
  ///
  /// Está escrito para encenderse solo: el día que el motor devuelva
  /// `prioridad_dexter` en el contexto —con su nivel, sus motivos y su hora—
  /// esto pasa a `true` sin tocar la tarjeta.
  bool get prioridadEvaluadaPorDexter {
    final dynamic p = contexto['prioridad_dexter'];
    return p is Map && p['nivel'] != null;
  }

  /// Por qué Dexter le puso esa prioridad.
  ///
  /// Un técnico que lee «Alta» no aprende nada; uno que lee «Alta — tercera
  /// visita por lo mismo · cliente suspendido» sabe qué va a encontrar. Sin
  /// motivos, la etiqueta es un adorno.
  List<String> get motivosPrioridad {
    final dynamic p = contexto['prioridad_dexter'];
    if (p is Map && p['motivos'] is List) {
      return (p['motivos'] as List).map((dynamic m) => m.toString()).toList();
    }
    return const <String>[];
  }

  /// Si hay ficha del cliente. Que falte NO es un error: se despacha una orden
  /// justamente cuando algo no se pudo resolver solo, y muchas veces eso
  /// incluye no haber identificado al cliente.
  bool get contextoDisponible => contexto['contexto_disponible'] == true;

  /// La diferencia que le importa a quien mira la orden: **no se pudo
  /// preguntar** (el motor no respondió) no es lo mismo que **se preguntó y no
  /// se pudo identificar al cliente**. Para el técnico, una se reintenta y la
  /// otra se resuelve preguntándole a la persona.
  bool get motorAlcanzado => contexto['motor_alcanzado'] != false;

  /// Por qué no hay ficha del cliente. Son **tres** casos, no dos, y el
  /// tercero se descubrió mirando datos reales: 4 de 100 casos nacieron de una
  /// conversación y **nunca van a tener servicio asociado**.
  ///
  /// Decirle «se reintenta al sincronizar» a ese tercero es mandar al técnico
  /// a esperar algo que no va a pasar. El backend ya los distingue con su
  /// `motivo` normalizado; acá solo se lee, no se deduce.
  SinFicha get sinFicha {
    if (contextoDisponible) return SinFicha.hayFicha;
    final String motivo = contexto['motivo']?.toString() ?? '';
    if (motivo == 'caso_sin_servicio') return SinFicha.casoSinServicio;
    if (!motorAlcanzado) return SinFicha.noSePudoConsultar;
    return SinFicha.clienteNoIdentificado;
  }

  static double? _decimal(Object? valor) {
    if (valor == null) return null;
    if (valor is num) return valor.toDouble();
    return double.tryParse(valor.toString());
  }

  static DateTime? _fecha(Object? valor) {
    final texto = valor?.toString();
    if (texto == null || texto.isEmpty) return null;
    return DateTime.tryParse(texto)?.toLocal();
  }
}

/// De qué clase de trabajo se trata, para poder distinguirlos de un vistazo.
///
/// **No son entidades distintas del sistema**: una orden de trabajo es una
/// orden de trabajo, venga de una instalación nueva o de un ticket de soporte.
/// Esto solo cambia el icono y la palabra de la tarjeta. El tipo real es
/// `tipo_codigo`, que cada empresa define a su manera (la semilla del backend
/// trae `ftth_instalacion`), así que se reconoce por lo que el texto contiene y,
/// si no se reconoce, se muestra el nombre del tipo tal cual vino.
/// Por que una orden no trae la ficha del cliente.
///
/// Tres casos, no dos. El tercero aparecio mirando datos REALES: de 100 casos
/// de produccion, 4 nacieron de una conversacion y no tienen servicio
/// asociado -- no van a tenerlo nunca. Con datos inventados no se habria visto,
/// porque todos habrian tenido servicio.
///
/// La diferencia no es cosmetica: cada uno se arregla distinto, y dos de los
/// tres no se arreglan solos.
enum SinFicha {
  /// Hay ficha. El caso normal cuando el motor resolvio.
  hayFicha,

  /// El motor no respondio. **Se reintenta**: al sincronizar puede resolverse.
  noSePudoConsultar,

  /// El motor respondio y no pudo identificar al cliente. No se reintenta: se
  /// resuelve preguntandole a la persona. Medido por el motor sobre 85
  /// conversaciones reales, 45 con cliente identificado -- o sea que este es
  /// el caso NORMAL, no la excepcion.
  clienteNoIdentificado,

  /// El caso no tiene servicio asociado. **No se arregla**: nacio de una
  /// conversacion, no de un ticket. Decir "se reintenta" aca manda al tecnico
  /// a esperar algo que no va a pasar.
  casoSinServicio,
}

enum FamiliaTrabajo {
  instalacion,
  incidencia,
  mantenimiento,
  otro;

  static FamiliaTrabajo desde({required String codigo, required String nombre}) {
    final texto = '$codigo $nombre'.toLowerCase();
    if (texto.contains('instal') || texto.contains('alta')) {
      return FamiliaTrabajo.instalacion;
    }
    if (texto.contains('ticket') ||
        texto.contains('incidencia') ||
        texto.contains('correctivo') ||
        texto.contains('falla') ||
        texto.contains('soporte')) {
      return FamiliaTrabajo.incidencia;
    }
    if (texto.contains('mantenimiento') || texto.contains('preventivo')) {
      return FamiliaTrabajo.mantenimiento;
    }
    return FamiliaTrabajo.otro;
  }

  String get etiqueta => switch (this) {
        FamiliaTrabajo.instalacion => 'Instalación',
        FamiliaTrabajo.incidencia => 'Incidencia',
        FamiliaTrabajo.mantenimiento => 'Mantenimiento',
        FamiliaTrabajo.otro => 'Orden de trabajo',
      };
}

/// Lo que el supervisor devolvió para rehacer.
///
/// Sale de `correccion` en el detalle de la orden. El backend la arma desde la
/// bitácora, y siempre es la de la vuelta que corre: si una orden se devolvió
/// dos veces, acá está la segunda.
class DevolucionDeValidacion {
  const DevolucionDeValidacion({
    required this.vuelta,
    required this.requisitos,
    required this.observacion,
    required this.devueltaEn,
  });

  /// En qué vuelta se devolvió.
  final int vuelta;

  /// Los identificadores de las evidencias que hay que volver a tomar. Salen
  /// de la plantilla de la orden, así que se pueden cruzar con sus títulos.
  final List<String> requisitos;

  /// Lo que escribió el supervisor. Puede venir vacío.
  final String observacion;

  final DateTime? devueltaEn;

  static DevolucionDeValidacion? desdeJson(Object? json) {
    if (json == null) return null;
    try {
      final dynamic d = jsonDecode(json.toString());
      if (d is! Map) return null;
      return DevolucionDeValidacion(
        vuelta: d['vuelta'] is int ? d['vuelta'] as int : 1,
        requisitos: <String>[
          for (final dynamic r in (d['requisitos'] as List<dynamic>? ?? const <dynamic>[]))
            r.toString(),
        ],
        observacion: d['observacion']?.toString() ?? '',
        devueltaEn: DateTime.tryParse(d['devuelta_en']?.toString() ?? '')?.toLocal(),
      );
    } on FormatException {
      return null;
    }
  }
}

/// De dónde vino la orden: qué sistema la pidió y con qué referencia.
class OrigenDeOrden {
  const OrigenDeOrden({
    required this.sistema,
    required this.tipo,
    required this.referencia,
  });

  final String sistema;
  final String tipo;
  final String referencia;

  /// Cómo se nombra en pantalla: "Ticket WH-91288". Vacío si no hay nada que
  /// decir —una orden creada a mano no viene de ningún lado—.
  String get etiqueta {
    if (referencia.isEmpty) return '';
    final String nombre = tipo.isEmpty ? 'Origen' : _capitalizado(tipo);
    return '$nombre $referencia';
  }

  static String _capitalizado(String texto) =>
      texto.isEmpty ? texto : texto[0].toUpperCase() + texto.substring(1);

  static OrigenDeOrden? desdeJson(Object? json) {
    if (json == null) return null;
    try {
      final dynamic d = jsonDecode(json.toString());
      if (d is! Map) return null;
      final origen = OrigenDeOrden(
        sistema: d['sistema']?.toString() ?? '',
        tipo: d['tipo']?.toString() ?? '',
        referencia: d['ref']?.toString() ?? '',
      );
      return origen.referencia.isEmpty ? null : origen;
    } on FormatException {
      return null;
    }
  }
}
