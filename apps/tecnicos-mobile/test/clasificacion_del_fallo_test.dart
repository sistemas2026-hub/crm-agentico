import 'dart:typed_data';

import 'package:campo/core/api/api_client.dart';
import 'package:campo/core/sync/sync_presentacion.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// LA CLASIFICACIÓN, CONTRA EL SERVICIO REAL  --  06/11/2026
///
/// POR QUÉ ESTE ARCHIVO NECESITABA ESTA PARTE. Las pruebas de arriba arman el
/// `SyncSummary` a mano: miden los TEXTOS, que es lo que el técnico lee, pero
/// nunca ejercitan a quién decide si el fallo fue de red o del servidor. La
/// mutación lo cazó: volver `sinRed = fallo` —el código viejo, el del reclamo
/// original— SOBREVIVÍA a la suite entera. Una guarda que no mata la mutación
/// que la contradice no protege nada.
///
/// Acá la decisión se mide donde vive, con el cliente real y un servidor
/// simulado debajo de Dio.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('clasificacion_del_fallo.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  tearDown(pumpEventQueue);
  tearDownAll(j.cerrarTodo);

  late _ServidorFalso servidor;

  setUp(() {
    servidor = _ServidorFalso();
    ApiClient().dio.httpClientAdapter = servidor;
    ApiClient.crearDioDeRenovacion = (String base) =>
        Dio(BaseOptions(baseUrl: base))..httpClientAdapter = servidor;
    //  Con red: es el caso del reclamo —«sale sin internet teniendo
    //  internet»— y el único donde las dos clasificaciones difieren.
    SyncQueueService().anotarRed(true);
  });

  test('EL DEFECTO: el servidor falla con red y NO se dice «sin conexión»',
      () async {
    await j.limpiar();
    servidor.trabajos = (RequestOptions o) =>
        ResponseBody.fromString('', 500, headers: <String, List<String>>{});

    await SyncQueueService().procesarCola();
    final r = SyncQueueService().lastSummary;

    expect(r?.falloDelServidor, isTrue,
        reason: 'un 500 con señal tiene que decirse como falla del servidor');
    expect(r?.hasConnectionError, isFalse,
        reason: 'esto es exactamente «sin internet teniendo internet»');
    expect(SyncPresentacion.detalle(r), isNot(contains('sin conexión')));
  });

  test('y sin red, el MISMO fallo sí es «sin conexión»', () async {
    await j.limpiar();
    SyncQueueService().anotarRed(false);
    servidor.trabajos = (RequestOptions o) =>
        ResponseBody.fromString('', 500, headers: <String, List<String>>{});

    await SyncQueueService().procesarCola();
    final r = SyncQueueService().lastSummary;

    expect(r?.hasConnectionError, isTrue);
    expect(r?.falloDelServidor, isFalse);
  });

  test('y cuando el servidor contesta bien, no se inventa ningún fallo',
      () async {
    await j.limpiar();
    servidor.trabajos = (_) => ResponseBody.fromString(
          '{"results": []}', 200,
          headers: <String, List<String>>{
            'content-type': <String>['application/json'],
          },
        );

    await SyncQueueService().procesarCola();
    final r = SyncQueueService().lastSummary;

    expect(r?.hasConnectionError, isFalse);
    expect(r?.falloDelServidor, isFalse);
  });
}

class _ServidorFalso implements HttpClientAdapter {
  ResponseBody Function(RequestOptions o) trabajos = (_) =>
      ResponseBody.fromString('{"results": []}', 200,
          headers: <String, List<String>>{
            'content-type': <String>['application/json'],
          });

  @override
  Future<ResponseBody> fetch(
    RequestOptions o,
    Stream<Uint8List>? cuerpo,
    Future<void>? cancelar,
  ) async {
    if (o.path.endsWith('/api/campo/trabajos/')) return trabajos(o);
    return ResponseBody.fromString('', 204);
  }

  @override
  void close({bool force = false}) {}
}
