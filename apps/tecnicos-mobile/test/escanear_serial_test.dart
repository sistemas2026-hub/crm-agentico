import 'package:campo/core/acciones/lector_de_codigo.dart';
import 'package:flutter_test/flutter_test.dart';

/// Comparar dos seriales, que es lo que decide si el técnico confía en el lector.
///
/// POR QUÉ ESTA COMPARACIÓN NO ES `==`
/// -----------------------------------
/// El mismo equipo aparece escrito de tres formas en el mismo día:
///
///   la etiqueta         ZTEG-C0A1B2C3
///   lo que cargó bodega zteg c0a1b2c3
///   el código de barras ZTEGC0A1B2C3
///
/// Con `==` las tres son equipos distintos, y la app le dice al técnico que
/// trajo el equipo equivocado teniendo el correcto en la mano. La primera vez lo
/// vuelve a escanear; la segunda deja de usar el lector y sigue comparando a
/// ojo — que es exactamente lo que el lector vino a evitar.
///
/// Y EL ERROR OPUESTO ES PEOR
/// --------------------------
/// Aflojar la comparación hasta que *casi* todo coincida hace que diga que sí
/// siempre. Un serial que **contiene** a otro no es el mismo equipo: se instala
/// una ONT que no es, queda registrada la que no es, y el problema aparece
/// cuando alguien va a buscar ese equipo y no está donde dice el sistema.
///
/// Las dos direcciones se miden acá.
void main() {
  group('A · el mismo equipo escrito distinto', () {
    test('a1 · guiones, espacios y mayúsculas no hacen otro equipo', () {
      const String enLaTarjeta = 'ZTEG-C0A1B2C3';
      for (final String leido in <String>[
        'ZTEG-C0A1B2C3',
        'zteg-c0a1b2c3',
        'ZTEG C0A1B2C3',
        'ZTEGC0A1B2C3',
        '  zteg_c0a1b2c3  ',
        'ZTEG.C0A1B2C3',
      ]) {
        expect(mismoSerial(enLaTarjeta, leido), isTrue, reason: leido);
      }
    });

    test('a2 · da igual cuál de los dos venga del lector', () {
      expect(mismoSerial('ZTEGC0A1B2C3', 'zteg-c0a1b2c3'), isTrue);
      expect(mismoSerial('zteg-c0a1b2c3', 'ZTEGC0A1B2C3'), isTrue);
    });
  });

  group('B · equipos que NO son el mismo', () {
    test('b1 · un carácter distinto es otro equipo', () {
      // El caso que el lector vino a cazar: el técnico tipeó un 8 donde iba un B.
      expect(mismoSerial('ZTEGC0A1B2C3', 'ZTEGC0A1B2C8'), isFalse);
    });

    test('b2 · un serial que CONTIENE al otro no es el mismo', () {
      // La trampa de aflojar: con `contains` esto diría que sí, y el técnico
      // instalaría el equipo equivocado con la app diciéndole que está bien.
      expect(mismoSerial('ZTEGC0A1B2C3', 'ZTEGC0A1B2C'), isFalse);
      expect(mismoSerial('ZTEGC0A1B2C', 'ZTEGC0A1B2C3'), isFalse);
      expect(mismoSerial('C0A1B2C3', 'ZTEGC0A1B2C3'), isFalse);
    });

    test('b3 · el orden importa: no se comparan como conjuntos', () {
      expect(mismoSerial('ZTEGC0A1B2C3', 'ZTEGC0A1B23C'), isFalse);
    });
  });

  group('C · cuando no hay nada que comparar', () {
    test('c1 · un lado vacío NUNCA coincide', () {
      // Si coincidiera, una tarjeta sin serial cargado daría «coincide» con
      // cualquier cosa que se escanee. Es el falso positivo más barato de
      // producir y el más caro de detectar.
      expect(mismoSerial('', 'ZTEGC0A1B2C3'), isFalse);
      expect(mismoSerial('ZTEGC0A1B2C3', ''), isFalse);
      expect(mismoSerial('', ''), isFalse);
    });

    test('c2 · un lado solo con separadores tampoco coincide', () {
      // `---` y `   ` se normalizan a vacío. Sin la guarda de c1, dos cadenas
      // de guiones serían «el mismo equipo».
      expect(mismoSerial('---', '   '), isFalse);
      expect(mismoSerial('- -', 'ZTEGC0A1B2C3'), isFalse);
    });
  });
}
