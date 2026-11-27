/// QUIÉN DECIDE SI UNA ORDEN VA A VALIDACIÓN (27/11/2026).
///
/// En producción la plantilla de instalaciones se llama `traslado_servicio`, y
/// la app lo adivinaba por el código («contiene instalacion»): en la OT-501 el
/// técnico nunca vio el botón para entregar y el ticket no se cerró. Ahora lo
/// dice el servidor; el código de la plantilla solo sirve mientras una orden
/// vieja no se vuelva a leer.
library;

import 'package:campo/features/trabajo/como_se_cierra.dart';
import 'package:campo/features/trabajo/estado_trabajo.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _orden({String codigo = 'traslado_servicio', String? labor, Object? valida}) =>
    <String, dynamic>{
      'id': 'ot-1',
      'estado': 'completada_campo',
      'tipo_codigo': codigo,
      'tipo_nombre': 'Instalación de fibra',
      'labor': labor,
      'valida_una_persona': valida,
      'schema_version': 1,
    };

void main() {
  test('EL SERVIDOR MANDA, aunque el código de la plantilla no diga «instalacion»', () {
    expect(validaUnaPersona(_orden(valida: 1)), isTrue, reason: 'la OT-501');
    expect(validaUnaPersona(_orden(valida: true)), isTrue);
    expect(validaUnaPersona(_orden(codigo: 'ftth_instalacion', labor: 'instalacion', valida: 0)), isFalse,
        reason: 'una empresa que no valida a mano: se finaliza como siempre');
  });

  test('SIN EL DATO (orden bajada antes de la v32): vale si lleva contrato', () {
    expect(validaUnaPersona(_orden(labor: 'instalacion')), isTrue);
    expect(validaUnaPersona(_orden(codigo: 'ftth_instalacion')), isTrue);
    expect(validaUnaPersona(_orden(labor: 'correctivo')), isFalse);
    expect(validaUnaPersona(null), isFalse);
  });

  test('LA FICHA lo lee de la fila de la base, como 1/0', () {
    final TrabajoVista t = TrabajoVista.desdeOrden(_orden(valida: 1));
    expect(t.estado, EstadoTrabajo.completadaCampo);
    expect(t.validaUnaPersona, isTrue);
    expect(TrabajoVista.desdeOrden(_orden(labor: 'correctivo', valida: 0)).validaUnaPersona, isFalse);
  });
}
