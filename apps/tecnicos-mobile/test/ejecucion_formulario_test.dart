import 'package:campo/demo/field_mock_data.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/ejecucion/widgets/bloque_academia.dart';
import 'package:campo/features/ejecucion/widgets/formulario_de_campo.dart';
import 'package:flutter/material.dart';
import 'package:campo/features/ejecucion/campo_del_formulario.dart';
import 'package:flutter_test/flutter_test.dart';

/// El formulario de campo con el aspecto del diseño.
///
/// Lo que estas pruebas cuidan no es el aspecto: es que el aspecto no se haya
/// comido el contenido. Las preguntas siguen llegando del backend, la respuesta
/// que se reporta es exactamente la que el técnico tocó, y lo que todavía no
/// existe —la sugerencia de reemplazo, el medidor por Bluetooth— ni se ve fuera
/// de la demostración ni escribe una respuesta cuando se ve.
///
/// Corren igual en las dos compilaciones: cada caso dice explícitamente si
/// quiere los datos futuros, así que no dependen de `--dart-define`.

/// Un formulario como el que manda el backend: tres tipos de campo.
List<dynamic> _campos() => <dynamic>[
      <String, dynamic>{
        'clave': 'estado_luces',
        'etiqueta': 'Estado de luces físicas en ONT',
        'tipo': 'seleccion',
        'obligatorio': true,
        'opciones': <String>['Online', 'Offline', 'Intermitente'],
      },
      <String, dynamic>{
        'clave': 'requiere_cambio',
        'etiqueta': '¿Requiere cambio de conector o equipo?',
        'tipo': 'booleano',
        'ayuda': 'Sustitución física en sitio',
      },
      <String, dynamic>{
        'clave': 'potencia_rx',
        'etiqueta': 'Nueva medición en campo',
        'tipo': 'decimal',
        'unidad': 'dBm',
      },
    ];

Widget _enApp(Widget hijo) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: SingleChildScrollView(child: hijo)),
    );

void main() {
  late Map<String, dynamic> valores;
  late Map<String, dynamic> reportado;
  late Map<String, TextEditingController> controladores;

  setUp(() {
    valores = <String, dynamic>{};
    reportado = <String, dynamic>{};
    controladores = <String, TextEditingController>{
      for (final dynamic c in _campos())
        (c as Map<String, dynamic>)['clave'] as String: TextEditingController(),
    };
  });

  tearDown(() {
    for (final TextEditingController c in controladores.values) {
      c.dispose();
    }
  });

  Widget formulario({
    required bool datosFuturos,
    List<dynamic>? campos,
    void Function(void Function())? redibujar,
  }) {
    return StatefulBuilder(
      builder: (BuildContext context, void Function(void Function()) setState) {
        return FormularioDeCampo(
          // El widget recibe los campos ya interpretados: la lectura del
          // esquema vive en un solo lugar para toda la aplicacion.
          campos: CampoDelFormulario.normalizar(campos ?? _campos(), valores),
          valores: valores,
          controladores: controladores,
          mostrarDatosFuturos: datosFuturos,
          alCambiar: (String clave, dynamic valor) {
            setState(() {
              reportado[clave] = valor;
              valores[clave] = valor;
            });
          },
        );
      },
    );
  }

  group('Formulario de campo', () {
    testWidgets('1. Las preguntas siguen siendo las del backend, numeradas',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(formulario(datosFuturos: false)));
      await tester.pumpAndSettle();

      expect(find.text('Formulario de Validación'), findsOneWidget);
      expect(
        find.textContaining('1. Estado de luces físicas en ONT'),
        findsOneWidget,
      );
      // El diseño numera lo que se contesta eligiendo; el sí/no y la medición
      // van sin número, así la cuenta no salta a la vista.
      expect(find.textContaining('Nueva medición en campo'), findsOneWidget);
      expect(find.textContaining('2. Nueva medición'), findsNothing);
      expect(find.textContaining('3. Nueva medición'), findsNothing);
      expect(find.textContaining('2. ¿Requiere cambio'), findsNothing);
      // Las preguntas de la maqueta que no manda el backend no aparecen.
      expect(find.textContaining('SC/APC inspeccionados'), findsNothing);
    });

    testWidgets('2. Una selección se responde con botones, no con una lista',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(formulario(datosFuturos: false)));
      await tester.pumpAndSettle();

      expect(find.byType(DropdownButtonFormField<String>), findsNothing);
      for (final String opcion in <String>['Online', 'Offline', 'Intermitente']) {
        expect(find.byKey(Key('opcion-estado_luces-$opcion')), findsOneWidget);
      }

      await tester.tap(find.byKey(const Key('opcion-estado_luces-Intermitente')));
      await tester.pumpAndSettle();

      // El valor que sube es el de la opción, tal cual lo manda el backend.
      expect(reportado['estado_luces'], 'Intermitente');
      // Y queda marcada: el técnico ve qué contestó.
      expect(find.byIcon(Icons.check), findsOneWidget);
    });

    testWidgets('3. El campo obligatorio se distingue del que no lo es',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(formulario(datosFuturos: false)));
      await tester.pumpAndSettle();

      expect(find.textContaining('1. Estado de luces físicas en ONT *'), findsOneWidget);
      expect(find.textContaining('3. Nueva medición en campo *'), findsNothing);
    });

    testWidgets('4. El sí/no reporta el valor booleano',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(formulario(datosFuturos: false)));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('interruptor-requiere_cambio')));
      await tester.pumpAndSettle();
      expect(reportado['requiere_cambio'], true);

      await tester.tap(find.byKey(const Key('interruptor-requiere_cambio')));
      await tester.pumpAndSettle();
      expect(reportado['requiere_cambio'], false);
    });

    testWidgets('5. La medición se escribe como número, no como texto',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(formulario(datosFuturos: false)));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).last, '-21.4');
      await tester.pumpAndSettle();

      expect(reportado['potencia_rx'], -21.4);
      expect(find.text('dBm'), findsOneWidget);
    });

    testWidgets('6. En demostración, decir que sí muestra el equipo sugerido',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(formulario(datosFuturos: true)));
      await tester.pumpAndSettle();

      // Apagado, no hay sugerencia: nada de ejemplo aparece por su cuenta.
      expect(find.text(FieldMockData.equipoSugerido), findsNothing);

      await tester.tap(find.byKey(const Key('interruptor-requiere_cambio')));
      await tester.pumpAndSettle();

      expect(find.text('EQUIPO SUGERIDO PARA REEMPLAZO'), findsOneWidget);
      expect(find.text(FieldMockData.equipoSugerido), findsOneWidget);
      // Y la sugerencia no se guarda como respuesta del formulario.
      expect(reportado.keys, <String>['requiere_cambio']);
    });

    testWidgets('7. Fuera de la demostración no hay sugerencia ni medidor',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(formulario(datosFuturos: false)));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('interruptor-requiere_cambio')));
      await tester.pumpAndSettle();

      expect(
        find.text(FieldMockData.equipoSugerido),
        findsNothing,
        reason: 'un equipo de ejemplo se leeria como stock real en la camioneta',
      );
      expect(find.byKey(const Key('medidor-potencia_rx')), findsNothing);
      expect(find.text(FieldMockData.medidorBluetooth), findsNothing);
    });

    testWidgets('8. El medidor de ejemplo no escribe ninguna lectura',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(formulario(datosFuturos: true)));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('medidor-potencia_rx')), findsOneWidget);

      await tester.tap(find.byKey(const Key('medidor-potencia_rx')));
      await tester.pump();

      expect(
        reportado.containsKey('potencia_rx'),
        isFalse,
        reason: 'una medición inventada quedaría firmada por el técnico',
      );
      expect(controladores['potencia_rx']!.text, isEmpty);
      expect(find.textContaining('todavía no está integrado'), findsOneWidget);
    });

    testWidgets('11. El formulario registra la medicion, no la dictamina',
        (WidgetTester tester) async {
      // El veredicto de la señal sale de lo que mide la OLT, no de una
      // comparacion hecha en el telefono. Una sola regla, en un solo lugar
      // (veredictos.onu_signal_1490), y la pantalla del detalle ya la
      // muestra.
      //
      // Se llego a evaluar la lectura aca, con bandas que viajaban en la
      // plantilla, y se saco el 25/09/2026: eran dos reglas para la misma
      // señal, que es lo que este modulo viene arrastrando.
      await tester.pumpWidget(_enApp(formulario(datosFuturos: false)));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).last, '-28.9');
      await tester.pumpAndSettle();

      expect(find.textContaining('aceptable'), findsNothing);
      expect(find.textContaining('fuera de rango'), findsNothing);
      expect(find.textContaining('óptima'), findsNothing);

      // Y lo registra: una señal mala medida bien suele ser el motivo mismo
      // de la visita.
      expect(reportado['potencia_rx'], -28.9);
    });

    testWidgets('11b. Tampoco pregunta con que longitud de onda se midio',
        (WidgetTester tester) async {
      // 1550 nm es la portadora de video. No entra en una orden de internet,
      // y preguntarlo obligaba al tecnico a responder algo que no cambia
      // nada de lo que hace.
      await tester.pumpWidget(_enApp(formulario(datosFuturos: false)));
      await tester.pumpAndSettle();

      expect(find.textContaining('Longitud de onda'), findsNothing);
      expect(find.textContaining('1550'), findsNothing);
    });

    testWidgets('12. Pero un error de tipeo se sigue atrapando',
        (WidgetTester tester) async {
      // La guarda no es un umbral de calidad: -45 dBm no lo lee ningun
      // medidor en una ONT.
      await tester.pumpWidget(_enApp(formulario(
        datosFuturos: false,
        campos: <dynamic>[
          <String, dynamic>{
            'clave': 'potencia_rx',
            'etiqueta': 'Nueva medición en campo',
            'tipo': 'decimal',
            'unidad': 'dBm',
            'reglas': <String, dynamic>{'min': -40.0, 'max': -5.0},
          },
        ],
      )));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).last, '-45');
      await tester.pumpAndSettle();
      expect(find.textContaining('Tiene que ser -40.0 o más'), findsOneWidget);
    });

    testWidgets('9. Una orden sin formulario lo dice, no inventa preguntas',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _enApp(formulario(datosFuturos: true, campos: const <dynamic>[])),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('no trae formulario de campo'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
    });
  });

  group('Academia en la orden', () {
    testWidgets('10. Las cápsulas abren su guía y no tocan el formulario',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(const BloqueAcademia()));
      await tester.pumpAndSettle();

      expect(find.text('ACADEMIA DEXTER'), findsOneWidget);
      expect(find.text(FieldMockData.capsulasAcademia.first.titulo), findsOneWidget);

      await tester.tap(find.text(FieldMockData.capsulasAcademia.first.titulo));
      await tester.pumpAndSettle();

      expect(find.text('Guía de Campo Express'), findsOneWidget);
      expect(
        find.textContaining(FieldMockData.capsulasAcademia.first.pasos.first),
        findsOneWidget,
      );
    });
  });
}
