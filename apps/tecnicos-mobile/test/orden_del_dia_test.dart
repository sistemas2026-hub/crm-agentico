import 'dart:async';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/features/trabajo/orden_operativo.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// EL ORDEN DEL DÍA QUE ARMA EL SUPERVISOR (29/10/2026).
///
/// Pedido del usuario: «en la app, cuando esté haciendo un ticket, le indique
/// con cuál sigue, y así que el mismo Supervisor le arme el orden en que
/// trabaja los tickets». El servidor decide el orden (`campo/orden_del_dia.py`);
/// la app lo sigue —solo el de hoy— y lo dice en la orden: «SIGUE».

final DateTime _ahora = DateTime(2026, 10, 29, 9, 0);
const String _hoy = '2026-10-29';

Map<String, dynamic> _fila(
  String id,
  int numero, {
  String estado = 'asignada',
  String prioridad = '',
  String? vence,
  int? lugar,
  String fecha = _hoy,
}) =>
    <String, dynamic>{
      'id': id,
      'numero': numero,
      'estado': estado,
      'cliente_nombre': 'Cliente $numero',
      'direccion': 'Calle $numero',
      'telefono': '',
      'tipo_nombre': 'Soporte',
      'tipo_codigo': 'sop',
      'schema_version': 1,
      'revision': 1,
      'prioridad': prioridad,
      'zona': 'Barrio $numero',
      'sla_vence_en': ?vence,
      'orden_del_dia': ?lugar,
      'orden_del_dia_fecha': lugar == null ? null : fecha,
    };

List<String> _ids(List<Map<String, dynamic>> filas) => OrdenOperativo.ordenar(
      filas.map(TrabajoVista.desdeOrden).toList(),
      ahora: _ahora,
    ).map((TrabajoVista t) => t.id).toList();

void main() {
  group('la regla', () {
    test('el orden del Supervisor manda sobre lo que vence y la prioridad, '
        'después de lo empezado', () {
      expect(
        _ids(<Map<String, dynamic>>[
          _fila('vence', 1, vence: _ahora.add(const Duration(minutes: 30)).toIso8601String()),
          _fila('alta', 2, prioridad: 'alta'),
          _fila('segunda', 3, lugar: 2),
          _fila('primera', 4, lugar: 1),
          _fila('camino', 5, estado: 'en_camino', lugar: 9),
          _fila('cerrada', 6, estado: 'cerrada', lugar: 3),
        ]),
        <String>['camino', 'primera', 'segunda', 'vence', 'alta', 'cerrada'],
      );
    });

    test('el orden de otro día no cuenta: se ordena con la regla de siempre', () {
      expect(
        _ids(<Map<String, dynamic>>[
          _fila('ayer', 1, lugar: 1, fecha: '2026-10-28'),
          _fila('alta', 2, prioridad: 'alta'),
        ]),
        <String>['alta', 'ayer'],
      );
    });

    test('con cuál sigue: la siguiente que no es esta ni está terminada', () {
      final List<TrabajoVista> dia = <Map<String, dynamic>>[
        _fila('a', 1, estado: 'en_sitio', lugar: 1),
        _fila('b', 2, estado: 'completada_campo', lugar: 2),
        _fila('c', 3, lugar: 3),
        _fila('d', 4, lugar: 4),
      ].map(TrabajoVista.desdeOrden).toList();

      expect(OrdenOperativo.queSigue(dia, actual: 'a', ahora: _ahora)?.id, 'c');
      expect(OrdenOperativo.queSigue(dia, actual: 'c', ahora: _ahora)?.id, 'a');
      expect(
        OrdenOperativo.queSigue(dia.sublist(0, 2), actual: 'a', ahora: _ahora),
        isNull,
        reason: 'lo demás está terminado: no hay con cuál seguir',
      );
    });
  });

  group('la base del teléfono', () {
    final JornadaDePrueba j = JornadaDePrueba('orden_del_dia.db');

    setUpAll(j.prepararElEntorno);
    setUp(j.empezar);
    tearDown(j.terminar);
    tearDownAll(j.cerrarTodo);

    Future<TrabajoVista> guardarYLeer(Map<String, dynamic> compromiso) async {
      await j.db.upsertOrden(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
        ordenData: <String, dynamic>{
          'id': 'ot-1',
          'numero': 4832,
          'estado': 'asignada',
          'cliente_nombre': 'Cliente',
          'revision': 1,
          'tipo': <String, dynamic>{'nombre': 'Soporte', 'codigo': 'sop', 'schema_version': 1},
          'compromiso': compromiso,
        },
      );
      final List<Map<String, Object?>> filas = await (await j.db.database).query(
        'local_ordenes',
        where: 'id = ?',
        whereArgs: <Object?>['ot-1'],
      );
      return TrabajoVista.desdeOrden(Map<String, dynamic>.from(filas.single));
    }

    test('guarda el lugar y su día; sin la clave lo conserva; con null lo borra', () async {
      await j.limpiar();
      TrabajoVista t =
          await guardarYLeer(<String, dynamic>{'orden_del_dia': 2, 'orden_del_dia_fecha': _hoy});
      expect((t.ordenDelDia, t.ordenDelDiaFecha), (2, _hoy));
      expect(t.ordenDelDiaPara(_ahora), 2);

      t = await guardarYLeer(<String, dynamic>{});
      expect(t.ordenDelDia, 2, reason: 'una clave que no vino no borra lo que había');

      t = await guardarYLeer(<String, dynamic>{'orden_del_dia': null, 'orden_del_dia_fecha': null});
      expect(t.ordenDelDia, isNull, reason: 'un null del servidor sí manda');
    });
  });

  group('la orden dice con cuál sigue', () {
    late StreamController<SyncStatus> avisos;
    late OrdenesJornada ordenes;

    Future<void> abrir(WidgetTester t, List<Map<String, dynamic>> filas, String id) async {
      t.view.physicalSize = const Size(1000, 4400);
      t.view.devicePixelRatio = 1.0;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);
      avisos = StreamController<SyncStatus>.broadcast();
      ordenes = OrdenesJornada(
        leerOrdenes: () async => filas,
        sincronizar: () async {},
        avisosDeSincronizacion: avisos.stream,
      );
      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: DetalleOrdenScreen(
          ordenId: id,
          ordenes: ordenes,
          acciones: AccionesOrden(
            transicionar: ({
              required String ordenId,
              required String nuevoEstadoLocal,
              required String tipoAccion,
              required int revisionBase,
            }) async {},
            sincronizar: () async {},
          ),
        ),
      ));
      await t.pumpAndSettle();
    }

    tearDown(() async {
      await avisos.close();
      ordenes.dispose();
    });

    testWidgets('en la primera dice la segunda del Supervisor', (WidgetTester t) async {
      final String hoy = DateTime.now().toIso8601String().substring(0, 10);
      await abrir(t, <Map<String, dynamic>>[
        _fila('ot-1', 11, estado: 'en_sitio', lugar: 1, fecha: hoy),
        _fila('ot-2', 12, prioridad: 'baja', lugar: 3, fecha: hoy),
        _fila('ot-3', 13, prioridad: 'alta', lugar: 2, fecha: hoy),
      ], 'ot-1');

      expect(find.byKey(const ValueKey<String>('que-sigue')), findsOneWidget);
      expect(find.text('SIGUE'), findsOneWidget);
      expect(find.text('OT #13 · Cliente 13'), findsOneWidget);
      expect(find.text('Barrio 13'), findsOneWidget);
    });

    testWidgets('si no queda nada por hacer, no lo dice', (WidgetTester t) async {
      await abrir(t, <Map<String, dynamic>>[
        _fila('ot-1', 11, estado: 'en_sitio'),
        _fila('ot-2', 12, estado: 'cerrada'),
      ], 'ot-1');

      expect(find.byKey(const ValueKey<String>('que-sigue')), findsNothing);
    });
  });
}
