import 'package:dio/dio.dart';
import '../storage/secure_storage_service.dart';
import 'api_endpoints.dart';

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;

  late final Dio _dio;
  final SecureStorageService _storage = SecureStorageService();
  bool _isRefreshing = false;

  ApiClient._internal() {
    _dio = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 20),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          // Si es llamada de login o refresh, no inyectamos token
          if (!options.path.contains('/api/auth/login/') &&
              !options.path.contains('/api/auth/refresh-token/')) {
            final token = await _storage.getAccessToken();
            if (token != null && token.isNotEmpty) {
              options.headers['Authorization'] = 'Bearer $token';
            }

            // NO se manda la organización en una cabecera, y no es un olvido.
            //
            // El tenant se obtiene exclusivamente del JWT firmado que valida
            // el backend: viaja como claim `org_id` dentro del token, que el
            // servidor firma y verifica (`common/middleware/get_company.py`).
            // Una cabecera la elige el cliente, y un cliente es un teléfono
            // en la calle: si el servidor le creyera, cambiar un valor
            // bastaría para leer las órdenes de otra empresa.
            //
            // Hasta acá se enviaba `X-Org-Id`. Ninguna ruta del backend la
            // leía nunca -- se verificó buscándola en todo el servidor -- así
            // que no abría ninguna puerta; pero dejaba escrito que el cliente
            // opina sobre su tenant, y la próxima persona que leyera esto
            // podía creerle. Si algún día hace falta cambiar de empresa, se
            // hace pidiendo un token nuevo (`/api/auth/switch-org/`), no
            // mandando otro valor acá.
          }

          // Asegurar base URL dinámica
          final baseUrl = await _storage.getBaseUrl();
          options.baseUrl = baseUrl;

          return handler.next(options);
        },
        onError: (DioException error, handler) async {
          final statusCode = error.response?.statusCode;
          if ((statusCode == 401 || statusCode == 403) && !_isRefreshing) {
            final isAuthPath = error.requestOptions.path.contains('/api/auth/');
            if (!isAuthPath) {
              _isRefreshing = true;
              try {
                final refreshed = await _refreshToken();
                _isRefreshing = false;
                if (refreshed) {
                  final retryOptions = error.requestOptions;
                  final token = await _storage.getAccessToken();
                  retryOptions.headers['Authorization'] = 'Bearer $token';
                  final response = await _dio.fetch(retryOptions);
                  return handler.resolve(response);
                }
              } catch (e) {
                _isRefreshing = false;
                await _storage.clearSession();
              }
            }
          }
          return handler.next(error);
        },
      ),
    );
  }

  Dio get dio => _dio;

  Future<bool> _refreshToken() async {
    final refreshToken = await _storage.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) return false;

    try {
      final baseUrl = await _storage.getBaseUrl();
      final refreshDio = Dio(BaseOptions(baseUrl: baseUrl));
      final response = await refreshDio.post(
        ApiEndpoints.refreshToken,
        data: {'refresh': refreshToken},
      );

      if (response.statusCode == 200 && response.data != null) {
        final data = response.data;
        final newAccess = data['access'] as String?;
        final newRefresh = data['refresh'] as String? ?? refreshToken;

        if (newAccess != null) {
          await _storage.saveTokens(
            accessToken: newAccess,
            refreshToken: newRefresh,
          );
          return true;
        }
      }
    } catch (_) {}
    return false;
  }

  // Métodos wrapper
  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    return await _dio.get<T>(
      path,
      queryParameters: queryParameters,
      options: options,
    );
  }

  Future<Response<T>> post<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    return await _dio.post<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
    );
  }

  Future<Response<T>> patch<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    return await _dio.patch<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
    );
  }

  Future<Response<T>> put<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    return await _dio.put<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
    );
  }

  Future<Response<T>> request<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    return await _dio.request<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
    );
  }
}
