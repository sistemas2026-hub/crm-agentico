/// LA INSTALACIÓN EN LA PANTALLA DE TRABAJO (26/11/2026).
///
/// Lo que pidió el usuario al probar una instalación en el teléfono:
///   * «quitar el letrero de cierre de trabajo y un botón para ver el
///     contrato donde está»;
///   * «la pantalla de reportar no debería salir en instalación, o por lo
///     menos mejor abajo».
/// Y el control: en un trabajo que NO es instalación, todo sigue como estaba.
library;

import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:campo/features/contrato/contrato_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

void _pantallaAlta(WidgetTester t) {
  t.view.physicalSize = const Size(1000, 4200);
  t.view.devicePixelRatio = 1.0;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
}

Widget _app(FuenteDeEjecucionFalsa fuente, {ApiDelContrato api = const _SinContrato()}) =>
    MaterialApp(
      theme: AppTheme.lightTheme,
      home: EjecucionScreen(
        ordenId: 'ot-1',
        fuente: fuente,
        apiDelContrato: api,
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

/// El contrato, como lo contesta el servidor.
class _ContratoFalso extends ApiDelContrato {
  const _ContratoFalso(this.cuerpo, {this.error});
  final Map<String, dynamic>? cuerpo;
  final String? error;
  @override
  Future<RespuestaDelServidor> leer(String ordenId) async =>
      RespuestaDelServidor(cuerpo: cuerpo, error: error);
}

class _SinContrato extends _ContratoFalso {
  const _SinContrato() : super(const <String, dynamic>{'contrato': null});
}

Map<String, dynamic> _seguimiento() => <String, dynamic>{
      'eventos': <dynamic>[],
      'momentos_registrados': <String>[],
      'formularios': <String, dynamic>{
        for (final String m in <String>['inicio', 'avance', 'bloqueo', 'cierre'])
          m: <String, dynamic>{
            'momento': m,
            'campos': <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 'nota_$m',
                'titulo': 'Nota',
                'tipo': 'texto',
                'reglas': <String, dynamic>{'required': true},
              },
            ],
            'evidencias': <dynamic>[],
          },
      },
    };

FuenteDeEjecucionFalsa _fuente(String tipoCodigo) =>
    FuenteDeEjecucionFalsa(tipoCodigo: tipoCodigo)..seguimientoDado = _seguimiento();

Map<String, dynamic> _campo(String id, String paso) => <String, dynamic>{
      'id': id, 'titulo': 'Dato $id', 'tipo': 'texto', 'paso': paso,
      'reglas': <String, dynamic>{'required': false},
    };

/// Una instalación cuya plantilla dice en qué paso va cada botón (26/11/2026).
FuenteDeEjecucionFalsa _conBotonesPorPaso() => FuenteDeEjecucionFalsa(
      tipoCodigo: 'ftth_instalacion',
      requisitos: const <Map<String, dynamic>>[],
      campos: <Map<String, dynamic>>[
        _campo('a', 'paso_1'), _campo('b', 'paso_2'), _campo('c', 'paso_3'),
      ],
      pasos: const <Map<String, dynamic>>[
        <String, dynamic>{'id': 'paso_1', 'titulo': 'Puerto y acceso', 'botones': <String>['reportar']},
        <String, dynamic>{'id': 'paso_2', 'titulo': 'Contrato y documentos', 'botones': <String>['contrato']},
        <String, dynamic>{'id': 'paso_3', 'titulo': 'Instalación', 'botones': <String>['ip']},
      ],
    )..seguimientoDado = _seguimiento();

double _alto(WidgetTester t, Finder f) => t.getTopLeft(f.first).dy;

void main() {
  testWidgets('EN UNA INSTALACIÓN: «Ver el contrato» donde estaba «Cierre de trabajo»',
      (WidgetTester t) async {
    _pantallaAlta(t);
    await t.pumpWidget(_app(_fuente('ftth_instalacion')));
    await t.pumpAndSettle();

    expect(find.text('Cierre de trabajo'), findsNothing);
    expect(find.text('Ver el contrato'), findsOneWidget,
        reason: 'un solo botón: el de arriba se quitó');
    expect(find.textContaining('créalo aquí'), findsNothing);
  });

  testWidgets('EN UNA INSTALACIÓN: los reportes van al final, debajo del contrato',
      (WidgetTester t) async {
    _pantallaAlta(t);
    await t.pumpWidget(_app(_fuente('ftth_instalacion')));
    await t.pumpAndSettle();

    //  No se quitan: «no hay puerto» se reporta como bloqueo con el NOC.
    expect(find.text('Bloqueo'), findsOneWidget);
    expect(_alto(t, find.text('Bloqueo')), greaterThan(_alto(t, find.text('Ver el contrato'))));
    expect(_alto(t, find.text('Bloqueo')), greaterThan(_alto(t, find.text('Datos del trabajo'))),
        reason: 'debajo del formulario, no arriba');
  });

  testWidgets('EN UNA INSTALACIÓN, sin «Cierre de trabajo», lo que falta se sigue nombrando y '
      'Finalizar no cierra', (WidgetTester t) async {
    _pantallaAlta(t);
    final FuenteDeEjecucionFalsa f = _fuente('ftth_instalacion');
    await t.pumpWidget(_app(f));
    await t.pumpAndSettle();

    //  La franja fija de arriba nombra lo que falta: es el mismo veredicto
    //  que tenía el bloque que se quitó.
    expect(find.textContaining('Falta: '), findsOneWidget);
    await t.tap(find.text('Finalizar'));
    await t.pumpAndSettle();
    expect(f.transiciones, isEmpty, reason: 'con obligatorios vacíos no se cierra');
  });

  testWidgets('EL CONTROL: un trabajo que no es instalación queda como estaba',
      (WidgetTester t) async {
    _pantallaAlta(t);
    await t.pumpWidget(_app(_fuente('ftth_correctivo')));
    await t.pumpAndSettle();

    expect(find.text('Cierre de trabajo'), findsOneWidget);
    expect(find.text('Ver el contrato'), findsNothing);
    expect(find.text('Bloqueo'), findsOneWidget);
    expect(_alto(t, find.text('Bloqueo')), lessThan(_alto(t, find.text('Datos del trabajo'))),
        reason: 'en un correctivo los reportes siguen arriba');
  });

  testWidgets('BOTONES POR PASO: «Reportar» solo en su paso y «Ver el contrato» solo en el suyo',
      (WidgetTester t) async {
    //  El usuario: «en cada paso al último siempre sale ver contrato y
    //  reportar». Eligió el contrato en el paso 2 y reportar en el paso 1.
    _pantallaAlta(t);
    await t.pumpWidget(_app(_conBotonesPorPaso()));
    await t.pumpAndSettle();

    expect(find.text('1. Puerto y acceso'), findsOneWidget);
    expect(find.text('Bloqueo'), findsOneWidget);
    expect(find.text('Ver el contrato'), findsNothing);

    await t.tap(find.bySemanticsLabel(RegExp(r'^Paso 2(, completo)?$')));
    await t.pumpAndSettle();
    expect(find.text('Ver el contrato'), findsOneWidget);
    expect(find.text('Bloqueo'), findsNothing);

    await t.tap(find.bySemanticsLabel(RegExp(r'^Paso 3(, completo)?$')));
    await t.pumpAndSettle();
    expect(find.text('Ver el contrato'), findsNothing, reason: 'un paso sin botones no los muestra');
    expect(find.text('Bloqueo'), findsNothing);
    expect(find.text('Cierre de trabajo'), findsNothing);
  });

  testWidgets('EN UNA INSTALACIÓN NO SALE «INICIO»; en un correctivo sí (el control)',
      (WidgetTester t) async {
    _pantallaAlta(t);
    await t.pumpWidget(_app(_fuente('ftth_instalacion')));
    await t.pumpAndSettle();
    expect(find.text('Avance'), findsOneWidget);
    expect(find.text('Inicio'), findsNothing);

    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(_app(_fuente('ftth_correctivo')));
    await t.pumpAndSettle();
    expect(find.text('Inicio'), findsOneWidget);
  });

  testWidgets('LA IP QUE ASIGNÓ EL SISTEMA sale en su paso, se copia y no se edita',
      (WidgetTester t) async {
    //  El usuario: «en el paso 4 debe salir la IP que asignó el sistema, y que
    //  deje copiar pero no modificar».
    _pantallaAlta(t);
    String? copiado;
    t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform,
        (MethodCall llamada) async {
      if (llamada.method == 'Clipboard.setData') {
        copiado = (llamada.arguments as Map<dynamic, dynamic>)['text'] as String?;
      }
      return null;
    });
    addTearDown(() => t.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
    await t.pumpWidget(_app(_conBotonesPorPaso(),
        api: const _ContratoFalso(<String, dynamic>{
          'contrato': <String, dynamic>{'numero': 'C-1', 'ip_elegida': '172.16.30.13'},
        })));
    await t.pumpAndSettle();
    expect(find.text('172.16.30.13'), findsNothing, reason: 'en el paso 1 no va');

    await t.tap(find.bySemanticsLabel(RegExp(r'^Paso 3(, completo)?$')));
    await t.pumpAndSettle();
    expect(find.text('172.16.30.13'), findsOneWidget);
    expect(find.widgetWithText(TextField, '172.16.30.13'), findsNothing, reason: 'no es un campo');
    await t.tap(find.bySemanticsLabel('Copiar la IP'));
    await t.pumpAndSettle();
    expect(copiado, '172.16.30.13');
    expect(find.text('IP 172.16.30.13 copiada'), findsOneWidget);
  });

  testWidgets('sin contrato todavía, o sin señal, lo dice', (WidgetTester t) async {
    _pantallaAlta(t);
    await t.pumpWidget(_app(_conBotonesPorPaso()));
    await t.pumpAndSettle();
    await t.tap(find.bySemanticsLabel(RegExp(r'^Paso 3(, completo)?$')));
    await t.pumpAndSettle();
    expect(find.textContaining('la IP se asigna al crearlo'), findsOneWidget);

    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(_app(_conBotonesPorPaso(),
        api: const _ContratoFalso(null, error: 'sin señal')));
    await t.pumpAndSettle();
    await t.tap(find.bySemanticsLabel(RegExp(r'^Paso 3(, completo)?$')));
    await t.pumpAndSettle();
    expect(find.textContaining('Sin señal'), findsOneWidget);
  });
}
