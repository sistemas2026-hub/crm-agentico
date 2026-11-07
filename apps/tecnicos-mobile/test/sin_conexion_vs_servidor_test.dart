// ignore_for_file: avoid_print
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:campo/core/sync/sync_presentacion.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/widgets/dexter_sync_badge.dart';

/// «SIN INTERNET TENIENDO INTERNET»  --  06/11/2026
///
/// Reportado por el usuario: «falla al mandar como si no mandara, sale sin
/// internet teniendo internet».
///
/// La causa estaba en una sola línea: `hasConnectionError` se calculaba como
/// `_currentStatus == SyncStatus.error`, así que CUALQUIER fallo se escribía
/// «Sin conexión». Una sesión vencida, un 500 del servidor o un cuerpo vacío
/// salían idénticos a estar sin señal — y el técnico, mirando la barra de
/// señal llena, dejaba de creerle a la pastilla.
///
/// Son dos estados con salidas OPUESTAS: sin red, esperar alcanza; con red y
/// el servidor caído, esperar no arregla nada y hay que avisar. Acá se
/// afirma sobre el TEXTO que el técnico lee, que es lo único que decide qué
/// hace.
SyncSummary resumen({
  required bool sinRed,
  required bool falloServidor,
  int pendientes = 0,
}) =>
    SyncSummary(
      status: (sinRed || falloServidor) ? SyncStatus.error : SyncStatus.success,
      isSyncing: false,
      hasConnectionError: sinRed,
      falloDelServidor: falloServidor,
      mutacionesPendientes: pendientes,
      mutacionesConflicto: 0,
      evidenciasPendientes: 0,
      datosDirty: 0,
    );

void main() {
  final ahora = DateTime(2026, 11, 6, 20, 0);

  group('el fallo del servidor no se disfraza de falta de señal', () {
    test('EL DEFECTO: con red y fallando, no dice «sin conexión»', () {
      final r = resumen(sinRed: false, falloServidor: true, pendientes: 3);

      final detalle = SyncPresentacion.detalle(r);
      expect(detalle, isNot(contains('sin conexión')),
          reason: 'el técnico mira la barra de señal llena y deja de creerle');
      expect(detalle, contains('servidor'));
    });

    test('y la franja dice qué hacer, porque esperar no lo arregla', () {
      final r = resumen(sinRed: false, falloServidor: true, pendientes: 2);
      final frase = SyncPresentacion.fraseFranja(r, ahora: ahora);

      expect(frase, contains('señal'));
      expect(frase, contains('NOC'),
          reason: 'sin decir a quién avisar, el técnico espera de gusto');
      expect(frase, isNot(contains('al volver la conexión')));
    });

    test('sin pendientes también lo dice', () {
      final r = resumen(sinRed: false, falloServidor: true);
      expect(SyncPresentacion.detalle(r), contains('servidor'));
      expect(SyncPresentacion.fraseFranja(r, ahora: ahora), contains('NOC'));
    });
  });

  group('sin red de verdad sigue diciendo sin conexión', () {
    //  EL CONTROL. Es la mitad que no se puede romper al arreglar la otra:
    //  sin señal, «el servidor falla» sería igual de mentiroso al revés, y
    //  mandaría al técnico a llamar al NOC por un túnel sin cobertura.
    test('con pendientes', () {
      final r = resumen(sinRed: true, falloServidor: false, pendientes: 4);
      expect(SyncPresentacion.detalle(r), contains('sin conexión'));
      expect(SyncPresentacion.fraseFranja(r, ahora: ahora),
          contains('al volver la conexión'));
    });

    test('sin pendientes', () {
      final r = resumen(sinRed: true, falloServidor: false);
      expect(SyncPresentacion.detalle(r), 'Sin conexión');
      expect(SyncPresentacion.fraseFranja(r, ahora: ahora),
          contains('Sin conexión'));
    });
  });

  group('todo bien se sigue viendo como todo bien', () {
    test('sin fallos no aparece ninguno de los dos avisos', () {
      final r = resumen(sinRed: false, falloServidor: false);
      expect(SyncPresentacion.detalle(r), isNull);
      expect(SyncPresentacion.fraseFranja(r, ahora: ahora),
          contains('Todo sincronizado'));
      expect(SyncPresentacion.puedeSincronizarAhora(r), isFalse);
    });

    test('con pendientes y sin fallo, no se inventa un problema', () {
      final r = resumen(sinRed: false, falloServidor: false, pendientes: 2);
      final detalle = SyncPresentacion.detalle(r);
      expect(detalle, '2 en cola');
      expect(detalle, isNot(contains('servidor')));
      expect(detalle, isNot(contains('conexión')));
    });
  });

  group('los dos estados se ven distintos', () {
    //  Que los textos existan no alcanza: si los dos se dibujaran iguales,
    //  partirlos en dos no habría servido de nada. Es la misma lección que
    //  dejó «Pendiente · cola: 3» cortado a 150 px.
    test('misma cola, distinto motivo, distinto texto', () {
      final sin = resumen(sinRed: true, falloServidor: false, pendientes: 3);
      final mal = resumen(sinRed: false, falloServidor: true, pendientes: 3);

      expect(SyncPresentacion.detalle(sin),
          isNot(SyncPresentacion.detalle(mal)));
      expect(SyncPresentacion.fraseFranja(sin, ahora: ahora),
          isNot(SyncPresentacion.fraseFranja(mal, ahora: ahora)));
    });

    test('y el fallo del servidor pide atención, no paciencia', () {
      final mal = resumen(sinRed: false, falloServidor: true);
      final sin = resumen(sinRed: true, falloServidor: false);

      expect(SyncPresentacion.estado(mal), DexterSyncStatus.error);
      expect(SyncPresentacion.estado(sin), DexterSyncStatus.pendiente);
    });
  });

  group('qué cuenta como fallo de red', () {
    //  LO QUE ENSEÑO LA GUARDA DEL 28/10. Clasificar solo por
    //  `connectivity_plus` estaba mal: ese paquete contesta si hay una
    //  interfaz LEVANTADA, no si hay salida. El wifi del barrio con el router
    //  sin internet da «hay red» y ningún pedido llega. Lo que dice el error
    //  mide la salida, así que manda.
    test('un corte de conexión lo es, diga lo que diga el teléfono', () {
      for (final tipo in <DioExceptionType>[
        DioExceptionType.connectionError,
        DioExceptionType.connectionTimeout,
        DioExceptionType.sendTimeout,
        DioExceptionType.receiveTimeout,
      ]) {
        expect(
          SyncQueueService.esFalloDeRed(
            DioException(requestOptions: RequestOptions(path: '/x'), type: tipo),
          ),
          isTrue,
          reason: '$tipo quedó clasificado como falla del servidor',
        );
      }
    });

    test('un socket caído también', () {
      expect(
        SyncQueueService.esFalloDeRed(DioException(
          requestOptions: RequestOptions(path: '/x'),
          error: const SocketException('sin ruta'),
        )),
        isTrue,
      );
    });

    //  EL CONTROL: el servidor contestó, mal, pero contestó. Decir «sin
    //  conexión» acá es exactamente el reclamo original.
    test('un 500 NO es fallo de red: el servidor contestó', () {
      final o = RequestOptions(path: '/x');
      expect(
        SyncQueueService.esFalloDeRed(DioException(
          requestOptions: o,
          type: DioExceptionType.badResponse,
          response: Response<void>(requestOptions: o, statusCode: 500),
        )),
        isFalse,
      );
    });

    test('ni un 401 de sesión vencida', () {
      final o = RequestOptions(path: '/x');
      expect(
        SyncQueueService.esFalloDeRed(DioException(
          requestOptions: o,
          type: DioExceptionType.badResponse,
          response: Response<void>(requestOptions: o, statusCode: 401),
        )),
        isFalse,
      );
    });

    test('ni un error que no viene de Dio', () {
      expect(SyncQueueService.esFalloDeRed(StateError('x')), isFalse);
    });
  });
}

