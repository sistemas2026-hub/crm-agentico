import 'dart:io';

import 'package:campo/core/widgets/campana_de_avisos.dart';
import 'package:campo/core/widgets/dexter_app_header.dart';
import 'package:campo/features/inicio/fila_de_aviso.dart';
import 'package:campo/features/inicio/resumen_de_inicio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// LA CAMPANA DEL ENCABEZADO (09/11/2026).
///
/// El usuario, sobre la app en uso: «que salga una campanita, y para ver las
/// notificaciones que sea dando clic para verlas, y cuando le den clic afuera
/// se recoja».
///
/// Antes los avisos vivían dentro de la pantalla de Inicio, debajo del trabajo
/// del día: desde cualquier otra pantalla no existían, y lo único que anunciaba
/// uno nuevo era un punto en la barra de abajo.
void main() {
  group('Lo que dice la chapita', () {
    test('sin avisos no hay chapita', () {
      expect(textoDelBadge(0), '');
      expect(textoDelBadge(-3), '');
    });

    test('hasta nueve se cuenta; de ahí en más, «9+»', () {
      expect(textoDelBadge(1), '1');
      expect(textoDelBadge(9), '9');
      expect(textoDelBadge(10), '9+');
      expect(textoDelBadge(347), '9+');
    });

    /// Quien no ve la chapita roja tiene que oír lo mismo: «Avisos» a secas no
    /// dice si hay algo sin leer, que es lo único que importa.
    test('el lector de pantalla oye cuántos hay sin leer', () {
      expect(etiquetaDeLaCampana(0), 'Avisos, ninguno sin leer');
      expect(etiquetaDeLaCampana(1), 'Avisos, 1 sin leer');
      expect(etiquetaDeLaCampana(12), 'Avisos, 12 sin leer');
    });
  });

  group('La campana', () {
    Widget app(Widget hijo) => MaterialApp(home: Scaffold(body: hijo));

    testWidgets('con avisos muestra el número; sin avisos no muestra nada',
        (WidgetTester tester) async {
      await tester.pumpWidget(app(
        CampanaDeAvisos(sinLeer: 3, onTap: () {}),
      ));
      expect(find.text('3'), findsOneWidget);

      await tester.pumpWidget(app(
        CampanaDeAvisos(sinLeer: 0, onTap: () {}),
      ));
      expect(find.text('0'), findsNothing);
    });

    testWidgets('tocarla avisa una sola vez', (WidgetTester tester) async {
      int toques = 0;
      await tester.pumpWidget(app(
        CampanaDeAvisos(sinLeer: 2, onTap: () => toques++),
      ));

      await tester.tap(find.byType(CampanaDeAvisos));
      await tester.pumpAndSettle();
      expect(toques, 1);
    });
  });

  /// EL CABLEADO. La campana puede estar perfecta y no servir de nada si el
  /// encabezado no la dibuja, o si le pasa un número que no es el real --que
  /// es lo que pasaba hasta hoy: el contenedor mandaba
  /// `FieldMockData.notificacionesSinLeer`, un dato de ejemplo.
  group('La campana en el encabezado', () {
    Widget header({int sinLeer = 0, VoidCallback? onAvisos}) => MaterialApp(
          home: Scaffold(
            body: DexterAppHeader(
              empresa: 'Rapilink',
              conexion: EstadoConexion.conRed,
              seccion: 'Inicio',
              notificacionesSinLeer: sinLeer,
              onAvisos: onAvisos,
            ),
          ),
        );

    testWidgets('se dibuja con el número que le pasan', (WidgetTester tester) async {
      await tester.pumpWidget(header(sinLeer: 4, onAvisos: () {}));
      expect(find.byType(CampanaDeAvisos), findsOneWidget);
      expect(find.text('4'), findsOneWidget);
    });

    testWidgets('sin nada que abrir no se dibuja', (WidgetTester tester) async {
      await tester.pumpWidget(header(sinLeer: 4));
      expect(find.byType(CampanaDeAvisos), findsNothing);
    });

    testWidgets('tocarla llama al encabezado', (WidgetTester tester) async {
      int toques = 0;
      await tester.pumpWidget(header(sinLeer: 1, onAvisos: () => toques++));
      await tester.tap(find.byType(CampanaDeAvisos));
      await tester.pumpAndSettle();
      expect(toques, 1);
    });
  });

  /// LAS ALERTAS DE LA JORNADA TAMBIÉN VIVEN ACÁ (09/11/2026).
  ///
  /// El usuario, viendo la campana andando: «hay un aviso que dice para
  /// resolver hoy y un mensaje en rojo, ¿por qué no se pone igual en
  /// notificación?». Eligió un solo lugar para todo lo que avisa.
  ///
  /// Lo que se pierde con eso, y por eso está escrito: una alerta de la
  /// jornada ya no está a la vista, hay que abrir la campana. El precio se
  /// paga con el número, que las suma: mientras haya una sin resolver, la
  /// campana no baja a cero. Si el número dejara de sumarlas, mudarlas
  /// adentro sería hacerlas invisibles.
  group('Las alertas de la jornada en la campana', () {
    testWidgets('el número suma los avisos y las alertas',
        (WidgetTester tester) async {
      //  2 avisos de la plataforma + 3 alertas de hoy = 5.
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: DexterAppHeader(
            empresa: 'Rapilink',
            conexion: EstadoConexion.conRed,
            notificacionesSinLeer: 2 + 3,
            onAvisos: () {},
          ),
        ),
      ));
      expect(find.text('5'), findsOneWidget);
    });

    /// EL PEDIDO: «ponle al aviso, cuando se le dé clic, direcciones igual».
    testWidgets('la alerta que lleva a algún lado se toca y avisa',
        (WidgetTester tester) async {
      int toques = 0;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FilaDeAviso(
            aviso: const AvisoDeInicio(
              titulo: '2 materiales no cuadran',
              detalle: 'Hay que explicar qué pasó antes de cerrar la jornada.',
              gravedad: GravedadDeAviso.alta,
              lleva: DondeSeResuelve.materiales,
            ),
            alTocar: () => toques++,
          ),
        ),
      ));

      expect(find.byIcon(Icons.chevron_right), findsOneWidget);
      await tester.tap(find.byType(FilaDeAviso));
      await tester.pumpAndSettle();
      expect(toques, 1);
    });

    /// Y la que no lleva a ningún lado no finge que sí: un toque que no hace
    /// nada se siente como una aplicación rota, y la flecha lo promete.
    testWidgets('la que no lleva a ningún lado no tiene flecha',
        (WidgetTester tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: FilaDeAviso(
            aviso: AvisoDeInicio(
              titulo: 'Algo informativo',
              detalle: 'No hay nada que hacer con esto.',
              gravedad: GravedadDeAviso.media,
            ),
          ),
        ),
      ));

      expect(find.byIcon(Icons.chevron_right), findsNothing);
    });

    testWidgets('el panel las dibuja, y antes que los avisos',
        (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (BuildContext ctx) => CampanaDeAvisos(
              sinLeer: 2,
              onTap: () => mostrarPanelDeAvisos(
                ctx,
                contenido: (BuildContext _) => Column(
                  children: const <Widget>[
                    Text('2 materiales no cuadran'),
                    Text('Te devolvieron la OT #188'),
                  ],
                ),
              ),
            ),
          ),
        ),
      ));

      await tester.tap(find.byType(CampanaDeAvisos));
      await tester.pumpAndSettle();

      final double alerta =
          tester.getTopLeft(find.text('2 materiales no cuadran')).dy;
      final double aviso =
          tester.getTopLeft(find.text('Te devolvieron la OT #188')).dy;
      expect(alerta, lessThan(aviso),
          reason: 'lo que hay que resolver hoy va antes que lo que ya pasó');
    });

    /// EL CABLEADO DEL CONTENEDOR.
    ///
    /// Las dos cosas que lo sostienen --que el panel reciba las alertas y que
    /// el número las sume-- viven en `app_shell.dart`, y montarlo con una
    /// jornada descuadrada pide una base local de verdad: esa prueba no entra
    /// en este arnés. Mientras tanto se mide el archivo, y se dice.
    ///
    /// Sin el primer cable el panel se abre sin las alertas; sin el segundo,
    /// mudarlas adentro las vuelve invisibles, que es lo único que esta
    /// mudanza no puede hacer.
    test('el contenedor le pasa las alertas al panel y las suma al número', () {
      final String fuente =
          File('lib/features/shell/app_shell.dart').readAsStringSync();

      expect(fuente, contains('for (final AvisoDeInicio aviso in _alertasDeHoy)'));
      expect(fuente, contains('alTocar: _comoSeResuelve(aviso)'));
      expect(
        fuente,
        contains('notificacionesSinLeer: _avisosSinLeer + _alertasDeHoy.length'),
      );
    });
  });

  group('El panel', () {
    /// EL PEDIDO, MEDIDO: «cuando le den clic afuera se recoja».
    testWidgets('se abre al tocar la campana y se cierra tocando afuera',
        (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (BuildContext ctx) => CampanaDeAvisos(
              sinLeer: 1,
              onTap: () => mostrarPanelDeAvisos(
                ctx,
                contenido: (BuildContext _) => const Text('Te asignaron la OT #12'),
              ),
            ),
          ),
        ),
      ));

      expect(find.text('Te asignaron la OT #12'), findsNothing);

      await tester.tap(find.byType(CampanaDeAvisos));
      await tester.pumpAndSettle();
      expect(find.text('Te asignaron la OT #12'), findsOneWidget);

      //  Un toque arriba a la izquierda: fuera del panel, que está arriba a la
      //  derecha. Es el gesto del pedido.
      await tester.tapAt(const Offset(10, 300));
      await tester.pumpAndSettle();
      expect(find.text('Te asignaron la OT #12'), findsNothing);
    });

    /// El botón Atrás de Android tiene que cerrarlo igual: un panel que se
    /// queda pegado con Atrás se siente como una aplicación trabada.
    testWidgets('el botón Atrás también lo cierra', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (BuildContext ctx) => CampanaDeAvisos(
              sinLeer: 1,
              onTap: () => mostrarPanelDeAvisos(
                ctx,
                contenido: (BuildContext _) => const Text('Un aviso'),
              ),
            ),
          ),
        ),
      ));

      await tester.tap(find.byType(CampanaDeAvisos));
      await tester.pumpAndSettle();
      expect(find.text('Un aviso'), findsOneWidget);

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.text('Un aviso'), findsNothing);
    });

    /// Si el técnico tocó la campana y no hay nada, el panel tiene que
    /// abrirse igual y decírselo. Uno que no se abre se lee como una
    /// aplicación trabada, y el técnico la toca tres veces más.
    testWidgets('con cero avisos igual se abre', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (BuildContext ctx) => CampanaDeAvisos(
              sinLeer: 0,
              onTap: () => mostrarPanelDeAvisos(
                ctx,
                contenido: (BuildContext _) => const Text('No hay avisos.'),
              ),
            ),
          ),
        ),
      ));

      await tester.tap(find.byType(CampanaDeAvisos));
      await tester.pumpAndSettle();
      expect(find.text('No hay avisos.'), findsOneWidget);
    });
  });
}
