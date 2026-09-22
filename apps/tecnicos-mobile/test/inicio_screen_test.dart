import 'dart:async';
import 'dart:ui' as ui;

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/mock/field_mock_data.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/inicio/inicio_screen.dart';
import 'package:campo/features/trabajo/seleccion_jornada.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _orden({
  required String id,
  required int numero,
  required String estado,
  String cliente = 'Cliente de prueba',
  DateTime? compromiso,
}) {
  return <String, dynamic>{
    'id': id,
    'numero': numero,
    'estado': estado,
    'cliente_nombre': cliente,
    'direccion': 'Calle 45 #12-30',
    'telefono': '',
    'tipo_nombre': 'Instalación FTTH',
    'tipo_codigo': 'ftth_instalacion',
    'schema_version': 1,
    'diagnostico_previo_ia': '',
    'fecha_compromiso': compromiso?.toIso8601String(),
  };
}

TrabajoVista _vista({
  required String id,
  required int numero,
  required String estado,
  DateTime? compromiso,
}) =>
    TrabajoVista.desdeOrden(_orden(
      id: id,
      numero: numero,
      estado: estado,
      compromiso: compromiso,
    ));

class _Banco {
  _Banco({this.filas = const <Map<String, dynamic>>[], this.falla = false});

  final List<Map<String, dynamic>> filas;
  final bool falla;

  final StreamController<SyncStatus> avisos = StreamController<SyncStatus>.broadcast();
  int cargas = 0;
  final List<String> abiertos = <String>[];

  late final OrdenesJornada ordenes = OrdenesJornada(
    leerOrdenes: () async {
      cargas++;
      if (falla) throw StateError('base ilegible');
      return filas;
    },
    sincronizar: () async {},
    avisosDeSincronizacion: avisos.stream,
  );

  Widget app({
    bool mostrarDatosFuturos = false,
    SyncSummary? resumen,
    VoidCallback? onVerTodos,
  }) =>
      MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: InicioScreen(
            ordenes: ordenes,
            nombreTecnico: 'Carlos',
            mostrarDatosFuturos: mostrarDatosFuturos,
            resumenSincronizacion: resumen,
            onVerTodos: onVerTodos,
            abrirTrabajo: (BuildContext contexto, TrabajoVista trabajo) async {
              abiertos.add(trabajo.id);
              await Navigator.of(contexto).push(
                MaterialPageRoute<void>(
                  builder: (BuildContext c) => Scaffold(
                    body: Center(
                      child: ElevatedButton(
                        onPressed: () => Navigator.of(c).pop(),
                        child: const Text('Cerrar detalle'),
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      );

  Future<void> cerrar() async {
    await avisos.close();
    ordenes.dispose();
  }
}

/// Inicio es una lista larga: en el alto de prueba por defecto, lo de abajo ni
/// siquiera se construye. Con una pantalla alta entra todo y las pruebas
/// hablan del contenido, no del scroll.
void _pantallaAlta(WidgetTester tester) {
  tester.view.physicalSize = const Size(1000, 3200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  final ahora = DateTime.now();
  final enUnaHora = ahora.add(const Duration(hours: 1));
  final enDosHoras = ahora.add(const Duration(hours: 2));

  group('Lectura de la jornada, compartida con Trabajo', () {
    test('1. Sin ninguno empezado no hay trabajo en curso', () {
      final trabajos = <TrabajoVista>[
        _vista(id: '1', numero: 1, estado: 'asignada'),
        _vista(id: '2', numero: 2, estado: 'completada_campo'),
      ];

      expect(SeleccionJornada.enCursoDestacado(trabajos), isNull);
      expect(SeleccionJornada.hayVariosEnCurso(trabajos), isFalse);
    });

    test('2. Con uno empezado, ese es el trabajo en curso', () {
      final trabajos = <TrabajoVista>[
        _vista(id: '1', numero: 1, estado: 'asignada'),
        _vista(id: '2', numero: 2, estado: 'en_sitio'),
      ];

      expect(SeleccionJornada.enCursoDestacado(trabajos)!.id, '2');
      expect(SeleccionJornada.hayVariosEnCurso(trabajos), isFalse);
    });

    test('3. Con varios empezados elige siempre el mismo y avisa', () {
      final trabajos = <TrabajoVista>[
        _vista(id: 'tarde', numero: 9, estado: 'en_sitio', compromiso: enDosHoras),
        _vista(id: 'temprano', numero: 3, estado: 'en_camino', compromiso: enUnaHora),
      ];

      // El de compromiso mas temprano, sin importar el orden de la lista.
      expect(SeleccionJornada.enCursoDestacado(trabajos)!.id, 'temprano');
      expect(
        SeleccionJornada.enCursoDestacado(trabajos.reversed.toList())!.id,
        'temprano',
        reason: 'la eleccion no puede depender del orden en que vino la base',
      );
      expect(SeleccionJornada.hayVariosEnCurso(trabajos), isTrue);
    });

    test('4. Los proximos van en orden y excluyen los empezados', () {
      final trabajos = <TrabajoVista>[
        _vista(id: 'b', numero: 2, estado: 'asignada', compromiso: enDosHoras),
        _vista(id: 'a', numero: 1, estado: 'asignada', compromiso: enUnaHora),
        _vista(id: 'curso', numero: 3, estado: 'en_sitio', compromiso: ahora),
        _vista(id: 'listo', numero: 4, estado: 'cerrada', compromiso: enUnaHora),
      ];

      final proximos = SeleccionJornada.proximos(trabajos, desde: ahora);
      expect(proximos.map((TrabajoVista t) => t.id).toList(), <String>['a', 'b']);
    });

    test('5. Una orden activa sin fecha no entra en la agenda, pero se cuenta', () {
      final trabajos = <TrabajoVista>[
        _vista(id: 'sin', numero: 7, estado: 'asignada'),
        _vista(id: 'con', numero: 8, estado: 'asignada', compromiso: enUnaHora),
      ];

      expect(
        SeleccionJornada.proximos(trabajos, desde: ahora)
            .map((TrabajoVista t) => t.id),
        <String>['con'],
      );
      expect(
        SeleccionJornada.activosSinFecha(trabajos).map((TrabajoVista t) => t.id),
        <String>['sin'],
        reason: 'existe y hay que hacerla: no se la esconde ni se le inventa hora',
      );
    });
  });

  group('Pantalla Inicio', () {
    testWidgets('6. Las metricas salen de las ordenes reales',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
        _orden(id: '2', numero: 2, estado: 'correccion_requerida'),
        _orden(id: '3', numero: 3, estado: 'completada_campo'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.textContaining('Carlos'), findsWidgets); // saludo con su nombre
      // El avance del día sale de las órdenes: una terminada de tres.
      expect(find.text('Avance Diario'), findsOneWidget);
      expect(find.text('1 / 3 OT'), findsOneWidget);
      expect(find.text('33%'), findsOneWidget);
      expect(find.textContaining('2 pendientes'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('7. Sin ninguno empezado no se muestra un trabajo como en curso',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada', cliente: 'Carlos Gomez', compromiso: enUnaHora),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('No tenés ningún trabajo empezado'), findsOneWidget);
      // El unico trabajo aparece en proximos, no como si estuviera empezado.
      expect(find.text('Próximos Trabajos'), findsOneWidget);
      expect(find.text('Instalación FTTH'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('8. Con varios empezados lo dice en vez de elegir en silencio',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'en_camino', cliente: 'Uno', compromiso: enUnaHora),
        _orden(id: '2', numero: 2, estado: 'en_sitio', cliente: 'Dos', compromiso: enDosHoras),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(
        find.text('Tenés 2 trabajos empezados a la vez. Se muestra el más próximo.'),
        findsOneWidget,
      );
      expect(find.text('Uno'), findsOneWidget); // el cliente del trabajo destacado
      await banco.cerrar();
    });

    testWidgets('9. Los trabajos sin fecha se avisan, sin inventarles hora',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
        _orden(id: '2', numero: 2, estado: 'asignada'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('Tenés 2 trabajos sin fecha asignada'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('10. Si no se puede leer la base, lo dice; no finge jornada vacia',
        (WidgetTester tester) async {
      final banco = _Banco(falla: true);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('No se pudieron leer tus trabajos'), findsOneWidget);
      expect(find.text('No te queda nada agendado'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('11. El bloque de sincronizacion usa la misma lectura de la cola',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(
        resumen: const SyncSummary(
          status: SyncStatus.idle,
          isSyncing: false,
          hasConnectionError: false,
          mutacionesPendientes: 2,
          mutacionesConflicto: 0,
          evidenciasPendientes: 0,
          datosDirty: 0,
        ),
      ));
      await tester.pumpAndSettle();

      expect(
        find.text('2 cambios guardados acá · esperando turno para enviarse'),
        findsOneWidget,
      );
      await banco.cerrar();
    });

    testWidgets('12. Fuera del modo demostracion no se muestran datos de ejemplo',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'en_sitio', cliente: 'Carlos Gomez', compromiso: enUnaHora),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('Mi Kit de Materiales'), findsNothing);
      expect(find.text('Diagnóstico Central OLT'), findsNothing);
      expect(find.textContaining('Vehículo'), findsNothing);
      expect(find.textContaining(FieldMockData.turno), findsNothing);
      expect(find.textContaining('SLA'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('13. En modo demostracion aparecen, y siguen siendo de ejemplo',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'en_sitio', cliente: 'Carlos Gomez', compromiso: enUnaHora),
      ]);
      _pantallaAlta(tester);
      await tester.pumpWidget(banco.app(mostrarDatosFuturos: true));
      await tester.pumpAndSettle();

      expect(find.text('Telemetría & Recursos de Turno'), findsOneWidget);
      expect(find.text('KIT DROP'), findsOneWidget);
      expect(find.text('VEHÍCULO'), findsOneWidget);
      expect(find.text('ACADEMIA'), findsOneWidget);
      expect(find.text('Diagnóstico Central OLT'), findsOneWidget);
      expect(find.textContaining(FieldMockData.turno), findsOneWidget);
      expect(
        find.text('${FieldMockData.kitDisponibles} disp.'),
        findsOneWidget,
      );
      // El modo de jornada, que el diseño nuevo pone arriba.
      expect(find.text('JORNADA EN CURSO'), findsOneWidget);
      expect(find.text('En ruta'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('17. El modo de jornada cambia lo que se ve y no toca ninguna orden',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
      ]);
      _pantallaAlta(tester);
      await tester.pumpWidget(banco.app(mostrarDatosFuturos: true));
      await tester.pumpAndSettle();

      final int cargasAntes = banco.cargas;
      await tester.tap(find.text('Pausa'));
      await tester.pumpAndSettle();

      // Cambia la selección…
      final SemanticsHandle semantica = tester.ensureSemantics();
      expect(
        tester.getSemantics(find.text('Pausa')).flagsCollection.isSelected,
        ui.Tristate.isTrue,
      );
      semantica.dispose();

      // …y no vuelve a leer la base ni abre ningún trabajo: no hay nada que
      // guardar, y decir lo contrario sería inventar una jornada.
      expect(banco.cargas, cargasAntes);
      expect(banco.abiertos, isEmpty);
      await banco.cerrar();
    });

    testWidgets('14. Abrir el trabajo en curso y volver recarga la jornada',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: 'abc', numero: 4832, estado: 'en_sitio', cliente: 'Carlos Gomez'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();
      final cargasAntes = banco.cargas;

      await tester.tap(find.textContaining('CONTINUAR OT #'));
      await tester.pumpAndSettle();
      expect(banco.abiertos, <String>['abc']);

      await tester.tap(find.text('Cerrar detalle'));
      await tester.pumpAndSettle();

      expect(banco.cargas, greaterThan(cargasAntes));
      expect(find.textContaining('Carlos'), findsWidgets);
      await banco.cerrar();
    });

    testWidgets('15. "Ver todos" lleva a Trabajo sin tocar los datos',
        (WidgetTester tester) async {
      var vecesQueLlamo = 0;
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada', compromiso: enUnaHora),
      ]);
      await tester.pumpWidget(banco.app(onVerTodos: () => vecesQueLlamo++));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Ver Agenda'));
      await tester.pumpAndSettle();
      expect(vecesQueLlamo, 1);
      await banco.cerrar();
    });

    testWidgets('16. Una sincronizacion exitosa actualiza la jornada una sola vez',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();
      final antes = banco.cargas;

      banco.avisos.add(SyncStatus.success);
      await tester.pumpAndSettle();
      expect(banco.cargas, antes + 1);

      banco.avisos.add(SyncStatus.error);
      await tester.pumpAndSettle();
      expect(banco.cargas, antes + 1);
      await banco.cerrar();
    });
  });
}
