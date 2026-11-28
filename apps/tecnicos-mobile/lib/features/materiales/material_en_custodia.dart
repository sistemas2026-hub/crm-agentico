/// El material que un técnico tiene a cargo.
///
/// Este tipo vivía dentro del archivo de datos de ejemplo, cuando la custodia
/// no existía en ninguna parte y era solo la forma que el diseño proponía.
/// Ahora hay modelo, API y cola offline, así que el tipo se mudó acá: lo que
/// describe es la operación real, y el ejemplo pasó a ser un usuario más de
/// esta misma forma.
///
/// Sigue sin conocer de dónde salen los datos. Los arma la base local cuando
/// hay una jornada de verdad, y el catálogo de ejemplo cuando está encendido
/// el modo demostración; la pantalla no distingue, y no debería.
library;

/// De qué clase es un material. Cambia cómo se cuenta y cómo se muestra.
enum ClaseMaterial {
  /// Se consume por unidades: conectores, precintos.
  consumible,

  /// Se mide en metros y queda un remanente en la camioneta.
  bobina,

  /// Tiene número de serie y hay que poder rastrearlo.
  serializado,

  /// Caja terminal, roseta: se recibe y se instala.
  terminal,
}

/// Cómo se agrupa el kit para contarlo: una ONT, un metro de cable y un
/// conector no se pueden sumar entre sí (18/10/2026).
enum ClaseDeResumen { equipos, cable, consumibles }

/// Una serie que ya se instaló.
class SerieInstalada {
  const SerieInstalada({this.ordenNumero, this.sinSubir = false});

  /// La orden donde quedó, si se sabe.
  final int? ordenNumero;

  /// Se registró en el teléfono y todavía no llegó al servidor.
  final bool sinSubir;
}

class MaterialEnCustodia {
  const MaterialEnCustodia({
    required this.categoria,
    required this.nombre,
    required this.detalle,
    this.codigo = '',
    required this.clase,
    required this.recibidos,
    required this.usados,
    required this.unidad,
    this.serie,
    this.ordenesRelacionadas = const <String>[],
    this.razon,
    this.ultimoMovimiento,
    this.series = const <String>[],
    this.instaladas = const <String, SerieInstalada>{},
    this.enManoExacto,
    this.usadoExacto,
    this.recibidoExacto,
  });

  final String categoria;
  final String nombre;
  final String detalle;

  /// El código del catálogo. ES CON LO QUE SE LE HABLA AL SERVIDOR.
  ///
  /// El kit no trae el UUID del material: trae el código, y es lo que ya manda
  /// la cola de movimientos. Vacío sólo en el catálogo de ejemplo, que no pide
  /// nada a nadie.
  final String codigo;
  final ClaseMaterial clase;
  final int recibidos;
  final int usados;

  /// "unidades", "m"…
  final String unidad;

  /// Solo para los serializados.
  final String? serie;

  final List<String> ordenesRelacionadas;
  final String? razon;
  final String? ultimoMovimiento;

  /// Todas las series entregadas de este material. Hasta el 18/10/2026 la
  /// pantalla mostraba solo la primera: con cinco ONT del mismo modelo, se veía
  /// una.
  final List<String> series;

  /// Las que ya se instalaron, por serie: en qué orden, y si ya subió.
  final Map<String, SerieInstalada> instaladas;

  /// Las cantidades exactas: los metros de cable tienen decimales, y los
  /// enteros de arriba los redondean.
  final double? enManoExacto;
  final double? usadoExacto;
  final double? recibidoExacto;

  int get disponibles => recibidos - usados;

  /// Lo que el técnico tiene encima AHORA: el saldo del servidor menos lo que
  /// registró en el teléfono y todavía no subió.
  double get enMano => enManoExacto ?? disponibles.toDouble();
  double get usado => usadoExacto ?? usados.toDouble();
  double get recibido => recibidoExacto ?? recibidos.toDouble();

  /// Las series, con las de ejemplo de antes (una sola) como respaldo.
  List<String> get todasLasSeries =>
      series.isNotEmpty ? series : <String>[?serie];

  /// La clase en la que se resume arriba: equipos, cable u otros.
  ClaseDeResumen get claseDeResumen => switch (clase) {
        ClaseMaterial.serializado => ClaseDeResumen.equipos,
        ClaseMaterial.bobina => ClaseDeResumen.cable,
        _ => ClaseDeResumen.consumibles,
      };

  /// Qué porcentaje del material recibido ya se usó.
  double get consumo => recibidos == 0 ? 0 : usados / recibidos;
}
