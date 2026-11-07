import 'package:campo/core/api/api_client.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// EL TELÉFONO SUELTA UNA ORDEN QUE YA NO ES DEL TÉCNICO  --  27/10/2026.
///
/// Hueco heredado de la fase 2.2 para la 3.1
/// (SPEC/objetivos/supervisor-arma-la-jornada.md): la descarga solo agregaba
/// y actualizaba, así que una orden que el reparto pasaba a otra cuadrilla se
/// quedaba en este teléfono —con el nombre, la dirección y el teléfono del
/// cliente— y el técnico la seguía viendo como suya.
///
/// LO QUE SE AFIRMA
/// ----------------
/// 1. Con el listado COMPLETO, la que ya no viene se suelta con sus copias
///    (materiales, historial, seguimiento), y la que viene se queda.
/// 2. Lo que tiene algo SIN SUBIR no se suelta, en cada una de las seis colas
///    que guardan un `orden_id`; con la misma fila ya subida, sí.
/// 3. Un CORTE de red a mitad del listado no suelta nada.
/// 4. El TOPE de páginas no suelta nada: «no vino» no es «ya no es suya».
/// 5. La copia de OTRA persona del mismo teléfono no se toca, y sus copias
///    por orden se conservan.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('soltar_reasignadas.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  //  Antes de desenchufar la sesión (los tearDown corren al revés): soltar
  //  avisa un cambio de la base, y quien escucha ese aviso lee la sesión por
  //  el canal. Si el aviso llega con la sesión ya desenchufada, el error cae en
  //  la prueba que creó al que escucha, no en la que lo disparó.
  tearDown(pumpEventQueue);
  tearDownAll(j.cerrarTodo);

  const String org = JornadaDePrueba.org;
  const String yo = JornadaDePrueba.perfil;
  const String otra = JornadaDePrueba.otraPersona;
  const int ahora = 1793116800000;

  Map<String, dynamic> orden(String id, int numero) => <String, dynamic>{
        'id': id,
        'numero': numero,
        'estado': 'asignada',
        'cliente_nombre': 'Zoraida Clientela',
        'direccion': 'Cra 45 #12-88',
        'telefono': '3001234567',
        'revision': 1,
        'tipo': <String, dynamic>{
          'nombre': 'Soporte',
          'codigo': 'soporte',
          'schema_version': 1,
        },
      };

  Future<void> sembrar(String id, int numero, {String perfil = yo}) =>
      j.db.upsertOrden(orgId: org, profileId: perfil, ordenData: orden(id, numero));

  Future<void> sembrarCopias(String id) async {
    final base = await j.db.database;
    await base.insert('local_materiales_orden', <String, Object?>{
      'orden_id': id, 'org_id': org, 'materiales_json': '[]',
      'sincronizado_en': ahora,
    });
    await base.insert('local_historial_servicio', <String, Object?>{
      'orden_id': id, 'org_id': org, 'historial_json': '[]',
      'sincronizado_en': ahora,
    });
    await base.insert('local_seguimiento', <String, Object?>{
      'orden_id': id, 'org_id': org, 'seguimiento_json': '{}',
      'sincronizado_en': ahora,
    });
  }

  Future<int> copiasDe(String id) async {
    final base = await j.db.database;
    var n = 0;
    for (final String t in const <String>[
      'local_materiales_orden',
      'local_historial_servicio',
      'local_seguimiento',
    ]) {
      n += (await base.query(t, where: 'orden_id = ?', whereArgs: <Object?>[id]))
          .length;
    }
    return n;
  }

  Future<Set<String>> enElTelefono({String perfil = yo}) async {
    final base = await j.db.database;
    final filas = await base.query(
      'local_ordenes',
      columns: <String>['id'],
      where: 'org_id = ? AND profile_id = ?',
      whereArgs: <Object?>[org, perfil],
    );
    return <String>{for (final f in filas) f['id']! as String};
  }

  Future<void> limpiarTodo() async {
    final base = await j.db.database;
    for (final String t in const <String>[
      'local_ordenes',
      'local_materiales_orden',
      'local_historial_servicio',
      'local_seguimiento',
      'cola_mutaciones',
      'local_datos_dirty',
      'cola_evidencias',
      'cola_seguimiento',
      'cola_movimientos_material',
      'cola_pedidos_material',
    ]) {
      await base.delete(t);
    }
  }

  /// El servidor: el listado lo contesta `listado` según el cursor; todo lo
  /// demás (detalle, colas, kit, jornada) un 204 vacío, que este caso no mide.
  void servidor(
    Response<dynamic> Function(RequestOptions o, String? cursor) listado,
  ) {
    final Dio dio = ApiClient().dio;
    dio.interceptors.clear();
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (RequestOptions o, RequestInterceptorHandler siga) {
        if (!o.path.endsWith('/api/campo/trabajos/')) {
          siga.resolve(Response<dynamic>(requestOptions: o, statusCode: 204));
          return;
        }
        final Response<dynamic> r =
            listado(o, o.queryParameters['cursor'] as String?);
        if ((r.statusCode ?? 0) >= 400) {
          siga.reject(DioException(
            requestOptions: o,
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

  Response<dynamic> lista(
    RequestOptions o,
    List<Map<String, dynamic>> ordenes, {
    String? siguiente,
  }) =>
      Response<dynamic>(
        requestOptions: o,
        statusCode: 200,
        data: <String, dynamic>{'results': ordenes, 'next_cursor': siguiente},
      );

  test('1 · con el listado completo suelta la reasignada y sus copias', () async {
    await limpiarTodo();
    await sembrar('ot-mia', 1);
    await sembrar('ot-movida', 2);
    await sembrarCopias('ot-movida');
    servidor((o, _) => lista(o, <Map<String, dynamic>>[orden('ot-mia', 1)]));

    await SyncQueueService().procesarCola();

    expect(await enElTelefono(), <String>{'ot-mia'});
    expect(await copiasDe('ot-movida'), 0);
  });

  /// (tabla, la fila sin subir, el estado que la da por subida o null si la
  /// tabla no tiene uno: un dato editado se borra al subir).
  final List<(String, Map<String, Object?>, String?, String)> colas =
      <(String, Map<String, Object?>, String?, String)>[
    (
      'cola_mutaciones',
      <String, Object?>{
        'id': 'm1', 'org_id': org, 'profile_id': yo, 'orden_id': 'ot-x',
        'tipo': 'marcar_en_camino', 'revision_base': 1,
        'idempotency_key': 'k1', 'estado': 'pendiente', 'created_at': ahora,
      },
      'sincronizada',
      'estado',
    ),
    (
      'local_datos_dirty',
      <String, Object?>{
        'orden_id': 'ot-x', 'org_id': org, 'profile_id': yo,
        'campo_clave': 'potencia', 'valor_json': '"-21"', 'updated_at': ahora,
      },
      null,
      '',
    ),
    (
      'cola_evidencias',
      <String, Object?>{
        'id': 'e1', 'org_id': org, 'profile_id': yo, 'orden_id': 'ot-x',
        'requisito_id': 'foto', 'archivo_path': '/no/existe.jpg',
        'sha256': '0', 'tamano_bytes': 1, 'mime_type': 'image/jpeg',
        'subida_estado': 'pendiente_registro', 'created_at': ahora,
      },
      'confirmada',
      'subida_estado',
    ),
    (
      'cola_seguimiento',
      <String, Object?>{
        'id': 's1', 'org_id': org, 'profile_id': yo, 'orden_id': 'ot-x',
        'momento': 'avance', 'respuestas_json': '{}',
        'capturado_en_dispositivo': '2026-10-27T10:00:00',
        'estado': 'pendiente', 'created_at': ahora,
      },
      'sincronizado',
      'estado',
    ),
    (
      'cola_movimientos_material',
      <String, Object?>{
        'id': 'mv1', 'org_id': org, 'profile_id': yo,
        'material_codigo': 'CON-SC-APC', 'tipo': 'consumo', 'cantidad': '1',
        'orden_id': 'ot-x', 'estado': 'pendiente',
        'ocurrido_en': '2026-10-27T10:00:00', 'created_at': ahora,
      },
      'confirmado',
      'estado',
    ),
    (
      'cola_pedidos_material',
      <String, Object?>{
        'id': 'p1', 'org_id': org, 'profile_id': yo, 'material_id': 'mat-1',
        'material_nombre': 'Conector SC/APC', 'cantidad': '20',
        'orden_id': 'ot-x', 'estado': 'pendiente', 'created_at': ahora,
      },
      'enviado',
      'estado',
    ),
  ];

  for (final (String tabla, Map<String, Object?> fila, String? subida,
      String columna) in colas) {
    test('2 · $tabla: sin subir no se suelta; subida, sí', () async {
      await limpiarTodo();
      await sembrar('ot-x', 7);
      final base = await j.db.database;
      await base.insert(tabla, fila);

      var soltadas = await j.db.soltarOrdenesQueYaNoSonMias(
        orgId: org, profileId: yo, vistas: <String>{});
      expect(soltadas, isEmpty, reason: '$tabla con algo sin subir');
      expect(await enElTelefono(), <String>{'ot-x'});

      if (subida == null) {
        await base.delete(tabla);
      } else {
        await base.update(tabla, <String, Object?>{columna: subida});
      }
      soltadas = await j.db.soltarOrdenesQueYaNoSonMias(
        orgId: org, profileId: yo, vistas: <String>{});
      expect(soltadas, <String>['ot-x'], reason: '$tabla ya subida');
    });
  }

  test('2b · una transición que el servidor dio por reasignada no la retiene',
      () async {
    await limpiarTodo();
    await sembrar('ot-x', 7);
    final base = await j.db.database;
    await base.insert('cola_mutaciones', <String, Object?>{
      'id': 'm404', 'org_id': org, 'profile_id': yo, 'orden_id': 'ot-x',
      'tipo': 'marcar_en_camino', 'revision_base': 1,
      'idempotency_key': 'k404', 'estado': 'terminal_404', 'created_at': ahora,
    });

    expect(
      await j.db.soltarOrdenesQueYaNoSonMias(
          orgId: org, profileId: yo, vistas: <String>{}),
      <String>['ot-x'],
    );
  });

  test('3 · un corte de red a mitad del listado no suelta nada', () async {
    await limpiarTodo();
    await sembrar('ot-mia', 1);
    await sembrar('ot-de-la-pagina-2', 2);
    servidor((o, cursor) => cursor == null
        ? lista(o, <Map<String, dynamic>>[orden('ot-mia', 1)], siguiente: 'c2')
        : Response<dynamic>(requestOptions: o, statusCode: 500));

    await SyncQueueService().procesarCola();

    expect(await enElTelefono(), <String>{'ot-mia', 'ot-de-la-pagina-2'});
  });

  test('4 · con el tope de páginas no suelta nada', () async {
    await limpiarTodo();
    await sembrar('ot-mia', 1);
    //  Un servidor que nunca termina de paginar.
    servidor((o, _) => lista(o, <Map<String, dynamic>>[], siguiente: 'otra'));

    await SyncQueueService().procesarCola();

    expect(await enElTelefono(), <String>{'ot-mia'});
  });

  test('5 · la copia de otra persona no se toca, ni sus copias por orden',
      () async {
    await limpiarTodo();
    await sembrar('ot-compartida', 3);
    await sembrar('ot-compartida', 3, perfil: otra);
    await sembrarCopias('ot-compartida');
    servidor((o, _) => lista(o, <Map<String, dynamic>>[]));

    await SyncQueueService().procesarCola();

    expect(await enElTelefono(), isEmpty);
    expect(await enElTelefono(perfil: otra), <String>{'ot-compartida'});
    expect(await copiasDe('ot-compartida'), 3);
  });
}
