import 'dart:convert';

import '../../core/mock/field_mock_data.dart';
import 'estado_trabajo.dart';
import 'estado_validacion.dart';

/// Un trabajo, tal como lo muestra la lista.
///
/// Junta dos cosas que no se mezclan en ningún otro lado: lo que la orden trae
/// de verdad y lo que el diseño muestra pero el backend todavía no entrega.
/// Cada campo dice de dónde viene, y los futuros están agrupados en [futuro],
/// así que no hay forma de leer un dato de ejemplo creyendo que es real.
///
/// Esto **no** se guarda. La fila de `local_ordenes` no cambia: el día que la
/// API mande zona o prioridad, se cambia de dónde sale [futuro] y nada más.
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
    required this.futuro,
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

  /// CAMPO-DATA-015
  /// Zona, prioridad, SLA y distancia. Se muestran; no filtran ni deciden.
  final TrabajoFuturoMock futuro;

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
      futuro: FieldMockData.trabajoFuturo(id),
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

  /// El plan que tiene contratado el cliente, si el despacho lo capturó.
  String get planContratado {
    final dynamic cliente = contexto['cliente'];
    if (cliente is Map && cliente['plan'] != null) {
      return cliente['plan'].toString();
    }
    return '';
  }

  /// El serial de la ONU del cliente, si el despacho lo capturó.
  String get serialOnu => contexto['sn_onu']?.toString() ?? '';

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
