import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:uuid/uuid.dart';
import '../../core/mock/field_mock_data.dart';
import '../../core/storage/evidencia_storage_service.dart';
import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/offline_saved_banner.dart';
import '../../core/widgets/sync_badge.dart';
import 'progreso_evidencias.dart';
import 'widgets/bloque_academia.dart';
import 'widgets/formulario_de_campo.dart';

/// El trabajo, ejecutándose: el formulario de campo y la evidencia.
///
/// El aspecto es el del diseño de Stitch; las preguntas siguen siendo las que
/// manda el backend con la orden (`formulario_campos_json`), y cada respuesta
/// se guarda en SQLite en el momento, sin esperar a tener señal.
class EjecucionScreen extends StatefulWidget {
  final String ordenId;

  /// Enciende lo que el diseño muestra y todavía no existe: la sugerencia de
  /// reemplazo, el medidor por Bluetooth y las cápsulas de Academia.
  final bool mostrarDatosFuturos;

  const EjecucionScreen({
    super.key,
    required this.ordenId,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  @override
  State<EjecucionScreen> createState() => _EjecucionScreenState();
}

class _EjecucionScreenState extends State<EjecucionScreen> {
  final LocalDatabase _localDb = LocalDatabase();
  final SecureStorageService _storage = SecureStorageService();
  final SyncQueueService _syncService = SyncQueueService();
  final ImagePicker _picker = ImagePicker();

  Map<String, dynamic>? _orden;
  String? _orgId;
  String? _profileId;
  bool _isLoading = true;
  bool _showSavedIndicator = false;
  Timer? _savedIndicatorTimer;

  /// El botón "Borrador" no guarda nada nuevo —cada respuesta ya se escribió
  /// en SQLite al tocarla—: confirma que lo escrito está a salvo.
  bool _borradorConfirmado = false;
  Timer? _borradorTimer;

  List<dynamic> _campos = [];
  List<dynamic> _evidenciasRequisitos = [];
  Map<String, dynamic> _valoresFormulario = {};
  List<Map<String, dynamic>> _evidenciasCapturadas = [];

  final Map<String, TextEditingController> _controllers = {};

  @override
  void initState() {
    super.initState();
    _loadOrdenData();
  }

  @override
  void dispose() {
    _savedIndicatorTimer?.cancel();
    _borradorTimer?.cancel();
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  void _triggerSavedBanner() {
    setState(() {
      _showSavedIndicator = true;
    });
    _savedIndicatorTimer?.cancel();
    _savedIndicatorTimer = Timer(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _showSavedIndicator = false;
        });
      }
    });
  }

  Future<void> _loadOrdenData() async {
    _orgId = await _storage.getOrgId();
    _profileId = await _storage.getProfileId();

    if (_orgId != null && _profileId != null) {
      final orden = await _localDb.getOrden(
        orgId: _orgId!,
        profileId: _profileId!,
        id: widget.ordenId,
      );

      if (orden != null) {
        final camposStr = orden['formulario_campos_json'] as String? ?? '[]';
        final evidenciasStr = orden['formulario_evidencias_json'] as String? ?? '[]';

        _campos = jsonDecode(camposStr);
        _evidenciasRequisitos = jsonDecode(evidenciasStr);

        // Obtener valores mezclados (base + dirty local persistido)
        _valoresFormulario = await _localDb.getMergedDatosOrden(
          orgId: _orgId!,
          profileId: _profileId!,
          ordenId: widget.ordenId,
        );

        // Cargar evidencias ya capturadas localmente
        _evidenciasCapturadas = await _localDb.getEvidenciasOrden(
          orgId: _orgId!,
          profileId: _profileId!,
          ordenId: widget.ordenId,
        );

        // Inicializar controladores de texto
        for (final c in _campos) {
          final clave = (c['clave'] ?? c['id']) as String;
          final valor = _valoresFormulario[clave]?.toString() ?? '';
          _controllers[clave] = TextEditingController(text: valor);
        }

        if (mounted) {
          setState(() {
            _orden = orden;
            _isLoading = false;
          });
        }
      }
    }
  }

  Future<void> _onFieldChanged(String clave, dynamic valor) async {
    if (_orgId == null || _profileId == null) return;

    _valoresFormulario[clave] = valor;

    // Persistencia atómica inmediata en SQLite
    await _localDb.saveDatoCampo(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      campoClave: clave,
      valor: valor,
    );

    _syncService.refreshSyncSummary();
    _triggerSavedBanner();
  }

  Future<void> _tomarFoto(String requisitoId) async {
    if (_orgId == null || _profileId == null) return;

    try {
      final XFile? foto = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 85,
        maxWidth: 1920,
      );

      if (foto == null) return;

      final tempFile = File(foto.path);
      // El id se genera ANTES de copiar el archivo porque el archivo se llama
      // como él: si la fila se perdiera, la foto sigue diciendo cual es su
      // evidencia, de quien es y de que orden.
      final evId = const Uuid().v4();
      // Persistir inmediatamente en almacenamiento seguro y durable privado
      final persistentFile = await EvidenciaStorageService.persistirArchivoCaptura(
        tempFile,
        nombreOriginal: foto.name,
        orgId: _orgId!,
        profileId: _profileId!,
        ordenId: widget.ordenId,
        evidenciaId: evId,
      );
      final sha = await SyncQueueService.calcularSha256(persistentFile);
      final size = await persistentFile.length();
      final registroKey = const Uuid().v4();
      final confirmacionKey = const Uuid().v4();

      await _localDb.encolarEvidencia(
        id: evId,
        orgId: _orgId!,
        profileId: _profileId!,
        ordenId: widget.ordenId,
        requisitoId: requisitoId,
        archivoPath: persistentFile.path,
        sha256: sha,
        tamanoBytes: size,
        mimeType: 'image/jpeg',
        registroIdempotencyKey: registroKey,
        confirmacionIdempotencyKey: confirmacionKey,
      );

      _evidenciasCapturadas = await _localDb.getEvidenciasOrden(
        orgId: _orgId!,
        profileId: _profileId!,
        ordenId: widget.ordenId,
      );

      _triggerSavedBanner();

      // Disparar sincronización oportunista de fondo
      _syncService.procesarCola();

      if (mounted) setState(() {});
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error al capturar foto: $e')),
        );
      }
    }
  }

  Future<void> _completarOrden() async {
    if (_orden == null || _orgId == null || _profileId == null) return;

    // 1. Validar campos obligatorios
    for (final c in _campos) {
      final obligatorio = c['obligatorio'] == true || c['reglas']?['required'] == true;
      final clave = (c['clave'] ?? c['id']) as String;
      final etiqueta = (c['etiqueta'] ?? c['titulo'] ?? clave) as String;
      final valor = _valoresFormulario[clave];
      if (obligatorio && (valor == null || valor.toString().trim().isEmpty)) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: AppTheme.errorRed,
            content: Text('El campo "$etiqueta" es obligatorio.'),
          ),
        );
        return;
      }
    }

    // 2. Validar evidencias obligatorias
    for (final req in _evidenciasRequisitos) {
      final obligatorio = req['obligatorio'] == true;
      final reqId = req['id'] as String;
      final capturada = _evidenciasCapturadas.any((e) => e['requisito_id'] == reqId);

      if (obligatorio && !capturada) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: AppTheme.errorRed,
            content: Text('La fotografía "${req['descripcion']}" es obligatoria.'),
          ),
        );
        return;
      }
    }

    // 3. Todo satisfecho: transicionar localmente a completada_pendiente_sync
    final revisionBase = _orden!['revision'] as int? ?? 0;
    final idempotencyKey = const Uuid().v4();

    await _localDb.transicionarEstadoLocal(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      nuevoEstadoLocal: 'completada_pendiente_sync',
      tipoAccion: 'completar',
      revisionBase: revisionBase,
      idempotencyKey: idempotencyKey,
    );

    // 4. Intentar sincronización en segundo plano
    _syncService.procesarCola();

    if (mounted) {
      await showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          icon: const Icon(Icons.check_circle, color: AppTheme.successGreen, size: 48),
          title: const Text('¡Trabajo Finalizado con Éxito!'),
          content: const Text(
            'La orden ha quedado guardada de forma segura en este dispositivo. Si no hay conexión, se enviará al servidor automáticamente al reconectar.',
          ),
          actions: [
            ElevatedButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                Navigator.of(context).pop();
              },
              child: const Text('ENTENDIDO'),
            ),
          ],
        ),
      );
    }
  }

  void _confirmarBorrador() {
    // No escribe: solo confirma. Cada respuesta ya se guardó al tocarla.
    _triggerSavedBanner();
    setState(() => _borradorConfirmado = true);
    _borradorTimer?.cancel();
    _borradorTimer = Timer(const Duration(milliseconds: 1500), () {
      if (mounted) setState(() => _borradorConfirmado = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    final numero = _orden?['numero'] ?? '---';

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        title: Text('Ejecución OT #$numero'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: AppSpacing.sm),
            child: SyncBadge(),
          ),
        ],
      ),
      body: Column(
        children: [
          OfflineSavedBanner(visible: _showSavedIndicator),
          _franjaDelFormulario(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.margen,
                AppSpacing.lg,
                AppSpacing.margen,
                AppSpacing.lg,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FormularioDeCampo(
                    campos: _campos,
                    valores: _valoresFormulario,
                    controladores: _controllers,
                    alCambiar: _onFieldChanged,
                    mostrarDatosFuturos: widget.mostrarDatosFuturos,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _evidencias(),
                  if (widget.mostrarDatosFuturos) ...[
                    const SizedBox(height: AppSpacing.lg),
                    const BloqueAcademia(),
                  ],
                ],
              ),
            ),
          ),
          _barraDeAcciones(),
        ],
      ),
    );
  }

  /// Cuántos requisitos de foto ya tienen su captura.
  int get _fotosCapturadas => fotosCapturadas(
        requisitos: _evidenciasRequisitos,
        capturadas: _evidenciasCapturadas,
      );

  /// Qué formulario se está respondiendo. La versión del esquema viene con la
  /// orden: si el backend cambia las preguntas, esto cambia con ellas.
  Widget _franjaDelFormulario() {
    final int version = _orden?['schema_version'] as int? ?? 0;
    final int campos = _campos.length;

    return Container(
      width: double.infinity,
      color: AppColors.surfaceContainerLow,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.margen,
        vertical: 6,
      ),
      child: Row(
        children: [
          const Icon(Icons.save, size: 13, color: AppColors.exitoTexto),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              'Se guarda en este equipo mientras trabajás',
              style: AppTypography.etiquetaChica,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Text(
            version == 0
                ? '$campos campos'
                : 'Formulario v$version · $campos campos',
            style: AppTypography.datoChico.copyWith(
              color: AppColors.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  /// La evidencia fotográfica que pide el tipo de trabajo. Igual que el
  /// formulario, la lista viene del backend: acá solo se dibuja y se captura.
  Widget _evidencias() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Evidencia Fotográfica', style: AppTypography.tituloChico),
                    Text(
                      'Queda guardada en el equipo y se envía sola al recuperar señal',
                      style: AppTypography.cuerpoChico,
                    ),
                  ],
                ),
              ),
              Text(
                '$_fotosCapturadas/${_evidenciasRequisitos.length}',
                style: AppTypography.dato.copyWith(
                  color: _fotosCapturadas == _evidenciasRequisitos.length
                      ? AppColors.exitoTexto
                      : AppColors.primary,
                ),
              ),
              const SizedBox(width: 6),
              const Icon(Icons.photo_camera, size: 20, color: AppColors.outline),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          if (_evidenciasRequisitos.isEmpty)
            Text(
              'Este tipo de trabajo no exige fotografías.',
              style: AppTypography.cuerpoChico,
            )
          else
            for (var i = 0; i < _evidenciasRequisitos.length; i++) ...[
              if (i > 0) const SizedBox(height: AppSpacing.md),
              _buildEvidenciaRequisito(
                Map<String, dynamic>.from(_evidenciasRequisitos[i] as Map),
              ),
            ],
        ],
      ),
    );
  }

  /// La barra fija del diseño: el borrador a la izquierda, el cierre a la
  /// derecha. El diseño dice "Registrar Materiales"; ese módulo todavía no
  /// existe, así que el botón hace lo que la aplicación sí sabe hacer: cerrar
  /// la orden con lo registrado.
  Widget _barraDeAcciones() {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        boxShadow: AppTheme.sombraNivel2,
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.margen,
            vertical: AppSpacing.md,
          ),
          child: Row(
            children: [
              Material(
                color: AppColors.surfaceContainer,
                borderRadius: AppRadius.brTarjeta,
                child: InkWell(
                  borderRadius: AppRadius.brTarjeta,
                  onTap: _confirmarBorrador,
                  child: Container(
                    height: AppSpacing.objetivoTactilAmplio,
                    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                    alignment: Alignment.center,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _borradorConfirmado ? Icons.check : Icons.save,
                          size: 18,
                          color: AppColors.onSurface,
                        ),
                        const SizedBox(width: AppSpacing.xs),
                        Text(
                          _borradorConfirmado ? 'Guardado' : 'Borrador',
                          style: AppTypography.etiqueta
                              .copyWith(color: AppColors.onSurface),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Material(
                  color: AppColors.primary,
                  borderRadius: AppRadius.brTarjeta,
                  child: InkWell(
                    borderRadius: AppRadius.brTarjeta,
                    onTap: _completarOrden,
                    child: Container(
                      height: AppSpacing.objetivoTactilAmplio,
                      alignment: Alignment.center,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            'Finalizar orden',
                            style: AppTypography.etiquetaGrande
                                .copyWith(color: AppColors.onPrimary),
                          ),
                          const SizedBox(width: AppSpacing.sm),
                          const Icon(
                            Icons.arrow_forward,
                            size: 20,
                            color: AppColors.onPrimary,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEvidenciaRequisito(Map<String, dynamic> req) {
    final reqId = req['id'] as String;
    final descripcion = (req['descripcion'] ?? req['titulo'] ?? reqId) as String;
    final obligatorio = req['obligatorio'] == true;
    final instrucciones = req['instrucciones'] as String?;

    final evidencia = _evidenciasCapturadas.firstWhere(
      (e) => e['requisito_id'] == reqId,
      orElse: () => {},
    );
    final hasFoto = evidencia.isNotEmpty && evidencia['archivo_path'] != null;
    final filePath = hasFoto ? evidencia['archivo_path'] as String : null;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        border: !hasFoto && obligatorio
            ? Border.all(color: AppColors.onErrorContainer.withValues(alpha: 0.4))
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: hasFoto
                      ? AppColors.exitoFondo
                      : AppColors.surfaceContainer,
                  borderRadius: AppRadius.brCampo,
                ),
                child: Icon(
                  hasFoto ? Icons.check_circle : Icons.camera_alt_outlined,
                  size: 18,
                  color: hasFoto ? AppColors.exito : AppColors.secondary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  '$descripcion${obligatorio ? ' *' : ''}',
                  style: AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: hasFoto
                      ? AppColors.exitoFondo
                      : (obligatorio
                          ? AppColors.errorContainer
                          : AppColors.surfaceContainer),
                  borderRadius: AppRadius.brChico,
                ),
                child: Text(
                  hasFoto ? 'CAPTURADA' : 'PENDIENTE',
                  style: AppTypography.etiquetaChica.copyWith(
                    color: hasFoto
                        ? AppColors.exitoTexto
                        : (obligatorio
                            ? AppColors.onErrorContainer
                            : AppColors.onSurfaceVariant),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          if (instrucciones != null && instrucciones.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(instrucciones, style: AppTypography.etiquetaChica),
          ],
          const SizedBox(height: AppSpacing.sm),
          if (hasFoto && filePath != null) ...[
            ClipRRect(
              borderRadius: AppRadius.brTarjeta,
              child: Image.file(
                File(filePath),
                height: 140,
                width: double.infinity,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) =>
                    const Text('No se puede cargar la vista previa'),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
          SizedBox(
            height: AppSpacing.objetivoTactil,
            child: OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.primary,
                side: const BorderSide(color: AppColors.outlineVariant),
                shape: const RoundedRectangleBorder(
                  borderRadius: AppRadius.brTarjeta,
                ),
              ),
              icon: Icon(hasFoto ? Icons.replay : Icons.camera_alt, size: 18),
              label: Text(hasFoto ? 'VOLVER A TOMAR' : 'TOMAR FOTOGRAFÍA'),
              onPressed: () => _tomarFoto(reqId),
            ),
          ),
        ],
      ),
    );
  }
}
