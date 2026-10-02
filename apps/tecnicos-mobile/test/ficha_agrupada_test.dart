import 'package:campo/core/widgets/dexter_bloques.dart';
import 'package:campo/features/detalle_orden/materiales_de_esta_orden.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Dos arreglos que nacieron de mirar la pantalla, no de leer el código.
///
/// 1 · ANOTAR LO QUE SE GASTÓ, DONDE SE MIRA LO QUE SE GASTÓ
/// --------------------------------------------------------
/// El registro de consumo existía y estaba bien resuelto, pero vivía detrás de
/// «Ejecutar el trabajo». El técnico mira «Material de esta orden», ve 37,5 m, y
/// no tiene cómo anotar el conector que acaba de poner. Lo que no se anota en el
/// momento se corrige a fin de mes de memoria, y entonces el inventario es una
/// ficción.
///
/// El botón aparece **también cuando no hay nada que mostrar**: sin señal es
/// justo cuando más falta hace, y un botón que desaparece ahí desaparece en el
/// único momento que importa.
///
/// 2 · UNA PILA DE TARJETAS IGUALES NO ES UNA JERARQUÍA
/// ---------------------------------------------------
/// La ficha apilaba doce `DexterBloque` con el mismo fondo, borde y separación:
/// al bajar parecía una sola sección larga. `GrupoDeFicha` pone un rótulo fuera
/// de las tarjetas y separa los grupos más que a sus miembros.
///
/// Lo que se afirma acá es lo que puede romperse: **un grupo sin tarjetas no se
/// anuncia**. Varias secciones de la ficha son condicionales —la telemetría, el
/// triage, el protocolo—, así que un grupo entero puede quedar vacío; dibujar su
/// rótulo mandaría al técnico a buscar algo que no está.
void main() {
  group('1. El técnico puede anotar lo que gastó desde la ficha', () {
    Future<void> montar(
      WidgetTester tester, {
      Map<String, dynamic>? materiales,
      VoidCallback? alAgregar,
    }) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: MaterialesDeEstaOrden(
                materiales: materiales,
                cargando: false,
                alAgregar: alAgregar,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    Map<String, dynamic> conMaterial() => <String, dynamic>{
      'hay_algo': true,
      'con_novedad': 0,
      'consumido': <dynamic>[
        <String, dynamic>{
          'material': <String, dynamic>{
            'codigo': 'FIB-DROP',
            'nombre': 'Fibra drop',
            'unidad': 'm',
          },
          'cantidad': '37.500',
        },
      ],
    };

    testWidgets('el gesto se ofrece junto a lo que ya se usó', (
      WidgetTester tester,
    ) async {
      await montar(tester, materiales: conMaterial(), alAgregar: () {});

      expect(find.text('Anotar lo que usé'), findsOneWidget);
    });

    testWidgets('y llama a quien sabe abrir el registro', (
      WidgetTester tester,
    ) async {
      bool pidio = false;
      await montar(
        tester,
        materiales: conMaterial(),
        alAgregar: () => pidio = true,
      );

      await tester.tap(find.text('Anotar lo que usé'));
      await tester.pumpAndSettle();

      expect(pidio, isTrue);
    });

    testWidgets('también sin nada descargado, que es cuando más falta hace', (
      WidgetTester tester,
    ) async {
      await montar(tester, materiales: null, alAgregar: () {});

      expect(find.textContaining('todavía no está disponible'), findsOneWidget);
      expect(find.text('Anotar lo que usé'), findsOneWidget);
    });

    testWidgets('sin a quién entregarlo, la sección queda en lectura', (
      WidgetTester tester,
    ) async {
      await montar(tester, materiales: conMaterial(), alAgregar: null);

      expect(find.text('Anotar lo que usé'), findsNothing);
    });
  });

  group('2. Los grupos ordenan la ficha', () {
    Future<void> montarGrupo(
      WidgetTester tester, {
      required String titulo,
      required List<Widget> children,
    }) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: GrupoDeFicha(titulo: titulo, children: children),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('el rótulo va en mayúsculas y fuera de las tarjetas', (
      WidgetTester tester,
    ) async {
      await montarGrupo(
        tester,
        titulo: 'Para llegar',
        children: <Widget>[
          const DexterBloque(titulo: 'Cliente', children: <Widget>[Text('x')]),
        ],
      );

      expect(find.text('PARA LLEGAR'), findsOneWidget);
      expect(find.text('Cliente'), findsOneWidget);
    });

    testWidgets('un grupo SIN tarjetas no se anuncia', (
      WidgetTester tester,
    ) async {
      // LA PRUEBA QUE IMPORTA. Varias secciones de la ficha son condicionales:
      // un grupo entero puede quedar vacío, y un rótulo solo mandaría a buscar
      // algo que no está.
      await montarGrupo(
        tester,
        titulo: 'Para entender la falla',
        children: const <Widget>[],
      );

      expect(find.text('PARA ENTENDER LA FALLA'), findsNothing);
    });

    testWidgets('con una sola tarjeta sí se anuncia', (
      WidgetTester tester,
    ) async {
      // La otra dirección: esconder siempre el rótulo cumpliría la prueba de
      // arriba sin servir para nada.
      await montarGrupo(
        tester,
        titulo: 'Para ejecutar',
        children: <Widget>[
          const DexterBloque(titulo: 'Material', children: <Widget>[Text('y')]),
        ],
      );

      expect(find.text('PARA EJECUTAR'), findsOneWidget);
    });

    testWidgets('las tarjetas del grupo se dibujan todas y en orden', (
      WidgetTester tester,
    ) async {
      await montarGrupo(
        tester,
        titulo: 'Para entender la falla',
        children: <Widget>[
          const DexterBloque(titulo: 'Uno', children: <Widget>[Text('1')]),
          const DexterBloque(titulo: 'Dos', children: <Widget>[Text('2')]),
        ],
      );

      final Offset uno = tester.getTopLeft(find.text('Uno'));
      final Offset dos = tester.getTopLeft(find.text('Dos'));

      expect(uno.dy < dos.dy, isTrue);
    });
  });
}
