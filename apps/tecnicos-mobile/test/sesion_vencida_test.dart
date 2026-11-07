import 'dart:convert';
import 'dart:typed_data';

import 'package:campo/core/api/api_client.dart';
import 'package:campo/core/api/api_endpoints.dart';
import 'package:campo/core/sync/sync_presentacion.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// LA SESIÓN MUERTA Y EL «SINCRONIZADO» QUE NO LO ERA (28/10/2026).
///
/// Medido en producción: un técnico con la app abierta y «sincronizado» en
/// pantalla, su última conexión con el servidor horas atrás, y la orden que le
/// asignaron sin llegar. Tres caminos llevaban ahí, y se prueban sobre el
/// cliente REAL (su interceptor), con el servidor simulado debajo de Dio:
///
///   1. La renovación rechazada no avisaba nada: la app seguía adentro.
///   2. Un 403 de permiso después de renovar BORRABA la sesión en silencio.
///   3. La sincronización marcaba éxito aunque el servidor no contestara.
///
/// Y lo que NO tiene que pasar: salir de la app por falta de señal o porque el
/// servidor se está desplegando (contesta 404 o 5xx un rato).
void main() {
  final JornadaDePrueba j = JornadaDePrueba('sesion_vencida.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  tearDown(pumpEventQueue);
  tearDownAll(j.cerrarTodo);

  late _Servidor servidor;
  late int avisos;

  setUp(() {
    j.sesion.poner('dexter_refresh_token', 'refresh-viejo');
    servidor = _Servidor();
    ApiClient().dio.httpClientAdapter = servidor;
    ApiClient.crearDioDeRenovacion =
        (String base) => Dio(BaseOptions(baseUrl: base))..httpClientAdapter = servidor;
    avisos = 0;
    final s = ApiClient.sesionVencida.listen((_) => avisos++);
    addTearDown(s.cancel);
  });

  Future<int?> pedir() async {
    try {
      final r = await ApiClient().get<dynamic>(ApiEndpoints.trabajos);
      return r.statusCode;
    } on DioException catch (e) {
      return e.response?.statusCode ?? -1;
    }
  }

  group('renovar la sesión', () {
    test('1 · el servidor la rechaza: se avisa, y no la borra el cliente', () async {
      servidor.trabajos = (_) => _json(401, <String, dynamic>{});
      servidor.renovar = (_) => _json(401, <String, dynamic>{'error': 'vencido'});

      expect(await pedir(), 401);
      await pumpEventQueue();

      expect(avisos, 1);
      //  Salir le toca al contenedor, por el camino que conserva lo pendiente.
      expect(j.sesion.valor('dexter_profile_id'), JornadaDePrueba.perfil);
    });

    test('2 · sin llave para renovar también es un rechazo', () async {
      j.sesion.poner('dexter_refresh_token', null);
      servidor.trabajos = (_) => _json(401, <String, dynamic>{});

      await pedir();
      await pumpEventQueue();

      expect(avisos, 1);
    });

    for (final int estado in <int>[404, 500, 502, 503]) {
      test('3 · un $estado al renovar (desplegando) no saca a nadie', () async {
        servidor.trabajos = (_) => _json(401, <String, dynamic>{});
        servidor.renovar = (_) => _json(estado, <String, dynamic>{});

        await pedir();
        await pumpEventQueue();

        expect(avisos, 0);
        expect(j.sesion.valor('dexter_access_token'), 'token-de-prueba');
      });
    }

    test('4 · sin señal al renovar no saca a nadie', () async {
      servidor.trabajos = (_) => _json(401, <String, dynamic>{});
      servidor.renovar = (RequestOptions o) =>
          throw DioException(requestOptions: o, type: DioExceptionType.connectionError);

      await pedir();
      await pumpEventQueue();

      expect(avisos, 0);
      expect(j.sesion.valor('dexter_access_token'), 'token-de-prueba');
    });

    test('5 · renovada y el reintento da 403 de permiso: la sesión NO se borra', () async {
      var llamadas = 0;
      servidor.trabajos = (_) => _json(403, <String, dynamic>{'detail': 'sin permiso'}, () => llamadas++);
      servidor.renovar = (_) => _json(200, <String, dynamic>{'access': 'nuevo', 'refresh': 'refresh-nuevo'});

      expect(await pedir(), 403);
      await pumpEventQueue();

      expect(llamadas, 2);                       // el pedido y su reintento
      expect(avisos, 0);
      expect(j.sesion.valor('dexter_access_token'), 'nuevo');
      expect(j.sesion.valor('dexter_refresh_token'), 'refresh-nuevo');
      expect(j.sesion.valor('dexter_profile_id'), JornadaDePrueba.perfil);
    });

    test('6 · renovada y el reintento contesta: el pedido sale bien', () async {
      servidor.trabajos = (RequestOptions o) =>
          o.headers['Authorization'] == 'Bearer nuevo'
              ? _json(200, <String, dynamic>{'results': <Object>[]})
              : _json(401, <String, dynamic>{});
      servidor.renovar = (_) => _json(200, <String, dynamic>{'access': 'nuevo', 'refresh': 'r2'});

      expect(await pedir(), 200);
      expect(avisos, 0);
    });
  });

  group('«sincronizado» solo si el servidor contestó', () {
    test('7 · sin respuesta del listado: «sin conexión», no «sincronizado»', () async {
      await j.limpiar();
      servidor.trabajos = (RequestOptions o) =>
          throw DioException(requestOptions: o, type: DioExceptionType.connectionError);

      await SyncQueueService().procesarCola();

      final resumen = SyncQueueService().lastSummary;
      expect(resumen?.hasConnectionError, isTrue);
      expect(SyncPresentacion.estado(resumen), isNot(SyncPresentacion.estado(_sano)));
      expect(SyncPresentacion.detalle(resumen), 'Sin conexión');
    });

    test('8 · con el listado contestado: sincronizado', () async {
      await j.limpiar();
      servidor.trabajos = (_) => _json(200, <String, dynamic>{'results': <Object>[]});

      await SyncQueueService().procesarCola();

      final resumen = SyncQueueService().lastSummary;
      expect(resumen?.hasConnectionError, isFalse);
      expect(SyncPresentacion.estado(resumen), SyncPresentacion.estado(_sano));
    });

    test('9 · sin sesión en el teléfono: se avisa a quien contiene la app', () async {
      j.sesion.poner('dexter_profile_id', null);

      await SyncQueueService().procesarCola();
      await pumpEventQueue();

      expect(avisos, 1);
    });
  });
}

/// Un resumen sin nada pendiente y con el servidor contestando.
const SyncSummary _sano = SyncSummary(
  status: SyncStatus.success,
  isSyncing: false,
  hasConnectionError: false,
  mutacionesPendientes: 0,
  mutacionesConflicto: 0,
  evidenciasPendientes: 0,
  seguimientosPendientes: 0,
  datosDirty: 0,
);

ResponseBody _json(int estado, Object cuerpo, [void Function()? contar]) {
  contar?.call();
  return ResponseBody.fromString(
    jsonEncode(cuerpo),
    estado,
    headers: <String, List<String>>{
      Headers.contentTypeHeader: <String>[Headers.jsonContentType],
    },
  );
}

/// El servidor, debajo de Dio: lo que pasa por el interceptor es lo real.
class _Servidor implements HttpClientAdapter {
  ResponseBody Function(RequestOptions o) trabajos =
      (_) => _json(200, <String, dynamic>{'results': <Object>[]});
  ResponseBody Function(RequestOptions o) renovar =
      (_) => _json(200, <String, dynamic>{'access': 'nuevo', 'refresh': 'r2'});

  @override
  Future<ResponseBody> fetch(
    RequestOptions o,
    Stream<Uint8List>? cuerpo,
    Future<void>? cancelar,
  ) async {
    if (o.path.contains('/api/auth/refresh-token/')) return renovar(o);
    if (o.path.endsWith('/api/campo/trabajos/')) return trabajos(o);
    //  Todo lo demás de la sincronización (detalle, colas, kit, jornada): vacío.
    return ResponseBody.fromString('', 204);
  }

  @override
  void close({bool force = false}) {}
}
