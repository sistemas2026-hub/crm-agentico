import 'package:campo/core/api/api_client.dart';
import 'package:campo/core/storage/ciclo_de_vida_local.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/materiales/pedir_a_bodega.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// Lo que encontró una auditoría independiente sobre el pedido a bodega.
///
/// POR QUÉ ESTE ARCHIVO EXISTE APARTE
/// ----------------------------------
/// `pedir_a_bodega_test` y `subir_pedidos_test` miden lo que el pedido
/// **tiene** que hacer. Esto mide lo que se descubrió que hacía mal cuando
/// alguien que no lo construyó fue a romperlo, el 06/10/2026. Van juntos acá
/// porque comparten una lección: **las tres fallas eran silenciosas y las tres
/// terminaban en que el técnico espera material que no viene**, leyendo en la
/// pantalla que su pedido va en camino.
///
/// Que cada caso diga de dónde salió no es anécdota: es lo que evita que el
/// próximo arreglo las borre creyendo que sobran.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('auditoria_pedidos.db');

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

  // ---------------------------------------------------------------------- //
  // A1 · El bucle infinito
  // ---------------------------------------------------------------------- //

  group('A1 · Ningún fallo se reintenta para siempre', () {
    test('un 500 que se repite TERMINA en fallido, no en «sube cuando haya '
        'señal» eterno', () async {
      // EL HALLAZGO. `definitivo` era `codigo == 400 || codigo == 404`, así que
      // un 500 quedaba `pendiente`. El backoff topa en 60 s: el pedido se
      // reenviaba cada minuto, para siempre, y el técnico leía que estaba por
      // subir mientras bodega nunca se enteraba.
      await j.limpiar();
      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'el-que-revienta',
      );

      final Dio dio = ApiClient().dio;
      dio.interceptors.clear();
      int llamadas = 0;
      dio.interceptors.add(InterceptorsWrapper(
        onRequest: (RequestOptions o, RequestInterceptorHandler siga) {
          if (!o.path.contains('/inventario/pedidos/')) {
            siga.resolve(Response<dynamic>(requestOptions: o, statusCode: 204));
            return;
          }
          llamadas++;
          siga.reject(DioException(
            requestOptions: o,
            response: Response<dynamic>(requestOptions: o, statusCode: 500),
            type: DioExceptionType.badResponse,
          ));
        },
      ));
      addTearDown(dio.interceptors.clear);

      final LocalDatabase db = LocalDatabase();
      // Se fuerza la espera a cero en cada vuelta: lo que se mide es el techo
      // de INTENTOS, no el reloj.
      for (int i = 0; i < 12; i++) {
        final base = await db.database;
        await base.update(
          'cola_pedidos_material',
          <String, Object?>{'next_attempt_at': 0},
        );
        await SyncQueueService().procesarCola();
      }

      final List<PedidoEnCola> pedidos = await leerPedidosDeMaterial();
      expect(pedidos.first.estado, 'fallido',
          reason: 'tras el techo de intentos el pedido se cierra');
      expect(pedidos.first.comoVa, 'No se pudo pedir');
      expect(pedidos.first.errorMensaje, contains('intentos'),
          reason: 'el motivo dice que se dejó de intentar, no «sin conexión»');
      expect(llamadas, lessThanOrEqualTo(10),
          reason: 'no sigue llamando después del techo');
    });

    test('un 500 PASAJERO no cierra el pedido: dos intentos y sigue pendiente',
        () async {
      // El contrapeso. Si el techo fuera 1, un corte de diez minutos perdería
      // pedidos buenos — y perder un pedido es el peor resultado de los dos.
      await j.limpiar();
      await encolarPedidoDeMaterial(
        material: conector,
        cantidad: '20',
        idFijo: 'pasajero',
      );

      final Dio dio = ApiClient().dio;
      dio.interceptors.clear();
      dio.interceptors.add(InterceptorsWrapper(
        onRequest: (RequestOptions o, RequestInterceptorHandler siga) {
          if (!o.path.contains('/inventario/pedidos/')) {
            siga.resolve(Response<dynamic>(requestOptions: o, statusCode: 204));
            return;
          }
          siga.reject(DioException(
            requestOptions: o,
            type: DioExceptionType.connectionError,
            message: 'sin red',
          ));
        },
      ));
      addTearDown(dio.interceptors.clear);

      final LocalDatabase db = LocalDatabase();
      for (int i = 0; i < 2; i++) {
        final base = await db.database;
        await base.update(
          'cola_pedidos_material',
          <String, Object?>{'next_attempt_at': 0},
        );
        await SyncQueueService().procesarCola();
      }

      expect((await leerPedidosDeMaterial()).first.estado, 'pendiente');
    });
  });

  // ---------------------------------------------------------------------- //
  // A1 + A3 · El tope y el mínimo de la cantidad
  // ---------------------------------------------------------------------- //

  group('A1/A3 · La cantidad que el servidor puede guardar', () {
    test('diez dígitos se rechazan EN LA HOJA, no con un 500 del servidor', () {
      // `numeric(12,3)` admite nueve enteros. Se teclean con el dedo gordo en
      // el teclado numérico, y antes el pedido salía, reventaba y se
      // reintentaba sin fin.
      expect(ReglasDelPedido.queLeFaltaALaCantidad('1000000000'), isNotNull);
      expect(ReglasDelPedido.queLeFaltaALaCantidad('999999999'), isNull,
          reason: 'el tope no puede comerse lo que la columna sí aguanta');
    });

    test('una cantidad que se guardaría como CERO se rechaza', () {
      // `0,0001` pasaba el «más que cero» y el servidor lo escribía `0.000`:
      // el aviso a bodega decía «0 de Conector SC/APC».
      expect(ReglasDelPedido.queLeFaltaALaCantidad('0,0001'), isNotNull);
      expect(ReglasDelPedido.queLeFaltaALaCantidad('0,001'), isNull,
          reason: 'la escala de la columna son tres decimales');
    });

    test('NaN e infinito no son cantidades', () {
      for (final String malo in <String>['NaN', 'Infinity', '-Infinity']) {
        expect(ReglasDelPedido.queLeFaltaALaCantidad(malo), isNotNull,
            reason: malo);
      }
    });

    test('lo que no se encola tampoco llega a la base', () async {
      await j.limpiar();

      expect(
        await encolarPedidoDeMaterial(
            material: conector, cantidad: '1000000000'),
        isFalse,
      );
      expect(await leerPedidosDeMaterial(), isEmpty);
    });
  });

  // ---------------------------------------------------------------------- //
  // A4 · El teléfono de cuadrilla
  // ---------------------------------------------------------------------- //

  group('A4 · Un pedido pendiente es trabajo sin subir', () {
    test('CUENTA como pendiente, así la purga no se lo lleva', () async {
      // EL HALLAZGO, Y EL PEOR DE LOS TRES. El técnico A pide sin señal y
      // entrega el teléfono de cuadrilla; B entra; `prepararPara` veía cero
      // pendientes de A y purgaba su identidad. El pedido no subía nunca —solo
      // se suben los de la sesión activa— y A esperaba material que nadie pidió.
      await j.limpiar();
      await encolarPedidoDeMaterial(material: conector, cantidad: '20');

      final CicloDeVidaLocal ciclo = CicloDeVidaLocal(LocalDatabase());
      final ResumenPendientes resumen = await ciclo.pendientesDe(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );

      expect(resumen.pedidosABodega, 1);
      expect(resumen.hayPendientes, isTrue,
          reason: 'con esto en falso, la identidad se purga y el pedido se pierde');
      expect(
        resumen.detalle.any((String d) => d.contains('Pedido a bodega')),
        isTrue,
        reason: 'quien está por cerrar sesión tiene que ver QUÉ se perdería',
      );
    });

    test('LA PURGA ALCANZA A TODAS LAS TABLAS DE LA PERSONA, no a una lista',
        () async {
      // La purga llevaba OCHO nombres escritos a mano y el esquema ya tenía
      // doce tablas con `(org_id, profile_id)`. Faltaban la cola de
      // seguimiento, las notificaciones, los materiales de la orden y la de
      // pedidos. Lo grave es el patrón: cada tabla nueva lo repetía, y una
      // rutina que informa «borré tus datos» dejaba datos.
      //
      // Esta afirmación no se puede olvidar: pregunta al ESQUEMA cuáles son.
      await j.limpiar();
      final LocalDatabase db = LocalDatabase();
      final List<String> tablas = await db.tablasPorIdentidad();

      expect(tablas, contains('cola_pedidos_material'));
      expect(tablas.length, greaterThanOrEqualTo(9),
          reason: 'la lista a mano tenía 8 y el esquema tiene más');

      // Se siembra UNA fila en cada tabla por identidad y se comprueba que
      // ninguna sobrevive. Sembrar a mano cada una exigiría conocer su esquema,
      // así que se usa lo que ya hay: el pedido, el kit y una orden.
      await encolarPedidoDeMaterial(material: conector, cantidad: '20');
      await j.sembrarKit();
      await j.sembrarOrden();

      await db.borrarDatosDeIdentidad(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );

      final base = await db.database;
      for (final String tabla in tablas) {
        final List<Map<String, Object?>> quedan = await base.query(
          tabla,
          where: 'org_id = ? AND profile_id = ?',
          whereArgs: <Object?>[JornadaDePrueba.org, JornadaDePrueba.perfil],
        );
        expect(quedan, isEmpty, reason: '$tabla quedó con datos tras la purga');
      }
    });

    test('la purga NO se lleva lo de otra persona', () async {
      // El contrapeso: borrar de más en un teléfono de cuadrilla le borra la
      // jornada al compañero.
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

      await db.borrarDatosDeIdentidad(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );

      final base = await db.database;
      final List<Map<String, Object?>> dePedro = await base.query(
        'cola_pedidos_material',
        where: 'profile_id = ?',
        whereArgs: <Object?>[JornadaDePrueba.otraPersona],
      );
      expect(dePedro, hasLength(1));
    });
  });
}
