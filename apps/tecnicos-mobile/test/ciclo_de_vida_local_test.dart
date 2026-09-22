import 'dart:io';

import 'package:campo/core/storage/ciclo_de_vida_local.dart';
import 'package:campo/core/storage/evidencia_storage_service.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Qué se borra del teléfono, qué no, y de quién es cada cosa.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// Dos cosas que se contradicen, y por eso hay que probar las dos juntas:
///
/// 1. Al salir, los datos de los clientes no se quedan en el dispositivo. Un
///    teléfono de cuadrilla cambia de manos.
/// 2. El trabajo que todavía no subió no se destruye jamás. Una jornada sin
///    señal vive solo acá.
///
/// Una implementación que borre siempre pasa la primera y arruina a un
/// técnico. Una que no borre nunca pasa la segunda y deja la libreta de
/// clientes en un teléfono prestado. Lo que se afirma acá es la frontera.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  // Base propia: si compartiera archivo con otra suite, la
  // preparación de cada una le vaciaría las tablas a la otra.
  LocalDatabase.usarBaseDePruebas('pruebas_ciclo_de_vida.db');

  const orgA = 'org_rapilink';
  const perfilA = 'prof_carlos';
  const ordenA = 'ot-alpha-1';

  const orgB = 'org_conexiones';
  const perfilB = 'prof_pedro';

  late LocalDatabase localDb;
  late CicloDeVidaLocal ciclo;
  late Directory dirEvidencias;

  setUp(() async {
    localDb = LocalDatabase();
    ciclo = CicloDeVidaLocal(localDb);
    final db = await localDb.database;
    for (final t in const ['local_ordenes', 'local_datos_dirty',
                           'cola_mutaciones', 'cola_evidencias']) {
      await db.delete(t);
    }
    dirEvidencias = await Directory.systemTemp.createTemp('evidencias_test_');
    EvidenciaStorageService.setOverrideDirectory(dirEvidencias);
  });

  tearDown(() async {
    EvidenciaStorageService.setOverrideDirectory(null);
    if (await dirEvidencias.exists()) {
      await dirEvidencias.delete(recursive: true);
    }
  });

  Future<void> sembrarOrden({
    required String org,
    required String perfil,
    required String ordenId,
    int numero = 4832,
  }) async {
    await localDb.upsertOrden(
      orgId: org,
      profileId: perfil,
      ordenData: <String, dynamic>{
        'id': ordenId,
        'numero': numero,
        'estado': 'asignada',
        'cliente_nombre': 'María Fernández',
        'direccion': 'Cra 48 # 12-30',
        'telefono': '+57 300 111 2233',
        'tipo': <String, dynamic>{'nombre': 'Instalación FTTH', 'codigo': 'ftth'},
        'revision': 1,
      },
    );
  }

  /// Una foto ya persistida, con su fila, como la deja una captura real.
  Future<File> sembrarEvidencia({
    required String org,
    required String perfil,
    required String ordenId,
    required String evidenciaId,
    required String estado,
  }) async {
    final temporal = File('${dirEvidencias.path}/captura_$evidenciaId.tmp');
    await temporal.writeAsString('bytes de una fotografia');

    final archivo = await EvidenciaStorageService.persistirArchivoCaptura(
      temporal,
      orgId: org,
      profileId: perfil,
      ordenId: ordenId,
      evidenciaId: evidenciaId,
    );
    await localDb.encolarEvidencia(
      id: evidenciaId,
      orgId: org,
      profileId: perfil,
      ordenId: ordenId,
      requisitoId: 'req-1',
      archivoPath: archivo.path,
      sha256: 'abc123',
      tamanoBytes: await archivo.length(),
      mimeType: 'image/jpeg',
      registroIdempotencyKey: 'reg-$evidenciaId',
      confirmacionIdempotencyKey: 'conf-$evidenciaId',
    );
    if (estado != 'pendiente_registro') {
      await localDb.updateEvidenciaEstado(
        id: evidenciaId,
        orgId: org,
        profileId: perfil,
        subidaEstado: estado,
      );
    }
    return archivo;
  }

  group('1. Contar lo pendiente antes de tocar nada', () {
    test('Sin nada sin subir, no hay pendientes', () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);

      final pendientes = await ciclo.pendientesDe(orgId: orgA, profileId: perfilA);

      expect(pendientes.hayPendientes, isFalse);
      expect(pendientes.total, 0);
    });

    test('Una orden descargada NO es trabajo pendiente', () async {
      // Importa: si una orden solo leída contara como pendiente, cerrar
      // sesión nunca limpiaría nada y la protección sería letra muerta.
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-subida', estado: 'confirmada',
      );

      final pendientes = await ciclo.pendientesDe(orgId: orgA, profileId: perfilA);

      expect(pendientes.hayPendientes, isFalse);
    });

    test('El detalle nombra la orden y la acción, no solo cuenta', () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA, numero: 4832);
      await localDb.transicionarEstadoLocal(
        orgId: orgA, profileId: perfilA, ordenId: ordenA,
        nuevoEstadoLocal: 'completada_campo', tipoAccion: 'completar',
        revisionBase: 1, idempotencyKey: 'mut-1',
      );

      final pendientes = await ciclo.pendientesDe(orgId: orgA, profileId: perfilA);

      expect(pendientes.detalle, contains('OT #4832 · cierre'));
      expect(pendientes.titulo, 'Hay 1 cambio pendiente de sincronizar.');
    });

    test('Cuenta transiciones, fotografías y datos por separado', () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      await localDb.transicionarEstadoLocal(
        orgId: orgA, profileId: perfilA, ordenId: ordenA,
        nuevoEstadoLocal: 'en_camino', tipoAccion: 'marcar_en_camino',
        revisionBase: 1, idempotencyKey: 'mut-2',
      );
      await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-1', estado: 'pendiente_registro',
      );
      await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-2', estado: 'pendiente_registro',
      );
      await localDb.saveDatoCampo(
        orgId: orgA, profileId: perfilA, ordenId: ordenA,
        campoClave: 'potencia_rx', valor: -18.4,
      );

      final pendientes = await ciclo.pendientesDe(orgId: orgA, profileId: perfilA);

      expect(pendientes.mutaciones, 1);
      expect(pendientes.evidencias, 2);
      expect(pendientes.ordenesConDatos, 1);
      expect(pendientes.detalle, contains('2 fotografías'));
    });
  });

  group('2. Salir sin nada pendiente deja el teléfono limpio', () {
    test('Se van las filas y también los archivos', () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      final foto = await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-ok', estado: 'confirmada',
      );
      expect(await foto.exists(), isTrue);

      await ciclo.purgarIdentidad(orgId: orgA, profileId: perfilA);

      final ordenes = await localDb.getOrdenes(orgId: orgA, profileId: perfilA);
      expect(ordenes, isEmpty, reason: 'los datos del cliente no se quedan');
      expect(await foto.exists(), isFalse,
          reason: 'la fotografía de la casa del cliente tampoco');
    });

    test('Borrar una identidad no toca a la otra', () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      await sembrarOrden(org: orgB, perfil: perfilB, ordenId: 'ot-beta-1');
      final fotoB = await sembrarEvidencia(
        org: orgB, perfil: perfilB, ordenId: 'ot-beta-1',
        evidenciaId: 'ev-beta', estado: 'confirmada',
      );

      await ciclo.purgarIdentidad(orgId: orgA, profileId: perfilA);

      expect(await localDb.getOrdenes(orgId: orgB, profileId: perfilB), hasLength(1));
      expect(await fotoB.exists(), isTrue);
    });
  });

  group('3. Lo que no subió no se destruye', () {
    test('Al entrar otra cuenta, una identidad con pendientes se conserva',
        () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      await localDb.transicionarEstadoLocal(
        orgId: orgA, profileId: perfilA, ordenId: ordenA,
        nuevoEstadoLocal: 'completada_campo', tipoAccion: 'completar',
        revisionBase: 1, idempotencyKey: 'mut-sin-subir',
      );

      final resultado = await ciclo.prepararPara(orgId: orgB, profileId: perfilB);

      expect(resultado.hayTrabajoAjenoRetenido, isTrue);
      expect(resultado.aisladas.single.profileId, perfilA);
      // Y sigue entero, esperando a que vuelva su dueño.
      final suyo = await ciclo.pendientesDe(orgId: orgA, profileId: perfilA);
      expect(suyo.mutaciones, 1);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
    });

    test('Al entrar otra cuenta, una identidad sin pendientes se purga',
        () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      final foto = await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-vieja', estado: 'confirmada',
      );

      final resultado = await ciclo.prepararPara(orgId: orgB, profileId: perfilB);

      expect(resultado.purgadas.single.profileId, perfilA);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), isEmpty);
      expect(await foto.exists(), isFalse);
    });

    test('Preparar no borra lo de quien está entrando', () async {
      await sembrarOrden(org: orgB, perfil: perfilB, ordenId: 'ot-beta-1');

      await ciclo.prepararPara(orgId: orgB, profileId: perfilB);

      expect(await localDb.getOrdenes(orgId: orgB, profileId: perfilB), hasLength(1));
    });

    test('Quien entra no ve ni una fila de quien estuvo antes', () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      await localDb.transicionarEstadoLocal(
        orgId: orgA, profileId: perfilA, ordenId: ordenA,
        nuevoEstadoLocal: 'completada_campo', tipoAccion: 'completar',
        revisionBase: 1, idempotencyKey: 'mut-ajena',
      );

      await ciclo.prepararPara(orgId: orgB, profileId: perfilB);

      // Aunque la cola ajena se conservó, para B no existe.
      expect(await localDb.getOrdenes(orgId: orgB, profileId: perfilB), isEmpty);
      final deB = await ciclo.pendientesDe(orgId: orgB, profileId: perfilB);
      expect(deB.hayPendientes, isFalse);
      expect(
        await localDb.getMutacionesPendientes(orgId: orgB, profileId: perfilB),
        isEmpty,
      );
    });
  });

  group('3b. La identidad tiene que ser real para poder limpiar', () {
    test('Con identidad vacía no se borra absolutamente nada', () async {
      // Si no se validara, ninguna identidad guardada coincidiría con la
      // vacía: todas pasarían por ajenas y las que estuvieran al día se
      // borrarían. Un dato faltante convertido en borrado masivo.
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      final foto = await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-intacta', estado: 'confirmada',
      );

      final resultado = await ciclo.prepararPara(orgId: '', profileId: '');

      expect(resultado.purgadas, isEmpty);
      expect(resultado.aisladas, isEmpty);
      expect(resultado.archivosBorrados, 0);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
      expect(await foto.exists(), isTrue);
    });

    test('Con la organización vacía tampoco', () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);

      await ciclo.prepararPara(orgId: '', profileId: perfilB);

      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
    });

    test('El login no puede inventar una identidad de relleno', () {
      // 'org_default' y 'profile_default' hacían que dos personas sin
      // organización compartieran partición, y una viera las órdenes de la
      // otra.
      final login = File('lib/features/auth/login_screen.dart').readAsStringSync();
      expect(login, isNot(contains("'org_default'")));
      expect(login, isNot(contains("'profile_default'")));
      // Y sin identidad completa, no entra.
      expect(login, contains('orgId.isEmpty || profileId.isEmpty'));
      expect(login, contains('_storage.clearSession()'));
    });
  });

  group('4. Los archivos llevan su identidad en la ruta', () {
    test('La foto se guarda bajo org / perfil / orden y se llama como su evidencia',
        () async {
      final foto = await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-ruta', estado: 'pendiente_registro',
      );

      expect(foto.path, contains(orgA));
      expect(foto.path, contains(perfilA));
      expect(foto.path, contains(ordenA));
      expect(foto.path, contains('ev-ruta'));
    });

    test('La copia temporal de la cámara no queda en el disco', () async {
      // Cada foto quedaba dos veces: la persistente y la que deja
      // image_picker en el directorio de caché, que no limpiaba nadie.
      final temporal = File('${dirEvidencias.path}/captura_suelta.tmp');
      await temporal.writeAsString('bytes');

      await EvidenciaStorageService.persistirArchivoCaptura(
        temporal,
        orgId: orgA, profileId: perfilA, ordenId: ordenA, evidenciaId: 'ev-tmp',
      );

      expect(await temporal.exists(), isFalse);
    });

    test('Un archivo que ninguna fila reclama se borra', () async {
      final huerfano = File('${dirEvidencias.path}/huerfano_sin_duenio.jpg');
      await huerfano.writeAsString('foto vieja de nadie');

      final borrados = await ciclo.borrarArchivosHuerfanos();

      expect(borrados, greaterThanOrEqualTo(1));
      expect(await huerfano.exists(), isFalse);
    });

    test('Un archivo que SÍ tiene fila no se toca al limpiar huérfanos',
        () async {
      final foto = await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-viva', estado: 'pendiente_registro',
      );

      await ciclo.borrarArchivosHuerfanos();

      expect(await foto.exists(), isTrue,
          reason: 'es trabajo sin subir: borrarlo es perder la evidencia');
    });

    test('Un id con separadores no escapa del directorio de evidencias',
        () async {
      // Los ids vienen del servidor, pero esto arma rutas de archivo: un
      // valor con '..' convertiría un borrado por identidad en un borrado
      // en cualquier parte del disco.
      final temporal = File('${dirEvidencias.path}/captura_rara.tmp');
      await temporal.writeAsString('bytes');

      final archivo = await EvidenciaStorageService.persistirArchivoCaptura(
        temporal,
        orgId: '../../etc', profileId: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-escape',
      );

      // Lo que importa no es que el texto '..' desaparezca sino que no
      // funcione COMO salto de directorio: queda neutralizado dentro de un
      // nombre de carpeta, y el archivo sigue bajo el directorio de
      // evidencias. Se compara la ruta ya resuelta por el sistema, que es la
      // que de verdad se usaría para borrar.
      final resuelta = archivo.absolute.path;
      final base = dirEvidencias.absolute.path;
      expect(resuelta.startsWith(base), isTrue,
          reason: 'un id con separadores no puede sacar el archivo de su carpeta');
      expect(Directory(base).listSync(recursive: true).whereType<File>(),
          isNotEmpty);
    });
  });

  group('5. Las escrituras de la cola no alcanzan a otra identidad', () {
    test('Actualizar con la identidad equivocada no escribe nada', () async {
      await sembrarOrden(org: orgA, perfil: perfilA, ordenId: ordenA);
      await localDb.transicionarEstadoLocal(
        orgId: orgA, profileId: perfilA, ordenId: ordenA,
        nuevoEstadoLocal: 'en_camino', tipoAccion: 'marcar_en_camino',
        revisionBase: 1, idempotencyKey: 'mut-propia',
      );

      // B conoce el id (es un UUID, pero supongamos que lo obtuvo) e intenta
      // marcarla como sincronizada.
      await localDb.updateMutacionEstado(
        id: 'mut-propia',
        orgId: orgB,
        profileId: perfilB,
        estado: 'sincronizada',
      );

      final deA = await localDb.getMutacionesPendientes(
        orgId: orgA, profileId: perfilA,
      );
      expect(deA, hasLength(1),
          reason: 'la mutación de A sigue pendiente: nadie más pudo tocarla');
      expect(deA.first['estado'], 'pendiente');
    });

    test('Una evidencia ajena tampoco se puede marcar como subida', () async {
      await sembrarEvidencia(
        org: orgA, perfil: perfilA, ordenId: ordenA,
        evidenciaId: 'ev-de-a', estado: 'pendiente_registro',
      );

      await localDb.updateEvidenciaEstado(
        id: 'ev-de-a',
        orgId: orgB,
        profileId: perfilB,
        subidaEstado: 'confirmada',
      );

      final pendientes = await localDb.getEvidenciasPendientes(
        orgId: orgA, profileId: perfilA,
      );
      expect(pendientes, hasLength(1));
    });
  });
}
