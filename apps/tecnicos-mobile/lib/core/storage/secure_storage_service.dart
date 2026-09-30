import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorageService {
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

  // Servidor local con adb reverse
  static const String defaultBaseUrl = 'http://127.0.0.1:8000';

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
  Future<String?> getOrgId() async => await _storage.read(key: _keyOrgId);
  Future<String?> getOrgName() async => await _storage.read(key: _keyOrgName);
  Future<String?> getProfileId() async => await _storage.read(key: _keyProfileId);
  Future<String?> getUserEmail() async => await _storage.read(key: _keyUserEmail);
  Future<String?> getUserName() async => await _storage.read(key: _keyUserName);

  Future<String> getBaseUrl() async {
    final url = await _storage.read(key: _keyBaseUrl);
    return url ?? defaultBaseUrl;
  }

  Future<void> setBaseUrl(String url) async {
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
