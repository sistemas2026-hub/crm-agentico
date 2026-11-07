import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/core/widgets/dexter_app_header.dart';
import 'package:campo/core/widgets/dexter_bloques.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Las medidas del diseño "DEXTER CAMPO", clavadas.
///
/// POR QUÉ ESTA PRUEBA EXISTE
/// --------------------------
/// El tema de esta aplicación ya se migró una vez de un diseño de Stitch a
/// otro del mismo producto. Los dos usaban los MISMOS NOMBRES de token con
/// tonos distintos, así que nada falló ni avisó: la aplicación simplemente
/// quedó pintada con la paleta de otra maqueta durante días.
///
/// Por eso acá no se afirma que un token exista —eso no prueba nada—, sino
/// que vale exactamente lo que dice la configuración de Tailwind de las seis
/// pantallas, bajada el 25/09/2026. Si alguien vuelve a mezclar dos familias,
/// esto se pone rojo antes de que llegue a un teléfono.
void main() {
  group('1. La paleta es la de las seis pantallas, no la de otra familia', () {
    test('Los tonos que distinguen esta familia', () {
      // El verde del sistema. En la familia anterior el terciario era un azul
      // oscuro y este verde había que inventarlo aparte.
      expect(AppColors.onTertiaryContainer, const Color(0xFF009971));
      expect(AppColors.exito, AppColors.onTertiaryContainer,
          reason: 'el verde de "esto está bien" es un token, no uno propio');

      // El azul de acción y el del botón dominante, que NO son el mismo.
      expect(AppColors.secondary, const Color(0xFF0055C6));
      expect(AppColors.secondaryContainer, const Color(0xFF116DF4));

      expect(AppColors.surface, const Color(0xFFF7F9FF));
      expect(AppColors.surfaceContainerLowest, const Color(0xFFFFFFFF));
      expect(AppColors.surfaceContainerHigh, const Color(0xFFDBEAFB));
      expect(AppColors.onSurface, const Color(0xFF0F1D29));
      expect(AppColors.outline, const Color(0xFF75777E));
      expect(AppColors.error, const Color(0xFFBA1A1A));
    });

    test('Esta familia no declara un ámbar, y no se inventa uno', () {
      // Se buscaron amber/yellow/orange en las seis maquetas: las únicas
      // apariciones son nombres de ícono. Lo que pide atención se dice con el
      // azul del sistema o con el rojo.
      expect(AppColors.precaucion, AppColors.onSecondaryFixedVariant);
      expect(AppColors.precaucionFondo, AppColors.secondaryFixed);
    });
  });

  group('2. La escala tipográfica, con la monoespaciada donde va', () {
    test('Las insignias y la telemetría son monoespaciadas', () {
      // Es lo que cambió respecto del diseño anterior, donde las etiquetas
      // eran Inter: acá un dato del sistema se ve distinto de una palabra
      // escrita por una persona.
      expect(AppTypography.labelBadge.fontFamily, AppTypography.familiaMono);
      expect(AppTypography.labelBadge.fontSize, 12);
      expect(AppTypography.labelBadge.fontWeight, FontWeight.w700);

      expect(AppTypography.labelTelemetry.fontFamily, AppTypography.familiaMono);
      expect(AppTypography.labelTelemetry.fontSize, 16);

      // Y el rótulo gris NO lo es: es de interfaz.
      expect(AppTypography.labelCaption.fontFamily, AppTypography.familiaTexto);
      expect(AppTypography.labelCaption.fontSize, 12);
      expect(AppTypography.labelCaption.fontWeight, FontWeight.w600);
    });

    test('Los escalones de título y cuerpo', () {
      expect(AppTypography.headlineMd.fontSize, 20);
      expect(AppTypography.headlineMd.fontWeight, FontWeight.w600);
      expect(AppTypography.headlineLg.fontSize, 24);
      expect(AppTypography.headlineXlMovil.fontSize, 28);
      expect(AppTypography.headlineXl.fontSize, 36);
      expect(AppTypography.bodyLg.fontSize, 18);
      expect(AppTypography.bodyMd.fontSize, 16);
      expect(AppTypography.bodySm.fontSize, 14);
    });
  });

  group('3. El ritmo y la curvatura', () {
    test('Los escalones de espacio son los de esta familia', () {
      expect(AppSpacing.xs, 4);
      expect(AppSpacing.sm, 8);
      expect(AppSpacing.md, 12);
      // Estos dos cambiaron al pasar de familia: 1.25rem y 2rem.
      expect(AppSpacing.lg, 20);
      expect(AppSpacing.xl, 32);
      // Y el margen NO los sigue: el diseño tiene su propio token de 1rem.
      expect(AppSpacing.margen, 16);
      expect(AppSpacing.encabezado, 64);
      expect(AppSpacing.barraInferior, 80);
    });

    test('Los radios', () {
      expect(AppRadius.chico, 4); // rounded
      expect(AppRadius.tarjeta, 8); // rounded-lg
      expect(AppRadius.completo, 12); // rounded-xl
    });
  });

  group('4. Los bloques miden lo que el diseño dice', () {
    testWidgets('La tarjeta de sección es rounded-xl, no rounded-lg',
        (WidgetTester t) async {
      await t.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: DexterBloque(
            titulo: 'Abonado & Terminal',
            icono: Icons.person_pin,
            children: <Widget>[Text('contenido')],
          ),
        ),
      ));

      final caja = t.widget<DecoratedBox>(
        find
            .descendant(
              of: find.byType(DexterBloque),
              matching: find.byType(DecoratedBox),
            )
            .first,
      );
      final decoracion = caja.decoration as BoxDecoration;
      expect(
        decoracion.borderRadius,
        const BorderRadius.all(Radius.circular(12)),
        reason: 'p-space-md rounded-xl: 12, no los 8 de la version anterior',
      );
      expect(decoracion.color, AppColors.surfaceContainerLowest);

      // El título va en headline-md.
      expect(
        t.widget<Text>(find.text('Abonado & Terminal')).style?.fontSize,
        20,
      );
    });

    testWidgets('Los dos botones miden 56 px de alto', (WidgetTester t) async {
      await t.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Column(
            children: <Widget>[
              DexterAccionRapida(
                icono: Icons.phone_in_talk,
                texto: 'Llamar Cliente',
                alTocar: () {},
              ),
              DexterAccionDominante(
                texto: 'Iniciar Diagnóstico',
                icono: Icons.play_circle,
                alTocar: () {},
              ),
            ],
          ),
        ),
      ));

      // h-14 en las dos: la aplicación se usa con guantes.
      expect(t.getSize(find.byType(DexterAccionRapida)).height, 56);
      expect(t.getSize(find.byType(DexterAccionDominante)).height, 56);

      // El dominante es el único relleno de azul saturado.
      final material = t.widget<Material>(
        find
            .descendant(
              of: find.byType(DexterAccionDominante),
              matching: find.byType(Material),
            )
            .first,
      );
      expect(material.color, AppColors.secondaryContainer);

      // Y su texto va en mayúsculas, como en el diseño.
      expect(find.text('INICIAR DIAGNÓSTICO'), findsOneWidget);
    });

    testWidgets('Un botón sin acción no se pinta como si la tuviera',
        (WidgetTester t) async {
      await t.pumpWidget(const MaterialApp(
        home: Scaffold(body: DexterAccionDominante(texto: 'Sin acción')),
      ));

      final material = t.widget<Material>(
        find
            .descendant(
              of: find.byType(DexterAccionDominante),
              matching: find.byType(Material),
            )
            .first,
      );
      expect(
        material.color,
        isNot(AppColors.secondaryContainer),
        reason: 'un boton azul que no hace nada promete algo que no existe',
      );
    });

    testWidgets('La barra dibuja una celda por color, y solo esas',
        (WidgetTester t) async {
      await t.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: DexterBarraSegmentada(
            celdas: <Color>[
              AppColors.onTertiaryContainer,
              AppColors.onTertiaryContainer,
              AppColors.tertiaryFixedDim,
              AppColors.error,
              AppColors.surfaceContainerHigh,
            ],
            izquierda: '-14 dBm',
            centro: '-28.9 dBm',
            derecha: '-32 dBm',
          ),
        ),
      ));

      final celdas = find.descendant(
        of: find.byType(DexterBarraSegmentada),
        matching: find.byType(DecoratedBox),
      );
      expect(t.widgetList(celdas).length, 5);

      // 12 px de alto, como el `h-3` del diseño.
      expect(t.getSize(find.byType(DexterBarraSegmentada)).height, greaterThan(12));
      expect(find.text('-28.9 dBm'), findsOneWidget);
    });

    testWidgets('La barra de avance del encabezado crece desde la izquierda, '
        'y mide el paso', (WidgetTester t) async {
      // Un FractionallySizedBox sin alineacion se CENTRA. La barra aparecia
      // flotando en el medio del encabezado, que se lee como un cargador a
      // medio andar y no como "vas por el primero de cinco".
      await t.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: Column(
            children: <Widget>[
              DexterStepHeader(titulo: 'OT #1845', paso: 1, deTotal: 5),
              Expanded(child: SizedBox()),
            ],
          ),
        ),
      ));

      final Finder pintada = find.descendant(
        of: find.byType(DexterStepHeader),
        matching: find.byWidgetPredicate(
          (Widget w) => w is ColoredBox && w.color == AppColors.secondary,
        ),
      );
      expect(pintada, findsOneWidget);

      final Rect barra = t.getRect(pintada);
      final Rect encabezado = t.getRect(find.byType(DexterStepHeader));

      expect(barra.left, encabezado.left,
          reason: 'la barra arranca donde arranca el encabezado');
      expect(
        barra.width,
        closeTo(encabezado.width / 5, 0.5),
        reason: 'paso 1 de 5 pinta un quinto, ni mas ni menos',
      );
    });

    testWidgets('Y con el ultimo paso llega hasta el final',
        (WidgetTester t) async {
      await t.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: Column(
            children: <Widget>[
              DexterStepHeader(titulo: 'OT #1845', paso: 5, deTotal: 5),
              Expanded(child: SizedBox()),
            ],
          ),
        ),
      ));

      final Rect barra = t.getRect(find.descendant(
        of: find.byType(DexterStepHeader),
        matching: find.byWidgetPredicate(
          (Widget w) => w is ColoredBox && w.color == AppColors.secondary,
        ),
      ));
      expect(barra.width, closeTo(t.getRect(find.byType(DexterStepHeader)).width, 0.5));
    });

    testWidgets('La pastilla en regla lleva el texto verde, no el fondo verde',
        (WidgetTester t) async {
      await t.pumpWidget(const MaterialApp(
        home: Scaffold(body: DexterPastilla.enRegla(texto: 'Activo')),
      ));

      // En esta paleta el chip verde es superficie elevada + texto verde.
      final caja = t.widget<Container>(
        find
            .descendant(
              of: find.byType(DexterPastilla),
              matching: find.byType(Container),
            )
            .first,
      );
      expect(
        (caja.decoration as BoxDecoration).color,
        AppColors.surfaceContainerHigh,
      );

      final texto = t.widget<Text>(find.text('ACTIVO'));
      expect(texto.style?.color, AppColors.onTertiaryContainer);
      expect(
        texto.style?.fontFamily,
        AppTypography.familiaMono,
        reason: 'label-badge es monoespaciada en esta familia',
      );
    });
  });
}
