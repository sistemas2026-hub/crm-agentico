import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/core/widgets/dexter_card.dart';
import 'package:campo/core/widgets/dexter_empty_state.dart';
import 'package:campo/core/widgets/dexter_metric_tile.dart';
import 'package:campo/core/widgets/dexter_segmented_choice.dart';
import 'package:campo/core/widgets/dexter_status_badge.dart';
import 'package:campo/core/widgets/dexter_sync_badge.dart';
// Tristate describe las banderas de semantica que pueden estar sin definir.
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Monta un widget con el tema real de la aplicación.
Widget _enApp(Widget hijo) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: Center(child: hijo)),
    );

void main() {
  group('Componentes base de Field Ops Precision', () {
    testWidgets('1. La tarjeta muestra su contenido y responde al toque',
        (WidgetTester tester) async {
      var toques = 0;
      await tester.pumpWidget(_enApp(
        DexterCard(
          onTap: () => toques++,
          child: const Text('Carlos Gomez'),
        ),
      ));

      expect(find.text('Carlos Gomez'), findsOneWidget);
      await tester.tap(find.byType(DexterCard));
      expect(toques, 1, reason: 'una tarjeta con onTap tiene que ser tocable');
    });

    testWidgets('2. Sin onTap la tarjeta no falla ni intercepta el toque',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(const DexterCard(child: Text('Solo lectura'))));
      await tester.tap(find.byType(DexterCard));
      await tester.pump();
      expect(find.text('Solo lectura'), findsOneWidget);
    });

    testWidgets('3. Cada estado operativo trae su propio icono, no solo un color',
        (WidgetTester tester) async {
      final iconos = <IconData>{};

      for (final DexterOperationalStatus estado in DexterOperationalStatus.values) {
        await tester.pumpWidget(_enApp(DexterStatusBadge(estado: estado)));
        iconos.add(tester.widget<Icon>(find.byType(Icon)).icon!);
      }

      expect(
        iconos.length,
        DexterOperationalStatus.values.length,
        reason: 'dos estados con el mismo icono se distinguirian solo por color',
      );
    });

    testWidgets('4. La etiqueta propia no cambia la semantica del estado',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        const DexterStatusBadge(
          estado: DexterOperationalStatus.enProceso,
          etiqueta: 'En camino',
        ),
      ));

      expect(find.text('EN CAMINO'), findsOneWidget);
      expect(
        tester.widget<Icon>(find.byType(Icon)).icon,
        Icons.play_arrow,
        reason: 'el icono lo decide el estado, no el texto',
      );
    });

    testWidgets('5. Sincronizacion y estado operativo son dominios separados',
        (WidgetTester tester) async {
      // Un trabajo completado que todavia no viajo al servidor: las dos
      // pastillas conviven y dicen cosas distintas.
      await tester.pumpWidget(_enApp(
        const Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            DexterStatusBadge(estado: DexterOperationalStatus.completada),
            SizedBox(width: 8),
            DexterSyncBadge(
              estado: DexterSyncStatus.pendiente,
              detalle: '4 cambios',
            ),
          ],
        ),
      ));

      expect(find.text('COMPLETADA'), findsOneWidget);
      expect(find.text('PENDIENTE · 4 CAMBIOS'), findsOneWidget);
    });

    testWidgets('6. La pastilla de sincronizacion tocable cumple el minimo tactil',
        (WidgetTester tester) async {
      var sincronizaciones = 0;
      await tester.pumpWidget(_enApp(
        DexterSyncBadge(
          estado: DexterSyncStatus.error,
          onTap: () => sincronizaciones++,
        ),
      ));

      await tester.tap(find.byType(DexterSyncBadge));
      expect(sincronizaciones, 1);

      final caja = tester.getSize(find.byType(InkWell).first);
      expect(caja.height, greaterThanOrEqualTo(AppSpacing.objetivoTactil));
      expect(caja.width, greaterThanOrEqualTo(AppSpacing.objetivoTactil));
    });

    testWidgets('7. La metrica muestra valor y unidad sin que el widget la suponga',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        const DexterMetricTile(
          etiqueta: 'Potencia RX',
          valor: '-18.7',
          unidad: 'dBm',
          tono: DexterMetricTone.precaucion,
          nota: 'Rango optimo: -18 a -25',
        ),
      ));

      expect(find.text('-18.7'), findsOneWidget);
      expect(find.text('dBm'), findsOneWidget);
      expect(find.text('POTENCIA RX'), findsOneWidget);
      expect(find.text('Rango optimo: -18 a -25'), findsOneWidget);
    });

    testWidgets('8. La metrica sirve igual para un dato que no lleva unidad',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        const DexterMetricTile(etiqueta: 'SLA restante', valor: '01:42'),
      ));

      expect(find.text('01:42'), findsOneWidget);
      // Ninguna unidad inventada al lado del valor.
      expect(find.text('h'), findsNothing);
      expect(find.text('dBm'), findsNothing);
    });

    testWidgets('9. El valor usa la tipografia monoespaciada tabular',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        const DexterMetricTile(etiqueta: 'Drop tendido', valor: '35', unidad: 'm'),
      ));

      final estilo = tester.widget<Text>(find.text('35')).style!;
      expect(estilo.fontFamily, AppTypography.familiaMono);
      expect(estilo.fontFeatures, contains(const FontFeature.tabularFigures()));
    });

    testWidgets('10. Elegir una opcion avisa una sola vez y con el valor tipado',
        (WidgetTester tester) async {
      final elegidos = <String>[];

      await tester.pumpWidget(_enApp(
        DexterSegmentedChoice<String>(
          opciones: const <DexterChoiceOption<String>>[
            DexterChoiceOption<String>(valor: 'online', etiqueta: 'Online'),
            DexterChoiceOption<String>(valor: 'offline', etiqueta: 'Offline'),
          ],
          valor: 'online',
          onChanged: elegidos.add,
        ),
      ));

      await tester.tap(find.text('Offline'));
      expect(elegidos, <String>['offline']);
    });

    testWidgets('11. La opcion elegida se marca tambien con un tilde',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        DexterSegmentedChoice<int>(
          opciones: const <DexterChoiceOption<int>>[
            DexterChoiceOption<int>(valor: 1, etiqueta: 'Si'),
            DexterChoiceOption<int>(valor: 2, etiqueta: 'No'),
          ],
          valor: 1,
          onChanged: (_) {},
        ),
      ));

      expect(find.byIcon(Icons.check), findsOneWidget);
    });

    testWidgets('12. Cada opcion anuncia si esta elegida y respeta el minimo tactil',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        DexterSegmentedChoice<String>(
          opciones: const <DexterChoiceOption<String>>[
            DexterChoiceOption<String>(valor: 'a', etiqueta: 'Intermitente'),
            DexterChoiceOption<String>(valor: 'b', etiqueta: 'Estable'),
          ],
          valor: 'a',
          onChanged: (_) {},
        ),
      ));

      final banderas = tester.getSemantics(find.text('Intermitente')).flagsCollection;
      expect(banderas.isSelected, ui.Tristate.isTrue);
      expect(banderas.isButton, isTrue);

      for (final String etiqueta in <String>['Intermitente', 'Estable']) {
        expect(
          tester.getSize(find.ancestor(
            of: find.text(etiqueta),
            matching: find.byType(InkWell),
          )).height,
          greaterThanOrEqualTo(AppSpacing.objetivoTactil),
        );
      }
    });

    testWidgets('13. Sin onChanged el grupo queda en lectura y no avisa cambios',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        const DexterSegmentedChoice<String>(
          opciones: <DexterChoiceOption<String>>[
            DexterChoiceOption<String>(valor: 'a', etiqueta: 'Si'),
          ],
          valor: null,
          onChanged: null,
        ),
      ));

      await tester.tap(find.text('Si'));
      await tester.pump();
      expect(
        tester.getSemantics(find.text('Si')).flagsCollection.isEnabled,
        ui.Tristate.isFalse,
      );
    });

    testWidgets('14. El vacio con accion la ofrece; el vacio tranquilo no',
        (WidgetTester tester) async {
      var reintentos = 0;
      await tester.pumpWidget(_enApp(
        DexterEmptyState(
          icono: Icons.cloud_off,
          titulo: 'No se pudo leer',
          mensaje: 'Revisa la conexion.',
          textoAccion: 'Reintentar',
          onAccion: () => reintentos++,
          esAdvertencia: true,
        ),
      ));

      await tester.tap(find.text('Reintentar'));
      expect(reintentos, 1);

      await tester.pumpWidget(_enApp(
        const DexterEmptyState(
          icono: Icons.event_available,
          titulo: 'Sin trabajos para hoy',
        ),
      ));
      expect(find.byType(OutlinedButton), findsNothing);
    });
  });
}
