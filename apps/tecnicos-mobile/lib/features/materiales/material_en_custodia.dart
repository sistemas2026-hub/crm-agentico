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

class MaterialEnCustodia {
  const MaterialEnCustodia({
    required this.categoria,
    required this.nombre,
    required this.detalle,
    required this.clase,
    required this.recibidos,
    required this.usados,
    required this.unidad,
    this.serie,
    this.ordenesRelacionadas = const <String>[],
    this.razon,
    this.ultimoMovimiento,
  });

  final String categoria;
  final String nombre;
  final String detalle;
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

  int get disponibles => recibidos - usados;

  /// Qué porcentaje del material recibido ya se usó.
  double get consumo => recibidos == 0 ? 0 : usados / recibidos;
}
