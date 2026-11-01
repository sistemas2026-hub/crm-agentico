import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:campo/core/ubicacion/compartir_ubicacion.dart';

/// COMPARTIR LA UBICACIÓN (31/10/2026).
///
/// Lo que se mide es la CONDUCTA del servicio, no que la clase exista: que
/// nace apagado, que lo que no se pudo enviar no se encola, y que un rechazo
/// del servidor lo apaga en vez de insistir contra una puerta cerrada.
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
    test('nace apagado: nadie comparte sin haberlo prendido', () async {
      var guardado = false;
      final s = CompartirUbicacion(
        enviar: (_, __) async => true,
        leerEncendido: () async => false,
        guardarEncendido: (v) async => guardado = v,
      );
      //  CON EL PERMISO CONCEDIDO, a propósito: sin esto la prueba pasaba por
      //  accidente --el permiso fallaba en el entorno de pruebas y tapaba el
      //  encendido-- y sobrevivía a la mutación «nace encendido» (31/10/2026).
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      expect(s.encendido, isFalse);
      expect(s.estado.value, EstadoDeUbicacion.apagado);

      await s.alArrancar();

      expect(s.encendido, isFalse, reason: 'al abrir la app no se prende solo');
      expect(guardado, isFalse);
      s.soltar();
    });

    test('sin permiso no comparte, y lo dice', () async {
      var envios = 0;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerEncendido: () async => false,
        guardarEncendido: (_) async {},
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

    test('un rechazo del servidor lo APAGA, no lo pone a reintentar', () async {
      var envios = 0;
      var guardado = true;
      final s = CompartirUbicacion(
        //  `false` = el servidor dijo que no corresponde (fuera de jornada o
        //  de horario).
        enviar: (_, __) async {
          envios++;
          return false;
        },
        leerEncendido: () async => true,
        guardarEncendido: (v) async => guardado = v,
        cada: const Duration(milliseconds: 20),
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.encender(pedirPermiso: false);
      await Future<void>.delayed(const Duration(milliseconds: 80));

      expect(s.encendido, isFalse, reason: 'se para solo');
      expect(s.estado.value, EstadoDeUbicacion.fueraDeJornada);
      expect(envios, 1, reason: 'no insiste contra una puerta cerrada');
      expect(guardado, isFalse, reason: 'y no vuelve a arrancar mañana solo');
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
        leerEncendido: () async => false,
        guardarEncendido: (_) async {},
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

    test('apagarlo corta el envío y queda recordado', () async {
      var envios = 0;
      var guardado = true;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerEncendido: () async => true,
        guardarEncendido: (v) async => guardado = v,
        cada: const Duration(milliseconds: 20),
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.encender(pedirPermiso: false);
      await s.apagar();
      final cuantos = envios;
      await Future<void>.delayed(const Duration(milliseconds: 80));

      expect(envios, cuantos, reason: 'después de apagar no sale ni una más');
      expect(guardado, isFalse);
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
