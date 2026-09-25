import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:uuid/uuid.dart';
import '../api/api_client.dart';
import '../api/api_endpoints.dart';
import '../storage/local_database.dart';
import '../storage/secure_storage_service.dart';

enum SyncStatus { idle, syncing, error, success }

class SyncSummary {
  final SyncStatus status;
  final bool isSyncing;
  final bool hasConnectionError;
  final int mutacionesPendientes;
  final int mutacionesConflicto;
  final int evidenciasPendientes;
  final int datosDirty;

  const SyncSummary({
    required this.status,
    required this.isSyncing,
    required this.hasConnectionError,
    required this.mutacionesPendientes,
    required this.mutacionesConflicto,
    required this.evidenciasPendientes,
    required this.datosDirty,
  });

  int get totalPendientes => mutacionesPendientes + evidenciasPendientes + (datosDirty > 0 ? 1 : 0);
  bool get isClean => totalPendientes == 0 && mutacionesConflicto == 0;
}

class SyncQueueService {
  static final SyncQueueService _instance = SyncQueueService._internal();
  factory SyncQueueService() => _instance;
  SyncQueueService._internal() {
    // Escuchar el Stream broadcast de cambios en SQLite respetando el tenant activo
    LocalDatabase.onDataChanged.listen((event) async {
      final currentOrg = await _storage.getOrgId();
      final currentProf = await _storage.getProfileId();
      if (event.orgId == null || (event.orgId == currentOrg && event.profileId == currentProf)) {
        refreshSyncSummary();
      }
    });
  }

  final LocalDatabase _localDb = LocalDatabase();
  final ApiClient _apiClient = ApiClient();
  final SecureStorageService _storage = SecureStorageService();

  final _syncStatusController = StreamController<SyncStatus>.broadcast();
  Stream<SyncStatus> get syncStatusStream => _syncStatusController.stream;
  SyncStatus _currentStatus = SyncStatus.idle;
  SyncStatus get currentStatus => _currentStatus;

  final _syncSummaryController = StreamController<SyncSummary>.broadcast();
  Stream<SyncSummary> get syncSummaryStream => _syncSummaryController.stream;
  SyncSummary? _lastSummary;
  SyncSummary? get lastSummary => _lastSummary;

  bool _isSyncing = false;

  void _setStatus(SyncStatus status) {
    _currentStatus = status;
    _syncStatusController.add(status);
  }

  /// Hash djb2 determinista de 31 bits reproducible y estable entre ejecuciones y plataformas
  static int hashEstable(String str) {
    var hash = 5381;
    for (var i = 0; i < str.length; i++) {
      hash = ((hash << 5) + hash) + str.codeUnitAt(i);
      hash = hash & 0x7FFFFFFF;
    }
    return hash;
  }

  /// Calcula backoff exponencial acotado con jitter real estable por mutación y soporte para Retry-After
  static int calcularBackoffMs(
    int reintentos, {
    String? mutationId,
    int? retryAfterSeconds,
  }) {
    // 1. Si el servidor entregó Retry-After explícito (delta-seconds o fecha), se respeta estrictamente
    if (retryAfterSeconds != null && retryAfterSeconds > 0) {
      return retryAfterSeconds * 1000;
    }

    // 2. Backoff exponencial normal (base 2s, tope 60s)
    final factor = reintentos >= 5 ? 60 : (2 * (1 << reintentos));
    final delaySeconds = factor.clamp(2, 60);

    // 3. Jitter determinista pero disperso por mutación estable entre procesos:
    final idSeed = mutationId != null ? hashEstable(mutationId) : 0;
    final jitterMs = (idSeed + (reintentos * 173)) % 500;

    return (delaySeconds * 1000) + jitterMs;
  }

  /// Refresca el resumen de sincronización consultando el estado real en SQLite
  Future<SyncSummary> refreshSyncSummary({bool? hasConnectionErrorOverride}) async {
    final orgId = await _storage.getOrgId();
    final profileId = await _storage.getProfileId();
    if (orgId == null || profileId == null) {
      final empty = SyncSummary(
        status: _currentStatus,
        isSyncing: _isSyncing,
        hasConnectionError: hasConnectionErrorOverride ?? (_currentStatus == SyncStatus.error),
        mutacionesPendientes: 0,
        mutacionesConflicto: 0,
        evidenciasPendientes: 0,
        datosDirty: 0,
      );
      _lastSummary = empty;
      _syncSummaryController.add(empty);
      return empty;
    }

    final counts = await _localDb.getSyncCounts(orgId: orgId, profileId: profileId);
    final summary = SyncSummary(
      status: _currentStatus,
      isSyncing: _isSyncing,
      hasConnectionError: hasConnectionErrorOverride ?? (_currentStatus == SyncStatus.error),
      mutacionesPendientes: counts['mutaciones_pendientes'] ?? 0,
      mutacionesConflicto: counts['mutaciones_conflicto'] ?? 0,
      evidenciasPendientes: counts['evidencias_pendientes'] ?? 0,
      datosDirty: counts['datos_dirty'] ?? 0,
    );
    _lastSummary = summary;
    _syncSummaryController.add(summary);
    return summary;
  }

  /// Calcula SHA-256 de un archivo local
  static Future<String> calcularSha256(File file) async {
    final bytes = await file.readAsBytes();
    return sha256.convert(bytes).toString();
  }

  /// Procesa todo el ciclo de sincronización de manera determinista (DAG)
  Future<void> procesarCola() async {
    if (_isSyncing) return;
    _isSyncing = true;
    _setStatus(SyncStatus.syncing);
    await refreshSyncSummary(hasConnectionErrorOverride: false);

    try {
      final orgId = await _storage.getOrgId();
      final profileId = await _storage.getProfileId();

      if (orgId == null || profileId == null) {
        _isSyncing = false;
        _setStatus(SyncStatus.idle);
        await refreshSyncSummary(hasConnectionErrorOverride: false);
        return;
      }

      // 1. Descargar o refrescar órdenes asignadas desde el servidor si hay conexión
      await _descargarOrdenesAsignadas(orgId, profileId);

      // 2. Procesar mutaciones de estado no finales (iniciar, en_camino, suspender)
      await _procesarMutacionesTransicion(orgId, profileId, soloNoFinales: true);

      // 3. Coalescing y sincronización de datos técnicos dirty
      await _procesarDatosDirty(orgId, profileId);

      // 4. Subida y confirmación en 3 pasos de evidencias pendientes
      await _procesarEvidencias(orgId, profileId);

      // 5. Procesar mutación 'completar' (DAG: solo si no quedan dirty ni evidencias pendientes)
      await _procesarMutacionCompletar(orgId, profileId);

      // 6. Refresco final de estado
      await _descargarOrdenesAsignadas(orgId, profileId);

      _setStatus(SyncStatus.success);
      await refreshSyncSummary(hasConnectionErrorOverride: false);
    } catch (e) {
      _setStatus(SyncStatus.error);
      await refreshSyncSummary(hasConnectionErrorOverride: true);
    } finally {
      _isSyncing = false;
      await refreshSyncSummary();
    }
  }

  Future<void> _descargarOrdenesAsignadas(String orgId, String profileId) async {
    try {
      final response = await _apiClient.get(ApiEndpoints.trabajos);
      if (response.statusCode == 200 && response.data != null) {
        final List results = response.data['results'] ?? response.data;
        for (final item in results) {
          final id = item['id'] as String;
          Map<String, dynamic> fullData = item as Map<String, dynamic>;

          try {
            final detailRes = await _apiClient.get(ApiEndpoints.trabajoDetalle(id));
            if (detailRes.statusCode == 200 && detailRes.data is Map) {
              fullData = Map<String, dynamic>.from(detailRes.data);
            }
          } catch (_) {}

          await _localDb.upsertOrden(
            orgId: orgId,
            profileId: profileId,
            ordenData: fullData,
          );
        }
      }
    } catch (_) {
      // Offline o error de red: se ignora silenciosamente para mantener datos locales
    }
  }

  Future<void> _procesarMutacionesTransicion(
    String orgId,
    String profileId, {
    required bool soloNoFinales,
  }) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final mutaciones = await _localDb.getMutacionesPendientes(
      orgId: orgId,
      profileId: profileId,
      soloListasHasta: now,
    );

    for (final m in mutaciones) {
      final tipo = m['tipo'] as String;
      if (soloNoFinales && tipo == 'completar') continue;
      if (!soloNoFinales && tipo != 'completar') continue;

      final ordenId = m['orden_id'] as String;
      final revisionBase = m['revision_base'] as int;
      final idempotencyKey = m['idempotency_key'] as String;
      Map<String, dynamic> payload = {};
      if (m['payload_json'] != null) {
        try {
          payload = jsonDecode(m['payload_json']);
        } catch (_) {}
      }

      final url = ApiEndpoints.accionTrabajo(ordenId, tipo);

      try {
        final accionBackend = switch (tipo) {
          'en_camino' || 'marcar_en_camino' => 'marcar_en_camino',
          'iniciar' || 'en_sitio' || 'marcar_llegada' => 'marcar_llegada',
          _ => tipo,
        };

        final Map<String, dynamic> requestData = tipo == 'completar'
            ? payload
            : {
                'accion': accionBackend,
                'client_mutation_id': idempotencyKey,
                if (payload.isNotEmpty) 'metadatos': payload,
              };

        final response = await _apiClient.post(
          url,
          data: requestData,
          options: Options(
            headers: {
              'Idempotency-Key': idempotencyKey,
              if (tipo == 'completar') 'X-Revision-Base': revisionBase.toString(),
            },
          ),
        );

        if (response.statusCode == 200) {
          final data = response.data;
          await _localDb.updateMutacionEstado(id: m['id'], estado: 'sincronizada');
          final estadoBackend = data?['estado_operativo']?.toString();
          if (data != null && data['revision'] != null && estadoBackend != null) {
            await _localDb.updateOrdenRevisionYEstado(
              orgId: orgId,
              profileId: profileId,
              ordenId: ordenId,
              nuevaRevision: data['revision'],
              nuevoEstado: estadoBackend,
            );
          }
        }
      } on DioException catch (dioErr) {
        final status = dioErr.response?.statusCode;
        if (status == 400) {
          // Error de validación: no reintentable automáticamente para evitar bucles
          await _localDb.updateMutacionEstado(
            id: m['id'],
            estado: 'error_validacion',
            errorMensaje: dioErr.response?.data?['error']?.toString() ?? dioErr.message,
          );
        } else if (status == 401 || status == 403) {
          // Error de autenticación persistente tras intento de refresh
          await _localDb.updateMutacionEstado(
            id: m['id'],
            estado: 'error_auth',
            errorMensaje: 'Sesión expirada o no autorizada.',
          );
        } else if (status == 404) {
          // Terminal: orden inexistente o reasignada
          await _localDb.updateMutacionEstado(
            id: m['id'],
            estado: 'terminal_404',
            errorMensaje: 'La orden no existe o fue reasignada.',
          );
        } else if (status == 409) {
          // Conflicto de revisión (STALE_WORK_ORDER) u operación en curso
          final code = dioErr.response?.data?['code'] ?? '';
          await _localDb.updateMutacionEstado(
            id: m['id'],
            estado: 'conflicto',
            errorMensaje: code.isNotEmpty ? code : 'STALE_WORK_ORDER',
          );
        } else {
          // Errores reintentables: 408 (Timeout), 429 (Rate limit), 5xx, timeouts de red, caídas de socket
          int? retryAfterSeconds;
          if (status == 429) {
            final rawRetryAfter = dioErr.response?.headers.value('retry-after');
            if (rawRetryAfter != null) {
              final parsed = int.tryParse(rawRetryAfter.trim());
              if (parsed != null && parsed > 0) {
                retryAfterSeconds = parsed;
              } else {
                try {
                  final httpDate = HttpDate.parse(rawRetryAfter.trim());
                  final diff = httpDate.difference(DateTime.now()).inSeconds;
                  if (diff > 0) retryAfterSeconds = diff;
                } catch (_) {}
              }
            }
          }

          final reintentosActuales = (m['reintentos'] as int? ?? 0);
          final delayMs = calcularBackoffMs(
            reintentosActuales,
            mutationId: m['id'] as String?,
            retryAfterSeconds: retryAfterSeconds,
          );
          final nextAttemptAt = DateTime.now().millisecondsSinceEpoch + delayMs;

          await _localDb.registrarFalloMutacion(
            id: m['id'],
            nextAttemptAt: nextAttemptAt,
            errorMensaje: dioErr.message,
          );
        }
      }
    }
  }

  Future<void> _procesarDatosDirty(String orgId, String profileId) async {
    final ordenes = await _localDb.getOrdenes(orgId: orgId, profileId: profileId);

    for (final orden in ordenes) {
      final ordenId = orden['id'] as String;
      final dirtyDatos = await _localDb.getDirtyDatosForSync(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
      );

      if (dirtyDatos.isEmpty) continue;

      final currentRev = orden['revision'] as int;

      try {
        final response = await _apiClient.patch(
          ApiEndpoints.datosTrabajo(ordenId),
          data: {
            'revision_base': currentRev,
            'valores': dirtyDatos,
          },
        );

        if (response.statusCode == 200) {
          final data = response.data;
          // Limpiar datos dirty confirmados
          await _localDb.clearDirtyDatos(
            orgId: orgId,
            profileId: profileId,
            ordenId: ordenId,
            claves: dirtyDatos.keys.toList(),
          );

          if (data != null && data['revision'] != null) {
            await _localDb.updateOrdenRevisionYEstado(
              orgId: orgId,
              profileId: profileId,
              ordenId: ordenId,
              nuevaRevision: data['revision'],
              nuevoEstado: orden['estado'],
            );
          }
        }
      } on DioException catch (dioErr) {
        if (dioErr.response?.statusCode == 409) {
          // No borrar dirty; el técnico no debe perder su trabajo
        }
      }
    }
  }

  Future<void> _procesarEvidencias(String orgId, String profileId) async {
    final evidencias = await _localDb.getEvidenciasPendientes(orgId: orgId, profileId: profileId);

    for (final ev in evidencias) {
      final id = ev['id'] as String;
      final ordenId = ev['orden_id'] as String;
      final requisitoId = ev['requisito_id'] as String;
      final archivoPath = ev['archivo_path'] as String;
      final sha256 = ev['sha256'] as String;
      final tamanoBytes = ev['tamano_bytes'] as int;
      final mimeType = ev['mime_type'] as String;
      var subidaEstado = ev['subida_estado'] as String;
      var signedUploadUrl = ev['signed_upload_url'] as String?;
      var uploadMethod = ev['upload_method'] as String?;
      var uploadHeadersJson = ev['upload_headers_json'] as String?;
      final dynamic rawAuth = ev['upload_requiere_auth'];
      var uploadRequiereAuth = rawAuth == null ? null : (rawAuth == 1 || rawAuth == true);
      var backendEvidenciaId = ev['backend_evidencia_id'] as String?;

      var registroKey = ev['registro_idempotency_key'] as String?;
      if (registroKey == null || registroKey.isEmpty) {
        registroKey = id;
      }

      var confirmacionKey = ev['confirmacion_idempotency_key'] as String?;
      if (confirmacionKey == null || confirmacionKey.isEmpty) {
        confirmacionKey = const Uuid().v4();
        await _localDb.updateEvidenciaEstado(
          id: id,
          subidaEstado: subidaEstado,
          confirmacionIdempotencyKey: confirmacionKey,
        );
      }

      final file = File(archivoPath);
      if (!await file.exists()) {
        await _localDb.updateEvidenciaEstado(
          id: id,
          subidaEstado: 'error_archivo_inexistente',
          errorMensaje: 'El archivo local de la foto no fue encontrado.',
        );
        continue;
      }

      // Paso 1: Registrar intención de evidencia (o renovar signed URL expirada)
      if (subidaEstado == 'pendiente_registro' || (subidaEstado != 'subido_binario' && subidaEstado != 'confirmada' && signedUploadUrl == null)) {
        try {
          final filename = file.path.split(Platform.pathSeparator).last;
          final response = await _apiClient.post(
            ApiEndpoints.evidenciasTrabajo(ordenId),
            data: {
              'requisito_id': requisitoId,
              'nombre': filename.isNotEmpty ? filename : 'evidencia.jpg',
              'bytes': tamanoBytes,
              'mime_type': mimeType,
              'sha256': sha256,
              'client_mutation_id': registroKey,
            },
            options: Options(
              headers: {
                'Idempotency-Key': registroKey,
              },
            ),
          );

          if (response.statusCode == 201 || response.statusCode == 200) {
            final data = response.data;
            if (data is! Map) continue;

            backendEvidenciaId = data['evidencia_id']?.toString();
            final String estadoArchivo = (data['estado_archivo'] ?? '').toString().toLowerCase();

            // Caso especial contrato: upload == null + estado_archivo RECIBIDO / VERIFICADO
            // La evidencia ya existe y está satisfecha en el servidor; no requiere subida binaria
            final uploadObj = data['upload'];
            if (uploadObj == null && (estadoArchivo == 'recibido' || estadoArchivo == 'verificado')) {
              subidaEstado = 'confirmada';
              await _localDb.updateEvidenciaEstado(
                id: id,
                subidaEstado: 'confirmada',
                backendEvidenciaId: backendEvidenciaId,
              );
              continue; // Evidencia remota satisfecha
            }

            // Descriptor oficial upload
            if (uploadObj is Map) {
              signedUploadUrl = uploadObj['url']?.toString();
              uploadMethod = (uploadObj['method'] ?? 'PUT').toString().toUpperCase();
              uploadRequiereAuth = uploadObj['requiere_auth_dexter'] == true;

              final headersMap = uploadObj['headers'];
              if (headersMap is Map) {
                final Map<String, String> parsedHeaders = {};
                headersMap.forEach((k, v) => parsedHeaders[k.toString()] = v.toString());
                uploadHeadersJson = jsonEncode(parsedHeaders);
              } else {
                uploadHeadersJson = jsonEncode({});
              }

              subidaEstado = 'url_obtenida';

              await _localDb.updateEvidenciaEstado(
                id: id,
                subidaEstado: subidaEstado,
                signedUploadUrl: signedUploadUrl,
                uploadMethod: uploadMethod,
                uploadHeadersJson: uploadHeadersJson,
                uploadRequiereAuth: uploadRequiereAuth,
                backendEvidenciaId: backendEvidenciaId,
              );
            }
          }
        } catch (e) {
          // Error de red: conservar archivo local y reintentar en el siguiente ciclo
          continue;
        }
      }

      // Paso 2: Subir archivo binario según descriptor de upload
      if (subidaEstado == 'url_obtenida' && signedUploadUrl != null) {
        try {
          final bytes = await file.readAsBytes();
          final targetUrl = signedUploadUrl.startsWith('/')
              ? '${ApiEndpoints.baseUrl}$signedUploadUrl'
              : signedUploadUrl;

          final method = (uploadMethod ?? 'PUT').toUpperCase();
          final bool requiereAuth = uploadRequiereAuth == true;

          // Headers exactos del descriptor upload
          final Map<String, dynamic> descriptorHeaders = {};
          if (uploadHeadersJson != null) {
            try {
              final Map<String, dynamic> parsed = jsonDecode(uploadHeadersJson);
              parsed.forEach((k, v) => descriptorHeaders[k] = v.toString());
            } catch (_) {}
          }

          Response uploadRes;

          if (requiereAuth) {
            // upload.requiere_auth_dexter == true
            // Usar cliente Dexter IA autenticado
            uploadRes = await _apiClient.request(
              targetUrl,
              data: Stream.fromIterable([bytes]),
              options: Options(
                method: method,
                headers: {
                  ...descriptorHeaders,
                  if (!descriptorHeaders.containsKey('Content-Type')) 'Content-Type': mimeType,
                  if (!descriptorHeaders.containsKey('Content-Length')) 'Content-Length': bytes.length.toString(),
                },
              ),
            );
          } else {
            // upload.requiere_auth_dexter == false
            // Usar cliente HTTP limpio SIN Authorization Bearer.
            // Usar upload.method y upload.headers exactamente como vienen en el descriptor.
            // No agregar headers de autenticación ni headers propios a una signed URL externa.
            final cleanUploadDio = Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 15),
                sendTimeout: const Duration(seconds: 60),
                receiveTimeout: const Duration(seconds: 15),
              ),
            );

            uploadRes = await cleanUploadDio.request(
              targetUrl,
              data: Stream.fromIterable([bytes]),
              options: Options(
                method: method,
                headers: descriptorHeaders, // Únicamente los headers del descriptor
              ),
            );
          }

          if (uploadRes.statusCode == 200 || uploadRes.statusCode == 204) {
            subidaEstado = 'subido_binario';
            await _localDb.updateEvidenciaEstado(
              id: id,
              subidaEstado: subidaEstado,
            );
          }
        } catch (e) {
          // Timeout o caída de red: conservar archivo local intacto y estado url_obtenida
          // para reintentar oportunamente sin duplicar la evidencia
          await _localDb.updateEvidenciaEstado(
            id: id,
            subidaEstado: 'url_obtenida',
            errorMensaje: 'Timeout o error en subida binaria: $e',
          );
          continue;
        }
      }

      // Paso 3: Confirmar evidencia en backend
      if (subidaEstado == 'subido_binario' && backendEvidenciaId != null) {
        try {
          final confirmRes = await _apiClient.post(
            ApiEndpoints.confirmarEvidencia(ordenId, backendEvidenciaId),
            options: Options(
              headers: {
                'Idempotency-Key': confirmacionKey,
              },
            ),
          );

          if (confirmRes.statusCode == 200) {
            subidaEstado = 'confirmada';
            await _localDb.updateEvidenciaEstado(
              id: id,
              subidaEstado: subidaEstado,
            );
          }
        } catch (e) {
          // Error al confirmar: conservar subido_binario para reintentar confirmación directa
          continue;
        }
      }
    }
  }

  Future<void> _procesarMutacionCompletar(String orgId, String profileId) async {
    final mutaciones = await _localDb.getMutacionesPendientes(orgId: orgId, profileId: profileId);
    final mutacionCompletar = mutaciones.where((m) => m['tipo'] == 'completar').toList();

    for (final m in mutacionCompletar) {
      final ordenId = m['orden_id'] as String;

      // Verificación DAG: No deben quedar datos técnicos dirty para esta orden
      final dirty = await _localDb.getDirtyDatosForSync(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
      );
      if (dirty.isNotEmpty) continue;

      // Verificación DAG: Todas las evidencias obligatorias deben estar confirmadas
      final evidencias = await _localDb.getEvidenciasOrden(
        orgId: orgId,
        profileId: profileId,
        ordenId: ordenId,
      );
      final hayEvidenciasSinConfirmar = evidencias.any((e) => e['subida_estado'] != 'confirmada');
      if (hayEvidenciasSinConfirmar) continue;

      // Todo listo: enviar transición 'completar'
      await _procesarMutacionesTransicion(orgId, profileId, soloNoFinales: false);
    }
  }
}
