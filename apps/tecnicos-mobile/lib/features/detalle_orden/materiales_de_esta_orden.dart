import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';

/// Qué material tocó **esta** orden.
///
/// LO QUE NO SE MEZCLA, Y ES TODO EL SENTIDO DEL ARCHIVO
/// ----------------------------------------------------
/// El kit de la jornada —que esta app ya muestra en su propia pantalla— es lo
/// que el técnico lleva encima para todo el día: 150 m de drop, diez conectores,
/// dos ONT. Con eso hace cinco instalaciones.
///
/// Esto es otra cosa: lo que pasó en **un** trabajo. Si los dos números se
/// mostraran juntos, la ficha diría que en una casa se usaron 150 m cuando se
/// usaron 37,5.
///
/// El backend ya resolvió esa separación y manda los bloques con el nombre de lo
/// que cada dato es —`comprometido`, `consumido`, `devuelto`, `otros`—. Acá no
/// se suma, no se cruza y no se calcula: se dibuja. La existencia sale del libro
/// de movimientos, y una suma en esta pantalla sería una segunda contabilidad.
class MaterialesDeEstaOrden extends StatelessWidget {
  const MaterialesDeEstaOrden({
    super.key,
    required this.materiales,
    required this.cargando,
    this.alAgregar,
  });

  /// Qué hacer cuando el técnico anota lo que gastó.
  ///
  /// POR QUE EL GESTO VIVE ACA, Y NO SOLO EN LA PANTALLA DE EJECUCION
  /// ---------------------------------------------------------------
  /// El registro de consumo existe desde antes y está bien resuelto —atado a la
  /// orden, sin señal, con el disponible leído de la base local—. Pero vive
  /// detrás de «Ejecutar el trabajo», y esta sección es donde el técnico está
  /// mirando qué se usó. Ver «37,5 m» y no tener cómo anotar el conector que
  /// acaba de poner es el camino corto a que no lo anote, y entonces el
  /// inventario se corrige a fin de mes de memoria.
  ///
  /// No es un flujo nuevo: abre el mismo que ya existía. `null` deja la sección
  /// en lectura.
  final VoidCallback? alAgregar;

  /// Lo que devolvió el backend, o `null` si **nunca se descargó** acá.
  ///
  /// `null` no es «no se usó material»: es «no se sabe». Una lista vacía diría
  /// lo primero, y sería falso.
  final Map<String, dynamic>? materiales;

  final bool cargando;

  /// Los cuatro bloques, en el orden en que se leen, con lo que cada uno
  /// significa. El pie existe para que nadie tenga que adivinarlo.
  static const List<(String, String, String)> _bloques =
      <(String, String, String)>[
        (
          'comprometido',
          'Reservado para esta orden',
          'Lo único que de verdad está asignado a este trabajo.',
        ),
        ('consumido', 'Usado en esta orden', ''),
        ('devuelto', 'Devuelto', ''),
        (
          'otros',
          'Otros movimientos',
          'Ajustes, traslados y bajas atados a esta orden.',
        ),
      ];

  @override
  Widget build(BuildContext context) {
    return DexterBloque(
      titulo: 'Material de esta orden',
      icono: Icons.inventory_2_outlined,
      children: _cuerpo(),
    );
  }

  List<Widget> _cuerpo() {
    if (cargando && materiales == null) {
      return <Widget>[
        Text(
          'Buscando el material de este trabajo…',
          style: AppTypography.cuerpoChico,
        ),
      ];
    }

    if (materiales == null) {
      return <Widget>[
        Text(
          'El material de esta orden todavía no está disponible en este '
          'dispositivo.',
          style: AppTypography.cuerpo,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Que no esté acá no quiere decir que no se haya usado nada.',
          style: AppTypography.cuerpoChico,
        ),
        // Se puede anotar igual. No saber qué hay en el servidor no impide
        // registrar lo que uno acaba de usar, y es justo cuando el técnico está
        // sin señal: si el botón desapareciera ahí, desaparecería cuando más
        // falta hace.
        ..._accionDeAgregar(),
      ];
    }

    final int conNovedad = (materiales!['con_novedad'] as int?) ?? 0;
    final bool hayAlgo = materiales!['hay_algo'] == true;

    return <Widget>[
      if (conNovedad > 0) ...<Widget>[
        DexterPastilla.alerta(
          texto: conNovedad == 1
              ? '1 movimiento con novedad'
              : '$conNovedad movimientos con novedad',
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Un descuadre o un conflicto quedó registrado. El hecho se respeta: '
          'lo mira alguien de bodega.',
          style: AppTypography.cuerpoChico,
        ),
        const SizedBox(height: AppSpacing.xs),
      ],

      if (!hayAlgo)
        Text(
          'Todavía no hay material reservado ni usado en esta orden.',
          style: AppTypography.cuerpoChico,
        ),

      for (final (String clave, String titulo, String pie) bloque in _bloques)
        ..._bloque(bloque.$1, bloque.$2, bloque.$3),

      // El kit del día se menciona pero NO se muestra acá: tiene su propia
      // pantalla, y traerlo a la ficha de un trabajo es lo que hace que alguien
      // lea «150 m» como gastados en una casa.
      const SizedBox(height: AppSpacing.xs),
      Text(
        'Lo que llevás encima para toda la jornada se ve en Materiales.',
        style: AppTypography.etiquetaChica,
      ),

      ..._accionDeAgregar(),
    ];
  }

  List<Widget> _accionDeAgregar() {
    if (alAgregar == null) {
      return const <Widget>[];
    }
    return <Widget>[
      const SizedBox(height: AppSpacing.sm),
      DexterAccionRapida(
        texto: 'Anotar lo que usé',
        icono: Icons.add,
        alTocar: alAgregar,
      ),
    ];
  }

  List<Widget> _bloque(String clave, String titulo, String pie) {
    final List<dynamic> filas =
        (materiales![clave] as List<dynamic>?) ?? const <dynamic>[];
    if (filas.isEmpty) {
      return const <Widget>[];
    }

    return <Widget>[
      const SizedBox(height: AppSpacing.sm),
      Text(titulo, style: AppTypography.etiqueta),
      for (final dynamic cruda in filas)
        if (cruda is Map) _fila(Map<String, dynamic>.from(cruda)),
      if (pie.isNotEmpty) ...<Widget>[
        const SizedBox(height: 2),
        Text(pie, style: AppTypography.etiquetaChica),
      ],
    ];
  }

  Widget _fila(Map<String, dynamic> linea) {
    final Map<String, dynamic> material =
        (linea['material'] as Map<String, dynamic>?) ?? <String, dynamic>{};
    final String codigo = (material['codigo'] ?? '').toString();
    final String nombre = (material['nombre'] ?? '').toString();
    final String unidad = (material['unidad'] ?? '').toString();
    final String cantidad = (linea['cantidad'] ?? '').toString();
    final String serie = (linea['serie'] ?? '').toString();
    final String estado = (linea['estado'] ?? '').toString();
    final bool pendiente = linea['pendiente'] == true;
    final String desenlace = (linea['desenlace'] ?? '').toString();

    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  nombre.isEmpty ? codigo : '$codigo · $nombre',
                  style: AppTypography.cuerpoChico,
                ),
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                '${_legible(cantidad)} $unidad'.trim(),
                style: AppTypography.etiqueta,
              ),
            ],
          ),
          if (serie.isNotEmpty)
            Text('Serie: $serie', style: AppTypography.etiquetaChica),
          // Un descuadre o un conflicto no se esconde: es lo que alguien tiene
          // que mirar, y una pantalla que solo muestra lo que cuadra no sirve
          // para averiguar por qué no cuadra.
          if (estado.isNotEmpty && estado != 'aceptado')
            DexterPastilla.alerta(texto: estado),
          if (linea.containsKey('pendiente'))
            Text(
              pendiente ? 'Pendiente' : (desenlace.isEmpty ? '' : desenlace),
              style: AppTypography.etiquetaChica,
            ),
        ],
      ),
    );
  }

  /// `37.500` → `37,5`. Lo que manda el servidor trae los tres decimales de la
  /// columna; en un teléfono eso es ruido.
  static String _legible(String cantidad) {
    if (!cantidad.contains('.')) {
      return cantidad;
    }
    final double? n = double.tryParse(cantidad);
    if (n == null) {
      return cantidad;
    }
    final String texto = n == n.roundToDouble()
        ? n.toStringAsFixed(0)
        : n.toString().replaceAll(RegExp(r'0+$'), '');
    return texto.replaceAll('.', ',');
  }
}
