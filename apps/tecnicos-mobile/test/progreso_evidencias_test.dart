import 'package:campo/features/ejecucion/progreso_evidencias.dart';
import 'package:flutter_test/flutter_test.dart';

/// La cuenta de fotos de una orden.
///
/// Importa por dos cosas que el técnico ve antes de cerrar: el contador de
/// arriba ("2/3") y qué requisito queda marcado en rojo. Si la cuenta se
/// equivoca, o cierra una orden a la que le falta una foto obligatoria, o
/// marca como pendiente algo que ya se tomó y lo manda a repetir un trabajo.
List<dynamic> _requisitos() => <dynamic>[
      <String, dynamic>{'id': 'r1', 'descripcion': 'Roseta instalada', 'obligatorio': true},
      <String, dynamic>{'id': 'r2', 'descripcion': 'Caja CTO', 'obligatorio': true},
      <String, dynamic>{'id': 'r3', 'descripcion': 'Fachada', 'obligatorio': false},
    ];

Map<String, dynamic> _foto(String requisitoId) => <String, dynamic>{
      'requisito_id': requisitoId,
      'archivo_path': '/tmp/$requisitoId.jpg',
    };

void main() {
  group('Progreso de la evidencia fotográfica', () {
    test('1. Sin fotos, todos los requisitos están pendientes', () {
      final List<dynamic> reqs = _requisitos();
      expect(
        fotosCapturadas(requisitos: reqs, capturadas: <Map<String, dynamic>>[]),
        0,
      );
      expect(
        requisitosPendientes(requisitos: reqs, capturadas: <Map<String, dynamic>>[])
            .length,
        3,
      );
      expect(
        faltaEvidenciaObligatoria(
          requisitos: reqs,
          capturadas: <Map<String, dynamic>>[],
        ),
        isTrue,
      );
    });

    test('2. Una foto cuenta solo para su propio requisito', () {
      final List<dynamic> reqs = _requisitos();
      final capturadas = <Map<String, dynamic>>[_foto('r1')];

      expect(fotosCapturadas(requisitos: reqs, capturadas: capturadas), 1);
      expect(
        requisitosPendientes(requisitos: reqs, capturadas: capturadas)
            .map((Map<String, dynamic> r) => r['id']),
        <String>['r2', 'r3'],
        reason: 'una foto de la roseta no cubre la de la CTO',
      );
    });

    test('3. Tres fotos del mismo requisito siguen siendo un requisito', () {
      final List<dynamic> reqs = _requisitos();
      final capturadas = <Map<String, dynamic>>[
        _foto('r1'),
        _foto('r1'),
        _foto('r1'),
      ];

      expect(
        fotosCapturadas(requisitos: reqs, capturadas: capturadas),
        1,
        reason: 'el contador cuenta requisitos cubiertos, no archivos',
      );
    });

    test('4. Lo opcional no bloquea el cierre; lo obligatorio sí', () {
      final List<dynamic> reqs = _requisitos();

      // Faltan las dos obligatorias.
      expect(
        faltaEvidenciaObligatoria(
          requisitos: reqs,
          capturadas: <Map<String, dynamic>>[_foto('r3')],
        ),
        isTrue,
      );

      // Están las dos obligatorias y falta la opcional.
      expect(
        faltaEvidenciaObligatoria(
          requisitos: reqs,
          capturadas: <Map<String, dynamic>>[_foto('r1'), _foto('r2')],
        ),
        isFalse,
      );
    });

    test('5. Una evidencia de un requisito que ya no existe no infla la cuenta', () {
      final List<dynamic> reqs = _requisitos();
      // El backend cambió el formulario y esta foto quedó huérfana.
      final capturadas = <Map<String, dynamic>>[_foto('r1'), _foto('viejo')];

      expect(fotosCapturadas(requisitos: reqs, capturadas: capturadas), 1);
    });

    test('6. Sin requisitos no hay nada pendiente ni nada que contar', () {
      expect(
        fotosCapturadas(
          requisitos: const <dynamic>[],
          capturadas: <Map<String, dynamic>>[_foto('r1')],
        ),
        0,
      );
      expect(
        faltaEvidenciaObligatoria(
          requisitos: const <dynamic>[],
          capturadas: <Map<String, dynamic>>[],
        ),
        isFalse,
      );
    });
  });
}
