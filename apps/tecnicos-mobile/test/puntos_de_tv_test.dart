/// LOS PUNTOS DE TV (26/11/2026).
///
/// La regla del usuario: 1 punto = 2 conectores coaxiales; 2 puntos = 6
/// conectores y un spliter de 2; para 3 a 5, 2 por punto + 2 de entrada; el
/// spliter, el más chico que alcance ENTRE LOS QUE TIENE EL TÉCNICO; el cable
/// se pregunta; máximo 5.
library;

import 'dart:convert';

import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:campo/features/ejecucion/puntos_de_tv.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

const Map<String, dynamic> _rapilink = <String, dynamic>{
  'conector': <String, dynamic>{'codigo': 'CONCOAX', 'nombre': 'Conector coaxial RG6'},
  'conectores_por_punto': 2,
  'conectores_de_entrada': 2,
  'maximo_de_puntos': 5,
  'cable': <String, dynamic>{'codigo': 'RG6', 'nombre': 'Cable coaxial RG6'},
  'spliters': <Map<String, dynamic>>[
    <String, dynamic>{'codigo': 'SPL4', 'nombre': 'Spliter de 4 salidas', 'salidas': 4},
    <String, dynamic>{'codigo': 'SPL2', 'nombre': 'Spliter de 2 salidas', 'salidas': 2},
    <String, dynamic>{'codigo': 'SPL3', 'nombre': 'Spliter de 3 salidas', 'salidas': 3},
  ],
};

/// Lo que tiene el técnico de la OT-15 en local: sin spliter de 3.
List<Map<String, dynamic>> _kit({bool conSpl3 = false}) => <Map<String, dynamic>>[
      <String, dynamic>{'codigo': 'CONCOAX', 'disponible': '20'},
      <String, dynamic>{'codigo': 'SPL2', 'disponible': '2'},
      <String, dynamic>{'codigo': 'SPL4', 'disponible': '2'},
      if (conSpl3) <String, dynamic>{'codigo': 'SPL3', 'disponible': '1'},
      <String, dynamic>{'codigo': 'RG6', 'disponible': '100'},
    ];

void main() {
  group('A · la cuenta', () {
    test('la regla del usuario: 2, 6, 8, 10, 12 conectores', () {
      expect(<int>[
        for (int n = 1; n <= 5; n++) cuentaDeTv(config: _rapilink, puntos: n, kit: _kit()).conectores,
      ], <int>[2, 6, 8, 10, 12]);
    });

    test('1 punto no lleva spliter', () {
      final CuentaDeTv c = cuentaDeTv(config: _rapilink, puntos: 1, kit: _kit());
      expect(c.spliter, isNull);
      expect(c.ningunSpliterAlcanza, isFalse);
    });

    test('2 puntos: el de 2', () {
      expect(cuentaDeTv(config: _rapilink, puntos: 2, kit: _kit()).spliter!.codigo, 'SPL2');
    });

    test('3 puntos SIN spliter de 3 en el kit: el de 4 que SÍ tiene', () {
      final CuentaDeTv c = cuentaDeTv(config: _rapilink, puntos: 3, kit: _kit());
      expect(c.spliter!.codigo, 'SPL4');
      expect(c.spliterEnElKit, isTrue);
    });

    test('3 puntos CON spliter de 3 en el kit: el de 3 (el más chico que alcance)', () {
      expect(cuentaDeTv(config: _rapilink, puntos: 3, kit: _kit(conSpl3: true)).spliter!.codigo, 'SPL3');
    });

    test('sin ninguno que alcance en el kit, el más chico de la empresa, y se dice', () {
      final CuentaDeTv c = cuentaDeTv(config: _rapilink, puntos: 3, kit: const <Map<String, dynamic>>[]);
      expect(c.spliter!.codigo, 'SPL3');
      expect(c.spliterEnElKit, isFalse);
    });

    test('5 puntos y ningún spliter de 5 o más: no se inventa uno', () {
      final CuentaDeTv c = cuentaDeTv(config: _rapilink, puntos: 5, kit: _kit());
      expect(c.spliter, isNull);
      expect(c.ningunSpliterAlcanza, isTrue);
    });

    test('otra empresa, otra cuenta: 3 por punto y 1 de entrada', () {
      final Map<String, dynamic> otra = <String, dynamic>{
        ..._rapilink, 'conectores_por_punto': 3, 'conectores_de_entrada': 1,
      };
      expect(cuentaDeTv(config: otra, puntos: 1, kit: _kit()).conectores, 3);
      expect(cuentaDeTv(config: otra, puntos: 2, kit: _kit()).conectores, 7);
    });
  });

  group('B · en «Material utilizado»', () {
    void pantallaAlta(WidgetTester t) {
      t.view.physicalSize = const Size(1000, 4600);
      t.view.devicePixelRatio = 1.0;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);
    }

    Widget app(FuenteDeEjecucionFalsa f) => MaterialApp(
          theme: AppTheme.lightTheme,
          home: EjecucionScreen(
            ordenId: 'ot-1',
            fuente: f,
            resumenDeSync: const SyncSummary(
              status: SyncStatus.idle, isSyncing: false, hasConnectionError: false,
              mutacionesPendientes: 0, mutacionesConflicto: 0, evidenciasPendientes: 0, datosDirty: 0,
            ),
          ),
        );

    FuenteDeEjecucionFalsa fuente({List<Map<String, dynamic>>? materiales}) => FuenteDeEjecucionFalsa(
          requisitos: const <Map<String, dynamic>>[],
          materiales: materiales,
          puntosDeTv: jsonDecode(jsonEncode(_rapilink)) as Map<String, dynamic>,
          kitDado: _kit(),
        );

    testWidgets('3 PUNTOS Y CABLE: 8 conectores, el spliter de 4 que tiene, y los metros',
        (WidgetTester t) async {
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = fuente();
      await t.pumpWidget(app(f));
      await t.pumpAndSettle();

      expect(find.text('¿Cuántos puntos de TV instalaste?'), findsOneWidget);
      await t.tap(find.text('3'));
      await t.pumpAndSettle();
      expect(find.text('× 8'), findsOneWidget);
      expect(find.text('Spliter de 4 salidas'), findsOneWidget);
      expect(find.text('Tienes 2 · de 4 salidas'), findsOneWidget);

      await t.tap(find.text('Sí'));
      await t.pumpAndSettle();
      await t.enterText(find.widgetWithText(TextField, 'Metros'), '25');
      await t.tap(find.text('Registrar el material de TV'));
      await t.pumpAndSettle();

      expect(<List<String>>[
        for (final Map<String, dynamic> c in f.consumos)
          <String>[c['material_codigo'] as String, c['cantidad'] as String],
      ], <List<String>>[
        <String>['CONCOAX', '8'],
        <String>['SPL4', '1'],
        <String>['RG6', '25'],
      ]);
      expect(find.text('¿Cuántos puntos de TV instalaste?'), findsNothing,
          reason: 'registrado, ya está en la lista de abajo');
    });

    testWidgets('1 punto sin cable de la empresa: solo los 2 conectores', (WidgetTester t) async {
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = fuente();
      await t.pumpWidget(app(f));
      await t.pumpAndSettle();
      await t.tap(find.text('1'));
      await t.pumpAndSettle();
      await t.tap(find.text('No'));
      await t.pumpAndSettle();
      await t.tap(find.text('Registrar el material de TV'));
      await t.pumpAndSettle();
      expect(f.consumos.map((Map<String, dynamic> c) => '${c['material_codigo']}:${c['cantidad']}'),
          <String>['CONCOAX:2']);
    });

    testWidgets('lo que falta decir se pide antes de registrar: el cable y sus metros', (WidgetTester t) async {
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = fuente();
      await t.pumpWidget(app(f));
      await t.pumpAndSettle();
      await t.tap(find.text('2'));
      await t.pumpAndSettle();
      await t.tap(find.text('Registrar el material de TV'));
      await t.pumpAndSettle();
      expect(find.text('Di si usaste cable de la empresa.'), findsOneWidget);
      await t.tap(find.text('Sí'));
      await t.pumpAndSettle();
      await t.tap(find.text('Registrar el material de TV'));
      await t.pumpAndSettle();
      expect(find.text('Escribe cuántos metros de cable usaste.'), findsOneWidget);
      expect(f.consumos, isEmpty);
    });

    testWidgets('5 puntos sin spliter que alcance: se elige el que usó', (WidgetTester t) async {
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa f = fuente();
      await t.pumpWidget(app(f));
      await t.pumpAndSettle();
      await t.tap(find.text('5'));
      await t.pumpAndSettle();
      expect(find.textContaining('Ningún spliter de la empresa tiene 5 salidas'), findsOneWidget);
      await t.tap(find.text('De 4'));
      await t.tap(find.text('No'));
      await t.pumpAndSettle();
      await t.tap(find.text('Registrar el material de TV'));
      await t.pumpAndSettle();
      expect(f.consumos.map((Map<String, dynamic> c) => '${c['material_codigo']}:${c['cantidad']}'),
          <String>['CONCOAX:12', 'SPL4:1']);
    });

    testWidgets('máximo 5 puntos, y sin TV configurada no sale la tarjeta', (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(fuente()));
      await t.pumpAndSettle();
      expect(find.text('5'), findsOneWidget);
      expect(find.text('6'), findsNothing);

      await t.pumpWidget(const SizedBox());
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(requisitos: const <Map<String, dynamic>>[])));
      await t.pumpAndSettle();
      expect(find.text('Puntos de TV'), findsNothing);
    });
  });
}
