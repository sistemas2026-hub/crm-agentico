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

/// El estado con el que la sincronización marca una evidencia que el servidor
/// ya confirmó. Cualquier otro valor (`pendiente_registro`, `subiendo`, …) es
/// una foto que sigue viviendo solo en el teléfono.
const String estadoEvidenciaConfirmada = 'confirmada';

/// Cuántas de las fotos tomadas **salieron del teléfono**.
///
/// POR QUE SE CUENTA APARTE DE [fotosCapturadas]. Son dos hechos distintos y
/// el técnico decide con los dos: capturada es que la foto existe, enviada es
/// que la empresa la tiene. Confundirlas lleva a cerrar una jornada creyendo
/// que la evidencia ya está del otro lado — y si el teléfono se rompe o se
/// formatea esa noche, no está en ningún lado.
///
/// Se cuenta sobre `subida_estado`, la columna que la propia cola de
/// sincronización escribe (`cola_evidencias`). No se deduce de la presencia de
/// la foto: una foto presente es exactamente el caso que no dice nada.
int fotosEnviadas({required List<Map<String, dynamic>> capturadas}) {
  return capturadas
      .where((Map<String, dynamic> e) =>
          (e['subida_estado'] ?? '').toString() == estadoEvidenciaConfirmada)
      .length;
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
