import 'dart:async';
import 'dart:convert';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// LA SEÑAL QUE EL TÉCNICO VE ES LA DEL CLIENTE, NO UN EJEMPLO.
///
/// El motor consulta SmartOLT al armar la ficha (`_estado_equipo`) y el backend
/// congela el resultado en `contexto.equipo`. El dato llegaba entero hasta el
/// teléfono y **nadie lo leía**: la pantalla dibujaba `-28.9 dBm` con la
/// etiqueta roja «ATENUACIÓN ALTA», fijo, sin mirar la bandera de
/// demostración.
///
/// Medido sobre la orden 1849 de producción el 24/09/2026, la lectura real era
/// `-21.19 dBm` con veredicto `aceptable`. O sea que la pantalla le decía al
/// técnico que la señal estaba mal **cuando estaba bien**, y lo mandaba a
/// buscar una atenuación que no existía.
///
/// Es el tercer caso del mismo patrón en este módulo: `localidad`, `dirección`
/// y `teléfono` ya habían viajado enteros y se habían caído en el último paso.
/// Por eso estas pruebas afirman sobre lo que **se ve en pantalla**, nunca
/// sobre que el getter exista: una prueba que dice que un mecanismo existe no
/// prueba que funcione, y acá el mecanismo existía completo salvo el renglón
/// final.
void main() {
  /// Los valores son los de la orden 1849 tal como están guardados en
  /// producción, no inventados: así, si el formato que manda SmartOLT cambia
  /// (`'-21.19 dBm'` como texto, no como número), la prueba se entera.
  Map<String, dynamic> orden({
    String potencia = '-21.19 dBm',
    String veredicto = 'aceptable',
    String estadoOnu = 'Online',
    bool conEquipo = true,
    String? equipoNoDisponible,
    String capturadoEn = '2026-09-24T19:39:15.917233+00:00',
  }) =>
      <String, dynamic>{
        'id': 'ot-1',
        'numero': 1849,
        'estado': 'asignada',
        'cliente_nombre': 'MARIO SABANAGRANDE',
        'direccion': 'CALLE 38 # 78-33',
        'telefono': '3005380776',
        'tipo_nombre': 'Reparación de Señal (FTTH)',
        'tipo_codigo': 'ftth_correctivo',
        'schema_version': 1,
        'revision': 1,
        'diagnostico_previo_ia': '',
        'contexto_json': jsonEncode(<String, dynamic>{
          'contexto_disponible': true,
          'capturado_en': capturadoEn,
          'sn_onu': 'HWTCA6FB5263',
          'cliente': <String, dynamic>{
            'ip': '172.16.40.70',
            'plan': 'PLAN FIBRA OPTICA 100MB_SB PARCELA',
          },
          if (conEquipo)
            'equipo': <String, dynamic>{
              'onu_status': estadoOnu,
              'onu_signal': 'Very good',
              'onu_signal_1490': potencia,
              'onu_signal_1310': '-26.99 dBm',
              'onu_signal_1490_veredicto': veredicto,
              'last_status_change': '2026-09-22 08:40:29',
            },
          if (equipoNoDisponible != null)
            'equipo_no_disponible': equipoNoDisponible,
        }),
      };

  Widget app(OrdenesJornada ordenes) => MaterialApp(
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
    tester.view.physicalSize = const Size(1000, 4200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  Future<void> montar(WidgetTester tester, Map<String, dynamic> fila) async {
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
    await tester.pumpWidget(app(ordenes));
    await tester.pumpAndSettle();
  }

  group('1. La señal que se ve es la de esta orden', () {
    testWidgets('La potencia real aparece en pantalla', (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.text('-21.19'), findsOneWidget,
          reason: 'la potencia de la orden 1849, no la del fixture de ejemplo');
    });

    testWidgets('El valor de ejemplo ya no se dibuja', (WidgetTester t) async {
      // La afirmación que de verdad importa. Antes esto aparecía SIEMPRE,
      // encima del dato real y con el modo demostración apagado.
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.text('-28.9'), findsNothing,
          reason: 'FieldMockData.potenciaRxPrevia tapaba la lectura real');
      expect(find.text('ATENUACIÓN ALTA'), findsNothing,
          reason: 'una señal aceptable no puede rotularse como atenuación');
    });

    testWidgets('Una señal mala se rotula como mala', (WidgetTester t) async {
      // El contrapeso: que el caso bueno esté verde no puede lograrse a costa
      // de que el malo también lo esté.
      pantallaAlta(t);
      await montar(t, orden(potencia: '-28.90 dBm', veredicto: 'fuera_de_rango'));

      expect(find.text('-28.90'), findsOneWidget);
      expect(find.text('FUERA_DE_RANGO'), findsOneWidget);
    });

    testWidgets('El veredicto no se recalcula en el teléfono',
        (WidgetTester t) async {
      // -21.19 dBm cae dentro de -8..-25, así que un recálculo local diría
      // «aceptable». Si el motor manda otra cosa, manda el motor: el umbral
      // vive en un solo lugar (G-GO-04), y la pantalla lo muestra.
      pantallaAlta(t);
      await montar(t, orden(veredicto: 'revisar'));

      expect(find.text('REVISAR'), findsOneWidget);
      expect(find.text('ACEPTABLE'), findsNothing);
    });
  });

  group('2. Una lectura congelada no se presenta como si fuera de ahora', () {
    testWidgets('Dice a qué hora se midió', (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.textContaining('Medido '), findsOneWidget);
      expect(find.text('Live'), findsNothing,
          reason: 'la ficha se congela al despachar; «Live» era una promesa '
              'que el dato no puede cumplir');
    });
  });

  group('3. Sin lectura se dice POR QUÉ, no se deja un hueco', () {
    testWidgets('Serial no cargado: no es una falla de red',
        (WidgetTester t) async {
      // Le pasa a 1.299 de 4.163 clientes activos, medido. Una tarjeta vacía
      // manda a buscar una falla donde solo falta cargar un dato.
      pantallaAlta(t);
      await montar(t, orden(
        conEquipo: false,
        equipoNoDisponible: 'onu_no_vinculada',
      ));

      expect(find.textContaining('no tiene el equipo cargado'), findsOneWidget);
      expect(find.textContaining('No es una falla de red'), findsOneWidget);
    });

    testWidgets('Serial desactualizado se distingue del anterior',
        (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden(
        conEquipo: false,
        equipoNoDisponible: 'serial_desactualizado',
      ));

      expect(find.textContaining('no existe en la OLT'), findsOneWidget);
    });

    testWidgets('Sin motivo declarado se ofrece reintentar',
        (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden(conEquipo: false));

      expect(find.textContaining('refrescar la ficha'), findsOneWidget);
    });
  });
}
