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
  _ApiFalsa({this.lectura, this.errorDeLectura, this.ips});

  final Map<String, dynamic>? lectura;
  final String? errorDeLectura;
  /// Lo que contesta `/ips-libres/`, por zona. Sin esto, lista vacia.
  final Map<int, Map<String, dynamic>>? ips;
  Map<String, dynamic>? enviado;
  int lecturas = 0;
  final List<int> zonasPedidas = <int>[];

  @override
  Future<Map<String, dynamic>> ipsLibres(String ordenId, int idZona) async {
    zonasPedidas.add(idZona);
    return ips?[idZona] ??
        <String, dynamic>{'libres': const <dynamic>[], 'motivo': 'sin pool'};
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

void main() {
  setUp(() {
    UbicacionDeCaptura.overrideParaPruebas =
        () async => <String, dynamic>{'lat': 10.9108, 'lng': -74.8186, 'precision_m': 6};
  });
  tearDown(() => UbicacionDeCaptura.overrideParaPruebas = null);

  // ========================================================================
  //  LA DIRECCION IP  --  14/11/2026
  //
  //  Se OFRECE y no se teclea: el usuario reporto que al digitar los datos
  //  «hay muchos errores». Una IP mal tecleada no es un dedazo, es un cliente
  //  sin servicio o dos clientes con la misma.
  // ========================================================================
  testWidgets('elegir el servidor pide las IP de ESA zona', (WidgetTester t) async {
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(lectura: _borrador(), ips: <int, Map<String, dynamic>>{
      20061: <String, dynamic>{
        'libres': <String>['172.16.9.2', '172.16.9.3'],
        'advertencia': 'Ninguna de estas la tiene un CLIENTE. Los equipos de red...',
      },
    });
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    //  Con DOS servidores no se pide nada hasta que elija.
    expect(api.zonasPedidas, isEmpty);
    expect(find.text('172.16.9.2'), findsNothing);

    await t.tap(find.text('SERVIDOR 2'));
    await t.pumpAndSettle();

    expect(api.zonasPedidas, <int>[20061]);
    expect(find.text('172.16.9.2'), findsOneWidget);
    expect(find.text('172.16.9.3'), findsOneWidget);
  });

  testWidgets('LA ADVERTENCIA SE MUESTRA: libre no es usable', (WidgetTester t) async {
    _telefonoAlto(t);
    await t.pumpWidget(_montar(_ApiFalsa(
        lectura: _borrador(),
        ips: <int, Map<String, dynamic>>{
          20061: <String, dynamic>{
            'libres': <String>['172.16.9.2'],
            'advertencia': 'Los equipos de red no estan en el listado del proveedor.',
          },
        })));
    await t.pumpAndSettle();
    await t.tap(find.text('SERVIDOR 2'));
    await t.pumpAndSettle();

    expect(find.textContaining('equipos de red'), findsOneWidget);
  });

  testWidgets('sin direcciones para ofrecer, se dice el motivo', (WidgetTester t) async {
    _telefonoAlto(t);
    await t.pumpWidget(_montar(_ApiFalsa(
        lectura: _borrador(),
        ips: <int, Map<String, dynamic>>{
          20061: <String, dynamic>{
            'libres': const <dynamic>[],
            'motivo': 'la ocupacion de IP no se ha sincronizado nunca',
          },
        })));
    await t.pumpAndSettle();
    await t.tap(find.text('SERVIDOR 2'));
    await t.pumpAndSettle();

    expect(find.textContaining('no se ha sincronizado'), findsOneWidget);
  });

  testWidgets('cambiar de servidor SUELTA la IP elegida', (WidgetTester t) async {
    //  Dejarla puesta seria mandar una direccion de otro rango sin que nadie
    //  lo note.
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(lectura: _borrador(), ips: <int, Map<String, dynamic>>{
      20061: <String, dynamic>{'libres': <String>['172.16.9.2']},
      20053: <String, dynamic>{'libres': <String>['10.0.0.5']},
    });
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    await t.tap(find.text('SERVIDOR 2'));
    await t.pumpAndSettle();
    await t.tap(find.text('172.16.9.2'));
    await t.pumpAndSettle();

    await t.tap(find.text('SERVIDOR 1'));
    await t.pumpAndSettle();

    expect(find.text('172.16.9.2'), findsNothing, reason: 'la de la zona vieja se va');
    expect(find.text('10.0.0.5'), findsOneWidget);
    expect(api.zonasPedidas, <int>[20061, 20053]);
  });

  testWidgets('la IP elegida VIAJA en el contrato', (WidgetTester t) async {
    //  LAS DOS PRUEBAS DE ARRIBA NO ALCANZABAN, y lo dijeron las mutaciones:
    //  quitar `if (_ip != null) 'ip': _ip` del cuerpo no rompia ninguna,
    //  porque ninguna FIRMABA con una direccion elegida. Mirar la pantalla no
    //  prueba que el dato salga.
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(lectura: _borrador(), ips: <int, Map<String, dynamic>>{
      20061: <String, dynamic>{'libres': <String>['172.16.9.2', '172.16.9.3']},
    });
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    await t.tap(find.text('SERVIDOR 2'));
    await t.pumpAndSettle();
    await t.tap(find.text('172.16.9.3'));
    await t.pump();
    await t.drag(find.byType(LienzoDeFirma), const Offset(140, -40));
    await t.pump();

    await t.runAsync(() async {
      await t.tap(find.text('Crear el contrato'));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await t.pumpAndSettle();

    expect(api.enviado!['ip'], '172.16.9.3');
  });

  testWidgets('cambiar de servidor NO deja viajar la IP de la zona vieja',
      (WidgetTester t) async {
    //  El control de la de arriba: sin soltar `_ip` al cambiar de zona, el
    //  contrato saldria con una direccion de OTRO rango, y eso no se ve en la
    //  pantalla porque el chip de la zona vieja ya no esta.
    _telefonoAlto(t);
    final _ApiFalsa api = _ApiFalsa(lectura: _borrador(), ips: <int, Map<String, dynamic>>{
      20061: <String, dynamic>{'libres': <String>['172.16.9.2']},
      20053: <String, dynamic>{'libres': <String>['10.0.0.5']},
    });
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    await t.tap(find.text('SERVIDOR 2'));
    await t.pumpAndSettle();
    await t.tap(find.text('172.16.9.2'));
    await t.pump();

    //  Se arrepiente y cambia de servidor, SIN elegir una nueva.
    await t.tap(find.text('SERVIDOR 1'));
    await t.pumpAndSettle();

    await t.drag(find.byType(LienzoDeFirma), const Offset(140, -40));
    await t.pump();
    await t.runAsync(() async {
      await t.tap(find.text('Crear el contrato'));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await t.pumpAndSettle();

    expect(api.enviado!.containsKey('ip'), isFalse,
        reason: 'la de la zona vieja no puede viajar');
    expect(api.enviado!['id_zona'], 20053);
  });

  testWidgets('con UN SOLO servidor las pide sola', (WidgetTester t) async {
    //  La zona se elige sola en la carga, asi que el onChanged del radio no
    //  corre: sin este camino la pantalla quedaba sin nada que ofrecer.
    _telefonoAlto(t);
    final Map<String, dynamic> uno = _borrador();
    uno['servidores'] = <Map<String, dynamic>>[
      <String, dynamic>{'id_zona': 20053, 'nombre': 'SERVIDOR 1'},
    ];
    final _ApiFalsa api = _ApiFalsa(lectura: uno, ips: <int, Map<String, dynamic>>{
      20053: <String, dynamic>{'libres': <String>['10.0.0.5']},
    });
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    expect(api.zonasPedidas, <int>[20053]);
    expect(find.text('10.0.0.5'), findsOneWidget);
  });

  test('lleva contrato: por la labor, y por el código de la plantilla como respaldo', () {
    expect(llevaContrato(<String, dynamic>{'labor': 'instalacion'}), isTrue);
    expect(llevaContrato(<String, dynamic>{'tipo_codigo': 'instalacion_fibra'}), isTrue);
    expect(llevaContrato(<String, dynamic>{'labor': 'correctivo', 'tipo_codigo': 'soporte'}),
        isFalse);
    expect(llevaContrato(null), isFalse);
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
}
