import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';
import 'apoyo/sesion_en_el_telefono.dart';

/// E2E-003 · Un día entero sin señal, y la vuelta.
///
/// POR QUÉ ESTE ES EL ESCENARIO MÁS IMPORTANTE
/// -------------------------------------------
/// Porque es el día normal, no la excepción. En un sótano, en una zona rural
/// o dentro de una caja de distribución no hay red, y la aplicación tiene que
/// dejar trabajar igual. Todo lo demás —las pantallas, el dominio, la
/// conciliación— importa menos que esto: si alguien no puede registrar lo que
/// acaba de hacer, vuelve al papel y no vuelve más.
///
/// Lo que se mide acá no es que "funcione sin red". Es lo que pasa **cuando
/// la red vuelve**: que nada se duplique, que nada se pierda, y que el saldo
/// no se mueva solo. Esa transición es donde se rompen las aplicaciones
/// offline, y es invisible mirando una pantalla a la vez.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('e2e_003.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  tearDownAll(j.cerrarTodo);

  /// La pantalla de materiales, leyendo de la base como en el teléfono.
  Future<void> abrirMateriales(WidgetTester t) => montarConBaseReal(
        t,
        j.enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );

  group('E2E-003 · Sin señal, y la vuelta', () {
    testWidgets('1. Se registra sin red y el saldo baja en el acto',
        (WidgetTester t) async {
      // No se espera al servidor para mostrar lo que la persona acaba de
      // hacer: un conector que ya puso es un conector que ya no tiene.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
      });

      await abrirMateriales(t);

      expect(find.textContaining('8 Disp.'), findsWidgets);
      expect(find.textContaining('1 movimiento esperando señal'),
          findsOneWidget);
    });

    testWidgets('2. Dos registros seguidos se suman, no se pisan',
        (WidgetTester t) async {
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
        await j.consumir(id: 'mov-2', cantidad: '3');
      });

      await abrirMateriales(t);

      expect(find.textContaining('5 Disp.'), findsWidgets);
      expect(find.textContaining('2 movimientos esperando señal'),
          findsOneWidget);
    });

    testWidgets('3. El mismo toque dos veces descuenta una sola',
        (WidgetTester t) async {
      // Un doble toque, o un reintento de la pantalla, no puede gastar el
      // material dos veces. La clave del hecho es la que manda, no cuántas
      // veces se llamó.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
        await j.consumir(id: 'mov-1', cantidad: '2');
      });

      await abrirMateriales(t);

      expect(find.textContaining('8 Disp.'), findsWidgets,
          reason: 'dos conectores, no cuatro');
      expect(find.textContaining('1 movimiento esperando señal'),
          findsOneWidget);
    });

    testWidgets('4. Cuando vuelve la señal, el saldo NO se mueve',
        (WidgetTester t) async {
      // El defecto que encontró el flujo completo, ahora mirado desde la
      // pantalla: al confirmar, el movimiento sale de la cola y el saldo
      // rebotaba a diez. Un número que se mueve solo, en la pantalla donde
      // alguien decide si le alcanza el material para el próximo trabajo.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
        await j.elServidorResponde(id: 'mov-1');
      });

      await abrirMateriales(t);

      expect(find.textContaining('8 Disp.'), findsWidgets,
          reason: 'el mismo saldo antes y después de subir');
      expect(
        find.textContaining('esperando señal'),
        findsNothing,
        reason: 'ya llegó: no puede seguir diciendo que espera',
      );
    });

    testWidgets('5. Un envío fallido no borra el trabajo hecho',
        (WidgetTester t) async {
      // 503 del servidor, o la red que se cortó en el medio. El movimiento
      // sigue en la cola y el saldo sigue descontado: lo que la persona hizo
      // no depende de que el servidor esté disponible.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
        await j.db.registrarFalloMovimientoMaterial(
          id: 'mov-1',
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
          nextAttemptAt: 0,
          errorMensaje: 'El servidor respondió 503.',
        );
      });

      await abrirMateriales(t);

      expect(find.textContaining('8 Disp.'), findsWidgets);
      expect(find.textContaining('1 movimiento esperando señal'),
          findsOneWidget);
    });

    testWidgets('6. Reintentar después de un fallo no duplica el descuento',
        (WidgetTester t) async {
      // El caso que junta todo: falló, se reintentó, el servidor lo aceptó.
      // Si el descuento se aplicara dos veces —una por la cola y otra al
      // confirmar— el saldo quedaría en seis y nadie sabría por qué.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
        await j.db.registrarFalloMovimientoMaterial(
          id: 'mov-1',
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
          nextAttemptAt: 0,
          errorMensaje: 'timeout',
        );
        await j.elServidorResponde(id: 'mov-1');
        // Y el servidor contesta de nuevo el mismo movimiento: pasa cuando
        // la respuesta anterior se perdió y el reintento llegó igual.
        await j.elServidorResponde(id: 'mov-1');
      });

      await abrirMateriales(t);

      expect(find.textContaining('8 Disp.'), findsWidgets,
          reason: 'dos conectores gastados, por más vueltas que haya dado');
      expect(find.textContaining('esperando señal'), findsNothing);
    });
  });
}
