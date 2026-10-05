/// Cerrar sesión sin perder trabajo y sin dejar datos de clientes atrás.
///
/// Esta clase no dibuja nada. Decide, y devuelve la decisión: la pantalla se
/// limita a obedecerla. Separarlas es lo que permite probar la regla —la que
/// no puede fallar— sin cámara, sin base y sin emulador.
///
/// LA REGLA
/// --------
/// Salir borra lo que ya está a salvo en el servidor y **nunca** lo que no.
/// Si queda algo sin subir, esto no elige por nadie: devuelve el detalle para
/// que la persona decida si sincroniza o si se va igual. Un dato de trabajo
/// que desaparece sin aviso es peor que un dato que se queda.
library;

import '../../core/storage/ciclo_de_vida_local.dart';
import '../../core/storage/secure_storage_service.dart';

/// Qué corresponde hacer cuando alguien pide cerrar sesión.
enum DecisionDeCierre {
  /// No hay nada sin subir: se puede salir y limpiar el dispositivo.
  limpiarYSalir,

  /// Hay trabajo sin sincronizar. No se borra nada y se pregunta.
  preguntarPorPendientes,

  /// No hay sesión guardada (ya se cerró, o nunca entró). Salir sin más.
  salirSinDatos,
}

/// La decisión, con lo que la pantalla necesita para explicarla.
class ResultadoDeCierre {
  final DecisionDeCierre decision;
  final ResumenPendientes pendientes;

  const ResultadoDeCierre(this.decision, this.pendientes);

  bool get hayQuePreguntar => decision == DecisionDeCierre.preguntarPorPendientes;
}

class CierreDeSesion {
  final SecureStorageService _almacenamiento;
  final CicloDeVidaLocal _ciclo;

  /// Qué hacer con el registro de push al salir. Nulo en pruebas.
  final Future<void> Function()? _darDeBajaElTelefono;

  CierreDeSesion({
    required SecureStorageService almacenamiento,
    required CicloDeVidaLocal ciclo,
    Future<void> Function()? darDeBajaElTelefono,
  }) : this._(almacenamiento, ciclo, darDeBajaElTelefono);

  CierreDeSesion._(
    this._almacenamiento,
    this._ciclo,
    this._darDeBajaElTelefono,
  );

  /// Da de baja este teléfono ANTES de borrar las llaves.
  ///
  /// El orden no es un detalle: la baja es un pedido autenticado, y después de
  /// `clearSession()` no hay con qué firmarlo. Si falla, se sigue saliendo: el
  /// servidor da de baja el token solo cuando el proveedor lo rechace, así que
  /// lo peor que pasa es que llegue un aviso de más a un teléfono que ya cambió
  /// de manos. Quedarse adentro de la sesión por eso sería mucho peor.
  Future<void> _soltarElPush() async {
    final baja = _darDeBajaElTelefono;
    if (baja == null) return;
    try {
      await baja();
    } catch (_) {
      // Ver el docstring: no puede impedir salir.
    }
  }

  /// Mira el estado antes de tocar nada. No borra.
  Future<ResultadoDeCierre> evaluar() async {
    final orgId = await _almacenamiento.getOrgId();
    final profileId = await _almacenamiento.getProfileId();

    if (orgId == null || orgId.isEmpty || profileId == null || profileId.isEmpty) {
      return const ResultadoDeCierre(
        DecisionDeCierre.salirSinDatos,
        ResumenPendientes.vacio(),
      );
    }

    final pendientes = await _ciclo.pendientesDe(orgId: orgId, profileId: profileId);
    return ResultadoDeCierre(
      pendientes.hayPendientes
          ? DecisionDeCierre.preguntarPorPendientes
          : DecisionDeCierre.limpiarYSalir,
      pendientes,
    );
  }

  /// Sale borrando todo lo de esta identidad.
  ///
  /// Solo se llama cuando `evaluar()` dijo que no hay pendientes, o cuando la
  /// persona confirmó que quiere irse igual. Vuelve a contar antes de borrar:
  /// entre la pregunta y la respuesta pudo entrar trabajo nuevo, y esa
  /// ventana es justo donde se pierde algo sin que nadie lo note.
  ///
  /// Devuelve `false` y no borra nada si aparecieron pendientes.
  Future<bool> limpiarYSalir({bool aunConPendientes = false}) async {
    final orgId = await _almacenamiento.getOrgId();
    final profileId = await _almacenamiento.getProfileId();

    if (orgId != null && orgId.isNotEmpty && profileId != null && profileId.isNotEmpty) {
      if (!aunConPendientes) {
        final ahora = await _ciclo.pendientesDe(orgId: orgId, profileId: profileId);
        if (ahora.hayPendientes) return false;
      }
      await _ciclo.purgarIdentidad(orgId: orgId, profileId: profileId);
    }

    await _soltarElPush();
    await _almacenamiento.clearSession();
    return true;
  }

  /// Sale sin borrar nada.
  ///
  /// Es lo que pasa cuando hay trabajo sin subir y la persona decide irse
  /// igual: sus datos quedan en el dispositivo, aislados por identidad, y los
  /// recupera cuando vuelva a entrar con la misma cuenta.
  Future<void> salirConservando() async {
    await _soltarElPush();
    await _almacenamiento.clearSession();
  }
}
