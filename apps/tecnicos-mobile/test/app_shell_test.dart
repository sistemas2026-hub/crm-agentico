import 'dart:async';
// Tristate describe las banderas de semantica que pueden estar sin definir.
import 'dart:ui' as ui;

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/core/widgets/dexter_app_header.dart';
import 'package:campo/core/widgets/dexter_bottom_nav.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:campo/features/shell/app_shell.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

SyncSummary _resumen({
  bool sincronizando = false,
  bool errorDeConexion = false,
  int pendientes = 0,
  int conflictos = 0,
}) {
  return SyncSummary(
    status: SyncStatus.idle,
    isSyncing: sincronizando,
    hasConnectionError: errorDeConexion,
    mutacionesPendientes: pendientes,
    mutacionesConflicto: conflictos,
    evidenciasPendientes: 0,
    datosDirty: 0,
  );
}

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

/// Arma el contenedor con todo inyectado: ni base, ni sesion, ni radio.
/// El rótulo de la barra inferior, y no el título del encabezado.
///
/// En este diseño los dos dicen la misma palabra —"Materiales" arriba y
/// "Materiales" abajo—, así que un `find.text` suelto encuentra dos y no
/// distingue cuál se tocó.
Finder _enBarra(String texto) => find.descendant(
      of: find.byType(DexterBottomNav),
      matching: find.text(texto),
    );

/// El título del encabezado, y no el rótulo de la barra.
Finder _enEncabezado(String texto) => find.descendant(
      of: find.byType(DexterAppHeader),
      matching: find.text(texto),
    );

class _Banco {
  _Banco({
    this.resumenInicial,
    this.conConectividad = true,
    List<Map<String, dynamic>>? filas,
  }) : filas = filas ?? <Map<String, dynamic>>[] {
    resumenes = StreamController<SyncSummary>.broadcast(
      onListen: () => escuchasResumen++,
      onCancel: () => cancelacionesResumen++,
    );
    conectividad = StreamController<bool>.broadcast(
      onListen: () => escuchasConexion++,
      onCancel: () => cancelacionesConexion++,
    );
  }

  final SyncSummary? resumenInicial;
  final bool conConectividad;
  final List<Map<String, dynamic>> filas;

  late final StreamController<SyncSummary> resumenes;
  late final StreamController<bool> conectividad;
  final StreamController<SyncStatus> avisosSync =
      StreamController<SyncStatus>.broadcast();

  int escuchasResumen = 0;
  int cancelacionesResumen = 0;
  int escuchasConexion = 0;
  int cancelacionesConexion = 0;
  int sincronizacionesPedidas = 0;

  /// Cuántas veces se leyeron las ordenes de la base.
  int lecturas = 0;
  final List<String> abiertos = <String>[];

  late final OrdenesJornada ordenes = OrdenesJornada(
    leerOrdenes: () async {
      lecturas++;
      return filas;
    },
    sincronizar: () async {},
    avisosDeSincronizacion: avisosSync.stream,
  );

  ShellDependencias get dependencias => ShellDependencias(
        resumenes: resumenes.stream,
        resumenInicial: resumenInicial,
        sincronizarAhora: () async => sincronizacionesPedidas++,
        conectividad: conConectividad ? conectividad.stream : null,
        cargarIdentidad: () async => const IdentidadTecnico(
          nombre: 'Carlos Gomez',
          empresa: 'Rapilink ISP',
        ),
        ordenes: ordenes,
        abrirTrabajo: (BuildContext contexto, TrabajoVista trabajo) async {
          abiertos.add(trabajo.id);
          await Navigator.of(contexto).push(
            MaterialPageRoute<void>(
              builder: (BuildContext c) => Scaffold(
                appBar: AppBar(title: const Text('Detalle de la orden')),
                body: ElevatedButton(
                  onPressed: () => Navigator.of(c).pop(),
                  child: const Text('Volver'),
                ),
              ),
            ),
          );
        },
        cerrarSesion: () async {},
      );

  /// La aplicación montada para una prueba.
  ///
  /// Con el movimiento permitido por omisión: el latido del encabezado es una
  /// ráfaga finita, así que `pumpAndSettle` asienta igual. [conMovimiento] en
  /// falso monta lo que vería un teléfono con "reducir movimiento" activado.
  Widget app({
    SeccionCampo inicial = SeccionCampo.trabajo,
    bool conMovimiento = true,
  }) =>
      MaterialApp(
        theme: AppTheme.lightTheme,
        home: Builder(
          builder: (BuildContext contexto) => MediaQuery(
            data: MediaQuery.of(contexto)
                .copyWith(disableAnimations: !conMovimiento),
            child: AppShell(dependencias: dependencias, seccionInicial: inicial),
          ),
        ),
      );

  Future<void> cerrar() async {
    await resumenes.close();
    await conectividad.close();
    await avisosSync.close();
    ordenes.dispose();
  }
}

void main() {
  final hoy = DateTime.now();

  group('AppShell', () {
    testWidgets('1. Arranca en Trabajo con la lista real',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(
            id: '1',
            numero: 10,
            estado: 'asignada',
            cliente: 'Carlos Gomez',
            compromiso: hoy),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('Carlos Gomez'), findsOneWidget);
      expect(find.byType(DexterBottomNav), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('2. Cambiar de pestaña muestra la otra seccion',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      await tester.tap(_enBarra('Materiales'));
      await tester.pumpAndSettle();

      // El encabezado dice en que seccion esta parado el tecnico.
      expect(_enEncabezado('Materiales'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('3. Volver a Trabajo conserva la pestaña elegida',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      await tester.tap(find.textContaining('Pendientes'));
      await tester.pumpAndSettle();

      await tester.tap(_enBarra('Inicio'));
      await tester.pumpAndSettle();
      await tester.tap(_enBarra('Órdenes'));
      await tester.pumpAndSettle();

      expect(
        tester.getSemantics(find.textContaining('Pendientes')).flagsCollection.isSelected,
        ui.Tristate.isTrue,
        reason: 'si el filtro se reconstruyera se perderia lo elegido',
      );
      await banco.cerrar();
    });

    testWidgets('4. El encabezado usa la identidad real de la sesion',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      // Las iniciales del técnico, en el avatar del encabezado.
      expect(_enEncabezado('CG'), findsOneWidget);

      // La empresa ya no va en el encabezado: este diseño no le reserva un
      // lugar. Sigue estando, y se llega tocando el avatar -- que es de quien
      // depende. Esto es lo que hay que afirmar, no la pastilla que se fue.
      await tester.tap(_enEncabezado('CG'));
      await tester.pumpAndSettle();
      // Tal como se guardó, sin forzar mayúsculas: la pastilla que las ponía
      // era del encabezado viejo.
      expect(find.text('Rapilink ISP'), findsOneWidget);
      expect(find.text('Carlos Gomez'), findsWidgets);
      await banco.cerrar();
    });

    testWidgets('4b. El punto del encabezado late cuando el estado cambia, y '
        'se queda quieto despues', (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      banco.conectividad.add(true);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final animado = find.descendant(
        of: find.byType(DexterAppHeader),
        matching: find.byType(FadeTransition),
      );
      expect(animado, findsOneWidget);

      // Late: la opacidad cambia sola, sin que nadie toque nada.
      final double antes = tester.widget<FadeTransition>(animado).opacity.value;
      await tester.pump(const Duration(milliseconds: 350));
      final double durante =
          tester.widget<FadeTransition>(animado).opacity.value;
      expect(
        durante,
        isNot(closeTo(antes, 0.02)),
        reason: 'si no cambia, el punto no esta latiendo',
      );

      // Y TERMINA. Esto es lo que la version infinita del diseño no hacía, y
      // lo que permite que el resto de la bateria use pumpAndSettle.
      await tester.pumpAndSettle();
      expect(
        tester.widget<FadeTransition>(animado).opacity.value,
        closeTo(1, 0.01),
        reason: 'al terminar la rafaga el punto queda encendido, no a medias',
      );

      // Cambia el estado: vuelve a llamar la atencion.
      banco.conectividad.add(false);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));
      expect(find.text('SIN RED'), findsOneWidget);
      await tester.pumpAndSettle();
      await banco.cerrar();
    });

    testWidgets('4c. Con "reducir movimiento" el punto no se anima, y no se '
        'pierde ninguna informacion', (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app(conMovimiento: false));
      banco.conectividad.add(true);
      await tester.pumpAndSettle();

      expect(
        find.descendant(
          of: find.byType(DexterAppHeader),
          matching: find.byType(FadeTransition),
        ),
        findsNothing,
      );
      // El estado sigue escrito al lado: el punto era decoracion.
      expect(find.text('CON RED'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('5. Sin red el encabezado lo dice, aunque la cola este limpia',
        (WidgetTester tester) async {
      final banco = _Banco(resumenInicial: _resumen());
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      banco.conectividad.add(false);
      await tester.pumpAndSettle();
      expect(find.text('SIN RED'), findsOneWidget);

      banco.conectividad.add(true);
      await tester.pumpAndSettle();
      expect(find.text('CON RED'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('6. Con red pero sin llegar al servidor no dice CON RED',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      banco.conectividad.add(true);
      banco.resumenes.add(_resumen(errorDeConexion: true));
      await tester.pumpAndSettle();

      expect(find.text('SIN SERVIDOR'), findsOneWidget);
      expect(find.text('CON RED'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('7. La franja dice lo que la cola sabe de verdad',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());

      banco.resumenes.add(_resumen());
      await tester.pumpAndSettle();
      expect(find.text('Todo sincronizado'), findsOneWidget);
      expect(find.text('ENVIAR AHORA'), findsNothing);

      banco.resumenes.add(_resumen(pendientes: 3));
      await tester.pumpAndSettle();
      // Con cola pendiente, la franja usa el texto corto del diseño.
      expect(find.textContaining('Cola de datos'), findsOneWidget);
      expect(find.textContaining('3 cambios locales'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('8. Con cambios sin enviar ofrece hacerlo y lo pide al servicio',
        (WidgetTester tester) async {
      final banco = _Banco(resumenInicial: _resumen(pendientes: 2));
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      await tester.tap(find.text('ENVIAR AHORA'));
      await tester.pumpAndSettle();

      expect(banco.sincronizacionesPedidas, 1);
      await banco.cerrar();
    });

    testWidgets('9. Una sola escucha de la cola, y se cancela al destruirse',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(banco.escuchasResumen, 1);
      expect(banco.escuchasConexion, 1);
      expect(banco.cancelacionesResumen, 0);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();

      expect(banco.cancelacionesResumen, 1, reason: 'quedaria una escucha viva');
      expect(banco.cancelacionesConexion, 1);
      expect(banco.resumenes.hasListener, isFalse);

      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();
      expect(banco.escuchasResumen, 2);
      expect(banco.cancelacionesResumen, 1);
      await banco.cerrar();
    });

    testWidgets('10. Abrir una orden desde Trabajo y volver no rompe el shell',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(
            id: 'abc',
            numero: 4832,
            estado: 'asignada',
            cliente: 'Carlos Gomez',
            compromiso: hoy),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      // Una orden sin empezar se abre desde su boton Detalles.
      await tester.ensureVisible(find.text('Detalles'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Detalles'));
      await tester.pumpAndSettle();
      expect(find.text('Detalle de la orden'), findsOneWidget);
      expect(_enBarra('Materiales'), findsNothing);

      await tester.tap(find.text('Volver'));
      await tester.pumpAndSettle();

      expect(banco.abiertos, <String>['abc']);
      expect(find.byType(DexterAppHeader), findsOneWidget);
      expect(find.byType(DexterBottomNav), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('10b. Una seccion nunca visitada no se construye',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app(inicial: SeccionCampo.inicio));
      await tester.pumpAndSettle();

      expect(
        find.byType(MaterialesScreen, skipOffstage: false),
        findsNothing,
        reason: 'abrir la aplicacion no debe construir las cinco secciones',
      );

      await tester.tap(_enBarra('Materiales'));
      await tester.pumpAndSettle();
      expect(find.byType(MaterialesScreen), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('10c. Inicio y Trabajo leen las ordenes una sola vez',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada', compromiso: hoy),
      ]);
      await tester.pumpWidget(banco.app(inicial: SeccionCampo.inicio));
      await tester.pumpAndSettle();

      final lecturasTrasInicio = banco.lecturas;
      expect(lecturasTrasInicio, 1);

      await tester.tap(_enBarra('Órdenes'));
      await tester.pumpAndSettle();

      expect(
        banco.lecturas,
        lecturasTrasInicio,
        reason: 'la segunda pantalla usa la lista ya cargada, no consulta otra vez',
      );
      await banco.cerrar();
    });

    testWidgets('10d. El contador de la barra sale de las ordenes compartidas',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
        _orden(id: '2', numero: 2, estado: 'en_camino'),
        _orden(id: '3', numero: 3, estado: 'completada_campo'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      // Dos activos: la completada no cuenta.
      expect(find.text('2'), findsWidgets);
      await banco.cerrar();
    });

    testWidgets('11. La pestaña activa se anuncia como elegida',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      final activa = tester.getSemantics(_enBarra('Órdenes'));
      expect(activa.label, 'Órdenes');
      expect(activa.flagsCollection.isSelected, ui.Tristate.isTrue);

      // Academia y Mas ya no se ofrecen: llevaban a "en construccion".
      expect(_enBarra('Academia'), findsNothing);
      final otra = tester.getSemantics(_enBarra('Materiales'));
      expect(otra.flagsCollection.isSelected, isNot(ui.Tristate.isTrue));
      await banco.cerrar();
    });

    testWidgets('12. El perfil ofrece cerrar sesion y lleva al login',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      await tester.tap(find.text('CG'));
      await tester.pumpAndSettle();
      expect(find.text('Carlos Gomez'), findsOneWidget);
      expect(find.text('Cerrar sesión'), findsOneWidget);
      await banco.cerrar();
    });
  });

  group('Lectura del estado de sincronizacion', () {
    testWidgets('13. Sin saber nada todavia, no dice que esta sincronizado',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pump();

      expect(find.text('Todo sincronizado'), findsNothing);
      expect(
        find.text('Revisando cambios guardados en el teléfono'),
        findsOneWidget,
      );
      await banco.cerrar();
    });

    testWidgets('13b. Sin señal de red disponible no se afirma nada de la conexion',
        (WidgetTester tester) async {
      final banco = _Banco(conConectividad: false, resumenInicial: _resumen());
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('BUSCANDO'), findsOneWidget);
      expect(find.text('CON RED'), findsNothing);
      expect(banco.escuchasConexion, 0);
      await banco.cerrar();
    });

    testWidgets('14. Un conflicto se muestra distinto de un pendiente',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());

      banco.resumenes.add(_resumen(conflictos: 1));
      await tester.pumpAndSettle();
      expect(
        find.text('Un cambio necesita que alguien lo revise'),
        findsOneWidget,
      );
      await banco.cerrar();
    });

    testWidgets('15. Sin conexion avisa que lo hecho se guarda igual',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());

      banco.resumenes.add(_resumen(errorDeConexion: true, pendientes: 1));
      await tester.pumpAndSettle();
      expect(
        find.text('Un cambio guardado acá · se envían al volver la conexión'),
        findsOneWidget,
      );
      await banco.cerrar();
    });
  });
}
