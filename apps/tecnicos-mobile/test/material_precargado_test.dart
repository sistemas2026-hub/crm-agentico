/// EL MATERIAL QUE YA VIENE PUESTO (26/11/2026).
///
/// El usuario: «material utilizado, que sea precargado: en una instalación se
/// utilizan 2 conectores APC, una ONU, dos tensores, un precinto, dos chazos y
/// dos tornillos; las grapas y la fibra son variadas». Decidió: vienen puestas
/// y el técnico las ajusta.
library;

import 'dart:convert';

import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

void _pantallaAlta(WidgetTester t) {
  t.view.physicalSize = const Size(1000, 4600);
  t.view.devicePixelRatio = 1.0;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
}

Widget _app(FuenteDeEjecucionFalsa fuente) => MaterialApp(
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

const List<Map<String, dynamic>> _instalacion = <Map<String, dynamic>>[
  <String, dynamic>{'codigo': 'SCAPC', 'nombre': 'Conector SC/APC', 'unidad': 'unidades',
    'clase': 'consumible', 'cantidad': 2},
  <String, dynamic>{'codigo': 'ONU', 'nombre': 'ONU GPON', 'unidad': 'unidades',
    'clase': 'serializado', 'cantidad': 1},
  <String, dynamic>{'codigo': 'TENSOR', 'nombre': 'Tensor', 'unidad': 'unidades',
    'clase': 'consumible', 'cantidad': 2},
  <String, dynamic>{'codigo': 'GRAPA', 'nombre': 'Grapa', 'unidad': 'unidades',
    'clase': 'consumible', 'cantidad': null},
];

List<Map<String, dynamic>> _kit() => <Map<String, dynamic>>[
      <String, dynamic>{'codigo': 'SCAPC', 'disponible': '10', 'series_json': null},
      <String, dynamic>{'codigo': 'ONU', 'disponible': '2',
        'series_json': jsonEncode(<String>['ONU-0001', 'ONU-0002'])},
      <String, dynamic>{'codigo': 'TENSOR', 'disponible': '1', 'series_json': null},
    ];

/// Un campo que se lee con la cámara: el serial de la ONU.
Map<String, dynamic> _serial() => <String, dynamic>{
      'id': 'serial', 'titulo': 'Serial de la ONU', 'tipo': 'texto', 'escaneable': true,
      'reglas': <String, dynamic>{'required': false},
    };

FuenteDeEjecucionFalsa _fuente({
  List<Map<String, dynamic>> habitual = _instalacion,
  Map<String, dynamic> valores = const <String, dynamic>{},
  List<Map<String, dynamic>>? materiales,
}) =>
    FuenteDeEjecucionFalsa(
      campos: <Map<String, dynamic>>[_serial()],
      requisitos: const <Map<String, dynamic>>[],
      valores: Map<String, dynamic>.from(valores),
      materiales: materiales,
      materialHabitual: habitual,
      kitDado: _kit(),
    );

void main() {
  testWidgets('VIENE PUESTO: «Material utilizado» trae la lista, con lo que tiene el técnico',
      (WidgetTester t) async {
    _pantallaAlta(t);
    await t.pumpWidget(_app(_fuente()));
    await t.pumpAndSettle();

    expect(find.text('Material utilizado'), findsOneWidget);
    expect(find.text('Materiales en esta orden'), findsNothing);
    expect(find.text('Lo que se usa en este trabajo'), findsOneWidget);
    expect(find.text('Conector SC/APC'), findsOneWidget);
    expect(find.text('Tienes 10'), findsOneWidget);
    expect(find.text('Tienes 1: te faltan 1'), findsOneWidget, reason: 'tensores: 2 de 1');
  });

  testWidgets('SE AJUSTA Y SE REGISTRA: una línea por material, con la serie de la ONU que ya escribió',
      (WidgetTester t) async {
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f =
        _fuente(valores: <String, dynamic>{'serial': ' onu-0002 '});
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();

    //  Un conector más (3) y 4 grapas escritas a mano.
    await t.tap(find.bySemanticsLabel('Uno más').first);
    await t.pump();
    await t.enterText(find.widgetWithText(TextField, 'Cuánto'), '4');
    await t.pump();
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();

    expect(<List<String>>[
      for (final Map<String, dynamic> c in f.consumos)
        <String>[c['material_codigo'] as String, c['cantidad'] as String, c['serie'] as String],
    ], <List<String>>[
      <String>['SCAPC', '3', ''],
      <String>['ONU', '1', 'ONU-0002'],
      <String>['TENSOR', '2', ''],
      <String>['GRAPA', '4', ''],
    ]);
    expect(f.consumos.map((Map<String, dynamic> c) => c['id']).toSet(), hasLength(4),
        reason: 'cada uno con su clave: el servidor no los confunde');
    expect(find.text('Lo que se usa en este trabajo'), findsNothing,
        reason: 'lo registrado sale de la lista');
  });

  testWidgets('LA ONU SIN SERIE no se registra: lo dice, y no encola nada', (WidgetTester t) async {
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f = _fuente();
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();
    expect(find.textContaining('Elige la serie de ONU GPON'), findsOneWidget);
    expect(f.consumos, isEmpty);

    //  Y eligiéndola de las que tiene a cargo, sí.
    await t.tap(find.text('ONU-0001'));
    await t.pump();
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();
    expect(f.consumos.firstWhere((Map<String, dynamic> c) => c['material_codigo'] == 'ONU')['serie'],
        'ONU-0001');
  });

  testWidgets('una línea en CERO no se registra; una sin escribir (las grapas) tampoco',
      (WidgetTester t) async {
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f = _fuente(habitual: <Map<String, dynamic>>[
      _instalacion[0], _instalacion[3],
    ]);
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();
    await t.tap(find.bySemanticsLabel('Uno menos').first);
    await t.pump();
    await t.tap(find.bySemanticsLabel('Uno menos').first);
    await t.pump();
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();
    expect(f.consumos, isEmpty);
    expect(find.textContaining('No hay nada para registrar'), findsOneWidget);
  });

  testWidgets('lo que ya se registró de un material NO se vuelve a ofrecer', (WidgetTester t) async {
    _pantallaAlta(t);
    await t.pumpWidget(_app(_fuente(materiales: <Map<String, dynamic>>[
      <String, dynamic>{'material_codigo': 'SCAPC', 'material_nombre': 'Conector SC/APC',
        'cantidad': '2', 'serie': '', 'estado': 'pendiente'},
    ])));
    await t.pumpAndSettle();
    expect(find.text('Tienes 10'), findsNothing, reason: 'la línea del conector ya no está');
    expect(find.text('Tensor'), findsOneWidget);
  });

  testWidgets('EL CONTROL: sin lista de la empresa, el bloque es el de siempre', (WidgetTester t) async {
    _pantallaAlta(t);
    await t.pumpWidget(_app(_fuente(habitual: const <Map<String, dynamic>>[])));
    await t.pumpAndSettle();
    expect(find.text('Material utilizado'), findsOneWidget);
    expect(find.text('Lo que se usa en este trabajo'), findsNothing);
    expect(find.text('Todavía no registraste material en este trabajo.'), findsOneWidget);
  });

  testWidgets('LA FIBRA SALE DE SU CAMPO: lo que se escribió en «Metros de fibra usados» se registra',
      (WidgetTester t) async {
    //  El usuario: «cuando se pone la fibra utilizada y se pone la cantidad,
    //  que lo marque en material utilizado».
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f = FuenteDeEjecucionFalsa(
      campos: <Map<String, dynamic>>[_metros()],
      requisitos: const <Map<String, dynamic>>[],
      valores: <String, dynamic>{'metros': '35'},
      materialHabitual: const <Map<String, dynamic>>[_drop],
      kitDado: <Map<String, dynamic>>[<String, dynamic>{'codigo': 'DROP', 'disponible': '300'}],
    );
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();
    expect(find.text('35 metros'), findsOneWidget);
    expect(find.text('De «Metros de fibra usados»'), findsOneWidget);
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();
    expect(f.consumos.single['material_codigo'], 'DROP');
    expect(f.consumos.single['cantidad'], '35');
  });

  testWidgets('sin los metros escritos, la fibra no se registra y se dice dónde escribirlos',
      (WidgetTester t) async {
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f = FuenteDeEjecucionFalsa(
      campos: <Map<String, dynamic>>[_metros()],
      requisitos: const <Map<String, dynamic>>[],
      materialHabitual: const <Map<String, dynamic>>[_drop, _tensor],
    );
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();
    expect(find.text('Escríbelos en «Metros de fibra usados»'), findsOneWidget);
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();
    expect(f.consumos.map((Map<String, dynamic> c) => c['material_codigo']), <String>['TENSOR']);
  });

  testWidgets('LA ONU SALE DEL SERIAL ESCANEADO: no se elige ni se vuelve a escribir',
      (WidgetTester t) async {
    //  El usuario: «donde dice ONU GPON debe llenarse solo al momento que el
    //  técnico escanea, para no volver a escribir».
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f = FuenteDeEjecucionFalsa(
      campos: <Map<String, dynamic>>[_serialDeLaOnu(), _precinto()],
      requisitos: const <Map<String, dynamic>>[],
      //  El precinto también se escanea: NO es la serie de la ONU.
      valores: <String, dynamic>{'serial': ' onu-0002 ', 'precinto': 'PRE-777'},
      materialHabitual: const <Map<String, dynamic>>[_onuDesdeElSerial],
      kitDado: _kit(),
    );
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();
    expect(find.text('ONU-0002'), findsOneWidget);
    expect(find.text('Serie de «Serial de la ONU»'), findsOneWidget);
    expect(find.text('ONU-0001'), findsNothing, reason: 'no hay lista para elegir');
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();
    expect(f.consumos.single['serie'], 'ONU-0002');
    expect(f.consumos.single['material_codigo'], 'ONU');
  });

  testWidgets('una serie escaneada que NO está en el kit se avisa y se registra igual',
      (WidgetTester t) async {
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f = FuenteDeEjecucionFalsa(
      campos: <Map<String, dynamic>>[_serialDeLaOnu()],
      requisitos: const <Map<String, dynamic>>[],
      valores: <String, dynamic>{'serial': 'FHTT99990000'},
      materialHabitual: const <Map<String, dynamic>>[_onuDesdeElSerial],
      kitDado: _kit(),
    );
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();
    expect(find.textContaining('Esa serie no está en tu kit'), findsOneWidget);
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();
    expect(f.consumos.single['serie'], 'FHTT99990000');
  });

  testWidgets('sin el serial escaneado, la ONU no se registra y se dice dónde escanearlo',
      (WidgetTester t) async {
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f = FuenteDeEjecucionFalsa(
      campos: <Map<String, dynamic>>[_serialDeLaOnu()],
      requisitos: const <Map<String, dynamic>>[],
      materialHabitual: const <Map<String, dynamic>>[_onuDesdeElSerial],
      kitDado: _kit(),
    );
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();
    expect(find.text('Escanéalo en «Serial de la ONU»'), findsOneWidget);
    await t.tap(find.text('Registrar este material'));
    await t.pumpAndSettle();
    expect(find.textContaining('Escanea el serial en «Serial de la ONU»'), findsOneWidget);
    expect(f.consumos, isEmpty);
  });
}

Map<String, dynamic> _serialDeLaOnu() => <String, dynamic>{
      'id': 'serial', 'titulo': 'Serial de la ONU', 'tipo': 'texto', 'escaneable': true,
      'reglas': <String, dynamic>{'required': false},
    };

Map<String, dynamic> _precinto() => <String, dynamic>{
      'id': 'precinto', 'titulo': 'Precinto del cliente', 'tipo': 'texto', 'escaneable': true,
      'reglas': <String, dynamic>{'required': false},
    };

const Map<String, dynamic> _onuDesdeElSerial = <String, dynamic>{'codigo': 'ONU',
  'nombre': 'ONU GPON', 'unidad': 'unidades', 'clase': 'serializado', 'cantidad': 1,
  'campo': 'Serial de la ONU'};

Map<String, dynamic> _metros() => <String, dynamic>{
      'id': 'metros', 'titulo': 'Metros de fibra usados', 'tipo': 'numero',
      'reglas': <String, dynamic>{'required': false},
    };

const Map<String, dynamic> _drop = <String, dynamic>{'codigo': 'DROP', 'nombre': 'Cable drop',
  'unidad': 'metros', 'clase': 'bobina', 'cantidad': null, 'campo': 'Metros de fibra usados'};

const Map<String, dynamic> _tensor = <String, dynamic>{'codigo': 'TENSOR', 'nombre': 'Tensor',
  'unidad': 'unidades', 'clase': 'consumible', 'cantidad': 2};
