import 'dart:async';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/inicio/inicio_screen.dart';
import 'package:campo/features/materiales/devolucion_screen.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';
import 'apoyo/sesion_en_el_telefono.dart';

/// E2E-001 · La jornada completa, con las pantallas de verdad.
///
/// QUÉ AGREGA SOBRE TODO LO ANTERIOR
/// ---------------------------------
/// `flujo_de_jornada_test.dart` ya prueba que el dato viaja bien entre
/// módulos, pero lo hace llamando a las clases de datos. Responde "¿el dato
/// viaja?" y deja abierta la otra mitad: **¿el técnico ve la verdad?**
///
/// Acá las pantallas se montan sin inyectarles nada —como las construye la
/// aplicación—, leen su identidad por el canal del almacenamiento seguro y
/// sus datos de la base real. Un consumo registrado se busca después con los
/// ojos, en la pantalla de Materiales, no preguntándole a `KitDeJornada`.
///
/// Eso encuentra lo que ninguna de las dos mitades encuentra sola: una
/// pantalla que lee de otra fuente, un widget que no se entera de un cambio,
/// un estado que el dominio conoce y la interfaz no muestra.
///
/// ESCENARIO DORADO
/// ----------------
/// Corre en la suite normal, sin etiqueta. Un escenario que hay que acordarse
/// de invocar deja de correr en tres semanas, y entonces no protege nada.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('e2e_jornada.db');

  const String org = 'org_rapilink';
  const String perfil = 'prof_carlos';
  const String ot = 'ot-4832';

  late LocalDatabase db;
  final SesionEnElTelefono sesion =
      SesionEnElTelefono(orgId: org, profileId: perfil);

  setUpAll(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(), 'e2e_jornada.db'),
    );
  });

  // El setUp NO toca la base.
  //
  // Dentro de un `testWidgets` todo corre bajo un reloj falso, y eso incluye
  // el setUp: un `await` a SQLite ahí queda esperando un tiempo que no avanza
  // y la prueba se cuelga antes de dibujar nada. La preparación va adentro de
  // cada caso, envuelta en `runAsync`.
  setUp(() {
    sesion.instalar();
    db = LocalDatabase();
  });

  Future<void> limpiar() async {
    final base = await db.database;
    for (final String t in const <String>[
      'local_ordenes',
      'local_kit',
      'cola_movimientos_material',
      'local_jornada',
      'cola_incidencias',
    ]) {
      await base.delete(t);
    }
  }

  tearDown(sesion.desinstalar);

  // --- Lo que el despacho y la bodega dejaron listo -------------------------

  Future<void> sembrarOrden() => db.upsertOrden(
        orgId: org,
        profileId: perfil,
        ordenData: <String, dynamic>{
          'id': ot,
          'numero': 4832,
          'estado': 'en_sitio',
          'cliente_nombre': 'Carlos Gómez Rincón',
          'direccion': 'Cra 45 #12-88, Barrio San José',
          'telefono': '3001234567',
          'revision': 7,
          'resumen': 'Diagnóstico en domicilio',
          'tipo': <String, dynamic>{
            'nombre': 'Instalación FTTH',
            'codigo': 'ftth_instalacion',
            'schema_version': 1,
          },
          'schema': <String, dynamic>{
            'campos': FuenteDeEjecucionFalsa.camposTipicos,
            'evidencias': FuenteDeEjecucionFalsa.requisitosTipicos,
          },
        },
      );

  Future<void> sembrarKit() => db.reemplazarKit(
        orgId: org,
        profileId: perfil,
        materiales: <Map<String, dynamic>>[
          <String, dynamic>{
            'codigo': 'CON-SC-APC',
            'nombre': 'Conector SC/APC',
            'categoria': 'Conectividad',
            'clase': 'consumible',
            'unidad': 'unidades',
            'recibido': '10',
            'consumido': '0',
            'devuelto': '0',
            'acta': 'Acta #K-2026-311',
          },
        ],
      );

  Future<void> sembrarJornada({
    String consumido = '0',
    String aDevolver = '10',
    String estado = 'pendiente',
  }) =>
      db.guardarJornada(
        orgId: org,
        profileId: perfil,
        datos: <String, dynamic>{
          'estado': estado,
          'puede_cerrar': true,
          'motivos': <String>[],
          'series_sin_devolver': <String>[],
          'transferencias_pendientes': <Map<String, dynamic>>[],
          'resumen': <String, dynamic>{
            'ordenes': <String, dynamic>{
              'asignadas': 1,
              'completadas': 0,
              'pendientes': 1,
            },
            'material': <String, dynamic>{
              'recibido': '10',
              'consumido': consumido,
              'a_devolver': aDevolver,
              'devuelto': '0',
              'diferencias': 0,
            },
            'detalle': <Map<String, dynamic>>[
              <String, dynamic>{
                'codigo': 'CON-SC-APC',
                'nombre': 'Conector SC/APC',
                'unidad': 'unidades',
                'esperado_devolver': aDevolver,
                'devuelto': '0',
              },
            ],
          },
        },
      );

  /// El consumo que el técnico registra dentro de la orden.
  ///
  /// Se escribe por la misma puerta que usa la hoja de consumo, no tocando la
  /// tabla a mano: lo que se prueba después es que las pantallas lo vean.
  Future<void> consumirDosConectores() => db.encolarMovimientoMaterial(
        id: 'mov-e2e',
        orgId: org,
        profileId: perfil,
        materialCodigo: 'CON-SC-APC',
        materialNombre: 'Conector SC/APC',
        tipo: 'consumo',
        cantidad: '2',
        ordenId: ot,
        ordenNumero: 4832,
      );

  // --- Andamiaje de pantallas ----------------------------------------------

  final List<OrdenesJornada> vivas = <OrdenesJornada>[];
  final List<StreamController<SyncStatus>> canales =
      <StreamController<SyncStatus>>[];

  tearDownAll(() async {
    for (final StreamController<SyncStatus> c in canales) {
      await c.close();
    }
    for (final OrdenesJornada o in vivas) {
      o.dispose();
    }
  });

  /// Las órdenes, leídas de la base igual que en la aplicación.
  OrdenesJornada ordenesReales() {
    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    canales.add(avisos);
    final OrdenesJornada o = OrdenesJornada(
      leerOrdenes: () => db.getOrdenes(orgId: org, profileId: perfil),
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    vivas.add(o);
    return o;
  }

  Widget enApp(Widget pantalla) => MaterialApp(
        theme: AppTheme.lightTheme,
        home: pantalla is Scaffold ? pantalla : Scaffold(body: pantalla),
      );

  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  group('E2E-001 · Jornada completa con consumo', () {
    testWidgets('1. Inicio lee la jornada del teléfono, sin que nadie se la dé',
        (WidgetTester t) async {
      // `jornada:` va sin pasar a propósito: la pantalla la busca sola, con la
      // identidad del almacenamiento seguro, como en el teléfono.
      pantallaAlta(t);
      await t.runAsync(() async {
        await limpiar();
        await sembrarOrden();
        await sembrarKit();
        await sembrarJornada();
      });

      await montarConBaseReal(
        t,
        enApp(InicioScreen(
          ordenes: ordenesReales(),
          nombreTecnico: 'Carlos Gómez',
          ahora: DateTime(2026, 9, 22, 10, 0),
          abrirTrabajo: (_, _) async {},
        )),
      );

      expect(find.text('Jornada en curso'), findsOneWidget);
      expect(find.textContaining('Diagnóstico en domicilio'), findsOneWidget);
      expect(find.text('Materiales'), findsOneWidget);
      // Diez recibidos, cero consumidos: el kit entero todavía encima.
      expect(find.text('10'), findsWidgets);
    });

    testWidgets('2. Materiales muestra el kit real, sin recibirlo armado',
        (WidgetTester t) async {
      pantallaAlta(t);
      await t.runAsync(() async {
        await limpiar();
        await sembrarKit();
      });

      await montarConBaseReal(
        t,
        enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );

      expect(find.text('Acta #K-2026-311'), findsOneWidget);
      expect(find.textContaining('10 Disp.'), findsWidgets);
    });

    testWidgets('3. Un consumo registrado se ve en Materiales',
        (WidgetTester t) async {
      // El paso que ninguna prueba de dibujo podía dar: el dato se escribe
      // por la puerta de la aplicación y se busca con los ojos en la pantalla.
      pantallaAlta(t);
      await t.runAsync(() async {
        await limpiar();
        await sembrarKit();
        await consumirDosConectores();
      });

      await montarConBaseReal(
        t,
        enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );

      expect(find.textContaining('8 Disp.'), findsWidgets,
          reason: 'diez menos los dos que acaba de poner');
      expect(find.textContaining('1 movimiento esperando señal'),
          findsOneWidget);
    });

    testWidgets('4. Y el cierre de jornada lo tiene en cuenta',
        (WidgetTester t) async {
      pantallaAlta(t);
      await t.runAsync(() async {
        await limpiar();
        await sembrarKit();
        await consumirDosConectores();
        await sembrarJornada(consumido: '2', aDevolver: '8');
      });

      await montarConBaseReal(t, enApp(const DevolucionScreen()));

      expect(find.text('Cierre de jornada'), findsOneWidget);
      expect(find.textContaining('Conector SC/APC'), findsWidgets);
      // Ocho a devolver, no diez: el consumo llegó hasta acá.
      expect(find.textContaining('Esperado 8'), findsWidgets);
    });

    testWidgets('5. Desde Materiales se llega al cierre, tocando el botón',
        (WidgetTester t) async {
      // Acá se toca de verdad, y no se monta la pantalla siguiente a mano:
      // ese botón fue durante días un Container sin acción, y el cierre de
      // jornada estaba construido y era inalcanzable. Montar la pantalla por
      // separado no lo habría encontrado nunca.
      pantallaAlta(t);
      await t.runAsync(() async {
        await limpiar();
        await sembrarKit();
        await consumirDosConectores();
        await sembrarJornada(consumido: '2', aDevolver: '8');
      });

      await montarConBaseReal(
        t,
        enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );

      expect(find.textContaining('8 Disp.'), findsWidgets);

      await t.tap(find.text('Preparar Devolución al Depósito'));
      await esperarLaBase(t);

      // Y lo que aparece del otro lado es la jornada de verdad, con el
      // consumo que se registró tres pasos atrás.
      expect(find.text('Cierre de jornada'), findsOneWidget);
      expect(find.textContaining('Esperado 8'), findsWidgets);
    });

    testWidgets('6. El cierre se toma desde la pantalla y queda pendiente',
        (WidgetTester t) async {
      // El último tramo del día. Lo que se mide es la distinción que más
      // importa de todo el módulo: tomar el cierre NO es tener la jornada
      // cerrada, y la pantalla tiene que decirlo con esas palabras.
      pantallaAlta(t);
      await t.runAsync(() async {
        await limpiar();
        await sembrarKit();
        await sembrarJornada(consumido: '2', aDevolver: '8');
      });

      await montarConBaseReal(t, enApp(const DevolucionScreen()));

      expect(find.text('Cerrar jornada'), findsOneWidget);

      await t.tap(find.text('Cerrar jornada'));
      await esperarLaAnimacion(t);

      // La hoja dice con qué números se va a firmar, y avisa que después no
      // se cambian desde el teléfono. Son los del día: diez recibidos, dos
      // consumidos.
      expect(
        find.textContaining('Estos números quedan firmados'),
        findsOneWidget,
      );
      expect(find.text('Recibido 10'), findsOneWidget);
      expect(find.text('Consumido 2'), findsOneWidget);
      expect(find.text('Sí, cerrar jornada'), findsOneWidget);

      // Y se confirma. Lo que queda no es una jornada cerrada: es una
      // intención que viaja en la cola.
      await t.tap(find.text('Sí, cerrar jornada'));
      await esperarLaBase(t);

      final EstadoDeJornada despues = (await t.runAsync(
        () => EstadoDeJornada.leer(baseLocal: db),
      ))!;
      expect(despues.cierreTomado, isTrue);
      expect(
        despues.cerrada,
        isFalse,
        reason: 'eso lo dice el servidor cuando congela el acta, no el botón',
      );
    });
  });
}
