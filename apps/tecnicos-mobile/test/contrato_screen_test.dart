// EL CONTRATO DEL CLIENTE, DESDE LA APP (13/11/2026).
//
// Lo que se afirma: los datos del cliente llegan prellenados de la solicitud;
// el botón no se habilita sin servidor y sin firma; sin señal lo dice y no
// encola nada; lo que se manda al servidor lleva lo que el técnico corrigió,
// el servidor elegido y la firma como PNG.
import 'dart:convert';

import 'package:campo/core/storage/ubicacion_de_captura.dart';
import 'package:campo/features/contrato/contrato_screen.dart';
import 'package:campo/features/ejecucion/widgets/firma_del_cliente.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _ApiFalsa extends ApiDelContrato {
  _ApiFalsa({this.lectura, this.errorDeLectura});

  final Map<String, dynamic>? lectura;
  final String? errorDeLectura;
  Map<String, dynamic>? enviado;
  int lecturas = 0;
  final List<int> zonasPedidas = <int>[];

  @override
  Future<Map<String, dynamic>> ipsLibres(String ordenId, int idZona) async {
    zonasPedidas.add(idZona);
    //  Desde el 26/11/2026 la app no las pide: la IP la asigna el servidor.
    //  Se anota igual, para afirmar que no se llama.
    return <String, dynamic>{'libres': const <dynamic>[], 'motivo': 'sin pool'};
  }

  @override
  Future<RespuestaDelServidor> leer(String ordenId) async {
    lecturas++;
    if (errorDeLectura != null) return RespuestaDelServidor(error: errorDeLectura);
    return RespuestaDelServidor(cuerpo: lectura);
  }

  @override
  Future<RespuestaDelServidor> firmar(String ordenId, Map<String, dynamic> cuerpo) async {
    enviado = cuerpo;
    return RespuestaDelServidor(cuerpo: <String, dynamic>{
      'contrato': <String, dynamic>{
        'numero': 'C-2026-000301',
        'estado': 'firmado',
        'cliente': cuerpo['cliente'],
        'plan': cuerpo['plan'],
        'servidor': <String, dynamic>{'id_zona': cuerpo['id_zona'], 'nombre': 'SERVIDOR 2'},
      },
    });
  }
}

Map<String, dynamic> _borrador() => <String, dynamic>{
      'contrato': null,
      'borrador': <String, dynamic>{
        'origen': 'solicitud',
        'cliente': <String, dynamic>{
          'nombre': 'Laura', 'apellido': 'Gómez', 'tipo_documento': 'CC',
          'numero_documento': '1043000000', 'telefono': '3000000000',
          'correo': '', 'direccion': 'Cra 21 # 45-12', 'barrio': 'Villa Estadio',
        },
        'plan': 'Fibra 300 Mb',
        'autorizaciones': <String, dynamic>{'habeas_data': true, 'centrales_de_riesgo': true},
      },
      'servidores': <Map<String, dynamic>>[
        <String, dynamic>{'id_zona': 20053, 'nombre': 'SERVIDOR 1'},
        <String, dynamic>{'id_zona': 20061, 'nombre': 'SERVIDOR 2'},
      ],
      'condiciones_cargadas': true,
    };

/// Un teléfono alto: la lista se construye perezosa y el botón del fondo no
/// existe si no entra en pantalla.
void _telefonoAlto(WidgetTester t) {
  t.view.physicalSize = const Size(1080, 5200);
  t.view.devicePixelRatio = 2.6;
  addTearDown(t.view.reset);
}

Widget _montar(ApiDelContrato api) => MaterialApp(
      home: ContratoScreen(ordenId: 'o-1', titulo: 'OT #301', api: api),
    );

FilledButton _boton(WidgetTester t) =>
    t.widget<FilledButton>(find.byWidgetPredicate((Widget w) => w is FilledButton));

//  EL SERVIDOR DE HOY (26/11/2026): el plan del ticket ya reconocido, la lista
//  de planes con sus servidores y el del corte, y SOLO el servidor del corte.
Map<String, dynamic> _conPlanes({String plan = 'PLAN FAMILIA', Object? gps}) {
  final Map<String, dynamic> l = _borrador();
  final Map<String, dynamic> b = l['borrador'] as Map<String, dynamic>;
  b['plan'] = plan;
  b['plan_del_ticket'] = 'FAMILIA 200MB - \$89.900';
  b['autorizaciones'] = null;
  b['tipo_documento'] = 'CC';
  (b['cliente'] as Map<String, dynamic>)['tipo_documento'] = '';
  b['gps'] = gps;
  b['servidor_sugerido'] = 20061;
  //  Todos los del plan, el del corte primero (26/11/2026: «en la parte de
  //  corte no deja escoger»).
  l['servidores'] = <Map<String, dynamic>>[
    <String, dynamic>{'id_zona': 20061, 'nombre': 'SERVIDOR 2'},
    <String, dynamic>{'id_zona': 20053, 'nombre': 'SERVIDOR 1'},
  ];
  l['planes'] = <Map<String, dynamic>>[
    <String, dynamic>{
      'nombre': 'PLAN FAMILIA',
      'servidores': <Map<String, dynamic>>[
        <String, dynamic>{'id_zona': 20053, 'nombre': 'SERVIDOR 1'},
        <String, dynamic>{'id_zona': 20061, 'nombre': 'SERVIDOR 2'},
      ],
      'servidor_sugerido': 20061,
    },
    <String, dynamic>{
      'nombre': 'PLAN SABANA',
      'servidores': <Map<String, dynamic>>[
        <String, dynamic>{'id_zona': 32278, 'nombre': 'SERVIDOR 3'},
      ],
      'servidor_sugerido': null,
    },
    //  Repetido a proposito: el menu de Flutter se cae con dos valores
    //  iguales, y la app tiene que quedarse con el primero.
    <String, dynamic>{
      'nombre': 'PLAN FAMILIA',
      'servidores': <Map<String, dynamic>>[],
      'servidor_sugerido': null,
    },
    <String, dynamic>{
      'nombre': 'PLAN HOGAR',
      'servidores': <Map<String, dynamic>>[
        <String, dynamic>{'id_zona': 20053, 'nombre': 'SERVIDOR 1'},
        <String, dynamic>{'id_zona': 20061, 'nombre': 'SERVIDOR 2'},
      ],
      'servidor_sugerido': null,
    },
  ];
  return l;
}

Future<void> _firmar(WidgetTester t) async {
  await t.drag(find.byType(LienzoDeFirma), const Offset(140, -40));
  await t.pump();
  await t.runAsync(() async {
    await t.tap(find.text('Crear el contrato'));
    await Future<void>.delayed(const Duration(milliseconds: 300));
  });
  await t.pumpAndSettle();
}

Future<void> _elegirPlan(WidgetTester t, String nombre) async {
  await t.tap(find.byType(DropdownButtonFormField<String>));
  await t.pumpAndSettle();
  await t.tap(find.text(nombre).last);
  await t.pumpAndSettle();
}

void main() {
  setUp(() {
    UbicacionDeCaptura.overrideParaPruebas =
        () async => <String, dynamic>{'lat': 10.9108, 'lng': -74.8186, 'precision_m': 6};
  });
  tearDown(() => UbicacionDeCaptura.overrideParaPruebas = null);

  // ========================================================================
  //  LA DIRECCION IP  --  14/11/2026, y desde el 26/11/2026 la asigna el
  //  sistema: «sería mejor si el sistema le indica la IP al contrato sin que
  //  tenga que elegir el técnico».
  // ========================================================================
  testWidgets('LA IP NO SE ELIGE: no se piden direcciones, no viaja ninguna, y se dice quién la pone',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(lectura: _borrador());
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    await t.tap(find.text('SERVIDOR 2'));
    await t.pumpAndSettle();
    expect(find.text('Se asigna al firmar'), findsOneWidget);
    await _firmar(t);
    expect(api.zonasPedidas, isEmpty, reason: 'la app ya no pide la lista de libres');
    expect(api.enviado!.containsKey('ip'), isFalse, reason: 'la elige el servidor al firmar');
  });

  testWidgets('sin señal lo dice, y Reintentar vuelve a preguntar', (WidgetTester t) async {
    final _ApiFalsa api = _ApiFalsa(errorDeLectura: 'Sin señal: el contrato no se creó.');
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    expect(find.text('Necesitas señal para el contrato'), findsOneWidget);
    await t.tap(find.text('Reintentar'));
    await t.pumpAndSettle();
    expect(api.lecturas, 2);
  });

  testWidgets('los datos llegan de la solicitud, y sin servidor ni firma no se crea',
      (WidgetTester t) async {
    _telefonoAlto(t);
    await t.pumpWidget(_montar(_ApiFalsa(lectura: _borrador())));
    await t.pumpAndSettle();
    expect(find.text('Laura'), findsOneWidget);
    expect(find.text('1043000000'), findsOneWidget);
    expect(find.textContaining('Lo llenó el cliente'), findsOneWidget);
    expect(_boton(t).onPressed, isNull, reason: 'falta servidor y firma');
    expect(find.textContaining('el servidor'), findsOneWidget);
    expect(find.textContaining('la firma del cliente'), findsOneWidget);
  });

  testWidgets('un contrato ya firmado se muestra, no el formulario', (WidgetTester t) async {
    final Map<String, dynamic> l = _borrador()
      ..['borrador'] = null
      ..['contrato'] = <String, dynamic>{
        'numero': 'C-2026-000301', 'estado': 'firmado',
        'cliente': <String, dynamic>{'nombre': 'Laura'}, 'plan': 'Fibra 300 Mb',
        'servidor': <String, dynamic>{'nombre': 'SERVIDOR 1'},
      };
    await t.pumpWidget(_montar(_ApiFalsa(lectura: l)));
    await t.pumpAndSettle();
    expect(find.text('Contrato firmado'), findsOneWidget);
    expect(find.text('N.º C-2026-000301'), findsOneWidget);
    expect(find.text('Crear el contrato'), findsNothing);
  });

  testWidgets('firmar manda lo corregido, el servidor elegido y la firma en PNG',
      (WidgetTester t) async {
    _telefonoAlto(t);

    final _ApiFalsa api = _ApiFalsa(lectura: _borrador());
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    //  El técnico corrige la cédula con el documento delante.
    await t.enterText(find.widgetWithText(TextField, 'Documento'), '1043000001');
    await t.tap(find.text('SERVIDOR 2'));
    await t.pump();

    await t.drag(find.byType(LienzoDeFirma), const Offset(140, -40));
    await t.pump();
    expect(_boton(t).onPressed, isNotNull);

    await t.runAsync(() async {
      await t.tap(find.text('Crear el contrato'));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await t.pumpAndSettle();

    final Map<String, dynamic> e = api.enviado!;
    expect(e['id_zona'], 20061);
    expect((e['cliente'] as Map)['numero_documento'], '1043000001');
    expect((e['cliente'] as Map)['nombre'], 'Laura');
    expect(e['plan'], 'Fibra 300 Mb');
    expect(e['gps'], isNotNull);
    final List<int> png = base64Decode(e['firma_png_base64'] as String);
    expect(png.sublist(0, 4), <int>[0x89, 0x50, 0x4E, 0x47], reason: 'la firma va como PNG');
    expect(find.text('Contrato firmado'), findsOneWidget);
  });

  // ========================================================================
  //  LO QUE PIDIÓ EL USUARIO AL PROBARLO EN EL TELÉFONO  --  26/11/2026
  // ========================================================================
  testWidgets('sin «CC» pegado al número, y sin las casillas de habeas data',
      (WidgetTester t) async {
    _telefonoAlto(t);
    //  El servidor viejo todavía manda el tipo y las autorizaciones: la app
    //  nueva no los dibuja igual.
    await t.pumpWidget(_montar(_ApiFalsa(lectura: _borrador())));
    await t.pumpAndSettle();
    final TextField doc = t.widget<TextField>(find.widgetWithText(TextField, 'Documento'));
    expect(doc.decoration?.prefixText, isNull);
    //  Nombre arriba y apellido abajo, a todo el ancho (26/11/2026).
    final Offset nombre = t.getTopLeft(find.widgetWithText(TextField, 'Nombre'));
    final Offset apellido = t.getTopLeft(find.widgetWithText(TextField, 'Apellido'));
    expect(apellido.dy, greaterThan(nombre.dy));
    expect(apellido.dx, nombre.dx);
    expect(find.textContaining('Habeas'), findsNothing);
    expect(find.textContaining('Centrales de riesgo'), findsNothing);
  });

  testWidgets('las coordenadas del ticket se ven; sin ellas, se dice qué se guarda',
      (WidgetTester t) async {
    _telefonoAlto(t);
    await t.pumpWidget(_montar(_ApiFalsa(
        lectura: _conPlanes(gps: <String, dynamic>{'lat': 10.9108, 'lng': -74.8186}))));
    await t.pumpAndSettle();
    expect(find.text('10.910800, -74.818600'), findsOneWidget);
    expect(find.text('COORDENADAS · DEL TICKET'), findsOneWidget);

    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(_montar(_ApiFalsa(lectura: _conPlanes())));
    await t.pumpAndSettle();
    expect(find.text('Del teléfono, al firmar'), findsOneWidget);
    expect(textoDeCoordenadas(<String, dynamic>{'lat': '10.91', 'lng': '-74.81'}), '10.91, -74.81',
        reason: 'también si llegan como texto');
    expect(textoDeCoordenadas(<String, dynamic>{'lat': null, 'lng': 1}), '');
  });

  testWidgets('LAS COORDENADAS SE CORRIGEN con el GPS y VIAJAN; sin corregir, no viajan',
      (WidgetTester t) async {
    _telefonoAlto(t);
    //  El control primero: sin tocar nada, mandan las del ticket (no viajan).
    final _ApiFalsa sinTocar = _ApiFalsa(
        lectura: _conPlanes(gps: <String, dynamic>{'lat': 10.5, 'lng': -74.5}));
    await t.pumpWidget(_montar(sinTocar));
    await t.pumpAndSettle();
    await _firmar(t);
    expect(sinTocar.enviado!.containsKey('coordenadas'), isFalse);

    await t.pumpWidget(const SizedBox());
    final _ApiFalsa api = _ApiFalsa(
        lectura: _conPlanes(gps: <String, dynamic>{'lat': 10.5, 'lng': -74.5}));
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    await t.tap(find.text('Donde estoy'));
    await t.pumpAndSettle();
    expect(find.text('COORDENADAS · CORREGIDAS POR TI'), findsOneWidget);
    expect(find.text('10.910800, -74.818600'), findsOneWidget);
    await _firmar(t);
    expect(api.enviado!['coordenadas'], <String, dynamic>{'lat': 10.9108, 'lng': -74.8186});
  });

  testWidgets('EL MAPA: se abre en el punto que hay, y «Usar esta ubicación» lo deja corregido',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(
        lectura: _conPlanes(gps: <String, dynamic>{'lat': 10.5, 'lng': -74.5}));
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    await t.tap(find.text('Elegir en el mapa'));
    await t.pumpAndSettle();
    expect(find.text('Dónde queda la casa'), findsOneWidget);
    expect(find.text('10.500000, -74.500000'), findsWidgets, reason: 'abre donde estaba el punto');
    await t.tap(find.text('Usar esta ubicación'));
    await t.pumpAndSettle();
    expect(find.text('COORDENADAS · CORREGIDAS POR TI'), findsOneWidget);
    await _firmar(t);
    expect(api.enviado!['coordenadas'], <String, dynamic>{'lat': 10.5, 'lng': -74.5});
  });

  testWidgets('EL PLAN ES UN MENÚ y el servidor del corte llega MARCADO, con los demás a la mano',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(lectura: _conPlanes());
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    expect(find.byType(DropdownButtonFormField<String>), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Plan'), findsNothing, reason: 'el plan no se teclea');
    expect(find.text('PLAN FAMILIA'), findsOneWidget);
    expect(find.text('SERVIDOR 2'), findsOneWidget);
    expect(find.text('SERVIDOR 1'), findsOneWidget, reason: 'el corte se puede cambiar');
    expect(find.text('SERVIDOR · MARCADO POR EL CORTE DEL TICKET'), findsOneWidget);
    await _firmar(t);
    expect(api.enviado!['id_zona'], 20061, reason: 'sin tocar nada, va el del corte');
  });

  testWidgets('EL CORTE SE PUEDE CAMBIAR: tocar otro servidor lo elige', (WidgetTester t) async {
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(lectura: _conPlanes());
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    await t.tap(find.text('SERVIDOR 1'));
    await t.pumpAndSettle();
    expect(find.text('ELIGE EL SERVIDOR'), findsOneWidget, reason: 'ya no es el del corte');
    await _firmar(t);
    expect(api.enviado!['id_zona'], 20053);
  });

  testWidgets('cambiar de plan deja los servidores DE ESE PLAN, y marca el del corte si lo tiene',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(lectura: _conPlanes());
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    //  Un plan con un solo servidor: queda ese, asignado.
    await _elegirPlan(t, 'PLAN SABANA');
    expect(find.text('SERVIDOR 3'), findsOneWidget);
    expect(find.text('SERVIDOR 2'), findsNothing);

    //  Un plan con dos servidores y sin el del corte: el técnico elige.
    await _elegirPlan(t, 'PLAN HOGAR');
    expect(find.text('SERVIDOR 1'), findsOneWidget);
    expect(find.text('SERVIDOR 2'), findsOneWidget);
    expect(find.textContaining('el servidor'), findsOneWidget, reason: 'falta elegirlo');

    //  Vuelve al de antes: otra vez marcado el del corte.
    await _elegirPlan(t, 'PLAN FAMILIA');
    expect(find.text('SERVIDOR · MARCADO POR EL CORTE DEL TICKET'), findsOneWidget);

    await _firmar(t);
    expect(api.zonasPedidas, isEmpty);
    expect(api.enviado!['plan'], 'PLAN FAMILIA');
    expect(api.enviado!['id_zona'], 20061);
  });

  testWidgets('un plan del ticket que no está en la lista queda SIN ELEGIR, con lo que decía',
      (WidgetTester t) async {
    _telefonoAlto(t);
    await t.pumpWidget(_montar(_ApiFalsa(lectura: _conPlanes(plan: 'familia 200 megas'))));
    await t.pumpAndSettle();
    expect(find.text('Elige el plan'), findsOneWidget);
    expect(find.textContaining('En el ticket dice: «FAMILIA 200MB'), findsOneWidget);
    expect(find.textContaining('Falta el plan'), findsOneWidget);
  });
}
