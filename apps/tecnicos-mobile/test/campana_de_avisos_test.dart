import 'package:campo/core/widgets/campana_de_avisos.dart';
import 'package:campo/core/widgets/dexter_app_header.dart';
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
