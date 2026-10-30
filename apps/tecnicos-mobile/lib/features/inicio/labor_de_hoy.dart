import 'dart:convert';

/// Con qué cuadrilla y qué labor sale hoy el técnico, como la armó la oficina
/// en Programación (29/10/2026, el usuario: «que salga hola, nombre del
/// técnico, y tu labor para hoy es…, que se actualiza según esté en la
/// plataforma de Dexter»). Lo manda `GET /api/campo/mi-dia/`.
///
/// Se guarda en el teléfono para verlo sin señal, pero SOLO vale el día al que
/// se refiere: la labor de ayer mostrada hoy mandaría al técnico a hacer otra
/// cosa.
class LaborDeHoy {
  const LaborDeHoy({required this.fecha, this.jornada});

  /// El día de la empresa al que se refiere, AAAA-MM-DD.
  final String fecha;

  /// Null si ese día no sale con ninguna cuadrilla. No es lo mismo que no
  /// saber: eso es un [LaborDeHoy] que no existe.
  final JornadaDeHoy? jornada;

  /// Si es la de `hoy`.
  bool esDe(DateTime hoy) =>
      fecha ==
      '${hoy.year.toString().padLeft(4, '0')}-'
          '${hoy.month.toString().padLeft(2, '0')}-'
          '${hoy.day.toString().padLeft(2, '0')}';

  /// Lo que contesta el servidor. Null si no trae la clave `jornada`: un
  /// servidor viejo no dice «hoy no salís», no dice nada.
  static LaborDeHoy? desdeJson(Object? json) {
    if (json is! Map || !json.containsKey('jornada')) return null;
    final Object? fecha = json['fecha'];
    if (fecha is! String || fecha.isEmpty) return null;
    final Object? j = json['jornada'];
    return LaborDeHoy(
      fecha: fecha,
      jornada: j is Map ? JornadaDeHoy.desdeJson(j) : null,
    );
  }

  /// Como se guarda en el teléfono.
  String aTexto() => jsonEncode(<String, Object?>{
    'fecha': fecha,
    'jornada': jornada?.aJson(),
  });

  static LaborDeHoy? desdeTexto(String? texto) {
    if (texto == null || texto.isEmpty) return null;
    try {
      return desdeJson(jsonDecode(texto));
    } on FormatException {
      return null;
    }
  }
}

class JornadaDeHoy {
  const JornadaDeHoy({
    required this.cuadrilla,
    required this.labor,
    this.apoyo = '',
    this.zonas = const <String>[],
  });

  final String cuadrilla;

  /// Cómo la llama la empresa: «Instalación», «Soporte en campo».
  final String labor;

  /// La labor de apoyo (30/10/2026): la que hace con el cupo que la suya deja
  /// libre. Vacía = sin apoyo.
  final String apoyo;
  final List<String> zonas;

  static JornadaDeHoy desdeJson(Map<dynamic, dynamic> j) => JornadaDeHoy(
    cuadrilla: j['cuadrilla']?.toString() ?? '',
    labor: (j['labor_nombre'] ?? j['labor'] ?? '').toString(),
    apoyo: (j['apoyo_nombre'] ?? '').toString(),
    zonas: <String>[
      if (j['zonas'] is List)
        for (final Object? z in j['zonas'] as List) z.toString(),
    ],
  );

  Map<String, Object?> aJson() => <String, Object?>{
    'cuadrilla': cuadrilla,
    'labor_nombre': labor,
    'apoyo_nombre': apoyo,
    'zonas': zonas,
  };

  /// «Cuadrilla #1 · Norte, Soledad zona 2».
  String get detalle => <String>[
    cuadrilla,
    zonas.join(', '),
  ].where((String s) => s.isNotEmpty).join(' · ');
}
