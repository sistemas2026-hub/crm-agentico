/// LA MARCA DE AGUA, VISTA DESDE EL TELÉFONO (13/11/2026).
///
/// EL PEDIDO
/// ---------
/// El usuario quiere ver la marca en el teléfono al tomar la foto, no recién
/// cuando la foto llega a la plataforma.
///
/// LO QUE ESTO HACE, Y LO QUE NO
/// -----------------------------
/// El archivo lo sigue estampando SOLO el servidor
/// (`campo/services/marca_de_agua.py`), cuando la foto sube. Este archivo
/// **dibuja encima** de la foto la misma banda, con la misma configuración de
/// la empresa, para que el técnico vea lo que va a quedar. No toca el archivo.
///
/// Por qué no se estampa también acá: la foto saldría con dos bandas, y si el
/// servidor aceptara «ya viene marcada», el teléfono tendría la forma de
/// apagar la marca que lo certifica -- el mismo agujero que el servidor cerró
/// cuando dejó de creerle al tipo de archivo declarado.
///
/// UNA COPIA DE LAS REGLAS DEL SERVIDOR, Y POR ESO TIENE PRUEBAS ESPEJO
/// --------------------------------------------------------------------
/// `lineasDe`, `seEstampa` y `aLaDerecha` repiten `lineas_de`, `_se_estampa`
/// y `a_la_derecha` del servidor. `test/marca_de_agua_test.dart` repite los
/// mismos casos que `campo/tests/test_marca_de_agua.py`: si alguien cambia una
/// regla de un lado, la prueba del otro lado es la que lo dice. Lo que NO es
/// idéntico, y queda dicho: la letra. El servidor usa DejaVu Sans; el teléfono
/// usa la de la app. El tamaño, la posición y el texto son los mismos.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';

/// Lo que la empresa eligió en Programación. Llega del servidor.
@immutable
class ConfiguracionDeMarca {
  const ConfiguracionDeMarca({
    this.activa = false,
    this.mostrarLogo = false,
    this.mostrarEmpresa = false,
    this.mostrarTecnico = false,
    this.mostrarFecha = false,
    this.mostrarCoordenadas = false,
    this.estamparCapturas = false,
    this.posicion = 'abajo_izquierda',
    this.opacidad = 55,
    this.textoExtra = '',
  });

  /// La que rige sin datos del servidor: apagada, igual que `APAGADA` allá.
  /// El teléfono no puede prometer una banda que la foto no va a llevar.
  static const ConfiguracionDeMarca apagada = ConfiguracionDeMarca();

  final bool activa;
  final bool mostrarLogo;
  final bool mostrarEmpresa;
  final bool mostrarTecnico;
  final bool mostrarFecha;
  final bool mostrarCoordenadas;
  final bool estamparCapturas;
  final String posicion;
  final int opacidad;
  final String textoExtra;

  /// Cada casilla se compara contra `true`: de la API llega JSON, y `"si"` o
  /// `1` no son la marca. Lo dudoso cae a apagado.
  factory ConfiguracionDeMarca.fromJson(Map<String, dynamic>? j) {
    if (j == null) return apagada;
    final dynamic op = j['opacidad'];
    return ConfiguracionDeMarca(
      activa: j['activa'] == true,
      mostrarLogo: j['mostrar_logo'] == true,
      mostrarEmpresa: j['mostrar_empresa'] == true,
      mostrarTecnico: j['mostrar_tecnico'] == true,
      mostrarFecha: j['mostrar_fecha'] == true,
      mostrarCoordenadas: j['mostrar_coordenadas'] == true,
      estamparCapturas: j['estampar_capturas'] == true,
      posicion: (j['posicion'] ?? 'abajo_izquierda').toString(),
      opacidad: op is int ? op : 55,
      textoExtra: (j['texto_extra'] ?? '').toString(),
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'activa': activa,
        'mostrar_logo': mostrarLogo,
        'mostrar_empresa': mostrarEmpresa,
        'mostrar_tecnico': mostrarTecnico,
        'mostrar_fecha': mostrarFecha,
        'mostrar_coordenadas': mostrarCoordenadas,
        'estampar_capturas': estamparCapturas,
        'posicion': posicion,
        'opacidad': opacidad,
        'texto_extra': textoExtra,
      };

  ConfiguracionDeMarca copyWith({
    bool? activa,
    bool? mostrarLogo,
    bool? mostrarEmpresa,
    bool? mostrarTecnico,
    bool? mostrarFecha,
    bool? mostrarCoordenadas,
    bool? estamparCapturas,
    String? posicion,
    int? opacidad,
    String? textoExtra,
  }) =>
      ConfiguracionDeMarca(
        activa: activa ?? this.activa,
        mostrarLogo: mostrarLogo ?? this.mostrarLogo,
        mostrarEmpresa: mostrarEmpresa ?? this.mostrarEmpresa,
        mostrarTecnico: mostrarTecnico ?? this.mostrarTecnico,
        mostrarFecha: mostrarFecha ?? this.mostrarFecha,
        mostrarCoordenadas: mostrarCoordenadas ?? this.mostrarCoordenadas,
        estamparCapturas: estamparCapturas ?? this.estamparCapturas,
        posicion: posicion ?? this.posicion,
        opacidad: opacidad ?? this.opacidad,
        textoExtra: textoExtra ?? this.textoExtra,
      );
}

/// Lo que se sabe de ESTA foto. Ninguna de estas cosas se inventa acá.
@immutable
class DatosDeLaFoto {
  const DatosDeLaFoto({
    this.empresa = '',
    this.tecnico = '',
    this.fecha,
    this.metadatos = const <String, dynamic>{},
    this.esCaptura = false,
    this.esFirma = false,
  });

  final String empresa;
  final String tecnico;

  /// El instante del obturador -- el mismo `capturada_en` que sube.
  final DateTime? fecha;

  /// Los `metadatos_captura` que viajan con la evidencia: `lat`, `lng`,
  /// `precision_m`, `ubicacion_simulada`, `ubicacion_motivo`, `de_galeria`.
  final Map<String, dynamic> metadatos;
  final bool esCaptura;
  final bool esFirma;
}

/// Los motivos que la app emite (`ubicacion_de_captura.dart`), traducidos
/// igual que `MOTIVOS_DE_UBICACION` en el servidor. Un motivo que no está
/// acá no se imprime: el servidor tampoco lo imprime.
const Map<String, String> motivosDeUbicacion = <String, String>{
  'servicio_apagado': 'GPS apagado',
  'permiso_denegado': 'sin permiso de ubicacion',
  'sin_senal_gps': 'sin señal GPS',
};

/// Si el logo y el texto van contra el borde derecho. Espejo de
/// `a_la_derecha` del servidor.
bool aLaDerecha(String posicion) => posicion.endsWith('derecha');

/// Si es la firma del cliente. Espejo de `_es_firma`: la firma no lleva marca
/// porque el logo encima la tapa.
bool esRequisitoDeFirma(String requisitoId) {
  final String rid = requisitoId.trim().toLowerCase();
  return rid == 'firma_receptor' || rid == 'firma' || rid.startsWith('firma_');
}

/// Bogotá no tiene horario de verano: UTC-5 todo el año. Se calcula así y no
/// con la hora del teléfono porque el servidor estampa en hora de Colombia
/// aunque el aparato esté configurado en otra zona.
String fechaDeLaMarca(DateTime cuando) {
  final DateTime b = cuando.toUtc().subtract(const Duration(hours: 5));
  String dos(int n) => n.toString().padLeft(2, '0');
  return '${dos(b.day)}/${dos(b.month)}/${b.year} ${dos(b.hour)}:${dos(b.minute)}';
}

String _textoDeCoordenada(Map<String, dynamic> m) {
  if (!m.containsKey('lat') || !m.containsKey('lng')) {
    final String motivo = (m['ubicacion_motivo'] ?? '').toString().trim();
    String? legible = motivosDeUbicacion[motivo];
    if (legible == null && motivo.startsWith('error_')) {
      legible = 'error del sistema';
    }
    return legible != null ? 'Sin ubicacion ($legible)' : 'Sin ubicacion';
  }

  final double? lat = double.tryParse(m['lat'].toString());
  final double? lng = double.tryParse(m['lng'].toString());
  if (lat == null || lng == null) return 'Sin ubicacion';

  final double precision =
      double.tryParse((m['precision_m'] ?? 0).toString()) ?? 0;
  final int decimales = precision > 500 ? 3 : (precision > 50 ? 4 : 6);

  String texto =
      '${lat.toStringAsFixed(decimales)}, ${lng.toStringAsFixed(decimales)}';
  if (precision > 0) texto += ' (±${precision.toInt()} m)';
  if (m['ubicacion_simulada'] == true) texto += '  (ubicacion no verificada)';
  return texto;
}

/// Qué dice la banda. Espejo de `lineas_de` del servidor.
List<String> lineasDe(ConfiguracionDeMarca c, DatosDeLaFoto d) {
  final List<String> lineas = <String>[];
  if (c.mostrarEmpresa && d.empresa.isNotEmpty) lineas.add(d.empresa);
  if (c.mostrarTecnico && d.tecnico.isNotEmpty) lineas.add(d.tecnico);
  if (c.mostrarFecha && d.fecha != null) lineas.add(fechaDeLaMarca(d.fecha!));
  if (c.mostrarCoordenadas) {
    if (d.metadatos['de_galeria'] == true) {
      lineas.add('Imagen de galeria (sin ubicacion de captura)');
    } else {
      lineas.add(_textoDeCoordenada(d.metadatos));
    }
  }
  final String extra = c.textoExtra.trim();
  if (extra.isNotEmpty) lineas.add(extra);
  return lineas;
}

/// Si esta foto va a llevar banda. Espejo de `_se_estampa` + la salida
/// temprana de `estampar` (sin nada que decir, no se dibuja).
bool seEstampa(ConfiguracionDeMarca c, DatosDeLaFoto d, {bool hayLogo = false}) {
  if (!c.activa) return false;
  if (d.esFirma) return false;
  if (d.esCaptura && !c.estamparCapturas) return false;
  return lineasDe(c, d).isNotEmpty || (c.mostrarLogo && hayLogo);
}

/// Las medidas de la banda, en PÍXELES DE LA FOTO. Son las del servidor
/// (`_dibujar`), número por número: por eso la banda se dibuja sobre una caja
/// del tamaño real de la foto y después se escala entera.
@immutable
class MedidasDeBanda {
  factory MedidasDeBanda.para(Size foto, int nLineas) {
    final double corto =
        foto.width < foto.height ? foto.width : foto.height;
    final int unidad = (corto * 0.055).floor();
    final int alto = unidad * (nLineas < 1 ? 1 : nLineas);
    final int letra = (corto * 0.055 * 0.6).floor();
    final int margen = (corto * 0.012).floor();
    return MedidasDeBanda._(
      alto: alto.toDouble(),
      letra: (letra < 11 ? 11 : letra).toDouble(),
      margen: (margen < 8 ? 8 : margen).toDouble(),
    );
  }

  const MedidasDeBanda._({
    required this.alto,
    required this.letra,
    required this.margen,
  });

  final double alto;
  final double letra;
  final double margen;
}

/// La banda sola, en píxeles de la foto. [ancho] es el ancho de la foto.
class BandaDeMarca extends StatelessWidget {
  const BandaDeMarca({
    super.key,
    required this.ancho,
    required this.medidas,
    required this.lineas,
    required this.configuracion,
    this.logo,
  });

  final double ancho;
  final MedidasDeBanda medidas;
  final List<String> lineas;
  final ConfiguracionDeMarca configuracion;
  final Uint8List? logo;

  @override
  Widget build(BuildContext context) {
    final bool derecha = aLaDerecha(configuracion.posicion);
    //  `or 55` en el servidor: una opacidad 0 o ausente es 55, no invisible.
    final int op = (configuracion.opacidad == 0 ? 55 : configuracion.opacidad)
        .clamp(0, 100);
    final double m = medidas.margen;
    final double altoLogo = medidas.alto - m;
    final bool conLogo =
        configuracion.mostrarLogo && logo != null && logo!.isNotEmpty;
    final double yTexto =
        ((medidas.alto - medidas.letra * lineas.length) / 2).floorToDouble();

    final Widget textos = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment:
          derecha ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      children: <Widget>[
        for (final String l in lineas)
          SizedBox(
            height: medidas.letra,
            child: Text(
              l,
              maxLines: 1,
              softWrap: false,
              overflow: TextOverflow.visible,
              style: TextStyle(
                color: Colors.white,
                fontSize: medidas.letra,
                height: 1.0,
                fontWeight: FontWeight.w400,
                decoration: TextDecoration.none,
              ),
            ),
          ),
      ],
    );

    final Widget? imagenLogo = conLogo
        ? Image.memory(
            logo!,
            height: altoLogo,
            fit: BoxFit.contain,
            gaplessPlayback: true,
            //  El logo no puede costar la marca: si no abre, va el texto solo.
            errorBuilder: (_, _, _) => const SizedBox.shrink(),
          )
        : null;

    return SizedBox(
      width: ancho,
      height: medidas.alto,
      child: ColoredBox(
        color: Color.fromARGB((255 * op / 100).round(), 0, 0, 0),
        child: Padding(
          //  Margen a los dos lados; la fila se invierte a la derecha, y así
          //  el logo queda contra el borde que corresponde, como en
          //  `_dibujar` (`x_logo = ancho - margen - logo` del lado derecho).
          padding: EdgeInsets.symmetric(horizontal: m),
          child: Row(
            textDirection: derecha ? TextDirection.rtl : TextDirection.ltr,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              if (imagenLogo != null) ...<Widget>[
                Padding(
                  padding: EdgeInsets.only(top: (m / 2).floorToDouble()),
                  child: imagenLogo,
                ),
                SizedBox(width: m),
              ],
              Expanded(
                child: Padding(
                  padding: EdgeInsets.only(top: yTexto < 0 ? 0 : yTexto),
                  child: Align(
                    alignment:
                        derecha ? Alignment.topRight : Alignment.topLeft,
                    child: textos,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Una foto con la banda que va a llevar, escalada como un todo.
///
/// La foto y la banda se arman en una caja del tamaño REAL de la imagen
/// (p. ej. 1920×1080) y `FittedBox` escala las dos juntas: así la banda ocupa
/// en pantalla exactamente la proporción que va a ocupar en el archivo, sea
/// una miniatura de 180 px o la pantalla completa.
class FotoConMarca extends StatefulWidget {
  const FotoConMarca({
    super.key,
    required this.imagen,
    required this.configuracion,
    required this.datos,
    this.logo,
    this.ajuste = BoxFit.contain,
  });

  final ImageProvider imagen;
  final ConfiguracionDeMarca configuracion;
  final DatosDeLaFoto datos;
  final Uint8List? logo;
  final BoxFit ajuste;

  @override
  State<FotoConMarca> createState() => _FotoConMarcaState();
}

class _FotoConMarcaState extends State<FotoConMarca> {
  Size? _tamano;
  bool _fallo = false;
  ImageStream? _flujo;
  ImageStreamListener? _oyente;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _resolver();
  }

  @override
  void didUpdateWidget(FotoConMarca anterior) {
    super.didUpdateWidget(anterior);
    if (anterior.imagen != widget.imagen) _resolver();
  }

  void _resolver() {
    final ImageStream flujo =
        widget.imagen.resolve(createLocalImageConfiguration(context));
    if (flujo.key == _flujo?.key) return;
    _soltar();
    _flujo = flujo;
    _oyente = ImageStreamListener(
      (ImageInfo info, bool _) {
        if (!mounted) return;
        setState(() {
          _tamano = Size(
            info.image.width.toDouble(),
            info.image.height.toDouble(),
          );
          _fallo = false;
        });
      },
      onError: (Object _, StackTrace? _) {
        if (mounted) setState(() => _fallo = true);
      },
    );
    flujo.addListener(_oyente!);
  }

  void _soltar() {
    if (_flujo != null && _oyente != null) _flujo!.removeListener(_oyente!);
  }

  @override
  void dispose() {
    _soltar();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_fallo) {
      return const Center(child: Text('No se puede cargar la vista previa'));
    }
    final Size? t = _tamano;
    if (t == null) {
      //  QUIETO, NO UN INDICADOR QUE GIRA. Una foto local se decodifica en
      //  milisegundos; un indicador animado no le dice nada al técnico y, si
      //  la imagen no termina de resolverse, deja la pantalla animándose para
      //  siempre (las pruebas de Ejecución lo midieron: `pumpAndSettle` no
      //  terminaba nunca).
      return const Center(
        child: Icon(Icons.image_outlined, color: Colors.white38, size: 28),
      );
    }

    final bool hayLogo = widget.logo != null && widget.logo!.isNotEmpty;
    final bool conBanda =
        seEstampa(widget.configuracion, widget.datos, hayLogo: hayLogo);
    final List<String> lineas =
        conBanda ? lineasDe(widget.configuracion, widget.datos) : <String>[];
    final MedidasDeBanda medidas = MedidasDeBanda.para(t, lineas.length);
    final bool arriba = widget.configuracion.posicion.startsWith('arriba');

    return FittedBox(
      fit: widget.ajuste,
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        width: t.width,
        height: t.height,
        child: Stack(
          children: <Widget>[
            Positioned.fill(
              child: Image(
                image: widget.imagen,
                fit: BoxFit.fill,
                gaplessPlayback: true,
              ),
            ),
            if (conBanda)
              Positioned(
                left: 0,
                right: 0,
                top: arriba ? 0 : null,
                bottom: arriba ? null : 0,
                child: BandaDeMarca(
                  key: const ValueKey<String>('banda_de_marca'),
                  ancho: t.width,
                  medidas: medidas,
                  lineas: lineas,
                  configuracion: widget.configuracion,
                  logo: widget.logo,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
