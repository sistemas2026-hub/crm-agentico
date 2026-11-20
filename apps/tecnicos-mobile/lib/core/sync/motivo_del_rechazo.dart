/// Qué dijo el servidor cuando rechazó un cambio, en una frase que se pueda leer.
///
/// EL DEFECTO QUE ESTO CIERRA  --  10/11/2026, reportado por el usuario:
/// «los cambios no se envían desde la app, quedan ahí acumulándose», con la
/// pastilla diciendo «9 cambios necesitan que alguien lo revise» y el foquito
/// de red en verde.
///
/// No era la red ni el envío: la cola se disparaba bien. Eran rechazos del
/// servidor que quedan fuera del reintento a propósito (un 400 de validación
/// y un 409 de concurrencia no se arreglan repitiéndolos). El servidor dice
/// EXACTAMENTE qué está mal —qué campo no existe en la plantilla, en qué
/// campos chocó la revisión— y la app leía DOS CLAVES QUE NO EXISTEN:
///
///     400  el servidor manda  {"guardado": false, "errores": {...}}
///          la app leía        data['error']            -> null
///     409  el servidor manda  {"error": "...", "detalle": "campos: [...]"}
///          la app leía        data['code']             -> null
///
/// En los dos casos el `?? ` de respaldo tapaba el hueco con el mensaje
/// genérico de Dio o con la palabra `STALE_WORK_ORDER`, así que el motivo
/// real se perdía en la línea que lo recibía. Por eso «repetí el proceso y
/// sigue igual» no tenía ninguna pista a la que agarrarse.
///
/// POR QUE VIVE EN SU PROPIO ARCHIVO, con una función pura: para que su
/// prueba corra sin levantar la base, la sesión ni la red. Es la misma razón
/// que `una_pasada_a_la_vez.dart`, y es lo que hace que la guarda sirva de
/// guarda: las formas de abajo son las del servidor REAL, leídas de
/// `campo/views.py` y `campo/services/validador.py`, y si alguna cambia la
/// prueba se pone roja acá y no en el teléfono de un técnico.
library;

/// Lo más largo que se guarda. Un mensaje no es un informe: entra en la
/// pantalla de un teléfono, y la base local no es el lugar de un volcado.
const int _topeDeTexto = 400;

/// Las formas en que este backend dice «no» (medidas el 10/11/2026).
///
/// - `errores` como MAPA, campo -> frase. Lo devuelve
///   `validar_campos_tecnicos`: `{"guardado": false, "errores": {"potencia":
///   "El campo 'potencia' no existe en la plantilla de este trabajo."}}`.
/// - `errores` como LISTA de objetos con `mensaje`. Lo devuelve
///   `verificar_checklist_completo`: `[{"codigo": "CAMPO_FALTANTE",
///   "campo_id": "firma", "mensaje": "..."}]`.
/// - `error` + `detalle`, del 409 de concurrencia: `{"error":
///   "STALE_WORK_ORDER", "detalle": "Conflicto de concurrencia en campos:
///   ['potencia']. ..."}`.
/// - Lo plano de DRF, cuando el serializer corta antes de llegar a la vista:
///   `{"revision_base": ["This field is required."]}`.
///
/// [respaldo] es lo que se guarda si el cuerpo no dice nada útil — el mensaje
/// de Dio, que al menos distingue un timeout de un rechazo.
String motivoDelRechazo(Object? cuerpo, {String? respaldo}) {
  final String? leido = _leer(cuerpo);
  final String elegido = (leido != null && leido.trim().isNotEmpty)
      ? leido.trim()
      : (respaldo ?? '').trim();
  if (elegido.isEmpty) return 'El servidor rechazó el cambio sin decir por qué.';
  return elegido.length <= _topeDeTexto
      ? elegido
      : '${elegido.substring(0, _topeDeTexto - 1)}…';
}

String? _leer(Object? cuerpo) {
  if (cuerpo is String) return cuerpo;
  if (cuerpo is! Map) return null;

  //  `errores` primero: es la única forma que nombra EL CAMPO, y el campo es
  //  lo que el técnico necesita para arreglarlo.
  final Object? errores = cuerpo['errores'];
  final String? deErrores = _deLaColeccion(errores);
  if (deErrores != null) return deErrores;

  //  El 409: `detalle` es la frase con los campos que chocaron; `error` es el
  //  código. Se prefiere el detalle, y si no hay, el código solo.
  final Object? detalle = cuerpo['detalle'];
  if (detalle is String && detalle.trim().isNotEmpty) return detalle;
  final String? delDetalle = _deLaColeccion(detalle);
  if (delDetalle != null) return delDetalle;

  final Object? error = cuerpo['error'];
  if (error is String && error.trim().isNotEmpty) return error;
  final String? delError = _deLaColeccion(error);
  if (delError != null) return delError;

  //  Lo plano de DRF. Se saltean las claves que no son del rechazo para que
  //  un `{"guardado": false}` no se lea como un motivo.
  final List<String> partes = <String>[];
  for (final MapEntry<Object?, Object?> e in cuerpo.entries) {
    final String clave = e.key?.toString() ?? '';
    if (clave.isEmpty || _noSonMotivo.contains(clave)) continue;
    final String? dicho = _deLaColeccion(e.value) ??
        (e.value is String ? e.value as String : null);
    if (dicho == null || dicho.trim().isEmpty) continue;
    partes.add('$clave: ${dicho.trim()}');
  }
  return partes.isEmpty ? null : partes.join(' · ');
}

/// Claves que acompañan un rechazo sin ser el motivo. Si se leyeran, un
/// `{"guardado": false}` produciría «guardado: false», que no le dice nada a
/// nadie.
const Set<String> _noSonMotivo = <String>{
  'guardado', 'aplicada', 'revision', 'revision_actual', 'server_time',
  'mutation_id', 'estado_operativo', 'code',
};

/// Un mapa campo -> frase, o una lista de frases u objetos con `mensaje`.
String? _deLaColeccion(Object? valor) {
  if (valor is Map) {
    final List<String> partes = <String>[];
    for (final MapEntry<Object?, Object?> e in valor.entries) {
      final String? frase = _unaFrase(e.value);
      if (frase == null) continue;
      final String clave = e.key?.toString() ?? '';
      //  La frase de este backend YA NOMBRA el campo («El campo 'x' no
      //  existe…»), así que repetir la clave delante diría el nombre dos
      //  veces. Solo se antepone cuando la frase no lo trae.
      partes.add(
        clave.isEmpty || frase.contains(clave) ? frase : '$clave: $frase',
      );
    }
    return partes.isEmpty ? null : partes.join(' · ');
  }
  if (valor is List) {
    final List<String> partes = <String>[];
    for (final Object? item in valor) {
      final String? frase = _unaFrase(item);
      if (frase != null) partes.add(frase);
    }
    return partes.isEmpty ? null : partes.join(' · ');
  }
  return null;
}

/// Una frase, venga como texto, como lista de textos (DRF) o como el objeto
/// `{"codigo":…, "campo_id":…, "mensaje":…}` del checklist.
String? _unaFrase(Object? valor) {
  if (valor is String) return valor.trim().isEmpty ? null : valor.trim();
  if (valor is List) {
    final List<String> dichas = <String>[];
    for (final Object? v in valor) {
      final String? f = _unaFrase(v);
      if (f != null) dichas.add(f);
    }
    return dichas.isEmpty ? null : dichas.join(' ');
  }
  if (valor is Map) {
    final Object? mensaje = valor['mensaje'] ?? valor['detail'] ?? valor['msg'];
    if (mensaje is String && mensaje.trim().isNotEmpty) return mensaje.trim();
    return null;
  }
  return null;
}
