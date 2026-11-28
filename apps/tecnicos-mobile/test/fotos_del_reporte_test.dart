import 'package:campo/core/storage/local_database.dart';
import 'package:campo/features/detalle_orden/hoja_de_reporte.dart';
import 'package:campo/features/detalle_orden/seguimiento_de_la_intervencion.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' show join;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// La foto que pertenece a un reporte, y el orden que la hace posible.
///
/// EL PROBLEMA QUE RESUELVE ESTE ARCHIVO
/// -------------------------------------
/// La foto se saca **antes** de que el reporte suba. En ese instante el evento
/// del servidor no existe, así que la foto no se puede registrar: el backend la
/// rechazaría por pertenecer a un id que nadie creó.
///
/// La cadena es: la foto nace con el id de un **borrador** → al guardar se
/// repunta al reporte encolado → cuando ese reporte sube, el servidor devuelve
/// el id del evento y recién ahí la foto se vuelve visible para la
/// sincronización.
///
/// Cada eslabón se afirma acá, y también lo que pasa cuando se corta:
///
/// * una foto atada a un reporte que no subió **no se intenta** — reintentarla
///   sería gastar batería contra un 400 seguro;
/// * una foto del checklist (sin reporte) **sigue subiendo sin esperar a
///   nadie**, que es como funcionaba antes de la Fase 4;
/// * un borrador que se abandona **se tira**, con su archivo: una foto que no se
///   puede ver ni se puede subir es basura en el teléfono de alguien que
///   trabaja en la calle;
/// * y el reporte **se guarda igual sin la foto**, que es la decisión de
///   producto de esta fase.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  LocalDatabase.usarBaseDePruebas('pruebas_fotos_reporte.db');

  late LocalDatabase base;

  setUp(() async {
    LocalDatabase.resetForTesting();
    base = LocalDatabase();
  });

  tearDown(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(
        await databaseFactory.getDatabasesPath(),
        'pruebas_fotos_reporte.db',
      ),
    );
  });

  Future<void> encolarFoto({
    required String id,
    String requisito = 'foto_del_obstaculo',
    String? reporteLocalId,
  }) {
    return base.encolarEvidencia(
      id: id,
      orgId: 'org-1',
      profileId: 'prof-1',
      ordenId: 'ot-1',
      requisitoId: requisito,
      archivoPath: '/tmp/$id.jpg',
      sha256: 'sha-$id',
      tamanoBytes: 1000,
      mimeType: 'image/jpeg',
      reporteLocalId: reporteLocalId,
    );
  }

  Future<List<String>> idsPendientes() async {
    final filas = await base.getEvidenciasPendientes(
      orgId: 'org-1',
      profileId: 'prof-1',
    );
    return filas.map((f) => f['id'] as String).toList();
  }

  group('1. Una foto no sube antes que su reporte', () {
    test('atada a un reporte sin subir, no aparece como pendiente', () async {
      await encolarFoto(id: 'f1', reporteLocalId: 'borrador-1');

      expect(await idsPendientes(), isEmpty);
    });

    test('sellada con el evento, sí aparece', () async {
      await encolarFoto(id: 'f1', reporteLocalId: 'rep-1');

      final int sellados = await base.sellarEvidenciasDelReporte(
        reporteLocalId: 'rep-1',
        eventoId: 'evt-999',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(sellados, 1);
      expect(await idsPendientes(), <String>['f1']);
    });

    test('la foto del checklist no espera a nadie', () async {
      // Es como funcionaba antes de la Fase 4, y tiene que seguir igual: sin
      // reporte, sube en la primera pasada.
      await encolarFoto(id: 'f-checklist');

      expect(await idsPendientes(), <String>['f-checklist']);
    });

    test('sellar lleva el evento a la fila, que es lo que viaja', () async {
      await encolarFoto(id: 'f1', reporteLocalId: 'rep-1');
      await base.sellarEvidenciasDelReporte(
        reporteLocalId: 'rep-1',
        eventoId: 'evt-42',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      final filas = await base.getEvidenciasPendientes(
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(filas.single['evento_id'], 'evt-42');
    });

    test('sellar dos veces no vuelve a tocar lo ya sellado', () async {
      // El segundo intento tiene que contar CERO: si contara uno, quien llama
      // volvería a correr la cola de evidencias cada vez, para nada.
      await encolarFoto(id: 'f1', reporteLocalId: 'rep-1');
      await base.sellarEvidenciasDelReporte(
        reporteLocalId: 'rep-1',
        eventoId: 'evt-1',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      final int otra = await base.sellarEvidenciasDelReporte(
        reporteLocalId: 'rep-1',
        eventoId: 'evt-2',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(otra, 0);
      final filas = await base.getEvidenciasPendientes(
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      expect(filas.single['evento_id'], 'evt-1');
    });
  });

  group('2. Del borrador al reporte', () {
    test('repuntar deja la foto lista para sellarse', () async {
      await encolarFoto(id: 'f1', reporteLocalId: 'borrador-7');

      await base.reasignarEvidenciasDeBorrador(
        borradorId: 'borrador-7',
        reporteLocalId: 'seg-ot-1-bloqueo-123',
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      final int sellados = await base.sellarEvidenciasDelReporte(
        reporteLocalId: 'seg-ot-1-bloqueo-123',
        eventoId: 'evt-7',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(sellados, 1);
      expect(await idsPendientes(), <String>['f1']);
    });

    test('sin repuntar, el sello no la encuentra', () async {
      // La otra dirección: si el repunte faltara, la foto quedaría esperando un
      // reporte que nunca la va a nombrar. Una sola de las dos pruebas se
      // cumpliría sola.
      await encolarFoto(id: 'f1', reporteLocalId: 'borrador-7');

      final int sellados = await base.sellarEvidenciasDelReporte(
        reporteLocalId: 'seg-ot-1-bloqueo-123',
        eventoId: 'evt-7',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(sellados, 0);
      expect(await idsPendientes(), isEmpty);
    });

    test('repuntar no toca el borrador de otra hoja', () async {
      await encolarFoto(id: 'f1', reporteLocalId: 'borrador-a');
      await encolarFoto(id: 'f2', reporteLocalId: 'borrador-b');

      await base.reasignarEvidenciasDeBorrador(
        borradorId: 'borrador-a',
        reporteLocalId: 'rep-a',
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      await base.sellarEvidenciasDelReporte(
        reporteLocalId: 'rep-a',
        eventoId: 'evt-a',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(await idsPendientes(), <String>['f1']);
    });
  });

  group('3. Un borrador abandonado no deja basura', () {
    test('descartar borra la fila', () async {
      await encolarFoto(id: 'f1', reporteLocalId: 'borrador-x');

      final int borradas = await base.descartarEvidenciasDeBorrador(
        borradorId: 'borrador-x',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(borradas, 1);
      expect(
        await base.contarEvidenciasDelReporte(
          reporteLocalId: 'borrador-x',
          orgId: 'org-1',
          profileId: 'prof-1',
        ),
        0,
      );
    });

    test('descartar NO toca las fotos del checklist', () async {
      // Están en la misma tabla. Un borrado por identidad y no por borrador se
      // llevaría por delante evidencia que nadie pidió tirar.
      await encolarFoto(id: 'f-checklist');
      await encolarFoto(id: 'f1', reporteLocalId: 'borrador-x');

      await base.descartarEvidenciasDeBorrador(
        borradorId: 'borrador-x',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(await idsPendientes(), <String>['f-checklist']);
    });

    test('descartar un borrador de otra cuenta no borra nada', () async {
      await encolarFoto(id: 'f1', reporteLocalId: 'borrador-x');

      final int borradas = await base.descartarEvidenciasDeBorrador(
        borradorId: 'borrador-x',
        orgId: 'org-OTRA',
        profileId: 'prof-1',
      );

      expect(borradas, 0);
    });
  });

  group('4. La hoja pide la foto, pero no retiene el reporte', () {
    Future<void> montar(
      WidgetTester tester, {
      required List<Map<String, dynamic>> evidencias,
      Future<void> Function(String)? alTomarFoto,
      Map<String, int> fotos = const <String, int>{},
      void Function(
        Map<String, dynamic>, {
        bool requiereNoc,
        bool detener,
      })?
      alGuardar,
    }) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: HojaDeReporte(
                momento: 'bloqueo',
                titulo: 'Reportar un bloqueo',
                campos: const <Map<String, dynamic>>[],
                evidencias: evidencias,
                alTomarFoto: alTomarFoto,
                fotosTomadas: fotos,
                alGuardar:
                    alGuardar ??
                    (
                      Map<String, dynamic> _, {
                      bool requiereNoc = false,
                      bool detener = true,
                    }) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    const List<Map<String, dynamic>> pideUna = <Map<String, dynamic>>[
      <String, dynamic>{
        'id': 'foto_del_obstaculo',
        'titulo': 'Foto de lo que impide seguir',
      },
    ];

    testWidgets('muestra lo que el tipo de trabajo pide fotografiar', (
      WidgetTester tester,
    ) async {
      await montar(tester, evidencias: pideUna, alTomarFoto: (String _) async {});

      expect(find.text('Foto de lo que impide seguir'), findsOneWidget);
      expect(find.text('Tomar foto'), findsOneWidget);
    });

    testWidgets('un reporte sin fotos declaradas no muestra nada de esto', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        evidencias: const <Map<String, dynamic>>[],
        alTomarFoto: (String _) async {},
      );

      expect(find.text('Fotos de este reporte'), findsNothing);
      expect(find.textContaining('Tomar foto'), findsNothing);
    });

    testWidgets('dice cuántas van, y cambia el botón', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        evidencias: pideUna,
        alTomarFoto: (String _) async {},
        fotos: const <String, int>{'foto_del_obstaculo': 2},
      );

      expect(find.text('2 fotos tomadas'), findsOneWidget);
      expect(find.text('Tomar otra'), findsOneWidget);
    });

    testWidgets('pide el requisito por su id, no por su título', (
      WidgetTester tester,
    ) async {
      String? pedido;
      await montar(
        tester,
        evidencias: pideUna,
        alTomarFoto: (String r) async => pedido = r,
      );

      await tester.tap(find.text('Tomar foto'));
      await tester.pumpAndSettle();

      expect(pedido, 'foto_del_obstaculo');
    });

    testWidgets('SIN foto, el reporte se guarda igual', (
      WidgetTester tester,
    ) async {
      // LA DECISIÓN DE PRODUCTO DE LA FASE 4, afirmada donde se puede romper.
      // El texto es lo que destraba al NOC: tiene que llegar aunque la cámara
      // falle. Si alguien hiciera obligatoria la foto, esta prueba lo dice.
      bool guardo = false;
      await montar(
        tester,
        evidencias: pideUna,
        alTomarFoto: (String _) async {},
        alGuardar:
            (
              Map<String, dynamic> _, {
              bool requiereNoc = false,
              bool detener = true,
            }) {
              guardo = true;
            },
      );

      await tester.tap(find.text('GUARDAR EL REPORTE'));
      await tester.pumpAndSettle();

      expect(guardo, isTrue);
      expect(find.textContaining('Todavía no hay foto'), findsOneWidget);
    });

    testWidgets('sin quién reciba la foto, no se ofrece y se dice', (
      WidgetTester tester,
    ) async {
      await montar(tester, evidencias: pideUna, alTomarFoto: null);

      expect(find.text('Tomar foto'), findsNothing);
      expect(find.textContaining('no se pueden tomar fotos'), findsOneWidget);
    });
  });
  group('5. La bitácora dice qué foto hay y cuál falta', () {
    Future<void> conEvento(
      WidgetTester tester, {
      required List<Map<String, dynamic>> evidencias,
      required List<Map<String, dynamic>> declaradas,
    }) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: SeguimientoDeLaIntervencion(
                seguimiento: <String, dynamic>{
                  'momentos_registrados': <String>['bloqueo'],
                  'formularios': <String, dynamic>{},
                  'eventos': <dynamic>[
                    <String, dynamic>{
                      'id': 'e1',
                      'tipo': 'bloqueo_campo',
                      'etiqueta': 'Bloqueo',
                      'es_seguimiento': true,
                      'quien': 'Carlos Gómez',
                      'detalle': <dynamic>[],
                      'evidencias': evidencias,
                      'evidencias_declaradas': declaradas,
                    },
                  ],
                },
                cargando: false,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('una foto que llegó se nombra', (WidgetTester tester) async {
      await conEvento(
        tester,
        evidencias: <Map<String, dynamic>>[
          <String, dynamic>{
            'requisito_id': 'foto_del_obstaculo',
            'disponible': true,
          },
        ],
        declaradas: <Map<String, dynamic>>[
          <String, dynamic>{'id': 'foto_del_obstaculo', 'titulo': 'El obstáculo'},
        ],
      );

      // El título lo declara el tipo de trabajo; el servidor manda el id.
      expect(find.text('El obstáculo'), findsOneWidget);
      expect(find.text('foto_del_obstaculo'), findsNothing);
      expect(find.textContaining('Falta la foto'), findsNothing);
    });

    testWidgets('una que todavía sube NO se declara disponible', (
      WidgetTester tester,
    ) async {
      await conEvento(
        tester,
        evidencias: <Map<String, dynamic>>[
          <String, dynamic>{
            'requisito_id': 'foto_del_obstaculo',
            'disponible': false,
          },
        ],
        declaradas: const <Map<String, dynamic>>[],
      );

      expect(find.textContaining('subiendo'), findsOneWidget);
    });

    testWidgets('una que se pedía y no está, se dice', (
      WidgetTester tester,
    ) async {
      // Es la razón de que el backend mande las dos listas: sin esto, un bloqueo
      // sin foto y uno al que nunca se le pidió una se leen igual.
      await conEvento(
        tester,
        evidencias: const <Map<String, dynamic>>[],
        declaradas: <Map<String, dynamic>>[
          <String, dynamic>{'id': 'foto_del_obstaculo', 'titulo': 'El obstáculo'},
        ],
      );

      expect(find.text('Falta la foto: El obstáculo'), findsOneWidget);
    });

    testWidgets('un reporte al que no se le pidió foto no dice nada', (
      WidgetTester tester,
    ) async {
      await conEvento(
        tester,
        evidencias: const <Map<String, dynamic>>[],
        declaradas: const <Map<String, dynamic>>[],
      );

      expect(find.textContaining('Falta la foto'), findsNothing);
      expect(find.textContaining('subiendo'), findsNothing);
    });
  });

  group('6. La foto sobrevive a que la cámara destruya la pantalla', () {
    // EL DEFECTO QUE ENCONTRO EL EMULADOR (02/10/2026)
    // -----------------------------------------------
    // Abrir la cámara en Android puede destruir la pantalla que la abrió. Al
    // volver, Flutter la reconstruye con estado nuevo. Con un borrador sorteado
    // en memoria y un contador en memoria, la foto quedaba HUÉRFANA: no subía
    // --no tenía evento-- y no se descartaba --nadie recordaba su id--; la hoja
    // decía «todavía no hay foto» con la foto encolada.
    //
    // Por eso el borrador se deriva de la orden y el momento, y la cuenta sale
    // del disco. Acá se simula la reconstrucción: se vuelve a derivar el id y se
    // vuelve a contar, sin que sobreviva nada en memoria.
    String borradorDe(String ordenId, String momento) =>
        'borrador-$ordenId-$momento';

    test('el id del borrador se puede volver a derivar igual', () {
      expect(
        borradorDe('ot-1', 'bloqueo'),
        borradorDe('ot-1', 'bloqueo'),
      );
      // Y no se mezcla con el de otro momento ni con el de otra orden.
      expect(
        borradorDe('ot-1', 'bloqueo') == borradorDe('ot-1', 'cierre'),
        isFalse,
      );
      expect(
        borradorDe('ot-1', 'bloqueo') == borradorDe('ot-2', 'bloqueo'),
        isFalse,
      );
    });

    test('después de reconstruir, la foto se vuelve a encontrar', () async {
      final String borrador = borradorDe('ot-1', 'bloqueo');
      await encolarFoto(id: 'f1', reporteLocalId: borrador);

      // -- aquí la pantalla muere y se reconstruye: nada sobrevive en memoria --

      final Map<String, int> cuenta = await base.fotosPorRequisitoDeBorrador(
        borradorId: borradorDe('ot-1', 'bloqueo'),
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(cuenta, <String, int>{'foto_del_obstaculo': 1});
    });

    test('y se puede repuntar al reporte, que es lo que la salva', () async {
      final String borrador = borradorDe('ot-1', 'bloqueo');
      await encolarFoto(id: 'f1', reporteLocalId: borrador);

      await base.reasignarEvidenciasDeBorrador(
        borradorId: borradorDe('ot-1', 'bloqueo'),
        reporteLocalId: 'seg-ot-1-bloqueo-999',
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      await base.sellarEvidenciasDelReporte(
        reporteLocalId: 'seg-ot-1-bloqueo-999',
        eventoId: 'evt-9',
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(await idsPendientes(), <String>['f1']);
    });

    test('dos fotos del mismo requisito se cuentan las dos', () async {
      final String borrador = borradorDe('ot-1', 'bloqueo');
      await encolarFoto(id: 'f1', reporteLocalId: borrador);
      await encolarFoto(id: 'f2', reporteLocalId: borrador);

      final Map<String, int> cuenta = await base.fotosPorRequisitoDeBorrador(
        borradorId: borrador,
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(cuenta['foto_del_obstaculo'], 2);
    });

    test('la cuenta no mezcla requisitos ni borradores', () async {
      await encolarFoto(
        id: 'f1',
        requisito: 'foto_del_obstaculo',
        reporteLocalId: borradorDe('ot-1', 'bloqueo'),
      );
      await encolarFoto(
        id: 'f2',
        requisito: 'foto_del_avance',
        reporteLocalId: borradorDe('ot-1', 'avance'),
      );

      final Map<String, int> cuenta = await base.fotosPorRequisitoDeBorrador(
        borradorId: borradorDe('ot-1', 'bloqueo'),
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(cuenta, <String, int>{'foto_del_obstaculo': 1});
    });
  });

}
