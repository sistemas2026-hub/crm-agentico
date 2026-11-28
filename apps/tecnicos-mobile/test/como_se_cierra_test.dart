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

  //  27/11/2026: enviada a validación no está terminada hasta finalizarla.
  test('LA QUE FALTA FINALIZAR no cuenta como terminada ni va a «Finalizadas»', () {
    final TrabajoVista enValidacion = TrabajoVista.desdeOrden(
        <String, dynamic>{..._orden(valida: 1), 'estado_validacion': 'pendiente'});
    final TrabajoVista aprobada = TrabajoVista.desdeOrden(
        <String, dynamic>{..._orden(valida: 1), 'estado_validacion': 'aprobado'});
    final TrabajoVista otra = TrabajoVista.desdeOrden(_orden(labor: 'correctivo', valida: 0));

    expect(enValidacion.faltaFinalizar && !enValidacion.terminada, isTrue);
    expect(enValidacion.leTocaAlTecnico, isFalse, reason: 'mientras la revisan, espera');
    expect(enValidacion.etiquetaDeEstado, 'En validación');
    expect(aprobada.leTocaAlTecnico, isTrue, reason: 'aprobada, le toca finalizarla');
    expect(aprobada.etiquetaDeEstado, 'Aprobada · falta finalizar');
    expect(otra.faltaFinalizar || !otra.terminada, isFalse, reason: 'una completada común sí terminó');

    final DateTime ahora = DateTime(2026, 11, 27);
    expect(perteneceA(PestanaTrabajo.finalizadas, aprobada.estado, null, ahora: ahora,
        faltaFinalizar: aprobada.faltaFinalizar), isFalse);
    expect(perteneceA(PestanaTrabajo.enProceso, aprobada.estado, null, ahora: ahora,
        faltaFinalizar: aprobada.faltaFinalizar), isTrue);
    expect(perteneceA(PestanaTrabajo.finalizadas, otra.estado, null, ahora: ahora,
        faltaFinalizar: otra.faltaFinalizar), isTrue);
  });
}
