import 'dart:convert';

import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';

/// Por qué una orden no trae datos del equipo, y por qué eso hay que decirlo.
///
/// LO QUE SE MIDIO (02/10/2026)
/// ---------------------------
/// La OT #1844 del laboratorio tiene el `contexto` vacío en la base. En la ficha
/// no se dibujaba nada: ni el serial, ni la telemetría, ni una explicación. El
/// técnico no podía distinguir «no se pudo preguntar» —que mejora
/// sincronizando— de «este caso no tiene servicio» —que no va a mejorar nunca—.
///
/// Los tres casos ya estaban resueltos en [TrabajoVista.sinFicha], leyendo el
/// `motivo` normalizado del backend, y ya se dibujaban en la tarjeta de la
/// lista. La pantalla donde el técnico se para a entender la falla era la única
/// que no los usaba.
///
/// Acá se afirma la clasificación, que es de donde sale el consejo. El consejo
/// cambia con el caso: prometer un reintento donde no lo hay deja a alguien
/// esperando en la calle.
void main() {
  TrabajoVista conContexto(Map<String, dynamic> contexto) {
    return TrabajoVista.desdeOrden(<String, dynamic>{
      'id': 'ot-1',
      'numero': 1844,
      'estado_operativo': 'en_sitio',
      // La clave es la del backend, y viaja como TEXTO: la fila de SQLite
      // guarda el JSON crudo, asi que `TrabajoVista` lo decodifica. Pasar un
      // Map acá haría que se lea como vacío y la prueba mediría otra cosa.
      'contexto_json': jsonEncode(contexto),
    });
  }

  group('Los tres motivos no se confunden', () {
    test('contexto vacío = no se pudo identificar al cliente', () {
      // Es el caso de la OT #1844: el motor contestó y no encontró servicio.
      expect(
        conContexto(<String, dynamic>{}).sinFicha,
        SinFicha.clienteNoIdentificado,
      );
    });

    test('el motor no respondió = se reintenta', () {
      expect(
        conContexto(<String, dynamic>{'motor_alcanzado': false}).sinFicha,
        SinFicha.noSePudoConsultar,
      );
    });

    test('un caso sin servicio NO va a llegar nunca', () {
      // 4 de 100 casos nacen de una conversación. Decirle a ese técnico «se
      // reintenta al sincronizar» es mandarlo a esperar algo que no va a pasar.
      expect(
        conContexto(<String, dynamic>{'motivo': 'caso_sin_servicio'}).sinFicha,
        SinFicha.casoSinServicio,
      );
    });

    test('con contexto disponible no hay nada que explicar', () {
      expect(
        conContexto(<String, dynamic>{'contexto_disponible': true}).sinFicha,
        SinFicha.hayFicha,
      );
    });

    test('«sin servicio» gana sobre «no se pudo consultar»', () {
      // Si llegan los dos, el que decide el consejo es el que cierra la puerta.
      expect(
        conContexto(<String, dynamic>{
          'motivo': 'caso_sin_servicio',
          'motor_alcanzado': false,
        }).sinFicha,
        SinFicha.casoSinServicio,
      );
    });
  });
}
