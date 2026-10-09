import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un estado operativo de una pantalla, con lo que se espera de él.
///
/// POR QUÉ NO ALCANZA CON LA CAPTURA
/// ---------------------------------
/// Una captura se mira y se aprueba de un vistazo; dos estados distintos que
/// se dibujan parecido pasan sin que nadie lo note. Lo que hace falta afirmar
/// no es "se ve así" sino cuatro cosas concretas:
///
/// - qué tiene que aparecer;
/// - qué **no** puede aparecer —que es lo que más se escapa, porque nadie
///   revisa lo que no está—;
/// - qué puede hacer la persona desde ahí;
/// - si puede seguir adelante o está frenada.
///
/// Con eso, un estado que deja de distinguirse de otro rompe la prueba en vez
/// de pasar desapercibido en una imagen.
class EstadoVisual {
  const EstadoVisual({
    required this.nombre,
    required this.montar,
    this.apareceTexto = const <String>[],
    this.apareceParcial = const <String>[],
    this.noAparece = const <String>[],
    this.accionDisponible,
    this.accionAusente,
    required this.permiteContinuar,
    this.porQue = '',
  });

  /// Cómo se llama en la matriz y en el nombre de la captura.
  final String nombre;

  /// La pantalla armada con los datos de este estado.
  final Widget Function() montar;

  /// Textos exactos que tienen que estar.
  final List<String> apareceTexto;

  /// Fragmentos, para frases que llevan números o nombres variables.
  final List<String> apareceParcial;

  /// Lo que **no** puede estar. Suele ser el texto de otro estado: es la
  /// forma de comprobar que dos situaciones distintas no dicen lo mismo.
  final List<String> noAparece;

  /// El botón que la persona puede tocar acá, si hay uno.
  final String? accionDisponible;

  /// Un botón que NO puede estar ofrecido en este estado.
  final String? accionAusente;

  /// Si desde este estado se puede avanzar en el trabajo.
  ///
  /// No es lo mismo que "hay un botón": un botón que al tocarlo avisa que
  /// falta algo es un estado que **no** permite continuar.
  final bool permiteContinuar;

  /// Por qué este estado es como es. Se lee en el informe de la matriz.
  final String porQue;

  /// Comprueba las cuatro cosas sobre la pantalla ya montada.
  void verificar(WidgetTester tester) {
    for (final String texto in apareceTexto) {
      expect(find.text(texto), findsWidgets,
          reason: '[$nombre] tiene que decir "$texto"');
    }
    for (final String fragmento in apareceParcial) {
      expect(find.textContaining(fragmento), findsWidgets,
          reason: '[$nombre] tiene que mencionar "$fragmento"');
    }
    for (final String texto in noAparece) {
      expect(find.textContaining(texto), findsNothing,
          reason: '[$nombre] NO puede decir "$texto": es de otro estado');
    }
    if (accionDisponible != null) {
      expect(find.text(accionDisponible!), findsWidgets,
          reason: '[$nombre] tiene que ofrecer "$accionDisponible"');
    }
    if (accionAusente != null) {
      expect(find.text(accionAusente!), findsNothing,
          reason: '[$nombre] no puede ofrecer "$accionAusente"');
    }
  }
}
