/// LA PANTALLA DE EJECUCIÓN (18/10/2026), pedidos del usuario:
///
///   A  los datos que le preguntan al técnico —ticket, serial, IP, señal— a la
///      vista en una franja fija, plegada en una línea, copiables
///   B  «Reportar» en el orden del trabajo: inicio, avance, bloqueo
///   C  «Otro» con texto en un campo de opciones: aparece la caja, y sin decir
///      qué fue no se puede cerrar ni mandar el reporte
library;

import 'dart:convert';

import 'package:campo/features/detalle_orden/hoja_de_reporte.dart';
import 'package:campo/features/detalle_orden/seguimiento_de_la_intervencion.dart';
import 'package:campo/features/ejecucion/campo_del_formulario.dart';
import 'package:campo/features/ejecucion/widgets/formulario_de_campo.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:campo/features/trabajo/widgets/franja_del_servicio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _montar(WidgetTester t, Widget w) async {
  t.view.physicalSize = const Size(1000, 3000);
  t.view.devicePixelRatio = 1.0;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
  await t.pumpWidget(MaterialApp(
    home: Scaffold(body: SingleChildScrollView(child: w)),
  ));
  await t.pumpAndSettle();
}

const Map<String, dynamic> _campoOtro = <String, dynamic>{
  'id': 'que_encontro',
  'titulo': 'Qué encontró',
  'tipo': 'seleccion',
  'permite_otro': true,
  'reglas': <String, dynamic>{
    'required': true,
    'options': <String>['Conector sucio', 'Fibra cortada', 'Otro'],
  },
};

void main() {
  group('A · la franja del servicio', () {
    TrabajoVista trabajo() => TrabajoVista.desdeOrden(<String, dynamic>{
          'id': 'ot-1',
          'numero': 1849,
          'estado': 'en_sitio',
          'cliente_nombre': 'Cliente',
          'telefono': '3001234567',
          'contexto_json': jsonEncode(<String, dynamic>{
            'contexto_disponible': true,
            'capturado_en': '2026-10-18T13:10:00+00:00',
            'sn_onu': 'ZTEGC0A1B2C3',
            'cliente': <String, dynamic>{'ip': '172.16.40.70'},
            'ticket': <String, dynamic>{'numero': '95218'},
            'equipo': <String, dynamic>{
              'onu_signal_1490': '-21.19 dBm',
              'onu_signal_1490_veredicto': 'aceptable',
              'odb_name': 'CTO 56',
            },
          }),
        });

    testWidgets('plegada: solo el ticket; el serial y la IP, a un toque',
        (WidgetTester t) async {
      // Antes la línea traía también el serial y la IP, y al desplegar se
      // repetían abajo (pedido del usuario, 18/10/2026).
      await _montar(t, FranjaDelServicio(trabajo: trabajo()));
      expect(find.text('Ticket #95218'), findsOneWidget);
      expect(find.textContaining('172.16.40.70'), findsNothing);
      expect(find.textContaining('A1B2C3'), findsNothing);
    });

    testWidgets('desplegada: todo, la señal dice que es de la ficha, y se copia',
        (WidgetTester t) async {
      final List<String> copiado = <String>[];
      t.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall c) async {
          if (c.method == 'Clipboard.setData') {
            copiado.add((c.arguments as Map)['text'] as String);
          }
          return null;
        },
      );
      addTearDown(() => t.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null));

      await _montar(t, FranjaDelServicio(trabajo: trabajo()));
      await t.tap(find.textContaining('Ticket #95218'));
      await t.pumpAndSettle();

      expect(find.text('ZTEGC0A1B2C3'), findsOneWidget);
      expect(find.text('CTO 56'), findsOneWidget);
      expect(find.textContaining('al despachar'), findsOneWidget);

      await t.tap(find.byTooltip('Copiar IP'));
      await t.pumpAndSettle();
      expect(copiado, <String>['172.16.40.70']);
    });

    testWidgets('sin ningún dato no ocupa lugar', (WidgetTester t) async {
      await _montar(t, FranjaDelServicio(
        trabajo: TrabajoVista.desdeOrden(<String, dynamic>{
          'id': 'x', 'numero': 1, 'estado': 'en_sitio',
        }),
      ));
      expect(find.byIcon(Icons.badge_outlined), findsNothing);
    });
  });

  group('B · Reportar en el orden del trabajo', () {
    testWidgets('inicio, avance y bloqueo, en ese orden', (WidgetTester t) async {
      await _montar(t, SeguimientoDeLaIntervencion(
        cargando: false,
        cierreEnFinalizar: true,
        alReportar: (_, _, {bool requiereNoc = false, bool detener = true}) {},
        seguimiento: <String, dynamic>{
          'eventos': <dynamic>[],
          'momentos_registrados': <String>[],
          'formularios': <String, dynamic>{
            for (final String m in <String>['inicio', 'avance', 'bloqueo', 'cierre'])
              m: <String, dynamic>{'momento': m, 'campos': <dynamic>[]},
          },
        },
      ));
      final Offset inicio = t.getTopLeft(find.text('Inicio'));
      final Offset avance = t.getTopLeft(find.text('Avance'));
      final Offset bloqueo = t.getTopLeft(find.text('Bloqueo'));
      // De a dos: inicio y avance arriba, bloqueo abajo a la izquierda.
      expect(inicio.dy, avance.dy);
      expect(inicio.dx < avance.dx, isTrue);
      expect(bloqueo.dy > inicio.dy, isTrue);
      expect(find.text('Reporte de cierre'), findsNothing);
    });
  });

  group('C · «Otro» con texto', () {
    test('elegir «Otro» sin decir qué bloquea; diciéndolo, no', () {
      final CampoDelFormulario sin = CampoDelFormulario.desdeEsquema(
          _campoOtro, <String, dynamic>{'que_encontro': 'Otro'});
      expect(sin.eligioOtro, isTrue);
      expect(sin.bloqueaCierre, isTrue);
      expect(sin.motivoDelError, contains('contá qué fue'));

      final CampoDelFormulario con = CampoDelFormulario.desdeEsquema(
          _campoOtro, <String, dynamic>{
        'que_encontro': 'Otro',
        'que_encontro_otro': 'Roseta quemada',
      });
      expect(con.bloqueaCierre, isFalse);

      // Sin la casilla en la plantilla, «Otro» es una opción común.
      final CampoDelFormulario comun = CampoDelFormulario.desdeEsquema(
          <String, dynamic>{..._campoOtro, 'permite_otro': false},
          <String, dynamic>{'que_encontro': 'Otro'});
      expect(comun.eligioOtro, isFalse);
      expect(comun.bloqueaCierre, isFalse);
    });

    testWidgets('al elegirlo aparece la caja, y lo escrito se guarda al lado',
        (WidgetTester t) async {
      final Map<String, dynamic> valores = <String, dynamic>{};
      final Map<String, TextEditingController> ctrl = <String, TextEditingController>{};
      final List<String> guardados = <String>[];

      Future<void> dibujar() => _montar(
            t,
            FormularioDeCampo(
              campos: CampoDelFormulario.normalizar(<dynamic>[_campoOtro], valores),
              valores: valores,
              controladores: ctrl,
              alCambiar: (String clave, dynamic v) {
                valores[clave] = v;
                guardados.add(clave);
              },
              mostrarDatosFuturos: false,
            ),
          );

      await dibujar();
      expect(find.text('¿Qué fue?'), findsNothing);
      await t.tap(find.text('Otro'));
      await t.pumpAndSettle();
      await dibujar();
      expect(find.text('¿Qué fue?'), findsOneWidget);

      await t.enterText(find.byType(TextField).last, 'Roseta quemada');
      await t.pumpAndSettle();
      expect(guardados, contains('que_encontro_otro'));
      expect(valores['que_encontro_otro'], 'Roseta quemada');
    });

    testWidgets('un reporte con «Otro» sin texto no se manda', (WidgetTester t) async {
      bool mandado = false;
      await _montar(t, HojaDeReporte(
        momento: 'avance',
        titulo: 'Registrar un avance',
        campos: const <Map<String, dynamic>>[_campoOtro],
        alGuardar: (Map<String, dynamic> _, {bool requiereNoc = false, bool detener = true}) {
          mandado = true;
        },
      ));
      await t.tap(find.text('Otro'));
      await t.pumpAndSettle();
      await t.tap(find.text('GUARDAR EL REPORTE'));
      await t.pumpAndSettle();
      expect(mandado, isFalse);
      expect(find.textContaining('contá qué fue'), findsWidgets);
    });
  });
}
