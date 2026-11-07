import 'package:campo/demo/field_mock_data.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';

/// Lo que decide la oficina, ya en el teléfono.
///
/// La tanda 2 agregó ocho datos que la orden no sabía decir y la aplicación
/// dibujaba de ejemplo. Lo que estas pruebas cuidan es la regla que ordena las
/// dos fuentes: **lo real le gana al ejemplo, y lo que no se sabe no se
/// inventa**. Un SLA calculado a ojo o una franja supuesta son peores que no
/// mostrar nada, porque el técnico los usa para decidir a dónde va primero.
TrabajoVista _trabajo(Map<String, dynamic> extra) => TrabajoVista.desdeOrden(<String, dynamic>{
      'id': 'ot-1',
      'numero': 4832,
      'estado': 'asignada',
      'cliente_nombre': 'Carlos Gomez',
      'direccion': 'Cra 45 #12-88',
      'telefono': '',
      'tipo_nombre': 'Instalación FTTH',
      'tipo_codigo': 'ftth_instalacion',
      'schema_version': 1,
      'revision': 1,
      'diagnostico_previo_ia': '',
      'fecha_compromiso': null,
      ...extra,
    });

void main() {
  group('Los datos del despacho', () {
    test('1. Llegan al modelo tal como los manda el servidor', () {
      final t = _trabajo(<String, dynamic>{
        'prioridad': 'alta',
        'zona': 'Industrial Sur',
        'resumen': 'Reubicación de acometida',
        'detalle_acceso': 'Galpón 3',
        'id_abonado': 'WH-10984214',
        'requisitos_seguridad_json': '["trabajo_en_altura"]',
      });

      expect(t.prioridad, 'alta');
      expect(t.zona, 'Industrial Sur');
      expect(t.resumen, 'Reubicación de acometida');
      expect(t.detalleAcceso, 'Galpón 3');
      expect(t.idAbonado, 'WH-10984214');
      expect(t.requisitosSeguridad, <String>['trabajo_en_altura']);
    });

    test('2. Una orden vieja, sin nada de esto, sigue siendo válida', () {
      final t = _trabajo(const <String, dynamic>{});

      expect(t.prioridad, '');
      expect(t.zona, '');
      expect(t.requisitosSeguridad, isEmpty);
      expect(t.ventanaTexto, '');
      // Y lo que sí tenía sigue en su lugar.
      expect(t.clienteNombre, 'Carlos Gomez');
    });

    test('3. La franja prometida se escribe como la lee el técnico', () {
      final t = _trabajo(<String, dynamic>{
        'ventana_inicio': '2026-09-22T09:30:00',
        'ventana_fin': '2026-09-22T11:00:00',
      });

      expect(t.ventanaTexto, '09:30 - 11:00');
    });

    test('4. Sin franja no se inventa una', () {
      expect(_trabajo(const <String, dynamic>{}).ventanaTexto, '');
      // Con una sola de las dos puntas tampoco: media franja no es una franja.
      expect(
        _trabajo(<String, dynamic>{'ventana_inicio': '2026-09-22T09:30:00'}).ventanaTexto,
        '',
      );
    });

    test('5. El SLA se cuenta contra la fecha del servidor', () {
      final DateTime ahora = DateTime(2026, 9, 22, 10, 00);
      final t = _trabajo(<String, dynamic>{
        'sla_vence_en': '2026-09-22T10:45:00',
      });

      expect(t.minutosParaVencer(ahora: ahora), 45);
      expect(t.vencido(ahora: ahora), isFalse);
    });

    test('6. Un compromiso que ya pasó se dice vencido', () {
      final DateTime ahora = DateTime(2026, 9, 22, 12, 00);
      final t = _trabajo(<String, dynamic>{
        'sla_vence_en': '2026-09-22T10:45:00',
      });

      expect(t.minutosParaVencer(ahora: ahora), lessThan(0));
      expect(t.vencido(ahora: ahora), isTrue);
    });

    test('7. Sin fecha de vencimiento no se calcula ni se afirma nada', () {
      final t = _trabajo(const <String, dynamic>{});

      expect(
        t.minutosParaVencer(),
        isNull,
        reason: 'el teléfono no conoce las reglas de SLA de la empresa',
      );
      expect(
        t.vencido(),
        isFalse,
        reason: 'afirmar que algo venció sin saberlo es peor que callar',
      );
    });

    test('8. Los requisitos de seguridad son los del servidor, no los de ejemplo', () {
      final t = _trabajo(<String, dynamic>{
        'requisitos_seguridad_json': '["espacios_confinados","certificacion_electrica"]',
      });

      expect(t.requisitosSeguridad.length, 2);
      // El texto de ejemplo del catálogo no se mezcla con lo real.
      expect(t.requisitosSeguridad, isNot(contains(FieldMockData.requisitoSeguridad)));
    });

    test('10. El ticket de origen real gana sobre el de ejemplo', () {
      final real = _trabajo(<String, dynamic>{
        'origen_json': '{"sistema":"wisphub","tipo":"ticket","ref":"WH-91288"}',
      });
      expect(real.origen!.etiqueta, 'Ticket WH-91288');

      // Una orden creada a mano no viene de ningún lado: no se le inventa un
      // origen.
      final manual = _trabajo(<String, dynamic>{
        'origen_json': '{"sistema":"manual","tipo":"","ref":""}',
      });
      expect(manual.origen, isNull);
    });

    test('9. Un JSON roto no rompe la pantalla: se lee como vacío', () {
      final t = _trabajo(<String, dynamic>{
        'requisitos_seguridad_json': '{esto no es json',
      });

      expect(t.requisitosSeguridad, isEmpty);
    });
  });
}
