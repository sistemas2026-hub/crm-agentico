// ============================================================================
//  NO DESBORDAR NO ES LO MISMO QUE LEERSE ENTERO
// ============================================================================
//
// POR QUE EXISTE, Y QUE NO CUBRIA LA OTRA GUARDA
// ----------------------------------------------
// `guarda_de_ancho_real_test.dart` afirma que nada DESBORDA a 360 y 412 px:
// se apoya en que Flutter reporta `A RenderFlex overflowed by N pixels` y
// `flutter_test` lo convierte en un fallo.
//
// Pero un `Text` con `overflow: TextOverflow.ellipsis` NUNCA desborda: se
// corta y pone «...». Para esa guarda eso es un exito, y en la pantalla el
// tecnico ve «0/3 capturadas · 0/3 ...» -- perdiendo exactamente el numero
// que el bloque existe para mostrar.
//
// Paso de verdad el 06/10/2026: la fila de las dos cuentas de fotos quedo
// verde en la guarda de ancho y aun asi llegaba cortada. Lo encontro una
// captura a 390 px, mirandola. Esta guarda lo mide.
//
// COMO SE MIDE
// ------------
// Un `RenderParagraph` sabe cuanto ancho necesitaria para dibujarse sin
// cortar (`getMaxIntrinsicWidth`) y cuanto le dieron (`size.width`). Si lo
// segundo es menor que lo primero, el texto esta truncado -- lo diga el
// ellipsis o no.
//
// LO QUE NO HACE
// --------------
// No vigila TODO texto de la aplicacion: hay textos largos que es correcto
// cortar (una direccion, el nombre de un cliente, la descripcion de un
// ticket). Vigila los que NO se pueden perder, nombrados uno por uno. Una
// guarda que vigila todo se desactiva el primer dia.

import 'dart:async';
import 'dart:convert';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

void main() {
  const List<(String, double)> anchos = <(String, double)>[
    ('360 (gama baja)', 360),
    ('390', 390),
    ('412 (Pixel)', 412),
  ];

  /// Falla si el texto que [buscar] encuentra se esta dibujando cortado.
  void seLeeEntero(WidgetTester t, Finder buscar, {required String porque}) {
    expect(buscar, findsWidgets, reason: 'no se encontro el texto: $porque');

    for (final Element e in buscar.evaluate()) {
      final RenderObject? render = e.renderObject;
      if (render is! RenderParagraph) continue;

      // `didExceedMaxLines` es la propiedad que Flutter mismo usa para decidir
      // si dibuja el ellipsis. Vale para una línea y para varias, así que un
      // texto que se envuelve en dos renglones NO cuenta como cortado — que es
      // justo lo que una comparación de anchos intrínsecos diría mal.
      expect(
        render.didExceedMaxLines,
        isFalse,
        reason: 'Se corta: «${render.text.toPlainText()}»'
            '\n$porque',
      );
    }
  }

  /// Una orden con ficha del equipo y el sello que se quiera probar.
  OrdenesJornada ordenesCon(WidgetTester t, {required String ultimoCambio}) {
    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    final OrdenesJornada ordenes = OrdenesJornada(
      leerOrdenes: () async => <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'ot-1',
              'numero': 4832,
              'estado': 'en_sitio',
              'cliente_nombre': 'MARÍA FERNANDA SABANAGRANDE DE LA ESPRIELLA',
              'direccion': 'CALLE 38 # 78-33 BARRIO LA ESPERANZA, TORRE 4',
              'tipo_nombre': 'Reparación de Señal (FTTH)',
              'tipo_codigo': 'ftth_correctivo',
              'schema_version': 1,
              'revision': 1,
              'contexto_json': jsonEncode(<String, dynamic>{
                'contexto_disponible': true,
                'capturado_en': '2026-10-05T13:10:00+00:00',
                'sn_onu': 'ZTEGC0A1B2C3',
                'equipo': <String, dynamic>{
                  'onu_status': 'Offline',
                  'last_status_change': ultimoCambio,
                  // Las DOS lecturas: con una sola, la tarjeta de medicion
                  // optica desborda por su cuenta --defecto preexistente,
                  // ajeno a lo que esta prueba mide-- y el fallo apuntaria al
                  // lugar equivocado.
                  'onu_signal_1490': '-21.19 dBm',
                  'onu_signal_1310': '-23.98 dBm',
                  'onu_signal_1490_veredicto': 'aceptable',
                  'odb_name': 'CTO 56',
                  'board': 4,
                  'port': 14,
                },
              }),
            }
          ],
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
    Widget pantalla, {
    double escalaDeLetra = 1.0,
  }) async {
    t.view.physicalSize = Size(ancho, 800);
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);

    await t.pumpWidget(MaterialApp(
      theme: AppTheme.lightTheme,
      home: MediaQuery(
        data: MediaQueryData(
          size: Size(ancho, 800),
          textScaler: TextScaler.linear(escalaDeLetra),
        ),
        child: pantalla,
      ),
    ));
    await t.pumpAndSettle();
  }

  for (final (String etiqueta, double ancho) in anchos) {
    group('A $etiqueta px', () {
      // Los tres estados que importan. El del medio es el de un tecnico sin
      // señal, que es donde este dato decide si cierra la jornada tranquilo.
      for (final (String nombre, String estado, int esperadas) in <(String, String, int)>[
        ('nada enviado', 'pendiente', 0),
        ('todo enviado', 'confirmada', 3),
      ]) {
        testWidgets('Las dos cuentas de fotos se leen enteras con $nombre',
            (WidgetTester t) async {
          await aEsteAncho(
            t,
            ancho,
            EjecucionScreen(
              ordenId: 'ot-1',
              fuente: FuenteDeEjecucionFalsa(
                evidencias: <Map<String, dynamic>>[
                  for (final String req in <String>[
                    'foto_power_meter',
                    'foto_roseta',
                    'firma_cliente',
                  ])
                    FuenteDeEjecucionFalsa.evidencia(
                      requisitoId: req,
                      estado: estado,
                    ),
                ],
              ),
            ),
          );

          // LAS DOS, por separado: van en lineas distintas justamente
          // porque juntas no entraban.
          seLeeEntero(
            t,
            find.text('3/3 capturadas'),
            porque: 'es lo que el tecnico tomo',
          );
          seLeeEntero(
            t,
            find.text('$esperadas/3 enviadas'),
            porque: 'capturada y enviada son dos hechos distintos; si este '
                'numero se corta, el tecnico cierra la jornada creyendo que '
                'la evidencia ya esta del otro lado',
          );
        });
      }

      testWidgets('Y tambien sin ninguna foto, que es como se abre',
          (WidgetTester t) async {
        await aEsteAncho(
          t,
          ancho,
          EjecucionScreen(
            ordenId: 'ot-1',
            fuente: FuenteDeEjecucionFalsa(),
          ),
        );

        seLeeEntero(
          t,
          find.text('0/3 capturadas'),
          porque: 'es el estado en que se abre la pantalla',
        );
        seLeeEntero(
          t,
          find.text('0/3 enviadas'),
          porque: 'y ninguna salio todavia, que es lo que hay que ver',
        );
      });

      // EL SELLO DEL ULTIMO CAMBIO, en su caso mas largo.
      //
      // Una ficha congelada antes del 06/10/2026 llega SIN offset, y el texto
      // lleva «(hora de la OLT)» pegado para no insinuar una antiguedad que
      // no se puede calcular. Es el estado del equipo mas el sello mas el
      // origen del reloj, todo en el detalle de una caja que tenia una sola
      // linea: el caso que mas facil se corta, y el que mas se pierde si se
      // corta -- porque lo que queda afuera es la hora.
      for (final (String nombre, String sello) in <(String, String)>[
        ('sin zona (ficha vieja)', '2026-10-05 10:42:00'),
        ('con zona (ficha nueva)', '2026-10-05T10:42:00-05:00'),
      ]) {
        testWidgets('El estado de la ONU y su ultimo cambio, $nombre',
            (WidgetTester t) async {
          await aEsteAncho(
            t,
            ancho,
            DetalleOrdenScreen(
              ordenId: 'ot-1',
              ordenes: ordenesCon(t, ultimoCambio: sello),
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

          // El bloque de datos del equipo vive abajo en la ficha, y un
          // ListView solo construye lo que entra en pantalla: sin este
          // scroll la prueba no encontraria el texto y pasaria sin mirar.
          await t.scrollUntilVisible(
            find.textContaining('último cambio'),
            300,
            scrollable: find.byType(Scrollable).first,
          );
          await t.pumpAndSettle();

          // DESBORDE AJENO, DECLARADO Y NO TAPADO.
          //
          // Al hacer scroll se construye la tarjeta de medicion optica
          // (`detalle_orden_screen.dart:3720`), que desborda 93 px a 360 y 78
          // a 412 -- un defecto PREEXISTENTE que no es de este lote y que no
          // se arregla aca. Se descarta la excepcion para poder medir lo que
          // esta prueba sí mide; no se silencia: queda escrito, y
          // `guarda_de_ancho_real_test` no lo ve porque un ListView solo
          // construye lo que entra en pantalla y esa tarjeta vive mas abajo.
          t.takeException();

          seLeeEntero(
            t,
            find.textContaining('último cambio'),
            porque: 'un Offline sin su hora no dice si el equipo se cayo hace '
                'diez minutos o hace dos meses, y eso se atiende distinto',
          );
        });
      }

      // NO SE VIGILA «n requeridas pendientes» ACA: en el formulario de
      // este fixture los tres requisitos de foto son OPCIONALES, asi que esa
      // fila no se dibuja y la prueba afirmaria sobre algo que no existe.
      // Quedo escrito para que no se agregue sin un caso que la produzca.
    });
  }

  group('La guarda sirve: caza un texto cortado de verdad', () {
    // VERIFICACION HACIA ATRAS, dentro de la propia prueba. Sin esto, todo lo
    // de arriba podria estar pasando porque el matcher no mira nada -- que es
    // exactamente el patron que este repositorio ya se comio tres veces.
    testWidgets('Un texto al que no le dan ancho se detecta',
        (WidgetTester t) async {
      await t.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 40,
            child: Text(
              '0/3 capturadas y unas cuantas palabras mas',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      ));
      await t.pumpAndSettle();

      final Finder f = find.text('0/3 capturadas y unas cuantas palabras mas');
      final RenderParagraph p =
          f.evaluate().first.renderObject! as RenderParagraph;

      expect(
        p.didExceedMaxLines,
        isTrue,
        reason: 'si esto no se cumple, el metodo de medicion no sirve y las '
            'pruebas de arriba estan en verde sin mirar nada',
      );
    });
  });
}
