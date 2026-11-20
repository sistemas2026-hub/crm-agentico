import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../storage/secure_storage_service.dart';
import 'api_endpoints.dart';

/// Qué pasó al pedir una sesión nueva.
///
/// `rechazada` y `sinRespuesta` NO son lo mismo, y confundirlas tiene dos
/// costos opuestos: sacar al técnico de la app cada vez que se queda sin señal
/// o se reinicia el servidor (un despliegue contesta 404 o 502 un rato), o
/// dejarlo adentro para siempre con una sesión muerta.
enum RenovacionDeSesion { renovada, rechazada, sinRespuesta }

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;

  late final Dio _dio;
  final SecureStorageService _storage = SecureStorageService();
  bool _isRefreshing = false;

  /// Marca, en el pedido, que ya es el reintento después de renovar.
  static const String _marcaDeReintento = 'dexter_reintento_tras_renovar';

  /// LA SESIÓN VENCIÓ (28/10/2026): el servidor RECHAZÓ la renovación.
  ///
  /// Medido en producción: un técnico con la app abierta, «sincronizado» en
  /// pantalla, y su última conexión con el servidor horas atrás; la orden que
  /// le asignaron no le llegaba. Con la sesión muerta la app no avisaba nada:
  /// seguía mostrando lo último que había bajado. Esto lo avisa, y quien
  /// escucha (el contenedor de la app) lo saca por el mismo camino que el
  /// cierre de sesión que conserva lo pendiente.
  static final StreamController<void> _sesionVencida =
      StreamController<void>.broadcast();
  static Stream<void> get sesionVencida => _sesionVencida.stream;
  static void avisarSesionVencida() => _sesionVencida.add(null);

  /// Con qué se pide la sesión nueva. Reemplazable en pruebas para simular al
  /// servidor sin red.
  @visibleForTesting
  static Dio Function(String baseUrl) crearDioDeRenovacion =
      (String baseUrl) => Dio(BaseOptions(baseUrl: baseUrl));

  /// Solo un «no» del servidor es un rechazo: 400 (falta el token), 401
  /// (vencido o dado de baja) y 403 (la cuenta ya no puede entrar). Cualquier
  /// otra cosa --sin respuesta, 404 o 5xx mientras se despliega-- no prueba
  /// nada sobre la sesión.
  static RenovacionDeSesion clasificarRespuesta(int? estado) =>
      (estado == 400 || estado == 401 || estado == 403)
          ? RenovacionDeSesion.rechazada
          : RenovacionDeSesion.sinRespuesta;

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
          //  UN REINTENTO NO VUELVE A RENOVAR. Si no, un 403 de permiso
          //  renovaba y reintentaba sin fin; el código anterior cortaba ese
          //  bucle borrando la sesión, que es justo el defecto de arriba.
          final esReintento = error.requestOptions.extra[_marcaDeReintento] == true;
          if ((statusCode == 401 || statusCode == 403) && !_isRefreshing && !esReintento) {
            final isAuthPath = error.requestOptions.path.contains('/api/auth/');
            if (!isAuthPath) {
              _isRefreshing = true;
              final RenovacionDeSesion renovacion;
              try {
                renovacion = await _renovarSesion();
              } finally {
                _isRefreshing = false;
              }
              if (renovacion == RenovacionDeSesion.renovada) {
                final retryOptions = error.requestOptions;
                retryOptions.extra[_marcaDeReintento] = true;
                final token = await _storage.getAccessToken();
                retryOptions.headers['Authorization'] = 'Bearer $token';
                try {
                  final response = await _dio.fetch(retryOptions);
                  return handler.resolve(response);
                } on DioException catch (otra) {
                  //  El reintento falló CON la sesión recién renovada: es un
                  //  403 de permiso de esa ruta, o falta de señal. Ninguno
                  //  dice nada de la sesión. Hasta el 28/10/2026 esto borraba
                  //  las llaves sin avisar: la app quedaba abierta, sin volver
                  //  a hablar con el servidor y marcando «sincronizado».
                  return handler.next(otra);
                }
              }
              if (renovacion == RenovacionDeSesion.rechazada) {
                avisarSesionVencida();
              }
            }
          }
          return handler.next(error);
        },
      ),
    );
  }

  Dio get dio => _dio;

  Future<RenovacionDeSesion> _renovarSesion() async {
    final refreshToken = await _storage.getRefreshToken();
    //  Sin con qué renovar, no hay renovación posible: es un rechazo.
    if (refreshToken == null || refreshToken.isEmpty) {
      return RenovacionDeSesion.rechazada;
    }

    try {
      final baseUrl = await _storage.getBaseUrl();
      final refreshDio = crearDioDeRenovacion(baseUrl);
      final response = await refreshDio.post(
        ApiEndpoints.refreshToken,
        data: {'refresh': refreshToken},
      );

      if (response.statusCode == 200 && response.data is Map) {
        final data = response.data as Map;
        final newAccess = data['access'] as String?;
        final newRefresh = data['refresh'] as String? ?? refreshToken;

        if (newAccess != null) {
          await _storage.saveTokens(
            accessToken: newAccess,
            refreshToken: newRefresh,
          );
          return RenovacionDeSesion.renovada;
        }
      }
      return clasificarRespuesta(response.statusCode);
    } on DioException catch (e) {
      return clasificarRespuesta(e.response?.statusCode);
    } catch (_) {
      return RenovacionDeSesion.sinRespuesta;
    }
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

  /// DELETE **con cuerpo**, que es lo que pide dar de baja un dispositivo: el
  /// token identifica al telefono y no cabe en la ruta --son 160 caracteres y
  /// cambian--. Dio lo permite; muchos clientes HTTP no, y por eso se declara.
  Future<Response<T>> delete<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    return await _dio.delete<T>(
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
