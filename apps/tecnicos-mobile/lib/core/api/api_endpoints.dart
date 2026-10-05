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

  // Materiales: la custodia del tecnico y lo que gasta.
  static String get kit => '$baseUrl/api/campo/kit/';
  static String get movimientosMaterial =>
      '$baseUrl/api/campo/materiales/movimientos/';
  static String get incidenciasMaterial =>
      '$baseUrl/api/campo/materiales/incidencias/';

  /// El seguimiento de una intervencion: la linea de tiempo y los formularios
  /// que ESE tipo de trabajo declara para cada momento.
  ///
  /// Los campos los decide `WorkTypeVersion`, no la aplicacion: por eso una
  /// empresa puede cambiar lo que se pide sin que haya que publicar una version
  /// nueva de la app.
  /// Las notificaciones de esta persona.
  ///
  /// NO es de campo: vive en `/api/notifications/`, que es el unico
  /// despachador de la plataforma --el mismo que alimenta la campanita de
  /// la web--. Campo era la unica parte que no lo usaba.
  static String get notificaciones => '$baseUrl/api/notifications/';

  /// Marcar una como leida.
  static String notificacionLeida(String id) =>
      '$baseUrl/api/notifications/$id/read/';

  /// Que material toco ESTA orden: comprometido, consumido, devuelto.
  ///
  /// Distinto del kit, que es lo que el tecnico lleva encima para toda la
  /// jornada: con los mismos 150 m de drop hace cinco instalaciones. Esto es
  /// lo que de verdad paso en este trabajo.
  static String materialesDeOrden(String ordenId) =>
      '$baseUrl/api/campo/trabajos/$ordenId/materiales/';

  /// Destrabar un trabajo detenido.
  ///
  /// El estado al que vuelve lo guardo el bloqueo al abrirse: ni la app ni
  /// quien resuelve lo eligen.
  static String resolverBloqueo(String ordenId) =>
      '$baseUrl/api/campo/trabajos/$ordenId/bloqueo/resolver/';

  static String seguimientoDeOrden(String ordenId) =>
      '$baseUrl/api/campo/trabajos/$ordenId/seguimiento/';

  static String get jornada => '$baseUrl/api/campo/jornada/';
  static String get cerrarJornada => '$baseUrl/api/campo/jornada/cerrar/';
  static String trabajoDetalle(String id) => '$baseUrl/api/campo/trabajos/$id/';
  static String trabajoAcciones(String id) =>
      '$baseUrl/api/campo/trabajos/$id/acciones/';
  static String trabajoDatos(String id) =>
      '$baseUrl/api/campo/trabajos/$id/datos/';
  static String trabajoProbarConexion(String id) =>
      '$baseUrl/api/campo/trabajos/$id/probar-conexion/';
  static String trabajoEvidencias(String id) =>
      '$baseUrl/api/campo/trabajos/$id/evidencias/';
  static String trabajoCompletar(String id) =>
      '$baseUrl/api/campo/trabajos/$id/completar/';
  static String confirmarEvidencia(String trabajoId, String evidenciaId) =>
      '$baseUrl/api/campo/evidencias/$evidenciaId/confirmar/';
  static String evidenciaUrl(String id) =>
      '$baseUrl/api/campo/evidencias/$id/url/';

  // Aliases convenientes
  static String accionTrabajo(String id, String accion) {
    if (accion == 'completar') return trabajoCompletar(id);
    return trabajoAcciones(id);
  }

  static String datosTrabajo(String id) => trabajoDatos(id);
  static String evidenciasTrabajo(String id) => trabajoEvidencias(id);
}
