@Tags(<String>['capturas'])
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/features/inicio/inicio_screen.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:campo/features/materiales/kit_de_jornada.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/materiales/devolucion_screen.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:campo/core/widgets/dexter_bottom_nav.dart';
import 'package:campo/features/shell/app_shell.dart';
import 'package:campo/features/trabajo/trabajo_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Capturas de las pantallas reales, para compararlas con el diseño.
///
/// NO es una prueba de regresión visual. No afirma nada: dibuja cada pantalla
/// a un tamaño dado y guarda el PNG. Por eso lleva la etiqueta `capturas` y no
/// corre en la suite normal.
///
///     flutter test test/capturas_qa_test.dart --run-skipped --update-goldens
///
/// POR QUÉ ASÍ Y NO CON EL EMULADOR
/// --------------------------------
/// Porque una captura del emulador depende de a dónde llegó alguien tocando la
/// pantalla, y no se puede repetir igual mañana. Acá cada pantalla se arma con
/// los mismos datos siempre, así que dos capturas separadas por una semana se
/// pueden comparar y la diferencia es del código.
///
/// LAS FUENTES SE CARGAN A MANO
/// ----------------------------
/// Sin esto el motor de pruebas dibuja todo el texto como rectángulos negros:
/// las capturas saldrían, se verían "raras" y la comparación de tipografía
/// sería imposible. Se cargan las mismas Inter y JetBrains Mono del `pubspec`.
Future<void> _cargarFuentes() async {
  // Los iconos primero. Sin esta fuente cada icono se dibuja como un cuadrado
  // vacio: la primera tanda de capturas salio asi y parecia un problema de
  // diseno de la aplicacion.
  //
  // La fuente vive en la cache del SDK, no en el proyecto. Si no aparece esto
  // falla a proposito en vez de seguir: una captura con cuadrados no sirve
  // para comparar nada y, peor, se puede mirar sin notar que esta rota.
  final String? raizSdk = Platform.environment['FLUTTER_ROOT'];
  final List<String> candidatos = <String>[
    if (raizSdk != null) '$raizSdk/bin/cache/artifacts/material_fonts',
    'C:/src/flutter/bin/cache/artifacts/material_fonts',
  ];
  final Iterable<File> hallados = candidatos
      .map((String d) => File('$d/materialicons-regular.otf'))
      .where((File f) => f.existsSync());

  if (hallados.isEmpty) {
    throw StateError(
      'No se encontro materialicons-regular.otf en: $candidatos. '
      'Sin ella las capturas salen con cuadrados en vez de iconos.',
    );
  }
  final FontLoader cargadorDeIconos = FontLoader('MaterialIcons');
  cargadorDeIconos.addFont(Future<ByteData>.value(
    ByteData.view(hallados.first.readAsBytesSync().buffer),
  ));
  await cargadorDeIconos.load();

  for (final (String familia, List<String> archivos) in <(String, List<String>)>[
    ('Inter', <String>[
      'Inter-Regular.ttf',
      'Inter-Medium.ttf',
      'Inter-SemiBold.ttf',
      'Inter-Bold.ttf',
    ]),
    ('JetBrainsMono', <String>[
      'JetBrainsMono-Medium.ttf',
      'JetBrainsMono-SemiBold.ttf',
      'JetBrainsMono-Bold.ttf',
    ]),
  ]) {
    final FontLoader cargador = FontLoader(familia);
    for (final String archivo in archivos) {
      final File f = File('assets/fonts/$archivo');
      if (f.existsSync()) {
        cargador.addFont(Future<ByteData>.value(
          ByteData.view(f.readAsBytesSync().buffer),
        ));
      }
    }
    await cargador.load();
  }
}

/// Un tamaño de pantalla con nombre.
typedef Medida = (String nombre, double ancho, double alto);

/// 390x844 es el teléfono de referencia. Los altos grandes no son pantallas
/// reales: capturan la composición entera de un tirón, que es lo que hay que
/// comparar contra el diseño, donde también se ve todo junto.
const Medida telefono = ('390x844', 390, 844);
const Medida telefonoLargo = ('390x2600', 390, 2600);
const Medida tablet = ('1024x768', 1024, 768);
const Medida escritorio = ('1440x900', 1440, 900);

Map<String, dynamic> _orden({
  required String id,
  required int numero,
  required String estado,
  required String cliente,
  String direccion = 'Cra 45 #12-88, Barrio San José',
  String tipo = 'Instalación FTTH',
  String prioridad = '',
  DateTime? compromiso,
  String? slaVenceEn,
}) =>
    <String, dynamic>{
      'id': id,
      'numero': numero,
      'estado': estado,
      'cliente_nombre': cliente,
      'direccion': direccion,
      'telefono': '3001234567',
      'tipo_nombre': tipo,
      'tipo_codigo': 'ftth_instalacion',
      'schema_version': 1,
      'revision': 7,
      'diagnostico_previo_ia': '',
      'prioridad': prioridad,
      'fecha_compromiso': compromiso?.toIso8601String(),
      'sla_vence_en': ?slaVenceEn,
    };

void main() {
  final DateTime ahora = DateTime(2026, 9, 22, 10, 0);

  setUpAll(_cargarFuentes);

  /// La primera orden, con TODO lo que la pantalla de detalle sabe leer.
  ///
  /// Una captura hecha con una orden pelada muestra una pantalla vacía y
  /// parece un problema de diseño cuando es del dato. Acá se le da lo que el
  /// backend sí entrega hoy: origen, procedimiento, contexto técnico,
  /// coordenadas, ventana y diagnóstico.
  Map<String, dynamic> ordenCompleta() => <String, dynamic>{
        ..._orden(
          id: 'ot-1',
          numero: 4832,
          estado: 'en_sitio',
          cliente: 'Carlos Gómez Rincón',
          compromiso: DateTime(2026, 9, 22, 10, 0),
          slaVenceEn: '2026-09-22T10:45:00',
        ),
        'diagnostico_previo_ia':
            'El abonado reporta cortes intermitentes desde el jueves. La '
                'última lectura de la OLT quedó por debajo del rango.',
        'cliente_lat': 6.2518,
        'cliente_lng': -75.5636,
        'zona': 'Norte Urbano',
        'prioridad': 'alta',
        'resumen': 'Diagnóstico en domicilio y verificación de potencia',
        'detalle_acceso': 'Interior 3 - Apto 402 · Torre Norte',
        'id_abonado': 'ID 10984214',
        'ventana_inicio': '2026-09-22T10:00:00',
        'ventana_fin': '2026-09-22T12:00:00',
        // Estas columnas son TEXT en la base: el modelo las lee con
        // jsonDecode, asi que un Map de Dart se descarta en silencio. La
        // primera tanda de capturas salio sin protocolo por esto, y parecia
        // que la pantalla no lo dibujaba.
        'origen_json': jsonEncode(<String, dynamic>{
          'sistema': 'wisphub',
          'tipo': 'ticket',
          'ref': 'WH-91288',
        }),
        'requisitos_seguridad_json': jsonEncode(<String>[
          'Trabajo en altura sobre escalera',
        ]),
        'pasos_json': jsonEncode(<Map<String, dynamic>>[
          {'titulo': 'Notificación de llegada al inmueble'},
          {'titulo': 'Inspección visual de acometida y roseta'},
          {'titulo': 'Medición óptica con power meter'},
          {'titulo': 'Reconectorización en CTO o roseta'},
          {'titulo': 'Prueba de servicio y velocidad'},
          {'titulo': 'Registro fotográfico de evidencias'},
          {'titulo': 'Firma del abonado'},
        ]),
        'contexto_json': jsonEncode(<String, dynamic>{
          'cliente': <String, dynamic>{'plan': 'Fibra 500 Mbps + TV'},
          'sn_onu': '48575443-B981F',
          'cto': 'CTO-04-A',
        }),
      };

  final List<Map<String, dynamic>> jornadaDeEjemplo = <Map<String, dynamic>>[
    ordenCompleta(),
    _orden(
      id: 'ot-2',
      numero: 4835,
      estado: 'asignada',
      cliente: 'Dra. Mariana Restrepo',
      direccion: 'Calle 93 #11-27, Apto 502',
      tipo: 'Revisión de señal',
      prioridad: 'alta',
      compromiso: DateTime(2026, 9, 22, 11, 30),
    ),
    _orden(
      id: 'ot-3',
      numero: 4841,
      estado: 'asignada',
      cliente: 'Talleres Unidos S.A.S.',
      direccion: 'Zona Industrial, Bodega 12',
      tipo: 'Reubicación de acometida',
      compromiso: DateTime(2026, 9, 22, 14, 15),
    ),
    _orden(
      id: 'ot-4',
      numero: 4820,
      estado: 'cerrada',
      cliente: 'Panadería La Espiga',
      tipo: 'Cambio de ONT',
    ),
  ];

  EstadoDeJornada jornada() => const EstadoDeJornada(
        recibido: '24',
        consumido: '14',
        aDevolver: '10',
        devuelto: '0',
        diferencias: 0,
        ordenesAsignadas: 4,
        ordenesCompletadas: 1,
        materiales: <MaterialDeJornada>[],
        transferencias: <TransferenciaPendiente>[],
        motivos: <String>[],
        sinSubir: 0,
        cerrada: false,
        hayJornada: true,
      );

  SyncSummary resumen() => const SyncSummary(
        status: SyncStatus.idle,
        isSyncing: false,
        hasConnectionError: false,
        mutacionesPendientes: 3,
        mutacionesConflicto: 0,
        evidenciasPendientes: 0,
        datosDirty: 0,
      );

  /// Monta el widget al tamaño pedido y guarda el PNG.
  Future<void> capturar(
    WidgetTester tester,
    Widget pantalla,
    String nombre,
    Medida medida,
  ) async {
    final (String etiqueta, double ancho, double alto) = medida;
    tester.view.physicalSize = Size(ancho, alto);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.lightTheme,
      home: pantalla,
      debugShowCheckedModeBanner: false,
    ));
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('capturas/${nombre}_$etiqueta.png'),
    );
  }

  group('Capturas de la aplicación real', () {
    late StreamController<SyncStatus> avisos;
    late OrdenesJornada ordenes;

    setUp(() {
      avisos = StreamController<SyncStatus>.broadcast();
      ordenes = OrdenesJornada(
        leerOrdenes: () async => jornadaDeEjemplo,
        sincronizar: () async {},
        avisosDeSincronizacion: avisos.stream,
      );
    });

    tearDown(() async {
      await avisos.close();
      ordenes.dispose();
    });

    Widget inicio() => Scaffold(
          body: InicioScreen(
            ordenes: ordenes,
            nombreTecnico: 'Carlos Gómez',
            resumenSincronizacion: resumen(),
            jornada: jornada(),
            ahora: ahora,
            onVerTodos: () {},
            abrirTrabajo: (_, _) async {},
          ),
        );


    /// El armazón completo: encabezado, franja de cola y barra inferior.
    ///
    /// Sin esto la comparación con el diseño no es justa: Stitch dibuja la
    /// pantalla entera, y juzgar la densidad de Inicio sin su encabezado ni su
    /// navegación es medir otra cosa.
    for (final Medida m in <Medida>[telefono, tablet, escritorio]) {
    testWidgets('Armazón completo, Inicio ${m.$1}', (WidgetTester t) async {
      final StreamController<SyncSummary> resumenes =
          StreamController<SyncSummary>.broadcast();
      addTearDown(resumenes.close);

      await capturar(
        t,
        AppShell(
          seccionInicial: SeccionCampo.inicio,
          dependencias: ShellDependencias(
            resumenes: resumenes.stream,
            resumenInicial: resumen(),
            sincronizarAhora: () async {},
            cargarIdentidad: () async => const IdentidadTecnico(
              nombre: 'Carlos Gómez',
              empresa: 'Rapilink ISP',
            ),
            ordenes: ordenes,
            abrirTrabajo: (_, _) async {},
          ),
        ),
        'armazon_inicio',
        m,
      );
    });
    }

    for (final Medida m in <Medida>[telefono, telefonoLargo, tablet, escritorio]) {
      testWidgets('Inicio ${m.$1}', (WidgetTester t) async {
        await capturar(t, inicio(), 'inicio', m);
      });
    }


    /// Jornada: la conciliación y el cierre.
    ///
    /// Se inyecta el estado ya leído: lo que se compara acá es el dibujo, y
    /// la lectura contra la base tiene sus propias pruebas.
    for (final Medida m in <Medida>[telefono, telefonoLargo]) {
      testWidgets('Jornada ${m.$1}', (WidgetTester t) async {
        await capturar(
          t,
          DevolucionScreen(
            estado: const EstadoDeJornada(
              recibido: '24',
              consumido: '14',
              aDevolver: '10',
              devuelto: '8',
              diferencias: 1,
              ordenesAsignadas: 4,
              ordenesCompletadas: 3,
              materiales: <MaterialDeJornada>[
                MaterialDeJornada(
                  codigo: 'CON-SC-APC',
                  nombre: 'Conector SC/APC',
                  unidad: 'unidades',
                  esperado: '7',
                  devuelto: '7',
                  diferencia: 0,
                  porDevolver: 0,
                ),
                MaterialDeJornada(
                  codigo: 'DROP-1H',
                  nombre: 'Bobina Drop Fibra 1 Hilo',
                  unidad: 'm',
                  esperado: '65',
                  devuelto: '63',
                  diferencia: -2,
                  porDevolver: 2,
                ),
                MaterialDeJornada(
                  codigo: 'ONT-HG8145',
                  nombre: 'ONT Huawei HG8145V5',
                  unidad: 'unidades',
                  esperado: '1',
                  devuelto: '0',
                  diferencia: -1,
                  porDevolver: 1,
                  serie: '48575443-A190C',
                ),
              ],
              transferencias: <TransferenciaPendiente>[],
              motivos: <String>[
                'Bobina Drop Fibra 1 Hilo: faltan 2 m sin explicar.',
              ],
              sinSubir: 0,
              cerrada: false,
              hayJornada: true,
            ),
          ),
          'jornada',
          m,
        );
      });
    }

    for (final Medida m in <Medida>[telefono, telefonoLargo]) {
      testWidgets('Trabajo ${m.$1}', (WidgetTester t) async {
        await capturar(
          t,
          Scaffold(
            body: TrabajoScreen(
              ordenes: ordenes,
              abrirTrabajo: (_, _) async {},
            ),
          ),
          'trabajo',
          m,
        );
      });

      testWidgets('Detalle de OT ${m.$1}', (WidgetTester t) async {
        await capturar(
          t,
          DetalleOrdenScreen(
            ordenId: 'ot-1',
            ordenes: ordenes,
            acciones: AccionesOrden(
              transicionar: ({
                required String ordenId,
                required String nuevoEstadoLocal,
                required String tipoAccion,
                required int revisionBase,
              }) async {},
              sincronizar: () async {},
            ),
            resumenInicial: resumen(),
          ),
          'detalle_ot',
          m,
        );
      });

      testWidgets('Materiales ${m.$1}', (WidgetTester t) async {
        await capturar(
          t,
          Scaffold(
            body: MaterialesScreen(
              tecnico: 'Carlos Gómez',
              kit: const KitDeJornada(
                materiales: <MaterialEnCustodia>[
                  MaterialEnCustodia(
                    categoria: 'Activos',
                    nombre: 'ONT Huawei EchoLife HG8145V5',
                    detalle: 'Equipo del abonado',
                    clase: ClaseMaterial.serializado,
                    recibidos: 1,
                    usados: 0,
                    unidad: 'unidades',
                    serie: '48575443-A190C',
                  ),
                  MaterialEnCustodia(
                    categoria: 'Consumibles',
                    nombre: 'Conector SC/APC Rápido Verde',
                    detalle: 'Reconectorización en roseta',
                    clase: ClaseMaterial.consumible,
                    recibidos: 10,
                    usados: 3,
                    unidad: 'unidades',
                  ),
                  MaterialEnCustodia(
                    categoria: 'Consumibles',
                    nombre: 'Bobina Drop Fibra 1 Hilo',
                    detalle: 'Tendido de acometida',
                    clase: ClaseMaterial.bobina,
                    recibidos: 150,
                    usados: 85,
                    unidad: 'm',
                  ),
                ],
                acta: 'Acta #K-2026-311',
                sinSubir: 0,
                conNovedad: <MovimientoConNovedad>[],
              ),
            ),
          ),
          'materiales',
          m,
        );
      });
    }
  });
}
