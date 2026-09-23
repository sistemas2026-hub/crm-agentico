import 'dart:async';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'fuente_de_ejecucion_falsa.dart';
import 'sesion_en_el_telefono.dart';

/// El andamiaje que comparten los escenarios dorados.
///
/// Cada escenario vive en su archivo porque se lee entero de un tirón y
/// cuenta una historia: qué le pasa a alguien un martes. Lo que no puede
/// repetirse cuatro veces es esto — sembrar la orden, el kit y la jornada,
/// abrir la base, instalar la sesión.
///
/// Todo lo que toca la base es `Future` y hay que llamarlo **dentro** de
/// `runAsync`. La razón está en `sesion_en_el_telefono.dart`: bajo el reloj de
/// una prueba de widget, un `await` a SQLite no avanza nunca.
class JornadaDePrueba {
  JornadaDePrueba(this.archivoDeBase);

  /// Cada escenario usa su propio archivo: dos corriendo a la vez sobre el
  /// mismo se pisan y el fallo aparece en el que no tiene la culpa.
  final String archivoDeBase;

  static const String org = 'org_rapilink';
  static const String perfil = 'prof_carlos';
  static const String otraPersona = 'prof_pedro';
  static const String ot = 'ot-4832';

  /// `late` a secas y no `late final`: el setUp corre una vez por caso, y un
  /// `final` explota en el segundo con "already been initialized". Es la misma
  /// instancia igual —LocalDatabase es un singleton— pero el campo se
  /// reasigna.
  late LocalDatabase db;

  final SesionEnElTelefono sesion =
      SesionEnElTelefono(orgId: org, profileId: perfil);

  final List<OrdenesJornada> _vivas = <OrdenesJornada>[];
  final List<StreamController<SyncStatus>> _canales =
      <StreamController<SyncStatus>>[];

  /// Se llama una vez, en `setUpAll`.
  Future<void> prepararElEntorno() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
    LocalDatabase.usarBaseDePruebas(archivoDeBase);
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(), archivoDeBase),
    );
  }

  /// Se llama en `setUp`. No toca la base: ahí todavía manda el reloj falso.
  void empezar() {
    sesion.instalar();
    db = LocalDatabase();
  }

  void terminar() => sesion.desinstalar();

  Future<void> cerrarTodo() async {
    for (final StreamController<SyncStatus> c in _canales) {
      await c.close();
    }
    for (final OrdenesJornada o in _vivas) {
      o.dispose();
    }
  }

  Future<void> limpiar() async {
    final base = await db.database;
    for (final String t in const <String>[
      'local_ordenes',
      'local_kit',
      'cola_movimientos_material',
      'local_jornada',
      'cola_incidencias',
      'cola_evidencias',
    ]) {
      try {
        await base.delete(t);
      } catch (_) {
        // Una tabla que no existe en esta versión del esquema no es un
        // problema de la prueba: lo que importa es empezar sin restos.
      }
    }
  }

  // --- Lo que dejan el despacho y la bodega --------------------------------

  Future<void> sembrarOrden({
    String estado = 'en_sitio',
    String perfilDe = perfil,
    List<Map<String, dynamic>>? campos,
    List<Map<String, dynamic>>? evidencias,
  }) =>
      db.upsertOrden(
        orgId: org,
        profileId: perfilDe,
        ordenData: <String, dynamic>{
          'id': ot,
          'numero': 4832,
          'estado': estado,
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
            'campos': campos ?? FuenteDeEjecucionFalsa.camposTipicos,
            'evidencias': evidencias ?? FuenteDeEjecucionFalsa.requisitosTipicos,
          },
        },
      );

  Future<void> sembrarKit({
    String recibido = '10',
    String consumido = '0',
    String perfilDe = perfil,
  }) =>
      db.reemplazarKit(
        orgId: org,
        profileId: perfilDe,
        materiales: <Map<String, dynamic>>[
          <String, dynamic>{
            'codigo': 'CON-SC-APC',
            'nombre': 'Conector SC/APC',
            'categoria': 'Conectividad',
            'clase': 'consumible',
            'unidad': 'unidades',
            'recibido': recibido,
            'consumido': consumido,
            'devuelto': '0',
            'acta': 'Acta #K-2026-311',
          },
        ],
      );

  Future<void> sembrarJornada({
    String consumido = '0',
    String aDevolver = '10',
    String estado = 'pendiente',
    List<String> motivos = const <String>[],
  }) =>
      db.guardarJornada(
        orgId: org,
        profileId: perfil,
        datos: <String, dynamic>{
          'estado': estado,
          'puede_cerrar': motivos.isEmpty,
          'motivos': motivos,
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

  /// Un consumo, por la misma puerta que usa la hoja de la pantalla.
  Future<void> consumir({
    String id = 'mov-1',
    String cantidad = '2',
    String serie = '',
    String perfilDe = perfil,
  }) =>
      db.encolarMovimientoMaterial(
        id: id,
        orgId: org,
        profileId: perfilDe,
        materialCodigo: 'CON-SC-APC',
        materialNombre: 'Conector SC/APC',
        tipo: 'consumo',
        cantidad: cantidad,
        serie: serie,
        ordenId: ot,
        ordenNumero: 4832,
      );

  /// Lo que contesta el servidor cuando el movimiento sube.
  Future<void> elServidorResponde({
    String id = 'mov-1',
    String resultado = 'aceptado',
    String motivo = '',
  }) =>
      db.confirmarMovimientoMaterial(
        id: id,
        orgId: org,
        profileId: perfil,
        resultado: resultado,
        motivo: motivo,
      );

  /// Una foto o una firma ya capturada y esperando turno.
  ///
  /// El archivo no existe de verdad: lo que se prueba es que la pantalla
  /// reconozca el requisito como cumplido, no que sepa abrir un JPEG.
  Future<void> capturarEvidencia({
    required String requisitoId,
    String id = '',
  }) =>
      db.encolarEvidencia(
        id: id.isEmpty ? 'ev-$requisitoId' : id,
        orgId: org,
        profileId: perfil,
        ordenId: ot,
        requisitoId: requisitoId,
        archivoPath: '/datos/evidencias/$requisitoId.jpg',
        sha256: 'sha-$requisitoId',
        tamanoBytes: 1024,
        mimeType: 'image/jpeg',
        registroIdempotencyKey: 'reg-$requisitoId',
        confirmacionIdempotencyKey: 'conf-$requisitoId',
      );

  // --- Pantallas -----------------------------------------------------------

  /// Las órdenes, leídas de la base igual que en la aplicación.
  OrdenesJornada ordenesReales() {
    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    _canales.add(avisos);
    final OrdenesJornada o = OrdenesJornada(
      leerOrdenes: () => db.getOrdenes(orgId: org, profileId: perfil),
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    _vivas.add(o);
    return o;
  }

  Widget enApp(Widget pantalla) => MaterialApp(
        theme: AppTheme.lightTheme,
        home: pantalla is Scaffold ? pantalla : Scaffold(body: pantalla),
      );

  /// Alta para que entre todo: lo que no se construye no se puede afirmar.
  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }
}
