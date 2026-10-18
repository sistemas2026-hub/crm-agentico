/// LA FICHA EN EL PASO 3 (18/10/2026), pedidos del usuario pantalla por
/// pantalla:
///
///   A  el seguimiento dice la FECHA de cada evento, no solo la hora, y se lee
///      como línea de tiempo: agrupado por día y lo más nuevo arriba
///   B  las visitas anteriores traen los tickets del servicio en el sistema del
///      ISP, que es la historia real; sin asunto, que trae nombres a mano
library;

import 'package:campo/features/detalle_orden/seguimiento_de_la_intervencion.dart';
import 'package:campo/features/detalle_orden/visitas_anteriores.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _montar(WidgetTester t, Widget w) async {
  t.view.physicalSize = const Size(1000, 3000);
  t.view.devicePixelRatio = 1.0;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
  await t.pumpWidget(MaterialApp(
    home: Scaffold(body: SingleChildScrollView(child: w)),
  ));
  await t.pumpAndSettle();
}

Map<String, dynamic> _evento(String etiqueta, DateTime cuando) => <String, dynamic>{
      'id': etiqueta,
      'tipo': etiqueta.toLowerCase(),
      'etiqueta': etiqueta,
      'severidad': 'info',
      'recibido_en': cuando.toUtc().toIso8601String(),
      'detalle': <dynamic>[],
    };

String _fecha(DateTime d) =>
    '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';

void main() {
  group('A · la línea de tiempo', () {
    testWidgets('cada día con su fecha, la hora al lado, y lo último arriba',
        (WidgetTester t) async {
      final DateTime ahora = DateTime.now();
      final DateTime hoy = DateTime(ahora.year, ahora.month, ahora.day, 9, 5);
      final DateTime ayer = hoy.subtract(const Duration(days: 1));
      final DateTime antes = hoy.subtract(const Duration(days: 5));

      await _montar(t, SeguimientoDeLaIntervencion(
        cargando: false,
        seguimiento: <String, dynamic>{
          // El servidor los manda del más viejo al más nuevo.
          'eventos': <dynamic>[
            _evento('Asignada', antes),
            _evento('Inicio', ayer),
            _evento('Avance', hoy),
          ],
        },
      ));

      expect(find.text('HOY · ${_fecha(hoy)}'), findsOneWidget);
      expect(find.text('AYER · ${_fecha(ayer)}'), findsOneWidget);
      expect(find.text(_fecha(antes)), findsOneWidget);
      expect(find.text('09:05'), findsWidgets);

      // Lo más nuevo arriba.
      final double yAvance = t.getTopLeft(find.text('AVANCE')).dy;
      final double yInicio = t.getTopLeft(find.text('INICIO')).dy;
      final double yAsignada = t.getTopLeft(find.text('ASIGNADA')).dy;
      expect(yAvance < yInicio && yInicio < yAsignada, isTrue);
    });
  });

  group('B · la historia del servicio', () {
    testWidgets('con tickets y sin visitas de campo, NO dice «primera visita»',
        (WidgetTester t) async {
      await _montar(t, const VisitasAnteriores(historial: <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[],
        'tickets': <dynamic>[
          <String, dynamic>{
            'numero': '95001',
            'abierto_en': '2026-09-12T15:00:00+00:00',
            'cerrado_en': '2026-09-14T15:00:00+00:00',
            'estado': 'cerrado',
            'area': 'soporte_tecnico',
          },
          <String, dynamic>{
            'numero': '95218',
            'abierto_en': '2026-10-16T15:00:00+00:00',
            'cerrado_en': null,
            'estado': 'abierto',
            'area': '',
          },
        ],
      }));

      expect(find.textContaining('primera visita'), findsNothing);
      expect(find.text('Ticket #95001'), findsOneWidget);
      expect(find.text('Ticket #95218'), findsOneWidget);
      expect(find.textContaining('Abierto el 12/09/2026'), findsOneWidget);
      expect(find.textContaining('cerrado el 14/09/2026'), findsOneWidget);
      expect(find.textContaining('soporte tecnico'), findsOneWidget);
      expect(find.text('ABIERTO'), findsOneWidget);
    });

    testWidgets('sin visitas ni tickets, sí es la primera vez', (WidgetTester t) async {
      await _montar(t, const VisitasAnteriores(historial: <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[],
        'tickets': <dynamic>[],
      }));
      expect(find.textContaining('Es la primera visita'), findsOneWidget);
    });
  });
}
