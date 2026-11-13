/// BANCO DE PRUEBA DE LA MARCA DE AGUA (13/11/2026). NO ES PRODUCTO.
///
/// Para ver cómo va quedando la marca sin servidor, sin sesión y sin una
/// orden: se abre sola, toma una foto con la cámara (la del emulador también
/// sirve) y deja prender y apagar cada opción de Programación.
///
///     flutter run -t lib/vista_previa/marca_de_agua_main.dart
///
/// Es otro punto de entrada: la app de los técnicos (`lib/main.dart`) no lo
/// importa, así que no viaja en su APK. Dibuja con el MISMO widget que la
/// pantalla de ejecución (`FotoConMarca`), así que lo que se ve acá es lo que
/// ve el técnico.
library;

import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../core/marca/marca_de_agua.dart';

void main() => runApp(const _Banco());

class _Banco extends StatelessWidget {
  const _Banco();

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Marca de agua',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorSchemeSeed: const Color(0xFF1F5FAF)),
        home: const _PantallaDelBanco(),
      );
}

/// Las situaciones de ubicación que la app de verdad produce.
enum _Ubicacion {
  buena('GPS bueno (±8 m)'),
  triangulada('Triangulada (±2000 m)'),
  sinGps('Sin GPS (apagado)'),
  simulada('Ubicación simulada'),
  galeria('Foto de galería');

  const _Ubicacion(this.texto);
  final String texto;

  Map<String, dynamic> get metadatos => switch (this) {
        _Ubicacion.buena => <String, dynamic>{
            'lat': 10.9108, 'lng': -74.8186, 'precision_m': 8},
        _Ubicacion.triangulada => <String, dynamic>{
            'lat': 10.9108, 'lng': -74.8186, 'precision_m': 2000},
        _Ubicacion.sinGps => <String, dynamic>{
            'ubicacion_motivo': 'servicio_apagado'},
        _Ubicacion.simulada => <String, dynamic>{
            'lat': 10.9108, 'lng': -74.8186, 'precision_m': 5,
            'ubicacion_simulada': true},
        _Ubicacion.galeria => <String, dynamic>{
            'lat': 10.9108, 'lng': -74.8186, 'de_galeria': true},
      };
}

class _PantallaDelBanco extends StatefulWidget {
  const _PantallaDelBanco();

  @override
  State<_PantallaDelBanco> createState() => _EstadoDelBanco();
}

class _EstadoDelBanco extends State<_PantallaDelBanco> {
  ConfiguracionDeMarca _config = const ConfiguracionDeMarca(
    activa: true,
    mostrarLogo: true,
    mostrarEmpresa: true,
    mostrarTecnico: true,
    mostrarFecha: true,
    mostrarCoordenadas: true,
  );
  String _empresa = 'Rapilink SAS';
  String _tecnico = 'Carlos Pérez';
  _Ubicacion _ubicacion = _Ubicacion.buena;
  bool _vertical = false;
  ImageProvider? _foto;
  Uint8List? _logo;
  final ImagePicker _picker = ImagePicker();
  final DateTime _cuando = DateTime.now();

  @override
  void initState() {
    super.initState();
    _prepararEjemplos();
  }

  Future<void> _prepararEjemplos() async {
    final Uint8List foto = await _escenaDeEjemplo(_vertical);
    final Uint8List logo = await _logoDeEjemplo();
    if (!mounted) return;
    setState(() {
      _foto = MemoryImage(foto);
      _logo = logo;
    });
  }

  Future<void> _tomar(ImageSource fuente) async {
    //  Los mismos parámetros que la pantalla de ejecución: la foto que se ve
    //  acá tiene el tamaño de la que sube.
    final XFile? f = await _picker.pickImage(
      source: fuente,
      imageQuality: 85,
      maxWidth: 1920,
    );
    if (f == null) return;
    final Uint8List bytes = await f.readAsBytes();
    if (!mounted) return;
    setState(() {
      _foto = MemoryImage(bytes);
      if (fuente == ImageSource.gallery) _ubicacion = _Ubicacion.galeria;
    });
  }

  @override
  Widget build(BuildContext context) {
    final DatosDeLaFoto datos = DatosDeLaFoto(
      empresa: _empresa,
      tecnico: _tecnico,
      fecha: _cuando,
      metadatos: _ubicacion.metadatos,
    );

    return Scaffold(
      appBar: AppBar(title: const Text('Marca de agua · vista previa')),
      body: Column(
        children: <Widget>[
          Container(
            color: Colors.black,
            height: MediaQuery.sizeOf(context).height * 0.42,
            width: double.infinity,
            child: _foto == null
                ? const Center(child: CircularProgressIndicator())
                : InteractiveViewer(
                    maxScale: 6,
                    child: Center(
                      child: FotoConMarca(
                        imagen: _foto!,
                        configuracion: _config,
                        datos: datos,
                        logo: _logo,
                      ),
                    ),
                  ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: FilledButton.icon(
                    icon: const Icon(Icons.photo_camera),
                    label: const Text('Tomar foto'),
                    onPressed: () => _tomar(ImageSource.camera),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.photo_library_outlined),
                    label: const Text('Galería'),
                    onPressed: () => _tomar(ImageSource.gallery),
                  ),
                ),
              ],
            ),
          ),
          Expanded(child: _controles()),
        ],
      ),
    );
  }

  Widget _controles() {
    Widget casilla(String t, bool v, ConfiguracionDeMarca Function(bool) c) =>
        SwitchListTile(
          dense: true,
          title: Text(t),
          value: v,
          onChanged: (bool n) => setState(() => _config = c(n)),
        );

    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: <Widget>[
        casilla('Marca prendida', _config.activa,
            (bool v) => _config.copyWith(activa: v)),
        casilla('Logo', _config.mostrarLogo,
            (bool v) => _config.copyWith(mostrarLogo: v)),
        casilla('Nombre de la empresa', _config.mostrarEmpresa,
            (bool v) => _config.copyWith(mostrarEmpresa: v)),
        casilla('Técnico', _config.mostrarTecnico,
            (bool v) => _config.copyWith(mostrarTecnico: v)),
        casilla('Fecha y hora', _config.mostrarFecha,
            (bool v) => _config.copyWith(mostrarFecha: v)),
        casilla('Coordenadas', _config.mostrarCoordenadas,
            (bool v) => _config.copyWith(mostrarCoordenadas: v)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: DropdownButtonFormField<String>(
            initialValue: _config.posicion,
            decoration: const InputDecoration(labelText: 'Posición'),
            items: const <DropdownMenuItem<String>>[
              DropdownMenuItem<String>(
                  value: 'abajo_izquierda', child: Text('Abajo a la izquierda')),
              DropdownMenuItem<String>(
                  value: 'abajo_derecha', child: Text('Abajo a la derecha')),
              DropdownMenuItem<String>(
                  value: 'arriba_izquierda', child: Text('Arriba a la izquierda')),
              DropdownMenuItem<String>(
                  value: 'arriba_derecha', child: Text('Arriba a la derecha')),
            ],
            onChanged: (String? v) =>
                setState(() => _config = _config.copyWith(posicion: v)),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: <Widget>[
              Text('Opacidad ${_config.opacidad}%'),
              Expanded(
                child: Slider(
                  min: 10,
                  max: 100,
                  divisions: 18,
                  value: _config.opacidad.toDouble(),
                  onChanged: (double v) => setState(
                      () => _config = _config.copyWith(opacidad: v.round())),
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: TextFormField(
            maxLength: 80,
            decoration: const InputDecoration(labelText: 'Texto extra'),
            onChanged: (String v) =>
                setState(() => _config = _config.copyWith(textoExtra: v)),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: TextFormField(
            initialValue: _empresa,
            decoration: const InputDecoration(labelText: 'Empresa (ejemplo)'),
            onChanged: (String v) => setState(() => _empresa = v),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: TextFormField(
            initialValue: _tecnico,
            decoration: const InputDecoration(labelText: 'Técnico (ejemplo)'),
            onChanged: (String v) => setState(() => _tecnico = v),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: DropdownButtonFormField<_Ubicacion>(
            initialValue: _ubicacion,
            decoration: const InputDecoration(labelText: 'Ubicación de la foto'),
            items: <DropdownMenuItem<_Ubicacion>>[
              for (final _Ubicacion u in _Ubicacion.values)
                DropdownMenuItem<_Ubicacion>(value: u, child: Text(u.texto)),
            ],
            onChanged: (_Ubicacion? u) =>
                setState(() => _ubicacion = u ?? _Ubicacion.buena),
          ),
        ),
        SwitchListTile(
          dense: true,
          title: const Text('Foto de ejemplo vertical'),
          value: _vertical,
          onChanged: (bool v) {
            setState(() => _vertical = v);
            _prepararEjemplos();
          },
        ),
      ],
    );
  }
}

/// Una escena de ejemplo: cielo, pared y una caja de fibra. Dibujada con el
/// motor de Flutter para no meter fotos en el repositorio.
Future<Uint8List> _escenaDeEjemplo(bool vertical) async {
  final int w = vertical ? 1080 : 1920;
  final int h = vertical ? 1920 : 1080;
  final ui.PictureRecorder r = ui.PictureRecorder();
  final Canvas c = Canvas(r);
  final Rect todo = Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble());
  c.drawRect(
    todo,
    Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: <Color>[Color(0xFF8EC5E8), Color(0xFFD9CBB0), Color(0xFFB79E7C)],
        stops: <double>[0, 0.55, 1],
      ).createShader(todo),
  );
  final double cx = w / 2, cy = h * 0.5;
  final Rect caja = Rect.fromCenter(
      center: Offset(cx, cy), width: w * 0.28, height: h * 0.26);
  c.drawRRect(RRect.fromRectAndRadius(caja, const Radius.circular(18)),
      Paint()..color = const Color(0xFFF2F2F2));
  c.drawRRect(
      RRect.fromRectAndRadius(caja.deflate(caja.width * 0.12),
          const Radius.circular(10)),
      Paint()..color = const Color(0xFF3A3F45));
  for (int i = 0; i < 4; i++) {
    c.drawCircle(
        Offset(caja.left + caja.width * (0.3 + 0.13 * i), caja.center.dy),
        caja.width * 0.035,
        Paint()..color = i == 1 ? const Color(0xFF2ECC71) : const Color(0xFF1ABC9C));
  }
  c.drawLine(Offset(caja.center.dx, caja.bottom), Offset(cx * 0.6, h.toDouble()),
      Paint()
        ..color = const Color(0xFFFFD000)
        ..strokeWidth = w * 0.006);
  final ui.Image img = await r.endRecording().toImage(w, h);
  final ByteData? b = await img.toByteData(format: ui.ImageByteFormat.png);
  return b!.buffer.asUint8List();
}

/// Un logo de ejemplo, cuadrado y con transparencia, como los que se suben.
Future<Uint8List> _logoDeEjemplo() async {
  const int t = 256;
  final ui.PictureRecorder r = ui.PictureRecorder();
  final Canvas c = Canvas(r);
  c.drawCircle(const Offset(t / 2, t / 2), t / 2,
      Paint()..color = const Color(0xFF1F5FAF));
  final TextPainter tp = TextPainter(
    text: const TextSpan(
      text: 'R',
      style: TextStyle(
          color: Colors.white, fontSize: 170, fontWeight: FontWeight.w800),
    ),
    textDirection: TextDirection.ltr,
  )..layout();
  tp.paint(c, Offset((t - tp.width) / 2, (t - tp.height) / 2));
  final ui.Image img = await r.endRecording().toImage(t, t);
  final ByteData? b = await img.toByteData(format: ui.ImageByteFormat.png);
  return b!.buffer.asUint8List();
}
