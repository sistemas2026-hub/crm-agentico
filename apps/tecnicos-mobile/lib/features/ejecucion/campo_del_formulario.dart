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

/// Un dato YA medido que se muestra junto a un campo, para comparar.
///
/// QUE ES Y QUE NO
/// ---------------
/// No es una respuesta: no se guarda, no se valida y no bloquea nada. Es lo
/// que el sistema ya sabía cuando se despachó la orden, puesto al lado del
/// lugar donde el técnico anota lo que midió él.
///
/// El caso que lo trajo: el técnico mide con el power meter en la casa y la
/// OLT ya tenía su propia lectura de la misma señal. Las dos sirven, y sirven
/// MAS juntas -- si difieren mucho, el problema está entre la central y el
/// equipo. Tenerlas en dos pantallas distintas obligaba a memorizar un número
/// y volver.
///
/// QUE CAMPO SE MUESTRA LO DICE LA PLANTILLA
/// -----------------------------------------
/// La plantilla declara las rutas dentro del contexto de la orden
/// (`equipo.onu_signal_1490`, `capturado_en`), así que este código no conoce
/// ningún nombre de SmartOLT ni de ninguna empresa. Otro ISP que congele otra
/// lectura la nombra en su plantilla y funciona igual.
class ReferenciaDeFicha {
  const ReferenciaDeFicha({
    required this.titulo,
    required this.valor,
    this.veredicto = '',
    this.medidaEn,
  });

  final String titulo;

  /// El valor, tal como lo congeló la ficha. No se reformatea: si SmartOLT
  /// manda '-21.19 dBm' como texto, eso se ve.
  final String valor;

  /// El veredicto que ya trae calculado, si la plantilla lo nombró. Vacío
  /// cuando no hay -- y entonces no se inventa ninguno.
  final String veredicto;

  /// Cuándo se congeló. Va siempre con el valor: una medición sin su hora se
  /// lee como la señal de ahora, y no lo es.
  final DateTime? medidaEn;

  /// Arma la referencia que declara la plantilla, con lo que trae la ficha.
  ///
  /// Devuelve nulo si no hay lectura. Sin dato no se dibuja un hueco ni un
  /// guion: la ficha puede venir sin equipo, y decirlo es cosa de la pantalla
  /// de detalle, que ya lo hace.
  static ReferenciaDeFicha? desde(Object? declarada, Map<String, dynamic> ficha) {
    if (declarada is! Map) return null;

    final String valor = _enRuta(ficha, (declarada['valor'] ?? '').toString());
    if (valor.trim().isEmpty) return null;

    final String cuando =
        _enRuta(ficha, (declarada['medida_en'] ?? '').toString());

    return ReferenciaDeFicha(
      titulo: (declarada['titulo'] ?? '').toString(),
      valor: valor,
      veredicto: _enRuta(ficha, (declarada['veredicto'] ?? '').toString()),
      medidaEn: DateTime.tryParse(cuando)?.toLocal(),
    );
  }

  /// Sigue una ruta con puntos dentro de un mapa anidado.
  static String _enRuta(Map<String, dynamic> raiz, String ruta) {
    if (ruta.isEmpty) return '';
    Object? actual = raiz;
    for (final String paso in ruta.split('.')) {
      if (actual is Map && actual[paso] != null) {
        actual = actual[paso];
      } else {
        return '';
      }
    }
    return actual?.toString() ?? '';
  }
}

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
    this.referencia,
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

  /// Lo que la ficha ya sabía de esto, si la plantilla lo pidió. Se muestra
  /// arriba del campo; no se guarda ni valida.
  final ReferenciaDeFicha? referencia;

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
    Map<String, dynamic> valores, {
    Map<String, dynamic> ficha = const <String, dynamic>{},
  }) {
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

    // La referencia viaja FUERA de 'reglas' a proposito: 'reglas' es el
    // vocabulario cerrado que valida el backend, y esto no valida nada.
    final ReferenciaDeFicha? referencia =
        ReferenciaDeFicha.desde(campo['referencia'], ficha);

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
        referencia: referencia,
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
      referencia: referencia,
    );
  }

  static List<CampoDelFormulario> normalizar(
    List<dynamic> campos,
    Map<String, dynamic> valores, {
    Map<String, dynamic> ficha = const <String, dynamic>{},
  }) =>
      <CampoDelFormulario>[
        for (final dynamic campo in campos)
          if (campo is Map)
            desdeEsquema(Map<String, dynamic>.from(campo), valores,
                ficha: ficha),
      ];

  static double? _decimal(Object? valor) {
    if (valor == null) return null;
    if (valor is num) return valor.toDouble();
    return double.tryParse(valor.toString().trim());
  }
}
