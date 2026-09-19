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
        expect(find.textContaining('SLA'), findsOneWidget);
        expect(find.textContaining('km'), findsOneWidget);
      } else {
        expect(
          find.textContaining('SLA'),
          findsNothing,
          reason: 'en produccion un SLA de ejemplo se leeria como el real',
        );
        expect(find.textContaining('km'), findsNothing);
        expect(find.textContaining('Urbano'), findsNothing);
        expect(find.text('Alta'), findsNothing);
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
