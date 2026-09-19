import 'dart:async';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/features/detalle_orden/pasos_orden.dart';
import 'package:campo/features/inicio/inicio_screen.dart';
import 'package:campo/features/trabajo/estado_trabajo.dart';
import 'package:campo/features/trabajo/trabajo_screen.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _orden({
  String id = 'ot-1',
  int numero = 4832,
  required String estado,
  String cliente = 'Carlos Gomez',
  String telefono = '3001234567',
  String diagnostico = '',
  int revision = 7,
  int schemaVersion = 1,
  DateTime? compromiso,
}) {
  return <String, dynamic>{
    'id': id,
    'numero': numero,
    'estado': estado,
    'cliente_nombre': cliente,
    'direccion': 'Cra 45 #12-88',
    'telefono': telefono,
    'tipo_nombre': 'Instalación FTTH',
    'tipo_codigo': 'ftth_instalacion',
    'schema_version': schemaVersion,
    'revision': revision,
    'diagnostico_previo_ia': diagnostico,
    'fecha_compromiso': compromiso?.toIso8601String(),
  };
}

/// Una base de mentira que se comporta como la real: al transicionar, guarda
/// el estado nuevo y deja la mutacion encolada.
class _BaseFalsa {
  _BaseFalsa(this.filas);

  List<Map<String, dynamic>> filas;
  final List<Map<String, Object?>> mutacionesEncoladas = <Map<String, Object?>>[];
  int lecturas = 0;
  int sincronizaciones = 0;

  final StreamController<SyncStatus> avisos = StreamController<SyncStatus>.broadcast();

  late final OrdenesJornada ordenes = OrdenesJornada(
    leerOrdenes: () async {
      lecturas++;
      return filas
          .map((Map<String, dynamic> f) => Map<String, dynamic>.from(f))
          .toList();
    },
    sincronizar: () async => sincronizaciones++,
    avisosDeSincronizacion: avisos.stream,
  );

  AccionesOrden get acciones => AccionesOrden(
        transicionar: ({
          required String ordenId,
          required String nuevoEstadoLocal,
          required String tipoAccion,
          required int revisionBase,
        }) async {
          mutacionesEncoladas.add(<String, Object?>{
            'orden': ordenId,
            'accion': tipoAccion,
            'revision_base': revisionBase,
          });
          filas = filas.map((Map<String, dynamic> f) {
            if (f['id'] != ordenId) return f;
            return <String, dynamic>{...f, 'estado': nuevoEstadoLocal};
          }).toList();
        },
        sincronizar: () async => sincronizaciones++,
      );

  Future<void> cerrar() async {
    await avisos.close();
    ordenes.dispose();
  }
}

Widget _app(
  _BaseFalsa base, {
  String ordenId = 'ot-1',
  bool mostrarDatosFuturos = false,
  SyncSummary? resumen,
  Future<void> Function(BuildContext, TrabajoVista)? abrirEjecucion,
}) =>
    MaterialApp(
      theme: AppTheme.lightTheme,
      home: DetalleOrdenScreen(
        ordenId: ordenId,
        ordenes: base.ordenes,
        acciones: base.acciones,
        resumenInicial: resumen,
        mostrarDatosFuturos: mostrarDatosFuturos,
        abrirEjecucion: abrirEjecucion,
      ),
    );

/// El detalle es largo: con una pantalla alta entra todo y las pruebas hablan
/// del contenido, no del scroll.
void _pantallaAlta(WidgetTester tester) {
  tester.view.physicalSize = const Size(1000, 3200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  group('Lectura de la maquina de estados', () {
    test('1. El camino normal avanza paso a paso', () {
      expect(LecturaDePasos.de(EstadoTrabajo.asignada).pasoActual, 0);
      expect(LecturaDePasos.de(EstadoTrabajo.enCamino).pasoActual, 1);
      expect(LecturaDePasos.de(EstadoTrabajo.enSitio).pasoActual, 2);
      expect(LecturaDePasos.de(EstadoTrabajo.completadaCampo).pasoActual, 3);
      expect(LecturaDePasos.de(EstadoTrabajo.cerrada).pasoActual, 4);

      for (final EstadoTrabajo e in <EstadoTrabajo>[
        EstadoTrabajo.asignada,
        EstadoTrabajo.enCamino,
        EstadoTrabajo.enSitio,
        EstadoTrabajo.completadaCampo,
        EstadoTrabajo.cerrada,
      ]) {
        expect(LecturaDePasos.de(e).excepcion, isFalse);
      }
    });

    test('2. Devuelta para corregir es excepcion, no un paso mas', () {
      final lectura = LecturaDePasos.de(EstadoTrabajo.correccionRequerida);
      expect(lectura.excepcion, isTrue);
      expect(lectura.avisoExcepcion, isNotNull);
      // No se la pinta como si hubiera avanzado a completada.
      expect(lectura.pasoActual, lessThan(3));
    });

    test('3. Cancelada no se muestra como progreso', () {
      final lectura = LecturaDePasos.de(EstadoTrabajo.cancelada);
      expect(lectura.excepcion, isTrue);
      expect(lectura.pasoActual, -1);
    });

    test('4. Terminada sin enviar alcanzo el paso, pero no es lo mismo', () {
      expect(LecturaDePasos.de(EstadoTrabajo.completadaSinEnviar).pasoActual, 3);
      expect(LecturaDePasos.de(EstadoTrabajo.completadaSinEnviar).excepcion, isFalse);
    });

    test('5. Un estado desconocido no se hace pasar por avance', () {
      final lectura = LecturaDePasos.de(EstadoTrabajo.desconocido);
      expect(lectura.pasoActual, -1);
      expect(lectura.excepcion, isTrue);
    });
  });

  group('Acciones disponibles', () {
    test('6. Cada estado ofrece solo transiciones que el backend permite', () {
      // asignada -> en_camino (primaria) y -> en_sitio (la matriz lo permite)
      final asignada = AccionesDisponibles.para(EstadoTrabajo.asignada);
      expect(asignada.primaria!.tipoAccion, 'marcar_en_camino');
      expect(asignada.secundarias.single.tipoAccion, 'iniciar');

      expect(
        AccionesDisponibles.para(EstadoTrabajo.enCamino).primaria!.tipoAccion,
        'iniciar',
      );

      // en_sitio no transiciona desde acá: abre la ejecución, que es la que
      // valida el formulario y completa.
      final enSitio = AccionesDisponibles.para(EstadoTrabajo.enSitio);
      expect(enSitio.primaria!.abreEjecucion, isTrue);

      // devuelta para corregir: unico camino de vuelta, a en_sitio
      expect(
        AccionesDisponibles.para(EstadoTrabajo.correccionRequerida).primaria!.tipoAccion,
        'iniciar',
      );
    });

    test('7. Lo terminado, cerrado o cancelado no ofrece ninguna accion', () {
      for (final EstadoTrabajo e in <EstadoTrabajo>[
        EstadoTrabajo.completadaSinEnviar,
        EstadoTrabajo.completadaCampo,
        EstadoTrabajo.cerrada,
        EstadoTrabajo.cancelada,
        EstadoTrabajo.desconocido,
      ]) {
        expect(AccionesDisponibles.para(e).primaria, isNull, reason: e.name);
      }
    });

    test('8. Ninguna accion inventa un nombre que el backend no conozca', () {
      // Los nombres que /acciones/ acepta, segun campo/services/transiciones.py
      const permitidos = <String>{'marcar_en_camino', 'marcar_llegada', 'iniciar', 'cancelar'};

      for (final EstadoTrabajo e in EstadoTrabajo.values) {
        final acciones = AccionesDisponibles.para(e);
        for (final AccionOrden a in <AccionOrden>[
          if (acciones.primaria != null) acciones.primaria!,
          ...acciones.secundarias,
        ]) {
          if (a.abreEjecucion) continue;
          expect(permitidos, contains(a.tipoAccion), reason: '${e.name} -> ${a.etiqueta}');
        }
      }
    });
  });

  group('Pantalla Detalle', () {
    testWidgets('9. Muestra los datos reales de la orden',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[
        _orden(estado: 'en_camino', compromiso: DateTime(2026, 9, 18, 10, 30)),
      ]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.text('Orden #4832'), findsOneWidget);
      expect(find.text('Carlos Gomez'), findsOneWidget);
      expect(find.text('Cra 45 #12-88'), findsOneWidget);
      expect(find.text('3001234567'), findsOneWidget);
      expect(find.text('EN CAMINO'), findsOneWidget);
      expect(find.text('Comprometido para 18/09 a las 10:30'), findsOneWidget);
      await base.cerrar();
    });

    testWidgets('10. El diagnostico previo se muestra tal cual llega',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      const texto = 'Cliente reporta cortes intermitentes | NAP: NAP-04';
      final base = _BaseFalsa(<Map<String, dynamic>>[
        _orden(estado: 'en_sitio', diagnostico: texto),
      ]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.text('DIAGNÓSTICO PREVIO'), findsOneWidget);
      expect(find.text(texto), findsOneWidget);
      await base.cerrar();
    });

    testWidgets('11. Sin diagnostico no se dibuja una tarjeta vacia',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[_orden(estado: 'asignada')]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.text('DIAGNÓSTICO PREVIO'), findsNothing);
      await base.cerrar();
    });

    testWidgets('12. Terminada sin enviar no se muestra como confirmada',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[
        _orden(estado: 'completada_pendiente_sync'),
      ]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.text('Completado en campo · pendiente de enviar'), findsOneWidget);
      expect(find.text('Ya está hecho. Falta que se envíe al servidor.'), findsOneWidget);
      // Y no ofrece ninguna accion de avance.
      expect(find.byType(ElevatedButton), findsNothing);
      await base.cerrar();
    });

    testWidgets('13. Devuelta para corregir avisa y ofrece volver al sitio',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[
        _orden(estado: 'correccion_requerida'),
      ]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.textContaining('El supervisor devolvió este trabajo'), findsOneWidget);
      expect(find.text('Volver al sitio'), findsOneWidget);
      await base.cerrar();
    });

    testWidgets('14. Cancelada no ofrece nada y lo explica',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[_orden(estado: 'cancelada')]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.text('Este trabajo fue cancelado.'), findsOneWidget);
      expect(find.byType(ElevatedButton), findsNothing);
      await base.cerrar();
    });

    testWidgets('15. La orden que exige actualizar bloquea la accion',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[
        _orden(estado: 'asignada', schemaVersion: 2),
      ]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      final boton = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      expect(boton.onPressed, isNull);
      expect(find.text('Voy en camino'), findsNothing);
      await base.cerrar();
    });

    testWidgets('16. Fuera del modo demostracion no hay telemetria ficticia',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[_orden(estado: 'en_sitio')]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.text('SEÑAL DEL CLIENTE'), findsNothing);
      await base.cerrar();
    });

    testWidgets('17. En modo demostracion aparece la telemetria',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[_orden(estado: 'en_sitio')]);
      await tester.pumpWidget(_app(base, mostrarDatosFuturos: true));
      await tester.pumpAndSettle();

      expect(find.text('SEÑAL DEL CLIENTE'), findsOneWidget);
      expect(find.text('POTENCIA RX'), findsOneWidget);
      await base.cerrar();
    });

    testWidgets('18. La barra de pasos se anuncia para lectores de pantalla',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[_orden(estado: 'en_sitio')]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.text('Paso 3 de 5: En sitio'), findsOneWidget);
      await base.cerrar();
    });

    testWidgets('19. La orden que ya no esta en la lista lo dice',
        (WidgetTester tester) async {
      final base = _BaseFalsa(<Map<String, dynamic>>[_orden(estado: 'asignada')]);
      await tester.pumpWidget(_app(base, ordenId: 'otra'));
      await tester.pumpAndSettle();

      expect(find.text('No encontramos esta orden'), findsOneWidget);
      await base.cerrar();
    });
  });

  group('Transicion real', () {
    testWidgets('20. Tocar la accion encola la mutacion y actualiza el detalle',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final base = _BaseFalsa(<Map<String, dynamic>>[
        _orden(estado: 'asignada', revision: 7),
      ]);
      await tester.pumpWidget(_app(base));
      await tester.pumpAndSettle();

      expect(find.text('ASIGNADA'), findsOneWidget);

      await tester.tap(find.text('Voy en camino'));
      await tester.pumpAndSettle();

      expect(base.mutacionesEncoladas.single, <String, Object?>{
        'orden': 'ot-1',
        'accion': 'marcar_en_camino',
        'revision_base': 7,
      });
      expect(find.text('EN CAMINO'), findsOneWidget);
      expect(find.text('Llegué al sitio'), findsOneWidget);
      await base.cerrar();
    });

    testWidgets('21. El cambio llega a Trabajo y a Inicio, sin otra coleccion',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      final hoy = DateTime.now();
      final base = _BaseFalsa(<Map<String, dynamic>>[
        _orden(estado: 'asignada', revision: 3, compromiso: hoy),
      ]);

      // Las tres pantallas comparten la misma lista.
      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: Column(
            children: <Widget>[
              Expanded(
                child: InicioScreen(
                  ordenes: base.ordenes,
                  nombreTecnico: 'Carlos',
                  abrirTrabajo: (_, _) async {},
                ),
              ),
              Expanded(
                child: TrabajoScreen(
                  ordenes: base.ordenes,
                  abrirTrabajo: (_, _) async {},
                ),
              ),
            ],
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // Antes: Inicio dice que no hay nada empezado.
      expect(find.text('No tenés ningún trabajo empezado'), findsOneWidget);

      // La transicion ocurre como la haria el detalle.
      await base.acciones.transicionar(
        ordenId: 'ot-1',
        nuevoEstadoLocal: 'en_camino',
        tipoAccion: 'marcar_en_camino',
        revisionBase: 3,
      );
      await base.ordenes.recargar();
      await tester.pumpAndSettle();

      // Despues: Inicio lo muestra en curso y Trabajo lo cuenta en proceso.
      expect(find.text('No tenés ningún trabajo empezado'), findsNothing);
      expect(find.text('EN CAMINO'), findsWidgets);
      await base.cerrar();
    });

    testWidgets('22. Abrir la ejecucion no transiciona por su cuenta',
        (WidgetTester tester) async {
      _pantallaAlta(tester);
      var veces = 0;
      final base = _BaseFalsa(<Map<String, dynamic>>[_orden(estado: 'en_sitio')]);
      await tester.pumpWidget(_app(
        base,
        abrirEjecucion: (_, _) async => veces++,
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Ejecutar el trabajo'));
      await tester.pumpAndSettle();

      expect(veces, 1);
      expect(
        base.mutacionesEncoladas,
        isEmpty,
        reason: 'completar es decision de la pantalla de ejecucion, no del detalle',
      );
      await base.cerrar();
    });
  });
}
