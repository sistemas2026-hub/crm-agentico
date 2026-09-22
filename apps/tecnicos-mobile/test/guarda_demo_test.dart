import 'dart:async';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/demo/field_mock_data.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/core/widgets/dexter_app_header.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/demo/kit_mock_data.dart';
import 'package:campo/features/materiales/kit_de_jornada.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:campo/features/trabajo/widgets/tarjeta_trabajo.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// La frontera entre lo real y lo de ejemplo.
///
/// Estas pruebas corren en las dos compilaciones y afirman lo contrario en cada
/// una, así que valen como evidencia de la guarda: si alguien dibujara un dato
/// futuro sin condicionarlo, la corrida normal lo encontraría en pantalla y
/// fallaría.
///
///   flutter test -j 1                                # produccion
///   flutter test -j 1 --dart-define=DEXTER_DEMO=true # demostracion
TrabajoVista _trabajo() => TrabajoVista.desdeOrden(<String, dynamic>{
      'id': 'ot-1',
      'numero': 4832,
      'estado': 'en_sitio',
      'cliente_nombre': 'Carlos Gomez',
      'direccion': 'Cra 45 #12-88',
      'telefono': '',
      'tipo_nombre': 'Instalación FTTH',
      'tipo_codigo': 'ftth_instalacion',
      'schema_version': 1,
      'revision': 1,
      'diagnostico_previo_ia': '',
      'fecha_compromiso': null,
    });

/// El detalle necesita la lista de ordenes; nada mas.
class _Base {
  _Base(this.filas);

  final List<Map<String, dynamic>> filas;
  final StreamController<SyncStatus> avisos =
      StreamController<SyncStatus>.broadcast();

  late final OrdenesJornada ordenes = OrdenesJornada(
    leerOrdenes: () async => filas,
    sincronizar: () async {},
    avisosDeSincronizacion: avisos.stream,
  );

  AccionesOrden get acciones => AccionesOrden(
        transicionar: ({
          required String ordenId,
          required String nuevoEstadoLocal,
          required String tipoAccion,
          required int revisionBase,
        }) async {},
        sincronizar: () async {},
      );

  Future<void> cerrar() async {
    await avisos.close();
    ordenes.dispose();
  }
}

/// Una pantalla alta: si lo de abajo no se construye, una fuga pasaria
/// inadvertida y la prueba diria que no hay nada inventado.
void _pantallaAlta(WidgetTester tester) {
  tester.view.physicalSize = const Size(1000, 4000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

/// Una pantalla que trae su propio scroll: envolver un ListView en otro
/// scroll le da alto infinito y no dibuja nada, y entonces la prueba "pasa"
/// sin haber mirado.
Widget _pantalla(Widget hijo) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: hijo),
    );

Widget _enApp(Widget hijo) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: SingleChildScrollView(child: hijo)),
    );

void main() {
  group('Guarda del modo demostración', () {
    testWidgets('1. La tarjeta, sin parametro, sigue a DEXTER_DEMO',
        (WidgetTester tester) async {
      // Sin pasar `mostrarDatosFuturos`: es como la construye la aplicacion.
      await tester.pumpWidget(_enApp(TarjetaTrabajo(trabajo: _trabajo())));
      await tester.pumpAndSettle();

      // Lo real se ve siempre.
      expect(find.text('Carlos Gomez'), findsOneWidget);

      if (FieldMockData.modoDemo) {
        // Distancia estimada y telemetria de red: los dos son de ejemplo.
        expect(find.textContaining('km de tu posición'), findsOneWidget);
        expect(find.textContaining('RX: '), findsOneWidget);
        // CAMPO-DATA-029: de qué ticket vino la orden.
        expect(find.textContaining('Derivado de Ticket #'), findsOneWidget);
      } else {
        expect(
          find.textContaining('Derivado de Ticket #'),
          findsNothing,
          reason: 'un ticket de origen inventado se leeria como el real',
        );
        expect(
          find.textContaining('km de tu posición'),
          findsNothing,
          reason: 'en produccion una distancia de ejemplo se leeria como real',
        );
        expect(find.textContaining('RX: '), findsNothing);
        expect(find.textContaining('CTO'), findsNothing);
        expect(find.textContaining('Alerta Dexter'), findsNothing);
      }
    });

    testWidgets('4. El requisito de seguridad y el acta solo salen en demostración',
        (WidgetTester tester) async {
      // Un trabajo que todavía no empezó y que exige trabajar en altura: el
      // requisito se deriva del identificador, así que se busca uno que lo
      // tenga en vez de suponerlo.
      final String id = <String>['ot-2', 'ot-3', 'ot-4', 'ot-5', 'ot-6']
          .firstWhere((String i) => FieldMockData.trabajoFuturo(i).requiereAlturas);

      await tester.pumpWidget(_enApp(TarjetaTrabajo(
        trabajo: TrabajoVista.desdeOrden(<String, dynamic>{
          'id': id,
          'numero': 4835,
          'estado': 'asignada',
          'cliente_nombre': 'Talleres Unidos',
          'direccion': 'Zona Industrial',
          'telefono': '',
          'tipo_nombre': 'Reubicación de acometida',
          'tipo_codigo': 'reubicacion',
          'schema_version': 1,
          'revision': 1,
          'diagnostico_previo_ia': '',
          'fecha_compromiso': null,
        }),
      )));
      await tester.pumpAndSettle();

      if (FieldMockData.modoDemo) {
        expect(find.text(FieldMockData.requisitoSeguridad), findsOneWidget);
        expect(find.text(FieldMockData.aptitudTecnico), findsOneWidget);
      } else {
        expect(
          find.text(FieldMockData.requisitoSeguridad),
          findsNothing,
          reason: 'anunciar una certificación que nadie verificó es peor que callar',
        );
        expect(find.text(FieldMockData.aptitudTecnico), findsNothing);
      }
    });

    testWidgets('5. La tarjeta no rellena la prioridad ni la franja que faltan',
        (WidgetTester tester) async {
      // El bloque del plan solo se dibuja en un trabajo que NO empezo: con uno
      // en curso esta prueba pasaria sin mirar nada. Ya paso una vez.
      _pantallaAlta(tester);
      final TrabajoVista sinEmpezar = TrabajoVista.desdeOrden(<String, dynamic>{
        'id': 'ot-9',
        'numero': 4840,
        'estado': 'asignada',
        'cliente_nombre': 'Carlos Gomez',
        'direccion': 'Cra 45 #12-88',
        'telefono': '',
        'tipo_nombre': 'Instalación FTTH',
        'tipo_codigo': 'ftth_instalacion',
        'schema_version': 1,
        'revision': 1,
        'diagnostico_previo_ia': '',
        'fecha_compromiso': null,
      });

      await tester.pumpWidget(_enApp(TarjetaTrabajo(trabajo: sinEmpezar)));
      await tester.pumpAndSettle();

      if (FieldMockData.modoDemo) {
        // Con la bandera encendida SI se ven: eso prueba que la prueba mira
        // el lugar correcto, y no que el bloque simplemente no se dibujo.
        expect(find.textContaining('Prioridad '), findsOneWidget);
        expect(find.textContaining('Ventana: '), findsOneWidget);
      } else {
        expect(
          find.textContaining('Prioridad '),
          findsNothing,
          reason: 'la orden no trae prioridad: rellenarla manda a correr sin motivo',
        );
        expect(
          find.textContaining(FieldMockData.ventanaHoraria),
          findsNothing,
          reason: 'sin ventana ni compromiso, la aplicacion no promete una franja',
        );
        expect(
          find.text('Fibra 500 Mbps + TV'),
          findsNothing,
          reason: 'el plan contratado no viene en la orden',
        );
      }
    });

    testWidgets('6. El detalle no inventa zona, ticket ni hora de sincronizacion',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _Base(<Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'ot-1',
          'numero': 4832,
          'estado': 'en_sitio',
          'cliente_nombre': 'Carlos Gomez',
          'direccion': 'Cra 45 #12-88',
          'telefono': '3001234567',
          'tipo_nombre': 'Instalación FTTH',
          'tipo_codigo': 'ftth_instalacion',
          'schema_version': 1,
          'revision': 7,
          'diagnostico_previo_ia': '',
          'fecha_compromiso': null,
        },
      ]);

      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: DetalleOrdenScreen(
          ordenId: 'ot-1',
          ordenes: base.ordenes,
          acciones: base.acciones,
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Carlos Gomez'), findsWidgets, reason: 'lo real se ve');

      if (FieldMockData.modoDemo) {
        // La rama que prueba que la prueba sirve. Ya no incluye el ticket de
        // origen: ese dato es REAL y se muestra siempre, asi que salio del
        // bloque de demostracion.
        expect(find.textContaining(FieldMockData.ultimaSincronizacion),
            findsWidgets);
      } else {
        expect(
          find.textContaining('Ticket #'),
          findsNothing,
          reason: 'un ticket de origen inventado se leeria como el real',
        );
        for (final String zona in <String>[
          'Norte Urbano',
          'Sur Urbano',
          'Centro',
          'Rural Oriente',
        ]) {
          expect(find.textContaining('Zona $zona'), findsNothing);
        }
        expect(
          find.textContaining(FieldMockData.ultimaSincronizacion),
          findsNothing,
          reason: 'la cola no guarda cuando fue el ultimo envio bueno',
        );
        expect(find.textContaining('SLA '), findsNothing);
        expect(find.textContaining(FieldMockData.oltYPuerto), findsNothing);
        expect(find.textContaining(FieldMockData.enlaceDexter), findsNothing);
      }
      await base.cerrar();
    });

    testWidgets('7. Sin kit real, el catalogo de ejemplo sigue a la bandera',
        (WidgetTester tester) async {
      // El kit se inyecta: sin eso la pantalla se queda leyendo la base del
      // entorno y la prueba no mira nada. Ya paso una vez.
      _pantallaAlta(tester);
      await tester.pumpWidget(_pantalla(const MaterialesScreen(
        tecnico: 'Carlos Gomez',
        kit: KitDeJornada.vacio(),
      )));
      await tester.pumpAndSettle();

      if (FieldMockData.modoDemo) {
        // Con la bandera encendida se ve el catalogo de ejemplo; esa es la
        // rama que prueba que la prueba mira el lugar correcto.
        expect(find.text('Mi Kit'), findsOneWidget);
        expect(find.textContaining('Todos (${KitMockData.items.length})'),
            findsOneWidget);
      } else {
        expect(
          find.text('Mi Kit'),
          findsNothing,
          reason: 'sin kit entregado no hay pantalla de kit que mostrar',
        );
        expect(find.textContaining('Todavía no hay material entregado'),
            findsOneWidget);
      }
    });

    testWidgets('8. Con kit real, la cabecera no puede ser de ejemplo',
        (WidgetTester tester) async {
      // Esta es la peor forma de mentir: lista real, cabecera inventada. El
      // tecnico no tiene como saber que el acta y el deposito que firma no
      // salieron de ningun lado.
      _pantallaAlta(tester);
      await tester.pumpWidget(_pantalla(MaterialesScreen(
        tecnico: 'Carlos Gomez',
        kit: const KitDeJornada(
          materiales: <MaterialEnCustodia>[
            MaterialEnCustodia(
              categoria: 'Conectores',
              nombre: 'Conector SC/APC',
              detalle: 'Entregado por bodega',
              clase: ClaseMaterial.consumible,
              recibidos: 30,
              usados: 12,
              unidad: 'unidades',
            ),
          ],
          acta: 'Acta #K-2026-311',
          sinSubir: 0,
          conNovedad: <MovimientoConNovedad>[],
        ),
      )));
      await tester.pumpAndSettle();

      expect(find.textContaining('Conector SC/APC'), findsWidgets,
          reason: 'lo real se ve');

      // Nada de esto tiene fuente, ni siquiera en demostracion: con kit real
      // la cabecera no puede traer datos de otro lado.
      expect(find.textContaining(KitMockData.deposito), findsNothing,
          reason: 'la bodega de origen no viene en el kit');
      expect(find.textContaining(KitMockData.despachadoPor), findsNothing,
          reason: 'quien despacho no viene en el kit');
      expect(find.textContaining(KitMockData.acta), findsNothing,
          reason: 'el acta de ejemplo taparia la real');
      expect(find.textContaining(KitMockData.jornada), findsNothing);
      expect(find.textContaining(KitMockData.macEquipo), findsNothing);
      expect(find.text('${FieldMockData.kitRecibidos}'), findsNothing,
          reason: 'las cifras salen del kit, no de una constante');
    });

    testWidgets('2. La campana solo trae numero en demostración',
        (WidgetTester tester) async {
      await tester.pumpWidget(_enApp(
        const DexterAppHeader(
          empresa: 'Rapilink ISP',
          conexion: EstadoConexion.conRed,
          iniciales: 'CG',
          notificacionesSinLeer: FieldMockData.notificacionesSinLeer,
        ),
      ));
      await tester.pumpAndSettle();

      if (FieldMockData.modoDemo) {
        expect(FieldMockData.notificacionesSinLeer, greaterThan(0));
        expect(find.text('${FieldMockData.notificacionesSinLeer}'), findsOneWidget);
      } else {
        expect(
          FieldMockData.notificacionesSinLeer,
          0,
          reason: 'un numero en la campana se lee como avisos reales sin ver',
        );
        expect(find.text('2'), findsNothing);
      }
    });

    test('3. En producción el interruptor está apagado', () {
      // Comprueba el cableado del propio interruptor: vale lo que diga la
      // bandera de compilacion, y nada mas.
      expect(
        FieldMockData.modoDemo,
        const bool.fromEnvironment('DEXTER_DEMO'),
      );
      expect(
        FieldMockData.notificacionesSinLeer,
        FieldMockData.modoDemo ? 2 : 0,
      );
    });
  });
}
