import 'package:campo/core/api/api_client.dart';
import 'package:campo/core/api/api_endpoints.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/materiales/pedir_a_bodega.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// Lo que pasa CUANDO VUELVE LA SEÑAL con un pedido encolado.
///
/// POR QUÉ ESTA PRUEBA EXISTE APARTE
/// ---------------------------------
/// `pedir_a_bodega_test` mide la cola: que el pedido se guarde, que no cruce
/// personas, que no mueva el saldo. Nada de eso dice que el pedido **suba**.
/// Y ese es justo el tramo que §6 llama *código construido no es código que
/// corre*: un procesador escrito, con su `catch` y su backoff, que nadie llama
/// o que llama mal, no da error, ni log, ni alerta — el pedido simplemente se
/// queda ahí y el técnico espera material que nadie pidió.
///
/// Se mide interceptando el `Dio` real del cliente: la petición se arma
/// completa y se responde desde acá. Así se afirma lo que el servidor VA A
/// RECIBIR, no lo que el código se propone mandar.
///
/// LO QUE SE AFIRMA
/// ----------------
/// 1. Sube, y con la **clave de idempotencia en el cuerpo** — que es toda la
///    garantía contra el duplicado.
/// 2. El **200 también cierra el pedido**: el servidor contesta 200 cuando
///    reconoce un reenvío, y si eso llegara como error se reintentaría para
///    siempre.
/// 3. Un **400 es definitivo** y queda a la vista con su motivo.
/// 4. Un **corte de red NO lo pierde**: sigue pendiente.
/// 5. Un pedido ya enviado **no se manda otra vez**.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('subir_pedidos.db');

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

  /// Lo que el teléfono le mandó al servidor, visto desde el otro lado.
  late List<RequestOptions> enviadas;

  /// Responde la petición de pedidos con lo que diga el caso, y deja pasar todo
  /// lo demás al vacío — el ciclo completo toca muchos endpoints y ninguno
  /// importa acá.
  void responder(Response<dynamic> Function(RequestOptions) comoContesta) {
    final Dio dio = ApiClient().dio;
    dio.interceptors.clear();
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (RequestOptions opciones, RequestInterceptorHandler siga) {
        if (!opciones.path.contains('/inventario/pedidos/')) {
          // Un 204 vacío: no es lo que devolvería el servidor de verdad, pero
          // este caso no mide esos endpoints y cualquier cosa que no sea una
          // llamada a la red sirve.
          siga.resolve(Response<dynamic>(
            requestOptions: opciones,
            statusCode: 204,
          ));
          return;
        }
        enviadas.add(opciones);
        final Response<dynamic> r = comoContesta(opciones);
        if (r.statusCode != null && r.statusCode! >= 400) {
          siga.reject(DioException(
            requestOptions: opciones,
            response: r,
            type: DioExceptionType.badResponse,
          ));
          return;
        }
        siga.resolve(r);
      },
    ));
    addTearDown(dio.interceptors.clear);
  }

  Response<dynamic> ok(RequestOptions o, int codigo) => Response<dynamic>(
        requestOptions: o,
        statusCode: codigo,
        data: <String, dynamic>{
          'id': 'srv-1',
          'material': 'Conector SC/APC',
          'cantidad': '20',
          'estado': 'pendiente',
        },
      );

  setUp(() => enviadas = <RequestOptions>[]);

  /// Corre sólo el tramo de pedidos del ciclo.
  ///
  /// `procesarCola()` entera arrastra descargas y transiciones que no tienen
  /// nada que ver, y un fallo ahí aparecería como un fallo de los pedidos.
  Future<void> subirLosPedidos() => SyncQueueService().procesarCola();

  Future<void> encolarUno({String id = 'p1', String cantidad = '20'}) =>
      encolarPedidoDeMaterial(
        material: conector,
        cantidad: cantidad,
        motivo: 'Me quedé en la tercera instalación',
        idFijo: id,
      );

  test('1 · sube, y la clave de idempotencia VA EN EL CUERPO', () async {
    // La clave es el `id` de la fila, generado al encolar. Si se generara al
    // enviar sería un identificador único por intento, no una clave
    // idempotente: bodega creería que hacen falta cuarenta conectores.
    await j.limpiar();
    await encolarUno(id: 'clave-de-la-fila');
    responder((RequestOptions o) => ok(o, 201));

    await subirLosPedidos();

    expect(enviadas, hasLength(1));
    final Map<String, dynamic> cuerpo =
        enviadas.first.data as Map<String, dynamic>;
    expect(cuerpo['idempotency_key'], 'clave-de-la-fila');
    expect(cuerpo['material'], 'CON-SC-APC',
        reason: 'se identifica por código, que es lo que el kit trae');
    expect(cuerpo['cantidad'], '20');
    expect(cuerpo['motivo'], 'Me quedé en la tercera instalación');
    expect(enviadas.first.path, ApiEndpoints.pedidosMaterial);

    final List<PedidoEnCola> pedidos = await leerPedidosDeMaterial();
    expect(pedidos.first.estado, 'enviado');
  });

  test('2 · EL 200 TAMBIÉN CIERRA EL PEDIDO', () async {
    // El servidor contesta 200 cuando reconoce un reenvío. Si eso llegara como
    // error, la cola lo reintentaría para siempre.
    await j.limpiar();
    await encolarUno();
    responder((RequestOptions o) => ok(o, 200));

    await subirLosPedidos();

    final List<PedidoEnCola> pedidos = await leerPedidosDeMaterial();
    expect(pedidos.first.estado, 'enviado');
  });

  test('3 · un 400 es DEFINITIVO y queda con su motivo a la vista', () async {
    // Una cantidad que el servidor no acepta da el mismo resultado para
    // siempre. Lo que destraba no es reintentar: es que el técnico lo VEA
    // fallado y pueda volver a pedirlo bien.
    await j.limpiar();
    await encolarUno();
    responder((RequestOptions o) => Response<dynamic>(
          requestOptions: o,
          statusCode: 400,
          data: <String, dynamic>{'detail': 'La cantidad no es un número.'},
        ));

    await subirLosPedidos();

    final List<PedidoEnCola> pedidos = await leerPedidosDeMaterial();
    expect(pedidos.first.estado, 'fallido');
    expect(pedidos.first.errorMensaje, isNotEmpty);
    expect(pedidos.first.comoVa, 'No se pudo pedir');
  });

  test('4 · un 404 también es definitivo', () async {
    await j.limpiar();
    await encolarUno();
    responder((RequestOptions o) => Response<dynamic>(
          requestOptions: o,
          statusCode: 404,
          data: <String, dynamic>{'detail': 'Ese material no existe.'},
        ));

    await subirLosPedidos();

    expect((await leerPedidosDeMaterial()).first.estado, 'fallido');
  });

  test('5 · UN CORTE DE RED NO PIERDE EL PEDIDO', () async {
    // Es el caso normal, no la excepción: se pide desde un sótano. Perderlo
    // acá sería perderlo siempre.
    await j.limpiar();
    await encolarUno();
    final Dio dio = ApiClient().dio;
    dio.interceptors.clear();
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (RequestOptions o, RequestInterceptorHandler siga) {
        if (!o.path.contains('/inventario/pedidos/')) {
          siga.resolve(Response<dynamic>(requestOptions: o, statusCode: 204));
          return;
        }
        enviadas.add(o);
        siga.reject(DioException(
          requestOptions: o,
          type: DioExceptionType.connectionError,
          message: 'sin red',
        ));
      },
    ));
    addTearDown(dio.interceptors.clear);

    await subirLosPedidos();

    final List<PedidoEnCola> pedidos = await leerPedidosDeMaterial();
    expect(pedidos, hasLength(1));
    expect(pedidos.first.estado, 'pendiente',
        reason: 'un corte de red no cierra el pedido');
  });

  test('6 · un pedido ya enviado NO se manda de nuevo', () async {
    await j.limpiar();
    await encolarUno();
    responder((RequestOptions o) => ok(o, 201));

    await subirLosPedidos();
    await subirLosPedidos();

    expect(enviadas, hasLength(1),
        reason: 'el segundo ciclo no tiene nada que subir');
  });

  test('7 · sin pedidos no se llama al servidor', () async {
    // El contrapeso: un procesador que llama igual con la cola vacía gasta una
    // petición por ciclo de sincronización, todo el día.
    await j.limpiar();
    responder((RequestOptions o) => ok(o, 201));

    await subirLosPedidos();

    expect(enviadas, isEmpty);
  });

  test('8 · dos pedidos distintos suben los dos', () async {
    await j.limpiar();
    await encolarUno(id: 'p1', cantidad: '20');
    await encolarUno(id: 'p2', cantidad: '5');
    responder((RequestOptions o) => ok(o, 201));

    await subirLosPedidos();

    expect(enviadas, hasLength(2));
    final Set<Object?> claves = <Object?>{
      for (final RequestOptions o in enviadas)
        (o.data as Map<String, dynamic>)['idempotency_key'],
    };
    expect(claves, <String>{'p1', 'p2'});
  });

  test('9 · un pedido que falla NO frena al que viene detrás', () async {
    // Si el `catch` estuviera afuera del bucle, el primer 400 dejaría al
    // segundo pedido sin intentar — y nadie lo notaría, porque el primero sí
    // muestra su error.
    await j.limpiar();
    await encolarUno(id: 'malo', cantidad: '20');
    await encolarUno(id: 'bueno', cantidad: '5');
    responder((RequestOptions o) {
      final Map<String, dynamic> cuerpo = o.data as Map<String, dynamic>;
      if (cuerpo['idempotency_key'] == 'malo') {
        return Response<dynamic>(
          requestOptions: o,
          statusCode: 400,
          data: <String, dynamic>{'detail': 'no'},
        );
      }
      return ok(o, 201);
    });

    await subirLosPedidos();

    expect(enviadas, hasLength(2));
    final LocalDatabase db = LocalDatabase();
    final base = await db.database;
    final List<Map<String, Object?>> filas =
        await base.query('cola_pedidos_material', orderBy: 'id');
    final Map<Object?, Object?> porId = <Object?, Object?>{
      for (final Map<String, Object?> f in filas) f['id']: f['estado'],
    };
    expect(porId['bueno'], 'enviado');
    expect(porId['malo'], 'fallido');
  });
}
