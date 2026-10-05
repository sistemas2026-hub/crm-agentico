import 'dart:async';

import 'package:campo/core/acciones/salir_de_la_app.dart';
import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/features/inicio/inicio_screen.dart';
import 'package:campo/features/inicio/resumen_de_inicio.dart';
import 'package:campo/features/trabajo/trabajo_screen.dart';
import 'package:flutter/material.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';

/// Lo que el técnico pidió al recorrer la app pantalla por pantalla.
///
/// Cada grupo de abajo nace de una frase suya, no de una idea de diseño. Se
/// anotan acá porque lo que hace que una decisión de producto no se revierta
/// sola en tres meses es tener escrito **qué problema resolvía**.
void main() {
  TrabajoVista trabajo({
    required String id,
    DateTime? ventana,
    DateTime? compromiso,
    String estado = 'asignada',
  }) {
    return TrabajoVista.desdeOrden(<String, dynamic>{
      'id': id,
      'numero': 1000,
      'estado': estado,
      'cliente_nombre': 'Beatriz Pinzón',
      'direccion': 'Calle 50',
      'tipo_nombre': 'Reparación',
      'tipo_codigo': 'ftth_correctivo',
      'schema_version': 1,
      'ventana_inicio': ventana?.toUtc().toIso8601String(),
      'fecha_compromiso': compromiso?.toUtc().toIso8601String(),
    });
  }

  EstadoDeJornada jornadaCon({required String aDevolver}) {
    return EstadoDeJornada(
      recibido: '0',
      consumido: '38.5',
      aDevolver: aDevolver,
      devuelto: '0',
      diferencias: 2,
      ordenesAsignadas: 3,
      ordenesCompletadas: 0,
      materiales: const <MaterialDeJornada>[],
      transferencias: const <TransferenciaPendiente>[],
      motivos: const <String>[],
      sinSubir: 0,
      cerrada: false,
      hayJornada: true,
    );
  }

  // ------------------------------------------------------------------------ //
  // 1. «A qué hora es cada trabajo»
  // ------------------------------------------------------------------------ //

  group('1 · las horas del día', () {
    test('a · salen en orden, no en el que las creó la oficina', () {
      // «3 ASIGNADAS» no dice si la primera es a las 8 o a las 2, y eso es lo
      // que decide el día. Había que abrir las tres fichas para saberlo.
      final DateTime hoy = DateTime(2026, 10, 5, 7);
      final r = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'c', ventana: DateTime(2026, 10, 5, 15)),
          trabajo(id: 'a', ventana: DateTime(2026, 10, 5, 8)),
          trabajo(id: 'b', ventana: DateTime(2026, 10, 5, 11, 30)),
        ],
        ahora: hoy,
      );

      expect(r.horasDelDia.map((HoraDelDia h) => h.hora).toList(),
          <String>['08:00', '11:30', '15:00']);
    });

    test('b · sin ninguna hora, la lista queda VACÍA', () {
      // Es el caso real hoy: ninguna orden del laboratorio trae hora. La
      // pantalla no dibuja la línea en vez de poner una fila de guiones en el
      // lugar donde el técnico mira cuando sí las hay.
      final r = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'a'), trabajo(id: 'b')],
        ahora: DateTime(2026, 10, 5, 7),
      );

      expect(r.horasDelDia, isEmpty);
    });

    test('c · los trabajos sin hora no empujan a los que sí la tienen', () {
      final r = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'sin'),
          trabajo(id: 'con', ventana: DateTime(2026, 10, 5, 9)),
        ],
        ahora: DateTime(2026, 10, 5, 7),
      );

      expect(r.horasDelDia.length, 1);
      expect(r.horasDelDia.single.ordenId, 'con');
    });

    test('d · la ventana prometida le gana al compromiso', () {
      // Son dos cosas distintas: al abonado se le dijo «entre 8 y 10», y esa es
      // la hora que él está esperando en la puerta.
      final r = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(
            id: 'a',
            ventana: DateTime(2026, 10, 5, 8),
            compromiso: DateTime(2026, 10, 5, 17),
          ),
        ],
        ahora: DateTime(2026, 10, 5, 7),
      );

      expect(r.horasDelDia.single.hora, '08:00');
    });

    test('e · una hora pasada con el trabajo abierto está VENCIDA', () {
      final r = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'a', ventana: DateTime(2026, 10, 5, 8)),
        ],
        ahora: DateTime(2026, 10, 5, 11),
      );

      expect(r.horasDelDia.single.vencida, isTrue);
    });

    test('f · una hora pasada con el trabajo HECHO no está vencida', () {
      // Un trabajo terminado tarde ya no es un problema que mirar a las siete
      // de la mañana. Marcarlo en rojo enseña a ignorar los rojos.
      final r = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(
            id: 'a',
            ventana: DateTime(2026, 10, 5, 8),
            estado: 'cerrada',
          ),
        ],
        ahora: DateTime(2026, 10, 5, 11),
      );

      expect(r.horasDelDia.single.hecha, isTrue);
      expect(r.horasDelDia.single.vencida, isFalse);
    });
  });

  // ------------------------------------------------------------------------ //
  // 2. «EN MANO -38.5»
  // ------------------------------------------------------------------------ //

  group('2 · no existe tener menos de cero en la mano', () {
    test('a · un saldo negativo se convierte en el faltante, en POSITIVO', () {
      // Lo que hay que decir es «consumiste 38,5 que no figuran entregados»,
      // no un saldo negativo con cara de medición.
      final r = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        jornada: jornadaCon(aDevolver: '-38.5'),
      );

      expect(r.consumidoSinEntrega, '38.5');
    });

    test('b · un saldo posible NO dispara el aviso', () {
      // El contrapeso: que el caso roto se diga bien no puede lograrse
      // marcando como problema una jornada que está en orden.
      for (final String saldo in <String>['0', '12', '38.5']) {
        final r = ResumenDeInicio.armar(
          trabajos: const <TrabajoVista>[],
          jornada: jornadaCon(aDevolver: saldo),
        );
        expect(r.consumidoSinEntrega, isNull, reason: saldo);
      }
    });

    test('c · sin ceros de relleno', () {
      // PostgreSQL devuelve el decimal con la escala de la columna, y en
      // Colombia el punto separa MILES: «38.500» se lee como treinta y ocho mil.
      final r = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        jornada: jornadaCon(aDevolver: '-38.500'),
      );

      expect(r.consumidoSinEntrega, '38.5');
    });

    test('d · un entero no arrastra decimales', () {
      final r = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        jornada: jornadaCon(aDevolver: '-12'),
      );

      expect(r.consumidoSinEntrega, '12');
    });

    test('e · sin jornada no se inventa un problema', () {
      final r = ResumenDeInicio.armar(trabajos: const <TrabajoVista>[]);

      expect(r.consumidoSinEntrega, isNull);
    });
  });

  // ------------------------------------------------------------------------ //
  // 3 y 4. Lo que se ve en pantalla
  // ------------------------------------------------------------------------ //

  Map<String, dynamic> fila({bool conCoordenadas = true}) =>
      <String, dynamic>{
        'id': 'ot-1',
        'numero': 1842,
        'estado': 'asignada',
        'cliente_nombre': 'María Fernández',
        'direccion': 'Cra. 48 # 12-30, Apto 402',
        'telefono': '+57 300 999 8877',
        'tipo_nombre': 'Instalación Fibra Óptica (FTTH)',
        'tipo_codigo': 'ftth_instalacion',
        'schema_version': 1,
        'revision': 1,
        'cliente_lat': conCoordenadas ? 6.20870 : null,
        'cliente_lng': conCoordenadas ? -75.56780 : null,
      };

  OrdenesJornada ordenesCon(WidgetTester t, Map<String, dynamic> f) {
    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    final OrdenesJornada o = OrdenesJornada(
      leerOrdenes: () async => <Map<String, dynamic>>[f],
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    addTearDown(() async {
      await avisos.close();
      o.dispose();
    });
    t.view.physicalSize = const Size(1000, 4200);
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);
    return o;
  }

  group('3 · el recuadro de ubicación abre el mapa', () {
    testWidgets('a · tocarlo pide abrir el punto del cliente',
        (WidgetTester t) async {
      // «Parece un mapa y no lo es. La primera vez intenté arrastrarlo.»
      // Un elemento que finge ser interactivo enseña a desconfiar del resto.
      // El arbol de semantica NO se construye por omision en una prueba de
      // widget, asi que `bySemanticsLabel` no encuentra nada aunque el widget
      // este. Se enciende a proposito -- y de paso esto comprueba que el gesto
      // tiene nombre para un lector de pantalla.
      // Se libera DENTRO del cuerpo, no en `addTearDown`: la verificación de
      // handles corre antes que los tearDown y el test falla por el handle en
      // vez de por lo que mide.
      final SemanticsHandle semantica = t.ensureSemantics();

      final List<Uri> abiertos = <Uri>[];
      final OrdenesJornada ordenes = ordenesCon(t, fila());

      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: DetalleOrdenScreen(
          ordenId: 'ot-1',
          ordenes: ordenes,
          salir: SalirDeLaApp(abrir: (Uri u) async {
            abiertos.add(u);
            return true;
          }),
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

      await t.tap(find.bySemanticsLabel(
          'Abrir el mapa en la ubicación del cliente'));
      await t.pumpAndSettle();

      semantica.dispose();

      expect(abiertos.length, 1);
      expect(abiertos.single.scheme, 'geo');
      expect(abiertos.single.path, '6.2087,-75.5678');
    });

    testWidgets('b · sin coordenadas NO se ofrece tocar', (WidgetTester t) async {
      // No hay a dónde ir. Un gesto que no lleva a ningún lado es el mismo
      // defecto con otra cara.
      final OrdenesJornada ordenes = ordenesCon(t, fila(conCoordenadas: false));

      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: DetalleOrdenScreen(
          ordenId: 'ot-1',
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

      expect(
        find.bySemanticsLabel('Abrir el mapa en la ubicación del cliente'),
        findsNothing,
      );
    });
  });

  group('4 · el glosario se fue de la lista', () {
    testWidgets('a · ya no ocupa lugar en la pantalla más usada',
        (WidgetTester t) async {
      // «Yo sé qué es una OT. Lo leo una vez en mi vida.»
      final OrdenesJornada ordenes = ordenesCon(t, fila());

      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: TrabajoScreen(ordenes: ordenes, abrirTrabajo: (_, _) async {}),
        ),
      ));
      await t.pumpAndSettle();

      expect(find.textContaining('Arquitectura de Campo'), findsNothing);
      // Y lo que sí se usa sigue estando.
      // El buscador es un `hintText`, no un `Text`: se busca el campo.
      expect(find.byType(TextField), findsWidgets);
    });
  });

  group('1bis · la línea de horas en la pantalla', () {
    testWidgets('a · con horas se dibujan; sin horas no ocupa lugar',
        (WidgetTester t) async {
      final OrdenesJornada ordenes = ordenesCon(t, <String, dynamic>{
        ...fila(),
        'ventana_inicio':
            DateTime(2026, 10, 5, 8).toUtc().toIso8601String(),
      });

      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        // `jornada` inyectada y `Scaffold` propio: sin la jornada, `InicioScreen`
        // consulta SQLite en `initState` y la prueba se queda mirando la
        // pantalla de carga. Es el mismo montaje de `inicio_screen_test`.
        home: Scaffold(
          body: InicioScreen(
            ordenes: ordenes,
            abrirTrabajo: (_, _) async {},
            nombreTecnico: 'Carlos',
            jornada: const EstadoDeJornada.vacio(),
            ahora: DateTime(2026, 10, 5, 7),
          ),
        ),
      ));
      await t.pumpAndSettle();

      expect(find.text('08:00'), findsOneWidget);
    });

    testWidgets('b · sin horas, ninguna', (WidgetTester t) async {
      final OrdenesJornada ordenes = ordenesCon(t, fila());

      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        // `jornada` inyectada y `Scaffold` propio: sin la jornada, `InicioScreen`
        // consulta SQLite en `initState` y la prueba se queda mirando la
        // pantalla de carga. Es el mismo montaje de `inicio_screen_test`.
        home: Scaffold(
          body: InicioScreen(
            ordenes: ordenes,
            abrirTrabajo: (_, _) async {},
            nombreTecnico: 'Carlos',
            jornada: const EstadoDeJornada.vacio(),
            ahora: DateTime(2026, 10, 5, 7),
          ),
        ),
      ));
      await t.pumpAndSettle();

      expect(find.textContaining(':'), findsNothing);
    });
  });
}
