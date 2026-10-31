import 'package:campo/core/storage/local_database.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:campo/features/materiales/pedir_a_bodega.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';
import 'apoyo/sesion_en_el_telefono.dart';

/// Pedirle material a bodega desde la calle.
///
/// EL PROBLEMA QUE CIERRA
/// ----------------------
/// El técnico se queda sin conectores en la tercera instalación y la aplicación
/// no tenía nada que ofrecerle: sacaba el otro teléfono y escribía al grupo. La
/// pantalla de Materiales le decía lo que tiene, y ahí se cortaba.
///
/// LO QUE SE AFIRMA, Y POR QUÉ CADA COSA
/// --------------------------------------
/// 1. **Se puede pedir sin señal**, que es el único momento en que hace falta.
/// 2. **La cola NO es la de movimientos.** Un movimiento es un hecho que YA
///    ocurrió; un pedido es que todavía no pasó nada. Compartirla haría que el
///    saldo cuente material que nadie entregó — la afirmación que sostiene al
///    inventario entero.
/// 3. **El reenvío es el mismo pedido**: la clave viaja en la fila, no se
///    genera al enviar.
/// 4. **Se ve que se pidió.** Sin eso, un pedido encolado no produce ninguna
///    señal visible y el técnico vuelve a pedir lo mismo, o deja de pedir
///    creyendo que ya pidió.
/// 5. **Un pedido fallado se dice fallado**, y no se borra: borrarlo lo deja
///    pareciendo que está en camino, y el técnico lo espera.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('pedidos.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  tearDownAll(j.cerrarTodo);

  const MaterialEnCustodia conector = MaterialEnCustodia(
    categoria: 'Conectividad',
    nombre: 'Conector SC/APC',
    detalle: 'CON-SC-APC',
    codigo: 'CON-SC-APC',
    clase: ClaseMaterial.consumible,
    recibidos: 10,
    usados: 9,
    unidad: 'unidades',
  );

  // ------------------------------------------------------------------------ //
  // A. Las reglas, sin pantalla
  // ------------------------------------------------------------------------ //

  group('A · Las reglas de la cantidad', () {
    test('A1 · vacía, no es un pedido', () {
      expect(ReglasDelPedido.queLeFaltaALaCantidad(''), isNotNull);
      expect(ReglasDelPedido.queLeFaltaALaCantidad('   '), isNotNull);
    });

    test('A2 · cero y negativo se rechazan', () {
      // Llenarían la lista de bodega de filas que no piden nada.
      expect(ReglasDelPedido.queLeFaltaALaCantidad('0'), isNotNull);
      expect(ReglasDelPedido.queLeFaltaALaCantidad('-5'), isNotNull);
    });

    test('A3 · lo que no es número se rechaza', () {
      expect(ReglasDelPedido.queLeFaltaALaCantidad('muchos'), isNotNull);
    });

    test('A4 · LA COMA DECIMAL VALE: es la que se escribe en Colombia', () {
      // «2,5» es lo que un técnico teclea para dos metros y medio de bobina.
      // Rechazarlo sería rechazar la forma correcta de escribirlo.
      expect(ReglasDelPedido.queLeFaltaALaCantidad('2,5'), isNull);
      expect(ReglasDelPedido.cantidadParaElServidor('2,5'), '2.5');
    });

    test('A5 · un entero sale entero, no «20.0»', () {
      expect(ReglasDelPedido.cantidadParaElServidor('20'), '20');
      expect(ReglasDelPedido.cantidadParaElServidor('20,000'), '20');
    });

    test('A6 · un número normal pasa', () {
      expect(ReglasDelPedido.queLeFaltaALaCantidad('20'), isNull);
    });
  });

  // ------------------------------------------------------------------------ //
  // B. La cola, contra la base de verdad
  // ------------------------------------------------------------------------ //

  group('B · La cola del teléfono', () {
    test('B1 · un pedido queda encolado SIN red', () async {
      await j.limpiar();

      final bool quedo = await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        motivo: 'Me quedé en la tercera instalación',
      );

      expect(quedo, isTrue);
      final List<PedidoEnCola> pedidos = await leerPedidosDeMaterial();
      expect(pedidos, hasLength(1));
      expect(pedidos.first.material, 'Conector SC/APC');
      expect(pedidos.first.cantidad, '20');
      expect(pedidos.first.estado, 'pendiente');
    });

    test('B2 · PEDIR NO MUEVE EL SALDO. La afirmación del inventario entero',
        () async {
      // Un movimiento es un hecho que ya ocurrió; un pedido es que todavía no
      // pasó nada. Si pedir creara un movimiento, el saldo contaría material
      // que nadie entregó, y el descuadre de fin de mes sería inexplicable.
      await j.limpiar();
      await j.sembrarKit(recibido: '10', consumido: '9');

      await encolarPedidoDeMaterial(material: conector, cantidad: '20');

      final LocalDatabase db = LocalDatabase();
      final List<Map<String, dynamic>> movimientos =
          await db.getMovimientosMaterialPendientes(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );
      expect(movimientos, isEmpty,
          reason: 'un pedido no puede crear un movimiento');

      final List<Map<String, dynamic>> kit = await db.getKit(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );
      expect(kit.first['recibido'], '10',
          reason: 'el kit no se toca por haber pedido');
    });

    test('B3 · el pedido es de ESTA persona, no del teléfono', () async {
      // Un teléfono de cuadrilla pasa de mano en mano. El pedido del que salió
      // no se manda con la sesión del que entró.
      await j.limpiar();
      final LocalDatabase db = LocalDatabase();
      await db.encolarPedidoDeMaterial(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.otraPersona,
        id: 'de-pedro',
        materialId: 'CON-SC-APC',
        materialNombre: 'Conector de Pedro',
        cantidad: '5',
      );
      await encolarPedidoDeMaterial(material: conector, cantidad: '20');

      final List<PedidoEnCola> mios = await leerPedidosDeMaterial();

      expect(mios, hasLength(1));
      expect(mios.first.cantidad, '20');
    });

    test('B4 · un pedido sin código de material NO se encola', () async {
      // Sin código no hay con qué preguntarle al servidor. Encolarlo sería
      // guardar una fila que falla para siempre y que el técnico ve como
      // «pedido»: peor que no haber pedido.
      await j.limpiar();
      const MaterialEnCustodia sinCodigo = MaterialEnCustodia(
        categoria: 'x',
        nombre: 'Material de ejemplo',
        detalle: '',
        clase: ClaseMaterial.consumible,
        recibidos: 1,
        usados: 0,
        unidad: 'unidades',
      );

      final bool quedo =
          await encolarPedidoDeMaterial(material: sinCodigo, cantidad: '20');

      expect(quedo, isFalse);
      expect(await leerPedidosDeMaterial(), isEmpty);
    });

    test('B5 · una cantidad inválida no llega a la base', () async {
      await j.limpiar();

      expect(
        await encolarPedidoDeMaterial(material: conector, cantidad: '0'),
        isFalse,
      );
      expect(await leerPedidosDeMaterial(), isEmpty);
    });

    test('B6 · EL MISMO ID ES EL MISMO PEDIDO, no dos', () async {
      // La clave es el `id` de la fila, generado al encolar. Una clave nueva
      // por intento sería un identificador único, no una clave idempotente — y
      // bodega creería que hacen falta cuarenta conectores.
      await j.limpiar();

      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'misma-clave',
      );
      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'misma-clave',
      );

      expect(await leerPedidosDeMaterial(), hasLength(1));
    });

    test('B6b · reencolar un id YA ENVIADO no lo reabre', () async {
      // El contrapeso de B6: que no se dupliquen no puede lograrse pisando la
      // fila. Si el insert reemplazara, un pedido que bodega ya recibió
      // volvería a `pendiente` y se mandaría de nuevo — el duplicado entraría
      // por la puerta de al lado.
      await j.limpiar();
      final LocalDatabase db = LocalDatabase();
      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'ya-subio',
      );
      await db.marcarPedidoEnviado(
        id: 'ya-subio',
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );

      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'ya-subio',
      );

      final List<PedidoEnCola> todos = await leerPedidosDeMaterial();
      expect(todos, hasLength(1));
      expect(todos.first.estado, 'enviado',
          reason: 'el pedido ya subió; reencolarlo no puede reabrirlo');
    });

    test('B7 · sólo sale a subir lo PENDIENTE, y una vez enviado no vuelve',
        () async {
      await j.limpiar();
      final LocalDatabase db = LocalDatabase();
      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'p1',
      );

      expect(
        await db.pedidosPendientes(
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
        ),
        hasLength(1),
      );

      await db.marcarPedidoEnviado(
        id: 'p1',
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );

      expect(
        await db.pedidosPendientes(
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
        ),
        isEmpty,
        reason: 'un pedido ya enviado no se vuelve a mandar',
      );
      // Pero SIGUE A LA VISTA: una fila que desaparece se lee como «no se
      // mandó», y es lo contrario de lo que pasó.
      final List<PedidoEnCola> todos = await leerPedidosDeMaterial();
      expect(todos, hasLength(1));
      expect(todos.first.estado, 'enviado');
    });

    test('B8 · un fallo definitivo queda FALLIDO con su motivo, y no se reenvía',
        () async {
      // Un 400 por una cantidad que el servidor no acepta da el mismo resultado
      // para siempre. Reintentarlo es ruido; lo que destraba es que el técnico
      // lo VEA fallado y pueda volver a pedirlo bien.
      await j.limpiar();
      final LocalDatabase db = LocalDatabase();
      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'p2',
      );

      await db.registrarFalloPedido(
        id: 'p2',
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
        errorMensaje: 'Ese material no existe en esta empresa.',
        intentos: 0,
        definitivo: true,
      );

      expect(
        await db.pedidosPendientes(
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
        ),
        isEmpty,
      );
      final List<PedidoEnCola> todos = await leerPedidosDeMaterial();
      expect(todos.first.estado, 'fallido');
      expect(todos.first.errorMensaje, contains('no existe'));
      expect(todos.first.comoVa, 'No se pudo pedir');
      expect(todos.first.esProblema, isTrue);
    });

    test('B9 · un fallo pasajero SIGUE pendiente, pero espera su turno',
        () async {
      // Un corte de red se reintenta. Sin la espera, un pedido que falla
      // machaca al servidor en cada ciclo de sincronización.
      await j.limpiar();
      final LocalDatabase db = LocalDatabase();
      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'p3',
      );

      await db.registrarFalloPedido(
        id: 'p3',
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
        errorMensaje: 'sin conexión',
        intentos: 0,
        nextAttemptAt:
            DateTime.now().millisecondsSinceEpoch + const Duration(minutes: 5).inMilliseconds,
      );

      expect(
        await db.pedidosPendientes(
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
        ),
        isEmpty,
        reason: 'todavía no le toca',
      );
      final List<PedidoEnCola> todos = await leerPedidosDeMaterial();
      expect(todos.first.estado, 'pendiente',
          reason: 'un fallo de red no cierra el pedido');
    });

    test('B11 · cerrar un pedido NO cruza personas', () async {
      // Defensa en profundidad y medida igual. Hoy el procesador marca ids que
      // salieron de su propia consulta filtrada, así que el camino no se
      // alcanza — pero esta es exactamente la familia de fallo que ya apareció
      // una vez en este módulo (desactivar un token sin filtrar por empresa),
      // y lo que la hace invisible es que sólo se nota cuando dos sesiones
      // comparten el teléfono.
      await j.limpiar();
      final LocalDatabase db = LocalDatabase();
      await db.encolarPedidoDeMaterial(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.otraPersona,
        id: 'de-pedro',
        materialId: 'CON-SC-APC',
        materialNombre: 'Conector de Pedro',
        cantidad: '5',
      );

      // Con MI sesión, el id de Pedro.
      await db.marcarPedidoEnviado(
        id: 'de-pedro',
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );
      await db.registrarFalloPedido(
        id: 'de-pedro',
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
        errorMensaje: 'no debería tocarlo',
        intentos: 0,
        definitivo: true,
      );

      final base = await db.database;
      final List<Map<String, Object?>> dePedro = await base.query(
        'cola_pedidos_material',
        where: 'id = ?',
        whereArgs: <Object?>['de-pedro'],
      );
      expect(dePedro.first['estado'], 'pendiente',
          reason: 'el pedido de otra persona sigue intacto');
      expect(dePedro.first['error_mensaje'], isNull);
    });

    test('B10 · la cola de pedidos NO es la de movimientos', () async {
      // Están separadas a propósito y esto lo mide: un pedido no aparece en la
      // tabla append-only de hechos, ni al revés.
      await j.limpiar();
      final LocalDatabase db = LocalDatabase();
      await encolarPedidoDeMaterial(material: conector, cantidad: '20');

      final base = await db.database;
      final pedidos = await base.query('cola_pedidos_material');
      final movimientos = await base.query('cola_movimientos_material');

      expect(pedidos, hasLength(1));
      expect(movimientos, isEmpty);
    });
  });

  // ------------------------------------------------------------------------ //
  // C. La pantalla
  // ------------------------------------------------------------------------ //

  group('C · La pantalla de Materiales', () {
    testWidgets('C1 · hay un botón para pedir donde antes había uno muerto',
        (WidgetTester t) async {
      // «Transferir» estaba dibujado sin acción desde que la pantalla se
      // replicó del diseño. Un botón que no responde enseña a no confiar en la
      // barra entera.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
      });

      await montarConBaseReal(
        t,
        j.enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );

      expect(find.text('Pedir'), findsOneWidget);
      expect(find.text('Transferir'), findsNothing,
          reason: 'el botón muerto no puede seguir ahí');
    });

    testWidgets('C2 · el toque abre la hoja, y la hoja dice qué hace',
        (WidgetTester t) async {
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
      });

      await montarConBaseReal(
        t,
        j.enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );
      await t.tap(find.text('Pedir'));
      await esperarLaAnimacion(t);

      expect(find.text('Pedir a bodega'), findsOneWidget);
      // Que queda guardado es LO QUE HAY QUE DECIR: sin eso, quien está sin
      // señal no sabe si tocar el botón sirvió de algo.
      expect(
        find.textContaining('sube cuando haya señal'),
        findsOneWidget,
      );
    });

    testWidgets('C3 · SE VE QUE SE PIDIÓ, con su estado', (WidgetTester t) async {
      // Sin esta tira, un pedido encolado no produce ninguna señal visible: el
      // técnico vuelve a pedir lo mismo o deja de pedir creyendo que ya pidió.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await encolarPedidoDeMaterial(material: conector, cantidad: '20');
      });

      await montarConBaseReal(
        t,
        j.enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );

      expect(find.text('Pedidos a bodega'), findsOneWidget);
      expect(find.textContaining('Conector SC/APC'), findsWidgets);
      expect(find.text('Sube cuando haya señal'), findsOneWidget);
    });

    testWidgets('C4 · sin pedidos la tira NO aparece', (WidgetTester t) async {
      // El contrapeso: una tira vacía que dice «Pedidos a bodega» ocupa el
      // lugar de lo que sí hay que mirar.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
      });

      await montarConBaseReal(
        t,
        j.enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );

      expect(find.text('Pedidos a bodega'), findsNothing);
    });
  });

  // ------------------------------------------------------------------------ //
  // D. La hoja
  // ------------------------------------------------------------------------ //

  group('D · La hoja de pedido', () {
    Widget hoja({
      Future<bool> Function({
        required MaterialEnCustodia material,
        required String cantidad,
        String motivo,
        String? ordenId,
      })? alPedir,
    }) =>
        MaterialApp(
          home: Scaffold(
            body: HojaDePedido(
              materiales: const <MaterialEnCustodia>[conector],
              alPedir: alPedir,
            ),
          ),
        );

    testWidgets('D1 · el saldo va en la misma línea del material',
        (WidgetTester t) async {
      // Lo primero que uno quiere saber al pedir es cuánto le queda.
      await t.pumpWidget(hoja());
      await t.pump();

      expect(find.textContaining('quedan 1 unidades'), findsWidgets);
    });

    testWidgets('D2 · sin cantidad NO se pide, y lo dice', (WidgetTester t) async {
      bool llamado = false;
      await t.pumpWidget(hoja(alPedir: ({
        required MaterialEnCustodia material,
        required String cantidad,
        String motivo = '',
        String? ordenId,
      }) async {
        llamado = true;
        return true;
      }));
      await t.pump();

      await t.tap(find.text('Pedir'));
      await t.pump();

      expect(llamado, isFalse, reason: 'no puede salir un pedido sin cantidad');
      expect(find.text('Decí cuánto necesitás.'), findsOneWidget);
    });

    testWidgets('D3 · el motivo es OPCIONAL y el pedido sale igual',
        (WidgetTester t) async {
      // Parado en una escalera, escribir un motivo es lo primero que se saltea.
      // Exigirlo haría que el pedido no se haga, que es el único resultado malo.
      String? motivoRecibido;
      await t.pumpWidget(hoja(alPedir: ({
        required MaterialEnCustodia material,
        required String cantidad,
        String motivo = '',
        String? ordenId,
      }) async {
        motivoRecibido = motivo;
        return true;
      }));
      await t.pump();

      await t.enterText(find.byType(TextField).first, '20');
      await t.tap(find.text('Pedir'));
      await t.pump();

      expect(motivoRecibido, '');
    });

    testWidgets('D4 · SI NO SE PUDO GUARDAR, LA HOJA NO SE CIERRA',
        (WidgetTester t) async {
      // Cerrarla diciendo «listo» cuando nada se guardó es la peor salida: el
      // técnico sigue su día creyendo que el material viene.
      await t.pumpWidget(hoja(alPedir: ({
        required MaterialEnCustodia material,
        required String cantidad,
        String motivo = '',
        String? ordenId,
      }) async =>
          false));
      await t.pump();

      await t.enterText(find.byType(TextField).first, '20');
      await t.tap(find.text('Pedir'));
      await t.pump();
      await t.pump();

      expect(find.text('Pedir a bodega'), findsOneWidget,
          reason: 'la hoja sigue abierta');
      expect(find.textContaining('No se pudo guardar'), findsOneWidget);
    });

    testWidgets('D5 · con kit vacío lo dice y el botón no se puede tocar',
        (WidgetTester t) async {
      await t.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: HojaDePedido(materiales: <MaterialEnCustodia>[]),
        ),
      ));
      await t.pump();

      expect(find.textContaining('no hay de qué pedir'), findsOneWidget);
      final FilledButton boton =
          t.widget<FilledButton>(find.byType(FilledButton));
      expect(boton.onPressed, isNull);
    });

    testWidgets('D6 · la cantidad llega TAL COMO SE ESCRIBIÓ a quien encola',
        (WidgetTester t) async {
      String? recibida;
      await t.pumpWidget(hoja(alPedir: ({
        required MaterialEnCustodia material,
        required String cantidad,
        String motivo = '',
        String? ordenId,
      }) async {
        recibida = cantidad;
        return true;
      }));
      await t.pump();

      await t.enterText(find.byType(TextField).first, '2,5');
      await t.tap(find.text('Pedir'));
      await t.pump();

      expect(recibida, '2,5',
          reason: 'la traducción a punto decimal es de quien encola, no de la '
              'pantalla: así hay un solo lugar donde puede estar mal');
    });
  });
}
