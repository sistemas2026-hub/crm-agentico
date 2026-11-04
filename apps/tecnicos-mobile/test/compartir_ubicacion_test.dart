import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:campo/core/ubicacion/compartir_ubicacion.dart';

/// COMPARTIR LA UBICACIÓN (31/10/2026, rehecho el 02/11/2026).
///
/// La ubicación la enciende **el arranque de la jornada**, y la marca es la
/// FECHA en que el técnico arrancó. Lo que se mide es esa conducta, no que la
/// clase exista:
///
///   - al abrir la aplicación NO comparte sola: espera a que él arranque;
///   - una jornada de AYER no sirve: a medianoche deja de compartir sin que
///     nadie apague nada;
///   - lo que no se pudo enviar NO se encola;
///   - un rechazo del servidor para por hoy, pero no borra la jornada.
///
/// El permiso y la lectura del GPS son del sistema operativo y no entran acá:
/// esta prueba corre sin teléfono. Por eso el servicio recibe el envío, el
/// permiso y la posición por parámetro — lo que se prueba es la decisión.
Position _posicion() => Position(
      latitude: 10.9185,
      longitude: -74.7668,
      timestamp: DateTime.utc(2026, 11, 2, 16, 0),
      accuracy: 8,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: 0,
      headingAccuracy: 0,
      speed: 0,
      speedAccuracy: 0,
    );

const String hoy = '2026-11-02';
const String ayer = '2026-11-01';

void main() {
  group('compartir la ubicación', () {
    test('al abrir la app NO comparte: espera a que arranque la jornada',
        () async {
      var envios = 0;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerDiaIniciado: () async => null,
        guardarDiaIniciado: (_) async {},
        hoyTexto: () => hoy,
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.alArrancar();

      expect(s.jornadaIniciada, isFalse);
      expect(envios, 0, reason: 'abrir la app no es decir que empezó a trabajar');
      expect(s.estado.value, EstadoDeUbicacion.apagado);
      s.soltar();
    });

    test('«Iniciar jornada» deja escrito el día y empieza a compartir',
        () async {
      var envios = 0;
      String? guardado;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerDiaIniciado: () async => null,
        guardarDiaIniciado: (d) async => guardado = d,
        hoyTexto: () => hoy,
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      final pudo = await s.iniciarJornada();

      expect(pudo, isTrue);
      expect(s.jornadaIniciada, isTrue);
      expect(guardado, hoy, reason: 'se guarda la FECHA, no un sí/no');
      expect(s.sePidioElPermiso, isTrue, reason: 'acá sí se le pide');
      expect(envios, 1, reason: 'y ya mandó la primera');
      expect(s.estado.value, EstadoDeUbicacion.compartiendo);
      s.soltar();
    });

    test('la jornada de HOY se retoma al reabrir, sin volver a preguntar nada',
        () async {
      var envios = 0;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerDiaIniciado: () async => hoy,
        guardarDiaIniciado: (_) async {},
        hoyTexto: () => hoy,
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.alArrancar();

      expect(s.jornadaIniciada, isTrue);
      expect(envios, 1);
      //  Y SIN DIALOGO: abrir la aplicacion no le tira el permiso en la cara
      //  a quien ya lo dio. El permiso se pide al tocar «Iniciar jornada».
      expect(s.sePidioElPermiso, isFalse);
      s.soltar();
    });

    test('la jornada de AYER no comparte: se apaga sola a medianoche',
        () async {
      //  LA DECISIÓN (02/11/2026): la marca es una FECHA, no un booleano. No
      //  hay que apagar nada al terminar el día; mañana esa fecha ya no es
      //  hoy y la ubicación no sale hasta que vuelva a arrancar.
      var envios = 0;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerDiaIniciado: () async => ayer,
        guardarDiaIniciado: (_) async {},
        hoyTexto: () => hoy,
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.alArrancar();

      expect(s.jornadaIniciada, isFalse);
      expect(envios, 0, reason: 'la jornada de ayer no habilita la de hoy');
      s.soltar();
    });

    test('sin permiso no comparte, no deja la jornada escrita, y lo dice',
        () async {
      var envios = 0;
      String? guardado;
      final s = CompartirUbicacion(
        enviar: (_, __) async {
          envios++;
          return true;
        },
        leerDiaIniciado: () async => null,
        guardarDiaIniciado: (d) async => guardado = d,
        hoyTexto: () => hoy,
        cada: const Duration(milliseconds: 20),
      );
      s.permisoDePrueba = false;
      s.posicionDePrueba = _posicion;

      final pudo = await s.iniciarJornada();
      await Future<void>.delayed(const Duration(milliseconds: 60));

      expect(pudo, isFalse);
      expect(s.jornadaIniciada, isFalse);
      expect(guardado, isNull, reason: 'sin permiso la jornada no quedó escrita');
      expect(envios, 0, reason: 'ni una posición');
      expect(s.estado.value, EstadoDeUbicacion.sinPermiso);
      s.soltar();
    });

    test('un rechazo del servidor para por hoy, y NO borra la jornada',
        () async {
      var envios = 0;
      final s = CompartirUbicacion(
        //  `false` = el servidor dijo que no corresponde (fuera de jornada o
        //  de horario).
        enviar: (_, __) async {
          envios++;
          return false;
        },
        leerDiaIniciado: () async => hoy,
        guardarDiaIniciado: (_) async {},
        hoyTexto: () => hoy,
        cada: const Duration(milliseconds: 20),
      );
      s.permisoDePrueba = true;
      s.posicionDePrueba = _posicion;

      await s.encender(pedirPermiso: false);
      await Future<void>.delayed(const Duration(milliseconds: 80));

      expect(s.encendido, isFalse, reason: 'se para solo');
      expect(s.estado.value, EstadoDeUbicacion.fueraDeJornada);
      expect(envios, 1, reason: 'no insiste contra una puerta cerrada');
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
        leerDiaIniciado: () async => null,
        guardarDiaIniciado: (_) async {},
        hoyTexto: () => hoy,
        //  El reloj no llega a sonar: cada envío de esta prueba lo dispara
        //  ella, para contar exactamente y no medir la frecuencia del timer.
        cada: const Duration(hours: 1),
      );
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
