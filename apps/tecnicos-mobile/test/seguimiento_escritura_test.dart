import 'package:campo/features/detalle_orden/seguimiento_de_la_intervencion.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Los botones de reporte, y de dónde sale que existan.
///
/// LO QUE ESTE ARCHIVO DEFIENDE
/// ----------------------------
/// * **Solo se ofrece lo que la máquina permite.** La lista de botones no sale
///   de lo que sea cómodo mostrar: sale de `formularios` —lo que el tipo de
///   trabajo declaró— y de `momentos_registrados` —lo que ya ocurrió—. Un botón
///   que lleva a un rechazo es peor que no tenerlo: el técnico escribe el
///   reporte en la calle y lo pierde.
/// * **Sin a quién entregarlo, no hay botones.** Si `alReportar` es `null` la
///   sección queda en lectura, como en la Fase 1.
/// * **La hoja usa el formulario dinámico.** Los campos los declara el esquema y
///   se dibujan sin que esta pantalla sepa cuáles son.
/// * **Un obligatorio vacío no viaja.** Es cortesía, no la validación de verdad
///   —esa es del servidor— pero evita que el técnico escriba, mande, y recién
///   entonces se entere.
void main() {
  Future<void> montar(
    WidgetTester tester, {
    required Map<String, dynamic> seguimiento,
    void Function(
      String momento,
      Map<String, dynamic> respuestas, {
      bool requiereNoc,
      bool detener,
    })?
    alReportar,
    int pendientes = 0,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: SeguimientoDeLaIntervencion(
              seguimiento: seguimiento,
              cargando: false,
              alReportar: alReportar,
              pendientesDeSubir: pendientes,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Map<String, dynamic> conFormularios({
    List<String> momentos = const <String>[
      'inicio',
      'avance',
      'bloqueo',
      'cierre',
    ],
    List<String> yaOcurrio = const <String>[],
    List<Map<String, dynamic>>? campos,
  }) {
    return <String, dynamic>{
      'eventos': <dynamic>[],
      'momentos_registrados': yaOcurrio,
      'formularios': <String, dynamic>{
        for (final String m in momentos)
          m: <String, dynamic>{
            'momento': m,
            'campos':
                campos ??
                <Map<String, dynamic>>[
                  <String, dynamic>{
                    'id': 'nota',
                    'titulo': 'Qué pasó',
                    'tipo': 'texto',
                    'reglas': <String, dynamic>{'required': true},
                  },
                ],
          },
      },
    };
  }

  // SOBRE LAS MAYUSCULAS, QUE YA CONFUNDIERON DOS VECES
  // --------------------------------------------------
  // Los widgets del diseño no son uniformes, y es a proposito:
  //
  //   DexterAccionDominante  dibuja `texto.toUpperCase()`  (el boton grande)
  //   DexterAccionRapida     dibuja el texto tal cual      (los chips)
  //   DexterPastilla         dibuja `texto.toUpperCase()`
  //
  // Asi que el boton de guardar se busca en mayusculas y los de momento no. Se
  // deja escrito porque la primera version de estas pruebas fallo justo aca, y
  // el error estaba en la prueba.
  const String guardar = 'GUARDAR EL REPORTE';

  group('1. De dónde salen los botones', () {
    testWidgets('sin alReportar no hay ninguno: la sección queda en lectura', (
      WidgetTester tester,
    ) async {
      await montar(tester, seguimiento: conFormularios());

      expect(find.textContaining('Registrar'), findsNothing);
      expect(find.textContaining('Reportar'), findsNothing);
      expect(find.textContaining('Cerrar'), findsNothing);
    });

    testWidgets('con alReportar aparecen los cuatro momentos declarados', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: conFormularios(),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
      );

      expect(find.text('Registrar inicio'), findsOneWidget);
      expect(find.text('Registrar avance'), findsOneWidget);
      expect(find.text('Reportar bloqueo'), findsOneWidget);
      expect(find.text('Cerrar intervención'), findsOneWidget);
    });

    testWidgets('un momento que el tipo de trabajo NO declara no se ofrece', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        // Esta empresa no usa bloqueos en este tipo de trabajo.
        seguimiento: conFormularios(
          momentos: <String>['inicio', 'avance', 'cierre'],
        ),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
      );

      expect(find.text('Reportar bloqueo'), findsNothing);
      expect(find.text('Registrar avance'), findsOneWidget);
    });

    testWidgets('el INICIO desaparece después del primer INICIO', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: conFormularios(yaOcurrio: <String>['inicio_campo']),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
      );

      expect(
        find.text('Registrar inicio'),
        findsNothing,
        reason:
            'El servidor rechaza un segundo INICIO: ofrecerlo haría que el '
            'técnico escriba un reporte que se va a perder.',
      );
      expect(find.text('Registrar avance'), findsOneWidget);
    });
  });

  group('2. La hoja usa el formulario dinámico', () {
    testWidgets(
      'al tocar un momento aparecen los campos que declaró el esquema',
      (WidgetTester tester) async {
        await montar(
          tester,
          seguimiento: conFormularios(
            momentos: <String>['avance'],
            campos: <Map<String, dynamic>>[
              // Campos que nadie escribió en Flutter.
              <String, dynamic>{
                'id': 'presion_de_linea',
                'titulo': 'Presión de línea',
                'tipo': 'texto',
                'reglas': <String, dynamic>{'required': true},
              },
              <String, dynamic>{
                'id': 'observacion',
                'titulo': 'Observación',
                'tipo': 'texto',
              },
            ],
          ),
          alReportar: (
            _,
            _, {
            bool requiereNoc = false,
            bool detener = true,
          }) {},
        );

        await tester.tap(find.text('Registrar avance'));
        await tester.pumpAndSettle();

        expect(find.textContaining('Presión de línea'), findsWidgets);
        expect(find.textContaining('Observación'), findsWidgets);
        expect(find.text(guardar), findsOneWidget);
      },
    );

    testWidgets('dice que se guarda en el teléfono y sube cuando haya señal', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: conFormularios(momentos: <String>['avance']),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
      );

      await tester.tap(find.text('Registrar avance'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('sube cuando haya señal'),
        findsOneWidget,
        reason:
            'El técnico tiene que saber que su reporte no se perdió, '
            'aunque no haya red.',
      );
    });

    testWidgets('volver a tocar el mismo botón cierra la hoja', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: conFormularios(momentos: <String>['avance']),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
      );

      await tester.tap(find.text('Registrar avance'));
      await tester.pumpAndSettle();
      expect(find.text(guardar), findsOneWidget);

      await tester.tap(find.text('Registrar avance'));
      await tester.pumpAndSettle();
      expect(find.text(guardar), findsNothing);
    });
  });

  group('3. Un obligatorio vacío no viaja', () {
    testWidgets('guardar sin completar no llama a alReportar, y lo dice', (
      WidgetTester tester,
    ) async {
      bool llamado = false;
      await montar(
        tester,
        seguimiento: conFormularios(momentos: <String>['avance']),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {
          llamado = true;
        },
      );

      await tester.tap(find.text('Registrar avance'));
      await tester.pumpAndSettle();
      await tester.tap(find.text(guardar));
      await tester.pumpAndSettle();

      expect(
        llamado,
        isFalse,
        reason:
            'Es cortesía, no la validación de verdad: evita que el técnico '
            'escriba, mande y recién entonces se entere.',
      );
      expect(find.textContaining('Este campo es requerido'), findsWidgets);
    });

    testWidgets('con el obligatorio completo sí entrega el reporte', (
      WidgetTester tester,
    ) async {
      String? momentoRecibido;
      Map<String, dynamic>? respuestasRecibidas;

      await montar(
        tester,
        seguimiento: conFormularios(momentos: <String>['avance']),
        alReportar:
            (
              String momento,
              Map<String, dynamic> respuestas, {
              bool requiereNoc = false,
              bool detener = true,
            }) {
              momentoRecibido = momento;
              respuestasRecibidas = respuestas;
            },
      );

      await tester.tap(find.text('Registrar avance'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, 'revisé el empalme');
      await tester.pumpAndSettle();
      await tester.tap(find.text(guardar));
      await tester.pumpAndSettle();

      expect(momentoRecibido, 'avance');
      expect(respuestasRecibidas?['nota'], 'revisé el empalme');
    });
  });

  group('4. Los dos datos del bloqueo', () {
    testWidgets('el bloqueo ofrece las dos casillas, y son distintas', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: conFormularios(momentos: <String>['bloqueo']),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
      );

      await tester.tap(find.text('Reportar bloqueo'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Hace falta que el NOC haga algo'),
        findsOneWidget,
      );
      expect(find.textContaining('Detener el trabajo'), findsOneWidget);
      // Y se explica por qué no es lo mismo.
      expect(
        find.textContaining('está bloqueado igual, pero no es de esa mesa'),
        findsOneWidget,
      );
    });

    testWidgets('un avance NO ofrece esas casillas', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: conFormularios(momentos: <String>['avance']),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
      );

      await tester.tap(find.text('Registrar avance'));
      await tester.pumpAndSettle();

      expect(find.byType(Checkbox), findsNothing);
    });

    testWidgets('las casillas llegan al callback con su valor', (
      WidgetTester tester,
    ) async {
      bool? nocRecibido;
      bool? detenerRecibido;

      await montar(
        tester,
        seguimiento: conFormularios(momentos: <String>['bloqueo']),
        alReportar:
            (
              String momento,
              Map<String, dynamic> respuestas, {
              bool requiereNoc = false,
              bool detener = true,
            }) {
              nocRecibido = requiereNoc;
              detenerRecibido = detener;
            },
      );

      await tester.tap(find.text('Reportar bloqueo'));
      await tester.pumpAndSettle();
      // Se marca «requiere NOC» y se destilda «detener».
      await tester.tap(find.byType(Checkbox).first);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox).last);
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, 'sin acceso');
      await tester.pumpAndSettle();
      // La hoja del bloqueo es mas alta que la pantalla de prueba: hay que
      // desplazarse hasta el boton, igual que haria una persona.
      await tester.ensureVisible(find.text(guardar));
      await tester.pumpAndSettle();
      await tester.tap(find.text(guardar));
      await tester.pumpAndSettle();

      expect(nocRecibido, isTrue);
      expect(detenerRecibido, isFalse);
    });
  });

  group('5. Lo que espera subir se ve', () {
    testWidgets('un reporte sin subir se cuenta y se dice', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        seguimiento: conFormularios(),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
        pendientes: 1,
      );

      // «ESTA OT» AL PRINCIPIO: la cuenta ahora esta acotada a esta orden
      // (`contarSeguimientosPendientes` no filtraba por orden_id y devolvia
      // la cola entera del tecnico), y el texto lo dice para no confundirse
      // con la pastilla del encabezado, que cuenta la cola general.
      expect(
        find.textContaining('Esta OT: 1 reporte sin enviar'),
        findsOneWidget,
        reason:
            'Un reporte guardado y sin subir es un hecho que el técnico '
            'tiene que poder ver: si no, no sabe si el NOC se enteró.',
      );
    });

    testWidgets('con varios lo dice en plural', (WidgetTester tester) async {
      await montar(
        tester,
        seguimiento: conFormularios(),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
        pendientes: 3,
      );

      expect(
        find.textContaining('Esta OT: 3 reportes sin enviar'),
        findsOneWidget,
      );
    });

    testWidgets('sin pendientes no dice nada', (WidgetTester tester) async {
      await montar(
        tester,
        seguimiento: conFormularios(),
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
      );

      expect(find.textContaining('todavía no subió'), findsNothing);
      expect(find.textContaining('no subieron'), findsNothing);
    });
  });
  group('5. Cambiar de momento no arrastra lo escrito', () {
    testWidgets('lo tipeado en una hoja no aparece en la siguiente', (
      WidgetTester tester,
    ) async {
      // MEDIDO EN EL EMULADOR, 02/10/2026
      // ---------------------------------
      // Se escribio un BLOQUEO, se toco «Cerrar intervencion» sin guardar, y el
      // motivo del bloqueo aparecio dentro de «Que se hizo para resolverlo»,
      // listo para mandarse como respuesta a otra pregunta. Los dos formularios
      // declaran un campo con el mismo id, asi que para Flutter eran el mismo
      // widget y le reuso el estado.
      await montar(
        tester,
        seguimiento: conFormularios(momentos: <String>['bloqueo', 'cierre']),
        alReportar:
            (
              String momento,
              Map<String, dynamic> respuestas, {
              bool requiereNoc = false,
              bool detener = true,
            }) {},
      );

      await tester.tap(find.text('Reportar bloqueo'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, 'La casa cerrada');
      await tester.pumpAndSettle();

      // Se cambia de hoja SIN guardar.
      await tester.tap(find.text('Cerrar intervención'));
      await tester.pumpAndSettle();

      expect(find.text('La casa cerrada'), findsNothing);
    });
  });

  group('6. El reparto entre las dos pantallas', () {
    // POR QUE ESTO SE AFIRMA
    // ----------------------
    // Esta seccion hace dos cosas que ocurren en momentos distintos: LEER la
    // historia --«que paso en este trabajo»-- y ESCRIBIR un reporte --«se me
    // cayo un poste»--. Hasta el 02/10/2026 las hacia juntas en la ficha, y el
    // tecnico tenia que salir de la ejecucion, volver atras y bajar para
    // reportar un bloqueo.
    //
    // Ahora cada pantalla monta la MISMA seccion con su mitad. Las dos
    // direcciones se afirman: una sola se cumpliria escondiendo todo siempre.
    Future<void> montarCon(
      WidgetTester tester, {
      required bool historia,
      required bool bloqueo,
    }) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: SeguimientoDeLaIntervencion(
                seguimiento: <String, dynamic>{
                  'momentos_registrados': <String>[],
                  'formularios': <String, dynamic>{},
                  'eventos': <dynamic>[
                    <String, dynamic>{
                      'id': 'e1',
                      'tipo': 'avance_campo',
                      'etiqueta': 'Avance',
                      'es_seguimiento': true,
                      'quien': 'Carlos Gómez',
                      'detalle': <dynamic>[
                        <String, dynamic>{
                          'id': 'nota',
                          'titulo': 'Qué se hizo',
                          'valor': 'Se revisó la roseta',
                        },
                      ],
                    },
                  ],
                  'bloqueo_abierto': <String, dynamic>{
                    'requiere_noc': false,
                    'detuvo_el_trabajo': true,
                    'motivo': 'Poste caído',
                  },
                },
                cargando: false,
                mostrarHistoria: historia,
                mostrarBloqueoAbierto: bloqueo,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('la FICHA muestra la historia y el bloqueo', (
      WidgetTester tester,
    ) async {
      await montarCon(tester, historia: true, bloqueo: true);

      expect(find.text('Se revisó la roseta'), findsOneWidget);
      expect(find.text('TRABAJO DETENIDO'), findsOneWidget);
    });

    testWidgets('EJECUCIÓN no repite ninguna de las dos', (
      WidgetTester tester,
    ) async {
      // La historia se consulta, no se escribe; y el bloqueo abierto vive en la
      // ficha porque con el trabajo detenido no hay «Ejecutar el trabajo»: si
      // destrabar viviera acá, un trabajo bloqueado sería un callejón sin
      // salida.
      await montarCon(tester, historia: false, bloqueo: false);

      expect(find.text('Se revisó la roseta'), findsNothing);
      expect(find.text('TRABAJO DETENIDO'), findsNothing);
    });

    testWidgets('sin historia tampoco se dice «no hay reportes»', (
      WidgetTester tester,
    ) async {
      // Ese texto es de la ficha: en ejecución diría que no hay historia en una
      // pantalla que no la muestra.
      await montarCon(tester, historia: false, bloqueo: false);

      expect(
        find.textContaining('Todavía no hay reportes de campo'),
        findsNothing,
      );
    });
  });

}
