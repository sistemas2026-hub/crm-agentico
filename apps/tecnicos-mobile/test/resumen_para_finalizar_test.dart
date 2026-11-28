import 'package:campo/features/ejecucion/campo_del_formulario.dart';
import 'package:campo/features/ejecucion/resumen_para_finalizar.dart';
import 'package:flutter_test/flutter_test.dart';

/// EL RESUMEN QUE SE REVISA ANTES DE FINALIZAR (09/11/2026).
///
/// El usuario: «para cerrar el caso debería mostrar mejor un resumen de lo
/// realizado, y así el técnico revisa el resumen y corrige o finaliza si está
/// todo bien».
///
/// Lo que estas pruebas cuidan es lo que pasa si el resumen MIENTE POR
/// OMISIÓN: el técnico aprueba un trabajo mirando algo que no incluía lo que
/// él cargó. Por eso casi todas miran el lado de «esto tiene que aparecer».
CampoDelFormulario campo({
  String id = 'c1',
  String titulo = 'Un campo',
  String tipo = 'texto',
  dynamic valor,
  String unidad = '',
  bool permiteOtro = false,
  String textoOtro = '',
}) =>
    CampoDelFormulario(
      id: id,
      titulo: titulo,
      tipo: tipo,
      obligatorio: false,
      opciones: const <String>[],
      valor: valor,
      estado: EstadoDeCampo.pendiente,
      unidad: unidad,
      permiteOtro: permiteOtro,
      textoOtro: textoOtro,
    );

void main() {
  group('qué entra en el resumen', () {
    test('lo respondido entra, en orden', () {
      final lineas = resumenParaFinalizar(<CampoDelFormulario>[
        campo(id: 'que', titulo: 'Qué encontraste', valor: 'Drop pinchado'),
        campo(id: 'sin_responder', titulo: 'Observaciones'),
        campo(
          id: 'pot',
          titulo: 'Potencia al llegar',
          tipo: 'decimal',
          valor: '-21.19',
          unidad: 'dBm',
        ),
      ]);

      expect(lineas.map((l) => l.titulo).toList(),
          <String>['Qué encontraste', 'Potencia al llegar']);
      expect(lineas.first.valor, 'Drop pinchado');
      expect(lineas.first.id, 'que');
    });

    test('lo que no se respondió NO se muestra vacío', () {
      //  Un renglón con el título y nada al lado llena el resumen de cosas
      //  que no dicen nada, y el técnico deja de leerlo.
      expect(resumenParaFinalizar(<CampoDelFormulario>[campo()]), isEmpty);
    });

    test('un espacio en blanco tampoco es una respuesta', () {
      expect(
        resumenParaFinalizar(<CampoDelFormulario>[campo(valor: '   ')]),
        isEmpty,
      );
    });

    test('sin campos no revienta', () {
      expect(resumenParaFinalizar(const <CampoDelFormulario>[]), isEmpty);
    });

    test('un campo sin id no entra: no se podría corregir', () {
      expect(
        resumenParaFinalizar(<CampoDelFormulario>[campo(id: '', valor: 'x')]),
        isEmpty,
      );
    });
  });

  group('cómo se lee cada respuesta', () {
    test('EL FALSO SE MUESTRA: «No» es una respuesta, no una ausencia', () {
      //  «¿Se reemplazó la ONT? No» es justo lo que alguien podría querer
      //  corregir antes de firmar. Si se omitiera, el resumen diría que esa
      //  pregunta quedó sin contestar.
      final lineas = resumenParaFinalizar(<CampoDelFormulario>[
        campo(titulo: '¿Se reemplazó la ONT?', tipo: 'booleano', valor: false),
      ]);

      expect(lineas, hasLength(1));
      expect(lineas.single.valor, 'No');
    });

    test('el verdadero dice Sí, no «true»', () {
      final lineas = resumenParaFinalizar(<CampoDelFormulario>[
        campo(tipo: 'booleano', valor: true),
      ]);

      expect(lineas.single.valor, 'Sí');
    });

    test('la unidad va pegada: una potencia sin unidad no se revisa', () {
      final lineas = resumenParaFinalizar(<CampoDelFormulario>[
        campo(valor: '-18.4', unidad: 'dBm'),
      ]);

      expect(lineas.single.valor, '-18.4 dBm');
    });

    test('«Otro» muestra lo que la persona escribió, no la palabra «Otro»', () {
      //  Mostrar «Otro» a secas oculta la única parte que agrega información.
      final lineas = resumenParaFinalizar(<CampoDelFormulario>[
        campo(
          tipo: 'seleccion',
          valor: 'Otro',
          permiteOtro: true,
          textoOtro: 'Empalme viejo mojado por dentro.',
        ),
      ]);

      expect(lineas.single.valor, 'Empalme viejo mojado por dentro.');
    });

    test('«Otro» sin detallar se muestra igual, para poder corregirlo', () {
      final lineas = resumenParaFinalizar(<CampoDelFormulario>[
        campo(tipo: 'seleccion', valor: 'Otro', permiteOtro: true),
      ]);

      expect(lineas.single.valor, 'Otro (sin detallar)');
    });
  });

  /// LO QUE EL CIERRE TODAVIA TIENE QUE PREGUNTAR (09/11/2026).
  ///
  /// El usuario: «ese ultimo formulario no deberia salir... solo el boton de
  /// que el servicio queda funcionando, en el mismo resumen».
  group('como se reparten las preguntas del cierre', () {
    List<CampoDelFormulario> minimo() => <CampoDelFormulario>[
          campo(id: 'solucion', tipo: 'texto'),
          campo(id: 'servicio_validado', tipo: 'booleano'),
        ];

    test('el booleano se declara; el texto lo responde el resumen', () {
      final p = repartirElCierre(minimo());

      expect(p.declaraciones.single.id, 'servicio_validado');
      expect(p.sePuedenDeducir.single.id, 'solucion');
      expect(p.hayQuePreguntarAparte, isEmpty);
      expect(p.alcanzaConElResumen, isTrue);
    });

    /// EL CASO QUE OBLIGA A NO BORRAR LA HOJA. Si la empresa declara su
    /// propio cierre con una medicion o una seleccion, nadie la respondio
    /// antes y no se puede deducir de nada: esa se sigue preguntando.
    /// Preferible una pantalla de mas que una pregunta sin contestar.
    test('lo que no es texto ni booleano sigue necesitando su hoja', () {
      final p = repartirElCierre(<CampoDelFormulario>[
        ...minimo(),
        campo(id: 'potencia_final', tipo: 'decimal'),
      ]);

      expect(p.hayQuePreguntarAparte.single.id, 'potencia_final');
      expect(p.alcanzaConElResumen, isFalse);
    });

    /// FAIL-CLOSED CON LO QUE NO SE CONOCE. Una fecha, o un tipo que esta
    /// version no sabe dibujar, SE VE como texto pero su respuesta no esta en
    /// ningun lado: darla por respondida con el resumen seria inventar.
    test('una fecha y un tipo desconocido se preguntan, no se deducen', () {
      final p = repartirElCierre(<CampoDelFormulario>[
        campo(id: 'cuando', tipo: 'fecha'),
        campo(id: 'raro', tipo: 'algo_nuevo'),
      ]);

      expect(p.sePuedenDeducir, isEmpty);
      expect(p.hayQuePreguntarAparte.map((c) => c.id).toList(),
          <String>['cuando', 'raro']);
      expect(p.alcanzaConElResumen, isFalse);
    });

    test('un campo sin id no entra en ningun grupo', () {
      final p = repartirElCierre(<CampoDelFormulario>[
        campo(id: '', tipo: 'booleano'),
      ]);

      expect(p.declaraciones, isEmpty);
      expect(p.sePuedenDeducir, isEmpty);
      expect(p.hayQuePreguntarAparte, isEmpty);
    });

    test('sin formulario de cierre, alcanza con el resumen', () {
      expect(
        repartirElCierre(const <CampoDelFormulario>[]).alcanzaConElResumen,
        isTrue,
      );
    });

    test('el texto deducido repite lo que el tecnico aprobo, con sus titulos',
        () {
      final texto = cierreDeducido(const <LineaDeResumen>[
        LineaDeResumen(
            id: 'a', titulo: 'Que encontraste', valor: 'Drop pinchado'),
        LineaDeResumen(id: 'b', titulo: 'Que hiciste', valor: 'Cambie el tramo'),
      ]);

      expect(texto, 'Que encontraste: Drop pinchado. Que hiciste: Cambie el tramo');
    });
  });
}
