import 'package:campo/features/ejecucion/datos_de_ejecucion.dart';
import 'package:flutter_test/flutter_test.dart';

/// La foto se toma desde el paso del protocolo.
///
/// EL PROBLEMA
/// -----------
/// El protocolo decía *«3. Medición óptica con power meter»* y la foto se
/// llamaba *«Fotografía de la medición»*. Son lo mismo, y vivían en dos
/// pantallas distintas sin nada que las relacionara: el protocolo en la ficha,
/// las fotos en ejecución. El técnico trabaja siguiendo el protocolo y tenía que
/// acordarse de cuál foto correspondía a cuál paso.
///
/// LO QUE SE DECIDIÓ, Y POR QUÉ ASÍ
/// --------------------------------
/// Que una evidencia pueda declarar `paso` **es opcional y lo decide cada
/// empresa en su plantilla**. Ninguna de las que existen hoy lo declara, y esas
/// se siguen dibujando exactamente igual que antes. Agrupar no puede ser una
/// regla del código: la empresa siguiente arma su protocolo distinto.
void main() {
  List<dynamic> pasos() => <dynamic>[
        <String, dynamic>{'id': 'p1', 'titulo': 'Llegada al inmueble'},
        <String, dynamic>{'id': 'p2', 'titulo': 'Inspección de la roseta'},
        <String, dynamic>{'id': 'p3', 'titulo': 'Medición óptica'},
      ];

  Map<String, dynamic> foto(String id, {String? paso}) => <String, dynamic>{
        'id': id,
        'titulo': id,
        'tipo': 'foto',
        'paso': ?paso,
      };

  group('A · sin pasos declarados, todo sigue igual', () {
    test('a1 · una sola bolsa sin título', () {
      // Es el caso de TODAS las plantillas que existen hoy, medido el
      // 05/10/2026 sobre `ftth_correctivo`: las dos evidencias tienen `paso`
      // en nulo. Esto tiene que dibujarse como antes o se rompe lo que anda.
      final List<GrupoDeEvidencias> g = agruparPorPaso(
        requisitos: <dynamic>[foto('foto_cto'), foto('foto_potencia')],
        pasos: pasos(),
      );

      expect(g.length, 1);
      expect(g.single.titulo, '');
      expect(g.single.requisitos.length, 2);
    });

    test('a2 · sin pasos en la plantilla, tampoco rompe', () {
      final List<GrupoDeEvidencias> g = agruparPorPaso(
        requisitos: <dynamic>[foto('foto_cto')],
        pasos: const <dynamic>[],
      );

      expect(g.length, 1);
      expect(g.single.requisitos.length, 1);
    });
  });

  group('B · con pasos declarados', () {
    test('b1 · cada foto queda bajo el título de SU paso', () {
      final List<GrupoDeEvidencias> g = agruparPorPaso(
        requisitos: <dynamic>[
          foto('foto_potencia', paso: 'p3'),
          foto('foto_roseta', paso: 'p2'),
        ],
        pasos: pasos(),
      );

      expect(g.map((GrupoDeEvidencias x) => x.titulo).toList(),
          <String>['Inspección de la roseta', 'Medición óptica']);
    });

    test('b2 · los grupos salen en el ORDEN DEL PROTOCOLO', () {
      // No en el orden en que la plantilla listó las evidencias. El técnico
      // recorre el protocolo de arriba abajo, y una foto del paso 3 antes que
      // la del paso 1 lo manda a buscar.
      final List<GrupoDeEvidencias> g = agruparPorPaso(
        requisitos: <dynamic>[
          foto('c', paso: 'p3'),
          foto('a', paso: 'p1'),
          foto('b', paso: 'p2'),
        ],
        pasos: pasos(),
      );

      expect(
        g.map((GrupoDeEvidencias x) => x.requisitos.single['id']).toList(),
        <String>['a', 'b', 'c'],
      );
    });

    test('b3 · un paso SIN fotos no se dibuja', () {
      // Un encabezado vacío debajo de otro encabezado vacío convierte la
      // pantalla en una lista de títulos.
      final List<GrupoDeEvidencias> g = agruparPorPaso(
        requisitos: <dynamic>[foto('foto_potencia', paso: 'p3')],
        pasos: pasos(),
      );

      expect(g.length, 1);
      expect(g.single.titulo, 'Medición óptica');
    });

    test('b4 · varias fotos del mismo paso van juntas', () {
      final List<GrupoDeEvidencias> g = agruparPorPaso(
        requisitos: <dynamic>[
          foto('antes', paso: 'p2'),
          foto('despues', paso: 'p2'),
        ],
        pasos: pasos(),
      );

      expect(g.length, 1);
      expect(g.single.requisitos.length, 2);
    });
  });

  group('C · las que no pertenecen a ningún paso', () {
    test('c1 · van al final, juntas y sin encabezado', () {
      // Mezclarlas con las de un paso diría que pertenecen a ese paso. Y la
      // firma del cliente es justamente así: no es de ningún paso.
      final List<GrupoDeEvidencias> g = agruparPorPaso(
        requisitos: <dynamic>[
          foto('firma'),
          foto('foto_potencia', paso: 'p3'),
        ],
        pasos: pasos(),
      );

      expect(g.length, 2);
      expect(g.first.titulo, 'Medición óptica');
      expect(g.last.titulo, '');
      expect(g.last.requisitos.single['id'], 'firma');
    });

    test('c2 · una que apunta a un paso INEXISTENTE no desaparece', () {
      // El backend rechaza publicar una plantilla así, pero una vieja puede
      // tenerlo. Esconder la foto haría que el técnico no sepa que le falta
      // hasta que el botón de cerrar no lo deje, y sin saber por qué.
      final List<GrupoDeEvidencias> g = agruparPorPaso(
        requisitos: <dynamic>[
          foto('huerfana', paso: 'p99'),
          foto('buena', paso: 'p1'),
        ],
        pasos: pasos(),
      );

      final List<String> todas = <String>[
        for (final GrupoDeEvidencias x in g)
          for (final dynamic r in x.requisitos) r['id'] as String,
      ];
      expect(todas, containsAll(<String>['huerfana', 'buena']));
    });

    test('c3 · ninguna evidencia se pierde, nunca', () {
      // La afirmación que cubre todas las demás: agrupar no puede perder una
      // foto. Si se pierde, el técnico cierra la orden sin ella y el supervisor
      // se la devuelve.
      final List<dynamic> entrada = <dynamic>[
        foto('a', paso: 'p1'),
        foto('b', paso: 'p2'),
        foto('c'),
        foto('d', paso: 'p99'),
      ];

      final List<GrupoDeEvidencias> g =
          agruparPorPaso(requisitos: entrada, pasos: pasos());

      final int cuantas = g.fold<int>(
          0, (int n, GrupoDeEvidencias x) => n + x.requisitos.length);
      expect(cuantas, entrada.length);
    });
  });
}
