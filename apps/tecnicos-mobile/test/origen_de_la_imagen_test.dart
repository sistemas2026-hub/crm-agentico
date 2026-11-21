import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:campo/features/ejecucion/origen_de_la_imagen.dart';

/// DE DÓNDE SALIÓ UNA IMAGEN DE GALERÍA, Y DE CUÁNDO ES  --  21/11/2026
///
/// «Que revise la fecha en que es la captura y si es de internet o captura
/// del teléfono.» La app guardaba solo que la imagen venía de la galería.
///
/// Estas pruebas arman los bytes A MANO, con las cabeceras de verdad: un PNG
/// y un JPEG con su bloque EXIF. No usan una imagen de muestra porque lo que
/// se mide es la lectura de la cabecera, y una muestra escondería qué byte
/// decide qué.

Uint8List _png(int ancho, int alto) => Uint8List.fromList(<int>[
      0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
      0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
      ..._be32(ancho), ..._be32(alto),
      0x08, 0x06, 0x00, 0x00, 0x00,
    ]);

List<int> _be32(int n) =>
    <int>[(n >> 24) & 0xFF, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF];
List<int> _be16(int n) => <int>[(n >> 8) & 0xFF, n & 0xFF];
List<int> _le32(int n) => _be32(n).reversed.toList();
List<int> _le16(int n) => _be16(n).reversed.toList();

/// Un JPEG mínimo: opcionalmente su EXIF (cámara y fecha), y su tamaño.
Uint8List _jpeg(int ancho, int alto,
    {String? camara, String? fecha, bool grande = true}) {
  final List<int> Function(int) u16 = grande ? _be16 : _le16;
  final List<int> Function(int) u32 = grande ? _be32 : _le32;
  final List<int> b = <int>[0xFF, 0xD8];
  if (camara != null || fecha != null) {
    final List<int> marca = <int>[...(camara ?? '').codeUnits, 0];
    final List<int> cuando = <int>[...(fecha ?? '').codeUnits, 0];
    //  IFD0 con dos entradas (30 bytes desde el 8), después el texto de la
    //  cámara, después el IFD de EXIF con una entrada, después la fecha.
    final int dondeMarca = 38;
    final int dondeExif = dondeMarca + marca.length;
    final int dondeFecha = dondeExif + 18;
    final List<int> tiff = <int>[
      ...(grande ? <int>[0x4D, 0x4D] : <int>[0x49, 0x49]), ...u16(42), ...u32(8),
      ...u16(2),
      ...u16(0x010F), ...u16(2), ...u32(marca.length), ...u32(dondeMarca),
      ...u16(0x8769), ...u16(4), ...u32(1), ...u32(dondeExif),
      ...u32(0),
      ...marca,
      ...u16(1),
      ...u16(0x9003), ...u16(2), ...u32(cuando.length), ...u32(dondeFecha),
      ...u32(0),
      ...cuando,
    ];
    b.addAll(<int>[0xFF, 0xE1, ..._be16(2 + 6 + tiff.length),
      0x45, 0x78, 0x69, 0x66, 0x00, 0x00, ...tiff]);
  }
  b.addAll(<int>[0xFF, 0xC0, ..._be16(17), 0x08, ..._be16(alto), ..._be16(ancho),
    0x03, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1]);
  b.addAll(<int>[0xFF, 0xD9]);
  return Uint8List.fromList(b);
}

void main() {
  group('el tamaño, leído de la cabecera', () {
    test('de un PNG, que es como sale una captura', () {
      expect(tamanoDeImagen(_png(1080, 2400)), (ancho: 1080, alto: 2400));
    });

    test('de un JPEG, con o sin EXIF adelante', () {
      expect(tamanoDeImagen(_jpeg(1920, 1080)), (ancho: 1920, alto: 1080));
      expect(
          tamanoDeImagen(_jpeg(800, 600,
              camara: 'Canon', fecha: '2026:11:21 09:23:01')),
          (ancho: 800, alto: 600));
    });

    test('ancho y alto NO se cruzan', () {
      //  En el JPEG el alto va PRIMERO. Leídos al revés, una captura de pie
      //  parecería acostada y dejaría de coincidir con la pantalla.
      final t = tamanoDeImagen(_jpeg(1080, 2400))!;
      expect(t.ancho, 1080);
      expect(t.alto, 2400);
    });

    test('lo que no es una imagen conocida no inventa un tamaño', () {
      expect(tamanoDeImagen(Uint8List.fromList(<int>[1, 2, 3, 4])), isNull);
      expect(tamanoDeImagen(Uint8List(0)), isNull);
    });

    test('un archivo cortado no revienta', () {
      final Uint8List entero = _jpeg(1080, 2400, camara: 'Canon',
          fecha: '2026:11:21 09:23:01');
      for (int n = 0; n < entero.length; n++) {
        expect(() => tamanoDeImagen(Uint8List.sublistView(entero, 0, n)),
            returnsNormally);
        expect(() => exifDe(Uint8List.sublistView(entero, 0, n)),
            returnsNormally);
      }
    });
  });

  group('si el nombre dice captura', () {
    test('lo que Android le pone a una captura', () {
      expect(nombreDiceCaptura('Screenshot_20261121-092301.png'), isTrue);
      expect(nombreDiceCaptura('scaled_Screenshot_20261121_092301_Chrome.jpg'),
          isTrue);
      expect(nombreDiceCaptura('Captura de pantalla_20261121.png'), isTrue);
    });

    test('una foto de cámara o una de WhatsApp, no', () {
      expect(nombreDiceCaptura('IMG_20261121_092301.jpg'), isFalse);
      expect(nombreDiceCaptura('IMG-20261121-WA0003.jpg'), isFalse);
      expect(nombreDiceCaptura('1000012345.jpg'), isFalse);
    });
  });

  group('la fecha que el nombre trae escrita', () {
    test('las tres formas de Android', () {
      expect(fechaSegunElNombre('Screenshot_20261121-092301.png'),
          '2026-11-21T09:23:01');
      expect(fechaSegunElNombre('scaled_Screenshot_20261121_092301_Chrome.jpg'),
          '2026-11-21T09:23:01');
      expect(
          fechaSegunElNombre(
              'Screenshot_2026-11-21-09-23-01-123_com.android.chrome.jpg'),
          '2026-11-21T09:23:01');
    });

    test('solo el día, cuando no trae hora', () {
      expect(fechaSegunElNombre('IMG-20261121-WA0003.jpg'), '2026-11-21');
    });

    test('un contador NO es una fecha', () {
      //  Leerlo como fecha inventaría un día, y el servidor le creería.
      expect(fechaSegunElNombre('1000012345.jpg'), isNull);
      expect(fechaSegunElNombre('1720261121092301.jpg'), isNull);
      expect(fechaSegunElNombre('20261121092301999.jpg'), isNull);
    });

    test('una fecha que no existe no se acepta', () {
      expect(fechaSegunElNombre('Screenshot_20261341-092301.png'), isNull);
      expect(fechaSegunElNombre('Screenshot_20260231-092301.png'), isNull);
      expect(fechaSegunElNombre('Screenshot_20261121-256199.png'), '2026-11-21');
    });

    test('sin fecha, nada', () {
      expect(fechaSegunElNombre('foto del medidor.jpg'), isNull);
    });
  });

  group('lo que una foto de cámara trae adentro', () {
    test('la fecha en que se tomó y que la tomó una cámara', () {
      final e = exifDe(_jpeg(4000, 3000,
          camara: 'samsung', fecha: '2026:11:14 16:05:09'));
      expect(e.camara, isTrue);
      expect(e.fecha, '2026-11-14T16:05:09');
    });

    test('también con los bytes en el otro orden', () {
      final e = exifDe(_jpeg(4000, 3000,
          camara: 'Xiaomi', fecha: '2026:11:14 16:05:09', grande: false));
      expect(e.camara, isTrue);
      expect(e.fecha, '2026-11-14T16:05:09');
    });

    test('una captura y una imagen sin EXIF no traen nada', () {
      expect(exifDe(_png(1080, 2400)), (fecha: null, camara: false));
      expect(exifDe(_jpeg(800, 800)), (fecha: null, camara: false));
    });

    test('un EXIF sin nombre de cámara no cuenta como cámara', () {
      final e = exifDe(_jpeg(800, 800, camara: '', fecha: '2026:11:14 16:05:09'));
      expect(e.camara, isFalse);
      expect(e.fecha, '2026-11-14T16:05:09');
    });

    test('una fecha mal escrita no se acepta', () {
      expect(exifDe(_jpeg(800, 800, camara: 'Canon', fecha: '0000:00:00 00:00:00')).fecha,
          isNull);
      expect(exifDe(_jpeg(800, 800, camara: 'Canon', fecha: 'ayer a la tarde 123')).fecha,
          isNull);
    });
  });

  group('lo que sube con la evidencia', () {
    test('una captura de este teléfono', () {
      final m = origenDeLaImagen(
          bytes: _png(1080, 2400),
          nombre: 'scaled_Screenshot_20261121-092301.png',
          pantallaAncho: 1080,
          pantallaAlto: 2400);

      expect(m['origen_version'], versionDelOrigen);
      expect(m['imagen_ancho'], 1080);
      expect(m['imagen_alto'], 2400);
      expect(m['pantalla_ancho'], 1080);
      expect(m['pantalla_alto'], 2400);
      expect(m['nombre_dice_captura'], isTrue);
      expect(m['fecha_segun_nombre'], '2026-11-21T09:23:01');
      expect(m['exif_camara'], isFalse);
      expect(m.containsKey('exif_fecha'), isFalse);
    });

    test('una imagen bajada de internet: lo que NO se sabe no viaja', () {
      final m = origenDeLaImagen(
          bytes: _jpeg(800, 800), nombre: '1000012345.jpg',
          pantallaAncho: 1080, pantallaAlto: 2400);

      expect(m['imagen_ancho'], 800);
      expect(m['nombre_dice_captura'], isFalse);
      expect(m['exif_camara'], isFalse);
      //  Ausente, no `null` ni vacío: el servidor distingue «no se sabe».
      expect(m.containsKey('fecha_segun_nombre'), isFalse);
      expect(m.containsKey('exif_fecha'), isFalse);
    });

    test('el NOMBRE del archivo no viaja', () {
      //  Un archivo renombrado puede traer el nombre de un cliente.
      final m = origenDeLaImagen(
          bytes: _png(10, 10), nombre: 'cedula de Beatriz Pinzon 20261121.png');

      expect(m.values.whereType<String>().any((v) => v.contains('Beatriz')),
          isFalse);
      expect(m.keys, isNot(contains('nombre')));
    });

    test('sin el tamaño de la pantalla, esas dos claves no van', () {
      final m = origenDeLaImagen(bytes: _png(10, 10), nombre: 'a.png');

      expect(m.containsKey('pantalla_ancho'), isFalse);
      expect(m.containsKey('pantalla_alto'), isFalse);
    });
  });

  group('leyendo el archivo', () {
    test('lee lo mismo que con los bytes en la mano', () async {
      final Directory d = await Directory.systemTemp.createTemp('origen');
      final File f = File('${d.path}/x.png');
      await f.writeAsBytes(_png(1080, 2400));

      final m = await leerOrigenDeLaImagen(f.path,
          nombre: 'Screenshot_20261121-092301.png',
          pantallaAncho: 1080, pantallaAlto: 2400);

      expect(m['imagen_alto'], 2400);
      expect(m['fecha_segun_nombre'], '2026-11-21T09:23:01');
      await d.delete(recursive: true);
    });

    test('un archivo que no existe NO frena la evidencia', () async {
      expect(await leerOrigenDeLaImagen('/no/existe.png', nombre: 'a.png'),
          isEmpty);
    });
  });
}
