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
    bool conTopologia = true,
    String? caja,
    Map<String, dynamic>? dexter,
    Map<String, dynamic>? ticket,
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
              if (conTopologia) 'board': '0',
              if (conTopologia) 'port': '10',
              if (conTopologia) 'onu': '5',
              if (conTopologia) 'olt_name': 'OLT SABANA_GRANDE',
              if (conTopologia) 'zone_name': 'CACARAMOA 2',
              if (conTopologia) 'onu_type_name': 'CDATA-CATV',
              if (conTopologia) 'distance': '2626',
              'odb_name': ?caja,
              'onu_status': estadoOnu,
              'onu_signal': 'Very good',
              'onu_signal_1490': potencia,
              'onu_signal_1310': '-26.99 dBm',
              'onu_signal_1490_veredicto': veredicto,
              'last_status_change': '2026-09-22 08:40:29',
            },
          'dexter': ?dexter,
          'ticket': ?ticket,
          'equipo_no_disponible': ?equipoNoDisponible,
        }),
      };

  Widget app(
    OrdenesJornada ordenes, {
    Future<ResultadoPing> Function(String, int)? probarConexion,
  }) =>
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
            probarConexion: probarConexion,
          ),
        ),
      );

  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 4200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  Future<void> montar(
    WidgetTester tester,
    Map<String, dynamic> fila, {
    Future<ResultadoPing> Function(String, int)? probarConexion,
  }) async {
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
    await tester.pumpWidget(app(ordenes, probarConexion: probarConexion));
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
      // Con espacio y no con guion bajo: la etiqueta se lee, no se copia del
      // nombre del campo.
      expect(find.text('FUERA DE RANGO'), findsOneWidget);
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
  group('4. El ping contesta otra pregunta, y no dictamina', () {
    testWidgets('Antes de tocar no hay ningún resultado inventado',
        (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden(), probarConexion: (String _, int _) async =>
          const ResultadoPing(medido: true, respondieron: '10 de 10'));

      expect(find.widgetWithText(TextButton, 'Ping'), findsOneWidget);
      expect(find.textContaining('Respondieron'), findsNothing,
          reason: 'una medición que nadie pidió no se muestra');
    });

    testWidgets('Los diez llegan en tandas y se numeran de corrido',
        (WidgetTester t) async {
      // WispHub no acepta menos de 3 por llamada (medido: 1 y 2 dan 400), así
      // que se piden 3+3+4. Cada tanda vuelve empezando en 1, y una lista que
      // dijera 1,2,3,1,2,3 sería ilegible.
      final List<int> pedidas = <int>[];
      pantallaAlta(t);
      await montar(t, orden(), probarConexion: (String _, int n) async {
        pedidas.add(n);
        return ResultadoPing(
          medido: true,
          respondieron: '\$n de \$n',
          paquetes: <PaqueteDePing>[
            for (int i = 1; i <= n; i++)
              PaqueteDePing(n: i, respondio: true, rtt: 'tanda\${pedidas.length}'),
          ],
        );
      });

      await t.tap(find.widgetWithText(TextButton, 'Ping'));
      await t.pumpAndSettle();

      expect(pedidas, <int>[3, 3, 4], reason: 'tres tandas, no una de diez');
      expect(find.textContaining('Respondieron 10 de 10'), findsOneWidget);
      expect(find.text('10.'), findsOneWidget,
          reason: 'renumerados de corrido, no 1,2,3 tres veces');
      expect(find.text('4.'), findsOneWidget);
    });

    testWidgets('Si una tanda falla, lo ya medido NO se tira',
        (WidgetTester t) async {
      // Cinco paquetes medidos y una explicación valen más que una pantalla
      // en blanco.
      int vuelta = 0;
      pantallaAlta(t);
      await montar(t, orden(), probarConexion: (String _, int n) async {
        vuelta++;
        if (vuelta == 1) {
          return ResultadoPing(
            medido: true,
            respondieron: '\$n de \$n',
            paquetes: <PaqueteDePing>[
              for (int i = 1; i <= n; i++)
                PaqueteDePing(n: i, respondio: true, rtt: '1ms'),
            ],
          );
        }
        return ResultadoPing.noSePudo('sin_conexion');
      });

      await t.tap(find.widgetWithText(TextButton, 'Ping'));
      await t.pumpAndSettle();

      expect(find.textContaining('Respondieron 3 de 3'), findsOneWidget,
          reason: 'lo que volvió se conserva');
      expect(find.text('3.'), findsOneWidget);
    });

    testWidgets('Un paquete perdido se ve, y se ve DÓNDE',
        (WidgetTester t) async {
      // El motivo de listarlos. Un '9 de 10' no dice si se cayó uno suelto
      // --intermitencia-- o si fue el último de una racha.
      int vuelta = 0;
      pantallaAlta(t);
      await montar(t, orden(), probarConexion: (String _, int n) async {
        vuelta++;
        return ResultadoPing(
          medido: true,
          respondieron: '$n de $n',
          paquetes: <PaqueteDePing>[
            for (int i = 1; i <= n; i++)
              // El segundo de la primera tanda no vuelve; el resto sí.
              PaqueteDePing(
                n: i,
                respondio: !(vuelta == 1 && i == 2),
                rtt: (vuelta == 1 && i == 2) ? '' : '1ms',
              ),
          ],
        );
      });

      await t.tap(find.widgetWithText(TextButton, 'Ping'));
      await t.pumpAndSettle();

      expect(find.text('sin respuesta'), findsOneWidget);
      expect(find.textContaining('Respondieron 9 de 10'), findsOneWidget,
          reason: 'el conteo se recalcula sobre lo acumulado, no se copia '
              'el texto de la última tanda');
    });

    testWidgets('El resultado se puede cerrar', (WidgetTester t) async {
      // La lista ocupa media pantalla y debajo está el botón con el que el
      // técnico avanza la orden.
      pantallaAlta(t);
      await montar(t, orden(), probarConexion: (String _, int _) async =>
          const ResultadoPing(
            medido: true,
            respondieron: '1 de 1',
            paquetes: <PaqueteDePing>[PaqueteDePing(n: 1, respondio: true)],
          ));

      await t.tap(find.widgetWithText(TextButton, 'Ping'));
      await t.pumpAndSettle();
      expect(find.textContaining('Respondieron'), findsOneWidget);

      await t.tap(find.byTooltip('Cerrar el resultado'));
      await t.pumpAndSettle();
      expect(find.textContaining('Respondieron'), findsNothing);
      expect(find.widgetWithText(TextButton, 'Ping'), findsOneWidget,
          reason: 'y se puede volver a pedir');
    });

    testWidgets('Un cero de diez se muestra, no se traduce a un juicio',
        (WidgetTester t) async {
      // Está medido dos veces que el mismo equipo sano da 1, 2 y 3 de 3 en
      // corridas seguidas. La pantalla no puede decir «el servicio está
      // caído»: dice lo que pasó.
      pantallaAlta(t);
      await montar(t, orden(), probarConexion: (String _, int n) async =>
          ResultadoPing(
            medido: true,
            respondieron: '0 de $n',
            paquetes: <PaqueteDePing>[
              for (int i = 1; i <= n; i++)
                PaqueteDePing(n: i, respondio: false),
            ],
          ));

      await t.tap(find.widgetWithText(TextButton, 'Ping'));
      await t.pumpAndSettle();

      expect(find.textContaining('Respondieron 0 de 10'), findsOneWidget);
      expect(find.textContaining('caído'), findsNothing);
      expect(find.textContaining('sin servicio'), findsNothing);
    });

    testWidgets('Sin conexión lo dice, y dice que no se encola',
        (WidgetTester t) async {
      // La distinción entera de este bloque: «no se pudo medir» nunca puede
      // leerse como «no respondió». Una manda a esperar señal; la otra manda a
      // revisar el equipo.
      pantallaAlta(t);
      await montar(t, orden(), probarConexion: (String _, int _) async =>
          ResultadoPing.noSePudo('sin_conexion'));

      await t.tap(find.widgetWithText(TextButton, 'Ping'));
      await t.pumpAndSettle();

      expect(find.textContaining('Sin conexión'), findsOneWidget);
      expect(find.textContaining('no se encola'), findsOneWidget);
      expect(find.textContaining('Respondieron'), findsNothing);
    });

    testWidgets('Que el motor no conteste no dice nada del equipo',
        (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden(), probarConexion: (String _, int _) async =>
          ResultadoPing.noSePudo('motor_no_responde'));

      await t.tap(find.widgetWithText(TextButton, 'Ping'));
      await t.pumpAndSettle();

      expect(find.textContaining('No dice nada del equipo'), findsOneWidget);
    });

    testWidgets('Sin acción inyectada el botón queda inactivo, no miente',
        (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden());

      final TextButton boton =
          t.widget<TextButton>(find.widgetWithText(TextButton, 'Ping'));
      expect(boton.onPressed, isNull);
    });
  });


  group('5. La planta: lo que hay, y lo que no está cargado', () {
    testWidgets('El puerto PON sale de la ficha, no de un ejemplo',
        (WidgetTester t) async {
      // Son tres campos de SmartOLT --tarjeta, puerto y ONU-- y se muestran
      // juntos porque es como un técnico lo dice y lo busca en la OLT.
      pantallaAlta(t);
      await montar(t, orden());

      // 'board/port' y nada mas: asi lo rotula el propio SmartOLT al
      // agrupar una caida ({'label': '1/3', 'board': '1', 'port': '3'}). El
      // numero de ONU es su posicion DENTRO del puerto, no parte del puerto.
      expect(find.text('0/10'), findsOneWidget);
      expect(find.text('0/10/5'), findsNothing);
      expect(find.text('ONU en el puerto'), findsOneWidget);
      expect(find.text('5'), findsOneWidget);
      expect(find.text('PUERTO PON'), findsOneWidget);
    });

    testWidgets('Sin caja cargada se dice, no se inventa una',
        (WidgetTester t) async {
      // Medido el 25/09/2026: el cliente de la orden 1849 no tiene 'odb_name'
      // en SmartOLT. Dibujar 'CTO-04-A' ahí mandaría a buscar una caja que no
      // existe.
      pantallaAlta(t);
      await montar(t, orden());

      // La caja tiene su propia tarjeta: juntas se leia mal, el valor
      // grande era el puerto y la caja parecia su detalle.
      expect(find.text('CAJA / CTO'), findsOneWidget);
      expect(find.text('Sin caja cargada'), findsOneWidget);
      expect(find.textContaining('CTO-04-A'), findsNothing);
    });

    testWidgets('Con caja cargada, se muestra la suya', (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden(caja: 'CTO 56'));

      expect(find.text('CTO 56'), findsOneWidget);
      expect(find.text('Sin caja cargada'), findsNothing);
    });

    testWidgets('La OLT, la zona y el equipo se ven cuando llegan',
        (WidgetTester t) async {
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.text('OLT SABANA_GRANDE'), findsOneWidget);
      expect(find.text('CACARAMOA 2'), findsOneWidget);
      expect(find.text('CDATA-CATV'), findsOneWidget);
      expect(find.text('2626 m'), findsOneWidget);
    });

    testWidgets('Sin topología, esas filas no ocupan lugar en blanco',
        (WidgetTester t) async {
      // Una etiqueta con un guion al lado ocupa el mismo espacio y no informa
      // nada. Las órdenes despachadas antes del 25/09 no traen estos campos.
      pantallaAlta(t);
      await montar(t, orden(conTopologia: false));

      expect(find.text('OLT'), findsNothing);
      expect(find.text('Zona de red'), findsNothing);
      expect(find.text('Dato no disponible'), findsOneWidget,
          reason: 'el puerto tampoco está, y la tarjeta lo dice');
    });
  });

  group('6. Lo que el asistente ya averiguó, y el ticket del ISP', () {
    const Map<String, dynamic> evaluacion = <String, dynamic>{
      'caso': 'sin_senal_tv',
      'motivo_escalada': 'solicitud_explicita',
      'resumen': 'El cliente (Mario Sabanagrande, cedula (documento)) reporta '
          'que no tiene señal de TV.',
      'siguiente_paso': 'Confirmar con el cliente si el coaxial lo instaló la '
          'empresa o lo modificó él.',
    };

    testWidgets('El siguiente paso se ve, y destacado', (WidgetTester t) async {
      // Es trabajo hecho que se estaba tirando: el técnico llegaba a preguntar
      // lo que el cliente ya había contestado por WhatsApp.
      pantallaAlta(t);
      await montar(t, orden(dexter: evaluacion));

      expect(find.text('QUÉ FALTA AVERIGUAR'), findsOneWidget);
      expect(find.textContaining('el coaxial lo instaló la empresa'),
          findsOneWidget);
    });

    testWidgets('El documento del cliente no aparece', (WidgetTester t) async {
      // La ficha se congela en la orden y viaja al teléfono. El nombre sí
      // --el técnico visita a esa persona--; el documento no.
      pantallaAlta(t);
      await montar(t, orden(dexter: evaluacion));

      expect(find.textContaining('000021'), findsNothing);
      expect(find.textContaining('Mario Sabanagrande'), findsOneWidget);
    });

    testWidgets('Sin evaluación, la tarjeta no aparece vacía',
        (WidgetTester t) async {
      // Un caso importado del ISP no tiene conversación detrás. No es un
      // error: es que nadie habló con el cliente todavía.
      pantallaAlta(t);
      await montar(t, orden());

      expect(find.text('Lo que el asistente ya averiguó'), findsNothing);
    });

    testWidgets('El ticket del ISP reemplaza al UUID del caso',
        (WidgetTester t) async {
      // Antes decía «Viene de · Case · 293f1eb8-958d-…», que no le sirve a
      // nadie: la oficina y el técnico hablan de «el 93426».
      pantallaAlta(t);
      await montar(t, orden(ticket: <String, dynamic>{
        'numero': '93426',
        'proveedor': 'wisphub',
        'estado': 'Nuevo',
        'abierto_por': 'DANIELA OSPINO',
      }));

      expect(find.text('TICKET:'), findsOneWidget);
      expect(find.text('#93426 · Nuevo · wisphub'), findsOneWidget);
      expect(find.text('DANIELA OSPINO'), findsOneWidget,
          reason: 'quién lo abrió cambia la conversación con el cliente');
    });
  });
}
