import 'package:campo/features/detalle_orden/guardar_ubicacion_del_cliente.dart';
import 'package:flutter_test/flutter_test.dart';

/// LA UBICACION DE LA CASA, TOMADA DESDE LA PUERTA  --  10/11/2026.
///
/// Lo que estas pruebas defienden, y por que cada una es un efecto y no un
/// mecanismo:
///
/// * **Lo que no sirve NO SE MANDA**, y se afirma contando los envios: una
///   posicion simulada o con cientos de metros de error queda escrita en el
///   sistema del ISP como si fuera la casa, y el que la lea despues la va a
///   creer. Peor que no tenerla.
/// * **Cada motivo de fallo lleva a una accion distinta** --prender el GPS,
///   dar el permiso, salir a cielo abierto--, asi que se afirma que el
///   mensaje los distingue y no que exista un mensaje.
/// * **Un exito a medias se dice como tal**, y se dice que volver a tocar
///   completa sin repetir lo que ya salio.
void main() {
  /// Una lectura del GPS como la que devuelve `UbicacionDeCaptura.tomar()`.
  Map<String, dynamic> lectura({
    double? lat = 10.9108,
    double? lng = -74.8186,
    double? precision = 8.0,
    bool simulada = false,
    String? motivo,
  }) =>
      <String, dynamic>{
        'origen': 'app_campo',
        if (lat != null) 'lat': lat,
        if (lng != null) 'lng': lng,
        if (precision != null) 'precision_m': precision,
        if (simulada) 'ubicacion_simulada': true,
        if (motivo != null) 'ubicacion_motivo': motivo,
      };

  /// Cuenta los envios y responde lo que se le diga.
  ({
    GuardarUbicacionDelCliente accion,
    List<List<double>> enviados,
    List<String> motivos,
  }) armar({
    Map<String, dynamic>? gps,
    int codigo = 200,
    Map<String, dynamic>? cuerpo,
    bool rompe = false,
  }) {
    final List<List<double>> enviados = <List<double>>[];
    final List<String> motivos = <String>[];
    return (
      enviados: enviados,
      motivos: motivos,
      accion: GuardarUbicacionDelCliente(
        tomarUbicacion: () async => gps ?? lectura(),
        enviar: (double la, double lo, String motivo) async {
          enviados.add(<double>[la, lo]);
          motivos.add(motivo);
          if (rompe) throw Exception('se corto la red');
          return (codigo: codigo, cuerpo: cuerpo ?? <String, dynamic>{});
        },
      ),
    );
  }

  group('A · lo que sí se guarda', () {
    test('a1 · una posición buena viaja tal cual', () async {
      final a = armar(cuerpo: <String, dynamic>{'codigo': 'guardada'});
      final r = await a.accion.ejecutar();

      expect(r.estado, EstadoDeGuardado.guardada);
      expect(a.enviados, hasLength(1));
      expect(a.enviados.single, <double>[10.9108, -74.8186],
          reason: 'la que leyó el GPS, sin redondear ni mover');
    });

    test('a2 · sin precisión informada no se bloquea', () async {
      //  Algunos equipos no la reportan. Rechazar por eso dejaría al técnico
      //  sin poder guardar nada en ese teléfono.
      final a = armar(
          gps: lectura(precision: null),
          cuerpo: <String, dynamic>{'codigo': 'guardada'});
      final r = await a.accion.ejecutar();

      expect(r.estado, EstadoDeGuardado.guardada);
      expect(a.enviados, hasLength(1));
    });

    test('a3 · justo en el límite se acepta', () async {
      final a = armar(
          gps: lectura(precision: metrosDeErrorAceptados),
          cuerpo: <String, dynamic>{'codigo': 'guardada'});
      expect((await a.accion.ejecutar()).estado, EstadoDeGuardado.guardada);
    });
  });

  group('B · lo que NO se manda', () {
    test('b1 · una posición simulada no se escribe, y se dice por qué',
        () async {
      final a = armar(gps: lectura(simulada: true));
      final r = await a.accion.ejecutar();

      expect(r.estado, EstadoDeGuardado.demasiadoImprecisa);
      //  CERO ENVIOS: queda en el sistema del ISP como si fuera la casa, y
      //  nadie que la lea después va a saber que era falsa.
      expect(a.enviados, isEmpty);
      expect(r.mensaje.toLowerCase(), contains('simulada'));
    });

    test('b2 · una posición de la antena de celular tampoco', () async {
      final a = armar(gps: lectura(precision: 1800.0));
      final r = await a.accion.ejecutar();

      expect(r.estado, EstadoDeGuardado.demasiadoImprecisa);
      expect(a.enviados, isEmpty);
      //  Y el número, porque «imprecisa» no le dice al técnico si esperar
      //  cinco segundos o salir a la vereda.
      expect(r.mensaje, contains('1800'));
    });

    test('b3 · sin coordenada no se inventa nada', () async {
      final a = armar(gps: lectura(lat: null, lng: null, motivo: 'sin_senal_gps'));
      final r = await a.accion.ejecutar();

      expect(r.estado, EstadoDeGuardado.sinUbicacion);
      expect(a.enviados, isEmpty);
    });
  });

  group('C · cada motivo lleva a una acción distinta', () {
    test('c1 · el servicio apagado dice que lo active', () async {
      final a = armar(
          gps: lectura(lat: null, lng: null, motivo: 'servicio_apagado'));
      final r = await a.accion.ejecutar();
      expect(r.mensaje.toLowerCase(), contains('activ'));
    });

    test('c2 · el permiso denegado manda a los ajustes', () async {
      final a = armar(
          gps: lectura(lat: null, lng: null, motivo: 'permiso_denegado'));
      final r = await a.accion.ejecutar();
      expect(r.mensaje.toLowerCase(), contains('permiso'));
      expect(r.mensaje.toLowerCase(), contains('ajustes'));
    });

    test('c3 · sin señal manda afuera', () async {
      final a = armar(
          gps: lectura(lat: null, lng: null, motivo: 'sin_senal_gps'));
      final r = await a.accion.ejecutar();
      expect(r.mensaje.toLowerCase(), contains('señal'));
    });

    test('c4 · los tres mensajes son distintos entre sí', () async {
      //  Si dos motivos dijeran lo mismo, distinguirlos no serviría de nada.
      final List<String> dichos = <String>[];
      for (final String m in <String>[
        'servicio_apagado',
        'permiso_denegado',
        'sin_senal_gps'
      ]) {
        final a = armar(gps: lectura(lat: null, lng: null, motivo: m));
        dichos.add((await a.accion.ejecutar()).mensaje);
      }
      expect(dichos.toSet(), hasLength(3), reason: 'tres motivos, tres frases');
    });
  });

  group('C2 · el motivo de una corrección', () {
    test('c2a · el motivo viaja tal cual al servidor', () async {
      //  Una correccion pisa un punto que ya estaba: alguien decidio que el
      //  anterior era peor. Esa decision tiene que llegar con su motivo, y el
      //  servidor la rechaza sin el.
      final a = armar(cuerpo: <String, dynamic>{'codigo': 'guardada'});
      await a.accion.ejecutar(motivo: 'El pin caia en la otra cuadra');

      expect(a.motivos.single, 'El pin caia en la otra cuadra');
    });

    test('c2b · llenar un vacío no manda motivo', () async {
      //  No hay nada que justificar, y pedir un texto ahi solo enseña a
      //  escribir «ok» para destrabar el boton.
      final a = armar(cuerpo: <String, dynamic>{'codigo': 'guardada'});
      await a.accion.ejecutar();

      expect(a.motivos.single, isEmpty);
    });

    test('c2c · un rechazo por falta de motivo se dice con esas palabras',
        () async {
      final a = armar(
          codigo: 400, cuerpo: <String, dynamic>{'codigo': 'motivo_requerido'});
      final r = await a.accion.ejecutar();

      //  «Proba de nuevo» seria mentira: no va a andar hasta que escriba algo.
      expect(r.mensaje.toLowerCase(), contains('por qué'));
      expect(r.mensaje.toLowerCase(), isNot(contains('probá de nuevo')));
    });
  });

  group('D · lo que contesta el servidor', () {
    test('d1 · un éxito a medias se dice, y dice qué hacer', () async {
      final a = armar(
          codigo: 200, cuerpo: <String, dynamic>{'codigo': 'parcial'});
      final r = await a.accion.ejecutar();

      expect(r.estado, EstadoDeGuardado.parcial);
      expect(r.algoQuedoEscrito, isTrue, reason: 'algo quedó, y no se deshace');
      expect(r.mensaje.toLowerCase(), contains('volvé a tocar'));
    });

    test('d2 · el interruptor detenido no se confunde con un fallo de red',
        () async {
      final a = armar(
          codigo: 409,
          cuerpo: <String, dynamic>{'codigo': 'bloqueado_por_interruptor'});
      final r = await a.accion.ejecutar();

      expect(r.estado, EstadoDeGuardado.rechazada);
      expect(r.algoQuedoEscrito, isFalse);
      //  «Probá de nuevo» sería mentira: no va a andar hasta que alguien lo
      //  encienda desde la oficina.
      expect(r.mensaje.toLowerCase(), contains('detenid'));
      expect(r.mensaje.toLowerCase(), isNot(contains('probá de nuevo')));
    });

    test('d3 · el servidor sin responder no tumba nada', () async {
      final a = armar(rompe: true);
      final r = await a.accion.ejecutar();

      expect(r.estado, EstadoDeGuardado.rechazada);
      expect(r.mensaje.toLowerCase(), contains('no respondió'));
    });

    test('d4 · una orden sin identificador lo dice con esas palabras',
        () async {
      final a = armar(
          codigo: 400,
          cuerpo: <String, dynamic>{'codigo': 'sin_identificador'});
      final r = await a.accion.ejecutar();
      expect(r.mensaje.toLowerCase(), contains('identificar'));
    });
  });
}
