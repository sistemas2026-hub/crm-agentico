import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/diagnostico_de_campo.dart';
import 'package:flutter_test/flutter_test.dart';

/// LO QUE DICE LO MEDIDO, Y SOBRE TODO LO QUE NO DICE.
///
/// El diagnóstico junta el ping, la potencia y el estado de la ONU para decir
/// QUÉ TRAMO MIRAR PRIMERO. No es un veredicto sobre la falla, y estas pruebas
/// cuidan las dos mitades: que diga lo útil cuando hay con qué, y que se calle
/// cuando no.
///
/// La mitad que se calla es la que importa. Está medido en este proyecto que
/// el ping no es un veredicto —el mismo equipo sano da 1, 2 y 3 de 3 en
/// corridas seguidas— y que una lectura que afirma de más manda a un técnico a
/// revisar un tramo sano.
ResultadoPing ping(int volvieron, int total) => ResultadoPing(
      medido: true,
      respondieron: '$volvieron de $total',
      paquetes: <PaqueteDePing>[
        for (int i = 1; i <= total; i++)
          PaqueteDePing(n: i, respondio: i <= volvieron, rtt: '2ms'),
      ],
    );

void main() {
  group('1. Cuando hay con qué, dice qué tramo mirar', () {
    test('La OLT no lo ve: manda sobre todo lo demás', () {
      // Sin enlace óptico no hay nada que discutir del router, aunque la
      // última señal guardada fuera buena.
      final d = DiagnosticoDeCampo.de(
          veredicto: 'aceptable', estadoOnu: 'Offline', ping: ping(0, 10));

      expect(d.malo, isTrue);
      expect(d.texto, contains('no ve el equipo'));
      expect(d.texto, contains('caja NAP'));
    });

    test('Responde todo y la señal está en rango: descarta el tramo óptico',
        () {
      // Es lo más útil que puede decir esta medición: dónde NO está.
      final d = DiagnosticoDeCampo.de(
          veredicto: 'aceptable', estadoOnu: 'Online', ping: ping(10, 10));

      expect(d.malo, isFalse);
      expect(d.texto, contains('de la caja NAP hacia el equipo'));
    });

    test('La OLT lo ve y no contesta: apunta al equipo, no a la fibra', () {
      final d = DiagnosticoDeCampo.de(
          veredicto: 'aceptable', estadoOnu: 'Online', ping: ping(0, 10));

      expect(d.malo, isTrue);
      expect(d.texto, contains('router del cliente'));
    });

    test('Pierde paquetes: lo dice con el número, sin nombrar la causa', () {
      final d = DiagnosticoDeCampo.de(
          veredicto: 'aceptable', estadoOnu: 'Online', ping: ping(8, 10));

      expect(d.texto, contains('8 de 10'));
      expect(d.texto, contains('caja NAP'));
      expect(d.malo, isTrue);
    });

    test('Responde todo pero la señal está fuera de rango: avisa igual', () {
      // El caso que un ping solo dejaría pasar: hoy contesta y va a volver a
      // fallar.
      final d = DiagnosticoDeCampo.de(
          veredicto: 'fuera_de_rango', estadoOnu: 'Online', ping: ping(10, 10));

      expect(d.malo, isTrue);
      expect(d.texto, contains('va a volver a fallar'));
    });
  });

  group('2. Cuando no hay con qué, se calla', () {
    test('Sin ping no opina del enlace', () {
      final d = DiagnosticoDeCampo.de(
          veredicto: 'aceptable', estadoOnu: 'Online', ping: null);

      expect(d.hayAlgoQueDecir, isFalse);
    });

    test('Sin ping pero con la señal fuera de rango, sí dice eso', () {
      // Habla solo de lo que midió: la señal, que viene en la ficha.
      final d = DiagnosticoDeCampo.de(
          veredicto: 'fuera_de_rango', estadoOnu: 'Online', ping: null);

      expect(d.texto, contains('fuera de rango'));
      expect(d.texto, isNot(contains('paquete')));
    });

    test('Sin ningún dato no inventa nada', () {
      final d = DiagnosticoDeCampo.de(
          veredicto: '', estadoOnu: '', ping: null);

      expect(d.hayAlgoQueDecir, isFalse);
    });

    test('Un ping que no se pudo medir no cuenta como cero', () {
      // "No se pudo preguntar" no es "no respondió". Confundirlos manda a
      // revisar una caja sana.
      final d = DiagnosticoDeCampo.de(
          veredicto: 'aceptable',
          estadoOnu: 'Online',
          ping: ResultadoPing.noSePudo('sin_conexion'));

      expect(d.hayAlgoQueDecir, isFalse);
    });
  });

  group('3. Nunca habla de roseta', () {
    test('El tramo se nombra como lo nombra la operación', () {
      // En Rapilink se dice caja NAP o CTO. 'Roseta' es otro punto de la red y
      // mandaría a mirar donde no es.
      for (final d in <DiagnosticoDeCampo>[
        DiagnosticoDeCampo.de(
            veredicto: 'aceptable', estadoOnu: 'Offline', ping: ping(0, 10)),
        DiagnosticoDeCampo.de(
            veredicto: 'aceptable', estadoOnu: 'Online', ping: ping(10, 10)),
        DiagnosticoDeCampo.de(
            veredicto: 'aceptable', estadoOnu: 'Online', ping: ping(8, 10)),
      ]) {
        expect(d.texto.toLowerCase(), isNot(contains('roseta')));
      }
    });
  });
}
