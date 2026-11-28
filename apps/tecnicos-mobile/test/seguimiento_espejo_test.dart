import 'package:campo/core/storage/local_database.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' show join;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// El seguimiento guardado en el teléfono, y las tres cosas que no puede hacer.
///
/// LO QUE ESTE ARCHIVO DEFIENDE
/// ----------------------------
/// 1. **Desconocido no es vacío.** Si nunca se descargó, `leerSeguimiento`
///    devuelve `null` — no un seguimiento con la lista de eventos vacía. La
///    diferencia es todo: una línea de tiempo vacía se lee como «este trabajo no
///    tiene historia», y lo que pasa en realidad es «no pude preguntar». Es la
///    misma regla que el inventario aplica con las existencias.
///
/// 2. **Una descarga que falla no destruye el espejo bueno.** Una caída de red no
///    puede convertir `INICIO → AVANCE → BLOQUEO` en una pantalla en blanco.
///
/// 3. **El teléfono no interpreta: guarda.** Lo que llega se conserva entero,
///    incluidos los tipos de evento y las claves que la app no conoce. Si mañana
///    el backend agrega `medicion_extraordinaria`, el espejo lo guarda sin que
///    nadie publique una versión nueva de la aplicación.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // Base propia de esta suite: contra la compartida, el borrado del tearDown se
  // lleva puesta cualquier otra que corra en paralelo.
  LocalDatabase.usarBaseDePruebas('pruebas_seguimiento_espejo.db');

  late LocalDatabase base;

  setUp(() async {
    LocalDatabase.resetForTesting();
    base = LocalDatabase();
  });

  tearDown(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(
        await databaseFactory.getDatabasesPath(),
        'pruebas_seguimiento_espejo.db',
      ),
    );
  });

  /// Un seguimiento con la forma que devuelve el backend de verdad.
  Map<String, dynamic> seguimiento({List<Map<String, dynamic>>? eventos}) {
    return <String, dynamic>{
      'orden_id': 'ot-1',
      'estado_operativo': 'en_sitio',
      'eventos': eventos ??
          <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'e1',
              'tipo': 'inicio_campo',
              'etiqueta': 'INICIO',
              'es_seguimiento': true,
              'recibido_en': '2026-10-01T08:14:00Z',
              'detalle': <Map<String, dynamic>>[
                <String, dynamic>{
                  'id': 'punto_intervenido',
                  'titulo': 'Punto intervenido',
                  'valor': 'CTO-045',
                },
              ],
            },
            <String, dynamic>{
              'id': 'e2',
              'tipo': 'avance_campo',
              'etiqueta': 'AVANCE',
              'es_seguimiento': true,
              'recibido_en': '2026-10-01T08:42:00Z',
              'detalle': <Map<String, dynamic>>[],
            },
          ],
      'ultimo_reporte': <String, dynamic>{
        'tipo': 'avance_campo',
        'etiqueta': 'AVANCE',
        'minutos_desde_que_lo_recibimos': 12,
      },
      'salud': <String, dynamic>{'tipo': 'al_dia', 'etiqueta': 'Al día'},
      'formularios': <String, dynamic>{
        'avance': <String, dynamic>{
          'momento': 'avance',
          'campos': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'validaciones',
              'titulo': 'Validaciones realizadas',
              'tipo': 'texto',
              'reglas': <String, dynamic>{'required': true},
            },
          ],
        },
      },
    };
  }

  group('1. Desconocido no es vacío', () {
    test('una orden que nunca se descargó devuelve null', () async {
      final leido = await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1');

      expect(
        leido,
        isNull,
        reason: 'Devolver un seguimiento con eventos vacíos haría que la '
            'pantalla diga "este trabajo no tiene historia" cuando lo cierto '
            'es que nunca se pudo preguntar.',
      );
    });

    test('otra orden de la misma empresa no hereda el seguimiento', () async {
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(),
      );

      expect(
        await base.leerSeguimiento(ordenId: 'ot-2', orgId: 'org-1'),
        isNull,
      );
    });

    test('otra EMPRESA no lo ve, aunque el id de la orden coincida', () async {
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(),
      );

      expect(
        await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-2'),
        isNull,
      );
    });
  });

  group('2. Un fallo no destruye el espejo bueno', () {
    test('lo guardado sigue entero después de una lectura cualquiera',
        () async {
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(),
      );

      final antes = await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1');
      expect(antes, isNotNull);
      expect((antes!['eventos'] as List).length, 2);

      // Un GET que falla no llama a `guardarSeguimiento`: el servicio devuelve
      // false y la base no se toca. Lo que se afirma es que leer no destruye.
      final despues =
          await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1');

      expect((despues!['eventos'] as List).length, 2,
          reason: 'Una caída de red no puede convertir una historia en una '
              'pantalla en blanco.');
    });

    test('un JSON corrupto se lee como "no hay", no como media historia',
        () async {
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(),
      );

      // Se corrompe lo guardado, que es lo que dejaría una escritura cortada.
      final db = await base.database;
      await db.update(
        'local_seguimiento',
        <String, Object?>{'seguimiento_json': '{esto no es json'},
        where: 'orden_id = ? AND org_id = ?',
        whereArgs: ['ot-1', 'org-1'],
      );

      expect(
        await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1'),
        isNull,
        reason: 'Mejor decir que no se sabe que dibujar media historia.',
      );
    });
  });

  group('3. El teléfono guarda, no interpreta', () {
    test('un tipo de evento que la app no conoce se conserva igual', () async {
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(
          eventos: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'ex1',
              'tipo': 'medicion_extraordinaria',
              'etiqueta': 'Medición extraordinaria',
              'severidad': 'atencion',
              'es_seguimiento': true,
              'recibido_en': '2026-10-01T09:00:00Z',
              'detalle': <Map<String, dynamic>>[
                <String, dynamic>{
                  'id': 'presion',
                  'titulo': 'Presión del equipo',
                  'valor': '2.4',
                },
              ],
            },
          ],
        ),
      );

      final leido = await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1');
      final evento = (leido!['eventos'] as List).first as Map;

      expect(evento['tipo'], 'medicion_extraordinaria');
      expect(evento['etiqueta'], 'Medición extraordinaria');
      expect(evento['severidad'], 'atencion');
      expect(
        ((evento['detalle'] as List).first as Map)['titulo'],
        'Presión del equipo',
      );
    });

    test('una clave que nadie declaró tampoco se pierde ni rompe nada',
        () async {
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: <String, dynamic>{
          ...seguimiento(),
          'algo_que_nadie_declaro': <String, dynamic>{
            'color_del_borde': 'azul',
          },
        },
      );

      final leido = await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1');

      expect(leido, isNotNull);
      expect(leido!['algo_que_nadie_declaro'], isNotNull);
      // Y lo que la pantalla sí usa sigue intacto.
      expect((leido['salud'] as Map)['etiqueta'], 'Al día');
    });

    test('los formularios llegan con el vocabulario que el widget ya lee',
        () async {
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(),
      );

      final leido = await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1');
      final formularios = leido!['formularios'] as Map;
      final avance = formularios['avance'] as Map;
      final campo = (avance['campos'] as List).first as Map;

      // `id`, `titulo`, `tipo` y `reglas.required`: el mismo vocabulario que
      // `CampoDelFormulario.desdeEsquema` ya sabe leer. Por eso ese archivo no
      // se toca.
      expect(campo['id'], 'validaciones');
      expect(campo['titulo'], 'Validaciones realizadas');
      expect(campo['tipo'], 'texto');
      expect((campo['reglas'] as Map)['required'], isTrue);
    });
  });

  group('4. El espejo dice cuándo se trajo', () {
    test('guardar deja la hora de sincronización', () async {
      final antes = DateTime.now().millisecondsSinceEpoch;
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(),
      );

      final leido = await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1');

      expect(
        leido!['sincronizado_en'] as int,
        greaterThanOrEqualTo(antes),
        reason: 'Un espejo sin su hora invita a leerlo como si fuera de ahora.',
      );
    });

    test('volver a guardar reemplaza: es un espejo, no un historial', () async {
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(),
      );
      await base.guardarSeguimiento(
        ordenId: 'ot-1',
        orgId: 'org-1',
        seguimiento: seguimiento(
          eventos: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'solo-uno',
              'tipo': 'cierre_campo',
              'etiqueta': 'CIERRE DE CAMPO',
              'es_seguimiento': true,
              'recibido_en': '2026-10-01T10:00:00Z',
              'detalle': <Map<String, dynamic>>[],
            },
          ],
        ),
      );

      final db = await base.database;
      final filas = await db.query(
        'local_seguimiento',
        where: 'orden_id = ? AND org_id = ?',
        whereArgs: ['ot-1', 'org-1'],
      );
      expect(filas.length, 1);

      final leido = await base.leerSeguimiento(ordenId: 'ot-1', orgId: 'org-1');
      final eventos = leido!['eventos'] as List;
      expect(eventos.length, 1);
      expect((eventos.first as Map)['id'], 'solo-uno');
    });
  });
}
