import '../api/api_endpoints.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Lo minimo que hace falta para saber de quien son los datos.
///
/// Existe para que quien solo necesita leer la identidad no dependa del
/// almacenamiento seguro entero -- que habla por un canal de plataforma y no
/// existe en una prueba. Con esto, una prueba pasa una sesion de mentira y
/// mide lo que le importa.
abstract interface class SecureStorageLectura {
  Future<String?> getOrgId();
  Future<String?> getProfileId();
}

class SecureStorageService implements SecureStorageLectura {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(),
  );

  static const _keyAccessToken = 'dexter_access_token';
  static const _keyRefreshToken = 'dexter_refresh_token';
  static const _keyOrgId = 'dexter_current_org_id';
  static const _keyOrgName = 'dexter_current_org_name';
  static const _keyProfileId = 'dexter_profile_id';
  static const _keyUserEmail = 'dexter_user_email';
  static const _keyUserName = 'dexter_user_name';
  static const _keyBaseUrl = 'dexter_api_base_url';

  /// El servidor con el que se compiló la aplicación.
  ///
  /// NO una constante propia. Antes acá vivía un `http://127.0.0.1:8000`
  /// fijo, y quedaban dos valores por defecto distintos: el de compilación
  /// —que llega por `--dart-define=BACKEND_URL=...`— y éste. Cualquier
  /// petición anterior al primer inicio de sesión salía contra el segundo, o
  /// sea contra el propio teléfono, y el error que se ve es "conexión
  /// rechazada" sin ninguna pista de por qué.
  static String get defaultBaseUrl => ApiEndpoints.defaultEnvironmentUrl;

  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _keyAccessToken, value: accessToken);
    await _storage.write(key: _keyRefreshToken, value: refreshToken);
  }

  Future<void> saveSessionData({
    required String orgId,
    required String orgName,
    required String profileId,
    required String email,
    required String name,
  }) async {
    await _storage.write(key: _keyOrgId, value: orgId);
    await _storage.write(key: _keyOrgName, value: orgName);
    await _storage.write(key: _keyProfileId, value: profileId);
    await _storage.write(key: _keyUserEmail, value: email);
    await _storage.write(key: _keyUserName, value: name);
  }

  Future<String?> getAccessToken() async => await _storage.read(key: _keyAccessToken);
  Future<String?> getRefreshToken() async => await _storage.read(key: _keyRefreshToken);
  @override
  Future<String?> getOrgId() async => await _storage.read(key: _keyOrgId);
  Future<String?> getOrgName() async => await _storage.read(key: _keyOrgName);
  @override
  Future<String?> getProfileId() async => await _storage.read(key: _keyProfileId);
  Future<String?> getUserEmail() async => await _storage.read(key: _keyUserEmail);
  Future<String?> getUserName() async => await _storage.read(key: _keyUserName);

  Future<String> getBaseUrl() async {
    final url = await _storage.read(key: _keyBaseUrl);
    return url ?? defaultBaseUrl;
  }

  /// Cambia el servidor y lo aplica en el acto.
  ///
  /// Las dos mitades tienen que moverse juntas. `ApiEndpoints` arma rutas
  /// ABSOLUTAS (`'$baseUrl/api/...'`), y una ruta absoluta le gana al
  /// `baseUrl` que el interceptor de Dio pone en cada pedido. Guardar la URL
  /// sin actualizar esa variable dejaba la pantalla de servidor sin ningún
  /// efecto: se escribía otro dominio, se guardaba, y los pedidos seguían
  /// yendo al que se fijó al compilar.
  Future<void> setBaseUrl(String url) async {
    ApiEndpoints.baseUrl = url;
    await _storage.write(key: _keyBaseUrl, value: url);
  }

  Future<void> clearSession() async {
    await _storage.delete(key: _keyAccessToken);
    await _storage.delete(key: _keyRefreshToken);
    await _storage.delete(key: _keyOrgId);
    await _storage.delete(key: _keyOrgName);
    await _storage.delete(key: _keyProfileId);
    await _storage.delete(key: _keyUserEmail);
    await _storage.delete(key: _keyUserName);
  }

  Future<bool> hasValidSession() async {
    final token = await getAccessToken();
    final orgId = await getOrgId();
    final profileId = await getProfileId();
    return token != null && token.isNotEmpty && orgId != null && profileId != null;
  }
}
