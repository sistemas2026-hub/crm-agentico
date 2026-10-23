import 'dart:async';
import 'dart:convert';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Volver a medir la señal, parado en la casa.
///
/// EL PROBLEMA
/// -----------
/// La señal que trae la ficha es la del momento en que se armó la orden. Si eso
/// fue a las 08:10 y el técnico llegó a las 14:00, esa lectura tiene seis horas
/// — y justo después de limpiar un conector o cambiar una roseta, lo único que
/// contesta *«¿quedó bien?»* es volver a medir. Hoy eso es una llamada al NOC.
///
/// LO QUE ESTAS PRUEBAS CUIDAN
/// ---------------------------
/// 1. **La lectura nueva NO reemplaza a la de la ficha.** Las dos quedan en
///    pantalla: una es cómo estaba el servicio *antes* de la visita y la otra
///    cómo está *ahora*. Pisar la primera borra la única evidencia de que la
///    visita sirvió.
///
/// 2. **«No se pudo medir» se dice distinto según por qué.** Uno se reintenta,
///    otro es configuración de la empresa y otro no se arregla nunca. Un mensaje
///    único los manda a los tres al mismo lugar equivocado — que es de dónde
///    salen las llamadas al NOC.
///
/// 3. **Un fallo no se muestra como una señal mala.** Es la confusión que manda
///    al técnico a buscar una falla de planta que no existe.
void main() {
  Map<String, dynamic> ordenConSenal() => <String, dynamic>{
        'id': 'ot-1',
        'numero': 1849,
        'estado': 'en_sitio',
        'cliente_nombre': 'MARIO SABANAGRANDE',
        'direccion': 'CALLE 38 # 78-33',
        'telefono': '3005380776',
        'tipo_nombre': 'Reparación de Señal (FTTH)',
        'tipo_codigo': 'ftth_correctivo',
        'schema_version': 1,
        'revision': 1,
        'contexto_json': jsonEncode(<String, dynamic>{
          'contexto_disponible': true,
          'capturado_en': '2026-10-05T13:10:00+00:00',
          'servicio': 'WH-1042',
          'sn_onu': 'ZTEGC0A1B2C3',
          'equipo': <String, dynamic>{
            'onu_status': 'Online',
            // La lectura CONGELADA. Es la que no puede desaparecer.
            'onu_signal_1490': '-21.19 dBm',
            'onu_signal_1310': '-23.98 dBm',
            'onu_signal_1490_veredicto': 'aceptable',
          },
        }),
      };

  Future<void> montar(
    WidgetTester t, {
    required Future<MedicionDeSenal> Function(String) medir,
  }) async {
    t.view.physicalSize = const Size(1000, 4200);
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);

    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    final OrdenesJornada ordenes = OrdenesJornada(
      leerOrdenes: () async => <Map<String, dynamic>>[ordenConSenal()],
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    addTearDown(() async {
      await avisos.close();
      ordenes.dispose();
    });

    await t.pumpWidget(MaterialApp(
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
          medirSenal: medir,
        ),
      ),
    ));
    await t.pumpAndSettle();
  }

  group('A · lo que se interpreta de la respuesta', () {
    test('a1 · la potencia llega como TEXTO y se lee igual', () {
      // Medido sobre la orden 1849 de producción: SmartOLT la manda como
      // `'-19.40 dBm'`. Asumir número deja la tarjeta vacía la mitad de las
      // veces.
      final m = MedicionDeSenal.desde(<String, dynamic>{
        'ok': true,
        'medido_en': '2026-10-05T19:32:00+00:00',
        'lectura': <String, dynamic>{
          'onu_signal_1490': '-19.40 dBm',
          'onu_signal_1310': -23.1,
        },
      });

      expect(m.medido, isTrue);
      expect(m.senal1490, -19.40);
      expect(m.senal1310, -23.1);
      expect(m.medidoEn, isNotNull);
    });

    test('a2 · `ok:false` nunca produce una señal', () {
      // Si produjera un 0.0, la pantalla diría que la señal está en el piso —
      // y el técnico se subiría a un poste por un fallo de red.
      final m = MedicionDeSenal.desde(<String, dynamic>{
        'ok': false,
        'motivo': 'motor_no_responde',
      });

      expect(m.medido, isFalse);
      expect(m.senal1490, isNull);
      expect(m.senal1310, isNull);
    });

    test('a3 · cada motivo se explica distinto', () {
      // Uno se reintenta, otro es configuración y otro no se arregla nunca.
      final Set<String> frases = <String>{
        for (final String motivo in <String>[
          'sin_conexion',
          'sin_equipo',
          'medicion_no_habilitada',
          'motor_no_responde',
          'sin_lectura',
        ])
          MedicionDeSenal.noSePudo(motivo).explicacion,
      };

      expect(frases.length, 5, reason: 'dos motivos dicen lo mismo');
    });

    test('a4 · un motivo desconocido no deja la pantalla muda', () {
      expect(MedicionDeSenal.noSePudo('algo_nuevo').explicacion, isNotEmpty);
    });
  });

  group('B · en la ficha', () {
    testWidgets('b1 · el botón está, junto a la lectura congelada', (t) async {
      await montar(t, medir: (_) async => const MedicionDeSenal.noSePudo('x'));

      expect(find.text('Volver a medir'), findsOneWidget);
      // Y la congelada sigue ahí.
      expect(find.text('-21.19'), findsOneWidget);
    });

    testWidgets('b2 · medir NO borra la lectura de la ficha', (t) async {
      // LA MÁS IMPORTANTE. Las dos juntas son lo que permite decir si la visita
      // sirvió; pisar la vieja deja el «antes» igual al «después» siempre.
      await montar(
        t,
        medir: (_) async => MedicionDeSenal(
          medido: true,
          medidoEn: DateTime(2026, 10, 5, 14, 32),
          senal1490: -19.40,
          veredicto: 'aceptable',
          estadoOnu: 'Online',
        ),
      );

      await t.tap(find.text('Volver a medir'));
      await t.pumpAndSettle();

      expect(find.text('-21.19'), findsOneWidget, reason: 'la congelada');
      expect(find.textContaining('Rx ONU -19.40 dBm'), findsOneWidget,
          reason: 'la de ahora');
    });

    testWidgets('b3 · la lectura nueva dice que es de AHORA y a qué hora',
        (t) async {
      // Sin la hora, en cinco minutos vuelve a ser una lectura vieja sin que
      // nadie lo note.
      await montar(
        t,
        medir: (_) async => MedicionDeSenal(
          medido: true,
          medidoEn: DateTime(2026, 10, 5, 14, 32),
          senal1490: -19.40,
        ),
      );

      await t.tap(find.text('Volver a medir'));
      await t.pumpAndSettle();

      expect(find.textContaining('AHORA'), findsOneWidget);
      expect(find.textContaining('14:32'), findsOneWidget);
    });

    testWidgets('b4 · un fallo se dice con su motivo, no como señal mala',
        (t) async {
      await montar(
        t,
        medir: (_) async => const MedicionDeSenal.noSePudo('sin_conexion'),
      );

      await t.tap(find.text('Volver a medir'));
      await t.pumpAndSettle();

      expect(find.textContaining('Sin señal no se puede medir'), findsOneWidget);
      // Y no aparece ningún número nuevo que se pueda leer como medición.
      expect(find.textContaining('AHORA'), findsNothing);
    });

    testWidgets('b5 · sin acción inyectada el botón no se dibuja', (t) async {
      // No miente: una app compilada contra un backend que no tiene la ruta no
      // ofrece un botón que va a fallar.
      final StreamController<SyncStatus> avisos =
          StreamController<SyncStatus>.broadcast();
      final OrdenesJornada ordenes = OrdenesJornada(
        leerOrdenes: () async => <Map<String, dynamic>>[ordenConSenal()],
        sincronizar: () async {},
        avisosDeSincronizacion: avisos.stream,
      );
      addTearDown(() async {
        await avisos.close();
        ordenes.dispose();
      });
      t.view.physicalSize = const Size(1000, 4200);
      t.view.devicePixelRatio = 1.0;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);

      await t.pumpWidget(MaterialApp(
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
      ));
      await t.pumpAndSettle();

      expect(find.text('Volver a medir'), findsNothing);
    });
  });
}
