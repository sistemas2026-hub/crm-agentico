import 'package:campo/core/api/api_client.dart';
import 'package:campo/core/api/api_endpoints.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// LA NOVEDAD SUBE CON LA COLA (30/10/2026, novedad-de-cuadrilla.md): sin
/// señal queda avisada en el teléfono y sube cuando haya, con la clave de la
/// fila — un reintento no la duplica —, y su «Ya seguí» sube aparte.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('subir_novedades.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  tearDownAll(j.cerrarTodo);

  late List<RequestOptions> enviadas;

  void responder(int Function(RequestOptions) codigo) {
    final Dio dio = ApiClient().dio;
    dio.interceptors.clear();
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (RequestOptions o, RequestInterceptorHandler siga) {
        if (!o.path.contains('/novedades/')) {
          siga.resolve(Response<dynamic>(requestOptions: o, statusCode: 204));
          return;
        }
        enviadas.add(o);
        final Response<dynamic> r = Response<dynamic>(
          requestOptions: o,
          statusCode: codigo(o),
          data: <String, dynamic>{'id': 'srv-1', 'vigente': true},
        );
        if (r.statusCode! >= 400) {
          siga.reject(DioException(
              requestOptions: o, response: r, type: DioExceptionType.badResponse));
          return;
        }
        siga.resolve(r);
      },
    ));
    addTearDown(dio.interceptors.clear);
  }

  setUp(() => enviadas = <RequestOptions>[]);

  Future<void> encolar(String id) => j.db.encolarNovedad(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
        id: id,
        tipo: 'llanta',
        afecta: 'resto_del_dia',
        texto: 'en la autopista',
        avisadaEn: '2026-10-30T15:00:00.000Z',
      );

  Future<Map<String, dynamic>> fila() async => (await j.db.leerNovedades(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      ))
          .single;

  test('1 · sube con la clave de la fila en Idempotency-Key, y guarda el id del servidor',
      () async {
    await j.limpiar();
    await encolar('clave-de-la-fila');
    responder((_) => 201);

    await SyncQueueService().procesarCola();

    expect(enviadas, hasLength(1));
    expect(enviadas.single.path, ApiEndpoints.novedades);
    expect(enviadas.single.headers['Idempotency-Key'], 'clave-de-la-fila');
    final Map<String, dynamic> cuerpo = enviadas.single.data as Map<String, dynamic>;
    expect((cuerpo['tipo'], cuerpo['afecta'], cuerpo['texto']),
        ('llanta', 'resto_del_dia', 'en la autopista'));
    final Map<String, dynamic> f = await fila();
    expect((f['estado'], f['servidor_id']), ('enviada', 'srv-1'));

    enviadas.clear();
    await SyncQueueService().procesarCola();
    expect(enviadas, isEmpty, reason: 'subida, no se vuelve a mandar');
  });

  test('2 · «Ya seguí» sube aparte, al id del servidor', () async {
    await j.limpiar();
    await encolar('n-2');
    responder((_) => 201);
    await SyncQueueService().procesarCola();
    await j.db.resolverNovedad(
        id: 'n-2', orgId: JornadaDePrueba.org, profileId: JornadaDePrueba.perfil);
    enviadas.clear();

    await SyncQueueService().procesarCola();

    expect(enviadas.map((RequestOptions o) => o.path),
        <String>[ApiEndpoints.resolverNovedad('srv-1')]);
    expect((await fila())['resuelta_subida'], 1);
  });

  test('3 · un 400 es definitivo: queda fallida y a la vista, no se reintenta', () async {
    await j.limpiar();
    await encolar('n-3');
    responder((_) => 400);

    await SyncQueueService().procesarCola();
    enviadas.clear();
    await SyncQueueService().procesarCola();

    expect((await fila())['estado'], 'fallida');
    expect(enviadas, isEmpty);
  });
}
