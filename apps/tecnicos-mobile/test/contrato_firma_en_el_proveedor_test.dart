// EL CLIENTE FIRMA EL CONTRATO DEL PROVEEDOR (26/11/2026).
//
// Lo que se afirma: con la empresa en ese modo, la pantalla no pide la firma
// de Dexter y el botón dice «Confirmar contrato»; no viaja ninguna firma; si el
// servidor dice que faltan la cédula o el recibo, se muestra tal cual; con el
// contrato de WispHub listo, «Firmar en WispHub» pide el enlace y lo abre
// fuera de la app; «Ya firmó: comprobar» lo lee y, firmado, lo dice.
import 'package:campo/core/storage/ubicacion_de_captura.dart';
import 'package:campo/features/contrato/contrato_screen.dart';
import 'package:campo/features/ejecucion/widgets/firma_del_cliente.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _enlace = 'http://portal.example/login-panel/AAAA.BBBB.CCCC/';

class _Api extends ApiDelContrato {
  _Api({required this.lectura, this.errorAlConfirmar, this.firmaDespues = 'lista'});

  Map<String, dynamic> lectura;
  final String? errorAlConfirmar;
  final String firmaDespues;
  Map<String, dynamic>? enviado;
  int lecturas = 0;
  final List<String> abiertos = <String>[];
  int enlacesPedidos = 0;
  bool firmadoEnWispHub = false;
  final List<String> reintentos = <String>[];

  static Map<String, dynamic> contrato(String estadoFirma,
          {bool firmado = false, bool sePuedePedir = false}) =>
      <String, dynamic>{
        'id': 'c-611',
        'numero': 'C-2026-000611',
        'estado': 'instalacion',
        'cliente': <String, dynamic>{'nombre': 'Laura', 'apellido': 'Gómez'},
        'plan': 'Fibra 300 Mb',
        'servidor': <String, dynamic>{'id_zona': 20061, 'nombre': 'SERVIDOR 2'},
        'alta': <String, dynamic>{'estado': null},
        'firma_proveedor': <String, dynamic>{
          'activa': true,
          'estado': firmado ? 'firmada' : estadoFirma,
          'puede_firmar': !firmado && estadoFirma == 'lista',
          'firmado': firmado,
          'se_puede_pedir': sePuedePedir,
          'detalle': estadoFirma == 'fallida' ? 'El proveedor no guardó el contrato.' : null,
        },
      };

  @override
  Future<RespuestaDelServidor> leer(String ordenId) async {
    lecturas++;
    return RespuestaDelServidor(cuerpo: lectura);
  }

  @override
  Future<RespuestaDelServidor> firmar(String ordenId, Map<String, dynamic> cuerpo) async {
    enviado = cuerpo;
    if (errorAlConfirmar != null) return RespuestaDelServidor(error: errorAlConfirmar);
    return RespuestaDelServidor(cuerpo: <String, dynamic>{'contrato': contrato(firmaDespues)});
  }

  @override
  Future<({String? enlace, String? error})> enlaceDeFirma(String ordenId) async {
    enlacesPedidos++;
    return (enlace: _enlace, error: null);
  }

  @override
  Future<bool> abrir(String enlace) async {
    abiertos.add(enlace);
    return true;
  }

  @override
  Future<RespuestaDelServidor> volverAPreparar(String contratoId) async {
    reintentos.add(contratoId);
    return RespuestaDelServidor(cuerpo: <String, dynamic>{'contrato': contrato('pedida')});
  }

  @override
  Future<RespuestaDelServidor> comprobarFirma(String ordenId) async =>
      RespuestaDelServidor(cuerpo: <String, dynamic>{
        'contrato': contrato('lista', firmado: firmadoEnWispHub),
      });
}

Map<String, dynamic> _borrador() => <String, dynamic>{
      'contrato': null,
      'firma_en_el_proveedor': true,
      'borrador': <String, dynamic>{
        'origen': 'solicitud',
        'cliente': <String, dynamic>{
          'nombre': 'Laura', 'apellido': 'Gómez', 'tipo_documento': 'CC',
          'numero_documento': '1043000000', 'telefono': '3000000000',
          'correo': '', 'direccion': 'Cra 21 # 45-12', 'barrio': 'Villa Estadio',
        },
        'plan': 'Fibra 300 Mb',
      },
      'servidores': <Map<String, dynamic>>[
        <String, dynamic>{'id_zona': 20061, 'nombre': 'SERVIDOR 2'},
      ],
      'condiciones_cargadas': true,
    };

void _telefonoAlto(WidgetTester t) {
  t.view.physicalSize = const Size(1080, 5200);
  t.view.devicePixelRatio = 2.6;
  addTearDown(t.view.reset);
}

Widget _montar(ApiDelContrato api) => MaterialApp(
      home: ContratoScreen(ordenId: 'o-1', titulo: 'OT #611', api: api),
    );

Future<void> _confirmar(WidgetTester t) async {
  await t.runAsync(() async {
    await t.tap(find.text('Confirmar contrato'));
    await Future<void>.delayed(const Duration(milliseconds: 300));
  });
  await t.pump();
}

void main() {
  setUp(() {
    UbicacionDeCaptura.overrideParaPruebas =
        () async => <String, dynamic>{'lat': 10.9108, 'lng': -74.8186, 'precision_m': 6};
  });
  tearDown(() => UbicacionDeCaptura.overrideParaPruebas = null);

  testWidgets('SIN FIRMA DE DEXTER: no hay lienzo, el botón dice «Confirmar contrato» y no viaja firma',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final _Api api = _Api(lectura: _borrador());
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();

    expect(find.byType(LienzoDeFirma), findsNothing);
    expect(find.text('La firma, en WispHub'), findsOneWidget);
    await _confirmar(t);

    expect(api.enviado, isNotNull);
    expect(api.enviado!.containsKey('firma_png_base64'), isFalse);
    expect(find.text('Contrato confirmado'), findsOneWidget);
    expect(find.text('Firmar en WispHub'), findsOneWidget);
  });

  testWidgets('si faltan la cédula o el recibo, el servidor lo dice y se muestra tal cual',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final _Api api = _Api(
        lectura: _borrador(),
        errorAlConfirmar: 'Antes de confirmar falta: Recibo público, «Valor de la instalación» anotado.');
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    await _confirmar(t);
    expect(find.textContaining('falta: Recibo público, «Valor de la instalación»'), findsOneWidget);
    expect(find.text('Confirmar contrato'), findsOneWidget);
  });

  testWidgets('FIRMAR EN WISPHUB pide el enlace y lo abre fuera de la app', (WidgetTester t) async {
    _telefonoAlto(t);
    final _Api api = _Api(lectura: _borrador());
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    await _confirmar(t);

    await t.tap(find.text('Firmar en WispHub'));
    await t.pump();
    await t.pump();
    expect(api.enlacesPedidos, 1);
    expect(api.abiertos, <String>[_enlace]);
    expect(find.textContaining('vuelve y toca «Ya firmó: comprobar»'), findsOneWidget);
  });

  testWidgets('YA FIRMÓ: sin la firma lo dice; con la firma queda «Firmado»', (WidgetTester t) async {
    _telefonoAlto(t);
    final _Api api = _Api(lectura: _borrador());
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    await _confirmar(t);

    await t.tap(find.text('Ya firmó: comprobar'));
    await t.pump();
    await t.pump();
    expect(find.textContaining('Todavía no aparece la firma'), findsOneWidget);

    api.firmadoEnWispHub = true;
    await t.tap(find.text('Ya firmó: comprobar'));
    await t.pump();
    await t.pump();
    expect(find.text('El cliente firmó el contrato en WispHub.'), findsOneWidget);
    expect(find.text('Firmar en WispHub'), findsNothing);
    expect(find.text('Contrato firmado'), findsOneWidget);
  });

  testWidgets('SI WISPHUB DIJO QUE NO: «Volver a intentar» lo pide otra vez y vuelve a esperar',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final _Api api = _Api(lectura: <String, dynamic>{
      'contrato': _Api.contrato('fallida', sePuedePedir: true),
      'firma_en_el_proveedor': true,
    });
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    expect(find.textContaining('Puedes volver a intentarlo'), findsOneWidget);

    await t.tap(find.text('Volver a intentar'));
    await t.pump();
    await t.pump();
    expect(api.reintentos, <String>['c-611']);
    expect(find.textContaining('Guardando el contrato en WispHub'), findsOneWidget);
    expect(find.text('Volver a intentar'), findsNothing);
  });

  testWidgets('SI NO SE SABE SI QUEDÓ: no hay «Volver a intentar», se avisa a la oficina',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final _Api api = _Api(lectura: <String, dynamic>{
      'contrato': _Api.contrato('por_revisar', sePuedePedir: true),
      'firma_en_el_proveedor': true,
    });
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    expect(find.text('Volver a intentar'), findsNothing);
    expect(find.textContaining('Avísale a la oficina'), findsOneWidget);
  });

  testWidgets('MIENTRAS SE PREPARA lo dice, y se vuelve a leer solo hasta que queda listo',
      (WidgetTester t) async {
    _telefonoAlto(t);
    final Duration antesDelIntervalo = ContratoScreenRelectura.intervalo;
    ContratoScreenRelectura.intervalo = const Duration(milliseconds: 200);
    addTearDown(() => ContratoScreenRelectura.intervalo = antesDelIntervalo);
    final _Api api = _Api(lectura: _borrador(), firmaDespues: 'pedida');
    await t.pumpWidget(_montar(api));
    await t.pumpAndSettle();
    await _confirmar(t);
    expect(find.textContaining('Guardando el contrato en WispHub'), findsOneWidget);
    expect(find.text('Firmar en WispHub'), findsNothing);

    api.lectura = <String, dynamic>{'contrato': _Api.contrato('lista')};
    final int antes = api.lecturas;
    //  El temporizador nace con el reloj real (la confirmación corre en
    //  `runAsync`): se espera de verdad, con un intervalo corto.
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 500)));
    await t.pump();
    expect(api.lecturas, antes + 1, reason: 'se volvió a leer solo');
    expect(find.text('Firmar en WispHub'), findsOneWidget);
  });
}
