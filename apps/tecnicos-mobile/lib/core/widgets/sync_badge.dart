import 'package:flutter/material.dart';
import '../sync/sync_queue_service.dart';
import '../theme/app_theme.dart';

class SyncBadge extends StatefulWidget {
  const SyncBadge({super.key});

  @override
  State<SyncBadge> createState() => _SyncBadgeState();
}

class _SyncBadgeState extends State<SyncBadge> {
  final SyncQueueService syncService = SyncQueueService();

  @override
  void initState() {
    super.initState();
    // Consultar el estado real en SQLite inmediatamente al montar el widget
    syncService.refreshSyncSummary();
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<SyncSummary>(
      stream: syncService.syncSummaryStream,
      initialData: syncService.lastSummary,
      builder: (context, snapshot) {
        final summary = snapshot.data;

        IconData icon;
        String text;
        Color color;

        if (summary == null) {
          icon = Icons.cloud_queue;
          text = 'Verificando...';
          color = Colors.white70;
        } else if (summary.isSyncing) {
          icon = Icons.sync;
          text = 'Sincronizando...';
          color = AppTheme.accentAmber;
        } else if (summary.mutacionesConflicto > 0) {
          icon = Icons.warning_amber_rounded;
          text = summary.mutacionesConflicto == 1
              ? '1 en conflicto'
              : '${summary.mutacionesConflicto} en conflicto';
          color = AppTheme.errorRed;
        } else if (summary.hasConnectionError) {
          icon = Icons.cloud_off;
          color = summary.totalPendientes > 0 ? AppTheme.warningOrange : Colors.white70;
          text = summary.totalPendientes > 0
              ? 'Sin conexión · ${summary.totalPendientes} pendientes'
              : 'Sin conexión';
        } else if (summary.totalPendientes > 0) {
          icon = Icons.hourglass_top;
          color = AppTheme.warningOrange;
          if (summary.mutacionesPendientes > 0 && summary.evidenciasPendientes > 0) {
            text = '${summary.mutacionesPendientes} cambios · ${summary.evidenciasPendientes} fotos';
          } else if (summary.evidenciasPendientes > 0) {
            text = '${summary.evidenciasPendientes} fotos pendientes';
          } else if (summary.mutacionesPendientes > 0) {
            text = '${summary.mutacionesPendientes} cambios pendientes';
          } else {
            text = '${summary.totalPendientes} pendientes';
          }
        } else {
          icon = Icons.cloud_done;
          text = 'Sincronizado';
          color = AppTheme.successGreen;
        }

        return InkWell(
          onTap: () async {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Iniciando sincronización manual con servidor...'),
                duration: Duration(seconds: 1),
              ),
            );
            await syncService.procesarCola();
          },
          borderRadius: BorderRadius.circular(16),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.white.withValues(alpha: 0.3)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 14, color: color),
                const SizedBox(width: 6),
                Text(
                  text,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: Colors.white,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
