import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/visitas_anteriores.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Lo que ya se hizo en este mismo servicio.
///
/// EL PROBLEMA QUE RESUELVE
/// -----------------------
/// El técnico toca el timbre y el cliente le dice *«ya llamé tres veces»*. No
/// tenía con qué contestar: la ficha le daba el número de ticket y nada más — el
/// número que sirve para buscar el historial **en otro lado**, o sea para llamar
/// al NOC. Es la llamada más frecuente de las que el técnico enumeró.
///
/// LO QUE ESTAS PRUEBAS CUIDAN
/// ---------------------------
/// **Que los tres «no hay nada» no se digan igual.** Son tres cosas distintas y
/// el técnico actúa distinto en cada una:
///
///   nunca se bajó          -> sincronizar, o llamar
///   no hay servicio        -> llamar al NOC
///   lista vacía            -> contestarle al cliente «es la primera vez»
///
/// Resumirlos en «sin visitas anteriores» es el error que importa: le haría
/// decirle *«es la primera vez que venimos»* a alguien que vino tres veces, y el
/// cliente le cree porque se lo dice la empresa.
void main() {
  Future<void> montar(WidgetTester t, Map<String, dynamic>? historial) async {
    t.view.physicalSize = const Size(900, 2000);
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);

    await t.pumpWidget(MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(
        body: SingleChildScrollView(
          child: VisitasAnteriores(historial: historial),
        ),
      ),
    ));
    await t.pumpAndSettle();
  }

  Map<String, dynamic> visita({
    int numero = 1842,
    String tipo = 'Reparación de Señal (FTTH)',
    String cuando = '2026-09-28T14:05:00+00:00',
    String termino = 'resuelto',
    String quien = 'Carlos Gómez',
    bool cambioEquipo = false,
    List<Map<String, dynamic>>? materiales,
  }) =>
      <String, dynamic>{
        'id': 'ot-$numero',
        'numero': numero,
        'tipo': tipo,
        'cuando': cuando,
        'como_termino': termino,
        'quien': quien,
        'vuelta': 1,
        'cambio_equipo': cambioEquipo,
        'materiales': materiales ?? const <Map<String, dynamic>>[],
      };

  group('A · los tres «no hay nada» se dicen distinto', () {
    testWidgets('a1 · sin bajar: dice que falta descargarlo', (t) async {
      await montar(t, null);

      expect(find.textContaining('Todavía no se descargó'), findsOneWidget);
      // Y NO dice que sea la primera visita, que es la respuesta equivocada.
      expect(find.textContaining('primera visita'), findsNothing);
    });

    testWidgets('a2 · sin servicio: dice que NO SE PUEDE SABER', (t) async {
      // Esta orden no tiene identificado el servicio en el sistema del ISP.
      // Adivinar por nombre o dirección devolvería visitas del vecino.
      await montar(t, <String, dynamic>{
        'hay_servicio': false,
        'visitas': <dynamic>[],
      });

      expect(find.textContaining('No se puede saber'), findsOneWidget);
      expect(find.textContaining('preguntá al NOC'), findsOneWidget);
      expect(find.textContaining('primera visita'), findsNothing);
    });

    testWidgets('a3 · con servicio y sin visitas: ES la primera vez', (t) async {
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[],
      });

      expect(find.textContaining('Es la primera visita'), findsOneWidget);
      expect(find.textContaining('No se puede saber'), findsNothing);
      expect(find.textContaining('Todavía no se descargó'), findsNothing);
    });
  });

  group('B · lo que dice una visita', () {
    testWidgets('b1 · el tipo, el número, cuándo, quién y cómo terminó',
        (t) async {
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[visita()],
      });

      expect(find.textContaining('Reparación de Señal (FTTH)'), findsOneWidget);
      expect(find.textContaining('#1842'), findsOneWidget);
      expect(find.textContaining('Carlos Gómez'), findsOneWidget);
      expect(find.text('RESUELTO'), findsOneWidget);
    });

    testWidgets('b2 · la fecha se muestra en el huso del teléfono', (t) async {
      // El servidor manda UTC. Sin convertir, en Colombia cada visita perdería
      // cinco horas y una «de ayer» aparecería como de anteayer — justo cuando
      // el técnico está contando cuántas van.
      final DateTime esperada =
          DateTime.parse('2026-09-28T14:05:00+00:00').toLocal();
      final String dia = esperada.day.toString().padLeft(2, '0');
      final String mes = esperada.month.toString().padLeft(2, '0');

      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[visita()],
      });

      expect(find.textContaining('$dia/$mes/${esperada.year}'), findsOneWidget);
    });

    testWidgets('b3 · «se cambió el equipo» se destaca', (t) async {
      // Es la pregunta que el técnico hace distinto del resto, y la que cambia
      // qué va a hacer en esta visita.
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[visita(cambioEquipo: true)],
      });

      expect(find.text('Se cambió el equipo'), findsOneWidget);
    });

    testWidgets('b4 · si NO se cambió el equipo, no se dice nada', (t) async {
      // El contrapeso: afirmarlo siempre lo volvería ruido y dejaría de leerse.
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[visita(cambioEquipo: false)],
      });

      expect(find.text('Se cambió el equipo'), findsNothing);
    });

    testWidgets('b5 · el material usado aparece con su unidad', (t) async {
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[
          visita(materiales: <Map<String, dynamic>>[
            <String, dynamic>{
              'material': 'Cable drop',
              'cantidad': '43',
              'unidad': 'm',
            },
          ]),
        ],
      });

      expect(find.textContaining('Cable drop 43 m'), findsOneWidget);
    });

    testWidgets('b6 · las tres visitas se dibujan, no solo la última',
        (t) async {
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[
          visita(numero: 1842),
          visita(numero: 1799, termino: 'cancelado'),
          visita(numero: 1703),
        ],
      });

      expect(find.textContaining('#1842'), findsOneWidget);
      expect(find.textContaining('#1799'), findsOneWidget);
      expect(find.textContaining('#1703'), findsOneWidget);
    });
  });

  group('C · datos rotos no tumban la ficha', () {
    testWidgets('c1 · `visitas` que no es lista se trata como vacía',
        (t) async {
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': 'nada',
      });

      expect(find.textContaining('Es la primera visita'), findsOneWidget);
    });

    testWidgets('c2 · una visita sin tipo igual se puede leer', (t) async {
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[
          <String, dynamic>{'numero': 1500, 'materiales': <dynamic>[]},
        ],
      });

      expect(find.textContaining('OT #1500'), findsOneWidget);
    });

    testWidgets('c3 · una fecha ilegible no imprime basura', (t) async {
      await montar(t, <String, dynamic>{
        'hay_servicio': true,
        'visitas': <dynamic>[visita(cuando: 'ayer por la tarde')],
      });

      expect(find.textContaining('ayer por la tarde'), findsNothing);
      // Y el resto de la visita se sigue viendo.
      expect(find.textContaining('#1842'), findsOneWidget);
    });
  });
}
