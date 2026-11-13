import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../features/trabajo/trabajo_vista.dart';
import '../storage/local_database.dart';
import '../storage/secure_storage_service.dart';
import '../sync/sync_queue_service.dart';

/// Las órdenes de la jornada, en un solo lugar.
///
/// Inicio y Trabajo miran la misma lista: la carga ocurre una vez, y una
/// sincronización exitosa provoca **una** recarga, no una por pantalla. Antes
/// de esto cada pantalla abría su propia escucha y su propia consulta contra
/// la base.
///
/// Es un [ChangeNotifier] —de Flutter, sin paquetes— y deliberadamente chico.
/// No sabe nada de pestañas, filtros, scroll ni datos de ejemplo: eso es de
/// cada pantalla. Tampoco lo maneja el contenedor: el contenedor lo crea, lo
/// comparte y lo cierra.
class OrdenesJornada extends ChangeNotifier {
  OrdenesJornada({
    required this.leerOrdenes,
    required this.sincronizar,
    required Stream<SyncStatus> avisosDeSincronizacion,
  }) {
    _suscripcion = avisosDeSincronizacion.listen((SyncStatus estado) {
      // Solo una sincronización que trajo algo nuevo justifica releer la base.
      if (estado == SyncStatus.success) _cargar();
    });
  }

  /// Cableado real: la base local, la sesión y la cola.
  factory OrdenesJornada.real() {
    final baseLocal = LocalDatabase();
    final almacenamiento = SecureStorageService();
    final sincronizacion = SyncQueueService();

    return OrdenesJornada(
      leerOrdenes: () async {
        final orgId = await almacenamiento.getOrgId();
        final profileId = await almacenamiento.getProfileId();
        if (orgId == null || profileId == null) return <Map<String, dynamic>>[];
        return baseLocal.getOrdenes(orgId: orgId, profileId: profileId);
      },
      sincronizar: sincronizacion.procesarCola,
      avisosDeSincronizacion: sincronizacion.syncStatusStream,
    );
  }

  /// De dónde salen las filas de órdenes.
  final Future<List<Map<String, dynamic>>> Function() leerOrdenes;

  /// Qué hacer para que la cola envíe y reciba.
  final Future<void> Function() sincronizar;
  StreamSubscription<SyncStatus>? _suscripcion;

  List<TrabajoVista> _trabajos = <TrabajoVista>[];
  bool _cargando = true;
  bool _fallo = false;
  bool _pedidoAlgunaVez = false;
  bool _cerrado = false;

  List<TrabajoVista> get trabajos => List<TrabajoVista>.unmodifiable(_trabajos);
  bool get cargando => _cargando;

  /// No se pudo leer la base. Distinto de "no hay trabajos".
  bool get fallo => _fallo;

  /// La primera pantalla que se muestra pide esto; la segunda encuentra los
  /// datos ya cargados y no vuelve a consultar. Así la carga ocurre cuando
  /// alguien la necesita —no al abrir la aplicación— y una sola vez.
  Future<void> asegurarCargado() async {
    if (_pedidoAlgunaVez) return;
    _pedidoAlgunaVez = true;
    await _cargar();
    await sincronizar();
  }

  /// Vuelve a leer la base. Se usa al volver de una orden.
  Future<void> recargar() => _cargar();

  /// Pide a la cola que envíe y reciba, y después relee.
  Future<void> refrescar() async {
    await sincronizar();
    await _cargar();
  }

  Future<void> _cargar() async {
    try {
      final filas = await leerOrdenes();
      if (_cerrado) return;
      _trabajos = filas.map(TrabajoVista.desdeOrden).toList();
      _cargando = false;
      _fallo = false;
    } catch (_) {
      // Que la base no se pueda leer tiene que verse como un problema, no
      // como una jornada sin trabajo asignado.
      if (_cerrado) return;
      _cargando = false;
      _fallo = true;
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _cerrado = true;
    _suscripcion?.cancel();
    super.dispose();
  }
}
