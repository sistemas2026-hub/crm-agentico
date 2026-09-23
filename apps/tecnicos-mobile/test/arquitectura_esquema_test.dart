import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

/// El esquema del formulario dinámico se interpreta en un solo lugar.
///
/// POR QUÉ ESTA GUARDA
/// -------------------
/// Porque el mismo defecto apareció **cinco veces**, y ninguna la encontró una
/// prueba: las cinco salieron de mirar una captura.
///
/// El esquema llega del servidor como JSON y cada componente lo leía a su
/// manera. El formulario aceptaba `id` y `reglas.required`; la validación de
/// cierre sólo `clave` y `obligatorio`; el botón Finalizar tenía una tercera
/// versión; los controladores de texto una cuarta. Resultado en un teléfono
/// real: la pantalla pintaba el asterisco rojo, el checklist no exigía el
/// campo, y el botón cerraba una orden con los obligatorios vacíos. Un campo
/// de selección salía sin opciones para elegir.
///
/// Ninguna de esas lecturas estaba mal escrita. El problema era que existieran
/// varias: cada cambio de esquema las desincroniza otra vez.
///
/// QUÉ MIDE
/// --------
/// Que nadie vuelva a leer el JSON del esquema por su cuenta. Lo único que
/// puede hacerlo es `campo_del_formulario.dart`; el resto consume el modelo.
///
/// Es una guarda sobre el texto del código, y eso acá está bien: lo que se
/// vigila **es** cómo se escribe el acceso. Igual lleva una prueba que le
/// mete una infracción artificial, porque un detector que no detecta pasa
/// igual que uno que no encuentra nada.
void main() {
  final Directory lib = Directory(p.join(Directory.current.path, 'lib'));

  /// El que puede leer el JSON crudo. Es su trabajo.
  const String normalizador = 'features/ejecucion/campo_del_formulario.dart';

  /// Claves que sólo existen en el esquema de **campos**. Verlas en cualquier
  /// otro lado significa que alguien lo está interpretando de nuevo.
  const List<String> clavesDeCampo = <String>[
    "['reglas']",
    "['options']",
    "['opciones']",
    "['required']",
  ];

  /// Claves ambiguas: también aparecen en el esquema de evidencias y en el de
  /// pasos, que son otros. Se vigilan sólo donde vive el formulario.
  const List<String> clavesAmbiguas = <String>["['clave']", "['tipo']"];

  /// Archivos que leen OTRO esquema —el de evidencias— y por eso siguen
  /// tocando claves parecidas.
  ///
  /// Es deuda, no permiso: las evidencias merecen su propio modelo normalizado
  /// por las mismas razones que los campos. Mientras no exista, estos tres
  /// están declarados a mano para que sumar un cuarto cueste una línea visible
  /// en el diff.
  const Set<String> leenElEsquemaDeEvidencias = <String>{
    'features/ejecucion/cierre_de_orden.dart',
    'features/ejecucion/datos_de_ejecucion.dart',
    'features/ejecucion/ejecucion_screen.dart',
    'features/ejecucion/progreso_evidencias.dart',
  };

  List<String> archivosDeLib() => lib
      .listSync(recursive: true)
      .whereType<File>()
      .where((File f) => f.path.endsWith('.dart'))
      .map((File f) => p.relative(f.path, from: lib.path).replaceAll(r'\', '/'))
      .toList()
    ..sort();

  /// Las líneas de un archivo que contienen alguna de estas claves.
  ///
  /// Se ignoran comentarios: explicar el defecto en la documentación —cosa que
  /// estos archivos hacen bastante— no es cometerlo.
  List<String> lineasCon(String relativo, List<String> claves, String texto) {
    final List<String> encontradas = <String>[];
    final List<String> lineas = texto.split('\n');

    for (var i = 0; i < lineas.length; i++) {
      final String linea = lineas[i];
      final String sinEspacios = linea.trimLeft();
      if (sinEspacios.startsWith('//') || sinEspacios.startsWith('///')) {
        continue;
      }
      for (final String clave in claves) {
        if (linea.contains(clave)) {
          encontradas.add('$relativo:${i + 1}  ${linea.trim()}');
          break;
        }
      }
    }
    return encontradas;
  }

  String leer(String relativo) =>
      File(p.join(lib.path, relativo)).readAsStringSync();

  group('El esquema de campos se lee en un solo lugar', () {
    test('1. Nadie más toca reglas, options, opciones ni required', () {
      final List<String> infracciones = <String>[];

      for (final String archivo in archivosDeLib()) {
        if (archivo == normalizador) continue;
        infracciones.addAll(lineasCon(archivo, clavesDeCampo, leer(archivo)));
      }

      expect(
        infracciones,
        isEmpty,
        reason: 'estas claves son del esquema del formulario y sólo las lee '
            '`CampoDelFormulario`. Si necesitás el dato, pedíselo al modelo: '
            'tiene id, titulo, tipo, obligatorio, opciones, valor y estado.\n'
            '${infracciones.join('\n')}',
      );
    });

    test('2. Dentro de ejecución tampoco se leen clave ni tipo a mano', () {
      final List<String> infracciones = <String>[];

      for (final String archivo in archivosDeLib()) {
        if (archivo == normalizador) continue;
        if (!archivo.startsWith('features/ejecucion/')) continue;
        if (leenElEsquemaDeEvidencias.contains(archivo)) continue;
        infracciones.addAll(lineasCon(archivo, clavesAmbiguas, leer(archivo)));
      }

      expect(infracciones, isEmpty,
          reason: 'lo mismo: el modelo ya trae `id` y `tipo`.\n'
              '${infracciones.join('\n')}');
    });

    test('3. La lista de excepciones no guarda archivos ya limpios', () {
      // Una lista de excepciones que no se poda deja de decir la verdad, y
      // entonces nadie la mira.
      final Set<String> sucios = <String>{
        for (final String archivo in leenElEsquemaDeEvidencias)
          if (lineasCon(
            archivo,
            <String>[
              "['obligatorio']",
              "['descripcion']",
              "['titulo']",
              "['tipo']",
            ],
            leer(archivo),
          ).isNotEmpty)
            archivo,
      };

      expect(
        leenElEsquemaDeEvidencias.difference(sucios),
        isEmpty,
        reason: 'estos ya no leen el esquema de evidencias: sacalos de la '
            'lista para que siga diciendo la verdad',
      );
    });
  });

  group('La guarda sabe encontrar una infracción', () {
    test('4. Detecta una lectura prohibida metida a propósito', () {
      // Sin esto, las pruebas de arriba pasarían igual con el detector roto:
      // "no encontré nada" y "no hay nada" se ven idénticos desde afuera.
      const String codigoMalo = '''
class PantallaNueva {
  String titulo(Map<String, dynamic> campo) {
    final reglas = campo['reglas'];
    if (reglas['required'] == true) return 'obligatorio';
    return campo['opciones'].first.toString();
  }
}
''';

      final List<String> encontradas =
          lineasCon('inventado.dart', clavesDeCampo, codigoMalo);

      expect(encontradas, hasLength(3),
          reason: 'reglas, required y opciones, una por línea');
    });

    test('5. No se confunde con un comentario que las nombra', () {
      // Estos archivos explican el defecto en su documentación. Contarlo como
      // infracción obligaría a no poder escribir por qué existe la regla.
      const String soloComentarios = '''
/// El servidor manda campo['reglas']['required'] y no campo['obligatorio'].
// Antes se leía campo['opciones'], que nadie manda.
class Limpia {}
''';

      expect(
        lineasCon('inventado.dart', clavesDeCampo, soloComentarios),
        isEmpty,
      );
    });

    test('6. El normalizador sí las usa, y por eso está exceptuado', () {
      // Si esto saliera vacío, la excepción estaría de más y las pruebas 1 y 2
      // estarían pasando por mirar un archivo que no hace lo que creemos.
      expect(
        lineasCon(normalizador, clavesDeCampo, leer(normalizador)),
        isNotEmpty,
        reason: 'campo_del_formulario.dart es el que interpreta el JSON',
      );
    });
  });
}
