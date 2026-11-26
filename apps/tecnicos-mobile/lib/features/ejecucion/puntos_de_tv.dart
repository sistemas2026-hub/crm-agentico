/// LA CUENTA DEL MATERIAL DE TV (26/11/2026).
///
/// El usuario: «1 punto de TV lleva 2 conectores coaxiales; 2 puntos, 6
/// conectores y un spliter de dos; debe tener en cuenta qué material tiene
/// asignado el técnico para ver qué spliter utilizar; y sigue sumando la
/// cantidad de material a medida que instale, como máximo 5». Para 3 a 5
/// eligió: 2 por punto + 2 de entrada.
///
/// Los números y los materiales son de la empresa y llegan con la orden
/// (`tipo.puntos_de_tv`, ver `campo/puntos_de_tv.py`). Acá solo se cuenta, sin
/// pantalla, para poder probar la regla sola.
library;

/// Un material de la cuenta.
class MaterialDeLaCuenta {
  const MaterialDeLaCuenta({required this.codigo, required this.nombre, this.salidas});
  final String codigo;
  final String nombre;

  /// Solo en un spliter.
  final int? salidas;
}

/// Lo que llevan N puntos de TV.
class CuentaDeTv {
  const CuentaDeTv({
    required this.puntos,
    required this.conectores,
    this.spliter,
    this.spliterEnElKit = false,
    this.ningunSpliterAlcanza = false,
  });

  final int puntos;
  final int conectores;

  /// El spliter que va: el más chico que alcance entre los que el técnico
  /// tiene; si no tiene ninguno que alcance, el más chico de la empresa que
  /// alcance (y `spliterEnElKit` lo dice). Nulo con un solo punto.
  final MaterialDeLaCuenta? spliter;
  final bool spliterEnElKit;

  /// Ningún spliter de la empresa tiene salidas para tantos puntos.
  final bool ningunSpliterAlcanza;
}

int _entero(dynamic v, int porDefecto) => int.tryParse('${v ?? ''}') ?? porDefecto;

double _disponible(List<Map<String, dynamic>> kit, String codigo) {
  for (final Map<String, dynamic> k in kit) {
    if (k['codigo'] == codigo) return double.tryParse('${k['disponible'] ?? ''}') ?? 0;
  }
  return 0;
}

/// Los spliters de la empresa, del más chico al más grande.
List<MaterialDeLaCuenta> spliteresDe(Map<String, dynamic> config) {
  final List<MaterialDeLaCuenta> s = <MaterialDeLaCuenta>[
    for (final dynamic x in (config['spliters'] as List? ?? const <dynamic>[]))
      if (x is Map && (x['codigo'] ?? '').toString().isNotEmpty)
        MaterialDeLaCuenta(
          codigo: x['codigo'].toString(),
          nombre: (x['nombre'] ?? x['codigo']).toString(),
          salidas: _entero(x['salidas'], 0),
        ),
  ]..sort((MaterialDeLaCuenta a, MaterialDeLaCuenta b) => a.salidas!.compareTo(b.salidas!));
  return s;
}

/// Cuánto lleva [puntos] puntos de TV, con el kit del técnico delante.
CuentaDeTv cuentaDeTv({
  required Map<String, dynamic> config,
  required int puntos,
  required List<Map<String, dynamic>> kit,
}) {
  final int porPunto = _entero(config['conectores_por_punto'], 2);
  final int entrada = _entero(config['conectores_de_entrada'], 2);
  //  Con un solo punto no hay spliter, y por eso tampoco cable de entrada.
  final int conectores = puntos <= 0 ? 0 : porPunto * puntos + (puntos >= 2 ? entrada : 0);
  if (puntos < 2) return CuentaDeTv(puntos: puntos, conectores: conectores);

  final List<MaterialDeLaCuenta> alcanzan = spliteresDe(config)
      .where((MaterialDeLaCuenta s) => s.salidas! >= puntos)
      .toList();
  if (alcanzan.isEmpty) {
    return CuentaDeTv(puntos: puntos, conectores: conectores, ningunSpliterAlcanza: true);
  }
  final MaterialDeLaCuenta? enElKit = alcanzan
      .where((MaterialDeLaCuenta s) => _disponible(kit, s.codigo) > 0)
      .firstOrNull;
  return CuentaDeTv(
    puntos: puntos,
    conectores: conectores,
    spliter: enElKit ?? alcanzan.first,
    spliterEnElKit: enElKit != null,
  );
}
