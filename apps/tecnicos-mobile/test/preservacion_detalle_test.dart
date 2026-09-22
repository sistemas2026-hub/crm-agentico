import 'dart:convert';

import 'package:campo/core/storage/local_database.dart';
import 'package:campo/features/trabajo/estado_validacion.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// CAMPO-D2: un retrato pobre no puede borrar uno rico.
///
/// El listado no trae formulario, evidencias, diagnóstico, datos técnicos ni
/// la versión del esquema. Cuando la llamada al detalle falla, lo que se guarda
/// es ese listado — y como el upsert reemplaza la fila entera, antes de esta
/// fase le vaciaba al técnico lo que ya tenía descargado.
///
/// La regla es por procedencia y no por valor: un detalle que dice que el
/// formulario está vacío manda; un listado no puede afirmar nada sobre eso.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  const orgId = 'org_rapilink';
  const profileId = 'prof_carlos';
  const ordenId = 'ot-4832';

  late String rutaBase;
  late LocalDatabase baseLocal;

  setUp(() async {
    rutaBase = join(await databaseFactory.getDatabasesPath(), 'dexter_campo.db');
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(rutaBase);
    baseLocal = LocalDatabase();
  });

  tearDown(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(rutaBase);
  });

  /// Lo que devuelve `GET /trabajos/{id}/`.
  Map<String, dynamic> detalle({
    String estado = 'en_sitio',
    List<Map<String, dynamic>>? campos,
    List<Map<String, dynamic>>? evidencias,
    Object? diagnostico = 'Cortes intermitentes en la noche',
    Map<String, dynamic>? datos,
    int schemaVersion = 2,
  }) {
    return <String, dynamic>{
      'id': ordenId,
      'numero': 4832,
      'revision': 7,
      'estado_operativo': estado,
      'estado_validacion': 'pendiente',
      'cliente': <String, dynamic>{
        'nombre': 'Carlos Gomez',
        'direccion': 'Cra 45 #12-88',
        'telefono': '3001234567',
        'lat': 6.244203,
        'lng': -75.581212,
      },
      'tipo': <String, dynamic>{
        'nombre': 'Instalación FTTH',
        'codigo': 'ftth_instalacion',
        'version': 3,
        'schema_version': schemaVersion,
      },
      'schema': <String, dynamic>{
        'campos': campos ??
            <Map<String, dynamic>>[
              <String, dynamic>{'clave': 'potencia_rx', 'tipo': 'numero', 'obligatorio': true},
              <String, dynamic>{'clave': 'serial_ont', 'tipo': 'texto', 'obligatorio': true},
            ],
        'evidencias': evidencias ??
            <Map<String, dynamic>>[
              <String, dynamic>{'id': 'foto_fachada', 'descripcion': 'Fachada', 'obligatoria': true},
            ],
      },
      'datos': datos ?? <String, dynamic>{'potencia_rx': -18.7},
      'diagnostico_previo': diagnostico,
      'programada_para': '2026-09-18T10:30:00Z',
      'iniciada_en': '2026-09-18T11:02:00Z',
      'completada_campo_en': '2026-09-18T12:40:00Z',
    };
  }

  /// Lo que devuelve `GET /trabajos/` para esa misma orden: sin formulario,
  /// sin evidencias, sin diagnóstico, sin datos y sin versión de esquema.
  Map<String, dynamic> listado({
    String estado = 'completada_campo',
    String estadoValidacion = 'aprobado',
    int revision = 9,
  }) {
    return <String, dynamic>{
      'id': ordenId,
      'numero': 4832,
      'revision': revision,
      'estado_operativo': estado,
      'estado_validacion': estadoValidacion,
      'cliente': <String, dynamic>{
        'nombre': 'Carlos Gomez Restrepo',
        'direccion': 'Cra 45 #12-88 apto 301',
        'telefono': '3001234567',
        'lat': 6.244203,
        'lng': -75.581212,
      },
      'tipo': <String, dynamic>{
        'nombre': 'Instalación FTTH',
        'codigo': 'ftth_instalacion',
        'version': 3,
      },
      'programada_para': '2026-09-18T10:30:00Z',
      'iniciada_en': '2026-09-18T11:02:00Z',
    };
  }

  Future<Map<String, dynamic>> filaGuardada() async {
    final filas = await baseLocal.getOrdenes(orgId: orgId, profileId: profileId);
    return filas.firstWhere((Map<String, dynamic> f) => f['id'] == ordenId);
  }

  group('CAMPO-D2 · el listado no borra lo que trajo el detalle', () {
    test('1. El detalle guarda el formulario, las evidencias y el diagnóstico',
        () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(),
        fuente: FuenteOrden.detalle,
      );

      final fila = await filaGuardada();
      expect(jsonDecode(fila['formulario_campos_json'] as String), hasLength(2));
      expect(jsonDecode(fila['formulario_evidencias_json'] as String), hasLength(1));
      expect(fila['diagnostico_previo_ia'], 'Cortes intermitentes en la noche');
      expect(jsonDecode(fila['datos_json'] as String), <String, dynamic>{'potencia_rx': -18.7});
      expect(fila['schema_version'], 2);
    });

    test('2. Si el detalle falla, el listado no vacía el formulario ni las fotos',
        () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(),
        fuente: FuenteOrden.detalle,
      );

      // Siguiente sincronización: llega el listado y el detalle se cae.
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(),
        fuente: FuenteOrden.listado,
      );

      final fila = await filaGuardada();
      expect(
        jsonDecode(fila['formulario_campos_json'] as String),
        hasLength(2),
        reason: 'sin el formulario, la pantalla de ejecucion queda vacia',
      );
      expect(jsonDecode(fila['formulario_evidencias_json'] as String), hasLength(1));
      expect(fila['diagnostico_previo_ia'], 'Cortes intermitentes en la noche');
      expect(jsonDecode(fila['datos_json'] as String), <String, dynamic>{'potencia_rx': -18.7});
    });

    test('3. Y en ese mismo fallback sí actualiza lo que el listado puede afirmar',
        () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(),
        fuente: FuenteOrden.detalle,
      );
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(),
        fuente: FuenteOrden.listado,
      );

      final fila = await filaGuardada();
      // Conservar no es congelar: el estado, la revisión, la validación y los
      // datos del cliente sí vienen en el listado y se actualizan.
      expect(fila['estado'], 'completada_campo');
      expect(fila['revision'], 9);
      expect(fila['cliente_nombre'], 'Carlos Gomez Restrepo');
      expect(fila['direccion'], 'Cra 45 #12-88 apto 301');
      expect(
        TrabajoVista.desdeOrden(fila).estadoValidacion,
        EstadoValidacion.aprobado,
      );
    });

    test('4. El bloqueo por versión de esquema no se degrada en el fallback',
        () async {
      // Una orden que exige una version mas nueva de la aplicacion.
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(schemaVersion: 2),
        fuente: FuenteOrden.detalle,
      );
      expect(TrabajoVista.desdeOrden(await filaGuardada()).requiereActualizacion, isTrue);

      // El listado no trae schema_version: caer al 1 por defecto habria
      // desbloqueado una orden que tiene que quedar bloqueada.
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(),
        fuente: FuenteOrden.listado,
      );

      final fila = await filaGuardada();
      expect(fila['schema_version'], 2);
      expect(TrabajoVista.desdeOrden(fila).requiereActualizacion, isTrue);
    });
  });

  group('CAMPO-D2 · el detalle sigue mandando', () {
    test('5. Un detalle posterior actualiza el formulario y el diagnóstico',
        () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(),
        fuente: FuenteOrden.detalle,
      );

      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(
          campos: <Map<String, dynamic>>[
            <String, dynamic>{'clave': 'potencia_rx', 'tipo': 'numero', 'obligatorio': true},
            <String, dynamic>{'clave': 'serial_ont', 'tipo': 'texto', 'obligatorio': true},
            <String, dynamic>{'clave': 'metros_drop', 'tipo': 'numero', 'obligatorio': false},
          ],
          diagnostico: 'Revisado: falla en el conector',
        ),
        fuente: FuenteOrden.detalle,
      );

      final fila = await filaGuardada();
      expect(jsonDecode(fila['formulario_campos_json'] as String), hasLength(3));
      expect(fila['diagnostico_previo_ia'], 'Revisado: falla en el conector');
    });

    test('6. Un detalle que dice que está vacío, vacía: no se confunde con ausencia',
        () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(),
        fuente: FuenteOrden.detalle,
      );

      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(
          campos: <Map<String, dynamic>>[],
          evidencias: <Map<String, dynamic>>[],
          diagnostico: null,
          datos: <String, dynamic>{},
        ),
        fuente: FuenteOrden.detalle,
      );

      final fila = await filaGuardada();
      expect(
        jsonDecode(fila['formulario_campos_json'] as String),
        isEmpty,
        reason: 'el detalle es autoritativo: si dice vacio, es vacio',
      );
      expect(jsonDecode(fila['formulario_evidencias_json'] as String), isEmpty);
      expect(fila['diagnostico_previo_ia'], '');
      expect(jsonDecode(fila['datos_json'] as String), isEmpty);
    });
  });

  group('CAMPO-D2 · casos de borde', () {
    test('7. Una orden nueva que solo llegó por listado se guarda sin inventar nada',
        () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(estado: 'asignada', estadoValidacion: 'sin_evaluar'),
        fuente: FuenteOrden.listado,
      );

      final fila = await filaGuardada();
      expect(fila['cliente_nombre'], 'Carlos Gomez Restrepo');
      expect(fila['estado'], 'asignada');
      // Vacío de verdad: no se fabrica un formulario ni fotos requeridas que
      // nadie mandó.
      expect(jsonDecode(fila['formulario_campos_json'] as String), isEmpty);
      expect(jsonDecode(fila['formulario_evidencias_json'] as String), isEmpty);
      expect(fila['diagnostico_previo_ia'], '');
    });

    test('7b. Orden nueva sin detalle: la versión de esquema queda desconocida '
        'y la orden no se habilita', () async {
      // El listado no trae tipo.schema_version y no hay fila anterior de donde
      // sacarla: no se sabe qué versión exige esta orden.
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(estado: 'asignada', estadoValidacion: 'sin_evaluar'),
        fuente: FuenteOrden.listado,
      );

      final fila = await filaGuardada();
      expect(
        fila['schema_version'],
        LocalDatabase.versionEsquemaDesconocida,
        reason: 'un 1 seria afirmar compatibilidad sin tener con que',
      );

      // Y lo que importa: el mecanismo que decide si se puede trabajar.
      final vista = TrabajoVista.desdeOrden(fila);
      expect(vista.versionEsquemaConocida, isFalse);
      expect(
        vista.requiereActualizacion,
        isTrue,
        reason: 'compatibilidad no demostrada no es compatibilidad',
      );
    });

    test('7c. Cuando baja el detalle con una versión soportada, se habilita',
        () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(estado: 'asignada'),
        fuente: FuenteOrden.listado,
      );
      expect(
        TrabajoVista.desdeOrden(await filaGuardada()).requiereActualizacion,
        isTrue,
      );

      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(schemaVersion: 1),
        fuente: FuenteOrden.detalle,
      );

      final vista = TrabajoVista.desdeOrden(await filaGuardada());
      expect(vista.versionEsquema, 1);
      expect(vista.versionEsquemaConocida, isTrue);
      expect(vista.requiereActualizacion, isFalse);
    });

    test('7d. Si el detalle dice que exige una versión más nueva, sigue bloqueada',
        () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(estado: 'asignada'),
        fuente: FuenteOrden.listado,
      );
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(schemaVersion: 3),
        fuente: FuenteOrden.detalle,
      );

      final vista = TrabajoVista.desdeOrden(await filaGuardada());
      expect(vista.versionEsquema, 3);
      expect(vista.versionEsquemaConocida, isTrue);
      expect(vista.requiereActualizacion, isTrue);
    });

    test('8. Repetir el fallback no degrada de a poco', () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(),
        fuente: FuenteOrden.detalle,
      );
      for (var i = 0; i < 3; i++) {
        await baseLocal.upsertOrden(
          orgId: orgId,
          profileId: profileId,
          ordenData: listado(revision: 9 + i),
          fuente: FuenteOrden.listado,
        );
      }

      final filas = await baseLocal.getOrdenes(orgId: orgId, profileId: profileId);
      expect(filas, hasLength(1), reason: 'no se duplica la orden');
      final fila = filas.single;
      expect(jsonDecode(fila['formulario_campos_json'] as String), hasLength(2));
      expect(fila['revision'], 11);
    });

    test('9. Lo de F7A.1 sigue igual: los cinco campos se preservan', () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(),
        fuente: FuenteOrden.detalle,
      );
      // El listado no trae completada_campo_en.
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(),
        fuente: FuenteOrden.listado,
      );

      final vista = TrabajoVista.desdeOrden(await filaGuardada());
      expect(vista.completadaEn, isNotNull);
      expect(vista.latitud, closeTo(6.244203, 0.000001));
      expect(vista.iniciadaEn, isNotNull);
      // Y un detalle que manda null sigue borrando.
      final borrando = detalle();
      borrando['completada_campo_en'] = null;
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: borrando,
        fuente: FuenteOrden.detalle,
      );
      expect(TrabajoVista.desdeOrden(await filaGuardada()).completadaEn, isNull);
    });

    test('10. La cola offline no se toca en ningún caso', () async {
      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: detalle(),
        fuente: FuenteOrden.detalle,
      );
      await baseLocal.transicionarEstadoLocal(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
        nuevoEstadoLocal: 'completada_pendiente_sync',
        tipoAccion: 'completar',
        revisionBase: 7,
        idempotencyKey: 'clave-completar-1',
        payload: <String, dynamic>{'valores': <String, dynamic>{'potencia_rx': -18.7}},
      );

      final antes = await baseLocal.getMutacionesPendientes(
        orgId: orgId,
        profileId: profileId,
      );
      expect(antes, hasLength(1));

      await baseLocal.upsertOrden(
        orgId: orgId,
        profileId: profileId,
        ordenData: listado(),
        fuente: FuenteOrden.listado,
      );

      final despues = await baseLocal.getMutacionesPendientes(
        orgId: orgId,
        profileId: profileId,
      );
      expect(despues, hasLength(1));
      expect(despues.single['idempotency_key'], 'clave-completar-1');
      expect(despues.single['revision_base'], 7);
      expect(
        jsonDecode(despues.single['payload_json']! as String),
        <String, dynamic>{'valores': <String, dynamic>{'potencia_rx': -18.7}},
      );
    });
  });
}
