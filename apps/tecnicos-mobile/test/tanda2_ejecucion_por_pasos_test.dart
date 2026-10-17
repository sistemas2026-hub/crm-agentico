/// TANDA 2 (17/10/2026): la ejecución por pasos de la plantilla, «Comprobar
/// conexión» dentro de la intervención, y un solo cierre.
///
///   A  la regla que reparte campos y fotos en los pasos de la plantilla real
///   B  la pantalla por pasos: uno a la vez, con anterior y siguiente; sin
///      pasos, la de siempre
///   C  «Finalizar» es el único cierre: pregunta por el material si no hay,
///      pide el reporte de cierre y no lo duplica en un reintento
///   D  «Comprobar conexión»: la ficha es «Al despachar», la medición es
///      «Ahora», y sin serial se puede volver a pedir la ficha
///   E  el dato «no usé materiales» viaja aparte de las respuestas
///   F  el reporte de cierre con id fijo no se duplica en la cola del teléfono
library;

import 'dart:convert';

import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/comprobar_conexion.dart';
import 'package:campo/features/ejecucion/datos_de_ejecucion.dart';
import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' show join;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

const List<Map<String, dynamic>> _pasos = <Map<String, dynamic>>[
  <String, dynamic>{'id': 'paso_1', 'titulo': 'Diagnóstico'},
  <String, dynamic>{'id': 'paso_2', 'titulo': 'Solución'},
];

Map<String, dynamic> _campo(String id, String titulo, {String paso = '', bool req = true}) =>
    <String, dynamic>{
      'id': id,
      'titulo': titulo,
      'tipo': 'texto',
      'reglas': <String, dynamic>{'required': req},
      if (paso.isNotEmpty) 'paso': paso,
    };

void _pantallaAlta(WidgetTester t) {
  t.view.physicalSize = const Size(1000, 4200);
  t.view.devicePixelRatio = 1.0;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
}

Widget _app(FuenteDeEjecucionFalsa fuente, {AccionesOrden? acciones}) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: EjecucionScreen(
        ordenId: 'ot-1',
        fuente: fuente,
        acciones: acciones,
        resumenDeSync: const SyncSummary(
          status: SyncStatus.idle,
          isSyncing: false,
          hasConnectionError: false,
          mutacionesPendientes: 0,
          mutacionesConflicto: 0,
          evidenciasPendientes: 0,
          datosDirty: 0,
        ),
      ),
    );

Map<String, dynamic> _seguimientoConCierre() => <String, dynamic>{
      'eventos': <dynamic>[],
      'momentos_registrados': <String>[],
      'formularios': <String, dynamic>{
        for (final String m in <String>['inicio', 'avance', 'bloqueo', 'cierre'])
          m: <String, dynamic>{
            'momento': m,
            'campos': <Map<String, dynamic>>[
              _campo('nota_$m', m == 'cierre' ? 'Qué se hizo para resolverlo' : 'Nota'),
            ],
            'evidencias': <dynamic>[],
          },
      },
    };

void main() {
  group('A · los pasos son los de la plantilla', () {
    test('a1 · en orden del protocolo; lo suelto va a «Otros datos»; la firma no', () {
      final List<PasoDeEjecucion> p = pasosDeEjecucion(
        campos: <dynamic>[
          _campo('sol', 'Qué se cambió', paso: 'paso_2'),
          _campo('med', 'Medición al llegar', paso: 'paso_1'),
          _campo('obs', 'Observaciones'),
        ],
        requisitos: <dynamic>[
          <String, dynamic>{'id': 'f1', 'titulo': 'Foto caja', 'paso': 'paso_1'},
          <String, dynamic>{'id': 'firma', 'tipo': 'firma', 'paso': 'paso_2'},
        ],
        pasos: <dynamic>[
          ..._pasos,
          <String, dynamic>{'id': 'paso_3', 'titulo': 'Sin nada'},
        ],
      );
      expect(p.map((PasoDeEjecucion x) => x.titulo),
          <String>['Diagnóstico', 'Solución', 'Otros datos']);
      expect(p[0].campos.single['id'], 'med');
      expect(p[0].evidencias.single['id'], 'f1');
      expect(p[1].evidencias, isEmpty, reason: 'la firma es del cierre');
      expect(p[2].campos.single['id'], 'obs');
    });

    test('a2 · si nadie declara un paso que exista, no hay pasos: la pantalla de siempre', () {
      expect(
        pasosDeEjecucion(
          campos: <dynamic>[_campo('a', 'A'), _campo('b', 'B', paso: 'inventado')],
          requisitos: const <dynamic>[],
          pasos: _pasos,
        ),
        isEmpty,
      );
    });
  });

  group('B · la pantalla por pasos', () {
    FuenteDeEjecucionFalsa porPasos() => FuenteDeEjecucionFalsa(
          campos: <Map<String, dynamic>>[
            _campo('med', 'Medición al llegar', paso: 'paso_1'),
            _campo('sol', 'Qué se cambió', paso: 'paso_2'),
          ],
          requisitos: const <Map<String, dynamic>>[],
          pasos: _pasos,
        );

    testWidgets('un paso a la vez, con siguiente y anterior; Finalizar en el último',
        (WidgetTester t) async {
      _pantallaAlta(t);
      await t.pumpWidget(_app(porPasos()));
      await t.pumpAndSettle();

      expect(find.text('PASOS DEL TRABAJO'), findsOneWidget);
      expect(find.text('1. Diagnóstico'), findsOneWidget);
      expect(find.textContaining('Medición al llegar'), findsWidgets);
      expect(find.textContaining('Qué se cambió'), findsNothing);
      expect(find.text('Finalizar'), findsNothing);

      await t.tap(find.text('Siguiente paso'));
      await t.pumpAndSettle();
      expect(find.textContaining('Qué se cambió'), findsWidgets);
      expect(find.textContaining('Medición al llegar'), findsNothing);
      expect(find.text('Finalizar'), findsOneWidget);

      await t.tap(find.text('Anterior'));
      await t.pumpAndSettle();
      expect(find.textContaining('Medición al llegar'), findsWidgets);
    });

    testWidgets('tocar un paso lo abre', (WidgetTester t) async {
      _pantallaAlta(t);
      await t.pumpWidget(_app(porPasos()));
      await t.pumpAndSettle();
      await t.tap(find.text('2. Solución'));
      await t.pumpAndSettle();
      expect(find.textContaining('Qué se cambió'), findsWidgets);
    });

    testWidgets('sin pasos en la plantilla, la pantalla de siempre', (WidgetTester t) async {
      _pantallaAlta(t);
      await t.pumpWidget(_app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();
      expect(find.text('PASOS DEL TRABAJO'), findsNothing);
      // El encabezado, y la línea del checklist que lleva el mismo nombre.
      expect(find.text('Datos del trabajo'), findsWidgets);
      expect(find.text('Finalizar'), findsOneWidget);
    });
  });

  group('C · un solo cierre', () {
    FuenteDeEjecucionFalsa lista({bool conMaterial = false}) {
      final FuenteDeEjecucionFalsa f = FuenteDeEjecucionFalsa(
        valores: <String, dynamic>{
          'tipo_intervencion': 'Roseta / Conector',
          'potencia_rx': '-18.4',
        },
        evidencias: <Map<String, dynamic>>[
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_power_meter'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_roseta'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'firma_cliente'),
        ],
        materiales: conMaterial
            ? <Map<String, dynamic>>[FuenteDeEjecucionFalsa.material()]
            : <Map<String, dynamic>>[],
      );
      f.seguimientoDado = _seguimientoConCierre();
      return f;
    }

    testWidgets('sin material: pregunta, pide el cierre, y lo guarda con el dato', (WidgetTester t) async {
      _pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = lista();
      await t.pumpWidget(_app(f));
      await t.pumpAndSettle();

      expect(find.text('Reporte de cierre'), findsNothing,
          reason: 'el cierre ya no es un botón aparte');
      expect(find.text('Reportar bloqueo'), findsOneWidget);

      await t.tap(find.text('Finalizar'));
      await t.pumpAndSettle();
      expect(find.text('No hay materiales registrados en esta orden'), findsOneWidget);
      await t.tap(find.text('Sí, no utilicé materiales'));
      await t.pumpAndSettle();

      expect(find.text('Cierre del trabajo'), findsOneWidget);
      await t.enterText(find.byType(TextField).last, 'Se cambió el conector');
      await t.pumpAndSettle();
      await t.tap(find.text('GUARDAR Y FINALIZAR'));
      await t.pumpAndSettle();

      expect(f.reportes, hasLength(1));
      expect(f.reportes.single['id'], 'seg-ot-1-cierre-r7');
      expect(f.reportes.single['momento'], 'cierre');
      final Map<String, dynamic> r = f.reportes.single['respuestas'] as Map<String, dynamic>;
      expect(r['nota_cierre'], 'Se cambió el conector');
      expect((r['__plataforma'] as Map)['sin_material_confirmado'], isTrue);
      expect(f.transiciones, hasLength(1), reason: 'y la orden queda finalizada');
    });

    testWidgets('con material registrado no pregunta, y no afirma nada del material', (WidgetTester t) async {
      _pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = lista(conMaterial: true);
      await t.pumpWidget(_app(f));
      await t.pumpAndSettle();

      await t.tap(find.text('Finalizar'));
      await t.pumpAndSettle();
      expect(find.text('No hay materiales registrados en esta orden'), findsNothing);
      await t.enterText(find.byType(TextField).last, 'Se cambió el conector');
      await t.pumpAndSettle();
      await t.tap(find.text('GUARDAR Y FINALIZAR'));
      await t.pumpAndSettle();
      expect((f.reportes.single['respuestas'] as Map).containsKey('__plataforma'), isFalse);
    });

    testWidgets('cerrar la hoja del cierre no finaliza', (WidgetTester t) async {
      _pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = lista(conMaterial: true);
      await t.pumpWidget(_app(f));
      await t.pumpAndSettle();
      await t.tap(find.text('Finalizar'));
      await t.pumpAndSettle();
      await t.tap(find.byTooltip('Cerrar'));
      await t.pumpAndSettle();
      expect(f.reportes, isEmpty);
      expect(f.transiciones, isEmpty);
    });

    testWidgets('un reintento de finalizar no pide ni escribe otro cierre', (WidgetTester t) async {
      _pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = lista(conMaterial: true);
      // El cierre de esta vuelta ya está en el teléfono (un intento anterior).
      f.reportes.add(<String, dynamic>{'id': 'seg-ot-1-cierre-r7', 'momento': 'cierre'});
      await t.pumpWidget(_app(f));
      await t.pumpAndSettle();
      await t.tap(find.text('Finalizar'));
      await t.pumpAndSettle();
      expect(find.text('Cierre del trabajo'), findsNothing);
      expect(f.reportes, hasLength(1));
      expect(f.transiciones, hasLength(1));
    });

    testWidgets('sin el seguimiento en el teléfono, finaliza igual', (WidgetTester t) async {
      // El trabajo no puede quedar trabado porque el formulario del cierre no
      // bajó: se finaliza, y la bitácora queda sin ese reporte.
      _pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = lista(conMaterial: true)..seguimientoDado = null;
      await t.pumpWidget(_app(f));
      await t.pumpAndSettle();
      await t.tap(find.text('Finalizar'));
      await t.pumpAndSettle();
      expect(f.transiciones, hasLength(1));
    });
  });

  group('D · Comprobar conexión', () {
    TrabajoVista trabajo({bool conSerial = true, bool conLectura = true}) =>
        TrabajoVista.desdeOrden(<String, dynamic>{
          'id': 'ot-1',
          'numero': 1849,
          'estado': 'en_sitio',
          'cliente_nombre': 'Cliente',
          'telefono': '3001234567',
          'contexto_json': jsonEncode(<String, dynamic>{
            'contexto_disponible': conLectura || conSerial,
            'capturado_en': '2026-10-17T13:10:00+00:00',
            if (conSerial) 'sn_onu': 'ZTEGC0A1B2C3',
            if (conLectura)
              'equipo': <String, dynamic>{
                'onu_status': 'Online',
                'onu_signal_1490': '-21.19 dBm',
                'onu_signal_1490_veredicto': 'aceptable',
              },
          }),
        });

    AccionesOrden acciones({
      List<String>? llamadas,
      ResultadoRefresco refresco = const ResultadoRefresco(ok: true),
    }) =>
        AccionesOrden(
          transicionar: ({
            required String ordenId,
            required String nuevoEstadoLocal,
            required String tipoAccion,
            required int revisionBase,
          }) async {},
          sincronizar: () async {},
          medirSenal: (String _) async {
            llamadas?.add('medir');
            return MedicionDeSenal(
              medido: true,
              medidoEn: DateTime(2026, 10, 17, 11, 42),
              senal1490: -19.4,
              veredicto: 'aceptable',
              estadoOnu: 'Online',
            );
          },
          probarConexion: (String _, int n) async => ResultadoPing(
            medido: true,
            paquetes: <PaqueteDePing>[
              for (int i = 1; i <= n; i++) PaqueteDePing(n: i, respondio: i != 2),
            ],
          ),
          refrescarFicha: (String _) async {
            llamadas?.add('refrescar');
            return refresco;
          },
        );

    Future<void> montar(WidgetTester t, Widget w) async {
      _pantallaAlta(t);
      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(body: SingleChildScrollView(child: w)),
      ));
      await t.pumpAndSettle();
    }

    testWidgets('la ficha dice «Al despachar»; medir dice «Ahora»', (WidgetTester t) async {
      await montar(t, ComprobarConexion(
        ordenId: 'ot-1', trabajo: trabajo(), acciones: acciones()));

      expect(find.textContaining('AL DESPACHAR'), findsOneWidget);
      expect(find.text('Rx ONU -21.19 dBm'), findsOneWidget);
      expect(find.textContaining('no confirma que el cliente tenga internet'), findsOneWidget);
      expect(find.text('Volver a consultar el equipo'), findsNothing,
          reason: 'con ficha completa no hace falta');

      await t.tap(find.text('Medir la señal ahora'));
      await t.pumpAndSettle();
      expect(find.textContaining('AHORA · 11:42'), findsOneWidget);
      expect(find.text('Rx ONU -19.40 dBm'), findsOneWidget);
    });

    testWidgets('el ping dice cuántos respondieron, y no dictamina', (WidgetTester t) async {
      await montar(t, ComprobarConexion(
        ordenId: 'ot-1', trabajo: trabajo(), acciones: acciones()));
      await t.tap(find.text('Probar conexión (ping)'));
      await t.pumpAndSettle();
      expect(find.textContaining('respondieron 3 de 4'), findsOneWidget);
      expect(find.textContaining('caído'), findsNothing);
      expect(find.textContaining('funciona'), findsNothing);
    });

    testWidgets('sin serial no se ofrece medir, pero sí volver a pedir la ficha', (WidgetTester t) async {
      final List<String> llamadas = <String>[];
      int recargas = 0;
      await montar(t, ComprobarConexion(
        ordenId: 'ot-1',
        trabajo: trabajo(conSerial: false, conLectura: false),
        acciones: acciones(llamadas: llamadas),
        alActualizarFicha: () async => recargas++,
      ));

      expect(find.text('Medir la señal ahora'), findsNothing);
      expect(find.textContaining('no llegó cuando se creó la orden'), findsOneWidget);
      await t.tap(find.text('Volver a consultar el equipo'));
      await t.pumpAndSettle();
      expect(llamadas, <String>['refrescar']);
      expect(recargas, 1, reason: 'con éxito, quien la muestra relee la orden');
    });

    testWidgets('si no se pudo, lo dice y no promete un reintento solo', (WidgetTester t) async {
      int recargas = 0;
      await montar(t, ComprobarConexion(
        ordenId: 'ot-1',
        trabajo: trabajo(conSerial: false, conLectura: false),
        acciones: acciones(
            refresco: const ResultadoRefresco(ok: false, motivo: 'sin_conexion')),
        alActualizarFicha: () async => recargas++,
      ));
      await t.tap(find.text('Volver a consultar el equipo'));
      await t.pumpAndSettle();
      expect(find.textContaining('Sin señal no se puede consultar'), findsOneWidget);
      expect(recargas, 0);
    });

    testWidgets('en Ejecutar está, sin salir de la intervención', (WidgetTester t) async {
      _pantallaAlta(t);
      await t.pumpWidget(_app(FuenteDeEjecucionFalsa(), acciones: acciones()));
      await t.pumpAndSettle();
      expect(find.text('Comprobar conexión'), findsOneWidget);
    });
  });

  group('E · «no usé materiales» viaja aparte', () {
    test('se saca de las respuestas y va como dato del cierre', () {
      final Map<String, dynamic> c = SyncQueueService.cuerpoDelReporte(
        momento: 'cierre',
        respuestas: <String, dynamic>{
          'solucion': 'x',
          '__plataforma': <String, dynamic>{'sin_material_confirmado': true, 'otro': 1},
        },
      );
      expect(c['sin_material_confirmado'], isTrue);
      expect((c['respuestas'] as Map).containsKey('__plataforma'), isFalse);
      expect(c.containsKey('otro'), isFalse, reason: 'solo pasa lo nombrado');
    });

    test('fuera del cierre no viaja', () {
      final Map<String, dynamic> c = SyncQueueService.cuerpoDelReporte(
        momento: 'avance',
        respuestas: <String, dynamic>{
          'nota': 'x',
          '__plataforma': <String, dynamic>{'sin_material_confirmado': true},
        },
      );
      expect(c.containsKey('sin_material_confirmado'), isFalse);
      expect((c['respuestas'] as Map).containsKey('__plataforma'), isFalse);
    });
  });

  group('F · el cierre con id fijo no se duplica en el teléfono', () {
    setUpAll(() {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
      LocalDatabase.usarBaseDePruebas('pruebas_tanda2_cierre.db');
    });
    tearDown(() async {
      LocalDatabase.resetForTesting();
      await databaseFactory.deleteDatabase(
        join(await databaseFactory.getDatabasesPath(), 'pruebas_tanda2_cierre.db'),
      );
    });

    test('dos veces el mismo id: una sola fila', () async {
      LocalDatabase.resetForTesting();
      final LocalDatabase base = LocalDatabase();
      Future<String> encolar(String texto) => base.encolarSeguimiento(
            ordenId: 'ot-1',
            orgId: 'org-1',
            profileId: 'prof-1',
            momento: 'cierre',
            respuestas: <String, dynamic>{'solucion': texto},
            idFijo: 'seg-ot-1-cierre-r7',
          );
      expect(await encolar('primera'), 'seg-ot-1-cierre-r7');
      expect(await encolar('segunda'), 'seg-ot-1-cierre-r7');
      final List<Map<String, dynamic>> pend =
          await base.seguimientosPendientes(orgId: 'org-1', profileId: 'prof-1');
      expect(pend, hasLength(1));
      expect(jsonDecode(pend.single['respuestas_json'] as String)['solucion'], 'primera');
      expect(await base.existeSeguimiento('seg-ot-1-cierre-r7'), isTrue);
      expect(await base.existeSeguimiento('seg-ot-1-cierre-r8'), isFalse);
    });
  });
}
