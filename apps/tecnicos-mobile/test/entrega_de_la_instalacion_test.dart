/// LA INSTALACIÓN QUE VALIDA UNA PERSONA (26/11/2026): el recuadro de la entrega.
library;

import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/entrega_de_la_instalacion.dart';
import 'package:campo/features/trabajo/estado_validacion.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiDeLaEntrega {
  _Api({this.error});

  final String? error;
  final List<String> pedidas = <String>[];

  @override
  Future<String?> entregar(String ordenId) async {
    pedidas.add(ordenId);
    return error;
  }
}

Widget _app(Widget hijo) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: SingleChildScrollView(child: hijo)),
    );

void main() {
  testWidgets('FINALIZADA Y SIN APROBAR: dice que espera, y no ofrece entregar', (WidgetTester t) async {
    final _Api api = _Api();
    await t.pumpWidget(_app(EntregaDeLaInstalacion(
        ordenId: 'ot-1', validacion: EstadoValidacion.pendiente, api: api)));
    expect(find.text('En validación'), findsOneWidget);
    expect(find.text('Finalizar trabajo'), findsNothing);
  });

  testWidgets('APROBADA: se confirma la entrega, y la pantalla vuelve a leer la orden', (WidgetTester t) async {
    final _Api api = _Api();
    int releidas = 0;
    await t.pumpWidget(_app(EntregaDeLaInstalacion(
        ordenId: 'ot-1', validacion: EstadoValidacion.aprobado, api: api,
        alEntregar: () async => releidas++)));
    expect(find.text('Aprobada y activa'), findsOneWidget);
    await t.tap(find.text('Finalizar trabajo'));
    await t.pumpAndSettle();
    expect(api.pedidas, <String>['ot-1']);
    expect(find.text('Trabajo finalizado'), findsOneWidget);
    expect(find.textContaining('se cerraron la orden y el ticket'), findsOneWidget);
    expect(releidas, 1);
  });

  testWidgets('si el servidor dice que no, lo muestra y se puede volver a tocar', (WidgetTester t) async {
    final _Api api = _Api(error: 'Todavía no está aprobada: espera el aviso de que quedó activada.');
    await t.pumpWidget(_app(EntregaDeLaInstalacion(
        ordenId: 'ot-1', validacion: EstadoValidacion.aprobado, api: api)));
    await t.tap(find.text('Finalizar trabajo'));
    await t.pumpAndSettle();
    expect(find.textContaining('Todavía no está aprobada'), findsOneWidget);
    expect(find.text('Finalizar trabajo'), findsOneWidget);
  });

  testWidgets('APROBADA: «Material y cierre» antes de finalizar, y lo pendiente sube primero (27/11/2026)',
      (WidgetTester t) async {
    final _Api api = _Api();
    final List<String> orden = <String>[];
    int abiertas = 0;
    await t.pumpWidget(_app(EntregaDeLaInstalacion(
        ordenId: 'ot-1', validacion: EstadoValidacion.aprobado, api: api,
        alAbrirMaterialYCierre: () async => abiertas++,
        antesDeFinalizar: () async => orden.add('subir'))));
    await t.tap(find.text('Material y cierre'));
    await t.pumpAndSettle();
    expect(abiertas, 1);
    await t.tap(find.text('Finalizar trabajo'));
    await t.pumpAndSettle();
    expect(orden, <String>['subir'], reason: 'antes de finalizar sube lo que esté en la cola');
    expect(api.pedidas, <String>['ot-1']);
  });

  testWidgets('si el servidor dice que falta el cierre, se lee tal cual', (WidgetTester t) async {
    final _Api api = _Api(error: 'Falta el material y el cierre: regístralos en «Material y cierre».');
    await t.pumpWidget(_app(EntregaDeLaInstalacion(
        ordenId: 'ot-1', validacion: EstadoValidacion.aprobado, api: api,
        alAbrirMaterialYCierre: () async {})));
    await t.tap(find.text('Finalizar trabajo'));
    await t.pumpAndSettle();
    expect(find.textContaining('Falta el material y el cierre'), findsOneWidget);
  });
}
