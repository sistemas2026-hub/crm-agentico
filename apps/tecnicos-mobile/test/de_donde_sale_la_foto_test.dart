import 'package:campo/features/ejecucion/de_donde_sale_la_foto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';

/// DE DÓNDE SALE LA IMAGEN DE UNA EVIDENCIA.
///
/// LO QUE DE VERDAD SE PRUEBA no es un `if`: es que **el valor por omisión sea
/// cámara**. Una evidencia que se puede elegir de la galería ya no prueba que
/// alguien estuvo ahí -- puede ser de otro día o de otra casa, y la orden la
/// guarda igual, con la misma cara de evidencia.
///
/// Por eso casi todas las pruebas de acá miran el lado del NO: que una
/// plantilla vieja, un dato raro de la API o una clave ausente caigan a
/// cámara. La galería es la excepción, y tiene que pedirse a propósito.
void main() {
  group('la galería se abre SOLO si la plantilla lo dice', () {
    test('marcada como captura: galería', () {
      //  El caso que lo originó: el test de velocidad ES una captura de
      //  pantalla, y no hay forma de «tomarle una foto».
      final req = <String, dynamic>{
        'id': 'r1', 'titulo': 'Test de velocidad', 'es_captura': true
      };

      expect(fuenteDeLaEvidencia(req), ImageSource.gallery);
      expect(esUnaCaptura(req), isTrue);
    });

    test('sin marcar: cámara', () {
      final req = <String, dynamic>{
        'id': 'r2', 'titulo': 'Daño encontrado', 'es_captura': false
      };

      expect(fuenteDeLaEvidencia(req), ImageSource.camera);
    });

    test('UNA PLANTILLA VIEJA no trae la clave, y sigue siendo cámara', () {
      //  EL CASO MÁS IMPORTANTE DE ESTE ARCHIVO. Todas las plantillas que ya
      //  existen están así. Si la ausencia cayera a galería, cada evidencia
      //  del sistema empezaría a aceptar imágenes viejas de un día para otro,
      //  sin que nadie lo decidiera.
      final req = <String, dynamic>{'id': 'r3', 'titulo': 'Medición al salir'};

      expect(fuenteDeLaEvidencia(req), ImageSource.camera);
      expect(esUnaCaptura(req), isFalse);
    });
  });

  group('lo que NO cuenta como la marca', () {
    test('de la API llega JSON: «si», 1 y «true» no son la marca', () {
      //  Se compara contra `true` y no se usa el valor como booleano. Un
      //  backend que mande otra cosa no puede abrir la galería por accidente.
      for (final valor in <Object>['si', 'true', 1, 'yes', <String>[]]) {
        final req = <String, dynamic>{'es_captura': valor};
        expect(fuenteDeLaEvidencia(req), ImageSource.camera,
            reason: '$valor no es la marca');
      }
    });

    test('null, en el valor o en el requisito entero', () {
      expect(fuenteDeLaEvidencia(<String, dynamic>{'es_captura': null}),
          ImageSource.camera);
      expect(fuenteDeLaEvidencia(null), ImageSource.camera);
      expect(fuenteDeLaEvidencia(<String, dynamic>{}), ImageSource.camera);
    });

    test('false explícito', () {
      expect(fuenteDeLaEvidencia(<String, dynamic>{'es_captura': false}),
          ImageSource.camera);
    });
  });

  group('el botón dice lo que va a pasar', () {
    test('en una captura NO dice «tomar»', () {
      //  «Tomar fotografía» abriendo la galería deja al técnico esperando una
      //  cámara que no se abre, y eso se lee como que la app falló.
      final texto = textoDelBoton(yaHayFoto: false, esCaptura: true);

      expect(texto, 'ELEGIR LA CAPTURA');
      expect(texto.toLowerCase(), isNot(contains('tomar')));
    });

    test('en una foto normal sí', () {
      expect(textoDelBoton(yaHayFoto: false, esCaptura: false),
          'TOMAR FOTOGRAFÍA');
    });

    test('con una ya puesta, ofrece cambiarla en los dos casos', () {
      expect(textoDelBoton(yaHayFoto: true, esCaptura: true), 'ELEGIR OTRA');
      expect(textoDelBoton(yaHayFoto: true, esCaptura: false),
          'VOLVER A TOMAR');
    });

    test('los cuatro textos son distintos entre sí', () {
      //  Si dos coincidieran, el técnico no podría saber qué va a pasar al
      //  tocar -- que es lo único para lo que esta función existe.
      final textos = <String>{
        for (final hay in <bool>[true, false])
          for (final cap in <bool>[true, false])
            textoDelBoton(yaHayFoto: hay, esCaptura: cap)
      };

      expect(textos.length, 4);
    });
  });
}
