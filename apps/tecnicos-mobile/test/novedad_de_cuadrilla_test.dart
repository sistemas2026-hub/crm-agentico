import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/inicio/novedad_de_cuadrilla.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// LA NOVEDAD DE LA CUADRILLA (30/10/2026). El usuario: «¿cómo el técnico
/// reporta alguna novedad sin tener que escribir en el ticket, por ejemplo se
/// pinchó la llanta?». SPEC/objetivos/novedad-de-cuadrilla.md.

final DateTime _diez = DateTime(2026, 10, 30, 10, 0);

NovedadLocal _n({String afecta = 'media_hora', bool resuelta = false, String estado = 'pendiente'}) =>
    NovedadLocal(
      id: 'n-1',
      tipo: 'llanta',
      afecta: afecta,
      avisadaEn: _diez,
      estado: estado,
      resuelta: resuelta,
    );

void main() {
  group('cuándo está vigente: la misma regla que el servidor', () {
    test('la corta vence sola; la del resto del día, hasta «Ya seguí»', () {
      expect(_n().vigente(_diez.add(const Duration(minutes: 29))), isTrue);
      expect(_n().vigente(_diez.add(const Duration(minutes: 30))), isFalse);
      expect(_n(afecta: 'una_hora').vigente(_diez.add(const Duration(minutes: 59))), isTrue);
      expect(_n(afecta: 'resto_del_dia').vigente(_diez.add(const Duration(hours: 8))), isTrue);
      expect(_n(afecta: 'resto_del_dia', resuelta: true).vigente(_diez), isFalse);
    });

    test('dice qué fue y cuándo', () {
      expect(_n().queFue, 'Se pinchó una llanta');
      expect(_n().cuando, 'desde las 10:00 · hasta las 10:30');
      expect(_n(afecta: 'resto_del_dia').cuando, 'desde las 10:00 · el resto del día');
    });
  });

  group('la hoja para avisar', () {
    testWidgets('sin qué pasó y cuánto afecta no se puede avisar; con los dos, '
        'devuelve lo elegido', (WidgetTester t) async {
      (String, String, String)? devuelto;
      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: Builder(
            builder: (BuildContext c) => TextButton(
              onPressed: () async {
                devuelto = await showModalBottomSheet<(String, String, String)>(
                  context: c,
                  isScrollControlled: true,
                  builder: (_) => const HojaDeNovedad(),
                );
              },
              child: const Text('abrir'),
            ),
          ),
        ),
      ));
      await t.tap(find.text('abrir'));
      await t.pumpAndSettle();

      final Finder avisar = find.byKey(const ValueKey<String>('avisar-novedad'));
      expect(t.widget<FilledButton>(avisar).onPressed, isNull);

      await t.tap(find.byKey(const ValueKey<String>('tipo-llanta')));
      await t.pump();
      expect(t.widget<FilledButton>(avisar).onPressed, isNull, reason: 'falta cuánto afecta');

      await t.tap(find.byKey(const ValueKey<String>('afecta-resto_del_dia')));
      await t.pump();
      expect(find.text('Tus órdenes sin empezar pasan a otra cuadrilla.'), findsOneWidget);
      await t.enterText(find.byKey(const ValueKey<String>('texto-de-la-novedad')), '  en la vía  ');
      await t.tap(avisar);
      await t.pumpAndSettle();

      expect(devuelto, ('llanta', 'resto_del_dia', 'en la vía'));
    });
  });

  group('la franja', () {
    testWidgets('dice si la oficina ya la tiene, y «Ya seguí» la cierra', (WidgetTester t) async {
      int cerradas = 0;
      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(body: FranjaDeNovedad(novedad: _n(), onYaSegui: () => cerradas++)),
      ));
      expect(find.text('Sin enviar: sube cuando haya señal'), findsOneWidget);
      await t.tap(find.byKey(const ValueKey<String>('ya-segui')));
      expect(cerradas, 1);

      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(body: FranjaDeNovedad(novedad: _n(estado: 'enviada'))),
      ));
      expect(find.text('La oficina ya la tiene'), findsOneWidget);
    });
  });

  group('la cola del teléfono', () {
    final JornadaDePrueba j = JornadaDePrueba('novedades.db');

    setUpAll(j.prepararElEntorno);
    setUp(j.empezar);
    tearDown(j.terminar);
    tearDownAll(j.cerrarTodo);

    test('se encola, sube, y su «Ya seguí» sube aparte', () async {
      await j.limpiar();
      const String org = JornadaDePrueba.org;
      const String yo = JornadaDePrueba.perfil;
      await j.db.encolarNovedad(
          orgId: org, profileId: yo, id: 'n-1', tipo: 'llanta',
          afecta: 'resto_del_dia', avisadaEn: '2026-10-30T15:00:00.000Z');
      await j.db.encolarNovedad(
          orgId: org, profileId: yo, id: 'n-1', tipo: 'otra',
          afecta: 'media_hora', avisadaEn: '2026-10-30T15:00:00.000Z');

      List<Map<String, dynamic>> p = await j.db.novedadesPendientes(orgId: org, profileId: yo);
      expect(p.map((Map<String, dynamic> f) => f['tipo']), <String>['llanta'],
          reason: 'la misma clave no se encola dos veces');

      await j.db.marcarNovedadSubida(id: 'n-1', orgId: org, profileId: yo, servidorId: 's-1');
      expect(await j.db.novedadesPendientes(orgId: org, profileId: yo), isEmpty);

      await j.db.resolverNovedad(id: 'n-1', orgId: org, profileId: yo);
      p = await j.db.novedadesPendientes(orgId: org, profileId: yo);
      expect(p.single['servidor_id'], 's-1', reason: 'falta subir el «Ya seguí»');

      await j.db.marcarNovedadSubida(id: 'n-1', orgId: org, profileId: yo, resueltaSubida: true);
      expect(await j.db.novedadesPendientes(orgId: org, profileId: yo), isEmpty);

      final NovedadLocal? n = NovedadLocal.desdeFila(
          (await j.db.leerNovedades(orgId: org, profileId: yo)).single);
      expect((n?.estado, n?.resuelta), ('enviada', true));
    });
  });
}
