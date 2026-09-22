import 'dart:async';
import 'dart:convert';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/core/widgets/contenido_centrado.dart';
import 'package:campo/core/widgets/dexter_bottom_nav.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Lo que el técnico necesita saber antes de tocar la puerta.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// El problema espejo del de Inicio. Allá se mostraban datos que no existían;
/// acá se **ocultaban datos que sí existen**: el ticket de origen, la franja
/// prometida y los requisitos de seguridad llegan del backend y vivían detrás
/// de la bandera de demostración, mezclados con los valores de ejemplo. En
/// producción no los veía nadie.
///
/// Ocultar un dato verdadero se paga distinto que mostrar uno falso, pero se
/// paga: alguien sube a una escalera sin saber que el trabajo exigía
/// certificación de alturas.
void main() {
  Map<String, dynamic> orden({
    bool conVentana = true,
    bool conOrigen = true,
    bool conSeguridad = true,
    bool conTecnicos = true,
    String plan = 'Fibra 500 Mbps + TV',
  }) =>
      <String, dynamic>{
        'id': 'ot-1',
        'numero': 4832,
        'estado': 'en_sitio',
        'cliente_nombre': 'Carlos Gómez Rincón',
        'direccion': 'Cra 45 #12-88',
        'telefono': '3001234567',
        'tipo_nombre': 'Instalación FTTH',
        'tipo_codigo': 'ftth_instalacion',
        'schema_version': 1,
        'revision': 7,
        'diagnostico_previo_ia': '',
        'detalle_acceso': 'Interior 3 - Apto 402',
        'id_abonado': 'ID 10984214',
        if (conVentana) 'ventana_inicio': '2026-09-22T10:00:00',
        if (conVentana) 'ventana_fin': '2026-09-22T12:00:00',
        if (conOrigen)
          'origen_json': jsonEncode(<String, dynamic>{
            'sistema': 'wisphub',
            'tipo': 'ticket',
            'ref': 'WH-91288',
          }),
        if (conSeguridad)
          'requisitos_seguridad_json':
              jsonEncode(<String>['Trabajo en altura sobre escalera']),
        'contexto_json': jsonEncode(<String, dynamic>{
          'cliente': <String, dynamic>{'plan': plan},
          if (conTecnicos) 'sn_onu': '48575443-B981F',
          if (conTecnicos) 'cto': 'CTO-04-A',
        }),
      };

  Widget app(Map<String, dynamic> fila, {required OrdenesJornada ordenes}) =>
      MaterialApp(
        theme: AppTheme.lightTheme,
        home: DetalleOrdenScreen(
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
      );

  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  Future<OrdenesJornada> montar(
    WidgetTester tester,
    Map<String, dynamic> fila,
  ) async {
    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    final OrdenesJornada ordenes = OrdenesJornada(
      leerOrdenes: () async => <Map<String, dynamic>>[fila],
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    addTearDown(() async {
      await avisos.close();
      ordenes.dispose();
    });
    await tester.pumpWidget(app(fila, ordenes: ordenes));
    await tester.pumpAndSettle();
    return ordenes;
  }

  group('1. Lo que la orden trae se ve, sin modo demostración', () {
    testWidgets('El ticket del que salió la orden', (WidgetTester t) async {
      // El cliente abre la puerta diciendo "ya llamé tres veces". Con el
      // ticket se puede buscar qué le contestaron.
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.text('Viene de'), findsOneWidget);
      expect(find.text('Ticket WH-91288'), findsOneWidget);
    });

    testWidgets('La franja que se le prometió al cliente',
        (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.text('Franja prometida al cliente'), findsOneWidget);
      expect(find.text('10:00 - 12:00'), findsOneWidget);
    });

    testWidgets('El requisito de seguridad, antes que todo lo demás',
        (WidgetTester t) async {
      // Decide si el trabajo se puede hacer hoy con lo que hay en la
      // camioneta. Va arriba del resto del bloque por eso.
      pantallaAlta(t);
      await montar(t, orden());

      final double seguridad =
          t.getTopLeft(find.text('Trabajo en altura sobre escalera')).dy;
      final double franja =
          t.getTopLeft(find.text('Franja prometida al cliente')).dy;
      expect(seguridad, lessThan(franja));
    });

    testWidgets('La caja y el serial del equipo', (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.text('Caja de distribución'), findsOneWidget);
      expect(find.text('Serial del equipo del cliente'), findsOneWidget);
      // findsWidgets y no findsOneWidget: con la bandera de demostración
      // encendida, la matriz de telemetría de ejemplo repite estos valores.
      // Lo que se mide acá es que el bloque REAL los muestre.
      expect(find.text('CTO-04-A'), findsWidgets);
      expect(find.text('48575443-B981F'), findsWidgets);
    });

    testWidgets('El plan contratado y cómo se entra al inmueble',
        (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.text('Fibra 500 Mbps + TV'), findsOneWidget);
      expect(find.text('Interior 3 - Apto 402'), findsOneWidget);
      expect(find.text('ID 10984214'), findsOneWidget);
    });
  });

  group('2. Lo que la orden NO trae, no se rellena', () {
    testWidgets('Una orden vieja muestra menos, y no inventa',
        (WidgetTester t) async {
      // Hay órdenes creadas antes de que estos campos existieran. Con ellas
      // el bloque entero desaparece en vez de llenarse de ejemplos.
      pantallaAlta(t);
      await montar(
        t,
        orden(
          conVentana: false,
          conOrigen: false,
          conSeguridad: false,
          conTecnicos: false,
          plan: '',
        ),
      );

      expect(find.text('El trabajo'), findsNothing);
      expect(find.text('Datos técnicos'), findsNothing);
      expect(find.textContaining('Ticket'), findsNothing);
      expect(find.text('Plan Activo'), findsNothing);
    });

    testWidgets('Sin plan no se anuncia una velocidad de ejemplo',
        (WidgetTester t) async {
      // El plan decide contra qué velocidad se prueba el servicio antes de
      // dar el trabajo por bueno: uno inventado hace aprobar lo que no está.
      pantallaAlta(t);
      await montar(t, orden(plan: ''));

      expect(find.textContaining('Fibra 500 Mbps Simétrica'), findsNothing);
      expect(find.text('Plan Activo'), findsNothing);
    });

    testWidgets('El plan real no arrastra un "+ Dexter TV" escrito a mano',
        (WidgetTester t) async {
      // Estaba dentro del bloque del plan. Se veía sólo en demostración y
      // paso a verse siempre al mostrar el plan verdadero: asi es como un
      // dato de ejemplo se escapa a producción.
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.textContaining('Dexter TV'), findsNothing);
    });
  });

  group('3. La navegación sólo ofrece lo que existe', () {
    test('Academia y Más no están en la barra', () {
      // Un destino en la barra principal es una promesa: quien lo toca
      // espera que haga algo. Los dos llevaban a "en construcción", y al
      // segundo intento se aprende que la barra miente.
      expect(
        DexterBottomNav.visibles,
        <SeccionCampo>[
          SeccionCampo.inicio,
          SeccionCampo.trabajo,
          SeccionCampo.materiales,
        ],
      );
      expect(DexterBottomNav.visibles, isNot(contains(SeccionCampo.academia)));
      expect(DexterBottomNav.visibles, isNot(contains(SeccionCampo.mas)));
    });

    testWidgets('Y no se dibujan', (WidgetTester t) async {
      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          bottomNavigationBar: DexterBottomNav(
            seleccionada: SeccionCampo.inicio,
            onSeleccion: (_) {},
          ),
        ),
      ));
      await t.pumpAndSettle();

      expect(find.text('INICIO'), findsOneWidget);
      expect(find.text('TRABAJO'), findsOneWidget);
      expect(find.text('MATERIALES'), findsOneWidget);
      expect(find.text('ACADEMIA'), findsNothing);
      expect(find.text('MÁS'), findsNothing);
    });
  });

  group('4. El contenido tiene un techo de ancho', () {
    testWidgets('En una pantalla ancha no se estira', (WidgetTester t) async {
      // Sin techo, a 1440 px los botones miden mil píxeles y las líneas de
      // texto se releen solas: el ojo vuelve al renglón equivocado.
      t.view.physicalSize = const Size(1440, 900);
      t.view.devicePixelRatio = 1.0;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);

      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: const Scaffold(
          body: ContenidoCentrado(child: Text('contenido')),
        ),
      ));
      await t.pumpAndSettle();

      final Size medida = t.getSize(find.byKey(ContenidoCentrado.claveDelTecho));
      expect(medida.width, lessThanOrEqualTo(ContenidoCentrado.anchoMaximo));
    });

    testWidgets('En un teléfono no cambia nada', (WidgetTester t) async {
      t.view.physicalSize = const Size(390, 844);
      t.view.devicePixelRatio = 1.0;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);

      await t.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: const Scaffold(
          body: ContenidoCentrado(child: SizedBox.expand()),
        ),
      ));
      await t.pumpAndSettle();

      final Size medida = t.getSize(find.byKey(ContenidoCentrado.claveDelTecho));
      expect(medida.width, 390, reason: 'por debajo del techo no hace nada');
    });
  });
}
