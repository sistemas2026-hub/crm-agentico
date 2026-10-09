import 'dart:async';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/trabajo/cercania.dart';
import 'package:campo/features/trabajo/trabajo_screen.dart';
import 'package:flutter/material.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';

/// A qué distancia queda cada trabajo.
///
/// EL PROBLEMA
/// -----------
/// Tres órdenes en barrios distintos, mostradas **en el orden en que las creó la
/// oficina**. Cuál conviene primero lo decidía el técnico mirando direcciones y
/// adivinando, con las coordenadas ahí desde el principio.
///
/// LO QUE SE AFIRMA, Y QUÉ PASA SI SE ROMPE
/// ----------------------------------------
/// 1. **Lo que no se sabe va al final, nunca primero.** Un cero inventado
///    pondría la orden de la que no se sabe dónde queda en el primer lugar —el
///    peor sitio posible—.
/// 2. **La lista no se mueve sola.** Dos órdenes a la misma distancia, o dos sin
///    coordenadas, conservan el orden que traían. Si cambian entre aperturas, el
///    técnico que ya memorizó dónde estaba cada una pierde el hilo.
/// 3. **La distancia es real.** Se usa haversine y no una resta de grados: un
///    grado de longitud mide 111 km en el ecuador y 0 en el polo.
void main() {
  TrabajoVista enPunto(String id, {double? lat, double? lng}) {
    return TrabajoVista.desdeOrden(<String, dynamic>{
      'id': id,
      'numero': 1000,
      'estado': 'asignada',
      'cliente_nombre': 'Cliente',
      'direccion': 'Calle',
      'tipo_nombre': 'Reparación',
      'tipo_codigo': 'ftth_correctivo',
      'schema_version': 1,
      'cliente_lat': lat,
      'cliente_lng': lng,
    });
  }

  // Medellín. Dos puntos reales, para que el número sea comprobable contra un
  // mapa y no contra sí mismo.
  const double latCentro = 6.2518;
  const double lngCentro = -75.5636;

  _enLaPantalla();

  group('A · la distancia', () {
    test('a1 · el mismo punto da cero', () {
      expect(
        Cercania.metrosEntre(
            latA: latCentro, lngA: lngCentro, latB: latCentro, lngB: lngCentro),
        0,
      );
    });

    test('a2 · un kilómetro al norte da ~1000 m', () {
      // 0.00899° de latitud ≈ 1 km en cualquier punto del planeta.
      final double m = Cercania.metrosEntre(
        latA: latCentro,
        lngA: lngCentro,
        latB: latCentro + 0.00899,
        lngB: lngCentro,
      );

      expect(m, closeTo(1000, 15));
    });

    test('a3 · un grado de longitud NO mide lo mismo en todas partes', () {
      // Es el motivo de usar haversine. Con una resta de grados, estas dos
      // distancias serían iguales y el orden de la lista saldría mal.
      final double enElEcuador = Cercania.metrosEntre(
          latA: 0, lngA: 0, latB: 0, lngB: 1);
      final double enColombia = Cercania.metrosEntre(
          latA: 60, lngA: 0, latB: 60, lngB: 1);

      expect(enElEcuador, greaterThan(enColombia * 1.8));
    });
  });

  group('B · cuándo NO se puede saber', () {
    test('b1 · sin la posición del técnico', () {
      expect(
        Cercania.metrosHasta(enPunto('a', lat: 6.25, lng: -75.56),
            latTecnico: null, lngTecnico: null),
        isNull,
      );
    });

    test('b2 · sin las coordenadas de la orden', () {
      expect(
        Cercania.metrosHasta(enPunto('a'),
            latTecnico: latCentro, lngTecnico: lngCentro),
        isNull,
      );
    });

    test('b3 · con media coordenada', () {
      expect(
        Cercania.metrosHasta(enPunto('a', lat: 6.25),
            latTecnico: latCentro, lngTecnico: lngCentro),
        isNull,
      );
    });

    test('b4 · `0,0` no es una ubicación, es «no se sabe»', () {
      // La Isla Nula, en el Atlántico. Tratarla como un punto pondría esa orden
      // a 8.000 km y la mandaría al final por el motivo equivocado.
      expect(
        Cercania.metrosHasta(enPunto('a', lat: 0, lng: 0),
            latTecnico: latCentro, lngTecnico: lngCentro),
        isNull,
      );
    });
  });

  group('C · el orden', () {
    test('c1 · la más cercana primero', () {
      final List<TrabajoVista> ordenado = Cercania.ordenarPorCercania(
        <TrabajoVista>[
          enPunto('lejos', lat: latCentro + 0.05, lng: lngCentro),
          enPunto('cerca', lat: latCentro + 0.001, lng: lngCentro),
          enPunto('medio', lat: latCentro + 0.01, lng: lngCentro),
        ],
        latTecnico: latCentro,
        lngTecnico: lngCentro,
      );

      expect(ordenado.map((TrabajoVista t) => t.id).toList(),
          <String>['cerca', 'medio', 'lejos']);
    });

    test('c2 · lo que no se sabe va AL FINAL, nunca primero', () {
      // El peor sitio para una orden de la que no se sabe dónde queda es el
      // primero: el técnico arranca el día yendo a ciegas.
      final List<TrabajoVista> ordenado = Cercania.ordenarPorCercania(
        <TrabajoVista>[
          enPunto('sin'),
          enPunto('lejos', lat: latCentro + 0.05, lng: lngCentro),
          enPunto('cerca', lat: latCentro + 0.001, lng: lngCentro),
        ],
        latTecnico: latCentro,
        lngTecnico: lngCentro,
      );

      expect(ordenado.map((TrabajoVista t) => t.id).toList(),
          <String>['cerca', 'lejos', 'sin']);
    });

    test('c3 · varias sin coordenadas CONSERVAN su orden', () {
      // Si se reordenan sin motivo, la lista «se mueve sola» entre dos
      // aperturas y quien ya memorizó dónde estaba cada una pierde el hilo.
      final List<TrabajoVista> ordenado = Cercania.ordenarPorCercania(
        <TrabajoVista>[enPunto('x'), enPunto('y'), enPunto('z')],
        latTecnico: latCentro,
        lngTecnico: lngCentro,
      );

      expect(ordenado.map((TrabajoVista t) => t.id).toList(),
          <String>['x', 'y', 'z']);
    });

    test('c4 · dos a la MISMA distancia conservan su orden', () {
      final List<TrabajoVista> ordenado = Cercania.ordenarPorCercania(
        <TrabajoVista>[
          enPunto('segunda', lat: latCentro + 0.01, lng: lngCentro),
          enPunto('primera', lat: latCentro + 0.01, lng: lngCentro),
        ],
        latTecnico: latCentro,
        lngTecnico: lngCentro,
      );

      expect(ordenado.map((TrabajoVista t) => t.id).toList(),
          <String>['segunda', 'primera']);
    });

    test('c5 · sin la posición del técnico, la lista NO se toca', () {
      // Sin GPS no hay criterio nuevo. Reordenar por cualquier otra cosa sería
      // inventar uno.
      final List<TrabajoVista> original = <TrabajoVista>[
        enPunto('b', lat: latCentro + 0.05, lng: lngCentro),
        enPunto('a', lat: latCentro + 0.001, lng: lngCentro),
      ];

      final List<TrabajoVista> ordenado = Cercania.ordenarPorCercania(
        original,
        latTecnico: null,
        lngTecnico: null,
      );

      expect(ordenado.map((TrabajoVista t) => t.id).toList(),
          <String>['b', 'a']);
    });
  });

  group('D · cómo se dice', () {
    test('d1 · debajo del kilómetro, en metros redondeados a la decena', () {
      // A esa escala el técnico está en la cuadra: los metros exactos no le
      // cambian nada y ocupan más.
      expect(Cercania.texto(0), '0 m');
      expect(Cercania.texto(123), '120 m');
      expect(Cercania.texto(999), '1000 m');
    });

    test('d2 · arriba del kilómetro, un decimal y con COMA', () {
      // En Colombia el punto separa miles: «1.2 km» se lee como mil doscientos.
      expect(Cercania.texto(1200), '1,2 km');
      expect(Cercania.texto(12340), '12,3 km');
    });

    test('d3 · nunca promete tiempo', () {
      // Es distancia en línea recta. Un río o un sentido único hacen que lo más
      // cercano en el mapa sea lo más lejano en minutos, y el técnico ajusta su
      // día con ese número.
      for (final double m in <double>[500, 1500, 20000]) {
        final String t = Cercania.texto(m);
        expect(t.contains('min'), isFalse, reason: t);
        expect(t.contains('hora'), isFalse, reason: t);
      }
    });
  });
}

/// Lo que se ve en la lista cuando el técnico pide «Cerca mío».
void _enLaPantalla() {
  Map<String, dynamic> orden(String id, {double? lat, double? lng, int? numero}) =>
      <String, dynamic>{
        'id': id,
        'numero': numero ?? 1000,
        'estado': 'asignada',
        'cliente_nombre': 'Cliente $id',
        'direccion': 'Calle $id',
        'tipo_nombre': 'Reparación',
        'tipo_codigo': 'ftth_correctivo',
        'schema_version': 1,
        'cliente_lat': lat,
        'cliente_lng': lng,
      };

  Future<void> montar(
    WidgetTester t,
    List<Map<String, dynamic>> filas, {
    Future<(double, double)?> Function()? donde,
  }) async {
    t.view.physicalSize = const Size(1000, 4200);
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);

    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    final OrdenesJornada ordenes = OrdenesJornada(
      leerOrdenes: () async => filas,
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    addTearDown(() async {
      await avisos.close();
      ordenes.dispose();
    });

    await t.pumpWidget(MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(
        body: TrabajoScreen(
          ordenes: ordenes,
          abrirTrabajo: (_, _) async {},
          dondeEstoy: donde,
        ),
      ),
    ));
    await t.pumpAndSettle();
  }

  group('E · «Cerca mío» en la lista', () {
    testWidgets('e1 · sin quien sepa ubicar, el filtro NO se ofrece',
        (WidgetTester t) async {
      // Una app compilada sin eso no ofrece un filtro que no va a funcionar.
      await montar(t, <Map<String, dynamic>>[orden('a', lat: 6.25, lng: -75.56)]);

      expect(find.text('Cerca mío'), findsNothing);
    });

    testWidgets('e2 · con ubicación, el filtro está y empieza APAGADO',
        (WidgetTester t) async {
      // Una orden con ventana prometida se atiende cuando se prometió, aunque
      // quede lejos. Reordenar sin que lo pidan cambia el día en silencio.
      await montar(
        t,
        <Map<String, dynamic>>[
          orden('lejos', numero: 1, lat: 6.30, lng: -75.56),
          orden('cerca', numero: 2, lat: 6.2519, lng: -75.5636),
        ],
        donde: () async => (6.2518, -75.5636),
      );

      expect(find.text('Cerca mío'), findsOneWidget);
      // El orden original: la 1 antes que la 2.
      final List<String> antes = t
          .widgetList<Text>(find.byType(Text))
          .map((Text w) => w.data ?? '')
          .where((String x) => x.startsWith('Cliente '))
          .toList();
      expect(antes.first, 'Cliente lejos');
    });

    testWidgets('e3 · al encenderlo, la más cercana queda primera',
        (WidgetTester t) async {
      await montar(
        t,
        <Map<String, dynamic>>[
          orden('lejos', numero: 1, lat: 6.30, lng: -75.56),
          orden('cerca', numero: 2, lat: 6.2519, lng: -75.5636),
        ],
        donde: () async => (6.2518, -75.5636),
      );

      // `ensureVisible` por si el filtro queda fuera del scroll horizontal: un
      // `tap` sobre algo fuera de la vista no falla, golpea al aire. Asi se
      // descubrio que el chip estaba al final y el toque no llegaba.
      await t.ensureVisible(find.text('Cerca mío'));
      await t.tap(find.text('Cerca mío'));
      // Dos vueltas: la primera dibuja el filtro encendido, la segunda recoge
      // el `setState` que hace la busqueda de ubicacion al resolverse. Es un
      // futuro que no cuelga de un frame, asi que un solo `pumpAndSettle` no lo
      // ve.
      await t.pumpAndSettle();
      await t.pumpAndSettle();

      final List<String> despues = t
          .widgetList<Text>(find.byType(Text))
          .map((Text w) => w.data ?? '')
          .where((String x) => x.startsWith('Cliente '))
          .toList();
      expect(despues.first, 'Cliente cerca');
    });

    testWidgets('e4 · la distancia se muestra en la tarjeta',
        (WidgetTester t) async {
      await montar(
        t,
        <Map<String, dynamic>>[orden('a', lat: 6.2608, lng: -75.5636)],
        donde: () async => (6.2518, -75.5636),
      );

      // `ensureVisible` por si el filtro queda fuera del scroll horizontal: un
      // `tap` sobre algo fuera de la vista no falla, golpea al aire. Asi se
      // descubrio que el chip estaba al final y el toque no llegaba.
      await t.ensureVisible(find.text('Cerca mío'));
      await t.tap(find.text('Cerca mío'));
      // Dos vueltas: la primera dibuja el filtro encendido, la segunda recoge
      // el `setState` que hace la busqueda de ubicacion al resolverse. Es un
      // futuro que no cuelga de un frame, asi que un solo `pumpAndSettle` no lo
      // ve.
      await t.pumpAndSettle();
      await t.pumpAndSettle();

      // ~1 km al norte. Se afirma la forma, no el dígito exacto: el número lo
      // cuida `a2`, y acá lo que importa es que aparezca y diga «km».
      expect(find.textContaining('km'), findsWidgets);
    });

    testWidgets('e5 · si la ubicación no llega, la lista NO se reordena',
        (WidgetTester t) async {
      // Sin GPS no hay criterio nuevo; reordenar por otra cosa sería inventar
      // uno. Y el filtro queda encendido: el técnico pidió eso, y apagarlo solo
      // le escondería que no se pudo.
      await montar(
        t,
        <Map<String, dynamic>>[
          orden('lejos', numero: 1, lat: 6.30, lng: -75.56),
          orden('cerca', numero: 2, lat: 6.2519, lng: -75.5636),
        ],
        donde: () async => null,
      );

      // `ensureVisible` por si el filtro queda fuera del scroll horizontal: un
      // `tap` sobre algo fuera de la vista no falla, golpea al aire. Asi se
      // descubrio que el chip estaba al final y el toque no llegaba.
      await t.ensureVisible(find.text('Cerca mío'));
      await t.tap(find.text('Cerca mío'));
      // Dos vueltas: la primera dibuja el filtro encendido, la segunda recoge
      // el `setState` que hace la busqueda de ubicacion al resolverse. Es un
      // futuro que no cuelga de un frame, asi que un solo `pumpAndSettle` no lo
      // ve.
      await t.pumpAndSettle();
      await t.pumpAndSettle();

      final List<String> igual = t
          .widgetList<Text>(find.byType(Text))
          .map((Text w) => w.data ?? '')
          .where((String x) => x.startsWith('Cliente '))
          .toList();
      expect(igual.first, 'Cliente lejos');
    });
  });
}
