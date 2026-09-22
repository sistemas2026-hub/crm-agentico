import 'package:campo/core/mock/field_mock_data.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/core/widgets/dexter_app_header.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:campo/features/trabajo/widgets/tarjeta_trabajo.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// La frontera entre lo real y lo de ejemplo.
///
/// Estas pruebas corren en las dos compilaciones y afirman lo contrario en cada
/// una, así que valen como evidencia de la guarda: si alguien dibujara un dato
/// futuro sin condicionarlo, la corrida normal lo encontraría en pantalla y
/// fallaría.
///
///   flutter test -j 1                                # produccion
///   flutter test -j 1 --dart-define=DEXTER_DEMO=true # demostracion
TrabajoVista _trabajo() => TrabajoVista.desdeOrden(<String, dynamic>{
      'id': 'ot-1',
      'numero': 4832,
      'estado': 'en_sitio',
      'cliente_nombre': 'Carlos Gomez',
      'direccion': 'Cra 45 #12-88',
      'telefono': '',
      'tipo_nombre': 'Instalación FTTH',
      'tipo_codigo': 'ftth_instalacion',
      'schema_version': 1,
      'revision': 1,
      'diagnostico_previo_ia': '',
      'fecha_compromiso': null,
    });

Widget _enApp(Widget hijo) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: SingleChildScrollView(child: hijo)),
    );

void main() {
  group('Guarda del modo demostración', () {
    testWidgets('1. La tarjeta, sin parametro, sigue a DEXTER_DEMO',
        (WidgetTester tester) async {
      // Sin pasar `mostrarDatosFuturos`: es como la construye la aplicacion.
      await tester.pumpWidget(_enApp(TarjetaTrabajo(trabajo: _trabajo())));
      await tester.pumpAndSettle();

      // Lo real se ve siempre.
      expect(find.text('Carlos Gomez'), findsOneWidget);

      if (FieldMockData.modoDemo) {
        // Distancia estimada y telemetria de red: los dos son de ejemplo.
        expect(find.textContaining('km de tu posición'), findsOneWidget);
        expect(find.textContaining('RX: '), findsOneWidget);
        // CAMPO-DATA-029: de qué ticket vino la orden.
        expect(find.textContaining('Derivado de Ticket #'), findsOneWidget);
      } else {
        expect(
          find.textContaining('Derivado de Ticket #'),
          findsNothing,
          reason: 'un ticket de origen inventado se leeria como el real',
        );
        expect(
          find.textContaining('km de tu posición'),
          findsNothing,
          reason: 'en produccion una distancia de ejemplo se leeria como real',
        );
        expect(find.textContaining('RX: '), findsNothing);
        expect(find.textContaining('CTO'), findsNothing);
        expect(find.textContaining('Alerta Dexter'), findsNothing);
      }
    });

    testWidgets('4. El requisito de seguridad y el acta solo salen en demostración',
        (WidgetTester tester) async {
      // Un trabajo que todavía no empezó y que exige trabajar en altura: el
      // requisito se deriva del identificador, así que se busca uno que lo
      // tenga en vez de suponerlo.
      final String id = <String>['ot-2', 'ot-3', 'ot-4', 'ot-5', 'ot-6']
          .firstWhere((String i) => FieldMockData.trabajoFuturo(i).requiereAlturas);

      await tester.pumpWidget(_enApp(TarjetaTrabajo(
        trabajo: TrabajoVista.desdeOrden(<String, dynamic>{
          'id': id,
          'numero': 4835,
          'estado': 'asignada',
          'cliente_nombre': 'Talleres Unidos',
          'direccion': 'Zona Industrial',
          'telefono': '',
          'tipo_nombre': 'Reubicación de acometida',
          'tipo_codigo': 'reubicacion',
          'schema_version': 1,
          'revision': 1,
          'diagnostico_previo_ia': '',
          'fecha_compromiso': null,
        }),
      )));
      await tester.pumpAndSettle();

      if (FieldMockData.modoDemo) {
        expect(find.text(FieldMockData.requisitoSeguridad), findsOneWidget);
        expect(find.text(FieldMockData.aptitudTecnico), findsOneWidget);
      } else {
        expect(
          find.text(FieldMockData.requisitoSeguridad),
          findsNothing,
          reason: 'anunciar una certificación que nadie verificó es peor que callar',
        );
        expect(find.text(FieldMockData.aptitudTecnico), findsNothing);
      }
    });

    testWidgets('2. La campana solo trae numero en demostración',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        const DexterAppHeader(
          empresa: 'Rapilink ISP',
          conexion: EstadoConexion.conRed,
          iniciales: 'CG',
          notificacionesSinLeer: FieldMockData.notificacionesSinLeer,
        ),
      ));
      await tester.pumpAndSettle();

      if (FieldMockData.modoDemo) {
        expect(FieldMockData.notificacionesSinLeer, greaterThan(0));
        expect(find.text('${FieldMockData.notificacionesSinLeer}'), findsOneWidget);
      } else {
        expect(
          FieldMockData.notificacionesSinLeer,
          0,
          reason: 'un numero en la campana se lee como avisos reales sin ver',
        );
        expect(find.text('2'), findsNothing);
      }
    });

    test('3. En producción el interruptor está apagado', () {
      // Comprueba el cableado del propio interruptor: vale lo que diga la
      // bandera de compilacion, y nada mas.
      expect(
        FieldMockData.modoDemo,
        const bool.fromEnvironment('DEXTER_DEMO'),
      );
      expect(
        FieldMockData.notificacionesSinLeer,
        FieldMockData.modoDemo ? 2 : 0,
      );
    });
  });
}
