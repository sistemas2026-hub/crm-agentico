import 'package:campo/core/storage/ciclo_de_vida_local.dart';
import 'package:campo/features/sesion/hoja_de_pendientes.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// EL CALLEJON TENIA UN CARTEL Y NO UNA SALIDA  --  10/11/2026.
///
/// El usuario: «los cambios no se envían desde la app, quedan ahí
/// acumulándose». La pastilla decía «9 cambios necesitan que alguien lo
/// revise», la red en verde, y «Sincronizar ahora» no movía ninguno — porque
/// un `conflicto` (409) y un `error_validacion` (400) salen del reintento
/// automático a propósito. El aviso mandaba a revisar sin que existiera el
/// cómo.
///
/// LO QUE ESTAS PRUEBAS AFIRMAN ES EL EFECTO, Y NO QUE EL BOTON ESTE:
///
/// * que al tocarlo se reencola **y después** se manda — reencolar sin
///   sincronizar deja el cambio en la cola y la pantalla igual, que es el
///   defecto de nuevo con otro nombre;
/// * que un cero se diga como cero, en vez de parecer que algo pasó;
/// * y que el texto de error **deje de culpar a la señal**, que es lo que
///   mandaba a buscar cobertura a quien ya la tenía.
void main() {
  ResumenPendientes conMutaciones(int n, {List<String>? detalle}) =>
      ResumenPendientes(
        mutaciones: n,
        evidencias: 0,
        ordenesConDatos: 0,
        movimientosDeMaterial: 0,
        detalle: detalle ?? <String>['OT #4832 · cierre'],
      );

  /// Monta la hoja directamente, sin el shell: lo que se prueba es la hoja.
  Future<void> abrir(
    WidgetTester t, {
    required ResumenPendientes pendientes,
    required Future<ResumenPendientes> Function() sincronizar,
    Future<int> Function()? reencolar,
  }) async {
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: HojaDePendientes(
          pendientes: pendientes,
          sincronizar: sincronizar,
          reencolarRechazadas: reencolar,
        ),
      ),
    ));
    await t.pumpAndSettle();
  }

  group('A · cuándo se ofrece la salida', () {
    testWidgets('a1 · recién después de un intento que no vació la cola',
        (t) async {
      await abrir(
        t,
        pendientes: conMutaciones(9),
        sincronizar: () async => conMutaciones(9),
        reencolar: () async => 9,
      );

      //  Antes de intentar no se ofrece: el camino normal es «Sincronizar
      //  ahora», y ofrecer el raro primero enseña a usar el raro siempre.
      expect(find.text('Volver a intentar los rechazados'), findsNothing);

      await t.tap(find.text('Sincronizar ahora'));
      await t.pumpAndSettle();

      expect(find.text('Volver a intentar los rechazados'), findsOneWidget);
    });

    testWidgets('a2 · sin el camino cableado, el botón no se dibuja',
        (t) async {
      await abrir(
        t,
        pendientes: conMutaciones(9),
        sincronizar: () async => conMutaciones(9),
        // reencolar: null  -- la hoja se comporta como antes
      );
      await t.tap(find.text('Sincronizar ahora'));
      await t.pumpAndSettle();

      expect(find.text('Volver a intentar los rechazados'), findsNothing);
    });
  });

  group('B · qué hace el botón', () {
    testWidgets('b1 · reencola Y DESPUES manda, en ese orden', (t) async {
      final List<String> pasos = <String>[];
      await abrir(
        t,
        pendientes: conMutaciones(9),
        sincronizar: () async {
          pasos.add('mandar');
          return conMutaciones(9);
        },
        reencolar: () async {
          pasos.add('reencolar');
          return 3;
        },
      );

      await t.tap(find.text('Sincronizar ahora'));
      await t.pumpAndSettle();
      pasos.clear();

      await t.tap(find.text('Volver a intentar los rechazados'));
      await t.pumpAndSettle();

      //  EL EFECTO: los dos pasos, y en orden. Reencolar sin mandar deja el
      //  cambio en la cola y la pantalla igual que antes --el defecto otra
      //  vez--, y mandar antes de reencolar manda lo que todavía está
      //  rechazado, o sea nada.
      expect(pasos, <String>['reencolar', 'mandar']);
    });

    testWidgets('b2 · dice cuántos movió', (t) async {
      await abrir(
        t,
        pendientes: conMutaciones(9),
        sincronizar: () async => conMutaciones(9),
        reencolar: () async => 3,
      );
      await t.tap(find.text('Sincronizar ahora'));
      await t.pumpAndSettle();

      await t.tap(find.text('Volver a intentar los rechazados'));
      await t.pumpAndSettle();

      expect(find.textContaining('3 cambios vuelven a la cola'),
          findsOneWidget);
    });

    testWidgets('b3 · un cero se dice, y no se manda de nuevo', (t) async {
      int mandadas = 0;
      await abrir(
        t,
        pendientes: conMutaciones(9),
        sincronizar: () async {
          mandadas++;
          return conMutaciones(9);
        },
        reencolar: () async => 0,
      );
      await t.tap(find.text('Sincronizar ahora'));
      await t.pumpAndSettle();
      expect(mandadas, 1);

      await t.tap(find.text('Volver a intentar los rechazados'));
      await t.pumpAndSettle();

      //  Si no había ninguno rechazado, el problema es otro. Sincronizar de
      //  nuevo daría el mismo resultado y haría parecer que el botón hizo
      //  algo.
      expect(find.textContaining('No había ningún cambio rechazado'),
          findsOneWidget);
      expect(mandadas, 1, reason: 'no se manda otra vez por nada');
    });

    testWidgets('b4 · si el reencolado falla, la hoja sigue en pie',
        (t) async {
      await abrir(
        t,
        pendientes: conMutaciones(9),
        sincronizar: () async => conMutaciones(9),
        reencolar: () async => throw Exception('la base del teléfono falló'),
      );
      await t.tap(find.text('Sincronizar ahora'));
      await t.pumpAndSettle();

      await t.tap(find.text('Volver a intentar los rechazados'));
      await t.pumpAndSettle();

      //  El técnico tiene que poder salir de acá. Un fallo de escritura no
      //  puede dejar la hoja colgada ni tumbar la pantalla.
      expect(find.text('Cancelar'), findsOneWidget);
      //  Y la excepcion quedo ABSORBIDA, no propagada: si subiera, el harness
      //  la entrega aca. Afirmarlo con una funcion que devuelve `true` seria
      //  exactamente la prueba que no mide nada.
      expect(t.takeException(), isNull);
    });
  });

  group('C · el texto que culpaba a la señal', () {
    testWidgets('c1 · con la salida cableada, no manda a buscar cobertura',
        (t) async {
      await abrir(
        t,
        pendientes: conMutaciones(9),
        sincronizar: () async => conMutaciones(9),
        reencolar: () async => 9,
      );
      await t.tap(find.text('Sincronizar ahora'));
      await t.pumpAndSettle();

      //  Con la red en verde y el servidor rechazando, «puede ser que no haya
      //  señal» manda a buscar señal a quien ya la tiene.
      expect(find.textContaining('no haya señal'), findsNothing);
      expect(find.textContaining('no es falta de señal'), findsOneWidget);
    });

    testWidgets('c2 · sin la salida cableada, el texto de antes se mantiene',
        (t) async {
      await abrir(
        t,
        pendientes: conMutaciones(9),
        sincronizar: () async => conMutaciones(9),
      );
      await t.tap(find.text('Sincronizar ahora'));
      await t.pumpAndSettle();

      expect(find.textContaining('no haya señal'), findsOneWidget);
    });
  });

  group('D · el motivo se lee en la lista', () {
    testWidgets('d1 · el campo que el servidor nombró se muestra', (t) async {
      //  La línea la arma `pendientesDe`; acá se afirma que la hoja la
      //  MUESTRA, que es el otro extremo del mismo camino.
      await abrir(
        t,
        pendientes: conMutaciones(1, detalle: <String>[
          "OT #4832 · cierre · el servidor lo rechazó: El campo "
              "'potencia_rx' no existe en la plantilla.",
        ]),
        sincronizar: () async => conMutaciones(1),
        reencolar: () async => 1,
      );

      expect(find.textContaining('potencia_rx'), findsOneWidget);
      expect(find.textContaining('el servidor lo rechazó'), findsOneWidget);
    });
  });
}
