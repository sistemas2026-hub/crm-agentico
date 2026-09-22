import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../../core/storage/evidencia_storage_service.dart';
import '../../../core/storage/local_database.dart';
import '../../../core/sync/sync_queue_service.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radius.dart';
import '../../../core/theme/app_typography.dart';

/// La conformidad del cliente, firmada con el dedo.
///
/// UNA FIRMA ES UNA EVIDENCIA
/// --------------------------
/// Esa es toda la decisión de diseño, y es la que hace que este archivo sea
/// corto. La firma no estrena un mecanismo propio: se guarda como imagen, se
/// encola como evidencia y hereda de un saque todo lo que ya se construyó —
/// la ruta con la identidad adentro, la cola offline con su idempotencia, el
/// reintento con espera, la protección al cerrar sesión.
///
/// Un camino nuevo habría significado repetir esas cuatro cosas y descubrir,
/// meses después, que una de ellas quedó sin hacer justo para el documento que
/// prueba que el cliente aceptó el trabajo.
///
/// LO QUE SE MUESTRA ANTES DE FIRMAR
/// ---------------------------------
/// Quien firma tiene que ver qué está aceptando: qué se hizo, qué equipos
/// quedaron instalados y con qué números de serie. Una pantalla que solo pide
/// el dedo sobre un recuadro en blanco no recoge una conformidad, recoge un
/// trazo.
class FirmaDelCliente extends StatefulWidget {
  const FirmaDelCliente({
    super.key,
    required this.orgId,
    required this.profileId,
    required this.ordenId,
    required this.requisitoId,
    required this.resumenDelTrabajo,
    this.materialesInstalados = const <String>[],
    this.baseLocal,
  });

  final String orgId;
  final String profileId;
  final String ordenId;

  /// Con qué requisito del esquema se asocia. Lo declara el tipo de trabajo:
  /// la aplicación no inventa uno.
  final String requisitoId;

  final String resumenDelTrabajo;
  final List<String> materialesInstalados;
  final LocalDatabase? baseLocal;

  static Future<bool?> abrir(
    BuildContext context, {
    required String orgId,
    required String profileId,
    required String ordenId,
    required String requisitoId,
    required String resumenDelTrabajo,
    List<String> materialesInstalados = const <String>[],
    LocalDatabase? baseLocal,
  }) {
    return showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.hoja)),
      ),
      builder: (_) => FirmaDelCliente(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
        requisitoId: requisitoId,
        resumenDelTrabajo: resumenDelTrabajo,
        materialesInstalados: materialesInstalados,
        baseLocal: baseLocal,
      ),
    );
  }

  @override
  State<FirmaDelCliente> createState() => _FirmaDelClienteState();
}

class _FirmaDelClienteState extends State<FirmaDelCliente> {
  late final LocalDatabase _db = widget.baseLocal ?? LocalDatabase();
  final TextEditingController _receptor = TextEditingController();
  final TextEditingController _observaciones = TextEditingController();
  final TrazoDeFirma _trazo = TrazoDeFirma();
  bool _guardando = false;
  String? _error;

  @override
  void dispose() {
    _receptor.dispose();
    _observaciones.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    if (_trazo.vacio) {
      setState(() => _error = 'Falta la firma.');
      return;
    }
    if (_receptor.text.trim().isEmpty) {
      setState(() => _error = 'Falta el nombre de quien recibe.');
      return;
    }

    setState(() {
      _guardando = true;
      _error = null;
    });

    try {
      final bytes = await _trazo.aPng(const Size(600, 300));
      final evidenciaId = const Uuid().v4();

      // Se escribe primero un temporal y se persiste con el mismo servicio que
      // las fotos: así la firma queda bajo org/perfil/orden con su id, igual
      // que cualquier otra evidencia.
      final temporal = File(
        '${(await EvidenciaStorageService.getStorageDirectory()).path}'
        '/firma_$evidenciaId.tmp',
      );
      await temporal.writeAsBytes(bytes);

      final archivo = await EvidenciaStorageService.persistirArchivoCaptura(
        temporal,
        orgId: widget.orgId,
        profileId: widget.profileId,
        ordenId: widget.ordenId,
        evidenciaId: evidenciaId,
      );

      await _db.encolarEvidencia(
        id: evidenciaId,
        orgId: widget.orgId,
        profileId: widget.profileId,
        ordenId: widget.ordenId,
        requisitoId: widget.requisitoId,
        archivoPath: archivo.path,
        sha256: await SyncQueueService.calcularSha256(archivo),
        tamanoBytes: await archivo.length(),
        mimeType: 'image/png',
        registroIdempotencyKey: const Uuid().v4(),
        confirmacionIdempotencyKey: const Uuid().v4(),
      );

      // Quién firmó y qué observó viaja con la orden, no con la imagen: son
      // datos del trabajo, y ahí los puede leer la oficina sin abrir un PNG.
      await _db.saveDatoCampo(
        orgId: widget.orgId,
        profileId: widget.profileId,
        ordenId: widget.ordenId,
        campoClave: 'firma_receptor',
        valor: _receptor.text.trim(),
      );
      if (_observaciones.text.trim().isNotEmpty) {
        await _db.saveDatoCampo(
          orgId: widget.orgId,
          profileId: widget.profileId,
          ordenId: widget.ordenId,
          campoClave: 'firma_observaciones',
          valor: _observaciones.text.trim(),
        );
      }

      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _guardando = false;
        _error = 'No se pudo guardar la firma. Intentá de nuevo.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Conformidad del cliente', style: AppTypography.tituloChico),
              const SizedBox(height: 10),
              // Lo que se está aceptando, antes de pedir el dedo.
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppColors.surfaceContainer,
                  borderRadius: AppRadius.brTarjeta,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(widget.resumenDelTrabajo, style: AppTypography.cuerpo),
                    if (widget.materialesInstalados.isNotEmpty) ...<Widget>[
                      const SizedBox(height: 8),
                      Text('Equipos y materiales instalados',
                          style: AppTypography.etiquetaChica),
                      for (final linea in widget.materialesInstalados)
                        Text('· $linea', style: AppTypography.cuerpoChico),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _receptor,
                decoration: const InputDecoration(
                  labelText: 'Nombre de quien recibe',
                ),
              ),
              TextField(
                controller: _observaciones,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: 'Observaciones (opcional)',
                ),
              ),
              const SizedBox(height: 14),
              Text('Firma', style: AppTypography.etiquetaChica),
              const SizedBox(height: 6),
              Container(
                height: 180,
                decoration: BoxDecoration(
                  color: AppColors.surfaceContainerLowest,
                  borderRadius: AppRadius.brTarjeta,
                  border: Border.all(color: AppColors.outlineVariant),
                ),
                child: LienzoDeFirma(trazo: _trazo),
              ),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: _guardando
                      ? null
                      : () => setState(() => _trazo.limpiar()),
                  child: const Text('Borrar y volver a firmar'),
                ),
              ),
              if (_error != null)
                Text(_error!,
                    style: AppTypography.cuerpoChico
                        .copyWith(color: AppColors.error)),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: FilledButton(
                  onPressed: _guardando ? null : _guardar,
                  child: _guardando
                      ? const SizedBox(
                          width: 18, height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Guardar conformidad'),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Queda en el teléfono y sube cuando haya señal, igual que las '
                'fotografías.',
                style: AppTypography.cuerpoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Los trazos de una firma, y cómo se convierten en imagen.
///
/// Guarda puntos en coordenadas del lienzo y los redibuja a un tamaño fijo al
/// exportar: así la firma se ve igual en un teléfono chico y en una tableta,
/// en vez de salir diminuta o cortada según el aparato donde se firmó.
class TrazoDeFirma extends ChangeNotifier {
  final List<List<Offset>> _trazos = <List<Offset>>[];
  Size _lienzo = Size.zero;

  List<List<Offset>> get trazos => _trazos;
  bool get vacio => _trazos.every((t) => t.length < 2);

  void anotarTamano(Size tamano) => _lienzo = tamano;

  void empezar(Offset punto) {
    _trazos.add(<Offset>[punto]);
    notifyListeners();
  }

  void continuar(Offset punto) {
    if (_trazos.isEmpty) return;
    _trazos.last.add(punto);
    notifyListeners();
  }

  void limpiar() {
    _trazos.clear();
    notifyListeners();
  }

  /// La firma como PNG, a un tamaño estable.
  Future<Uint8List> aPng(Size destino) async {
    final grabador = ui.PictureRecorder();
    final lienzo = Canvas(grabador);

    lienzo.drawRect(
      Rect.fromLTWH(0, 0, destino.width, destino.height),
      Paint()..color = const Color(0xFFFFFFFF),
    );

    final escalaX = _lienzo.width == 0 ? 1.0 : destino.width / _lienzo.width;
    final escalaY = _lienzo.height == 0 ? 1.0 : destino.height / _lienzo.height;
    final pincel = Paint()
      ..color = const Color(0xFF0B1C30)
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    for (final trazo in _trazos) {
      for (var i = 0; i < trazo.length - 1; i++) {
        lienzo.drawLine(
          Offset(trazo[i].dx * escalaX, trazo[i].dy * escalaY),
          Offset(trazo[i + 1].dx * escalaX, trazo[i + 1].dy * escalaY),
          pincel,
        );
      }
    }

    final imagen = await grabador.endRecording().toImage(
          destino.width.round(),
          destino.height.round(),
        );
    final datos = await imagen.toByteData(format: ui.ImageByteFormat.png);
    return datos!.buffer.asUint8List();
  }
}

/// El recuadro donde se firma.
class LienzoDeFirma extends StatelessWidget {
  const LienzoDeFirma({super.key, required this.trazo});

  final TrazoDeFirma trazo;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, restricciones) {
        trazo.anotarTamano(Size(restricciones.maxWidth, restricciones.maxHeight));
        return GestureDetector(
          onPanStart: (d) => trazo.empezar(d.localPosition),
          onPanUpdate: (d) => trazo.continuar(d.localPosition),
          child: AnimatedBuilder(
            animation: trazo,
            builder: (context, _) => CustomPaint(
              painter: _PintorDeFirma(trazo),
              size: Size.infinite,
            ),
          ),
        );
      },
    );
  }
}

class _PintorDeFirma extends CustomPainter {
  _PintorDeFirma(this.trazo);

  final TrazoDeFirma trazo;

  @override
  void paint(Canvas canvas, Size size) {
    final pincel = Paint()
      ..color = AppColors.onSurface
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    for (final linea in trazo.trazos) {
      for (var i = 0; i < linea.length - 1; i++) {
        canvas.drawLine(linea[i], linea[i + 1], pincel);
      }
    }
  }

  @override
  bool shouldRepaint(_PintorDeFirma anterior) => true;
}
