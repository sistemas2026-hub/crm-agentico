// Endpoints exactos del contrato API Campo v1 y Auth de Django

class ApiEndpoints {
  // URL base configurada desde variable de entorno de compilación (--dart-define=BACKEND_URL=...)
  // En desarrollo local por defecto usa http://127.0.0.1:8000
  static const String defaultEnvironmentUrl = String.fromEnvironment(
    'BACKEND_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static String baseUrl = defaultEnvironmentUrl;

  // Autenticación (common/views/auth_views.py)
  static String get login => '$baseUrl/api/auth/login/';
  static String get refreshToken => '$baseUrl/api/auth/refresh-token/';
  static String get me => '$baseUrl/api/auth/me/';
  static String get switchOrg => '$baseUrl/api/auth/switch-org/';
  static String get logout => '$baseUrl/api/auth/logout/';

  // Módulo Campo v1 (campo/views.py)
  static String get bootstrap => '$baseUrl/api/campo/bootstrap/';
  static String get trabajos => '$baseUrl/api/campo/trabajos/';
  static String trabajoDetalle(String id) => '$baseUrl/api/campo/trabajos/$id/';
  static String trabajoAcciones(String id) => '$baseUrl/api/campo/trabajos/$id/acciones/';
  static String trabajoDatos(String id) => '$baseUrl/api/campo/trabajos/$id/datos/';
  static String trabajoEvidencias(String id) => '$baseUrl/api/campo/trabajos/$id/evidencias/';
  static String trabajoCompletar(String id) => '$baseUrl/api/campo/trabajos/$id/completar/';
  static String confirmarEvidencia(String trabajoId, String evidenciaId) =>
      '$baseUrl/api/campo/evidencias/$evidenciaId/confirmar/';
  static String evidenciaUrl(String id) => '$baseUrl/api/campo/evidencias/$id/url/';

  // Aliases convenientes
  static String accionTrabajo(String id, String accion) {
    if (accion == 'completar') return trabajoCompletar(id);
    return trabajoAcciones(id);
  }
  static String datosTrabajo(String id) => trabajoDatos(id);
  static String evidenciasTrabajo(String id) => trabajoEvidencias(id);
}
