import 'package:flutter_test/flutter_test.dart';

import 'package:campo/core/sync/envio_automatico.dart';

/// EL ENVÍO AUTOMÁTICO (30/10/2026). El usuario: «¿no debería ser mejor que
/// si no tiene internet y hace un cambio, apenas la app tenga conexión envíe
/// los datos automático?». Se prueba con el reloj de `testWidgets`: `pump`
/// con una duración hace correr los temporizadores sin esperar de verdad.
void main() {
  late int envios;
  late bool pendientes;
  late EnvioAutomatico envio;

  setUp(() {
    envios = 0;
    pendientes = false;
    envio = EnvioAutomatico(
      enviar: () async => envios++,
      hayPendientes: () => pendientes,
    );
  });

  //  Cada prueba que arranca el reloj lo corta al final: Flutter revisa los
  //  temporizadores pendientes ANTES del tearDown.
  tearDown(() => envio.parar());

  group('vuelve la red', () {
    testWidgets('de SIN red a CON red envía, a los 3 segundos',
        (WidgetTester tester) async {
      envio.alCambiarLaRed(false);
      envio.alCambiarLaRed(true);
      await tester.pump(const Duration(seconds: 2));
      expect(envios, 0, reason: 'todavía en la espera');
      await tester.pump(const Duration(seconds: 1));
      expect(envios, 1);
    });

    testWidgets('una red que parpadea envía UNA vez, al final',
        (WidgetTester tester) async {
      envio.alCambiarLaRed(false);
      for (var i = 0; i < 4; i++) {
        envio.alCambiarLaRed(true);
        await tester.pump(const Duration(seconds: 1));
        envio.alCambiarLaRed(false);
        await tester.pump(const Duration(seconds: 1));
      }
      envio.alCambiarLaRed(true);
      await tester.pump(const Duration(seconds: 3));
      expect(envios, 1);
    });

    testWidgets('si la red se va durante la espera, no envía',
        (WidgetTester tester) async {
      envio.alCambiarLaRed(false);
      envio.alCambiarLaRed(true);
      await tester.pump(const Duration(seconds: 1));
      envio.alCambiarLaRed(false);
      await tester.pump(const Duration(seconds: 5));
      expect(envios, 0);
    });

    testWidgets('el primer dato al abrir no es una vuelta: no envía',
        (WidgetTester tester) async {
      envio.alCambiarLaRed(true);
      envio.alCambiarLaRed(true);
      await tester.pump(const Duration(seconds: 5));
      expect(envios, 0);
    });
  });

  group('vuelve a la app', () {
    testWidgets('con red envía', (WidgetTester tester) async {
      envio.alCambiarLaRed(true);
      envio.alVolverALaApp();
      await tester.pump(const Duration(seconds: 3));
      expect(envios, 1);
    });

    testWidgets('dos vueltas seguidas envían UNA vez: la segunda reinicia la '
        'espera', (WidgetTester tester) async {
      envio.alCambiarLaRed(true);
      envio.alVolverALaApp();
      await tester.pump(const Duration(seconds: 2));
      envio.alVolverALaApp();
      await tester.pump(const Duration(seconds: 2));
      expect(envios, 0, reason: 'la segunda vuelta reinició la espera');
      await tester.pump(const Duration(seconds: 1));
      expect(envios, 1);
      await tester.pump(const Duration(seconds: 5));
      expect(envios, 1);
    });

    testWidgets('sin red no lo intenta', (WidgetTester tester) async {
      envio.alCambiarLaRed(false);
      envio.alVolverALaApp();
      await tester.pump(const Duration(seconds: 5));
      expect(envios, 0);
    });
  });

  group('cada 2 minutos', () {
    testWidgets('con pendientes reintenta solo', (WidgetTester tester) async {
      pendientes = true;
      envio.arrancar();
      await tester.pump(const Duration(minutes: 2));
      expect(envios, 1);
      await tester.pump(const Duration(minutes: 2));
      expect(envios, 2);
      envio.parar();
    });

    testWidgets('sin pendientes no gasta datos', (WidgetTester tester) async {
      envio.arrancar();
      await tester.pump(const Duration(minutes: 10));
      expect(envios, 0);
      envio.parar();
    });

    testWidgets('sin red no lo intenta aunque haya pendientes',
        (WidgetTester tester) async {
      pendientes = true;
      envio.alCambiarLaRed(false);
      envio.arrancar();
      await tester.pump(const Duration(minutes: 4));
      expect(envios, 0);
      envio.parar();
    });

    testWidgets('arrancar dos veces no suma otro reloj',
        (WidgetTester tester) async {
      pendientes = true;
      envio.arrancar();
      envio.arrancar();
      await tester.pump(const Duration(minutes: 2));
      expect(envios, 1);
      envio.parar();
    });
  });

  testWidgets('un envío que falla no rompe nada y el siguiente sale',
      (WidgetTester tester) async {
    var llamadas = 0;
    final EnvioAutomatico conFallo = EnvioAutomatico(
      enviar: () async {
        llamadas++;
        throw StateError('sin servidor');
      },
      hayPendientes: () => true,
    )..arrancar();
    await tester.pump(const Duration(minutes: 4));
    expect(llamadas, 2);
    conFallo.parar();
  });

  testWidgets('parar corta la espera y el reloj', (WidgetTester tester) async {
    pendientes = true;
    envio.arrancar();
    envio.alCambiarLaRed(false);
    envio.alCambiarLaRed(true);
    envio.parar();
    await tester.pump(const Duration(minutes: 5));
    expect(envios, 0);
  });
}
