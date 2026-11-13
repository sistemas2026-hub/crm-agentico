import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';

/// Con cuántas órdenes arrancó el día, como hecho y no como deducción.
///
/// POR QUÉ ESTO EXISTE  --  11/11/2026
///
/// La pantalla de inicio decía **«2 asignadas · arrancó con 38»**. El 38 era
/// `trabajos.length`: todo el historial que el teléfono descargó, las 36
/// cerradas de días anteriores incluidas. Se intentó derivar el número del día
/// de tres formas —filtrando por `completadaEn`, por estado, por fecha de
/// despacho— y las tres eran una suposición sobre un dato que puede faltar:
/// **una orden cerrada hace un minuto todavía no trae su fecha de cierre**.
/// Antes que adivinar una cuarta vez, el número se retiró.
///
/// Sellarlo lo saca del terreno de la deducción: el día tuvo tantas, se
/// escribe una vez y se lee.
///
/// LO QUE SE MUESTRA SALE DEL SELLO, NO DE LAS FECHAS, y eso es el punto:
///
///     asignadas    = las que siguen abiertas         (un hecho, hoy)
///     arrancó con  = el sello                        (un hecho, escrito)
///     lleva hechas = sello - abiertas                (resta, sin fechas)
///
/// Ninguna de las tres necesita saber cuándo se cerró una orden, que es
/// justamente el dato que no siempre está. La fecha de cierre se sigue usando
/// para UNA cosa —alimentar el sello hacia arriba cuando el teléfono se abre
/// por primera vez a media mañana— y ahí no puede hacer daño: si falta, el
/// sello sube igual en cuanto esa orden aparezca contada como abierta.
///
/// FALLA EN SILENCIO Y DEVUELVE `null`. Sin sesión, sin base o con un error
/// de SQLite no hay nota en la pantalla, que es exactamente como estaba antes
/// de esto. Una cifra sobre el día no justifica una pantalla en rojo.
class SelloDelArranque {
  const SelloDelArranque._();

  /// Sella lo que se puede contar ahora y devuelve el sello del día.
  ///
  /// [abiertas] las órdenes que no están terminadas.
  /// [cerradasHoy] las que el teléfono SABE que se cerraron hoy. Mejor
  /// esfuerzo: si una falta, el sello no baja (ver [LocalDatabase.sellarArranqueDelDia]).
  static Future<int?> sellarYLeer({
    required int abiertas,
    required int cerradasHoy,
    LocalDatabase? baseLocal,
    SecureStorageLectura? almacenamiento,
    DateTime? ahora,
  }) async {
    final LocalDatabase db = baseLocal ?? LocalDatabase();
    final SecureStorageLectura storage =
        almacenamiento ?? SecureStorageService();

    String? orgId;
    String? profileId;
    try {
      orgId = await storage.getOrgId();
      profileId = await storage.getProfileId();
    } catch (_) {
      return null;
    }
    if (orgId == null ||
        orgId.isEmpty ||
        profileId == null ||
        profileId.isEmpty) {
      return null;
    }

    try {
      return await db.sellarArranqueDelDia(
        orgId: orgId,
        profileId: profileId,
        trabajoDelDia: abiertas + cerradasHoy,
        ahora: ahora,
      );
    } catch (_) {
      return null;
    }
  }
}
