import 'dart:async';
import 'dart:convert';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/features/detalle_orden/visitas_anteriores.dart';
import 'package:campo/features/inicio/inicio_screen.dart';
import 'package:campo/features/trabajo/trabajo_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Que agregar algo no rompa lo que ya estaba.
///
/// EL PROBLEMA QUE RESUELVE
/// -----------------------
/// Todas las pruebas de pantalla de este proyecto montan a **1000 px de ancho**
/// —`tester.view.physicalSize = Size(1000, 4200)`— porque así entra todo y se
/// puede afirmar sobre el contenido sin pelear con el scroll. Mil píxeles es una
/// tablet. **A ese ancho no desborda nada nunca.**
///
/// El teléfono del técnico tiene 360 o 412. Y el daño típico de agregar algo no
/// es que deje de funcionar: es que una fila que entraba deje de entrar, y el
/// texto se corte o aparezca la banda amarilla. Eso hoy **no lo detecta ninguna
/// prueba**: lo encuentra alguien mirando una captura. El propio código lo dice
/// en `ejecucion_screen.dart` —*«a 390 px esta fila desbordaba 28 px. Lo
/// encontró la corrida de capturas, no una prueba»*— y las capturas están
/// apagadas por omisión.
///
/// POR QUÉ ESTO Y NO MÁS CAPTURAS
/// ------------------------------
/// Una captura dorada falla cada vez que alguien cambia un píxel **a propósito**:
/// un color, una tipografía, un espacio. Eso enseña a actualizarlas sin mirar, y
/// entonces dejan de proteger. Esta guarda no compara píxeles: afirma que el
/// contenido **cabe**. Un cambio de color no la toca; meter un widget de más en
/// una fila, sí.
///
/// CÓMO FUNCIONA
/// -------------
/// Flutter reporta `A RenderFlex overflowed by N pixels` como un error del
/// framework, y `flutter_test` convierte eso en un fallo. O sea que montar cada
/// pantalla al ancho de un teléfono de verdad **ya es la afirmación**: si entra,
/// pasa; si no, falla con el número de píxeles y el widget culpable.
///
/// LO QUE ESTA GUARDA NO HACE
/// --------------------------
/// No dice si el diseño es bonito, ni si algo quedó feo, ni si dos secciones se
/// parecen demasiado. Eso lo ve una persona. Lo que cuida es lo único que se
/// puede medir y es lo que más se rompe al agregar: **que lo que ya estaba siga
/// entrando**.
void main() {
  /// Anchos de teléfonos reales, en píxeles lógicos.
  ///
  /// 360 es el piso práctico en Android (Galaxy A de gama baja, que es
  /// exactamente el teléfono que una empresa le compra a una cuadrilla). 412 es
  /// un Pixel. Si entra en 360, entra en todos.
  const List<(String, double)> anchos = <(String, double)>[
    ('360 (gama baja)', 360),
    ('412 (Pixel)', 412),
  ];

  /// Cuánto agranda la letra el sistema.
  ///
  /// POR QUÉ ESTO NO ES UN CASO RARO
  /// -------------------------------
  /// Un técnico lee al sol, con casco, a un brazo de distancia. Subir el tamaño
  /// de letra del teléfono es lo primero que hace cualquiera que trabaje así —y
  /// 1.3 es un escalón medio, ni siquiera el máximo de Android (que llega a 2.0).
  ///
  /// Es, además, la forma más común de romper un diseño sin tocarlo: el texto
  /// crece y la fila que entraba deja de entrar, en el teléfono de una persona
  /// y no en el de quien programa.
  const double letraGrande = 1.3;

  /// El alto de un teléfono de verdad, no uno inventado.
  ///
  /// Se probó primero con 3000 px —para aislar el ancho— y eso producía un
  /// desborde vertical de 197.289 px en la lista de trabajos que era artefacto
  /// del montaje, no un defecto. Una pantalla alta falsa mide tan mal como una
  /// ancha falsa.
  ///
  /// Lo que importa igual es el ancho: un desborde vertical en una pantalla que
  /// scrollea se resuelve bajando; uno horizontal no se resuelve con ningún
  /// gesto, el texto queda cortado y ya.
  const double alto = 800;

  Map<String, dynamic> ordenDeEjemplo() => <String, dynamic>{
        'id': 'ot-1',
        'numero': 1849,
        'estado': 'en_sitio',
        // Nombres y direcciones LARGOS, que es donde revienta. Un dato corto
        // entra siempre y no prueba nada.
        'cliente_nombre': 'MARÍA FERNANDA SABANAGRANDE DE LA ESPRIELLA',
        'direccion': 'CALLE 38 # 78-33 BARRIO LA ESPERANZA, TORRE 4 APTO 1202',
        'telefono': '+57 312 455 8901',
        'tipo_nombre': 'Reparación de Señal (FTTH) con reconectorización',
        'tipo_codigo': 'ftth_correctivo',
        'schema_version': 1,
        'revision': 1,
        'zona': 'CANDELARIA 2 — SECTOR NORORIENTAL',
        'prioridad': 'alta',
        'contexto_json': jsonEncode(<String, dynamic>{
          'contexto_disponible': true,
          'capturado_en': '2026-10-05T13:10:00+00:00',
          'servicio': 'WH-1042',
          'sn_onu': 'ZTEGC0A1B2C3',
          'equipo': <String, dynamic>{
            'onu_status': 'Online',
            'onu_signal_1490': '-21.19 dBm',
            'onu_signal_1310': '-23.98 dBm',
            'onu_signal_1490_veredicto': 'aceptable',
            'odb_name': 'CTO 56 — PARQUE PRINCIPAL',
            'board': 4,
            'port': 14,
            'olt_name': 'OLT-RAPILINKSAS_X7',
            'zone_name': 'CANDELARIA 2',
          },
        }),
      };

  OrdenesJornada armarOrdenes(WidgetTester t) {
    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    final OrdenesJornada ordenes = OrdenesJornada(
      leerOrdenes: () async => <Map<String, dynamic>>[ordenDeEjemplo()],
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    addTearDown(() async {
      await avisos.close();
      ordenes.dispose();
    });
    return ordenes;
  }

  Future<void> aEsteAncho(
    WidgetTester t,
    double ancho,
    Widget Function() construir, {
    double escalaDeLetra = 1.0,
  }) async {
    t.view.physicalSize = Size(ancho, alto);
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);

    final Widget pantalla = construir();
    await t.pumpWidget(MaterialApp(
      theme: AppTheme.lightTheme,
      // Las pantallas que no traen `Scaffold` propio viven dentro del armazón,
      // que sí lo tiene. Es el mismo criterio que usa `capturas_qa_test`, y no
      // es cosmético: sin él, la lista de trabajos desborda 199.489 px hacia
      // abajo —medido— porque su `Column` con `Expanded` queda sin una caja que
      // le ponga el alto. Montarla sin armazón mide un montaje que no existe.
      home: MediaQuery(
        data: MediaQueryData(
          size: Size(ancho, alto),
          textScaler: TextScaler.linear(escalaDeLetra),
        ),
        child: pantalla is Scaffold ? pantalla : Scaffold(body: pantalla),
      ),
    ));
    await t.pumpAndSettle();
    // No hace falta `expect`: un desborde ya rompió la prueba acá arriba, con
    // el widget y los píxeles en el mensaje. Esta línea existe para que quede
    // dicho que el silencio ES el resultado.
    expect(t.takeException(), isNull, reason: 'algo no entra a $ancho px');
  }

  for (final (String etiqueta, double ancho) in anchos) {
    group('A $etiqueta px', () {
      testWidgets('Inicio entra', (WidgetTester t) async {
        final OrdenesJornada ordenes = armarOrdenes(t);
        await aEsteAncho(t, ancho, () => InicioScreen(
              ordenes: ordenes,
              abrirTrabajo: (_, __) async {},
              nombreTecnico: 'Carlos Gómez',
              ahora: DateTime(2026, 10, 5, 14),
            ));
      });

      testWidgets('La lista de trabajos entra', (WidgetTester t) async {
        final OrdenesJornada ordenes = armarOrdenes(t);
        await aEsteAncho(t, ancho, () => TrabajoScreen(
              ordenes: ordenes,
              abrirTrabajo: (_, __) async {},
            ));
      });

      testWidgets('La ficha de la orden entra', (WidgetTester t) async {
        final OrdenesJornada ordenes = armarOrdenes(t);
        await aEsteAncho(t, ancho, () => DetalleOrdenScreen(
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
                medirSenal: (_) async =>
                    const MedicionDeSenal.noSePudo('sin_conexion'),
              ),
            ));
      });

      testWidgets('La ficha entra tambien con la letra grande',
          (WidgetTester t) async {
        final OrdenesJornada ordenes = armarOrdenes(t);
        await aEsteAncho(
          t,
          ancho,
          () => DetalleOrdenScreen(
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
          ),
          escalaDeLetra: letraGrande,
        );
      });

      testWidgets('Las visitas anteriores entran', (WidgetTester t) async {
        // Con los textos más largos que puede devolver el servidor: un tipo de
        // trabajo con nombre completo, un técnico con nombre y apellido, y una
        // lista de materiales.
        await aEsteAncho(
          t,
          ancho,
          () => Scaffold(
            body: SingleChildScrollView(
              child: VisitasAnteriores(
                historial: <String, dynamic>{
                  'hay_servicio': true,
                  'visitas': <dynamic>[
                    <String, dynamic>{
                      'numero': 1842,
                      'tipo': 'Reparación de Señal (FTTH) con reconectorización',
                      'cuando': '2026-09-28T14:05:00+00:00',
                      'como_termino': 'resuelto',
                      'quien': 'Carlos Alberto Gómez Restrepo',
                      'cambio_equipo': true,
                      'materiales': <Map<String, dynamic>>[
                        <String, dynamic>{
                          'material': 'Cable drop fibra 1 hilo',
                          'cantidad': '43.5',
                          'unidad': 'm',
                        },
                        <String, dynamic>{
                          'material': 'Conector SC/APC rápido verde',
                          'cantidad': '2',
                          'unidad': 'u',
                        },
                      ],
                    },
                  ],
                },
              ),
            ),
          ),
        );
      });
    });
  }
}
