import 'dart:async';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/inicio/inicio_screen.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:campo/features/trabajo/seleccion_jornada.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// El inicio, con datos reales y nada más.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// Que en esta pantalla **no quede una sola cifra inventada**. Hasta acá el
/// inicio mostraba un vehículo, un curso obligatorio y una potencia de la OLT
/// que no existían en ningún backend: se veían igual que los números buenos, y
/// un técnico no tiene forma de distinguirlos. La prueba que lo cuida es la
/// que busca esos textos y exige no encontrarlos.
///
/// Y que la pantalla **no decida por su cuenta** cuál es el próximo trabajo.
/// Esa regla vive en `ResumenDeInicio`, probada aparte; acá se verifica que lo
/// que se dibuja sea lo que esa lógica eligió.

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

/// Una jornada como la que baja el servidor. `hay: false` es el espejo vacío:
/// todavía no sincronizó, o no hay kit entregado.
EstadoDeJornada _jornada({
  bool hay = true,
  String recibido = '24',
  String consumido = '14',
  String aDevolver = '10',
  int diferencias = 0,
  List<String> motivos = const <String>[],
  int sinSubir = 0,
  bool cerrada = false,
  bool cierreTomado = false,
}) =>
    EstadoDeJornada(
      recibido: recibido,
      consumido: consumido,
      aDevolver: aDevolver,
      devuelto: '0',
      diferencias: diferencias,
      ordenesAsignadas: 0,
      ordenesCompletadas: 0,
      materiales: const <MaterialDeJornada>[],
      transferencias: const <TransferenciaPendiente>[],
      motivos: motivos,
      sinSubir: sinSubir,
      cerrada: cerrada,
      hayJornada: hay,
      cierreTomado: cierreTomado,
    );

SyncSummary _sync({
  int pendientes = 0,
  int conflicto = 0,
  int evidencias = 0,
  bool sinConexion = false,
}) =>
    SyncSummary(
      status: SyncStatus.idle,
      isSyncing: false,
      hasConnectionError: sinConexion,
      mutacionesPendientes: pendientes,
      mutacionesConflicto: conflicto,
      evidenciasPendientes: evidencias,
      datosDirty: 0,
    );

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

  /// La jornada se inyecta siempre: sin eso la pantalla iría a la base real y
  /// la prueba dependería del almacenamiento del entorno, no del caso.
  Widget app({
    SyncSummary? resumen,
    EstadoDeJornada? jornada,
    VoidCallback? onVerTodos,
    DateTime? ahora,
  }) =>
      MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: InicioScreen(
            ordenes: ordenes,
            nombreTecnico: 'Carlos',
            resumenSincronizacion: resumen,
            jornada: jornada ?? _jornada(hay: false),
            onVerTodos: onVerTodos,
            ahora: ahora,
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

  group('6. Lo que se ve sale de la jornada real', () {
    testWidgets('El avance del día lo cuentan las órdenes, no una constante',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
        _orden(id: '2', numero: 2, estado: 'correccion_requerida'),
        _orden(id: '3', numero: 3, estado: 'completada_campo'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.textContaining('Carlos'), findsWidgets);
      expect(find.text('1 de 3'), findsOneWidget);
      expect(find.text('33%'), findsOneWidget);
      expect(find.textContaining('2 pendientes'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Un trabajo hecho y sin subir ya cuenta como hecho',
        (WidgetTester tester) async {
      // Decirle pendiente le diría al técnico que todavía tiene que ir.
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'completada_pendiente_sync'),
        _orden(id: '2', numero: 2, estado: 'asignada'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('1 de 2'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('El kit son los números de la jornada, no una cuenta propia',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(
        jornada: _jornada(recibido: '24', consumido: '14', aDevolver: '10'),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Materiales'), findsOneWidget);
      expect(find.text('Recibido'), findsOneWidget);
      expect(find.text('24'), findsOneWidget);
      expect(find.text('14'), findsOneWidget);
      expect(find.text('10'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Sin jornada cargada no se dibuja un kit en cero',
        (WidgetTester tester) async {
      // "0 disponible" y "todavía no sincronizó" se ven igual y significan lo
      // contrario: ante la duda, no se afirma.
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(jornada: _jornada(hay: false)));
      await tester.pumpAndSettle();

      expect(find.text('Materiales'), findsNothing);
      expect(find.text('Recibido'), findsNothing);
      await banco.cerrar();
    });
  });

  group('7. No queda ninguna cifra inventada', () {
    testWidgets('Vehículo, academia y la potencia de la OLT ya no se dibujan',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'en_sitio', compromiso: enUnaHora),
      ]);
      await tester.pumpWidget(banco.app(jornada: _jornada()));
      await tester.pumpAndSettle();

      for (final String falso in <String>[
        'VEHÍCULO',
        'ACADEMIA',
        'KIT DROP',
        'ENGINE SYNC',
        'Diagnóstico Central OLT',
        'Telemetría & Recursos de Turno',
        'Curso Obligatorio',
        'Preoperacional ✓',
      ]) {
        expect(find.textContaining(falso), findsNothing, reason: '"$falso" no tiene fuente');
      }
      await banco.cerrar();
    });

    testWidgets('Tampoco el turno, la cuadrilla ni el selector de modos',
        (WidgetTester tester) async {
      // El selector "En ruta / Pausa" se veía y no guardaba nada: un aviso que
      // el supervisor nunca recibe es peor que no poder darlo.
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
      ]);
      await tester.pumpWidget(banco.app(jornada: _jornada()));
      await tester.pumpAndSettle();

      expect(find.text('En ruta'), findsNothing);
      expect(find.text('Pausa'), findsNothing);
      expect(find.text('Disponible'), findsNothing);
      expect(find.textContaining('Turno:'), findsNothing);
      expect(find.textContaining('Cuadrilla'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('Sin sla_vence_en no se muestra un reloj corriendo',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'en_sitio', compromiso: enUnaHora),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.textContaining('SLA'), findsNothing);
      expect(find.textContaining('ETA'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('Con sla_vence_en sí, y con los minutos del servidor',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final momento = DateTime(2026, 9, 22, 10, 0);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        <String, dynamic>{
          ..._orden(id: '1', numero: 1, estado: 'en_sitio'),
          'sla_vence_en': '2026-09-22T10:30:00',
        },
      ]);
      await tester.pumpWidget(banco.app(ahora: momento));
      await tester.pumpAndSettle();

      expect(find.text('SLA: 30 min'), findsOneWidget);
      await banco.cerrar();
    });
  });

  group('8. Cuál es el próximo trabajo lo decide el dominio', () {
    testWidgets('El empezado gana al urgente, y el botón dice continuar',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        <String, dynamic>{
          ..._orden(id: 'urgente', numero: 10, estado: 'asignada', cliente: 'Urgente'),
          'prioridad': 'alta',
        },
        _orden(id: 'empezado', numero: 20, estado: 'en_sitio', cliente: 'Empezado'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('Próximo trabajo'), findsOneWidget);
      expect(find.text('Empezado'), findsOneWidget);
      expect(find.text('CONTINUAR OT #20'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Uno que no se abrió todavía se ofrece empezar, no continuar',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 4832, estado: 'asignada', cliente: 'Carlos Gomez'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('EMPEZAR OT #4832'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('El próximo no se repite abajo en la lista',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: 'a', numero: 1, estado: 'asignada', cliente: 'Uno', compromiso: enUnaHora),
        _orden(id: 'b', numero: 2, estado: 'asignada', cliente: 'Dos', compromiso: enDosHoras),
      ]);
      await tester.pumpWidget(banco.app(ahora: ahora));
      await tester.pumpAndSettle();

      expect(find.text('Uno'), findsOneWidget, reason: 'el destacado');
      expect(find.text('OT #2'), findsOneWidget, reason: 'el otro, en la lista');
      expect(find.text('OT #1'), findsNothing, reason: 'ya está arriba');
      await banco.cerrar();
    });

    testWidgets('Con varios empezados lo dice, en vez de elegir en silencio',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
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
      await banco.cerrar();
    });
  });

  group('9. Los vacíos dicen cuál vacío es', () {
    testWidgets('Sin nada asignado no se dice que terminó',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('No tenés trabajos asignados'), findsOneWidget);
      expect(find.text('Terminaste todos tus trabajos'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('Con todo hecho sí, y son cosas distintas',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'cerrada'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('Terminaste todos tus trabajos'), findsOneWidget);
      expect(find.text('No tenés trabajos asignados'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('Si no se puede leer la base lo dice, no finge jornada vacía',
        (WidgetTester tester) async {
      final banco = _Banco(falla: true);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('No se pudieron leer tus trabajos'), findsOneWidget);
      expect(find.text('No tenés trabajos asignados'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('Los trabajos sin fecha se avisan, sin inventarles hora',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
        _orden(id: '2', numero: 2, estado: 'asignada'),
        _orden(id: '3', numero: 3, estado: 'asignada'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      // Tres sin fecha: uno sube a "próximo trabajo" y quedan dos.
      expect(find.text('Tenés 2 trabajos sin fecha asignada'), findsOneWidget);
      await banco.cerrar();
    });
  });

  group('10. En qué estado está la jornada', () {
    testWidgets('Abierta lo dice, y no promete un acta', (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app(jornada: _jornada()));
      await tester.pumpAndSettle();

      expect(find.text('Jornada en curso'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Tomar el cierre NO es tenerla cerrada', (WidgetTester tester) async {
      // Decirle cerrada a una intención que viaja en la cola haría que alguien
      // se fuera a su casa creyendo que entregó.
      final banco = _Banco();
      await tester.pumpWidget(banco.app(jornada: _jornada(cierreTomado: true)));
      await tester.pumpAndSettle();

      expect(find.text('Cierre enviado · esperando confirmación'), findsOneWidget);
      expect(find.text('Jornada cerrada'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('Cerrada la dice el servidor', (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app(jornada: _jornada(cerrada: true)));
      await tester.pumpAndSettle();

      expect(find.text('Jornada cerrada'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Sin jornada no se afirma ninguno de los tres',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app(jornada: _jornada(hay: false)));
      await tester.pumpAndSettle();

      expect(find.textContaining('Jornada'), findsNothing);
      await banco.cerrar();
    });
  });

  group('11. Los problemas, y sólo los problemas', () {
    testWidgets('Sin nada roto, el día no empieza en rojo',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
      ]);
      await tester.pumpWidget(banco.app(resumen: _sync(), jornada: _jornada()));
      await tester.pumpAndSettle();

      expect(find.text('Alertas operativas'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('Lo que espera señal se avisa, pero no como alarma',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(resumen: _sync(pendientes: 3)));
      await tester.pumpAndSettle();

      expect(find.text('Alertas operativas'), findsOneWidget);
      expect(find.text('3 registros sin enviar'), findsOneWidget);
      expect(
        find.text('Suben solos cuando haya señal. No hace falta esperar acá.'),
        findsOneWidget,
      );
      await banco.cerrar();
    });

    testWidgets('Los movimientos de material también cuentan como sin enviar',
        (WidgetTester tester) async {
      // Viven en otra cola. Sin sumarlos, la pantalla diría "todo enviado"
      // justo el día que el técnico registró consumo sin señal.
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(
        resumen: _sync(pendientes: 1),
        jornada: _jornada(sinSubir: 2),
      ));
      await tester.pumpAndSettle();

      expect(find.text('3 registros sin enviar'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Un cambio rechazado sí es grave: no se arregla solo',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(resumen: _sync(conflicto: 1)));
      await tester.pumpAndSettle();

      expect(find.text('1 cambio rechazado'), findsOneWidget);
      expect(find.text('El servidor no los aceptó. Hay que revisarlos.'),
          findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Un material que no cuadra se avisa cuando el servidor objeta',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(
        jornada: _jornada(
          diferencias: 2,
          motivos: <String>['Faltan 2 unidades sin explicar.'],
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.text('2 materiales no cuadran'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Pero no por faltar material que todavía no toca devolver',
        (WidgetTester tester) async {
      // El contador de diferencias es mayor que cero desde la mañana: falta
      // devolver el kit entero. Un rojo diario deja de leerse.
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(jornada: _jornada(diferencias: 2)));
      await tester.pumpAndSettle();

      expect(find.text('Alertas operativas'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('Un equipo sin ubicar se muestra con el motivo del servidor',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(
        jornada: _jornada(motivos: <String>[
          'El equipo con serie 48575448A9B0C1 no se instaló ni volvió a bodega.',
        ]),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Un equipo sin ubicar'), findsOneWidget);
      expect(find.textContaining('48575448A9B0C1'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('Lo grave se ve antes que lo que puede esperar',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(
        resumen: _sync(pendientes: 5),
        jornada: _jornada(
          diferencias: 1,
          motivos: <String>['Faltan 2 unidades sin explicar.'],
        ),
      ));
      await tester.pumpAndSettle();

      final double grave = tester.getTopLeft(find.text('1 material no cuadra')).dy;
      final double espera = tester.getTopLeft(find.text('5 registros sin enviar')).dy;
      expect(grave, lessThan(espera));
      await banco.cerrar();
    });

    testWidgets('Una jornada cerrada no sigue reclamando',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(
        jornada: _jornada(diferencias: 3, cerrada: true),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Alertas operativas'), findsNothing);
      await banco.cerrar();
    });
  });

  group('12. Sin señal se sigue trabajando', () {
    testWidgets('La cola dice que se guarda igual', (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(resumen: _sync(sinConexion: true)));
      await tester.pumpAndSettle();

      expect(
        find.text('Sin conexión con el servidor · lo que hagas se guarda igual'),
        findsOneWidget,
      );
      await banco.cerrar();
    });

    testWidgets('Con pendientes dice que se envían al volver la conexión',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(
        resumen: _sync(pendientes: 2, sinConexion: true),
      ));
      await tester.pumpAndSettle();

      expect(
        find.text('2 cambios guardados acá · se envían al volver la conexión'),
        findsOneWidget,
      );
      await banco.cerrar();
    });

    testWidgets('El bloque de sincronización usa la misma lectura de la cola',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final banco = _Banco();
      await tester.pumpWidget(banco.app(resumen: _sync(pendientes: 2)));
      await tester.pumpAndSettle();

      expect(
        find.text('2 cambios guardados acá · esperando turno para enviarse'),
        findsOneWidget,
      );
      expect(find.text('2 sin enviar'), findsOneWidget, reason: 'la chapa del saludo');
      await banco.cerrar();
    });
  });

  group('13. Lo que la pantalla hace al tocarla', () {
    testWidgets('Abrir el próximo trabajo y volver recarga la jornada',
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
      await banco.cerrar();
    });

    testWidgets('"Ver Agenda" lleva a Trabajo sin tocar los datos',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      var vecesQueLlamo = 0;
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada', compromiso: enUnaHora),
        _orden(id: '2', numero: 2, estado: 'asignada', compromiso: enDosHoras),
      ]);
      await tester.pumpWidget(banco.app(
        onVerTodos: () => vecesQueLlamo++,
        ahora: ahora,
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Ver Agenda'));
      await tester.pumpAndSettle();
      expect(vecesQueLlamo, 1);
      expect(banco.abiertos, isEmpty);
      await banco.cerrar();
    });

    testWidgets('Una sincronización exitosa actualiza la jornada una sola vez',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();
      final cargasAntes = banco.cargas;

      banco.avisos.add(SyncStatus.success);
      await tester.pumpAndSettle();
      expect(banco.cargas, cargasAntes + 1);

      // Y una fallida no: no hay dato nuevo que leer.
      banco.avisos.add(SyncStatus.error);
      await tester.pumpAndSettle();
      expect(banco.cargas, cargasAntes + 1);
      await banco.cerrar();
    });
  });
}
