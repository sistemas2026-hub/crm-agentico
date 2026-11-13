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
}
