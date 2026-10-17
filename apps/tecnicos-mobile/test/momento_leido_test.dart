// ============================================================================
//  LA HORA QUE LLEGA DE AFUERA  --  que no vuelva a correrse cinco horas
// ============================================================================
//
// Estas pruebas afirman sobre el EFECTO: que el mismo instante escrito de dos
// formas no produzca dos horas distintas, y que un instante de ayer no se
// escriba como si fuera de hoy.
//
// Lo que NO se prueba acá a propósito: que exista una función de formato. Una
// prueba que dice que algo existe no prueba que funcione -- en este mismo
// repositorio una afirmó que una variable existiera y sobrevivió intacta a una
// inversión completa de la conducta.

import 'package:flutter_test/flutter_test.dart';
import 'package:campo/core/tiempo/formato_de_momento.dart';
import 'package:campo/core/tiempo/momento_leido.dart';

void main() {
  group('Leer un instante sin inventarle la zona', () {
    test('Con offset, el instante es inequívoco y se puede comparar', () {
      final MomentoLeido? m = MomentoLeido.desde('2026-08-15T18:04:39-05:00');

      expect(m, isNotNull);
      expect(m!.zona, ZonaDelMomento.declarada);
      expect(m.sePuedeComparar, isTrue);
      // El instante real: 18:04 en -05:00 son las 23:04 UTC.
      expect(m.cuando.toUtc().hour, 23);
      expect(m.cuando.toUtc().minute, 4);
    });

    test('Con Z también', () {
      final MomentoLeido? m = MomentoLeido.desde('2026-08-15T23:04:39Z');

      expect(m!.zona, ZonaDelMomento.declarada);
      expect(m.cuando.toUtc().hour, 23);
    });

    test('SIN offset no se compara, y los números quedan como vinieron', () {
      // Este es el caso de SmartOLT (`get_onu_status`). El error de 2026 fue
      // tratarlo como UTC: 18:00 contra 23:0x de la base, y de ahí "fue horas
      // antes" cuando eran cinco minutos.
      final MomentoLeido? m = MomentoLeido.desde('2026-08-15 18:00:25');

      expect(m, isNotNull);
      expect(m!.zona, ZonaDelMomento.ausente);
      expect(m.sePuedeComparar, isFalse);
      // Los números no se movieron: dicen 18:00 y siguen diciendo 18:00.
      expect(m.cuando.hour, 18);
      expect(m.cuando.minute, 0);
    });

    test('Una fecha sola no afirma una medianoche', () {
      final MomentoLeido? m = MomentoLeido.desde('2026-08-15');

      expect(m!.zona, ZonaDelMomento.ausente,
          reason: 'el guión de la fecha NO es un offset');
    });

    test('Vacío, nulo o ilegible no devuelven un instante', () {
      expect(MomentoLeido.desde(null), isNull);
      expect(MomentoLeido.desde(''), isNull);
      expect(MomentoLeido.desde('   '), isNull);
      expect(MomentoLeido.desde('ayer por la tarde'), isNull);
    });
  });

  group('Escribir la hora sin que se pueda leer como otra cosa', () {
    // Un martes cualquiera a las 14:30, hora del dispositivo.
    final DateTime ahora = DateTime(2026, 10, 6, 14, 30);

    test('Lo de hoy dice hoy', () {
      final String texto = textoDelMomentoCrudo(
        '${DateTime(2026, 10, 6, 8, 17).toIso8601String()}Z',
        ahora: ahora,
      );
      // La hora exacta depende de la zona del dispositivo; lo que importa es
      // que se afirme el DIA, que es lo que estaba faltando.
      expect(texto, startsWith('hoy '));
    });

    test('Lo de ayer dice ayer, y NO se escribe como hoy', () {
      final DateTime ayer = ahora.subtract(const Duration(days: 1));
      final MomentoLeido m = MomentoLeido(
        cuando: DateTime(ayer.year, ayer.month, ayer.day, 8, 17),
        zona: ZonaDelMomento.declarada,
      );

      expect(textoDelMomento(m, ahora: ahora), 'ayer 08:17');
    });

    test('Lo de la semana pasada lleva su fecha', () {
      final MomentoLeido m = MomentoLeido(
        cuando: DateTime(2026, 10, 1, 8, 17),
        zona: ZonaDelMomento.declarada,
      );

      expect(textoDelMomento(m, ahora: ahora), '01 oct · 08:17');
    });

    test('UNA HORA SIN ZONA NUNCA DICE hoy NI ayer', () {
      // El caso que importa: el instante cae en el día de hoy según los
      // números, pero no se sabe de qué reloj son. Decir "hoy 18:00" sería
      // afirmar justo lo que no se puede.
      final MomentoLeido m = MomentoLeido(
        cuando: DateTime(2026, 10, 6, 18, 0),
        zona: ZonaDelMomento.ausente,
      );

      final String texto = textoDelMomento(m, ahora: ahora, origen: 'la OLT');

      expect(texto, '06 oct · 18:00 (hora de la OLT)');
      expect(texto, isNot(contains('hoy')));
      expect(texto, isNot(contains('ayer')));
    });

    test('Sin origen declarado, la hora sin zona igual lleva su fecha', () {
      final MomentoLeido m = MomentoLeido(
        cuando: DateTime(2026, 10, 6, 18, 0),
        zona: ZonaDelMomento.ausente,
      );

      expect(textoDelMomento(m, ahora: ahora), '06 oct · 18:00');
    });

    test('Una fecha futura lleva su fecha, no un "hoy" optimista', () {
      // Pasa en campo: el reloj del teléfono atrasado. Lo honesto es la fecha.
      final MomentoLeido m = MomentoLeido(
        cuando: DateTime(2026, 10, 8, 9, 5),
        zona: ZonaDelMomento.declarada,
      );

      expect(textoDelMomento(m, ahora: ahora), '08 oct · 09:05');
    });

    test('Sin nada que escribir devuelve vacío, no un guión', () {
      expect(textoDelMomentoCrudo(null, ahora: ahora), '');
      expect(textoDelMomentoCrudo('', ahora: ahora), '');
    });
  });

  group('El mismo instante, escrito de las dos formas del proveedor', () {
    test('La diferencia de cinco horas se ve, y queda declarada', () {
      // SmartOLT manda el MISMO instante así desde dos endpoints distintos.
      final MomentoLeido conZona =
          MomentoLeido.desde('2026-08-15T18:04:39-05:00')!;
      final MomentoLeido sinZona = MomentoLeido.desde('2026-08-15 18:04:39')!;

      // El de la izquierda sabe qué instante es; el de la derecha no.
      expect(conZona.sePuedeComparar, isTrue);
      expect(sinZona.sePuedeComparar, isFalse);

      // Y por eso uno puede recibir "hoy/ayer" y el otro nunca.
      final DateTime ahora = DateTime(2026, 8, 15, 20, 0);
      expect(textoDelMomento(sinZona, ahora: ahora), isNot(contains('hoy')));
    });
  });
}
