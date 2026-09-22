import 'dart:convert';

import 'package:campo/core/storage/local_database.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' show join;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// La base local guarda lo que el backend empezó a entregar el 22/09/2026.
///
/// Siete datos que ya estaban en el servidor y ningún serializador devolvía
/// (tanda 1 de `SPEC/BACKEND_CAMPO_DATOS.md`). El que más importa es la
/// devolución del supervisor: sin guardarla, el técnico abre una orden
/// devuelta sin señal y sigue sin saber qué rehacer.
///
/// Se prueba lo mismo que en la migración anterior: que una base vieja se
/// actualiza sin perder nada, y que lo que solo dice el detalle no lo borra un
/// listado.
Map<String, dynamic> _detalle({
  String id = 'ot-1',
  Map<String, dynamic>? correccion,
  Map<String, dynamic>? origen,
  Map<String, dynamic>? contexto,
  List<Map<String, dynamic>>? pasos,
  int vuelta = 1,
}) {
  return <String, dynamic>{
    'id': id,
    'numero': 4832,
    'estado_operativo': 'en_sitio',
    'revision': 7,
    'vuelta': vuelta,
    'cliente': <String, dynamic>{
      'nombre': 'Carlos Gomez',
      'direccion': 'Cra 45 #12-88',
      'telefono': '3001234567',
    },
    'tipo': <String, dynamic>{
      'codigo': 'ftth_correctivo',
      'nombre': 'Correctivo Fibra',
      'schema_version': 1,
      'pasos': ?pasos,
    },
    'schema': <String, dynamic>{
      'campos': <dynamic>[],
      'evidencias': <dynamic>[
        <String, dynamic>{'id': 'foto_cto', 'descripcion': 'Foto de la CTO'},
        <String, dynamic>{'id': 'foto_potencia', 'descripcion': 'Foto de la potencia'},
      ],
    },
    'origen': ?origen,
    'contexto': ?contexto,
    'correccion': ?correccion,
  };
}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  late LocalDatabase base;

  setUp(() async {
    LocalDatabase.resetForTesting();
    base = LocalDatabase();
  });

  tearDown(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(), 'dexter_campo.db'),
    );
  });

  group('Base local v7', () {
    test('1. La devolución del supervisor se guarda y se lee entera', () async {
      await base.upsertOrden(
        orgId: 'org',
        profileId: 'prof',
        ordenData: _detalle(
          vuelta: 2,
          correccion: <String, dynamic>{
            'vuelta': 2,
            'requisitos': <String>['foto_potencia'],
            'observacion': 'La medición no coincide con la OLT',
            'devuelta_en': '2026-09-22T12:00:00Z',
          },
        ),
      );

      final fila = await base.getOrden(orgId: 'org', profileId: 'prof', id: 'ot-1');
      final guardada = jsonDecode(fila!['correccion_json'] as String) as Map<String, dynamic>;

      expect(guardada['requisitos'], <String>['foto_potencia']);
      expect(guardada['observacion'], 'La medición no coincide con la OLT');
      expect(fila['vuelta'], 2);
    });

    test('2. Un listado no borra la devolución que trajo el detalle', () async {
      await base.upsertOrden(
        orgId: 'org',
        profileId: 'prof',
        ordenData: _detalle(
          vuelta: 2,
          correccion: <String, dynamic>{
            'vuelta': 2,
            'requisitos': <String>['foto_cto'],
            'observacion': 'Foto movida',
          },
          contexto: <String, dynamic>{'sn_onu': '48575443-A9B0C1'},
          pasos: <Map<String, dynamic>>[
            <String, dynamic>{'id': 'p1', 'titulo': 'Llegada'},
          ],
        ),
      );

      // Se cae el detalle y solo entra lo del listado.
      await base.upsertOrden(
        orgId: 'org',
        profileId: 'prof',
        fuente: FuenteOrden.listado,
        ordenData: <String, dynamic>{
          'id': 'ot-1',
          'numero': 4832,
          'estado_operativo': 'en_sitio',
          'revision': 8,
          'cliente': <String, dynamic>{'nombre': 'Carlos Gomez', 'direccion': 'Cra 45 #12-88'},
          'tipo': <String, dynamic>{'codigo': 'ftth_correctivo', 'nombre': 'Correctivo Fibra'},
        },
      );

      final fila = await base.getOrden(orgId: 'org', profileId: 'prof', id: 'ot-1');
      expect(
        fila!['correccion_json'],
        isNotNull,
        reason: 'un listado no puede afirmar que ya no hay nada que corregir',
      );
      expect(fila['contexto_json'], isNotNull);
      expect(fila['pasos_json'], isNotNull);
      // Y lo que el listado sí sabe se actualiza.
      expect(fila['revision'], 8);
    });

    test('3. El origen viaja en las dos respuestas, así que el listado lo manda',
        () async {
      await base.upsertOrden(
        orgId: 'org',
        profileId: 'prof',
        fuente: FuenteOrden.listado,
        ordenData: <String, dynamic>{
          'id': 'ot-2',
          'numero': 4833,
          'estado_operativo': 'asignada',
          'cliente': <String, dynamic>{'nombre': 'Marta', 'direccion': 'Calle 1'},
          'tipo': <String, dynamic>{'codigo': 'ftth', 'nombre': 'Instalación'},
          'origen': <String, dynamic>{
            'sistema': 'wisphub',
            'tipo': 'ticket',
            'ref': 'WH-91288',
          },
        },
      );

      final fila = await base.getOrden(orgId: 'org', profileId: 'prof', id: 'ot-2');
      final origen = jsonDecode(fila!['origen_json'] as String) as Map<String, dynamic>;
      expect(origen['ref'], 'WH-91288');
    });

    test('4. Una orden que nadie devolvió no guarda una corrección inventada',
        () async {
      await base.upsertOrden(
        orgId: 'org',
        profileId: 'prof',
        ordenData: _detalle(),
      );

      final fila = await base.getOrden(orgId: 'org', profileId: 'prof', id: 'ot-1');
      expect(fila!['correccion_json'], isNull);
      expect(fila['vuelta'], 1);
    });

    test('5. Una base de la versión 6 se actualiza sin perder lo que tenía',
        () async {
      // Una base en disco como la que tendría un técnico que no actualizó.
      final String ruta =
          join(await databaseFactory.getDatabasesPath(), 'dexter_campo.db');
      LocalDatabase.resetForTesting();
      await databaseFactory.deleteDatabase(ruta);

      final vieja = await databaseFactory.openDatabase(
        ruta,
        options: OpenDatabaseOptions(version: 6),
      );
      await vieja.execute('''
        CREATE TABLE local_ordenes (
          id TEXT NOT NULL,
          org_id TEXT NOT NULL,
          profile_id TEXT NOT NULL,
          numero INTEGER,
          estado TEXT NOT NULL,
          cliente_nombre TEXT NOT NULL,
          direccion TEXT NOT NULL,
          telefono TEXT,
          tipo_nombre TEXT NOT NULL,
          tipo_codigo TEXT NOT NULL,
          work_type_version_id TEXT,
          schema_version INTEGER NOT NULL DEFAULT 1,
          formulario_campos_json TEXT,
          formulario_evidencias_json TEXT,
          revision INTEGER NOT NULL DEFAULT 0,
          diagnostico_previo_ia TEXT,
          datos_json TEXT,
          fecha_compromiso TEXT,
          estado_validacion TEXT,
          cliente_lat REAL,
          cliente_lng REAL,
          iniciada_en TEXT,
          completada_campo_en TEXT,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY (id, org_id, profile_id)
        )
      ''');
      await vieja.insert('local_ordenes', <String, Object?>{
        'id': 'vieja',
        'org_id': 'org',
        'profile_id': 'prof',
        'numero': 1,
        'estado': 'en_sitio',
        'cliente_nombre': 'Cliente de antes',
        'direccion': 'Calle vieja',
        'tipo_nombre': 'Instalación',
        'tipo_codigo': 'ftth',
        'schema_version': 1,
        'formulario_campos_json': '[]',
        'formulario_evidencias_json': '[]',
        'revision': 3,
        'diagnostico_previo_ia': 'Cortes intermitentes',
        'updated_at': 1700000000000,
      });
      await vieja.close();

      // Al abrirla, la aplicación la migra.
      final db = await LocalDatabase().database;
      final columnas = (await db.rawQuery('PRAGMA table_info(local_ordenes);'))
          .map((Map<String, Object?> c) => c['name'] as String)
          .toSet();

      for (final String col in <String>[
        'cerrada_en',
        'vuelta',
        'origen_json',
        'contexto_json',
        'correccion_json',
        'pasos_json',
        'cuadrilla_json',
      ]) {
        expect(columnas, contains(col), reason: 'falta la columna $col');
      }

      // Y la orden que ya estaba sigue estando, con lo suyo intacto.
      final fila = (await db.query('local_ordenes',
              where: 'id = ?', whereArgs: <Object?>['vieja']))
          .single;
      expect(fila['cliente_nombre'], 'Cliente de antes');
      expect(fila['diagnostico_previo_ia'], 'Cortes intermitentes');
      expect(fila['revision'], 3);
      // Lo nuevo empieza vacío, no inventado.
      expect(fila['correccion_json'], isNull);
      expect(fila['vuelta'], isNull);

      await databaseFactory.deleteDatabase(ruta);
    });
  });
}
