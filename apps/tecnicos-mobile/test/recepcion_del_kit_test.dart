import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/materiales/kit_de_jornada.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:campo/features/materiales/recepcion_del_kit.dart';
import 'package:campo/features/materiales/widgets/tarjeta_de_recepcion.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';
import 'apoyo/sesion_en_el_telefono.dart';

/// LA RECEPCIÓN DEL KIT (28/10/2026, fase 2 del material del día).
///
/// Lo que se mide es lo que llega al servidor —qué se confirmó, con qué
/// diferencias, qué serie se escaneó— y no solo que el botón exista: una
/// tarjeta que dibuja «Recibí todo» y manda `conforme: false` pasaría una
/// prueba que solo busca el texto.

class _Confirmacion {
  _Confirmacion(this.id, this.conforme, this.diferencias);
  final String id;
  final bool conforme;
  final List<Diferencia> diferencias;
}

/// El servidor, sin red. Cada `leer()` devuelve el siguiente estado; el
/// último se repite.
class _ServidorFalso implements RecepcionDelKit {
  _ServidorFalso(this.estados);

  final List<PendienteDeRecepcion> estados;
  int lecturas = 0;
  final List<_Confirmacion> confirmados = <_Confirmacion>[];
  final List<String> escaneados = <String>[];
  RecepcionError? fallarLeer;
  RecepcionError? fallarConfirmar;

  @override
  Future<PendienteDeRecepcion> leer() async {
    if (fallarLeer != null) throw fallarLeer!;
    final PendienteDeRecepcion p =
        estados[lecturas < estados.length ? lecturas : estados.length - 1];
    lecturas++;
    return p;
  }

  @override
  Future<void> confirmar(String entregaId,
      {required bool conforme, List<Diferencia> diferencias = const <Diferencia>[]}) async {
    if (fallarConfirmar != null) throw fallarConfirmar!;
    confirmados.add(_Confirmacion(entregaId, conforme, diferencias));
  }

  @override
  Future<String> escanear(String serie) async {
    escaneados.add(serie);
    return 'Recibido: ONT Huawei · $serie';
  }
}

const EntregaPorConfirmar _entrega = EntregaPorConfirmar(
  id: 'e-1',
  acta: 'MAT-20261028-abcd1234',
  bodega: 'Bodega Norte',
  lineas: <LineaDeEntrega>[
    LineaDeEntrega(codigo: 'DROP', nombre: 'Cable drop', unidad: 'm', cantidad: '100'),
    LineaDeEntrega(codigo: 'DROP', nombre: 'Cable drop', unidad: 'm', cantidad: '50'),
    LineaDeEntrega(codigo: 'CONN', nombre: 'Conector SC/APC', unidad: 'und', cantidad: '10'),
    LineaDeEntrega(
        codigo: 'ONT', nombre: 'ONT Huawei', unidad: 'und', cantidad: '1', serie: 'HWT111'),
  ],
);

const PendienteDeRecepcion _conEntrega =
    PendienteDeRecepcion(porConfirmar: <EntregaPorConfirmar>[_entrega]);

const PendienteDeRecepcion _conEquipos = PendienteDeRecepcion(
  porEscanear: <EquipoPorEscanear>[
    EquipoPorEscanear(codigo: 'ONT', nombre: 'ONT Huawei', bodega: 'Bodega Norte', cantidad: '2'),
  ],
);

const PendienteDeRecepcion _nada = PendienteDeRecepcion();

Widget _enApp(Widget hijo) => MaterialApp(
      theme: AppTheme.lightTheme,
      home: Scaffold(body: SingleChildScrollView(child: hijo)),
    );

void _pantallaAlta(WidgetTester tester) {
  tester.view.physicalSize = const Size(1000, 3000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  group('Tarjeta de recepción', () {
    testWidgets('1. Sin nada pendiente no dibuja nada', (WidgetTester t) async {
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_nada]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s)));
      await t.pumpAndSettle();

      expect(find.text('ENTREGA POR CONFIRMAR'), findsNothing);
      expect(find.text('EQUIPOS POR ESCANEAR'), findsNothing);
      expect(s.lecturas, 1);
    });

    testWidgets('2. «Recibí todo» confirma ESA entrega como conforme, y se va',
        (WidgetTester t) async {
      _pantallaAlta(t);
      int bajadas = 0;
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEntrega, _nada]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(
        recepcion: s,
        alCambiar: () async => bajadas++,
      )));
      await t.pumpAndSettle();

      expect(find.text('Acta MAT-20261028-abcd1234'), findsOneWidget);
      expect(find.text('Desde Bodega Norte'), findsOneWidget);
      expect(find.text('ONT Huawei: 1 und · HWT111'), findsOneWidget);

      await t.tap(find.text('Recibí todo'));
      await t.pumpAndSettle();

      expect(s.confirmados, hasLength(1));
      expect(s.confirmados.single.id, 'e-1');
      expect(s.confirmados.single.conforme, isTrue);
      expect(s.confirmados.single.diferencias, isEmpty);
      // La custodia cambió: se pide bajarla, y la tarjeta se vuelve a leer.
      expect(bajadas, 1);
      expect(find.text('ENTREGA POR CONFIRMAR'), findsNothing);
      expect(find.text('Listo: confirmaste que recibiste todo.'), findsOneWidget);
    });

    testWidgets('3. «No coincide» manda SOLO lo que cambió, con su motivo',
        (WidgetTester t) async {
      _pantallaAlta(t);
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEntrega, _nada]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s)));
      await t.pumpAndSettle();

      await t.tap(find.text('No coincide'));
      await t.pumpAndSettle();

      // Las dos líneas de drop son UN campo, con lo del acta sumado; el equipo
      // con serie no se corrige acá.
      expect(find.byKey(const ValueKey<String>('recibido-DROP')), findsOneWidget);
      expect(find.text('Cable drop (en el acta: 150 m)'), findsOneWidget);
      expect(find.byKey(const ValueKey<String>('recibido-ONT')), findsNothing);

      await t.enterText(find.byKey(const ValueKey<String>('recibido-DROP')), '120,5');
      await t.enterText(find.byKey(const ValueKey<String>('motivo')), 'Un rollo venía cortado');
      await t.tap(find.text('Enviar'));
      await t.pumpAndSettle();

      expect(s.confirmados, hasLength(1));
      final _Confirmacion c = s.confirmados.single;
      expect(c.conforme, isFalse);
      expect(c.diferencias, hasLength(1));
      expect(c.diferencias.single.codigo, 'DROP');
      expect(c.diferencias.single.recibido, '120.5');
      expect(c.diferencias.single.motivo, 'Un rollo venía cortado');
      expect(find.text('Quedó anotado lo que no llegó.'), findsOneWidget);
    });

    testWidgets('4. «No coincide» sin cambiar nada, o sin motivo, no manda',
        (WidgetTester t) async {
      _pantallaAlta(t);
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEntrega]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s)));
      await t.pumpAndSettle();
      await t.tap(find.text('No coincide'));
      await t.pumpAndSettle();

      await t.enterText(find.byKey(const ValueKey<String>('motivo')), 'algo');
      await t.tap(find.text('Enviar'));
      await t.pumpAndSettle();
      expect(find.text('Cambiá la cantidad de lo que no te llegó completo.'), findsOneWidget);

      await t.enterText(find.byKey(const ValueKey<String>('recibido-CONN')), '8');
      await t.enterText(find.byKey(const ValueKey<String>('motivo')), '   ');
      await t.tap(find.text('Enviar'));
      await t.pumpAndSettle();
      expect(find.text('Contá qué pasó: queda escrito para la bodega.'), findsOneWidget);

      expect(s.confirmados, isEmpty);
    });

    testWidgets('5. Un acta solo con equipos con serie no ofrece «No coincide»',
        (WidgetTester t) async {
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[
        const PendienteDeRecepcion(porConfirmar: <EntregaPorConfirmar>[
          EntregaPorConfirmar(id: 'e-2', acta: 'A-2', bodega: '', lineas: <LineaDeEntrega>[
            LineaDeEntrega(
                codigo: 'ONT', nombre: 'ONT Huawei', unidad: 'und', cantidad: '1', serie: 'X'),
          ]),
        ]),
      ]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s)));
      await t.pumpAndSettle();

      expect(find.text('Recibí todo'), findsOneWidget);
      expect(find.text('No coincide'), findsNothing);
    });

    testWidgets('6. Escanear manda la serie leída, limpia, y dice qué recibió',
        (WidgetTester t) async {
      int bajadas = 0;
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEquipos, _nada]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(
        recepcion: s,
        leerCodigo: (_) async => '  HWT222 ',
        alCambiar: () async => bajadas++,
      )));
      await t.pumpAndSettle();

      expect(find.text('ONT Huawei: 2 por escanear (Bodega Norte)'), findsOneWidget);
      await t.tap(find.text('Escanear'));
      await t.pumpAndSettle();

      expect(s.escaneados, <String>['HWT222']);
      expect(bajadas, 1);
      expect(find.text('Recibido: ONT Huawei · HWT222'), findsOneWidget);
      expect(find.text('EQUIPOS POR ESCANEAR'), findsNothing);
    });

    testWidgets('7. Cancelar el lector no manda nada', (WidgetTester t) async {
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEquipos]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(
        recepcion: s,
        leerCodigo: (_) async => null,
      )));
      await t.pumpAndSettle();
      await t.tap(find.text('Escanear'));
      await t.pumpAndSettle();

      expect(s.escaneados, isEmpty);
    });

    testWidgets('8. Un rechazo del servidor se dice y la entrega queda',
        (WidgetTester t) async {
      _pantallaAlta(t);
      int bajadas = 0;
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEntrega])
        ..fallarConfirmar = const RecepcionError('Esa entrega no es tuya o no existe.');
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(
        recepcion: s,
        alCambiar: () async => bajadas++,
      )));
      await t.pumpAndSettle();

      await t.tap(find.text('Recibí todo'));
      await t.pumpAndSettle();

      expect(find.text('Esa entrega no es tuya o no existe.'), findsOneWidget);
      expect(find.text('ENTREGA POR CONFIRMAR'), findsOneWidget);
      expect(bajadas, 0);
    });

    testWidgets('9. Sin señal lo dice en una línea', (WidgetTester t) async {
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEntrega])
        ..fallarLeer = const RecepcionError('Sin conexión con el servidor: se confirma cuando haya señal.');
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s)));
      await t.pumpAndSettle();

      expect(find.text('Sin conexión con el servidor: se confirma cuando haya señal.'),
          findsOneWidget);
      expect(find.text('Recibí todo'), findsNothing);
    });

    testWidgets('13. Cuando le avisan que el kit se bajó, vuelve a leer',
        (WidgetTester t) async {
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_nada, _conEntrega]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s, recargarCon: 0)));
      await t.pumpAndSettle();
      expect(find.text('ENTREGA POR CONFIRMAR'), findsNothing);

      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s, recargarCon: 1)));
      await t.pumpAndSettle();
      expect(find.text('ENTREGA POR CONFIRMAR'), findsOneWidget);
    });

    testWidgets('14. Sin señal después, no borra lo que ya estaba pendiente',
        (WidgetTester t) async {
      _pantallaAlta(t);
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEntrega]);
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s, recargarCon: 0)));
      await t.pumpAndSettle();

      s.fallarLeer = const RecepcionError('Sin conexión con el servidor: se confirma cuando haya señal.');
      await t.pumpWidget(_enApp(TarjetaDeRecepcion(recepcion: s, recargarCon: 1)));
      await t.pumpAndSettle();

      expect(find.text('Sin conexión con el servidor: se confirma cuando haya señal.'),
          findsOneWidget);
      expect(find.text('Recibí todo'), findsOneWidget);
    });
  });

  group('Con la base del teléfono', () {
    final JornadaDePrueba j = JornadaDePrueba('recepcion_del_kit.db');

    setUpAll(j.prepararElEntorno);
    setUp(j.empezar);
    tearDown(j.terminar);
    tearDownAll(j.cerrarTodo);

    testWidgets('15. Bajar el kit relee la recepción: la entrega de la mañana aparece sola',
        (WidgetTester t) async {
      //  La pestaña queda viva todo el día: si el Supervisor carga a las 7:00
      //  con la app abierta, la tarjeta se entera cuando la sincronización
      //  escribe el kit, no cuando el técnico cierra y abre.
      //  Con kit desde antes: si pasara de vacío a lleno, la tarjeta se
      //  recrearía y leería igual, y la prueba no mediría la relectura.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
      });
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_nada, _conEntrega]);
      await montarConBaseReal(
        t,
        j.enApp(MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
          recepcion: s,
        )),
      );
      expect(find.text('ENTREGA POR CONFIRMAR'), findsNothing);
      expect(find.text('ESTADO DE CUSTODIA'), findsOneWidget);

      await t.runAsync(() => j.sembrarKit(recibido: '20'));
      await esperarLaBase(t);

      expect(find.text('ENTREGA POR CONFIRMAR'), findsOneWidget);
    });
  });

  group('Materiales con la recepción', () {
    Widget pantalla(Widget hijo) => MaterialApp(
          theme: AppTheme.lightTheme,
          home: Scaffold(body: hijo),
        );

    testWidgets('10. Con el kit vacío aparece igual: hay equipos por escanear',
        (WidgetTester t) async {
      _pantallaAlta(t);
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEquipos]);
      await t.pumpWidget(pantalla(MaterialesScreen(
        mostrarDatosFuturos: false,
        kit: const KitDeJornada.vacio(),
        recepcion: s,
      )));
      await t.pumpAndSettle();

      expect(find.text('EQUIPOS POR ESCANEAR'), findsOneWidget);
      expect(find.textContaining('no hay material entregado a tu nombre'), findsOneWidget);
    });

    testWidgets('11. Con kit, va arriba de la custodia; al recibir, se avisa',
        (WidgetTester t) async {
      _pantallaAlta(t);
      int recibidos = 0;
      final _ServidorFalso s = _ServidorFalso(<PendienteDeRecepcion>[_conEntrega, _nada]);
      await t.pumpWidget(pantalla(MaterialesScreen(
        mostrarDatosFuturos: false,
        kit: const KitDeJornada(materiales: <MaterialEnCustodia>[
          MaterialEnCustodia(
            categoria: 'Consumibles',
            nombre: 'Conector SC/APC',
            detalle: '',
            clase: ClaseMaterial.consumible,
            recibidos: 10,
            usados: 0,
            unidad: 'unidades',
          ),
        ], acta: '', sinSubir: 0, conNovedad: <MovimientoConNovedad>[]),
        recepcion: s,
        alRecibir: () async => recibidos++,
      )));
      await t.pumpAndSettle();

      expect(find.text('ENTREGA POR CONFIRMAR'), findsOneWidget);
      expect(
        t.getTopLeft(find.text('ENTREGA POR CONFIRMAR')).dy,
        lessThan(t.getTopLeft(find.text('ESTADO DE CUSTODIA')).dy),
      );

      await t.tap(find.text('Recibí todo'));
      await t.pumpAndSettle();
      expect(recibidos, 1);
    });

    testWidgets('12. Sin recepción no la dibuja ni la pide', (WidgetTester t) async {
      await t.pumpWidget(pantalla(const MaterialesScreen(
        mostrarDatosFuturos: false,
        kit: KitDeJornada.vacio(),
      )));
      await t.pumpAndSettle();

      expect(find.byType(TarjetaDeRecepcion), findsNothing);
    });
  });
}
