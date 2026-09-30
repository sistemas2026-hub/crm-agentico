import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';

/// Por qué no hay ficha son TRES casos, no dos.
///
/// El tercero apareció mirando datos REALES de producción: de 100 casos, 4
/// nacieron de una conversación y no tienen servicio asociado. Con datos
/// inventados no se habría visto, porque todos habrían tenido servicio.
///
/// Lo que se afirma es el EFECTO —qué caso devuelve el modelo— y no que el
/// enum exista. Un enum con cuatro valores no prueba que alguien los
/// distinga: antes de esto la tarjeta miraba una sola bandera y le decía
/// «se reintenta al sincronizar» a un caso que no se arregla nunca.
void main() {
  // El contexto viaja como CADENA JSON, que es como lo guarda la base local
  // y como lo manda el servidor. Pasarlo como Map hace que `_mapa` no lo
  // decodifique y devuelva vacio -- la primera version de esta prueba fallaba
  // por eso, no por el codigo.
  TrabajoVista conContexto(Map<String, dynamic> contexto) =>
      TrabajoVista.desdeOrden(<String, dynamic>{
        'id': 'x',
        'numero': 1,
        'estado': 'asignada',
        'contexto_json': jsonEncode(contexto),
      });

  group('por qué falta la ficha del cliente', () {
    test('con ficha, no hay nada que explicar', () {
      final t = conContexto(<String, dynamic>{
        'contexto_disponible': true,
        'cliente': <String, dynamic>{'nombre': 'Quien Sea'},
      });
      expect(t.sinFicha, SinFicha.hayFicha);
    });

    test('el motor no respondió: se reintenta', () {
      final t = conContexto(<String, dynamic>{
        'contexto_disponible': false,
        'motor_alcanzado': false,
        'motivo': 'ConnectionError',
      });
      expect(t.sinFicha, SinFicha.noSePudoConsultar);
    });

    test('respondió y no identificó al cliente: se resuelve en sitio', () {
      final t = conContexto(<String, dynamic>{
        'contexto_disponible': false,
        'motor_alcanzado': true,
        'motivo': 'sin_identidad_resoluble',
      });
      expect(t.sinFicha, SinFicha.clienteNoIdentificado);
    });

    test('el caso no tiene servicio: NO se arregla, y no se confunde con los otros dos', () {
      final t = conContexto(<String, dynamic>{
        'contexto_disponible': false,
        'motor_alcanzado': true,
        'motivo': 'caso_sin_servicio',
      });
      expect(t.sinFicha, SinFicha.casoSinServicio);
      // La distinción que importa: no puede caer en el que promete reintento.
      expect(t.sinFicha, isNot(SinFicha.noSePudoConsultar));
    });

    test('sin contexto ninguno, no se inventa un motivo', () {
      final t = conContexto(<String, dynamic>{});
      // Sin datos, el modelo no afirma que el motor respondió ni que falló:
      // cae al caso genérico y la tarjeta no promete nada que no sepa.
      expect(t.sinFicha, isNot(SinFicha.hayFicha));
    });
  });
}
