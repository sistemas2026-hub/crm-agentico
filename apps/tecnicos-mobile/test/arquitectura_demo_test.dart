import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

/// El núcleo no conoce la demostración.
///
/// POR QUÉ ESTA REGLA
/// ------------------
/// `lib/core/` es lo que cualquier pantalla reutiliza sin leerlo: temas,
/// almacenamiento, cola de sincronización, widgets compartidos. `lib/demo/`
/// son valores de ejemplo de datos que ningún sistema entrega todavía.
///
/// Cuando un widget del núcleo trae adentro un dato de ejemplo, ese dato viaja
/// a toda pantalla que lo use, y quien la escribe no se entera: no lo pasó él.
/// Así estuvo `DexterSyncStrip`, que leía la bandera y el rótulo del modo de
/// trabajo por su cuenta.
///
/// POR QUÉ SE MIDE EL ALCANCE, NO EL IMPORT
/// ----------------------------------------
/// Prohibir la línea `import` sola se esquiva sin querer: basta que un archivo
/// del núcleo importe otro del núcleo que sí importe la demostración, y la
/// dependencia sigue ahí, sólo que a dos saltos. Por eso se sigue la cadena
/// completa: un archivo de `core/` no puede **alcanzar** `demo/` por ningún
/// camino.
///
/// LA LISTA DE FEATURES ES DEUDA, NO PERMISO
/// -----------------------------------------
/// Las pantallas sí pueden mostrar datos de ejemplo mientras el backend no
/// exista —esa es toda la razón de `lib/demo/`—, pero la lista de abajo está
/// escrita a mano para que agregar una pantalla nueva a la demostración sea
/// una decisión visible en el diff, y no algo que pasa solo. Que esta lista se
/// acorte es progreso; que crezca tiene que costar una línea de código.
void main() {
  final Directory lib = Directory(p.join(Directory.current.path, 'lib'));

  /// Las pantallas que hoy dibujan algo de ejemplo detrás de la bandera.
  ///
  /// Cada una tiene su deuda anotada en `docs/campo_datos_pendientes.md`.
  const Set<String> featuresConDemostracion = <String>{
    'features/detalle_orden/detalle_orden_screen.dart',
    'features/ejecucion/ejecucion_screen.dart',
    'features/ejecucion/widgets/bloque_academia.dart',
    'features/ejecucion/widgets/formulario_de_campo.dart',
    'features/materiales/materiales_screen.dart',
    'features/shell/app_shell.dart',
    'features/trabajo/trabajo_screen.dart',
    'features/trabajo/widgets/tarjeta_trabajo.dart',
  };

  /// Todos los `.dart` de `lib/`, con la ruta relativa a `lib/` y con barras
  /// normales: en Windows el separador es otro y las comparaciones fallarían
  /// en una máquina y no en la otra.
  List<String> archivosDeLib() => lib
      .listSync(recursive: true)
      .whereType<File>()
      .where((File f) => f.path.endsWith('.dart'))
      .map((File f) => p.relative(f.path, from: lib.path).replaceAll(r'\', '/'))
      .toList()
    ..sort();

  /// A qué archivos de `lib/` apunta este, por sus imports relativos.
  ///
  /// Los `package:` de terceros y los `dart:` no interesan: la regla es sobre
  /// el código de esta aplicación. Un `package:campo/...` sí se traduce,
  /// porque es la misma carpeta escrita de otra forma.
  Set<String> importaDe(String relativo) {
    final File archivo = File(p.join(lib.path, relativo));
    final RegExp patron = RegExp(
      r'''^\s*(?:import|export)\s+['"]([^'"]+)['"]''',
      multiLine: true,
    );
    final Set<String> destinos = <String>{};

    for (final RegExpMatch m in patron.allMatches(archivo.readAsStringSync())) {
      final String destino = m.group(1)!;
      String? resuelto;

      if (destino.startsWith('package:campo/')) {
        resuelto = destino.substring('package:campo/'.length);
      } else if (!destino.startsWith('package:') && !destino.startsWith('dart:')) {
        resuelto = p
            .normalize(p.join(p.dirname(relativo), destino))
            .replaceAll(r'\', '/');
      }

      if (resuelto != null && File(p.join(lib.path, resuelto)).existsSync()) {
        destinos.add(resuelto);
      }
    }
    return destinos;
  }

  /// Todo lo que este archivo alcanza, directo o a través de otros.
  Set<String> alcanceDe(String origen) {
    final Set<String> vistos = <String>{};
    final List<String> porVer = <String>[origen];

    while (porVer.isNotEmpty) {
      final String actual = porVer.removeLast();
      for (final String destino in importaDe(actual)) {
        if (vistos.add(destino)) porVer.add(destino);
      }
    }
    return vistos;
  }

  bool esDemo(String ruta) => ruta.startsWith('demo/');

  group('El núcleo no depende de la demostración', () {
    test('1. Ningún archivo de core/ importa demo/', () {
      final Map<String, Set<String>> culpables = <String, Set<String>>{};

      for (final String archivo in archivosDeLib()) {
        if (!archivo.startsWith('core/')) continue;
        final Set<String> aDemo = importaDe(archivo).where(esDemo).toSet();
        if (aDemo.isNotEmpty) culpables[archivo] = aDemo;
      }

      expect(
        culpables,
        isEmpty,
        reason: 'core/ es lo que toda pantalla reutiliza sin leerlo: un dato '
            'de ejemplo ahí adentro viaja a todas sin que nadie lo pase.\n'
            'El arreglo es recibirlo por parámetro, como hace DexterSyncStrip '
            'con etiquetaDeModo.\n'
            'Culpables: $culpables',
      );
    });

    test('2. Tampoco lo alcanza a través de otro archivo del núcleo', () {
      // La que de verdad cuida la regla: prohibir solo la línea `import` se
      // esquiva sin querer, poniendo un archivo del núcleo en el medio.
      final Map<String, List<String>> culpables = <String, List<String>>{};

      for (final String archivo in archivosDeLib()) {
        if (!archivo.startsWith('core/')) continue;
        final List<String> aDemo = alcanceDe(archivo).where(esDemo).toList();
        if (aDemo.isNotEmpty) culpables[archivo] = aDemo;
      }

      expect(culpables, isEmpty,
          reason: 'la dependencia sigue estando, solo que a más de un salto: '
              '$culpables');
    });

    test('3. El lector de imports lee de verdad', () {
      // Sin esto, las dos pruebas de arriba pasarían igual si el lector
      // estuviera roto y no viera ningún import: "no encontré nada" y "no hay
      // nada" se ven idénticos desde afuera.
      //
      // El testigo es un import real y que no tiene que ver con la
      // demostración, para que limpiar la demostración no deje ciega a la
      // guarda: `ordenes_jornada` sigue al modelo del trabajo.
      expect(
        importaDe('core/estado/ordenes_jornada.dart'),
        contains('features/trabajo/trabajo_vista.dart'),
        reason: 'si esto falla, el lector dejó de leer y las dos pruebas '
            'anteriores están pasando sin mirar nada',
      );

      // Y que sigue la cadena, no sólo el primer salto.
      expect(
        alcanceDe('core/estado/ordenes_jornada.dart'),
        contains('features/trabajo/estado_trabajo.dart'),
        reason: 'lo alcanza a través del modelo, no directamente',
      );
    });
  });

  group('Las pantallas con demostración están declaradas', () {
    test('4. Ninguna pantalla nueva entra a la demostración sin decirlo', () {
      final Set<String> reales = <String>{
        for (final String archivo in archivosDeLib())
          if (archivo.startsWith('features/') &&
              importaDe(archivo).any(esDemo))
            archivo,
      };

      expect(
        reales.difference(featuresConDemostracion),
        isEmpty,
        reason: 'esta pantalla empezó a mostrar datos de ejemplo. Si es a '
            'propósito, agregala a `featuresConDemostracion` y anotá la deuda '
            'en docs/campo_datos_pendientes.md; si no, sacale el import.',
      );
    });

    test('5. Y la lista no conserva pantallas que ya se limpiaron', () {
      // Una lista de excepciones que no se poda deja de decir la verdad, y
      // entonces nadie la mira.
      final Set<String> reales = <String>{
        for (final String archivo in archivosDeLib())
          if (archivo.startsWith('features/') &&
              importaDe(archivo).any(esDemo))
            archivo,
      };

      expect(
        featuresConDemostracion.difference(reales),
        isEmpty,
        reason: 'estas ya no importan la demostración: sacalas de la lista',
      );
    });

    test('6. Fuera de core/ y features/ nadie más la toca', () {
      final Set<String> intrusos = <String>{
        for (final String archivo in archivosDeLib())
          if (!archivo.startsWith('features/') &&
              !archivo.startsWith('demo/') &&
              importaDe(archivo).any(esDemo))
            archivo,
      };

      expect(intrusos, isEmpty,
          reason: 'main.dart y lo que cuelgue de lib/ tampoco: $intrusos');
    });
  });
}
