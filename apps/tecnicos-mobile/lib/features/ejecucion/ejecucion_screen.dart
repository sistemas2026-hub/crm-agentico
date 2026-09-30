import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:uuid/uuid.dart';
import '../../core/storage/evidencia_storage_service.dart';
import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/offline_saved_banner.dart';
import '../../core/widgets/sync_badge.dart';

class EjecucionScreen extends StatefulWidget {
  final String ordenId;

  const EjecucionScreen({super.key, required this.ordenId});

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
      // Persistir inmediatamente en almacenamiento seguro y durable privado
      final persistentFile = await EvidenciaStorageService.persistirArchivoCaptura(
        tempFile,
        nombreOriginal: foto.name,
      );
      final sha = await SyncQueueService.calcularSha256(persistentFile);
      final size = await persistentFile.length();
      final evId = const Uuid().v4();
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

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    final numero = _orden?['numero'] ?? '---';

    return Scaffold(
      appBar: AppBar(
        title: Text('Ejecución #$numero'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: SyncBadge(),
          ),
        ],
      ),
      body: Column(
        children: [
          OfflineSavedBanner(visible: _showSavedIndicator),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Sección 1: Formulario dinámico
                  const Text(
                    'PARÁMETROS TÉCNICOS',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.primaryDark,
                      letterSpacing: 0.8,
                    ),
                  ),
                  const SizedBox(height: 12),
                  ..._campos.map((c) => _buildCampoDinamico(c)),
                  const SizedBox(height: 24),

                  // Sección 2: Evidencias fotográficas requeridas
                  const Text(
                    'EVIDENCIAS FOTOGRÁFICAS',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.primaryDark,
                      letterSpacing: 0.8,
                    ),
                  ),
                  const SizedBox(height: 12),
                  ..._evidenciasRequisitos.map((req) => _buildEvidenciaRequisito(req)),
                  const SizedBox(height: 32),

                  // Botón Finalizar
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.successGreen,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    icon: const Icon(Icons.check_circle_outline, size: 22),
                    label: const Text('FINALIZAR ORDEN DE TRABAJO'),
                    onPressed: _completarOrden,
                  ),
                  const SizedBox(height: 20),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCampoDinamico(Map<String, dynamic> campo) {
    final clave = (campo['clave'] ?? campo['id']) as String;
    final etiqueta = (campo['etiqueta'] ?? campo['titulo'] ?? clave) as String;
    final tipo = campo['tipo'] as String;
    final obligatorio = campo['obligatorio'] == true || campo['reglas']?['required'] == true;
    final unidad = campo['unidad'] as String?;
    final ayuda = campo['ayuda'] as String?;

    if (tipo == 'seleccion') {
      final opciones = (campo['opciones'] as List<dynamic>?) ?? [];
      final valorActual = _valoresFormulario[clave]?.toString();

      return Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: DropdownButtonFormField<String>(
          initialValue: opciones.contains(valorActual) ? valorActual : null,
          decoration: InputDecoration(
            labelText: '$etiqueta${obligatorio ? ' *' : ''}',
            helperText: ayuda,
          ),
          items: opciones.map((opt) {
            return DropdownMenuItem<String>(
              value: opt.toString(),
              child: Text(opt.toString()),
            );
          }).toList(),
          onChanged: (val) => _onFieldChanged(clave, val),
        ),
      );
    } else if (tipo == 'booleano') {
      final valorActual = _valoresFormulario[clave] == true;
      return Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: SwitchListTile(
          title: Text('$etiqueta${obligatorio ? ' *' : ''}'),
          subtitle: ayuda != null ? Text(ayuda) : null,
          value: valorActual,
          onChanged: (val) => _onFieldChanged(clave, val),
        ),
      );
    } else {
      // Texto o Número (o decimal)
      final isNumber = tipo == 'numero' || tipo == 'decimal' || tipo == 'integer';
      final controller = _controllers[clave];

      return Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: TextField(
          controller: controller,
          keyboardType: isNumber
              ? const TextInputType.numberWithOptions(decimal: true, signed: true)
              : TextInputType.text,
          decoration: InputDecoration(
            labelText: '$etiqueta${obligatorio ? ' *' : ''}',
            suffixText: unidad,
            helperText: ayuda,
          ),
          onChanged: (val) {
            dynamic parsedVal = val;
            if (isNumber && val.isNotEmpty) {
              parsedVal = num.tryParse(val) ?? val;
            }
            _onFieldChanged(clave, parsedVal);
          },
        ),
      );
    }
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

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  hasFoto ? Icons.check_circle : Icons.camera_alt_outlined,
                  color: hasFoto ? AppTheme.successGreen : AppTheme.primaryBlue,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '$descripcion${obligatorio ? ' *' : ''}',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                ),
                if (hasFoto)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppTheme.successGreen.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Text(
                      'CAPTURADA',
                      style: TextStyle(fontSize: 10, color: AppTheme.successGreen, fontWeight: FontWeight.bold),
                    ),
                  ),
              ],
            ),
            if (instrucciones != null && instrucciones.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                instrucciones,
                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
              ),
            ],
            const SizedBox(height: 8),
            if (hasFoto && filePath != null) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.file(
                  File(filePath),
                  height: 140,
                  width: double.infinity,
                  errorBuilder: (context, error, stackTrace) =>
                      const Text('No se puede cargar la vista previa'),
                ),
              ),
              const SizedBox(height: 8),
            ],
            OutlinedButton.icon(
              icon: Icon(hasFoto ? Icons.replay : Icons.camera_alt),
              label: Text(hasFoto ? 'VOLVER A TOMAR' : 'TOMAR FOTOGRAFÍA'),
              onPressed: () => _tomarFoto(reqId),
            ),
          ],
        ),
      ),
    );
  }
}
