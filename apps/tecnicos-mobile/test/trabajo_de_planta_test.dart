import 'dart:async';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un trabajo que no es en la casa de nadie.
///
/// EL PROBLEMA QUE RESUELVE
/// -----------------------
/// El técnico hace las cuatro cosas: averías, instalaciones, **planta externa** y
/// mantenimiento. Cuando va a un poste a hacer una fusión no hay cliente, y la
/// ficha le armaba todo alrededor de «Cliente & Ubicación» y le decía *«no se
/// pudo identificar al cliente — preguntale en sitio»*. **No hay a quién
/// preguntarle: es un poste.** El mensaje es correcto para una avería y miente
/// para una obra, y mandar al técnico a buscar un dato que no existe le cuesta
/// una llamada al NOC.
///
/// POR QUÉ SE DERIVA DEL DATO Y NO DEL NOMBRE DEL TIPO DE TRABAJO
/// --------------------------------------------------------------
/// `FamiliaTrabajo` se decide buscando palabras en español —`instal`, `falla`,
/// `preventivo`— dentro del código y el nombre del tipo. Eso alcanza para elegir
/// un ícono y **no** para afirmar que no hay cliente: la empresa siguiente nombra
/// sus tipos distinto, y en otro idioma ninguna de esas palabras aparece. Una
/// palabra no es un hecho.
///
/// Lo que sí es un hecho, y vale igual en cualquier empresa: **la orden no trae a
/// nadie**. Esta prueba fija justamente eso, y la mitad de los casos existen para
/// que nadie lo "simplifique" mirando el tipo.
void main() {
  TrabajoVista hacer({
    String cliente = '',
    String telefono = '',
    String? serialOnu,
    String tipoCodigo = 'ftth_instalacion',
    String tipoNombre = 'Instalación FTTH',
    String direccion = 'Poste 42, carrera 7 con 45',
  }) {
    return TrabajoVista.desdeOrden(<String, dynamic>{
      'id': 'ot-1',
      'numero': 4832,
      'estado': 'asignada',
      'cliente_nombre': cliente,
      'direccion': direccion,
      'telefono': telefono,
      'tipo_nombre': tipoNombre,
      'tipo_codigo': tipoCodigo,
      'schema_version': 1,
      // La columna real se llama `contexto_json` y llega como texto: es como
      // la guarda la base local. Armar el mapa "ya lindo" probaría una forma que
      // en el teléfono nunca ocurre.
      'contexto_json':
          serialOnu == null ? null : '{"sn_onu": "$serialOnu"}',
    });
  }

  group('A · es trabajo de planta', () {
    test('a1 · sin nombre, sin teléfono y sin equipo: no hay cliente', () {
      expect(hacer().esTrabajoDePlanta, isTrue);
    });

    test('a2 · «Sin cliente» es relleno, no una persona', () {
      // Lo pone la capa local cuando el campo no vino. Tratarlo como nombre
      // haría que la ficha siga pidiendo preguntarle a alguien que no existe.
      for (final String relleno in <String>[
        'Sin cliente',
        'sin cliente',
        '  SIN CLIENTE  ',
        'Sin nombre',
        '   ',
      ]) {
        expect(hacer(cliente: relleno).esTrabajoDePlanta, isTrue,
            reason: '«$relleno»');
      }
    });
  });

  group('B · NO es trabajo de planta', () {
    test('b1 · con nombre de cliente, hay cliente', () {
      expect(hacer(cliente: 'Beatriz Pinzón').esTrabajoDePlanta, isFalse);
    });

    test('b2 · con teléfono y sin nombre, TODAVÍA hay a quién llamar', () {
      // Es el caso de una avería cuyo nombre no se pudo resolver: el técnico sí
      // tiene a quién preguntarle, y decirle que es planta le quitaría el
      // teléfono de la pantalla.
      expect(hacer(telefono: '+57 312 455 8901').esTrabajoDePlanta, isFalse);
    });

    test('b3 · con serial del equipo, hay un servicio detrás', () {
      expect(hacer(serialOnu: 'ZTEGC0A1B2C3').esTrabajoDePlanta, isFalse);
    });
  });

  _laPantalla();

  group('C · no se decide por el nombre del tipo de trabajo', () {
    test('c1 · un tipo que dice «instalación» SIN cliente sigue siendo planta',
        () {
      // La trampa opuesta: deducirlo de la palabra. Una instalación de planta
      // —tender fibra hasta una NAP nueva— se llama igual y no tiene cliente.
      final t = hacer(tipoCodigo: 'ftth_instalacion', tipoNombre: 'Instalación FTTH');
      expect(t.familia, FamiliaTrabajo.instalacion);
      expect(t.esTrabajoDePlanta, isTrue);
    });

    test('c2 · un tipo que la clasificación NO reconoce sigue teniendo cliente',
        () {
      // La empresa siguiente nombra sus tipos distinto y `FamiliaTrabajo` cae en
      // `otro`. Eso no puede cambiar si hay cliente o no.
      //
      // Nota de lo medido al escribir esto: `Fiber installation` SÍ se clasifica
      // como instalación, porque contiene «instal». Que acierte por accidente es
      // justo el motivo por el que no se puede colgar de ahí un hecho.
      final t = hacer(
        cliente: 'Beatriz Pinzón',
        tipoCodigo: 'svc_new_line',
        tipoNombre: 'New service turn-up',
      );
      expect(t.familia, FamiliaTrabajo.otro);
      expect(t.esTrabajoDePlanta, isFalse);
    });

    test('c3 · un tipo de mantenimiento con cliente tampoco es planta', () {
      final t = hacer(
        cliente: 'Beatriz Pinzón',
        tipoCodigo: 'mantenimiento_preventivo',
        tipoNombre: 'Mantenimiento preventivo',
      );
      expect(t.familia, FamiliaTrabajo.mantenimiento);
      expect(t.esTrabajoDePlanta, isFalse);
    });
  });
}

/// Lo que el técnico VE en la ficha de un trabajo de planta.
///
/// El modelo ya se midió arriba. Acá se afirma lo otro, que es donde estaba la
/// mentira: **qué dice la pantalla**. Una prueba que solo verifica el booleano
/// sobreviviría intacta a que la ficha siga diciendo «preguntale en sitio».
void _laPantalla() {
  Map<String, dynamic> filaDePlanta() => <String, dynamic>{
        'id': 'ot-1',
        'numero': 5120,
        'estado': 'asignada',
        'cliente_nombre': '',
        'direccion': 'Poste 42, carrera 7 con 45',
        'telefono': '',
        'tipo_nombre': 'Fusión en poste',
        'tipo_codigo': 'planta_fusion',
        'schema_version': 1,
        'revision': 1,
        'contexto_json': '{}',
      };

  Map<String, dynamic> filaDeCliente() => <String, dynamic>{
        ...filaDePlanta(),
        'cliente_nombre': 'Beatriz Pinzón',
        'telefono': '3005380776',
        'tipo_nombre': 'Reparación de Señal (FTTH)',
        'tipo_codigo': 'ftth_correctivo',
      };

  Future<void> montar(WidgetTester t, Map<String, dynamic> fila) async {
    t.view.physicalSize = const Size(1000, 4200);
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);

    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    final OrdenesJornada ordenes = OrdenesJornada(
      leerOrdenes: () async => <Map<String, dynamic>>[fila],
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    addTearDown(() async {
      await avisos.close();
      ordenes.dispose();
    });

    await t.pumpWidget(MaterialApp(
      theme: AppTheme.lightTheme,
      home: DetalleOrdenScreen(
        ordenId: 'ot-1',
        ordenes: ordenes,
        acciones: AccionesOrden(
          transicionar: ({
            required String ordenId,
            required String nuevoEstadoLocal,
            required String tipoAccion,
            required int revisionBase,
          }) async {},
          sincronizar: () async {},
        ),
      ),
    ));
    await t.pumpAndSettle();
  }

  group('D · lo que dice la ficha en un poste', () {
    testWidgets('d1 · NO manda a preguntarle a nadie', (WidgetTester t) async {
      await montar(t, filaDePlanta());

      // La frase que mentía. Es la afirmación más importante del archivo.
      expect(find.textContaining('Preguntale en sitio'), findsNothing);
      expect(find.text('No se pudo identificar al cliente'), findsNothing);
      expect(find.text('Este trabajo no es de un cliente'), findsOneWidget);
    });

    testWidgets('d2 · el bloque se llama Ubicación, no Cliente & Ubicación',
        (WidgetTester t) async {
      await montar(t, filaDePlanta());

      expect(find.text('Ubicación'), findsOneWidget);
      expect(find.text('Cliente & Ubicación'), findsNothing);
    });

    testWidgets('d3 · bajo el título va DÓNDE, no «Sin cliente»',
        (WidgetTester t) async {
      await montar(t, filaDePlanta());

      expect(find.text('Sin cliente'), findsNothing);
      expect(find.text('Poste 42, carrera 7 con 45'), findsWidgets);
    });

    testWidgets('d4 · una orden CON cliente sigue igual que antes',
        (WidgetTester t) async {
      // El contrapeso. Que el caso de planta quede bien no puede lograrse
      // quitándole el nombre y el teléfono a las averías, que son la mayoría.
      await montar(t, filaDeCliente());

      expect(find.text('Cliente & Ubicación'), findsOneWidget);
      expect(find.text('Beatriz Pinzón'), findsWidgets);
      expect(find.text('Este trabajo no es de un cliente'), findsNothing);
    });
  });
}
