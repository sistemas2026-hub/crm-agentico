/// TANDA 1 (17/10/2026): correcciones que salieron de una revisión externa de
/// la app, verificadas contra el código antes de tocarlo.
///
///   A  la lista de Órdenes y el «Próximo trabajo» de Inicio usan UNA regla
///   B  las detenidas tienen su filtro: antes solo aparecían en «Todos»
///   C  los íconos de navegar y llamar de la tarjeta abren de verdad, e
///      «Iniciar ruta de viaje» (que abría la ficha) ahora navega
///   D  en Materiales no queda ningún botón que no haga nada
///   E  la franja «Falta» es gris mientras se trabaja y roja al intentar cerrar
///   F  terminar sin señal no dice «¡con éxito!»
///   G  el bloqueo para el NOC dice que el NOC todavía no se enteró
///   H  el inventario de Inicio no suma ONTs con metros de cable
///
/// Todo es lógica sobre lo que ya está en el teléfono: ninguna de estas
/// pruebas necesita red, y ninguna corrección agrega una llamada al servidor.
library;

import 'dart:async';

import 'package:campo/core/acciones/salir_de_la_app.dart';
import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/seguimiento_de_la_intervencion.dart';
import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:campo/features/inicio/resumen_de_inicio.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:campo/features/materiales/kit_de_jornada.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:campo/features/trabajo/estado_trabajo.dart';
import 'package:campo/features/trabajo/orden_operativo.dart';
import 'package:campo/features/trabajo/trabajo_screen.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:campo/features/trabajo/widgets/tarjeta_trabajo.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

Map<String, dynamic> _fila({
  required String id,
  required int numero,
  String estado = 'asignada',
  String prioridad = '',
  String? slaVenceEn,
  double? lat,
  double? lng,
  String telefono = '',
}) =>
    <String, dynamic>{
      'id': id,
      'numero': numero,
      'estado': estado,
      'cliente_nombre': 'Cliente $numero',
      'direccion': 'Calle $numero',
      'telefono': telefono,
      'tipo_nombre': 'Instalación FTTH',
      'tipo_codigo': 'ftth_instalacion',
      'schema_version': 1,
      'revision': 1,
      'prioridad': prioridad,
      'sla_vence_en': ?slaVenceEn,
      'cliente_lat': ?lat,
      'cliente_lng': ?lng,
    };

TrabajoVista _t(Map<String, dynamic> f) => TrabajoVista.desdeOrden(f);

void _pantallaAlta(WidgetTester t) {
  t.view.physicalSize = const Size(1000, 4200);
  t.view.devicePixelRatio = 1.0;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
}

void main() {
  final DateTime ahora = DateTime(2026, 10, 17, 10, 0);

  // Un día con un poco de todo, en el orden en que viene de la base (número).
  List<Map<String, dynamic>> dia() => <Map<String, dynamic>>[
        _fila(id: 'a', numero: 1, prioridad: 'baja'),
        _fila(id: 'b', numero: 2, estado: 'cerrada'),
        _fila(id: 'c', numero: 3,
            slaVenceEn: ahora.add(const Duration(minutes: 90)).toIso8601String()),
        _fila(id: 'd', numero: 4, estado: 'en_camino'),
        _fila(id: 'e', numero: 5, prioridad: 'alta'),
        _fila(id: 'f', numero: 6,
            slaVenceEn: ahora.add(const Duration(minutes: 20)).toIso8601String()),
        _fila(id: 'g', numero: 7, estado: 'bloqueada'),
        _fila(id: 'h', numero: 8),
      ];

  group('A · una sola regla para Inicio y para la lista', () {
    test('a1 · el orden: en camino, lo que vence antes, prioridad, resto, terminado', () {
      final List<String> ids = OrdenOperativo.ordenar(
        dia().map(_t).toList(),
        ahora: ahora,
      ).map((TrabajoVista t) => t.id).toList();

      expect(ids, <String>['d', 'f', 'c', 'e', 'a', 'g', 'h', 'b']);
    });

    test('a2 · el «Próximo trabajo» de Inicio es el primero de la lista', () {
      // Se arman las dos cosas por separado, como las arma la app, y se
      // comparan: si alguna vez vuelven a tener reglas propias, esto lo ve.
      for (final List<Map<String, dynamic>> filas in <List<Map<String, dynamic>>>[
        dia(),
        dia().where((Map<String, dynamic> f) => f['estado'] != 'en_camino').toList(),
        <Map<String, dynamic>>[_fila(id: 'x', numero: 9, estado: 'en_sitio'), ...dia()],
        <Map<String, dynamic>>[_fila(id: 'y', numero: 1), _fila(id: 'z', numero: 2)],
      ]) {
        final List<TrabajoVista> trabajos = filas.map(_t).toList();
        final ResumenDeInicio inicio =
            ResumenDeInicio.armar(trabajos: trabajos, ahora: ahora);
        final List<TrabajoVista> lista =
            OrdenOperativo.ordenar(trabajos, ahora: ahora);
        expect(inicio.siguiente?.id, lista.first.id);
      }
    });

    test('a3 · a igualdad se respeta el orden de llegada, siempre', () {
      // `List.sort` de Dart no es estable: sin desempate, dos iguales podían
      // cambiar de lugar entre una lectura y la siguiente.
      final List<TrabajoVista> iguales = <TrabajoVista>[
        for (int i = 0; i < 40; i++) _t(_fila(id: 'n$i', numero: i)),
      ];
      expect(
        OrdenOperativo.ordenar(iguales, ahora: ahora).map((TrabajoVista t) => t.id),
        iguales.map((TrabajoVista t) => t.id),
      );
    });

    test('a4 · todo terminado: no hay próximo trabajo', () {
      expect(
        OrdenOperativo.siguiente(
          <TrabajoVista>[_t(_fila(id: 'b', numero: 2, estado: 'cerrada'))],
          ahora: ahora,
        ),
        isNull,
      );
    });
  });

  group('A/B · la pantalla de Órdenes', () {
    Future<OrdenesJornada> montar(WidgetTester t, List<Map<String, dynamic>> filas) async {
      final StreamController<SyncStatus> avisos =
          StreamController<SyncStatus>.broadcast();
      addTearDown(avisos.close);
      final OrdenesJornada ordenes = OrdenesJornada(
        leerOrdenes: () async => filas,
        sincronizar: () async {},
        avisosDeSincronizacion: avisos.stream,
      );
      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: TrabajoScreen(
            ordenes: ordenes,
            mostrarDatosFuturos: false,
            abrirTrabajo: (BuildContext c, TrabajoVista _) async {},
          ),
        ),
      ));
      await t.pumpAndSettle();
      return ordenes;
    }

    testWidgets('la lista sale en el orden de Inicio, y lo dice', (WidgetTester t) async {
      _pantallaAlta(t);
      await montar(t, <Map<String, dynamic>>[
        _fila(id: 'a', numero: 1),
        _fila(id: 'd', numero: 4, estado: 'en_camino'),
      ]);

      final double yCamino = t.getTopLeft(find.text('Cliente 4')).dy;
      final double yAsignada = t.getTopLeft(find.text('Cliente 1')).dy;
      expect(yCamino, lessThan(yAsignada),
          reason: 'la OT #4 va en camino: va antes que la #1, aunque su número sea mayor');
      expect(find.textContaining('Primero lo empezado'), findsOneWidget);
    });

    testWidgets('las detenidas tienen su filtro, con su número', (WidgetTester t) async {
      _pantallaAlta(t);
      await montar(t, <Map<String, dynamic>>[
        _fila(id: 'a', numero: 1),
        _fila(id: 'g', numero: 7, estado: 'bloqueada'),
      ]);

      expect(find.text('Detenidas (1)'), findsOneWidget);
      await t.tap(find.text('Detenidas (1)'));
      await t.pumpAndSettle();
      expect(find.text('Cliente 7'), findsOneWidget);
      expect(find.text('Cliente 1'), findsNothing);
    });

    test('el filtro de detenidas no se lleva las demás', () {
      expect(
        perteneceA(PestanaTrabajo.detenidas, EstadoTrabajo.bloqueada, null, ahora: ahora),
        isTrue,
      );
      for (final EstadoTrabajo e in EstadoTrabajo.values) {
        if (e == EstadoTrabajo.bloqueada) continue;
        expect(perteneceA(PestanaTrabajo.detenidas, e, null, ahora: ahora), isFalse,
            reason: e.name);
      }
    });
  });

  group('C · la tarjeta: lo que dice es lo que hace', () {
    Future<List<Uri>> montar(WidgetTester t, Map<String, dynamic> fila) async {
      final List<Uri> abiertos = <Uri>[];
      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: SingleChildScrollView(
            child: TarjetaTrabajo(
              trabajo: _t(fila),
              mostrarDatosFuturos: false,
              onTap: () {},
              salir: SalirDeLaApp(abrir: (Uri u) async {
                abiertos.add(u);
                return true;
              }),
            ),
          ),
        ),
      ));
      await t.pumpAndSettle();
      return abiertos;
    }

    testWidgets('en curso: los dos íconos abren el mapa y el marcador', (WidgetTester t) async {
      _pantallaAlta(t);
      final List<Uri> abiertos = await montar(t, _fila(
        id: 'd', numero: 4, estado: 'en_camino',
        lat: 10.96, lng: -74.78, telefono: '312 455 8901',
      ));

      await t.tap(find.byTooltip('Navegar'));
      await t.pump();
      await t.tap(find.byTooltip('Llamar al cliente'));
      await t.pump();
      expect(abiertos.map((Uri u) => u.scheme), <String>['geo', 'tel']);
    });

    testWidgets('en curso sin datos: se apagan y dicen por qué', (WidgetTester t) async {
      _pantallaAlta(t);
      final List<Uri> abiertos =
          await montar(t, _fila(id: 'd', numero: 4, estado: 'en_camino'));

      expect(find.byTooltip('Sin ubicación en la orden'), findsOneWidget);
      expect(find.byTooltip('Sin teléfono en la orden'), findsOneWidget);
      await t.tap(find.byTooltip('Sin ubicación en la orden'));
      await t.pump();
      expect(abiertos, isEmpty);
    });

    testWidgets('pendiente: «Navegar» abre el mapa; sin ubicación lo dice', (WidgetTester t) async {
      _pantallaAlta(t);
      List<Uri> abiertos = await montar(
          t, _fila(id: 'a', numero: 1, lat: 10.96, lng: -74.78));
      expect(find.text('Iniciar ruta de viaje'), findsNothing);
      await t.tap(find.text('Navegar'));
      await t.pump();
      expect(abiertos.single.scheme, 'geo');

      abiertos = await montar(t, _fila(id: 'b', numero: 2));
      expect(find.text('Sin ubicación'), findsOneWidget);
      await t.tap(find.text('Sin ubicación'));
      await t.pump();
      expect(abiertos, isEmpty);
    });
  });

  group('D · Materiales sin botones de adorno', () {
    testWidgets('ninguno de los que no hacían nada sigue dibujado', (WidgetTester t) async {
      // El kit de demostración trae las cuatro clases de material, que es
      // donde vivían esos botones.
      _pantallaAlta(t);
      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: const Scaffold(
          body: MaterialesScreen(mostrarDatosFuturos: true, kit: KitDeJornada.vacio()),
        ),
      ));
      await t.pumpAndSettle();

      for (final String muerto in <String>[
        'Incidencia', 'Ver OTs', 'Ajustar Metros', 'Log Trazabilidad',
        'Asignar', 'Ajustar', 'Validado',
      ]) {
        expect(find.text(muerto), findsNothing, reason: muerto);
      }
      // Y lo que sí hace algo sigue.
      expect(find.text('Escanear QR'), findsOneWidget);
      expect(find.text('Pedir'), findsOneWidget);
      expect(find.text('Verificar MAC/SN'), findsWidgets);
    });
  });

  group('E/F · Ejecutar: la franja y el final', () {
    Widget app(FuenteDeEjecucionFalsa fuente) => MaterialApp(
          theme: AppTheme.lightTheme,
          home: EjecucionScreen(
            ordenId: 'ot-1',
            fuente: fuente,
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

    Color fondoDeLaFranja(WidgetTester t) {
      final Container c = t.widget<Container>(find
          .ancestor(of: find.textContaining('Falta: '), matching: find.byType(Container))
          .first);
      return c.color!;
    }

    testWidgets('gris mientras se trabaja, roja al intentar finalizar', (WidgetTester t) async {
      _pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(fondoDeLaFranja(t), AppColors.surfaceContainerHigh);
      await t.tap(find.text('Finalizar'));
      await t.pumpAndSettle();
      expect(fondoDeLaFranja(t), AppColors.errorContainer);
    });

    testWidgets('al terminar no dice «con éxito»: dice qué falta que pase', (WidgetTester t) async {
      _pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(
        valores: <String, dynamic>{
          'tipo_intervencion': 'Roseta / Conector',
          'potencia_rx': '-18.4',
        },
        evidencias: <Map<String, dynamic>>[
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_power_meter'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_roseta'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'firma_cliente'),
        ],
        materiales: <Map<String, dynamic>>[FuenteDeEjecucionFalsa.material()],
      )));
      await t.pumpAndSettle();
      await t.tap(find.text('Finalizar'));
      await t.pumpAndSettle();

      expect(find.textContaining('Éxito'), findsNothing);
      expect(find.text('Trabajo terminado en campo'), findsOneWidget);
      expect(find.textContaining('guardado en este teléfono'), findsOneWidget);
      expect(find.textContaining('la oficina lo revisa'), findsOneWidget);
    });
  });

  group('G · el bloqueo para el NOC no promete que el NOC ya sabe', () {
    testWidgets('con «Hace falta que el NOC haga algo», el aviso lo dice', (WidgetTester t) async {
      await t.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: SeguimientoDeLaIntervencion(
              seguimiento: <String, dynamic>{
                'eventos': <dynamic>[],
                'momentos_registrados': <String>[],
                'formularios': <String, dynamic>{
                  'bloqueo': <String, dynamic>{
                    'momento': 'bloqueo',
                    'campos': <dynamic>[],
                  },
                },
              },
              cargando: false,
              alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
            ),
          ),
        ),
      ));
      await t.pumpAndSettle();
      await t.tap(find.text('Bloqueo'));
      await t.pumpAndSettle();
      await t.tap(find.byType(Checkbox).first); // requiere NOC
      await t.pumpAndSettle();
      await t.tap(find.text('GUARDAR EL REPORTE'));
      await t.pumpAndSettle();

      expect(find.textContaining('el NOC se entera cuando suba'), findsOneWidget);
    });
  });

  group('H · el inventario de Inicio no mezcla unidades', () {
    EstadoDeJornada jornada(List<MaterialDeJornada> materiales) => EstadoDeJornada(
          recibido: '161',
          consumido: '20',
          aDevolver: '141',
          devuelto: '0',
          diferencias: 0,
          ordenesAsignadas: 3,
          ordenesCompletadas: 1,
          materiales: materiales,
          transferencias: const <TransferenciaPendiente>[],
          motivos: const <String>[],
          sinSubir: 0,
          cerrada: false,
          hayJornada: true,
        );

    MaterialDeJornada m(String codigo, String unidad, String esperado) =>
        MaterialDeJornada.desde(<String, dynamic>{
          'codigo': codigo,
          'nombre': codigo,
          'unidad': unidad,
          'esperado_devolver': esperado,
          'devuelto': '0',
        });

    test('con dos unidades se dice por unidad', () {
      final ResumenDeInicio r = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        ahora: ahora,
        jornada: jornada(<MaterialDeJornada>[
          m('ont', 'unidades', '1'),
          m('conector', 'unidades', '10'),
          m('drop', 'metros', '130'),
        ]),
      );
      expect(r.enManoPorUnidad, '11 unidades · 130 metros');
    });

    test('con una sola unidad, el total sigue teniendo sentido y no se toca', () {
      final ResumenDeInicio r = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        ahora: ahora,
        jornada: jornada(<MaterialDeJornada>[m('ont', 'unidades', '3')]),
      );
      expect(r.enManoPorUnidad, isNull);
    });
  });
}
