import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/materiales/devolucion_screen.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// La pantalla de devolución, dibujada.
///
/// POR QUÉ ACÁ NO SE TOCA LA BASE
/// ------------------------------
/// `testWidgets` corre con un reloj controlado, y un `await` sobre SQLite real
/// nunca se resuelve dentro de él: el test no falla, se queda colgado para
/// siempre. Así que el estado se arma a mano y se inyecta.
///
/// No es una limitación: es la separación correcta. Que la lectura devuelva
/// los números bien es de `estado_de_jornada_test`; lo que se mide acá es que
/// la pantalla dibuje lo que recibe y que el botón de cerrar obedezca a los
/// motivos del servidor, nunca a la señal.
void main() {
  EstadoDeJornada estado({
    List<String> motivos = const <String>[],
    int sinSubir = 0,
    bool cerrada = false,
    bool hayJornada = true,
    List<MaterialDeJornada> materiales = const <MaterialDeJornada>[
      MaterialDeJornada(
        codigo: 'CON-SC-APC',
        nombre: 'Conector SC/APC',
        unidad: 'unidades',
        esperado: '10',
        devuelto: '10',
        diferencia: 0,
        porDevolver: 0,
      ),
    ],
    List<TransferenciaPendiente> transferencias =
        const <TransferenciaPendiente>[],
  }) =>
      EstadoDeJornada(
        recibido: '24',
        consumido: '14',
        aDevolver: '10',
        devuelto: '10',
        diferencias: materiales.where((m) => m.diferencia != 0).length,
        ordenesAsignadas: 8,
        ordenesCompletadas: 7,
        materiales: materiales,
        transferencias: transferencias,
        motivos: motivos,
        sinSubir: sinSubir,
        cerrada: cerrada,
        hayJornada: hayJornada,
      );

  Future<void> montar(WidgetTester tester, EstadoDeJornada valor) async {
    tester.view.physicalSize = const Size(1000, 3000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: DevolucionScreen(estado: valor)),
    ));
    await tester.pumpAndSettle();
  }

  group('1. El kit de hoy', () {
    testWidgets('Muestra los números de la jornada', (tester) async {
      await montar(tester, estado());

      expect(find.text('Kit de hoy'), findsOneWidget);
      expect(find.text('24'), findsOneWidget);
      expect(find.text('14'), findsOneWidget);
      expect(find.text('Conector SC/APC'), findsOneWidget);
    });

    testWidgets('Sin jornada lo dice, en vez de mostrar ceros', (tester) async {
      await montar(tester, const EstadoDeJornada.vacio());

      expect(
        find.textContaining('Todavía no hay una jornada que cerrar'),
        findsOneWidget,
      );
    });
  });

  group('2. Cada material dice si cuadra', () {
    testWidgets('Lo devuelto completo aparece como correcto', (tester) async {
      await montar(tester, estado());

      expect(find.text('Correcto'), findsOneWidget);
      expect(find.text('Diferencia'), findsNothing);
    });

    testWidgets('Lo que falta aparece como diferencia y ofrece devolver',
        (tester) async {
      await montar(tester, estado(materiales: const <MaterialDeJornada>[
        MaterialDeJornada(
          codigo: 'CON-SC-APC',
          nombre: 'Conector SC/APC',
          unidad: 'unidades',
          esperado: '10',
          devuelto: '8',
          diferencia: 2,
          porDevolver: 2,
        ),
      ]));

      expect(find.text('Diferencia'), findsOneWidget);
      expect(find.text('Devolver 2.0 unidades'), findsOneWidget);
    });

    testWidgets('Un equipo con número muestra su serie', (tester) async {
      // Lo que hay que ubicar es ESE aparato, no "una unidad".
      await montar(tester, estado(materiales: const <MaterialDeJornada>[
        MaterialDeJornada(
          codigo: 'ONT-HG8145',
          nombre: 'ONT Huawei HG8145V5',
          unidad: 'unidades',
          esperado: '1',
          devuelto: '0',
          diferencia: 1,
          porDevolver: 1,
          serie: '48575448A9B0C1',
        ),
      ]));

      expect(find.text('Serie 48575448A9B0C1'), findsOneWidget);
      expect(find.text('Diferencia'), findsOneWidget);
    });
  });

  group('3. Lo que bloquea el cierre', () {
    testWidgets('Con todo cuadrado, el botón está habilitado', (tester) async {
      await montar(tester, estado());

      final boton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Cerrar jornada'),
      );
      expect(boton.onPressed, isNotNull);
    });

    testWidgets('Con motivos, se deshabilita y se explican', (tester) async {
      await montar(tester, estado(motivos: const <String>[
        'Conector SC/APC: faltan 2 unidades sin explicar.',
      ]));

      expect(find.text('Falta resolver esto:'), findsOneWidget);
      expect(find.textContaining('faltan 2 unidades'), findsOneWidget);

      final boton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Cerrar jornada'),
      );
      expect(boton.onPressed, isNull);
    });

    testWidgets('La falta de señal NO bloquea, solo se avisa', (tester) async {
      // Esperar señal para cerrar dejaría a alguien sin poder irse a su casa.
      await montar(tester, estado(sinSubir: 3));

      expect(find.textContaining('3 pendiente'), findsOneWidget);
      expect(find.textContaining('Suben solos'), findsOneWidget);

      final boton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Cerrar jornada'),
      );
      expect(boton.onPressed, isNotNull, reason: 'la red no decide esto');
    });

    testWidgets('Una jornada cerrada lo dice y no ofrece cerrar otra vez',
        (tester) async {
      await montar(tester, estado(cerrada: true));

      expect(find.textContaining('Jornada cerrada'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Cerrar jornada'), findsNothing);
    });
  });

  group('4. Las transferencias explican un saldo que no baja', () {
    testWidgets('Se listan como pendientes de aceptación', (tester) async {
      await montar(tester, estado(
        transferencias: const <TransferenciaPendiente>[
          TransferenciaPendiente(
            material: 'Conector SC/APC',
            cantidad: '4',
            recibe: 'Pedro',
          ),
        ],
      ));

      expect(find.text('Entregado a otro técnico'), findsOneWidget);
      expect(find.textContaining('Pedro'), findsOneWidget);
      expect(find.textContaining('Sigue contando como tuyo'), findsOneWidget);
    });
  });
}
