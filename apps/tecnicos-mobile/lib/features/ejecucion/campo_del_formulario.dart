/// Un campo del formulario dinámico, ya interpretado.
///
/// POR QUÉ EXISTE
/// --------------
/// Porque había **dos lecturas distintas del mismo campo**, y no coincidían.
///
/// El widget que dibuja el formulario aceptaba `clave` o `id`, y tomaba como
/// obligatorio tanto `obligatorio: true` como `reglas.required: true`. La
/// validación que decide si el trabajo se puede cerrar leía sólo `clave` y
/// `obligatorio`. El servidor manda `id` y `reglas.required`.
///
/// El resultado, en un teléfono real: la pantalla **pintaba** el asterisco
/// rojo y el checklist de cierre **no exigía** el campo. Se podía terminar un
/// trabajo con los obligatorios vacíos. Y las opciones de un campo de
/// selección se leían de `opciones`, que el servidor tampoco manda, así que
/// salía "Sin opciones definidas": un campo obligatorio imposible de
/// responder.
///
/// Los dos defectos son el mismo defecto. Por eso el arreglo no es parchear
/// cada lugar —eso los vuelve a desincronizar en el próximo cambio de
/// esquema— sino que **todos lean esto**: el formulario, el checklist, la
/// validación de cierre y las capturas.
///
/// LOS DOS VOCABULARIOS
/// --------------------
/// El de hoy es el del backend (`campo/services/validador.py`):
///
///     {"id", "titulo", "tipo", "ayuda", "reglas": {"required", "options"}}
///
/// El viejo aparece en órdenes guardadas antes y en algunas pruebas:
///
///     {"clave", "etiqueta", "obligatorio", "opciones"}
///
/// Se entienden los dos, con el nuevo primero. Una orden vieja que ya está en
/// el teléfono tiene que seguir abriéndose: al técnico no se le puede pedir
/// que resincronice para poder trabajar.
library;

/// En qué situación está la respuesta de un campo.
enum EstadoDeCampo {
  /// Todavía no se respondió.
  pendiente,

  /// Tiene un valor y el valor sirve.
  completo,

  /// Hay algo mal: un número fuera del rango que pide el esquema, o un campo
  /// de selección que llegó sin opciones. No es lo mismo que estar vacío, y
  /// se dice distinto.
  error,
}

class CampoDelFormulario {
  const CampoDelFormulario({
    required this.id,
    required this.titulo,
    required this.tipo,
    required this.obligatorio,
    required this.opciones,
    required this.valor,
    required this.estado,
    this.ayuda = '',
    this.unidad = '',
    this.motivoDelError = '',
    this.minimo,
    this.maximo,
  });

  final String id;
  final String titulo;

  /// `texto`, `entero`, `decimal`, `booleano`, `seleccion`, `fecha`… tal como
  /// lo nombra el backend. No se traduce: si aparece uno nuevo, se dibuja como
  /// texto y no se pierde.
  final String tipo;

  final bool obligatorio;

  /// Las opciones, cuando el campo es de selección. Vacío en el resto.
  final List<String> opciones;

  /// Lo respondido hasta ahora. Nulo si no se respondió.
  final dynamic valor;

  final EstadoDeCampo estado;
  final String ayuda;
  final String unidad;

  /// Qué está mal, cuando el estado es `error`. En palabras que se puedan
  /// leer en la calle, no un código.
  final String motivoDelError;

  final double? minimo;
  final double? maximo;

  bool get esSeleccion => tipo == 'seleccion';
  bool get esBooleano => tipo == 'booleano';
  bool get esNumero =>
      tipo == 'decimal' || tipo == 'entero' || tipo == 'numero' ||
      tipo == 'integer';

  /// Si este campo impide dar el trabajo por terminado.
  ///
  /// Un obligatorio sin responder bloquea. Un valor con error bloquea aunque
  /// el campo sea opcional: un número fuera de rango es peor que un vacío,
  /// porque se firma como si fuera una medición buena.
  bool get bloqueaCierre =>
      estado == EstadoDeCampo.error ||
      (obligatorio && estado == EstadoDeCampo.pendiente);

  /// Interpreta un campo del esquema con lo respondido hasta ahora.
  static CampoDelFormulario desdeEsquema(
    Map<String, dynamic> campo,
    Map<String, dynamic> valores,
  ) {
    final Object? reglas = campo['reglas'];
    final Map<String, dynamic> r =
        reglas is Map ? Map<String, dynamic>.from(reglas) : <String, dynamic>{};

    // El id nuevo primero; el viejo `clave` como respaldo.
    final String id = (campo['id'] ?? campo['clave'] ?? '').toString();
    final String titulo =
        (campo['titulo'] ?? campo['etiqueta'] ?? id).toString();
    final String tipo = (campo['tipo'] ?? 'texto').toString();

    final bool obligatorio =
        r['required'] == true || campo['obligatorio'] == true;

    // Las opciones viajan en `reglas.options`; `opciones` es la forma vieja.
    final Object? crudas = r['options'] ?? campo['opciones'];
    final List<String> opciones = <String>[
      if (crudas is List)
        for (final dynamic o in crudas) o.toString(),
    ];

    final dynamic valor = valores[id];
    final bool vacio = valor == null || valor.toString().trim().isEmpty;

    final double? minimo = _decimal(r['min']);
    final double? maximo = _decimal(r['max']);

    // --- El estado, en orden de gravedad ---------------------------------

    // Un campo de selección sin opciones no se puede responder. Es un
    // problema del esquema, no del técnico, y hay que decirlo como tal en vez
    // de dejar un hueco en blanco.
    if (tipo == 'seleccion' && opciones.isEmpty) {
      return CampoDelFormulario(
        id: id,
        titulo: titulo,
        tipo: tipo,
        obligatorio: obligatorio,
        opciones: opciones,
        valor: valor,
        estado: EstadoDeCampo.error,
        ayuda: (campo['ayuda'] ?? '').toString(),
        unidad: (campo['unidad'] ?? '').toString(),
        motivoDelError: 'Este campo llegó sin opciones para elegir. '
            'Avisá a la oficina: la plantilla del trabajo está incompleta.',
        minimo: minimo,
        maximo: maximo,
      );
    }

    EstadoDeCampo estado;
    String motivo = '';

    if (vacio) {
      // Un booleano sin responder es `false`, no un hueco: el interruptor
      // siempre muestra una de las dos posiciones.
      estado = tipo == 'booleano'
          ? EstadoDeCampo.completo
          : EstadoDeCampo.pendiente;
    } else {
      estado = EstadoDeCampo.completo;

      final double? numero = _decimal(valor);
      if ((tipo == 'decimal' || tipo == 'entero') && numero == null) {
        estado = EstadoDeCampo.error;
        motivo = 'Tiene que ser un número.';
      } else if (numero != null && minimo != null && numero < minimo) {
        estado = EstadoDeCampo.error;
        motivo = 'Tiene que ser $minimo o más.';
      } else if (numero != null && maximo != null && numero > maximo) {
        estado = EstadoDeCampo.error;
        motivo = 'Tiene que ser $maximo o menos.';
      } else if (tipo == 'seleccion' &&
          opciones.isNotEmpty &&
          !opciones.contains(valor.toString())) {
        estado = EstadoDeCampo.error;
        motivo = 'Esa opción ya no está en la lista.';
      }
    }

    return CampoDelFormulario(
      id: id,
      titulo: titulo,
      tipo: tipo,
      obligatorio: obligatorio,
      opciones: opciones,
      valor: valor,
      estado: estado,
      ayuda: (campo['ayuda'] ?? '').toString(),
      unidad: (campo['unidad'] ?? '').toString(),
      motivoDelError: motivo,
      minimo: minimo,
      maximo: maximo,
    );
  }

  /// Interpreta la lista entera del esquema.
  ///
  /// Lo que no sea un mapa se descarta en silencio: un esquema corrupto no
  /// puede tumbar la pantalla con la que alguien está trabajando.
  static List<CampoDelFormulario> normalizar(
    List<dynamic> campos,
    Map<String, dynamic> valores,
  ) =>
      <CampoDelFormulario>[
        for (final dynamic campo in campos)
          if (campo is Map)
            desdeEsquema(Map<String, dynamic>.from(campo), valores),
      ];

  static double? _decimal(Object? valor) {
    if (valor == null) return null;
    if (valor is num) return valor.toDouble();
    return double.tryParse(valor.toString().trim());
  }
}
