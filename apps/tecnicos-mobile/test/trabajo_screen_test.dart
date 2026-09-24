import 'dart:async';
// Tristate describe las banderas de semantica que pueden estar sin definir.
import 'dart:ui' as ui;

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/trabajo/estado_trabajo.dart';
import 'package:campo/features/trabajo/seleccion_jornada.dart';
import 'package:campo/features/trabajo/trabajo_screen.dart';
import 'package:campo/demo/field_mock_data.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Una fila de `local_ordenes`, con la misma forma que la base entrega.
Map<String, dynamic> _orden({
  required String id,
  required int numero,
  required String estado,
  String cliente = 'Cliente de prueba',
  String tipoNombre = 'Instalación FTTH',
  String tipoCodigo = 'ftth_instalacion',
  DateTime? compromiso,
  int schemaVersion = 1,
}) {
  return <String, dynamic>{
    'id': id,
    'numero': numero,
    'estado': estado,
    'cliente_nombre': cliente,
    'direccion': 'Calle 45 #12-30',
    'telefono': '',
    'tipo_nombre': tipoNombre,
    'tipo_codigo': tipoCodigo,
    'schema_version': schemaVersion,
    'diagnostico_previo_ia': '',
    'fecha_compromiso': compromiso?.toIso8601String(),
  };
}

class _Banco {
  _Banco({this.filas = const <Map<String, dynamic>>[], this.falla = false});

  final List<Map<String, dynamic>> filas;
  final bool falla;

  final StreamController<SyncStatus> avisos = StreamController<SyncStatus>.broadcast();
  int cargas = 0;
  int sincronizaciones = 0;
  final List<String> abiertos = <String>[];
  bool volverDelDetalle = false;

  late final OrdenesJornada ordenes = OrdenesJornada(
    leerOrdenes: () async {
      cargas++;
      if (falla) throw StateError('base ilegible');
      return filas;
    },
    sincronizar: () async => sincronizaciones++,
    avisosDeSincronizacion: avisos.stream,
  );

  Widget app({bool mostrarDatosFuturos = false}) => MaterialApp(
        theme: AppTheme.lightTheme,
        home: Scaffold(
          body: TrabajoScreen(
            ordenes: ordenes,
            mostrarDatosFuturos: mostrarDatosFuturos,
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
              volverDelDetalle = true;
            },
          ),
        ),
      );

  Future<void> cerrar() async {
    await avisos.close();
    ordenes.dispose();
  }
}

void main() {
  final hoy = DateTime.now();
  final ayer = hoy.subtract(const Duration(days: 1));

  group('Mapeo de los estados reales', () {
    test('1. Los ocho estados que existen se reconocen, y nada mas', () {
      // Siete del backend (campo/models.py) y uno solo del telefono.
      expect(EstadoTrabajo.desde('asignada'), EstadoTrabajo.asignada);
      expect(EstadoTrabajo.desde('en_camino'), EstadoTrabajo.enCamino);
      expect(EstadoTrabajo.desde('en_sitio'), EstadoTrabajo.enSitio);
      expect(EstadoTrabajo.desde('completada_campo'), EstadoTrabajo.completadaCampo);
      expect(
        EstadoTrabajo.desde('completada_pendiente_sync'),
        EstadoTrabajo.completadaSinEnviar,
      );
      expect(
        EstadoTrabajo.desde('correccion_requerida'),
        EstadoTrabajo.correccionRequerida,
      );
      expect(EstadoTrabajo.desde('cerrada'), EstadoTrabajo.cerrada);
      expect(EstadoTrabajo.desde('cancelada'), EstadoTrabajo.cancelada);
      // Un estado que el backend todavia no tiene no se hace pasar por otro.
      expect(EstadoTrabajo.desde('en_revision'), EstadoTrabajo.desconocido);
      expect(EstadoTrabajo.desde(null), EstadoTrabajo.desconocido);
    });

    test('2. Le toca al tecnico lo que no esta terminado ni cancelado', () {
      expect(EstadoTrabajo.asignada.leTocaAlTecnico, isTrue);
      expect(EstadoTrabajo.enCamino.leTocaAlTecnico, isTrue);
      expect(EstadoTrabajo.enSitio.leTocaAlTecnico, isTrue);
      // Devuelta por el supervisor: hay que rehacerla, asi que cuenta.
      expect(EstadoTrabajo.correccionRequerida.leTocaAlTecnico, isTrue);

      expect(EstadoTrabajo.completadaSinEnviar.leTocaAlTecnico, isFalse);
      expect(EstadoTrabajo.completadaCampo.leTocaAlTecnico, isFalse);
      expect(EstadoTrabajo.cerrada.leTocaAlTecnico, isFalse);
      expect(EstadoTrabajo.cancelada.leTocaAlTecnico, isFalse);
      expect(EstadoTrabajo.desconocido.leTocaAlTecnico, isFalse);
    });

    test('3. Todos no filtra por estado ni exige fecha', () {
      bool enTodos(EstadoTrabajo e, DateTime? f) =>
          perteneceA(PestanaTrabajo.todos, e, f, ahora: hoy);

      expect(enTodos(EstadoTrabajo.asignada, hoy), isTrue);
      expect(enTodos(EstadoTrabajo.asignada, ayer), isTrue);
      expect(enTodos(EstadoTrabajo.asignada, null), isTrue);
      expect(enTodos(EstadoTrabajo.completadaCampo, hoy), isTrue);
    });

    test('4. Los cuatro filtros de estado se reparten sin solaparse', () {
      bool en(PestanaTrabajo p, EstadoTrabajo e) =>
          perteneceA(p, e, null, ahora: hoy);

      expect(en(PestanaTrabajo.pendientes, EstadoTrabajo.asignada), isTrue);
      expect(en(PestanaTrabajo.pendientes, EstadoTrabajo.enCamino), isFalse);
      // Devuelta para corregir ya no se esconde entre las pendientes: el
      // diseño la separa en "Con Novedad", que es donde hay que mirarla.
      expect(en(PestanaTrabajo.pendientes, EstadoTrabajo.correccionRequerida), isFalse);

      expect(en(PestanaTrabajo.enProceso, EstadoTrabajo.enCamino), isTrue);
      expect(en(PestanaTrabajo.enProceso, EstadoTrabajo.enSitio), isTrue);
      expect(en(PestanaTrabajo.enProceso, EstadoTrabajo.asignada), isFalse);

      expect(en(PestanaTrabajo.finalizadas, EstadoTrabajo.completadaSinEnviar), isTrue);
      expect(en(PestanaTrabajo.finalizadas, EstadoTrabajo.cerrada), isTrue);
      expect(en(PestanaTrabajo.finalizadas, EstadoTrabajo.enSitio), isFalse);
      // Cancelada no es un trabajo terminado: es una novedad.
      expect(en(PestanaTrabajo.finalizadas, EstadoTrabajo.cancelada), isFalse);

      expect(en(PestanaTrabajo.conNovedad, EstadoTrabajo.correccionRequerida), isTrue);
      expect(en(PestanaTrabajo.conNovedad, EstadoTrabajo.cancelada), isTrue);
      expect(en(PestanaTrabajo.conNovedad, EstadoTrabajo.desconocido), isTrue);
      expect(en(PestanaTrabajo.conNovedad, EstadoTrabajo.enSitio), isFalse);

      // Ninguno de los cuatro se pisa con otro.
      for (final EstadoTrabajo e in EstadoTrabajo.values) {
        final int cuantos = <PestanaTrabajo>[
          PestanaTrabajo.pendientes,
          PestanaTrabajo.enProceso,
          PestanaTrabajo.finalizadas,
          PestanaTrabajo.conNovedad,
        ].where((PestanaTrabajo p) => en(p, e)).length;
        expect(cuantos, lessThanOrEqualTo(1), reason: e.name);
      }
    });
  });

  group('Clase de trabajo', () {
    test('5. Se reconoce por el tipo real, y si no se reconoce no se fuerza', () {
      FamiliaTrabajo familia(String codigo, String nombre) =>
          FamiliaTrabajo.desde(codigo: codigo, nombre: nombre);

      expect(familia('ftth_instalacion', 'Instalación FTTH'),
          FamiliaTrabajo.instalacion);
      expect(familia('soporte_correctivo', 'Ticket de soporte'),
          FamiliaTrabajo.incidencia);
      expect(familia('mant_preventivo', 'Mantenimiento de red'),
          FamiliaTrabajo.mantenimiento);
      expect(familia('xyz', 'Algo nuevo'), FamiliaTrabajo.otro);
    });

    test('6. Los datos futuros no entran en la fila de la orden', () {
      final vista = TrabajoVista.desdeOrden(
        _orden(id: 'a1', numero: 10, estado: 'asignada'),
      );

      // La vista ya no trae valores de ejemplo adentro: si la orden no dice
      // zona ni prioridad, el modelo tampoco. Rellenarlos ahí los volvia
      // indistinguibles de los reales para cualquiera que leyera el objeto.
      expect(vista.zona, isEmpty);
      expect(vista.prioridad, isEmpty);

      // Los de ejemplo siguen existiendo, pero se piden aparte y son estables
      // para la misma orden: si cambiaran en cada refresco parecerian dato en
      // vivo.
      expect(
        FieldMockData.trabajoFuturo('a1').zona,
        FieldMockData.trabajoFuturo('a1').zona,
      );
    });
  });

  group('Pantalla Trabajo', () {
    testWidgets('7. Muestra los trabajos reales de la pestaña elegida',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 4832, estado: 'asignada', cliente: 'Carlos Gomez', compromiso: hoy),
        _orden(id: '2', numero: 4833, estado: 'en_sitio', cliente: 'Marta Rodriguez', compromiso: ayer),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      // El Hub abre en "Todos": están los dos, sin esconder ninguno.
      expect(find.text('Carlos Gomez'), findsOneWidget);
      expect(find.text('Marta Rodriguez'), findsOneWidget);

      await tester.tap(find.textContaining('En Proceso'));
      await tester.pumpAndSettle();
      expect(find.text('Marta Rodriguez'), findsOneWidget);
      expect(find.text('Carlos Gomez'), findsNothing);

      await tester.tap(find.textContaining('Pendientes'));
      await tester.pumpAndSettle();
      expect(find.text('Carlos Gomez'), findsOneWidget);
      expect(find.text('Marta Rodriguez'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('8. La tarjeta distingue la clase de trabajo sin unificarlas',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada', compromiso: hoy),
        _orden(
          id: '2',
          numero: 2,
          estado: 'asignada',
          tipoNombre: 'Ticket de soporte',
          tipoCodigo: 'soporte_correctivo',
          compromiso: hoy,
        ),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.textContaining('INSTALACIÓN'), findsOneWidget);
      expect(find.textContaining('INCIDENCIA'), findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('9. El filtro por clase de trabajo filtra de verdad',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada', cliente: 'Instalacion Uno', compromiso: hoy),
        _orden(
          id: '2',
          numero: 2,
          estado: 'asignada',
          cliente: 'Incidencia Dos',
          tipoNombre: 'Ticket de soporte',
          tipoCodigo: 'soporte_correctivo',
          compromiso: hoy,
        ),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      // El segmento de arriba dice de qué entidad se habla.
      await tester.tap(find.textContaining('Tickets'));
      await tester.pumpAndSettle();

      // La tarjeta de una incidencia titula el problema, no al cliente.
      expect(find.text('Ticket de soporte'), findsOneWidget);
      expect(find.text('Instalacion Uno'), findsNothing);

      await tester.tap(find.textContaining('Instalaciones'));
      await tester.pumpAndSettle();
      expect(find.text('Instalacion Uno'), findsOneWidget);
      expect(find.text('Ticket de soporte'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('10. El buscador filtra de verdad, y sobre lo que ya está local',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 4832, estado: 'asignada', cliente: 'Carlos Gomez', compromiso: hoy),
        _orden(id: '2', numero: 4901, estado: 'asignada', cliente: 'Marta Rodriguez', compromiso: hoy),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      final int lecturasAntes = banco.cargas;

      await tester.enterText(find.byType(TextField), 'marta');
      await tester.pumpAndSettle();
      expect(find.text('Marta Rodriguez'), findsOneWidget);
      expect(find.text('Carlos Gomez'), findsNothing);

      // También por número de orden.
      await tester.enterText(find.byType(TextField), '4832');
      await tester.pumpAndSettle();
      expect(find.text('Carlos Gomez'), findsOneWidget);
      expect(find.text('Marta Rodriguez'), findsNothing);

      // Y sin volver a la base: busca sobre lo que ya está en el teléfono.
      expect(banco.cargas, lecturasAntes);
      await banco.cerrar();
    });

    testWidgets('11. El contador informa lo que le queda al tecnico',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 1, estado: 'asignada'),
        _orden(id: '2', numero: 2, estado: 'en_camino'),
        _orden(id: '3', numero: 3, estado: 'correccion_requerida'),
        _orden(id: '4', numero: 4, estado: 'completada_campo'),
        _orden(id: '5', numero: 5, estado: 'cerrada'),
        _orden(id: '6', numero: 6, estado: 'cancelada'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(
        SeleccionJornada.activos(banco.ordenes.trabajos).length,
        3,
        reason: 'cuenta lo que falta hacer, no lo descargado',
      );
      await banco.cerrar();
    });

    testWidgets('17. El Hub dice de qué entidad habla y cuántas hay en el equipo',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: '1', numero: 4832, estado: 'asignada', cliente: 'Carlos Gomez', compromiso: hoy),
        _orden(
          id: '2',
          numero: 4833,
          estado: 'asignada',
          cliente: 'Marta Rodriguez',
          tipoNombre: 'Ticket de soporte',
          tipoCodigo: 'soporte_correctivo',
          compromiso: hoy,
        ),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('Mi Trabajo'), findsOneWidget);
      expect(find.text('2 órdenes asignadas para la jornada de hoy'), findsOneWidget);
      // Lo que está en el teléfono, que es lo que se puede abrir sin señal.
      expect(find.textContaining('2 OTs sincronizadas localmente'), findsOneWidget);

      // La cinta explica la entidad del segmento elegido, y cambia con él.
      expect(find.textContaining('OT = Orden de Trabajo'), findsOneWidget);
      await tester.tap(find.textContaining('Tickets'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Ticket = reporte del cliente'), findsOneWidget);

      // Y el pie cierra la lista sin prometer que hay más.
      //
      // Desde el 24/09/2026 hay que desplazarse para llegar: la tarjeta creció
      // —razón de falla, las dos prioridades, cliente y el desplegable— y el
      // pie dejó de caber en la primera pantalla. Lo que se afirma es lo mismo;
      // lo que cambió es que ahora está más abajo. Un `find.text` sin
      // desplazamiento no lo encuentra porque la lista no lo construyó todavía,
      // y eso se lee como "el pie desapareció" cuando en realidad está.
      // Se nombra la lista explícitamente: la pantalla tiene más de un
      // `Scrollable` (las pastillas de filtro son uno horizontal) y dejarlo
      // implícito falla con «Too many elements», que no dice nada del pie.
      final pie =
          find.text('No hay más órdenes asignadas en este ciclo de despacho');
      await tester.scrollUntilVisible(
        pie,
        300,
        scrollable: find.descendant(
          of: find.byType(ListView),
          matching: find.byType(Scrollable),
        ).first,
      );
      expect(pie, findsOneWidget);
      await banco.cerrar();
    });

    testWidgets('12. Sin trabajos muestra el vacio real, sin inventar ninguno',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('No tenés trabajos asignados'), findsOneWidget);
      expect(SeleccionJornada.activos(banco.ordenes.trabajos), isEmpty);
      await banco.cerrar();
    });

    testWidgets('13. Si no se puede leer la base, lo dice; no finge estar vacio',
        (WidgetTester tester) async {
      final banco = _Banco(falla: true);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(find.text('No se pudieron leer tus trabajos'), findsOneWidget);
      expect(find.text('No tenés trabajos para hoy'), findsNothing);
      await banco.cerrar();
    });

    testWidgets('14. Abrir un trabajo y volver recarga sin perder la pestaña',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(id: 'abc', numero: 4832, estado: 'en_sitio', cliente: 'Carlos Gomez'),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      await tester.tap(find.textContaining('En Proceso'));
      await tester.pumpAndSettle();
      final cargasAntes = banco.cargas;

      await tester.tap(find.text('Continuar ejecución'));
      await tester.pumpAndSettle();
      expect(banco.abiertos, <String>['abc']);

      await tester.tap(find.text('Cerrar detalle'));
      await tester.pumpAndSettle();

      expect(banco.cargas, greaterThan(cargasAntes), reason: 'al volver se recarga');
      expect(find.text('Carlos Gomez'), findsOneWidget);
      expect(
        tester.getSemantics(find.textContaining('En Proceso')).flagsCollection.isSelected,
        ui.Tristate.isTrue,
        reason: 'el filtro elegido no se pierde al volver del detalle',
      );
      await banco.cerrar();
    });

    testWidgets('15. Una sincronizacion exitosa recarga la lista sola',
        (WidgetTester tester) async {
      final banco = _Banco();
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();
      final antes = banco.cargas;

      banco.avisos.add(SyncStatus.success);
      await tester.pumpAndSettle();
      expect(banco.cargas, antes + 1);

      // Un error de sincronizacion no dispara recarga.
      banco.avisos.add(SyncStatus.error);
      await tester.pumpAndSettle();
      expect(banco.cargas, antes + 1);
      await banco.cerrar();
    });

    testWidgets('16. La orden que exige actualizar la app lo avisa en la lista',
        (WidgetTester tester) async {
      final banco = _Banco(filas: <Map<String, dynamic>>[
        _orden(
          id: '1',
          numero: 90,
          estado: 'asignada',
          compromiso: hoy,
          schemaVersion: 2,
        ),
      ]);
      await tester.pumpWidget(banco.app());
      await tester.pumpAndSettle();

      expect(
        find.text('Necesita una versión más nueva de la aplicación'),
        findsOneWidget,
      );
      await banco.cerrar();
    });
  });
}
