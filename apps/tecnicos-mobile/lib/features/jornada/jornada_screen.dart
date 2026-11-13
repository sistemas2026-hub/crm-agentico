import 'dart:async';

import 'package:flutter/material.dart';
import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/sync_badge.dart';
import '../auth/login_screen.dart';

/// La lista de órdenes anterior.
///
/// Desde la Fase 4 la reemplaza `TrabajoScreen` y ya no la abre nadie: quedó
/// sin llamadores. No se borra todavía a propósito — las pantallas de detalle
/// y ejecución se rediseñan en las Fases 6 y 7, y hasta confirmar ahí que no
/// falta nada de lo que esta hacía, conviene tenerla a mano para comparar.
/// Cuando esas fases cierren, se elimina junto con su `SyncBadge`.
class JornadaScreen extends StatefulWidget {
  const JornadaScreen({super.key, this.mostrarBarraSuperior = true});

  /// Dentro de [AppShell] el encabezado lo pone el contenedor, así que esta
  /// pantalla no dibuja el suyo. Fuera del shell sigue trayendo el propio.
  final bool mostrarBarraSuperior;

  @override
  State<JornadaScreen> createState() => _JornadaScreenState();
}

class _JornadaScreenState extends State<JornadaScreen> {
  final LocalDatabase _localDb = LocalDatabase();
  final SecureStorageService _storage = SecureStorageService();
  final SyncQueueService _syncService = SyncQueueService();

  /// Recarga las órdenes cuando termina una sincronización. Es su propia
  /// suscripción y no la del contenedor: aquella muestra el estado, esta trae
  /// datos. Se cancela en [dispose] — sin eso, cada vez que la pantalla se
  /// recreaba quedaba una escucha viva de más.
  StreamSubscription<SyncStatus>? _suscripcionSync;

  List<Map<String, dynamic>> _ordenes = [];
  String _tecnicoNombre = '';
  String _orgNombre = '';
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
    _suscripcionSync = _syncService.syncStatusStream.listen((status) {
      if (status == SyncStatus.success && mounted) {
        _loadData();
      }
    });
    // Sincronizar órdenes automáticamente al entrar
    _syncService.procesarCola();
  }

  @override
  void dispose() {
    _suscripcionSync?.cancel();
    super.dispose();
  }

  Future<void> _loadData() async {
    final orgId = await _storage.getOrgId();
    final profileId = await _storage.getProfileId();
    final name = await _storage.getUserName() ?? 'Técnico';
    final org = await _storage.getOrgName() ?? 'Organización';

    if (orgId != null && profileId != null) {
      final list = await _localDb.getOrdenes(orgId: orgId, profileId: profileId);
      if (mounted) {
        setState(() {
          _ordenes = list;
          _tecnicoNombre = name;
          _orgNombre = org;
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _onRefresh() async {
    await _syncService.procesarCola();
    await _loadData();
  }

  Future<void> _logout() async {
    await _storage.clearSession();
    if (mounted) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
      );
    }
  }

  Color _getColorForEstado(String estado) {
    switch (estado) {
      case 'en_camino':
        return Colors.blue;
      case 'en_sitio':
        return AppTheme.accentAmber;
      case 'completada_pendiente_sync':
        return AppTheme.warningOrange;
      case 'completada_campo':
        return AppTheme.successGreen;
      case 'suspendida':
        return Colors.grey;
      case 'cancelada':
        return AppTheme.errorRed;
      default:
        return AppTheme.primaryBlue;
    }
  }

  String _formatEstado(String estado) {
    switch (estado) {
      case 'asignada':
        return 'ASIGNADA';
      case 'en_camino':
        return 'EN CAMINO';
      case 'en_sitio':
        return 'EN SITIO';
      case 'completada_pendiente_sync':
        return 'LISTA (PENDIENTE SYNC)';
      case 'completada_campo':
        return 'FINALIZADA';
      case 'suspendida':
        return 'SUSPENDIDA';
      default:
        return estado.toUpperCase();
    }
  }

  @override
  Widget build(BuildContext context) {
    final total = _ordenes.length;
    final pendientes = _ordenes.where((o) => o['estado'] == 'asignada' || o['estado'] == 'en_camino').length;
    final enSitio = _ordenes.where((o) => o['estado'] == 'en_sitio').length;
    final completadas = _ordenes.where((o) => o['estado'] == 'completada_campo' || o['estado'] == 'completada_pendiente_sync').length;

    return Scaffold(
      appBar: !widget.mostrarBarraSuperior
          ? null
          : AppBar(
              title: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('¡Hola, $_tecnicoNombre!'),
                  Text(
                    _orgNombre,
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.normal, color: Colors.white70),
                  ),
                ],
              ),
              actions: [
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: SyncBadge(),
                ),
                IconButton(
                  icon: const Icon(Icons.logout, size: 20),
                  tooltip: 'Cerrar sesión',
                  onPressed: _logout,
                ),
              ],
            ),
      body: RefreshIndicator(
        onRefresh: _onRefresh,
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                children: [
                  // Métricas del día
                  Container(
                    color: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceAround,
                      children: [
                        _metricItem('Total', total.toString(), AppTheme.textMain),
                        _metricItem('Pendientes', pendientes.toString(), AppTheme.primaryBlue),
                        _metricItem('En Sitio', enSitio.toString(), AppTheme.accentAmber),
                        _metricItem('Completadas', completadas.toString(), AppTheme.successGreen),
                      ],
                    ),
                  ),
                  const Divider(height: 1, thickness: 1, color: Color(0xFFE2E8F0)),

                  // Lista de órdenes
                  Expanded(
                    child: _ordenes.isEmpty
                        ? ListView(
                            children: const [
                              SizedBox(height: 80),
                              Center(
                                child: Text(
                                  'No tienes órdenes asignadas para hoy.',
                                  style: TextStyle(fontSize: 16, color: AppTheme.textMuted),
                                ),
                              ),
                            ],
                          )
                        : ListView.builder(
                            itemCount: _ordenes.length,
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            itemBuilder: (context, index) {
                              final orden = _ordenes[index];
                              final estado = orden['estado'] as String;
                              final estadoColor = _getColorForEstado(estado);

                              return Card(
                                child: InkWell(
                                  borderRadius: BorderRadius.circular(12),
                                  // Pantalla heredada y sin llamadores desde la
                                  // Fase 4: no se cablea al detalle nuevo, que
                                  // necesita la lista compartida de la jornada.
                                  // Se elimina entera al cerrar la Fase 7.
                                  onTap: () => ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(
                                      content: Text('Pantalla heredada. Usá la pestaña Trabajo.'),
                                    ),
                                  ),
                                  child: Padding(
                                    padding: const EdgeInsets.all(16),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            Text(
                                              'ORDEN #${orden['numero'] ?? '---'}',
                                              style: const TextStyle(
                                                fontSize: 13,
                                                fontWeight: FontWeight.bold,
                                                color: AppTheme.primaryDark,
                                              ),
                                            ),
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                              decoration: BoxDecoration(
                                                color: estadoColor.withValues(alpha: 0.12),
                                                borderRadius: BorderRadius.circular(6),
                                                border: Border.all(color: estadoColor.withValues(alpha: 0.3)),
                                              ),
                                              child: Text(
                                                _formatEstado(estado),
                                                style: TextStyle(
                                                  fontSize: 11,
                                                  fontWeight: FontWeight.bold,
                                                  color: estadoColor,
                                                ),
                                              ),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 8),
                                        Text(
                                          orden['cliente_nombre'] ?? 'Sin cliente',
                                          style: const TextStyle(
                                            fontSize: 17,
                                            fontWeight: FontWeight.bold,
                                            color: AppTheme.textMain,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Row(
                                          children: [
                                            const Icon(Icons.location_on_outlined, size: 16, color: AppTheme.textMuted),
                                            const SizedBox(width: 4),
                                            Expanded(
                                              child: Text(
                                                orden['direccion'] ?? 'Sin dirección',
                                                style: const TextStyle(fontSize: 13, color: AppTheme.textMuted),
                                                maxLines: 1,
                                                overflow: TextOverflow.ellipsis,
                                              ),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 10),
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                              decoration: BoxDecoration(
                                                color: Colors.grey.shade100,
                                                borderRadius: BorderRadius.circular(4),
                                              ),
                                              child: Text(
                                                orden['tipo_nombre'] ?? 'Trabajo',
                                                style: const TextStyle(fontSize: 12, color: AppTheme.textMuted),
                                              ),
                                            ),
                                            const Row(
                                              children: [
                                                Text(
                                                  'Ver orden',
                                                  style: TextStyle(
                                                    fontSize: 13,
                                                    fontWeight: FontWeight.bold,
                                                    color: AppTheme.primaryBlue,
                                                  ),
                                                ),
                                                Icon(Icons.chevron_right, size: 18, color: AppTheme.primaryBlue),
                                              ],
                                            ),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              );
                            },
                          ),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _metricItem(String label, String value, Color color) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: color),
        ),
        Text(
          label,
          style: const TextStyle(fontSize: 11, color: AppTheme.textMuted),
        ),
      ],
    );
  }
}
