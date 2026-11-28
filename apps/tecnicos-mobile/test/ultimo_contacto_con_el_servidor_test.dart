import 'package:campo/core/api/api_client.dart';
import 'package:campo/core/sync/sync_presentacion.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/tiempo/momento_leido.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';

/// ============================================================================
///  CUANDO FUE LA ULTIMA VEZ QUE EL SERVIDOR CONTESTO  (CAMPO-DATA-036)
/// ============================================================================
///
/// La cola sabia CUANTO falta por enviar y no SI alguna vez llego. Con la
/// pastilla en «Pendiente · sin conexion», el tecnico no podia distinguir
/// «hace dos minutos que no sube» de «no sube desde ayer» -- y esas dos cosas
/// se deciden distinto: la primera se espera, la segunda se reporta.
///
/// QUE AFIRMA ESTA GUARDA, Y POR QUE ASI
/// -------------------------------------
/// No que el campo exista: que **la marca se mueva en el camino de exito y NO
/// se mueva en el de fallo**. Las dos mitades hacen falta. Una prueba que solo
/// corriera el camino bueno pasaria igual si alguien escribiera la marca al
/// empezar la pasada o en el `finally` -- y entonces el dato diria que hubo
/// contacto justo cuando no lo hubo, que es la mentira que vino a tapar.
///
/// Mutaciones que esta guarda mata (medidas el 06/11/2026):
///   · mover `marcarServidorContesto` arriba del `if (!llegoAlEmpezar ...)`
///     -> rojo en «no se mueve cuando el servidor no contesto»
///   · moverla al `finally`
///     -> rojo en la misma
///   · borrar la llamada
///     -> rojo en «queda escrita cuando el servidor contesto»
///   · que `fraseFranja` escriba una hora con la marca en `null`
///     -> rojo en «sin marca no se inventa una hora»
///
/// LO QUE NO PRUEBA: que la hora que se escribe sea la correcta al segundo.
/// Se escribe `DateTime.now()` en el unico punto donde ya se decidio que el
/// servidor respondio; afirmar el instante exacto seria afirmar sobre el reloj
/// del que corre la prueba, no sobre la conducta.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('ultimo_contacto.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  tearDownAll(j.cerrarTodo);

  /// La ruta que decide si la pasada fue un exito es la descarga de ordenes
  /// (`ApiEndpoints.trabajos`), por la regla del 28/10/2026: si ninguna de las
  /// dos descargas llego, no se sabe nada nuevo. Todo lo demas contesta vacio:
  /// cada paso se traga su error y no cambia el veredicto.
  void elServidor({required bool contesta}) {
    final Dio dio = ApiClient().dio;
    dio.interceptors.clear();
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (RequestOptions o, RequestInterceptorHandler siga) {
        final bool esLaDescargaDeOrdenes = o.path.endsWith('/campo/trabajos/');
        if (esLaDescargaDeOrdenes && !contesta) {
          siga.reject(DioException(
            requestOptions: o,
            type: DioExceptionType.connectionError,
            error: 'sin señal',
          ));
          return;
        }
        if (esLaDescargaDeOrdenes) {
          siga.resolve(Response<dynamic>(
            requestOptions: o,
            statusCode: 200,
            data: <String, dynamic>{'results': <dynamic>[]},
          ));
          return;
        }
        siga.resolve(Response<dynamic>(
          requestOptions: o,
          statusCode: 200,
          data: <String, dynamic>{'results': <dynamic>[]},
        ));
      },
    ));
    addTearDown(dio.interceptors.clear);
  }

  Future<DateTime?> laMarca() => j.db.servidorContestoEn(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
      );

  group('la marca del ultimo contacto', () {
    test('queda escrita cuando el servidor contesto', () async {
      expect(await laMarca(), isNull,
          reason: 'empieza sin marca: este telefono nunca hablo');

      elServidor(contesta: true);
      await SyncQueueService().procesarCola();

      expect(await laMarca(), isNotNull,
          reason: 'el servidor contesto, asi que hubo contacto');
    });

    test('NO se mueve cuando el servidor no contesto', () async {
      //  Una marca vieja, puesta a mano: lo que se mide es que la pasada
      //  fallida la deje EXACTAMENTE donde estaba.
      final DateTime antes = DateTime(2026, 11, 5, 8, 17);
      await j.db.marcarServidorContesto(
        orgId: JornadaDePrueba.org,
        profileId: JornadaDePrueba.perfil,
        cuando: antes,
      );

      elServidor(contesta: false);
      await SyncQueueService().procesarCola();

      expect(await laMarca(), antes,
          reason: 'sin respuesta del servidor no hubo contacto nuevo; '
              'moverla afirmaria lo contrario de lo que paso');
    });

    test('el resumen de la cola la lleva hasta la pantalla', () async {
      elServidor(contesta: true);
      await SyncQueueService().procesarCola();

      final SyncSummary resumen = await SyncQueueService().refreshSyncSummary();
      expect(resumen.servidorContestoEn, isNotNull,
          reason: 'escribirla en la base y no entregarla es no haberla hecho');
    });
  });

  group('como se escribe en la franja', () {
    SyncSummary resumen({DateTime? marca, bool sinConexion = false}) =>
        SyncSummary(
          status: SyncStatus.success,
          isSyncing: false,
          hasConnectionError: sinConexion,
          mutacionesPendientes: 0,
          mutacionesConflicto: 0,
          evidenciasPendientes: 0,
          datosDirty: 0,
          servidorContestoEn: marca,
        );

    final DateTime ahora = DateTime(2026, 11, 6, 9, 30);

    test('sin marca no se inventa una hora', () {
      final String frase =
          SyncPresentacion.fraseFranja(resumen(), ahora: ahora);

      expect(frase, 'Todo sincronizado');
      //  Lo que NO puede aparecer. Sin esto, la prueba de arriba pasaria
      //  igual con un «hace un rato» puesto a mano.
      expect(frase, isNot(contains('hoy')));
      expect(frase, isNot(contains('ayer')));
      expect(frase, isNot(contains(':')));
    });

    test('con marca de hoy dice hoy, y con la de ayer dice ayer', () {
      final String deHoy = SyncPresentacion.fraseFranja(
        resumen(marca: DateTime(2026, 11, 6, 8, 17)),
        ahora: ahora,
      );
      final String deAyer = SyncPresentacion.fraseFranja(
        resumen(marca: DateTime(2026, 11, 5, 8, 17)),
        ahora: ahora,
      );

      expect(deHoy, contains('hoy 08:17'));
      expect(deAyer, contains('ayer 08:17'));
      //  Y no se leen igual: es justo la distincion que el tecnico necesita.
      expect(deHoy, isNot(deAyer));
    });

    test('sin conexion es donde mas importa, y ahi tambien aparece', () {
      final String frase = SyncPresentacion.fraseFranja(
        resumen(marca: DateTime(2026, 11, 5, 8, 17), sinConexion: true),
        ahora: ahora,
      );

      expect(frase, contains('Sin conexión'));
      expect(frase, contains('ayer 08:17'),
          reason: 'sin conexion y sin hora, dos minutos y un dia entero '
              'se ven iguales');
      expect(frase, contains('se guarda igual'),
          reason: 'la tranquilidad de que nada se pierde no se saca para '
              'hacerle lugar a la hora');
    });

    test('la zona se declara, asi que la comparacion no se corre 5 horas', () {
      //  `momento_leido.dart` existe por un error de cinco horas. La marca la
      //  pone este telefono, asi que su zona se conoce y es comparable: si
      //  alguien la pasara como ausente, dejaria de decir «hoy».
      final MomentoLeido m = MomentoLeido(
        cuando: DateTime(2026, 11, 6, 8, 17),
        zona: ZonaDelMomento.declarada,
      );
      expect(m.sePuedeComparar, isTrue);

      expect(
        SyncPresentacion.fraseFranja(
          resumen(marca: m.cuando),
          ahora: ahora,
        ),
        contains('hoy'),
      );
    });
  });
}
