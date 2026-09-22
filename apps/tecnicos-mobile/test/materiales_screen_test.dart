import 'package:campo/core/mock/kit_mock_data.dart';
import 'package:campo/features/materiales/kit_de_jornada.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Materiales ya tiene todo detrás: modelo, API y cola offline. Estas pruebas
/// montan la pantalla con un kit inyectado --`kit:`-- porque lo que se mide acá
/// es el DIBUJO, no la lectura: la lectura tiene sus propias pruebas contra la
/// base en `materiales_offline_test.dart`.
///
/// El kit vacío ya no dice "falta construir el módulo": dice que todavía no
/// hay material a tu nombre, que es la verdad desde que el módulo existe.
void _pantallaAlta(WidgetTester tester) {
  tester.view.physicalSize = const Size(1000, 4200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Widget _enApp(Widget hijo) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: hijo),
    );

void main() {
  group('Materiales', () {
    testWidgets('1. Fuera de la demostración dice la verdad: falta el módulo',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _enApp(const MaterialesScreen(
          mostrarDatosFuturos: false,
          kit: KitDeJornada.vacio(),
        )),
      );
      await tester.pumpAndSettle();

      expect(find.text('Mi kit y custodia'), findsOneWidget);
      expect(
        find.textContaining('no hay material entregado a tu nombre'),
        findsOneWidget,
      );
      // Ni una cifra de inventario inventada.
      expect(find.text('Mi Kit Diario'), findsNothing);
      expect(find.textContaining('Disp.'), findsNothing);
    });

    testWidgets('2. En demostración reproduce el kit completo del diseño',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      await tester.pumpWidget(
        _enApp(const MaterialesScreen(
          mostrarDatosFuturos: true,
          kit: KitDeJornada.vacio(),
        )),
      );
      await tester.pumpAndSettle();

      expect(find.text('Mi Kit'), findsOneWidget);
      expect(find.text('Mi Kit Diario'), findsOneWidget);
      // El acta con la que se entregó, y quién la firmó.
      expect(find.text(KitMockData.acta), findsOneWidget);
      expect(find.textContaining(KitMockData.despachadoPor), findsOneWidget);
      expect(find.text('TURNO ACTIVO'), findsOneWidget);
      expect(find.text('Recibidos'), findsOneWidget);
      expect(find.text('Consumo'), findsOneWidget);
      expect(find.text('Disponibles'), findsOneWidget);
      expect(find.text('Escanear QR'), findsOneWidget);
      expect(find.text('Materiales en Custodia'), findsOneWidget);
      expect(find.text('¿Finalizaste tu turno?'), findsOneWidget);
    });

    testWidgets('3. Cada clase de material se muestra con su forma propia',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      await tester.pumpWidget(
        _enApp(const MaterialesScreen(
          mostrarDatosFuturos: true,
          kit: KitDeJornada.vacio(),
        )),
      );
      await tester.pumpAndSettle();

      // Consumible: barra de consumo y razón.
      expect(find.textContaining('Consumo: 3 de 10'), findsOneWidget);
      // Bobina: metraje inicial, tendido y restante.
      expect(find.text('Tendido Hoy'), findsOneWidget);
      expect(find.text('85 m'), findsOneWidget);
      // Serializado: su número de serie, que es lo que hay que poder rastrear.
      expect(find.textContaining('48575443-A190C'), findsOneWidget);
      expect(find.text('SERIAL NUMBER (SN) · CÓDIGO BARRAS'), findsOneWidget);
      // La MAC, que es el otro identificador del equipo.
      expect(find.textContaining(KitMockData.macEquipo), findsOneWidget);
    });

    testWidgets('4. El filtro por categoría muestra solo esa clase',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      await tester.pumpWidget(
        _enApp(const MaterialesScreen(
          mostrarDatosFuturos: true,
          kit: KitDeJornada.vacio(),
        )),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.textContaining('Activos ONT'));
      await tester.pumpAndSettle();

      expect(find.text('ONT Huawei EchoLife HG8145V5'), findsOneWidget);
      expect(find.text('Conector SC/APC Rápido Verde'), findsNothing);
    });

    testWidgets('6. Las categorías agrupan como el diseño: tres, no una por clase',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      await tester.pumpWidget(
        _enApp(const MaterialesScreen(
          mostrarDatosFuturos: true,
          kit: KitDeJornada.vacio(),
        )),
      );
      await tester.pumpAndSettle();

      expect(find.text('Todos (5)'), findsOneWidget);
      expect(find.text('Activos ONT (1)'), findsOneWidget);
      // Bobinas y terminales cuentan como consumibles: se gastan, no se rastrean.
      expect(find.text('Consumibles (4)'), findsOneWidget);
      expect(find.textContaining('Bobinas ('), findsNothing);

      // Lo que hay que rastrear uno por uno se anuncia como tal.
      expect(find.text('Trazable'), findsOneWidget);
    });

    testWidgets('7. Quien recibió el kit es la sesión real, no un nombre inventado',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      await tester.pumpWidget(
        _enApp(const MaterialesScreen(
          mostrarDatosFuturos: true,
          kit: KitDeJornada.vacio(),
          tecnico: 'Ana Restrepo',
        )),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Confirmado por Ana Restrepo'), findsOneWidget);
    });

    testWidgets('8. Sin sesión leída no se firma la recepción con nadie',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      await tester.pumpWidget(
        _enApp(const MaterialesScreen(
          mostrarDatosFuturos: true,
          kit: KitDeJornada.vacio(),
        )),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Confirmado por'), findsNothing);
      expect(find.textContaining('· Confirmado'), findsOneWidget);
    });

    test('5. Las cuentas del kit cierran: recibido menos usado es disponible', () {
      for (final MaterialEnCustodia m in KitMockData.items) {
        expect(
          m.disponibles,
          m.recibidos - m.usados,
          reason: '${m.nombre} no cuadra',
        );
        expect(m.usados, lessThanOrEqualTo(m.recibidos), reason: m.nombre);
      }
    });
  });
}
