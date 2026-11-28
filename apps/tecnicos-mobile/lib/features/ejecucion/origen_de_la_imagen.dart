/// DE DÓNDE SALIÓ UNA IMAGEN ELEGIDA DE LA GALERÍA, Y DE CUÁNDO ES
/// (21/11/2026).
///
/// EL PEDIDO
/// ---------
/// «Que revise la fecha en que es la captura y si es de internet o captura
/// del teléfono.»
///
/// Hasta hoy la app guardaba UNA cosa de una imagen de galería: que venía de
/// la galería (`de_galeria`, ver `de_donde_sale_la_foto.dart`). La hora que
/// viajaba era la del momento en que el técnico la ELIGIÓ, no la de la
/// imagen, y nadie miraba qué clase de archivo era. Quien revisa el cierre
/// veía una captura de hoy y una imagen bajada de una tienda con la misma
/// cara.
///
/// QUÉ SE LEE, Y POR QUÉ ESO
/// -------------------------
/// Cuatro cosas que el archivo dice de sí mismo, sin pedirle nada al sistema
/// ni agregar un permiso:
///
///  * SU TAMAÑO EN PIXELES, contra el de la pantalla de este teléfono. Una
///    captura mide EXACTAMENTE lo que la pantalla; una imagen de internet,
///    casi nunca. Es la señal más firme de las cuatro.
///  * SI EL NOMBRE DICE «captura». Android nombra `Screenshot_…` lo que
///    captura. Sirve cuando el tamaño no alcanza (una captura recortada).
///  * LA FECHA QUE TRAE EL NOMBRE. Una captura no lleva fecha adentro: el
///    sistema la escribe en el nombre del archivo.
///  * LA FECHA Y LA CÁMARA QUE TRAE ADENTRO (EXIF). Una foto de la cámara
///    guardada en la galería sí las lleva.
///
/// LO QUE ESTO NO PUEDE AFIRMAR, y por eso no lo afirma: que una imagen «es
/// de internet». Solo puede decir lo que NO es —ni captura de este teléfono
/// ni foto de una cámara—. El servidor lo llama «origen desconocido».
///
/// Y TODO SALE DEL TELÉFONO, que el técnico controla: sirve para ver un
/// descuido, no para probar un engaño. Por eso el servidor nunca devuelve
/// una orden sola por esto: se lo muestra a una persona.
///
/// NO VIAJA EL NOMBRE DEL ARCHIVO. Un archivo renombrado puede traer el
/// nombre de un cliente; de él se sacan un booleano y una fecha, acá, y eso
/// es lo que sube.
///
/// POR QUÉ SIN UNA LIBRERÍA DE IMÁGENES: lo que hace falta son veinte bytes
/// de la cabecera. Decodificar la imagen entera para leer su ancho gastaría
/// memoria del teléfono por nada, y una dependencia nueva hay que
/// compilarla en cada plataforma.
///
/// NADA DE ESTO LEVANTA. Una evidencia no se pierde ni se demora porque su
/// cabecera sea rara: lo que no se pudo leer, no viaja.
library;

import 'dart:io';
import 'dart:typed_data';

/// La versión de este contrato. El servidor la usa para saber que la app
/// SÍ miró —y no encontró— en vez de no haber mirado.
const int versionDelOrigen = 1;

/// Ancho y alto en pixeles, leídos de la cabecera. `null` si el formato no
/// es PNG ni JPEG, o si la cabecera no se entiende.
({int ancho, int alto})? tamanoDeImagen(Uint8List b) {
  try {
    //  PNG: firma de 8 bytes, y enseguida el bloque IHDR con ancho y alto.
    if (b.length >= 24 &&
        b[0] == 0x89 && b[1] == 0x50 && b[2] == 0x4E && b[3] == 0x47 &&
        b[12] == 0x49 && b[13] == 0x48 && b[14] == 0x44 && b[15] == 0x52) {
      final int ancho = _u32(b, 16, true);
      final int alto = _u32(b, 20, true);
      return (ancho > 0 && alto > 0) ? (ancho: ancho, alto: alto) : null;
    }
    //  JPEG: el tamaño vive en el segmento SOF, que no tiene posición fija.
    for (final _Segmento s in _segmentosJpeg(b)) {
      final bool esSof = s.marca >= 0xC0 && s.marca <= 0xCF &&
          s.marca != 0xC4 && s.marca != 0xC8 && s.marca != 0xCC;
      if (!esSof || s.fin - s.inicio < 5) continue;
      final int alto = _u16(b, s.inicio + 1, true);
      final int ancho = _u16(b, s.inicio + 3, true);
      return (ancho > 0 && alto > 0) ? (ancho: ancho, alto: alto) : null;
    }
  } catch (_) {}
  return null;
}

/// Si el nombre del archivo dice que es una captura de pantalla.
bool nombreDiceCaptura(String nombre) {
  final String n = nombre.toLowerCase();
  return n.contains('screenshot') ||
      n.contains('screen_shot') ||
      n.contains('screen-shot') ||
      n.contains('captura') ||
      n.contains('pantallazo');
}

/// La fecha que el nombre del archivo trae escrita, en ISO y SIN zona
/// (`2026-11-21T09:23:01`, o `2026-11-21` si no trae hora). `null` si no
/// trae ninguna que sea una fecha de verdad.
///
/// Las formas medidas contra nombres reales de Android:
///   Screenshot_20261121-092301.png            (Pixel, Motorola)
///   Screenshot_20261121_092301_Chrome.jpg     (Samsung, Huawei)
///   Screenshot_2026-11-21-09-23-01-123_x.jpg  (Xiaomi)
///
/// NO PRECEDIDA POR OTRO DÍGITO: `1720261121092301.jpg` es un contador, no
/// una fecha, y leerlo como tal inventaría un día.
String? fechaSegunElNombre(String nombre) {
  final RegExp conHora = RegExp(
      r'(?<!\d)(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[-_. ]?(\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d{3,})');
  final RegExpMatch? m = conHora.firstMatch(nombre);
  if (m != null) {
    final List<int> p = <int>[for (int i = 1; i <= 6; i++) int.parse(m.group(i)!)];
    if (_esFecha(p[0], p[1], p[2]) && p[3] < 24 && p[4] < 60 && p[5] < 60) {
      return '${_dd(p[0], 4)}-${_dd(p[1])}-${_dd(p[2])}'
          'T${_dd(p[3])}:${_dd(p[4])}:${_dd(p[5])}';
    }
  }
  final RegExp soloDia =
      RegExp(r'(?<!\d)(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)');
  final RegExpMatch? d = soloDia.firstMatch(nombre);
  if (d != null) {
    final int a = int.parse(d.group(1)!);
    final int me = int.parse(d.group(2)!);
    final int di = int.parse(d.group(3)!);
    if (_esFecha(a, me, di)) return '${_dd(a, 4)}-${_dd(me)}-${_dd(di)}';
  }
  return null;
}

/// Lo que una foto de cámara trae adentro: cuándo se tomó y si la tomó una
/// cámara. Una captura y una imagen bajada de internet casi nunca traen
/// ninguna de las dos.
({String? fecha, bool camara}) exifDe(Uint8List b) {
  try {
    for (final _Segmento s in _segmentosJpeg(b)) {
      if (s.marca != 0xE1 || s.fin - s.inicio < 14) continue;
      //  "Exif\0\0" y después el bloque TIFF, con sus propios desplazamientos.
      if (b[s.inicio] != 0x45 || b[s.inicio + 1] != 0x78 ||
          b[s.inicio + 2] != 0x69 || b[s.inicio + 3] != 0x66) {
        continue;
      }
      final int t = s.inicio + 6;
      final bool grande = b[t] == 0x4D && b[t + 1] == 0x4D;
      if (!grande && !(b[t] == 0x49 && b[t + 1] == 0x49)) continue;
      String? fecha;
      bool camara = false;
      int? exifIfd;
      for (final _Entrada e in _entradas(b, t, _u32(b, t + 4, grande), s.fin, grande)) {
        if (e.etiqueta == 0x010F) {
          camara = (_texto(b, t, e, s.fin) ?? '').trim().isNotEmpty;
        } else if (e.etiqueta == 0x8769) {
          exifIfd = e.valor;
        }
      }
      if (exifIfd != null) {
        for (final _Entrada e in _entradas(b, t, exifIfd, s.fin, grande)) {
          if (e.etiqueta == 0x9003) fecha = _fechaExif(_texto(b, t, e, s.fin));
        }
      }
      return (fecha: fecha, camara: camara);
    }
  } catch (_) {}
  return (fecha: null, camara: false);
}

/// Lo que sube con la evidencia. Solo las claves que se pudieron leer: una
/// clave ausente significa «no se sabe», nunca «no».
Map<String, dynamic> origenDeLaImagen({
  required Uint8List bytes,
  required String nombre,
  int? pantallaAncho,
  int? pantallaAlto,
}) {
  final ({int ancho, int alto})? tamano = tamanoDeImagen(bytes);
  final ({String? fecha, bool camara}) exif = exifDe(bytes);
  final String? delNombre = fechaSegunElNombre(nombre);
  return <String, dynamic>{
    'origen_version': versionDelOrigen,
    if (tamano != null) 'imagen_ancho': tamano.ancho,
    if (tamano != null) 'imagen_alto': tamano.alto,
    if (pantallaAncho != null && pantallaAncho > 0) 'pantalla_ancho': pantallaAncho,
    if (pantallaAlto != null && pantallaAlto > 0) 'pantalla_alto': pantallaAlto,
    'nombre_dice_captura': nombreDiceCaptura(nombre),
    'fecha_segun_nombre': ?delNombre,
    if (exif.fecha != null) 'exif_fecha': exif.fecha,
    'exif_camara': exif.camara,
  };
}

/// Lo mismo, leyendo el archivo. NUNCA LEVANTA: si no se puede leer devuelve
/// un mapa vacío y la evidencia sigue su camino sin estos datos.
Future<Map<String, dynamic>> leerOrigenDeLaImagen(
  String ruta, {
  required String nombre,
  int? pantallaAncho,
  int? pantallaAlto,
}) async {
  try {
    final Uint8List bytes = await File(ruta).readAsBytes();
    return origenDeLaImagen(
      bytes: bytes,
      nombre: nombre,
      pantallaAncho: pantallaAncho,
      pantallaAlto: pantallaAlto,
    );
  } catch (_) {
    return <String, dynamic>{};
  }
}

// ---------------------------------------------------------------------------
//  Lectura de bytes. Todo acotado: un archivo cortado no puede leer fuera.
// ---------------------------------------------------------------------------

class _Segmento {
  const _Segmento(this.marca, this.inicio, this.fin);
  final int marca;
  final int inicio;
  final int fin;
}

class _Entrada {
  const _Entrada(this.etiqueta, this.tipo, this.cuenta, this.valor, this.donde);
  final int etiqueta;
  final int tipo;
  final int cuenta;
  final int valor;

  /// Dónde están los 4 bytes del valor, para un texto corto que cabe ahí.
  final int donde;
}

Iterable<_Segmento> _segmentosJpeg(Uint8List b) sync* {
  if (b.length < 4 || b[0] != 0xFF || b[1] != 0xD8) return;
  int p = 2;
  //  El tope de vueltas es el seguro contra un archivo que se apunta a sí
  //  mismo: un JPEG de verdad tiene decenas de segmentos, no miles.
  for (int vueltas = 0; vueltas < 512 && p + 4 <= b.length; vueltas++) {
    if (b[p] != 0xFF) return;
    final int marca = b[p + 1];
    if (marca == 0xFF) {
      p += 1;
      continue;
    }
    if (marca == 0xD8 || marca == 0x01 || (marca >= 0xD0 && marca <= 0xD7)) {
      p += 2;
      continue;
    }
    if (marca == 0xDA || marca == 0xD9) return;
    final int largo = _u16(b, p + 2, true);
    if (largo < 2) return;
    final int fin = p + 2 + largo;
    if (fin > b.length) return;
    yield _Segmento(marca, p + 4, fin);
    p = fin;
  }
}

Iterable<_Entrada> _entradas(
    Uint8List b, int tiff, int desde, int fin, bool grande) sync* {
  final int base = tiff + desde;
  if (desde <= 0 || base + 2 > fin) return;
  final int cuantas = _u16(b, base, grande);
  for (int i = 0; i < cuantas && i < 256; i++) {
    final int e = base + 2 + i * 12;
    if (e + 12 > fin) return;
    yield _Entrada(_u16(b, e, grande), _u16(b, e + 2, grande),
        _u32(b, e + 4, grande), _u32(b, e + 8, grande), e + 8);
  }
}

String? _texto(Uint8List b, int tiff, _Entrada e, int fin) {
  if (e.tipo != 2 || e.cuenta <= 0 || e.cuenta > 64) return null;
  final int desde = e.cuenta <= 4 ? e.donde : tiff + e.valor;
  if (desde < 0 || desde + e.cuenta > fin) return null;
  final StringBuffer s = StringBuffer();
  for (int i = 0; i < e.cuenta; i++) {
    final int c = b[desde + i];
    if (c == 0) break;
    if (c < 0x20 || c > 0x7E) return null;
    s.writeCharCode(c);
  }
  return s.toString();
}

/// EXIF escribe `2026:11:21 09:23:01`. Sale en ISO sin zona, igual que la
/// del nombre, para que el servidor lea una sola forma.
String? _fechaExif(String? crudo) {
  if (crudo == null) return null;
  final RegExpMatch? m =
      RegExp(r'^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})$')
          .firstMatch(crudo.trim());
  if (m == null) return null;
  final List<int> p = <int>[for (int i = 1; i <= 6; i++) int.parse(m.group(i)!)];
  if (!_esFecha(p[0], p[1], p[2]) || p[3] >= 24 || p[4] >= 60 || p[5] >= 60) {
    return null;
  }
  return '${_dd(p[0], 4)}-${_dd(p[1])}-${_dd(p[2])}'
      'T${_dd(p[3])}:${_dd(p[4])}:${_dd(p[5])}';
}

/// Una fecha que existe en el calendario. `DateTime` acepta el 31 de
/// febrero y lo corre a marzo: por eso se compara contra lo que devuelve.
bool _esFecha(int a, int m, int d) {
  if (a < 2000 || a > 2099 || m < 1 || m > 12 || d < 1 || d > 31) return false;
  final DateTime f = DateTime(a, m, d);
  return f.year == a && f.month == m && f.day == d;
}

String _dd(int n, [int ancho = 2]) => n.toString().padLeft(ancho, '0');

int _u16(Uint8List b, int p, bool grande) =>
    grande ? (b[p] << 8) | b[p + 1] : (b[p + 1] << 8) | b[p];

int _u32(Uint8List b, int p, bool grande) => grande
    ? (b[p] << 24) | (b[p + 1] << 16) | (b[p + 2] << 8) | b[p + 3]
    : (b[p + 3] << 24) | (b[p + 2] << 16) | (b[p + 1] << 8) | b[p];
