/// ============================================================================
///  COMO SE ESCRIBE UNA HORA QUE EL TECNICO VA A USAR PARA DECIDIR
/// ============================================================================
///
/// Una hora sola —`08:17`— se lee como de hoy. Siempre. Si la lectura es de
/// ayer, el técnico decide con un dato que cree fresco, y eso es peor que no
/// mostrarle nada: una hora sin su día es una afirmación sobre el presente que
/// nadie puede verificar.
///
/// Por eso acá el día **nunca se esconde cuando no es hoy**, y una hora cuya
/// zona no se conoce ([ZonaDelMomento.ausente]) no recibe ni «hoy» ni «ayer»
/// ni una antigüedad: esas tres cosas son comparaciones contra el reloj del
/// teléfono, y compararlas sería inventarle la zona que no trajo.
library;

import 'momento_leido.dart';

/// Los meses, en tres letras y en español.
///
/// Sin `intl`: la aplicación no carga localizaciones hoy, y un formato de
/// fecha es lo último que justifica meter una dependencia nueva en un paquete
/// que tiene que compilar para campo. Doce cadenas no se desactualizan.
const List<String> _meses = <String>[
  'ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
];

String _dosDigitos(int n) => n.toString().padLeft(2, '0');

String _hhmm(DateTime f) => '${_dosDigitos(f.hour)}:${_dosDigitos(f.minute)}';

String _diaYMes(DateTime f) => '${_dosDigitos(f.day)} ${_meses[f.month - 1]}';

/// Cómo se escribe [momento] para que no se pueda leer como otra cosa.
///
/// - Hoy → `hoy 08:17`
/// - Ayer → `ayer 08:17`
/// - Antes → `05 oct · 08:17`
/// - Sin zona → `05 oct · 18:00`, siempre con fecha y nunca con «hoy»
///
/// [ahora] se pasa explícitamente, no se lee del reloj acá: así una prueba
/// puede fijar el día y afirmar sobre el EFECTO —que un instante de ayer se
/// escribe distinto a uno de hoy— en vez de sobre la existencia del formato.
///
/// [origen] es de quién es esa hora (`la OLT`). Solo se agrega cuando la zona
/// no vino declarada, que es justo cuando el lector necesita saber que esos
/// números son el reloj de otro sistema y no el suyo.
String textoDelMomento(
  MomentoLeido momento, {
  required DateTime ahora,
  String origen = '',
}) {
  final DateTime f = momento.cuando;

  if (!momento.sePuedeComparar) {
    // Sin zona no hay «hoy»: se escribe completa, y se dice de quién es el
    // reloj. Mostrar `18:00` a secas acá es exactamente el error de 2026.
    final String base = '${_diaYMes(f)} · ${_hhmm(f)}';
    return origen.isEmpty ? base : '$base (hora de $origen)';
  }

  final DateTime hoy = DateTime(ahora.year, ahora.month, ahora.day);
  final DateTime dia = DateTime(f.year, f.month, f.day);
  final int diferencia = hoy.difference(dia).inDays;

  if (diferencia == 0) return 'hoy ${_hhmm(f)}';
  if (diferencia == 1) return 'ayer ${_hhmm(f)}';
  // Más de un día, o una fecha futura (reloj del teléfono atrasado, pasa en
  // campo): en los dos casos la fecha completa es la que no engaña.
  return '${_diaYMes(f)} · ${_hhmm(f)}';
}

/// Lo mismo, partiendo del valor crudo. Devuelve `''` cuando no hay nada que
/// escribir, para que la pantalla no tenga que decidir qué hacer con un hueco.
String textoDelMomentoCrudo(
  Object? valor, {
  required DateTime ahora,
  String origen = '',
}) {
  final MomentoLeido? m = MomentoLeido.desde(valor);
  if (m == null) return '';
  return textoDelMomento(m, ahora: ahora, origen: origen);
}
