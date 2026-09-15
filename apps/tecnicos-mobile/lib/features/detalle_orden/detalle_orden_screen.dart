import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/sync_badge.dart';
import '../ejecucion/ejecucion_screen.dart';

class DetalleOrdenScreen extends StatefulWidget {
  final String ordenId;

  const DetalleOrdenScreen({super.key, required this.ordenId});

  @override
  State<DetalleOrdenScreen> createState() => _DetalleOrdenScreenState();
}

class _DetalleOrdenScreenState extends State<DetalleOrdenScreen> {
  final LocalDatabase _localDb = LocalDatabase();
  final SecureStorageService _storage = SecureStorageService();
  final SyncQueueService _syncService = SyncQueueService();

  Map<String, dynamic>? _orden;
  String? _orgId;
  String? _profileId;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadOrden();
  }

  Future<void> _loadOrden() async {
    _orgId = await _storage.getOrgId();
    _profileId = await _storage.getProfileId();

    if (_orgId != null && _profileId != null) {
      final item = await _localDb.getOrden(
        orgId: _orgId!,
        profileId: _profileId!,
        id: widget.ordenId,
      );
      if (mounted) {
        setState(() {
          _orden = item;
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _avanzarEstado({
    required String nuevoEstadoLocal,
    required String tipoAccion,
  }) async {
    if (_orden == null || _orgId == null || _profileId == null) return;

    final revisionBase = _orden!['revision'] as int? ?? 0;
    final idempotencyKey = const Uuid().v4();

    // Transición local atómica (guarda en DB y encola mutación)
    await _localDb.transicionarEstadoLocal(
      orgId: _orgId!,
      profileId: _profileId!,
      ordenId: widget.ordenId,
      nuevoEstadoLocal: nuevoEstadoLocal,
      tipoAccion: tipoAccion,
      revisionBase: revisionBase,
      idempotencyKey: idempotencyKey,
    );

    // Disparar sincronización oportunista de fondo
    _syncService.procesarCola();

    await _loadOrden();
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    if (_orden == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Orden no encontrada')),
        body: const Center(child: Text('No se encontró la información de la orden.')),
      );
    }

    final estado = _orden!['estado'] as String;
    final schemaVersion = _orden!['schema_version'] as int? ?? 1;
    final diagnosticoIa = _orden!['diagnostico_previo_ia'] as String?;

    return Scaffold(
      appBar: AppBar(
        title: Text('Orden #${_orden!['numero'] ?? '---'}'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: SyncBadge(),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Alerta si schema_version > 1 (Fallo seguro por actualización requerida)
            if (schemaVersion > 1) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.errorRed.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: AppTheme.errorRed),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.warning, color: AppTheme.errorRed),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Esta orden requiere una versión más reciente de la aplicación móvil (Schema v$schemaVersion). Actualice la app para completarla.',
                        style: const TextStyle(color: AppTheme.errorRed, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],

            // Tarjeta de Información del Cliente
            Card(
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'DATOS DEL CLIENTE',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textMuted,
                        letterSpacing: 1,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _orden!['cliente_nombre'] ?? 'Sin cliente',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        const Icon(Icons.location_on, size: 16, color: AppTheme.primaryBlue),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            _orden!['direccion'] ?? 'Sin dirección',
                            style: const TextStyle(fontSize: 14),
                          ),
                        ),
                      ],
                    ),
                    if (_orden!['telefono'] != null && _orden!['telefono'].toString().isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          const Icon(Icons.phone, size: 16, color: AppTheme.successGreen),
                          const SizedBox(width: 4),
                          Text(
                            _orden!['telefono'].toString(),
                            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Diagnóstico previo de IA (si existe)
            if (diagnosticoIa != null && diagnosticoIa.isNotEmpty) ...[
              Card(
                margin: EdgeInsets.zero,
                color: const Color(0xFFF0F4FF),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: const BorderSide(color: Color(0xFFC7D2FE)),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.auto_awesome, size: 18, color: AppTheme.primaryBlue),
                          SizedBox(width: 6),
                          Text(
                            'DIAGNÓSTICO PREVIO ASISTENTE IA',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                              color: AppTheme.primaryBlue,
                              letterSpacing: 0.5,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        diagnosticoIa,
                        style: const TextStyle(fontSize: 13, color: AppTheme.textMain),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],

            // Resumen de estado actual
            Card(
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'ESTADO ACTUAL',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppTheme.textMuted),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      estado.toUpperCase(),
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.primaryDark),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Tipo: ${_orden!['tipo_nombre']} (${_orden!['tipo_codigo']})',
                      style: const TextStyle(fontSize: 13, color: AppTheme.textMuted),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 32),

            // Botón de acción según la máquina de estados
            _buildBotonAccion(estado, schemaVersion),
          ],
        ),
      ),
    );
  }

  Widget _buildBotonAccion(String estado, int schemaVersion) {
    if (schemaVersion > 1) {
      return const ElevatedButton(
        onPressed: null,
        child: Text('ACTUALIZACIÓN REQUERIDA'),
      );
    }

    switch (estado) {
      case 'asignada':
        return ElevatedButton.icon(
          icon: const Icon(Icons.directions_car),
          label: const Text('INICIAR VIAJE (EN CAMINO)'),
          onPressed: () => _avanzarEstado(
            nuevoEstadoLocal: 'en_camino',
            tipoAccion: 'en_camino',
          ),
        );
      case 'en_camino':
        return ElevatedButton.icon(
          style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accentAmber),
          icon: const Icon(Icons.pin_drop),
          label: const Text('LLEGUÉ AL SITIO (EN SITIO)'),
          onPressed: () => _avanzarEstado(
            nuevoEstadoLocal: 'en_sitio',
            tipoAccion: 'iniciar',
          ),
        );
      case 'en_sitio':
        return ElevatedButton.icon(
          icon: const Icon(Icons.assignment_turned_in),
          label: const Text('EJECUTAR FORMULARIO Y FOTOS'),
          onPressed: () async {
            await Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => EjecucionScreen(ordenId: widget.ordenId),
              ),
            );
            _loadOrden();
          },
        );
      case 'completada_pendiente_sync':
        return ElevatedButton.icon(
          icon: const Icon(Icons.cloud_upload),
          label: const Text('COMPLETADA (PENDIENTE DE SINCRONIZAR)'),
          style: const ButtonStyle(backgroundColor: WidgetStatePropertyAll(AppTheme.warningOrange)),
          onPressed: null,
        );
      case 'completada_campo':
        return ElevatedButton.icon(
          icon: const Icon(Icons.check_circle),
          label: const Text('ORDEN FINALIZADA EN CAMPO'),
          style: const ButtonStyle(backgroundColor: WidgetStatePropertyAll(AppTheme.successGreen)),
          onPressed: null,
        );
      default:
        return const SizedBox.shrink();
    }
  }
}
