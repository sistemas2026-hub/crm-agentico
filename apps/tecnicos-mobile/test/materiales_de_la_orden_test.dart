import 'package:campo/features/detalle_orden/materiales_de_esta_orden.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// El material de **esta** orden, y las dos cosas que no se pueden mezclar.
///
/// LA PRUEBA QUE DA SENTIDO AL ARCHIVO
/// -----------------------------------
/// El kit de la jornada es lo que el técnico lleva encima para todo el día: con
/// los mismos 150 m de drop hace cinco instalaciones. Lo de esta orden es otra
/// cosa. Si los dos números se mostraran juntos —o peor, sumados— la ficha diría
/// que en una casa se usaron 150 m cuando se usaron 37,5.
///
/// Acá se afirma sobre el efecto: se pasan dos bloques con cantidades distintas
/// y se comprueba que **no aparece la suma en ninguna parte**. La existencia sale
/// del libro de movimientos; una suma en esta pantalla sería una segunda
/// contabilidad, y la que estaría mal es ésta.
///
/// LO OTRO QUE SE DEFIENDE
/// -----------------------
/// * **`null` no es «no se usó nada».** Es «no se sabe». Una lista vacía diría
///   lo primero y sería falso: el espejo puede no haberse descargado nunca.
/// * **Un descuadre no se esconde.** Una pantalla que solo muestra lo que cuadra
///   no sirve para averiguar por qué no cuadra.
/// * **Los bloques vacíos no ocupan lugar.** Cuatro títulos sin filas debajo
///   hacen que nadie lea ninguno.
void main() {
  Future<void> montar(
    WidgetTester tester, {
    Map<String, dynamic>? materiales,
    bool cargando = false,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: MaterialesDeEstaOrden(
              materiales: materiales,
              cargando: cargando,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Map<String, dynamic> fila({
    String codigo = 'DROP-1H',
    String nombre = 'Cable drop 1 hilo',
    String unidad = 'm',
    String cantidad = '37.500',
    String? serie,
    String? estado,
  }) {
    return <String, dynamic>{
      'material': <String, dynamic>{
        'codigo': codigo,
        'nombre': nombre,
        'unidad': unidad,
      },
      'cantidad': cantidad,
      'serie': ?serie,
      'estado': ?estado,
    };
  }

  group('1. Lo de la orden no se mezcla con el kit del día', () {
    testWidgets('dos bloques se muestran por separado, SIN sumarse', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 0,
          'comprometido': <dynamic>[fila(cantidad: '100.000')],
          'consumido': <dynamic>[fila(cantidad: '37.500')],
          'devuelto': <dynamic>[],
          'otros': <dynamic>[],
        },
      );

      expect(find.textContaining('100 m'), findsOneWidget);
      expect(find.textContaining('37,5 m'), findsOneWidget);

      // Lo que NO puede aparecer. Esta es la afirmación que vale: la pantalla
      // dibuja, no contabiliza.
      expect(find.textContaining('137'), findsNothing);
      expect(find.textContaining('62,5'), findsNothing);
    });

    testWidgets('manda a la otra pantalla por el kit de la jornada', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 0,
          'consumido': <dynamic>[fila()],
        },
      );

      expect(find.textContaining('para toda la jornada'), findsOneWidget);
    });
  });

  group('2. Desconocido no es vacío', () {
    testWidgets('sin descarga previa lo dice, y aclara qué NO significa', (
      WidgetTester tester,
    ) async {
      await montar(tester, materiales: null);

      expect(
        find.textContaining('todavía no está disponible'),
        findsOneWidget,
      );
      expect(
        find.textContaining('no se haya usado nada'),
        findsOneWidget,
      );
    });

    testWidgets('mientras busca, no afirma que no hay nada', (
      WidgetTester tester,
    ) async {
      await montar(tester, materiales: null, cargando: true);

      expect(find.textContaining('Buscando'), findsOneWidget);
      expect(find.textContaining('no está disponible'), findsNothing);
    });

    testWidgets('con respuesta vacía SÍ se puede decir que no hay material', (
      WidgetTester tester,
    ) async {
      // Esta es la diferencia con el caso de arriba, y es toda la razón por la
      // que el espejo distingue `null` de un mapa sin filas.
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': false,
          'con_novedad': 0,
          'comprometido': <dynamic>[],
          'consumido': <dynamic>[],
          'devuelto': <dynamic>[],
          'otros': <dynamic>[],
        },
      );

      expect(
        find.textContaining('Todavía no hay material reservado ni usado'),
        findsOneWidget,
      );
      expect(find.textContaining('no está disponible'), findsNothing);
    });
  });

  group('3. Un descuadre no se esconde', () {
    testWidgets('las novedades se cuentan y se nombran', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 2,
          'consumido': <dynamic>[fila()],
        },
      );

      expect(find.text('2 MOVIMIENTOS CON NOVEDAD'), findsOneWidget);
      expect(find.textContaining('lo mira alguien de bodega'), findsOneWidget);
    });

    testWidgets('una sola novedad se dice en singular', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 1,
          'consumido': <dynamic>[fila()],
        },
      );

      expect(find.text('1 MOVIMIENTO CON NOVEDAD'), findsOneWidget);
    });

    testWidgets('un estado distinto de aceptado se ve en la fila', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 1,
          'otros': <dynamic>[fila(estado: 'en_disputa')],
        },
      );

      expect(find.text('EN_DISPUTA'), findsOneWidget);
    });

    testWidgets('aceptado no agrega ruido', (WidgetTester tester) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 0,
          'otros': <dynamic>[fila(estado: 'aceptado')],
        },
      );

      expect(find.text('ACEPTADO'), findsNothing);
    });
  });

  group('4. Qué se dibuja de cada fila', () {
    testWidgets('el código y el nombre, y la serie cuando hay', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 0,
          'consumido': <dynamic>[
            fila(
              codigo: 'ONT-HG8145',
              nombre: 'ONT Huawei',
              unidad: 'u',
              cantidad: '1.000',
              serie: 'ABC123',
            ),
          ],
        },
      );

      expect(find.textContaining('ONT-HG8145'), findsOneWidget);
      expect(find.text('Serie: ABC123'), findsOneWidget);
      expect(find.textContaining('1 u'), findsOneWidget);
    });

    testWidgets('sin serie, esa línea no aparece', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 0,
          'consumido': <dynamic>[fila()],
        },
      );

      expect(find.textContaining('Serie:'), findsNothing);
    });

    testWidgets('un bloque sin filas no deja su título colgando', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        materiales: <String, dynamic>{
          'hay_algo': true,
          'con_novedad': 0,
          'comprometido': <dynamic>[fila()],
          'consumido': <dynamic>[],
          'devuelto': <dynamic>[],
          'otros': <dynamic>[],
        },
      );

      expect(find.text('Reservado para esta orden'), findsOneWidget);
      expect(find.text('Usado en esta orden'), findsNothing);
      expect(find.text('Devuelto'), findsNothing);
      expect(find.text('Otros movimientos'), findsNothing);
    });

    testWidgets('una clave que el backend no mandó no rompe la pantalla', (
      WidgetTester tester,
    ) async {
      // El backend puede agregar o dejar de mandar un bloque sin que haya que
      // publicar una versión nueva de la app.
      await montar(
        tester,
        materiales: <String, dynamic>{'hay_algo': true, 'con_novedad': 0},
      );

      expect(find.textContaining('para toda la jornada'), findsOneWidget);
    });
  });
}
