import 'package:campo/features/detalle_orden/seguimiento_de_la_intervencion.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// La pantalla del seguimiento, y la promesa que tiene que cumplir.
///
/// LA PRUEBA QUE DA SENTIDO A TODO EL OBJETIVO
/// -------------------------------------------
/// «Un esquema nuevo no exige una versión móvil nueva». Acá se afirma sobre el
/// dato: se le pasa un evento de un tipo que esta aplicación **nunca vio**, con
/// campos que nadie escribió en Flutter, y se comprueba que los dibuja.
///
/// Si esta prueba se rompe, la arquitectura del objetivo era falsa.
///
/// LO OTRO QUE SE DEFIENDE
/// -----------------------
/// * **Desconocido no es vacío.** Sin descarga previa dice que no está
///   disponible *en este dispositivo*, y aclara que eso no significa que el
///   trabajo no tenga reportes. Una lista vacía diría lo contrario.
/// * **No hay botones de acción.** La Fase 1 es lectura: un «Registrar avance»
///   que abriera un formulario incapaz de guardar sería peor que no tenerlo,
///   porque el técnico lo llenaría en la calle y lo perdería.
/// * **Las dos horas se distinguen.** Cuando un reporte se escribió sin señal,
///   se ve la hora del teléfono y la demora — y lo que gobierna el seguimiento
///   sigue siendo la llegada al servidor.
void main() {
  Future<void> montar(
    WidgetTester tester, {
    Map<String, dynamic>? seguimiento,
    bool cargando = false,
    bool actualizado = true,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: SeguimientoDeLaIntervencion(
              seguimiento: seguimiento,
              cargando: cargando,
              actualizado: actualizado,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  // NOTA SOBRE LAS MAYUSCULAS
  // ------------------------
  // `DexterPastilla` dibuja `texto.toUpperCase()`: es una decision de su diseño.
  // Por eso la etiqueta se busca en mayusculas. Se deja dicho porque la primera
  // version de estas pruebas fallo justo por eso, y el error estaba en la prueba.
  String enPastilla(String texto) => texto.toUpperCase();

  group('1. Desconocido no es vacío', () {
    testWidgets(
      'sin descarga previa lo dice, y aclara que no es "sin historia"',
      (WidgetTester tester) async {
        await montar(tester, seguimiento: null);

        expect(
          find.textContaining('todavía no está disponible en este dispositivo'),
          findsOneWidget,
        );
        expect(
          find.textContaining(
            'no quiere decir que el trabajo no tenga reportes',
          ),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'con descarga y sin eventos dice que no hay reportes, que es otra cosa',
      (WidgetTester tester) async {
        await montar(
          tester,
          seguimiento: <String, dynamic>{
            'eventos': <dynamic>[],
            'salud': <String, dynamic>{'tipo': 'al_dia', 'etiqueta': 'Al día'},
          },
        );

        expect(
          find.textContaining('Todavía no hay reportes de campo'),
          findsOneWidget,
        );
        expect(
          find.textContaining('no está disponible en este dispositivo'),
          findsNothing,
        );
      },
    );
  });

  group('2. LA PROMESA: dibuja lo que no conoce', () {
    testWidgets(
      'un tipo de evento inventado se muestra con su etiqueta y sus campos',
      (WidgetTester tester) async {
        await montar(
          tester,
          seguimiento: <String, dynamic>{
            'eventos': <dynamic>[
              <String, dynamic>{
                'id': 'ex1',
                // Ni este tipo ni estos campos existen en ninguna parte de la app.
                'tipo': 'medicion_extraordinaria',
                'etiqueta': 'Medición extraordinaria',
                'severidad': 'atencion',
                'es_seguimiento': true,
                'recibido_en': '2026-10-01T09:00:00Z',
                'detalle': <dynamic>[
                  <String, dynamic>{
                    'id': 'presion',
                    'titulo': 'Presión del equipo',
                    'valor': '2.4',
                  },
                  <String, dynamic>{
                    'id': 'temperatura_carcasa',
                    'titulo': 'Temperatura de la carcasa',
                    'valor': '41',
                  },
                ],
              },
            ],
          },
        );

        expect(
          find.text(enPastilla('Medición extraordinaria')),
          findsOneWidget,
        );
        expect(find.text('Presión del equipo'), findsOneWidget);
        expect(find.text('2.4'), findsOneWidget);
        expect(find.text('Temperatura de la carcasa'), findsOneWidget);
        expect(find.text('41'), findsOneWidget);
      },
    );

    testWidgets('una severidad desconocida degrada en vez de romper', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: <String, dynamic>{
          'eventos': <dynamic>[
            <String, dynamic>{
              'id': 'x',
              'tipo': 'lo_que_sea',
              'etiqueta': 'Lo que sea',
              'severidad': 'catastrofe_cosmica',
              'recibido_en': '2026-10-01T09:00:00Z',
              'detalle': <dynamic>[],
            },
          ],
        },
      );

      // Se dibuja, neutra. El backend puede agregar valores sin esperar a que
      // se publique una versión nueva de la app.
      expect(find.text(enPastilla('Lo que sea')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('un evento sin etiqueta cae al tipo, y no deja un hueco', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: <String, dynamic>{
          'eventos': <dynamic>[
            <String, dynamic>{
              'id': 'y',
              'tipo': 'algo_sin_etiqueta',
              'recibido_en': '2026-10-01T09:00:00Z',
              'detalle': <dynamic>[],
            },
          ],
        },
      );

      expect(find.text(enPastilla('algo_sin_etiqueta')), findsOneWidget);
    });
  });

  group('3. Las dos horas', () {
    testWidgets('un reporte escrito sin señal muestra la demora', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: <String, dynamic>{
          'eventos': <dynamic>[
            <String, dynamic>{
              'id': 'off1',
              'tipo': 'avance_campo',
              'etiqueta': 'AVANCE',
              'severidad': 'info',
              'recibido_en': '2026-10-01T09:47:00Z',
              'capturado_en_dispositivo': '2026-10-01T08:00:00Z',
              'detalle': <dynamic>[],
            },
          ],
        },
      );

      expect(
        find.textContaining('demora de sincronización'),
        findsOneWidget,
        reason:
            'La demora se muestra como dato. Lo que gobierna el '
            'seguimiento sigue siendo la llegada al servidor.',
      );
      expect(find.textContaining('1 h 47 min'), findsOneWidget);
    });

    testWidgets(
      'si se escribió y llegó a la misma hora, no se inventa una demora',
      (WidgetTester tester) async {
        await montar(
          tester,
          seguimiento: <String, dynamic>{
            'eventos': <dynamic>[
              <String, dynamic>{
                'id': 'on1',
                'tipo': 'avance_campo',
                'etiqueta': 'AVANCE',
                'recibido_en': '2026-10-01T09:00:30Z',
                'capturado_en_dispositivo': '2026-10-01T09:00:00Z',
                'detalle': <dynamic>[],
              },
            ],
          },
        );

        expect(find.textContaining('demora de sincronización'), findsNothing);
        expect(find.textContaining('misma hora'), findsOneWidget);
      },
    );
  });

  group('4. El estado del espejo', () {
    testWidgets('cuando no se pudo actualizar, lo dice sin borrar lo que hay', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        actualizado: false,
        seguimiento: <String, dynamic>{
          'eventos': <dynamic>[
            <String, dynamic>{
              'id': 'e1',
              'tipo': 'inicio_campo',
              'etiqueta': 'INICIO',
              'recibido_en': '2026-10-01T08:14:00Z',
              'detalle': <dynamic>[],
            },
          ],
          'salud': <String, dynamic>{'tipo': 'al_dia', 'etiqueta': 'Al día'},
        },
      );

      expect(
        find.textContaining('No se pudo actualizar ahora'),
        findsOneWidget,
      );
      // Y la historia sigue ahí: es el punto.
      expect(find.text(enPastilla('INICIO')), findsOneWidget);
    });

    testWidgets('muestra la hora de la última sincronización', (
      WidgetTester tester,
    ) async {
      final int hace5min = DateTime.now()
          .subtract(const Duration(minutes: 5))
          .millisecondsSinceEpoch;

      await montar(
        tester,
        seguimiento: <String, dynamic>{
          'eventos': <dynamic>[],
          'sincronizado_en': hace5min,
        },
      );

      expect(find.textContaining('Última sincronización:'), findsOneWidget);
    });

    testWidgets('el veredicto de salud se muestra con el texto del servidor', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: <String, dynamic>{
          'eventos': <dynamic>[],
          // El texto lo decide el backend porque ES el veredicto: «sin
          // sincronización reciente» no es lo mismo que «no reportó».
          'salud': <String, dynamic>{
            'tipo': 'sin_contacto_reciente',
            'etiqueta': 'Sin sincronización reciente',
          },
        },
      );

      expect(
        find.text(enPastilla('Sin sincronización reciente')),
        findsOneWidget,
      );
    });
  });

  group('5. La Fase 1 es lectura', () {
    testWidgets('no hay ningún botón de acción en la sección', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: <String, dynamic>{
          'eventos': <dynamic>[
            <String, dynamic>{
              'id': 'e1',
              'tipo': 'inicio_campo',
              'etiqueta': 'INICIO',
              'recibido_en': '2026-10-01T08:14:00Z',
              'detalle': <dynamic>[],
            },
          ],
          // El backend ya manda los formularios; la pantalla NO los ofrece todavía.
          'formularios': <String, dynamic>{
            'avance': <String, dynamic>{
              'campos': <dynamic>[
                <String, dynamic>{
                  'id': 'nota',
                  'titulo': 'Nota',
                  'tipo': 'texto',
                },
              ],
            },
          },
        },
      );

      expect(find.byType(ElevatedButton), findsNothing);
      expect(find.byType(TextButton), findsNothing);
      expect(find.byType(OutlinedButton), findsNothing);
      expect(
        find.textContaining('Registrar'),
        findsNothing,
        reason:
            'Un botón que abre un formulario incapaz de guardar hace que el '
            'técnico lo llene en la calle y lo pierda.',
      );
    });
  });
}
