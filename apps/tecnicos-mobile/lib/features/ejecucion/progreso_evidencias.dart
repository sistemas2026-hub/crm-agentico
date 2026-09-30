/// Cuántas de las fotos que pide la orden ya están tomadas.
///
/// Vive aparte de la pantalla porque es la cuenta que decide dos cosas que el
/// técnico mira antes de cerrar: el contador "2/3" y qué requisito sigue
/// marcado como pendiente. Acá se puede probar sin base de datos ni cámara.
library;

/// Los requisitos que todavía no tienen una captura asociada.
///
/// Un requisito se considera cumplido cuando existe una evidencia con su
/// `requisito_id`. No alcanza con que haya fotos: tienen que ser **de ese**
/// requisito, porque el backend valida uno por uno.
List<Map<String, dynamic>> requisitosPendientes({
  required List<dynamic> requisitos,
  required List<Map<String, dynamic>> capturadas,
}) {
  return <Map<String, dynamic>>[
    for (final dynamic req in requisitos)
      if (!_tieneFoto(req, capturadas)) Map<String, dynamic>.from(req as Map),
  ];
}

/// Cuántos requisitos ya están cubiertos.
int fotosCapturadas({
  required List<dynamic> requisitos,
  required List<Map<String, dynamic>> capturadas,
}) {
  return requisitos.length -
      requisitosPendientes(requisitos: requisitos, capturadas: capturadas).length;
}

/// Si falta alguna foto **obligatoria**. Las opcionales no bloquean el cierre:
/// eso lo decide el backend con `obligatorio`, no la aplicación.
bool faltaEvidenciaObligatoria({
  required List<dynamic> requisitos,
  required List<Map<String, dynamic>> capturadas,
}) {
  return requisitosPendientes(requisitos: requisitos, capturadas: capturadas)
      .any((Map<String, dynamic> req) => req['obligatorio'] == true);
}

bool _tieneFoto(dynamic requisito, List<Map<String, dynamic>> capturadas) {
  final Object? id = (requisito as Map)['id'];
  if (id == null) return false;
  return capturadas.any(
    (Map<String, dynamic> e) => e['requisito_id'] == id,
  );
}
