import 'dart:io';

import 'package:campo/core/storage/ciclo_de_vida_local.dart';
import 'package:campo/core/storage/evidencia_storage_service.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/features/sesion/cierre_de_sesion.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Cerrar sesión: qué se lleva y qué deja.
///
/// La decisión vive separada de la pantalla justamente para poder probarla
/// así: sin emulador, sin cámara y sin que nadie tenga que acordarse de
/// apretar el botón. Lo que se afirma es la frontera entre las dos cosas que
/// no pueden pasar —que queden datos de clientes en un teléfono que cambia de
/// manos, y que se pierda trabajo que costó una jornada— porque cualquier
/// implementación que cuide solo una de las dos parece correcta hasta el día
/// que no lo es.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  // Base propia: si compartiera archivo con otra suite, la
  // preparación de cada una le vaciaría las tablas a la otra.
  LocalDatabase.usarBaseDePruebas('pruebas_cierre_de_sesion.db');

  const orgA = 'org_rapilink';
  const perfilA = 'prof_carlos';
  const ordenA = 'ot-alpha-1';

  /// El almacenamiento seguro del teléfono, simulado en memoria.
  late Map<String, String> llavero;

  late LocalDatabase localDb;
  late CicloDeVidaLocal ciclo;
  late CierreDeSesion cierre;
  late Directory dirEvidencias;

  setUp(() async {
    llavero = <String, String>{};
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
      (MethodCall llamada) async {
        final args = (llamada.arguments as Map?) ?? <dynamic, dynamic>{};
        final clave = args['key']?.toString();
        switch (llamada.method) {
          case 'read':
            return llavero[clave];
          case 'write':
            if (clave != null) llavero[clave] = args['value']?.toString() ?? '';
            return null;
          case 'delete':
            llavero.remove(clave);
            return null;
          case 'deleteAll':
            llavero.clear();
            return null;
          case 'readAll':
            return Map<String, String>.from(llavero);
          case 'containsKey':
            return llavero.containsKey(clave);
        }
        return null;
      },
    );

    localDb = LocalDatabase();
    ciclo = CicloDeVidaLocal(localDb);
    cierre = CierreDeSesion(
      almacenamiento: SecureStorageService(),
      ciclo: ciclo,
    );

    final db = await localDb.database;
    for (final t in const ['local_ordenes', 'local_datos_dirty',
                           'cola_mutaciones', 'cola_evidencias']) {
      await db.delete(t);
    }

    dirEvidencias = await Directory.systemTemp.createTemp('cierre_test_');
    EvidenciaStorageService.setOverrideDirectory(dirEvidencias);
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
      null,
    );
    EvidenciaStorageService.setOverrideDirectory(null);
    if (await dirEvidencias.exists()) {
      await dirEvidencias.delete(recursive: true);
    }
  });

  Future<void> entrarComo(String org, String perfil) async {
    await SecureStorageService().saveTokens(
      accessToken: 'token-de-acceso',
      refreshToken: 'token-de-refresco',
    );
    await SecureStorageService().saveSessionData(
      orgId: org,
      orgName: 'Rapilink',
      profileId: perfil,
      email: 'tecnico@ejemplo.local',
      name: 'Carlos',
    );
  }

  Future<void> sembrarOrden({int numero = 4832}) async {
    await localDb.upsertOrden(
      orgId: orgA,
      profileId: perfilA,
      ordenData: <String, dynamic>{
        'id': ordenA,
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

  Future<void> dejarTrabajoSinSubir() async {
    await localDb.transicionarEstadoLocal(
      orgId: orgA,
      profileId: perfilA,
      ordenId: ordenA,
      nuevoEstadoLocal: 'completada_campo',
      tipoAccion: 'completar',
      revisionBase: 1,
      idempotencyKey: 'mut-sin-subir',
    );
  }

  pruebasDeTexto();

  group('Con todo sincronizado', () {
    test('La decisión es limpiar y salir', () async {
      await entrarComo(orgA, perfilA);
      await sembrarOrden();

      final evaluacion = await cierre.evaluar();

      expect(evaluacion.decision, DecisionDeCierre.limpiarYSalir);
      expect(evaluacion.hayQuePreguntar, isFalse);
    });

    test('Salir borra los datos del cliente y la sesión', () async {
      await entrarComo(orgA, perfilA);
      await sembrarOrden();

      final salio = await cierre.limpiarYSalir();

      expect(salio, isTrue);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), isEmpty);
      expect(llavero['dexter_access_token'], isNull);
      expect(llavero['dexter_current_org_id'], isNull);
    });
  });

  group('Con trabajo sin subir', () {
    test('La decisión es preguntar, y el detalle dice qué quedó', () async {
      await entrarComo(orgA, perfilA);
      await sembrarOrden();
      await dejarTrabajoSinSubir();

      final evaluacion = await cierre.evaluar();

      expect(evaluacion.decision, DecisionDeCierre.preguntarPorPendientes);
      expect(evaluacion.pendientes.titulo,
          'Hay 1 cambio pendiente de sincronizar.');
      expect(evaluacion.pendientes.detalle, contains('OT #4832 · cierre'));
    });

    test('Evaluar no borra nada: solo mira', () async {
      await entrarComo(orgA, perfilA);
      await sembrarOrden();
      await dejarTrabajoSinSubir();

      await cierre.evaluar();

      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
      expect(llavero['dexter_access_token'], isNotNull);
    });

    test('Limpiar se NIEGA mientras haya algo sin subir', () async {
      // La guarda que de verdad protege. Aunque la pantalla se equivoque y
      // pida limpiar, acá no se borra: el trabajo de una jornada no depende
      // de que ningún botón esté bien cableado.
      await entrarComo(orgA, perfilA);
      await sembrarOrden();
      await dejarTrabajoSinSubir();

      final salio = await cierre.limpiarYSalir();

      expect(salio, isFalse);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
      expect(
        await localDb.getMutacionesPendientes(orgId: orgA, profileId: perfilA),
        hasLength(1),
      );
      expect(llavero['dexter_access_token'], isNotNull,
          reason: 'tampoco se cierra la sesión a medias');
    });

    test('Si aparece trabajo entre la pregunta y la respuesta, no se borra',
        () async {
      // La ventana real: se pregunta, la persona duda, la cola recibe algo
      // nuevo, recién entonces contesta "sí, salir". Contar una sola vez
      // perdería eso sin que nadie lo note.
      await entrarComo(orgA, perfilA);
      await sembrarOrden();

      final evaluacion = await cierre.evaluar();
      expect(evaluacion.decision, DecisionDeCierre.limpiarYSalir);

      await dejarTrabajoSinSubir();
      final salio = await cierre.limpiarYSalir();

      expect(salio, isFalse);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
    });

    test('Salir conservando cierra la sesión y NO toca los datos', () async {
      await entrarComo(orgA, perfilA);
      await sembrarOrden();
      await dejarTrabajoSinSubir();

      await cierre.salirConservando();

      expect(llavero['dexter_access_token'], isNull, reason: 'la sesión sí se cierra');
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
      final pendientes = await ciclo.pendientesDe(orgId: orgA, profileId: perfilA);
      expect(pendientes.mutaciones, 1, reason: 'el trabajo espera a su dueño');
    });

    test('Y al volver a entrar con la misma cuenta, ahí está', () async {
      await entrarComo(orgA, perfilA);
      await sembrarOrden();
      await dejarTrabajoSinSubir();
      await cierre.salirConservando();

      // Vuelve la misma persona.
      await entrarComo(orgA, perfilA);
      final resultado = await ciclo.prepararPara(orgId: orgA, profileId: perfilA);

      expect(resultado.purgadas, isEmpty);
      final pendientes = await ciclo.pendientesDe(orgId: orgA, profileId: perfilA);
      expect(pendientes.mutaciones, 1);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
    });
  });

  group('Sesión expirada o cierre forzado', () {
    test('Sin sesión guardada no hay nada que decidir ni nada que borrar',
        () async {
      // Es el caso del token vencido: `api_client` llama a clearSession() por
      // su cuenta, sin pasar por ninguna pantalla. Lo que quede sin subir
      // tiene que seguir ahí.
      await sembrarOrden();
      await dejarTrabajoSinSubir();
      // Sin llaves: la sesión ya se cerró sola.

      final evaluacion = await cierre.evaluar();

      expect(evaluacion.decision, DecisionDeCierre.salirSinDatos);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA), hasLength(1));
      expect(
        await localDb.getMutacionesPendientes(orgId: orgA, profileId: perfilA),
        hasLength(1),
      );
    });

    test('Un cierre forzado no puede borrar trabajo ajeno al entrar otro',
        () async {
      await sembrarOrden();
      await dejarTrabajoSinSubir();

      // Entra otra persona en el mismo teléfono.
      final resultado = await ciclo.prepararPara(
        orgId: 'org_conexiones',
        profileId: 'prof_pedro',
      );

      expect(resultado.hayTrabajoAjenoRetenido, isTrue);
      expect(
        await localDb.getMutacionesPendientes(orgId: orgA, profileId: perfilA),
        hasLength(1),
      );
      // Y quien entró no ve nada de eso.
      expect(
        await localDb.getOrdenes(orgId: 'org_conexiones', profileId: 'prof_pedro'),
        isEmpty,
      );
    });
  });
}

/// El texto que ve alguien que se va con trabajo sin subir.
///
/// Se prueba el TEXTO y no solo la conducta porque acá el texto es la
/// protección: la decisión de irse la toma una persona leyendo esa pantalla, y
/// "se guardó" es exactamente la palabra que puede entenderse como "la oficina
/// ya lo tiene". Si alguien la suaviza, esto lo frena.
void pruebasDeTexto() {
  group('El aviso de salida dice las cuatro cosas', () {
    late String copy;

    setUpAll(() {
      copy = File('lib/features/sesion/hoja_de_pendientes.dart').readAsStringSync();
    });

    test('Dice que NO llegaron al servidor', () {
      expect(copy, contains('NO llegaron al servidor'));
    });

    test('Dice que no se borran', () {
      expect(copy, contains('No se borran'));
    });

    test('Dice que quedan solo en este teléfono', () {
      expect(copy, contains('únicamente en este teléfono'));
    });

    test('Dice que hay que volver con la misma cuenta y el mismo equipo', () {
      expect(copy, contains('este mismo teléfono'));
      expect(copy, contains('esta misma cuenta'));
    });

    test('El botón no promete que se sincronizó', () {
      expect(copy, contains("'Salir dejando los cambios en este teléfono'"));
      // El texto viejo decía "queda guardado", que se lee como "ya está a
      // salvo en algún lado". No vuelve.
      expect(copy, isNot(contains('queda guardado en este teléfono y vuelve')));
    });
  });
}
