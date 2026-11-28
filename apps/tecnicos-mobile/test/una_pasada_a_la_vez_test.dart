import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:campo/core/sync/una_pasada_a_la_vez.dart';

/// «NO SALEN ENSEGUIDA APENAS SE REPORTA»  --  06/11/2026
///
/// La sincronización ya se disparaba al guardar. Lo que se perdía era el
/// disparo que llegaba MIENTRAS otra pasada corría: `if (_isSyncing) return;`
/// lo tiraba en silencio, y lo recién escrito esperaba hasta dos minutos al
/// reloj de `EnvioAutomatico`.
///
/// Se afirma sobre el EFECTO —cuántas veces corrió la pasada— y no sobre la
/// bandera: una bandera que se pone y nadie lee pasaría igual.
void main() {
  group('una pasada por vez', () {
    test('dos pedidos a la vez no corren dos pasadas encimadas', () async {
      final turno = UnaPasadaALaVez();
      var corriendoAhora = 0;
      var maximoSimultaneo = 0;
      final puerta = Completer<void>();

      Future<void> pasada() async {
        corriendoAhora++;
        if (corriendoAhora > maximoSimultaneo) {
          maximoSimultaneo = corriendoAhora;
        }
        await puerta.future;
        corriendoAhora--;
      }

      final primera = turno.correr(pasada);
      await turno.correr(pasada); // llega mientras la otra corre
      puerta.complete();
      await primera;
      await Future<void>.delayed(Duration.zero);

      expect(maximoSimultaneo, 1, reason: 'se encimaron dos pasadas');
    });

    //  EL DEFECTO. Antes esto daba 1: el segundo pedido se descartaba y lo
    //  recién guardado esperaba al reloj.
    test('EL DEFECTO: el pedido que llega durante la pasada se corre después',
        () async {
      final turno = UnaPasadaALaVez();
      var veces = 0;
      final puerta = Completer<void>();

      Future<void> pasada() async {
        veces++;
        if (veces == 1) await puerta.future;
      }

      final primera = turno.correr(pasada);
      await turno.correr(pasada);
      puerta.complete();
      await primera;
      await Future<void>.delayed(Duration.zero);

      expect(veces, 2, reason: 'el disparo que llegó durante la pasada se perdió');
    });

    test('diez pedidos durante la misma pasada son UNA vuelta más', () async {
      final turno = UnaPasadaALaVez();
      var veces = 0;
      final puerta = Completer<void>();

      Future<void> pasada() async {
        veces++;
        if (veces == 1) await puerta.future;
      }

      final primera = turno.correr(pasada);
      for (var i = 0; i < 10; i++) {
        await turno.correr(pasada);
      }
      puerta.complete();
      await primera;
      await Future<void>.delayed(Duration.zero);

      expect(veces, 2, reason: 'encadenó una vuelta por pedido');
    });

    test('sin nadie encima, corre una sola vez', () async {
      final turno = UnaPasadaALaVez();
      var veces = 0;
      await turno.correr(() async => veces++);
      await Future<void>.delayed(Duration.zero);
      expect(veces, 1);
    });

    test('dos pedidos seguidos, uno después del otro, corren los dos', () async {
      final turno = UnaPasadaALaVez();
      var veces = 0;
      await turno.correr(() async => veces++);
      await turno.correr(() async => veces++);
      expect(veces, 2);
    });
  });

  group('un fallo no se come lo que quedó pendiente', () {
    test('la pasada que falla sube el error a quien la pidió', () async {
      final turno = UnaPasadaALaVez();
      await expectLater(
        turno.correr(() async => throw StateError('se cayó')),
        throwsStateError,
      );
    });

    test('y la vuelta pendiente se corre igual', () async {
      //  Lo que el técnico guardó mientras tanto no tiene la culpa de que
      //  esta pasada fallara. Si el fallo se llevara el pedido anotado, el
      //  caso que más necesita reintentar sería justo el que no reintenta.
      final turno = UnaPasadaALaVez();
      var veces = 0;
      final puerta = Completer<void>();

      Future<void> pasada() async {
        veces++;
        if (veces == 1) {
          await puerta.future;
          throw StateError('se cayó');
        }
      }

      final primera = turno.correr(pasada);
      await turno.correr(pasada);
      puerta.complete();
      await expectLater(primera, throwsStateError);
      await Future<void>.delayed(Duration.zero);

      expect(veces, 2, reason: 'el fallo se llevó puesto el pedido anotado');
    });

    test('y después del fallo el turno queda libre, no trabado', () async {
      final turno = UnaPasadaALaVez();
      await expectLater(
        turno.correr(() async => throw StateError('x')),
        throwsStateError,
      );
      expect(turno.corriendo, isFalse, reason: 'quedó trabado para siempre');

      var corrio = false;
      await turno.correr(() async => corrio = true);
      expect(corrio, isTrue);
    });
  });
}
