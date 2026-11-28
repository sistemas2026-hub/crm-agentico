// ============================================================================
//  CAPTURADA NO ES ENVIADA  --  y la pantalla no puede sugerir que sí
// ============================================================================
//
// El contador decía «Fotos cargadas: 2/2» mientras la línea de abajo decía
// «2 capturadas». Dos palabras para dos hechos distintos, y la de arriba era
// la que mentía: «cargada» se lee como que el servidor ya la tiene.
//
// Estas pruebas afirman sobre el EFECTO —que las dos cuentas den distinto
// cuando de verdad son distintas, y que la palabra equivocada no esté en
// ninguna pantalla— no sobre la existencia de un contador.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:campo/features/ejecucion/progreso_evidencias.dart';

/// Una evidencia como la devuelve `cola_evidencias` (todas sus columnas).
Map<String, dynamic> evidencia({
  required int requisitoId,
  required String subidaEstado,
}) {
  return <String, dynamic>{
    'requisito_id': requisitoId,
    'subida_estado': subidaEstado,
  };
}

const List<Map<String, dynamic>> dosRequisitos = <Map<String, dynamic>>[
  <String, dynamic>{'id': 1, 'obligatorio': true},
  <String, dynamic>{'id': 2, 'obligatorio': true},
];

void main() {
  group('Las dos cuentas no son la misma cuenta', () {
    test('Dos fotos tomadas y NINGUNA enviada: 2 y 0', () {
      // El caso de campo: sin red, el técnico tomó todo y nada salió.
      final List<Map<String, dynamic>> capturadas = <Map<String, dynamic>>[
        evidencia(requisitoId: 1, subidaEstado: 'pendiente_registro'),
        evidencia(requisitoId: 2, subidaEstado: 'pendiente_registro'),
      ];

      expect(
        fotosCapturadas(requisitos: dosRequisitos, capturadas: capturadas),
        2,
      );
      expect(fotosEnviadas(capturadas: capturadas), 0);
    });

    test('Una confirmada y una a medio subir: 2 y 1', () {
      // 'subiendo' NO cuenta como enviada: la subida puede fallar, y una foto
      // a mitad de camino no está del otro lado.
      final List<Map<String, dynamic>> capturadas = <Map<String, dynamic>>[
        evidencia(requisitoId: 1, subidaEstado: 'confirmada'),
        evidencia(requisitoId: 2, subidaEstado: 'subiendo'),
      ];

      expect(
        fotosCapturadas(requisitos: dosRequisitos, capturadas: capturadas),
        2,
      );
      expect(fotosEnviadas(capturadas: capturadas), 1);
    });

    test('Todo confirmado: las dos cuentas coinciden', () {
      final List<Map<String, dynamic>> capturadas = <Map<String, dynamic>>[
        evidencia(requisitoId: 1, subidaEstado: 'confirmada'),
        evidencia(requisitoId: 2, subidaEstado: 'confirmada'),
      ];

      expect(
        fotosCapturadas(requisitos: dosRequisitos, capturadas: capturadas),
        2,
      );
      expect(fotosEnviadas(capturadas: capturadas), 2);
    });

    test('Sin la columna, una foto NO se cuenta como enviada', () {
      // Fail-closed: si el dato de subida no llegó, lo que no se puede
      // afirmar es justamente que la empresa ya la tiene.
      final List<Map<String, dynamic>> capturadas = <Map<String, dynamic>>[
        <String, dynamic>{'requisito_id': 1},
      ];

      expect(fotosEnviadas(capturadas: capturadas), 0);
    });

    test('Sin fotos, cero y cero', () {
      expect(fotosEnviadas(capturadas: const <Map<String, dynamic>>[]), 0);
    });
  });

  group('La palabra equivocada no vuelve', () {
    test('Ninguna pantalla dice «cargada» de una foto', () {
      // Se afirma sobre el código fuente a propósito: el defecto era una
      // palabra, y una palabra no se caza con una prueba de comportamiento.
      // Lo que esto impide es que vuelva en otra pantalla.
      //
      // Vale solo para fotos/evidencias: «cargar» es correcto en otros
      // contextos (cargar la configuración, cargar una lista).
      final List<String> ofensores = <String>[];
      final Iterable<File> fuentes = Directory('lib')
          .listSync(recursive: true)
          .whereType<File>()
          .where((File f) => f.path.endsWith('.dart'));

      for (final File fuente in fuentes) {
        final List<String> lineas = fuente.readAsLinesSync();
        for (int i = 0; i < lineas.length; i++) {
          final String linea = lineas[i];
          final String limpia = linea.trimLeft();
          // Los comentarios quedan fuera: este mismo repositorio explica en
          // comentarios cuál era el texto viejo, y una guarda que se caza a
          // sí misma enseña a borrar la explicación, no a no repetir el error.
          if (limpia.startsWith('//') || limpia.startsWith('*')) continue;

          // Se busca sobre UNA línea, así que `[^']*` no puede cruzar nada:
          // el literal empieza y termina en la misma línea, como el texto que
          // el técnico lee en la pantalla.
          for (final RegExpMatch m in RegExp(
            r"'[^']*[Ff]otos?[^']*cargad[ao]s?[^']*'"
            r"|'[^']*cargad[ao]s?[^']*[Ff]otos?[^']*'",
          ).allMatches(linea)) {
            ofensores.add('${fuente.path}:${i + 1} → ${m.group(0)}');
          }
        }
      }

      expect(ofensores, isEmpty,
          reason: 'una foto que solo está en el teléfono no está «cargada»; '
              'decir capturada / enviada');
    });
  });
}
