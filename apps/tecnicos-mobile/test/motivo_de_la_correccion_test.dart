import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// EL DIALOGO QUE PIDE POR QUE SE CORRIGE UNA UBICACION  --  11/11/2026.
///
/// POR QUE EXISTE ESTE ARCHIVO. La primera version del diálogo creaba el
/// `TextEditingController` afuera y lo soltaba con `dispose()` apenas
/// `showDialog` devolvía — con el diálogo todavía desmontándose y el
/// `TextField` todavía escuchándolo. El técnico escribió el motivo, tocó
/// «Corregir», y la aplicación se cayó entera con
/// `'_dependents.isEmpty': is not true`.
///
/// `flutter analyze` NO VE ESO: es correcto como código y falla en tiempo de
/// ejecución, en el instante exacto en que alguien usa la función. La única
/// forma de atraparlo antes es montar el diálogo, escribir, confirmar y
/// afirmar que no quedó ninguna excepción — que es lo que hace `d1`.
///
/// El diálogo es público solo para esto. Era privado, y por eso ninguna
/// prueba podía montarlo.
void main() {
  /// Lo monta y devuelve lo que el diálogo entregó al cerrarse.
  Future<String?> abrir(WidgetTester t, {int minimo = 10}) async {
    String? devuelto;
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (BuildContext ctx) => ElevatedButton(
            onPressed: () async {
              devuelto = await showDialog<String>(
                context: ctx,
                builder: (_) => MotivoDeLaCorreccion(minimo: minimo),
              );
            },
            child: const Text('abrir'),
          ),
        ),
      ),
    ));
    await t.tap(find.text('abrir'));
    await t.pumpAndSettle();
    return devuelto;
  }

  testWidgets('d1 · escribir y confirmar NO tumba la aplicación', (t) async {
    await abrir(t);
    await t.enterText(find.byType(TextField), 'El pin caía en la otra cuadra');
    await t.pumpAndSettle();
    await t.tap(find.text('Corregir'));
    await t.pumpAndSettle();

    //  EL EFECTO: el diálogo se cerró y no quedó ninguna excepción. Con el
    //  controlador soltado desde afuera, acá aparecía
    //  `'_dependents.isEmpty': is not true` y la pantalla se ponía roja.
    expect(t.takeException(), isNull);
    expect(find.byType(TextField), findsNothing, reason: 'y se cerró');
  });

  testWidgets('d2 · cancelar tampoco', (t) async {
    await abrir(t);
    await t.enterText(find.byType(TextField), 'algo escrito');
    await t.pumpAndSettle();
    await t.tap(find.text('Cancelar'));
    await t.pumpAndSettle();

    expect(t.takeException(), isNull);
  });

  testWidgets('d3 · con un motivo corto el botón está apagado', (t) async {
    await abrir(t);
    //  Sin escribir nada.
    final FilledButton boton =
        t.widget<FilledButton>(find.widgetWithText(FilledButton, 'Corregir'));
    expect(boton.onPressed, isNull, reason: 'apagado de entrada');

    await t.enterText(find.byType(TextField), 'mal');
    await t.pumpAndSettle();
    expect(
      t
          .widget<FilledButton>(
              find.widgetWithText(FilledButton, 'Corregir'))
          .onPressed,
      isNull,
      reason: '«mal» no es una justificación: tres letras destraban cualquier '
          'cosa, y una justificación que se satisface así deja de significar '
          'algo',
    );

    await t.enterText(find.byType(TextField), 'El pin caía dos cuadras arriba');
    await t.pumpAndSettle();
    expect(
      t
          .widget<FilledButton>(
              find.widgetWithText(FilledButton, 'Corregir'))
          .onPressed,
      isNotNull,
      reason: 'con algo que leer, se habilita',
    );
  });

  testWidgets('d4 · lo que se escribió es lo que vuelve, sin espacios de más',
      (t) async {
    String? devuelto;
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (BuildContext ctx) => ElevatedButton(
            onPressed: () async {
              devuelto = await showDialog<String>(
                context: ctx,
                builder: (_) => const MotivoDeLaCorreccion(minimo: 10),
              );
            },
            child: const Text('abrir'),
          ),
        ),
      ),
    ));
    await t.tap(find.text('abrir'));
    await t.pumpAndSettle();
    await t.enterText(find.byType(TextField), '  El pin estaba en la esquina  ');
    await t.pumpAndSettle();
    await t.tap(find.text('Corregir'));
    await t.pumpAndSettle();

    //  El motivo viaja al servidor y queda en el historial de la orden: que
    //  llegue con espacios al principio es basura que despues alguien lee.
    expect(devuelto, 'El pin estaba en la esquina');
  });

  testWidgets('d5 · cancelar no devuelve un motivo', (t) async {
    String? devuelto = 'no se toco';
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (BuildContext ctx) => ElevatedButton(
            onPressed: () async {
              devuelto = await showDialog<String>(
                context: ctx,
                builder: (_) => const MotivoDeLaCorreccion(minimo: 10),
              );
            },
            child: const Text('abrir'),
          ),
        ),
      ),
    ));
    await t.tap(find.text('abrir'));
    await t.pumpAndSettle();
    await t.enterText(find.byType(TextField), 'me arrepenti a mitad');
    await t.pumpAndSettle();
    await t.tap(find.text('Cancelar'));
    await t.pumpAndSettle();

    //  `null` y no la cadena escrita: arrepentirse NO puede terminar
    //  escribiendo la ubicacion igual.
    expect(devuelto, isNull);
  });
}
