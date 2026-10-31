import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/trabajo/orden_operativo.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:campo/features/trabajo/vencimiento.dart';
import 'package:campo/features/trabajo/widgets/tarjeta_trabajo.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// LA TARJETA DE ÓRDENES, COMO LA DE PROGRAMACIÓN (29/10/2026).
///
/// El usuario, con la tarjeta de la web a la vista: «la tarjeta quedó bien,
/// ¿en la app debe salir así también?». La misma jerarquía en el teléfono: el
/// asunto del ticket como título, y arriba una franja con el lugar que le dio
/// el Supervisor, la prioridad, cuándo vence y cuál sigue.

final DateTime _ahora = DateTime(2026, 10, 29, 9, 0);
const String _hoy = '2026-10-29';

Map<String, dynamic> _fila(
  String id,
  int numero, {
  String estado = 'asignada',
  String prioridad = '',
  String? vence,
  int? lugar,
  String asunto = '',
  String resumen = '',
  String tipo = 'Instalación FTTH',
  String? completada,
}) =>
    <String, dynamic>{
      'id': id,
      'numero': numero,
      'estado': estado,
      'cliente_nombre': 'Beatriz Pinzón',
      'direccion': 'Calle $numero',
      'telefono': '',
      'tipo_nombre': tipo,
      'tipo_codigo': 'x',
      'schema_version': 1,
      'revision': 1,
      'prioridad': prioridad,
      'asunto': asunto,
      'resumen': resumen,
      'sla_vence_en': ?vence,
      'orden_del_dia': ?lugar,
      'orden_del_dia_fecha': lugar == null ? null : _hoy,
      'completada_campo_en': ?completada,
    };

TrabajoVista _t(Map<String, dynamic> f) => TrabajoVista.desdeOrden(f);

Future<void> _montar(WidgetTester t, TrabajoVista trabajo, {String? marca}) async {
  t.view.physicalSize = const Size(1000, 2400);
  t.view.devicePixelRatio = 1.0;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
  await t.pumpWidget(MaterialApp(
    theme: AppTheme.lightTheme,
    home: Scaffold(
      body: SingleChildScrollView(
        child: TarjetaTrabajo(
          trabajo: trabajo,
          mostrarDatosFuturos: false,
          marca: marca,
          ahora: _ahora,
        ),
      ),
    ),
  ));
  await t.pumpAndSettle();
}

void main() {
  group('cuándo vence, dicho como en Programación', () {
    test('venció, hoy, mañana, otro día; y sin fecha no se inventa', () {
      String? texto(DateTime? d) => Vencimiento.de(d, _ahora)?.texto;
      expect(texto(DateTime(2026, 10, 28, 23, 59)), 'Venció el 28/10');
      expect(texto(DateTime(2026, 10, 29, 23, 59)), 'Vence hoy');
      expect(texto(DateTime(2026, 10, 30, 0, 1)), 'Vence mañana');
      expect(texto(DateTime(2026, 11, 2, 12)), 'Vence el 02/11');
      expect(Vencimiento.de(null, _ahora), isNull);
      expect(Vencimiento.de(DateTime(2026, 10, 28), _ahora)?.tono,
          TonoDeVencimiento.vencida);
      expect(Vencimiento.de(DateTime(2026, 10, 29, 18), _ahora)?.tono,
          TonoDeVencimiento.hoy);
    });
  });

  group('cuál sigue en la lista', () {
    test('la primera sin empezar; «Empieza por esta» si no arrancó ninguna', () {
      final List<TrabajoVista> dia = <TrabajoVista>[
        _t(_fila('b', 2, lugar: 2)),
        _t(_fila('a', 1, lugar: 1)),
        _t(_fila('vieja', 9, estado: 'cerrada', completada: '2026-10-20T10:00:00-05:00')),
      ];
      expect(OrdenOperativo.laQueSigue(dia, ahora: _ahora),
          (id: 'a', texto: 'Empieza por esta'),
          reason: 'una cerrada de otro día no cuenta como haber arrancado hoy');
    });

    test('con una en sitio o hecha hoy, «Sigue esta» y no la empezada', () {
      expect(
        OrdenOperativo.laQueSigue(<TrabajoVista>[
          _t(_fila('en', 1, estado: 'en_sitio', lugar: 1)),
          _t(_fila('b', 2, lugar: 2)),
        ], ahora: _ahora),
        (id: 'b', texto: 'Sigue esta'),
      );
      expect(
        OrdenOperativo.laQueSigue(<TrabajoVista>[
          _t(_fila('hecha', 1,
              estado: 'completada_campo', completada: '2026-10-29T08:10:00-05:00')),
          _t(_fila('b', 2, lugar: 2)),
        ], ahora: _ahora),
        (id: 'b', texto: 'Sigue esta'),
      );
    });

    test('si no queda nada por hacer, no marca ninguna', () {
      expect(
        OrdenOperativo.laQueSigue(<TrabajoVista>[
          _t(_fila('en', 1, estado: 'en_camino')),
          _t(_fila('c', 2, estado: 'cerrada')),
        ], ahora: _ahora),
        isNull,
      );
    });
  });

  group('la tarjeta', () {
    testWidgets('el asunto es el título y el cliente va debajo', (WidgetTester t) async {
      await _montar(t, _t(_fila('a', 12, asunto: 'No Tiene Internet')));

      expect(find.byKey(const ValueKey<String>('asunto')), findsOneWidget);
      final double titulo = t.getTopLeft(find.text('No Tiene Internet')).dy;
      final double cliente = t.getTopLeft(find.text('Beatriz Pinzón')).dy;
      expect(titulo, lessThan(cliente));
    });

    // El usuario, 29/10/2026: «en la app aún sale "según el Supervisor: el
    // ticket es una solicitud de instalación de TDT" y se corta; debería salir
    // así como está en Programación». Lo propuesto va entero en el detalle.
    testWidgets('en una incidencia, el asunto es el título y lo propuesto no va',
        (WidgetTester t) async {
      await _montar(
          t,
          _t(_fila('a', 3,
              tipo: 'Soporte en campo',
              asunto: 'No Tiene Internet',
              resumen: 'Según el Supervisor: revisar la ONU')));

      expect(find.byKey(const ValueKey<String>('asunto')), findsOneWidget);
      expect(find.text('No Tiene Internet'), findsOneWidget);
      expect(find.textContaining('Según el Supervisor'), findsNothing);
    });

    testWidgets('sin asunto, el título es el tipo, como en Programación',
        (WidgetTester t) async {
      await _montar(t,
          _t(_fila('a', 3, tipo: 'Soporte en campo', resumen: 'Según el Supervisor: x')));
      expect(find.byKey(const ValueKey<String>('asunto')), findsNothing);
      expect(find.text('Soporte en campo'), findsOneWidget);
      expect(find.textContaining('Según el Supervisor'), findsNothing);
    });

    testWidgets('la franja: el lugar de hoy, la prioridad, el vencimiento y la marca',
        (WidgetTester t) async {
      await _montar(
        t,
        _t(_fila('a', 12,
            lugar: 2, prioridad: 'alta', vence: '2026-10-29T18:00:00')),
        marca: 'Sigue esta',
      );

      final Finder lugar = find.byKey(const ValueKey<String>('lugar-del-dia'));
      expect(lugar, findsOneWidget);
      expect(find.descendant(of: lugar, matching: find.text('2')), findsOneWidget);
      expect(find.text('Prioridad alta'), findsOneWidget);
      expect(find.text('Vence hoy'), findsOneWidget);
      expect(find.byKey(const ValueKey<String>('marca-que-sigue')), findsOneWidget);
      expect(find.text('Sigue esta'), findsOneWidget);
    });

    testWidgets('sin nada que decir no dibuja la franja; ni el lugar de otro día',
        (WidgetTester t) async {
      final Map<String, dynamic> ayer = _fila('a', 12, lugar: 1)
        ..['orden_del_dia_fecha'] = '2026-10-28';
      await _montar(t, _t(ayer));

      expect(find.byKey(const ValueKey<String>('lugar-del-dia')), findsNothing);
      expect(find.byKey(const ValueKey<String>('marca-que-sigue')), findsNothing);
      expect(find.textContaining('Prioridad'), findsNothing);
      expect(find.textContaining('Vence'), findsNothing);
    });

    testWidgets('si Dexter la evaluó, la franja no repite una prioridad que la contradiga',
        (WidgetTester t) async {
      final Map<String, dynamic> f = _fila('a', 3, tipo: 'Soporte en campo', prioridad: 'baja')
        ..['contexto_json'] =
            '{"prioridad_dexter": {"nivel": "alta", "motivos": ["tercera visita"]}}';
      await _montar(t, _t(f));

      expect(find.text('Prioridad baja'), findsNothing);
      expect(find.text('tercera visita'), findsOneWidget);
    });
  });

  group('la base del teléfono guarda el asunto', () {
    final JornadaDePrueba j = JornadaDePrueba('asunto_de_la_orden.db');

    setUpAll(j.prepararElEntorno);
    setUp(j.empezar);
    tearDown(j.terminar);
    tearDownAll(j.cerrarTodo);

    Future<TrabajoVista> guardarYLeer(Map<String, dynamic> extra) async {
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
          ...extra,
        },
      );
      final List<Map<String, Object?>> filas = await (await j.db.database).query(
        'local_ordenes',
        where: 'id = ?',
        whereArgs: <Object?>['ot-1'],
      );
      return TrabajoVista.desdeOrden(Map<String, dynamic>.from(filas.single));
    }

    test('lo guarda; sin la clave lo conserva; vacío lo borra', () async {
      await j.limpiar();
      TrabajoVista t = await guardarYLeer(<String, dynamic>{'asunto': 'No Tiene Internet'});
      expect(t.asunto, 'No Tiene Internet');

      t = await guardarYLeer(<String, dynamic>{});
      expect(t.asunto, 'No Tiene Internet',
          reason: 'un servidor viejo no manda la clave: no se borra lo que había');

      t = await guardarYLeer(<String, dynamic>{'asunto': ''});
      expect(t.asunto, '', reason: 'el servidor dice que no tiene asunto, y manda');
    });
  });
}
