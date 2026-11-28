/// Cuándo vence el compromiso de una orden, dicho como en Programación
/// (29/10/2026, el usuario: «la tarjeta quedó bien, ¿en la app debe salir así
/// también?»): «Vence hoy», «Vence mañana», «Vence el 31/10», «Venció el
/// 28/10». La regla es la de la web (`dia-publicado.js::vencimiento`).
///
/// Se compara el DÍA, no la hora: lo que el técnico decide con esto es si la
/// orden se hace hoy, y «vence en 7 h 12 min» no le dice eso mejor.
enum TonoDeVencimiento { vencida, hoy, proxima }

class Vencimiento {
  const Vencimiento(this.texto, this.tono);

  final String texto;
  final TonoDeVencimiento tono;

  /// El vencimiento contra el día de `hoy`; null si la orden no tiene: no se
  /// inventa.
  static Vencimiento? de(DateTime? vence, DateTime hoy) {
    if (vence == null) return null;
    final DateTime v = vence.toLocal();
    // En UTC para que un cambio de hora no deje un día de 23 horas.
    final int dias = DateTime.utc(
      v.year,
      v.month,
      v.day,
    ).difference(DateTime.utc(hoy.year, hoy.month, hoy.day)).inDays;
    final String corta =
        '${v.day.toString().padLeft(2, '0')}/${v.month.toString().padLeft(2, '0')}';
    if (dias < 0) {
      return Vencimiento('Venció el $corta', TonoDeVencimiento.vencida);
    }
    if (dias == 0) return const Vencimiento('Vence hoy', TonoDeVencimiento.hoy);
    if (dias == 1) {
      return const Vencimiento('Vence mañana', TonoDeVencimiento.proxima);
    }
    return Vencimiento('Vence el $corta', TonoDeVencimiento.proxima);
  }
}
