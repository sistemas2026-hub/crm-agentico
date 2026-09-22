/// Qué se queda en el teléfono, hasta cuándo, y de quién es.
///
/// POR QUÉ EXISTE ESTE ARCHIVO
/// ---------------------------
/// Cerrar sesión borraba las llaves de la sesión y nada más. Las órdenes
/// descargadas —nombre del cliente, dirección, teléfono y las coordenadas de
/// su casa— se quedaban en la base del teléfono, y las fotos en el disco. El
/// filtro por `(org_id, profile_id)` impide *verlas* desde otra cuenta, pero
/// el archivo seguía ahí. Un teléfono de cuadrilla cambia de manos.
///
/// LA TENSIÓN QUE RESUELVE
/// -----------------------
/// Borrar al salir es lo seguro para los datos del cliente y lo peor posible
/// para el técnico: el trabajo que todavía no subió vive en esas mismas
/// tablas. Una cuadrilla trabaja sin señal media jornada; borrar su cola es
/// borrarle la jornada.
///
/// Así que la regla no es "borrar al salir" sino **borrar lo que ya está a
/// salvo, y nunca lo que no**. Cuando hay algo sin subir, esta clase no
/// decide: cuenta, lo nombra, y deja que la persona elija. Que el trabajo se
/// pierda en silencio no es una opción, y que se quede sin que nadie lo sepa,
/// tampoco.
///
/// LO QUE NO HACE, A PROPÓSITO
/// ---------------------------
/// No borra pendientes de otra identidad. Si el teléfono tiene trabajo sin
/// subir de otro técnico, ese trabajo **se conserva aislado** y se reporta:
/// no es de quien está entrando, así que no lo ve; pero tampoco es de nadie
/// para destruirlo. Recuperarlo exige volver a entrar con esa cuenta.
library;

import 'dart:io';

import 'package:path/path.dart' as p;

import 'evidencia_storage_service.dart';
import 'local_database.dart';


/// Una identidad que dejó algo guardado en este dispositivo.
class IdentidadLocal {
  final String orgId;
  final String profileId;

  const IdentidadLocal({required this.orgId, required this.profileId});

  bool esLaMisma(String? org, String? profile) =>
      orgId == (org ?? '') && profileId == (profile ?? '');

  @override
  String toString() => '$orgId/$profileId';

  @override
  bool operator ==(Object other) =>
      other is IdentidadLocal &&
      other.orgId == orgId &&
      other.profileId == profileId;

  @override
  int get hashCode => Object.hash(orgId, profileId);
}

/// Lo que falta subir, ya contado y ya escrito para leer.
///
/// Guarda el detalle y no solo el total porque "4 cambios pendientes" no
/// alcanza para decidir: quien está por cerrar sesión necesita saber *qué* se
/// quedaría a medias.
class ResumenPendientes {
  /// Transiciones de estado sin confirmar (iniciar, en camino, cierre…).
  final int mutaciones;

  /// Fotografías y firmas que no terminaron de subir.
  final int evidencias;

  /// Órdenes con datos del formulario escritos y todavía sin viajar.
  final int ordenesConDatos;

  /// Consumos y devoluciones de material que no subieron.
  ///
  /// Cuentan como pendientes igual que una fotografía: lo que se gastó en la
  /// calle solo existe en este teléfono hasta que suba, y borrarlo deja el
  /// inventario de la empresa diciendo que el material sigue en la camioneta.
  final int movimientosDeMaterial;

  /// Una línea por cosa pendiente, tal como va en pantalla.
  final List<String> detalle;

  const ResumenPendientes({
    required this.mutaciones,
    required this.evidencias,
    required this.ordenesConDatos,
    required this.movimientosDeMaterial,
    required this.detalle,
  });

  const ResumenPendientes.vacio()
      : mutaciones = 0,
        evidencias = 0,
        ordenesConDatos = 0,
        movimientosDeMaterial = 0,
        detalle = const <String>[];

  int get total =>
      mutaciones + evidencias + ordenesConDatos + movimientosDeMaterial;

  bool get hayPendientes => total > 0;

  /// "Hay 4 cambios pendientes de sincronizar."
  String get titulo => total == 1
      ? 'Hay 1 cambio pendiente de sincronizar.'
      : 'Hay $total cambios pendientes de sincronizar.';
}

/// Qué pasó al preparar el dispositivo para quien acaba de entrar.
class ResultadoDeLimpieza {
  /// Identidades cuyos datos se borraron: no tenían nada sin subir.
  final List<IdentidadLocal> purgadas;

  /// Identidades que se conservaron porque tenían trabajo sin subir. Sus
  /// datos siguen en el dispositivo y siguen siendo invisibles para quien
  /// entró: el filtro por identidad los deja fuera de toda consulta.
  final List<IdentidadLocal> aisladas;

  final int archivosBorrados;

  const ResultadoDeLimpieza({
    required this.purgadas,
    required this.aisladas,
    required this.archivosBorrados,
  });

  bool get hayTrabajoAjenoRetenido => aisladas.isNotEmpty;
}

class CicloDeVidaLocal {
  final LocalDatabase _db;

  CicloDeVidaLocal(this._db);

  /// Cómo se llama en pantalla cada tipo de transición.
  ///
  /// El tipo que viaja en la cola es el del backend (`marcar_en_camino`); el
  /// que se muestra es el que usa la cuadrilla al hablar.
  static const Map<String, String> _nombreDeAccion = <String, String>{
    'iniciar': 'inicio',
    'marcar_en_camino': 'en camino',
    'completar': 'cierre',
    'suspender': 'suspensión',
  };

  // -- Contar -----------------------------------------------------------

  Future<ResumenPendientes> pendientesDe({
    required String orgId,
    required String profileId,
  }) async {
    final mutaciones = await _db.getMutacionesPendientesDetalle(
      orgId: orgId,
      profileId: profileId,
    );
    final conteos = await _db.getSyncCounts(orgId: orgId, profileId: profileId);
    final datos = await _db.getDatosDirtyDetalle(
      orgId: orgId,
      profileId: profileId,
    );
    final evidencias = conteos['evidencias_pendientes'] ?? 0;
    final movimientos = await _db.getMovimientosMaterialSinConfirmar(
      orgId: orgId,
      profileId: profileId,
    );

    final detalle = <String>[];
    for (final m in mutaciones) {
      final numero = m['numero'];
      final tipo = (m['tipo'] ?? '').toString();
      final accion = _nombreDeAccion[tipo] ?? tipo.replaceAll('_', ' ');
      // Sin número de orden no se inventa uno: la orden puede haberse
      // descargado y borrado, y "OT #null" es peor que no decir el número.
      detalle.add(numero == null ? 'Una orden · $accion' : 'OT #$numero · $accion');
    }
    if (evidencias > 0) {
      detalle.add(evidencias == 1 ? '1 fotografía' : '$evidencias fotografías');
    }
    for (final d in datos) {
      final numero = d['numero'];
      final campos = (d['campos'] ?? 0) as int;
      final cuantos = campos == 1 ? '1 dato' : '$campos datos';
      detalle.add(
        numero == null ? '$cuantos sin subir' : 'OT #$numero · $cuantos sin subir',
      );
    }
    // El material se nombra con su nombre y su cantidad, no como "3
    // movimientos": quien lo lee reconoce el conector que puso hace una hora,
    // no un número de filas.
    for (final m in movimientos) {
      final nombre = (m['material_nombre'] ?? '').toString().trim();
      final etiqueta = nombre.isNotEmpty
          ? nombre
          : (m['material_codigo'] ?? 'Material').toString();
      final cantidad = (m['cantidad'] ?? '').toString();
      final numero = m['orden_numero'];
      final tipo = (m['tipo'] ?? '').toString();
      final verbo = tipo == 'devolucion' ? 'devolución' : '';
      final cuerpo = verbo.isEmpty
          ? '$etiqueta x$cantidad'
          : '$etiqueta x$cantidad · $verbo';
      detalle.add(numero == null ? cuerpo : 'OT #$numero · $cuerpo');
    }

    return ResumenPendientes(
      mutaciones: mutaciones.length,
      evidencias: evidencias,
      ordenesConDatos: datos.length,
      movimientosDeMaterial: movimientos.length,
      detalle: detalle,
    );
  }

  Future<List<IdentidadLocal>> identidadesGuardadas() async {
    final filas = await _db.getIdentidadesLocales();
    return filas
        .map((f) => IdentidadLocal(
              orgId: f['org_id'] ?? '',
              profileId: f['profile_id'] ?? '',
            ))
        .toList();
  }

  // -- Borrar -----------------------------------------------------------

  /// Borra todo lo de una identidad: primero los archivos, después las filas.
  ///
  /// Ese orden importa. Si se borraran antes las filas, las rutas de los
  /// archivos se irían con ellas y las fotos quedarían en el disco sin nada
  /// que las reclame: huérfanas, imposibles de atribuir y por lo tanto
  /// imposibles de limpiar después.
  ///
  /// Devuelve cuántos archivos borró.
  Future<int> purgarIdentidad({
    required String orgId,
    required String profileId,
  }) async {
    final rutas = await _db.getRutasDeEvidencia(orgId: orgId, profileId: profileId);
    final borrados = await _borrarArchivos(rutas);
    await _db.borrarDatosDeIdentidad(orgId: orgId, profileId: profileId);
    return borrados;
  }

  /// Borra solo lo que ya está a salvo en el servidor.
  ///
  /// Se usa al cerrar sesión con todo sincronizado: la foto ya viajó, la
  /// copia del teléfono no agrega nada, y sí es la foto de la casa de un
  /// cliente.
  Future<int> purgarLoQueYaEstaASalvo({
    required String orgId,
    required String profileId,
  }) async {
    final rutas = await _db.getRutasDeEvidencia(
      orgId: orgId,
      profileId: profileId,
      confirmadas: true,
    );
    final borrados = await _borrarArchivos(rutas);
    await _db.borrarEvidenciasConfirmadas(orgId: orgId, profileId: profileId);
    return borrados;
  }

  /// Prepara el dispositivo para quien acaba de entrar.
  ///
  /// Recorre toda identidad que haya dejado algo y aplica la única regla que
  /// no admite excepción: **lo ajeno no se mezcla**. Lo que está subido se
  /// borra; lo que no, se conserva aislado y se reporta, porque destruir el
  /// trabajo de otro técnico no es una decisión que le toque a esta app.
  Future<ResultadoDeLimpieza> prepararPara({
    required String orgId,
    required String profileId,
  }) async {
    final purgadas = <IdentidadLocal>[];
    final aisladas = <IdentidadLocal>[];
    var archivos = 0;

    // Sin identidad no se limpia nada, y esta guarda no es teórica: acá
    // "quién entró" decide quién es el dueño de los datos y quién el ajeno.
    // Con la identidad vacía, NINGUNA de las guardadas coincidiría, así que
    // todas pasarían por ajenas y las que estuvieran al día se borrarían --
    // un dato faltante convertido en borrado masivo.
    //
    // Quien llama valida la identidad contra la respuesta del servidor antes
    // de llegar hasta acá. Esto es la segunda cerradura, por si algún día ese
    // camino cambia.
    if (orgId.isEmpty || profileId.isEmpty) {
      return const ResultadoDeLimpieza(
        purgadas: <IdentidadLocal>[],
        aisladas: <IdentidadLocal>[],
        archivosBorrados: 0,
      );
    }

    for (final identidad in await identidadesGuardadas()) {
      if (identidad.esLaMisma(orgId, profileId)) continue;

      final pendientes = await pendientesDe(
        orgId: identidad.orgId,
        profileId: identidad.profileId,
      );
      if (pendientes.hayPendientes) {
        aisladas.add(identidad);
        continue;
      }
      archivos += await purgarIdentidad(
        orgId: identidad.orgId,
        profileId: identidad.profileId,
      );
      purgadas.add(identidad);
    }

    // Los archivos que ninguna fila reclama se van acá: existían antes de que
    // la ruta llevara la identidad, y no hay forma de saber de quién son.
    //
    // Si el disco no responde no se interrumpe la limpieza: las filas ya se
    // borraron, y dejar eso a medias por un archivo sería peor. Se reintenta
    // en el próximo inicio de sesión.
    try {
      archivos += await borrarArchivosHuerfanos();
    } catch (_) {
      // Sin acceso al almacenamiento: se sigue.
    }

    return ResultadoDeLimpieza(
      purgadas: purgadas,
      aisladas: aisladas,
      archivosBorrados: archivos,
    );
  }

  /// Los archivos del directorio de evidencias que ninguna fila nombra.
  ///
  /// Aparecen de dos formas: una captura que se guardó y cuya fila nunca
  /// llegó a escribirse, y las que quedaron de cuando el nombre del archivo
  /// era un UUID suelto sin identidad. Un huérfano no se puede aislar por
  /// identidad —no se sabe de quién es—, así que la única salida es borrarlo.
  Future<int> borrarArchivosHuerfanos() async {
    final dir = await EvidenciaStorageService.getStorageDirectory();
    if (!await dir.exists()) return 0;

    final reclamadas = await _db.getTodasLasRutasDeEvidencia();
    final normalizadas = reclamadas.map(p.normalize).toSet();

    var borrados = 0;
    await for (final entidad in dir.list(recursive: true, followLinks: false)) {
      if (entidad is! File) continue;
      if (normalizadas.contains(p.normalize(entidad.path))) continue;
      try {
        await entidad.delete();
        borrados++;
      } on FileSystemException {
        // Un archivo que no se puede borrar no puede frenar el cierre de
        // sesión: se reintenta la próxima vez.
      }
    }
    return borrados;
  }

  Future<int> _borrarArchivos(List<String> rutas) async {
    var borrados = 0;
    for (final ruta in rutas) {
      try {
        final archivo = File(ruta);
        if (await archivo.exists()) {
          await archivo.delete();
          borrados++;
        }
      } on FileSystemException {
        // Igual que arriba: no frena nada.
      }
    }
    return borrados;
  }
}
