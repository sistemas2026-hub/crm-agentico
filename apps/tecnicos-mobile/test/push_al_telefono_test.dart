import 'dart:convert';

import 'package:campo/core/avisos/avisos_push.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/notificaciones/notificaciones_screen.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'apoyo/sesion_en_el_telefono.dart';

/// El aviso que llega al teléfono: qué se guarda y qué se abre.
///
/// QUÉ SE AFIRMA, Y QUÉ PASA SI SE ROMPE
/// -------------------------------------
/// 1. **El aviso que llega por push queda guardado, y COMPLETO.**
///    `guardarNotificaciones` traduce de las claves del servidor a las de la
///    tabla; pasarle las de la tabla no da error, inserta la fila con el verbo,
///    el título, el enlace y la fecha en blanco. El síntoma es un aviso vacío en
///    la lista, y no señala a la causa. Es la clase de defecto que `analyze` no
///    ve y una prueba que solo cuenta filas tampoco.
///
/// 2. **Es LA MISMA fila que baja la sincronización.** El push trae el id del
///    servidor justamente para eso. Sin él, el técnico vería el mismo aviso dos
///    veces y el segundo sin leer.
///
/// 3. **Leída por push, sigue leída después de sincronizar.** El contador que
///    sube solo es lo que hace que la gente deje de mirarlo.
///
/// 4. **Tocar el aviso con la app cerrada abre la orden, no la pantalla de
///    inicio.** El toque llega antes de que exista el contenedor, así que se
///    guarda y el shell lo reclama. Si se perdiera, el aviso serviría para
///    enterarse y no para actuar — que es la mitad que importa.
///
/// 5. **El bloque de avisos no ocupa lugar cuando no hay nada.** Un bloque que
///    dice "No hay avisos" todos los días enseña a no mirar esa parte de la
///    pantalla, y ese aprendizaje después se lleva puesto el aviso que sí
///    importaba.
///
/// LO QUE ESTAS PRUEBAS NO PUEDEN MEDIR
/// ------------------------------------
/// Que FCM entregue. Eso necesita un teléfono real y el proveedor del otro lado;
/// acá se mide todo lo que pasa **una vez que el mensaje llegó**, que es lo que
/// vive en este repositorio. El cuerpo que sale hacia FCM se mide del lado del
/// servidor, en `campo/tests/test_push_al_telefono.py`.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_push_al_telefono.db');

  const String orgA = 'org_rapilink';
  const String perfilA = 'prof_carlos';
  const String ordenA = 'ot-devuelta-1';

  late Map<String, String> llavero;
  late LocalDatabase base;
  late AvisosPush push;

  setUp(() async {
    llavero = <String, String>{};
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
      (MethodCall llamada) async {
        final args = (llamada.arguments as Map?) ?? <dynamic, dynamic>{};
        final String? clave = args['key']?.toString();
        switch (llamada.method) {
          case 'read':
            return llavero[clave];
          case 'write':
            if (clave != null) llavero[clave] = args['value']?.toString() ?? '';
            return null;
          case 'delete':
            llavero.remove(clave);
            return null;
          case 'deleteAll':
            llavero.clear();
            return null;
          case 'readAll':
            return Map<String, String>.from(llavero);
          case 'containsKey':
            return llavero.containsKey(clave);
        }
        return null;
      },
    );

    base = LocalDatabase();
    push = AvisosPush(baseLocal: base, almacen: SecureStorageService());

    final db = await base.database;
    await db.delete('local_notificaciones');

    await SecureStorageService().saveSessionData(
      orgId: orgA,
      orgName: 'Rapilink',
      profileId: perfilA,
      email: 'tecnico@ejemplo.local',
      name: 'Carlos',
    );
    AvisosPush.alAbrirOrden = null;
    AvisosPush.tomarOrdenPendiente();
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
      null,
    );
    AvisosPush.alAbrirOrden = null;
    AvisosPush.tomarOrdenPendiente();
  });

  /// Un mensaje con la forma EXACTA que arma el backend.
  ///
  /// Se construye desde el mapa crudo y no con constructores amables a
  /// propósito: en el teléfono `data` siempre llega como `Map<String, String>`
  /// --FCM no transporta otra cosa-- y una prueba que le pasara un entero o un
  /// mapa anidado probaría un caso que nunca ocurre.
  RemoteMessage mensajeDeDevolucion({
    String id = 'notif-abc-123',
    String enlace = '/ot/$ordenA',
    String titulo = 'OT #9401',
  }) {
    return RemoteMessage.fromMap(<String, dynamic>{
      'data': <String, String>{
        'enlace': enlace,
        'clase': 'aviso_de_campo',
        'id': id,
        'verbo': 'trabajo_devuelto',
        'titulo': titulo,
        'creada_en': '2026-10-04T15:30:00+00:00',
        'datos': jsonEncode(<String, dynamic>{
          'vuelta': 2,
          'observacion': 'Falta la foto del empalme',
          'rehacer': <String>['Fotografía de la medición'],
          'orden_numero': 9401,
        }),
      },
      'notification': <String, dynamic>{
        'title': titulo,
        'body': 'Te devolvieron la OT #9401',
      },
    });
  }

  Future<Map<String, dynamic>?> filaUnica() async {
    final filas = await base.leerNotificaciones(orgId: orgA, profileId: perfilA);
    return filas.isEmpty ? null : filas.first;
  }

  // ------------------------------------------------------------------------- #
  // A. El aviso queda guardado, y completo
  // ------------------------------------------------------------------------- #

  group('A · lo que llega por push se guarda', () {
    test('a1 · la fila queda COMPLETA, no solo presente', () async {
      await push.espejar(mensajeDeDevolucion());

      final fila = await filaUnica();
      expect(fila, isNotNull);
      // Cada una de éstas se vaciaría en silencio si alguien le pasara a
      // `guardarNotificaciones` las claves de la columna en vez de las del
      // servidor. Por eso se afirman los CUATRO valores y no que haya una fila.
      expect(fila!['id'], 'notif-abc-123');
      expect(fila['verbo'], 'trabajo_devuelto');
      expect(fila['titulo'], 'OT #9401');
      expect(fila['enlace'], '/ot/$ordenA');
      expect(fila['creada_en'], '2026-10-04T15:30:00+00:00');
      expect(fila['leida_en'], isNull);
    });

    test('a2 · el contenido se puede volver a leer, no solo está', () async {
      await push.espejar(mensajeDeDevolucion());

      final fila = await filaUnica();
      final datos = jsonDecode(fila!['datos_json'] as String) as Map;
      expect(datos['observacion'], 'Falta la foto del empalme');
      expect(datos['rehacer'], <String>['Fotografía de la medición']);
      expect(datos['vuelta'], 2);
    });

    test('a3 · sin id no se guarda nada', () async {
      // Inventar un id acá crearía una fila que la sincronización duplicaría
      // después. No guardar es la respuesta correcta.
      await push.espejar(
        RemoteMessage.fromMap(<String, dynamic>{
          'data': <String, String>{'enlace': '/ot/$ordenA'},
          'notification': <String, dynamic>{'title': 'OT #9401'},
        }),
      );

      expect(await filaUnica(), isNull);
    });

    test('a4 · sin sesión no se guarda nada', () async {
      // Un aviso que llega después de cerrar sesión no se puede atribuir a
      // nadie: guardarlo bajo la identidad anterior lo mostraría al técnico que
      // entre después con el mismo teléfono.
      await SecureStorageService().clearSession();

      await push.espejar(mensajeDeDevolucion());

      final db = await base.database;
      final filas = await db.query('local_notificaciones');
      expect(filas, isEmpty);
    });

    test('a5 · el mismo aviso dos veces sigue siendo UNA fila', () async {
      // FCM puede entregar el mismo mensaje más de una vez; es parte del
      // contrato, no una rareza.
      await push.espejar(mensajeDeDevolucion());
      await push.espejar(mensajeDeDevolucion());

      final filas = await base.leerNotificaciones(
        orgId: orgA,
        profileId: perfilA,
      );
      expect(filas.length, 1);
    });
  });

  // ------------------------------------------------------------------------- #
  // B. El push y la sincronización son el mismo hecho
  // ------------------------------------------------------------------------- #

  group('B · push y sincronización no se duplican', () {
    test('b1 · lo que baja la cola con el mismo id no crea otra fila', () async {
      await push.espejar(mensajeDeDevolucion(id: 'notif-xyz'));

      // Lo mismo que hace `_procesarNotificaciones` con lo que trae el servidor.
      await base.guardarNotificaciones(
        orgId: orgA,
        profileId: perfilA,
        notificaciones: <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'notif-xyz',
            'verb': 'trabajo_devuelto',
            'entity_name': 'OT #9401',
            'link': '/ot/$ordenA',
            'created_at': '2026-10-04T15:30:00+00:00',
            'data': <String, dynamic>{'vuelta': 2},
            'read_at': null,
          },
        ],
      );

      final filas = await base.leerNotificaciones(
        orgId: orgA,
        profileId: perfilA,
      );
      expect(filas.length, 1);
    });

    test('b2 · leída por push, sigue leída después de sincronizar', () async {
      // EL CONTADOR QUE SUBE SOLO es lo que hace que la gente deje de mirarlo.
      await push.espejar(mensajeDeDevolucion(id: 'notif-leida'));
      await base.marcarNotificacionLeida(
        id: 'notif-leida',
        orgId: orgA,
        profileId: perfilA,
      );

      await base.guardarNotificaciones(
        orgId: orgA,
        profileId: perfilA,
        notificaciones: <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'notif-leida',
            'verb': 'trabajo_devuelto',
            'entity_name': 'OT #9401',
            'link': '/ot/$ordenA',
            'created_at': '2026-10-04T15:30:00+00:00',
            'data': <String, dynamic>{},
            'read_at': null,
          },
        ],
      );

      expect(
        await base.contarNotificacionesSinLeer(orgId: orgA, profileId: perfilA),
        0,
      );
    });

    test('b3 · un aviso nuevo sube el contador', () async {
      expect(
        await base.contarNotificacionesSinLeer(orgId: orgA, profileId: perfilA),
        0,
      );

      await push.espejar(mensajeDeDevolucion());

      expect(
        await base.contarNotificacionesSinLeer(orgId: orgA, profileId: perfilA),
        1,
      );
    });

    test('b4 · el aviso de otra identidad no se cuenta', () async {
      await push.espejar(mensajeDeDevolucion());

      expect(
        await base.contarNotificacionesSinLeer(
          orgId: 'org_otra_empresa',
          profileId: perfilA,
        ),
        0,
      );
      expect(
        await base.contarNotificacionesSinLeer(
          orgId: orgA,
          profileId: 'prof_otro',
        ),
        0,
      );
    });
  });

  // ------------------------------------------------------------------------- #
  // C. Tocar el aviso abre la orden
  // ------------------------------------------------------------------------- #

  group('C · tocar el aviso', () {
    test('c1 · con el shell montado abre la orden en el acto', () {
      final abiertas = <String>[];
      AvisosPush.alAbrirOrden = abiertas.add;

      AvisosPush.abrirDesdeUnEnlace('/ot/$ordenA');

      expect(abiertas, <String>[ordenA]);
      // Nada quedó pendiente: ya se abrió.
      expect(AvisosPush.tomarOrdenPendiente(), isNull);
    });

    test('c2 · sin shell todavía, la orden queda pendiente y se abre después',
        () {
      // EL CASO REAL, y el que se pierde si nadie lo guarda: tocar el aviso con
      // la app cerrada arranca el proceso de cero, y `getInitialMessage`
      // contesta antes de que exista una pantalla donde navegar.
      AvisosPush.abrirDesdeUnEnlace('/ot/$ordenA');

      expect(AvisosPush.tomarOrdenPendiente(), ordenA);
    });

    test('c3 · la orden pendiente se consume UNA sola vez', () {
      // Si quedara, cada reconstrucción del contenedor volvería a abrir la
      // misma orden y el técnico no podría salir de ahí.
      AvisosPush.abrirDesdeUnEnlace('/ot/$ordenA');

      expect(AvisosPush.tomarOrdenPendiente(), ordenA);
      expect(AvisosPush.tomarOrdenPendiente(), isNull);
    });

    test('c4 · un enlace de otra forma no abre nada y no rompe', () {
      final abiertas = <String>[];
      AvisosPush.alAbrirOrden = abiertas.add;

      // `/ot/<id>` es el único formato que escribe el backend hoy. Adivinar
      // sobre otro abriría una pantalla equivocada, que es peor que no abrir.
      AvisosPush.abrirDesdeUnEnlace('https://campo.rapilink.co/ot/$ordenA');
      AvisosPush.abrirDesdeUnEnlace('/clientes/5');
      AvisosPush.abrirDesdeUnEnlace('/ot/');
      AvisosPush.abrirDesdeUnEnlace('');

      expect(abiertas, isEmpty);
      expect(AvisosPush.tomarOrdenPendiente(), isNull);
    });
  });

  // ------------------------------------------------------------------------- #
  // D. El bloque de avisos en la pantalla
  // ------------------------------------------------------------------------- #

  group('D · el bloque de avisos', () {
    /// POR QUE `montarConBaseReal` Y NO `pumpAndSettle`
    /// -----------------------------------------------
    /// Esta pantalla consulta SQLite en `initState`. `pumpAndSettle` avanza un
    /// reloj FALSO: el futuro de la base nunca resuelve y la prueba se queda
    /// mirando "Buscando…" --que es lo que paso al escribir esto--. El repo ya
    /// tiene el ayudante para eso, con la trampa documentada arriba de el.
    Future<void> montar(
      WidgetTester tester, {
      required bool ocultarSiVacio,
      void Function(String)? alAbrirOrden,
    }) {
      return montarConBaseReal(
        tester,
        MaterialApp(
          theme: AppTheme.lightTheme,
          home: Scaffold(
            body: SingleChildScrollView(
              child: NotificacionesScreen(
                baseLocal: base,
                ocultarSiVacio: ocultarSiVacio,
                alAbrirOrden: alAbrirOrden,
              ),
            ),
          ),
        ),
      );
    }

    testWidgets('d1 · sin avisos no ocupa lugar', (tester) async {
      await montar(tester, ocultarSiVacio: true);

      expect(find.text('Avisos'), findsNothing);
      expect(find.text('No hay avisos.'), findsNothing);
      // Y no deja un hueco: el alto del bloque es cero.
      expect(
        tester.getSize(find.byType(NotificacionesScreen)).height,
        0,
      );
    });

    testWidgets('d2 · suelta sí explica que no hay nada', (tester) async {
      // Esconderse acá dejaría una pantalla en blanco sin decir por qué.
      await montar(tester, ocultarSiVacio: false);

      expect(find.text('Avisos'), findsOneWidget);
      expect(find.text('No hay avisos.'), findsOneWidget);
    });

    testWidgets('d3 · con un aviso dice qué pasó y qué hay que rehacer',
        (tester) async {
      // `runAsync` por lo mismo que `montarConBaseReal`: escribir en SQLite es
      // E/S real, y el reloj falso de la prueba no entrega su respuesta. Sin
      // esto la prueba no falla -- se cuelga diez minutos, que es peor porque no
      // dice por que.
      await tester.runAsync(() => push.espejar(mensajeDeDevolucion()));

      await montar(tester, ocultarSiVacio: true);

      expect(find.text('Avisos'), findsOneWidget);
      expect(find.text('Te devolvieron la OT #9401'), findsOneWidget);
      expect(find.text('«Falta la foto del empalme»'), findsOneWidget);
      expect(
        find.text('Hay que volver a tomar: Fotografía de la medición'),
        findsOneWidget,
      );
      // La pastilla del diseño va en mayúsculas: `DexterPastilla` hace el
      // `toUpperCase`. Se afirma lo que el técnico ve, no lo que se le pasó.
      expect(find.text('NUEVO'), findsOneWidget);
    });

    testWidgets('d4 · un aviso que llega con la pantalla abierta aparece solo',
        (tester) async {
      await montar(tester, ocultarSiVacio: true);
      expect(find.text('Avisos'), findsNothing);

      // Esto es lo que hace el push mientras el técnico mira la pantalla. Sin
      // la suscripción a los cambios de la base no pasaría nada hasta que
      // alguien la refresque a mano.
      await tester.runAsync(() => push.espejar(mensajeDeDevolucion()));
      await esperarLaBase(tester);

      expect(find.text('Te devolvieron la OT #9401'), findsOneWidget);
    });

    testWidgets('d5 · tocarlo lo marca leído y abre la orden', (tester) async {
      await tester.runAsync(() => push.espejar(mensajeDeDevolucion()));
      final abiertas = <String>[];

      await montar(tester, ocultarSiVacio: true, alAbrirOrden: abiertas.add);

      await tester.tap(find.text('Te devolvieron la OT #9401'));
      // DOS VECES, y no es por las dudas. `esperarLaBase` da tres vueltas de
      // 40 ms de tiempo REAL; el toque dispara dos lecturas encadenadas --marcar
      // leída y volver a traer la lista-- y con la suite completa corriendo en
      // paralelo ese presupuesto se queda corto. Medido: pasa sola y parpadeó
      // una vez en la corrida entera.
      await esperarLaBase(tester);
      await esperarLaBase(tester);

      expect(abiertas, <String>[ordenA]);
      // Se marca ACÁ y en el acto, sin esperar al servidor: el técnico ya la
      // leyó, y sin señal eso tiene que valer igual.
      final int sinLeer = (await tester.runAsync(
        () => base.contarNotificacionesSinLeer(orgId: orgA, profileId: perfilA),
      ))!;
      expect(sinLeer, 0);
      expect(find.text('NUEVO'), findsNothing);
    });
  });
}
