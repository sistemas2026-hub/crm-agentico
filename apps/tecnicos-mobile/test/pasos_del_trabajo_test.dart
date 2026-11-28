import 'package:campo/features/ejecucion/pasos_del_trabajo.dart';
import 'package:flutter_test/flutter_test.dart';

/// QUÉ SE VE EN CADA PASO DEL TRABAJO (09/11/2026).
///
/// El usuario, sobre la pantalla de ejecución: «si le dan en 1 diagnóstico,
/// que solo le muestre lo que está en diagnóstico; quitar la comprobación de
/// conexión y materiales en esta orden, esos campos que solo salgan en
/// solución».
///
/// Antes esos dos bloques se dibujaban SIEMPRE debajo del paso, así que parado
/// en el paso 1 el técnico veía su diagnóstico y además dos cosas que no le
/// tocan todavía — y el paso dejaba de significar algo, porque igual había que
/// bajar por todo.
void main() {
  group('dónde van los bloques del final', () {
    test('EL DEFECTO: en el primero de varios pasos, NO', () {
      expect(esElPasoDeCierre(indice: 0, total: 3), isFalse);
      expect(esElPasoDeCierre(indice: 1, total: 3), isFalse);
    });

    test('en el último, sí', () {
      expect(esElPasoDeCierre(indice: 2, total: 3), isTrue);
    });

    /// Con un solo paso --o sin pasos-- van ahí: no hay ningún otro lugar, y
    /// esconderlos sería dejar al técnico sin registrar material.
    test('con un solo paso, o sin pasos, van igual', () {
      expect(esElPasoDeCierre(indice: 0, total: 1), isTrue);
      expect(esElPasoDeCierre(indice: 0, total: 0), isTrue);
    });

    /// Un índice fuera de rango no puede esconder los bloques: pasa si la
    /// plantilla cambia mientras el técnico está parado en el último paso.
    test('un índice pasado de largo sigue contando como el final', () {
      expect(esElPasoDeCierre(indice: 5, total: 3), isTrue);
    });
  });

  group('cómo se dibuja cada paso en la línea', () {
    test('donde está parado va en curso, aunque esté completo', () {
      expect(
        estadoDelPaso(indice: 1, actual: 1, completo: true),
        EstadoDelPaso.enCurso,
      );
    });

    /// Lo que importa es si le falta algo, no por dónde anduvo el técnico: un
    /// paso que quedó a medias y se dejó atrás tiene que seguir viéndose
    /// incompleto, o nadie vuelve a él.
    test('uno anterior sin terminar sigue pendiente, no hecho', () {
      expect(
        estadoDelPaso(indice: 0, actual: 2, completo: false),
        EstadoDelPaso.pendiente,
      );
      expect(
        estadoDelPaso(indice: 0, actual: 2, completo: true),
        EstadoDelPaso.hecho,
      );
    });

    test('uno que todavía no se abrió, pero está completo, se ve hecho', () {
      expect(
        estadoDelPaso(indice: 2, actual: 0, completo: true),
        EstadoDelPaso.hecho,
      );
    });
  });

  // ========================================================================
  //  EL RESUMEN DE UN PASO CERRADO  --  14/11/2026
  //
  //  «que muestre lo que está llenado». Un círculo con un número decía que el
  //  técnico pasó por ahí, no qué dejó adentro.
  // ========================================================================
  group('resumenDelPaso', () {
    test('muestra lo lleno, con su etiqueta adelante', () {
      expect(
        resumenDelPaso(
          etiquetas: <String>['Puerto', 'CTO'],
          valores: <String>['7', 'CTO-SOL-114'],
          camposVacios: 0,
          fotosPuestas: 2,
          fotosQueFaltan: 0,
        ),
        'Puerto 7 · CTO CTO-SOL-114 · 2 fotos',
      );
    });

    test('una etiqueta larga se cae: el valor es lo que importa', () {
      //  «Potencia medida en la roseta −20.5 dBm» no entra en un renglón.
      expect(
        resumenDelPaso(
          etiquetas: <String>['Potencia medida en la roseta'],
          valores: <String>['-20.5 dBm'],
          camposVacios: 0,
          fotosPuestas: 0,
          fotosQueFaltan: 0,
        ),
        '-20.5 dBm',
      );
    });

    test('LO QUE FALTA SE NOMBRA, y va al final', () {
      //  Sin esto, un paso a medias que muestre solo lo que tiene se lee como
      //  terminado.
      expect(
        resumenDelPaso(
          etiquetas: <String>['Serial'],
          valores: <String>['HWTC8A3F21B4'],
          camposVacios: 0,
          fotosPuestas: 0,
          fotosQueFaltan: 2,
        ),
        'Serial HWTC8A3F21B4 · faltan 2 fotos',
      );
    });

    test('datos y fotos que faltan se juntan en una frase', () {
      expect(
        resumenDelPaso(
          etiquetas: const <String>[],
          valores: const <String>[],
          camposVacios: 3,
          fotosQueFaltan: 1,
          fotosPuestas: 0,
        ),
        'faltan 3 datos y 1 foto',
      );
    });

    test('singular y plural, en las cuatro cuentas', () {
      expect(
        resumenDelPaso(
          etiquetas: const <String>[],
          valores: const <String>[],
          camposVacios: 1,
          fotosQueFaltan: 0,
          fotosPuestas: 1,
        ),
        '1 foto · faltan 1 dato',
      );
    });

    test('con más de tres valores, los de más se cuentan', () {
      //  Con todos, la línea pasa de un renglón y se corta en cualquier lado.
      expect(
        resumenDelPaso(
          etiquetas: <String>['A', 'B', 'C', 'D', 'E'],
          valores: <String>['1', '2', '3', '4', '5'],
          camposVacios: 0,
          fotosPuestas: 0,
          fotosQueFaltan: 0,
        ),
        'A 1 · B 2 · C 3 · +2',
      );
    });

    test('los vacíos no ocupan lugar ni se cuentan', () {
      expect(
        resumenDelPaso(
          etiquetas: <String>['A', 'B', 'C'],
          valores: <String>['', '  ', 'tres'],
          camposVacios: 2,
          fotosPuestas: 0,
          fotosQueFaltan: 0,
        ),
        'C tres · faltan 2 datos',
      );
    });

    test('un paso que no pide nada no dice nada', () {
      expect(
        resumenDelPaso(
          etiquetas: const <String>[],
          valores: const <String>[],
          camposVacios: 0,
          fotosPuestas: 0,
          fotosQueFaltan: 0,
        ),
        '',
      );
    });

    test('EL CONTROL: el valor se muestra tal cual, no se interpreta', () {
      //  Nada de traducir «true» a «sí» ni redondear: lo que el técnico
      //  escribió es lo que tiene que poder comprobar.
      expect(
        resumenDelPaso(
          etiquetas: <String>['Probado'],
          valores: <String>['true'],
          camposVacios: 0,
          fotosPuestas: 0,
          fotosQueFaltan: 0,
        ),
        'Probado true',
      );
    });
  });
}
