import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:campo/core/ubicacion/compartir_ubicacion.dart';

/// COMPARTIR LA UBICACIÓN (31/10/2026).
///
/// Lo que se mide es la CONDUCTA del servicio, no que la clase exista: que
/// comparte SOLA sin que nadie toque nada, que lo que el tecnico apaga se
/// recuerda, que lo que apaga el SERVIDOR no --manana corresponde-- y que lo
/// que no se pudo enviar no se encola.
///
/// El permiso y la lectura del GPS son del sistema operativo y no entran acá:
/// esta prueba corre sin teléfono. Por eso el servicio recibe el envío por
/// parámetro — lo que se prueba es la decisión, no el plugin.
Position _posicion() => Position(
      latitude: 10.9185,
      longitude: -74.7668,
      timestamp: DateTime.utc(2026, 10, 31, 16, 0),
      accuracy: 8,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: 0,
      headingAccuracy: 0,
      speed: 0,
      speedAccuracy: 0,
    );

void main() {
  group('compartir la ubicación', () {
    test('comparte SOLA al abrir la app, sin que nadie toque nada', () async {
      //  DECISIÓN DEL USUARIO (02/11/2026): «es mejor que el técnico no tenga
      //  que estar presionando un botón». Un técnico que tiene que acordarse
      //  de prender algo cada mañana no lo prende, y el mapa miente por
      //  omisión.
      var envios = 0;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerApagada: () async => false,
        guardarApagada: (_) async {},
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.alArrancar();

      expect(s.encendido, isTrue, reason: 'nadie la prendió: arrancó sola');
      expect(envios, 1, reason: 'y ya mandó la primera');
      expect(s.estado.value, EstadoDeUbicacion.compartiendo);
      s.soltar();
    });

    test('lo que el técnico apagó NO vuelve a encenderse solo', () async {
      var envios = 0;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerApagada: () async => true,
        guardarApagada: (_) async {},
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.alArrancar();

      expect(s.encendido, isFalse);
      expect(envios, 0, reason: 'ni una posición de quien la apagó');
      expect(s.estado.value, EstadoDeUbicacion.apagado);
      s.soltar();
    });

    test('sin permiso no comparte, y lo dice', () async {
      var envios = 0;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerApagada: () async => false,
        guardarApagada: (_) async {},
        cada: const Duration(milliseconds: 20),
      );
      s.permisoDePrueba = false;
      s.posicionDePrueba = _posicion;

      final prendio = await s.encender();
      await Future<void>.delayed(const Duration(milliseconds: 60));

      expect(prendio, isFalse);
      expect(s.encendido, isFalse);
      expect(envios, 0, reason: 'sin permiso no sale ni una posición');
      expect(s.estado.value, EstadoDeUbicacion.sinPermiso);
      s.soltar();
    });

    test('un rechazo del servidor la APAGA por hoy, y NO lo recuerda', () async {
      var envios = 0;
      bool? guardado;
      final s = CompartirUbicacion(
        //  `false` = el servidor dijo que no corresponde (fuera de jornada o
        //  de horario).
        enviar: (_, __) async {
          envios++;
          return false;
        },
        leerApagada: () async => false,
        guardarApagada: (v) async => guardado = v,
        cada: const Duration(milliseconds: 20),
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.encender(pedirPermiso: false);
      await Future<void>.delayed(const Duration(milliseconds: 80));

      expect(s.encendido, isFalse, reason: 'se para solo');
      expect(s.estado.value, EstadoDeUbicacion.fueraDeJornada);
      expect(envios, 1, reason: 'no insiste contra una puerta cerrada');
      //  LO QUE APAGA EL SERVIDOR NO SE RECUERDA: mañana dentro del horario
      //  sí corresponde, y el técnico no tiene por qué volver a prenderla.
      //  `false` es lo que escribió `encender`; nunca `true`.
      expect(guardado, isNot(true),
          reason: 'mañana a las siete tiene que arrancar sola otra vez');
      s.soltar();
    });

    test('sin señal NO se encola: la próxima dice dónde está de verdad',
        () async {
      final enviadas = <Position>[];
      final s = CompartirUbicacion(
        enviar: (p, __) async {
          enviadas.add(p);
          return true;
        },
        leerApagada: () async => false,
        guardarApagada: (_) async {},
        //  El reloj no llega a sonar: cada envío de esta prueba lo dispara
        //  ella, para contar exactamente y no medir la frecuencia del timer.
        cada: const Duration(hours: 1),
      );
      //  Primero no hay señal, después sí.
      var hay = false;
      s.permisoDePrueba = true;
      s.posicionDePrueba = () => hay ? _posicion() : null;

      await s.encender(pedirPermiso: false);

      expect(enviadas, isEmpty, reason: 'sin señal no sale nada');
      expect(s.estado.value, EstadoDeUbicacion.sinSenal);

      hay = true;
      await s.encender(pedirPermiso: false);

      //  LA PRUEBA DEL NO-ENCOLADO: si la que no se pudo mandar se hubiera
      //  guardado, este segundo intento habría sacado DOS --la vieja y la
      //  nueva--. Sale una: la de ahora.
      expect(enviadas.length, 1, reason: 'no se acumuló la que no se pudo mandar');
      expect(s.estado.value, EstadoDeUbicacion.compartiendo);
      s.soltar();
    });

    test('apagarla corta el envío y queda recordado', () async {
      var envios = 0;
      var guardado = false;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerApagada: () async => false,
        guardarApagada: (v) async => guardado = v,
        cada: const Duration(milliseconds: 20),
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.encender(pedirPermiso: false);
      await s.apagar();
      final cuantos = envios;
      await Future<void>.delayed(const Duration(milliseconds: 80));

      expect(envios, cuantos, reason: 'después de apagar no sale ni una más');
      expect(guardado, isTrue, reason: 'lo que apaga el técnico se recuerda');
      expect(s.estado.value, EstadoDeUbicacion.apagado);
      s.soltar();
    });

    test('cada estado tiene un texto, y ninguno muestra una coordenada', () {
      for (final e in EstadoDeUbicacion.values) {
        final t = textoDeUbicacion(e);
        expect(t, isNotEmpty);
        expect(RegExp(r'-?\d+\.\d{3,}').hasMatch(t), isFalse,
            reason: 'al técnico no le sirve ver sus grados');
      }
    });
  });
}
