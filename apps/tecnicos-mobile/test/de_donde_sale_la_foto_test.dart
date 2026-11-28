import 'package:campo/features/ejecucion/de_donde_sale_la_foto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';

/// DE DÓNDE SALE LA IMAGEN DE UNA EVIDENCIA.
///
/// LA DECISIÓN CAMBIÓ EL 09/11/2026, y conviene saber desde dónde.
///
/// Hasta ese día la galería se abría SOLO si la plantilla marcaba el requisito
/// como captura, y todo lo demás era cámara obligatoria. El motivo era bueno:
/// una foto sacada en el momento prueba que alguien estuvo ahí; una elegida de
/// la galería puede ser de otro día o de otra casa, y la orden la guardaría
/// igual, con la misma cara de evidencia.
///
/// El usuario lo probó en campo y pidió lo contrario: «en test de velocidad
/// solo sale para elegir captura, deben ser ambos pero en un solo botón». Y
/// tenía razón por los dos lados: con una captura no se podía fotografiar la
/// pantalla de otro aparato, y con una foto normal no se podía usar la que ya
/// había sacado cinco minutos antes.
///
/// LO QUE REEMPLAZA A LA PROHIBICIÓN. La diferencia entre una foto de ahora y
/// una vieja sigue importando, así que ahora la app GUARDA DE DÓNDE SALIÓ
/// --`de_galeria`, en los metadatos de la evidencia-- y quien revisa el cierre
/// decide con el dato a la vista. Antes se defendía prohibiendo, y el precio
/// lo pagaba el técnico cuando la cámara no servía para ese requisito.
///
/// Lo que la plantilla decide HOY es cuál se ofrece primero, no cuál es la
/// única. Por eso las pruebas de abajo siguen mirando el lado del NO: un dato
/// raro, una clave ausente o una plantilla vieja tienen que ofrecer la cámara
/// primero, que es el caso frecuente y el lado seguro.
void main() {
  group('cuál se ofrece primero', () {
    test('marcada como captura: la galería', () {
      //  El caso que lo originó: el test de velocidad ES una captura de
      //  pantalla, y lo normal es elegirla de la galería.
      final req = <String, dynamic>{
        'id': 'r1', 'titulo': 'Test de velocidad', 'es_captura': true
      };

      expect(fuenteDeLaEvidencia(req), ImageSource.gallery);
      expect(esUnaCaptura(req), isTrue);
    });

    test('sin marcar: la cámara', () {
      final req = <String, dynamic>{
        'id': 'r2', 'titulo': 'Daño encontrado', 'es_captura': false
      };

      expect(fuenteDeLaEvidencia(req), ImageSource.camera);
    });

    test('UNA PLANTILLA VIEJA no trae la clave, y ofrece cámara primero', () {
      //  Todas las plantillas que ya existen están así. La marca no cambia
      //  qué se PUEDE usar --las dos, siempre-- pero sí cuál queda a un toque,
      //  y una plantilla que nadie editó no puede cambiar eso sola.
      final req = <String, dynamic>{'id': 'r3', 'titulo': 'Medición al salir'};

      expect(fuenteDeLaEvidencia(req), ImageSource.camera);
      expect(esUnaCaptura(req), isFalse);
    });

    test('LAS DOS ESTÁN SIEMPRE: la otra es la que falta', () {
      //  El pedido del usuario, medido: sea cual sea la primera, hay una
      //  segunda, y nunca es la misma.
      for (final req in <Map<String, dynamic>?>[
        <String, dynamic>{'es_captura': true},
        <String, dynamic>{'es_captura': false},
        <String, dynamic>{},
        null,
      ]) {
        final ImageSource primera = fuenteDeLaEvidencia(req);
        final ImageSource segunda = laOtraFuente(primera);
        expect(segunda, isNot(primera));
        expect(<ImageSource>{primera, segunda},
            <ImageSource>{ImageSource.camera, ImageSource.gallery});
      }
    });
  });

  group('lo que NO cuenta como la marca', () {
    test('de la API llega JSON: «si», 1 y «true» no son la marca', () {
      //  Se compara contra `true` y no se usa el valor como booleano. Un
      //  backend que mande otra cosa no puede reordenar las opciones por
      //  accidente.
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

  /// LO QUE REEMPLAZA A LA PROHIBICIÓN. Sin esto, abrir la galería a todos los
  /// requisitos afloja en silencio lo único que una foto de campo prueba.
  group('queda registrado de dónde salió', () {
    test('la de la galería se marca; la de la cámara, no', () {
      expect(esDeGaleria(ImageSource.gallery), isTrue);
      expect(esDeGaleria(ImageSource.camera), isFalse);
    });
  });

  group('el botón y las opciones dicen lo que va a pasar', () {
    test('el botón YA NO NOMBRA UNA FUENTE: abre una elección', () {
      //  «Tomar fotografía» abriendo la galería dejaba al técnico esperando
      //  una cámara que no se abre. Ahora no promete ninguna de las dos,
      //  porque el que elige es él.
      for (final cap in <bool>[true, false]) {
        final texto = textoDelBoton(yaHayFoto: false, esCaptura: cap);
        expect(texto.toLowerCase(), isNot(contains('tomar')));
        expect(texto.toLowerCase(), isNot(contains('elegir')));
      }
    });

    test('dice de qué imagen habla: captura o foto', () {
      expect(textoDelBoton(yaHayFoto: false, esCaptura: true),
          'AGREGAR LA CAPTURA');
      expect(textoDelBoton(yaHayFoto: false, esCaptura: false),
          'AGREGAR LA FOTO');
    });

    test('con una ya puesta, ofrece cambiarla', () {
      //  Uno solo para los dos casos: con la imagen puesta, lo que se hace es
      //  lo mismo --volver a elegir de dónde sale--, así que distinguirlos
      //  sería decir una diferencia que ya no existe.
      expect(textoDelBoton(yaHayFoto: true, esCaptura: true),
          'CAMBIAR LA IMAGEN');
      expect(textoDelBoton(yaHayFoto: true, esCaptura: false),
          'CAMBIAR LA IMAGEN');
    });

    test('las dos opciones de la hoja dicen el gesto, y son distintas', () {
      //  Si las dos dijeran lo mismo, el técnico no podría elegir: es lo
      //  único para lo que esta función existe.
      final camara = textoDeLaOpcion(ImageSource.camera);
      final galeria = textoDeLaOpcion(ImageSource.gallery);

      expect(camara, isNot(galeria));
      expect(camara.toLowerCase(), contains('ahora'));
      expect(galeria.toLowerCase(), contains('ya tengo'));
    });
  });
}
