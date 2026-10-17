/// ============================================================================
///  UN INSTANTE QUE VINO DE AFUERA, Y SI SABE EN QUE ZONA ESTABA
/// ============================================================================
///
/// POR QUE ESTO EXISTE
/// -------------------
/// `DateTime.parse('2026-08-15 18:00:25')` no falla: devuelve un instante y lo
/// trata como hora LOCAL del teléfono. `DateTime.parse('...Z')` lo trata como
/// UTC. Las dos formas llegan a esta aplicación por el mismo campo, y el
/// resultado se diferencia en cinco horas sin que nada avise.
///
/// Eso ya costó una conclusión equivocada el 15/08/2026: se comparó un
/// `last_status_change` de las 18:00 contra timestamps de la base (UTC, 23:0x)
/// y se dio por sentado que el reinicio había sido *horas antes*. Eran cinco
/// minutos. Con eso se descartó por error la causa real de un caso en rojo.
///
/// SmartOLT manda ese campo en hora local de su instancia y **sin offset**
/// (`get_onu_status`), mientras otro endpoint del mismo proveedor manda el
/// mismo instante **con** offset. No es un descuido de un endpoint: son dos
/// contratos distintos del mismo dato, y la aplicación recibe los dos.
///
/// LA REGLA
/// --------
/// Un instante sin zona no se convierte, no se compara contra el reloj del
/// teléfono y no se le calcula una antigüedad. Se muestra tal como vino y se
/// dice de quién es esa hora. Inventarle una zona es exactamente el error que
/// este archivo existe para que no se repita — y dos de los nueve parseos que
/// había en la aplicación lo hacían en silencio.
library;

/// Qué se sabe de la zona horaria del instante que llegó.
enum ZonaDelMomento {
  /// El texto traía offset (`Z`, `-05:00`): el instante es inequívoco y se
  /// puede convertir, comparar y restar.
  declarada,

  /// El texto no traía nada. Los números son la hora de **quien la escribió**,
  /// y no se sabe cuánto hay que correrlos.
  ausente,
}

/// Un instante leído de un sistema externo, con lo que se sabe de su zona.
///
/// La diferencia con un `DateTime` pelado es que este tipo **no se puede usar
/// sin decidir qué hacer con la ambigüedad**: el llamador tiene que mirar
/// [zona], y por eso el error de las cinco horas no vuelve a pasar por
/// distracción.
class MomentoLeido {
  const MomentoLeido({required this.cuando, required this.zona});

  /// El instante. Cuando [zona] es [ZonaDelMomento.declarada] está convertido
  /// a la hora del dispositivo; cuando es [ZonaDelMomento.ausente] son los
  /// números tal como vinieron, sin corrimiento.
  final DateTime cuando;

  /// Si el texto de origen decía en qué zona estaba.
  final ZonaDelMomento zona;

  /// Si se puede comparar contra el reloj del teléfono sin mentir.
  bool get sePuedeComparar => zona == ZonaDelMomento.declarada;

  /// Lee un instante de un valor cualquiera, sin asumirle una zona.
  ///
  /// Devuelve `null` cuando no hay nada que leer — ausente, vacío o ilegible.
  /// Un valor ilegible y un valor ausente se tratan igual a propósito: en los
  /// dos casos lo honesto es no dibujar una hora.
  static MomentoLeido? desde(Object? valor) {
    final String texto = (valor ?? '').toString().trim();
    if (texto.isEmpty) return null;

    final DateTime? leido = DateTime.tryParse(texto);
    if (leido == null) return null;

    if (_declaraZona(texto)) {
      return MomentoLeido(
        cuando: leido.toLocal(),
        zona: ZonaDelMomento.declarada,
      );
    }
    // Sin zona NO se llama a toLocal(): `DateTime.tryParse` ya lo devolvió
    // como hora local del dispositivo, y convertirlo otra vez lo correría de
    // nuevo. Los números quedan como vinieron, que es lo único cierto.
    return MomentoLeido(cuando: leido, zona: ZonaDelMomento.ausente);
  }

  /// Si el texto ISO-8601 trae designador de zona.
  ///
  /// Se mira **solo la parte de la hora**: un `-` de la fecha
  /// (`2026-08-15`) no es un offset, y buscar el guión en todo el texto daría
  /// por declarada cualquier fecha. Por eso se parte en la `T` o el espacio
  /// que separa fecha de hora, igual que ISO-8601.
  static bool _declaraZona(String texto) {
    final int corte = texto.indexOf(RegExp(r'[T ]'));
    if (corte < 0) {
      // Solo fecha (`2026-08-15`): no hay hora, así que no hay zona que
      // declarar. Se trata como ausente para no afirmar una medianoche.
      return false;
    }
    final String hora = texto.substring(corte + 1);
    return hora.contains('Z') ||
        hora.contains('z') ||
        hora.contains('+') ||
        hora.contains('-');
  }
}
