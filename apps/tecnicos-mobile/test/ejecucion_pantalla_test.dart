import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/ejecucion/datos_de_ejecucion.dart';
import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

/// La pantalla de ejecución, dibujada sin base y sin sesión.
///
/// POR QUÉ ESTO NO EXISTÍA ANTES
/// -----------------------------
/// Porque la pantalla leía SQLite y el almacenamiento seguro por su cuenta.
/// Montarla exigía levantar la base entera, y mezclar eso con pruebas de
/// widget ya colgó la suite de este proyecto una vez, así que la pantalla
/// donde el técnico pasa la mayor parte de su día era la única sin pruebas de
/// interfaz.
///
/// Ahora recibe [FuenteDeEjecucion]. En la aplicación es la base; acá es un
/// fixture con la misma forma —filas en `snake_case` y JSON en texto, como
/// llegan de verdad— para que lo que se prueba no sea una versión amable de
/// los datos.
void main() {
  Widget app(FuenteDeEjecucionFalsa fuente) => MaterialApp(
        theme: AppTheme.lightTheme,
        home: EjecucionScreen(
          ordenId: 'ot-1',
          fuente: fuente,
          // El chip de la cola tambien se inyecta: si no, consulta el
          // almacenamiento seguro al montarse y la prueba muere antes de
          // dibujar nada.
          resumenDeSync: const SyncSummary(
            status: SyncStatus.idle,
            isSyncing: false,
            hasConnectionError: false,
            mutacionesPendientes: 0,
            mutacionesConflicto: 0,
            evidenciasPendientes: 0,
            datosDirty: 0,
          ),
        ),
      );

  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  group('1. Se dibuja con los datos que le dan', () {
    testWidgets('El formulario sale de la plantilla de la orden',
        (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa()));
      await t.pumpAndSettle();

      expect(find.textContaining('4832'), findsWidgets);
      expect(find.textContaining('Potencia óptica en roseta'), findsWidgets);
      expect(find.textContaining('Tipo de intervención'), findsWidgets);
    });

    testWidgets('Sin sesión no inventa una orden', (WidgetTester t) async {
      // Queda en su estado de carga. Dibujar una orden vacía seria peor:
      // alguien la completaria creyendo que es la suya.
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(sinIdentidad: true)));
      await t.pumpAndSettle();

      expect(find.textContaining('Potencia óptica'), findsNothing);
    });

    testWidgets('Si la orden no bajó todavía, tampoco', (WidgetTester t) async {
      pantallaAlta(t);
      await t.pumpWidget(app(FuenteDeEjecucionFalsa(sinOrden: true)));
      await t.pumpAndSettle();

      expect(find.textContaining('Potencia óptica'), findsNothing);
    });
  });

  group('2. Lo que se escribe se guarda apenas se escribe', () {
    testWidgets('Un campo de texto llega a la fuente sin apretar nada',
        (WidgetTester t) async {
      // Sin esperar a un botón "guardar": el teléfono se puede quedar sin
      // batería en mitad de un formulario.
      pantallaAlta(t);
      final FuenteDeEjecucionFalsa fuente = FuenteDeEjecucionFalsa();
      await t.pumpWidget(app(fuente));
      await t.pumpAndSettle();

      await t.enterText(find.byType(TextField).first, '-18.4');
      await t.pumpAndSettle();

      expect(fuente.guardados, isNotEmpty);
      // Se guarda como numero, no como texto: el campo es de tipo numero y
      // la pantalla lo convierte antes de persistirlo.
      expect(fuente.guardados.last['valor'].toString(), '-18.4');
      expect(fuente.resumenesRefrescados, greaterThan(0),
          reason: 'la cola tiene que volver a contar lo pendiente');
    });
  });

  group('3. Las reglas de cierre se pueden probar sin dibujar nada', () {
    // Viven en DatosDeEjecucion, no en el widget: son las que deciden si el
    // trabajo se puede dar por terminado.
    DatosDeEjecucion datos({
      Map<String, dynamic>? valores,
      List<Map<String, dynamic>>? evidencias,
      List<Map<String, dynamic>>? materiales,
    }) =>
        DatosDeEjecucion(
          orgId: 'org',
          profileId: 'perfil',
          orden: const <String, dynamic>{'numero': 4832, 'revision': 7},
          campos: FuenteDeEjecucionFalsa.camposTipicos,
          requisitosDeEvidencia: FuenteDeEjecucionFalsa.requisitosTipicos,
          valores: valores ?? <String, dynamic>{},
          evidenciasCapturadas: evidencias ?? <Map<String, dynamic>>[],
          materialesUsados: materiales ?? <Map<String, dynamic>>[],
        );

    test('Faltan los obligatorios vacíos, con su etiqueta', () {
      final List<String> faltan = datos().camposObligatoriosSinLlenar;

      expect(faltan, hasLength(2));
      expect(faltan.first, 'Potencia óptica en roseta (dBm)');
      expect(
        faltan,
        isNot(contains('Observaciones técnicas')),
        reason: 'ese campo no es obligatorio',
      );
    });

    test('Un obligatorio con espacios sigue estando vacío', () {
      final List<String> faltan = datos(
        valores: <String, dynamic>{'potencia_rx': '   '},
      ).camposObligatoriosSinLlenar;

      expect(faltan, contains('Potencia óptica en roseta (dBm)'));
    });

    test('La plantilla pide firma, y se nota si no está', () {
      expect(datos().exigeFirma, isTrue);
      expect(datos().hayFirma, isFalse);
    });

    test('Una firma tomada pero sin subir se distingue de una confirmada', () {
      // No es lo mismo: una firma que espera señal ya existe y el trabajo
      // puede cerrarse; una que no se tomó, no.
      final DatosDeEjecucion pendiente = datos(evidencias: <Map<String, dynamic>>[
        FuenteDeEjecucionFalsa.evidencia(
          requisitoId: 'firma_cliente',
          estado: 'pendiente',
        ),
      ]);
      final DatosDeEjecucion confirmada = datos(evidencias: <Map<String, dynamic>>[
        FuenteDeEjecucionFalsa.evidencia(requisitoId: 'firma_cliente'),
      ]);

      expect(pendiente.hayFirma, isTrue);
      expect(pendiente.firmaSinSubir, isTrue);
      expect(confirmada.hayFirma, isTrue);
      expect(confirmada.firmaSinSubir, isFalse);
    });

    test('Con todo hecho, el cierre deja de objetar', () {
      final DatosDeEjecucion completo = datos(
        valores: <String, dynamic>{
          'potencia_rx': '-18.4',
          'tipo_intervencion': 'Reconectorización',
        },
        evidencias: <Map<String, dynamic>>[
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_roseta'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'foto_medicion'),
          FuenteDeEjecucionFalsa.evidencia(requisitoId: 'firma_cliente'),
        ],
        materiales: <Map<String, dynamic>>[
          FuenteDeEjecucionFalsa.material(),
        ],
      );

      expect(completo.camposObligatoriosSinLlenar, isEmpty);
      expect(completo.cierre.puedeCerrar, isTrue);
    });

    test('Sin nada hecho, no', () {
      expect(datos().cierre.puedeCerrar, isFalse);
    });

    test('El número y la revisión salen de la fila, no de otro lado', () {
      // La revisión viaja en la transición para que el servidor detecte si
      // alguien movió la orden mientras tanto.
      expect(datos().numeroDeOrden, 4832);
      expect(datos().revision, 7);
    });
  });
}
