/// ACTIVAR LA ONU (26/11/2026). El recuadro del paso de la instalación.
library;

import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/ejecucion/widgets/activar_onu.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiDeLaOnu {
  _Api({this.encendido = true, this.vlan = 300, this.ultima, this.errorDeBusqueda,
      this.apareceTras = 0});

  final bool encendido;
  final int? vlan;
  Map<String, dynamic>? ultima;
  final String? errorDeBusqueda;

  /// Cuántas búsquedas del serial bueno contestan «no espera» antes de que la
  /// red la vea: la ONU recién conectada.
  int apareceTras;
  final List<String?> buscados = <String?>[];
  final List<List<String>> pedidos = <List<String>>[];
  int preguntas = 0;

  @override
  Future<Map<String, dynamic>> estado(String ordenId, {String? serial}) async {
    if (serial == null) {
      preguntas++;
      //  A la segunda pregunta, el pedido ya quedó.
      if (ultima != null && ultima!['en_vuelo'] == true && preguntas > 2) {
        ultima = <String, dynamic>{...ultima!, 'estado': 'activada', 'en_vuelo': false,
          'olt': '3', 'placa': '3', 'puerto': '6'};
      }
      return <String, dynamic>{'encendido': encendido, 'ultima': ultima, 'onu': null};
    }
    buscados.add(serial);
    if (errorDeBusqueda != null) {
      return <String, dynamic>{'encendido': encendido, 'ultima': null, 'onu': null,
        'error': errorDeBusqueda};
    }
    if (serial == 'FHTT12345678' && apareceTras > 0) {
      apareceTras--;
      return <String, dynamic>{'encendido': encendido, 'ultima': null,
        'onu': <String, dynamic>{'estado': 'no_espera'}};
    }
    if (serial != 'FHTT12345678') {
      return <String, dynamic>{'encendido': encendido, 'ultima': null,
        'onu': <String, dynamic>{'estado': 'no_espera'}};
    }
    return <String, dynamic>{'encendido': encendido, 'ultima': null, 'onu': <String, dynamic>{
      'estado': 'esperando', 'olt': '3', 'placa': '3', 'puerto': '6', 'tipo': 'FD714GS1-R850',
      'zonas': <String>['SAN VICENTE', 'VILLA ADELA 2'], 'zona_sugerida': 'VILLA ADELA 2',
      'vlan': vlan, 'servidor': 'CORTE 30 - SERVIDOR 1'}};
  }

  @override
  Future<Map<String, dynamic>> activar(String ordenId, String serial, String zona) async {
    pedidos.add(<String>[serial, zona]);
    ultima = <String, dynamic>{'estado': 'pedida', 'en_vuelo': true, 'olt': '', 'placa': '',
      'puerto': ''};
    return <String, dynamic>{'activacion': ultima};
  }
}

Widget _app(_Api api, {List<String> seriales = const <String>['PRE-0001', 'FHTT12345678']}) =>
    MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(
        body: SingleChildScrollView(
          child: ActivarOnu(ordenId: 'ot-1', seriales: seriales, api: api,
              cadaCuanto: const Duration(milliseconds: 20), vueltas: 20,
              esperaEntreBusquedas: const Duration(milliseconds: 30), busquedas: 3),
        ),
      ),
    );

void _alto(WidgetTester t) {
  t.view.physicalSize = const Size(900, 2400);
  t.view.devicePixelRatio = 1.0;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
}

void main() {
  testWidgets('BUSCA con cada valor del paso hasta que la red reconoce uno, y ACTIVA con la zona sugerida',
      (WidgetTester t) async {
    _alto(t);
    final _Api api = _Api();
    await t.pumpWidget(_app(api));
    await t.pumpAndSettle();
    await t.tap(find.text('Buscar la ONU en la red'));
    await t.pumpAndSettle();

    expect(api.buscados, <String>['PRE-0001', 'FHTT12345678'],
        reason: 'el precinto no es una ONU; el serial sí');
    expect(find.text('OLT 3 · placa 3 · puerto 6'), findsOneWidget);
    expect(find.text('VILLA ADELA 2'), findsOneWidget, reason: 'la zona sugerida, ya elegida');
    expect(find.text('VLAN 300, la del servidor CORTE 30 - SERVIDOR 1.'), findsOneWidget);

    await t.tap(find.text('Activar ONU'));
    await t.pump();
    expect(api.pedidos, <List<String>>[<String>['FHTT12345678', 'VILLA ADELA 2']]);
    expect(find.textContaining('Activando la ONU'), findsOneWidget);
    for (int i = 0; i < 10; i++) {
      await t.pump(const Duration(milliseconds: 25));
    }
    await t.pumpAndSettle();
    expect(find.text('ONU activada en la red (OLT 3 · placa 3 · puerto 6).'), findsOneWidget);
    expect(find.text('ACTIVADA'), findsOneWidget, reason: 'la pastilla escribe en mayúsculas');
  });

  testWidgets('SIN VLAN del servidor, o APAGADO, no deja activar y dice por qué', (WidgetTester t) async {
    _alto(t);
    await t.pumpWidget(_app(_Api(vlan: null)));
    await t.pumpAndSettle();
    await t.tap(find.text('Buscar la ONU en la red'));
    await t.pumpAndSettle();
    expect(find.textContaining('Falta la VLAN del servidor'), findsOneWidget);
    FilledButton boton = t.widget<FilledButton>(find.byWidgetPredicate((Widget w) => w is FilledButton));
    expect(boton.onPressed, isNull);

    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(_app(_Api(encendido: false)));
    await t.pumpAndSettle();
    expect(find.textContaining('no encendió «Activar ONU»'), findsOneWidget);
    await t.tap(find.text('Buscar la ONU en la red'));
    await t.pumpAndSettle();
    boton = t.widget<FilledButton>(find.byWidgetPredicate((Widget w) => w is FilledButton));
    expect(boton.onPressed, isNull);
  });

  testWidgets('si NINGÚN valor espera, lo dice; y sin serial escrito, pide escribirlo', (WidgetTester t) async {
    _alto(t);
    final _Api nadie = _Api();
    await t.pumpWidget(_app(nadie, seriales: <String>['OTRO-1234']));
    await t.pumpAndSettle();
    await t.tap(find.text('Buscar la ONU en la red'));
    await t.pump();
    for (int i = 0; i < 6; i++) {
      await t.pump(const Duration(milliseconds: 30));
    }
    await t.pumpAndSettle();
    expect(nadie.buscados, <String>['OTRO-1234', 'OTRO-1234', 'OTRO-1234'],
        reason: 'busca sola las veces que tiene, y ahí para');
    expect(find.textContaining('no aparece esperando autorización'), findsOneWidget);
    expect(find.text('Activar ONU'), findsNothing);

    await t.pumpWidget(const SizedBox());
    final _Api api = _Api();
    await t.pumpWidget(_app(api, seriales: const <String>[]));
    await t.pumpAndSettle();
    await t.tap(find.text('Buscar la ONU en la red'));
    await t.pumpAndSettle();
    expect(find.textContaining('Primero escribe o escanea el serial'), findsOneWidget);
    expect(api.buscados, isEmpty);
  });

  testWidgets('LA ONU RECIÉN CONECTADA: si no aparece, sigue buscando sola y la encuentra',
      (WidgetTester t) async {
    _alto(t);
    final _Api api = _Api(apareceTras: 1);
    await t.pumpWidget(_app(api, seriales: const <String>['FHTT12345678']));
    await t.pumpAndSettle();
    await t.tap(find.text('Buscar la ONU en la red'));
    await t.pump();
    await t.pump();
    expect(find.textContaining('sigo buscando (2 de 3)'), findsOneWidget);
    await t.pump(const Duration(milliseconds: 40));
    await t.pumpAndSettle();
    expect(api.buscados, <String>['FHTT12345678', 'FHTT12345678'],
        reason: 'la segunda vez ya está, sin que el técnico vuelva a tocar');
    expect(find.text('OLT 3 · placa 3 · puerto 6'), findsOneWidget);
    expect(find.textContaining('sigo buscando'), findsNothing);
  });

  testWidgets('un error del servidor (sin contrato) se dice tal cual', (WidgetTester t) async {
    _alto(t);
    await t.pumpWidget(_app(_Api(errorDeBusqueda: 'Primero crea el contrato: de ahí salen el nombre.')));
    await t.pumpAndSettle();
    await t.tap(find.text('Buscar la ONU en la red'));
    await t.pumpAndSettle();
    expect(find.text('Primero crea el contrato: de ahí salen el nombre.'), findsOneWidget);
  });

  testWidgets('al abrir, muestra cómo quedó el último pedido', (WidgetTester t) async {
    _alto(t);
    await t.pumpWidget(_app(_Api(ultima: <String, dynamic>{'estado': 'por_revisar', 'en_vuelo': false,
      'detalle': 'Que la oficina la mire en SmartOLT.', 'olt': '', 'placa': '', 'puerto': ''})));
    await t.pumpAndSettle();
    expect(find.text('Que la oficina la mire en SmartOLT.'), findsOneWidget);
    expect(find.text('REVISAR'), findsOneWidget);
    expect(find.text('Volver a buscar'), findsOneWidget);
  });
}
